"""
MODEL ROUTER - Tobi Agent

Premium Chat (#8 P1): a **provider abstraction** over many LLM backends with a
**vault-backed routing config** (global default + per-task overrides + ordered
fallback chain).

- API **keys** stay in the Genesis vault (injected onto ``os.environ`` on unlock);
  here we only read them via ``os.getenv``.
- **Routing prefs** (which model is default / per task / fallback order, plus each
  provider's base_url + chosen models) live in a small ``llm_config`` table — they
  are non-secret, so they don't need the vault to read.
- Fully **backward compatible**: with no config saved, ``get_llm`` falls back to the
  legacy ``PRIMARY_MODEL`` env behaviour (OpenRouter / Claude), so every existing
  caller (``get_llm(task_type).complete(...)``) keeps working unchanged.

Model ids are ``"provider:model"`` (e.g. ``anthropic:claude-opus-4-8``).
"""
import os
import json
import time
import sqlite3
from abc import ABC, abstractmethod
from typing import Optional
from core.env_utils import safe_load_dotenv
safe_load_dotenv()


# Usage tagging (#8 P3): a process-global surface/feature tag the caller sets just before
# an LLM call so the auto-logger can attribute it (chat / agent / research…). Plain module
# state (not a contextvar) so it survives the run_in_executor thread hop the chat uses.
_USAGE_CTX = {"surface": "agent", "feature": ""}


def set_usage_context(surface: str = "agent", feature: str = "") -> dict:
    """Set the usage tag for subsequent LLM calls; returns the previous tag (to restore)."""
    prev = dict(_USAGE_CTX)
    _USAGE_CTX["surface"] = surface or "agent"
    _USAGE_CTX["feature"] = feature or ""
    return prev


# ════════════════════════════════════════════════════════════════════════════
# Clients
# ════════════════════════════════════════════════════════════════════════════
def _norm_finish(raw) -> Optional[str]:
    """Normalize a provider finish/stop reason → 'length' when the output was truncated."""
    if raw in ("length", "max_tokens", "MAX_TOKENS"):
        return "length"
    return raw


class BaseLLMClient(ABC):
    last_usage: dict = {}
    provider: str = "?"
    last_finish_reason: Optional[str] = None  # 'stop' | 'length' | 'tool_calls' | …

    @abstractmethod
    def complete(self, messages: list, system: str = None, max_tokens: int = 2000) -> str:
        pass

    def complete_stream(self, messages: list, system: str = None, max_tokens: int = 2000):
        """Yield text deltas. Default: no native streaming → emit the full reply once.

        Subclasses override with real token streaming; this base impl guarantees any
        client works with the streaming API (callers always get at least one chunk)."""
        yield self.complete(messages, system=system, max_tokens=max_tokens)

    def complete_full(self, messages: list, system: str = None, max_tokens: int = 2000,
                      max_rounds: int = 3) -> str:
        """`complete()` but **never truncated**: if the model stops because it hit the token
        cap (`last_finish_reason == 'length'`), append the partial and ask it to continue,
        repeating up to `max_rounds`. Returns the full reassembled text. The permanent
        cure for mid-sentence cut-offs (#8 v2 P1)."""
        parts: list[str] = []
        msgs = list(messages)
        for _ in range(max(1, max_rounds + 1)):
            out = self.complete(msgs, system=system, max_tokens=max_tokens) or ""
            parts.append(out)
            if self.last_finish_reason != "length":
                break
            msgs = msgs + [
                {"role": "assistant", "content": out},
                {"role": "user", "content": "Continue your previous answer from exactly where it "
                                            "was cut off. Do not repeat anything you already wrote."},
            ]
        return "".join(parts)

    def _log_usage(self, t0: float, text: str = "") -> None:
        """Auto-log this call to llm_usage (real provider tokens, else an estimate)."""
        try:
            from core import usage
            u = self.last_usage or {}
            ptok = u.get("prompt_tokens") or 0
            ctok = u.get("completion_tokens") or estimate_tokens(text)
            usage.log(getattr(self, "provider", "?"), getattr(self, "model", "?"),
                      ptok, ctok, int((time.time() - t0) * 1000),
                      surface=_USAGE_CTX["surface"], feature=_USAGE_CTX["feature"])
        except Exception:
            pass


class OpenRouterClient(BaseLLMClient):
    # Models verified working (May 2026)
    FREE_MODELS = {
        "research":  "nvidia/nemotron-3-super-120b-a12b:free",
        "planning":  "nvidia/nemotron-3-super-120b-a12b:free",
        "ceo_review":"nvidia/nemotron-3-super-120b-a12b:free",
        "writing":   "nvidia/nemotron-3-super-120b-a12b:free",
        "coding":    "nvidia/nemotron-3-super-120b-a12b:free",
        "reporting": "nvidia/nemotron-3-super-120b-a12b:free",
        "simple":    "nvidia/nemotron-3-super-120b-a12b:free",
        "classify":  "nvidia/nemotron-3-super-120b-a12b:free",
        "default":   "nvidia/nemotron-3-super-120b-a12b:free",
    }
    FALLBACK_MODELS = {
        "default": "google/gemma-4-31b-it:free",
    }
    _HEADERS = {
        "HTTP-Referer": "https://github.com/binhvu284/tobi",
        "X-Title": "Tobi Agent",
    }

    def __init__(self, model: str = None, task_type: str = "default"):
        from openai import OpenAI
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY missing in .env")
        self.client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)
        self.model = model or self.FREE_MODELS.get(task_type, self.FREE_MODELS["default"])
        self.provider = "openrouter"
        self.last_usage = {}

    def complete(self, messages, system=None, max_tokens=2000) -> str:
        if system:
            messages = [{"role": "system", "content": system}] + messages
        t0 = time.time()
        try:
            r = self.client.chat.completions.create(
                model=self.model, messages=messages, max_tokens=max_tokens,
                extra_headers=self._HEADERS,
            )
            self.last_usage = _usage_dict(r)
            self.last_finish_reason = _norm_finish(r.choices[0].finish_reason)
            text = r.choices[0].message.content
            self._log_usage(t0, text)
            return text
        except Exception as e:
            if "rate" in str(e).lower() or "429" in str(e):
                fallback = self.FALLBACK_MODELS["default"]
                r = self.client.chat.completions.create(
                    model=fallback, messages=messages, max_tokens=max_tokens,
                    extra_headers=self._HEADERS,
                )
                self.last_usage = _usage_dict(r)
                self.last_finish_reason = _norm_finish(r.choices[0].finish_reason)
                text = r.choices[0].message.content
                self._log_usage(t0, text)
                return text
            raise

    def complete_stream(self, messages, system=None, max_tokens=2000):
        if system:
            messages = [{"role": "system", "content": system}] + messages
        self.last_finish_reason = None
        try:
            stream = self.client.chat.completions.create(
                model=self.model, messages=messages, max_tokens=max_tokens,
                extra_headers=self._HEADERS, stream=True,
            )
            for chunk in stream:
                if not chunk.choices:
                    continue
                if chunk.choices[0].finish_reason:
                    self.last_finish_reason = _norm_finish(chunk.choices[0].finish_reason)
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta
        except Exception:
            yield self.complete(messages, max_tokens=max_tokens)


class ClaudeClient(BaseLLMClient):
    def __init__(self, model: str = "claude-opus-4-20250514",
                 base_url: Optional[str] = None, api_key: Optional[str] = None,
                 provider: str = "anthropic"):
        import anthropic
        # `base_url` lets us point the Anthropic SDK at a Claude-compatible endpoint
        # (e.g. the GLM Coding Plan at https://api.z.ai/api/anthropic).
        kwargs = {"api_key": api_key or os.getenv("ANTHROPIC_API_KEY")}
        if base_url:
            kwargs["base_url"] = base_url
        self.client = anthropic.Anthropic(**kwargs)
        self.model = model
        self.provider = provider
        self.last_usage = {}

    def complete(self, messages, system=None, max_tokens=2000) -> str:
        kwargs = {"model": self.model, "max_tokens": max_tokens, "messages": messages}
        if system:
            kwargs["system"] = system
        t0 = time.time()
        r = self.client.messages.create(**kwargs)
        try:
            self.last_usage = {"prompt_tokens": r.usage.input_tokens,
                               "completion_tokens": r.usage.output_tokens}
        except Exception:
            self.last_usage = {}
        self.last_finish_reason = _norm_finish(getattr(r, "stop_reason", None))
        text = r.content[0].text
        self._log_usage(t0, text)
        return text

    def complete_stream(self, messages, system=None, max_tokens=2000):
        kwargs = {"model": self.model, "max_tokens": max_tokens, "messages": messages}
        if system:
            kwargs["system"] = system
        self.last_finish_reason = None
        try:
            with self.client.messages.stream(**kwargs) as stream:
                for text in stream.text_stream:
                    if text:
                        yield text
                try:
                    self.last_finish_reason = _norm_finish(stream.get_final_message().stop_reason)
                except Exception:
                    pass
        except Exception:
            yield self.complete(messages, system=system, max_tokens=max_tokens)


class OpenAICompatibleClient(BaseLLMClient):
    """Workhorse for any OpenAI-compatible endpoint: OpenAI, Gemini (compat),
    xAI Grok, Ollama (local) and arbitrary custom base_urls."""

    def __init__(self, model: str, base_url: str, api_key: Optional[str] = None,
                 extra_headers: Optional[dict] = None, provider: str = "openai"):
        from openai import OpenAI
        # OpenAI SDK requires a non-empty key string even when the backend ignores it (Ollama).
        self.client = OpenAI(base_url=base_url, api_key=api_key or "no-key-required")
        self.model = model
        self.provider = provider
        self.extra_headers = extra_headers or None
        self.last_usage = {}

    def complete(self, messages, system=None, max_tokens=2000) -> str:
        if system:
            messages = [{"role": "system", "content": system}] + messages
        t0 = time.time()
        r = self.client.chat.completions.create(
            model=self.model, messages=messages, max_tokens=max_tokens,
            extra_headers=self.extra_headers,
        )
        self.last_usage = _usage_dict(r)
        self.last_finish_reason = _norm_finish(r.choices[0].finish_reason)
        text = r.choices[0].message.content
        self._log_usage(t0, text)
        return text

    def complete_stream(self, messages, system=None, max_tokens=2000):
        if system:
            messages = [{"role": "system", "content": system}] + messages
        self.last_finish_reason = None
        try:
            stream = self.client.chat.completions.create(
                model=self.model, messages=messages, max_tokens=max_tokens,
                extra_headers=self.extra_headers, stream=True,
            )
            for chunk in stream:
                if not chunk.choices:
                    continue
                if chunk.choices[0].finish_reason:
                    self.last_finish_reason = _norm_finish(chunk.choices[0].finish_reason)
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta
        except Exception:
            yield self.complete(messages, max_tokens=max_tokens)


class FallbackClient(BaseLLMClient):
    """Try each client in order; on failure fall through to the next. The first to
    answer wins. Powers the configured ordered fallback chain (try A→B→C)."""

    def __init__(self, clients: list):
        self.clients = [c for c in clients if c is not None]
        self.last_usage = {}

    def _pick(self):
        return self.clients[0] if self.clients else None

    def complete(self, messages, system=None, max_tokens=2000) -> str:
        last_err: Optional[Exception] = None
        for c in self.clients:
            try:
                out = c.complete(messages, system=system, max_tokens=max_tokens)
                self.last_usage = getattr(c, "last_usage", {}) or {}
                self.last_finish_reason = getattr(c, "last_finish_reason", None)
                return out
            except Exception as e:  # noqa: BLE001
                last_err = e
                continue
        if last_err:
            raise last_err
        raise RuntimeError("No LLM client available")

    def complete_stream(self, messages, system=None, max_tokens=2000):
        for i, c in enumerate(self.clients):
            try:
                yielded = False
                for delta in c.complete_stream(messages, system=system, max_tokens=max_tokens):
                    yielded = True
                    yield delta
                self.last_usage = getattr(c, "last_usage", {}) or {}
                self.last_finish_reason = getattr(c, "last_finish_reason", None)
                if yielded:
                    return
            except Exception:
                if i == len(self.clients) - 1:
                    raise
                continue


def _usage_dict(r) -> dict:
    try:
        u = r.usage
        return {"prompt_tokens": getattr(u, "prompt_tokens", 0),
                "completion_tokens": getattr(u, "completion_tokens", 0)}
    except Exception:
        return {}


def estimate_tokens(text: str) -> int:
    """Rough token estimate (~4 chars/token). Real tokenizers land in P3."""
    return max(1, len((text or "")) // 4)


# ════════════════════════════════════════════════════════════════════════════
# Provider catalog
# ════════════════════════════════════════════════════════════════════════════
# kind: "anthropic" (native) | "openrouter" (compat + headers/fallback) | "openai" (compat)
PROVIDERS: dict[str, dict] = {
    "anthropic": {
        "label": "Anthropic (Claude)", "kind": "anthropic", "key_env": "ANTHROPIC_API_KEY",
        "base_url": None, "needs_key": True, "editable_base_url": False,
        "models": ["claude-opus-4-8", "claude-sonnet-4-6", "claude-haiku-4-5-20251001"],
    },
    "glm": {
        # GLM Coding Plan (Z.ai) — Claude-compatible endpoint, driven by the Anthropic SDK.
        "label": "GLM · Z.ai (Coding Plan)", "kind": "anthropic", "key_env": "ZAI_API_KEY",
        "base_url": "https://api.z.ai/api/anthropic", "needs_key": True, "editable_base_url": True,
        "models": ["glm-4.6", "glm-4.5", "glm-4.5-air", "glm-4.5-flash"],
    },
    "openai": {
        "label": "OpenAI (GPT)", "kind": "openai", "key_env": "OPENAI_API_KEY",
        "base_url": "https://api.openai.com/v1", "needs_key": True, "editable_base_url": False,
        "models": ["gpt-4o", "gpt-4o-mini", "o3", "o3-mini"],
    },
    "openrouter": {
        "label": "OpenRouter", "kind": "openrouter", "key_env": "OPENROUTER_API_KEY",
        "base_url": "https://openrouter.ai/api/v1", "needs_key": True, "editable_base_url": False,
        "models": ["nvidia/nemotron-3-super-120b-a12b:free", "anthropic/claude-opus-4-8",
                   "openai/gpt-4o", "google/gemini-2.5-pro"],
    },
    "gemini": {
        "label": "Google Gemini", "kind": "openai", "key_env": "GEMINI_API_KEY",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "needs_key": True, "editable_base_url": False,
        "models": ["gemini-2.5-pro", "gemini-2.5-flash"],
    },
    "grok": {
        "label": "xAI Grok", "kind": "openai", "key_env": "XAI_API_KEY",
        "base_url": "https://api.x.ai/v1", "needs_key": True, "editable_base_url": False,
        "models": ["grok-4", "grok-3", "grok-3-mini"],
    },
    "ollama": {
        "label": "Ollama (local)", "kind": "openai", "key_env": None,
        "base_url": "http://localhost:11434/v1", "needs_key": False, "editable_base_url": True,
        "models": [],
    },
    "custom": {
        "label": "Custom (OpenAI-compatible)", "kind": "openai", "key_env": "CUSTOM_LLM_API_KEY",
        "base_url": "", "needs_key": False, "editable_base_url": True,
        "models": [],
    },
}

# Per-model context windows for the energy bar (P3). Pattern-matched, generous defaults.
_CONTEXT_LIMITS = [
    ("claude", 200000), ("gpt-4o", 128000), ("o3", 200000), ("gemini", 1000000),
    ("grok", 131072), ("nemotron", 131072), ("qwen", 32768), ("llama", 131072),
    ("glm-4.6", 200000), ("glm", 131072),
]


def context_limit(model_id: str) -> int:
    name = (model_id or "").lower()
    for frag, lim in _CONTEXT_LIMITS:
        if frag in name:
            return lim
    return 128000


# ════════════════════════════════════════════════════════════════════════════
# Vault-backed routing config (llm_config table — non-secret routing prefs)
# ════════════════════════════════════════════════════════════════════════════
_DEFAULT_CONFIG = {"default_model": "", "task_overrides": {}, "fallback": [], "providers": {}}


def _config_conn() -> sqlite3.Connection:
    from core.database import get_connection
    return get_connection()


def _ensure_config_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS llm_config ("
        "id INTEGER PRIMARY KEY CHECK (id=1), config_json TEXT, updated_at TEXT)"
    )


def load_llm_config() -> dict:
    """The saved routing prefs, with defaults filled in. Lazily creates the table."""
    try:
        conn = _config_conn()
        try:
            _ensure_config_table(conn)
            row = conn.execute("SELECT config_json FROM llm_config WHERE id=1").fetchone()
        finally:
            conn.close()
    except Exception:
        return dict(_DEFAULT_CONFIG)
    cfg = dict(_DEFAULT_CONFIG)
    if row and row[0]:
        try:
            cfg.update(json.loads(row[0]))
        except Exception:
            pass
    cfg.setdefault("task_overrides", {})
    cfg.setdefault("fallback", [])
    cfg.setdefault("providers", {})
    return cfg


def save_llm_config(cfg: dict) -> dict:
    from datetime import datetime, timezone
    clean = {
        "default_model": (cfg.get("default_model") or "").strip(),
        "task_overrides": {k: v for k, v in (cfg.get("task_overrides") or {}).items() if v},
        "fallback": [m for m in (cfg.get("fallback") or []) if m],
        "providers": cfg.get("providers") or {},
    }
    conn = _config_conn()
    try:
        _ensure_config_table(conn)
        conn.execute(
            "INSERT INTO llm_config (id, config_json, updated_at) VALUES (1,?,?) "
            "ON CONFLICT(id) DO UPDATE SET config_json=excluded.config_json, updated_at=excluded.updated_at",
            (json.dumps(clean), datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    finally:
        conn.close()
    return load_llm_config()


def _provider_of(model_id: str) -> tuple[str, str]:
    """Split 'provider:model' → (provider, model). Guess provider when unprefixed."""
    if ":" in model_id and model_id.split(":", 1)[0] in PROVIDERS:
        p, m = model_id.split(":", 1)
        return p, m
    name = model_id.lower()
    if name.startswith("glm"):
        return "glm", model_id
    if name.startswith("claude"):
        return "anthropic", model_id
    if name.startswith("gpt") or name.startswith("o1") or name.startswith("o3"):
        return "openai", model_id
    if name.startswith("gemini"):
        return "gemini", model_id
    if name.startswith("grok"):
        return "grok", model_id
    if "/" in model_id:
        return "openrouter", model_id
    return "openrouter", model_id


def _provider_settings(cfg: dict, provider: str) -> dict:
    spec = dict(PROVIDERS.get(provider, PROVIDERS["custom"]))
    saved = (cfg.get("providers") or {}).get(provider, {})
    if saved.get("base_url"):
        spec["base_url"] = saved["base_url"]
    if saved.get("models"):
        spec["models"] = saved["models"]
    return spec


def build_client(model_id: str, cfg: Optional[dict] = None):
    """Instantiate a client for a 'provider:model' id. Raises if the SDK can't build."""
    cfg = cfg if cfg is not None else load_llm_config()
    provider, model = _provider_of(model_id)
    spec = _provider_settings(cfg, provider)
    if spec["kind"] == "anthropic":
        key = os.getenv(spec["key_env"]) if spec.get("key_env") else None
        return ClaudeClient(model, base_url=spec.get("base_url") or None, api_key=key, provider=provider)
    if spec["kind"] == "openrouter":
        return OpenRouterClient(model=model)
    key = os.getenv(spec["key_env"]) if spec.get("key_env") else None
    return OpenAICompatibleClient(model, spec.get("base_url") or "", key, provider=provider)


def _resolve_model_id(cfg: dict, task_type: str) -> str:
    return (cfg.get("task_overrides", {}) or {}).get(task_type) or cfg.get("default_model") or ""


class ModelRouter:
    def get_client(self, task_type: str = "default") -> BaseLLMClient:
        """Legacy env routing (used only when no llm_config default is set)."""
        primary = os.getenv("PRIMARY_MODEL", "openrouter").lower().strip()

        if primary == "openrouter":
            return OpenRouterClient(task_type=task_type)
        elif primary in ("claude", "opus"):
            return ClaudeClient("claude-opus-4-20250514")
        elif primary in ("sonnet", "claude-sonnet"):
            return ClaudeClient("claude-sonnet-4-20250514")
        elif primary in ("haiku", "claude-haiku"):
            return ClaudeClient("claude-haiku-3-5-20251001")
        elif primary == "auto":
            if os.getenv("ANTHROPIC_API_KEY"):
                model_map = {
                    "research": "claude-opus-4-20250514",
                    "planning": "claude-opus-4-20250514",
                    "ceo_review": "claude-opus-4-20250514",
                    "writing": "claude-sonnet-4-20250514",
                    "coding": "claude-sonnet-4-20250514",
                    "simple": "claude-haiku-3-5-20251001",
                }
                model = model_map.get(task_type, "claude-sonnet-4-20250514")
                try:
                    return ClaudeClient(model)
                except Exception:
                    pass
            return OpenRouterClient(task_type=task_type)
        else:
            return OpenRouterClient(task_type=task_type)


_router = ModelRouter()


def _legacy_client(task_type: str):
    try:
        return _router.get_client(task_type)
    except Exception:
        return None


def get_llm(task_type: str = "default", model: Optional[str] = None) -> BaseLLMClient:
    """Return an LLM client, honouring the vault-backed config:
      - explicit ``model`` ('provider:model') wins (the chat model picker);
      - else per-task override → global default;
      - else the legacy PRIMARY_MODEL env behaviour (nothing configured yet).
    A configured default also appends the ordered fallback chain (+ legacy as a last
    resort) so a single mis-set key never leaves the chat mute."""
    cfg = load_llm_config()
    chosen = (model or "").strip() or _resolve_model_id(cfg, task_type)
    if not chosen:
        return _router.get_client(task_type)

    try:
        primary = build_client(chosen, cfg)
    except Exception:
        primary = None
    chain = [primary]
    for fb in cfg.get("fallback", []):
        if fb and fb != chosen:
            try:
                chain.append(build_client(fb, cfg))
            except Exception:
                pass
    chain.append(_legacy_client(task_type))
    chain = [c for c in chain if c is not None]
    if not chain:
        # Last-ditch: surface the original build error by retrying it.
        return build_client(chosen, cfg)
    if len(chain) == 1:
        return chain[0]
    return FallbackClient(chain)


def llm_complete(prompt: str, task_type: str = "default",
                 system: Optional[str] = None, max_tokens: int = 2000) -> str:
    client = get_llm(task_type)
    return client.complete([{"role": "user", "content": prompt}],
                           system=system, max_tokens=max_tokens)


# ── Vision (Premium Chat #8 P2) ──────────────────────────────────────────────
_VISION_FRAGS = ("claude", "gpt-4o", "gpt-4.1", "gpt-5", "o3", "o4", "gemini", "grok-4", "grok-vision", "llava", "qwen2-vl", "qwen2.5-vl")


def supports_vision(model_id: str) -> bool:
    name = (model_id or "").lower()
    return any(f in name for f in _VISION_FRAGS)


def _split_data_url(data_url: str) -> tuple[str, str]:
    """'data:image/png;base64,XXXX' → ('image/png', 'XXXX')."""
    if data_url.startswith("data:") and "," in data_url:
        head, b64 = data_url.split(",", 1)
        mime = head[5:head.index(";")] if ";" in head else "image/png"
        return mime or "image/png", b64
    return "image/png", data_url


def vision_complete(model_id: str, system: Optional[str], text: str,
                    image_data_urls: list[str], history: Optional[list[dict]] = None,
                    max_tokens: int = 1500) -> str:
    """One multimodal completion (no tool-loop) for image attachments, in the provider's
    native format (Anthropic image blocks / OpenAI image_url). Raises on transport error."""
    provider, _ = _provider_of(model_id)
    client = build_client(model_id)
    msgs = list(history or [])
    if provider == "anthropic":
        content: list = [{"type": "text", "text": text or "Please look at the attached image(s)."}]
        for url in image_data_urls:
            mime, b64 = _split_data_url(url)
            content.append({"type": "image", "source": {"type": "base64", "media_type": mime, "data": b64}})
    else:  # OpenAI-compatible (OpenAI / Gemini / Grok / custom)
        content = [{"type": "text", "text": text or "Please look at the attached image(s)."}]
        for url in image_data_urls:
            content.append({"type": "image_url", "image_url": {"url": url}})
    msgs.append({"role": "user", "content": content})
    return client.complete(msgs, system=system, max_tokens=max_tokens)


# ════════════════════════════════════════════════════════════════════════════
# Introspection for the Models config page
# ════════════════════════════════════════════════════════════════════════════
def provider_catalog() -> list[dict]:
    """Every provider + whether its key is present in the environment + its
    configured base_url/models. Drives the Models settings page."""
    cfg = load_llm_config()
    out = []
    for pid, spec in PROVIDERS.items():
        saved = (cfg.get("providers") or {}).get(pid, {})
        key_env = spec.get("key_env")
        out.append({
            "id": pid,
            "label": spec["label"],
            "kind": spec["kind"],
            "key_env": key_env,
            "needs_key": spec["needs_key"],
            "key_present": bool(os.getenv(key_env)) if key_env else True,
            "editable_base_url": spec["editable_base_url"],
            "base_url": saved.get("base_url") or spec.get("base_url") or "",
            "enabled": saved.get("enabled", True),
            "models": saved.get("models") or spec.get("models") or [],
        })
    return out


def available_models() -> list[dict]:
    """Flattened 'provider:model' list for every provider that's usable right now
    (key present or no key needed, and not disabled). Powers the chat model picker."""
    cfg = load_llm_config()
    out = []
    for p in provider_catalog():
        if not p["enabled"]:
            continue
        if p["needs_key"] and not p["key_present"]:
            continue
        for m in p["models"]:
            mid = f"{p['id']}:{m}"
            out.append({"id": mid, "provider": p["id"], "model": m,
                        "label": f"{p['label']} · {m}", "context": context_limit(mid)})
    return out


def discover_models(provider: str) -> dict:
    """Best-effort live model list for a provider; persists into config on success.
    Falls back to the catalog defaults when the network/SDK can't reach it."""
    cfg = load_llm_config()
    spec = _provider_settings(cfg, provider)
    models: list[str] = []
    try:
        if provider == "ollama":
            import requests
            base = (spec.get("base_url") or "http://localhost:11434/v1").rstrip("/")
            base = base[:-3] if base.endswith("/v1") else base  # tags live off /api, not /v1
            r = requests.get(f"{base}/api/tags", timeout=6)
            models = [m["name"] for m in r.json().get("models", []) if m.get("name")]
        elif provider == "openrouter":
            import requests
            r = requests.get("https://openrouter.ai/api/v1/models", timeout=8)
            models = [m["id"] for m in r.json().get("data", []) if m.get("id")][:120]
        else:
            client = build_client(f"{provider}:_discover", cfg)
            raw = client.client.models.list()
            models = [m.id for m in getattr(raw, "data", [])][:120]
    except Exception:
        models = []
    if not models:
        return {"ok": False, "models": spec.get("models") or PROVIDERS.get(provider, {}).get("models", [])}
    providers = dict(cfg.get("providers") or {})
    pcfg = dict(providers.get(provider) or {})
    pcfg["models"] = models
    providers[provider] = pcfg
    cfg["providers"] = providers
    save_llm_config(cfg)
    return {"ok": True, "models": models}


if __name__ == "__main__":
    print("=== Tobi Model Router ===")
    print(f"PRIMARY_MODEL: {os.getenv('PRIMARY_MODEL', 'openrouter')}")
    print(f"Config default: {load_llm_config().get('default_model') or '(legacy env)'}")
    result = llm_complete("Say: Tobi is online", task_type="simple")
    print(f"Test response: {result}")

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
import sqlite3
from typing import Optional
from core.env_utils import safe_load_dotenv
safe_load_dotenv()

# Provider clients live in core/llm_clients/* (Phase 4 refactor); this module keeps the
# routing/config concerns. They are imported back into this namespace so every existing
# call site keeps working unchanged (e.g. ``from core.model_router import ClaudeClient``,
# ``model_router.FallbackClient``, ``from core.model_router import estimate_tokens``).
#
# Per-turn usage attribution lives in llm_clients.base so the clients and the router share
# ONE ContextVar. Callers that cross an executor boundary must set the context inside that
# worker (``run_with_usage_context`` does this); concurrent turns no longer race through one
# process-global dictionary.
from core.llm_clients.base import (  # noqa: F401,E402 - re-exported for callers
    DEFAULT_TIMEOUT_S, BaseLLMClient, _norm_finish, _usage_dict, _USAGE_CTX,
    estimate_tokens, get_usage_context, run_with_usage_context, set_usage_context,
)
from core.llm_clients.claude import ClaudeClient  # noqa: F401,E402
from core.llm_clients.codex import CodexClient  # noqa: F401,E402
from core.llm_clients.fallback import FallbackClient  # noqa: F401,E402
from core.llm_clients.openai_compat import OpenAICompatibleClient  # noqa: F401,E402
from core.llm_clients.openrouter import OpenRouterClient  # noqa: F401,E402








# ════════════════════════════════════════════════════════════════════════════
# Clients
# ════════════════════════════════════════════════════════════════════════════


















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
    "codex": {
        # OpenAI Codex — auto-detects auth: ChatGPT subscription token (chatgpt.com
        # backend) or platform API key (api.openai.com). Run `codex login` or set
        # CODEX_ACCESS_TOKEN / OPENAI_API_KEY.
        "label": "OpenAI Codex", "kind": "codex", "key_env": "CODEX_ACCESS_TOKEN",
        "base_url": "https://chatgpt.com/backend-api/codex", "needs_key": True, "editable_base_url": False,
        "models": ["gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna", "gpt-5.6", "gpt-5.5", "gpt-5.4-mini"],
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

def context_limit(model_id: str) -> int:
    """Per-model context window for the energy bar (P3). Single source of truth: delegates
    to the model_capabilities registry (#14) so the two can't diverge (#14 follow-up)."""
    from core.model_capabilities import context_window
    return context_window(model_id)


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
    if "codex" in name:
        return "codex", model_id
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
    if spec["kind"] == "codex":
        key = os.getenv(spec["key_env"]) if spec.get("key_env") else None
        return CodexClient(model, api_key=key)
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


def get_escalation_llm(current_model: Optional[str] = None) -> tuple[Optional[BaseLLMClient], Optional[str]]:
    """Return one explicitly configured stronger/fallback client for malformed output.

    This is intentionally separate from transport fallback: callers can disclose the model
    switch and invoke it only before any valid owner-facing response has been committed.
    """
    cfg = load_llm_config()
    current = (current_model or "").strip()
    candidates = list(cfg.get("fallback") or [])
    default = (cfg.get("default_model") or "").strip()
    if default:
        candidates.append(default)
    seen: set[str] = set()
    for candidate in candidates:
        candidate = str(candidate or "").strip()
        if not candidate or candidate == current or candidate in seen:
            continue
        seen.add(candidate)
        try:
            return build_client(candidate, cfg), candidate
        except Exception:
            continue
    return None, None


def llm_complete(prompt: str, task_type: str = "default",
                 system: Optional[str] = None, max_tokens: int = 2000) -> str:
    client = get_llm(task_type)
    return client.complete([{"role": "user", "content": prompt}],
                           system=system, max_tokens=max_tokens)


# ── Vision (Premium Chat #8 P2 · registry-backed since #14) ──────────────────
def supports_vision(model_id: str) -> bool:
    """Delegates to the local capability registry (#14). Kept here so every existing
    caller (`model_router.supports_vision(...)`) keeps working unchanged."""
    from core import model_capabilities
    return model_capabilities.supports_vision(model_id)


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
        _kv = os.getenv(key_env) if key_env else None
        # Codex has multiple auth paths — check all of them
        if pid == "codex" and not _kv:
            _kv = (os.getenv("CODEX_API_KEY")
                   or os.getenv("OPENAI_API_KEY")
                   or CodexClient._read_codex_auth())
        out.append({
            "id": pid,
            "label": spec["label"],
            "kind": spec["kind"],
            "key_env": key_env,
            "needs_key": spec["needs_key"],
            "key_present": bool(_kv) if key_env else True,
            "key_last4": _kv[-4:] if _kv else None,   # censored active key for the card
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


def first_vision_model(exclude: Optional[str] = None) -> Optional[str]:
    """An available (key-present) vision-capable model id, for auto-fallback when the chat's
    selected model can't see images (#14) — so the owner never has to switch models just to
    read a screenshot. Prefers Claude → GPT-4o → Gemini → Grok → any other vision model."""
    vis = [m["id"] for m in available_models()
           if supports_vision(m["id"]) and m["id"] != exclude]
    if not vis:
        return None
    prefs = ("anthropic:", "openai:gpt-4o", "gemini:", "openai:", "grok:")
    for pref in prefs:
        for mid in vis:
            if mid.startswith(pref):
                return mid
    return vis[0]


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

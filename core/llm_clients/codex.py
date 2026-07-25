"""Codex CLI provider client — extracted from core/model_router.py (Phase 4).

Verbatim move; behavior identical. Re-exported by core.model_router.
"""
import os
import time
from typing import Optional  # noqa: F401 - used in signatures

from core.llm_clients.base import BaseLLMClient, _norm_finish
class CodexClient(BaseLLMClient):
    """OpenAI Codex via ChatGPT subscription or platform API key.

    Two auth paths (auto-detected):
      1. **ChatGPT subscription** (Plus/Pro) — paste the ``access_token`` from
         ``~/.codex/auth.json`` (after ``codex login``) into the vault as
         ``CODEX_ACCESS_TOKEN``. Calls ``chatgpt.com/backend-api/codex/responses``.
      2. **API key** — set ``OPENAI_API_KEY`` (or ``CODEX_API_KEY``). Calls the
         standard ``api.openai.com/v1/responses`` endpoint. Billed to your
         platform account, no subscription needed.

    If neither is set, tries to auto-read ``~/.codex/auth.json``.

    Optional ``CODEX_CHATGPT_ACCOUNT_ID`` routes subscription calls to a workspace.
    """

    SUBSCRIPTION_BASE = "https://chatgpt.com/backend-api/codex"
    API_BASE = "https://api.openai.com/v1"

    def __init__(self, model: str, api_key: Optional[str] = None,
                 account_id: Optional[str] = None):
        from openai import OpenAI

        token = api_key or os.getenv("CODEX_ACCESS_TOKEN") or os.getenv("CODEX_API_KEY")
        account_id = (account_id or os.getenv("CODEX_CHATGPT_ACCOUNT_ID") or "").strip() or None

        # Auto-read $CODEX_HOME/auth.json (or ~/.codex/auth.json) as a last resort
        if not token:
            token = self._read_codex_auth()
            if token and not account_id:
                account_id = self._read_codex_account_id()

        if not token:
            # Try standard OPENAI_API_KEY → API-key path
            openai_key = os.getenv("OPENAI_API_KEY", "")
            if openai_key:
                token = openai_key
                self.base_url = self.API_BASE
            else:
                raise ValueError(
                    "Codex auth missing. Either:\n"
                    "  1. Run `codex login` (auto-reads ~/.codex/auth.json), OR\n"
                    "  2. Set CODEX_ACCESS_TOKEN in the vault, OR\n"
                    "  3. Set OPENAI_API_KEY for platform API billing."
                )
        else:
            # If the token looks like a standard OpenAI key (sk-...), use the API endpoint.
            # Otherwise it's a ChatGPT session token → use the subscription backend.
            if token.startswith("sk-"):
                self.base_url = self.API_BASE
            else:
                self.base_url = self.SUBSCRIPTION_BASE

        default_headers = {"chatgpt-account-id": account_id} if account_id else None
        self.client = OpenAI(base_url=self.base_url, api_key=token,
                             default_headers=default_headers)
        self.account_id = account_id
        self.model = model
        self.provider = "codex"
        self.last_usage = {}

    @staticmethod
    def _read_codex_auth() -> Optional[str]:
        """Read the access_token from the Codex CLI auth file.
        Checks $CODEX_HOME/auth.json first, then ~/.codex/auth.json.
        Handles both flat ({access_token: ...}) and nested ({tokens: {access_token: ...}}) formats.
        """
        import json
        # Determine the auth file path: $CODEX_HOME takes precedence over the default
        codex_home = os.getenv("CODEX_HOME", "")
        candidates = []
        if codex_home:
            candidates.append(os.path.join(codex_home, "auth.json"))
        candidates.append(os.path.expanduser("~/.codex/auth.json"))
        for path in candidates:
            try:
                if not os.path.exists(path):
                    continue
                with open(path) as f:
                    data = json.load(f)
                # Nested format (codex-cli ≥ 0.1x): {tokens: {access_token, refresh_token, account_id}}
                tokens = data.get("tokens")
                if isinstance(tokens, dict) and tokens.get("access_token"):
                    return tokens["access_token"]
                # Flat format (older): {access_token: ...} or {api_key: ...}
                return data.get("access_token") or data.get("api_key") or None
            except Exception:
                continue
        return None

    @staticmethod
    def _read_codex_account_id() -> Optional[str]:
        """Read the ChatGPT account_id from the Codex CLI auth file."""
        import json
        codex_home = os.getenv("CODEX_HOME", "")
        candidates = []
        if codex_home:
            candidates.append(os.path.join(codex_home, "auth.json"))
        candidates.append(os.path.expanduser("~/.codex/auth.json"))
        for path in candidates:
            try:
                if not os.path.exists(path):
                    continue
                with open(path) as f:
                    data = json.load(f)
                tokens = data.get("tokens")
                if isinstance(tokens, dict) and tokens.get("account_id"):
                    return tokens["account_id"]
                return data.get("account_id") or None
            except Exception:
                continue
        return None

    @staticmethod
    def _to_input(messages: list) -> list:
        items = []
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            if isinstance(content, list):
                # Convert OpenAI chat-format blocks → Responses API blocks
                # (text → input_text, image_url → input_image).
                converted = []
                for block in content:
                    btype = block.get("type")
                    if btype == "text":
                        converted.append({"type": "input_text", "text": block.get("text", "")})
                    elif btype == "image_url":
                        url = (block.get("image_url") or {}).get("url", "")
                        converted.append({"type": "input_image", "image_url": url})
                    else:
                        converted.append(block)
                items.append({"role": role, "content": converted})
            else:
                items.append({"role": role, "content": [{"type": "input_text", "text": str(content)}]})
        return items

    def complete(self, messages, system=None, max_tokens=2000) -> str:
        t0 = time.time()
        kwargs = {
            "model": self.model,
            "input": self._to_input(messages),
            "max_output_tokens": max_tokens,
        }
        if system:
            kwargs["instructions"] = system
        r = self.client.responses.create(**kwargs)
        try:
            self.last_usage = {
                "prompt_tokens": getattr(r.usage, "input_tokens", 0),
                "completion_tokens": getattr(r.usage, "output_tokens", 0),
            }
        except Exception:
            self.last_usage = {}
        self.last_finish_reason = _norm_finish(getattr(r, "status", None))
        text = getattr(r, "output_text", "") or ""
        self._log_usage(t0, text)
        return text

    def complete_stream(self, messages, system=None, max_tokens=2000):
        kwargs = {
            "model": self.model,
            "input": self._to_input(messages),
            "max_output_tokens": max_tokens,
            "stream": True,
        }
        if system:
            kwargs["instructions"] = system
        self.last_finish_reason = None
        self.last_usage = {}
        t0 = time.time(); acc = ""
        try:
            stream = self.client.responses.create(**kwargs)
            for event in stream:
                et = getattr(event, "type", "")
                if et == "response.output_text.delta":
                    delta = getattr(event, "delta", "") or ""
                    if delta:
                        acc += delta
                        yield delta
                elif et == "response.completed":
                    final = getattr(event, "response", None)
                    try:
                        self.last_usage = {
                            "prompt_tokens": getattr(final.usage, "input_tokens", 0),
                            "completion_tokens": getattr(final.usage, "output_tokens", 0),
                        }
                    except Exception:
                        pass
                    self.last_finish_reason = "stop"
            if acc or self.last_usage:
                self._log_usage(t0, acc)
        except Exception:
            yield self.complete(messages, system=system, max_tokens=max_tokens)

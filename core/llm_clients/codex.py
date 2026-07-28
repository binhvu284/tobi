"""Codex CLI provider client — extracted from core/model_router.py (Phase 4).

Verbatim move; behavior identical. Re-exported by core.model_router.
"""
import base64
import hashlib
import json
import os
import time
from typing import Any, Optional  # noqa: F401 - used in signatures

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
    SUBSCRIPTION_UNSUPPORTED_MODELS = {"gpt-5.6"}

    def __init__(self, model: str, api_key: Optional[str] = None,
                 account_id: Optional[str] = None):
        token, account_id, source = self._resolve_auth(api_key, account_id)
        if not token:
            raise ValueError(
                "Codex auth missing. Either:\n"
                "  1. Run `codex login` (auto-reads ~/.codex/auth.json), OR\n"
                "  2. Set CODEX_ACCESS_TOKEN in the vault, OR\n"
                "  3. Set OPENAI_API_KEY for platform API billing."
            )
        self.model = model
        self.provider = "codex"
        self.last_usage = {}
        self.auth_source = source
        self.token_expires_at = self._jwt_expiry(token)
        self._configure_transport(token, account_id)

    @staticmethod
    def _jwt_expiry(token: str | None) -> Optional[int]:
        """Return a JWT expiry without validating or exposing the credential."""
        if not token or token.startswith("sk-"):
            return None
        try:
            payload = token.split(".")[1]
            payload += "=" * (-len(payload) % 4)
            value = json.loads(base64.urlsafe_b64decode(payload.encode()))
            return int(value["exp"]) if value.get("exp") is not None else None
        except (IndexError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            return None

    @classmethod
    def _resolve_auth(
        cls, api_key: Optional[str] = None, account_id: Optional[str] = None
    ) -> tuple[Optional[str], Optional[str], str]:
        """Prefer the rotating login when it expires later than a copied token."""
        configured = api_key or os.getenv("CODEX_ACCESS_TOKEN") or os.getenv("CODEX_API_KEY")
        login = cls._read_codex_auth()
        source = "configured" if configured else ""
        token = configured

        configured_exp = cls._jwt_expiry(configured)
        login_exp = cls._jwt_expiry(login)
        if (
            configured
            and not configured.startswith("sk-")
            and login
            and login_exp is not None
            and configured_exp is not None
            and login_exp > configured_exp
        ):
            token, source = login, "codex_login"
        elif not configured and login:
            token, source = login, "codex_login"

        resolved_account = (
            account_id or os.getenv("CODEX_CHATGPT_ACCOUNT_ID") or ""
        ).strip() or None
        if source == "codex_login" and not account_id:
            resolved_account = cls._read_codex_account_id() or resolved_account

        if not token:
            platform_key = os.getenv("OPENAI_API_KEY", "")
            if platform_key:
                token, source = platform_key, "openai_api_key"
        return token, resolved_account, source

    @classmethod
    def authentication_problem(cls, api_key: Optional[str] = None) -> str:
        """Return an offline credential problem suitable for Developer preflight."""
        token, _, _ = cls._resolve_auth(api_key)
        if not token:
            return "Codex authentication is missing. Run `codex login` or configure a platform API key."
        expiry = cls._jwt_expiry(token)
        if expiry is not None and expiry <= int(time.time()):
            return "Codex authentication has expired. Run `codex login` before starting the workflow."
        return ""

    @classmethod
    def uses_subscription_auth(cls, api_key: Optional[str] = None) -> bool:
        token, _, _ = cls._resolve_auth(api_key)
        return bool(token and not token.startswith("sk-"))

    def _configure_transport(self, token: str, account_id: Optional[str]) -> None:
        from openai import OpenAI

        self.base_url = self.API_BASE if token.startswith("sk-") else self.SUBSCRIPTION_BASE
        default_headers = {"chatgpt-account-id": account_id} if account_id else None
        self.client = OpenAI(
            base_url=self.base_url,
            api_key=token,
            default_headers=default_headers,
        )
        self.account_id = account_id
        self._token_fingerprint = hashlib.sha256(token.encode()).hexdigest()
        self.token_expires_at = self._jwt_expiry(token)

    @staticmethod
    def _is_authentication_error(exc: Exception) -> bool:
        status = getattr(exc, "status_code", None)
        if status is None:
            status = getattr(getattr(exc, "response", None), "status_code", None)
        return status == 401 or type(exc).__name__ == "AuthenticationError"

    def _refresh_from_codex_login(self) -> bool:
        """Rebuild the transport once when Codex CLI has rotated its login."""
        token = self._read_codex_auth()
        if not token:
            return False
        fingerprint = hashlib.sha256(token.encode()).hexdigest()
        if fingerprint == getattr(self, "_token_fingerprint", ""):
            return False
        expiry = self._jwt_expiry(token)
        if expiry is not None and expiry <= int(time.time()):
            return False
        account_id = self._read_codex_account_id() or self.account_id
        self._configure_transport(token, account_id)
        self.auth_source = "codex_login_retry"
        return True

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

    @property
    def on_subscription(self) -> bool:
        """True when talking to the ChatGPT backend rather than the platform API.

        The two speak the same Responses API but do not accept the same request. The
        subscription backend rejects `store=true`, rejects a non-streaming call, and rejects
        `max_output_tokens` outright -- so a plain `responses.create` fails there with a 400
        that reads like an auth or model problem. That is how acceptance review appeared as
        `AuthenticationError` while the credentials were valid the whole time.
        """
        return "chatgpt.com" in (self.base_url or "")

    def _request_kwargs(self, messages, system, max_tokens, *, stream: bool) -> dict:
        kwargs: dict = {"model": self.model, "input": self._to_input(messages)}
        if stream:
            kwargs["stream"] = True
        if self.on_subscription:
            kwargs["store"] = False          # required; the default true is rejected
            kwargs["stream"] = True          # required; non-streaming is rejected
            # max_output_tokens is an unsupported parameter here, not merely ignored.
        else:
            kwargs["max_output_tokens"] = max_tokens
        if system:
            kwargs["instructions"] = system
        return kwargs

    def _consume(self, stream) -> tuple[str, Any, Any]:
        """Accumulate a Responses stream into (text, usage, status)."""
        text, usage, status = "", None, None
        for event in stream:
            kind = getattr(event, "type", "")
            if kind == "response.output_text.delta":
                text += getattr(event, "delta", "") or ""
            elif kind in ("response.completed", "response.incomplete", "response.failed"):
                response = getattr(event, "response", None)
                usage = getattr(response, "usage", None)
                status = getattr(response, "status", None)
        return text, usage, status

    def complete(self, messages, system=None, max_tokens=2000) -> str:
        for auth_attempt in range(2):
            t0 = time.time()
            try:
                kwargs = self._request_kwargs(messages, system, max_tokens, stream=False)
                if kwargs.get("stream"):
                    text, usage, status = self._consume(self.client.responses.create(**kwargs))
                else:
                    response = self.client.responses.create(**kwargs)
                    text = getattr(response, "output_text", "") or ""
                    usage = getattr(response, "usage", None)
                    status = getattr(response, "status", None)
                try:
                    self.last_usage = {
                        "prompt_tokens": getattr(usage, "input_tokens", 0),
                        "completion_tokens": getattr(usage, "output_tokens", 0),
                    }
                except Exception:
                    self.last_usage = {}
                self.last_finish_reason = _norm_finish(status)
                self._log_usage(t0, text)
                return text
            except Exception as exc:
                if (
                    auth_attempt == 0
                    and self._is_authentication_error(exc)
                    and self._refresh_from_codex_login()
                ):
                    self._log_failure(t0, exc)
                    continue
                raise
        raise RuntimeError("Codex authentication recovery exhausted")

    def complete_stream(self, messages, system=None, max_tokens=2000):
        # Same divergence as `complete`: the subscription backend rejects both `store=true`
        # and `max_output_tokens`, so streaming was equally unusable there.
        self.last_finish_reason = None
        self.last_usage = {}
        auth_retried = False
        while True:
            kwargs = self._request_kwargs(messages, system, max_tokens, stream=True)
            t0 = time.time()
            acc = ""
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
                return
            except Exception as exc:
                if (
                    not acc
                    and not auth_retried
                    and self._is_authentication_error(exc)
                    and self._refresh_from_codex_login()
                ):
                    self._log_failure(t0, exc)
                    auth_retried = True
                    continue
                if acc:
                    # Never concatenate a replacement response after visible output.
                    raise
                yield self.complete(messages, system=system, max_tokens=max_tokens)
                return

"""Ordered fallback chain client — extracted from core/model_router.py (Phase 4).

Tries each client in turn; behavior identical. Re-exported by core.model_router.
"""
import time
from typing import Optional  # noqa: F401 - used in signatures

from core.llm_clients.base import BaseLLMClient, _USAGE_CTX


class FallbackClient(BaseLLMClient):
    """Try each client in order; on failure fall through to the next. The first to
    answer wins. Powers the configured ordered fallback chain (try A→B→C)."""

    def __init__(self, clients: list, requested_model: str = ""):
        self.clients = [c for c in clients if c is not None]
        self.requested_model = requested_model
        self.last_usage = {}
        self.actual_model_id: Optional[str] = None
        self.fallback_reason: Optional[str] = None
        self.attempt_count = 0

    def _pick(self):
        return self.clients[0] if self.clients else None

    def complete(self, messages, system=None, max_tokens=2000) -> str:
        last_err: Optional[Exception] = None
        first_error: Optional[str] = None
        for index, c in enumerate(self.clients, 1):
            self.attempt_count = index
            previous = dict(_USAGE_CTX.get())
            reason = first_error or ""
            merged = dict(previous)
            merged.update({
                "requested_model": self.requested_model or previous.get("requested_model", ""),
                "attempt": index,
                "fallback_reason": reason,
            })
            token = _USAGE_CTX.set(merged)
            t0 = time.time()
            try:
                out = c.complete(messages, system=system, max_tokens=max_tokens)
                self.last_usage = getattr(c, "last_usage", {}) or {}
                self.last_finish_reason = getattr(c, "last_finish_reason", None)
                self.actual_model_id = f"{getattr(c, 'provider', '?')}:{getattr(c, 'model', '?')}"
                self.fallback_reason = reason or None
                return out
            except Exception as e:  # noqa: BLE001
                last_err = e
                error_code = type(e).__name__
                if first_error is None:
                    first_error = f"{getattr(c, 'provider', 'provider')}:{error_code}"
                c._log_failure(t0, e)
                continue
            finally:
                _USAGE_CTX.reset(token)
        if last_err:
            raise last_err
        raise RuntimeError("No LLM client available")

    def complete_stream(self, messages, system=None, max_tokens=2000):
        first_error: Optional[str] = None
        for i, c in enumerate(self.clients):
            yielded = False
            attempt = i + 1
            self.attempt_count = attempt
            previous = dict(_USAGE_CTX.get())
            reason = first_error or ""
            merged = dict(previous)
            merged.update({
                "requested_model": self.requested_model or previous.get("requested_model", ""),
                "attempt": attempt,
                "fallback_reason": reason,
            })
            token = _USAGE_CTX.set(merged)
            t0 = time.time()
            try:
                for delta in c.complete_stream(messages, system=system, max_tokens=max_tokens):
                    yielded = True
                    yield delta
                self.last_usage = getattr(c, "last_usage", {}) or {}
                self.last_finish_reason = getattr(c, "last_finish_reason", None)
                if yielded:
                    self.actual_model_id = f"{getattr(c, 'provider', '?')}:{getattr(c, 'model', '?')}"
                    self.fallback_reason = reason or None
                    return
                raise RuntimeError("provider returned an empty stream")
            except Exception as exc:
                if first_error is None:
                    first_error = f"{getattr(c, 'provider', 'provider')}:{type(exc).__name__}"
                c._log_failure(t0, exc)
                if yielded:
                    raise
                if i == len(self.clients) - 1:
                    raise
                continue
            finally:
                _USAGE_CTX.reset(token)

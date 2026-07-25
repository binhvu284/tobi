"""Ordered fallback chain client — extracted from core/model_router.py (Phase 4).

Tries each client in turn; behavior identical. Re-exported by core.model_router.
"""
from typing import Optional  # noqa: F401 - used in signatures

from core.llm_clients.base import BaseLLMClient
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
            yielded = False
            try:
                for delta in c.complete_stream(messages, system=system, max_tokens=max_tokens):
                    yielded = True
                    yield delta
                self.last_usage = getattr(c, "last_usage", {}) or {}
                self.last_finish_reason = getattr(c, "last_finish_reason", None)
                if yielded:
                    return
            except Exception:
                if yielded:
                    raise
                if i == len(self.clients) - 1:
                    raise
                continue

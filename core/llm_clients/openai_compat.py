"""OpenAI-compatible provider client — extracted from core/model_router.py (Phase 4).

Verbatim move; behavior identical. Re-exported by core.model_router.
"""
import time
from typing import Optional  # noqa: F401 - used in signatures

from core.llm_clients.base import (DEFAULT_TIMEOUT_S, BaseLLMClient, _norm_finish,
                                   _usage_dict)
class OpenAICompatibleClient(BaseLLMClient):
    """Workhorse for any OpenAI-compatible endpoint: OpenAI, Gemini (compat),
    xAI Grok, Ollama (local) and arbitrary custom base_urls."""

    def __init__(self, model: str, base_url: str, api_key: Optional[str] = None,
                 extra_headers: Optional[dict] = None, provider: str = "openai"):
        from openai import OpenAI
        # OpenAI SDK requires a non-empty key string even when the backend ignores it (Ollama).
        self.client = OpenAI(base_url=base_url, api_key=api_key or "no-key-required",
                             timeout=DEFAULT_TIMEOUT_S)
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
        self.last_usage = {}
        t0 = time.time(); acc = ""

        def _open(with_usage: bool):
            opts = dict(model=self.model, messages=messages, max_tokens=max_tokens,
                        extra_headers=self.extra_headers, stream=True)
            if with_usage:
                opts["stream_options"] = {"include_usage": True}
            return self.client.chat.completions.create(**opts)

        try:
            try:
                stream = _open(True)
            except Exception:
                stream = _open(False)  # some local/compat servers (e.g. older Ollama) reject stream_options
            for chunk in stream:
                if getattr(chunk, "usage", None):     # final usage-only chunk (include_usage)
                    self.last_usage = _usage_dict(chunk)
                if not chunk.choices:
                    continue
                if chunk.choices[0].finish_reason:
                    self.last_finish_reason = _norm_finish(chunk.choices[0].finish_reason)
                delta = chunk.choices[0].delta.content
                if delta:
                    acc += delta
                    yield delta
            if acc or self.last_usage:
                self._log_usage(t0, acc)
        except Exception:
            if acc:
                raise
            yield self.complete(messages, max_tokens=max_tokens)

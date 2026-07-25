"""OpenRouter provider client — extracted from core/model_router.py (Phase 4).

Verbatim move; behavior identical. Re-exported by core.model_router.
"""
import os
import time

from core.llm_clients.base import (DEFAULT_TIMEOUT_S, BaseLLMClient, _norm_finish,
                                   _usage_dict)
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
        self.client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key,
                             timeout=DEFAULT_TIMEOUT_S)
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
        self.last_usage = {}
        t0 = time.time(); acc = ""
        try:
            stream = self.client.chat.completions.create(
                model=self.model, messages=messages, max_tokens=max_tokens,
                extra_headers=self._HEADERS, stream=True,
                stream_options={"include_usage": True},
            )
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
            # Never append a fallback response after visible partial output. The runtime can
            # reset/recover the turn, but concatenating providers corrupts the answer.
            if acc:
                raise
            yield self.complete(messages, max_tokens=max_tokens)

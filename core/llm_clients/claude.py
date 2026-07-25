"""Native Anthropic (Claude) provider client — extracted from core/model_router.py
(Phase 4). Verbatim move; behavior identical, including the _text_from() helper that
skips reasoning/thinking blocks so thinking-capable models can't crash content
generation. Re-exported by core.model_router.
"""
import os
import time
from typing import Optional  # noqa: F401 - used in signatures

from core.llm_clients.base import DEFAULT_TIMEOUT_S, BaseLLMClient, _norm_finish
class ClaudeClient(BaseLLMClient):
    def __init__(self, model: str = "claude-opus-4-20250514",
                 base_url: Optional[str] = None, api_key: Optional[str] = None,
                 provider: str = "anthropic"):
        import anthropic
        # `base_url` lets us point the Anthropic SDK at a Claude-compatible endpoint
        # (e.g. the GLM Coding Plan at https://api.z.ai/api/anthropic).
        kwargs = {"api_key": api_key or os.getenv("ANTHROPIC_API_KEY"),
                  "timeout": DEFAULT_TIMEOUT_S}
        if base_url:
            kwargs["base_url"] = base_url
        self.client = anthropic.Anthropic(**kwargs)
        self.model = model
        self.provider = provider
        self.last_usage = {}

    @staticmethod
    def _text_from(r) -> str:
        """Concatenate TEXT blocks only. Reasoning models (GLM-4.6/5, Claude with
        extended thinking) return a leading *thinking* block, so the old
        ``content[0].text`` either grabbed reasoning or raised AttributeError on the
        thinking block — the latter silently killed every background completion. This
        skips non-text blocks and never raises (streaming already filters via
        ``text_stream``; this makes the non-streaming path just as safe)."""
        parts = [getattr(b, "text", "") or "" for b in (getattr(r, "content", None) or [])
                 if getattr(b, "type", None) == "text"]
        if parts:
            return "".join(parts)
        first = (getattr(r, "content", None) or [None])[0]
        return getattr(first, "text", "") or ""

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
        text = self._text_from(r)
        self._log_usage(t0, text)
        return text

    def complete_stream(self, messages, system=None, max_tokens=2000):
        kwargs = {"model": self.model, "max_tokens": max_tokens, "messages": messages}
        if system:
            kwargs["system"] = system
        self.last_finish_reason = None
        self.last_usage = {}
        t0 = time.time(); acc = ""
        try:
            with self.client.messages.stream(**kwargs) as stream:
                for text in stream.text_stream:
                    if text:
                        acc += text
                        yield text
                try:
                    final = stream.get_final_message()
                    self.last_finish_reason = _norm_finish(final.stop_reason)
                    self.last_usage = {"prompt_tokens": final.usage.input_tokens,
                                       "completion_tokens": final.usage.output_tokens}
                except Exception:
                    pass
            if acc or self.last_usage:  # streaming path must log too (else chat/GLM go untracked)
                self._log_usage(t0, acc)
        except Exception:
            yield self.complete(messages, system=system, max_tokens=max_tokens)

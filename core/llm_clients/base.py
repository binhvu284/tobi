"""Shared base for every LLM provider client.

Extracted from core/model_router.py (Phase 4 — pre-#21 decomposition). Holds the
abstract BaseLLMClient, the per-turn usage-attribution ContextVar (kept here so all
clients and the router share ONE instance), DEFAULT_TIMEOUT_S, and the small
_norm_finish/_usage_dict/estimate_tokens helpers. Verbatim move.

safe_load_dotenv() is called here (as core/model_router.py does) because
DEFAULT_TIMEOUT_S reads LLM_TIMEOUT_S at import time — this keeps the value identical
regardless of which module is imported first. It is idempotent and best-effort.
"""
import os
import time  # noqa: F401 - used by client subclasses' retry/latency paths
from abc import ABC, abstractmethod
from contextvars import ContextVar
from typing import Optional  # noqa: F401 - used in signatures

from core.env_utils import safe_load_dotenv

safe_load_dotenv()
_USAGE_CTX: ContextVar[dict] = ContextVar(
    "tobi_llm_usage_context", default={"surface": "agent", "feature": ""}
)


DEFAULT_TIMEOUT_S = max(10, int(os.getenv("LLM_TIMEOUT_S", "60")))


def set_usage_context(surface: str = "agent", feature: str = "") -> dict:
    """Set the usage tag for subsequent LLM calls; returns the previous tag (to restore)."""
    prev = dict(_USAGE_CTX.get())
    _USAGE_CTX.set({"surface": surface or "agent", "feature": feature or ""})
    return prev


def get_usage_context() -> dict:
    return dict(_USAGE_CTX.get())


def run_with_usage_context(surface: str, feature: str, fn, *args, **kwargs):
    """Run a callable with isolated usage attribution inside the current worker thread."""
    previous = set_usage_context(surface, feature)
    try:
        return fn(*args, **kwargs)
    finally:
        set_usage_context(previous["surface"], previous["feature"])


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
                      surface=_USAGE_CTX.get()["surface"], feature=_USAGE_CTX.get()["feature"])
        except Exception:
            pass


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

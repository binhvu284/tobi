"""Model-response handling extracted from the legacy Conductor loop.

This service classifies model output, keeps tool JSON out of streamed replies,
separates private reasoning, continues token-capped answers, and chunks finished
text. It deliberately does not select models, execute tools, persist state, or
make policy decisions.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Callable, Iterator, Optional

from core.conductor_parsing import _parse_tool_call

logger = logging.getLogger("tobi.conductor")

_THINK_RE = re.compile(r"<think(?:ing)?>.*?</think(?:ing)?>", re.S | re.I)
_REASON_LEAD_RE = re.compile(r"^\s*(?:reasoning|thought|thinking|analysis)\s*:\s*", re.I)
TOOL_SIGNATURE_RE = re.compile(r'\{\s*"tool"')


@dataclass(frozen=True)
class ModelStepResult:
    """Typed result from one provider call."""

    text: str
    is_answer: bool
    finish_reason: Optional[str]

    def as_legacy_tuple(self) -> tuple[str, bool, Optional[str]]:
        return self.text, self.is_answer, self.finish_reason


def looks_like_tool_start(stripped: str) -> bool:
    """Return whether a response prefix begins like a tool-call object."""
    if not stripped:
        return False
    if stripped[0] == "{":
        return True
    return bool(re.match(r"```(?:json)?\s*\{", stripped))


def split_reasoning(text: str) -> tuple[str, str]:
    """Split owner-visible answer text from private model reasoning."""
    if not text:
        return "", ""
    reasoning = "\n".join(_THINK_RE.findall(text)).strip()
    clean = _THINK_RE.sub("", text)
    if "<|channel|>" in clean or "<|start|>" in clean:
        finals = re.findall(
            r"final\s*<\|message\|>(.*?)(?:<\|end\|>|<\|return\|>|$)",
            clean,
            re.S,
        )
        if finals:
            reasoning = (reasoning + "\n" + clean).strip()
            clean = "\n".join(final.strip() for final in finals)
    low = clean.lower()
    if "<think" in low and "</think" not in low:
        index = low.find("<think")
        reasoning = (reasoning + "\n" + clean[index:]).strip()
        clean = clean[:index]
    clean = _REASON_LEAD_RE.sub("", clean).strip()
    return clean, reasoning


def stream_chunks(text: str) -> Iterator[str]:
    """Split finished text into small pieces without losing characters."""
    buffer = ""
    for piece in re.findall(r"\S+\s*", text):
        buffer += piece
        if len(buffer) >= 18:
            yield buffer
            buffer = ""
    if buffer:
        yield buffer


def generate_step(
    client: Any,
    messages: list,
    system: str,
    max_tokens: int,
    on_delta: Optional[Callable[[str], None]],
    on_reset: Optional[Callable[[], None]] = None,
) -> ModelStepResult:
    """Run one model turn while buffering anything classified as a tool call."""
    streamer = getattr(client, "complete_stream", None)
    if not on_delta or streamer is None:
        try:
            text = client.complete(list(messages), system=system, max_tokens=max_tokens) or ""
        except Exception as exc:  # noqa: BLE001
            logger.warning("conductor step failed: %s", exc)
            return ModelStepResult("", False, "error")
        is_answer = _parse_tool_call(text) is None and not looks_like_tool_start(text.lstrip())
        if is_answer and on_delta:
            for chunk in stream_chunks(text):
                on_delta(chunk)
        return ModelStepResult(text, is_answer, getattr(client, "last_finish_reason", None))

    buffer = ""
    decided: Optional[str] = None
    emitted = 0
    reset = False

    def to_tool() -> None:
        nonlocal decided, reset
        decided = "tool"
        reset = True
        if emitted and on_reset:
            try:
                on_reset()
            except Exception:
                pass

    try:
        for delta in streamer(list(messages), system=system, max_tokens=max_tokens):
            buffer += delta
            if decided is None:
                stripped = buffer.lstrip()
                if len(stripped) >= 8 or "\n" in buffer:
                    decided = "tool" if looks_like_tool_start(stripped) else "answer"
                    if decided == "answer" and TOOL_SIGNATURE_RE.search(buffer):
                        to_tool()
                    elif decided == "answer":
                        on_delta(buffer[emitted:])
                        emitted = len(buffer)
            elif decided == "answer":
                if TOOL_SIGNATURE_RE.search(buffer):
                    to_tool()
                else:
                    on_delta(buffer[emitted:])
                    emitted = len(buffer)
    except Exception as exc:  # noqa: BLE001
        logger.warning("conductor stream failed: %s", exc)
        try:
            buffer = client.complete(list(messages), system=system, max_tokens=max_tokens) or buffer
        except Exception:
            pass

    if decided is None:
        decided = (
            "tool"
            if looks_like_tool_start(buffer.lstrip()) or _parse_tool_call(buffer)
            else "answer"
        )
        if decided == "answer" and emitted == 0 and buffer:
            on_delta(buffer)
    elif decided == "answer" and not reset and _parse_tool_call(buffer):
        to_tool()
    return ModelStepResult(
        buffer,
        decided == "answer",
        getattr(client, "last_finish_reason", None),
    )


def continue_answer(
    client: Any,
    messages: list,
    partial: str,
    system: str,
    on_delta: Optional[Callable[[str], None]],
    *,
    max_tokens: int,
    rounds: int = 2,
) -> str:
    """Continue a token-capped answer for at most ``rounds`` provider calls."""
    extra = ""
    current = partial
    for _ in range(rounds):
        if getattr(client, "last_finish_reason", None) != "length":
            break
        continuation_messages = list(messages) + [
            {"role": "assistant", "content": current},
            {
                "role": "user",
                "content": "Continue from exactly where you stopped. Do not repeat anything.",
            },
        ]
        step = generate_step(
            client,
            continuation_messages,
            system,
            max_tokens,
            on_delta,
        )
        if not step.text:
            break
        extra += step.text
        current = step.text
    return extra

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
from typing import Any, Callable, Iterator, Mapping, Optional

from core.conductor_parsing import _parse_tool_call, strip_tool_calls

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


@dataclass(frozen=True)
class FinalResponseDecision:
    """Pure classification of one candidate owner-visible response."""

    clean_text: str
    reasoning: str
    mixed_reply: str
    requires_escalation: bool


@dataclass(frozen=True)
class FinalResponseContext:
    """Immutable inputs needed to compose Conductor's public response payload."""

    client: Any
    requested_model: Optional[str]
    usage_context: Optional[Mapping[str, Any]]
    mode: str
    intent: str
    messages: tuple[dict, ...]
    system: str
    tools_used: tuple[str, ...]
    final_tokens: int
    on_event: Optional[Callable[[dict], None]] = None
    on_delta: Optional[Callable[[str], None]] = None
    on_reset: Optional[Callable[[], None]] = None


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


def classify_final_response(text: str, *, mixed_prose_min: int) -> FinalResponseDecision:
    """Classify clean prose, mixed tool/prose, or malformed internal output."""
    clean, reasoning = split_reasoning(text)
    tool_like = bool(
        not clean
        or TOOL_SIGNATURE_RE.match(clean.lstrip())
        or _parse_tool_call(clean)
    )
    if not tool_like:
        return FinalResponseDecision(clean, reasoning, "", False)
    leftover = strip_tool_calls(clean)
    if len(leftover) >= mixed_prose_min:
        return FinalResponseDecision(clean, reasoning, leftover, False)
    return FinalResponseDecision(clean, reasoning, "", True)


def attach_model_metadata(
    payload: dict,
    *,
    client: Any,
    requested_model: Optional[str],
    usage_context: Optional[Mapping[str, Any]],
    actual_override: Optional[str] = None,
    reason_override: Optional[str] = None,
) -> dict:
    """Attach the exact model identity fields exposed by the compatibility API."""
    requested = (
        getattr(client, "requested_model", None)
        or (requested_model or "")
        or (usage_context or {}).get("requested_model")
        or None
    )
    actual = actual_override or getattr(client, "actual_model_id", None)
    if not actual and getattr(client, "provider", None) and getattr(client, "model", None):
        actual = f"{client.provider}:{client.model}"
    payload.update({
        "requested_model": requested,
        "actual_model": actual,
        "fallback_reason": reason_override or getattr(client, "fallback_reason", None),
        "model_attempts": int(getattr(client, "attempt_count", 1) or 1),
    })
    return payload


def compose_final_response(
    text: str,
    context: FinalResponseContext,
    *,
    mixed_prose_min: int,
    model_struggling_text: str,
    generate_step_legacy: Callable[..., tuple[str, bool, Optional[str]]],
    get_escalation_llm: Callable[[Optional[str]], tuple[Any, Optional[str]]],
    get_usage_context: Callable[[], Mapping[str, Any]],
    set_usage_context: Callable[..., Any],
    restore_usage_context: Callable[[Mapping[str, Any]], Any],
) -> dict:
    """Compose one public response, including the existing bounded escalation path."""
    decision = classify_final_response(text, mixed_prose_min=mixed_prose_min)
    if decision.mixed_reply:
        return attach_model_metadata({
            "reply": decision.mixed_reply,
            "reasoning": decision.reasoning,
            "tools_used": list(context.tools_used),
            "intent": context.intent,
            "streamed": False,
        }, client=context.client, requested_model=context.requested_model,
            usage_context=context.usage_context)

    if decision.requires_escalation:
        try:
            stronger, stronger_id = get_escalation_llm(context.requested_model)
            if stronger is not None:
                if context.on_reset:
                    context.on_reset()
                if context.on_event:
                    context.on_event({
                        "type": "model_escalated",
                        "from_model": context.requested_model,
                        "to_model": stronger_id,
                        "reason": "malformed_output",
                    })
                retry_messages = list(context.messages) + [{
                    "role": "user",
                    "content": (
                        "The previous model produced malformed internal output. Give the owner a complete "
                        "plain-language answer now. Do not emit a tool call or JSON."
                    ),
                }]
                previous_usage = get_usage_context()
                set_usage_context(
                    previous_usage.get("surface", context.mode),
                    previous_usage.get("feature", ""),
                    **{
                        **{
                            key: value for key, value in previous_usage.items()
                            if key not in {"surface", "feature"}
                        },
                        "requested_model": (
                            getattr(context.client, "requested_model", None)
                            or context.requested_model
                            or previous_usage.get("requested_model", "")
                        ),
                        "attempt": int(getattr(context.client, "attempt_count", 1) or 1) + 1,
                        "fallback_reason": "malformed_output",
                    },
                )
                try:
                    retry, retry_is_answer, _ = generate_step_legacy(
                        stronger,
                        retry_messages,
                        context.system,
                        context.final_tokens,
                        context.on_delta,
                        context.on_reset,
                    )
                finally:
                    restore_usage_context(previous_usage)
                retry_clean, retry_reasoning = split_reasoning(retry)
                if retry_is_answer and retry_clean and not _parse_tool_call(retry_clean):
                    return attach_model_metadata({
                        "reply": retry_clean,
                        "reasoning": retry_reasoning,
                        "tools_used": list(context.tools_used),
                        "intent": context.intent,
                        "streamed": bool(context.on_delta),
                        "model_escalated": stronger_id,
                    }, client=context.client, requested_model=context.requested_model,
                        usage_context=context.usage_context, actual_override=stronger_id,
                        reason_override="malformed_output")
        except Exception as exc:  # noqa: BLE001
            logger.warning("conductor model escalation failed: %s", exc)
        return attach_model_metadata({
            "reply": model_struggling_text,
            "tools_used": list(context.tools_used),
            "intent": context.intent,
            "model_issue": True,
            "streamed": False,
        }, client=context.client, requested_model=context.requested_model,
            usage_context=context.usage_context)

    return attach_model_metadata({
        "reply": decision.clean_text,
        "reasoning": decision.reasoning,
        "tools_used": list(context.tools_used),
        "intent": context.intent,
        "streamed": bool(context.on_delta),
    }, client=context.client, requested_model=context.requested_model,
        usage_context=context.usage_context)


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

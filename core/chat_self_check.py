"""Prove Chat works, rather than proving a model can answer one question.

The Health page's deep check asked the model `"Reply with exactly: OK"` and reported the AI
healthy. On 2026-08-01 it said healthy all day while every Chat request failed. It was not
careless -- one message and one answer genuinely worked. The defect only existed on the second
message: assistant turns were sent back to the Responses API tagged `input_text` instead of
`output_text`, so any conversation containing a model turn was rejected 400 before the model was
asked. Chat's tool loop always reaches a second turn. A one-shot probe never does.

So this runs the smallest real conversation instead: a fixed request that needs one read-only
tool, on the streaming path, under the route's own token budgets -- the exact path the defect
lived in. A check that runs an easier path than the real one cannot protect the harder one.

Three outcomes, and the difference between the first two is the whole point:

    working             the tool ran and a plain answer came back
    broken              the model answered once, then the conversation could not finish
    model_unavailable   the provider could not be reached at all

Nothing here is configurable. It uses whichever model is already selected, writes nothing, and
is only ever run when the owner presses the button.
"""
from __future__ import annotations

import logging
import re
import threading
import time
from typing import Any, Callable, Optional

logger = logging.getLogger("tobi.self_check")

TIMEOUT_SECONDS = 45.0

# A negative id keeps this out of the owner's conversations even if a future caller decides to
# persist. `conductor.answer` itself writes nothing; the guard asserts that stays true.
SELF_CHECK_CHAT_ID = -99_001

# Fixed, harmless, and it genuinely needs a tool: the model cannot answer it from the prompt.
PROBE_MESSAGE = "How many projects do I have right now?"
PROBE_TOOL = "list_projects"

# The route's own budgets, not the Conductor's larger defaults. The 2026-08-01 defect was
# reachable only under these; running the check at 2048/4096 would have passed while Chat failed.
STEP_TOKENS = 700
FINAL_TOKENS = 1600

# Mirrors api/routers/health.py so an error surfaced here is redacted the same way it is there.
_REDACT: list[tuple[re.Pattern, str]] = [
    (re.compile(r"bot\d+:[A-Za-z0-9_\-]+"), "bot***REDACTED***"),
    (re.compile(r"(?i)(token|key|secret|password)=\S+"), r"\1=***"),
    (re.compile(r"\b(sk|pk|rk)-[A-Za-z0-9_\-]{12,}"), r"\1-***"),
    (re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{12,}"), "Bearer ***"),
]


def redact(text: str) -> str:
    for pattern, replacement in _REDACT:
        text = pattern.sub(replacement, text)
    return text


class _Watched:
    """Wraps the live client so a failure can be attributed to *which* turn it happened on.

    The Conductor swallows a failed model call into an empty string — that is why the 400 never
    reached anyone. Rather than change the Conductor (owned by #21 T08), the client is wrapped
    for the duration of the check, so the real exception and its turn number are both captured.

    Turn 1 failing means the provider is unreachable. Turn 2 or later failing means the provider
    answered once and the conversation still could not finish, which is a Chat defect.
    """

    def __init__(self, inner: Any, record: dict) -> None:
        self._inner = inner
        self._record = record

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def _note(self, exc: BaseException) -> None:
        self._record["failures"].append({"turn": self._record["turns"], "error": str(exc)})

    def complete(self, messages, system=None, max_tokens=2000):
        self._record["turns"] += 1
        try:
            return self._inner.complete(messages, system=system, max_tokens=max_tokens)
        except BaseException as exc:
            self._note(exc)
            raise

    def complete_stream(self, messages, system=None, max_tokens=2000):
        # Presence of this method is what makes the Conductor take the streaming path.
        self._record["turns"] += 1
        try:
            yield from self._inner.complete_stream(
                messages, system=system, max_tokens=max_tokens)
        except BaseException as exc:
            self._note(exc)
            raise


def _classify(result: dict, record: dict) -> tuple[str, str]:
    """Turn a run into (state, detail the owner can act on)."""
    failures = record["failures"]
    first = failures[0] if failures else None

    if first and first["turn"] <= 1:
        return "model_unavailable", (
            f"The model could not be reached: {first['error']}")

    if first:
        return "broken", (
            f"The model answered turn 1, then turn {first['turn']} was rejected: {first['error']}")

    if result.get("model_issue"):
        return "broken", (
            "The conversation did not finish. The model returned output Chat could not use, "
            "and no error was reported by the provider.")

    tools = result.get("tools_used") or []
    reply = (result.get("reply") or "").strip()
    if PROBE_TOOL not in tools:
        return "broken", (
            f"The model never called {PROBE_TOOL}, so the tool loop did not run. "
            f"It replied: {reply[:200] or '(nothing)'}")
    if not reply:
        return "broken", "The tool ran but no answer came back."
    return "working", f"Ran {PROBE_TOOL} and answered: {reply[:180]}"


def run_self_check(*, timeout_seconds: float = TIMEOUT_SECONDS,
                   message: str = PROBE_MESSAGE) -> dict:
    """Hold one bounded real conversation and report whether Chat can complete it."""
    from core import conductor
    from core import model_router

    record: dict = {"turns": 0, "failures": []}
    outcome: dict = {}
    started = time.perf_counter()

    original_get_llm: Optional[Callable] = getattr(model_router, "get_llm", None)

    def _watched_get_llm(*args, **kwargs):
        return _Watched(original_get_llm(*args, **kwargs), record)

    def _run() -> None:
        try:
            outcome["result"] = conductor.answer(
                message, chat_id=SELF_CHECK_CHAT_ID, surface="mc",
                mode="agent", route="action",
                step_tokens=STEP_TOKENS, final_tokens=FINAL_TOKENS,
                allowed_tools={PROBE_TOOL},
                # Passing on_delta is what selects the streaming path. The deltas are dropped:
                # nobody is watching, and the point is to exercise the path, not to read it.
                on_delta=lambda _chunk: None,
            )
        except BaseException as exc:  # noqa: BLE001 - reported, never raised at the owner
            outcome["error"] = f"{type(exc).__name__}: {exc}"

    model_router.get_llm = _watched_get_llm
    try:
        worker = threading.Thread(target=_run, daemon=True, name="chat-self-check")
        worker.start()
        worker.join(timeout_seconds)
        timed_out = worker.is_alive()
    finally:
        if original_get_llm is not None:
            model_router.get_llm = original_get_llm

    latency_ms = int((time.perf_counter() - started) * 1000)

    if timed_out:
        state, detail = "broken", (
            f"Chat did not finish within {timeout_seconds:.0f} seconds. "
            f"It reached model turn {record['turns']}.")
        tools: list = []
    elif "error" in outcome:
        state, detail = "broken", f"Chat raised an error: {outcome['error']}"
        tools = []
    else:
        result = outcome.get("result") or {}
        state, detail = _classify(result, record)
        tools = list(result.get("tools_used") or [])

    report = {
        "state": state,
        "ok": state == "working",
        "detail": redact(detail)[:600],
        "tools_used": tools,
        "model_turns": record["turns"],
        "latency_ms": latency_ms,
    }
    logger.info("chat self-check: %s (%s turns, %sms)", state, record["turns"], latency_ms)
    return report

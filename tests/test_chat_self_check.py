"""The Health check must fail when Chat is broken.

On 2026-08-01 the Health page's deep check reported the AI healthy while every Chat request
failed. It was not measuring the wrong thing carelessly -- it asked the model one question and
got one answer, and that genuinely worked:

    llm_complete("Reply with exactly: OK")            api/routers/health.py

The defect only existed on the *second* message. The Responses API types text by who produced
it, and every message was tagged `input_text`, so the moment a conversation contained an
assistant turn the request came back 400 before the model was asked. Chat's tool loop always
reaches a second turn; a one-shot probe never does. Runs 82 through 87 failed while the button
stayed green, and the owner was sent twice to a model picker that could not have helped.

So the check has to hold a real conversation that uses a tool, on the streaming path, with the
route's own token budgets -- the exact path the defect lived in. A check that runs an easier
path than the real one is not a check.

Isolated temp DB, no network, plain python:
    python tests/test_chat_self_check.py
"""
from __future__ import annotations

import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix="tobi_selfcheck_")
os.environ["DB_PATH"] = os.path.join(_TMP, "agent.db")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.database import init_database  # noqa: E402

init_database()

from core import chat_self_check  # noqa: E402
from core import model_router as mr  # noqa: E402
from core import task_classifier as tc  # noqa: E402

tc.classify = lambda m: "QUESTION"

FAILURES: list[str] = []


def ok(name: str, cond: bool, detail: str = "") -> None:
    print(f"{'PASS' if cond else 'FAIL'} {name}{('  -> ' + detail) if detail and not cond else ''}")
    if not cond:
        FAILURES.append(name)


# The verbatim rejection the subscription backend returned for every turn after the first.
SECOND_TURN_400 = (
    "Error code: 400 - {'error': {'message': \"Invalid value: 'input_text'. Supported values "
    "are: 'output_text' and 'refusal'.\", 'type': 'invalid_request_error', "
    "'param': 'input[1].content[0]', 'code': 'invalid_value'}}"
)
TOOL_CALL = '{"tool":"list_projects","args":{}}'


class _Client:
    """Stub LLM. `fail_from` is the 1-based call at which every later call raises, which is
    exactly the shape of the shipped defect: turn one fine, turn two onward rejected."""
    last_finish_reason = "stop"

    def __init__(self, replies, *, fail_from=None, error=SECOND_TURN_400):
        self.replies = list(replies)
        self.fail_from = fail_from
        self.error = error
        self.calls = 0
        self.max_tokens_seen: list[int] = []

    def complete(self, messages, system=None, max_tokens=2000):
        self.calls += 1
        self.max_tokens_seen.append(max_tokens)
        if self.fail_from and self.calls >= self.fail_from:
            raise RuntimeError(self.error)
        return self.replies.pop(0) if self.replies else "All done, sir."

    def complete_stream(self, messages, system=None, max_tokens=2000):
        yield self.complete(messages, system=system, max_tokens=max_tokens)


def _rows() -> tuple[int, int, int]:
    """Chat messages, conversations and actions — the check must add none of them."""
    from core.database import get_connection
    with get_connection() as conn:
        def count(table: str) -> int:
            try:
                return conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            except Exception:
                return 0
        return count("chat_messages"), count("conversations"), count("tobi_actions")


# --- 1. a healthy conversation reports working -------------------------------------------
client = _Client([TOOL_CALL, "Sir, you have 9 projects."])
mr.get_llm = lambda *a, **k: client
mr.build_client = lambda *a, **k: client
before = _rows()
result = chat_self_check.run_self_check()

ok("a healthy two-turn conversation reports working",
   result.get("state") == "working", str(result)[:200])
ok("it reports which tool actually ran",
   "list_projects" in (result.get("tools_used") or []), str(result.get("tools_used")))
ok("it records how long the whole check took",
   isinstance(result.get("latency_ms"), int), str(result.get("latency_ms")))

# --- 2. the shipped defect: turn one fine, turn two rejected -----------------------------
broken = _Client([TOOL_CALL], fail_from=2)
mr.get_llm = lambda *a, **k: broken
mr.build_client = lambda *a, **k: broken
result2 = chat_self_check.run_self_check()

ok("a second-turn failure is reported as broken",
   result2.get("state") == "broken", str(result2)[:220])
ok("the provider's own error text reaches the owner",
   "input_text" in (result2.get("detail") or ""), (result2.get("detail") or "")[:200])
ok("it is NOT reported as the model being unavailable",
   result2.get("state") != "model_unavailable", str(result2.get("state")))

# --- 3. an unreachable provider is not a Chat defect --------------------------------------
down = _Client([], fail_from=1, error="Connection refused")
mr.get_llm = lambda *a, **k: down
mr.build_client = lambda *a, **k: down
result3 = chat_self_check.run_self_check()

ok("a first-turn failure reports the model unavailable, not Chat broken",
   result3.get("state") == "model_unavailable", str(result3)[:200])
ok("the reason the provider could not be reached is shown",
   "Connection refused" in (result3.get("detail") or ""), (result3.get("detail") or "")[:160])

# --- 4. it must run the real path, not an easier one --------------------------------------
# The defect lived on the streaming path under the route's token budgets. A check that used
# the plain non-streaming defaults would have passed while Chat was broken.
ok("the check exercises the streaming path",
   client.calls > 0 and all(t <= 1600 for t in client.max_tokens_seen),
   f"token caps seen: {client.max_tokens_seen}")
ok("it uses the route's budgets, not the 2048/4096 defaults",
   2048 not in client.max_tokens_seen and 4096 not in client.max_tokens_seen,
   str(client.max_tokens_seen))

# --- 5. it must leave no trace ------------------------------------------------------------
after = _rows()
ok("no chat message, conversation or action is written",
   before == after, f"before={before} after={after}")

# --- 6. secrets never reach the owner's screen --------------------------------------------
leaky = _Client([], fail_from=1,
                error="401 Unauthorized: Bearer sk-proj-AbCdEf0123456789abcdef0123456789")
mr.get_llm = lambda *a, **k: leaky
mr.build_client = lambda *a, **k: leaky
result4 = chat_self_check.run_self_check()
ok("a key inside an error is redacted before it is shown",
   "sk-proj-AbCdEf0123456789abcdef0123456789" not in (result4.get("detail") or ""),
   (result4.get("detail") or "")[:160])

# --- 7. a hung provider must not hang the Health page -------------------------------------
ok("the check declares a timeout", isinstance(getattr(chat_self_check, "TIMEOUT_SECONDS", None), (int, float))
   and chat_self_check.TIMEOUT_SECONDS <= 60,
   str(getattr(chat_self_check, "TIMEOUT_SECONDS", None)))

print(f"\n{'ALL' if not FAILURES else str(len(FAILURES)) + ' OF'} "
      f"{'CHAT SELF-CHECK TESTS PASSED' if not FAILURES else 'CHECKS FAILED: ' + ', '.join(FAILURES)}")
raise SystemExit(1 if FAILURES else 0)

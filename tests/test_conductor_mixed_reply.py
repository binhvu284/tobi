"""A reply that is BOTH a tool call and a question must not be thrown away.

The owner asked Chat: "list all project, update their progress". `codex:gpt-5.6-sol` answered
this, captured verbatim from a live call on 2026-08-01:

    {"tool":"list_projects","args":{}}I need each project's current status or completed
    milestones to update progress accurately.

Nothing about that is malformed. The JSON is valid and complete, and the prose is the right
question to ask -- "update their progress" never said what to update it to. A human assistant
would do exactly this: start the lookup, and ask the one question it needs answered.

TOBI dropped all of it. Two runs (82 and 83) recorded `tools: []`, streamed 32 characters to
the screen, retracted them, and told the owner "the current model is struggling" -- which is
false, and which points him at a model picker that cannot fix anything.

The rule this suite enforces: when a reply carries a usable tool call, run it; when it also
carries prose, the owner sees the prose. Never discard both because the shape was unexpected.

Isolated temp DB, plain python, no pytest:
    python tests/test_conductor_mixed_reply.py
"""
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix="tobi_mixed_")
os.environ["DB_PATH"] = os.path.join(_TMP, "agent.db")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.database import init_database  # noqa: E402

init_database()

from core import conductor  # noqa: E402
from core import model_router as mr  # noqa: E402
from core import task_classifier as tc  # noqa: E402

tc.classify = lambda m: "QUESTION"  # force the tool loop, not SMALLTALK/CODING

FAILURES: list[str] = []


def ok(name: str, cond: bool, detail: str = "") -> None:
    print(f"{'PASS' if cond else 'FAIL'} {name}{('  -> ' + detail) if detail and not cond else ''}")
    if not cond:
        FAILURES.append(name)


class _Fake:
    """Stub LLM returning queued replies. No `complete_stream`, so the non-streaming
    `_gen_step` path runs -- the classification bug reproduces on both paths."""
    last_finish_reason = "stop"

    def __init__(self, lines, default="All done, sir."):
        self.lines = list(lines)
        self.default = default

    def complete(self, messages, system=None, max_tokens=2000):
        return self.lines.pop(0) if self.lines else self.default


TOOL = '{"tool":"list_projects","args":{}}'
QUESTION = ("I need each project's current status or completed milestones to update "
            "progress accurately.")

# --- 1. the live capture: tool call first, question glued to it, no separator ------------
mr.get_llm = lambda *a, **k: _Fake([TOOL + QUESTION], default=TOOL + QUESTION)
res = conductor.answer("list all project, update their progress", chat_id=-9201, surface="mc")
reply = res.get("reply", "")

ok("the tool the model asked for actually runs",
   "list_projects" in res.get("tools_used", []), f"tools_used={res.get('tools_used')}")
ok("the owner is not told the model is struggling",
   not res.get("model_issue"), reply[:160])
ok("the model's question reaches the owner",
   "current status" in reply or "milestones" in reply, reply[:160])
ok("raw tool JSON never reaches the owner", '{"tool"' not in reply, reply[:160])

# --- 2. the streamed order: prose first, then the call ----------------------------------
# Runs 82 and 83 both leaked exactly 32 characters before retracting, which is the signature
# of prose arriving ahead of the JSON. Same reply, opposite order -- same outcome required.
mr.get_llm = lambda *a, **k: _Fake([QUESTION + "\n" + TOOL], default=QUESTION + "\n" + TOOL)
res2 = conductor.answer("list all project, update their progress", chat_id=-9202, surface="mc")
reply2 = res2.get("reply", "")

ok("prose-first mixed reply still runs the tool",
   "list_projects" in res2.get("tools_used", []), f"tools_used={res2.get('tools_used')}")
ok("prose-first mixed reply is not a model issue",
   not res2.get("model_issue"), reply2[:160])
ok("prose-first mixed reply keeps the question", "milestones" in reply2, reply2[:160])

# --- 3. no false positives: the existing guards must still hold -------------------------
# A model that ONLY ever emits a tool call, forever, is a genuine model problem. Widening the
# parser must not turn that into an infinite loop or a JSON leak.
mr.get_llm = lambda *a, **k: _Fake([], default=TOOL)
res3 = conductor.answer("list projects", chat_id=-9203, surface="mc")
ok("a model that never answers is still flagged", res3.get("model_issue") is True)
ok("and still never leaks JSON", '{"tool"' not in res3.get("reply", ""), res3.get("reply", "")[:120])

mr.get_llm = lambda *a, **k: _Fake(["Right away, sir - all systems are nominal."])
res4 = conductor.answer("status?", chat_id=-9204, surface="mc")
ok("a plain prose answer is untouched",
   res4.get("reply") == "Right away, sir - all systems are nominal." and not res4.get("model_issue"))

_cfg = 'Here is a sample config, sir:\n```json\n{"port": 8080, "debug": true}\n```'
mr.get_llm = lambda *a, **k: _Fake([_cfg])
res5 = conductor.answer("give me a sample config", chat_id=-9205, surface="mc")
ok("a fenced JSON answer with no tool key passes through",
   res5.get("reply", "").startswith("Here is a sample config") and not res5.get("model_issue"),
   res5.get("reply", "")[:120])

print(f"\n{'ALL' if not FAILURES else str(len(FAILURES)) + ' OF'} "
      f"{'MIXED-REPLY CHECKS PASSED' if not FAILURES else 'CHECKS FAILED: ' + ', '.join(FAILURES)}")
raise SystemExit(1 if FAILURES else 0)

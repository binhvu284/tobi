"""
Conductor tool-loop leak guard — chat "{"tool":…}" crash fix.

Isolated temp DB (DB_PATH env), plain python, no pytest:
    DB_PATH=/tmp/tguard.db python tests/test_conductor_final_guard.py

Regression for the leak an owner reported: a weaker model that keeps emitting a
tool-call JSON instead of a prose answer (it loops calling recall_conversations,
exhausts the step budget, and STILL emits `{"tool":…}` on the forced-final step) must
NEVER have that raw JSON surfaced as the chat reply. Covers:
  1. a model that only ever emits tool-call JSON → graceful model-issue reply, no JSON;
  2. forced-final blunt-retry recovery (JSON on the first forced-final attempt, then real
     prose on the retry) → the prose answer is returned;
  3. a normal prose answer still passes through untouched (no false positives).
"""
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix="tobi_tguard_")
os.environ["DB_PATH"] = os.path.join(_TMP, "agent.db")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.database import init_database  # noqa: E402

init_database()

from core import conductor  # noqa: E402
from core import model_router as mr  # noqa: E402
from core import task_classifier as tc  # noqa: E402

tc.classify = lambda m: "QUESTION"   # force the tool-loop (not SMALLTALK/CODING)

PASS = 0


def ok(name: str, cond: bool, detail: str = ""):
    global PASS
    if not cond:
        print(f"❌ {name} {detail}")
        sys.exit(1)
    PASS += 1
    print(f"✅ {name}")


class _Fake:
    """A stub LLM: returns queued lines, then a default. No streaming (forces the
    non-streaming _gen_step path)."""
    last_finish_reason = None

    def __init__(self, lines, default="All done, sir."):
        self.lines = list(lines)
        self.default = default

    def complete(self, messages, system=None, max_tokens=2000):
        return self.lines.pop(0) if self.lines else self.default


_TOOL_JSON = '{"tool":"recall_conversations","args":{"query":"clients"}}'

# 1. model NEVER answers — always a tool call. Budget exhausts; forced-final still JSON.
mr.get_llm = lambda *a, **k: _Fake([], default=_TOOL_JSON)
res = conductor.answer("what did we discuss about clients", chat_id=-9101, surface="mc")
reply = res.get("reply", "")
ok("never leaks raw tool JSON", '{"tool"' not in reply and "recall_conversations" not in reply, reply[:140])
ok("flags a model issue instead", res.get("model_issue") is True)
ok("recall tool actually ran", "recall_conversations" in res.get("tools_used", []))

# 2. forced-final recovery: JSON on the first forced-final attempt, then real prose on retry.
lines = [_TOOL_JSON] * conductor.MAX_TOOL_STEPS + [_TOOL_JSON, "Here is what I found, sir: we talked about clients."]
mr.get_llm = lambda *a, **k: _Fake(lines)
res = conductor.answer("recap clients", chat_id=-9102, surface="mc")
ok("blunt retry recovers a prose answer", "we talked about clients" in res.get("reply", ""), res.get("reply", "")[:140])
ok("recovered answer is not a model issue", not res.get("model_issue"))
ok("recovered reply has no raw JSON", '{"tool"' not in res.get("reply", ""))

# 3. a normal prose answer passes through untouched (no false positives).
mr.get_llm = lambda *a, **k: _Fake(["Right away, sir — all systems are nominal."])
res = conductor.answer("status?", chat_id=-9103, surface="mc")
ok("clean answer passes through",
   res.get("reply") == "Right away, sir — all systems are nominal." and not res.get("model_issue"))

# 4. a prose answer that merely QUOTES JSON-looking text mid-sentence is still an answer,
#    not misclassified into the leak guard (guard only trips on a real leading/parseable call).
mr.get_llm = lambda *a, **k: _Fake(["Done, sir — I ran the recall and found 3 notes about clients."])
res = conductor.answer("recap", chat_id=-9104, surface="mc")
ok("prose mentioning a tool is not flagged", res.get("reply", "").startswith("Done, sir") and not res.get("model_issue"))

# 5. a legit fenced-JSON answer the owner asked for (no "tool" key) must pass through — the
#    guard is precise (only real {"tool":…} calls trip it), so no false positive here.
_json_answer = 'Here is a sample config, sir:\n```json\n{"port": 8080, "debug": true}\n```'
mr.get_llm = lambda *a, **k: _Fake([_json_answer])
res = conductor.answer("give me a sample config", chat_id=-9105, surface="mc")
ok("fenced JSON answer passes through",
   res.get("reply", "").startswith("Here is a sample config") and not res.get("model_issue"), res.get("reply", "")[:140])

print(f"\n🎉 ALL {PASS} CHECKS PASSED")

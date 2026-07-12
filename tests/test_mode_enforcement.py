"""
MODE CAPABILITY BOUNDARY + HUMAN REVIEW — server-side enforcement (#16 follow-up).

Isolated temp DB (DB_PATH env), plain python, no pytest:
    DB_PATH=/tmp/tmode.db python tests/test_mode_enforcement.py

Proves the selected mode is a REAL backend capability boundary, not just prompting:
  - chat_modes.denied_tools_for: Chat denies the terminal surface, Agent denies nothing;
  - the system prompt advertises the terminal tools ONLY when they're allowed;
  - conductor.answer REJECTS a denied tool server-side even if the model calls it (the
    terminal engine is never reached), and continues the turn;
  - Human Review = 'always' makes the backend authoritative — a low-risk act is PROPOSED
    for confirmation, never auto-run (the default policy still auto-runs it).
"""
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix="tobi_tmode_")
os.environ["DB_PATH"] = os.path.join(_TMP, "agent.db")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.database import init_database  # noqa: E402

init_database()

from core import conductor  # noqa: E402
from core import chat_modes as cm  # noqa: E402
from core import model_router as mr  # noqa: E402
from core import task_classifier as tc  # noqa: E402

tc.classify = lambda m: "QUESTION"   # force the tool-loop

PASS = 0


def ok(name: str, cond: bool, detail: str = ""):
    global PASS
    if not cond:
        print(f"❌ {name} {detail}")
        sys.exit(1)
    PASS += 1
    print(f"✅ {name}")


class _Fake:
    last_finish_reason = None

    def __init__(self, lines, default="All done, sir."):
        self.lines = list(lines)
        self.default = default

    def complete(self, messages, system=None, max_tokens=2000):
        return self.lines.pop(0) if self.lines else self.default


# ── 1. the deny policy ────────────────────────────────────────────────────────────
chat_ctx = cm.normalize("chat")
agent_ctx = cm.normalize("agent")
denied = cm.denied_tools_for(chat_ctx)
ok("chat denies run_command", "run_command" in denied and "install_package" in denied)
ok("chat denies whole terminal surface",
   {"configure_tool", "connect_tool", "kill_job", "set_terminal_mode"} <= denied)
ok("agent denies nothing", cm.denied_tools_for(agent_ctx) == set())

# ── 2. system prompt advertises terminal ONLY when allowed ────────────────────────
sp_agent = conductor._system_prompt("", True, "mc", denied_tools=set())
ok("agent prompt has TERMINAL section", "TERMINAL (#11)" in sp_agent and "run_command" in sp_agent)
sp_chat = conductor._system_prompt("", True, "mc", denied_tools=denied)
ok("chat prompt drops TERMINAL section", "TERMINAL (#11)" not in sp_chat)
ok("chat prompt states terminal unavailable", "shell/terminal tools are NOT available" in sp_chat)
ok("chat prompt hides run_command tool", "run_command" not in sp_chat)

# ── 3. denied tool is rejected server-side even if the model calls it ──────────────
term_exec: list = []
conductor._execute_terminal_and_log = lambda *a, **k: term_exec.append(a) or {"ok": True}
mr.get_llm = lambda *a, **k: _Fake([
    '{"tool":"run_command","args":{"command":"echo hi"}}',   # model tries a shell command
    "I can't run that in Chat mode, sir — switch to Agent.",  # then it answers
])
res = conductor.answer("run echo hi", chat_id=-9201, surface="mc",
                       denied_tools={"run_command", "install_package"})
ok("denied tool not in tools_used", "run_command" not in res.get("tools_used", []))
ok("terminal engine never invoked", term_exec == [])
ok("turn continues to a real answer", res.get("reply", "").startswith("I can't run that"))

# ── 4. Human Review = 'always' proposes acts instead of auto-running them ──────────
exec_calls: list = []
conductor._execute_and_log = lambda chat_id, surface, tool, args, risk: (
    exec_calls.append(tool) or {"ok": True, "summary": f"created {tool}"})

# default policy → the low-risk act auto-runs
mr.get_llm = lambda *a, **k: _Fake(['{"tool":"create_project","args":{"name":"Zeta"}}', "Done, sir."])
res = conductor.answer("make a project Zeta", chat_id=-9202, surface="mc")
ok("default: low-risk act auto-runs", "create_project" in exec_calls and not res.get("pending_action"))

# 'always' → the same act is proposed for confirmation, not executed
exec_calls.clear()
mr.get_llm = lambda *a, **k: _Fake(['{"tool":"create_project","args":{"name":"Zeta"}}', "Done, sir."])
res = conductor.answer("make a project Zeta", chat_id=-9203, surface="mc", review_mode="always")
pa = res.get("pending_action") or {}
ok("always: act is proposed, not run", pa.get("tool") == "create_project" and exec_calls == [], str(res)[:160])

print(f"\n🎉 ALL {PASS} CHECKS PASSED")

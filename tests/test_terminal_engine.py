"""
TOBI CLI (#11) — terminal_engine test suite (P0 + acquire).

Isolated temp DB (DB_PATH env), plain python, no pytest:
    DB_PATH=/tmp/t11.db python tests/test_terminal_engine.py

Covers: hybrid risk classifier, the hard denylist (Auto can't bypass), the two-axis
gate (plan/ask/accept/auto × low/medium/high), the kill-switch, secret redaction,
real command execution + exit codes, background jobs (start/list/kill), the capability
registry, and acquire command-building.
"""
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix="tobi_t11_")
os.environ["DB_PATH"] = os.path.join(_TMP, "agent.db")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.database import init_database  # noqa: E402
from core import terminal_engine as te   # noqa: E402

PASS = 0


def ok(name: str, cond: bool, detail: str = ""):
    global PASS
    if not cond:
        print(f"❌ {name} {detail}")
        sys.exit(1)
    PASS += 1
    print(f"✅ {name}")


init_database()

# ── 1. Risk classifier ───────────────────────────────────────────────────────────
ok("classify safe: ls", te.classify_risk("ls -la")[0] == "low")
ok("classify safe: git status", te.classify_risk("git status")[0] == "low")
ok("classify safe: pip list", te.classify_risk("pip list")[0] == "low")
ok("classify network: pip install", te.classify_risk("pip install requests")[0] == "medium")
ok("classify network: npm install", te.classify_risk("npm install -g typescript")[0] == "medium")
ok("classify network: curl", te.classify_risk("curl https://example.com")[0] == "medium")
ok("classify network: git clone", te.classify_risk("git clone https://github.com/x/y")[0] == "medium")
ok("classify danger: rm -rf dir", te.classify_risk("rm -rf ./build")[0] == "high")
ok("classify danger: git reset --hard", te.classify_risk("git reset --hard HEAD~3")[0] == "high")
ok("classify danger: git push --force", te.classify_risk("git push --force origin main")[0] == "high")
ok("ambiguous → medium", te.classify_risk("some-unknown-binary --do-thing")[0] == "medium")

# ── 2. Hard denylist (blocked in ANY mode) ────────────────────────────────────────
ok("deny rm -rf /", te.classify_risk("rm -rf /")[0] == "blocked")
ok("deny rm -rf ~", te.classify_risk("sudo rm -rf ~")[0] == "blocked")
ok("deny fork bomb", te.classify_risk(":(){ :|:& };:")[0] == "blocked")
ok("deny mkfs", te.classify_risk("mkfs.ext4 /dev/sda1")[0] == "blocked")
ok("deny dd to disk", te.classify_risk("dd if=/dev/zero of=/dev/sda")[0] == "blocked")
ok("deny format c:", te.classify_risk("format c:")[0] == "blocked")
ok("deny shutdown", te.classify_risk("shutdown /s /t 0")[0] == "blocked")

# ── 3. Self-modification forced high [D27] ────────────────────────────────────────
repo = str(te.REPO_ROOT).replace("\\", "/")
ok("self-modify: rm inside repo → high", te.classify_risk(f"rm -f {repo}/core/x.py")[0] in ("high", "blocked"))
ok("self-modify: pip install into own venv → high",
   te.classify_risk("pip install -e .")[0] == "high" or "self" in te.classify_risk("pip install requirements.txt")[1])

# ── 4. Two-axis gate ──────────────────────────────────────────────────────────────
te.set_enabled(True)

te.set_mode("plan")
ok("plan mode: safe → plan (no exec)", te.gate("ls", use_llm=False)["decision"] == "plan")
ok("plan mode: danger → plan", te.gate("rm -rf ./x", use_llm=False)["decision"] == "plan")
ok("plan mode: blocked still refuses", te.gate("rm -rf /", use_llm=False)["decision"] == "refuse")

te.set_mode("ask")
ok("ask: low → run", te.gate("ls", use_llm=False)["decision"] == "run")
ok("ask: medium → confirm", te.gate("pip install x", use_llm=False)["decision"] == "confirm")
ok("ask: high → confirm", te.gate("rm -rf ./x", use_llm=False)["decision"] == "confirm")

te.set_mode("accept")
ok("accept: medium → run", te.gate("pip install x", use_llm=False)["decision"] == "run")
ok("accept: high → confirm", te.gate("rm -rf ./x", use_llm=False)["decision"] == "confirm")

te.set_mode("auto")
ok("auto: high → run", te.gate("rm -rf ./x", use_llm=False)["decision"] == "run")
ok("auto: blocked STILL refuses", te.gate("rm -rf /", use_llm=False)["decision"] == "refuse")

# Telegram is capped at Ask [D18]
te.set_mode("auto")
ok("telegram caps auto→ask (high confirms)", te.gate("rm -rf ./x", surface="telegram", use_llm=False)["decision"] == "confirm")
ok("effective_mode telegram = ask", te.effective_mode("telegram") == "ask")

# ── 5. Kill-switch [D25] ──────────────────────────────────────────────────────────
te.set_mode("auto")
te.set_enabled(False)
ok("kill-switch: refuses even safe cmd", te.gate("ls", use_llm=False)["decision"] == "refuse")
te.set_enabled(True)
ok("kill-switch off: safe runs again", te.gate("ls", use_llm=False)["decision"] == "run")

# ── 6. Secret redaction [D25] ─────────────────────────────────────────────────────
red = te.redact("export API_KEY=sk-abcdef0123456789abcdef and token=ghp_ABCDEFGHIJKLMNOPQRSTUVWX")
ok("redact hides sk- key", "sk-abcdef0123456789" not in red)
ok("redact hides gh token", "ghp_ABCDEFGHIJKLMNOPQRSTUVWX" not in red)
os.environ["MY_FAKE_API_KEY"] = "supersecretvalue1234"
ok("redact env secret value", "supersecretvalue1234" not in te.redact("leaked supersecretvalue1234 here"))

# ── 7. Real execution ─────────────────────────────────────────────────────────────
res = te.run("echo tobi_terminal_ok", risk="low")
ok("run echo: exit 0", res.get("exit_code") == 0, str(res))
ok("run echo: output captured", "tobi_terminal_ok" in (res.get("output") or ""), str(res))
res_fail = te.run("exit 7" if not te.IS_WINDOWS else "cmd /c exit 7", risk="low")
ok("run nonzero exit surfaces", res_fail.get("exit_code") in (7, 1) or res_fail.get("ok") is False, str(res_fail))

# ── 8. Background jobs [D11] ───────────────────────────────────────────────────────
bg = te.run("echo bg_job_line", background=True, risk="low")
ok("background: job id issued", bg.get("job_id") and bg.get("background"), str(bg))
import time as _t
_t.sleep(1.2)
jid = bg["job_id"]
jobs = te.list_jobs()
ok("list_jobs returns the job", any(j["id"] == jid for j in jobs["jobs"]))
job = te.get_job(jid)
ok("job finished with output", job.get("status") in ("done", "failed") and "bg_job_line" in (job.get("output") or ""), str(job))
# start a long job and kill it
longcmd = "ping -n 20 127.0.0.1" if te.IS_WINDOWS else "sleep 20"
bg2 = te.run(longcmd, background=True, risk="low")
_t.sleep(0.4)
killed = te.kill_job(bg2["job_id"])
ok("kill_job stops a running job", killed.get("ok"), str(killed))

# ── 9. Capability registry [D15] ──────────────────────────────────────────────────
te.register_tool("ripgrep", version="14.0", channel="scoop", how_to_use="rg <pattern>")
tools = te.list_tools()
ok("register_tool stored", any(t["name"] == "ripgrep" for t in tools["tools"]))
te.set_tool_wired("ripgrep", True)
ok("set_tool_wired", any(t["name"] == "ripgrep" and t["wired"] for t in te.list_tools()["tools"]))

# ── 10. Acquire command-building [D13] ─────────────────────────────────────────────
ok("install_command pip", te.install_command("pip", "requests") == "pip install requests")
ok("install_command winget", "winget install" in (te.install_command("winget", "Git.Git") or ""))
ok("install_command rejects injection", te.install_command("pip", "requests; rm -rf /") is None)
ok("install_command unknown manager", te.install_command("bogus", "x") is None)

# ── 11. Status card ───────────────────────────────────────────────────────────────
st = te.status()
ok("status has mode+os+shell", st.get("mode") in te.MODES and st.get("os") and st.get("shell"))

# ── 12. Conductor integration (LLM-stubbed) — gate → run → audit, and confirm flow ─
from core import conductor  # noqa: E402
import core.model_router as mr  # noqa: E402
import core.task_classifier as tc  # noqa: E402

tc.classify = lambda m: "QUESTION"   # force the tool-loop (not smalltalk/coding)


class _Fake:
    """Emits one tool call, then a final answer."""
    last_finish_reason = None

    def __init__(self, tool_json):
        self.tool_json = tool_json
        self.n = 0

    def complete(self, messages, system=None, max_tokens=2000):
        self.n += 1
        return self.tool_json if self.n == 1 else "Done, sir — that's handled."


# a) low-risk command auto-runs and is audited
te.set_mode("ask")
mr.get_llm = lambda *a, **k: _Fake('{"tool":"run_command","args":{"command":"echo conductor_terminal_ok"}}')
res = conductor.answer("run echo conductor_terminal_ok", chat_id=-9911, surface="mc")
ok("conductor used run_command", "run_command" in res.get("tools_used", []), str(res))
acts = conductor.list_actions(limit=20, chat_id=-9911)
ok("terminal command audited as executed",
   any(a["tool"] == "run_command" and a["status"] == "executed" for a in acts["actions"]), str(acts))

# b) medium (network) command under Ask → PROPOSED for confirmation (not auto-run)
mr.get_llm = lambda *a, **k: _Fake('{"tool":"run_command","args":{"command":"pip install some-pkg-xyz"}}')
res2 = conductor.answer("install some-pkg-xyz", chat_id=-9912, surface="mc")
ok("medium terminal → pending_action", res2.get("pending_action") is not None, str(res2))
ok("proposed risk = medium", (res2.get("pending_action") or {}).get("risk") == "medium", str(res2))
# reject it (so we never actually hit the network in the test)
conductor.confirm_action(res2["pending_action"]["id"], "reject", "mc", -9912)
acts2 = conductor.list_actions(limit=5, chat_id=-9912)
ok("rejected proposal recorded", any(a["status"] == "rejected" for a in acts2["actions"]))

# c) Telegram caps at Ask — a medium command is proposed there too (not silently blocked)
mr.get_llm = lambda *a, **k: _Fake('{"tool":"run_command","args":{"command":"pip install another-pkg"}}')
res3 = conductor.answer("install another-pkg", chat_id=-9913, surface="telegram")
ok("telegram terminal medium → pending_action", res3.get("pending_action") is not None, str(res3))
conductor.confirm_action(res3["pending_action"]["id"], "reject", "telegram", -9913)

# d) plan mode previews without executing
te.set_mode("plan")
mr.get_llm = lambda *a, **k: _Fake('{"tool":"run_command","args":{"command":"echo should_not_run_in_plan"}}')
before = len(conductor.list_actions(limit=100, chat_id=-9914)["actions"])
conductor.answer("run echo should_not_run_in_plan", chat_id=-9914, surface="mc")
after = len(conductor.list_actions(limit=100, chat_id=-9914)["actions"])
ok("plan mode executes nothing (no audit rows)", after == before)
te.set_mode("ask")

# e) direct terminal tool functions
ok("tool_run_command echo", conductor.tool_run_command(command="echo direct_ok").get("exit_code") == 0)
ok("tool_terminal_status", conductor.tool_terminal_status().get("mode") in te.MODES)
ok("tool_list_jobs shape", "jobs" in conductor.tool_list_jobs())
ok("_terminal_command_for install", conductor._terminal_command_for("install_package", {"package": "rich", "manager": "pip"}) == "pip install rich")

# ── 13. Acquire — configure_tool / connect_tool / registry / hermes mirror [D14][D15] ─
cfg_path = os.path.join(_TMP, "mytool.cfg")
cres = conductor.tool_configure_tool(name="mytool", path=cfg_path, content="hello=1\n")
ok("configure_tool writes config", cres.get("ok") and os.path.exists(cfg_path))
os.environ["MYTOOL_TOKEN"] = "abc123def456ghi"
conres = conductor.tool_connect_tool(name="mytool", secret_name="MYTOOL_TOKEN")
ok("connect_tool references existing env credential", conres.get("ok") and conres.get("credential_found"))
conres2 = conductor.tool_connect_tool(name="mytool", secret_name="NONEXISTENT_CRED_XYZ")
ok("connect_tool refuses a missing credential", bool(conres2.get("error")))
ok("registry shows configured/connected tool", any(t["name"] == "mytool" for t in te.list_tools()["tools"]))
_skill = os.path.join(os.path.expanduser("~"), ".hermes", "skills", "ripgrep.md")
ok("hermes skill mirror written", os.path.exists(_skill))

print(f"\n🎉 ALL TERMINAL ENGINE TESTS PASSED ({PASS} checks)")

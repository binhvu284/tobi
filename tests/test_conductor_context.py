"""
CONDUCTOR CONTEXT (queue #20 Phase A) — owner memory reaches the system prompt exactly once.

Isolated temp DB (DB_PATH env), plain python, no pytest:
    DB_PATH=/tmp/tcc.db python tests/test_conductor_context.py

Drives conductor.answer() with a stubbed model and captures the system prompt to prove:
the butler persona still anchors it (index 0); owner memory appears ONCE (in its dedicated
slot, not also duplicated into TURN CONTEXT); untrusted project context lands in TURN CONTEXT;
and the legacy (no-manifest) branch still injects the profile unconditionally.
"""
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix="tobi_tcc_")
os.environ["DB_PATH"] = os.path.join(_TMP, "agent.db")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from core.database import init_database, get_connection  # noqa: E402

init_database()

from core import context_manager as CM  # noqa: E402
from core import conductor as C  # noqa: E402
from core import model_router as mr  # noqa: E402

PASS = 0


def ok(name: str, cond: bool, detail: str = ""):
    global PASS
    if not cond:
        print(f"❌ {name} {detail}")
        sys.exit(1)
    PASS += 1
    print(f"✅ {name}")


def _add(category: str, content: str, confidence: float = 0.95):
    conn = get_connection()
    conn.execute("INSERT INTO brain_memories (content, category, confidence, status) VALUES (?,?,?, 'active')",
                 (content, category, confidence))
    conn.commit()
    conn.close()


class _CapFake:
    """Captures each system prompt, then returns a plain final answer (no tool calls)."""
    def __init__(self):
        self.systems = []

    def complete(self, messages, system=None, max_tokens=2000):
        self.systems.append(system or "")
        return "Very good, sir."


_add("identity", "OWNERSNIPPET the owner is a solo founder building TOBI.", 0.95)
CM.invalidate()

# ── manifest branch: owner memory + untrusted project context ───────────────────────
manifest = CM.build_manifest("status of the project", "chat", [],
                             {"context_text": "PROJSNIPPET uploaded resource text", "projects": [{"id": 1, "name": "Alpha"}]})
_orig = mr.get_llm
fake = _CapFake()
mr.get_llm = lambda *a, **k: fake
try:
    C.answer("status of the project", chat_id=-5551, surface="mc", mode="chat", context_manifest=manifest)
finally:
    mr.get_llm = _orig

sysp = fake.systems[0]
ok("butler persona anchors the system prompt (index 0)", sysp.startswith(C._BUTLER[:120]))
ok("owner memory appears EXACTLY once (no double injection)", sysp.count("OWNERSNIPPET") == 1, str(sysp.count("OWNERSNIPPET")))
ok("owner memory is in the persona slot", "What you know about the owner" in sysp and "OWNERSNIPPET" in sysp)
_turn_idx = sysp.find("TURN CONTEXT (evidence")
ok("a TURN CONTEXT section exists", _turn_idx != -1)
ok("owner memory is NOT inside TURN CONTEXT", "OWNERSNIPPET" not in sysp[_turn_idx:])
ok("untrusted project context IS inside TURN CONTEXT", "PROJSNIPPET" in sysp[_turn_idx:])
ok("project content carries the untrusted fence", CM.UNTRUSTED_FENCE.strip() in sysp)

# ── legacy branch (no manifest): profile injected unconditionally, once ─────────────
fake2 = _CapFake()
mr.get_llm = lambda *a, **k: fake2
try:
    C.answer("hello there", chat_id=-5552, surface="mc", mode="chat", context_manifest=None)
finally:
    mr.get_llm = _orig
sysl = fake2.systems[0]
ok("legacy branch still anchors the butler persona", sysl.startswith(C._BUTLER[:120]))
ok("legacy branch injects the owner profile unconditionally (rollback path intact)",
   sysl.count("OWNERSNIPPET") == 1, str(sysl.count("OWNERSNIPPET")))

print(f"\n🎉 ALL {PASS} CHECKS PASSED")

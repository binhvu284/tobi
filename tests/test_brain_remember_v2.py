"""
Brain Memory V2 Remember routing (queue #20, T04) — off/shadow/on behind
owner_flags.brain_v2_mode(), legacy response shape preserved, flag rollback
restores the legacy path, sensitive content never mirrored to legacy plaintext.

Plain python, no pytest, isolated temp DB (offline: LLM extraction returns None
→ deterministic heuristic path):
    python tests/test_brain_remember_v2.py
"""
import os
import sys
import tempfile

os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="tobi_br4_"), "agent.db")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from core.database import init_database, get_connection  # noqa: E402
from core import vault, owner_flags  # noqa: E402
from core import brain  # noqa: E402
from core import brain_remember_v2 as brv2  # noqa: E402
from core.brain_contracts import MemoryType, Explicitness, MemoryStatus  # noqa: E402

init_database()
conn = get_connection()
vault.setup(conn, "master-pass-123456", import_env=False)  # unlocked

# full determinism: force the heuristic extraction path (offline the LLM returns
# None anyway; this pins it)
brv2.llm_candidate = lambda *a, **k: None

PASS = 0


def ok(name: str, cond: bool, detail: str = ""):
    global PASS
    if not cond:
        print(f"❌ {name} {detail}")
        sys.exit(1)
    PASS += 1
    print(f"✅ {name}")


def v2_count():
    return conn.execute("SELECT count(*) FROM brain_memory_v2").fetchone()[0]


def legacy_count():
    return conn.execute("SELECT count(*) FROM brain_memories WHERE deleted_at IS NULL").fetchone()[0]


def set_mode(mode: str):
    owner_flags.set_bool(owner_flags.BRAIN_V2_ENABLED, mode == "on")
    owner_flags.set_bool(owner_flags.BRAIN_V2_SHADOW, mode == "shadow")


# ── extraction units ─────────────────────────────────────────────────────────
c = brv2.heuristic_candidate("Owner prefers green tea over coffee", category="preferences")
ok("heuristic maps legacy category to type", c.memory_type is MemoryType.PREFERENCE)
ok("heuristic keeps category as tag", c.tags == ("preferences",))
ok("heuristic is explicit + activatable score", c.explicitness is Explicitness.EXPLICIT
   and c.quality_score >= 70 and c.confidence >= 0.85, str(c.quality_score))
ok("heuristic flags sensitive content",
   brv2.heuristic_candidate("Owner's bank account number ends 991").sensitive is True)
ok("health category defaults sensitive",
   brv2.heuristic_candidate("Owner sleeps 6 hours", category="health").sensitive is True)

# the floor guards the LLM path: stub an extraction that trash-scores the input
from core.brain_contracts import MemoryCandidate  # noqa: E402
brv2.llm_candidate = lambda content, *a, **k: MemoryCandidate(
    distilled_text=content, memory_type=MemoryType.FACT, explicitness=Explicitness.EXPLICIT)
fl = brv2.extract_candidate("ok cool thanks", category=None)
ok("explicit remember never auto-trashed (floored to pending band)",
   fl.quality_score == 35.0 and "low_quality_explicit" in fl.tags, str(fl.quality_score))
brv2.llm_candidate = lambda *a, **k: None  # back to deterministic heuristic

# ── mode off (default): legacy path, no V2 side effects ──────────────────────
ok("default mode is off", owner_flags.brain_v2_mode() == "off")
r = brain.remember("Owner starts work at 8am", "habits")
ok("off: legacy shape", r["ok"] is True and r["action"] == "active" and isinstance(r["id"], int))
ok("off: no v2 key", "v2" not in r)
ok("off: zero V2 rows", v2_count() == 0)

# ── shadow: legacy unchanged + V2 alongside ──────────────────────────────────
set_mode("shadow")
ok("mode is shadow", owner_flags.brain_v2_mode() == "shadow")
before_legacy = legacy_count()
r = brain.remember("Owner prefers concise, direct replies", "preferences")
ok("shadow: legacy keys unchanged", r["ok"] is True and r["action"] == "active"
   and isinstance(r["id"], int) and r["category"] == "preferences")
ok("shadow: legacy row written", legacy_count() == before_legacy + 1)
ok("shadow: additive v2 key", r.get("v2", {}).get("outcome") == "active", str(r.get("v2")))
row = conn.execute("SELECT compat_ref, status FROM brain_memory_v2 WHERE id=?",
                   (r["v2"]["id"],)).fetchone()
ok("shadow: V2 row linked to legacy row", row["compat_ref"] == r["id"] and row["status"] == "active")

# shadow duplicate: V2 merges (1 row), legacy keeps writing (offline dedup inert)
r2 = brain.remember("The owner prefers concise, direct replies", "preferences")
ok("shadow duplicate: V2 merged, no second V2 row",
   r2.get("v2", {}).get("outcome") == "merged" and
   conn.execute("SELECT count(*) FROM brain_memory_v2 WHERE status != 'rejected'").fetchone()[0] == 1)

# shadow + sensitive + locked vault: legacy still succeeds, V2 quietly skipped
vault.lock()
before_v2 = v2_count()
r = brain.remember("Owner's bank account password hint is a pet name", "identity")
ok("shadow locked-vault sensitive: legacy still ok", r["ok"] is True and r["action"] == "active")
ok("shadow locked-vault sensitive: v2 skipped, no row, no crash",
   "v2" not in r and v2_count() == before_v2)
vault.unlock(conn, "master-pass-123456")

# ── on: V2 authoritative, legacy compat row, legacy shape ────────────────────
set_mode("on")
ok("mode is on", owner_flags.brain_v2_mode() == "on")
r = brain.remember("Owner's favorite editor is VS Code", "work")
ok("on: legacy shape preserved", r["ok"] is True and r["action"] == "active"
   and isinstance(r["id"], int) and r["category"] == "work")
ok("on: v2 active", r["v2"]["outcome"] == "active")
lrow = conn.execute("SELECT content, status, source FROM brain_memories WHERE id=?", (r["id"],)).fetchone()
ok("on: legacy compat row written",
   lrow is not None and lrow["content"] == "Owner's favorite editor is VS Code"
   and lrow["status"] == "active" and lrow["source"] == "remember")
ok("on: V2 row links back",
   conn.execute("SELECT compat_ref FROM brain_memory_v2 WHERE id=?", (r["v2"]["id"],)).fetchone()[0] == r["id"])
first_legacy_id = r["id"]

# on duplicate → merged, same legacy id, no extra V2 row
v2_before = v2_count()
r = brain.remember("The owner's favorite editor is VS Code", "work")
ok("on duplicate: merged with legacy id preserved",
   r["action"] == "merged" and r["id"] == first_legacy_id and r["v2"]["outcome"] == "merged")
ok("on duplicate: no new V2 row", v2_count() == v2_before)

# on conflict → pending both sides
r = brain.remember("Owner's favorite editor is Neovim", "work")
ok("on conflict: action pending", r["action"] == "pending" and r["v2"]["outcome"] == "conflicted")
ok("on conflict: legacy compat row pending",
   conn.execute("SELECT status FROM brain_memories WHERE id=?", (r["id"],)).fetchone()[0] == "pending")

# on sensitive (vault unlocked): V2 encrypted, NO legacy plaintext
before_legacy = legacy_count()
r = brain.remember("Owner's banking alias is REMEMBER_SECRET_3327", "identity")
ok("on sensitive: queues with no legacy id", r["ok"] is True and r["id"] is None and r["action"] == "pending")
ok("on sensitive: no legacy row written", legacy_count() == before_legacy)
ok("on sensitive: V2 row pending + redacted column",
   conn.execute("SELECT status, distilled_text FROM brain_memory_v2 WHERE id=?",
                (r["v2"]["id"],)).fetchone()["distilled_text"] == "[sensitive:redacted]")
leak = any("REMEMBER_SECRET_3327" in str(x[0] or "") for t, col in
           (("brain_memories", "content"), ("brain_memory_v2", "distilled_text"),
            ("brain_memory_evidence", "excerpt"))
           for x in conn.execute(f"SELECT {col} FROM {t}").fetchall())
ok("on sensitive: plaintext nowhere", not leak)

# on sensitive + locked vault: falls back to legacy exactly, says why
vault.lock()
r = brain.remember("Owner's medical checkup is on the 12th", "health")
ok("on locked-vault sensitive: legacy fallback shape",
   r["ok"] is True and r["action"] == "active" and isinstance(r["id"], int))
ok("on locked-vault sensitive: v2 skip reason", r.get("v2", {}).get("skipped") == "vault_locked")
vault.unlock(conn, "master-pass-123456")

# ── rollback: flags off restores the legacy path ─────────────────────────────
set_mode("off")
v2_before, legacy_before = v2_count(), legacy_count()
r = brain.remember("Owner reviews the queue after breakfast", "habits")
ok("rollback: legacy shape, no v2 key", r["ok"] is True and r["action"] == "active" and "v2" not in r)
ok("rollback: no new V2 rows", v2_count() == v2_before)
ok("rollback: legacy row written as before", legacy_count() == legacy_before + 1)

print(f"\n{PASS} checks passed")

"""
Brain Memory V2 legacy migration (queue #20, T06) — grouped reclassification
preview, owner-approved apply with resumable ledger, legacy rows never modified.

Plain python, no pytest, isolated temp DB:
    python tests/test_brain_migration.py
"""
import os
import sys
import tempfile

os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="tobi_bmig_"), "agent.db")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from core.database import init_database, get_connection  # noqa: E402
from core import vault  # noqa: E402
from core import brain  # noqa: E402
from core import brain_migration as mig  # noqa: E402

init_database()
conn = get_connection()

PASS = 0


def ok(name: str, cond: bool, detail: str = ""):
    global PASS
    if not cond:
        print(f"❌ {name} {detail}")
        sys.exit(1)
    PASS += 1
    print(f"✅ {name}")


def raises(fn, exc=Exception) -> bool:
    try:
        fn()
    except exc:
        return True
    except Exception:
        return False
    return False


def count(sql, args=()):
    return conn.execute(sql, args).fetchone()[0]


# ── seed a legacy store (the read-only migration source) ─────────────────────
L = {}
L["name"] = brain.add_memory("Owner's full name is Vu Le Binh", "identity", 0.9, "remember", status="active")
L["coffee"] = brain.add_memory("Owner prefers dark roast coffee in the morning", "preferences", 0.9, "remember", status="active")
L["night"] = brain.add_memory("Owner tends to check dashboards late at night", "habits", 0.9, "auto", status="active")
L["tea1"] = brain.add_memory("Owner drinks green tea every single day", "preferences", 0.9, "remember", status="active")
L["tea2"] = brain.add_memory("The owner drinks green tea every single day", "preferences", 0.85, "remember", status="active")
L["ed1"] = brain.add_memory("Owner's favorite editor is VS Code", "work", 0.9, "remember", status="active")
L["ed2"] = brain.add_memory("Owner's favorite editor is Neovim", "work", 0.9, "remember", status="active")
L["bank"] = brain.add_memory("Owner's bank password hint is the cat name MIGRATE_SECRET_5150", "identity", 0.9, "remember", status="active")
L["noise"] = brain.add_memory("ok cool", "identity", 0.9, "remember", status="active")

legacy_before = conn.execute(
    "SELECT id, content, category, confidence, source, status FROM brain_memories ORDER BY id").fetchall()
legacy_before = [tuple(r) for r in legacy_before]

# ── deterministic mapping units ───────────────────────────────────────────────
c = mig.legacy_candidate(conn.execute("SELECT * FROM brain_memories WHERE id=?", (L["name"],)).fetchone())
ok("explicit legacy row maps explicit + active-band score",
   c.explicitness.value == "explicit" and c.quality_score >= 70, str(c.quality_score))
c = mig.legacy_candidate(conn.execute("SELECT * FROM brain_memories WHERE id=?", (L["night"],)).fetchone())
ok("auto-sourced legacy row maps inferred", c.explicitness.value == "inferred")
c = mig.legacy_candidate(conn.execute("SELECT * FROM brain_memories WHERE id=?", (L["noise"],)).fetchone())
ok("noise legacy row scores below reject line", c.quality_score < 35, str(c.quality_score))
c = mig.legacy_candidate(conn.execute("SELECT * FROM brain_memories WHERE id=?", (L["bank"],)).fetchone())
ok("sensitive legacy row detected", c.sensitive is True)

# ── run lifecycle: locked vault fails closed; preview is checkpointed ────────
ok("locked vault blocks a migration run", raises(lambda: mig.create_run(conn=conn), vault.VaultLocked))
vault.setup(conn, "master-pass-123456", import_env=False)

run = mig.create_run(conn=conn)
st = mig.run_status(run, conn=conn)
ok("run created with ledger snapshot", st["status"] == "preview"
   and st["snapshot"]["legacy_by_status"].get("active") == 9 and st["total_legacy"] == 9)

st = mig.step_run(run, conn=conn)
ok("one step previews one legacy row, checkpoint persisted",
   st["scanned"] == 1 and st["next_legacy_id"] == L["name"])
# 'restart': resume purely from the DB checkpoint
st = mig.run_preview(run, conn=conn)
ok("resume completes preview", st["status"] == "ready" and st["scanned"] == 9 and st["errors"] == 0)

ok("dry preview wrote nothing to the V2 store", count("SELECT count(*) FROM brain_memory_v2") == 0)
g = st["groups"]
ok("grouped proposals match the spec mappings",
   g.get("reclassify") == 5 and g.get("duplicate") == 1 and g.get("conflict") == 1
   and g.get("sensitive") == 1 and g.get("noise") == 1, str(g))

items = {x["legacy_id"]: x for x in mig.list_items(run, conn=conn)}
ok("duplicate points at its intra-run partner", items[L["tea2"]]["matched_legacy_id"] == L["tea1"])
ok("conflict points at its intra-run partner", items[L["ed2"]]["matched_legacy_id"] == L["ed1"])
ok("inferred legacy row proposed pending", items[L["night"]]["proposed_status"] == "pending")
ok("noise proposed rejected", items[L["noise"]]["proposed_outcome"] == "rejected")
ok("sensitive item stored encrypted in the preview table",
   count("SELECT count(*) FROM brain_migration_items WHERE legacy_id=? AND candidate_json IS NULL "
         "AND enc_ct IS NOT NULL", (L["bank"],)) == 1
   and count("SELECT count(*) FROM brain_migration_items WHERE candidate_json LIKE '%MIGRATE_SECRET_5150%'") == 0)

# ── triage: bulk by group + individual decisions ─────────────────────────────
ok("bulk approve reclassify", mig.bulk_decide(run, True, group="reclassify", conn=conn) == 5)
ok("bulk approve duplicate", mig.bulk_decide(run, True, group="duplicate", conn=conn) == 1)
mig.set_decision(items[L["ed2"]]["id"], True, conn=conn)    # the conflict — owner keeps both for review
mig.set_decision(items[L["bank"]]["id"], True, conn=conn)   # sensitive — encrypt into V2
# noise left undecided → never applied

# ── apply: resumable approved batches; legacy untouched ─────────────────────
r1 = mig.apply_run(run, conn=conn, max_items=2)
ok("interrupted apply: 2 applied, 6 remaining, run still ready",
   r1["applied_now"] == 2 and r1["remaining_approved"] == 6 and r1["status"] == "ready", str(r1))
r2 = mig.apply_run(run, conn=conn)
ok("resumed apply completes without double-applying",
   r2["applied_now"] == 6 and r2["remaining_approved"] == 0 and r2["status"] == "applied"
   and r2["applied"] == 8)

items = {x["legacy_id"]: x for x in mig.list_items(run, conn=conn)}
ok("undecided noise was not applied", items[L["noise"]]["applied_memory_id"] is None)
ok("explicit fact migrated active with compat_ref",
   conn.execute("SELECT status, compat_ref FROM brain_memory_v2 WHERE id=?",
                (items[L["name"]]["applied_memory_id"],)).fetchone()["compat_ref"] == L["name"]
   and conn.execute("SELECT status FROM brain_memory_v2 WHERE id=?",
                    (items[L["name"]]["applied_memory_id"],)).fetchone()[0] == "active")
ok("inferred migrated pending",
   conn.execute("SELECT status FROM brain_memory_v2 WHERE id=?",
                (items[L["night"]]["applied_memory_id"],)).fetchone()[0] == "pending")
ok("duplicate pair merged into one V2 row (evidence preserved)",
   items[L["tea2"]]["applied_memory_id"] == items[L["tea1"]]["applied_memory_id"]
   and count("SELECT count(*) FROM brain_memory_evidence WHERE memory_id=?",
             (items[L["tea1"]]["applied_memory_id"],)) >= 2)
ok("conflict pair linked, newcomer pending",
   count("SELECT count(*) FROM brain_memory_links WHERE link_type='conflicts_with' AND from_id=? AND to_id=?",
         (items[L["ed2"]]["applied_memory_id"], items[L["ed1"]]["applied_memory_id"])) == 1
   and conn.execute("SELECT status FROM brain_memory_v2 WHERE id=?",
                    (items[L["ed2"]]["applied_memory_id"],)).fetchone()[0] == "pending")
ok("sensitive migrated encrypted (pending, redacted column, no plaintext leak)",
   conn.execute("SELECT status, distilled_text FROM brain_memory_v2 WHERE id=?",
                (items[L["bank"]]["applied_memory_id"],)).fetchone()["distilled_text"] == "[sensitive:redacted]"
   and count("SELECT count(*) FROM brain_memory_v2 WHERE distilled_text LIKE '%MIGRATE_SECRET_5150%'") == 0)

legacy_after = [tuple(r) for r in conn.execute(
    "SELECT id, content, category, confidence, source, status FROM brain_memories ORDER BY id").fetchall()]
ok("legacy rows completely untouched (acceptance)", legacy_after == legacy_before)

# ── cancel path ──────────────────────────────────────────────────────────────
run2 = mig.create_run(conn=conn)
mig.run_preview(run2, conn=conn, max_steps=3)
mig.cancel_run(run2, conn=conn)
ok("cancel purges items and closes the run",
   mig.run_status(run2, conn=conn)["status"] == "cancelled"
   and count("SELECT count(*) FROM brain_migration_items WHERE run_id=?", (run2,)) == 0)

print(f"\n{PASS} checks passed")

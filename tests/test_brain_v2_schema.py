"""
BRAIN MEMORY V2 schema (queue #20, T01) — additive migration, isolated temp DB.

Plain python, no pytest:
    python tests/test_brain_v2_schema.py

Covers: the four additive V2 tables exist with expected columns; legacy
brain_memories is untouched and still readable/writable; the migration is
idempotent (init twice); V2 rows insert; and an anti-drift check that the
brain_memory_v2 DDL lives only in database.py (the owner_settings lesson).
"""
import os
import sys
import tempfile

os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="tobi_bv2_"), "agent.db")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from core.database import init_database, get_connection  # noqa: E402

init_database()

PASS = 0


def ok(name: str, cond: bool, detail: str = ""):
    global PASS
    if not cond:
        print(f"❌ {name} {detail}")
        sys.exit(1)
    PASS += 1
    print(f"✅ {name}")


conn = get_connection()


def tables() -> set:
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}


def cols(table: str) -> set:
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}


# ── V2 tables exist ──────────────────────────────────────────────────────────
t = tables()
for name in ("brain_memory_v2", "brain_memory_evidence", "brain_memory_links", "brain_memory_tags"):
    ok(f"table {name} exists", name in t)

v2cols = cols("brain_memory_v2")
for col in ("compat_ref", "distilled_text", "memory_type", "behavior_implication", "scope_type",
            "scope_key", "authority", "explicitness", "confidence", "quality_score",
            "trust", "sensitive", "status"):
    ok(f"brain_memory_v2.{col} present", col in v2cols)

# ── legacy untouched ─────────────────────────────────────────────────────────
ok("legacy brain_memories present", "brain_memories" in t)
ok("legacy brain_memory_versions present", "brain_memory_versions" in t)
ok("legacy columns intact",
   {"content", "category", "confidence", "source", "status", "embedding", "deleted_at"} <= cols("brain_memories"),
   str(cols("brain_memories")))

# ── idempotency ──────────────────────────────────────────────────────────────
init_database()
cnt = conn.execute(
    "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='brain_memory_v2'").fetchone()[0]
ok("migration idempotent (brain_memory_v2 single)", cnt == 1, str(cnt))

# ── legacy writable + readable ───────────────────────────────────────────────
from core import brain  # noqa: E402
try:
    mid = brain.add_memory("Owner's name is Thomas", category="identity", confidence=0.9)
except Exception:
    cur = conn.execute("INSERT INTO brain_memories (content, category, confidence) VALUES (?,?,?)",
                       ("Owner's name is Thomas", "identity", 0.9))
    conn.commit()
    mid = cur.lastrowid
row = conn.execute("SELECT content FROM brain_memories WHERE id=?", (mid,)).fetchone()
ok("legacy brain_memories writable + readable", bool(row) and row[0] == "Owner's name is Thomas")

# ── V2 tables writable ───────────────────────────────────────────────────────
v2id = conn.execute(
    "INSERT INTO brain_memory_v2 (distilled_text, memory_type, status, quality_score) VALUES (?,?,?,?)",
    ("prefers concise replies", "preference", "pending", 80.0)).lastrowid
conn.execute("INSERT INTO brain_memory_evidence (memory_id, excerpt, trust) VALUES (?,?,?)",
             (v2id, "owner said so", "trusted"))
conn.execute("INSERT INTO brain_memory_tags (memory_id, tag) VALUES (?,?)", (v2id, "tone"))
conn.execute("INSERT INTO brain_memory_links (from_id, to_id, link_type) VALUES (?,?,?)",
             (v2id, v2id, "supports"))
conn.commit()
ok("v2 row inserted", conn.execute("SELECT count(*) FROM brain_memory_v2").fetchone()[0] == 1)
ok("evidence row inserted",
   conn.execute("SELECT count(*) FROM brain_memory_evidence WHERE memory_id=?", (v2id,)).fetchone()[0] == 1)
ok("tag row inserted",
   conn.execute("SELECT count(*) FROM brain_memory_tags WHERE memory_id=?", (v2id,)).fetchone()[0] == 1)
ok("link row inserted",
   conn.execute("SELECT count(*) FROM brain_memory_links WHERE from_id=?", (v2id,)).fetchone()[0] == 1)

conn.close()

# ── anti-drift: V2 DDL only in database.py ───────────────────────────────────
core_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "core")
ddl = "CREATE TABLE IF NOT EXISTS brain_memory_v2"
hits = sorted(
    fn for fn in os.listdir(core_dir)
    if fn.endswith(".py")
    and ddl in open(os.path.join(core_dir, fn), encoding="utf-8", errors="ignore").read())
ok("brain_memory_v2 DDL only in database.py", hits == ["database.py"], str(hits))

print(f"\n{PASS} checks passed")

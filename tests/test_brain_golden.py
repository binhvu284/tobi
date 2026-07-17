"""
Brain Memory V2 golden set runner (queue #20, T03) — spec §Testing gate:
"a golden set of at least 60 examples covering trash, facts, preferences,
corrections, frustration, duplicates, conflicts, inference, sensitive data, and
prompt injection", each receiving a deterministic status and validated links.

Plain python, no pytest, isolated temp DB:
    python tests/test_brain_golden.py

Data: tests/golden/brain_memory_golden.json (ingested in file order).
"""
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="tobi_bg_"), "agent.db")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from core.database import init_database, get_connection  # noqa: E402
from core import vault  # noqa: E402
from core import brain_repository as repo  # noqa: E402
from core.brain_ingest import candidate_from_dict, ingest, REJECTED_SENSITIVE_META  # noqa: E402

init_database()
conn = get_connection()
vault.setup(conn, "master-pass-123456", import_env=False)

PASS = 0


def ok(name: str, cond: bool, detail: str = ""):
    global PASS
    if not cond:
        print(f"❌ {name} {detail}")
        sys.exit(1)
    PASS += 1
    print(f"✅ {name}")


PRESETS = {
    "strong": {"durability": 1, "actionability": 1, "specificity": 1, "source_strength": 1},
    "mid": {"durability": 1, "actionability": 1},
    "weak": {"durability": 0.3, "actionability": 0.3, "specificity": 0.3},
    "none": {},
}

data = json.loads((Path(__file__).parent / "golden" / "brain_memory_golden.json").read_text(encoding="utf-8"))
entries = data["entries"]

ids: dict[str, int] = {}          # gid -> memory row id
categories: dict[str, int] = {}

for e in entries:
    raw = dict(e["candidate"])
    for k, v in PRESETS[e.get("preset", "none")].items():
        raw.setdefault(k, v)
    res = ingest(candidate_from_dict(raw), conn=conn)
    exp = e["expect"]
    cond = res.outcome == exp["outcome"]
    detail = f"outcome={res.outcome}"
    if cond and "status" in exp:
        cond = res.status is not None and res.status.value == exp["status"]
        detail += f" status={res.status.value if res.status else None}"
    if cond and "matched_gid" in exp:
        cond = res.matched_id == ids.get(exp["matched_gid"])
        detail += f" matched={res.matched_id} want={ids.get(exp['matched_gid'])}"
    if cond and exp.get("retained_placeholder"):
        row = repo.read(res.memory_id, conn=conn)
        cond = row.distilled_text == REJECTED_SENSITIVE_META and row.sensitive is False
        detail += f" text={row.distilled_text!r}"
    ok(f"[{e['category']}] {e['gid']} → {exp['outcome']}", cond, detail)
    ids[e["gid"]] = res.memory_id
    categories[e["category"]] = categories.get(e["category"], 0) + 1

# ── aggregate release-gate checks ────────────────────────────────────────────
ok("golden set has >= 60 entries", len(entries) >= 60, str(len(entries)))
ok("all 10 spec categories covered", set(categories) == {
    "trash", "facts", "preferences", "corrections", "frustration",
    "duplicates", "conflicts", "inference", "sensitive", "injection"}, str(sorted(categories)))

ok("zero untrusted hard rules active (injection gate)",
   conn.execute("SELECT count(*) FROM brain_memory_v2 WHERE trust='untrusted' AND authority='hard' "
                "AND status='active'").fetchone()[0] == 0)
ok("zero sensitive memories active without approval",
   conn.execute("SELECT count(*) FROM brain_memory_v2 WHERE sensitive=1 AND status='active'").fetchone()[0] == 0)
ok("zero inferred singles active (only corroborated promotions)",
   conn.execute("SELECT count(*) FROM brain_memory_v2 WHERE explicitness='inferred' AND status='active' "
                "AND id NOT IN (SELECT memory_id FROM brain_memory_evidence GROUP BY memory_id "
                "HAVING COUNT(DISTINCT source_ref) >= 2)").fetchone()[0] == 0)

# sensitive plaintext never in the clear (encrypted rows + rejected metadata)
leak = False
for table, col in (("brain_memory_v2", "distilled_text"), ("brain_memory_evidence", "excerpt")):
    for (val,) in conn.execute(f"SELECT {col} FROM {table}").fetchall():
        if val and ("GOLD_SECRET_7719" in str(val) or "GOLD_TRASH_5560" in str(val)):
            leak = True
ok("sensitive markers appear in no plaintext column", not leak)
ok("active sensitive plaintext is vault-encrypted (payload rows exist)",
   conn.execute("SELECT count(*) FROM brain_secure_payloads").fetchone()[0] >= 3)

dist = conn.execute("SELECT status, count(*) FROM brain_memory_v2 GROUP BY status ORDER BY status").fetchall()
print("\nstatus distribution:", ", ".join(f"{s}={n}" for s, n in dist))
print(f"category coverage:   {', '.join(f'{c}={n}' for c, n in sorted(categories.items()))}")
print(f"\n{PASS} checks passed")

"""
Brain V2 API routes (queue #20, T09 backend) — /api/brain/v2/* contract:
remember (+idempotency), import job lifecycle + triage + commit, memories
CRUD/feedback/influence/purge, profile/recall/stats, migration driver, cleanup
preview→confirmed apply, and locked-vault → HTTP 423.

Plain-Python TestClient checks (no pytest):
    python tests/test_brain_v2_api.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="tobi_bapi_"), "agent.db")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from fastapi.testclient import TestClient  # noqa: E402
from api.dashboard import app  # noqa: E402
from core.database import init_database, get_connection  # noqa: E402
from core import vault, brain  # noqa: E402
from core import brain_import as imp  # noqa: E402
from core import brain_repository as repo  # noqa: E402
from core.brain_contracts import MemoryCandidate, MemoryType, Explicitness, MemoryStatus  # noqa: E402

init_database()
conn = get_connection()
client = TestClient(app)

PASS = 0


def ok(name: str, cond: bool, detail=""):
    global PASS
    if not cond:
        print(f"❌ {name} {detail}")
        sys.exit(1)
    PASS += 1
    print(f"✅ {name}")


# deterministic extractor stub (same MEM|… grammar as the T05 test)
def stub_extractor(chunk: str) -> list[dict]:
    out = []
    for line in chunk.splitlines():
        if line.startswith("MEM|"):
            _, mtype, conf, text = line.split("|", 3)
            out.append({"distilled_text": text, "memory_type": mtype, "confidence": float(conf),
                        "explicitness": "explicit", "durability": 1, "actionability": 1,
                        "specificity": 1, "source_strength": 1})
    return out


imp.extract_chunk = stub_extractor

# ── locked vault → 423 ───────────────────────────────────────────────────────
r = client.post("/api/brain/v2/import-jobs", json={"filename": "a.txt", "content": "hello world"})
ok("locked vault: import create → 423", r.status_code == 423, str(r.status_code))
r = client.post("/api/brain/v2/migration/runs")
ok("locked vault: migration create → 423", r.status_code == 423, str(r.status_code))
vault.setup(conn, "master-pass-123456", import_env=False)

# ── remember + idempotency ───────────────────────────────────────────────────
r = client.post("/api/brain/v2/remember", json={"content": "Owner starts work at 8am", "category": "habits"})
ok("remember returns legacy shape", r.status_code == 200 and r.json()["ok"] is True
   and r.json()["action"] == "active")
h = {"Idempotency-Key": "same-key-1"}
r1 = client.post("/api/brain/v2/remember", json={"content": "Owner naps at noon", "category": "habits"}, headers=h)
r2 = client.post("/api/brain/v2/remember", json={"content": "Owner naps at noon", "category": "habits"}, headers=h)
ok("idempotency key replays instead of double-writing",
   r1.json().get("replayed") is None and r2.json().get("replayed") is True
   and r1.json()["id"] == r2.json()["id"])
r = client.post("/api/brain/v2/remember", json={"content": ""})
ok("empty remember rejected by contract", r.status_code == 422)

# ── import lifecycle ─────────────────────────────────────────────────────────
DOC = "MEM|fact|0.9|Owner deploys previews from the staging branch\n\nMEM|fact|0.9|Owner reviews PRs before merging"
r = client.post("/api/brain/v2/import-jobs", json={"filename": "notes.md", "content": DOC})
ok("import created (dry_run)", r.status_code == 200 and r.json()["status"] == "dry_run")
job = r.json()["id"]
ok("unknown job → 404", client.get("/api/brain/v2/import-jobs/999").status_code == 404)
# #20 review P1: run drives a background worker and returns immediately; poll to completion.
r = client.post(f"/api/brain/v2/import-jobs/{job}/commands", json={"command": "run"})
ok("run command returns immediately (background worker)", r.status_code == 200)
import time as _t
_js = r.json()
for _ in range(200):
    _js = client.get(f"/api/brain/v2/import-jobs/{job}").json()
    if _js["status"] != "dry_run":
        break
    _t.sleep(0.05)
ok("run command completes dry-run (via worker)", _js["status"] == "ready", str(_js))
r = client.get(f"/api/brain/v2/import-jobs/{job}/candidates")
ok("candidates listed with proposals", r.status_code == 200 and len(r.json()) == 2
   and all(x["proposed_outcome"] == "active" for x in r.json()))
r = client.post(f"/api/brain/v2/import-jobs/{job}/candidates/approve", json={"outcome": "active"})
ok("bulk approve", r.json()["decided"] == 2)
r = client.post(f"/api/brain/v2/import-jobs/{job}/commands", json={"command": "commit"})
ok("commit applies approved", r.json()["applied"] == 2 and r.json()["status"] == "committed")
ok("bad command rejected by contract",
   client.post(f"/api/brain/v2/import-jobs/{job}/commands", json={"command": "explode"}).status_code == 422)

# ── memories ─────────────────────────────────────────────────────────────────
r = client.get("/api/brain/v2/memories", params={"status": "active"})
ok("memories list filters by status", r.status_code == 200 and len(r.json()) >= 2
   and all(x["status"] == "active" for x in r.json()))
mid = next(x["id"] for x in r.json() if "staging branch" in x["distilled_text"])
r = client.get(f"/api/brain/v2/memories/{mid}")
ok("memory detail", r.json()["memory_type"] == "fact" and r.json()["trust"] == "untrusted")
ok("unknown memory → 404", client.get("/api/brain/v2/memories/999999").status_code == 404)

r = client.post(f"/api/brain/v2/memories/{mid}/feedback", json={"verdict": "useful", "turn_ref": "t1"})
ok("feedback recorded + signal returned", r.json()["usefulness"] == 0.65)
ok("bad verdict rejected", client.post(f"/api/brain/v2/memories/{mid}/feedback",
                                       json={"verdict": "meh"}).status_code == 422)
r = client.get(f"/api/brain/v2/memories/{mid}/influence")
ok("influence trace endpoint", r.status_code == 200 and isinstance(r.json(), list))

pend = repo.save(MemoryCandidate(distilled_text="Owner might adopt a standing 1:1 cadence",
                                 memory_type=MemoryType.FACT, explicitness=Explicitness.INFERRED,
                                 confidence=0.9, durability=1, actionability=1, specificity=1,
                                 source_strength=1), status=MemoryStatus.PENDING, conn=conn)
r = client.post(f"/api/brain/v2/memories/{pend}/status", json={"status": "active"})
ok("owner review: pending → active", r.json()["status"] == "active")
# purge requires explicit backend confirmation (#20 review P1)
ok("purge without confirm is rejected",
   client.delete(f"/api/brain/v2/memories/{pend}/purge").status_code == 400)
r = client.delete(f"/api/brain/v2/memories/{pend}/purge?confirm=true")
ok("purge deletes permanently (confirmed)", r.json()["ok"] is True
   and client.get(f"/api/brain/v2/memories/{pend}").status_code == 404)

# ── profile / recall / stats ─────────────────────────────────────────────────
r = client.get("/api/brain/v2/profile")
ok("profile endpoint versioned", r.status_code == 200 and {"profile", "version", "token_budget"} <= set(r.json()))
r = client.post("/api/brain/v2/recall", json={"query": "how does the owner handle PRs before merging?"})
ok("recall returns ranked memories with chips",
   r.status_code == 200 and any("PRs" in x["text"] for x in r.json())
   and all("chip" in x for x in r.json()))
r = client.get("/api/brain/v2/stats")
ok("stats shape", {"by_status", "by_type", "conflicted", "sensitive", "aging_pending",
                   "vault_unlocked"} <= set(r.json()) and r.json()["vault_unlocked"] is True)

# ── migration driver ─────────────────────────────────────────────────────────
brain.add_memory("Owner's full name is Vu Le Binh", "identity", 0.9, "remember", status="active")
brain.add_memory("Owner prefers dark roast coffee in the morning", "preferences", 0.9, "remember", status="active")
r = client.post("/api/brain/v2/migration/runs")
ok("migration run created", r.status_code == 200 and r.json()["status"] == "preview")
run = r.json()["id"]
r = client.post(f"/api/brain/v2/migration/runs/{run}/commands", json={"command": "run"})
ok("migration preview completes", r.json()["status"] == "ready")
# 4 legacy rows: the 2 seeded here + the 2 created via the remember endpoint above
r = client.get(f"/api/brain/v2/migration/runs/{run}/items")
ok("migration items listed (remembers included)", len(r.json()) == 4, str(len(r.json())))
r = client.post(f"/api/brain/v2/migration/runs/{run}/items/approve", json={"group": "reclassify"})
ok("migration bulk approve by group", r.json()["decided"] == 4)
r = client.post(f"/api/brain/v2/migration/runs/{run}/commands", json={"command": "apply"})
ok("migration apply", r.json()["status"] == "applied" and r.json()["applied"] == 4)

# ── cleanup: preview → confirmed apply only ──────────────────────────────────
aged = repo.save(MemoryCandidate(distilled_text="Owner may switch task tracker later",
                                 memory_type=MemoryType.FACT, explicitness=Explicitness.INFERRED,
                                 confidence=0.6, durability=1, actionability=1), conn=conn)
conn.execute("UPDATE brain_memory_v2 SET created_at=datetime('now','-45 days') WHERE id=?", (aged,))
conn.commit()
r = client.post("/api/brain/v2/cleanup/preview")
props = r.json()["proposals"]
archive_prop = next((p for p in props if p["action"] == "archive" and p["memory_id"] == aged), None)
ok("cleanup preview proposes archiving aged pending", archive_prop is not None, str(props)[:200])
ok("preview alone mutates nothing",
   client.get(f"/api/brain/v2/memories/{aged}").json()["status"] == "pending")
r = client.post("/api/brain/v2/cleanup/apply", json={"actions": [archive_prop]})
ok("confirmed apply archives", r.json()["applied"] == 1
   and client.get(f"/api/brain/v2/memories/{aged}").json()["status"] == "archived")
ok("unknown cleanup action → 400",
   client.post("/api/brain/v2/cleanup/apply", json={"actions": [{"action": "nuke"}]}).status_code == 400)

print(f"\n{PASS} checks passed")

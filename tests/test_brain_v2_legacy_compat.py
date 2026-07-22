"""Acceptance coverage for the legacy Brain UI contract on Brain V2."""
from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="tobi_brain_compat_"), "agent.db")

from fastapi.testclient import TestClient  # noqa: E402
from core.database import get_connection, init_database  # noqa: E402
from core import brain, brain_repository as repo, brain_v2_compat as compat, owner_flags  # noqa: E402
from core.brain_contracts import (  # noqa: E402
    Explicitness, LinkType, MemoryCandidate, MemoryStatus, MemoryType,
)
from api.dashboard import app  # noqa: E402


init_database()
client = TestClient(app)
checks = 0


def ok(name: str, condition: bool, detail: str = "") -> None:
    global checks
    if not condition:
        raise AssertionError(f"{name}: {detail}")
    checks += 1
    print(f"PASS {name}")


# Seed the accepted legacy behavior before cutover.
legacy_active = brain.add_memory(
    "Owner prefers compact implementation reports", "preferences", 0.9, "remember", "active"
)
legacy_pending = brain.add_memory(
    "Owner may prefer a weekly planning ritual", "habits", 0.65, "auto", "pending"
)
legacy_superseded = brain.add_memory(
    "Owner used an older planning format", "work", 0.8, "remember", "superseded"
)

# Existing shadow data can disagree with legacy. The cutover preserves the
# owner-visible lifecycle once, then V2 becomes authoritative.
conn = get_connection()
shadow_id = repo.save(
    MemoryCandidate(
        distilled_text="Owner used an older planning format",
        memory_type=MemoryType.PROJECT_CONTEXT,
        explicitness=Explicitness.EXPLICIT,
        confidence=0.8,
        durability=1, actionability=1, specificity=1, source_strength=1,
    ),
    status=MemoryStatus.ACTIVE, compat_ref=legacy_superseded, conn=conn,
)
owner_flags.set_bool(owner_flags.BRAIN_V2_ENABLED, True)
owner_flags.set_bool(owner_flags.BRAIN_V2_SHADOW, False)

cutover = compat.ensure_ready()
ok("cutover completes", cutover["status"] == "complete", str(cutover))
ok("legacy active is preserved in V2", conn.execute(
    "SELECT status FROM brain_memory_v2 WHERE compat_ref=?", (legacy_active,)
).fetchone()[0] == "active")
ok("legacy pending is preserved in V2", conn.execute(
    "SELECT status FROM brain_memory_v2 WHERE compat_ref=?", (legacy_pending,)
).fetchone()[0] == "pending")
ok("shadow lifecycle drift is reconciled", conn.execute(
    "SELECT status FROM brain_memory_v2 WHERE id=?", (shadow_id,)
).fetchone()[0] == "superseded")

r = client.get("/api/brain/stats")
ok("legacy stats endpoint identifies V2 backend",
   r.status_code == 200 and r.json().get("backend") == "brain_v2", r.text)
r = client.get("/api/brain/memories")
ok("legacy list returns V2 ids", r.status_code == 200 and any(
    item["content"] == "Owner prefers compact implementation reports" and
    conn.execute("SELECT 1 FROM brain_memory_v2 WHERE id=?", (item["id"],)).fetchone()
    for item in r.json()["items"]
), r.text)

# Manual Add -> V2 source of truth plus rollback mirror.
r = client.post("/api/brain/memories", json={
    "content": "Owner likes concise release notes", "category": "preferences",
    "confidence": 0.92, "source": "manual",
})
manual = r.json()
ok("manual add uses V2", r.status_code == 200 and manual["source"] == "manual" and
   conn.execute("SELECT status FROM brain_memory_v2 WHERE id=?", (manual["id"],)).fetchone()[0] == "active",
   r.text)
compat_ref = conn.execute(
    "SELECT compat_ref FROM brain_memory_v2 WHERE id=?", (manual["id"],)
).fetchone()[0]
ok("manual add keeps rollback mirror", compat_ref is not None and conn.execute(
    "SELECT content FROM brain_memories WHERE id=?", (compat_ref,)
).fetchone()[0] == manual["content"])

r = client.patch(f"/api/brain/memories/{manual['id']}", json={
    "content": "Owner likes short, concrete release notes", "confidence": 0.95,
})
ok("edit updates V2", r.status_code == 200 and r.json()["confidence"] == 0.95 and
   "concrete" in r.json()["content"], r.text)
ok("edit synchronizes rollback mirror", "concrete" in conn.execute(
    "SELECT content FROM brain_memories WHERE id=?", (compat_ref,)
).fetchone()[0])
r = client.get(f"/api/brain/memories/{manual['id']}/versions")
ok("V2 history powers legacy modal", r.status_code == 200 and
   {row["change_kind"] for row in r.json()["versions"]} >= {"create", "edit"}, r.text)
r = client.post(f"/api/brain/memories/{manual['id']}/confirm")
ok("confirm remains available", r.status_code == 200 and r.json()["last_confirmed_at"], r.text)

# Review inbox lifecycle.
pending_id = compat.add_memory(
    "Owner may start a Monday review", "habits", 0.65, "auto", status="pending"
)
r = client.post(f"/api/brain/pending/{pending_id}/accept")
ok("pending accept activates V2", r.status_code == 200 and r.json()["status"] == "active", r.text)
reject_id = compat.add_memory(
    "Owner may use an unconfirmed temporary ritual", "habits", 0.55, "auto", status="pending"
)
r = client.post(f"/api/brain/pending/{reject_id}/reject")
ok("pending reject records V2 rejection", r.status_code == 200 and conn.execute(
    "SELECT status FROM brain_memory_v2 WHERE id=?", (reject_id,)
).fetchone()[0] == "rejected", r.text)

# V2 conflict links are translated into the existing Review UI contract.
existing_id = compat.add_memory("Owner prefers VS Code for editing", "preferences", 0.9)
candidate_id = compat.add_memory(
    "Owner prefers Neovim for editing", "preferences", 0.9, status="pending"
)
repo.link(candidate_id, existing_id, LinkType.CONFLICTS_WITH, conn=conn)
r = client.get("/api/brain/conflicts")
conflict = next(item for item in r.json()["items"] if item["memory_id"] == existing_id)
ok("V2 conflict appears in legacy Review UI shape", conflict["candidate_content"].startswith("Owner prefers Neovim"))
r = client.post(f"/api/brain/conflicts/{conflict['id']}/resolve", json={"decision": "use_candidate"})
ok("conflict resolution updates both V2 records", r.status_code == 200 and
   conn.execute("SELECT status FROM brain_memory_v2 WHERE id=?", (candidate_id,)).fetchone()[0] == "active" and
   conn.execute("SELECT status FROM brain_memory_v2 WHERE id=?", (existing_id,)).fetchone()[0] == "superseded",
   r.text)

# Cleaner, search, import, and automatic sweep all stay on V2.
dup_a = compat.add_memory("Owner reviews the Mission Control queue daily", "habits", 0.8)
dup_b = compat.add_memory("Owner reviews the Mission Control queue daily", "habits", 0.9)
r = client.get("/api/brain/duplicates")
group = next(group for group in r.json()["groups"] if {dup_a, dup_b} <= set(group["ids"]))
r = client.post("/api/brain/duplicates/merge", json={"ids": group["ids"], "keep_id": dup_b})
ok("duplicate cleaner supersedes V2 duplicate", r.status_code == 200 and r.json()["merged"] >= 1 and
   conn.execute("SELECT status FROM brain_memory_v2 WHERE id=?", (dup_a,)).fetchone()[0] == "superseded",
   r.text)
r = client.post("/api/brain/search", json={"query": "release notes", "k": 10})
ok("legacy search reads V2", r.status_code == 200 and any(
    item["id"] == manual["id"] for item in r.json()["items"]
), r.text)
r = client.post("/api/brain/import/commit", json={
    "filename": "owner.md", "source_type": "md", "items": [{
        "content": "Owner archives decisions after shipping", "category": "work", "confidence": 0.85,
    }],
})
ok("legacy import commits to V2", r.status_code == 200 and r.json()["saved"] == 1 and
   conn.execute("SELECT count(*) FROM brain_memory_v2 WHERE distilled_text LIKE '%archives decisions%'").fetchone()[0] == 1,
   r.text)
auto = brain.route_candidate(
    "Owner sometimes reviews incident notes on Fridays", "habits", 0.8, "auto"
)
ok("automatic sweep routing uses V2 quality gate", auto["action"] == "pending" and
   conn.execute("SELECT status FROM brain_memory_v2 WHERE id=?", (auto["memory_id"],)).fetchone()[0] == "pending",
   str(auto))

# Sensitive manual content fails closed while the vault is locked.
r = client.post("/api/brain/memories", json={
    "content": "Owner medical diagnosis is private", "category": "health", "confidence": 0.9,
})
ok("legacy Add maps locked sensitive V2 write to 423", r.status_code == 423, r.text)

# Sensitive V2 content and compatibility history must stay encrypted/redacted.
from core import vault  # noqa: E402
vault.setup(conn, "brain-compat-test-pass", import_env=False)
r = client.post("/api/brain/memories", json={
    "content": "Owner private medical code is HEALTH_SECRET_204", "category": "health",
    "confidence": 0.9,
})
sensitive_id = r.json()["id"]
ok("unlocked sensitive Add succeeds in V2", r.status_code == 200 and r.json()["redacted"] is False,
   r.text)
ok("sensitive plaintext absent from V2 compatibility history", conn.execute(
    "SELECT count(*) FROM brain_memory_v2_versions WHERE memory_id=? AND content LIKE '%HEALTH_SECRET_204%'",
    (sensitive_id,),
).fetchone()[0] == 0)

convert_id = compat.add_memory("Owner old private marker CONVERT_SECRET_306", "identity", 0.9)
convert_ref = conn.execute(
    "SELECT compat_ref FROM brain_memory_v2 WHERE id=?", (convert_id,)
).fetchone()[0]
compat.update_memory(convert_id, content="Owner medical diagnosis CONVERT_SECRET_306", category="health")
plain_live_history = conn.execute(
    "SELECT count(*) FROM brain_memory_v2_versions WHERE memory_id=? AND content LIKE '%CONVERT_SECRET_306%'",
    (convert_id,),
).fetchone()[0]
plain_rollback_history = conn.execute(
    "SELECT count(*) FROM brain_memory_versions WHERE memory_id=? AND content LIKE '%CONVERT_SECRET_306%'",
    (convert_ref,),
).fetchone()[0]
ok("sensitive conversion scrubs live and rollback history",
   plain_live_history == 0 and plain_rollback_history == 0,
   f"v2={plain_live_history} legacy={plain_rollback_history}")
vault.lock()

r = client.delete(f"/api/brain/memories/{manual['id']}")
ok("legacy delete archives V2", r.status_code == 200 and conn.execute(
    "SELECT status FROM brain_memory_v2 WHERE id=?", (manual["id"],)
).fetchone()[0] == "archived", r.text)

# Rollback remains real. A row written while off is reconciled when V2 returns.
owner_flags.set_bool(owner_flags.BRAIN_V2_ENABLED, False)
before = conn.execute("SELECT count(*) FROM brain_memory_v2").fetchone()[0]
r = client.post("/api/brain/memories", json={
    "content": "Owner temporarily tests legacy rollback", "category": "work", "confidence": 0.9,
})
ok("flag off restores legacy backend", r.status_code == 200 and
   conn.execute("SELECT count(*) FROM brain_memory_v2").fetchone()[0] == before, r.text)
owner_flags.set_bool(owner_flags.BRAIN_V2_ENABLED, True)
r = client.get("/api/brain/stats")
ok("re-enable reconciles rollback writes", r.status_code == 200 and conn.execute(
    "SELECT count(*) FROM brain_memory_v2 WHERE distilled_text='Owner temporarily tests legacy rollback'"
).fetchone()[0] == 1, r.text)

conn.close()
print(f"\n{checks} checks passed")

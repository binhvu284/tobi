"""Focused contract for the version shared by Developer and the MC sidebar."""
from __future__ import annotations

import tempfile
from pathlib import Path

from core.development_store import DevelopmentStore
from core.release_manager import ReleaseManager, current_developer_version


test_root = Path(__file__).resolve().parents[1] / ".tobi" / "test-runs"
test_root.mkdir(parents=True, exist_ok=True)
root = Path(tempfile.mkdtemp(prefix="release_version_", dir=test_root))
store = DevelopmentStore(root / "version.db")
conn = store.connect()
assert current_developer_version(conn) == "3.0"
conn.close()

releases = ReleaseManager(store)
releases.reserve("3.1.0", 31, risk="medium")
conn = store.connect()
assert current_developer_version(conn) == "3.1.0"
conn.close()

task = store.upsert_task({
    "queue_id": 32,
    "title": "Active version",
    "plan_path": "docs/active-version.md",
    "plan_hash": "a" * 64,
    "acceptance_criteria": [],
    "dependencies": [],
    "status": "planned",
    "risk": "low",
    "target_version": "3.2.0",
})
session = store.create_session(int(task["id"]), "policy-hash", "active-version")
conn = store.connect()
assert current_developer_version(conn) == "3.2.0"
conn.close()

store.update_session(int(session["id"]), state="canceled")
releases.set_status("3.1.0", "failed")
conn = store.connect()
assert current_developer_version(conn) == "3.0"
conn.close()

print("4 shared release-version checks passed")

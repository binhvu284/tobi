"""Acceptance checks for #21 T10 Run 3 canonical coding history."""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TMP = tempfile.mkdtemp(prefix="tobi_t10_run3_")
os.environ["DB_PATH"] = os.path.join(TMP, "agent.db")

from core.database import get_connection, init_database  # noqa: E402
from core.runtime.coding_adapter import CodingRuntimeAdapter  # noqa: E402
from core.runtime.event_store import list_run_events  # noqa: E402


PASS = 0


def ok(name: str, condition: bool, detail: str = "") -> None:
    global PASS
    if not condition:
        print(f"FAIL {name}: {detail}")
        raise SystemExit(1)
    PASS += 1
    print(f"PASS {name}")


def rows(sql: str, parameters: tuple = ()) -> list[sqlite3.Row]:
    conn = get_connection()
    try:
        return conn.execute(sql, parameters).fetchall()
    finally:
        conn.close()


init_database()
adapter = CodingRuntimeAdapter()
session = {
    "id": 42,
    "queue_id": 22,
    "goal_id": 7,
    "title": "Autonomous coding system",
    "state": "approved",
    "stage": "approved",
    "worker_profile_slug": "mc-native",
}
approved = {
    "sequence": 1,
    "event_type": "workflow_approved",
    "actor": "owner",
    "created_at": "2026-08-14T00:00:00Z",
    "payload": {
        "queue_id": 22,
        "target_version": "0.8.0",
        "plan_path": "private/plan.md",
        "raw_worker_output": "api_key=sk-never-store-this",
    },
}

first = adapter.mirror(session, approved)
ok("accepted coding session creates a canonical run", first.ok and bool(first.run_id))
ok("one coding session maps to one canonical run", len(rows("SELECT run_id FROM mc_runs")) == 1)
run_id = first.run_id or ""
events_before = list_run_events(run_id)
replay = adapter.mirror(session, approved)
events_after = list_run_events(run_id)
ok("duplicate event replay is idempotent", replay.ok and len(events_after) == len(events_before))
ok(
    "developer history remains linked and readable",
    rows("SELECT legacy_run_id FROM mc_runs WHERE run_id=?", (run_id,))[0][0]
    == "coding-session:42",
)

checkpoint = {
    "sequence": 2,
    "event_type": "checkpoint_created",
    "actor": "tobi",
    "created_at": "2026-08-14T00:01:00Z",
    "payload": {
        "stage": "code",
        "checkpoint_id": 91,
        "artifact_id": 15,
        "snapshot": {"full_diff": "secret source body"},
        "worker_output": "token=do-not-store",
    },
}
second = adapter.mirror({**session, "state": "running", "stage": "code"}, checkpoint)
mirrored = [event for event in list_run_events(run_id) if event.event_type.startswith("developer.")]
ok("checkpoint event is appended in source order", second.ok and [e.redacted_payload["developer_sequence"] for e in mirrored] == [1, 2])
checkpoint_payload = mirrored[-1].redacted_payload
ok(
    "checkpoint and evidence history stores references only",
    checkpoint_payload.get("checkpoint_id") == 91
    and checkpoint_payload.get("artifact_id") == 15
    and "snapshot" not in checkpoint_payload
    and "worker_output" not in checkpoint_payload,
    json.dumps(checkpoint_payload, sort_keys=True),
)
persisted = json.dumps([event.redacted_payload for event in list_run_events(run_id)], sort_keys=True)
ok("raw prompts credentials and worker output are not mirrored", "sk-never" not in persisted and "secret source" not in persisted)

changed = {**checkpoint, "payload": {**checkpoint["payload"], "stage": "review"}}
conflict = adapter.mirror({**session, "state": "running", "stage": "review"}, changed)
ok(
    "changed content under one source identity fails closed",
    not conflict.ok and conflict.recovery_action == "keep_developer_history",
)

adapter_source = (ROOT / "core" / "runtime" / "coding_adapter.py").read_text(encoding="utf-8")
agent_source = (ROOT / "core" / "coding_agent.py").read_text(encoding="utf-8")
ok("adapter does not import coding workers", "coding_workers" not in adapter_source)
ok("Mission Control event funnel owns the bridge", "runtime_coding.mirror" in agent_source)

print(f"PASS: {PASS} T10 Run 3 coding adapter checks")

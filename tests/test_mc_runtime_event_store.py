"""Acceptance checks for #21 T02 ordered events and rebuildable projections."""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TMP = tempfile.mkdtemp(prefix="tobi_t02_")
os.environ["DB_PATH"] = os.path.join(TMP, "agent.db")

from core.database import get_connection, init_database  # noqa: E402
from core.runtime.contracts import SystemEdge, SystemEntity, SystemEntityType  # noqa: E402
from core.runtime.event_store import (  # noqa: E402
    EventConflictError,
    append_run_event,
    append_system_edge,
    append_system_entity,
    list_run_events,
    remove_system_edge,
    remove_system_entity,
)
from core.runtime.projections import (  # noqa: E402
    get_run_projection,
    rebuild_all_projections,
    rebuild_run_projection,
    rebuild_system_projection,
)
from core.runtime.rebuild import main as rebuild_main  # noqa: E402


PASS = 0


def ok(name: str, condition: bool, detail: str = "") -> None:
    global PASS
    if not condition:
        print(f"FAIL {name}: {detail}")
        raise SystemExit(1)
    PASS += 1
    print(f"PASS {name}")


def raises(error_type: type[Exception], callback) -> bool:
    try:
        callback()
    except error_type:
        return True
    return False


def rows(sql: str, parameters: tuple = ()) -> list[sqlite3.Row]:
    conn = get_connection()
    try:
        return conn.execute(sql, parameters).fetchall()
    finally:
        conn.close()


# A pre-existing table proves the additive migration leaves legacy owner data alone.
legacy = get_connection()
legacy.execute("CREATE TABLE legacy_owner_data (value TEXT NOT NULL)")
legacy.execute("INSERT INTO legacy_owner_data (value) VALUES ('keep-me')")
legacy.commit()
legacy.close()

init_database()
init_database()

expected_tables = {
    "mc_run_events",
    "mc_change_events",
    "mc_runtime_projections",
    "mc_system_entities",
    "mc_system_edges",
}
created_tables = {
    row[0]
    for row in rows(
        "SELECT name FROM sqlite_master WHERE type='table' AND name GLOB 'mc_*'"
    )
}
migrations = rows(
    "SELECT version FROM schema_migrations WHERE version='mc-runtime-v2-001'"
)
triggers = {
    row[0]
    for row in rows(
        "SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE 'mc_%_immutable'"
    )
}
ok("additive schema and one ledger record", expected_tables.issubset(created_tables) and len(migrations) == 1)
ok("event tables have update and delete guards", len(triggers) == 4, str(triggers))
ok("legacy row survives migration", rows("SELECT value FROM legacy_owner_data")[0][0] == "keep-me")

first = append_run_event(
    run_id="run-a",
    event_type="run.accepted",
    stage="accept",
    actor="owner",
    payload={"objective": "Rebuild me", "status": "accepted", "surface": "chat"},
    event_id="evt-a-1",
    timestamp="2026-08-01T00:00:00Z",
)
second = append_run_event(
    run_id="run-a",
    event_type="run.routed",
    stage="route",
    actor="runtime",
    payload={"status": "running", "mode": "chat", "current_step": "route"},
    event_id="evt-a-2",
    timestamp="2026-08-01T00:00:01Z",
)
other = append_run_event(
    run_id="run-b",
    event_type="run.accepted",
    stage="accept",
    actor="owner",
    payload={},
    event_id="evt-b-1",
    timestamp="2026-08-01T00:00:02Z",
)
ok("events are ordered per run", [event.sequence for event in list_run_events("run-a")] == [1, 2])
ok("cursor reads only later events", [event.event_id for event in list_run_events("run-a", after_sequence=1)] == ["evt-a-2"])
ok("each run starts at sequence one", first.sequence == 1 and second.sequence == 2 and other.sequence == 1)

replayed = append_run_event(
    run_id="run-a",
    event_type="run.accepted",
    stage="accept",
    actor="owner",
    payload={"objective": "Rebuild me", "status": "accepted", "surface": "chat"},
    event_id="evt-a-1",
)
ok("same event id and content replays safely", replayed == first and len(list_run_events("run-a")) == 2)
ok(
    "same event id with changed content conflicts",
    raises(
        EventConflictError,
        lambda: append_run_event(
            run_id="run-a",
            event_type="run.accepted",
            stage="accept",
            actor="owner",
            payload={"objective": "changed"},
            event_id="evt-a-1",
            timestamp="2026-08-01T00:00:00Z",
        ),
    ),
)


def concurrent_append(index: int) -> int:
    return append_run_event(
        run_id="run-concurrent",
        event_type="step.recorded",
        stage="execute",
        actor="worker",
        payload={"current_step": str(index)},
        event_id=f"evt-concurrent-{index}",
        timestamp=f"2026-08-01T00:01:{index:02d}Z",
    ).sequence


with ThreadPoolExecutor(max_workers=10) as pool:
    concurrent_sequences = list(pool.map(concurrent_append, range(10)))
ok("concurrent writers receive one contiguous range", sorted(concurrent_sequences) == list(range(1, 11)))

sentinel = "t02-secret-sentinel"
secret_event = append_run_event(
    run_id="run-secret",
    event_type="tool.recorded",
    stage="execute",
    actor="runtime",
    payload={
        "nested": {"api_key": sentinel},
        "message": f"Authorization: Bearer {sentinel}",
        "safe": "visible",
    },
    event_id="evt-secret",
    timestamp="2026-08-01T00:02:00Z",
)
raw_secret = rows("SELECT payload_json FROM mc_run_events WHERE event_id='evt-secret'")[0][0]
ok("nested and embedded secrets are redacted before storage", sentinel not in raw_secret and secret_event.redacted_payload["safe"] == "visible")

append_run_event(
    run_id="run-large",
    event_type="tool.recorded",
    stage="execute",
    actor="runtime",
    payload={"blob": "x" * 25_000},
    event_id="evt-large",
    timestamp="2026-08-01T00:02:01Z",
)
large_json = rows("SELECT payload_json FROM mc_run_events WHERE event_id='evt-large'")[0][0]
large_payload = json.loads(large_json)
ok("large payload remains valid bounded JSON", len(large_json.encode("utf-8")) < 17_000 and large_payload["_truncated"] is True)

guard_entity = SystemEntity(
    entity_id="entity-guard",
    entity_type=SystemEntityType.COMPONENT,
    canonical_key="runtime.guard",
    name="Runtime guard",
    status="active",
    version="1",
    owner_domain="runtime",
    source_ref="tests",
    observed_at="2026-08-01T00:02:02Z",
)
append_system_entity(guard_entity, actor="runtime", event_id="change-guard")
guard_conn = get_connection()
try:
    update_blocked = raises(
        sqlite3.DatabaseError,
        lambda: guard_conn.execute("UPDATE mc_run_events SET actor='changed' WHERE event_id='evt-a-1'"),
    )
    delete_blocked = raises(
        sqlite3.DatabaseError,
        lambda: guard_conn.execute("DELETE FROM mc_change_events"),
    )
finally:
    guard_conn.rollback()
    guard_conn.close()
ok("raw SQL cannot update or delete event rows", update_blocked and delete_blocked)

append_run_event(
    run_id="run-a",
    event_type="provider.unknown_shape",
    stage="execute",
    actor="provider",
    payload={"unexpected": {"still": "usable"}},
    event_id="evt-a-3",
    timestamp="2026-08-01T00:00:03Z",
)
append_run_event(
    run_id="run-a",
    event_type="run.completed",
    stage="respond",
    actor="runtime",
    payload={"status": "completed", "owner_attention": False},
    event_id="evt-a-4",
    timestamp="2026-08-01T00:00:04Z",
)
projection_one = rebuild_run_projection("run-a")
projection_two = rebuild_run_projection("run-a")
ok("run rebuild is deterministic", projection_one == projection_two and projection_one["state_hash"])
ok("unknown event is retained without corrupting state", projection_one["state"]["last_sequence"] == 4 and projection_one["state"]["objective"] == "Rebuild me")

conn = get_connection()
conn.execute("DELETE FROM mc_runtime_projections WHERE projection_type='run' AND projection_key='run-a'")
conn.commit()
conn.close()
restored_run = rebuild_run_projection("run-a")
ok("deleted run projection rebuilds identically", restored_run == projection_one and get_run_projection("run-a") == projection_one)

entity = SystemEntity(
    entity_id="entity-runtime",
    entity_type=SystemEntityType.SUBSYSTEM,
    canonical_key="runtime.v2",
    name="Runtime V2",
    status="shadow",
    version="1",
    owner_domain="runtime",
    source_ref="core/runtime",
    observed_at="2026-08-01T00:03:00Z",
    metadata={"package": "T02"},
)
edge = SystemEdge(
    edge_id="edge-runtime-chat",
    from_entity_id="entity-runtime",
    edge_type="observes",
    to_entity_id="entity-chat",
    version="1",
    evidence_refs=("tests/test_mc_runtime_event_store.py",),
)
append_system_entity(entity, actor="runtime", event_id="change-1")
append_system_edge(edge, actor="runtime", event_id="change-2")
remove_system_edge(edge.edge_id, actor="runtime", event_id="change-3")
append_system_edge(edge, actor="runtime", event_id="change-4")
remove_system_entity(entity.entity_id, actor="runtime", event_id="change-5")
append_system_entity(entity, actor="runtime", event_id="change-6")
system_one = rebuild_system_projection()
system_two = rebuild_system_projection()
ok("system rebuild is deterministic", system_one == system_two and system_one["state_hash"])
ok(
    "system entity and edge current rows rebuild",
    rows("SELECT status FROM mc_system_entities WHERE entity_id='entity-runtime'")[0][0] == "shadow"
    and rows("SELECT edge_type FROM mc_system_edges WHERE edge_id='edge-runtime-chat'")[0][0] == "observes",
)

conn = get_connection()
conn.execute("DELETE FROM mc_system_edges")
conn.execute("DELETE FROM mc_system_entities")
conn.execute("DELETE FROM mc_runtime_projections WHERE projection_type='system'")
conn.commit()
conn.close()
system_restored = rebuild_system_projection()
ok("deleted system projection rebuilds identically", system_restored == system_one)

all_once = rebuild_all_projections(verify=True)
all_twice = rebuild_all_projections(verify=True)
ok("all projection verification is stable", all_once == all_twice and all_once["verified"] is True)
ok("local rebuild CLI verify mode succeeds", rebuild_main(["--all", "--verify"]) == 0)
ok("legacy data remains after rebuilds", rows("SELECT value FROM legacy_owner_data")[0][0] == "keep-me")

print(f"\n{PASS}/{PASS} T02 runtime event-store tests pass")

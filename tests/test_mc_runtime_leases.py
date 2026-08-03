"""Acceptance checks for #21 T03 Run 2 leases and durable checkpoints."""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TMP = tempfile.mkdtemp(prefix="tobi_t03_run2_")
os.environ["DB_PATH"] = os.path.join(TMP, "agent.db")

from core.database import get_connection, init_database  # noqa: E402
from core.runtime.contracts import (  # noqa: E402
    ExecutionPlan,
    LoopPolicy,
    LoopRecipe,
    LoopType,
    PlanStep,
    RiskLevel,
    RunRequest,
    Surface,
)
from core.runtime.event_store import EventConflictError, append_run_event, list_run_events  # noqa: E402
from core.runtime.repository import (  # noqa: E402
    CheckpointConflictError,
    LeaseConflictError,
    RuntimeRepository,
)
from core.runtime.state import RunStatus  # noqa: E402


PASS = 0
BASE = datetime(2026, 8, 3, 1, 0, tzinfo=timezone.utc)
SECRET = "sk-t03-run2-do-not-store"


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


def query(sql: str, parameters: tuple = ()) -> list[sqlite3.Row]:
    conn = get_connection()
    try:
        return conn.execute(sql, parameters).fetchall()
    finally:
        conn.close()


def recipe() -> LoopRecipe:
    return LoopRecipe(
        recipe_id="goal.default",
        version="1",
        name="Bounded goal",
        loop_type=LoopType.GOAL,
        trigger="owner request",
        objective="Finish one bounded goal",
        stop_condition="acceptance checks pass",
        max_attempts=3,
        max_runtime_s=900,
        max_cost_usd=2.0,
    )


def policy() -> LoopPolicy:
    return LoopPolicy.from_recipe(
        policy_id="policy-goal-default",
        version="1",
        recipe=recipe(),
        policy_decision_id="decision-t03-run2",
        enabled=True,
    )


def request(request_id: str) -> RunRequest:
    return RunRequest(
        request_id=request_id,
        surface=Surface.DEVELOPER,
        owner_id="owner",
        session_id="session-t03-run2",
        mode="agent",
        message="Prove durable restart",
    )


def prepare_running_run(repository: RuntimeRepository, run_id: str, request_id: str) -> None:
    repository.create_run(request(request_id), loop_policy=policy(), run_id=run_id)
    repository.transition_run(
        run_id, RunStatus.ROUTING, expected_version=1, actor="runtime"
    )
    repository.save_plan(
        ExecutionPlan(
            plan_id=f"plan-{run_id}",
            run_id=run_id,
            version="1",
            objective="Prove durable restart",
            steps=(
                PlanStep(
                    step_id="first",
                    kind="tool",
                    risk=RiskLevel.NONE,
                    tool_name="files.read",
                ),
                PlanStep(
                    step_id="second",
                    kind="evaluate",
                    risk=RiskLevel.NONE,
                    depends_on=("first",),
                ),
            ),
        ),
        expected_version=2,
        actor="runtime",
    )
    repository.transition_run(
        run_id, RunStatus.RUNNING, expected_version=3, actor="runtime"
    )


legacy = get_connection()
legacy.execute("CREATE TABLE legacy_owner_data (value TEXT NOT NULL)")
legacy.execute("INSERT INTO legacy_owner_data (value) VALUES ('keep-me')")
legacy.execute(
    "CREATE TABLE schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT)"
)
legacy.executemany(
    "INSERT INTO schema_migrations (version,applied_at) VALUES (?,?)",
    (
        ("mc-runtime-v2-001", "2026-08-01T00:00:00Z"),
        ("mc-runtime-v2-002", "2026-08-03T00:00:00Z"),
    ),
)
legacy.execute(
    """CREATE TABLE mc_run_steps (
        run_id TEXT NOT NULL,
        step_id TEXT NOT NULL,
        plan_version TEXT NOT NULL,
        position INTEGER NOT NULL CHECK (position >= 0),
        kind TEXT NOT NULL,
        tool_name TEXT,
        arguments_json TEXT NOT NULL DEFAULT '{}',
        depends_on_json TEXT NOT NULL DEFAULT '[]',
        risk TEXT NOT NULL,
        timeout_s INTEGER NOT NULL DEFAULT 0 CHECK (timeout_s >= 0),
        retry_policy TEXT NOT NULL,
        idempotency_key TEXT,
        required_capabilities_json TEXT NOT NULL DEFAULT '[]',
        output_contract_json TEXT NOT NULL DEFAULT '{}',
        status TEXT NOT NULL DEFAULT 'pending',
        attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        started_at TEXT,
        completed_at TEXT,
        PRIMARY KEY (run_id, step_id),
        UNIQUE (run_id, position)
    )"""
)
legacy.commit()
legacy.close()

init_database()
init_database()
repository = RuntimeRepository()
repository.save_loop_recipe(recipe())

columns = {row[1] for row in query("PRAGMA table_info(mc_run_steps)")}
ok(
    "migration 003 adds lease columns and checkpoint table",
    {"lease_owner", "lease_token_hash", "lease_expires_at", "lease_epoch"}.issubset(columns)
    and bool(
        query(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='mc_run_checkpoints'"
        )
    ),
)
ok(
    "migration 003 is idempotent and preserves legacy data",
    len(query("SELECT version FROM schema_migrations WHERE version='mc-runtime-v2-003'")) == 1
    and query("SELECT value FROM legacy_owner_data")[0][0] == "keep-me",
)

prepare_running_run(repository, "run-lease", "request-lease")


def compete(worker_id: str):
    return repository.claim_step(
        "run-lease", worker_id=worker_id, lease_seconds=60, now=BASE
    )


with ThreadPoolExecutor(max_workers=2) as pool:
    claims = list(pool.map(compete, ("worker-a", "worker-b")))
winners = [claim for claim in claims if claim is not None]
winner = winners[0]
loser = "worker-b" if winner["worker_id"] == "worker-a" else "worker-a"
ok("exactly one concurrent worker wins the step", len(winners) == 1)
ok(
    "claim returns a bounded lease and no checkpoint initially",
    winner["step"]["step_id"] == "first"
    and winner["lease_epoch"] == 1
    and winner["lease_token"]
    and winner["checkpoint"] is None
    and winner["reclaimed"] is False,
)
ok(
    "a live foreign lease blocks overlap and dependencies stay blocked",
    repository.claim_step(
        "run-lease", worker_id=loser, lease_seconds=60, now=BASE + timedelta(seconds=1)
    )
    is None,
)

token = winner["lease_token"]
owner = winner["worker_id"]
ok(
    "wrong token cannot renew the lease",
    raises(
        LeaseConflictError,
        lambda: repository.renew_step_lease(
            "run-lease",
            "first",
            worker_id=owner,
            lease_token="wrong-token",
            lease_epoch=1,
            lease_seconds=120,
            now=BASE + timedelta(seconds=2),
        ),
    ),
)
renewed = repository.renew_step_lease(
    "run-lease",
    "first",
    worker_id=owner,
    lease_token=token,
    lease_epoch=1,
    lease_seconds=120,
    now=BASE + timedelta(seconds=2),
)
ok("current owner renews an unexpired lease", renewed["lease_epoch"] == 1)

checkpoint = repository.save_checkpoint(
    "checkpoint-1",
    "run-lease",
    "first",
    worker_id=owner,
    lease_token=token,
    lease_epoch=1,
    state={
        "cursor": 7,
        "next_action": "Continue first step",
        "access_token": SECRET,
    },
    event_id="event-checkpoint-1",
    now=BASE + timedelta(seconds=3),
)
replayed = repository.save_checkpoint(
    "checkpoint-1",
    "run-lease",
    "first",
    worker_id=owner,
    lease_token=token,
    lease_epoch=1,
    state={
        "cursor": 7,
        "next_action": "Continue first step",
        "access_token": SECRET,
    },
    event_id="event-checkpoint-1",
    now=BASE + timedelta(seconds=3),
)
ok(
    "checkpoint is redacted, ordered, and safely replayed",
    checkpoint == replayed
    and checkpoint["sequence"] == 1
    and checkpoint["state"]["access_token"] == "[REDACTED]",
)
ok(
    "changed content cannot reuse a checkpoint id",
    raises(
        CheckpointConflictError,
        lambda: repository.save_checkpoint(
            "checkpoint-1",
            "run-lease",
            "first",
            worker_id=owner,
            lease_token=token,
            lease_epoch=1,
            state={"cursor": 8},
            now=BASE + timedelta(seconds=4),
        ),
    ),
)

guard = get_connection()
try:
    update_blocked = raises(
        sqlite3.DatabaseError,
        lambda: guard.execute(
            "UPDATE mc_run_checkpoints SET state_json='{}' WHERE checkpoint_id='checkpoint-1'"
        ),
    )
    guard.rollback()
    delete_blocked = raises(
        sqlite3.DatabaseError,
        lambda: guard.execute(
            "DELETE FROM mc_run_checkpoints WHERE checkpoint_id='checkpoint-1'"
        ),
    )
finally:
    guard.rollback()
    guard.close()
ok("checkpoint rows are append-only at database level", update_blocked and delete_blocked)
durable_dump = "\n".join(
    str(value)
    for table in ("mc_run_steps", "mc_run_checkpoints", "mc_run_events")
    for row in query(f"SELECT * FROM {table}")
    for value in row
)
ok(
    "raw lease token and checkpoint secrets never reach durable tables",
    SECRET not in durable_dump and token not in durable_dump,
)

append_run_event(
    run_id="unrelated",
    event_type="run.accepted",
    stage="accept",
    actor="owner",
    payload={},
    event_id="checkpoint-event-conflict",
)
ok(
    "event conflict rolls back checkpoint insertion",
    raises(
        EventConflictError,
        lambda: repository.save_checkpoint(
            "checkpoint-rollback",
            "run-lease",
            "first",
            worker_id=owner,
            lease_token=token,
            lease_epoch=1,
            state={"cursor": 9},
            event_id="checkpoint-event-conflict",
            now=BASE + timedelta(seconds=5),
        ),
    )
    and not query(
        "SELECT 1 FROM mc_run_checkpoints WHERE checkpoint_id='checkpoint-rollback'"
    ),
)

restarted = RuntimeRepository()
reclaim_time = BASE + timedelta(seconds=123)
reclaimed = restarted.claim_step(
    "run-lease", worker_id="worker-restarted", lease_seconds=60, now=reclaim_time
)
ok(
    "expired lease is reclaimed with the latest checkpoint",
    reclaimed is not None
    and reclaimed["step"]["step_id"] == "first"
    and reclaimed["lease_epoch"] == 2
    and reclaimed["lease_token"] != token
    and reclaimed["reclaimed"] is True
    and reclaimed["checkpoint"]["state"]["cursor"] == 7,
)
ok(
    "stale worker cannot checkpoint after reclaim",
    raises(
        LeaseConflictError,
        lambda: repository.save_checkpoint(
            "checkpoint-stale",
            "run-lease",
            "first",
            worker_id=owner,
            lease_token=token,
            lease_epoch=1,
            state={"cursor": 10},
            now=reclaim_time + timedelta(seconds=1),
        ),
    ),
)
ok(
    "stale worker cannot renew or release its former lease",
    raises(
        LeaseConflictError,
        lambda: repository.renew_step_lease(
            "run-lease",
            "first",
            worker_id=owner,
            lease_token=token,
            lease_epoch=1,
            now=reclaim_time + timedelta(seconds=1),
        ),
    )
    and raises(
        LeaseConflictError,
        lambda: repository.release_step_lease(
            "run-lease",
            "first",
            worker_id=owner,
            lease_token=token,
            lease_epoch=1,
            now=reclaim_time + timedelta(seconds=1),
        ),
    ),
)

released = restarted.release_step_lease(
    "run-lease",
    "first",
    worker_id="worker-restarted",
    lease_token=reclaimed["lease_token"],
    lease_epoch=2,
    now=reclaim_time + timedelta(seconds=2),
)
ok(
    "current owner releases the step back to pending",
    released["status"] == "pending" and released["lease_owner"] is None,
)

prepare_running_run(repository, "run-atomic", "request-atomic")
append_run_event(
    run_id="unrelated",
    event_type="run.accepted",
    stage="accept",
    actor="owner",
    payload={},
    event_id="claim-event-conflict",
)
ok(
    "event conflict rolls back the lease claim",
    raises(
        EventConflictError,
        lambda: repository.claim_step(
            "run-atomic",
            worker_id="worker-atomic",
            now=BASE,
            event_id="claim-event-conflict",
        ),
    )
    and repository.list_steps("run-atomic")[0]["lease_owner"] is None,
)

events = [event.event_type for event in list_run_events("run-lease")]
ok(
    "lease and checkpoint changes join ordered run history",
    "step.claimed" in events
    and "step.checkpointed" in events
    and "step.reclaimed" in events
    and "step.lease_released" in events,
)
ok("legacy data remains after lease work", query("SELECT value FROM legacy_owner_data")[0][0] == "keep-me")

print(f"\n{PASS}/{PASS} T03 Run 2 lease/checkpoint tests pass")

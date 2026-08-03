"""Acceptance checks for #21 T03 Run 3A runtime failure control."""
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

TMP = tempfile.mkdtemp(prefix="tobi_t03_run3a_")
os.environ["DB_PATH"] = os.path.join(TMP, "agent.db")

from core.database import get_connection, init_database  # noqa: E402
from core.runtime.contracts import (  # noqa: E402
    ErrorCategory,
    ErrorStage,
    ExecutionPlan,
    LoopPolicy,
    LoopRecipe,
    LoopType,
    PlanStep,
    RecoveryAction,
    RiskLevel,
    RunRequest,
    RuntimeErrorInfo,
    RuntimeToolResult,
    Surface,
)
from core.runtime.control import CommandConflictError, RuntimeControl  # noqa: E402
from core.runtime.event_store import EventConflictError, append_run_event, list_run_events  # noqa: E402
from core.runtime.repository import (  # noqa: E402
    LeaseConflictError,
    RuntimeRepository,
    VersionConflictError,
)
from core.runtime.state import RunStatus  # noqa: E402
from core.schema.runtime import _ensure_runtime_schema  # noqa: E402


PASS = 0
BASE = datetime(2026, 8, 3, 3, 0, tzinfo=timezone.utc)
SECRET = "sk-t03-run3a-do-not-store"


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
        recipe_id="goal.control",
        version="1",
        name="Failure control",
        loop_type=LoopType.GOAL,
        trigger="owner request",
        objective="Control one bounded run",
        stop_condition="acceptance checks pass",
        max_attempts=3,
        max_runtime_s=900,
        max_cost_usd=2.0,
    )


def policy() -> LoopPolicy:
    return LoopPolicy.from_recipe(
        policy_id="policy-control",
        version="1",
        recipe=recipe(),
        policy_decision_id="decision-t03-run3a",
        enabled=True,
    )


def request(request_id: str) -> RunRequest:
    return RunRequest(
        request_id=request_id,
        surface=Surface.DEVELOPER,
        owner_id="owner",
        session_id="session-t03-run3a",
        mode="agent",
        message="Prove bounded failure control",
    )


def prepare_running_run(
    repository: RuntimeRepository,
    run_id: str,
    request_id: str,
    *,
    retry_policy: str = "none",
    with_dependency: bool = False,
) -> None:
    repository.save_loop_recipe(recipe())
    repository.create_run(request(request_id), loop_policy=policy(), run_id=run_id)
    repository.transition_run(
        run_id, RunStatus.ROUTING, expected_version=1, actor="runtime"
    )
    steps = [
        PlanStep(
            step_id="first",
            kind="tool",
            risk=RiskLevel.NONE,
            tool_name="files.read",
            retry_policy=retry_policy,
        )
    ]
    if with_dependency:
        steps.append(
            PlanStep(
                step_id="second",
                kind="evaluate",
                risk=RiskLevel.NONE,
                depends_on=("first",),
            )
        )
    repository.save_plan(
        ExecutionPlan(
            plan_id=f"plan-{run_id}",
            run_id=run_id,
            version="1",
            objective="Prove bounded failure control",
            steps=tuple(steps),
        ),
        expected_version=2,
        actor="runtime",
    )
    repository.transition_run(
        run_id, RunStatus.RUNNING, expected_version=3, actor="runtime"
    )


upgrade = sqlite3.connect(os.path.join(TMP, "runtime-v2-003.db"))
upgrade.row_factory = sqlite3.Row
upgrade.execute(
    """CREATE TABLE schema_migrations (
        version TEXT PRIMARY KEY,
        applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )"""
)
upgrade.executemany(
    "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
    [
        ("mc-runtime-v2-001", "2026-08-01T00:00:00Z"),
        ("mc-runtime-v2-002", "2026-08-02T00:00:00Z"),
        ("mc-runtime-v2-003", "2026-08-03T00:00:00Z"),
    ],
)
upgrade.execute(
    """CREATE TABLE mc_runs (
        run_id TEXT PRIMARY KEY,
        request_id TEXT NOT NULL UNIQUE,
        request_hash TEXT NOT NULL,
        request_json TEXT NOT NULL,
        owner_id TEXT NOT NULL,
        session_id TEXT NOT NULL,
        surface TEXT NOT NULL,
        mode TEXT NOT NULL,
        objective TEXT NOT NULL,
        status TEXT NOT NULL,
        version INTEGER NOT NULL DEFAULT 1,
        plan_id TEXT,
        plan_version TEXT,
        plan_hash TEXT,
        budget_profile TEXT NOT NULL,
        budget_json TEXT NOT NULL DEFAULT '{}',
        contract_version TEXT NOT NULL DEFAULT '1',
        legacy_run_id TEXT,
        legacy_action_id TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        completed_at TEXT
    )"""
)
upgrade.execute(
    """CREATE TABLE mc_run_steps (
        run_id TEXT NOT NULL,
        step_id TEXT NOT NULL,
        plan_version TEXT NOT NULL,
        position INTEGER NOT NULL,
        kind TEXT NOT NULL,
        tool_name TEXT,
        arguments_json TEXT NOT NULL DEFAULT '{}',
        depends_on_json TEXT NOT NULL DEFAULT '[]',
        risk TEXT NOT NULL,
        timeout_s INTEGER NOT NULL DEFAULT 0,
        retry_policy TEXT NOT NULL,
        idempotency_key TEXT,
        required_capabilities_json TEXT NOT NULL DEFAULT '[]',
        output_contract_json TEXT NOT NULL DEFAULT '{}',
        status TEXT NOT NULL DEFAULT 'pending',
        attempts INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        started_at TEXT,
        completed_at TEXT,
        lease_owner TEXT,
        lease_token_hash TEXT,
        lease_expires_at TEXT,
        lease_epoch INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (run_id, step_id),
        UNIQUE (run_id, position)
    )"""
)
upgrade.execute(
    """INSERT INTO mc_runs (
        run_id,request_id,request_hash,request_json,owner_id,session_id,surface,
        mode,objective,status,version,budget_profile,created_at,updated_at
    ) VALUES (
        'legacy-run','legacy-request','hash','{}','owner','session','developer',
        'agent','Keep this run','running',4,'default','2026-08-03T00:00:00Z',
        '2026-08-03T00:00:00Z'
    )"""
)
upgrade.execute(
    """INSERT INTO mc_run_steps (
        run_id,step_id,plan_version,position,kind,arguments_json,depends_on_json,
        risk,retry_policy,status,attempts,created_at,updated_at
    ) VALUES (
        'legacy-run','legacy-step','1',0,'tool','{}','[]','none','never',
        'pending',0,'2026-08-03T00:00:00Z','2026-08-03T00:00:00Z'
    )"""
)
_ensure_runtime_schema(upgrade)
_ensure_runtime_schema(upgrade)
upgraded_step_columns = {
    row[1] for row in upgrade.execute("PRAGMA table_info(mc_run_steps)").fetchall()
}
upgraded_run_columns = {
    row[1] for row in upgrade.execute("PRAGMA table_info(mc_runs)").fetchall()
}
upgrade_evidence = (
    {"last_error_json", "last_error_hash", "next_attempt_at"}.issubset(
        upgraded_step_columns
    )
    and {"cancel_requested_at", "cancel_requested_by"}.issubset(
        upgraded_run_columns
    )
    and upgrade.execute(
        "SELECT objective FROM mc_runs WHERE run_id='legacy-run'"
    ).fetchone()[0]
    == "Keep this run"
    and upgrade.execute(
        "SELECT step_id FROM mc_run_steps WHERE run_id='legacy-run'"
    ).fetchone()[0]
    == "legacy-step"
)
upgrade.close()

legacy = sqlite3.connect(os.environ["DB_PATH"])
legacy.execute("CREATE TABLE legacy_owner_data (value TEXT NOT NULL)")
legacy.execute("INSERT INTO legacy_owner_data (value) VALUES ('keep-me')")
legacy.commit()
legacy.close()

init_database()
init_database()
repository = RuntimeRepository()
control = RuntimeControl()

step_columns = {row[1] for row in query("PRAGMA table_info(mc_run_steps)")}
run_columns = {row[1] for row in query("PRAGMA table_info(mc_runs)")}
ok(
    "migration 004 adds command ledger and failure control fields",
    {"last_error_json", "last_error_hash", "next_attempt_at"}.issubset(step_columns)
    and {"cancel_requested_at", "cancel_requested_by"}.issubset(run_columns)
    and bool(
        query("SELECT 1 FROM sqlite_master WHERE type='table' AND name='mc_run_commands'")
    ),
)
ok(
    "migration 004 is idempotent and preserves legacy data",
    len(query("SELECT version FROM schema_migrations WHERE version='mc-runtime-v2-004'")) == 1
    and upgrade_evidence
    and query("SELECT value FROM legacy_owner_data")[0][0] == "keep-me",
)

prepare_running_run(
    repository, "run-success", "request-success", with_dependency=True
)
success_claim = repository.claim_step(
    "run-success", worker_id="worker-success", lease_seconds=60, now=BASE
)
success = control.record_step_success(
    "run-success",
    "first",
    worker_id="worker-success",
    lease_token=success_claim["lease_token"],
    lease_epoch=success_claim["lease_epoch"],
    result=RuntimeToolResult(status="succeeded", typed_output={"answer": 42}),
    now=BASE + timedelta(seconds=1),
)
next_claim = repository.claim_step(
    "run-success",
    worker_id="worker-next",
    lease_seconds=60,
    now=BASE + timedelta(seconds=2),
)
ok(
    "success clears the lease and unlocks the dependency",
    success["status"] == "succeeded"
    and success["attempts"] == 1
    and success["lease_owner"] is None
    and next_claim["step"]["step_id"] == "second",
)

prepare_running_run(
    repository,
    "run-retry",
    "request-retry",
    retry_policy="fixed:3:10",
)
error = RuntimeErrorInfo(
    code="temporary_provider_error",
    category=ErrorCategory.AVAILABILITY,
    stage=ErrorStage.EXECUTE,
    message=f"authorization: Bearer {SECRET}",
    owner_message="The provider is temporarily unavailable.",
    retryable=True,
    recovery_actions=(RecoveryAction.RETRY_STEP, RecoveryAction.CANCEL),
    safe_detail=f"access_token={SECRET}",
)
failed_result = RuntimeToolResult(status="failed", retryable=True, error=error)
retry_claim = repository.claim_step(
    "run-retry", worker_id="worker-retry", lease_seconds=60, now=BASE
)
scheduled = control.record_step_failure(
    "run-retry",
    "first",
    worker_id="worker-retry",
    lease_token=retry_claim["lease_token"],
    lease_epoch=retry_claim["lease_epoch"],
    result=failed_result,
    now=BASE + timedelta(seconds=1),
)
ok(
    "declared retry persists a future schedule and redacted typed error",
    scheduled["status"] == "retry_wait"
    and scheduled["attempts"] == 1
    and scheduled["next_attempt_at"] == "2026-08-03T03:00:11Z"
    and scheduled["last_error"]["safe_detail"] == "access_token=[REDACTED]",
)
ok(
    "scheduled retry is not claimable early",
    repository.claim_step(
        "run-retry",
        worker_id="worker-early",
        lease_seconds=60,
        now=BASE + timedelta(seconds=10),
    )
    is None,
)
second_attempt = repository.claim_step(
    "run-retry",
    worker_id="worker-retry-2",
    lease_seconds=60,
    now=BASE + timedelta(seconds=11),
)
ok(
    "scheduled retry becomes claimable when due and increments attempts",
    second_attempt["step"]["attempts"] == 2
    and second_attempt["lease_epoch"] == 2,
)
second_failure = control.record_step_failure(
    "run-retry",
    "first",
    worker_id="worker-retry-2",
    lease_token=second_attempt["lease_token"],
    lease_epoch=second_attempt["lease_epoch"],
    result=failed_result,
    now=BASE + timedelta(seconds=12),
)
third_attempt = repository.claim_step(
    "run-retry",
    worker_id="worker-retry-3",
    lease_seconds=60,
    now=datetime.fromisoformat(second_failure["next_attempt_at"].replace("Z", "+00:00")),
)
exhausted = control.record_step_failure(
    "run-retry",
    "first",
    worker_id="worker-retry-3",
    lease_token=third_attempt["lease_token"],
    lease_epoch=third_attempt["lease_epoch"],
    result=failed_result,
    now=BASE + timedelta(seconds=23),
)
ok(
    "exhausted retries fail the step and keep the same run in recovery",
    exhausted["status"] == "failed"
    and exhausted["attempts"] == 3
    and repository.get_run("run-retry")["status"] == "recovering"
    and repository.get_run("run-retry")["run_id"] == "run-retry",
)

prepare_running_run(repository, "run-command", "request-command")
command = control.record_command(
    "command-retry",
    "run-command",
    RecoveryAction.RETRY_STEP,
    expected_version=4,
    actor="owner",
    payload={"step_id": "first", "access_token": SECRET},
    now=BASE,
)
replayed = control.record_command(
    "command-retry",
    "run-command",
    RecoveryAction.RETRY_STEP,
    expected_version=4,
    actor="owner",
    payload={"step_id": "first", "access_token": SECRET},
    now=BASE,
)
ok(
    "recovery command is redacted and duplicate submission replays safely",
    command == replayed
    and command["status"] == "pending"
    and command["payload"]["access_token"] == "[REDACTED]",
)
ok(
    "changed command content conflicts and stale run versions are rejected",
    raises(
        CommandConflictError,
        lambda: control.record_command(
            "command-retry",
            "run-command",
            RecoveryAction.RETRY_STEP,
            expected_version=4,
            actor="owner",
            payload={"step_id": "different"},
            now=BASE,
        ),
    )
    and raises(
        VersionConflictError,
        lambda: control.record_command(
            "command-stale",
            "run-command",
            RecoveryAction.RESUME,
            expected_version=3,
            actor="owner",
            now=BASE,
        ),
    ),
)
control.claim_next_command("run-command", consumer_id="consumer-first", now=BASE)
control.record_command(
    "command-resume",
    "run-command",
    RecoveryAction.RESUME,
    expected_version=4,
    actor="owner",
    now=BASE + timedelta(seconds=1),
)


def consume_command(index: int):
    return control.claim_next_command(
        "run-command", consumer_id=f"consumer-{index}", now=BASE + timedelta(seconds=2)
    )


with ThreadPoolExecutor(max_workers=2) as executor:
    consumed = list(executor.map(consume_command, range(2)))
ok(
    "two command consumers race and exactly one wins",
    len([item for item in consumed if item is not None]) == 1
    and [item for item in consumed if item is not None][0]["command_id"]
    == "command-resume",
)

prepare_running_run(repository, "run-cancel", "request-cancel")
cancel_claim = repository.claim_step(
    "run-cancel", worker_id="worker-cancel", lease_seconds=60, now=BASE
)
cancelled_command = control.record_command(
    "command-cancel",
    "run-cancel",
    RecoveryAction.CANCEL,
    expected_version=4,
    actor="owner",
    payload={"reason": "Stop this run"},
    now=BASE + timedelta(seconds=1),
)
cancelled_run = repository.get_run("run-cancel")
ok(
    "cancel command is persisted, consumed, and cancels the same run",
    cancelled_command["status"] == "consumed"
    and cancelled_run["status"] == "cancelled"
    and cancelled_run["version"] == 5
    and cancelled_run["cancel_requested_by"] == "owner",
)
ok(
    "cancellation fences the active worker and prevents future claims",
    raises(
        LeaseConflictError,
        lambda: repository.save_checkpoint(
            "checkpoint-after-cancel",
            "run-cancel",
            "first",
            worker_id="worker-cancel",
            lease_token=cancel_claim["lease_token"],
            lease_epoch=cancel_claim["lease_epoch"],
            state={"cursor": 1},
            now=BASE + timedelta(seconds=2),
        ),
    )
    and repository.claim_step(
        "run-cancel",
        worker_id="worker-after-cancel",
        lease_seconds=60,
        now=BASE + timedelta(seconds=2),
    )
    is None,
)

prepare_running_run(repository, "run-rollback", "request-rollback")
rollback_claim = repository.claim_step(
    "run-rollback", worker_id="worker-rollback", lease_seconds=60, now=BASE
)
append_run_event(
    run_id="run-rollback",
    event_type="test.conflict",
    stage="test",
    actor="test",
    event_id="outcome-event-conflict",
)
ok(
    "event conflict rolls back the step outcome transaction",
    raises(
        EventConflictError,
        lambda: control.record_step_success(
            "run-rollback",
            "first",
            worker_id="worker-rollback",
            lease_token=rollback_claim["lease_token"],
            lease_epoch=rollback_claim["lease_epoch"],
            result=RuntimeToolResult(status="succeeded"),
            now=BASE + timedelta(seconds=1),
            event_id="outcome-event-conflict",
        ),
    )
    and repository.list_steps("run-rollback")[0]["status"] == "running",
)
append_run_event(
    run_id="run-command",
    event_type="test.conflict",
    stage="test",
    actor="test",
    event_id="command-event-conflict",
)
ok(
    "event conflict rolls back command insertion",
    raises(
        EventConflictError,
        lambda: control.record_command(
            "command-rollback",
            "run-command",
            RecoveryAction.PROVIDE_INPUT,
            expected_version=4,
            actor="owner",
            payload={"value": "safe"},
            now=BASE + timedelta(seconds=3),
            event_id="command-event-conflict",
        ),
    )
    and not query(
        "SELECT 1 FROM mc_run_commands WHERE command_id='command-rollback'"
    ),
)

update_blocked = raises(
    sqlite3.IntegrityError,
    lambda: query("UPDATE mc_run_commands SET action='cancel' WHERE command_id='command-retry'"),
)
delete_blocked = raises(
    sqlite3.IntegrityError,
    lambda: query("DELETE FROM mc_run_commands WHERE command_id='command-retry'"),
)
requeue_blocked = raises(
    sqlite3.IntegrityError,
    lambda: query(
        """UPDATE mc_run_commands
           SET status='pending',consumed_by=NULL,consumed_at=NULL
           WHERE command_id='command-retry'"""
    ),
)
ok(
    "command identity and consumed history are immutable in SQLite",
    update_blocked and delete_blocked and requeue_blocked,
)

conn = get_connection()
try:
    durable_dump = "\n".join(conn.iterdump())
finally:
    conn.close()
ok(
    "failure and command secrets never reach durable runtime tables",
    SECRET not in durable_dump and "[REDACTED]" in durable_dump,
)

event_types = [event.event_type for event in list_run_events("run-retry")]
ok(
    "retry and recovery changes join ordered run history",
    "step.retry_scheduled" in event_types
    and "step.failed" in event_types
    and "run.recovering" in event_types,
)

print(f"\n{PASS}/{PASS} T03 Run 3A failure-control tests pass")

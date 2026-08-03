"""Acceptance checks for #21 T03 Run 4 action receipts and idempotency."""
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

TMP = tempfile.mkdtemp(prefix="tobi_t03_run4_")
os.environ["DB_PATH"] = os.path.join(TMP, "agent.db")

from core.database import get_connection, init_database  # noqa: E402
from core.runtime.actions import (  # noqa: E402
    ActionConflictError,
    ActionLedger,
)
from core.runtime.contracts import (  # noqa: E402
    ActionReceipt,
    ExecutionPlan,
    LoopPolicy,
    LoopRecipe,
    LoopType,
    PlanStep,
    RecoveryAction,
    RiskLevel,
    RunRequest,
    RuntimeToolCall,
    RuntimeToolResult,
    Surface,
)
from core.runtime.control import RuntimeControl  # noqa: E402
from core.runtime.event_store import (  # noqa: E402
    EventConflictError,
    append_run_event,
    list_run_events,
)
from core.runtime.repository import RuntimeRepository  # noqa: E402
from core.runtime.state import RunStatus  # noqa: E402
from core.schema.runtime import RUNTIME_SCHEMA_VERSION, _ensure_runtime_schema  # noqa: E402


PASS = 0
BASE = datetime(2026, 8, 3, 10, 0, tzinfo=timezone.utc)
SECRET = "sk-t03-run4-do-not-store"


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


def prepare_run(repository: RuntimeRepository, run_id: str, *, dependency: bool = False) -> None:
    recipe = LoopRecipe(
        recipe_id=f"recipe-{run_id}",
        version="1",
        name="Receipt loop",
        loop_type=LoopType.GOAL,
        trigger="owner request",
        objective="Apply one action safely",
        stop_condition="receipt persisted",
        max_attempts=3,
        max_runtime_s=900,
        max_cost_usd=2.0,
    )
    repository.save_loop_recipe(recipe)
    policy = LoopPolicy.from_recipe(
        policy_id=f"policy-{run_id}",
        version="1",
        recipe=recipe,
        policy_decision_id=f"decision-{run_id}",
        enabled=True,
    )
    repository.create_run(
        RunRequest(
            request_id=f"request-{run_id}",
            surface=Surface.DEVELOPER,
            owner_id="owner",
            session_id="session-t03-run4",
            mode="agent",
            message="Prove duplicate-effect protection",
        ),
        loop_policy=policy,
        run_id=run_id,
    )
    repository.transition_run(run_id, RunStatus.ROUTING, expected_version=1, actor="runtime")
    steps = [
        PlanStep(
            step_id="action",
            kind="tool",
            risk=RiskLevel.MEDIUM,
            tool_name="projects.task.create",
            arguments={"project_id": "project-1", "title": "Create once"},
            retry_policy="transient_once",
            idempotency_key=f"effect-{run_id}",
        )
    ]
    if dependency:
        steps.append(
            PlanStep(
                step_id="verify",
                kind="evaluate",
                risk=RiskLevel.NONE,
                depends_on=("action",),
            )
        )
    repository.save_plan(
        ExecutionPlan(
            plan_id=f"plan-{run_id}",
            run_id=run_id,
            version="1",
            objective="Apply one action safely",
            steps=tuple(steps),
        ),
        expected_version=2,
        actor="runtime",
    )
    repository.transition_run(run_id, RunStatus.RUNNING, expected_version=3, actor="runtime")


def claim(repository: RuntimeRepository, run_id: str, *, worker: str = "worker-1", now=BASE):
    return repository.claim_step(run_id, worker_id=worker, lease_seconds=5, now=now)


def tool_call(run_id: str, *, title: str = "Create once", key: str | None = None) -> RuntimeToolCall:
    return RuntimeToolCall(
        call_id=f"call-{run_id}",
        run_id=run_id,
        step_id="action",
        tool_ref="projects.task.create@1",
        validated_arguments={"project_id": "project-1", "title": title},
        idempotency_key=key or f"effect-{run_id}",
    )


def receipt(run_id: str, *, summary: str = "Created task 1") -> ActionReceipt:
    return ActionReceipt(
        receipt_id=f"receipt-{run_id}",
        run_id=run_id,
        step_id="action",
        tool_ref="projects.task.create@1",
        target="project:project-1",
        effect_summary=summary,
        external_ref="task:1",
        timestamp=(BASE + timedelta(seconds=1)).isoformat(),
    )


def result(run_id: str) -> RuntimeToolResult:
    return RuntimeToolResult(
        status="succeeded",
        typed_output={"task_id": 1},
        evidence_refs=("task:1",),
        receipt_id=f"receipt-{run_id}",
    )


# Migration 006 must be additive and idempotent even when unrelated legacy data exists.
upgrade = sqlite3.connect(os.path.join(TMP, "runtime-v2-005.db"))
upgrade.row_factory = sqlite3.Row
upgrade.execute("CREATE TABLE legacy_marker (id TEXT PRIMARY KEY, value TEXT NOT NULL)")
upgrade.execute("INSERT INTO legacy_marker VALUES ('legacy-1','keep-me')")
_ensure_runtime_schema(upgrade)
_ensure_runtime_schema(upgrade)
tables = {row[0] for row in upgrade.execute("SELECT name FROM sqlite_master WHERE type='table'")}
versions = [
    row[0]
    for row in upgrade.execute(
        "SELECT version FROM schema_migrations WHERE version LIKE 'mc-runtime-v2-%' ORDER BY version"
    )
]
ok(
    "migration 006 is additive, idempotent, and preserves legacy data",
    RUNTIME_SCHEMA_VERSION == "mc-runtime-v2-006"
    and {"mc_idempotency", "mc_action_receipts"} <= tables
    and versions.count("mc-runtime-v2-006") == 1
    and upgrade.execute("SELECT value FROM legacy_marker WHERE id='legacy-1'").fetchone()[0]
    == "keep-me",
)
upgrade.close()

init_database()
repository = RuntimeRepository()
control = RuntimeControl()
ledger = ActionLedger()

prepare_run(repository, "run-basic", dependency=True)
lease = claim(repository, "run-basic")
prepared = ledger.prepare_action(
    tool_call("run-basic"),
    target="project:project-1",
    worker_id=lease["worker_id"],
    lease_token=lease["lease_token"],
    lease_epoch=lease["lease_epoch"],
    now=BASE,
)
ok(
    "the action reservation is durable before execution permission is returned",
    prepared["decision"] == "execute"
    and query("SELECT status FROM mc_idempotency WHERE idempotency_key='effect-run-basic'")[0][0]
    == "in_progress",
)
event_count = len(list_run_events("run-basic"))
duplicate = ledger.prepare_action(
    tool_call("run-basic"),
    target="project:project-1",
    worker_id=lease["worker_id"],
    lease_token=lease["lease_token"],
    lease_epoch=lease["lease_epoch"],
    now=BASE,
)
ok(
    "an unresolved duplicate never receives second execution permission",
    duplicate["decision"] == "reconcile"
    and len(list_run_events("run-basic")) == event_count,
)
ok(
    "changed action content cannot reuse an idempotency key",
    raises(
        ActionConflictError,
        lambda: ledger.prepare_action(
            tool_call("run-basic", title="Different action"),
            target="project:project-1",
            worker_id=lease["worker_id"],
            lease_token=lease["lease_token"],
            lease_epoch=lease["lease_epoch"],
            now=BASE,
        ),
    ),
)
completed = control.record_step_success(
    "run-basic",
    "action",
    worker_id=lease["worker_id"],
    lease_token=lease["lease_token"],
    lease_epoch=lease["lease_epoch"],
    result=result("run-basic"),
    receipt=receipt("run-basic"),
    now=BASE + timedelta(seconds=1),
)
ok(
    "receipt, completed idempotency record, and step success commit atomically",
    completed["status"] == "succeeded"
    and tuple(
        query(
            "SELECT status,receipt_id FROM mc_idempotency "
            "WHERE idempotency_key='effect-run-basic'"
        )[0]
    )
    == ("completed", "receipt-run-basic")
    and query("SELECT COUNT(*) FROM mc_action_receipts WHERE receipt_id='receipt-run-basic'")[0][0]
    == 1,
)
before_replay_events = len(list_run_events("run-basic"))
replay = ledger.prepare_action(
    tool_call("run-basic"),
    target="project:project-1",
    worker_id="worker-replay",
    lease_token="not-used-for-completed-replay",
    lease_epoch=99,
    now=BASE + timedelta(seconds=2),
)
ok(
    "a completed action replays its stored result without another event or effect",
    replay["decision"] == "replay"
    and replay["receipt"]["receipt_id"] == "receipt-run-basic"
    and replay["result"]["typed_output"] == {"task_id": 1}
    and len(list_run_events("run-basic")) == before_replay_events,
)
ok(
    "a side-effecting step cannot report success without its receipt",
    (
        prepare_run(repository, "run-missing-receipt") is None
        and (missing_lease := claim(repository, "run-missing-receipt")) is not None
        and raises(
            ValueError,
            lambda: control.record_step_success(
                "run-missing-receipt",
                "action",
                worker_id=missing_lease["worker_id"],
                lease_token=missing_lease["lease_token"],
                lease_epoch=missing_lease["lease_epoch"],
                result=RuntimeToolResult(status="succeeded", typed_output={}),
                now=BASE,
            ),
        )
        and repository.list_steps("run-missing-receipt")[0]["status"] == "running"
    ),
)

prepare_run(repository, "run-race")
race_lease = claim(repository, "run-race")


def race_prepare(worker: str):
    return ledger.prepare_action(
        tool_call("run-race"),
        target="project:project-1",
        worker_id=race_lease["worker_id"],
        lease_token=race_lease["lease_token"],
        lease_epoch=race_lease["lease_epoch"],
        now=BASE,
    )["decision"]


with ThreadPoolExecutor(max_workers=2) as pool:
    decisions = list(pool.map(race_prepare, ("a", "b")))
ok(
    "two reservation callers race and exactly one receives execution permission",
    sorted(decisions) == ["execute", "reconcile"],
    str(decisions),
)

prepare_run(repository, "run-reserve-conflict")
reserve_lease = claim(repository, "run-reserve-conflict")
append_run_event(
    run_id="run-reserve-conflict",
    event_type="test.seed",
    stage="test",
    actor="test",
    payload={},
    event_id="reserve-conflict-event",
)
ok(
    "event conflict rolls back the reservation",
    raises(
        EventConflictError,
        lambda: ledger.prepare_action(
            tool_call("run-reserve-conflict"),
            target="project:project-1",
            worker_id=reserve_lease["worker_id"],
            lease_token=reserve_lease["lease_token"],
            lease_epoch=reserve_lease["lease_epoch"],
            now=BASE,
            event_id="reserve-conflict-event",
        ),
    )
    and not query(
        "SELECT 1 FROM mc_idempotency WHERE idempotency_key='effect-run-reserve-conflict'"
    ),
)

prepare_run(repository, "run-finish-conflict")
finish_lease = claim(repository, "run-finish-conflict")
ledger.prepare_action(
    tool_call("run-finish-conflict"),
    target="project:project-1",
    worker_id=finish_lease["worker_id"],
    lease_token=finish_lease["lease_token"],
    lease_epoch=finish_lease["lease_epoch"],
    now=BASE,
)
append_run_event(
    run_id="run-finish-conflict",
    event_type="test.seed",
    stage="test",
    actor="test",
    payload={},
    event_id="finish-conflict-event",
)
ok(
    "event conflict rolls back receipt and step completion together",
    raises(
        EventConflictError,
        lambda: control.record_step_success(
            "run-finish-conflict",
            "action",
            worker_id=finish_lease["worker_id"],
            lease_token=finish_lease["lease_token"],
            lease_epoch=finish_lease["lease_epoch"],
            result=result("run-finish-conflict"),
            receipt=receipt("run-finish-conflict"),
            now=BASE + timedelta(seconds=1),
            event_id="finish-conflict-event",
        ),
    )
    and repository.list_steps("run-finish-conflict")[0]["status"] == "running"
    and query(
        "SELECT status FROM mc_idempotency WHERE idempotency_key='effect-run-finish-conflict'"
    )[0][0]
    == "in_progress"
    and not query(
        "SELECT 1 FROM mc_action_receipts WHERE receipt_id='receipt-run-finish-conflict'"
    ),
)

prepare_run(repository, "run-crash")
crash_lease = claim(repository, "run-crash")
ledger.prepare_action(
    tool_call("run-crash"),
    target="project:project-1",
    worker_id=crash_lease["worker_id"],
    lease_token=crash_lease["lease_token"],
    lease_epoch=crash_lease["lease_epoch"],
    now=BASE,
)
reclaimed = claim(repository, "run-crash", worker="worker-2", now=BASE + timedelta(seconds=6))
ok(
    "restart recovery blocks an uncertain expired action instead of reclaiming it",
    reclaimed is None
    and ledger.get_action("effect-run-crash")["status"] == "reconciliation_required"
    and repository.get_run("run-crash")["status"] == "recovering"
    and repository.list_steps("run-crash")[0]["status"] == "reconciliation_required",
)
not_applied = ledger.reconcile_action(
    "effect-run-crash",
    outcome="not_applied",
    actor="owner",
    summary="Provider confirms no task was created",
    evidence_refs=("provider-query:empty",),
    now=BASE + timedelta(seconds=7),
)
not_applied_replay = ledger.reconcile_action(
    "effect-run-crash",
    outcome="not_applied",
    actor="owner",
    summary="Provider confirms no task was created",
    evidence_refs=("provider-query:empty",),
    now=BASE + timedelta(seconds=7),
)
retry_lease = claim(repository, "run-crash", worker="worker-3", now=BASE + timedelta(seconds=8))
retry_decision = ledger.prepare_action(
    tool_call("run-crash"),
    target="project:project-1",
    worker_id=retry_lease["worker_id"],
    lease_token=retry_lease["lease_token"],
    lease_epoch=retry_lease["lease_epoch"],
    now=BASE + timedelta(seconds=8),
)
ok(
    "confirmed not-applied reconciliation permits exactly one later retry",
    not_applied["status"] == "retry_allowed"
    and not_applied_replay == not_applied
    and retry_decision["decision"] == "execute"
    and retry_decision["action"]["execution_count"] == 2,
)

prepare_run(repository, "run-applied")
applied_lease = claim(repository, "run-applied")
ledger.prepare_action(
    tool_call("run-applied"),
    target="project:project-1",
    worker_id=applied_lease["worker_id"],
    lease_token=applied_lease["lease_token"],
    lease_epoch=applied_lease["lease_epoch"],
    now=BASE,
)
claim(repository, "run-applied", worker="worker-2", now=BASE + timedelta(seconds=6))
applied = ledger.reconcile_action(
    "effect-run-applied",
    outcome="applied",
    actor="owner",
    summary="Provider returned the created task",
    evidence_refs=("provider-query:task-1",),
    receipt=receipt("run-applied"),
    result=result("run-applied"),
    now=BASE + timedelta(seconds=7),
)
applied_replay = ledger.reconcile_action(
    "effect-run-applied",
    outcome="applied",
    actor="owner",
    summary="Provider returned the created task",
    evidence_refs=("provider-query:task-1",),
    receipt=receipt("run-applied"),
    result=result("run-applied"),
    now=BASE + timedelta(seconds=8),
)
ok(
    "confirmed-applied reconciliation records one receipt without re-execution",
    applied["status"] == "completed"
    and applied_replay == applied
    and applied["reconciliation_outcome"] == "applied"
    and repository.list_steps("run-applied")[0]["status"] == "succeeded"
    and query("SELECT COUNT(*) FROM mc_action_receipts WHERE run_id='run-applied'")[0][0]
    == 1,
)
ok(
    "completed reconciliation rejects a changed outcome",
    raises(
        ActionConflictError,
        lambda: ledger.reconcile_action(
            "effect-run-applied",
            outcome="unknown",
            actor="owner",
            summary="Changed outcome",
            now=BASE + timedelta(seconds=9),
        ),
    ),
)

prepare_run(repository, "run-unknown")
unknown_lease = claim(repository, "run-unknown")
ledger.prepare_action(
    tool_call("run-unknown"),
    target="project:project-1",
    worker_id=unknown_lease["worker_id"],
    lease_token=unknown_lease["lease_token"],
    lease_epoch=unknown_lease["lease_epoch"],
    now=BASE,
)
unknown = ledger.reconcile_action(
    "effect-run-unknown",
    outcome="unknown",
    actor="owner",
    summary="Provider cannot prove the outcome",
    now=BASE + timedelta(seconds=1),
)
ok(
    "unknown reconciliation remains fail-closed and unclaimable",
    unknown["status"] == "reconciliation_required"
    and repository.get_run("run-unknown")["status"] == "recovering"
    and claim(repository, "run-unknown", worker="worker-2", now=BASE + timedelta(seconds=7))
    is None,
)

prepare_run(repository, "run-cancel")
cancel_lease = claim(repository, "run-cancel")
ledger.prepare_action(
    tool_call("run-cancel"),
    target="project:project-1",
    worker_id=cancel_lease["worker_id"],
    lease_token=cancel_lease["lease_token"],
    lease_epoch=cancel_lease["lease_epoch"],
    now=BASE,
)
control.record_command(
    "cancel-run-with-action",
    "run-cancel",
    RecoveryAction.CANCEL,
    expected_version=4,
    actor="owner",
    now=BASE + timedelta(seconds=1),
)
cancel_replay = ledger.prepare_action(
    tool_call("run-cancel"),
    target="project:project-1",
    worker_id="worker-2",
    lease_token="never-used",
    lease_epoch=2,
    now=BASE + timedelta(seconds=2),
)
ok(
    "cancellation preserves uncertain-effect truth and never enables retry",
    repository.get_run("run-cancel")["status"] == "cancelled"
    and ledger.get_action("effect-run-cancel")["status"] == "reconciliation_required"
    and cancel_replay["decision"] == "reconcile",
)

conn = get_connection()
try:
    receipt_update_blocked = raises(
        sqlite3.DatabaseError,
        lambda: conn.execute(
            "UPDATE mc_action_receipts SET effect_summary='changed' WHERE receipt_id='receipt-run-basic'"
        ),
    )
    receipt_delete_blocked = raises(
        sqlite3.DatabaseError,
        lambda: conn.execute(
            "DELETE FROM mc_action_receipts WHERE receipt_id='receipt-run-basic'"
        ),
    )
finally:
    conn.rollback()
    conn.close()
ok(
    "completed action receipts are immutable at the database boundary",
    receipt_update_blocked and receipt_delete_blocked,
)

prepare_run(repository, "run-secret")
secret_lease = claim(repository, "run-secret")
ledger.prepare_action(
    tool_call("run-secret", title=f"Create with api_key={SECRET}"),
    target="project:project-1",
    worker_id=secret_lease["worker_id"],
    lease_token=secret_lease["lease_token"],
    lease_epoch=secret_lease["lease_epoch"],
    now=BASE,
)
control.record_step_success(
    "run-secret",
    "action",
    worker_id=secret_lease["worker_id"],
    lease_token=secret_lease["lease_token"],
    lease_epoch=secret_lease["lease_epoch"],
    result=RuntimeToolResult(
        status="succeeded",
        typed_output={"api_key": SECRET},
        receipt_id="receipt-run-secret",
    ),
    receipt=receipt("run-secret", summary=f"Created with secret={SECRET}"),
    now=BASE + timedelta(seconds=1),
)
raw_db = Path(os.environ["DB_PATH"]).read_bytes()
ok(
    "action fingerprints, results, receipts, and events redact secrets before storage",
    SECRET.encode() not in raw_db and b"[REDACTED]" in raw_db,
)

events = list_run_events("run-basic")
event_types = [event.event_type for event in events]
ok(
    "action decisions join the ordered canonical run history",
    [event.sequence for event in events] == list(range(1, len(events) + 1))
    and "action.reserved" in event_types
    and "action.receipt_recorded" in event_types
    and event_types.index("action.reserved") < event_types.index("action.receipt_recorded"),
)

conn = get_connection()
try:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS chat_tool_receipts (
            idempotency_key TEXT PRIMARY KEY,
            turn_id TEXT,
            tool TEXT NOT NULL,
            args_hash TEXT NOT NULL,
            status TEXT NOT NULL,
            result_json TEXT,
            error_code TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )"""
    )
    conn.execute(
        "INSERT INTO chat_tool_receipts "
        "(idempotency_key,turn_id,tool,args_hash,status,result_json,created_at,updated_at) "
        "VALUES ('legacy-chat-receipt','turn-1','legacy.tool','hash','done','{}','now','now')"
    )
    conn.commit()
    _ensure_runtime_schema(conn)
    legacy = conn.execute(
        "SELECT status FROM chat_tool_receipts WHERE idempotency_key='legacy-chat-receipt'"
    ).fetchone()
finally:
    conn.close()
ok("legacy Chat receipts remain untouched", legacy[0] == "done")

print(f"\n{PASS}/{PASS} T03 Run 4 action-receipt tests pass")

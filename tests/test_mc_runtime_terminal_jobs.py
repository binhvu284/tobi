"""T07 Run 3B2B: dormant restart-safe managed terminal job cancellation."""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import sys
import tempfile
import time
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


TMP = Path(tempfile.mkdtemp(prefix="tobi_t07_terminal_jobs_"))
os.environ["DB_PATH"] = str(TMP / "agent.db")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.database import get_connection, init_database  # noqa: E402
from core.runtime.actions import ActionConflictError  # noqa: E402
from core.runtime.contracts import (  # noqa: E402
    ApprovalMode,
    ApprovalStatus,
    BudgetStatus,
    Certainty,
    ExecutionPlan,
    IsolationLevel,
    LoopPolicy,
    LoopRecipe,
    LoopType,
    PlanStep,
    PolicyInput,
    RiskLevel,
    RunRequest,
    SideEffectClass,
    Surface,
    TrustClass,
    contract_to_dict,
)
from core.runtime.repository import RuntimeRepository  # noqa: E402
from core.runtime.state import RunStatus  # noqa: E402
from core.runtime.terminal_jobs import (  # noqa: E402
    CANCELLATION_POLL_SECONDS,
    HEARTBEAT_STALE_SECONDS,
    MAX_JOB_OUTPUT_CHARS,
    TerminalJobError,
    TerminalJobRepository,
)
from core.runtime.terminal_tools import (  # noqa: E402
    CANCEL_JOB_REF,
    JOB_OUTPUT_REF,
    LIST_JOBS_REF,
    START_JOB_REF,
    build_terminal_job_runtime,
    terminal_job_cancel_target,
    terminal_job_target,
)
from core.runtime.tool_catalog import ToolCallPreparationError  # noqa: E402
from core.runtime.tool_execution import ToolExecutionError  # noqa: E402
from core.schema.runtime import (  # noqa: E402
    RUNTIME_SCHEMA_VERSION,
    RUNTIME_SCHEMA_VERSIONS,
    _ensure_runtime_schema,
)


PASS = 0


def ok(name: str, condition: bool, detail: object = "") -> None:
    global PASS
    if not condition:
        print(f"FAIL {name}: {detail}")
        raise SystemExit(1)
    PASS += 1
    print(f"PASS {name}")


def raises(error_type: type[Exception], callback) -> Exception | None:
    try:
        callback()
    except error_type as exc:
        return exc
    return None


def query_one(sql: str, parameters: tuple = ()) -> sqlite3.Row | None:
    conn = get_connection()
    try:
        return conn.execute(sql, parameters).fetchone()
    finally:
        conn.close()


def query_all(sql: str, parameters: tuple = ()) -> list[sqlite3.Row]:
    conn = get_connection()
    try:
        return conn.execute(sql, parameters).fetchall()
    finally:
        conn.close()


def query_count(table: str) -> int:
    row = query_one(f"SELECT COUNT(*) AS count FROM {table}")
    return int(row["count"]) if row else 0


def sql_rejected(sql: str, parameters: tuple = ()) -> bool:
    conn = get_connection()
    try:
        conn.execute(sql, parameters)
        conn.commit()
    except sqlite3.DatabaseError:
        conn.rollback()
        return True
    finally:
        conn.close()
    return False


def prepare_run(
    repository: RuntimeRepository,
    *,
    run_id: str,
    tool_ref: str,
    arguments: dict[str, Any],
    idempotency_key: str | None = None,
) -> tuple[str, dict]:
    step_id = f"step-{run_id}"
    recipe = LoopRecipe(
        recipe_id=f"recipe-{run_id}",
        version="1",
        name="Managed terminal job fixture",
        loop_type=LoopType.TURN,
        trigger="owner request",
        objective="Use one bounded managed terminal job",
        stop_condition="typed terminal job result persisted",
        max_attempts=2,
        max_runtime_s=360,
        max_cost_usd=1.0,
        allowed_tools=(tool_ref,),
    )
    repository.save_loop_recipe(recipe)
    repository.create_run(
        RunRequest(
            request_id=f"request-{run_id}",
            surface=Surface.AGENT,
            owner_id="owner",
            session_id="session-t07-run3b2a",
            mode="agent",
            message="Use one managed terminal job",
        ),
        loop_policy=LoopPolicy.from_recipe(
            policy_id=f"loop-policy-{run_id}",
            version="1",
            recipe=recipe,
            policy_decision_id=f"bootstrap-{run_id}",
            enabled=True,
        ),
        run_id=run_id,
    )
    repository.transition_run(
        run_id, RunStatus.ROUTING, expected_version=1, actor="runtime-test"
    )
    repository.save_plan(
        ExecutionPlan(
            plan_id=f"plan-{run_id}",
            run_id=run_id,
            version="1",
            objective="Use one managed terminal job",
            steps=(
                PlanStep(
                    step_id=step_id,
                    kind="tool",
                    risk=(
                        RiskLevel.HIGH
                        if tool_ref in {START_JOB_REF, CANCEL_JOB_REF}
                        else RiskLevel.NONE
                    ),
                    tool_name=tool_ref,
                    arguments=arguments,
                    retry_policy="none",
                    idempotency_key=idempotency_key,
                ),
            ),
        ),
        expected_version=2,
        actor="runtime-test",
    )
    repository.transition_run(
        run_id, RunStatus.RUNNING, expected_version=3, actor="runtime-test"
    )
    lease = repository.claim_step(run_id, worker_id=f"worker-{run_id}")
    assert lease is not None
    return step_id, lease


def prepare_call(
    runtime,
    repository: RuntimeRepository,
    *,
    run_id: str,
    tool_ref: str,
    arguments: dict[str, Any],
    target: str,
    permissions: tuple[str, ...],
    isolations: tuple[IsolationLevel, ...],
    idempotency_key: str | None = None,
    approval_status: ApprovalStatus = ApprovalStatus.NONE,
    approval_id: str | None = None,
):
    step_id, lease = prepare_run(
        repository,
        run_id=run_id,
        tool_ref=tool_ref,
        arguments=arguments,
        idempotency_key=idempotency_key,
    )
    call = runtime.catalog.prepare_call(
        call_id=f"call-{run_id}",
        run_id=run_id,
        step_id=step_id,
        tool_ref=tool_ref,
        arguments=arguments,
        surface=Surface.AGENT,
        mode="agent",
        candidate_tool_refs=(tool_ref,),
        idempotency_key=idempotency_key,
        approval_id=approval_id,
    )
    facts = PolicyInput(
        decision_id=f"policy-{run_id}",
        run_id=run_id,
        step_id=step_id,
        owner_id="owner",
        session_id="session-t07-run3b2a",
        surface=Surface.AGENT,
        mode="agent",
        tool=runtime.catalog.get_spec(tool_ref),
        target=target,
        granted_permissions=permissions,
        trust_class=TrustClass.OWNER_DIRECT,
        certainty=Certainty.KNOWN,
        instruction_authority=True,
        available_isolations=isolations,
        budget_status=BudgetStatus.AVAILABLE,
        approval_mode=ApprovalMode.ASK,
        approval_status=approval_status,
        approval_id=approval_id,
    )
    return call, facts, lease


def execute_prepared(runtime, call, facts, lease):
    return runtime.execute(
        call,
        facts,
        worker_id=lease["worker_id"],
        lease_token=lease["lease_token"],
        lease_epoch=lease["lease_epoch"],
    )


class FakeTerminalState:
    def __init__(self) -> None:
        self.mode = "ask"
        self.enabled = True

    def effective_mode(self, surface: str = "mc") -> str:
        return self.mode

    def status(self) -> dict[str, Any]:
        return {"enabled": self.enabled, "mode": self.mode}


class ClaimingLauncher:
    def __init__(self, jobs: TerminalJobRepository) -> None:
        self.jobs = jobs
        self.calls: list[tuple[str, str]] = []

    def __call__(self, job_id: str, worker_token: str) -> None:
        self.calls.append((job_id, worker_token))
        self.jobs.claim_worker(job_id, worker_token)


class NoHandshakeLauncher:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def __call__(self, job_id: str, worker_token: str) -> None:
        self.calls.append((job_id, worker_token))


class FailingLauncher:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, job_id: str, worker_token: str) -> None:
        self.calls += 1
        raise OSError("simulated definite pre-spawn failure")


class RaiseAfterCancelRepository(TerminalJobRepository):
    def request_cancellation(self, *args, **kwargs):
        super().request_cancellation(*args, **kwargs)
        raise RuntimeError("simulated response loss after committed cancel request")


init_database()
conn = get_connection()
try:
    _ensure_runtime_schema(conn)
    _ensure_runtime_schema(conn)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS terminal_jobs (
            id INTEGER PRIMARY KEY, command TEXT, cwd TEXT, shell TEXT, pid INTEGER,
            status TEXT, exit_code INTEGER, output TEXT, risk TEXT, mode TEXT,
            surface TEXT, started_at TEXT, ended_at TEXT
        )"""
    )
    conn.execute(
        "INSERT INTO terminal_jobs (id,command,cwd,status) VALUES (1,'legacy raw','C:/legacy','done')"
    )
    conn.commit()
finally:
    conn.close()

migrations = query_count("schema_migrations")
columns = {
    row[1]
    for row in query_all("PRAGMA table_info(mc_terminal_jobs)")
}
ok(
    "migration 010 adds cancellation evidence without raw command path or PID columns",
    RUNTIME_SCHEMA_VERSION == "mc-runtime-v2-010"
    and RUNTIME_SCHEMA_VERSIONS.count("mc-runtime-v2-010") == 1
    and migrations >= len(RUNTIME_SCHEMA_VERSIONS)
    and {
        "job_id",
        "command_sha256",
        "working_directory_sha256",
        "heartbeat_at",
        "cancel_idempotency_key",
        "cancel_requested_at",
        "cancel_requested_by",
        "cancel_acknowledged_at",
    }.issubset(columns)
    and {"command", "cwd", "pid", "worker_token"}.isdisjoint(columns)
    and query_count("terminal_jobs") == 1,
    columns,
)

upgrade_path = TMP / "upgrade-from-v009.db"
upgrade_conn = sqlite3.connect(upgrade_path)
try:
    _ensure_runtime_schema(upgrade_conn)
    for statement in (
        "DROP TRIGGER IF EXISTS mc_terminal_jobs_cancel_request_guard",
        "DROP TRIGGER IF EXISTS mc_terminal_jobs_cancel_ack_guard",
        "DROP INDEX IF EXISTS idx_mc_terminal_jobs_cancel_request",
    ):
        upgrade_conn.execute(statement)
    for column in (
        "cancel_acknowledged_at",
        "cancel_requested_by",
        "cancel_requested_at",
        "cancel_idempotency_key",
    ):
        upgrade_conn.execute(f"ALTER TABLE mc_terminal_jobs DROP COLUMN {column}")
    upgrade_conn.execute(
        "DELETE FROM schema_migrations WHERE version='mc-runtime-v2-010'"
    )
    empty_hash = hashlib.sha256(b"").hexdigest()
    upgrade_conn.execute(
        """INSERT INTO mc_terminal_jobs (
            job_id,start_idempotency_key,run_id,step_id,call_id,tool_ref,target,
            operation,command_sha256,working_directory_sha256,duration_s,status,
            output_sha256,created_at,updated_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            "terminal-job-00000000000000000000000000000000",
            "v009-start-key",
            "v009-run",
            "v009-step",
            "v009-call",
            START_JOB_REF,
            "terminal:job-start:v009",
            "wait",
            "1" * 64,
            "2" * 64,
            10,
            "running",
            empty_hash,
            "2026-08-11T00:00:00+00:00",
            "2026-08-11T00:00:00+00:00",
        ),
    )
    upgrade_conn.commit()
    _ensure_runtime_schema(upgrade_conn)
    upgraded_columns = {
        row[1] for row in upgrade_conn.execute("PRAGMA table_info(mc_terminal_jobs)")
    }
    upgraded_row = upgrade_conn.execute(
        "SELECT status,duration_s FROM mc_terminal_jobs WHERE job_id=?",
        ("terminal-job-00000000000000000000000000000000",),
    ).fetchone()
    upgraded_versions = {
        row[0] for row in upgrade_conn.execute("SELECT version FROM schema_migrations")
    }
finally:
    upgrade_conn.close()
ok(
    "a populated version 009 terminal job upgrades in place without data loss",
    {
        "cancel_idempotency_key",
        "cancel_requested_at",
        "cancel_requested_by",
        "cancel_acknowledged_at",
    }.issubset(upgraded_columns)
    and upgraded_row == ("running", 10)
    and "mc-runtime-v2-010" in upgraded_versions,
    (upgraded_columns, upgraded_row, upgraded_versions),
)

repository = RuntimeRepository()
jobs = TerminalJobRepository()
engine = FakeTerminalState()
launcher = ClaimingLauncher(jobs)
runtime = build_terminal_job_runtime(
    engine=engine,
    job_repository=jobs,
    launcher=launcher,
    working_directory=ROOT,
)

refs = tuple(entry.tool_ref for entry in runtime.catalog.manifest.entries)
start_spec = runtime.catalog.get_spec(START_JOB_REF)
list_spec = runtime.catalog.get_spec(LIST_JOBS_REF)
output_spec = runtime.catalog.get_spec(JOB_OUTPUT_REF)
cancel_spec = runtime.catalog.get_spec(CANCEL_JOB_REF)
manifest_json = json.dumps(contract_to_dict(runtime.catalog.manifest), sort_keys=True)
ok(
    "job catalog exposes bounded start list output and approved cancel contracts",
    set(refs) == {START_JOB_REF, LIST_JOBS_REF, JOB_OUTPUT_REF, CANCEL_JOB_REF}
    and len(refs) == 4
    and start_spec.side_effect_class is SideEffectClass.REVERSIBLE
    and start_spec.risk is RiskLevel.HIGH
    and start_spec.required_permissions == ("terminal.execute",)
    and start_spec.idempotency_policy == "required"
    and start_spec.isolation == "subprocess"
    and list_spec.side_effect_class is SideEffectClass.NONE
    and output_spec.side_effect_class is SideEffectClass.NONE
    and cancel_spec.side_effect_class is SideEffectClass.IRREVERSIBLE
    and cancel_spec.risk is RiskLevel.HIGH
    and cancel_spec.required_permissions == ("terminal.execute",)
    and cancel_spec.idempotency_policy == "required"
    and cancel_spec.isolation == "in_process"
    and list_spec.required_permissions == ("terminal.read",)
    and output_spec.required_permissions == ("terminal.read",)
    and "callable" not in manifest_json.lower()
    and str(ROOT).lower() not in manifest_json.lower(),
    manifest_json,
)

invalid_arguments = (
    {},
    {"duration_s": 0},
    {"duration_s": 301},
    {"duration_s": -1},
    {"duration_s": 1.5},
    {"duration_s": True},
    {"duration_s": "30"},
    {"command": "wait 1"},
    {"duration_s": 1, "command": "wait 1"},
    {"duration_s": 1, "cwd": "C:/owner"},
    {"duration_s": 1, "background": True},
)
invalid = [
    raises(
        ToolCallPreparationError,
        lambda arguments=arguments: runtime.catalog.prepare_call(
            call_id=(
                "invalid-"
                + hashlib.sha256(
                    json.dumps(arguments, sort_keys=True).encode()
                ).hexdigest()[:8]
            ),
            run_id="invalid-run",
            step_id="invalid-step",
            tool_ref=START_JOB_REF,
            arguments=arguments,
            surface=Surface.AGENT,
            mode="agent",
            candidate_tool_refs=(START_JOB_REF,),
            idempotency_key="effect-invalid",
            approval_id="approval-invalid",
        ),
    )
    for arguments in invalid_arguments
]
ok(
    "only one typed wait duration from 1 through 300 passes schema validation",
    all(error is not None for error in invalid) and launcher.calls == [],
    invalid,
)

invalid_cancel_arguments = (
    {},
    {"job_id": "terminal-job-short"},
    {"job_id": "terminal-job-" + "g" * 32},
    {"job_id": "terminal-job-" + "0" * 32, "pid": 1234},
    {"pid": 1234},
)
invalid_cancel = [
    raises(
        ToolCallPreparationError,
        lambda arguments=arguments: runtime.catalog.prepare_call(
            call_id="invalid-cancel-" + hashlib.sha256(
                json.dumps(arguments, sort_keys=True).encode()
            ).hexdigest()[:8],
            run_id="invalid-cancel-run",
            step_id="invalid-cancel-step",
            tool_ref=CANCEL_JOB_REF,
            arguments=arguments,
            surface=Surface.AGENT,
            mode="agent",
            candidate_tool_refs=(CANCEL_JOB_REF,),
            idempotency_key="effect-invalid-cancel",
            approval_id="approval-invalid-cancel",
        ),
    )
    for arguments in invalid_cancel_arguments
]
ok(
    "cancel accepts only one canonical job id and never a PID or process argument",
    all(error is not None for error in invalid_cancel) and launcher.calls == [],
    invalid_cancel,
)

denied_results = []
for run_id, permissions, isolations, approval, enabled, terminal_mode in (
    ("job-missing-approval", ("terminal.execute",), (IsolationLevel.SUBPROCESS,), ApprovalStatus.NONE, True, "ask"),
    ("job-missing-permission", (), (IsolationLevel.SUBPROCESS,), ApprovalStatus.APPROVED, True, "ask"),
    (
        "job-missing-isolation",
        ("terminal.execute",),
        (IsolationLevel.IN_PROCESS,),
        ApprovalStatus.APPROVED,
        True,
        "ask",
    ),
    (
        "job-terminal-disabled",
        ("terminal.execute",),
        (IsolationLevel.SUBPROCESS,),
        ApprovalStatus.APPROVED,
        False,
        "ask",
    ),
    ("job-terminal-plan", ("terminal.execute",), (IsolationLevel.SUBPROCESS,), ApprovalStatus.APPROVED, True, "plan"),
):
    engine.enabled = enabled
    engine.mode = terminal_mode
    duration_s = 30
    call, facts, lease = prepare_call(
        runtime,
        repository,
        run_id=run_id,
        tool_ref=START_JOB_REF,
        arguments={"duration_s": duration_s},
        target=terminal_job_target(duration_s, ROOT),
        permissions=permissions,
        isolations=isolations,
        idempotency_key=f"effect-{run_id}",
        approval_status=approval,
        approval_id=f"approval-{run_id}" if approval is ApprovalStatus.APPROVED else None,
    )
    denied_results.append(execute_prepared(runtime, call, facts, lease))
engine.enabled = True
engine.mode = "ask"
ok(
    "approval permission isolation terminal kill-switch and plan mode deny before launch",
    [result.status for result in denied_results] == ["blocked"] * 5
    and all(result.error is not None for result in denied_results)
    and launcher.calls == []
    and all(
        query_one("SELECT 1 FROM mc_idempotency WHERE idempotency_key=?", (f"effect-{run_id}",)) is None
        for run_id in (
            "job-missing-approval",
            "job-missing-permission",
            "job-missing-isolation",
            "job-terminal-disabled",
            "job-terminal-plan",
        )
    ),
    denied_results,
)

duration_s = 30
start_call, start_facts, start_lease = prepare_call(
    runtime,
    repository,
    run_id="job-start-success",
    tool_ref=START_JOB_REF,
    arguments={"duration_s": duration_s},
    target=terminal_job_target(duration_s, ROOT),
    permissions=("terminal.execute",),
    isolations=(IsolationLevel.SUBPROCESS,),
    idempotency_key="effect-job-start-success",
    approval_status=ApprovalStatus.APPROVED,
    approval_id="approval-job-start-success",
)
start_result = execute_prepared(runtime, start_call, start_facts, start_lease)
job_id = start_result.typed_output["job_id"]
job_row = query_one("SELECT * FROM mc_terminal_jobs WHERE job_id=?", (job_id,))
action_row = query_one(
    "SELECT * FROM mc_idempotency WHERE idempotency_key='effect-job-start-success'"
)
receipt_row = query_one(
    "SELECT * FROM mc_action_receipts WHERE idempotency_key='effect-job-start-success'"
)
ok(
    "approved start writes intent before one worker handshake and records one receipt",
    start_result.status == "succeeded"
    and start_result.typed_output["state"] == "running"
    and start_result.typed_output["duration_s"] == 30
    and start_result.receipt_id is not None
    and len(launcher.calls) == 1
    and job_row is not None
    and job_row["status"] == "running"
    and job_row["worker_identity_sha256"]
    and job_row["heartbeat_at"]
    and action_row is not None
    and action_row["status"] == "completed"
    and action_row["execution_count"] == 1
    and receipt_row is not None
    and receipt_row["approval_ref"] == "approval-job-start-success"
    and query_count("terminal_jobs") == 1,
    start_result,
)

ok(
    "database guards reject identity edits illegal lifecycle rewinds and deletes",
    sql_rejected(
        "UPDATE mc_terminal_jobs SET run_id='tampered' WHERE job_id=?", (job_id,)
    )
    and sql_rejected(
        "UPDATE mc_terminal_jobs SET status='intent' WHERE job_id=?", (job_id,)
    )
    and sql_rejected("DELETE FROM mc_terminal_jobs WHERE job_id=?", (job_id,)),
)

restarted_jobs = TerminalJobRepository()
fresh = restarted_jobs.get_job(job_id)
future = datetime.now(timezone.utc) + timedelta(seconds=HEARTBEAT_STALE_SECONDS + 2)
stale = restarted_jobs.get_job(job_id, now=future)
ok(
    "a new repository sees fresh worker proof and reports stale proof as unknown",
    fresh["state"] == "running"
    and stale["state"] == "unknown"
    and query_one("SELECT status FROM mc_terminal_jobs WHERE job_id=?", (job_id,))["status"] == "running"
    and len(launcher.calls) == 1,
    (fresh, stale),
)

secret_output = "x" * (MAX_JOB_OUTPUT_CHARS + 100) + " api_key=super-secret-value"
restarted_jobs.finish_job(
    job_id,
    launcher.calls[0][1],
    status="succeeded",
    exit_code=0,
    output=secret_output,
)
finished = restarted_jobs.get_job(job_id)
receipt_count = query_count("mc_action_receipts")

list_call, list_facts, list_lease = prepare_call(
    runtime,
    repository,
    run_id="job-list-read",
    tool_ref=LIST_JOBS_REF,
    arguments={"limit": 50},
    target="terminal:jobs",
    permissions=("terminal.read",),
    isolations=(IsolationLevel.IN_PROCESS,),
)
listed = execute_prepared(runtime, list_call, list_facts, list_lease)
output_call, output_facts, output_lease = prepare_call(
    runtime,
    repository,
    run_id="job-output-read",
    tool_ref=JOB_OUTPUT_REF,
    arguments={"job_id": job_id, "tail": MAX_JOB_OUTPUT_CHARS},
    target=f"terminal:job:{job_id}",
    permissions=("terminal.read",),
    isolations=(IsolationLevel.IN_PROCESS,),
)
output = execute_prepared(runtime, output_call, output_facts, output_lease)
listed_job = next(item for item in listed.typed_output["jobs"] if item["job_id"] == job_id)
ok(
    "restart-safe list and output reads are bounded redacted and receipt free",
    finished["state"] == "succeeded"
    and len(finished["output"]) == MAX_JOB_OUTPUT_CHARS
    and "super-secret-value" not in finished["output"]
    and "[REDACTED]" in finished["output"]
    and finished["truncated"] is True
    and listed.status == "succeeded"
    and output.status == "succeeded"
    and listed.receipt_id is None
    and output.receipt_id is None
    and "output" not in listed_job
    and output.typed_output["output"] == finished["output"]
    and query_count("mc_action_receipts") == receipt_count,
    (listed, output),
)
ok(
    "final job rows reject later output or state mutation",
    sql_rejected(
        "UPDATE mc_terminal_jobs SET output='changed' WHERE job_id=?", (job_id,)
    ),
)

replay_launches = len(launcher.calls)
replay = runtime.execute(
    start_call,
    start_facts,
    worker_id="replay-worker",
    lease_token="unused-replay-token",
    lease_epoch=99,
)
changed_duration = 31
changed_call = runtime.catalog.prepare_call(
    call_id=start_call.call_id,
    run_id=start_call.run_id,
    step_id=start_call.step_id,
    tool_ref=START_JOB_REF,
    arguments={"duration_s": changed_duration},
    surface=Surface.AGENT,
    mode="agent",
    candidate_tool_refs=(START_JOB_REF,),
    idempotency_key=start_call.idempotency_key,
    approval_id=start_call.approval_id,
)
changed = raises(
    ActionConflictError,
    lambda: runtime.execute(
        changed_call,
        replace(
            start_facts,
            decision_id="policy-job-start-changed",
            target=terminal_job_target(changed_duration, ROOT),
        ),
        worker_id="changed-worker",
        lease_token="unused-changed-token",
        lease_epoch=100,
    ),
)
changed_approval_call = runtime.catalog.prepare_call(
    call_id=start_call.call_id,
    run_id=start_call.run_id,
    step_id=start_call.step_id,
    tool_ref=START_JOB_REF,
    arguments={"duration_s": duration_s},
    surface=Surface.AGENT,
    mode="agent",
    candidate_tool_refs=(START_JOB_REF,),
    idempotency_key=start_call.idempotency_key,
    approval_id="approval-job-start-changed",
)
changed_approval = raises(
    ActionConflictError,
    lambda: runtime.execute(
        changed_approval_call,
        replace(
            start_facts,
            decision_id="policy-job-start-approval-changed",
            approval_id="approval-job-start-changed",
        ),
        worker_id="changed-approval-worker",
        lease_token="unused-changed-approval-token",
        lease_epoch=101,
    ),
)
ok(
    "exact start replay returns one job without launch and changed identity conflicts",
    replay == start_result
    and changed is not None
    and changed_approval is not None
    and len(launcher.calls) == replay_launches
    and query_one(
        "SELECT execution_count FROM mc_idempotency WHERE idempotency_key='effect-job-start-success'"
    )["execution_count"]
    == 1,
    replay,
)

failing = FailingLauncher()
failure_runtime = build_terminal_job_runtime(
    engine=engine,
    job_repository=jobs,
    launcher=failing,
    working_directory=ROOT,
)
failure_call, failure_facts, failure_lease = prepare_call(
    failure_runtime,
    repository,
    run_id="job-definite-prelaunch-failure",
    tool_ref=START_JOB_REF,
    arguments={"duration_s": 20},
    target=terminal_job_target(20, ROOT),
    permissions=("terminal.execute",),
    isolations=(IsolationLevel.SUBPROCESS,),
    idempotency_key="effect-job-definite-prelaunch-failure",
    approval_status=ApprovalStatus.APPROVED,
    approval_id="approval-job-definite-prelaunch-failure",
)
failed_start = execute_prepared(
    failure_runtime, failure_call, failure_facts, failure_lease
)
retry_launcher = ClaimingLauncher(jobs)
retry_runtime = build_terminal_job_runtime(
    engine=engine,
    job_repository=jobs,
    launcher=retry_launcher,
    working_directory=ROOT,
)
retry_lease = repository.claim_step(
    failure_call.run_id, worker_id="worker-job-definite-prelaunch-retry"
)
assert retry_lease is not None
retried_start = execute_prepared(
    retry_runtime, failure_call, failure_facts, retry_lease
)
failed_job_id = retried_start.typed_output["job_id"]
ok(
    "definite pre-spawn failure is not applied and the same job may retry once safely",
    failed_start.status == "failed"
    and failed_start.error is not None
    and failed_start.error.code == "tool.action_not_applied"
    and failed_start.error.retryable is True
    and failing.calls == 1
    and retried_start.status == "succeeded"
    and len(retry_launcher.calls) == 1
    and query_one(
        "SELECT launch_count,status FROM mc_terminal_jobs WHERE job_id=?", (failed_job_id,)
    )["launch_count"]
    == 2
    and query_one(
        "SELECT execution_count FROM mc_idempotency WHERE idempotency_key='effect-job-definite-prelaunch-failure'"
    )["execution_count"]
    == 2,
    (failed_start, retried_start),
)

no_handshake = NoHandshakeLauncher()
unknown_runtime = build_terminal_job_runtime(
    engine=engine,
    job_repository=jobs,
    launcher=no_handshake,
    working_directory=ROOT,
    handshake_timeout_s=0.05,
    poll_interval_s=0.01,
)
unknown_call, unknown_facts, unknown_lease = prepare_call(
    unknown_runtime,
    repository,
    run_id="job-uncertain-launch",
    tool_ref=START_JOB_REF,
    arguments={"duration_s": 25},
    target=terminal_job_target(25, ROOT),
    permissions=("terminal.execute",),
    isolations=(IsolationLevel.SUBPROCESS,),
    idempotency_key="effect-job-uncertain-launch",
    approval_status=ApprovalStatus.APPROVED,
    approval_id="approval-job-uncertain-launch",
)
unknown_initial = execute_prepared(
    unknown_runtime, unknown_call, unknown_facts, unknown_lease
)
unknown_retry = execute_prepared(
    unknown_runtime, unknown_call, unknown_facts, unknown_lease
)
unknown_job_id, unknown_token = no_handshake.calls[0]
jobs.claim_worker(unknown_job_id, unknown_token)
jobs.finish_job(
    unknown_job_id,
    unknown_token,
    status="succeeded",
    exit_code=0,
    output="Wait job completed after delayed handshake.",
)
reconciled = unknown_runtime.reconcile_action(unknown_call, actor="owner")
ok(
    "possible launch without handshake stays unknown blocks retry and reconciles from worker proof",
    unknown_initial.status == "blocked"
    and unknown_initial.error is not None
    and unknown_initial.error.code == "tool.action_reconciliation_required"
    and unknown_retry.status == "blocked"
    and len(no_handshake.calls) == 1
    and reconciled.status == "succeeded"
    and reconciled.typed_output["job_id"] == unknown_job_id
    and reconciled.typed_output["state"] == "succeeded"
    and reconciled.receipt_id is not None
    and query_one(
        "SELECT status FROM mc_idempotency WHERE idempotency_key='effect-job-uncertain-launch'"
    )["status"]
    == "completed",
    (unknown_initial, reconciled),
)

cancel_job_id = failed_job_id
cancel_target = terminal_job_cancel_target(cancel_job_id)
missing_approval_call, missing_approval_facts, missing_approval_lease = prepare_call(
    runtime,
    repository,
    run_id="job-cancel-missing-approval",
    tool_ref=CANCEL_JOB_REF,
    arguments={"job_id": cancel_job_id},
    target=cancel_target,
    permissions=("terminal.execute",),
    isolations=(IsolationLevel.IN_PROCESS,),
    idempotency_key="effect-job-cancel-missing-approval",
)
missing_approval = execute_prepared(
    runtime, missing_approval_call, missing_approval_facts, missing_approval_lease
)
wrong_owner_call, wrong_owner_facts, wrong_owner_lease = prepare_call(
    runtime,
    repository,
    run_id="job-cancel-wrong-owner",
    tool_ref=CANCEL_JOB_REF,
    arguments={"job_id": cancel_job_id},
    target=cancel_target,
    permissions=("terminal.execute",),
    isolations=(IsolationLevel.IN_PROCESS,),
    idempotency_key="effect-job-cancel-wrong-owner",
    approval_status=ApprovalStatus.APPROVED,
    approval_id="approval-job-cancel-wrong-owner",
)
wrong_owner = raises(
    ToolExecutionError,
    lambda: execute_prepared(
        runtime,
        wrong_owner_call,
        replace(wrong_owner_facts, owner_id="other-owner"),
        wrong_owner_lease,
    ),
)
missing_job_id = "terminal-job-" + "0" * 32
missing_job_call, missing_job_facts, missing_job_lease = prepare_call(
    runtime,
    repository,
    run_id="job-cancel-missing-job",
    tool_ref=CANCEL_JOB_REF,
    arguments={"job_id": missing_job_id},
    target=terminal_job_cancel_target(missing_job_id),
    permissions=("terminal.execute",),
    isolations=(IsolationLevel.IN_PROCESS,),
    idempotency_key="effect-job-cancel-missing-job",
    approval_status=ApprovalStatus.APPROVED,
    approval_id="approval-job-cancel-missing-job",
)
missing_job = raises(
    ToolExecutionError,
    lambda: execute_prepared(
        runtime, missing_job_call, missing_job_facts, missing_job_lease
    ),
)
ok(
    "cancel requires approval existing job and matching owner before reservation",
    missing_approval.status == "blocked"
    and missing_approval.error is not None
    and wrong_owner is not None
    and missing_job is not None
    and query_one(
        "SELECT 1 FROM mc_idempotency WHERE idempotency_key=?",
        ("effect-job-cancel-missing-approval",),
    )
    is None
    and query_one(
        "SELECT 1 FROM mc_idempotency WHERE idempotency_key=?",
        ("effect-job-cancel-wrong-owner",),
    )
    is None,
    (missing_approval, wrong_owner, missing_job),
)

cancel_call, cancel_facts, cancel_lease = prepare_call(
    runtime,
    repository,
    run_id="job-cancel-request",
    tool_ref=CANCEL_JOB_REF,
    arguments={"job_id": cancel_job_id},
    target=cancel_target,
    permissions=("terminal.execute",),
    isolations=(IsolationLevel.IN_PROCESS,),
    idempotency_key="effect-job-cancel-request",
    approval_status=ApprovalStatus.APPROVED,
    approval_id="approval-job-cancel-request",
)
engine.enabled = False
engine.mode = "plan"
cancel_result = execute_prepared(runtime, cancel_call, cancel_facts, cancel_lease)
engine.enabled = True
engine.mode = "ask"
cancel_row = query_one(
    "SELECT * FROM mc_terminal_jobs WHERE job_id=?", (cancel_job_id,)
)
cancel_future = datetime.now(timezone.utc) + timedelta(
    seconds=HEARTBEAT_STALE_SECONDS + 2
)
cancel_stale = TerminalJobRepository().get_job(cancel_job_id, now=cancel_future)
ok(
    "approved cancel stores one request even when legacy launch mode is disabled",
    cancel_result.status == "succeeded"
    and cancel_result.typed_output["request_state"] == "requested"
    and cancel_result.typed_output["state"] == "running"
    and cancel_result.typed_output["cancellation_requested"] is True
    and cancel_result.typed_output["cancellation_acknowledged"] is False
    and cancel_result.receipt_id is not None
    and cancel_row is not None
    and cancel_row["cancel_idempotency_key"] == "effect-job-cancel-request"
    and cancel_row["cancel_requested_by"] == "owner"
    and cancel_row["cancel_requested_at"]
    and cancel_row["cancel_acknowledged_at"] is None
    and cancel_stale["state"] == "unknown"
    and cancel_stale["cancellation_requested"] is True
    and cancel_stale["cancellation_acknowledged"] is False,
    (cancel_result, cancel_stale),
)

second_cancel_call, second_cancel_facts, second_cancel_lease = prepare_call(
    runtime,
    repository,
    run_id="job-cancel-second-key",
    tool_ref=CANCEL_JOB_REF,
    arguments={"job_id": cancel_job_id},
    target=cancel_target,
    permissions=("terminal.execute",),
    isolations=(IsolationLevel.IN_PROCESS,),
    idempotency_key="effect-job-cancel-second-key",
    approval_status=ApprovalStatus.APPROVED,
    approval_id="approval-job-cancel-second-key",
)
second_cancel = execute_prepared(
    runtime, second_cancel_call, second_cancel_facts, second_cancel_lease
)
after_second_cancel = query_one(
    "SELECT * FROM mc_terminal_jobs WHERE job_id=?", (cancel_job_id,)
)
ok(
    "a second approved key reports the existing request without replacing it",
    second_cancel.status == "succeeded"
    and second_cancel.typed_output["request_state"] == "already_requested"
    and after_second_cancel["cancel_idempotency_key"]
    == "effect-job-cancel-request"
    and after_second_cancel["cancel_requested_at"] == cancel_row["cancel_requested_at"]
    and sql_rejected(
        """UPDATE mc_terminal_jobs
           SET cancel_idempotency_key='tampered',cancel_requested_by='other'
           WHERE job_id=?""",
        (cancel_job_id,),
    ),
    second_cancel,
)

cancel_receipts = query_count("mc_action_receipts")
cancel_replay = runtime.execute(
    cancel_call,
    cancel_facts,
    worker_id="cancel-replay-worker",
    lease_token="unused-cancel-replay-token",
    lease_epoch=200,
)
changed_cancel_call = runtime.catalog.prepare_call(
    call_id=cancel_call.call_id,
    run_id=cancel_call.run_id,
    step_id=cancel_call.step_id,
    tool_ref=CANCEL_JOB_REF,
    arguments={"job_id": job_id},
    surface=Surface.AGENT,
    mode="agent",
    candidate_tool_refs=(CANCEL_JOB_REF,),
    idempotency_key=cancel_call.idempotency_key,
    approval_id=cancel_call.approval_id,
)
changed_cancel = raises(
    ActionConflictError,
    lambda: runtime.execute(
        changed_cancel_call,
        replace(
            cancel_facts,
            decision_id="policy-job-cancel-changed-job",
            target=terminal_job_cancel_target(job_id),
        ),
        worker_id="cancel-changed-worker",
        lease_token="unused-cancel-changed-token",
        lease_epoch=201,
    ),
)
changed_cancel_approval_call = runtime.catalog.prepare_call(
    call_id=cancel_call.call_id,
    run_id=cancel_call.run_id,
    step_id=cancel_call.step_id,
    tool_ref=CANCEL_JOB_REF,
    arguments={"job_id": cancel_job_id},
    surface=Surface.AGENT,
    mode="agent",
    candidate_tool_refs=(CANCEL_JOB_REF,),
    idempotency_key=cancel_call.idempotency_key,
    approval_id="approval-job-cancel-changed",
)
changed_cancel_approval = raises(
    ActionConflictError,
    lambda: runtime.execute(
        changed_cancel_approval_call,
        replace(
            cancel_facts,
            decision_id="policy-job-cancel-changed-approval",
            approval_id="approval-job-cancel-changed",
        ),
        worker_id="cancel-changed-approval-worker",
        lease_token="unused-cancel-changed-approval-token",
        lease_epoch=202,
    ),
)
ok(
    "exact cancel replay writes nothing and changed job or approval conflicts",
    cancel_replay == cancel_result
    and changed_cancel is not None
    and changed_cancel_approval is not None
    and query_count("mc_action_receipts") == cancel_receipts
    and query_one(
        "SELECT execution_count FROM mc_idempotency WHERE idempotency_key=?",
        ("effect-job-cancel-request",),
    )["execution_count"]
    == 1,
    (cancel_replay, changed_cancel, changed_cancel_approval),
)

cancel_token = retry_launcher.calls[0][1]
wrong_token_finish = raises(
    TerminalJobError,
    lambda: jobs.finish_cancelled(cancel_job_id, "x" * 32),
)
natural_finish = raises(
    TerminalJobError,
    lambda: jobs.finish_job(
        cancel_job_id,
        cancel_token,
        status="succeeded",
        exit_code=0,
        output="Wait job completed despite cancellation.",
    ),
)
jobs.finish_cancelled(cancel_job_id, cancel_token)
cancelled_public = TerminalJobRepository().get_job(cancel_job_id)
cancelled_stored = query_one(
    "SELECT * FROM mc_terminal_jobs WHERE job_id=?", (cancel_job_id,)
)
ok(
    "only the authenticated worker can acknowledge cancellation and win the finish race",
    wrong_token_finish is not None
    and natural_finish is not None
    and cancelled_public["state"] == "cancelled"
    and cancelled_public["cancellation_requested"] is True
    and cancelled_public["cancellation_acknowledged"] is True
    and cancelled_stored["status"] == "failed"
    and cancelled_stored["error_code"] == "managed_job_cancelled"
    and cancelled_stored["cancel_acknowledged_at"]
    and cancelled_stored["completed_at"],
    (cancelled_public, dict(cancelled_stored)),
)

inactive_call, inactive_facts, inactive_lease = prepare_call(
    runtime,
    repository,
    run_id="job-cancel-already-inactive",
    tool_ref=CANCEL_JOB_REF,
    arguments={"job_id": job_id},
    target=terminal_job_cancel_target(job_id),
    permissions=("terminal.execute",),
    isolations=(IsolationLevel.IN_PROCESS,),
    idempotency_key="effect-job-cancel-already-inactive",
    approval_status=ApprovalStatus.APPROVED,
    approval_id="approval-job-cancel-already-inactive",
)
inactive_result = execute_prepared(runtime, inactive_call, inactive_facts, inactive_lease)
inactive_row = query_one("SELECT * FROM mc_terminal_jobs WHERE job_id=?", (job_id,))
ok(
    "cancelling an already inactive job is a receipted no-op",
    inactive_result.status == "succeeded"
    and inactive_result.typed_output["request_state"] == "already_inactive"
    and inactive_result.typed_output["state"] == "succeeded"
    and inactive_result.typed_output["cancellation_requested"] is False
    and inactive_result.receipt_id is not None
    and inactive_row["cancel_requested_at"] is None
    and inactive_row["cancel_acknowledged_at"] is None,
    inactive_result,
)

uncertain_start_call, uncertain_start_facts, uncertain_start_lease = prepare_call(
    runtime,
    repository,
    run_id="job-cancel-post-commit-start",
    tool_ref=START_JOB_REF,
    arguments={"duration_s": 20},
    target=terminal_job_target(20, ROOT),
    permissions=("terminal.execute",),
    isolations=(IsolationLevel.SUBPROCESS,),
    idempotency_key="effect-job-cancel-post-commit-start",
    approval_status=ApprovalStatus.APPROVED,
    approval_id="approval-job-cancel-post-commit-start",
)
uncertain_start = execute_prepared(
    runtime, uncertain_start_call, uncertain_start_facts, uncertain_start_lease
)
uncertain_cancel_job_id = uncertain_start.typed_output["job_id"]
ok(
    "database guards reject a cancellation request without its reserved action",
    sql_rejected(
        """UPDATE mc_terminal_jobs
           SET cancel_idempotency_key='unreserved-cancel',
               cancel_requested_at='2026-08-11T00:00:00Z',
               cancel_requested_by='owner'
           WHERE job_id=?""",
        (uncertain_cancel_job_id,),
    ),
)
uncertain_jobs = RaiseAfterCancelRepository()
uncertain_cancel_runtime = build_terminal_job_runtime(
    engine=engine,
    job_repository=uncertain_jobs,
    launcher=launcher,
    working_directory=ROOT,
)
uncertain_cancel_call, uncertain_cancel_facts, uncertain_cancel_lease = prepare_call(
    uncertain_cancel_runtime,
    repository,
    run_id="job-cancel-post-commit",
    tool_ref=CANCEL_JOB_REF,
    arguments={"job_id": uncertain_cancel_job_id},
    target=terminal_job_cancel_target(uncertain_cancel_job_id),
    permissions=("terminal.execute",),
    isolations=(IsolationLevel.IN_PROCESS,),
    idempotency_key="effect-job-cancel-post-commit",
    approval_status=ApprovalStatus.APPROVED,
    approval_id="approval-job-cancel-post-commit",
)
uncertain_cancel = execute_prepared(
    uncertain_cancel_runtime,
    uncertain_cancel_call,
    uncertain_cancel_facts,
    uncertain_cancel_lease,
)
uncertain_reconciled = uncertain_cancel_runtime.reconcile_action(
    uncertain_cancel_call, actor="owner"
)
ok(
    "a lost response after the cancel commit stays blocked until durable evidence reconciles it",
    uncertain_cancel.status == "blocked"
    and uncertain_cancel.error is not None
    and uncertain_cancel.error.code == "tool.action_reconciliation_required"
    and uncertain_reconciled.status == "succeeded"
    and uncertain_reconciled.typed_output["request_state"] == "requested"
    and uncertain_reconciled.receipt_id is not None
    and query_one(
        "SELECT status FROM mc_idempotency WHERE idempotency_key=?",
        ("effect-job-cancel-post-commit",),
    )["status"]
    == "completed",
    (uncertain_cancel, uncertain_reconciled),
)
uncertain_token = next(
    token for launched_job_id, token in launcher.calls if launched_job_id == uncertain_cancel_job_id
)
jobs.finish_cancelled(uncertain_cancel_job_id, uncertain_token)

real_runtime = build_terminal_job_runtime(
    engine=engine,
    job_repository=TerminalJobRepository(),
    working_directory=ROOT,
)
real_call, real_facts, real_lease = prepare_call(
    real_runtime,
    repository,
    run_id="job-real-detached",
    tool_ref=START_JOB_REF,
    arguments={"duration_s": 1},
    target=terminal_job_target(1, ROOT),
    permissions=("terminal.execute",),
    isolations=(IsolationLevel.SUBPROCESS,),
    idempotency_key="effect-job-real-detached",
    approval_status=ApprovalStatus.APPROVED,
    approval_id="approval-job-real-detached",
)
real_start = execute_prepared(real_runtime, real_call, real_facts, real_lease)
real_job_id = real_start.typed_output["job_id"]
after_restart = TerminalJobRepository()
deadline = time.monotonic() + 8
real_finished = after_restart.get_job(real_job_id)
while real_finished["state"] not in {"succeeded", "failed"} and time.monotonic() < deadline:
    time.sleep(0.1)
    real_finished = after_restart.get_job(real_job_id)
ok(
    "real detached worker survives app-side object replacement and finishes one bounded wait",
    real_start.status == "succeeded"
    and real_start.receipt_id is not None
    and real_finished["state"] == "succeeded"
    and real_finished["exit_code"] == 0
    and "completed" in real_finished["output"].lower(),
    (real_start, real_finished),
)

real_cancel_start_runtime = build_terminal_job_runtime(
    engine=engine,
    job_repository=TerminalJobRepository(),
    working_directory=ROOT,
)
real_cancel_start_call, real_cancel_start_facts, real_cancel_start_lease = prepare_call(
    real_cancel_start_runtime,
    repository,
    run_id="job-real-cancel-start",
    tool_ref=START_JOB_REF,
    arguments={"duration_s": 5},
    target=terminal_job_target(5, ROOT),
    permissions=("terminal.execute",),
    isolations=(IsolationLevel.SUBPROCESS,),
    idempotency_key="effect-job-real-cancel-start",
    approval_status=ApprovalStatus.APPROVED,
    approval_id="approval-job-real-cancel-start",
)
real_cancel_start = execute_prepared(
    real_cancel_start_runtime,
    real_cancel_start_call,
    real_cancel_start_facts,
    real_cancel_start_lease,
)
real_cancel_job_id = real_cancel_start.typed_output["job_id"]
real_cancel_runtime = build_terminal_job_runtime(
    engine=engine,
    job_repository=TerminalJobRepository(),
    working_directory=ROOT,
)
real_cancel_call, real_cancel_facts, real_cancel_lease = prepare_call(
    real_cancel_runtime,
    repository,
    run_id="job-real-cancel-request",
    tool_ref=CANCEL_JOB_REF,
    arguments={"job_id": real_cancel_job_id},
    target=terminal_job_cancel_target(real_cancel_job_id),
    permissions=("terminal.execute",),
    isolations=(IsolationLevel.IN_PROCESS,),
    idempotency_key="effect-job-real-cancel-request",
    approval_status=ApprovalStatus.APPROVED,
    approval_id="approval-job-real-cancel-request",
)
real_cancel_requested = execute_prepared(
    real_cancel_runtime, real_cancel_call, real_cancel_facts, real_cancel_lease
)
real_cancel_reader = TerminalJobRepository()
real_cancel_deadline = time.monotonic() + 8
real_cancelled = real_cancel_reader.get_job(real_cancel_job_id)
while real_cancelled["state"] != "cancelled" and time.monotonic() < real_cancel_deadline:
    time.sleep(0.05)
    real_cancelled = real_cancel_reader.get_job(real_cancel_job_id)
ok(
    "a real worker observes cancellation after app-side restart and exits itself",
    CANCELLATION_POLL_SECONDS <= 0.25
    and real_cancel_start.status == "succeeded"
    and real_cancel_requested.status == "succeeded"
    and real_cancel_requested.typed_output["request_state"] == "requested"
    and real_cancelled["state"] == "cancelled"
    and real_cancelled["cancellation_acknowledged"] is True
    and real_cancelled["exit_code"] is None
    and "cancel" in real_cancelled["output"].lower(),
    (real_cancel_requested, real_cancelled),
)

persisted_rows = []
for table in (
    "mc_terminal_jobs",
    "mc_idempotency",
    "mc_action_receipts",
    "mc_policy_decisions",
    "mc_run_events",
    "mc_run_steps",
):
    conn = get_connection()
    try:
        persisted_rows.extend(dict(row) for row in conn.execute(f"SELECT * FROM {table}").fetchall())
    finally:
        conn.close()
persisted_json = json.dumps(persisted_rows, sort_keys=True, default=str)
ok(
    "canonical persistence contains hashes and redaction but no raw command directory secret or token",
    "wait 30" not in persisted_json
    and str(ROOT).lower() not in persisted_json.lower()
    and "super-secret-value" not in persisted_json
    and launcher.calls[0][1] not in persisted_json
    and start_result.typed_output["command_sha256"] in persisted_json
    and "[REDACTED]" in persisted_json,
)

terminal_runtime_paths = {
    (ROOT / "core" / "runtime" / name).resolve()
    for name in ("terminal_tools.py", "terminal_jobs.py", "terminal_job_worker.py")
}
live_imports: list[str] = []
for source_root in (ROOT / "core", ROOT / "api"):
    for source_path in source_root.rglob("*.py"):
        if source_path.resolve() in terminal_runtime_paths:
            continue
        source = source_path.read_text(encoding="utf-8", errors="ignore")
        if (
            "core.runtime.terminal_jobs" in source
            or "core.runtime.terminal_job_worker" in source
            or "build_terminal_job_runtime" in source
        ):
            live_imports.append(source_path.relative_to(ROOT).as_posix())
ok("no live caller imports the dormant terminal job runtime", live_imports == [], live_imports)

print(f"\n{PASS}/{PASS} T07 RUN 3B2B TERMINAL JOB CHECKS PASS")

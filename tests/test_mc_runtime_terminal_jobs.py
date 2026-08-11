"""T07 Run 3B2A: dormant restart-safe managed terminal jobs."""
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
    HEARTBEAT_STALE_SECONDS,
    MAX_JOB_OUTPUT_CHARS,
    TerminalJobRepository,
)
from core.runtime.terminal_tools import (  # noqa: E402
    JOB_OUTPUT_REF,
    LIST_JOBS_REF,
    START_JOB_REF,
    build_terminal_job_runtime,
    terminal_job_target,
)
from core.runtime.tool_catalog import ToolCallPreparationError  # noqa: E402
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
                    risk=RiskLevel.HIGH if tool_ref == START_JOB_REF else RiskLevel.NONE,
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
    "migration 009 is additive idempotent and excludes raw command path and PID columns",
    RUNTIME_SCHEMA_VERSION == "mc-runtime-v2-009"
    and RUNTIME_SCHEMA_VERSIONS.count("mc-runtime-v2-009") == 1
    and migrations >= len(RUNTIME_SCHEMA_VERSIONS)
    and {"job_id", "command_sha256", "working_directory_sha256", "heartbeat_at"}.issubset(columns)
    and {"command", "cwd", "pid", "worker_token"}.isdisjoint(columns)
    and query_count("terminal_jobs") == 1,
    columns,
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
manifest_json = json.dumps(contract_to_dict(runtime.catalog.manifest), sort_keys=True)
ok(
    "job catalog exposes only bounded start list and output contracts",
    set(refs) == {START_JOB_REF, LIST_JOBS_REF, JOB_OUTPUT_REF}
    and len(refs) == 3
    and start_spec.side_effect_class is SideEffectClass.REVERSIBLE
    and start_spec.risk is RiskLevel.HIGH
    and start_spec.required_permissions == ("terminal.execute",)
    and start_spec.idempotency_policy == "required"
    and start_spec.isolation == "subprocess"
    and list_spec.side_effect_class is SideEffectClass.NONE
    and output_spec.side_effect_class is SideEffectClass.NONE
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

print(f"\n{PASS}/{PASS} T07 RUN 3B2A TERMINAL JOB CHECKS PASS")

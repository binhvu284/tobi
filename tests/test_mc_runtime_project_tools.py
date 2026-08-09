"""Acceptance checks for #21 T07 Run 1 dormant project tool execution."""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
from dataclasses import replace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TMP = tempfile.mkdtemp(prefix="tobi_t07_run1_")
os.environ["DB_PATH"] = os.path.join(TMP, "agent.db")

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
    PolicyEffect,
    PolicyInput,
    RiskLevel,
    RunRequest,
    RuntimeToolResult,
    Surface,
    TrustClass,
)
from core.runtime.event_store import list_run_events  # noqa: E402
from core.runtime.project_tools import (  # noqa: E402
    CREATE_TASK_REF,
    LIST_PROJECTS_REF,
    build_project_tool_runtime,
)
from core.runtime.repository import RuntimeRepository  # noqa: E402
from core.runtime.state import RunStatus  # noqa: E402
from core.runtime.tool_catalog import ToolCallPreparationError  # noqa: E402
from core.runtime.tool_execution import ToolExecutionError  # noqa: E402


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


def prepare_run(
    repository: RuntimeRepository,
    run_id: str,
    *,
    step_id: str,
    tool_ref: str,
    arguments: dict,
    idempotency_key: str | None = None,
) -> dict:
    recipe = LoopRecipe(
        recipe_id=f"recipe-{run_id}",
        version="1",
        name="Project tool fixture",
        loop_type=LoopType.TURN,
        trigger="owner request",
        objective="Execute one project tool safely",
        stop_condition="typed tool result persisted",
        max_attempts=2,
        max_runtime_s=300,
        max_cost_usd=1.0,
        allowed_tools=(tool_ref,),
    )
    repository.save_loop_recipe(recipe)
    repository.create_run(
        RunRequest(
            request_id=f"request-{run_id}",
            surface=Surface.CHAT,
            owner_id="owner",
            session_id="session-t07-run1",
            mode="chat",
            message="Use one project tool",
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
        run_id,
        RunStatus.ROUTING,
        expected_version=1,
        actor="runtime-test",
    )
    repository.save_plan(
        ExecutionPlan(
            plan_id=f"plan-{run_id}",
            run_id=run_id,
            version="1",
            objective="Execute one project tool safely",
            steps=(
                PlanStep(
                    step_id=step_id,
                    kind="tool",
                    risk=RiskLevel.LOW if idempotency_key else RiskLevel.NONE,
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
        run_id,
        RunStatus.RUNNING,
        expected_version=3,
        actor="runtime-test",
    )
    lease = repository.claim_step(run_id, worker_id=f"worker-{run_id}")
    assert lease is not None
    return lease


def policy_input(
    runtime,
    *,
    decision_id: str,
    run_id: str,
    step_id: str,
    tool_ref: str,
    target: str,
    permissions: tuple[str, ...],
    approval_status: ApprovalStatus = ApprovalStatus.NONE,
    approval_id: str | None = None,
) -> PolicyInput:
    return PolicyInput(
        decision_id=decision_id,
        run_id=run_id,
        step_id=step_id,
        owner_id="owner",
        session_id="session-t07-run1",
        surface=Surface.CHAT,
        mode="chat",
        tool=runtime.catalog.get_spec(tool_ref),
        target=target,
        granted_permissions=permissions,
        trust_class=TrustClass.OWNER_DIRECT,
        certainty=Certainty.KNOWN,
        instruction_authority=True,
        available_isolations=(IsolationLevel.IN_PROCESS,),
        budget_status=BudgetStatus.AVAILABLE,
        approval_mode=ApprovalMode.ASK,
        approval_status=approval_status,
        approval_id=approval_id,
    )


init_database()
conn = get_connection()
project_id = conn.execute(
    "INSERT INTO pm_projects (name,status,size,category,created_by) VALUES (?,?,?,?,?)",
    ("T07 Project", "active", "medium", "Engineering", "owner"),
).lastrowid
conn.commit()
conn.close()

invocations = {"read": 0, "create": 0}
from core.conductor_tools.action_tools import tool_create_task  # noqa: E402
from core.conductor_tools.read_tools import tool_list_projects  # noqa: E402


def counted_list_projects(**arguments):
    invocations["read"] += 1
    return tool_list_projects(**arguments)


def counted_create_task(**arguments):
    invocations["create"] += 1
    return tool_create_task(**arguments)


runtime = build_project_tool_runtime(
    list_projects_tool=counted_list_projects,
    create_task_tool=counted_create_task,
)
manifest_json = json.dumps(runtime.catalog.manifest, default=str, sort_keys=True)
ok(
    "project catalog is bounded available and contains no callable material",
    tuple(entry.tool_ref for entry in runtime.catalog.manifest.entries)
    == (CREATE_TASK_REF, LIST_PROJECTS_REF)
    and "counted_" not in manifest_json
    and "function" not in manifest_json.lower(),
    runtime.catalog.manifest,
)

invalid = raises(
    ToolCallPreparationError,
    lambda: runtime.catalog.prepare_call(
        call_id="call-invalid",
        run_id="run-invalid",
        step_id="read",
        tool_ref=LIST_PROJECTS_REF,
        arguments={"unexpected": "secret-do-not-echo"},
        surface=Surface.CHAT,
        mode="chat",
        candidate_tool_refs=(LIST_PROJECTS_REF,),
    ),
)
not_allowlisted = raises(
    ToolCallPreparationError,
    lambda: runtime.catalog.prepare_call(
        call_id="call-not-allowlisted",
        run_id="run-invalid",
        step_id="read",
        tool_ref=LIST_PROJECTS_REF,
        arguments={},
        surface=Surface.CHAT,
        mode="chat",
        candidate_tool_refs=(CREATE_TASK_REF,),
    ),
)
ok(
    "malformed and non-allowlisted calls fail before invocation without echoing values",
    invalid is not None
    and not_allowlisted is not None
    and "secret-do-not-echo" not in str(invalid)
    and invocations == {"read": 0, "create": 0},
)

repository = RuntimeRepository()
read_lease = prepare_run(
    repository,
    "run-project-read",
    step_id="read",
    tool_ref=LIST_PROJECTS_REF,
    arguments={"status": "active"},
)
read_call = runtime.catalog.prepare_call(
    call_id="call-project-read",
    run_id="run-project-read",
    step_id="read",
    tool_ref=LIST_PROJECTS_REF,
    arguments={"status": "active"},
    surface=Surface.CHAT,
    mode="chat",
    candidate_tool_refs=(LIST_PROJECTS_REF,),
)
read_result = runtime.executor.execute(
    read_call,
    policy_input(
        runtime,
        decision_id="policy-project-read",
        run_id="run-project-read",
        step_id="read",
        tool_ref=LIST_PROJECTS_REF,
        target="projects:collection",
        permissions=("projects.read",),
    ),
    worker_id=read_lease["worker_id"],
    lease_token=read_lease["lease_token"],
    lease_epoch=read_lease["lease_epoch"],
)
ok(
    "real project read returns schema-validated output without an action receipt",
    isinstance(read_result, RuntimeToolResult)
    and read_result.status == "succeeded"
    and read_result.receipt_id is None
    and any(item["id"] == project_id for item in read_result.typed_output["projects"])
    and invocations["read"] == 1
    and query_one(
        "SELECT status FROM mc_run_steps WHERE run_id='run-project-read' AND step_id='read'"
    )["status"]
    == "succeeded"
    and query_one("SELECT COUNT(*) AS count FROM mc_action_receipts")["count"] == 0,
    read_result,
)

denied_lease = prepare_run(
    repository,
    "run-project-denied",
    step_id="create",
    tool_ref=CREATE_TASK_REF,
    arguments={"project_id": project_id, "title": "Must not exist"},
    idempotency_key="effect-project-denied",
)
denied_call = runtime.catalog.prepare_call(
    call_id="call-project-denied",
    run_id="run-project-denied",
    step_id="create",
    tool_ref=CREATE_TASK_REF,
    arguments={"project_id": project_id, "title": "Must not exist"},
    surface=Surface.CHAT,
    mode="chat",
    candidate_tool_refs=(CREATE_TASK_REF,),
    idempotency_key="effect-project-denied",
)
denied_result = runtime.executor.execute(
    denied_call,
    policy_input(
        runtime,
        decision_id="policy-project-denied",
        run_id="run-project-denied",
        step_id="create",
        tool_ref=CREATE_TASK_REF,
        target=f"project:{project_id}",
        permissions=(),
    ),
    worker_id=denied_lease["worker_id"],
    lease_token=denied_lease["lease_token"],
    lease_epoch=denied_lease["lease_epoch"],
)
denied_policy = query_one(
    "SELECT effect FROM mc_policy_decisions WHERE decision_id='policy-project-denied'"
)
ok(
    "recorded central policy denial blocks the mutation before reservation or invocation",
    denied_result.status == "blocked"
    and denied_result.error is not None
    and denied_result.error.code == "tool.policy_denied"
    and denied_policy["effect"] == PolicyEffect.DENY.value
    and invocations["create"] == 0
    and query_one("SELECT COUNT(*) AS count FROM mc_idempotency")["count"] == 0
    and query_one(
        "SELECT COUNT(*) AS count FROM tasks WHERE title='Must not exist'"
    )["count"]
    == 0,
    denied_result,
)

approval_lease = prepare_run(
    repository,
    "run-project-approval",
    step_id="create",
    tool_ref=CREATE_TASK_REF,
    arguments={"project_id": project_id, "title": "Await approval"},
    idempotency_key="effect-project-approval",
)
approval_call = runtime.catalog.prepare_call(
    call_id="call-project-approval",
    run_id="run-project-approval",
    step_id="create",
    tool_ref=CREATE_TASK_REF,
    arguments={"project_id": project_id, "title": "Await approval"},
    surface=Surface.CHAT,
    mode="chat",
    candidate_tool_refs=(CREATE_TASK_REF,),
    idempotency_key="effect-project-approval",
)
approval_result = runtime.executor.execute(
    approval_call,
    policy_input(
        runtime,
        decision_id="policy-project-approval",
        run_id="run-project-approval",
        step_id="create",
        tool_ref=CREATE_TASK_REF,
        target=f"project:{project_id}",
        permissions=("projects.write",),
    ),
    worker_id=approval_lease["worker_id"],
    lease_token=approval_lease["lease_token"],
    lease_epoch=approval_lease["lease_epoch"],
)
ok(
    "unapproved mutation records approval-required and invokes nothing",
    approval_result.status == "blocked"
    and approval_result.error is not None
    and approval_result.error.code == "tool.approval_required"
    and query_one(
        "SELECT effect FROM mc_policy_decisions "
        "WHERE decision_id='policy-project-approval'"
    )["effect"]
    == PolicyEffect.REQUIRE_APPROVAL.value
    and invocations["create"] == 0
    and query_one(
        "SELECT COUNT(*) AS count FROM mc_idempotency "
        "WHERE idempotency_key='effect-project-approval'"
    )["count"]
    == 0
    and query_one(
        "SELECT COUNT(*) AS count FROM tasks WHERE title='Await approval'"
    )["count"]
    == 0,
    approval_result,
)

action_lease = prepare_run(
    repository,
    "run-project-create",
    step_id="create",
    tool_ref=CREATE_TASK_REF,
    arguments={"project_id": project_id, "title": "Create exactly once"},
    idempotency_key="effect-project-create",
)
action_call = runtime.catalog.prepare_call(
    call_id="call-project-create",
    run_id="run-project-create",
    step_id="create",
    tool_ref=CREATE_TASK_REF,
    arguments={"project_id": project_id, "title": "Create exactly once"},
    surface=Surface.CHAT,
    mode="chat",
    candidate_tool_refs=(CREATE_TASK_REF,),
    idempotency_key="effect-project-create",
    approval_id="approval-project-create",
)
approved_input = policy_input(
    runtime,
    decision_id="policy-project-create",
    run_id="run-project-create",
    step_id="create",
    tool_ref=CREATE_TASK_REF,
    target=f"project:{project_id}",
    permissions=("projects.write",),
    approval_status=ApprovalStatus.APPROVED,
    approval_id="approval-project-create",
)
action_result = runtime.executor.execute(
    action_call,
    approved_input,
    worker_id=action_lease["worker_id"],
    lease_token=action_lease["lease_token"],
    lease_epoch=action_lease["lease_epoch"],
)
created_task_id = action_result.typed_output["task_id"]
stored_receipt = query_one(
    "SELECT * FROM mc_action_receipts WHERE receipt_id=?",
    (action_result.receipt_id,),
)
ok(
    "approved task creation records one typed result and immutable project receipt",
    action_result.status == "succeeded"
    and action_result.receipt_id is not None
    and invocations["create"] == 1
    and query_one(
        "SELECT COUNT(*) AS count FROM tasks WHERE id=? AND pm_project_id=?",
        (created_task_id, project_id),
    )["count"]
    == 1
    and stored_receipt["target"] == f"project:{project_id}"
    and stored_receipt["external_ref"] == f"task:{created_task_id}"
    and stored_receipt["approval_ref"] == "approval-project-create"
    and query_one(
        "SELECT status FROM mc_idempotency WHERE idempotency_key='effect-project-create'"
    )["status"]
    == "completed",
    action_result,
)

event_count = len(list_run_events("run-project-create"))
replayed = runtime.executor.execute(
    action_call,
    approved_input,
    worker_id="replay-worker",
    lease_token="unused-for-completed-replay",
    lease_epoch=99,
)
ok(
    "identical retry replays the stored result without a second task or tool invocation",
    replayed == action_result
    and invocations["create"] == 1
    and query_one(
        "SELECT COUNT(*) AS count FROM tasks WHERE title='Create exactly once'"
    )["count"]
    == 1
    and query_one(
        "SELECT COUNT(*) AS count FROM pm_activity WHERE project_id=? AND action_type='task.created'",
        (project_id,),
    )["count"]
    == 1
    and len(list_run_events("run-project-create")) == event_count,
)

changed_call = runtime.catalog.prepare_call(
    call_id="call-project-create",
    run_id="run-project-create",
    step_id="create",
    tool_ref=CREATE_TASK_REF,
    arguments={"project_id": project_id, "title": "Changed content"},
    surface=Surface.CHAT,
    mode="chat",
    candidate_tool_refs=(CREATE_TASK_REF,),
    idempotency_key="effect-project-create",
    approval_id="approval-project-create",
)
changed_input = replace(
    approved_input,
    decision_id="policy-project-create-changed",
)
changed = raises(
    ActionConflictError,
    lambda: runtime.executor.execute(
        changed_call,
        changed_input,
        worker_id="changed-worker",
        lease_token="unused-for-conflict",
        lease_epoch=100,
    ),
)
spoofed = raises(
    ToolExecutionError,
    lambda: runtime.executor.execute(
        action_call,
        replace(
            approved_input,
            decision_id="policy-project-create-spoofed",
            target="project:999999",
        ),
        worker_id="spoof-worker",
        lease_token="unused-for-spoof",
        lease_epoch=101,
    ),
)
ok(
    "changed content conflicts and policy target spoofing fail closed",
    changed is not None
    and spoofed is not None
    and getattr(spoofed, "code", None) == "tool.policy_identity_mismatch"
    and invocations["create"] == 1
    and query_one(
        "SELECT COUNT(*) AS count FROM tasks WHERE title='Changed content'"
    )["count"]
    == 0
    and query_one(
        "SELECT decision_id FROM mc_policy_decisions "
        "WHERE decision_id='policy-project-create-spoofed'"
    )
    is None,
)

conn = get_connection()
try:
    immutable = False
    try:
        conn.execute(
            "UPDATE mc_action_receipts SET effect_summary='changed' WHERE receipt_id=?",
            (action_result.receipt_id,),
        )
        conn.commit()
    except sqlite3.DatabaseError:
        conn.rollback()
        immutable = True
finally:
    conn.close()
ok("project action receipt remains immutable at the database boundary", immutable)

live_imports = []
for path in (ROOT / "core").rglob("*.py"):
    if path.name in {"project_tools.py", "tool_execution.py"}:
        continue
    text = path.read_text(encoding="utf-8", errors="ignore")
    if "core.runtime.project_tools" in text or "core.runtime.tool_execution" in text:
        live_imports.append(str(path.relative_to(ROOT)))
ok("new project execution path remains dormant with no live imports", not live_imports, live_imports)

print(f"\n{PASS}/{PASS} T07 RUN 1 PROJECT TOOL CHECKS PASS")

"""Acceptance checks for #21 T05 Run 2 durable owner approvals."""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TMP = tempfile.mkdtemp(prefix="tobi_t05_run2_")
os.environ["DB_PATH"] = os.path.join(TMP, "agent.db")

from core import owner_flags  # noqa: E402
from core.database import get_connection, init_database  # noqa: E402
from core.runtime.approval import (  # noqa: E402
    ApprovalConflictError,
    ApprovalNotDueError,
    ApprovalService,
)
from core.runtime.contracts import (  # noqa: E402
    ApprovalRequest,
    ApprovalStatus,
    ExecutionPlan,
    LoopPolicy,
    LoopRecipe,
    LoopType,
    OwnerApprovalDecision,
    PlanStep,
    PolicyEffect,
    PolicyInput,
    RiskLevel,
    RunRequest,
    RuntimeToolSpec,
    SideEffectClass,
    Surface,
)
from core.runtime.event_store import list_run_events  # noqa: E402
from core.runtime.policy import PolicyEngine, PolicyLedger  # noqa: E402
from core.runtime.repository import RuntimeRepository  # noqa: E402
from core.runtime.state import RunStatus  # noqa: E402
from core.schema.runtime import (  # noqa: E402
    RUNTIME_SCHEMA_VERSION,
    RUNTIME_SCHEMA_VERSIONS,
    _ensure_runtime_schema,
)


PASS = 0
AUTH_HASH = "a" * 64


def ok(name: str, condition: bool, detail: object = "") -> None:
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


def query_one(sql: str, parameters: tuple = ()) -> sqlite3.Row | None:
    conn = get_connection()
    try:
        return conn.execute(sql, parameters).fetchone()
    finally:
        conn.close()


def material_tool() -> RuntimeToolSpec:
    return RuntimeToolSpec(
        name="send_message",
        namespace="tests",
        version="1",
        description="Send one externally visible message",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        side_effect_class=SideEffectClass.EXTERNAL,
        risk=RiskLevel.HIGH,
        allowed_modes=("agent",),
        allowed_surfaces=(Surface.AGENT,),
    )


def prepare_planned_run(run_id: str) -> tuple[RuntimeRepository, RuntimeToolSpec]:
    repository = RuntimeRepository()
    recipe = LoopRecipe(
        recipe_id=f"recipe-{run_id}",
        version="1",
        name="Approval fixture",
        loop_type=LoopType.TURN,
        trigger="owner request",
        objective="Approve one material action",
        stop_condition="action decision recorded",
        max_attempts=2,
        max_runtime_s=300,
        max_cost_usd=1.0,
    )
    repository.save_loop_recipe(recipe)
    repository.create_run(
        RunRequest(
            request_id=f"request-{run_id}",
            surface=Surface.AGENT,
            owner_id="owner",
            session_id=f"session-{run_id}",
            mode="agent",
            message="Send the approved message",
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
        run_id, RunStatus.ROUTING, expected_version=1, actor="test"
    )
    tool = material_tool()
    repository.save_plan(
        ExecutionPlan(
            plan_id=f"plan-{run_id}",
            run_id=run_id,
            version="1",
            objective="Send one approved message",
            steps=(
                PlanStep(
                    step_id="step-1",
                    kind="tool",
                    tool_name=tool.name,
                    risk=RiskLevel.HIGH,
                ),
            ),
            approval_points=("step-1",),
        ),
        expected_version=2,
        actor="test",
    )
    return repository, tool


def policy_input(
    decision_id: str,
    run_id: str,
    tool: RuntimeToolSpec,
    *,
    approval_status: ApprovalStatus = ApprovalStatus.NONE,
    approval_id: str | None = None,
) -> PolicyInput:
    return PolicyInput(
        decision_id=decision_id,
        run_id=run_id,
        step_id="step-1",
        owner_id="owner",
        session_id=f"session-{run_id}",
        surface=Surface.AGENT,
        mode="agent",
        tool=tool,
        target="external:message",
        approval_status=approval_status,
        approval_id=approval_id,
    )


def record_requirement(run_id: str, tool: RuntimeToolSpec) -> str:
    decision_id = f"policy-require-{run_id}"
    value = policy_input(decision_id, run_id, tool)
    decision = PolicyEngine(policy_id="mc.central", version="1").evaluate(value)
    assert decision.effect is PolicyEffect.REQUIRE_APPROVAL
    PolicyLedger().record(value, decision, actor="policy-test")
    return decision_id


def approval_request(run_id: str, decision_id: str, approval_id: str) -> ApprovalRequest:
    return ApprovalRequest(
        approval_id=approval_id,
        run_id=run_id,
        step_id="step-1",
        policy_decision_id=decision_id,
        owner_id="owner",
        session_id=f"session-{run_id}",
        tool_ref=material_tool().ref,
        expires_at="2026-08-08T01:00:00Z",
    )


def owner_decision(approval_id: str, status: ApprovalStatus) -> OwnerApprovalDecision:
    return OwnerApprovalDecision(
        approval_id=approval_id,
        owner_id="owner",
        session_id=approval_id.replace("approval-", "session-"),
        status=status,
        authentication_method="local_owner_session",
        authentication_evidence_hash=AUTH_HASH,
        authenticated_at="2026-08-08T00:05:00Z",
    )


init_database()
conn = get_connection()
conn.execute("CREATE TABLE legacy_approval_probe (value TEXT)")
conn.execute("INSERT INTO legacy_approval_probe(value) VALUES ('preserved')")
conn.commit()
_ensure_runtime_schema(conn)
_ensure_runtime_schema(conn)
versions = [row[0] for row in conn.execute(
    "SELECT version FROM schema_migrations WHERE version LIKE 'mc-runtime-v2-%'"
)]
tables = {row[0] for row in conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table'"
)}
conn.close()
ok(
    "migration 008 is additive and idempotent",
    RUNTIME_SCHEMA_VERSION == "mc-runtime-v2-008"
    and "mc-runtime-v2-008" in RUNTIME_SCHEMA_VERSIONS
    and versions.count("mc-runtime-v2-008") == 1
    and "mc_run_approvals" in tables
    and query_one("SELECT value FROM legacy_approval_probe")["value"] == "preserved",
)

ok(
    "owner decision contract requires a terminal owner choice and hashed evidence",
    raises(
        ValueError,
        lambda: owner_decision("approval-bad", ApprovalStatus.PENDING),
    )
    and raises(
        ValueError,
        lambda: replace(
            owner_decision("approval-bad", ApprovalStatus.APPROVED),
            authentication_evidence_hash="raw-secret",
        ),
    ),
)

service = ApprovalService()
repository, tool = prepare_planned_run("approve")
requirement_id = record_requirement("approve", tool)
request = approval_request("approve", requirement_id, "approval-approve")
pending = service.request(
    request,
    actor="policy-test",
    timestamp="2026-08-08T00:00:00Z",
)
run = repository.get_run("approve")
events = list_run_events("approve")
ok(
    "approval request and same-run pause are atomic and ordered",
    pending["status"] == "pending"
    and run["status"] == "waiting_approval"
    and run["version"] == 4
    and [event.event_type for event in events[-2:]]
    == ["approval.requested", "run.waiting_approval"],
    {"pending": pending, "run": run, "events": [event.event_type for event in events]},
)

event_count = len(events)
replayed = service.request(
    request,
    actor="policy-test",
    timestamp="2026-08-08T00:00:00Z",
)
ok(
    "identical request replay does not duplicate state or events",
    replayed == pending
    and repository.get_run("approve")["version"] == 4
    and len(list_run_events("approve")) == event_count,
)
ok(
    "changed request content cannot reuse an approval identity",
    raises(
        ApprovalConflictError,
        lambda: service.request(
            replace(request, expires_at="2026-08-08T02:00:00Z"),
            actor="policy-test",
            timestamp="2026-08-08T00:00:00Z",
        ),
    ),
)

mismatched = replace(owner_decision("approval-approve", ApprovalStatus.APPROVED), owner_id="other")
ok(
    "owner and session identity must match the paused run",
    raises(
        ApprovalConflictError,
        lambda: service.decide(
            mismatched,
            actor="owner-auth",
            timestamp="2026-08-08T00:10:00Z",
        ),
    )
    and service.get("approval-approve")["status"] == "pending",
)

approved = service.decide(
    owner_decision("approval-approve", ApprovalStatus.APPROVED),
    actor="owner-auth",
    timestamp="2026-08-08T00:10:00Z",
)
approved_input = service.apply_to_policy(
    policy_input("policy-after-approve", "approve", tool),
    "approval-approve",
)
ok(
    "approval evidence cannot authorize changed action facts",
    raises(
        ApprovalConflictError,
        lambda: service.apply_to_policy(
            replace(
                policy_input("policy-changed-target", "approve", tool),
                target="external:different-message",
            ),
            "approval-approve",
        ),
    ),
)
allow = PolicyEngine(policy_id="mc.central", version="1").evaluate(approved_input)
PolicyLedger().record(approved_input, allow, actor="policy-test")
ok(
    "approved evidence returns to central policy without resuming or executing",
    approved["status"] == "approved"
    and approved_input.approval_status is ApprovalStatus.APPROVED
    and allow.effect is PolicyEffect.ALLOW
    and repository.get_run("approve")["status"] == "waiting_approval"
    and query_one("SELECT COUNT(*) AS count FROM mc_action_receipts")["count"] == 0
    and list_run_events("approve")[-2].event_type == "approval.approved"
    and list_run_events("approve")[-1].event_type == "policy.decided",
)
approved_replay = service.decide(
    owner_decision("approval-approve", ApprovalStatus.APPROVED),
    actor="owner-auth",
    timestamp="2026-08-08T00:20:00Z",
)
ok(
    "same authenticated decision replays but a different decision is rejected",
    approved_replay == approved
    and raises(
        ApprovalConflictError,
        lambda: service.decide(
            owner_decision("approval-approve", ApprovalStatus.REJECTED),
            actor="owner-auth",
            timestamp="2026-08-08T00:20:00Z",
        ),
    ),
)

repository, tool = prepare_planned_run("reject")
requirement_id = record_requirement("reject", tool)
service.request(
    approval_request("reject", requirement_id, "approval-reject"),
    actor="policy-test",
    timestamp="2026-08-08T00:00:00Z",
)
rejected = service.decide(
    owner_decision("approval-reject", ApprovalStatus.REJECTED),
    actor="owner-auth",
    timestamp="2026-08-08T00:10:00Z",
)
rejected_input = service.apply_to_policy(
    policy_input("policy-after-reject", "reject", tool),
    "approval-reject",
)
denied = PolicyEngine(policy_id="mc.central", version="1").evaluate(rejected_input)
ok(
    "rejection denies centrally and cancels the paused run",
    rejected["status"] == "rejected"
    and repository.get_run("reject")["status"] == "cancelled"
    and denied.effect is PolicyEffect.DENY
    and "approval.rejected" in denied.reason_codes
    and [event.event_type for event in list_run_events("reject")[-2:]]
    == ["approval.rejected", "run.cancelled"],
)

repository, tool = prepare_planned_run("expire")
requirement_id = record_requirement("expire", tool)
service.request(
    approval_request("expire", requirement_id, "approval-expire"),
    actor="policy-test",
    timestamp="2026-08-08T00:00:00Z",
)
ok(
    "approval cannot expire before its deadline",
    raises(
        ApprovalNotDueError,
        lambda: service.expire(
            "approval-expire",
            actor="approval-expirer",
            timestamp="2026-08-08T00:30:00Z",
        ),
    )
    and service.get("approval-expire")["status"] == "pending",
)
expired = service.expire(
    "approval-expire",
    actor="approval-expirer",
    timestamp="2026-08-08T01:00:00Z",
)
expired_input = service.apply_to_policy(
    policy_input("policy-after-expire", "expire", tool),
    "approval-expire",
)
expired_denial = PolicyEngine(policy_id="mc.central", version="1").evaluate(expired_input)
ok(
    "expiry fails closed and cancels the paused run",
    expired["status"] == "expired"
    and repository.get_run("expire")["status"] == "cancelled"
    and expired_denial.effect is PolicyEffect.DENY
    and "approval.expired" in expired_denial.reason_codes,
)

repository, tool = prepare_planned_run("race")
requirement_id = record_requirement("race", tool)
service.request(
    approval_request("race", requirement_id, "approval-race"),
    actor="policy-test",
    timestamp="2026-08-08T00:00:00Z",
)


def race_decision(status: ApprovalStatus) -> str:
    try:
        return service.decide(
            owner_decision("approval-race", status),
            actor="owner-auth",
            timestamp="2026-08-08T00:10:00Z",
        )["status"]
    except ApprovalConflictError:
        return "conflict"


with ThreadPoolExecutor(max_workers=2) as pool:
    race_results = list(pool.map(
        race_decision,
        (ApprovalStatus.APPROVED, ApprovalStatus.REJECTED),
    ))
race_events = [
    event.event_type
    for event in list_run_events("race")
    if event.event_type in {"approval.approved", "approval.rejected"}
]
ok(
    "two concurrent owner decisions produce exactly one durable winner",
    race_results.count("conflict") == 1
    and len(race_events) == 1
    and service.get("approval-race")["status"] in {"approved", "rejected"},
    {"results": race_results, "events": race_events},
)

conn = get_connection()
identity_guard = raises(
    sqlite3.IntegrityError,
    lambda: conn.execute(
        "UPDATE mc_run_approvals SET owner_id='other' WHERE approval_id='approval-approve'"
    ),
)
conn.rollback()
delete_guard = raises(
    sqlite3.IntegrityError,
    lambda: conn.execute(
        "DELETE FROM mc_run_approvals WHERE approval_id='approval-approve'"
    ),
)
conn.rollback()
conn.close()
ok("approval identity and history reject mutation or deletion", identity_guard and delete_guard)

ok(
    "central policy rollout remains off and legacy approval callers stay untouched",
    owner_flags.get_bool(owner_flags.RUNTIME_V2_POLICY, False) is False,
)

print(f"\n{PASS}/{PASS} T05 RUN 2 APPROVAL CHECKS PASS")

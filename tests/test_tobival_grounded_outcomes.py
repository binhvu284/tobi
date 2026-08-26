"""Acceptance checks for #34/T04 grounded outcomes and bounded model recovery."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.runtime.contracts import (  # noqa: E402
    ActionReceipt,
    PolicyDecision,
    PolicyEffect,
    RecoveryAction,
    RuntimeToolResult,
)
from core.runtime.grounded_outcomes import (  # noqa: E402
    BoundedModelRecovery,
    GroundedOutcome,
    GroundedOutcomeComposer,
    ModelAttemptEvidence,
    ModelRecoveryResult,
    OutcomeContractError,
    repair_json_object,
)
from core.runtime.typed_resolution import EntityCandidate  # noqa: E402
from core.runtime.workflows import supported_workflow_catalog  # noqa: E402


PASS = 0


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


catalog = supported_workflow_catalog()
composer = GroundedOutcomeComposer()
summary_shapes = {workflow.summary_shape for workflow in catalog.definitions}
ok("all 19 frozen summary shapes have deterministic no-model templates", (
    len(summary_shapes) == 19
    and summary_shapes == composer.supported_summary_shapes
))

project_list = catalog.get("project.list")
read_result = RuntimeToolResult(
    status="succeeded",
    typed_output={
        "count": 2,
        "projects": [
            {"id": 1, "name": "Alpha", "status": "active"},
            {"id": 2, "name": "Beta", "status": "active"},
        ],
    },
    evidence_refs=("projects:collection",),
)
read_outcome = composer.success(project_list, read_result)
ok("a typed read becomes an understandable result without a model", (
    read_outcome.kind == "success"
    and read_outcome.model_required is False
    and ("Count", "2") in read_outcome.facts
    and "2" in read_outcome.render_plain()
    and read_outcome.evidence_refs == ("projects:collection",)
))

task_create = catalog.get("task.create")
action_result = RuntimeToolResult(
    status="succeeded",
    typed_output={"ok": True, "task_id": 44, "title": "Review", "project_id": 1},
    evidence_refs=("task:44",),
    receipt_id="receipt:44",
)
receipt = ActionReceipt(
    receipt_id="receipt:44",
    run_id="run-44",
    step_id="create",
    tool_ref="tobi.projects.create_task@1",
    target="project:1",
    effect_summary="Created task 44 in project 1",
    timestamp="2026-08-26T00:00:00Z",
    external_ref="task:44",
)
action_outcome = composer.success(task_create, action_result, receipt=receipt)
ok("verified action success is grounded in the matching receipt", (
    action_outcome.kind == "success"
    and "Created task 44" in action_outcome.summary
    and {"receipt:44", "task:44", "project:1"} <= set(action_outcome.evidence_refs)
))
ok("action success is impossible without the exact receipt", (
    raises(OutcomeContractError, lambda: composer.success(task_create, action_result))
    and raises(OutcomeContractError, lambda: composer.success(
        task_create,
        action_result,
        receipt=ActionReceipt(
            receipt_id="receipt:other",
            run_id="run-44",
            step_id="create",
            tool_ref="tobi.projects.create_task@1",
            target="project:1",
            effect_summary="Created something",
            timestamp="2026-08-26T00:00:00Z",
        ),
    ))
    and raises(OutcomeContractError, lambda: composer.success(
        task_create, RuntimeToolResult(status="blocked"), receipt=receipt,
    ))
))

denied = PolicyDecision(
    decision_id="policy:deny",
    run_id="run-deny",
    tool_ref="tobi.projects.create_task@1",
    policy_id="central",
    policy_version="1",
    effect=PolicyEffect.DENY,
    reason_codes=("authority.denied",),
    owner_message="This action is not allowed by the current policy.",
    required_approval=False,
    isolation="in_process",
)
refusal = composer.refusal(task_create, denied)
ok("policy refusal repeats the verified reason instead of model prose", (
    refusal.kind == "refusal"
    and refusal.summary == denied.owner_message
    and refusal.evidence_refs == ("policy:deny",)
    and refusal.model_required is False
))

approval = PolicyDecision(
    decision_id="policy:approval",
    run_id="run-approval",
    tool_ref="tobi.projects.create_task@1",
    policy_id="central",
    policy_version="1",
    effect=PolicyEffect.REQUIRE_APPROVAL,
    reason_codes=("approval.required",),
    owner_message="Your approval is required before this task is created.",
    required_approval=True,
    isolation="in_process",
    approval_id="approval:44",
)
approval_outcome = composer.refusal(task_create, approval)
ok("approval-required remains blocked with one actionable recovery", (
    approval_outcome.status == "approval_required"
    and approval_outcome.recovery_actions == (RecoveryAction.APPROVE.value,)
))

choices = tuple(
    EntityCandidate("project", index, f"Project {index}")
    for index in range(1, 7)
)
clarification = composer.clarification(
    task_create, missing_fields=("project_id",), choices=choices,
)
ok("clarification uses plain field names and at most five choices", (
    clarification.kind == "clarification"
    and "project" in clarification.summary.lower()
    and "project_id" not in clarification.summary
    and len(clarification.facts) == 5
))

partial = composer.partial(
    task_create,
    completed_steps=1,
    total_steps=3,
    evidence_refs=("step:1",),
    recovery_actions=(RecoveryAction.RESUME,),
)
ok("partial completion never claims the whole workflow succeeded", (
    partial.kind == "partial"
    and partial.status == "incomplete"
    and "1 of 3" in partial.summary
    and "completed successfully" not in partial.summary.lower()
))

connector = composer.stale_connector(
    catalog.get("connector.status"),
    connector_id="calendar",
    observed_at="2026-08-24T00:00:00Z",
)
ok("stale connector evidence is visible and never called ready", (
    connector.kind == "stale_connector"
    and "stale" in connector.summary.lower()
    and "ready" not in connector.summary.lower()
    and "connector:calendar" in connector.evidence_refs
))


def validate_status(value):
    if not isinstance(value, dict) or value.get("status") != "ok":
        raise ValueError("invalid structured output")
    return {"status": "ok", "count": int(value.get("count", 0))}


recovery = BoundedModelRecovery()
primary = recovery.execute(
    primary=lambda: {"status": "ok", "count": 1},
    primary_model_ref="model:primary",
    validator=validate_status,
)
ok("valid primary structured output needs no recovery", (
    primary.status == "usable" and primary.source == "primary" and len(primary.attempts) == 1
))

repaired = recovery.execute(
    primary=lambda: '```json\n{"status":"ok","count":2}\n```',
    primary_model_ref="model:primary",
    validator=validate_status,
    repair=repair_json_object,
)
ok("deterministic repair recovers fenced JSON without another model", (
    repaired.status == "usable"
    and repaired.source == "repair"
    and repaired.output == {"status": "ok", "count": 2}
))

escalation_calls = []
escalated = recovery.execute(
    primary=lambda: '{"status":',
    primary_model_ref="model:weak",
    validator=validate_status,
    repair=repair_json_object,
    escalation=lambda: escalation_calls.append("called") or {"status": "ok", "count": 3},
    escalation_model_ref="model:reference",
)
ok("failed repair escalates at most once to a configured model", (
    escalated.status == "usable"
    and escalated.source == "escalation"
    and escalation_calls == ["called"]
))

bounded = recovery.execute(
    primary=lambda: '{"status":',
    primary_model_ref="model:weak",
    validator=validate_status,
    repair=repair_json_object,
    escalation=lambda: "still malformed",
    escalation_model_ref="model:reference",
)
ok("unrecoverable malformed output becomes a truthful bounded failure", (
    bounded.status == "bounded_failure"
    and bounded.failure_class == "model.malformed_output"
    and bounded.output is None
))


class APIConnectionError(Exception):
    pass


transport = recovery.execute(
    primary=lambda: (_ for _ in ()).throw(APIConnectionError("secret provider URL")),
    primary_model_ref="model:primary",
    validator=validate_status,
)
provider_outcome = composer.provider_failure(catalog.get("provider.recover"), transport)
serialized_provider = json.dumps(provider_outcome.to_dict(), sort_keys=True)
ok("transport failure is not misreported as weak model quality", (
    transport.failure_class == "provider.unreachable"
    and provider_outcome.kind == "provider_failure"
    and "never reached" in provider_outcome.summary.lower()
    and "weak" not in serialized_provider.lower()
    and "stronger" not in serialized_provider.lower()
    and "secret provider URL" not in serialized_provider
))

recovery_outcome = composer.recovery(
    catalog.get("run.recover"),
    state="paused",
    evidence_refs=("checkpoint:7",),
    recovery_actions=(RecoveryAction.RESUME, RecoveryAction.CANCEL),
)
ok("run recovery is understandable without free-form model output", (
    recovery_outcome.kind == "recovery"
    and recovery_outcome.model_required is False
    and recovery_outcome.recovery_actions == ("resume", "cancel")
))

trace_payload = action_outcome.to_trace_payload()
ok("outcome trace payload contains references but no result body", (
    set(trace_payload) == {"workflow_ref", "result_ref", "evidence_id"}
    and "Review" not in json.dumps(trace_payload, sort_keys=True)
))

ok("public outcome and recovery contracts reject invented states", (
    raises(OutcomeContractError, lambda: GroundedOutcome(
        kind="invented",
        workflow_ref="workflow:test@v1",
        status="verified",
        title="Result",
        summary="Done.",
    ))
    and raises(OutcomeContractError, lambda: GroundedOutcome(
        kind="success",
        workflow_ref="workflow:test@v1",
        status="verified",
        title="Result",
        summary="Done.",
        recovery_actions=("invented",),
    ))
    and raises(OutcomeContractError, lambda: ModelRecoveryResult(
        status="usable",
        source="primary",
        output_json="not-json",
        attempts=(ModelAttemptEvidence("primary", "model:test", "usable"),),
    ))
))

print(f"PASS: {PASS} TOBIval T04 grounded-outcome checks")

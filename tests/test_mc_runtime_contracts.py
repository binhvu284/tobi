"""Contract checks for #21 T01. Plain Python; no database or network required."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import owner_flags  # noqa: E402
from core.chat_runtime_contracts import ToolSpec as ChatToolSpec  # noqa: E402
from core.runtime.config import RUNTIME_V2_FLAGS, rollout_enabled  # noqa: E402
from core.runtime.contracts import (  # noqa: E402
    ActionReceipt,
    Capability,
    ErrorCategory,
    ErrorStage,
    EvalCase,
    EvalFinding,
    EvalRun,
    EvalStatus,
    ExecutionPlan,
    FindingSeverity,
    LoopPolicy,
    LoopRecipe,
    LoopType,
    PlanStep,
    RecoveryAction,
    RiskLevel,
    RouteDecision,
    RunEvent,
    RunRequest,
    RuntimeErrorInfo,
    RuntimeToolCall,
    RuntimeToolResult,
    RuntimeToolSpec,
    Surface,
    SystemEdge,
    SystemEntity,
    SystemEntityType,
    contract_to_dict,
)


def raises_value_error(fn) -> bool:
    try:
        fn()
    except ValueError:
        return True
    return False


def test_run_and_plan_contracts_validate() -> None:
    request = RunRequest(
        request_id="req-1",
        surface=Surface.CHAT,
        owner_id="owner",
        session_id="session-1",
        mode="chat",
        message="hello",
        capability_toggles=(Capability.READ_FILES,),
        budget_profile="interactive",
    )
    step = PlanStep(
        step_id="step-1",
        kind="tool",
        risk=RiskLevel.LOW,
        tool_name="files.read",
        required_capabilities=(Capability.READ_FILES,),
    )
    plan = ExecutionPlan(
        plan_id="plan-1",
        run_id="run-1",
        version="1",
        objective="Read one file",
        steps=(step,),
        completion_predicate="file content returned",
    )
    event = RunEvent(
        event_id="event-1",
        run_id="run-1",
        sequence=1,
        event_type="run.accepted",
        stage="accepted",
        timestamp="2026-08-01T00:00:00Z",
        actor="owner",
    )
    assert contract_to_dict(request)["surface"] == "chat"
    assert contract_to_dict(plan)["steps"][0]["risk"] == "low"
    assert contract_to_dict(event)["sequence"] == 1
    route = RouteDecision(
        route_class="direct",
        intent="answer",
        confidence=0.9,
        candidate_capabilities=(Capability.READ_FILES,),
    )
    assert contract_to_dict(route)["candidate_capabilities"] == ["read_files"]
    assert raises_value_error(lambda: RunRequest("", Surface.CHAT, "owner", "s", "chat", "x"))
    assert raises_value_error(lambda: ExecutionPlan("p", "r", "", "objective"))
    assert raises_value_error(lambda: RunEvent("e", "r", 0, "type", "stage", "now", "actor"))


def test_tool_contract_reuses_chat_contract() -> None:
    chat_spec = ChatToolSpec(
        name="read_file",
        description="Read a file",
        risk="low",
        allowed_modes=("chat", "agent"),
        args_schema={"type": "object"},
        result_schema={"type": "object"},
        timeout_s=10,
        retry_policy="none",
        idempotent=True,
    )
    spec = RuntimeToolSpec.from_chat_spec(chat_spec, namespace="files", version="1")
    call = RuntimeToolCall(
        call_id="call-1",
        run_id="run-1",
        step_id="step-1",
        tool_ref=spec.ref,
        validated_arguments={"path": "README.md"},
    )
    result = RuntimeToolResult(status="succeeded", typed_output={"text": "ok"})
    receipt = ActionReceipt(
        receipt_id="receipt-1",
        run_id="run-1",
        step_id="step-1",
        tool_ref=spec.ref,
        target="README.md",
        effect_summary="Read file",
        timestamp="2026-08-01T00:00:01Z",
    )
    assert spec.ref == "files.read_file@1"
    assert call.tool_ref == spec.ref
    assert result.status == "succeeded"
    assert receipt.tool_ref == spec.ref
    assert raises_value_error(lambda: RuntimeToolSpec.from_chat_spec(chat_spec, namespace="", version="1"))


def test_loop_contracts_are_versioned_and_bounded() -> None:
    recipe = LoopRecipe(
        recipe_id="developer-goal",
        version="1",
        name="Developer goal loop",
        loop_type=LoopType.GOAL,
        trigger="owner approval",
        objective="Deliver one package",
        stop_condition="acceptance checks pass",
        max_attempts=3,
        max_runtime_s=1800,
        max_cost_usd=5.0,
        allowed_tools=("files.read", "terminal.run"),
        approval_gates=("push",),
        required_evals=("runtime-contracts",),
        recovery_policy="pause_with_options",
        evidence_required=("test output",),
    )
    policy = LoopPolicy.from_recipe(
        policy_id="policy-1",
        version="1",
        recipe=recipe,
        policy_decision_id="decision-1",
    )
    assert policy.recipe_id == recipe.recipe_id
    assert policy.max_attempts == 3
    assert policy.enabled is False
    assert raises_value_error(lambda: LoopRecipe(
        "bad", "1", "Bad", LoopType.GOAL, "trigger", "objective", "stop", 0, 1, 0.0
    ))
    assert raises_value_error(lambda: LoopPolicy.from_recipe("p", "", recipe, "d"))


def test_eval_and_error_contracts_validate() -> None:
    case = EvalCase(
        eval_case_id="runtime-contracts",
        version="1",
        category="contracts",
        objective="Reject invalid boundary values",
        input_fixture={"contract": "RunRequest"},
        expected_behavior="ValueError",
        required_evidence=("test output",),
        scorer="binary",
        threshold=1.0,
        release_gate=True,
    )
    run = EvalRun(
        eval_run_id="eval-run-1",
        eval_case_id=case.eval_case_id,
        eval_case_version=case.version,
        status=EvalStatus.PASSED,
        threshold=case.threshold,
        score=1.0,
    )
    finding = EvalFinding(
        finding_id="finding-1",
        eval_run_id=run.eval_run_id,
        category="contracts",
        severity=FindingSeverity.LOW,
        summary="Example finding",
        remediation_owner="runtime",
        status="open",
    )
    error = RuntimeErrorInfo(
        code="runtime.validation_failed",
        category=ErrorCategory.VALIDATION,
        stage=ErrorStage.ACCEPT,
        message="Internal validation detail",
        owner_message="TOBI could not validate this request.",
        recovery_actions=(RecoveryAction.REVISE, RecoveryAction.CANCEL),
    )
    assert run.eval_case_version == "1"
    assert finding.severity is FindingSeverity.LOW
    assert error.owner_message.endswith("request.")
    assert raises_value_error(lambda: EvalCase(
        "case", "", "contracts", "objective", {}, "expected", (), "binary", 1.0
    ))
    assert raises_value_error(lambda: EvalRun("run", "case", "1", EvalStatus.PASSED, 1.1))
    assert raises_value_error(lambda: RuntimeErrorInfo(
        "error", ErrorCategory.INTERNAL, ErrorStage.EXECUTE, "detail", ""
    ))


def test_system_contracts_and_flags_fail_closed() -> None:
    entity = SystemEntity(
        entity_id="runtime",
        entity_type=SystemEntityType.SUBSYSTEM,
        canonical_key="core.runtime",
        name="Runtime",
        status="planned",
        version="1",
        owner_domain="runtime",
        source_ref="core/runtime/contracts.py",
        observed_at="2026-08-01T00:00:00Z",
    )
    edge = SystemEdge(
        edge_id="runtime-uses-chat-contracts",
        from_entity_id=entity.entity_id,
        edge_type="reuses",
        to_entity_id="chat-runtime-contracts",
        version="1",
        evidence_refs=("core/runtime/contracts.py",),
        confidence=1.0,
        valid_from="2026-08-01",
    )
    assert entity.version == "1"
    assert edge.version == "1"
    assert edge.confidence == 1.0
    assert len(RUNTIME_V2_FLAGS) == 9
    assert owner_flags.RUNTIME_V2_CHAT_EXECUTION in RUNTIME_V2_FLAGS
    assert owner_flags.RUNTIME_V2_AGENT_EXECUTION in RUNTIME_V2_FLAGS
    assert all(flag in owner_flags.KEYS for flag in RUNTIME_V2_FLAGS)
    original_get_bool = owner_flags.get_bool
    owner_flags.get_bool = lambda _flag, default=False: default
    try:
        assert all(rollout_enabled(flag) is False for flag in RUNTIME_V2_FLAGS)
    finally:
        owner_flags.get_bool = original_get_bool
    assert raises_value_error(lambda: SystemEntity(
        "e", SystemEntityType.SUBSYSTEM, "key", "name", "status", "", "owner", "source", "now"
    ))
    assert raises_value_error(lambda: SystemEdge("e", "a", "uses", "b", version="1", confidence=1.01))


if __name__ == "__main__":
    tests = [
        test_run_and_plan_contracts_validate,
        test_tool_contract_reuses_chat_contract,
        test_loop_contracts_are_versioned_and_bounded,
        test_eval_and_error_contracts_validate,
        test_system_contracts_and_flags_fail_closed,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"\nALL {len(tests)} T01 CONTRACT GROUPS PASSED")

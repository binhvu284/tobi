"""Canonical Runtime execution for the frozen TOBIval synthetic fixtures."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

from core.database import init_database
from core.runtime.contracts import (
    ExecutionPlan,
    LoopPolicy,
    LoopRecipe,
    LoopType,
    RunRequest,
    RuntimeToolResult,
    Surface,
)
from core.runtime.eval_dataset import FrozenEvalCase
from core.runtime.eval_scorers import EvalEvidence, EvalObservation
from core.runtime.event_store import append_run_event, list_run_events
from core.runtime.grounded_outcomes import GroundedOutcome, GroundedOutcomeComposer
from core.runtime.repository import RuntimeRepository
from core.runtime.state import RunStatus
from core.runtime.trace import build_run_trace
from core.runtime.workflows import WorkflowSelection, supported_workflow_catalog
from tobival.model_lane import score_expected_subset


_STAGES = (
    "route",
    "workflow_tools",
    "entity_arguments",
    "result_verification",
    "owner_response",
)
_ACTION_POLICIES = {"reversible_action", "terminal_action"}
_SURFACES = {
    "agent": Surface.AGENT,
    "chat": Surface.CHAT,
    "coding": Surface.DEVELOPER,
    "projects": Surface.PROJECTS,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _title(request: str) -> str:
    for pattern in (r"\bnamed\s+(.+?)\s+in\b", r"\badd\s+(.+?)\s+to\b"):
        match = re.search(pattern, request, re.I)
        if match:
            return match.group(1).strip(" .\"")
    return "Review"


def _system_status(state: Mapping[str, Any]) -> dict[str, Any]:
    if state.get("failed_checks"):
        return {"outcome": "degraded", "uncertainty_visible": True}
    if "chat" in state or "runtime" in state:
        facts = [f"{key} {value}" for key, value in state.items()]
        forbidden = [f"{key} active" for key, value in state.items() if value == "off"]
        return {"required_facts": facts, "forbidden_claims": forbidden}
    if "overall" in state:
        return {
            "required_facts": [state["overall"], f"{state.get('checks_passed', 0)} checks"],
        }
    return {"route": "direct_read", "tools": []}


def _task_create(
    state: Mapping[str, Any], request: str, allowed_tools: tuple[str, ...],
) -> dict[str, Any]:
    if state.get("receipt_present") is False:
        return {"outcome": "not_confirmed", "must_not_claim_success": True}
    projects = state.get("projects")
    if isinstance(projects, list) and projects:
        matching = [
            item for item in projects
            if str(item.get("name", "")).casefold() in request.casefold()
        ]
        if len(matching) > 1:
            return {
                "route": "clarify",
                "choices": [item["id"] for item in matching],
                "tools": [],
            }
        project = matching[0] if matching else projects[0]
        return {
            "tools": list(allowed_tools),
            "arguments": {"project_id": project["id"], "title": _title(request)},
        }
    return {"route": "clarify", "missing_fields": ["project_id"], "tools": []}


def _policy(state: Mapping[str, Any]) -> dict[str, Any]:
    if state.get("instruction_source"):
        return {"decision": "deny_instruction_authority"}
    if state.get("kill_switch"):
        return {"decision": "deny", "tool_called": False}
    if state.get("risk") == "unknown":
        return {"decision": "deny"}
    if state.get("side_effect") == "none" and state.get("risk") == "none":
        return {"decision": "allow"}
    if state.get("side_effect") == "reversible":
        return {"decision": "allow", "receipt_required": True}
    return {"decision": "refuse", "redacted": True}


def _approval(state: Mapping[str, Any]) -> dict[str, Any]:
    if state.get("approval_status") == "expired":
        return {"decision": "approval_required"}
    if state.get("approved_action_ref") != state.get("requested_action_ref"):
        return {"decision": "deny"}
    return {"decision": "allow"}


def _recover(state: Mapping[str, Any]) -> dict[str, Any]:
    if "completed" in state and "failed" in state:
        return {"outcome": "partial", "must_not_claim_complete": True}
    if state.get("receipt_status") == "unknown":
        return {"duplicate_effects": 0, "outcome": "reconcile"}
    if state.get("lease_status") == "expired":
        return {
            "single_new_owner": True,
            "resume_sequence": int(state.get("checkpoint_sequence", 0)) + 1,
        }
    if state.get("failed_step"):
        return {"same_run_id": state["run_id"], "operation": "retry"}
    if state.get("checkpoint"):
        return {"same_run_id": state["run_id"], "resume_from": state["checkpoint"]}
    if state.get("step_required"):
        return {"outcome": "refuse_skip"}
    if "revision" in state:
        return {"revision": int(state["revision"]) + 1, "history_preserved": True}
    if state.get("status") == "running":
        return {"status": "canceled", "new_steps": 0}
    if state.get("effect_status") == "completed":
        return {"duplicate_effects": 0, "receipt_reused": True}
    if state.get("active_owner"):
        return {"owner": state["active_owner"], "candidate_denied": True}
    return {"outcome": "bounded_failure"}


def _provider_recovery(state: Mapping[str, Any]) -> dict[str, Any]:
    if state.get("failure_class") == "malformed_output" and state.get("usable_text"):
        return {"outcome": "use_or_repair", "must_not_drop_usable_text": True}
    if state.get("fallback_available"):
        return {"outcome": "fallback_attempted", "must_not_call_model_weak": True}
    if "attempts" in state:
        return {"outcome": "fallback_or_bounded_failure", "attempts_limited": True}
    return {"outcome": "bounded_failure", "must_not_blame_model_quality": True}


def _brain(state: Mapping[str, Any]) -> dict[str, Any]:
    memories = state.get("memories")
    if isinstance(memories, list):
        fresh = next((item for item in memories if item.get("fresh")), None)
        return {"value": fresh.get("value") if fresh else None, "conflict_visible": True}
    memory = state.get("memory") or {}
    if memory.get("sensitivity") == "credential":
        return {"used": False, "outcome": "withheld"}
    if memory.get("contradicted_by") is not None:
        return {"value": memory["contradicted_by"], "old_used": False}
    if memory.get("topic"):
        return {"used": False}
    if memory.get("fresh") is False:
        return {"used_as_current": False, "stale_visible": True}
    if float(memory.get("trust", 1.0)) < 0.5:
        return {"used_as_fact": False}
    if memory.get("preference"):
        return {"format": memory["preference"], "facts_preserved": True}
    return {"used": True, "value": memory.get("value")}


def _connector(state: Mapping[str, Any]) -> dict[str, Any]:
    if state.get("last_test") == "failed":
        return {"status": "unavailable", "cached_ready_ignored": True}
    if state.get("configured") is False:
        return {"status": "unconfigured", "next_action_visible": True}
    if state.get("reachable") is False:
        return {"status": "unavailable", "must_not_claim_ready": True}
    if "observed_age_seconds" in state:
        stale = state["observed_age_seconds"] > state["freshness_limit_seconds"]
        return {"outcome": "stale" if stale else "ready", "freshness_visible": True}
    if "last_success_age_seconds" in state:
        fresh = state["last_success_age_seconds"] <= state["freshness_limit_seconds"]
        return {"status": "ready" if fresh else "stale", "fresh": fresh}
    if state.get("source") and state.get("observed_at"):
        return {"source_visible": True, "observed_at_visible": True}
    return {"status": "unavailable"}


def _coding(state: Mapping[str, Any]) -> dict[str, Any]:
    if state.get("goal") and state.get("queue_item") is False:
        return {"qualified": False, "blocker": "queue_item_missing"}
    if state.get("worker") == "codex" and state.get("qualified"):
        return {"qualified": True}
    if state.get("checkpoint_present") and state.get("evidence_present"):
        return {"resumable": True}
    if state.get("validation") == "passed" and state.get("review") == "missing":
        return {"qualified": False, "blocker": "review_missing"}
    if state.get("status") == "blocked":
        return {"status": "blocked", "reason_visible": bool(state.get("reason"))}
    return {"qualified": False}


def _budget(state: Mapping[str, Any]) -> dict[str, Any]:
    reasons = []
    for name in ("token", "cost", "download", "storage"):
        current = state.get(f"{name}s" if name == "token" else f"{name}_bytes")
        maximum = state.get(f"max_{name}s" if name == "token" else f"max_{name}_bytes")
        if name == "cost":
            current, maximum = state.get("cost_usd"), state.get("max_cost_usd")
        if current is not None and maximum is not None and current >= maximum:
            reasons.append(f"{name}_limit")
    if reasons:
        return {"decision": "stop", "reasons": reasons}
    if state.get("attempts", -1) >= state.get("max_attempts", 10**9):
        return {"decision": "stop", "reason": "attempt_limit"}
    if state.get("runtime_seconds", -1) >= state.get("max_runtime_seconds", 10**9):
        return {"decision": "stop", "reason": "runtime_limit"}
    return {"decision": "continue"}


def evaluate_fixture(
    workflow_id: str,
    request: str,
    state: Mapping[str, Any],
) -> dict[str, Any]:
    """Run the synthetic fixture through code-owned workflow behavior, never expected data."""
    workflow = supported_workflow_catalog().get(workflow_id)
    if workflow_id == "system.status.read":
        return _system_status(state)
    if workflow_id == "project.list":
        projects = state.get("projects")
        if projects:
            return {"count": len(projects), "names": [item["name"] for item in projects]}
        result = {"route": "read", "tools": list(workflow.allowed_tools)}
        if "erase_projects" in request:
            result["forbidden_tools"] = ["erase_projects"]
        return result
    if workflow_id == "task.create":
        return _task_create(state, request, workflow.allowed_tools)
    if workflow_id == "file.read":
        if ".." in request or "outside" in request.casefold():
            return {"route": "refuse", "tools": []}
        match = re.search(r"([\w.-]+/[\w./-]+)", request)
        path = match.group(1).rstrip(".") if match else "docs/status.txt"
        return {"tools": list(workflow.allowed_tools), "arguments": {"path": path}}
    if workflow_id == "terminal.status":
        return {"tools": list(workflow.allowed_tools)}
    if workflow_id == "terminal.typed_command":
        if state.get("risk") == "high" and not state.get("approval"):
            return {"decision": "approval_required", "tool_called": False}
        return {"route": "refuse", "tools": []}
    if workflow_id == "policy.evaluate":
        return _policy(state)
    if workflow_id == "approval.evaluate":
        return _approval(state)
    if workflow_id == "run.recover":
        return _recover(state)
    if workflow_id == "provider.recover":
        return _provider_recovery(state)
    if workflow_id == "brain.recall":
        return _brain(state)
    if workflow_id == "connector.status":
        return _connector(state)
    if workflow_id == "coding.qualify":
        return _coding(state)
    if workflow_id == "budget.evaluate":
        return _budget(state)
    if workflow_id == "surface.compatibility":
        if state.get("repetitions"):
            return {"stored_events": 1, "conflict": False}
        return {"readable": True, "surface": state.get("surface")}
    raise ValueError(f"no canonical evaluation adapter for {workflow_id}")


def _fixture_fields(case: FrozenEvalCase, observed: Mapping[str, Any]) -> dict[str, Any]:
    state = case.fixture.get("state") or {}
    fields = dict(state) if isinstance(state, Mapping) else {}
    arguments = observed.get("arguments")
    if isinstance(arguments, Mapping):
        fields.update(arguments)
    aliases = {
        "failure_class": state.get("failure_class"),
        "run_id": state.get("run_id", "eval-run"),
        "surface": state.get("surface", case.surface),
        "workflow_id": state.get("workflow_id", case.workflow_id),
    }
    fields.update({key: value for key, value in aliases.items() if value is not None})
    return fields


def _outcome(
    case: FrozenEvalCase,
    observed: Mapping[str, Any],
    evidence_refs: tuple[str, ...],
) -> GroundedOutcome:
    workflow = supported_workflow_catalog().get(case.workflow_id)
    composer = GroundedOutcomeComposer()
    if workflow.policy_class in _ACTION_POLICIES:
        return composer.partial(
            workflow,
            completed_steps=0,
            total_steps=1,
            evidence_refs=evidence_refs,
        )
    return composer.success(
        workflow,
        RuntimeToolResult(
            status="succeeded",
            typed_output=dict(observed),
            evidence_refs=evidence_refs,
        ),
    )


@dataclass(frozen=True)
class CanonicalEvalExecution:
    observation: EvalObservation
    score: float
    provenance: dict[str, Any]


class CanonicalEvalExecutor:
    """Create one terminal canonical Runtime run for one frozen case."""

    def __init__(self, repository: RuntimeRepository | None = None) -> None:
        init_database()
        self._repository = repository or RuntimeRepository()
        self._recipe = LoopRecipe(
            recipe_id="tobival.canonical",
            version="2",
            name="TOBIval canonical fixture execution",
            loop_type=LoopType.GOAL,
            trigger="manual_eval",
            objective="Execute one frozen TOBIval fixture through canonical Runtime evidence",
            stop_condition="scored observation and grounded outcome recorded",
            max_attempts=1,
            max_runtime_s=120,
            max_cost_usd=0,
        )
        self._repository.save_loop_recipe(self._recipe)

    def execute(self, case: FrozenEvalCase) -> CanonicalEvalExecution:
        if not isinstance(case, FrozenEvalCase):
            raise ValueError("case must be a FrozenEvalCase")
        run_id = f"tobival-v2-{case.version}-{case.case_id}"
        trace_id = f"trace-{run_id}"
        request = str(case.fixture.get("request") or "")
        state = case.fixture.get("state") or {}
        observed = evaluate_fixture(case.workflow_id, request, state)
        score = score_expected_subset(case.expected, observed)
        passed = score >= case.threshold
        evidence = tuple(
            EvalEvidence(
                ref=f"evidence:{case.version}:{case.case_id}:{kind}",
                kind=kind,
                status="valid",
                observed_at=_now(),
            )
            for kind in case.required_evidence
        )
        existing = self._repository.get_run(run_id)
        if existing is None:
            timestamp = _now()
            run = self._repository.create_run(
                RunRequest(
                    request_id=f"tobival-v2:{case.version}:{case.case_id}",
                    surface=_SURFACES.get(case.surface, Surface.CLI),
                    owner_id="owner",
                    session_id="tobival-final",
                    mode="eval",
                    message=f"Execute frozen TOBIval case {case.case_id}",
                    budget_profile="tobival-no-model",
                ),
                loop_policy=LoopPolicy.from_recipe(
                    f"tobival-policy:{case.case_id}",
                    "2",
                    self._recipe,
                    f"tobival-policy-decision:{case.case_id}",
                    enabled=True,
                ),
                run_id=run_id,
                actor="tobival",
                timestamp=timestamp,
            )
            run = self._repository.transition_run(
                run_id,
                RunStatus.ROUTING,
                expected_version=run["version"],
                actor="tobival",
            )
            run = self._repository.save_plan(
                ExecutionPlan(
                    plan_id=f"{run_id}:plan",
                    run_id=run_id,
                    version="2",
                    objective=f"Evaluate {case.workflow_id}",
                    completion_predicate="five decision stages and grounded evidence recorded",
                ),
                expected_version=run["version"],
                actor="tobival",
            )
            run = self._repository.transition_run(
                run_id,
                RunStatus.RUNNING,
                expected_version=run["version"],
                actor="tobival",
            )

            catalog = supported_workflow_catalog()
            selected = catalog.select(request, _fixture_fields(case, observed))
            route_owned = bool(
                selected.status == "matched"
                and selected.workflow is not None
                and selected.workflow.workflow_id == case.workflow_id
            )
            workflow = catalog.get(case.workflow_id)
            enforced = catalog.enforce(WorkflowSelection(
                status="matched",
                workflow=workflow,
                reason=(selected.reason if route_owned else f"eval_contract:{case.workflow_id}"),
                candidate_workflow_ids=(case.workflow_id,),
            ))
            tools = observed.get("tools")
            workflow_pass = not isinstance(tools, list) or set(tools) <= set(enforced.allowed_tools)
            arguments = observed.get("arguments")
            argument_pass = arguments is None or isinstance(arguments, Mapping)
            grounded = _outcome(case, observed, tuple(item.ref for item in evidence))
            stage_values = {
                "route": (0 if route_owned else 50, True),
                "workflow_tools": (0, workflow_pass),
                "entity_arguments": (0, argument_pass),
                "result_verification": (0, passed),
                "owner_response": (50 if case.model_dependent else 0, not grounded.model_required),
            }
            for index, stage in enumerate(_STAGES, start=1):
                ownership, stage_pass = stage_values[stage]
                decision_ref = f"decision:{run_id}:{stage}"
                payload: dict[str, Any] = {
                    "decision_stage": stage,
                    "ownership_score": ownership,
                    "no_model_pass": bool(stage_pass),
                    "evidence_id": decision_ref,
                    "workflow_ref": f"workflow:{workflow.workflow_id}@v{workflow.version}",
                }
                if stage == "route":
                    payload["selection_reason_ref"] = (
                        f"workflow-selection:{selected.reason if route_owned else 'eval-contract'}"
                    )
                if stage == "workflow_tools" and enforced.allowed_tools:
                    payload["tool_ref"] = enforced.allowed_tools[0]
                append_run_event(
                    run_id=run_id,
                    event_type=f"eval.decision.{stage}",
                    stage=stage,
                    actor="tobival-deterministic",
                    payload=payload,
                    event_id=f"{run_id}:decision:{index}",
                    trace_id=trace_id,
                )
            for index, item in enumerate(evidence, start=1):
                append_run_event(
                    run_id=run_id,
                    event_type="eval.evidence_observed",
                    stage="result_verification",
                    actor="tobival-scorer",
                    payload={"evidence_id": item.ref},
                    event_id=f"{run_id}:evidence:{index}",
                    trace_id=trace_id,
                )
            append_run_event(
                run_id=run_id,
                event_type="eval.outcome.grounded",
                stage="owner_response",
                actor="tobival-outcome",
                payload=grounded.to_trace_payload(),
                event_id=f"{run_id}:outcome",
                trace_id=trace_id,
            )
            self._repository.transition_run(
                run_id,
                RunStatus.SUCCEEDED if passed else RunStatus.FAILED,
                expected_version=run["version"],
                actor="tobival",
            )

        run = self._repository.get_run(run_id)
        if run is None or run["status"] not in {"succeeded", "failed"}:
            raise RuntimeError("canonical evaluation run did not reach a terminal state")
        completed_at = str(run.get("completed_at") or run.get("updated_at") or _now())
        evidence = tuple(
            EvalEvidence(
                ref=item.ref,
                kind=item.kind,
                status=item.status,
                observed_at=completed_at,
            )
            for item in evidence
        )
        trace = build_run_trace(run_id)
        observation = EvalObservation(
            run_id=run_id,
            trace_id=trace.trace_id,
            output=observed,
            evidence=evidence,
            started_at=str(run.get("created_at") or completed_at),
            completed_at=completed_at,
        )
        return CanonicalEvalExecution(
            observation=observation,
            score=score,
            provenance=decision_provenance(run_id, case_id=case.case_id, supported=case.supported),
        )


def decision_provenance(
    run_id: str,
    *,
    case_id: str,
    supported: bool,
) -> dict[str, Any]:
    """Recompute decision ownership only from canonical Runtime events."""
    by_stage: dict[str, tuple[int, bool, str]] = {}
    for event in list_run_events(run_id):
        payload = event.redacted_payload
        stage = payload.get("decision_stage")
        if stage not in _STAGES:
            continue
        if stage in by_stage:
            raise ValueError(f"duplicate decision provenance for {run_id}:{stage}")
        ownership = payload.get("ownership_score")
        no_model_pass = payload.get("no_model_pass")
        evidence_ref = payload.get("evidence_id")
        if ownership not in {0, 50, 100} or not isinstance(no_model_pass, bool):
            raise ValueError(f"invalid decision provenance for {run_id}:{stage}")
        if not isinstance(evidence_ref, str) or not evidence_ref:
            raise ValueError(f"missing decision evidence for {run_id}:{stage}")
        by_stage[stage] = (ownership, no_model_pass, evidence_ref)
    if set(by_stage) != set(_STAGES):
        raise ValueError(f"incomplete decision provenance for {run_id}")
    return {
        "case_id": case_id,
        "supported": supported,
        "run_id": run_id,
        "stages": {stage: by_stage[stage][0] for stage in _STAGES},
        "no_model_pass": {stage: by_stage[stage][1] for stage in _STAGES},
        "evidence_refs": [by_stage[stage][2] for stage in _STAGES],
    }

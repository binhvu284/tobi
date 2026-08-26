"""Evidence-grounded no-model outcomes and bounded structured-output recovery."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Mapping

from core.runtime import transport_failure
from core.runtime.contracts import (
    ActionReceipt,
    PolicyDecision,
    PolicyEffect,
    RecoveryAction,
    RuntimeToolResult,
)
from core.runtime.workflows import WorkflowDefinition


OutcomeKind = Literal[
    "success",
    "refusal",
    "clarification",
    "partial",
    "stale_connector",
    "provider_failure",
    "recovery",
]
RecoveryStatus = Literal["usable", "bounded_failure"]
RecoverySource = Literal["primary", "repair", "escalation", "none"]
_OUTCOME_KINDS = {
    "success",
    "refusal",
    "clarification",
    "partial",
    "stale_connector",
    "provider_failure",
    "recovery",
}
_RECOVERY_STATUSES = {"usable", "bounded_failure"}
_RECOVERY_SOURCES = {"primary", "repair", "escalation", "none"}
_ACTION_POLICIES = {"reversible_action", "terminal_action"}
_SHAPE_TITLES = {
    "action_receipt": "Action result",
    "approval_state": "Approval status",
    "budget_state": "Budget status",
    "coding_status": "Coding status",
    "connector_status": "Connector status",
    "file_list": "Files",
    "file_result": "File result",
    "grounded_context": "Remembered context",
    "policy_decision": "Policy decision",
    "project_list": "Projects",
    "provider_recovery": "Provider recovery",
    "recovery_state": "Recovery status",
    "resource_list": "Resources",
    "search_matches": "Search results",
    "status_facts": "System status",
    "surface_status": "Surface status",
    "task_list": "Tasks",
    "terminal_result": "Terminal result",
    "terminal_status": "Terminal status",
}
_SCALAR_FIELDS = {
    "approval_state": ("status", "approval_id"),
    "budget_state": ("status", "remaining_attempts", "remaining_runtime_s"),
    "coding_status": ("status", "qualified", "checkpoint"),
    "connector_status": ("status", "freshness", "observed_at"),
    "file_list": ("count",),
    "file_result": ("name", "path", "size_bytes", "truncated"),
    "grounded_context": ("count", "freshness", "trust"),
    "policy_decision": ("effect", "required_approval"),
    "project_list": ("count",),
    "provider_recovery": ("status", "failure_class"),
    "recovery_state": ("status", "checkpoint"),
    "resource_list": ("count",),
    "search_matches": ("count",),
    "status_facts": ("status", "health", "count", "freshness"),
    "surface_status": ("status", "surface", "run_id"),
    "task_list": ("count",),
    "terminal_result": ("status", "exit_code", "timed_out"),
    "terminal_status": ("status", "mode", "available"),
}
_FIELD_LABELS = {
    "action": "action",
    "action_ref": "action",
    "command": "command",
    "connector_id": "connector",
    "failure_class": "failure type",
    "name": "project name",
    "operation": "recovery action",
    "path": "file path",
    "project_id": "project",
    "query": "search text",
    "resource_id": "resource",
    "risk": "risk level",
    "run_id": "run",
    "surface": "surface",
    "task_id": "task",
    "title": "task title",
    "workflow_id": "workflow",
}
_FENCE_RE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.I | re.S)


class OutcomeContractError(ValueError):
    """Typed evidence is insufficient or inconsistent with an owner-visible claim."""


def _text(value: Any, name: str, *, maximum: int = 240) -> str:
    if not isinstance(value, str) or not value.strip():
        raise OutcomeContractError(f"{name} must be non-empty text")
    return " ".join(value.split())[:maximum]


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _plain_scalar(value: Any) -> str | None:
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, str) and value.strip():
        return " ".join(value.split())[:100]
    return None


def _recovery_values(actions: tuple[RecoveryAction | str, ...]) -> tuple[str, ...]:
    values: list[str] = []
    allowed = {action.value for action in RecoveryAction}
    for action in actions:
        value = action.value if isinstance(action, RecoveryAction) else str(action)
        if value not in allowed:
            raise OutcomeContractError("unknown recovery action")
        if value not in values:
            values.append(value)
    return tuple(values)


@dataclass(frozen=True)
class GroundedOutcome:
    kind: OutcomeKind
    workflow_ref: str
    status: str
    title: str
    summary: str
    facts: tuple[tuple[str, str], ...] = ()
    evidence_refs: tuple[str, ...] = ()
    recovery_actions: tuple[str, ...] = ()
    model_required: bool = False

    def __post_init__(self) -> None:
        if self.kind not in _OUTCOME_KINDS:
            raise OutcomeContractError("unknown outcome kind")
        for name in ("workflow_ref", "status", "title", "summary"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if self.model_required is not False:
            raise OutcomeContractError("grounded outcomes cannot require a model")
        if len(self.facts) > 8 or len(self.evidence_refs) > 20:
            raise OutcomeContractError("outcome evidence must remain bounded")
        normalized_facts: list[tuple[str, str]] = []
        for fact in self.facts:
            if not isinstance(fact, tuple) or len(fact) != 2:
                raise OutcomeContractError("facts must be label/value pairs")
            normalized_facts.append((
                _text(fact[0], "fact label", maximum=80),
                _text(fact[1], "fact value", maximum=120),
            ))
        object.__setattr__(self, "facts", tuple(normalized_facts))
        object.__setattr__(self, "evidence_refs", tuple(
            _text(ref, "evidence_ref", maximum=200) for ref in self.evidence_refs
        ))
        if len(self.recovery_actions) > 5:
            raise OutcomeContractError("outcome recovery actions must remain bounded")
        object.__setattr__(
            self,
            "recovery_actions",
            _recovery_values(self.recovery_actions),
        )

    @property
    def outcome_ref(self) -> str:
        return f"outcome:{_digest(self._payload())}"

    def _payload(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "workflow_ref": self.workflow_ref,
            "status": self.status,
            "title": self.title,
            "summary": self.summary,
            "facts": list(self.facts),
            "evidence_refs": list(self.evidence_refs),
            "recovery_actions": list(self.recovery_actions),
            "model_required": self.model_required,
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self._payload(), "outcome_ref": self.outcome_ref}

    def render_plain(self) -> str:
        lines = [self.title, self.summary]
        lines.extend(f"- {label}: {value}" for label, value in self.facts)
        if self.recovery_actions:
            lines.append(f"Next: {', '.join(self.recovery_actions)}")
        return "\n".join(lines)

    def to_trace_payload(self) -> dict[str, str]:
        evidence_ref = self.evidence_refs[0] if self.evidence_refs else self.outcome_ref
        return {
            "workflow_ref": self.workflow_ref,
            "result_ref": self.outcome_ref,
            "evidence_id": evidence_ref,
        }


@dataclass(frozen=True)
class ModelAttemptEvidence:
    phase: str
    model_ref: str
    status: str
    failure_class: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "phase", _text(self.phase, "phase", maximum=40))
        object.__setattr__(
            self, "model_ref", _text(self.model_ref, "model_ref", maximum=160),
        )
        object.__setattr__(self, "status", _text(self.status, "status", maximum=40))
        if self.failure_class is not None:
            object.__setattr__(
                self,
                "failure_class",
                _text(self.failure_class, "failure_class", maximum=80),
            )


@dataclass(frozen=True)
class ModelRecoveryResult:
    status: RecoveryStatus
    source: RecoverySource
    output_json: str | None = field(default=None, repr=False)
    failure_class: str | None = None
    attempts: tuple[ModelAttemptEvidence, ...] = ()

    def __post_init__(self) -> None:
        if self.status not in _RECOVERY_STATUSES or self.source not in _RECOVERY_SOURCES:
            raise OutcomeContractError("unknown model recovery status or source")
        if not 1 <= len(self.attempts) <= 3:
            raise OutcomeContractError("model recovery needs one to three bounded attempts")
        if any(not isinstance(attempt, ModelAttemptEvidence) for attempt in self.attempts):
            raise OutcomeContractError("model recovery attempts must be typed evidence")
        if self.status == "usable":
            if self.source == "none" or self.output_json is None or self.failure_class is not None:
                raise OutcomeContractError("usable recovery result is inconsistent")
            try:
                parsed = json.loads(self.output_json)
                object.__setattr__(self, "output_json", _canonical_json(parsed))
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                raise OutcomeContractError("usable recovery output must be valid JSON") from exc
        elif self.output_json is not None or self.source != "none" or not self.failure_class:
            raise OutcomeContractError("bounded recovery failure is inconsistent")
        else:
            object.__setattr__(
                self,
                "failure_class",
                _text(self.failure_class, "failure_class", maximum=80),
            )

    @property
    def output(self) -> Any:
        return json.loads(self.output_json) if self.output_json is not None else None


def repair_json_object(raw: Any) -> dict[str, Any]:
    """Deterministically unwrap one JSON object; prose and trailing material stay invalid."""
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("repair input must be text")
    text = raw.strip()
    fenced = _FENCE_RE.fullmatch(text)
    if fenced:
        text = fenced.group(1).strip()
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("repaired output must be one JSON object")
    return parsed


class BoundedModelRecovery:
    """Run one primary attempt, one deterministic repair, and one escalation at most."""

    @staticmethod
    def _usable(
        source: RecoverySource,
        value: Any,
        attempts: list[ModelAttemptEvidence],
    ) -> ModelRecoveryResult:
        try:
            output_json = _canonical_json(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("validated output is not canonical JSON") from exc
        return ModelRecoveryResult(
            status="usable",
            source=source,
            output_json=output_json,
            attempts=tuple(attempts),
        )

    @staticmethod
    def _validate(validator: Callable[[Any], Any], raw: Any) -> Any:
        value = validator(raw)
        _canonical_json(value)
        return value

    @staticmethod
    def _bounded(attempts: list[ModelAttemptEvidence]) -> ModelRecoveryResult:
        malformed = any(
            attempt.status in {"malformed", "repair_failed"}
            for attempt in attempts
        )
        failure_class = "model.malformed_output" if malformed else (
            attempts[-1].failure_class or "provider.unknown"
        )
        return ModelRecoveryResult(
            status="bounded_failure",
            source="none",
            failure_class=failure_class,
            attempts=tuple(attempts),
        )

    def execute(
        self,
        *,
        primary: Callable[[], Any],
        primary_model_ref: str,
        validator: Callable[[Any], Any],
        repair: Callable[[Any], Any] | None = None,
        escalation: Callable[[], Any] | None = None,
        escalation_model_ref: str | None = None,
    ) -> ModelRecoveryResult:
        if not callable(primary) or not callable(validator):
            raise OutcomeContractError("primary and validator must be callable")
        if repair is not None and not callable(repair):
            raise OutcomeContractError("repair must be callable")
        if escalation is not None:
            if not callable(escalation):
                raise OutcomeContractError("escalation must be callable")
            _text(escalation_model_ref, "escalation_model_ref", maximum=160)
        primary_ref = _text(primary_model_ref, "primary_model_ref", maximum=160)
        attempts: list[ModelAttemptEvidence] = []
        raw: Any = None

        try:
            raw = primary()
        except Exception as exc:  # noqa: BLE001
            failure_class = f"provider.{transport_failure.classify(exc)}"
            attempts.append(ModelAttemptEvidence(
                "primary", primary_ref, "transport_failure", failure_class,
            ))
        else:
            try:
                validated = self._validate(validator, raw)
            except Exception:  # noqa: BLE001
                attempts.append(ModelAttemptEvidence(
                    "primary", primary_ref, "malformed", "model.malformed_output",
                ))
            else:
                attempts.append(ModelAttemptEvidence("primary", primary_ref, "usable"))
                return self._usable("primary", validated, attempts)

            if repair is not None:
                try:
                    repaired = repair(raw)
                    validated = self._validate(validator, repaired)
                except Exception:  # noqa: BLE001
                    attempts.append(ModelAttemptEvidence(
                        "repair", primary_ref, "repair_failed", "model.repair_failed",
                    ))
                else:
                    attempts.append(ModelAttemptEvidence("repair", primary_ref, "usable"))
                    return self._usable("repair", validated, attempts)

        if escalation is not None:
            escalation_ref = _text(
                escalation_model_ref, "escalation_model_ref", maximum=160,
            )
            try:
                escalated_raw = escalation()
            except Exception as exc:  # noqa: BLE001
                failure_class = f"provider.{transport_failure.classify(exc)}"
                attempts.append(ModelAttemptEvidence(
                    "escalation", escalation_ref, "transport_failure", failure_class,
                ))
            else:
                try:
                    validated = self._validate(validator, escalated_raw)
                except Exception:  # noqa: BLE001
                    attempts.append(ModelAttemptEvidence(
                        "escalation", escalation_ref, "malformed", "model.malformed_output",
                    ))
                else:
                    attempts.append(ModelAttemptEvidence(
                        "escalation", escalation_ref, "usable",
                    ))
                    return self._usable("escalation", validated, attempts)
        return self._bounded(attempts)


class GroundedOutcomeComposer:
    @property
    def supported_summary_shapes(self) -> frozenset[str]:
        return frozenset(_SHAPE_TITLES)

    @staticmethod
    def _workflow(workflow: WorkflowDefinition) -> tuple[str, str]:
        if not isinstance(workflow, WorkflowDefinition):
            raise OutcomeContractError("workflow must be a WorkflowDefinition")
        try:
            title = _SHAPE_TITLES[workflow.summary_shape]
        except KeyError as exc:
            raise OutcomeContractError("unsupported summary shape") from exc
        return f"workflow:{workflow.workflow_id}@v{workflow.version}", title

    @staticmethod
    def _facts(workflow: WorkflowDefinition, output: Any) -> tuple[tuple[str, str], ...]:
        if not isinstance(output, Mapping):
            return ()
        facts: list[tuple[str, str]] = []
        for field_name in _SCALAR_FIELDS.get(workflow.summary_shape, ()):
            value = _plain_scalar(output.get(field_name))
            if value is not None:
                label = field_name.replace("_", " ").title()
                facts.append((label, value))
        return tuple(facts[:8])

    def success(
        self,
        workflow: WorkflowDefinition,
        result: RuntimeToolResult,
        *,
        receipt: ActionReceipt | None = None,
    ) -> GroundedOutcome:
        workflow_ref, title = self._workflow(workflow)
        if not isinstance(result, RuntimeToolResult) or result.status != "succeeded":
            raise OutcomeContractError("success requires a succeeded typed result")
        action = workflow.policy_class in _ACTION_POLICIES
        evidence = set(result.evidence_refs) | set(result.artifact_refs)
        if action:
            if not isinstance(receipt, ActionReceipt):
                raise OutcomeContractError("action success requires a receipt")
            if not result.receipt_id or result.receipt_id != receipt.receipt_id:
                raise OutcomeContractError("action result and receipt do not match")
            if workflow.allowed_tools and receipt.tool_ref not in workflow.allowed_tools:
                raise OutcomeContractError("receipt tool is outside the workflow")
            evidence.update({receipt.receipt_id, receipt.target})
            evidence.update(
                ref for ref in (
                    receipt.before_ref,
                    receipt.after_ref,
                    receipt.external_ref,
                    receipt.approval_ref,
                )
                if ref
            )
            summary = _text(receipt.effect_summary, "effect_summary")
            if not summary.endswith((".", "!", "?")):
                summary += "."
        else:
            if receipt is not None:
                raise OutcomeContractError("read success cannot use an action receipt")
            if not evidence:
                raise OutcomeContractError("read success requires evidence")
            facts = self._facts(workflow, result.typed_output)
            count = next((value for label, value in facts if label == "Count"), None)
            summary = (
                f"Verified result: {count} item(s)."
                if count is not None
                else f"{title} is verified by typed evidence."
            )
        return GroundedOutcome(
            kind="success",
            workflow_ref=workflow_ref,
            status="verified",
            title=title,
            summary=summary,
            facts=self._facts(workflow, result.typed_output),
            evidence_refs=tuple(sorted(evidence)),
        )

    def refusal(
        self, workflow: WorkflowDefinition, decision: PolicyDecision,
    ) -> GroundedOutcome:
        workflow_ref, _ = self._workflow(workflow)
        if not isinstance(decision, PolicyDecision) or decision.effect is PolicyEffect.ALLOW:
            raise OutcomeContractError("refusal requires a blocking policy decision")
        if workflow.allowed_tools and decision.tool_ref not in workflow.allowed_tools:
            raise OutcomeContractError("policy tool is outside the workflow")
        approval_required = decision.effect is PolicyEffect.REQUIRE_APPROVAL
        return GroundedOutcome(
            kind="refusal",
            workflow_ref=workflow_ref,
            status="approval_required" if approval_required else "denied",
            title="Approval required" if approval_required else "Action refused",
            summary=_text(decision.owner_message, "owner_message"),
            facts=tuple(
                ("Reason", reason.replace("_", " "))
                for reason in decision.reason_codes[:5]
            ),
            evidence_refs=(decision.decision_id,),
            recovery_actions=(RecoveryAction.APPROVE.value,) if approval_required else (),
        )

    def clarification(
        self,
        workflow: WorkflowDefinition,
        *,
        missing_fields: tuple[str, ...],
        choices: tuple[Any, ...] = (),
    ) -> GroundedOutcome:
        workflow_ref, _ = self._workflow(workflow)
        if not missing_fields or any(not isinstance(field, str) for field in missing_fields):
            raise OutcomeContractError("clarification requires missing fields")
        labels = tuple(_FIELD_LABELS.get(field, field.replace("_", " ")) for field in missing_fields)
        facts: list[tuple[str, str]] = []
        for index, choice in enumerate(choices[:5], start=1):
            label = getattr(choice, "label", None)
            ref = getattr(choice, "ref", None)
            if isinstance(choice, Mapping):
                label = choice.get("label")
                ref = choice.get("ref")
            if isinstance(label, str) and label.strip():
                rendered = _text(label, "choice label", maximum=80)
                if isinstance(ref, str) and ref.strip():
                    rendered = f"{rendered} ({_text(ref, 'choice ref', maximum=80)})"
                facts.append((f"Choice {index}", rendered))
        return GroundedOutcome(
            kind="clarification",
            workflow_ref=workflow_ref,
            status="needs_input",
            title="More information needed",
            summary=f"I need {', '.join(labels)} before I can continue.",
            facts=tuple(facts),
            recovery_actions=(RecoveryAction.PROVIDE_INPUT.value,),
        )

    def partial(
        self,
        workflow: WorkflowDefinition,
        *,
        completed_steps: int,
        total_steps: int,
        evidence_refs: tuple[str, ...],
        recovery_actions: tuple[RecoveryAction | str, ...] = (),
    ) -> GroundedOutcome:
        workflow_ref, _ = self._workflow(workflow)
        if (
            isinstance(completed_steps, bool)
            or isinstance(total_steps, bool)
            or not isinstance(completed_steps, int)
            or not isinstance(total_steps, int)
            or completed_steps < 0
            or total_steps < 1
            or completed_steps >= total_steps
            or not evidence_refs
        ):
            raise OutcomeContractError("partial outcome requires incomplete evidenced progress")
        return GroundedOutcome(
            kind="partial",
            workflow_ref=workflow_ref,
            status="incomplete",
            title="Partially complete",
            summary=(
                f"Completed {completed_steps} of {total_steps} steps. "
                "The workflow is not complete yet."
            ),
            facts=(("Completed steps", str(completed_steps)), ("Total steps", str(total_steps))),
            evidence_refs=tuple(sorted(set(evidence_refs))),
            recovery_actions=_recovery_values(recovery_actions),
        )

    def stale_connector(
        self,
        workflow: WorkflowDefinition,
        *,
        connector_id: str,
        observed_at: str,
    ) -> GroundedOutcome:
        workflow_ref, _ = self._workflow(workflow)
        connector = _text(connector_id, "connector_id", maximum=80)
        observed = _text(observed_at, "observed_at", maximum=80)
        return GroundedOutcome(
            kind="stale_connector",
            workflow_ref=workflow_ref,
            status="stale",
            title="Connector evidence is stale",
            summary=(
                f"The latest {connector} check is stale. TOBI cannot confirm current availability."
            ),
            facts=(("Last checked", observed),),
            evidence_refs=(f"connector:{connector}", f"observed-at:{observed}"),
        )

    def provider_failure(
        self,
        workflow: WorkflowDefinition,
        recovery: ModelRecoveryResult,
    ) -> GroundedOutcome:
        workflow_ref, _ = self._workflow(workflow)
        if not isinstance(recovery, ModelRecoveryResult) or recovery.status != "bounded_failure":
            raise OutcomeContractError("provider failure needs a bounded recovery failure")
        failure_class = recovery.failure_class or "provider.unknown"
        if failure_class.startswith("provider."):
            code = failure_class.split(".", 1)[1]
            summary = transport_failure.owner_message(
                code if code in transport_failure.CODES else "unknown"
            )
            status = "unavailable"
            actions = (RecoveryAction.RETRY_STEP.value,)
        else:
            summary = (
                "The model responded, but its structured output could not be repaired or validated."
            )
            status = "malformed_output"
            actions = (RecoveryAction.REVISE.value,)
        evidence = tuple(
            f"model-attempt:{attempt.phase}:{attempt.model_ref}:{attempt.status}"
            for attempt in recovery.attempts
        )
        return GroundedOutcome(
            kind="provider_failure",
            workflow_ref=workflow_ref,
            status=status,
            title="Provider recovery stopped",
            summary=summary,
            facts=(("Failure type", failure_class),),
            evidence_refs=evidence,
            recovery_actions=actions,
        )

    def recovery(
        self,
        workflow: WorkflowDefinition,
        *,
        state: str,
        evidence_refs: tuple[str, ...],
        recovery_actions: tuple[RecoveryAction | str, ...],
    ) -> GroundedOutcome:
        workflow_ref, _ = self._workflow(workflow)
        state_text = _text(state, "state", maximum=80)
        if not evidence_refs:
            raise OutcomeContractError("recovery outcome requires evidence")
        return GroundedOutcome(
            kind="recovery",
            workflow_ref=workflow_ref,
            status=state_text,
            title="Run recovery",
            summary=f"The run is {state_text}. Choose one available recovery action to continue.",
            facts=(("State", state_text),),
            evidence_refs=tuple(sorted(set(evidence_refs))),
            recovery_actions=_recovery_values(recovery_actions),
        )

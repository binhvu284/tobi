"""Dormant canonical execution boundary for typed local tool bindings."""
from __future__ import annotations

import copy
import hashlib
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from core.runtime.actions import ActionLedger
from core.runtime.contracts import (
    ActionReceipt,
    ErrorCategory,
    ErrorStage,
    PolicyEffect,
    PolicyInput,
    RecoveryAction,
    RuntimeErrorInfo,
    RuntimeToolCall,
    RuntimeToolResult,
    SideEffectClass,
    ToolAvailabilityStatus,
)
from core.runtime.control import RuntimeControl
from core.runtime.policy import POLICY_ID, POLICY_VERSION, PolicyEngine, PolicyLedger
from core.runtime.tool_catalog import CanonicalToolCatalog
from core.runtime.tool_registry import ToolValidationError


class ToolExecutionError(ValueError):
    """A typed call was rejected at the private execution boundary."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class ToolExecutionBinding:
    """Private callable metadata that never enters canonical contracts or manifests."""

    tool_ref: str
    invoke: Callable[..., Any] = field(repr=False, compare=False)
    target_from_arguments: Callable[[Mapping[str, Any]], str] = field(
        repr=False, compare=False
    )
    read_failure_owner_message: str = "TOBI could not complete the requested read."
    effect_summary: Callable[[Mapping[str, Any], Any], str] | None = field(
        default=None, repr=False, compare=False
    )
    external_ref: Callable[[Any], str | None] | None = field(
        default=None, repr=False, compare=False
    )
    evidence_refs: Callable[[Any], tuple[str, ...]] | None = field(
        default=None, repr=False, compare=False
    )
    read_output_for_persistence: Callable[[Any], Any] | None = field(
        default=None, repr=False, compare=False
    )
    reported_error_is_not_applied: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.tool_ref, str) or not self.tool_ref.strip():
            raise ValueError("tool_ref must be a non-empty string")
        for name in ("invoke", "target_from_arguments"):
            if not callable(getattr(self, name)):
                raise ValueError(f"{name} must be callable")
        if (
            not isinstance(self.read_failure_owner_message, str)
            or not self.read_failure_owner_message.strip()
        ):
            raise ValueError("read_failure_owner_message must be a non-empty string")
        for name in (
            "effect_summary",
            "external_ref",
            "evidence_refs",
            "read_output_for_persistence",
        ):
            value = getattr(self, name)
            if value is not None and not callable(value):
                raise ValueError(f"{name} must be callable or None")
        if not isinstance(self.reported_error_is_not_applied, bool):
            raise ValueError("reported_error_is_not_applied must be a bool")


def _now_iso(now: datetime | None) -> str:
    value = now or datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _receipt_id(call: RuntimeToolCall) -> str:
    identity = f"{call.idempotency_key}:{call.run_id}:{call.step_id}:{call.call_id}"
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:32]
    return f"receipt-{digest}"


def _stored_result(value: Mapping[str, Any]) -> RuntimeToolResult:
    if value.get("status") != "succeeded" or value.get("error") is not None:
        raise ToolExecutionError("tool.replay_result_invalid")
    return RuntimeToolResult(
        status="succeeded",
        typed_output=copy.deepcopy(value.get("typed_output")),
        evidence_refs=tuple(value.get("evidence_refs") or ()),
        artifact_refs=tuple(value.get("artifact_refs") or ()),
        receipt_id=value.get("receipt_id"),
        retryable=bool(value.get("retryable", False)),
        timing=copy.deepcopy(value.get("timing") or {}),
        cost=copy.deepcopy(value.get("cost") or {}),
    )


def _blocked_result(
    *,
    code: str,
    category: ErrorCategory,
    stage: ErrorStage,
    owner_message: str,
    recovery_actions: tuple[RecoveryAction, ...] = (),
) -> RuntimeToolResult:
    return RuntimeToolResult(
        status="blocked",
        error=RuntimeErrorInfo(
            code=code,
            category=category,
            stage=stage,
            message=code,
            owner_message=owner_message,
            retryable=False,
            recovery_actions=recovery_actions,
        ),
    )


def _failed_result(
    *,
    code: str,
    owner_message: str,
    retryable: bool,
) -> RuntimeToolResult:
    return RuntimeToolResult(
        status="failed",
        retryable=retryable,
        error=RuntimeErrorInfo(
            code=code,
            category=ErrorCategory.EXECUTION,
            stage=ErrorStage.EXECUTE,
            message=code,
            owner_message=owner_message,
            retryable=retryable,
            recovery_actions=(RecoveryAction.RETRY_STEP,) if retryable else (),
        ),
    )


class CanonicalToolExecutor:
    """Execute private bindings only after catalog and central-policy checks pass."""

    def __init__(
        self,
        catalog: CanonicalToolCatalog,
        bindings: Iterable[ToolExecutionBinding],
        *,
        policy_engine: PolicyEngine | None = None,
        policy_ledger: PolicyLedger | None = None,
        action_ledger: ActionLedger | None = None,
        control: RuntimeControl | None = None,
    ) -> None:
        if not isinstance(catalog, CanonicalToolCatalog):
            raise ValueError("catalog must be a CanonicalToolCatalog")
        resolved: dict[str, ToolExecutionBinding] = {}
        for binding in bindings:
            if not isinstance(binding, ToolExecutionBinding):
                raise ValueError("bindings must contain ToolExecutionBinding values")
            if binding.tool_ref in resolved:
                raise ToolExecutionError("tool.duplicate_binding")
            spec = catalog.get_spec(binding.tool_ref)
            mutation = spec.side_effect_class is not SideEffectClass.NONE
            if mutation and (
                spec.idempotency_policy != "required"
                or binding.effect_summary is None
            ):
                raise ToolExecutionError("tool.action_binding_incomplete")
            if not mutation and binding.effect_summary is not None:
                raise ToolExecutionError("tool.read_binding_has_effect")
            if mutation and binding.read_output_for_persistence is not None:
                raise ToolExecutionError("tool.action_binding_has_read_persistence")
            resolved[binding.tool_ref] = binding
        if not resolved:
            raise ValueError("at least one execution binding is required")
        self.catalog = catalog
        self._bindings = resolved
        self._policy_engine = policy_engine or PolicyEngine(
            policy_id=POLICY_ID,
            version=POLICY_VERSION,
        )
        self._policy_ledger = policy_ledger or PolicyLedger()
        self._action_ledger = action_ledger or ActionLedger()
        self._control = control or RuntimeControl()

    def execute(
        self,
        call: RuntimeToolCall,
        policy_input: PolicyInput,
        *,
        worker_id: str,
        lease_token: str,
        lease_epoch: int,
        now: datetime | None = None,
    ) -> RuntimeToolResult:
        if not isinstance(call, RuntimeToolCall):
            raise ToolExecutionError("tool.call_invalid")
        if not isinstance(policy_input, PolicyInput):
            raise ToolExecutionError("tool.policy_input_invalid")
        try:
            binding = self._bindings[call.tool_ref]
        except KeyError as exc:
            raise ToolExecutionError("tool.binding_missing") from exc
        spec = self.catalog.get_spec(call.tool_ref)
        if self.catalog.availability(call.tool_ref).status is not ToolAvailabilityStatus.AVAILABLE:
            raise ToolExecutionError("tool.unavailable")
        validated_arguments = self.catalog.validate_arguments(
            call.tool_ref,
            call.validated_arguments,
        )
        target = binding.target_from_arguments(validated_arguments)
        if not isinstance(target, str) or not target.strip():
            raise ToolExecutionError("tool.target_invalid")
        identity_matches = (
            policy_input.run_id == call.run_id
            and policy_input.step_id == call.step_id
            and policy_input.tool == spec
            and policy_input.target == target
            and policy_input.approval_id == call.approval_id
        )
        if not identity_matches:
            raise ToolExecutionError("tool.policy_identity_mismatch")

        decision = self._policy_engine.evaluate(policy_input)
        self._policy_ledger.record(
            policy_input,
            decision,
            actor="canonical-tool-executor",
            timestamp=_now_iso(now),
        )
        if decision.effect is not PolicyEffect.ALLOW:
            approval = decision.effect is PolicyEffect.REQUIRE_APPROVAL
            return _blocked_result(
                code="tool.approval_required" if approval else "tool.policy_denied",
                category=ErrorCategory.APPROVAL if approval else ErrorCategory.POLICY,
                stage=ErrorStage.APPROVE if approval else ErrorStage.POLICY,
                owner_message=decision.owner_message,
                recovery_actions=(RecoveryAction.PROVIDE_INPUT,) if approval else (),
            )

        if spec.side_effect_class is SideEffectClass.NONE:
            return self._execute_read(
                binding,
                call,
                validated_arguments,
                worker_id=worker_id,
                lease_token=lease_token,
                lease_epoch=lease_epoch,
                now=now,
            )
        return self._execute_action(
            binding,
            call,
            validated_arguments,
            target=target,
            worker_id=worker_id,
            lease_token=lease_token,
            lease_epoch=lease_epoch,
            now=now,
        )

    def _execute_read(
        self,
        binding: ToolExecutionBinding,
        call: RuntimeToolCall,
        arguments: dict[str, Any],
        *,
        worker_id: str,
        lease_token: str,
        lease_epoch: int,
        now: datetime | None,
    ) -> RuntimeToolResult:
        try:
            output = binding.invoke(**copy.deepcopy(arguments))
            if isinstance(output, Mapping) and output.get("error"):
                raise ToolExecutionError("tool.reported_error")
            validated_output = self.catalog.validate_output(call.tool_ref, output)
            persisted_output = validated_output
            if binding.read_output_for_persistence is not None:
                persisted_output = self.catalog.validate_output(
                    call.tool_ref,
                    binding.read_output_for_persistence(copy.deepcopy(validated_output)),
                )
        except Exception:
            result = _failed_result(
                code="tool.read_failed",
                owner_message=binding.read_failure_owner_message,
                retryable=False,
            )
            self._control.record_step_failure(
                call.run_id,
                call.step_id,
                worker_id=worker_id,
                lease_token=lease_token,
                lease_epoch=lease_epoch,
                result=result,
                now=now,
            )
            return result
        evidence_refs = (
            binding.evidence_refs(validated_output) if binding.evidence_refs else ()
        )
        result = RuntimeToolResult(
            status="succeeded",
            typed_output=validated_output,
            evidence_refs=evidence_refs,
        )
        persisted_result = RuntimeToolResult(
            status="succeeded",
            typed_output=persisted_output,
            evidence_refs=evidence_refs,
        )
        self._control.record_step_success(
            call.run_id,
            call.step_id,
            worker_id=worker_id,
            lease_token=lease_token,
            lease_epoch=lease_epoch,
            result=persisted_result,
            now=now,
        )
        return result

    def _execute_action(
        self,
        binding: ToolExecutionBinding,
        call: RuntimeToolCall,
        arguments: dict[str, Any],
        *,
        target: str,
        worker_id: str,
        lease_token: str,
        lease_epoch: int,
        now: datetime | None,
    ) -> RuntimeToolResult:
        if not call.idempotency_key:
            raise ToolExecutionError("tool.idempotency_key_required")
        prepared = self._action_ledger.prepare_action(
            call,
            target=target,
            worker_id=worker_id,
            lease_token=lease_token,
            lease_epoch=lease_epoch,
            now=now,
        )
        if prepared["decision"] == "replay":
            return _stored_result(prepared["result"])
        if prepared["decision"] == "reconcile":
            return _blocked_result(
                code="tool.action_reconciliation_required",
                category=ErrorCategory.CONFLICT,
                stage=ErrorStage.RECOVER,
                owner_message="TOBI needs to verify whether this action already happened.",
                recovery_actions=(RecoveryAction.PROVIDE_INPUT,),
            )

        try:
            output = binding.invoke(**copy.deepcopy(arguments))
        except Exception:
            self._mark_unknown(call, worker_id=worker_id, now=now)
            return _blocked_result(
                code="tool.action_reconciliation_required",
                category=ErrorCategory.EXECUTION,
                stage=ErrorStage.RECOVER,
                owner_message="TOBI needs to verify whether this action already happened.",
                recovery_actions=(RecoveryAction.PROVIDE_INPUT,),
            )
        if isinstance(output, Mapping) and output.get("error"):
            if binding.reported_error_is_not_applied:
                self._action_ledger.reconcile_action(
                    call.idempotency_key,
                    outcome="not_applied",
                    actor=worker_id,
                    summary="The project tool rejected the action before applying it",
                    now=now,
                )
                return _failed_result(
                    code="tool.action_not_applied",
                    owner_message="TOBI could not apply the requested project change.",
                    retryable=True,
                )
            self._mark_unknown(call, worker_id=worker_id, now=now)
            return _blocked_result(
                code="tool.action_reconciliation_required",
                category=ErrorCategory.EXECUTION,
                stage=ErrorStage.RECOVER,
                owner_message="TOBI needs to verify whether this action already happened.",
                recovery_actions=(RecoveryAction.PROVIDE_INPUT,),
            )
        try:
            validated_output = self.catalog.validate_output(call.tool_ref, output)
        except ToolValidationError:
            self._mark_unknown(call, worker_id=worker_id, now=now)
            return _blocked_result(
                code="tool.action_reconciliation_required",
                category=ErrorCategory.VALIDATION,
                stage=ErrorStage.RECOVER,
                owner_message="TOBI needs to verify an action whose result was invalid.",
                recovery_actions=(RecoveryAction.PROVIDE_INPUT,),
            )

        receipt_id = _receipt_id(call)
        evidence_refs = (
            binding.evidence_refs(validated_output) if binding.evidence_refs else ()
        )
        receipt = ActionReceipt(
            receipt_id=receipt_id,
            run_id=call.run_id,
            step_id=call.step_id,
            tool_ref=call.tool_ref,
            target=target,
            effect_summary=binding.effect_summary(arguments, validated_output),
            external_ref=(
                binding.external_ref(validated_output) if binding.external_ref else None
            ),
            approval_ref=call.approval_id,
            timestamp=_now_iso(now),
        )
        result = RuntimeToolResult(
            status="succeeded",
            typed_output=validated_output,
            evidence_refs=evidence_refs,
            receipt_id=receipt_id,
        )
        try:
            self._control.record_step_success(
                call.run_id,
                call.step_id,
                worker_id=worker_id,
                lease_token=lease_token,
                lease_epoch=lease_epoch,
                result=result,
                receipt=receipt,
                now=now,
            )
        except Exception:
            self._mark_unknown(call, worker_id=worker_id, now=now)
            raise
        return result

    def _mark_unknown(
        self,
        call: RuntimeToolCall,
        *,
        worker_id: str,
        now: datetime | None,
    ) -> None:
        self._action_ledger.reconcile_action(
            call.idempotency_key or "",
            outcome="unknown",
            actor=worker_id,
            summary="The tool result was not safely recorded after invocation",
            now=now,
        )

"""Dormant deterministic policy decisions and immutable audit persistence."""
from __future__ import annotations

import sqlite3
from typing import Any

from core.database import get_connection
from core.runtime.contracts import (
    ApprovalMode,
    ApprovalStatus,
    BudgetStatus,
    Certainty,
    CredentialStatus,
    IsolationLevel,
    PolicyDecision,
    PolicyEffect,
    PolicyInput,
    RiskLevel,
    SideEffectClass,
    TrustClass,
    contract_to_dict,
)
from core.runtime.event_store import _append_run_event, redact_payload
from core.runtime.repository import (
    RunNotFoundError,
    _canonical_json,
    _hash,
    _load_json,
    _now,
)
from core.schema.runtime import _ensure_runtime_schema


class PolicyConflictError(ValueError):
    """A stable policy decision identity was reused for different content."""


POLICY_ID = "mc.central"
POLICY_VERSION = "1"


def _require_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _ordered_unique(values: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


class PolicyEngine:
    """Evaluate typed facts without reading state or causing side effects."""

    def __init__(self, *, policy_id: str, version: str) -> None:
        self.policy_id = _require_text(policy_id, "policy_id")
        self.version = _require_text(version, "version")
        if (self.policy_id, self.version) != (POLICY_ID, POLICY_VERSION):
            raise ValueError("unsupported central policy version")

    def evaluate(self, policy_input: PolicyInput) -> PolicyDecision:
        if not isinstance(policy_input, PolicyInput):
            raise ValueError("policy_input must be a PolicyInput")

        tool = policy_input.tool
        blockers: list[str] = []
        if policy_input.active_kill_switches:
            blockers.append("kill_switch.active")
        if policy_input.surface not in tool.allowed_surfaces:
            blockers.append("surface.denied")
        if policy_input.mode not in tool.allowed_modes:
            blockers.append("mode.denied")
        if set(tool.required_permissions) - set(policy_input.granted_permissions):
            blockers.append("permission.missing")
        if set(tool.required_integrations) - set(policy_input.available_integrations):
            blockers.append("integration.missing")

        if tool.credential_purpose:
            credential_reason = {
                CredentialStatus.NOT_REQUIRED: "credential.missing",
                CredentialStatus.MISSING: "credential.missing",
                CredentialStatus.LOCKED: "credential.locked",
                CredentialStatus.PURPOSE_MISMATCH: "credential.purpose_mismatch",
            }.get(policy_input.credential_status)
            if credential_reason:
                blockers.append(credential_reason)
        elif policy_input.credential_status not in {
            CredentialStatus.NOT_REQUIRED,
            CredentialStatus.AVAILABLE,
        }:
            blockers.append("credential.unexpected")

        if (
            policy_input.instruction_authority
            and policy_input.trust_class
            not in {TrustClass.OWNER_DIRECT, TrustClass.SYSTEM_VERIFIED}
        ):
            blockers.append("trust.instruction_authority")
        if policy_input.certainty is Certainty.CONTRADICTED:
            blockers.append("certainty.contradicted")

        try:
            required_isolation = IsolationLevel(tool.isolation)
        except ValueError:
            required_isolation = None
            blockers.append("isolation.unsupported")
        if (
            required_isolation is not None
            and required_isolation not in policy_input.available_isolations
        ):
            blockers.append("isolation.unavailable")

        if policy_input.budget_status is BudgetStatus.EXHAUSTED:
            blockers.append("budget.exhausted")
        elif policy_input.budget_status is BudgetStatus.UNKNOWN:
            blockers.append("budget.unknown")
        if policy_input.approval_status is ApprovalStatus.REJECTED:
            blockers.append("approval.rejected")

        if blockers:
            return self._decision(
                policy_input,
                PolicyEffect.DENY,
                blockers,
                "TOBI cannot run this action because required policy checks did not pass.",
            )

        mutation = tool.side_effect_class is not SideEffectClass.NONE
        approval_reasons: list[str] = []
        if tool.risk in {RiskLevel.HIGH, RiskLevel.CRITICAL}:
            approval_reasons.append(f"risk.{tool.risk.value}")
        if tool.side_effect_class in {
            SideEffectClass.IRREVERSIBLE,
            SideEffectClass.EXTERNAL,
        }:
            approval_reasons.append(f"side_effect.{tool.side_effect_class.value}")
        if mutation and policy_input.approval_mode is ApprovalMode.ASK:
            approval_reasons.append("approval.mode.ask")
        if mutation and policy_input.certainty is Certainty.INFERRED:
            approval_reasons.append("certainty.inferred")
        if mutation and policy_input.certainty is Certainty.STALE:
            approval_reasons.append("certainty.stale")
        if policy_input.approval_status is ApprovalStatus.PENDING:
            approval_reasons.append("approval.pending")

        if approval_reasons and policy_input.approval_status is not ApprovalStatus.APPROVED:
            return self._decision(
                policy_input,
                PolicyEffect.REQUIRE_APPROVAL,
                approval_reasons,
                "This action needs your approval before TOBI can run it.",
                required_approval=True,
            )
        if approval_reasons:
            return self._decision(
                policy_input,
                PolicyEffect.ALLOW,
                [*approval_reasons, "approval.satisfied"],
                "Policy allows this approved action.",
            )
        return self._decision(
            policy_input,
            PolicyEffect.ALLOW,
            ["policy.allowed"],
            "Policy allows this action.",
        )

    def _decision(
        self,
        policy_input: PolicyInput,
        effect: PolicyEffect,
        reasons: list[str],
        owner_message: str,
        *,
        required_approval: bool = False,
    ) -> PolicyDecision:
        return PolicyDecision(
            decision_id=policy_input.decision_id,
            run_id=policy_input.run_id,
            step_id=policy_input.step_id,
            tool_ref=policy_input.tool.ref,
            policy_id=self.policy_id,
            policy_version=self.version,
            effect=effect,
            reason_codes=_ordered_unique(reasons),
            owner_message=owner_message,
            required_approval=required_approval,
            approval_id=policy_input.approval_id,
            credential_purpose=policy_input.tool.credential_purpose,
            isolation=policy_input.tool.isolation,
            contract_version=policy_input.contract_version,
        )


def _decision_from_row(row: sqlite3.Row) -> dict[str, Any]:
    stored = dict(row)
    stored["input"] = _load_json(stored.pop("input_json"), {})
    stored["decision"] = _load_json(stored.pop("decision_json"), {})
    return stored


class PolicyLedger:
    """Persist each versioned decision and its ordered run event atomically."""

    def record(
        self,
        policy_input: PolicyInput,
        decision: PolicyDecision,
        *,
        actor: str,
        timestamp: str | None = None,
        event_id: str | None = None,
    ) -> dict[str, Any]:
        if not isinstance(policy_input, PolicyInput):
            raise ValueError("policy_input must be a PolicyInput")
        if not isinstance(decision, PolicyDecision):
            raise ValueError("decision must be a PolicyDecision")
        _require_text(actor, "actor")
        identity_matches = (
            decision.decision_id == policy_input.decision_id
            and decision.run_id == policy_input.run_id
            and decision.step_id == policy_input.step_id
            and decision.tool_ref == policy_input.tool.ref
            and decision.contract_version == policy_input.contract_version
        )
        if not identity_matches:
            raise PolicyConflictError("policy input and decision identities do not match")
        expected = PolicyEngine(
            policy_id=decision.policy_id,
            version=decision.policy_version,
        ).evaluate(policy_input)
        if decision != expected:
            raise PolicyConflictError("decision was not produced by the central policy engine")

        input_contract = contract_to_dict(policy_input)
        decision_contract = contract_to_dict(decision)
        input_hash = _hash(input_contract)
        decision_hash = _hash(decision_contract)
        stored_input = redact_payload(input_contract)
        stored_decision = redact_payload(decision_contract)
        timestamp = timestamp or _now()
        conn = get_connection()
        try:
            _ensure_runtime_schema(conn)
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT * FROM mc_policy_decisions WHERE decision_id=?",
                (decision.decision_id,),
            ).fetchone()
            if existing is not None:
                if not (
                    existing["input_hash"] == input_hash
                    and existing["decision_hash"] == decision_hash
                    and existing["actor"] == actor
                ):
                    raise PolicyConflictError(
                        f"decision_id {decision.decision_id!r} already has different content"
                    )
                conn.commit()
                return _decision_from_row(existing)

            run = conn.execute(
                "SELECT run_id FROM mc_runs WHERE run_id=?", (decision.run_id,)
            ).fetchone()
            if run is None:
                raise RunNotFoundError(decision.run_id)
            conn.execute(
                """INSERT INTO mc_policy_decisions (
                    decision_id,run_id,step_id,tool_ref,policy_id,policy_version,
                    effect,input_json,input_hash,decision_json,decision_hash,
                    actor,contract_version,created_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    decision.decision_id,
                    decision.run_id,
                    decision.step_id,
                    decision.tool_ref,
                    decision.policy_id,
                    decision.policy_version,
                    decision.effect.value,
                    _canonical_json(stored_input),
                    input_hash,
                    _canonical_json(stored_decision),
                    decision_hash,
                    actor,
                    decision.contract_version,
                    timestamp,
                ),
            )
            _append_run_event(
                conn,
                run_id=decision.run_id,
                event_type="policy.decided",
                stage="policy",
                actor=actor,
                payload={
                    "decision_id": decision.decision_id,
                    "step_id": decision.step_id,
                    "tool_ref": decision.tool_ref,
                    "policy_id": decision.policy_id,
                    "policy_version": decision.policy_version,
                    "effect": decision.effect.value,
                    "reason_codes": list(decision.reason_codes),
                    "required_approval": decision.required_approval,
                    "approval_id": decision.approval_id,
                },
                event_id=event_id or f"{decision.decision_id}:policy.decided",
                timestamp=timestamp,
                contract_version=decision.contract_version,
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM mc_policy_decisions WHERE decision_id=?",
                (decision.decision_id,),
            ).fetchone()
            return _decision_from_row(row)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get(self, decision_id: str) -> dict[str, Any] | None:
        _require_text(decision_id, "decision_id")
        conn = get_connection()
        try:
            _ensure_runtime_schema(conn)
            row = conn.execute(
                "SELECT * FROM mc_policy_decisions WHERE decision_id=?", (decision_id,)
            ).fetchone()
            return _decision_from_row(row) if row is not None else None
        finally:
            conn.close()

    def list_for_run(self, run_id: str) -> list[dict[str, Any]]:
        _require_text(run_id, "run_id")
        conn = get_connection()
        try:
            _ensure_runtime_schema(conn)
            rows = conn.execute(
                "SELECT * FROM mc_policy_decisions WHERE run_id=? ORDER BY created_at,decision_id",
                (run_id,),
            ).fetchall()
            return [_decision_from_row(row) for row in rows]
        finally:
            conn.close()

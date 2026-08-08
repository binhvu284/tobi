"""Durable, dormant owner approvals for Mission Control Runtime V2."""
from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any

from core.database import get_connection
from core.runtime.contracts import (
    ApprovalRequest,
    ApprovalStatus,
    OwnerApprovalDecision,
    PolicyInput,
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
from core.runtime.state import RunStatus, require_transition
from core.schema.runtime import _ensure_runtime_schema


class ApprovalConflictError(ValueError):
    """An approval identity, owner, action, or decision no longer matches."""


class ApprovalNotFoundError(LookupError):
    """The requested Runtime V2 approval does not exist."""


class ApprovalNotDueError(ValueError):
    """An approval expiry was requested before its deadline."""


def _require_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _parse_timestamp(value: str, name: str) -> datetime:
    _require_text(value, name)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{name} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{name} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _approval_from_row(row: sqlite3.Row) -> dict[str, Any]:
    approval = dict(row)
    approval["request"] = _load_json(approval.pop("request_json"), {})
    approval["response"] = _load_json(approval.pop("response_json"), None)
    return approval


class ApprovalService:
    """Persist approval evidence and run state without invoking any tool."""

    def request(
        self,
        request: ApprovalRequest,
        *,
        actor: str,
        timestamp: str | None = None,
    ) -> dict[str, Any]:
        if not isinstance(request, ApprovalRequest):
            raise ValueError("request must be an ApprovalRequest")
        _require_text(actor, "actor")
        timestamp = timestamp or _now()
        requested_at = _parse_timestamp(timestamp, "timestamp")
        expires_at = _parse_timestamp(request.expires_at, "expires_at")
        if expires_at <= requested_at:
            raise ApprovalConflictError("approval must expire after it is requested")

        request_contract = contract_to_dict(request)
        request_hash = _hash(request_contract)
        stored_request = redact_payload(request_contract)
        conn = get_connection()
        try:
            _ensure_runtime_schema(conn)
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT * FROM mc_run_approvals WHERE approval_id=?",
                (request.approval_id,),
            ).fetchone()
            if existing is not None:
                if not (
                    existing["request_hash"] == request_hash
                    and existing["requested_by"] == actor
                ):
                    raise ApprovalConflictError(
                        f"approval_id {request.approval_id!r} already has different content"
                    )
                conn.commit()
                return _approval_from_row(existing)

            duplicate = conn.execute(
                "SELECT approval_id FROM mc_run_approvals WHERE policy_decision_id=?",
                (request.policy_decision_id,),
            ).fetchone()
            if duplicate is not None:
                raise ApprovalConflictError(
                    "the policy decision already has a different approval request"
                )

            policy = conn.execute(
                "SELECT * FROM mc_policy_decisions WHERE decision_id=?",
                (request.policy_decision_id,),
            ).fetchone()
            if policy is None:
                raise ApprovalConflictError("approval requires a recorded policy decision")
            policy_input = _load_json(policy["input_json"], {})
            if not (
                policy["effect"] == "require_approval"
                and policy["run_id"] == request.run_id
                and policy["step_id"] == request.step_id
                and policy["tool_ref"] == request.tool_ref
                and policy_input.get("owner_id") == request.owner_id
                and policy_input.get("session_id") == request.session_id
            ):
                raise ApprovalConflictError(
                    "approval request does not match its central policy decision"
                )

            run = conn.execute(
                "SELECT * FROM mc_runs WHERE run_id=?", (request.run_id,)
            ).fetchone()
            if run is None:
                raise RunNotFoundError(request.run_id)
            if not (
                run["owner_id"] == request.owner_id
                and run["session_id"] == request.session_id
            ):
                raise ApprovalConflictError("approval owner does not match the run")
            step = conn.execute(
                "SELECT 1 FROM mc_run_steps WHERE run_id=? AND step_id=?",
                (request.run_id, request.step_id),
            ).fetchone()
            if step is None:
                raise ApprovalConflictError("approval step does not exist on the run")
            require_transition(run["status"], RunStatus.WAITING_APPROVAL)

            conn.execute(
                """INSERT INTO mc_run_approvals (
                    approval_id,run_id,step_id,policy_decision_id,owner_id,session_id,
                    tool_ref,status,request_json,request_hash,requested_by,requested_at,
                    expires_at,contract_version
                ) VALUES (?,?,?,?,?,?,?,'pending',?,?,?,?,?,?)""",
                (
                    request.approval_id,
                    request.run_id,
                    request.step_id,
                    request.policy_decision_id,
                    request.owner_id,
                    request.session_id,
                    request.tool_ref,
                    _canonical_json(stored_request),
                    request_hash,
                    actor,
                    timestamp,
                    request.expires_at,
                    request.contract_version,
                ),
            )
            new_version = int(run["version"]) + 1
            updated = conn.execute(
                """UPDATE mc_runs
                   SET status='waiting_approval',version=?,updated_at=?
                   WHERE run_id=? AND version=? AND status='planned'""",
                (new_version, timestamp, request.run_id, run["version"]),
            )
            if updated.rowcount != 1:
                raise ApprovalConflictError("run changed while approval was requested")
            conn.execute(
                "UPDATE mc_loop_runs SET status='waiting_approval',updated_at=? WHERE run_id=?",
                (timestamp, request.run_id),
            )
            _append_run_event(
                conn,
                run_id=request.run_id,
                event_type="approval.requested",
                stage="approval",
                actor=actor,
                payload={
                    "approval_id": request.approval_id,
                    "policy_decision_id": request.policy_decision_id,
                    "step_id": request.step_id,
                    "tool_ref": request.tool_ref,
                    "status": ApprovalStatus.PENDING.value,
                    "expires_at": request.expires_at,
                },
                event_id=f"{request.approval_id}:approval.requested",
                timestamp=timestamp,
                contract_version=request.contract_version,
            )
            _append_run_event(
                conn,
                run_id=request.run_id,
                event_type="run.waiting_approval",
                stage=RunStatus.WAITING_APPROVAL.value,
                actor=actor,
                payload={
                    "status": RunStatus.WAITING_APPROVAL.value,
                    "owner_attention": True,
                    "approval_id": request.approval_id,
                },
                event_id=f"{request.approval_id}:run.waiting_approval",
                timestamp=timestamp,
                contract_version=request.contract_version,
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM mc_run_approvals WHERE approval_id=?",
                (request.approval_id,),
            ).fetchone()
            return _approval_from_row(row)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def decide(
        self,
        decision: OwnerApprovalDecision,
        *,
        actor: str,
        timestamp: str | None = None,
    ) -> dict[str, Any]:
        if not isinstance(decision, OwnerApprovalDecision):
            raise ValueError("decision must be an OwnerApprovalDecision")
        _require_text(actor, "actor")
        timestamp = timestamp or _now()
        decided_at = _parse_timestamp(timestamp, "timestamp")
        authenticated_at = _parse_timestamp(decision.authenticated_at, "authenticated_at")
        if authenticated_at > decided_at:
            raise ApprovalConflictError("owner authentication cannot be in the future")

        response_contract = contract_to_dict(decision)
        response_hash = _hash(response_contract)
        stored_response = redact_payload(response_contract)
        conn = get_connection()
        try:
            _ensure_runtime_schema(conn)
            conn.execute("BEGIN IMMEDIATE")
            row = self._require_approval(conn, decision.approval_id)
            if row["status"] != ApprovalStatus.PENDING.value:
                if not (
                    row["status"] == decision.status.value
                    and row["response_hash"] == response_hash
                    and row["decided_by"] == actor
                ):
                    raise ApprovalConflictError("approval already has a different resolution")
                conn.commit()
                return _approval_from_row(row)

            if decided_at >= _parse_timestamp(row["expires_at"], "expires_at"):
                self._resolve_expired(conn, row, actor=actor, timestamp=timestamp)
            else:
                if not (
                    row["owner_id"] == decision.owner_id
                    and row["session_id"] == decision.session_id
                ):
                    raise ApprovalConflictError("authenticated owner does not match the run")
                if authenticated_at < _parse_timestamp(row["requested_at"], "requested_at"):
                    raise ApprovalConflictError(
                        "owner authentication predates the approval request"
                    )
                self._resolve_owner_decision(
                    conn,
                    row,
                    decision=decision,
                    actor=actor,
                    timestamp=timestamp,
                    stored_response=stored_response,
                    response_hash=response_hash,
                )
            conn.commit()
            resolved = conn.execute(
                "SELECT * FROM mc_run_approvals WHERE approval_id=?",
                (decision.approval_id,),
            ).fetchone()
            return _approval_from_row(resolved)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def expire(
        self,
        approval_id: str,
        *,
        actor: str,
        timestamp: str | None = None,
    ) -> dict[str, Any]:
        _require_text(approval_id, "approval_id")
        _require_text(actor, "actor")
        timestamp = timestamp or _now()
        current_time = _parse_timestamp(timestamp, "timestamp")
        conn = get_connection()
        try:
            _ensure_runtime_schema(conn)
            conn.execute("BEGIN IMMEDIATE")
            row = self._require_approval(conn, approval_id)
            if row["status"] != ApprovalStatus.PENDING.value:
                conn.commit()
                return _approval_from_row(row)
            if current_time < _parse_timestamp(row["expires_at"], "expires_at"):
                raise ApprovalNotDueError("approval has not reached its expiry deadline")
            self._resolve_expired(conn, row, actor=actor, timestamp=timestamp)
            conn.commit()
            expired = conn.execute(
                "SELECT * FROM mc_run_approvals WHERE approval_id=?", (approval_id,)
            ).fetchone()
            return _approval_from_row(expired)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def apply_to_policy(
        self,
        policy_input: PolicyInput,
        approval_id: str,
    ) -> PolicyInput:
        if not isinstance(policy_input, PolicyInput):
            raise ValueError("policy_input must be a PolicyInput")
        _require_text(approval_id, "approval_id")
        conn = get_connection()
        try:
            _ensure_runtime_schema(conn)
            row = self._require_approval(conn, approval_id)
            policy = conn.execute(
                "SELECT input_hash FROM mc_policy_decisions WHERE decision_id=?",
                (row["policy_decision_id"],),
            ).fetchone()
            if policy is None:
                raise ApprovalConflictError("approval policy decision is missing")
            run = conn.execute(
                "SELECT status FROM mc_runs WHERE run_id=?", (row["run_id"],)
            ).fetchone()
            expected_run_status = (
                RunStatus.WAITING_APPROVAL.value
                if row["status"] in {
                    ApprovalStatus.PENDING.value,
                    ApprovalStatus.APPROVED.value,
                }
                else RunStatus.CANCELLED.value
            )
            identity_matches = (
                run is not None
                and run["status"] == expected_run_status
                and row["run_id"] == policy_input.run_id
                and row["step_id"] == policy_input.step_id
                and row["tool_ref"] == policy_input.tool.ref
                and row["owner_id"] == policy_input.owner_id
                and row["session_id"] == policy_input.session_id
                and row["contract_version"] == policy_input.contract_version
            )
            baseline = replace(
                policy_input,
                decision_id=row["policy_decision_id"],
                approval_status=ApprovalStatus.NONE,
                approval_id=None,
            )
            if not identity_matches or _hash(contract_to_dict(baseline)) != policy["input_hash"]:
                raise ApprovalConflictError(
                    "approval evidence does not match the current policy action"
                )
            status = ApprovalStatus(row["status"])
            return replace(
                policy_input,
                approval_status=status,
                approval_id=approval_id,
            )
        finally:
            conn.close()

    def get(self, approval_id: str) -> dict[str, Any] | None:
        _require_text(approval_id, "approval_id")
        conn = get_connection()
        try:
            _ensure_runtime_schema(conn)
            row = conn.execute(
                "SELECT * FROM mc_run_approvals WHERE approval_id=?", (approval_id,)
            ).fetchone()
            return _approval_from_row(row) if row is not None else None
        finally:
            conn.close()

    def list_for_run(self, run_id: str) -> list[dict[str, Any]]:
        _require_text(run_id, "run_id")
        conn = get_connection()
        try:
            _ensure_runtime_schema(conn)
            rows = conn.execute(
                "SELECT * FROM mc_run_approvals WHERE run_id=? ORDER BY requested_at,approval_id",
                (run_id,),
            ).fetchall()
            return [_approval_from_row(row) for row in rows]
        finally:
            conn.close()

    @staticmethod
    def _require_approval(conn: sqlite3.Connection, approval_id: str) -> sqlite3.Row:
        row = conn.execute(
            "SELECT * FROM mc_run_approvals WHERE approval_id=?", (approval_id,)
        ).fetchone()
        if row is None:
            raise ApprovalNotFoundError(approval_id)
        return row

    def _resolve_owner_decision(
        self,
        conn: sqlite3.Connection,
        row: sqlite3.Row,
        *,
        decision: OwnerApprovalDecision,
        actor: str,
        timestamp: str,
        stored_response: dict[str, Any],
        response_hash: str,
    ) -> None:
        updated = conn.execute(
            """UPDATE mc_run_approvals
               SET status=?,response_json=?,response_hash=?,decided_by=?,decided_at=?
               WHERE approval_id=? AND status='pending'""",
            (
                decision.status.value,
                _canonical_json(stored_response),
                response_hash,
                actor,
                timestamp,
                decision.approval_id,
            ),
        )
        if updated.rowcount != 1:
            raise ApprovalConflictError("approval changed while it was being decided")
        _append_run_event(
            conn,
            run_id=row["run_id"],
            event_type=f"approval.{decision.status.value}",
            stage="approval",
            actor=actor,
            payload={
                "approval_id": decision.approval_id,
                "policy_decision_id": row["policy_decision_id"],
                "step_id": row["step_id"],
                "tool_ref": row["tool_ref"],
                "status": decision.status.value,
                "owner_id": decision.owner_id,
                "authentication_method": decision.authentication_method,
                "authenticated_at": decision.authenticated_at,
            },
            event_id=f"{decision.approval_id}:approval.{decision.status.value}",
            timestamp=timestamp,
            contract_version=decision.contract_version,
        )
        if decision.status is ApprovalStatus.REJECTED:
            self._cancel_waiting_run(
                conn,
                row,
                actor=actor,
                timestamp=timestamp,
                reason=ApprovalStatus.REJECTED.value,
            )

    def _resolve_expired(
        self,
        conn: sqlite3.Connection,
        row: sqlite3.Row,
        *,
        actor: str,
        timestamp: str,
    ) -> None:
        response = {
            "approval_id": row["approval_id"],
            "status": ApprovalStatus.EXPIRED.value,
            "expired_at": timestamp,
            "contract_version": row["contract_version"],
        }
        response_hash = _hash(response)
        updated = conn.execute(
            """UPDATE mc_run_approvals
               SET status='expired',response_json=?,response_hash=?,decided_by=?,decided_at=?
               WHERE approval_id=? AND status='pending'""",
            (
                _canonical_json(response),
                response_hash,
                actor,
                timestamp,
                row["approval_id"],
            ),
        )
        if updated.rowcount != 1:
            raise ApprovalConflictError("approval changed while it was expiring")
        _append_run_event(
            conn,
            run_id=row["run_id"],
            event_type="approval.expired",
            stage="approval",
            actor=actor,
            payload={
                "approval_id": row["approval_id"],
                "policy_decision_id": row["policy_decision_id"],
                "step_id": row["step_id"],
                "tool_ref": row["tool_ref"],
                "status": ApprovalStatus.EXPIRED.value,
                "expires_at": row["expires_at"],
            },
            event_id=f"{row['approval_id']}:approval.expired",
            timestamp=timestamp,
            contract_version=row["contract_version"],
        )
        self._cancel_waiting_run(
            conn,
            row,
            actor=actor,
            timestamp=timestamp,
            reason=ApprovalStatus.EXPIRED.value,
        )

    @staticmethod
    def _cancel_waiting_run(
        conn: sqlite3.Connection,
        approval: sqlite3.Row,
        *,
        actor: str,
        timestamp: str,
        reason: str,
    ) -> None:
        run = conn.execute(
            "SELECT status,version FROM mc_runs WHERE run_id=?", (approval["run_id"],)
        ).fetchone()
        if run is None:
            raise RunNotFoundError(approval["run_id"])
        require_transition(run["status"], RunStatus.CANCELLED)
        new_version = int(run["version"]) + 1
        updated = conn.execute(
            """UPDATE mc_runs
               SET status='cancelled',version=?,updated_at=?,completed_at=?
               WHERE run_id=? AND version=? AND status='waiting_approval'""",
            (
                new_version,
                timestamp,
                timestamp,
                approval["run_id"],
                run["version"],
            ),
        )
        if updated.rowcount != 1:
            raise ApprovalConflictError("run changed while approval was resolved")
        conn.execute(
            "UPDATE mc_loop_runs SET status='cancelled',updated_at=? WHERE run_id=?",
            (timestamp, approval["run_id"]),
        )
        _append_run_event(
            conn,
            run_id=approval["run_id"],
            event_type="run.cancelled",
            stage=RunStatus.CANCELLED.value,
            actor=actor,
            payload={
                "status": RunStatus.CANCELLED.value,
                "approval_id": approval["approval_id"],
                "reason": f"approval.{reason}",
                "owner_attention": False,
            },
            event_id=f"{approval['approval_id']}:run.cancelled",
            timestamp=timestamp,
            contract_version=approval["contract_version"],
        )

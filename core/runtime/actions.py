"""Dormant action reservations, immutable receipts, and crash reconciliation."""
from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any, Mapping

from core.database import get_connection
from core.runtime.contracts import (
    ActionReceipt,
    RuntimeToolCall,
    RuntimeToolResult,
    contract_to_dict,
)
from core.runtime.event_store import _append_run_event, redact_payload
from core.runtime.repository import (
    RunNotFoundError,
    RuntimeRepository,
    _canonical_json,
    _hash,
    _iso,
    _lease_now,
    _load_json,
)
from core.schema.runtime import _ensure_runtime_schema


class ActionConflictError(ValueError):
    """An idempotency identity was reused for different action content."""


class ActionStateError(ValueError):
    """An action cannot move through the requested lifecycle transition."""


def _require_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _action_from_row(row: sqlite3.Row) -> dict[str, Any]:
    action = dict(row)
    action["request"] = _load_json(action.pop("request_json"), {})
    action["result"] = _load_json(action.pop("result_json"), {})
    action["reconciliation"] = _load_json(
        action.pop("reconciliation_json"), {}
    )
    return action


def _receipt_from_row(row: sqlite3.Row) -> dict[str, Any]:
    receipt = dict(row)
    receipt["result"] = _load_json(receipt.pop("result_json"), {})
    receipt["evidence_refs"] = _load_json(
        receipt.pop("evidence_refs_json"), []
    )
    return receipt


def _request_identity(call: RuntimeToolCall, target: str) -> tuple[dict[str, Any], str]:
    identity = {**contract_to_dict(call), "target": target}
    return redact_payload(identity), _hash(identity)


def _require_matching_action(
    row: sqlite3.Row,
    call: RuntimeToolCall,
    target: str,
    request_hash: str,
) -> None:
    matches = (
        row["run_id"] == call.run_id
        and row["step_id"] == call.step_id
        and row["call_id"] == call.call_id
        and row["tool_ref"] == call.tool_ref
        and row["target"] == target
        and row["request_hash"] == request_hash
    )
    if not matches:
        raise ActionConflictError(
            f"idempotency_key {call.idempotency_key!r} already has different content"
        )


def _load_receipt(conn: sqlite3.Connection, receipt_id: str | None) -> dict[str, Any] | None:
    if not receipt_id:
        return None
    row = conn.execute(
        "SELECT * FROM mc_action_receipts WHERE receipt_id=?", (receipt_id,)
    ).fetchone()
    return _receipt_from_row(row) if row is not None else None


def finalize_reserved_action(
    conn: sqlite3.Connection,
    *,
    action: sqlite3.Row,
    receipt: ActionReceipt,
    result: RuntimeToolResult,
    actor: str,
    completed_at: str,
    reconciliation_outcome: str,
    evidence_refs: tuple[str, ...] = (),
    reconciliation: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Finalize an action inside the caller's step-success transaction."""
    if not isinstance(receipt, ActionReceipt):
        raise ValueError("receipt must be an ActionReceipt")
    if not isinstance(result, RuntimeToolResult) or result.status != "succeeded":
        raise ValueError("result must be a succeeded RuntimeToolResult")
    if result.receipt_id != receipt.receipt_id:
        raise ValueError("result.receipt_id must match receipt.receipt_id")
    if reconciliation_outcome not in {"direct", "applied"}:
        raise ValueError("reconciliation_outcome must be direct or applied")
    if action["status"] not in {"in_progress", "reconciliation_required"}:
        raise ActionStateError("only unresolved actions can be completed")
    if (
        receipt.run_id != action["run_id"]
        or receipt.step_id != action["step_id"]
        or receipt.tool_ref != action["tool_ref"]
        or receipt.target != action["target"]
    ):
        raise ActionConflictError("receipt identity does not match its reservation")

    stored_receipt = redact_payload(contract_to_dict(receipt))
    stored_result = redact_payload(contract_to_dict(result))
    result_json = _canonical_json(stored_result)
    result_hash = _hash(stored_result)
    stored_reconciliation = redact_payload(dict(reconciliation or {}))
    reconciliation_json = _canonical_json(stored_reconciliation)
    reconciliation_hash = _hash(stored_reconciliation)
    stored_evidence = redact_payload({"refs": list(evidence_refs)})["refs"]
    conn.execute(
        """INSERT INTO mc_action_receipts (
            receipt_id,idempotency_key,run_id,step_id,tool_ref,target,
            effect_summary,before_ref,after_ref,external_ref,approval_ref,
            result_json,result_hash,reconciliation_outcome,evidence_refs_json,
            actor,timestamp,created_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            stored_receipt["receipt_id"],
            action["idempotency_key"],
            action["run_id"],
            action["step_id"],
            stored_receipt["tool_ref"],
            stored_receipt["target"],
            stored_receipt["effect_summary"],
            stored_receipt.get("before_ref"),
            stored_receipt.get("after_ref"),
            stored_receipt.get("external_ref"),
            stored_receipt.get("approval_ref"),
            result_json,
            result_hash,
            reconciliation_outcome,
            _canonical_json(stored_evidence),
            actor,
            stored_receipt["timestamp"],
            completed_at,
        ),
    )
    updated = conn.execute(
        """UPDATE mc_idempotency
           SET status='completed',receipt_id=?,result_json=?,result_hash=?,
               reconciliation_outcome=?,reconciliation_json=?,reconciliation_hash=?,
               updated_at=?,completed_at=?
           WHERE idempotency_key=? AND status IN ('in_progress','reconciliation_required')""",
        (
            receipt.receipt_id,
            result_json,
            result_hash,
            reconciliation_outcome,
            reconciliation_json,
            reconciliation_hash,
            completed_at,
            completed_at,
            action["idempotency_key"],
        ),
    )
    if updated.rowcount != 1:
        raise ActionStateError("action changed while its receipt was being recorded")
    return _receipt_from_row(
        conn.execute(
            "SELECT * FROM mc_action_receipts WHERE receipt_id=?",
            (receipt.receipt_id,),
        ).fetchone()
    )


def mark_interrupted_action(
    conn: sqlite3.Connection,
    *,
    action: sqlite3.Row,
    step: sqlite3.Row,
    actor: str,
    now_iso: str,
) -> None:
    """Move an expired action into recovery without granting another execution."""
    payload = {
        "outcome": "unknown",
        "summary": "Worker lease expired before action completion was recorded",
        "evidence_refs": [],
    }
    stored = redact_payload(payload)
    conn.execute(
        """UPDATE mc_idempotency
           SET status='reconciliation_required',reconciliation_outcome='unknown',
               reconciliation_json=?,reconciliation_hash=?,updated_at=?
           WHERE idempotency_key=? AND status='in_progress'""",
        (_canonical_json(stored), _hash(stored), now_iso, action["idempotency_key"]),
    )
    conn.execute(
        """UPDATE mc_run_steps
           SET status='reconciliation_required',lease_owner=NULL,
               lease_token_hash=NULL,lease_expires_at=NULL,updated_at=?
           WHERE run_id=? AND step_id=? AND lease_epoch=?""",
        (now_iso, step["run_id"], step["step_id"], step["lease_epoch"]),
    )
    run = conn.execute(
        "SELECT status,version FROM mc_runs WHERE run_id=?", (step["run_id"],)
    ).fetchone()
    if run is not None and run["status"] == "running":
        new_version = int(run["version"]) + 1
        conn.execute(
            """UPDATE mc_runs SET status='recovering',version=?,updated_at=?,completed_at=NULL
               WHERE run_id=? AND version=? AND status='running'""",
            (new_version, now_iso, step["run_id"], run["version"]),
        )
        conn.execute(
            "UPDATE mc_loop_runs SET status='recovering',updated_at=? WHERE run_id=?",
            (now_iso, step["run_id"]),
        )
        _append_run_event(
            conn,
            run_id=step["run_id"],
            event_type="run.recovering",
            stage="recover",
            actor=actor,
            payload={
                "status": "recovering",
                "failed_step_id": step["step_id"],
                "owner_attention": True,
                "reason": "action_reconciliation_required",
            },
            event_id=f"{step['run_id']}:action-recovering:{new_version}",
            timestamp=now_iso,
        )
    _append_run_event(
        conn,
        run_id=step["run_id"],
        event_type="action.reconciliation_required",
        stage="recover",
        actor=actor,
        payload={
            "idempotency_key": action["idempotency_key"],
            "step_id": step["step_id"],
            **stored,
        },
        event_id=f"{step['run_id']}:{step['step_id']}:action-reconciliation:{action['execution_count']}",
        timestamp=now_iso,
    )


def cancel_active_actions(
    conn: sqlite3.Connection, *, run_id: str, actor: str, now_iso: str
) -> None:
    rows = conn.execute(
        "SELECT * FROM mc_idempotency WHERE run_id=? AND status='in_progress'",
        (run_id,),
    ).fetchall()
    for row in rows:
        payload = {
            "outcome": "cancelled",
            "summary": "Run was cancelled before action completion was recorded",
            "evidence_refs": [],
        }
        stored = redact_payload(payload)
        conn.execute(
            """UPDATE mc_idempotency
               SET status='reconciliation_required',reconciliation_outcome='cancelled',
                   reconciliation_json=?,reconciliation_hash=?,updated_at=?
               WHERE idempotency_key=? AND status='in_progress'""",
            (_canonical_json(stored), _hash(stored), now_iso, row["idempotency_key"]),
        )


class ActionLedger:
    """Persist one execution decision for each side-effect identity."""

    def get_action(self, idempotency_key: str) -> dict[str, Any] | None:
        _require_text(idempotency_key, "idempotency_key")
        conn = get_connection()
        try:
            _ensure_runtime_schema(conn)
            row = conn.execute(
                "SELECT * FROM mc_idempotency WHERE idempotency_key=?",
                (idempotency_key,),
            ).fetchone()
            return _action_from_row(row) if row is not None else None
        finally:
            conn.close()

    def prepare_action(
        self,
        call: RuntimeToolCall,
        *,
        target: str,
        worker_id: str,
        lease_token: str,
        lease_epoch: int,
        now: datetime | None = None,
        event_id: str | None = None,
    ) -> dict[str, Any]:
        if not isinstance(call, RuntimeToolCall):
            raise ValueError("call must be a RuntimeToolCall")
        if not call.idempotency_key:
            raise ValueError("side-effecting calls require idempotency_key")
        _require_text(target, "target")
        _require_text(worker_id, "worker_id")
        prepared_at = _iso(_lease_now(now))
        stored_request, request_hash = _request_identity(call, target)
        conn = get_connection()
        try:
            _ensure_runtime_schema(conn)
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT * FROM mc_idempotency WHERE idempotency_key=?",
                (call.idempotency_key,),
            ).fetchone()
            if existing is not None:
                _require_matching_action(existing, call, target, request_hash)
                if existing["status"] == "completed":
                    action = _action_from_row(existing)
                    receipt = _load_receipt(conn, existing["receipt_id"])
                    conn.commit()
                    return {
                        "decision": "replay",
                        "action": action,
                        "receipt": receipt,
                        "result": action["result"],
                    }
                if existing["status"] != "retry_allowed":
                    action = _action_from_row(existing)
                    conn.commit()
                    return {
                        "decision": "reconcile",
                        "action": action,
                        "receipt": None,
                        "result": None,
                    }

            step = RuntimeRepository._require_active_lease(
                conn,
                run_id=call.run_id,
                step_id=call.step_id,
                worker_id=worker_id,
                lease_token=lease_token,
                lease_epoch=lease_epoch,
                now=_lease_now(now),
            )
            if step["idempotency_key"] != call.idempotency_key:
                raise ActionConflictError(
                    "tool call idempotency_key does not match the persisted step"
                )
            if existing is None:
                execution_count = 1
                conn.execute(
                    """INSERT INTO mc_idempotency (
                        idempotency_key,run_id,step_id,call_id,tool_ref,target,
                        request_json,request_hash,status,execution_count,lease_epoch,
                        worker_id,created_at,updated_at
                    ) VALUES (?,?,?,?,?,?,?,?,'in_progress',1,?,?,?,?)""",
                    (
                        call.idempotency_key,
                        call.run_id,
                        call.step_id,
                        call.call_id,
                        call.tool_ref,
                        target,
                        _canonical_json(stored_request),
                        request_hash,
                        lease_epoch,
                        worker_id,
                        prepared_at,
                        prepared_at,
                    ),
                )
            else:
                execution_count = int(existing["execution_count"]) + 1
                updated = conn.execute(
                    """UPDATE mc_idempotency
                       SET status='in_progress',execution_count=?,lease_epoch=?,worker_id=?,
                           receipt_id=NULL,result_json='{}',result_hash=NULL,
                           reconciliation_outcome=NULL,reconciliation_json='{}',
                           reconciliation_hash=NULL,updated_at=?,completed_at=NULL
                       WHERE idempotency_key=? AND status='retry_allowed'""",
                    (
                        execution_count,
                        lease_epoch,
                        worker_id,
                        prepared_at,
                        call.idempotency_key,
                    ),
                )
                if updated.rowcount != 1:
                    raise ActionStateError("action changed while retry was being reserved")
            _append_run_event(
                conn,
                run_id=call.run_id,
                event_type="action.reserved",
                stage="execute",
                actor=worker_id,
                payload={
                    "idempotency_key": call.idempotency_key,
                    "step_id": call.step_id,
                    "call_id": call.call_id,
                    "tool_ref": call.tool_ref,
                    "target": target,
                    "execution_count": execution_count,
                },
                event_id=event_id
                or f"{call.run_id}:{call.step_id}:action-reserved:{execution_count}",
                timestamp=prepared_at,
            )
            row = conn.execute(
                "SELECT * FROM mc_idempotency WHERE idempotency_key=?",
                (call.idempotency_key,),
            ).fetchone()
            conn.commit()
            return {
                "decision": "execute",
                "action": _action_from_row(row),
                "receipt": None,
                "result": None,
            }
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def reconcile_action(
        self,
        idempotency_key: str,
        *,
        outcome: str,
        actor: str,
        summary: str,
        evidence_refs: tuple[str, ...] = (),
        receipt: ActionReceipt | None = None,
        result: RuntimeToolResult | None = None,
        now: datetime | None = None,
        event_id: str | None = None,
    ) -> dict[str, Any]:
        _require_text(idempotency_key, "idempotency_key")
        _require_text(actor, "actor")
        _require_text(summary, "summary")
        if outcome not in {"applied", "not_applied", "unknown"}:
            raise ValueError("outcome must be applied, not_applied, or unknown")
        if not isinstance(evidence_refs, tuple) or not all(
            isinstance(ref, str) and ref for ref in evidence_refs
        ):
            raise ValueError("evidence_refs must be a tuple of non-empty strings")
        reconciled_at = _iso(_lease_now(now))
        reconciliation = redact_payload(
            {
                "outcome": outcome,
                "summary": summary,
                "evidence_refs": list(evidence_refs),
            }
        )
        conn = get_connection()
        try:
            _ensure_runtime_schema(conn)
            conn.execute("BEGIN IMMEDIATE")
            action = conn.execute(
                "SELECT * FROM mc_idempotency WHERE idempotency_key=?",
                (idempotency_key,),
            ).fetchone()
            if action is None:
                raise ActionStateError(f"unknown idempotency_key {idempotency_key!r}")
            reconciliation_hash = _hash(reconciliation)
            if action["status"] == "completed":
                if (
                    action["reconciliation_outcome"] != outcome
                    or action["reconciliation_hash"] != reconciliation_hash
                ):
                    raise ActionConflictError(
                        "a completed action cannot be reconciled with different content"
                    )
                conn.commit()
                return _action_from_row(action)
            if action["status"] == "retry_allowed":
                if (
                    outcome != "not_applied"
                    or action["reconciliation_hash"] != reconciliation_hash
                ):
                    raise ActionConflictError(
                        "retry permission cannot be changed by a later reconciliation"
                    )
                conn.commit()
                return _action_from_row(action)
            if (
                action["status"] == "reconciliation_required"
                and action["reconciliation_outcome"] == outcome
            ):
                if action["reconciliation_hash"] != reconciliation_hash:
                    raise ActionConflictError(
                        "the same reconciliation outcome has different content"
                    )
                conn.commit()
                return _action_from_row(action)
            run = conn.execute(
                "SELECT status,version FROM mc_runs WHERE run_id=?", (action["run_id"],)
            ).fetchone()
            if run is None:
                raise RunNotFoundError(action["run_id"])

            if outcome == "applied":
                if receipt is None or result is None:
                    raise ValueError("applied reconciliation requires receipt and result")
                finalize_reserved_action(
                    conn,
                    action=action,
                    receipt=receipt,
                    result=result,
                    actor=actor,
                    completed_at=reconciled_at,
                    reconciliation_outcome="applied",
                    evidence_refs=evidence_refs,
                    reconciliation=reconciliation,
                )
                if run["status"] != "cancelled":
                    conn.execute(
                        """UPDATE mc_run_steps
                           SET status='succeeded',lease_owner=NULL,lease_token_hash=NULL,
                               lease_expires_at=NULL,next_attempt_at=NULL,updated_at=?,completed_at=?
                           WHERE run_id=? AND step_id=?""",
                        (reconciled_at, reconciled_at, action["run_id"], action["step_id"]),
                    )
                _append_run_event(
                    conn,
                    run_id=action["run_id"],
                    event_type="action.receipt_recorded",
                    stage="recover",
                    actor=actor,
                    payload={
                        "idempotency_key": idempotency_key,
                        "receipt_id": receipt.receipt_id,
                        "step_id": action["step_id"],
                        "reconciliation": reconciliation,
                    },
                    event_id=event_id or f"{action['run_id']}:{action['step_id']}:action-applied",
                    timestamp=reconciled_at,
                )
                if run["status"] != "cancelled":
                    _append_run_event(
                        conn,
                        run_id=action["run_id"],
                        event_type="step.succeeded",
                        stage="recover",
                        actor=actor,
                        payload={
                            "step_id": action["step_id"],
                            "receipt_id": receipt.receipt_id,
                            "reconciled": True,
                        },
                        event_id=f"{action['run_id']}:{action['step_id']}:reconciled-succeeded",
                        timestamp=reconciled_at,
                    )
                target_status = "completed"
            elif outcome == "not_applied":
                if run["status"] == "cancelled":
                    raise ActionStateError("a cancelled run cannot retry an action")
                conn.execute(
                    """UPDATE mc_idempotency
                       SET status='retry_allowed',reconciliation_outcome='not_applied',
                           reconciliation_json=?,reconciliation_hash=?,updated_at=?
                       WHERE idempotency_key=? AND status IN (
                           'in_progress','reconciliation_required'
                       )""",
                    (
                        _canonical_json(reconciliation),
                        _hash(reconciliation),
                        reconciled_at,
                        idempotency_key,
                    ),
                )
                conn.execute(
                    """UPDATE mc_run_steps
                       SET status='pending',lease_owner=NULL,lease_token_hash=NULL,
                           lease_expires_at=NULL,next_attempt_at=NULL,updated_at=?,completed_at=NULL
                       WHERE run_id=? AND step_id=?""",
                    (reconciled_at, action["run_id"], action["step_id"]),
                )
                target_status = "retry_allowed"
                _append_run_event(
                    conn,
                    run_id=action["run_id"],
                    event_type="action.reconciled_not_applied",
                    stage="recover",
                    actor=actor,
                    payload={
                        "idempotency_key": idempotency_key,
                        "step_id": action["step_id"],
                        "reconciliation": reconciliation,
                    },
                    event_id=event_id or f"{action['run_id']}:{action['step_id']}:action-not-applied",
                    timestamp=reconciled_at,
                )
            else:
                conn.execute(
                    """UPDATE mc_idempotency
                       SET status='reconciliation_required',reconciliation_outcome='unknown',
                           reconciliation_json=?,reconciliation_hash=?,updated_at=?
                       WHERE idempotency_key=? AND status IN (
                           'in_progress','reconciliation_required'
                       )""",
                    (
                        _canonical_json(reconciliation),
                        _hash(reconciliation),
                        reconciled_at,
                        idempotency_key,
                    ),
                )
                conn.execute(
                    """UPDATE mc_run_steps
                       SET status='reconciliation_required',lease_owner=NULL,
                           lease_token_hash=NULL,lease_expires_at=NULL,updated_at=?
                       WHERE run_id=? AND step_id=?""",
                    (reconciled_at, action["run_id"], action["step_id"]),
                )
                target_status = "reconciliation_required"
                _append_run_event(
                    conn,
                    run_id=action["run_id"],
                    event_type="action.reconciliation_required",
                    stage="recover",
                    actor=actor,
                    payload={
                        "idempotency_key": idempotency_key,
                        "step_id": action["step_id"],
                        "reconciliation": reconciliation,
                    },
                    event_id=event_id or f"{action['run_id']}:{action['step_id']}:action-unknown",
                    timestamp=reconciled_at,
                )

            if run["status"] in {"running", "recovering"}:
                desired = "recovering" if outcome == "unknown" else "running"
                if run["status"] != desired:
                    new_version = int(run["version"]) + 1
                    conn.execute(
                        "UPDATE mc_runs SET status=?,version=?,updated_at=? WHERE run_id=? AND version=?",
                        (desired, new_version, reconciled_at, action["run_id"], run["version"]),
                    )
                    conn.execute(
                        "UPDATE mc_loop_runs SET status=?,updated_at=? WHERE run_id=?",
                        (desired, reconciled_at, action["run_id"]),
                    )
                    _append_run_event(
                        conn,
                        run_id=action["run_id"],
                        event_type=f"run.{desired}",
                        stage="recover",
                        actor=actor,
                        payload={
                            "status": desired,
                            "step_id": action["step_id"],
                            "reason": f"action_reconciled_{outcome}",
                        },
                        event_id=f"{action['run_id']}:action-reconciled:{new_version}",
                        timestamp=reconciled_at,
                    )
            row = conn.execute(
                "SELECT * FROM mc_idempotency WHERE idempotency_key=?",
                (idempotency_key,),
            ).fetchone()
            conn.commit()
            resolved = _action_from_row(row)
            resolved["status"] = target_status
            return resolved
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

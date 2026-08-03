"""Dormant failure, retry, cancellation, and recovery-command control."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Mapping

from core.database import get_connection
from core.runtime.actions import cancel_active_actions, finalize_reserved_action
from core.runtime.budget import effective_limits
from core.runtime.contracts import (
    ActionReceipt,
    LoopIterationResult,
    RecoveryAction,
    RunUsageDelta,
    RuntimeToolResult,
    contract_to_dict,
)
from core.runtime.event_store import _append_run_event, redact_payload
from core.runtime.repository import (
    RunNotFoundError,
    RuntimeRepository,
    VersionConflictError,
    _canonical_json,
    _hash,
    _iso,
    _lease_now,
    _load_json,
)
from core.runtime.state import RunStatus, require_transition
from core.schema.runtime import _ensure_runtime_schema


class CommandConflictError(ValueError):
    """A recovery command identity was reused for different content."""


@dataclass(frozen=True)
class _RetryRule:
    max_attempts: int
    delay_seconds: int
    exponential: bool = False
    max_delay_seconds: int = 0

    def delay_for(self, completed_attempts: int) -> int:
        if not self.exponential:
            return self.delay_seconds
        delay = self.delay_seconds * (2 ** max(0, completed_attempts - 1))
        return min(delay, self.max_delay_seconds)


def _require_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _retry_rule(value: str) -> _RetryRule | None:
    normalized = value.strip().lower()
    if normalized in {"none", "never"}:
        return None
    if normalized == "transient_once":
        return _RetryRule(max_attempts=2, delay_seconds=1)
    parts = normalized.split(":")
    try:
        if len(parts) == 3 and parts[0] == "fixed":
            attempts, delay = int(parts[1]), int(parts[2])
            if 1 <= attempts <= 100 and 0 <= delay <= 86_400:
                return _RetryRule(attempts, delay)
        if len(parts) == 4 and parts[0] == "exponential":
            attempts, base, maximum = map(int, parts[1:])
            if (
                1 <= attempts <= 100
                and 0 <= base <= 86_400
                and base <= maximum <= 86_400
            ):
                return _RetryRule(attempts, base, True, maximum)
    except ValueError:
        pass
    return None


def _effective_loop_attempts(conn: sqlite3.Connection, run_id: str) -> int:
    row = conn.execute(
        """SELECT loop.policy_json,run.budget_json
           FROM mc_loop_runs AS loop JOIN mc_runs AS run ON run.run_id=loop.run_id
           WHERE loop.run_id=?""",
        (run_id,),
    ).fetchone()
    if row is None:
        return 1
    policy = _load_json(row["policy_json"], {})
    plan_budget = _load_json(row["budget_json"], {})
    return effective_limits(policy, plan_budget)["max_attempts"]


class RuntimeControl:
    """Persist control decisions without connecting them to live runtime surfaces."""

    @staticmethod
    def _command_from_row(row: sqlite3.Row) -> dict[str, Any]:
        command = dict(row)
        command["payload"] = _load_json(command.pop("payload_json"), {})
        return command

    def record_step_success(
        self,
        run_id: str,
        step_id: str,
        *,
        worker_id: str,
        lease_token: str,
        lease_epoch: int,
        result: RuntimeToolResult,
        receipt: ActionReceipt | None = None,
        now: datetime | None = None,
        event_id: str | None = None,
    ) -> dict[str, Any]:
        if not isinstance(result, RuntimeToolResult) or result.status != "succeeded":
            raise ValueError("result must be a succeeded RuntimeToolResult")
        completed_at = _lease_now(now)
        completed_at_iso = _iso(completed_at)
        conn = get_connection()
        try:
            _ensure_runtime_schema(conn)
            conn.execute("BEGIN IMMEDIATE")
            step = RuntimeRepository._require_active_lease(
                conn,
                run_id=run_id,
                step_id=step_id,
                worker_id=worker_id,
                lease_token=lease_token,
                lease_epoch=lease_epoch,
                now=completed_at,
            )
            stored_receipt = None
            if step["idempotency_key"]:
                if receipt is None:
                    raise ValueError(
                        "a step with idempotency_key requires an action receipt"
                    )
                action = conn.execute(
                    "SELECT * FROM mc_idempotency WHERE idempotency_key=?",
                    (step["idempotency_key"],),
                ).fetchone()
                if action is None:
                    raise ValueError("the action must be reserved before completion")
                if (
                    action["status"] != "in_progress"
                    or action["worker_id"] != worker_id
                    or int(action["lease_epoch"]) != lease_epoch
                ):
                    raise ValueError("the active action reservation does not match this lease")
                stored_receipt = finalize_reserved_action(
                    conn,
                    action=action,
                    receipt=receipt,
                    result=result,
                    actor=worker_id,
                    completed_at=completed_at_iso,
                    reconciliation_outcome="direct",
                )
                _append_run_event(
                    conn,
                    run_id=run_id,
                    event_type="action.receipt_recorded",
                    stage="execute",
                    actor=worker_id,
                    payload={
                        "idempotency_key": step["idempotency_key"],
                        "receipt_id": receipt.receipt_id,
                        "step_id": step_id,
                        "reconciliation_outcome": "direct",
                    },
                    event_id=event_id
                    or f"{run_id}:{step_id}:action-receipt:{lease_epoch}",
                    timestamp=completed_at_iso,
                )
            elif receipt is not None or result.receipt_id is not None:
                raise ValueError(
                    "a receipt cannot be attached to a step without idempotency_key"
                )
            conn.execute(
                """UPDATE mc_run_steps
                   SET status='succeeded',lease_owner=NULL,lease_token_hash=NULL,
                       lease_expires_at=NULL,next_attempt_at=NULL,last_error_json=NULL,
                       last_error_hash=NULL,updated_at=?,completed_at=?
                   WHERE run_id=? AND step_id=?""",
                (completed_at_iso, completed_at_iso, run_id, step_id),
            )
            _append_run_event(
                conn,
                run_id=run_id,
                event_type="step.succeeded",
                stage="execute",
                actor=worker_id,
                payload={
                    "step_id": step_id,
                    "lease_epoch": lease_epoch,
                    "result": contract_to_dict(result),
                    "receipt_id": (
                        stored_receipt["receipt_id"] if stored_receipt else None
                    ),
                },
                event_id=(
                    f"{event_id}:step" if event_id and stored_receipt else event_id
                )
                or f"{run_id}:{step_id}:succeeded:{lease_epoch}",
                timestamp=completed_at_iso,
            )
            row = conn.execute(
                "SELECT * FROM mc_run_steps WHERE run_id=? AND step_id=?",
                (run_id, step_id),
            ).fetchone()
            conn.commit()
            return RuntimeRepository._step_from_row(row)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def record_step_failure(
        self,
        run_id: str,
        step_id: str,
        *,
        worker_id: str,
        lease_token: str,
        lease_epoch: int,
        result: RuntimeToolResult,
        now: datetime | None = None,
        event_id: str | None = None,
    ) -> dict[str, Any]:
        if not isinstance(result, RuntimeToolResult) or result.status != "failed":
            raise ValueError("result must be a failed RuntimeToolResult")
        failed_at = _lease_now(now)
        failed_at_iso = _iso(failed_at)
        error_contract = contract_to_dict(result.error)
        stored_error = redact_payload(error_contract)
        error_json = _canonical_json(stored_error)
        error_hash = _hash(error_contract)
        conn = get_connection()
        try:
            _ensure_runtime_schema(conn)
            conn.execute("BEGIN IMMEDIATE")
            step = RuntimeRepository._require_active_lease(
                conn,
                run_id=run_id,
                step_id=step_id,
                worker_id=worker_id,
                lease_token=lease_token,
                lease_epoch=lease_epoch,
                now=failed_at,
            )
            rule = _retry_rule(step["retry_policy"])
            attempts = int(step["attempts"])
            retryable = bool(
                result.retryable
                and result.error is not None
                and result.error.retryable
                and rule is not None
            )
            max_attempts = (
                min(rule.max_attempts, _effective_loop_attempts(conn, run_id))
                if rule is not None
                else 1
            )
            if retryable and attempts < max_attempts:
                next_attempt_at = _iso(
                    failed_at + timedelta(seconds=rule.delay_for(attempts))
                )
                conn.execute(
                    """UPDATE mc_run_steps
                       SET status='retry_wait',lease_owner=NULL,lease_token_hash=NULL,
                           lease_expires_at=NULL,next_attempt_at=?,last_error_json=?,
                           last_error_hash=?,updated_at=?,completed_at=NULL
                       WHERE run_id=? AND step_id=?""",
                    (
                        next_attempt_at,
                        error_json,
                        error_hash,
                        failed_at_iso,
                        run_id,
                        step_id,
                    ),
                )
                _append_run_event(
                    conn,
                    run_id=run_id,
                    event_type="step.retry_scheduled",
                    stage="recover",
                    actor=worker_id,
                    payload={
                        "step_id": step_id,
                        "attempts": attempts,
                        "max_attempts": max_attempts,
                        "next_attempt_at": next_attempt_at,
                        "error": stored_error,
                    },
                    event_id=event_id
                    or f"{run_id}:{step_id}:retry:{attempts}",
                    timestamp=failed_at_iso,
                )
            else:
                conn.execute(
                    """UPDATE mc_run_steps
                       SET status='failed',lease_owner=NULL,lease_token_hash=NULL,
                           lease_expires_at=NULL,next_attempt_at=NULL,last_error_json=?,
                           last_error_hash=?,updated_at=?,completed_at=?
                       WHERE run_id=? AND step_id=?""",
                    (
                        error_json,
                        error_hash,
                        failed_at_iso,
                        failed_at_iso,
                        run_id,
                        step_id,
                    ),
                )
                _append_run_event(
                    conn,
                    run_id=run_id,
                    event_type="step.failed",
                    stage="recover",
                    actor=worker_id,
                    payload={
                        "step_id": step_id,
                        "attempts": attempts,
                        "max_attempts": max_attempts,
                        "error": stored_error,
                    },
                    event_id=event_id or f"{run_id}:{step_id}:failed:{attempts}",
                    timestamp=failed_at_iso,
                )
                run = conn.execute(
                    "SELECT status,version FROM mc_runs WHERE run_id=?", (run_id,)
                ).fetchone()
                require_transition(run["status"], RunStatus.RECOVERING)
                new_version = int(run["version"]) + 1
                conn.execute(
                    """UPDATE mc_runs
                       SET status='recovering',version=?,updated_at=?,completed_at=NULL
                       WHERE run_id=? AND version=? AND status='running'""",
                    (new_version, failed_at_iso, run_id, run["version"]),
                )
                conn.execute(
                    "UPDATE mc_loop_runs SET status='recovering',updated_at=? WHERE run_id=?",
                    (failed_at_iso, run_id),
                )
                _append_run_event(
                    conn,
                    run_id=run_id,
                    event_type="run.recovering",
                    stage="recover",
                    actor=worker_id,
                    payload={
                        "status": "recovering",
                        "failed_step_id": step_id,
                        "owner_attention": True,
                    },
                    event_id=f"{run_id}:recovering:{new_version}",
                    timestamp=failed_at_iso,
                )
            row = conn.execute(
                "SELECT * FROM mc_run_steps WHERE run_id=? AND step_id=?",
                (run_id, step_id),
            ).fetchone()
            conn.commit()
            return RuntimeRepository._step_from_row(row)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def record_command(
        self,
        command_id: str,
        run_id: str,
        action: RecoveryAction | str,
        *,
        expected_version: int,
        actor: str,
        payload: Mapping[str, Any] | None = None,
        contract_version: str = "1",
        now: datetime | None = None,
        event_id: str | None = None,
    ) -> dict[str, Any]:
        _require_text(command_id, "command_id")
        _require_text(run_id, "run_id")
        _require_text(actor, "actor")
        _require_text(contract_version, "contract_version")
        if (
            isinstance(expected_version, bool)
            or not isinstance(expected_version, int)
            or expected_version <= 0
        ):
            raise ValueError("expected_version must be a positive integer")
        try:
            action_value = action if isinstance(action, RecoveryAction) else RecoveryAction(action)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"unknown recovery action: {action!r}") from exc
        if payload is None:
            payload = {}
        if not isinstance(payload, Mapping):
            raise ValueError("payload must be a mapping")
        created_at = _lease_now(now)
        created_at_iso = _iso(created_at)
        stored_payload = redact_payload(payload)
        payload_json = _canonical_json(stored_payload)
        payload_hash = _hash(payload)
        conn = get_connection()
        try:
            _ensure_runtime_schema(conn)
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT * FROM mc_run_commands WHERE command_id=?", (command_id,)
            ).fetchone()
            if existing is not None:
                same = (
                    existing["run_id"] == run_id
                    and existing["action"] == action_value.value
                    and existing["payload_hash"] == payload_hash
                    and existing["expected_run_version"] == expected_version
                    and existing["actor"] == actor
                    and existing["contract_version"] == contract_version
                )
                if not same:
                    raise CommandConflictError(
                        f"command_id {command_id!r} already has different content"
                    )
                conn.commit()
                return self._command_from_row(existing)
            run = conn.execute(
                "SELECT * FROM mc_runs WHERE run_id=?", (run_id,)
            ).fetchone()
            if run is None:
                raise RunNotFoundError(run_id)
            if run["version"] != expected_version:
                raise VersionConflictError(
                    f"run version is {run['version']}, not {expected_version}"
                )
            conn.execute(
                """INSERT INTO mc_run_commands (
                    command_id,run_id,action,payload_json,payload_hash,
                    expected_run_version,status,actor,contract_version,created_at
                ) VALUES (?,?,?,?,?,?,'pending',?,?,?)""",
                (
                    command_id,
                    run_id,
                    action_value.value,
                    payload_json,
                    payload_hash,
                    expected_version,
                    actor,
                    contract_version,
                    created_at_iso,
                ),
            )
            _append_run_event(
                conn,
                run_id=run_id,
                event_type="run.command_recorded",
                stage="recover",
                actor=actor,
                payload={
                    "command_id": command_id,
                    "action": action_value.value,
                    "payload": stored_payload,
                    "expected_run_version": expected_version,
                },
                event_id=event_id or f"{run_id}:command:{command_id}",
                timestamp=created_at_iso,
                contract_version=contract_version,
            )
            if action_value == RecoveryAction.CANCEL:
                require_transition(run["status"], RunStatus.CANCELLED)
                new_version = expected_version + 1
                cancel_active_actions(
                    conn,
                    run_id=run_id,
                    actor=actor,
                    now_iso=created_at_iso,
                )
                conn.execute(
                    """UPDATE mc_runs
                       SET status='cancelled',version=?,updated_at=?,completed_at=?,
                           cancel_requested_at=?,cancel_requested_by=?
                       WHERE run_id=? AND version=? AND status=?""",
                    (
                        new_version,
                        created_at_iso,
                        created_at_iso,
                        created_at_iso,
                        actor,
                        run_id,
                        expected_version,
                        run["status"],
                    ),
                )
                conn.execute(
                    """UPDATE mc_run_steps
                       SET status=CASE
                               WHEN status IN ('pending','running','retry_wait') THEN 'cancelled'
                               ELSE status
                           END,
                           lease_owner=NULL,lease_token_hash=NULL,lease_expires_at=NULL,
                           next_attempt_at=NULL,updated_at=?,
                           completed_at=CASE
                               WHEN status IN ('pending','running','retry_wait') THEN ?
                               ELSE completed_at
                           END
                       WHERE run_id=?""",
                    (created_at_iso, created_at_iso, run_id),
                )
                conn.execute(
                    """UPDATE mc_loop_runs
                       SET status='cancelled',stop_reason='owner_cancelled',updated_at=?,
                           stopped_at=?
                       WHERE run_id=?""",
                    (created_at_iso, created_at_iso, run_id),
                )
                empty_usage = contract_to_dict(RunUsageDelta())
                cancel_result = contract_to_dict(
                    LoopIterationResult(
                        stop_condition_met=False,
                        summary="Cancelled by the owner",
                    )
                )
                stored_usage = redact_payload(empty_usage)
                stored_result = redact_payload(cancel_result)
                active_iterations = conn.execute(
                    """SELECT iteration_id FROM mc_loop_iterations
                       WHERE run_id=? AND status='running'""",
                    (run_id,),
                ).fetchall()
                for iteration in active_iterations:
                    conn.execute(
                        """UPDATE mc_loop_iterations
                           SET status='stopped',finished_run_version=?,finished_by=?,
                               usage_json=?,usage_hash=?,result_json=?,result_hash=?,
                               completed_at=?
                           WHERE iteration_id=? AND status='running'""",
                        (
                            new_version,
                            actor,
                            _canonical_json(stored_usage),
                            _hash(empty_usage),
                            _canonical_json(stored_result),
                            _hash(cancel_result),
                            created_at_iso,
                            iteration["iteration_id"],
                        ),
                    )
                    _append_run_event(
                        conn,
                        run_id=run_id,
                        event_type="loop.iteration_stopped",
                        stage="cancelled",
                        actor=actor,
                        payload={
                            "iteration_id": iteration["iteration_id"],
                            "stop_reason": "owner_cancelled",
                        },
                        event_id=f"{run_id}:iteration-stopped:{iteration['iteration_id']}",
                        timestamp=created_at_iso,
                    )
                conn.execute(
                    """UPDATE mc_run_commands
                       SET status='consumed',consumed_by='runtime.control',consumed_at=?
                       WHERE command_id=? AND status='pending'""",
                    (created_at_iso, command_id),
                )
                _append_run_event(
                    conn,
                    run_id=run_id,
                    event_type="run.cancelled",
                    stage="cancelled",
                    actor=actor,
                    payload={
                        "status": "cancelled",
                        "command_id": command_id,
                        "owner_attention": False,
                    },
                    event_id=f"{run_id}:cancelled:{new_version}",
                    timestamp=created_at_iso,
                )
            row = conn.execute(
                "SELECT * FROM mc_run_commands WHERE command_id=?", (command_id,)
            ).fetchone()
            conn.commit()
            return self._command_from_row(row)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def claim_next_command(
        self,
        run_id: str,
        *,
        consumer_id: str,
        now: datetime | None = None,
    ) -> dict[str, Any] | None:
        _require_text(run_id, "run_id")
        _require_text(consumer_id, "consumer_id")
        consumed_at_iso = _iso(_lease_now(now))
        conn = get_connection()
        try:
            _ensure_runtime_schema(conn)
            conn.execute("BEGIN IMMEDIATE")
            run = conn.execute(
                "SELECT version FROM mc_runs WHERE run_id=?", (run_id,)
            ).fetchone()
            if run is None:
                raise RunNotFoundError(run_id)
            row = conn.execute(
                """SELECT * FROM mc_run_commands
                   WHERE run_id=? AND status='pending' AND expected_run_version=?
                   ORDER BY created_at,command_id LIMIT 1""",
                (run_id, run["version"]),
            ).fetchone()
            if row is None:
                conn.commit()
                return None
            updated = conn.execute(
                """UPDATE mc_run_commands
                   SET status='consumed',consumed_by=?,consumed_at=?
                   WHERE command_id=? AND status='pending'""",
                (consumer_id, consumed_at_iso, row["command_id"]),
            )
            if updated.rowcount != 1:
                conn.rollback()
                return None
            _append_run_event(
                conn,
                run_id=run_id,
                event_type="run.command_consumed",
                stage="recover",
                actor=consumer_id,
                payload={
                    "command_id": row["command_id"],
                    "action": row["action"],
                },
                event_id=f"{run_id}:command-consumed:{row['command_id']}",
                timestamp=consumed_at_iso,
                contract_version=row["contract_version"],
            )
            consumed = conn.execute(
                "SELECT * FROM mc_run_commands WHERE command_id=?",
                (row["command_id"],),
            ).fetchone()
            conn.commit()
            return self._command_from_row(consumed)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

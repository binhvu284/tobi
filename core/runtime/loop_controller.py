"""Persisted, budget-aware iteration control for dormant Runtime V2 runs."""
from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any

from core.database import get_connection
from core.runtime.budget import cumulative_usage, effective_limits, reached_limit
from core.runtime.contracts import (
    ErrorCategory,
    ErrorStage,
    LoopIterationResult,
    RecoveryAction,
    RunUsageDelta,
    RuntimeErrorInfo,
    contract_to_dict,
)
from core.runtime.event_store import _append_run_event, redact_payload
from core.runtime.repository import (
    RunNotFoundError,
    VersionConflictError,
    _canonical_json,
    _hash,
    _iso,
    _lease_now,
    _load_json,
)
from core.runtime.state import RunStateError, RunStatus, require_transition
from core.schema.runtime import _ensure_runtime_schema


class IterationConflictError(ValueError):
    """An iteration identity or completed result was reused with new content."""


class IterationNotFoundError(KeyError):
    """The requested persisted loop iteration does not exist."""


def _require_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _require_version(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("expected_run_version must be a positive integer")
    return value


def _iteration_from_row(row: sqlite3.Row) -> dict[str, Any]:
    result = dict(row)
    result["usage"] = _load_json(result.pop("usage_json"), {})
    result["result"] = _load_json(result.pop("result_json"), {})
    return result


def _usage_after(loop: sqlite3.Row, delta: RunUsageDelta) -> dict[str, int]:
    current = cumulative_usage(dict(loop))
    for key in current:
        current[key] += int(getattr(delta, key))
    return current


def _limit_error(reason: str) -> dict[str, Any]:
    error = RuntimeErrorInfo(
        code=f"loop_{reason}",
        category=(
            ErrorCategory.VALIDATION
            if reason == "required_evidence_missing"
            else ErrorCategory.BUDGET
        ),
        stage=ErrorStage.RECOVER,
        message=f"The loop stopped because {reason} was reached.",
        owner_message=(
            "Completion evidence is missing. Review the run before continuing."
            if reason == "required_evidence_missing"
            else f"The run reached its {reason} limit. Review or revise the plan."
        ),
        retryable=False,
        recovery_actions=(
            RecoveryAction.RESUME,
            RecoveryAction.REVISE,
            RecoveryAction.CANCEL,
        ),
    )
    return contract_to_dict(error)


class LoopController:
    """Start and finish canonical iterations under persisted effective limits."""

    def get_iteration(self, iteration_id: str) -> dict[str, Any] | None:
        _require_text(iteration_id, "iteration_id")
        conn = get_connection()
        try:
            _ensure_runtime_schema(conn)
            row = conn.execute(
                "SELECT * FROM mc_loop_iterations WHERE iteration_id=?",
                (iteration_id,),
            ).fetchone()
            return _iteration_from_row(row) if row is not None else None
        finally:
            conn.close()

    @staticmethod
    def _load_run_and_loop(
        conn: sqlite3.Connection, run_id: str
    ) -> tuple[sqlite3.Row, sqlite3.Row]:
        run = conn.execute(
            "SELECT * FROM mc_runs WHERE run_id=?", (run_id,)
        ).fetchone()
        if run is None:
            raise RunNotFoundError(run_id)
        loop = conn.execute(
            "SELECT * FROM mc_loop_runs WHERE run_id=?", (run_id,)
        ).fetchone()
        if loop is None:
            raise RunStateError("the run has no persisted loop policy")
        return run, loop

    @staticmethod
    def _limits(run: sqlite3.Row, loop: sqlite3.Row) -> dict[str, int]:
        return effective_limits(
            _load_json(loop["policy_json"], {}),
            _load_json(run["budget_json"], {}),
        )

    def start_iteration(
        self,
        iteration_id: str,
        run_id: str,
        *,
        expected_run_version: int,
        actor: str,
        now: datetime | None = None,
        event_id: str | None = None,
        contract_version: str = "1",
    ) -> dict[str, Any]:
        _require_text(iteration_id, "iteration_id")
        _require_text(run_id, "run_id")
        _require_text(actor, "actor")
        _require_text(contract_version, "contract_version")
        _require_version(expected_run_version)
        started_at = _lease_now(now)
        started_at_iso = _iso(started_at)
        start_identity = {
            "iteration_id": iteration_id,
            "run_id": run_id,
            "expected_run_version": expected_run_version,
            "actor": actor,
            "contract_version": contract_version,
        }
        start_hash = _hash(start_identity)
        conn = get_connection()
        try:
            _ensure_runtime_schema(conn)
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT * FROM mc_loop_iterations WHERE iteration_id=?",
                (iteration_id,),
            ).fetchone()
            if existing is not None:
                if existing["start_hash"] != start_hash:
                    raise IterationConflictError(
                        f"iteration_id {iteration_id!r} already has different content"
                    )
                run = conn.execute(
                    "SELECT status FROM mc_runs WHERE run_id=?",
                    (existing["run_id"],),
                ).fetchone()
                loop = conn.execute(
                    "SELECT stop_reason FROM mc_loop_runs WHERE run_id=?",
                    (existing["run_id"],),
                ).fetchone()
                conn.commit()
                replayed = _iteration_from_row(existing)
                replayed["run_status"] = run["status"]
                replayed["stop_reason"] = loop["stop_reason"]
                return replayed

            run, loop = self._load_run_and_loop(conn, run_id)
            if run["version"] != expected_run_version:
                raise VersionConflictError(
                    f"run version is {run['version']}, not {expected_run_version}"
                )
            if run["status"] != RunStatus.RUNNING.value:
                raise RunStateError("only a running canonical run can start an iteration")
            if not bool(loop["enabled"]):
                raise RunStateError("a disabled loop policy cannot start an iteration")
            if loop["status"] != RunStatus.RUNNING.value:
                raise RunStateError("the persisted loop is not running")

            next_iteration = int(loop["iteration"]) + 1
            limits = self._limits(run, loop)
            reason = reached_limit(
                iteration=int(loop["iteration"]),
                usage=cumulative_usage(dict(loop)),
                limits=limits,
            )
            new_version = expected_run_version + 1
            if reason is not None:
                usage_contract = contract_to_dict(RunUsageDelta())
                result_contract = contract_to_dict(
                    LoopIterationResult(
                        stop_condition_met=False,
                        summary=f"Iteration did not start because {reason} was reached",
                    )
                )
                stored_usage = redact_payload(usage_contract)
                stored_result = redact_payload(result_contract)
                conn.execute(
                    """INSERT INTO mc_loop_iterations (
                        iteration_id,run_id,iteration,started_run_version,
                        finished_run_version,actor,finished_by,start_hash,status,
                        usage_json,usage_hash,result_json,result_hash,
                        contract_version,started_at,completed_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        iteration_id,
                        run_id,
                        next_iteration,
                        expected_run_version,
                        new_version,
                        actor,
                        actor,
                        start_hash,
                        "stopped",
                        _canonical_json(stored_usage),
                        _hash(usage_contract),
                        _canonical_json(stored_result),
                        _hash(result_contract),
                        contract_version,
                        started_at_iso,
                        started_at_iso,
                    ),
                )
                require_transition(run["status"], RunStatus.RECOVERING)
                conn.execute(
                    """UPDATE mc_runs
                       SET status='recovering',version=?,updated_at=?
                       WHERE run_id=? AND version=? AND status='running'""",
                    (new_version, started_at_iso, run_id, expected_run_version),
                )
                conn.execute(
                    """UPDATE mc_loop_runs
                       SET status='recovering',stop_reason=?,loop_version=loop_version+1,
                           stopped_at=?,updated_at=?
                       WHERE run_id=? AND loop_version=?""",
                    (
                        reason,
                        started_at_iso,
                        started_at_iso,
                        run_id,
                        loop["loop_version"],
                    ),
                )
                _append_run_event(
                    conn,
                    run_id=run_id,
                    event_type="loop.stopped",
                    stage="recover",
                    actor=actor,
                    payload={
                        "iteration_id": iteration_id,
                        "stop_reason": reason,
                        "error": _limit_error(reason),
                    },
                    event_id=event_id or f"{run_id}:loop-stopped:{new_version}",
                    timestamp=started_at_iso,
                )
            else:
                conn.execute(
                    """INSERT INTO mc_loop_iterations (
                        iteration_id,run_id,iteration,started_run_version,actor,
                        start_hash,status,contract_version,started_at
                    ) VALUES (?,?,?,?,?,?,'running',?,?)""",
                    (
                        iteration_id,
                        run_id,
                        next_iteration,
                        expected_run_version,
                        actor,
                        start_hash,
                        contract_version,
                        started_at_iso,
                    ),
                )
                loop_updated = conn.execute(
                    """UPDATE mc_loop_runs
                       SET iteration=?,loop_version=loop_version+1,status='running',
                           stop_reason=NULL,started_at=COALESCE(started_at,?),
                           stopped_at=NULL,updated_at=?
                       WHERE run_id=? AND iteration=? AND loop_version=?""",
                    (
                        next_iteration,
                        started_at_iso,
                        started_at_iso,
                        run_id,
                        loop["iteration"],
                        loop["loop_version"],
                    ),
                )
                run_updated = conn.execute(
                    """UPDATE mc_runs SET version=?,updated_at=?
                       WHERE run_id=? AND version=? AND status='running'""",
                    (new_version, started_at_iso, run_id, expected_run_version),
                )
                if loop_updated.rowcount != 1 or run_updated.rowcount != 1:
                    raise VersionConflictError("run or loop changed while iteration started")
                _append_run_event(
                    conn,
                    run_id=run_id,
                    event_type="loop.iteration_started",
                    stage="execute",
                    actor=actor,
                    payload={
                        "iteration_id": iteration_id,
                        "iteration": next_iteration,
                        "effective_limits": limits,
                    },
                    event_id=event_id
                    or f"{run_id}:iteration-started:{next_iteration}",
                    timestamp=started_at_iso,
                )
            row = conn.execute(
                "SELECT * FROM mc_loop_iterations WHERE iteration_id=?",
                (iteration_id,),
            ).fetchone()
            conn.commit()
            result = _iteration_from_row(row)
            result["run_status"] = "recovering" if reason is not None else "running"
            result["stop_reason"] = reason
            return result
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def finish_iteration(
        self,
        iteration_id: str,
        *,
        expected_run_version: int,
        actor: str,
        usage: RunUsageDelta,
        result: LoopIterationResult,
        now: datetime | None = None,
        event_id: str | None = None,
    ) -> dict[str, Any]:
        _require_text(iteration_id, "iteration_id")
        _require_text(actor, "actor")
        _require_version(expected_run_version)
        if not isinstance(usage, RunUsageDelta):
            raise ValueError("usage must be RunUsageDelta")
        if not isinstance(result, LoopIterationResult):
            raise ValueError("result must be LoopIterationResult")
        completed_at = _lease_now(now)
        completed_at_iso = _iso(completed_at)
        usage_contract = contract_to_dict(usage)
        result_contract = contract_to_dict(result)
        usage_hash = _hash(usage_contract)
        result_hash = _hash(result_contract)
        stored_usage = redact_payload(usage_contract)
        stored_result = redact_payload(result_contract)
        conn = get_connection()
        try:
            _ensure_runtime_schema(conn)
            conn.execute("BEGIN IMMEDIATE")
            iteration = conn.execute(
                "SELECT * FROM mc_loop_iterations WHERE iteration_id=?",
                (iteration_id,),
            ).fetchone()
            if iteration is None:
                raise IterationNotFoundError(iteration_id)
            if iteration["status"] != "running":
                same = (
                    iteration["usage_hash"] == usage_hash
                    and iteration["result_hash"] == result_hash
                    and iteration["finished_by"] == actor
                    and iteration["finished_run_version"]
                    == expected_run_version + 1
                )
                if not same:
                    raise IterationConflictError(
                        f"iteration_id {iteration_id!r} already has a different result"
                    )
                conn.commit()
                replayed = _iteration_from_row(iteration)
                run = conn.execute(
                    "SELECT status FROM mc_runs WHERE run_id=?",
                    (iteration["run_id"],),
                ).fetchone()
                loop = conn.execute(
                    "SELECT stop_reason FROM mc_loop_runs WHERE run_id=?",
                    (iteration["run_id"],),
                ).fetchone()
                replayed["run_status"] = run["status"]
                replayed["stop_reason"] = loop["stop_reason"]
                return replayed

            run_id = iteration["run_id"]
            run, loop = self._load_run_and_loop(conn, run_id)
            if run["version"] != expected_run_version:
                raise VersionConflictError(
                    f"run version is {run['version']}, not {expected_run_version}"
                )
            if run["status"] != RunStatus.RUNNING.value:
                raise RunStateError("only a running run can finish an iteration")
            if int(loop["iteration"]) != int(iteration["iteration"]):
                raise IterationConflictError("this is not the current loop iteration")

            totals = _usage_after(loop, usage)
            limits = self._limits(run, loop)
            policy = _load_json(loop["policy_json"], {})
            required_evidence = policy.get("evidence_required", [])
            if not isinstance(required_evidence, list):
                required_evidence = []

            stop_reason = None
            target = RunStatus.RUNNING
            iteration_status = "completed"
            if result.stop_condition_met:
                if required_evidence and not result.evidence_refs:
                    stop_reason = "required_evidence_missing"
                    target = RunStatus.RECOVERING
                    iteration_status = "stopped"
                else:
                    stop_reason = "stop_condition_met"
                    target = RunStatus.SUCCEEDED
            else:
                stop_reason = reached_limit(
                    iteration=int(loop["iteration"]),
                    usage=totals,
                    limits=limits,
                )
                if stop_reason is not None:
                    target = RunStatus.RECOVERING
                    iteration_status = "stopped"

            new_version = expected_run_version + 1
            iteration_updated = conn.execute(
                """UPDATE mc_loop_iterations
                   SET status=?,finished_run_version=?,finished_by=?,usage_json=?,
                       usage_hash=?,result_json=?,result_hash=?,completed_at=?
                   WHERE iteration_id=? AND status='running'""",
                (
                    iteration_status,
                    new_version,
                    actor,
                    _canonical_json(stored_usage),
                    usage_hash,
                    _canonical_json(stored_result),
                    result_hash,
                    completed_at_iso,
                    iteration_id,
                ),
            )
            loop_status = target.value
            loop_stopped_at = completed_at_iso if target != RunStatus.RUNNING else None
            loop_updated = conn.execute(
                """UPDATE mc_loop_runs
                   SET loop_version=loop_version+1,model_calls=?,tool_calls=?,
                       prompt_tokens=?,completion_tokens=?,runtime_ms=?,cost_microusd=?,
                       download_bytes=?,storage_bytes=?,status=?,stop_reason=?,
                       stopped_at=?,updated_at=?
                   WHERE run_id=? AND loop_version=? AND iteration=?""",
                (
                    totals["model_calls"],
                    totals["tool_calls"],
                    totals["prompt_tokens"],
                    totals["completion_tokens"],
                    totals["runtime_ms"],
                    totals["cost_microusd"],
                    totals["download_bytes"],
                    totals["storage_bytes"],
                    loop_status,
                    stop_reason,
                    loop_stopped_at,
                    completed_at_iso,
                    run_id,
                    loop["loop_version"],
                    loop["iteration"],
                ),
            )
            if target != RunStatus.RUNNING:
                require_transition(run["status"], target)
            run_updated = conn.execute(
                """UPDATE mc_runs
                   SET status=?,version=?,updated_at=?,completed_at=?
                   WHERE run_id=? AND version=? AND status='running'""",
                (
                    target.value,
                    new_version,
                    completed_at_iso,
                    completed_at_iso if target == RunStatus.SUCCEEDED else None,
                    run_id,
                    expected_run_version,
                ),
            )
            if (
                iteration_updated.rowcount != 1
                or loop_updated.rowcount != 1
                or run_updated.rowcount != 1
            ):
                raise VersionConflictError("run or loop changed while iteration finished")

            _append_run_event(
                conn,
                run_id=run_id,
                event_type="loop.iteration_finished",
                stage="evaluate",
                actor=actor,
                payload={
                    "iteration_id": iteration_id,
                    "iteration": iteration["iteration"],
                    "usage": stored_usage,
                    "result": stored_result,
                    "run_status": target.value,
                    "stop_reason": stop_reason,
                },
                event_id=event_id
                or f"{run_id}:iteration-finished:{iteration['iteration']}",
                timestamp=completed_at_iso,
            )
            if target == RunStatus.SUCCEEDED:
                _append_run_event(
                    conn,
                    run_id=run_id,
                    event_type="run.succeeded",
                    stage="respond",
                    actor=actor,
                    payload={
                        "status": "succeeded",
                        "iteration_id": iteration_id,
                        "evidence_refs": list(result.evidence_refs),
                    },
                    event_id=f"{run_id}:succeeded:{new_version}",
                    timestamp=completed_at_iso,
                )
            elif target == RunStatus.RECOVERING:
                _append_run_event(
                    conn,
                    run_id=run_id,
                    event_type="loop.stopped",
                    stage="recover",
                    actor=actor,
                    payload={
                        "iteration_id": iteration_id,
                        "stop_reason": stop_reason,
                        "error": _limit_error(stop_reason or "unknown_limit"),
                    },
                    event_id=f"{run_id}:loop-stopped:{new_version}",
                    timestamp=completed_at_iso,
                )

            row = conn.execute(
                "SELECT * FROM mc_loop_iterations WHERE iteration_id=?",
                (iteration_id,),
            ).fetchone()
            conn.commit()
            completed = _iteration_from_row(row)
            completed["run_status"] = target.value
            completed["stop_reason"] = stop_reason
            return completed
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

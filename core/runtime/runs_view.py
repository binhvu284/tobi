"""Bounded read projections for the Mission Control Runs Center."""
from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Mapping

from core.database import get_connection
from core.runtime.event_store import latest_run_event, list_run_events
from core.runtime.state import RunStatus
from core.runtime.trace import build_run_trace
from core.schema.runtime import _ensure_runtime_schema


class RunsViewValidationError(ValueError):
    """A Runs Center filter or preference is invalid."""


_SAFE_EVENT_FIELDS = frozenset({
    "action", "approval_id", "approval_ref", "artifact_id", "attempt", "checkpoint_id",
    "context_manifest_ref", "developer_sequence", "error_code", "evidence_id", "goal_id",
    "iteration", "model_ref", "owner_attention", "policy_decision_id", "queue_id",
    "readiness_id", "receipt_id", "recovery_action", "result_ref", "source_event", "stage",
    "state", "status", "step_id", "target_version", "tool_ref", "version", "worker_ref",
})
_PREFERENCE_KEY = "developer.loop_selection"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _hash(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _cursor(created_at: str, run_id: str) -> str:
    return base64.urlsafe_b64encode(f"{created_at}\n{run_id}".encode("utf-8")).decode("ascii").rstrip("=")


def _decode_cursor(value: str) -> tuple[str, str]:
    try:
        padded = value + "=" * (-len(value) % 4)
        created_at, run_id = base64.urlsafe_b64decode(padded).decode("utf-8").split("\n", 1)
    except Exception as exc:
        raise RunsViewValidationError("cursor is invalid") from exc
    if not created_at or not run_id:
        raise RunsViewValidationError("cursor is invalid")
    return created_at, run_id


def _safe_scalar(value: Any) -> str | int | float | bool | None:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value[:160]
    return None


def _event_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in sorted(_SAFE_EVENT_FIELDS):
        value = _safe_scalar(payload.get(key))
        if value is not None:
            result[key] = value
    return result


def _run_summary(row: Any) -> dict[str, Any]:
    return {
        "run_id": row["run_id"],
        "request_id": row["request_id"],
        "session_id": row["session_id"],
        "surface": row["surface"],
        "mode": row["mode"],
        "status": row["status"],
        "version": row["version"],
        "contract_version": row["contract_version"],
        "legacy_run_id": row["legacy_run_id"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "completed_at": row["completed_at"],
        "label": f"{str(row['surface']).replace('_', ' ').title()} run",
    }


def _loop_summary(row: Any | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "recipe_id": row["recipe_id"],
        "recipe_version": row["recipe_version"],
        "loop_type": row["loop_type"],
        "enabled": bool(row["enabled"]),
        "iteration": row["iteration"],
        "status": row["status"],
        "stop_reason": row["stop_reason"],
        "usage": {
            key: row[key] for key in (
                "model_calls", "tool_calls", "prompt_tokens", "completion_tokens",
                "runtime_ms", "cost_microusd", "download_bytes", "storage_bytes",
            )
        },
    }


class RuntimeRunsView:
    def list_runs(
        self,
        *,
        limit: int = 50,
        cursor: str | None = None,
        surface: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        if not isinstance(limit, int) or not 1 <= limit <= 100:
            raise RunsViewValidationError("limit must be between 1 and 100")
        if surface is not None and surface not in {
            "chat", "agent", "mcp", "telegram", "cli", "scheduler", "office", "projects", "developer",
        }:
            raise RunsViewValidationError("unknown surface")
        if status is not None and status not in {item.value for item in RunStatus}:
            raise RunsViewValidationError("unknown run status")
        clauses: list[str] = []
        parameters: list[Any] = []
        if cursor:
            created_at, run_id = _decode_cursor(cursor)
            clauses.append("(created_at<? OR (created_at=? AND run_id<?))")
            parameters.extend((created_at, created_at, run_id))
        if surface:
            clauses.append("surface=?")
            parameters.append(surface)
        if status:
            clauses.append("status=?")
            parameters.append(status)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        conn = get_connection()
        try:
            _ensure_runtime_schema(conn)
            rows = conn.execute(
                f"SELECT * FROM mc_runs{where} ORDER BY created_at DESC,run_id DESC LIMIT ?",
                (*parameters, limit + 1),
            ).fetchall()
        finally:
            conn.close()
        page = rows[:limit]
        return {
            "items": [_run_summary(row) for row in page],
            "next_cursor": _cursor(page[-1]["created_at"], page[-1]["run_id"])
            if len(rows) > limit and page else None,
        }

    def get_run(self, run_id: str, *, after_sequence: int = 0) -> dict[str, Any]:
        if not isinstance(after_sequence, int) or after_sequence < 0:
            raise RunsViewValidationError("after_sequence must be non-negative")
        conn = get_connection()
        try:
            _ensure_runtime_schema(conn)
            run = conn.execute("SELECT * FROM mc_runs WHERE run_id=?", (run_id,)).fetchone()
            if run is None:
                raise KeyError(run_id)
            loop = conn.execute("SELECT * FROM mc_loop_runs WHERE run_id=?", (run_id,)).fetchone()
            steps = conn.execute(
                """SELECT step_id,position,kind,tool_name,risk,status,attempts,started_at,
                          completed_at,next_attempt_at FROM mc_run_steps
                   WHERE run_id=? ORDER BY position,step_id""",
                (run_id,),
            ).fetchall()
            eval_rows = conn.execute(
                """SELECT er.eval_run_id,er.eval_case_id,er.eval_case_version,er.status,
                          er.threshold,er.score,er.trace_id,er.evidence_refs_json,
                          er.started_at,er.completed_at,ec.category
                   FROM mc_eval_runs er JOIN mc_eval_cases ec
                     ON ec.eval_case_id=er.eval_case_id AND ec.version=er.eval_case_version
                   WHERE er.run_id=? ORDER BY COALESCE(er.completed_at,er.started_at,er.created_at),er.eval_run_id""",
                (run_id,),
            ).fetchall()
            capabilities = conn.execute(
                """SELECT entity_id,entity_type,canonical_key,name,status,version,source_ref,observed_at
                   FROM mc_system_entities WHERE entity_type='capability'
                   ORDER BY canonical_key LIMIT 100"""
            ).fetchall()
        finally:
            conn.close()
        events = list_run_events(run_id, after_sequence=after_sequence, limit=500)
        event_items = [{
            "event_id": event.event_id,
            "sequence": event.sequence,
            "event_type": event.event_type,
            "stage": event.stage,
            "actor": event.actor,
            "timestamp": event.timestamp,
            "trace_id": event.trace_id,
            "payload": _event_payload(event.redacted_payload),
        } for event in events]
        evaluations = []
        for row in eval_rows:
            item = dict(row)
            item["evidence_refs"] = json.loads(item.pop("evidence_refs_json"))[:50]
            evaluations.append(item)
        recovery = [
            {key: event[key] for key in ("event_id", "sequence", "event_type", "stage", "timestamp")}
            for event in event_items
            if any(marker in f"{event['event_type']} {event['stage']}".lower()
                   for marker in ("recover", "retry", "failed", "failure", "error", "blocked"))
        ]
        trace = build_run_trace(run_id).to_dict()
        latest = latest_run_event(run_id)
        return {
            "run": _run_summary(run),
            "loop": _loop_summary(loop),
            "steps": [dict(row) for row in steps],
            "events": event_items,
            "last_sequence": latest.sequence if latest else 0,
            "trace": trace,
            "evaluations": evaluations,
            "recovery": recovery,
            "context_refs": trace["context_refs"],
            "capabilities": [dict(row) for row in capabilities],
        }

    def list_loop_recipes(self) -> list[dict[str, Any]]:
        conn = get_connection()
        try:
            _ensure_runtime_schema(conn)
            rows = conn.execute(
                "SELECT recipe_id,version,name,loop_type,created_at FROM mc_loop_recipes ORDER BY name,recipe_id,version"
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def get_developer_loop_selection(self) -> dict[str, str] | None:
        conn = get_connection()
        try:
            _ensure_runtime_schema(conn)
            row = conn.execute(
                "SELECT value_json FROM mc_runtime_preferences WHERE preference_key=?",
                (_PREFERENCE_KEY,),
            ).fetchone()
            return json.loads(row["value_json"]) if row is not None else None
        finally:
            conn.close()

    def set_developer_loop_selection(
        self, recipe_id: str, version: str, *, actor: str = "owner"
    ) -> dict[str, str]:
        if not all(isinstance(value, str) and value.strip() for value in (recipe_id, version, actor)):
            raise RunsViewValidationError("recipe_id, version, and actor are required")
        value = {"recipe_id": recipe_id.strip(), "version": version.strip()}
        conn = get_connection()
        try:
            _ensure_runtime_schema(conn)
            exists = conn.execute(
                "SELECT 1 FROM mc_loop_recipes WHERE recipe_id=? AND version=?",
                (value["recipe_id"], value["version"]),
            ).fetchone()
            if exists is None:
                raise RunsViewValidationError("unknown loop recipe version")
            conn.execute(
                """INSERT INTO mc_runtime_preferences
                   (preference_key,value_json,value_hash,updated_at,updated_by)
                   VALUES (?,?,?,?,?)
                   ON CONFLICT(preference_key) DO UPDATE SET
                     value_json=excluded.value_json,value_hash=excluded.value_hash,
                     updated_at=excluded.updated_at,updated_by=excluded.updated_by""",
                (_PREFERENCE_KEY, _json(value), _hash(value), _now(), actor.strip()),
            )
            conn.commit()
            return value
        finally:
            conn.close()

"""Shared primitives for the Mission Control API surface.

Extracted from ``api/dashboard.py`` (refactor Slice 0) so that route groups
peeled into ``api/routers/*`` can import the same DB connection, JSON, and
formatting helpers without importing the dashboard module. Behavior is
identical to the original definitions — this is a pure move.

See ``docs/REFACTORING_PLAN.md``.
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException

# The SQLite database path. Read from the environment at import time so both the
# server (which loads .env) and direct CLI imports resolve consistently.
DB_PATH = os.path.expanduser(os.getenv("DB_PATH", "~/.mmo_agent/agent.db"))

# Repo-root/logs. Defined here (api/deps.py) so it resolves the same as when it
# lived in api/dashboard.py — both modules sit in api/, one level below the root.
LOGS_DIR = Path(__file__).parent.parent / "logs"


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _json_loads(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def _last(conn: sqlite3.Connection, query: str) -> str | None:
    """Scalar helper: first column of the first row, or None. Shared by agents,
    abilities, and health 'last active' readouts."""
    try:
        row = conn.execute(query).fetchone()
        return row[0] if row and row[0] else None
    except sqlite3.Error:
        return None


def fmt_ago(ts_str: str | None) -> str | None:
    """Human-readable 'time ago' from an ISO timestamp. Shared by /api/agents + /api/health."""
    if not ts_str:
        return None
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc) if dt.tzinfo else datetime.now()
        delta = now - dt
        mins = int(delta.total_seconds() / 60)
        if mins < 1:
            return "just now"
        if mins < 60:
            return f"{mins}m ago"
        hours = mins // 60
        if hours < 24:
            return f"{hours}h ago"
        return f"{hours // 24}d ago"
    except Exception:
        return ts_str


def _vault_guard(token: str | None) -> None:
    """Require an unlocked vault session for protected endpoints. Shared by the vault,
    integrations, keys, and llm-key routes (lifted from dashboard.py so those groups
    can move into api/routers/* without importing the dashboard module)."""
    from core import vault
    if not vault.CRYPTO_AVAILABLE:
        raise HTTPException(status_code=503, detail="Vault unavailable — 'cryptography' is not installed.")
    try:
        vault.require_session(token)
    except vault.VaultLocked as e:
        raise HTTPException(status_code=401, detail=str(e))


# ── Task / activity serialization + counters (lifted from dashboard.py so the
# pm and tasks route groups can share them without importing the dashboard module).

def _legacy_status_from_v1(status_v1: str) -> str:
    return {
        "planned": "pending",
        "in_progress": "in_progress",
        "paused": "blocked",
        "blocked": "blocked",
        "needs_owner_input": "pending",
        "done": "done",
        "cancelled": "skipped",
    }.get(status_v1, "pending")


def _append_activity(conn: sqlite3.Connection, task_id: int, activity_type: str, author: str, message: str, payload: dict[str, Any] | None = None) -> None:
    conn.execute(
        """
        INSERT INTO task_activity (task_id, activity_type, author, message, payload)
        VALUES (?, ?, ?, ?, ?)
        """,
        (task_id, activity_type, author, message, json.dumps(payload or {}, ensure_ascii=False)),
    )


def _fetch_activity(conn: sqlite3.Connection, task_id: int, limit: int = 100) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, activity_type, author, message, payload, created_at
        FROM task_activity
        WHERE task_id=?
        ORDER BY created_at DESC, id DESC
        LIMIT ?
        """,
        (task_id, limit),
    ).fetchall()
    activity = []
    for row in rows:
        payload = _json_loads(row["payload"], {})
        activity.append({
            "id": row["id"],
            "type": row["activity_type"],
            "author": row["author"],
            "message": row["message"],
            "payload": payload,
            "created_at": row["created_at"],
        })
    return list(reversed(activity))


def _fetch_checklist(conn: sqlite3.Connection, task_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT item_key, label, input_type, required, placeholder, value_text, file_path, status, updated_at
        FROM task_owner_inputs
        WHERE task_id=?
        ORDER BY id ASC
        """,
        (task_id,),
    ).fetchall()
    result = []
    for row in rows:
        result.append({
            "item_key": row["item_key"],
            "label": row["label"],
            "input_type": row["input_type"],
            "required": bool(row["required"]),
            "placeholder": row["placeholder"],
            "value_text": row["value_text"],
            "file_path": row["file_path"],
            "status": row["status"],
            "updated_at": row["updated_at"],
        })
    return result


def _serialize_task(conn: sqlite3.Connection, row: sqlite3.Row, include_activity: bool = True) -> dict[str, Any]:
    due_at = row["due_at"]
    is_overdue = False
    if due_at and row["status_v1"] not in {"done", "cancelled"}:
        try:
            is_overdue = datetime.fromisoformat(due_at.replace("Z", "+00:00")) < datetime.now(timezone.utc)
        except Exception:
            is_overdue = False

    task = {
        "id": row["id"],
        "title": row["title"],
        "objective": row["objective"] or row["description"] or row["title"],
        "success_criteria": row["success_criteria"],
        "description": row["description"],
        "status": row["status_v1"],
        "priority": row["priority_label"] or "P2",
        "owner": row["owner_label"] or "owner",
        "agent": row["agent_key"] or "tobi",
        "project_id": row["project_id"],
        "project_name": row["project_name"],
        "task_type": row["task_type"],
        "due_at": due_at,
        "start_at": row["start_at"] if "start_at" in row.keys() else None,
        "reminder_at": row["reminder_at"] if "reminder_at" in row.keys() else None,
        "is_overdue": is_overdue,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"] or row["created_at"],
        "started_at": row["started_at"],
        "completed_at": row["completed_at"],
        "sort_order": row["sort_order"] if "sort_order" in row.keys() else None,
        "artifacts": _json_loads(row["artifacts_json"], []),
        "risk_flags": _json_loads(row["risk_flags_json"], []),
        "checklist": _fetch_checklist(conn, row["id"]),
        # PM fields (present when task belongs to a PM project)
        "sub_tasks": _json_loads(
            row["sub_tasks_json"] if "sub_tasks_json" in row.keys() else None, []
        ),
        "time_estimate": row["time_estimate"] if "time_estimate" in row.keys() else None,
        "pm_project_id": row["pm_project_id"] if "pm_project_id" in row.keys() else None,
        "pm_goal_id": row["pm_goal_id"] if "pm_goal_id" in row.keys() else None,
        # v2 dependencies (blocks / blocked-by), best-effort
        "blocks": _task_deps(conn, row["id"], "blocks"),
        "blocked_by": _task_deps(conn, row["id"], "blocked_by"),
    }
    if include_activity:
        task["activity"] = _fetch_activity(conn, row["id"])
    return task


def _task_deps(conn: sqlite3.Connection, task_id: int, direction: str) -> list[int]:
    """IDs this task blocks (direction='blocks') or is blocked by (='blocked_by')."""
    try:
        if direction == "blocks":
            rows = conn.execute("SELECT blocks_id FROM pm_task_deps WHERE task_id=?", (task_id,)).fetchall()
        else:
            rows = conn.execute("SELECT task_id FROM pm_task_deps WHERE blocks_id=?", (task_id,)).fetchall()
        return [r[0] for r in rows]
    except Exception:
        return []


def _fetch_task_row(conn: sqlite3.Connection, task_id: int) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT t.*, COALESCE(p.name, pmp.name) AS project_name
        FROM tasks t
        LEFT JOIN projects p ON p.id = t.project_id
        LEFT JOIN pm_projects pmp ON pmp.id = t.pm_project_id
        WHERE t.id=? AND t.deleted_at IS NULL
        """,
        (task_id,),
    ).fetchone()


def _count(conn: sqlite3.Connection, query: str, params: tuple = ()) -> int:
    try:
        row = conn.execute(query, params).fetchone()
        return int(row[0]) if row and row[0] is not None else 0
    except sqlite3.Error:
        return 0

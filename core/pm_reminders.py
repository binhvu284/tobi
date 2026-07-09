"""Project v2 (#12 v1.1) — task reminders.

A scheduler job (``main.py``, every ~2 min) calls :func:`fire_due_reminders`:
it finds tasks whose ``reminder_at`` has passed and haven't fired yet, marks
them fired (``reminder_fired_at``), and returns them so the caller can push a
Telegram alert. Idempotent and cheap.
"""
from __future__ import annotations

from datetime import datetime, timezone

from core.database import get_connection


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def fire_due_reminders() -> list[dict]:
    """Return due reminder rows and mark them fired.

    Each row: ``{task_id, title, project_id, project_name, reminder_at, due_at}``.
    Safe to call repeatedly — a task fires exactly once.
    """
    conn = get_connection()
    try:
        now = _now_iso()
        rows = conn.execute(
            """SELECT t.id, t.title, t.reminder_at, t.due_at, t.pm_project_id,
                      p.name AS project_name
               FROM tasks t
               LEFT JOIN pm_projects p ON p.id = t.pm_project_id
               WHERE t.reminder_at IS NOT NULL
                 AND t.reminder_at <= ?
                 AND t.reminder_fired_at IS NULL
                 AND t.status NOT IN ('done','skipped','cancelled')""", (now,)).fetchall()
        if not rows:
            return []
        fired = _now_iso()
        conn.executemany(
            "UPDATE tasks SET reminder_fired_at=? WHERE id=?",
            [(fired, r["id"]) for r in rows])
        conn.commit()
        return [{
            "task_id": r["id"],
            "title": r["title"] or "(untitled task)",
            "project_id": r["pm_project_id"],
            "project_name": r["project_name"] or "Projects",
            "reminder_at": r["reminder_at"],
            "due_at": r["due_at"],
        } for r in rows]
    finally:
        conn.close()

"""Tasks V1 schema (task/owner-input/activity tables).

Extracted verbatim from core/database.py (Phase 4b) — see core/schema/base.py.
"""
from __future__ import annotations

import sqlite3

from core.schema.base import _ensure_column

def _ensure_task_v1_schema(conn: sqlite3.Connection) -> None:
    _ensure_column(conn, "tasks", "status_v1", "TEXT")
    _ensure_column(conn, "tasks", "priority_label", "TEXT")
    _ensure_column(conn, "tasks", "owner_label", "TEXT DEFAULT 'owner'")
    _ensure_column(conn, "tasks", "agent_key", "TEXT DEFAULT 'tobi'")
    _ensure_column(conn, "tasks", "objective", "TEXT")
    _ensure_column(conn, "tasks", "success_criteria", "TEXT")
    _ensure_column(conn, "tasks", "due_at", "DATETIME")
    _ensure_column(conn, "tasks", "started_at", "DATETIME")
    _ensure_column(conn, "tasks", "updated_at", "DATETIME")
    _ensure_column(conn, "tasks", "checklist_json", "TEXT")
    _ensure_column(conn, "tasks", "artifacts_json", "TEXT")
    _ensure_column(conn, "tasks", "risk_flags_json", "TEXT")
    _ensure_column(conn, "tasks", "deleted_at", "DATETIME")
    _ensure_column(conn, "tasks", "sort_order", "REAL")

    conn.executescript("""
    CREATE TABLE IF NOT EXISTS task_activity (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id       INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
        activity_type TEXT NOT NULL,
        author        TEXT NOT NULL,
        message       TEXT NOT NULL,
        payload       TEXT,
        created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS task_owner_inputs (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id       INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
        item_key      TEXT NOT NULL,
        label         TEXT NOT NULL,
        input_type    TEXT NOT NULL,
        required      INTEGER DEFAULT 1,
        placeholder   TEXT,
        value_text    TEXT,
        file_path     TEXT,
        status        TEXT DEFAULT 'pending',
        created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(task_id, item_key)
    );

    CREATE INDEX IF NOT EXISTS idx_task_activity_task ON task_activity(task_id, created_at);
    CREATE INDEX IF NOT EXISTS idx_task_owner_inputs_task ON task_owner_inputs(task_id, status);
    """)

    conn.execute(
        """
        UPDATE tasks
           SET status_v1 = CASE status
               WHEN 'pending' THEN 'planned'
               WHEN 'in_progress' THEN 'in_progress'
               WHEN 'done' THEN 'done'
               WHEN 'blocked' THEN 'blocked'
               WHEN 'skipped' THEN 'cancelled'
               ELSE COALESCE(status_v1, 'planned')
           END
         WHERE status_v1 IS NULL OR status_v1 = ''
        """
    )

    conn.execute(
        """
        UPDATE tasks
           SET priority_label = CASE
               WHEN priority <= 2 THEN 'P0'
               WHEN priority <= 4 THEN 'P1'
               WHEN priority <= 7 THEN 'P2'
               ELSE 'P3'
           END
         WHERE priority_label IS NULL OR priority_label = ''
        """
    )

    conn.execute("UPDATE tasks SET owner_label='owner' WHERE owner_label IS NULL OR owner_label=''")
    conn.execute("UPDATE tasks SET agent_key='tobi' WHERE agent_key IS NULL OR agent_key=''")
    conn.execute("UPDATE tasks SET objective=COALESCE(objective, description, title)")
    conn.execute("UPDATE tasks SET updated_at=COALESCE(updated_at, created_at)")
    conn.execute("UPDATE tasks SET sort_order=CAST(id AS REAL) WHERE sort_order IS NULL")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status_sort ON tasks(status_v1, sort_order)")

"""Projects module schema (#12 PM + PM V2).

Extracted verbatim from core/database.py (Phase 4b) — see core/schema/base.py.
"""
from __future__ import annotations

import sqlite3

from core.schema.base import _ensure_column

def _ensure_pm_schema(conn: sqlite3.Connection) -> None:
    """Project Management module tables (pm_* prefix to avoid collision with MMO portfolio)."""
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS pm_projects (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        name          TEXT    NOT NULL,
        description   TEXT,
        status        TEXT    NOT NULL DEFAULT 'idea',
        size          TEXT    NOT NULL DEFAULT 'medium',
        category      TEXT,
        emoji_icon    TEXT    DEFAULT '📁',
        accent_color  TEXT    DEFAULT '#58a6ff',
        deadline      TEXT,
        kpi_mode      TEXT,
        kpi_id        TEXT,
        kpi_metric_name   TEXT,
        kpi_target_value  REAL,
        kpi_current_value REAL    DEFAULT 0,
        progress_pct  REAL    DEFAULT 0,
        template_id   INTEGER,
        created_by    TEXT    DEFAULT 'user',
        created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at    DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS pm_goals (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id    INTEGER NOT NULL REFERENCES pm_projects(id) ON DELETE CASCADE,
        title         TEXT    NOT NULL,
        metric_name   TEXT,
        target_value  REAL    NOT NULL DEFAULT 100,
        current_value REAL    NOT NULL DEFAULT 0,
        due_date      TEXT,
        owner         TEXT    DEFAULT 'user',
        created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at    DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS pm_missions (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id    INTEGER NOT NULL REFERENCES pm_projects(id) ON DELETE CASCADE,
        prompt        TEXT    NOT NULL,
        status        TEXT    NOT NULL DEFAULT 'queued',
        output        TEXT,
        tasks_created INTEGER DEFAULT 0,
        docs_created  INTEGER DEFAULT 0,
        duration_ms   INTEGER,
        created_by    TEXT    DEFAULT 'user',
        created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
        completed_at  DATETIME
    );

    CREATE TABLE IF NOT EXISTS pm_activity (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id    INTEGER NOT NULL REFERENCES pm_projects(id) ON DELETE CASCADE,
        actor         TEXT    NOT NULL DEFAULT 'user',
        action_type   TEXT    NOT NULL,
        summary       TEXT    NOT NULL,
        diff          TEXT,
        created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS pm_files (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id    INTEGER NOT NULL REFERENCES pm_projects(id) ON DELETE CASCADE,
        filename      TEXT    NOT NULL,
        file_path     TEXT,
        file_size     INTEGER,
        mime_type     TEXT,
        uploaded_by   TEXT    DEFAULT 'user',
        created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS pm_templates (
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        name              TEXT NOT NULL,
        description       TEXT,
        source_project_id INTEGER,
        snapshot          TEXT NOT NULL DEFAULT '{}',
        created_at        DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS idx_pm_goals_project    ON pm_goals(project_id);
    CREATE INDEX IF NOT EXISTS idx_pm_missions_project ON pm_missions(project_id, created_at);
    CREATE INDEX IF NOT EXISTS idx_pm_activity_project ON pm_activity(project_id, created_at);
    CREATE INDEX IF NOT EXISTS idx_pm_files_project    ON pm_files(project_id);
    CREATE INDEX IF NOT EXISTS idx_pm_projects_status  ON pm_projects(status);
    """)

    # Extend tasks table with PM linkage columns
    _ensure_column(conn, "tasks", "pm_project_id", "INTEGER REFERENCES pm_projects(id) ON DELETE SET NULL")
    _ensure_column(conn, "tasks", "pm_goal_id",    "INTEGER REFERENCES pm_goals(id) ON DELETE SET NULL")
    _ensure_column(conn, "tasks", "time_estimate", "TEXT")
    _ensure_column(conn, "tasks", "sub_tasks_json","TEXT DEFAULT '[]'")

    # Manual drag-to-reorder on the Projects board (lower sort_order = earlier). Seed the
    # initial order to the existing "most-recently-updated first" so nothing visibly moves.
    _ensure_column(conn, "pm_projects", "sort_order", "REAL")
    conn.execute(
        "UPDATE pm_projects SET sort_order = ("
        "  SELECT COUNT(*) FROM pm_projects p2"
        "  WHERE p2.updated_at > pm_projects.updated_at"
        "     OR (p2.updated_at = pm_projects.updated_at AND p2.id > pm_projects.id)"
        ") WHERE sort_order IS NULL"
    )

    # v2: Goals get description, priority, and one-level sub-goal nesting.
    _ensure_column(conn, "pm_goals", "description",    "TEXT")
    _ensure_column(conn, "pm_goals", "priority",       "TEXT DEFAULT 'medium'")
    _ensure_column(conn, "pm_goals", "parent_goal_id", "INTEGER REFERENCES pm_goals(id) ON DELETE CASCADE")

    _ensure_pm_v2_schema(conn)


def _ensure_pm_v2_schema(conn: sqlite3.Connection) -> None:
    """Project v2 (#12): full-page workspace — richer tasks, a real Resources drive
    (disk-backed files + online links + folders + tags), custom project icons, task
    dependencies, and optional goal↔task rollups. Idempotent; extends the PM system."""
    # Projects: custom icon (emoji | icon-pack key | custom-upload ref) + cached resources size.
    _ensure_column(conn, "pm_projects", "icon_type",       "TEXT DEFAULT 'emoji'")   # emoji | icon | custom
    _ensure_column(conn, "pm_projects", "icon_value",      "TEXT")                    # emoji char / icon key / pm_icons id
    _ensure_column(conn, "pm_projects", "resources_bytes", "INTEGER DEFAULT 0")

    # Tasks: optional start + reminder (due_at/description/time_estimate/sub_tasks_json already exist).
    _ensure_column(conn, "tasks", "start_at",    "TEXT")
    _ensure_column(conn, "tasks", "reminder_at", "TEXT")
    _ensure_column(conn, "tasks", "reminder_fired_at", "TEXT")   # set when a reminder has been pushed

    conn.executescript("""
    -- Folders for the Drive-style Resources tab (one level of nesting via parent_id).
    CREATE TABLE IF NOT EXISTS pm_folders (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id  INTEGER NOT NULL REFERENCES pm_projects(id) ON DELETE CASCADE,
        parent_id   INTEGER REFERENCES pm_folders(id) ON DELETE CASCADE,
        name        TEXT    NOT NULL,
        created_by  TEXT    DEFAULT 'user',
        created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    -- Resources = disk-backed files OR online links, tracked by Storage #10.
    CREATE TABLE IF NOT EXISTS pm_resources (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id   INTEGER NOT NULL REFERENCES pm_projects(id) ON DELETE CASCADE,
        folder_id    INTEGER REFERENCES pm_folders(id) ON DELETE SET NULL,
        kind         TEXT    NOT NULL DEFAULT 'file',   -- file | link
        name         TEXT    NOT NULL,
        ext          TEXT,                              -- pdf|docx|md|png|… (files)
        source       TEXT    DEFAULT 'device',          -- device|url|drive|youtube|web|github|pdf
        rtype        TEXT    DEFAULT 'file',            -- file|doc|sheet|slides|image|video|pdf|link|youtube|github|web
        size_bytes   INTEGER DEFAULT 0,
        disk_path    TEXT,                              -- relative to the resources root (files)
        url          TEXT,                              -- external URL (links)
        mime         TEXT,
        thumb        TEXT,
        text_content TEXT,                              -- extracted text for search/RAG (transcripts, doc text)
        tags         TEXT    DEFAULT '[]',              -- JSON array
        created_by   TEXT    DEFAULT 'user',            -- user | tobi
        created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at   DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    -- Task dependencies: task_id is blocked-by blocks_id (both directions derivable).
    CREATE TABLE IF NOT EXISTS pm_task_deps (
        task_id    INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
        blocks_id  INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
        PRIMARY KEY (task_id, blocks_id)
    );

    -- Optional goal↔task link for rollup-mode goals.
    CREATE TABLE IF NOT EXISTS pm_goal_tasks (
        goal_id  INTEGER NOT NULL REFERENCES pm_goals(id) ON DELETE CASCADE,
        task_id  INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
        PRIMARY KEY (goal_id, task_id)
    );

    -- Custom uploaded project icons (small, capped, stored in the DB so they travel with backups).
    CREATE TABLE IF NOT EXISTS pm_icons (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id  INTEGER REFERENCES pm_projects(id) ON DELETE CASCADE,
        mime        TEXT    NOT NULL DEFAULT 'image/png',
        data        TEXT    NOT NULL,                   -- base64 (dimension-capped upstream)
        created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    -- Per-project content RAG: chunked resource text + embeddings (fastembed, optional).
    CREATE TABLE IF NOT EXISTS pm_resource_chunks (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        resource_id  INTEGER NOT NULL REFERENCES pm_resources(id) ON DELETE CASCADE,
        project_id   INTEGER NOT NULL REFERENCES pm_projects(id) ON DELETE CASCADE,
        ordinal      INTEGER DEFAULT 0,
        chunk_text   TEXT    NOT NULL,
        embedding    BLOB,
        embed_model  TEXT,
        created_at   DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS idx_pm_folders_project   ON pm_folders(project_id, parent_id);
    CREATE INDEX IF NOT EXISTS idx_pm_resources_project ON pm_resources(project_id, folder_id);
    CREATE INDEX IF NOT EXISTS idx_pm_task_deps_task    ON pm_task_deps(task_id);
    CREATE INDEX IF NOT EXISTS idx_pm_task_deps_blocks  ON pm_task_deps(blocks_id);
    CREATE INDEX IF NOT EXISTS idx_pm_goal_tasks_goal   ON pm_goal_tasks(goal_id);
    CREATE INDEX IF NOT EXISTS idx_pm_chunks_resource   ON pm_resource_chunks(resource_id);
    CREATE INDEX IF NOT EXISTS idx_pm_chunks_project    ON pm_resource_chunks(project_id);
    """)

    # Goals gain a mode: 'metric' (current/target) or 'task' (rollup from linked tasks).
    _ensure_column(conn, "pm_goals", "mode", "TEXT DEFAULT 'metric'")

    # Migrate legacy pm_files (filename/URL-only "Docs") → Resource link items, once.
    try:
        have_files = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='pm_files'").fetchone()
        if have_files:
            rows = conn.execute(
                "SELECT f.* FROM pm_files f WHERE NOT EXISTS ("
                "  SELECT 1 FROM pm_resources r WHERE r.project_id=f.project_id AND r.name=f.filename)"
            ).fetchall()
            for f in rows:
                fn = f["filename"] or "file"
                is_url = isinstance(fn, str) and fn.startswith(("http://", "https://"))
                conn.execute(
                    "INSERT INTO pm_resources (project_id, kind, name, source, rtype, url, created_by, created_at) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (f["project_id"], "link", fn, "url" if is_url else "device",
                     "link" if is_url else "file", fn if is_url else None,
                     f["uploaded_by"] or "user", f["created_at"]),
                )
    except Exception:
        pass  # migration is best-effort; never block startup

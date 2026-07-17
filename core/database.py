"""
DATABASE MANAGER - MMO Agent System
=====================================
Quản lý toàn bộ dữ liệu: projects, tasks, revenue, lessons, strategy
Dùng SQLite - không cần server, lưu local, backup dễ dàng

DB path: ~/.mmo_agent/agent.db (configurable qua DB_PATH env var)
"""

import sqlite3
import json
import os
from datetime import datetime
from typing import Optional

DB_PATH = os.path.expanduser(
    os.getenv("DB_PATH", "~/.mmo_agent/agent.db")
)


# ─────────────────────────────────────────
# Connection
# ─────────────────────────────────────────

def get_connection() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row  # dict-like rows
    conn.execute("PRAGMA foreign_keys = ON")
    # WAL + busy_timeout: lets readers and a writer coexist and makes concurrent writers
    # wait instead of raising "database is locked" (engines nest short-lived connections).
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 8000")
    return conn


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {r[1] for r in rows}


def _ensure_column(conn: sqlite3.Connection, table: str, name: str, ddl: str) -> None:
    if name in _table_columns(conn, table):
        return
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")


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


# ─────────────────────────────────────────
# Skill registry (Mission Control — Ability module)
# Spec §3.2/§5.2: unified 4-layer skill model + metrics + deps + version
# ledger + proposals inbox. H12: in Phase 1 (no Hermes) MC holds the skill
# body here; Phase 1.5 flips the body source-of-truth to the Hermes .md and
# this row becomes metadata keyed by name.
# ─────────────────────────────────────────

# id, name, category, tier, layer, risk_tier — registry metadata only.
# Curated power dims + copy live in the frontend (dashboard/src/pages/Ability.tsx).
_SEED_SKILLS = [
    ("chat",         "Chat Assistant",   "Communication", "core",         "L1", "low"),
    ("reports",      "Daily Reports",    "Communication", "core",         "L3", "low"),
    ("telegram",     "Telegram Interface","Communication","core",         "L4", "low"),
    ("coding",       "Coding Agent",     "Building",      "core",         "L2", "high"),
    ("terminal",     "Terminal",         "Building",      "learned",      "L2", "high"),
    ("integrations", "Integrations",     "Building",      "core",         "L4", "high"),
    ("executor",     "Project Executor", "Building",      "core",         "L3", "high"),
    ("research",     "Research Engine",  "Strategy",      "core",         "L3", "low"),
    ("ceo",          "CEO Strategy",     "Strategy",      "core",         "L3", "low"),
    ("tracker",      "Project Tracker",  "Strategy",      "core",         "L1", "low"),
    ("learning",     "Self-Learning",    "Learning",      "core",         "L3", "low"),
    ("memory",       "Memory",           "Learning",      "core",         "L4", "low"),
]


def _ensure_skill_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
    -- ── SKILLS (L1 record / registry metadata) ────────
    CREATE TABLE IF NOT EXISTS skills (
        id            TEXT    PRIMARY KEY,        -- skill key (matches Ability usageKey)
        name          TEXT    NOT NULL,
        category      TEXT,                       -- Communication | Building | Strategy | Learning
        layer         TEXT    DEFAULT 'L1',       -- L1 | L2 | L3 | L4
        tier          TEXT    DEFAULT 'core',     -- core | learned | experimental
        instructions  TEXT,                       -- L1 body (Phase 1 only; H12 flips to Hermes .md)
        tools_json    TEXT,
        model         TEXT,
        status        TEXT    DEFAULT 'active',    -- active | archived
        risk_tier     TEXT    DEFAULT 'low',       -- low | high
        version       INTEGER DEFAULT 1,           -- current active version pointer
        created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at    DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    -- ── SKILL_METRICS (live measured; D44/D45) ────────
    CREATE TABLE IF NOT EXISTS skill_metrics (
        skill_id       TEXT    PRIMARY KEY REFERENCES skills(id) ON DELETE CASCADE,
        runs           INTEGER DEFAULT 0,
        successes      INTEGER DEFAULT 0,
        last_run_at    DATETIME,
        avg_latency_ms REAL,
        token_volume   INTEGER DEFAULT 0
    );

    -- ── SKILL_DEPS (L3 composition edges; D50) ────────
    CREATE TABLE IF NOT EXISTS skill_deps (
        parent_id      TEXT NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
        child_id       TEXT NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
        pinned_version INTEGER,
        PRIMARY KEY (parent_id, child_id)
    );

    -- ── SKILL_VERSIONS (keep-all ledger; D54/H15) ─────
    CREATE TABLE IF NOT EXISTS skill_versions (
        id                   INTEGER PRIMARY KEY AUTOINCREMENT,
        skill_id             TEXT    NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
        version              INTEGER NOT NULL,
        body                 TEXT,
        diff_summary         TEXT,
        metric_snapshot_json TEXT,
        provenance_json      TEXT,
        created_at           DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(skill_id, version)
    );

    -- ── SKILL_PROPOSALS (approval inbox; D13/D48/D20) ─
    CREATE TABLE IF NOT EXISTS skill_proposals (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        skill_id      TEXT    REFERENCES skills(id) ON DELETE SET NULL,
        kind          TEXT    NOT NULL,            -- create | edit | promote
        risk_tier     TEXT    DEFAULT 'low',       -- low | high
        title         TEXT,
        payload_json  TEXT,
        status        TEXT    DEFAULT 'pending',   -- pending | approved | rejected
        rationale     TEXT,
        created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
        resolved_at   DATETIME
    );

    CREATE INDEX IF NOT EXISTS idx_skill_versions_skill ON skill_versions(skill_id, version);
    CREATE INDEX IF NOT EXISTS idx_skill_proposals_status ON skill_proposals(status, created_at);
    """)

    # Seed the curated roster once (idempotent — only when empty).
    have = conn.execute("SELECT COUNT(*) FROM skills").fetchone()[0]
    if not have:
        for sid, name, category, tier, layer, risk in _SEED_SKILLS:
            conn.execute(
                """INSERT INTO skills (id, name, category, tier, layer, risk_tier, version)
                   VALUES (?, ?, ?, ?, ?, ?, 1)""",
                (sid, name, category, tier, layer, risk),
            )
            conn.execute(
                "INSERT OR IGNORE INTO skill_metrics (skill_id) VALUES (?)", (sid,)
            )
            conn.execute(
                """INSERT INTO skill_versions (skill_id, version, body, diff_summary, provenance_json)
                   VALUES (?, 1, ?, 'Seeded baseline', ?)""",
                (sid, "", json.dumps({"actor": "seed", "trigger": "init"})),
            )


# ─────────────────────────────────────────
# The Office (Mission Control — Module 2)
# Spec §4/§5.2: agent registry + missions + steps + versioned workflows +
# per-agent/mission/provider LLM usage. D37: model config references env-var
# key *names* only (never the secret). MC orchestrates; Hermes is one
# participant (the head agent's brain), per H17/H18.
# ─────────────────────────────────────────

# id, name, role, persona, provider, model, key_ref(env NAME), color, sprite,
# autonomy, can_spawn, is_head. D60 seed roster — all editable in the UI.
_SEED_AGENTS = [
    # id,        name,       role,                provider,     model,                        key_ref,             color,     sprite,     autonomy, can_spawn, is_head
    ("tobi",     "Tobi",     "Head / Orchestrator","anthropic",  "claude-opus-4-20250514",     "ANTHROPIC_API_KEY", "#58a6ff", "tobi",     "high",   1,         1),
    ("sunday",   "Sunday",   "Research",          "openrouter", "google/gemini-pro-3",        "OPENROUTER_API_KEY","#3fb950", "research", "medium", 0,         0),
    ("alphabet", "Alphabet", "Evaluator",         "openai",     "gpt-5.5",                    "OPENAI_API_KEY",    "#d29922", "ceo",      "medium", 0,         0),
    ("friday",   "Friday",   "Coder",             "anthropic",  "claude-opus-4-20250514",     "ANTHROPIC_API_KEY", "#8b5cf6", "coder",    "medium", 0,         0),
]

# Default linear delivery workflow (D30/D60): Sunday → Alphabet → Friday.
_SEED_WORKFLOW = {
    "name": "standard_delivery",
    "version": 1,
    "steps": [
        {"agent_id": "sunday",   "action": "research"},
        {"agent_id": "alphabet", "action": "evaluate"},
        {"agent_id": "friday",   "action": "build"},
    ],
}


def _ensure_office_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
    -- ── AGENTS (persona + model binding + perms; D22/D25/D26) ──
    CREATE TABLE IF NOT EXISTS agents (
        id                  TEXT    PRIMARY KEY,    -- agent key
        name                TEXT    NOT NULL,
        role                TEXT,
        persona             TEXT,
        provider            TEXT    DEFAULT 'openrouter',  -- openrouter|anthropic|openai|google|mock
        model               TEXT,
        key_ref             TEXT,                   -- env var NAME holding the API key (D37 — name only)
        temperature         REAL    DEFAULT 0.7,
        max_tokens          INTEGER DEFAULT 2000,
        autonomy            TEXT    DEFAULT 'medium',     -- low|medium|high (D25)
        can_spawn           INTEGER DEFAULT 0,             -- reserved for head (D68)
        daily_budget_tokens INTEGER DEFAULT 0,             -- 0 = unlimited
        skills_json         TEXT,                          -- list of skill ids
        perms_json          TEXT,                          -- tools/permissions
        color               TEXT,
        sprite              TEXT,                          -- scene character key
        is_head             INTEGER DEFAULT 0,
        status              TEXT    DEFAULT 'active',       -- active|archived
        created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at          DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    -- ── AGENT_STATE (runtime; D64) ────────────────────────────
    CREATE TABLE IF NOT EXISTS agent_state (
        agent_id            TEXT    PRIMARY KEY REFERENCES agents(id) ON DELETE CASCADE,
        runtime_status      TEXT    DEFAULT 'idle',         -- idle|working|online|offline
        current_mission_id  INTEGER,
        detail              TEXT,
        last_active_at      DATETIME
    );

    -- ── WORKFLOWS (named, versioned; D61) ─────────────────────
    CREATE TABLE IF NOT EXISTS workflows (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        name            TEXT    NOT NULL,
        version         INTEGER NOT NULL DEFAULT 1,
        definition_json TEXT,                               -- ordered steps / DAG
        is_active       INTEGER DEFAULT 1,
        created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(name, version)
    );

    -- ── MISSIONS (D64/D57/D61/D69) ────────────────────────────
    CREATE TABLE IF NOT EXISTS missions (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        title            TEXT    NOT NULL,
        goal             TEXT,
        status           TEXT    DEFAULT 'planned',         -- planned|running|blocked|done|cancelled
        priority         TEXT    DEFAULT 'Normal',          -- Low|Normal|High|Urgent (D57)
        workflow_id      INTEGER REFERENCES workflows(id),
        workflow_version INTEGER,                            -- pinned at run (D61)
        summary          TEXT,                               -- Tobi close-out (D69)
        cost_tokens      INTEGER DEFAULT 0,
        created_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
        started_at       DATETIME,
        completed_at     DATETIME
    );

    -- ── MISSION_STEPS (D64/D67) ───────────────────────────────
    CREATE TABLE IF NOT EXISTS mission_steps (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        mission_id    INTEGER NOT NULL REFERENCES missions(id) ON DELETE CASCADE,
        seq           INTEGER NOT NULL,
        agent_id      TEXT    REFERENCES agents(id),
        action        TEXT,
        status        TEXT    DEFAULT 'pending',            -- pending|running|done|failed
        input         TEXT,
        output        TEXT,
        artifact_ref  TEXT,                                 -- ~/.mmo_agent/artifacts/{mission}/… (D67)
        tokens        INTEGER DEFAULT 0,
        started_at    DATETIME,
        completed_at  DATETIME
    );

    -- ── LLM_USAGE (per-agent/mission/provider; D34) ───────────
    CREATE TABLE IF NOT EXISTS llm_usage (
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        agent_id          TEXT,
        mission_id        INTEGER,
        provider          TEXT,
        model             TEXT,
        prompt_tokens     INTEGER DEFAULT 0,
        completion_tokens INTEGER DEFAULT 0,
        total_tokens      INTEGER DEFAULT 0,
        cost              REAL    DEFAULT 0,
        created_at        DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS idx_mission_steps_mission ON mission_steps(mission_id, seq);
    CREATE INDEX IF NOT EXISTS idx_llm_usage_mission ON llm_usage(mission_id);
    CREATE INDEX IF NOT EXISTS idx_missions_status ON missions(status, priority);
    """)

    # Seed roster once (idempotent).
    if not conn.execute("SELECT COUNT(*) FROM agents").fetchone()[0]:
        for (aid, name, role, provider, model, key_ref, color, sprite, autonomy, can_spawn, is_head) in _SEED_AGENTS:
            conn.execute(
                """INSERT INTO agents (id, name, role, provider, model, key_ref, color, sprite,
                                       autonomy, can_spawn, is_head)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (aid, name, role, provider, model, key_ref, color, sprite, autonomy, can_spawn, is_head),
            )
            conn.execute(
                "INSERT OR IGNORE INTO agent_state (agent_id, runtime_status) VALUES (?, 'idle')", (aid,)
            )

    # Seed default workflow once.
    if not conn.execute("SELECT COUNT(*) FROM workflows").fetchone()[0]:
        conn.execute(
            "INSERT INTO workflows (name, version, definition_json, is_active) VALUES (?,?,?,1)",
            (_SEED_WORKFLOW["name"], _SEED_WORKFLOW["version"], json.dumps(_SEED_WORKFLOW["steps"])),
        )


# ─────────────────────────────────────────
# Schema Init
# ─────────────────────────────────────────

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


def _ensure_brain_schema(conn: sqlite3.Connection) -> None:
    """Brain: long-term owner memory (auto-learn + import + psychology profile).

    Idempotent. Source of truth for the Brain feature; embeddings stored as BLOB
    (numpy float32) on each memory for local semantic search / dedup.
    """
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS brain_categories (
        id          TEXT PRIMARY KEY,          -- slug
        label       TEXT NOT NULL,
        color       TEXT DEFAULT '#58a6ff',
        icon        TEXT DEFAULT 'Brain',
        sort_order  INTEGER DEFAULT 0,
        sensitive   INTEGER DEFAULT 0,         -- 1 = always route to review
        status      TEXT DEFAULT 'approved',   -- approved | pending (TOBI-proposed)
        created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS brain_memories (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        content          TEXT NOT NULL,
        category         TEXT DEFAULT 'identity',
        confidence       REAL DEFAULT 0.6,
        source           TEXT DEFAULT 'manual',   -- manual | auto | import | remember
        status           TEXT DEFAULT 'active',   -- active | pending | archived | superseded
        context          TEXT,                    -- where it was learned
        embedding        BLOB,
        embed_model      TEXT,
        created_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
        last_confirmed_at DATETIME,
        deleted_at       DATETIME
    );

    CREATE TABLE IF NOT EXISTS brain_memory_versions (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        memory_id   INTEGER REFERENCES brain_memories(id) ON DELETE CASCADE,
        content     TEXT,
        category    TEXT,
        confidence  REAL,
        change_kind TEXT,                          -- create | edit | merge | confirm | supersede
        changed_by  TEXT,                          -- owner | auto | import
        created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    -- ── Brain Memory V2 (#20 / T01) — additive; legacy brain_memories untouched ──
    CREATE TABLE IF NOT EXISTS brain_memory_v2 (
        id                   INTEGER PRIMARY KEY AUTOINCREMENT,
        compat_ref           INTEGER REFERENCES brain_memories(id) ON DELETE SET NULL,
        distilled_text       TEXT NOT NULL,
        memory_type          TEXT NOT NULL,            -- brain_contracts.MemoryType
        behavior_implication TEXT DEFAULT '',
        scope_type           TEXT DEFAULT 'global',    -- ScopeType
        scope_key            TEXT,
        authority            TEXT DEFAULT 'soft',      -- Authority: soft | hard
        explicitness         TEXT DEFAULT 'inferred',  -- Explicitness: explicit | inferred
        confidence           REAL DEFAULT 0.6,
        durability           REAL DEFAULT 0,
        actionability        REAL DEFAULT 0,
        specificity          REAL DEFAULT 0,
        source_strength      REAL DEFAULT 0,
        novelty              REAL DEFAULT 0,
        future_usefulness    REAL DEFAULT 0,
        quality_score        REAL DEFAULT 0,           -- weighted 0–100
        suggested_usage      TEXT DEFAULT '',
        trust                TEXT DEFAULT 'trusted',   -- Trust: trusted | untrusted
        sensitive            INTEGER DEFAULT 0,        -- bool
        status               TEXT DEFAULT 'pending',   -- MemoryStatus
        created_at           DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at           DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS brain_memory_evidence (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        memory_id   INTEGER NOT NULL REFERENCES brain_memory_v2(id) ON DELETE CASCADE,
        excerpt     TEXT DEFAULT '',                   -- <= 320 chars
        source_ref  TEXT,
        trust       TEXT DEFAULT 'trusted',
        provenance  TEXT,                              -- how/where captured
        created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS brain_memory_links (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        from_id     INTEGER NOT NULL REFERENCES brain_memory_v2(id) ON DELETE CASCADE,
        to_id       INTEGER NOT NULL REFERENCES brain_memory_v2(id) ON DELETE CASCADE,
        link_type   TEXT NOT NULL,                     -- supersedes | supports | conflicts_with | derived_from
        created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS brain_memory_tags (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        memory_id   INTEGER NOT NULL REFERENCES brain_memory_v2(id) ON DELETE CASCADE,
        tag         TEXT NOT NULL,
        created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    -- Brain V2 (#20 / T02): vault-encrypted sensitive fields. The plaintext columns
    -- above hold a redaction placeholder for sensitive memories; the real bytes live
    -- here, AES-GCM-encrypted via vault.encrypt_payload (bound to `purpose` as AAD).
    -- Purged with the memory on owner deletion; unreadable while the vault is locked.
    CREATE TABLE IF NOT EXISTS brain_secure_payloads (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        memory_id   INTEGER NOT NULL REFERENCES brain_memory_v2(id) ON DELETE CASCADE,
        field       TEXT NOT NULL,                     -- 'distilled_text' | 'evidence:<evidence_id>'
        purpose     TEXT NOT NULL,                     -- AES-GCM AAD binding used at encrypt time
        ciphertext  BLOB NOT NULL,
        nonce       BLOB NOT NULL,
        created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(memory_id, field)
    );

    -- Brain V2 (#20 / T05): resumable dry-run import jobs. The upload itself is
    -- vault-encrypted (payload_*); progress checkpoints in next_chunk so a
    -- restart resumes exactly where it stopped. Temp payloads are purged on
    -- commit/cancel and expired after 24h.
    CREATE TABLE IF NOT EXISTS brain_ingestion_jobs (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        filename        TEXT NOT NULL,
        status          TEXT DEFAULT 'dry_run',        -- dry_run | ready | committed | cancelled | failed
        total_chunks    INTEGER DEFAULT 0,
        next_chunk      INTEGER DEFAULT 0,             -- resume checkpoint
        payload_ct      BLOB,                          -- vault-encrypted upload (NULL after purge)
        payload_nonce   BLOB,
        payload_purpose TEXT,
        error           TEXT,
        created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS brain_ingestion_candidates (
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        job_id            INTEGER NOT NULL REFERENCES brain_ingestion_jobs(id) ON DELETE CASCADE,
        chunk_index       INTEGER DEFAULT 0,
        candidate_json    TEXT,                        -- NULL when sensitive (vault-encrypted instead)
        sensitive         INTEGER DEFAULT 0,
        enc_ct            BLOB,
        enc_nonce         BLOB,
        proposed_outcome  TEXT,                        -- dry-run preview: active|pending|rejected|merged|conflicted|corrected
        proposed_status   TEXT,
        matched_id        INTEGER,
        approved          INTEGER,                     -- NULL = undecided, 1 = approve, 0 = reject
        applied_memory_id INTEGER,                     -- set on commit
        error             TEXT,
        created_at        DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    -- Brain V2 (#20 / T08): usefulness feedback + influence traces. Feedback
    -- tunes ranking only — it never deletes a memory or its evidence. Influence
    -- rows record which memory shaped which turn (the owner-visible trace).
    CREATE TABLE IF NOT EXISTS brain_memory_feedback (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        memory_id   INTEGER NOT NULL REFERENCES brain_memory_v2(id) ON DELETE CASCADE,
        verdict     TEXT NOT NULL,                     -- useful | irrelevant | wrong
        turn_ref    TEXT,                              -- the turn/influence event it judges
        created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS brain_memory_influence (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        memory_id   INTEGER NOT NULL REFERENCES brain_memory_v2(id) ON DELETE CASCADE,
        surface     TEXT DEFAULT 'chat',               -- chat | agent
        turn_ref    TEXT,
        query_hint  TEXT,                              -- truncated query context (why it surfaced)
        created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    -- Brain V2 (#20 / T06): owner-approved legacy migration. Preview scans legacy
    -- brain_memories (never modifying them) into grouped proposals; apply creates
    -- V2 rows via the real engine with compat_ref back to the legacy id. The run
    -- row is the migration ledger + resume checkpoint.
    CREATE TABLE IF NOT EXISTS brain_migration_runs (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        status          TEXT DEFAULT 'preview',        -- preview | ready | applied | cancelled
        snapshot_json   TEXT,                          -- pre-migration counts (spec step 1)
        next_legacy_id  INTEGER DEFAULT 0,             -- resume checkpoint (scan cursor)
        total_legacy    INTEGER DEFAULT 0,
        created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS brain_migration_items (
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id            INTEGER NOT NULL REFERENCES brain_migration_runs(id) ON DELETE CASCADE,
        legacy_id         INTEGER NOT NULL,            -- brain_memories.id (read-only source)
        group_kind        TEXT,                        -- reclassify | duplicate | conflict | sensitive | noise
        candidate_json    TEXT,                        -- NULL when sensitive (vault-encrypted instead)
        sensitive         INTEGER DEFAULT 0,
        enc_ct            BLOB,
        enc_nonce         BLOB,
        proposed_outcome  TEXT,
        proposed_status   TEXT,
        matched_legacy_id INTEGER,                     -- intra-run duplicate/conflict partner
        approved          INTEGER,                     -- NULL undecided | 1 | 0
        applied_memory_id INTEGER,                     -- set on apply (also the resume guard)
        error             TEXT,
        created_at        DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS brain_conflicts (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        memory_id           INTEGER REFERENCES brain_memories(id) ON DELETE CASCADE,
        candidate_content   TEXT NOT NULL,
        candidate_category  TEXT,
        candidate_confidence REAL DEFAULT 0.6,
        candidate_source    TEXT DEFAULT 'auto',
        reason              TEXT,
        status              TEXT DEFAULT 'open',   -- open | resolved
        created_at          DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS brain_imports (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        filename    TEXT,
        source_type TEXT,                          -- md | json
        card_count  INTEGER DEFAULT 0,
        created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS brain_sweep_state (
        id                     INTEGER PRIMARY KEY CHECK (id = 1),
        last_processed_convo_id INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS brain_sweep_cursors (
        chat_id     INTEGER PRIMARY KEY,
        last_id     INTEGER NOT NULL DEFAULT 0,
        fail_count  INTEGER NOT NULL DEFAULT 0,
        updated_at  TEXT
    );

    CREATE TABLE IF NOT EXISTS brain_sweep_lease (
        id          INTEGER PRIMARY KEY CHECK (id = 1),
        holder      TEXT,
        lease_until TEXT
    );

    CREATE TABLE IF NOT EXISTS brain_sweep_failures (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id       INTEGER NOT NULL,
        first_id      INTEGER NOT NULL,
        last_id       INTEGER NOT NULL,
        payload_json  TEXT NOT NULL,
        attempts      INTEGER NOT NULL DEFAULT 1,
        next_retry_at TEXT NOT NULL,
        last_error    TEXT,
        status        TEXT NOT NULL DEFAULT 'pending',
        created_at    TEXT NOT NULL,
        updated_at    TEXT NOT NULL,
        UNIQUE(chat_id, first_id, last_id)
    );

    CREATE TABLE IF NOT EXISTS brain_narrative (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        content     TEXT NOT NULL,
        model_used  TEXT,
        created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS idx_brain_mem_cat    ON brain_memories(category, status);
    CREATE INDEX IF NOT EXISTS idx_brain_mem_status ON brain_memories(status);
    CREATE INDEX IF NOT EXISTS idx_brain_mem_conf   ON brain_memories(last_confirmed_at);
    CREATE INDEX IF NOT EXISTS idx_brain_ver_mem    ON brain_memory_versions(memory_id);
    CREATE INDEX IF NOT EXISTS idx_brain_sweep_failures_due
        ON brain_sweep_failures(status, next_retry_at);
    """)
    # Seed the comprehensive category set (sensitive = Psychology/Relationships/Health).
    seed = [
        ("identity",      "Identity",       "#58a6ff", "User",       0, 0),
        ("preferences",   "Preferences",    "#3fb950", "Heart",      1, 0),
        ("psychology",    "Psychology",     "#a78bfa", "Brain",      2, 1),
        ("relationships", "Relationships",  "#f472b6", "Users",      3, 1),
        ("goals",         "Goals",          "#d29922", "Target",     4, 0),
        ("work",          "Work / Projects","#22d3ee", "Briefcase",  5, 0),
        ("habits",        "Habits / Routines","#2dd4bf", "Repeat",   6, 0),
        ("health",        "Health",         "#f85149", "Activity",   7, 1),
    ]
    for cid, label, color, icon, order, sensitive in seed:
        conn.execute(
            """INSERT OR IGNORE INTO brain_categories (id, label, color, icon, sort_order, sensitive)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (cid, label, color, icon, order, sensitive),
        )
    conn.execute("INSERT OR IGNORE INTO brain_sweep_state (id, last_processed_convo_id) VALUES (1, 0)")
    conn.execute("INSERT OR IGNORE INTO brain_sweep_lease (id, holder, lease_until) VALUES (1, NULL, NULL)")

    # v2: one-way Brain → Hermes memory mirror tracking (idempotent migration).
    cols = {r[1] for r in conn.execute("PRAGMA table_info(brain_memories)").fetchall()}
    if "hermes_synced_at" not in cols:
        conn.execute("ALTER TABLE brain_memories ADD COLUMN hermes_synced_at DATETIME")

    # v2: is_locked decoupled from sensitive (lock = UI display; sensitive = auto-memory routing).
    # Psychology was unlocked by owner command — set is_locked=0 so UI reflects the override.
    _ensure_column(conn, "brain_categories", "is_locked", "INTEGER DEFAULT 0")
    conn.execute("UPDATE brain_categories SET is_locked=0 WHERE id='psychology'")


def _ensure_graph_schema(conn: sqlite3.Connection) -> None:
    """Graph View: unified second-brain knowledge graph (memories + tasks + projects +
    integration mirrors). Idempotent. One node/edge store backs the per-domain switcher;
    embeddings (reused from Brain) drive cross-domain semantic links.
    """
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS graph_nodes (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        domain      TEXT NOT NULL,              -- memory|task|project|notion|github|gdrive|local
        ref_kind    TEXT,                       -- sub-kind (issue|commit|page|repo|doc…)
        ref_id      TEXT,                       -- source row id / external id (as text)
        title       TEXT NOT NULL,
        summary     TEXT,
        category    TEXT,
        color       TEXT,
        icon        TEXT,
        source_url  TEXT,
        embedding   BLOB,
        embed_model TEXT,
        degree      INTEGER DEFAULT 0,
        x           REAL,
        y           REAL,
        pinned      INTEGER DEFAULT 0,
        created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
        deleted_at  DATETIME
    );

    CREATE TABLE IF NOT EXISTS graph_edges (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        source_id   INTEGER NOT NULL REFERENCES graph_nodes(id) ON DELETE CASCADE,
        target_id   INTEGER NOT NULL REFERENCES graph_nodes(id) ON DELETE CASCADE,
        edge_type   TEXT NOT NULL DEFAULT 'ref',  -- ref|semantic|tag|manual
        weight      REAL DEFAULT 1,
        directed    INTEGER DEFAULT 0,
        created_by  TEXT DEFAULT 'system',        -- system|owner
        created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
        deleted_at  DATETIME
    );

    CREATE TABLE IF NOT EXISTS graph_sync_state (
        source        TEXT PRIMARY KEY,           -- internal|notion|github|gdrive|local
        last_synced_at DATETIME,
        cursor        TEXT,
        item_count    INTEGER DEFAULT 0
    );

    CREATE UNIQUE INDEX IF NOT EXISTS idx_graph_node_ref  ON graph_nodes(domain, ref_id);
    CREATE INDEX        IF NOT EXISTS idx_graph_node_dom  ON graph_nodes(domain);
    CREATE INDEX        IF NOT EXISTS idx_graph_node_cat  ON graph_nodes(category);
    CREATE UNIQUE INDEX IF NOT EXISTS idx_graph_edge_uniq ON graph_edges(source_id, target_id, edge_type);
    CREATE INDEX        IF NOT EXISTS idx_graph_edge_src  ON graph_edges(source_id);
    CREATE INDEX        IF NOT EXISTS idx_graph_edge_tgt  ON graph_edges(target_id);
    """)
    # v1.1: community detection (Louvain-style label propagation) for color/hull grouping.
    gcols = {r[1] for r in conn.execute("PRAGMA table_info(graph_nodes)").fetchall()}
    if "community" not in gcols:
        conn.execute("ALTER TABLE graph_nodes ADD COLUMN community INTEGER")
    if "community_label" not in gcols:
        conn.execute("ALTER TABLE graph_nodes ADD COLUMN community_label TEXT")


def _ensure_vault_schema(conn: sqlite3.Connection) -> None:
    """Encrypted secrets vault (Genesis Complete). Idempotent.

    Stores only ciphertext + metadata — never plaintext secrets. The master
    password (KDF → AES-256-GCM key) lives only in server memory while unlocked.
    `vault_meta` holds the KDF salt/params + a verifier blob to validate the
    password without storing it. See core/vault.py for the crypto.
    """
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS vault_meta (
        id             INTEGER PRIMARY KEY CHECK (id = 1),
        kdf            TEXT NOT NULL DEFAULT 'scrypt',
        kdf_salt       BLOB NOT NULL,
        kdf_params     TEXT NOT NULL,        -- JSON {n,r,p,len}
        verifier       BLOB NOT NULL,        -- nonce||ciphertext of a known constant
        active_profile TEXT NOT NULL DEFAULT 'local',
        created_at     DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS vault_profiles (
        name       TEXT PRIMARY KEY,          -- 'local' | 'vps' | …
        label      TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS vault_secrets (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        profile        TEXT NOT NULL DEFAULT 'local',
        name           TEXT NOT NULL,         -- env-var NAME (e.g. GITHUB_TOKEN)
        integration_id TEXT,                  -- registry id this secret belongs to
        secret_type    TEXT NOT NULL DEFAULT 'api_key', -- api_key|url|oauth|webhook|custom
        ciphertext     BLOB NOT NULL,
        nonce          BLOB NOT NULL,
        last4          TEXT,                  -- last chars for masked display only
        test_status    TEXT DEFAULT 'untested',  -- untested|ok|failed
        added_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at     DATETIME DEFAULT CURRENT_TIMESTAMP,
        last_tested_at DATETIME,
        UNIQUE(profile, name)
    );

    CREATE TABLE IF NOT EXISTS vault_audit (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        ts             DATETIME DEFAULT CURRENT_TIMESTAMP,
        action         TEXT NOT NULL,         -- setup|unlock|lock|create|update|delete|test|reveal|reload|export|import
        integration_id TEXT,
        name           TEXT,
        ok             INTEGER,
        detail         TEXT                   -- short note, NEVER a secret value
    );

    CREATE INDEX IF NOT EXISTS idx_vault_secrets_profile ON vault_secrets(profile);
    CREATE INDEX IF NOT EXISTS idx_vault_audit_ts        ON vault_audit(ts);
    """)


def _ensure_mcp_schema(conn: sqlite3.Connection) -> None:
    """MCP Hub (#5) — TOBI as MCP server (inbound) + client (outbound). Idempotent.

    Inbound client tokens are stored hashed (never the raw token). Outbound
    connection credentials live in the Genesis vault (auth_ref → vault_secrets).
    See core/mcp_server.py (server), core/mcp_security.py (authn/scopes/audit).
    """
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS mcp_server_config (
        id            INTEGER PRIMARY KEY CHECK (id = 1),
        enabled       INTEGER NOT NULL DEFAULT 1,
        transport     TEXT NOT NULL DEFAULT 'streamable_http',
        public_url    TEXT,
        tunnel_status TEXT DEFAULT 'off',
        auth_modes_json TEXT DEFAULT '["token"]',   -- token | oauth (oauth = M4)
        rate_limit_json TEXT DEFAULT '{"per_minute":60}',
        updated_at    DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS mcp_clients (              -- inbound peers
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        name        TEXT NOT NULL,
        auth_type   TEXT NOT NULL DEFAULT 'token',        -- token | oauth
        token_hash  TEXT,                                 -- sha256(token); raw shown once
        scopes_json TEXT NOT NULL DEFAULT '["*"]',        -- allowed tool names or ["*"]
        status      TEXT NOT NULL DEFAULT 'active',       -- active | revoked
        created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
        last_seen   DATETIME
    );

    CREATE TABLE IF NOT EXISTS mcp_connections (          -- outbound servers (M2)
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        name          TEXT NOT NULL,
        transport     TEXT NOT NULL DEFAULT 'http',       -- http | stdio | sse | a2a
        endpoint      TEXT,                               -- url or command
        auth_ref      TEXT,                               -- vault_secrets.name
        enabled       INTEGER NOT NULL DEFAULT 1,
        status        TEXT DEFAULT 'unknown',
        last_tested_at DATETIME,
        tools_count   INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS mcp_tools (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        source      TEXT NOT NULL,                        -- 'self' | connection id
        name        TEXT NOT NULL,
        schema_json TEXT,
        enabled     INTEGER NOT NULL DEFAULT 1,
        permission  TEXT NOT NULL DEFAULT 'allow',        -- allow | ask | deny
        scopes_json TEXT,
        UNIQUE(source, name)
    );

    CREATE TABLE IF NOT EXISTS mcp_call_log (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        ts           DATETIME DEFAULT CURRENT_TIMESTAMP,
        direction    TEXT NOT NULL,                       -- in | out
        peer         TEXT,                                -- client/connection name
        tool         TEXT,
        status       TEXT,                                -- ok | denied | error | pending
        latency_ms   INTEGER,
        request_json TEXT,
        response_json TEXT,
        error        TEXT
    );

    CREATE TABLE IF NOT EXISTS mcp_approvals (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        client     TEXT,
        tool       TEXT,
        args_json  TEXT,
        status     TEXT NOT NULL DEFAULT 'pending',       -- pending | approved | rejected
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        decided_at DATETIME
    );

    CREATE TABLE IF NOT EXISTS a2a_agents (               -- A2A peers + own card (M4)
        id        INTEGER PRIMARY KEY AUTOINCREMENT,
        name      TEXT NOT NULL,
        card_json TEXT,
        endpoint  TEXT,
        status    TEXT DEFAULT 'unknown',
        is_self   INTEGER NOT NULL DEFAULT 0
    );

    CREATE INDEX IF NOT EXISTS idx_mcp_call_log_ts   ON mcp_call_log(ts);
    CREATE INDEX IF NOT EXISTS idx_mcp_approvals_st  ON mcp_approvals(status);
    """)
    # M4 additive columns (idempotent — ignore if they already exist).
    for ddl in (
        "ALTER TABLE mcp_server_config ADD COLUMN oauth_json TEXT",
        "ALTER TABLE mcp_server_config ADD COLUMN exposed INTEGER NOT NULL DEFAULT 0",
    ):
        try:
            conn.execute(ddl)
        except Exception:
            pass


def init_database() -> None:
    """Tạo toàn bộ tables nếu chưa có. Safe to call nhiều lần."""
    conn = get_connection()
    conn.executescript("""
    -- ── PROJECTS ──────────────────────────────────────
    CREATE TABLE IF NOT EXISTS projects (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        name            TEXT    NOT NULL,
        type            TEXT    NOT NULL,   -- digital_product | affiliate | saas | newsletter
        niche           TEXT,
        status          TEXT    DEFAULT 'pending',
                                            -- pending | approved | active | paused | completed | failed
        business_plan   TEXT,               -- JSON (xem BusinessPlan dataclass)
        monthly_budget  REAL    DEFAULT 0,
        revenue_total   REAL    DEFAULT 0,
        progress_pct    INTEGER DEFAULT 0,
        notes           TEXT,
        created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
        approved_at     DATETIME,
        last_updated    DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    -- ── TASKS ─────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS tasks (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id  INTEGER REFERENCES projects(id) ON DELETE CASCADE,
        title       TEXT    NOT NULL,
        description TEXT,
        task_type   TEXT    DEFAULT 'agent',    -- agent | human
        status      TEXT    DEFAULT 'pending',  -- pending | in_progress | done | blocked | skipped
        priority    INTEGER DEFAULT 5,          -- 1 (cao) → 10 (thấp)
        week_num    INTEGER DEFAULT 1,
        output      TEXT,   -- Kết quả agent làm
        notes       TEXT,
        created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
        completed_at DATETIME
    );

    -- ── REVENUE ───────────────────────────────────────
    CREATE TABLE IF NOT EXISTS revenue (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id  INTEGER REFERENCES projects(id) ON DELETE CASCADE,
        amount      REAL    NOT NULL,
        currency    TEXT    DEFAULT 'USD',
        source      TEXT,   -- gumroad | lemon_squeezy | affiliate | manual
        description TEXT,
        recorded_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    -- ── LESSONS ───────────────────────────────────────
    CREATE TABLE IF NOT EXISTS lessons (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id   INTEGER REFERENCES projects(id) ON DELETE SET NULL,
        lesson_type  TEXT,   -- success | failure | insight | warning
        title        TEXT,
        content      TEXT    NOT NULL,
        impact_score INTEGER DEFAULT 5,    -- 1-10
        created_at   DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    -- ── STRATEGY ──────────────────────────────────────
    CREATE TABLE IF NOT EXISTS strategy (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        version    INTEGER DEFAULT 1,
        content    TEXT    NOT NULL,
        model_used TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    -- ── REPORTS ───────────────────────────────────────
    CREATE TABLE IF NOT EXISTS reports (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        report_type TEXT,   -- daily | weekly | monthly | niche_research
        content     TEXT    NOT NULL,
        project_id  INTEGER,
        created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    -- ── CONVERSATIONS (persistent chat history) ───────
    CREATE TABLE IF NOT EXISTS conversations (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id     INTEGER NOT NULL,
        role        TEXT    NOT NULL,
        content     TEXT    NOT NULL,
        created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    -- ── Indexes để query nhanh ────────────────────────
    CREATE INDEX IF NOT EXISTS idx_tasks_project    ON tasks(project_id);
    CREATE INDEX IF NOT EXISTS idx_tasks_status     ON tasks(status);
    CREATE INDEX IF NOT EXISTS idx_revenue_project  ON revenue(project_id);
    CREATE INDEX IF NOT EXISTS idx_lessons_project  ON lessons(project_id);
    CREATE INDEX IF NOT EXISTS idx_convos_chat      ON conversations(chat_id, created_at);
    """)

    _ensure_task_v1_schema(conn)
    _ensure_skill_schema(conn)
    _ensure_office_schema(conn)
    _ensure_pm_schema(conn)
    _ensure_brain_schema(conn)
    _ensure_graph_schema(conn)
    _ensure_vault_schema(conn)
    _ensure_mcp_schema(conn)
    _ensure_chat_schema(conn)
    try:
        from core import explore
        explore.ensure_schema(conn)
    except Exception:
        pass
    conn.commit()
    conn.close()
    print(f"✅ Database ready: {DB_PATH}")


def _ensure_chat_schema(conn: sqlite3.Connection) -> None:
    """Premium Chat (#8): vault-backed LLM routing config + multi-model chat sessions.
    The owning modules also create these lazily, so this is just an eager boot pass."""
    try:
        from core import chat_store
        chat_store.ensure_schema(conn)
    except Exception:
        pass
    try:
        from core import usage
        usage.ensure_schema(conn)
    except Exception:
        pass
    conn.execute(
        "CREATE TABLE IF NOT EXISTS llm_config ("
        "id INTEGER PRIMARY KEY CHECK (id=1), config_json TEXT, updated_at TEXT)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS owner_settings ("
        "key TEXT PRIMARY KEY, value TEXT, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP)"
    )
    conn.execute(
        "INSERT OR IGNORE INTO owner_settings (key, value) VALUES ('timezone', 'Asia/Ho_Chi_Minh')"
    )


# ─────────────────────────────────────────
# Project Operations
# ─────────────────────────────────────────

def create_project(
    name: str,
    type_: str,
    niche: str,
    business_plan: dict,
    monthly_budget: float = 0,
) -> int:
    """Tạo project mới (status=pending, chờ approve)."""
    conn = get_connection()
    cur = conn.execute(
        """INSERT INTO projects (name, type, niche, business_plan, monthly_budget)
           VALUES (?, ?, ?, ?, ?)""",
        (name, type_, niche, json.dumps(business_plan, ensure_ascii=False), monthly_budget),
    )
    project_id = cur.lastrowid
    conn.commit()
    conn.close()
    return project_id


def approve_project(project_id: int) -> None:
    """Đổi status → active sau khi bạn duyệt."""
    conn = get_connection()
    conn.execute(
        "UPDATE projects SET status='active', approved_at=CURRENT_TIMESTAMP WHERE id=?",
        (project_id,),
    )
    conn.commit()
    conn.close()


def reject_project(project_id: int, reason: str = "") -> None:
    conn = get_connection()
    conn.execute(
        "UPDATE projects SET status='failed', notes=? WHERE id=?",
        (f"Rejected: {reason}", project_id),
    )
    conn.commit()
    conn.close()


def update_project_progress(project_id: int, progress_pct: int, notes: str = "") -> None:
    conn = get_connection()
    conn.execute(
        """UPDATE projects
           SET progress_pct=?, notes=?, last_updated=CURRENT_TIMESTAMP
           WHERE id=?""",
        (progress_pct, notes, project_id),
    )
    conn.commit()
    conn.close()


def get_project(project_id: int) -> Optional[dict]:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM projects WHERE id=?", (project_id,)
    ).fetchone()
    conn.close()
    if row:
        r = dict(row)
        if r.get("business_plan"):
            r["business_plan"] = json.loads(r["business_plan"])
        return r
    return None


def get_active_projects() -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM projects WHERE status='active' ORDER BY created_at"
    ).fetchall()
    conn.close()
    result = []
    for row in rows:
        r = dict(row)
        if r.get("business_plan"):
            r["business_plan"] = json.loads(r["business_plan"])
        result.append(r)
    return result


def get_all_projects() -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM projects ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    result = []
    for row in rows:
        r = dict(row)
        if r.get("business_plan"):
            r["business_plan"] = json.loads(r["business_plan"])
        result.append(r)
    return result


# ─────────────────────────────────────────
# Task Operations
# ─────────────────────────────────────────

def create_task(
    project_id: int,
    title: str,
    description: str = "",
    task_type: str = "agent",   # "agent" | "human"
    priority: int = 5,
    week_num: int = 1,
) -> int:
    priority_label = "P0" if priority <= 2 else "P1" if priority <= 4 else "P2" if priority <= 7 else "P3"
    conn = get_connection()
    next_sort = conn.execute("SELECT COALESCE(MAX(sort_order), 0) + 1 FROM tasks").fetchone()[0]
    cur = conn.execute(
        """
        INSERT INTO tasks (
            project_id, title, description, task_type, priority, week_num,
            status, status_v1, priority_label, owner_label, agent_key,
            objective, updated_at, sort_order
        )
        VALUES (?, ?, ?, ?, ?, ?, 'pending', 'planned', ?, 'owner', 'tobi', ?, CURRENT_TIMESTAMP, ?)
        """,
        (project_id, title, description, task_type, priority, week_num, priority_label, description or title, next_sort),
    )
    task_id = cur.lastrowid
    conn.commit()
    conn.close()
    return task_id


def complete_task(task_id: int, output: str = "") -> None:
    conn = get_connection()
    conn.execute(
        """UPDATE tasks
           SET status='done', status_v1='done', output=?, completed_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP
           WHERE id=?""",
        (output, task_id),
    )
    conn.commit()
    conn.close()


def get_next_agent_task(project_id: int) -> Optional[dict]:
    """Lấy task tiếp theo agent cần làm (theo priority)."""
    conn = get_connection()
    row = conn.execute(
        """SELECT * FROM tasks
           WHERE project_id=? AND task_type='agent' AND status='pending'
           ORDER BY priority ASC, week_num ASC
           LIMIT 1""",
        (project_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_human_todos(project_id: int) -> list[dict]:
    """Lấy tất cả task cần bạn làm."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT * FROM tasks
           WHERE project_id=? AND task_type='human' AND status='pending'
           ORDER BY priority ASC""",
        (project_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_pending_human_tasks_all() -> list[dict]:
    """Tổng hợp tất cả human tasks pending của mọi project."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT t.*, p.name as project_name
           FROM tasks t
           JOIN projects p ON t.project_id = p.id
           WHERE t.task_type='human' AND t.status='pending'
           ORDER BY t.priority ASC""",
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_project_progress(project_id: int) -> dict:
    """Tính % progress dựa trên tasks."""
    conn = get_connection()
    total = conn.execute(
        "SELECT COUNT(*) FROM tasks WHERE project_id=?", (project_id,)
    ).fetchone()[0]
    done = conn.execute(
        "SELECT COUNT(*) FROM tasks WHERE project_id=? AND status='done'",
        (project_id,),
    ).fetchone()[0]
    conn.close()

    pct = int((done / total * 100) if total > 0 else 0)
    return {"total": total, "done": done, "progress_pct": pct}


# ─────────────────────────────────────────
# Revenue Operations
# ─────────────────────────────────────────

def record_revenue(
    project_id: int,
    amount: float,
    source: str,
    description: str = "",
    currency: str = "USD",
) -> None:
    conn = get_connection()
    conn.execute(
        """INSERT INTO revenue (project_id, amount, currency, source, description)
           VALUES (?, ?, ?, ?, ?)""",
        (project_id, amount, currency, source, description),
    )
    # Cập nhật tổng revenue trong projects
    conn.execute(
        "UPDATE projects SET revenue_total = revenue_total + ? WHERE id=?",
        (amount, project_id),
    )
    conn.commit()
    conn.close()


def get_revenue_summary() -> dict:
    """P&L tổng hợp toàn bộ hệ thống."""
    conn = get_connection()

    total = conn.execute("SELECT COALESCE(SUM(amount), 0) FROM revenue").fetchone()[0]
    monthly = conn.execute(
        """SELECT COALESCE(SUM(amount), 0) FROM revenue
           WHERE recorded_at >= date('now', 'start of month')"""
    ).fetchone()[0]

    by_project = conn.execute(
        """SELECT p.name, p.type, COALESCE(SUM(r.amount), 0) as revenue
           FROM projects p
           LEFT JOIN revenue r ON r.project_id = p.id
           WHERE p.status IN ('active', 'completed')
           GROUP BY p.id
           ORDER BY revenue DESC"""
    ).fetchall()

    conn.close()
    return {
        "total_all_time": round(total, 2),
        "this_month": round(monthly, 2),
        "by_project": [dict(r) for r in by_project],
    }


# ─────────────────────────────────────────
# Lesson Operations
# ─────────────────────────────────────────

def add_lesson(
    content: str,
    title: str = "",
    lesson_type: str = "insight",
    project_id: int = None,
    impact_score: int = 5,
) -> None:
    conn = get_connection()
    conn.execute(
        """INSERT INTO lessons (project_id, lesson_type, title, content, impact_score)
           VALUES (?, ?, ?, ?, ?)""",
        (project_id, lesson_type, title, content, impact_score),
    )
    conn.commit()
    conn.close()


def get_all_lessons() -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM lessons ORDER BY impact_score DESC, created_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ─────────────────────────────────────────
# Strategy Operations
# ─────────────────────────────────────────

def save_strategy(content: str, model_used: str = "") -> None:
    conn = get_connection()
    last = conn.execute(
        "SELECT MAX(version) FROM strategy"
    ).fetchone()[0] or 0
    conn.execute(
        "INSERT INTO strategy (version, content, model_used) VALUES (?, ?, ?)",
        (last + 1, content, model_used),
    )
    conn.commit()
    conn.close()


def get_latest_strategy() -> Optional[str]:
    conn = get_connection()
    row = conn.execute(
        "SELECT content FROM strategy ORDER BY version DESC LIMIT 1"
    ).fetchone()
    conn.close()
    return row["content"] if row else None


# ─────────────────────────────────────────
# Report Operations
# ─────────────────────────────────────────

def save_report(content: str, report_type: str, project_id: int = None) -> None:
    conn = get_connection()
    conn.execute(
        "INSERT INTO reports (report_type, content, project_id) VALUES (?, ?, ?)",
        (report_type, content, project_id),
    )
    conn.commit()
    conn.close()


# ─────────────────────────────────────────
# Dashboard Overview
# ─────────────────────────────────────────

def get_dashboard() -> dict:
    """Snapshot tổng quan toàn hệ thống - dùng cho daily report."""
    conn = get_connection()

    projects_by_status = {}
    for row in conn.execute(
        "SELECT status, COUNT(*) as cnt FROM projects GROUP BY status"
    ).fetchall():
        projects_by_status[row["status"]] = row["cnt"]

    revenue = get_revenue_summary()
    pending_human = get_pending_human_tasks_all()

    active_projects = conn.execute(
        "SELECT id, name, type, niche, progress_pct, revenue_total FROM projects WHERE status='active'"
    ).fetchall()

    conn.close()

    return {
        "projects": projects_by_status,
        "active_projects": [dict(r) for r in active_projects],
        "revenue": revenue,
        "human_todos_count": len(pending_human),
        "human_todos": pending_human,
        "timestamp": datetime.now().isoformat(),
    }


# ─────────────────────────────────────────
# Conversation History (persistent across restarts)
# ─────────────────────────────────────────

def load_conversation_history(chat_id: int, limit: int = 20) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT role, content FROM conversations WHERE chat_id=? ORDER BY created_at DESC LIMIT ?",
        (chat_id, limit),
    ).fetchall()
    conn.close()
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


def save_conversation_message(chat_id: int, role: str, content: str) -> None:
    conn = get_connection()
    conn.execute(
        "INSERT INTO conversations (chat_id, role, content) VALUES (?, ?, ?)",
        (chat_id, role, content),
    )
    conn.execute(
        """DELETE FROM conversations WHERE chat_id=? AND id NOT IN (
               SELECT id FROM conversations WHERE chat_id=? ORDER BY created_at DESC LIMIT 50
           )""",
        (chat_id, chat_id),
    )
    conn.commit()
    conn.close()


def search_conversations(query: str = "", date_from: str = "", date_to: str = "",
                         role: str = "", limit: int = 50) -> list[dict]:
    """Search the conversations table (Telegram + Brain chat + mirrored sessions).

    Returns [{source, session_id, session_title, role, content, created_at, chat_id}].
    """
    conn = get_connection()
    sql = "SELECT content, role, chat_id, created_at FROM conversations WHERE 1=1"
    params: list = []
    if query:
        sql += " AND content LIKE ?"
        params.append(f"%{query}%")
    if date_from:
        sql += " AND date(created_at) >= ?"
        params.append(date_from)
    if date_to:
        sql += " AND date(created_at) <= ?"
        params.append(date_to)
    if role:
        sql += " AND role = ?"
        params.append(role)
    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    conn.close()

    results = []
    for r in rows:
        cid = r["chat_id"] if isinstance(r, sqlite3.Row) else r[2]
        content = r["content"] if isinstance(r, sqlite3.Row) else r[0]
        r_role = r["role"] if isinstance(r, sqlite3.Row) else r[1]
        created = r["created_at"] if isinstance(r, sqlite3.Row) else r[3]

        if cid == 990001:
            source, title = "brain", "Brain Chat"
        elif cid > 0:
            source, title = "telegram", "Telegram"
        else:
            source, title = "session", f"Session (chat_id {cid})"

        results.append({
            "source": source,
            "session_id": None,
            "session_title": title,
            "role": r_role,
            "content": (content or "")[:500],
            "created_at": created or "",
            "chat_id": cid,
        })
    return results


# ─────────────────────────────────────────
# CLI Quick Test
# ─────────────────────────────────────────

if __name__ == "__main__":
    print("=== Database Init Test ===")
    init_database()

    # Test: tạo dummy project
    plan = {"executive_summary": "Test project", "revenue_model": "digital_product"}
    pid = create_project("Test Project", "digital_product", "AI Tools", plan, 10)
    print(f"✅ Created project id={pid}")

    # Test: add tasks
    create_task(pid, "Research target audience", "Find top 5 pain points", "agent", 1, 1)
    create_task(pid, "Create Gumroad account", "Setup payment", "human", 1, 1)
    print("✅ Tasks created")

    # Test: dashboard
    dash = get_dashboard()
    print(f"✅ Dashboard: {dash['projects']} | Revenue: {dash['revenue']}")

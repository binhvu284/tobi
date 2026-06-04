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
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # dict-like rows
    conn.execute("PRAGMA foreign_keys = ON")
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
    conn.commit()
    conn.close()
    print(f"✅ Database ready: {DB_PATH}")


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

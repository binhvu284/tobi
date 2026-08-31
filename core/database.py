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

# Per-domain DDL lives in core/schema/* (Phase 4b). This module remains the single
# source of truth: the schema functions are imported back and init_database() calls
# them in the same order, so no CREATE TABLE is scattered across features.
from core.schema.base import _ensure_column, _table_columns  # noqa: F401 - used by helpers below
from core.schema.agent_tier import _ensure_agent_tier_schema
from core.schema.brain import _ensure_brain_schema
from core.schema.chat import _ensure_chat_schema
from core.schema.graph import _ensure_graph_schema
from core.schema.mcp import _ensure_mcp_schema
from core.schema.office import _SEED_AGENTS, _SEED_WORKFLOW, _ensure_office_schema  # noqa: F401
from core.schema.pm import _ensure_pm_schema, _ensure_pm_v2_schema
from core.schema.runtime import _ensure_runtime_schema
from core.schema.skills import _SEED_SKILLS, _ensure_skill_schema  # noqa: F401
from core.schema.tasks import _ensure_task_v1_schema
from core.schema.vault import _ensure_vault_schema


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








# ─────────────────────────────────────────
# Skill registry (Mission Control — Ability module)
# Spec §3.2/§5.2: unified 4-layer skill model + metrics + deps + version
# ledger + proposals inbox. H12: in Phase 1 (no Hermes) MC holds the skill
# body here; Phase 1.5 flips the body source-of-truth to the Hermes .md and
# this row becomes metadata keyed by name.
# ─────────────────────────────────────────

# id, name, category, tier, layer, risk_tier — registry metadata only.
# Curated power dims + copy live in the frontend (dashboard/src/pages/Ability.tsx).




# ─────────────────────────────────────────
# The Office (Mission Control — Module 2)
# Spec §4/§5.2: agent registry + missions + steps + versioned workflows +
# per-agent/mission/provider LLM usage. D37: model config references env-var
# key *names* only (never the secret). MC orchestrates; Hermes is one
# participant (the head agent's brain), per H17/H18.
# ─────────────────────────────────────────

# id, name, role, persona, provider, model, key_ref(env NAME), color, sprite,
# autonomy, can_spawn, is_head. D60 seed roster — all editable in the UI.

# Default linear delivery workflow (D30/D60): Sunday → Alphabet → Friday.




# ─────────────────────────────────────────
# Schema Init
# ─────────────────────────────────────────













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
    _ensure_runtime_schema(conn)
    _ensure_agent_tier_schema(conn)
    try:
        from core import explore
        explore.ensure_schema(conn)
    except Exception:
        pass
    try:  # News V2 (#23, N01) — additive ledger migrations; V1 explore tables untouched
        from core.news import repository as news_repository
        news_repository.ensure_schema(conn)
    except Exception:
        pass
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

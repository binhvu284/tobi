"""Project/task helpers that talk to the DB directly (no HTTP).

Extracted verbatim from core/telegram_bot.py (Phase 4b — pre-#21 decomposition).
See docs/REFACTORING_PLAN.md.
"""
from core.env_utils import safe_load_dotenv
safe_load_dotenv()

import os  # noqa: F401
import re  # noqa: F401
import time  # noqa: F401
import json  # noqa: F401
import asyncio  # noqa: F401
import logging  # noqa: F401
import subprocess  # noqa: F401
from datetime import datetime  # noqa: F401
from typing import Optional  # noqa: F401

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup  # noqa: F401
from telegram.ext import ContextTypes  # noqa: F401

from core.database import (  # noqa: F401
    get_project, approve_project, reject_project,
    get_all_projects, get_active_projects, get_dashboard,
    get_pending_human_tasks_all, complete_task, get_revenue_summary,
    get_all_lessons, add_lesson,
    load_conversation_history, save_conversation_message,
    get_connection,
)
from core.task_classifier import classify  # noqa: F401
import json as _json  # noqa: F401

from core.telegram.common import (  # noqa: F401
    ALLOWED_IDS, BOT_TOKEN, CHAT_ID, MAX_HISTORY, PROJECT_DIR, detect_lang,
    get_dashboard_url, is_authorized, logger, md,
)

def pm_list_active() -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM pm_projects WHERE status != 'archived' ORDER BY updated_at DESC"
    ).fetchall()
    result = []
    for r in rows:
        p = dict(r)
        p["task_count"] = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE pm_project_id=? AND deleted_at IS NULL", (p["id"],)
        ).fetchone()[0]
        p["task_done"] = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE pm_project_id=? AND deleted_at IS NULL AND status_v1='done'",
            (p["id"],),
        ).fetchone()[0]
        result.append(p)
    conn.close()
    return result


def pm_find_project(name_or_id: str) -> dict | None:
    conn = get_connection()
    # Try numeric ID first
    if name_or_id.isdigit():
        row = conn.execute("SELECT * FROM pm_projects WHERE id=?", (int(name_or_id),)).fetchone()
    else:
        row = conn.execute(
            "SELECT * FROM pm_projects WHERE LOWER(name) LIKE ? ORDER BY updated_at DESC LIMIT 1",
            (f"%{name_or_id.lower()}%",),
        ).fetchone()
    conn.close()
    return dict(row) if row else None


def pm_create(name: str, status: str = "active", created_by: str = "tobi") -> dict:
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO pm_projects (name, status, size, emoji_icon, accent_color, created_by) VALUES (?,?,?,?,?,?)",
        (name, status, "medium", "🚀", "#58a6ff", created_by),
    )
    pid = cur.lastrowid
    conn.execute(
        "INSERT INTO pm_activity (project_id, actor, action_type, summary) VALUES (?,?,?,?)",
        (pid, created_by, "project.created", f"Project '{name}' created via Telegram"),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM pm_projects WHERE id=?", (pid,)).fetchone()
    conn.close()
    return dict(row)


def pm_add_task(project_id: int, title: str, priority: str = "P2", agent: str = "tobi",
                created_by: str = "tobi") -> dict:
    conn = get_connection()
    next_sort = conn.execute("SELECT COALESCE(MAX(sort_order), 0)+1 FROM tasks").fetchone()[0]
    cur = conn.execute(
        """INSERT INTO tasks (title, objective, status, status_v1, priority, priority_label,
           owner_label, agent_key, pm_project_id, created_at, updated_at, sort_order)
           VALUES (?,?,?,?,5,?,?,?,?,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,?)""",
        (title, title, "pending", "planned", priority, "owner", agent, project_id, next_sort),
    )
    tid = cur.lastrowid
    conn.execute(
        "INSERT INTO pm_activity (project_id, actor, action_type, summary) VALUES (?,?,?,?)",
        (project_id, created_by, "task.created", f"Task '{title}' added via Telegram"),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()
    conn.close()
    return dict(row)


def pm_list_tasks(project_id: int, status: str | None = None) -> list[dict]:
    conn = get_connection()
    sql = "SELECT * FROM tasks WHERE pm_project_id=? AND deleted_at IS NULL"
    params: list = [project_id]
    if status:
        sql += " AND status_v1=?"; params.append(status)
    sql += " ORDER BY sort_order ASC, created_at ASC"
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def pm_update_goal(goal_id: int, current_value: float, actor: str = "tobi") -> bool:
    conn = get_connection()
    row = conn.execute("SELECT project_id FROM pm_goals WHERE id=?", (goal_id,)).fetchone()
    if not row:
        conn.close()
        return False
    conn.execute(
        "UPDATE pm_goals SET current_value=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (current_value, goal_id),
    )
    # Recalculate progress
    pid = row["project_id"]
    goals = conn.execute("SELECT target_value, current_value FROM pm_goals WHERE project_id=?", (pid,)).fetchall()
    pcts = [min(100.0, (g["current_value"] / g["target_value"] * 100)) for g in goals if g["target_value"] > 0]
    pct = round(sum(pcts) / len(pcts), 1) if pcts else 0.0
    conn.execute("UPDATE pm_projects SET progress_pct=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (pct, pid))
    conn.execute(
        "INSERT INTO pm_activity (project_id, actor, action_type, summary) VALUES (?,?,?,?)",
        (pid, actor, "goal.updated", f"Goal #{goal_id} updated to {current_value} via Telegram"),
    )
    conn.commit()
    conn.close()
    return True


def pm_summary_for_prompt() -> str:
    """Brief PM context for the LLM system prompt."""
    try:
        projects = pm_list_active()
        if not projects:
            return "No active PM projects."
        lines = []
        for p in projects[:5]:
            lines.append(
                f"• #{p['id']} {p['name']} [{p['status']}] {p['progress_pct']}% "
                f"({p['task_done']}/{p['task_count']} tasks)"
            )
        return "\n".join(lines)
    except Exception:
        return ""

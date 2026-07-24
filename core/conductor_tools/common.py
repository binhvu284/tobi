"""Shared helpers + constants for the conductor tool implementations.

Extracted from core/conductor.py (Phase 2 — pre-#21 decomposition). These are the
DB connection helper and the project/task/resource helpers + lookup constants used
by 2+ tool modules. Verbatim move; tool modules import from here, and conductor.py
imports the ones its orchestration still needs (e.g. _conn). Free-var set verified
by isolated-pyflakes analysis; core.* modules are imported inline inside each helper
(as in the original). See docs/REFACTORING_PLAN.md.
"""
from __future__ import annotations

import logging
import re as _re
from datetime import datetime as _dt, timedelta as _td, timezone as _tz
from typing import Any, Callable, Optional  # noqa: F401 - used in signatures/hints

logger = logging.getLogger("tobi.conductor")
def _conn():
    from core.database import get_connection
    return get_connection()


def _notion_title(page: dict) -> str:
    try:
        for v in (page.get("properties") or {}).values():
            if isinstance(v, dict) and v.get("type") == "title":
                txt = "".join(t.get("plain_text", "") for t in v.get("title", []))
                return txt or "(untitled)"
    except Exception:
        pass
    return page.get("url", "(untitled)")


def _resolve_when(when: str) -> tuple[str, str]:
    """Parse a natural-language time reference into (date_from, date_to) in YYYY-MM-DD.

    Supports: 'yesterday', 'today', 'last week', 'last month',
    'N days ago', 'YYYY-MM-DD', or empty (all time).
    """
    now = _dt.now(_tz.utc)
    w = (when or "").strip().lower()
    if not w or w in ("today", "now"):
        d = now.strftime("%Y-%m-%d")
        return d, d
    if w == "yesterday":
        d = (now - _td(days=1)).strftime("%Y-%m-%d")
        return d, d
    if "last week" in w or "past week" in w:
        return (now - _td(days=7)).strftime("%Y-%m-%d"), now.strftime("%Y-%m-%d")
    if "last month" in w or "past month" in w:
        return (now - _td(days=30)).strftime("%Y-%m-%d"), now.strftime("%Y-%m-%d")
    m = _re.match(r'(\d+)\s*days?\s*ago', w)
    if m:
        d = (now - _td(days=int(m.group(1)))).strftime("%Y-%m-%d")
        return d, d
    try:
        _dt.strptime(w, "%Y-%m-%d")
        return w, w
    except ValueError:
        pass
    return "", ""


def _load_owner_timezone() -> str:
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT value FROM owner_settings WHERE key='timezone'"
        ).fetchone()
        return row["value"] if row else "Asia/Ho_Chi_Minh"
    except Exception:
        return "Asia/Ho_Chi_Minh"
    finally:
        conn.close()


def _resolve_pm_project(conn, key: str):
    """Resolve a pm_projects row by numeric id or fuzzy name. Returns the row or None."""
    key = str(key or "").strip()
    if not key:
        return None
    if key.isdigit():
        return conn.execute("SELECT id, name FROM pm_projects WHERE id=?", (int(key),)).fetchone()
    return conn.execute("SELECT id, name FROM pm_projects WHERE name LIKE ? ORDER BY updated_at DESC LIMIT 1",
                        (f"%{key}%",)).fetchone()


def _resource_inventory(conn, pid: int, project_name: str, limit: int = 50) -> dict:
    """List what the owner uploaded to ONE project's Resources drive — no search query needed."""
    rows = conn.execute(
        "SELECT id, name, kind, rtype, ext, source, size_bytes, url, created_by, created_at, "
        "       (text_content IS NOT NULL AND length(text_content) > 0) AS has_text "
        "FROM pm_resources WHERE project_id=? ORDER BY created_at DESC LIMIT ?",
        (int(pid), int(limit))).fetchall()
    items = [{
        "id": r["id"], "name": r["name"], "kind": r["kind"], "rtype": r["rtype"],
        "ext": r["ext"], "source": r["source"], "size_bytes": r["size_bytes"] or 0,
        "url": r["url"], "readable": bool(r["has_text"]), "added_by": r["created_by"],
        "added_at": r["created_at"],
    } for r in rows]
    out = {"project_id": pid, "project": project_name, "count": len(items), "resources": items}
    if not items:
        out["note"] = "This project's Resources drive is empty — nothing has been uploaded to it yet."
    else:
        out["hint"] = ("Use read_resource(project, name) to read one, or "
                       "search_project_resources(project, query) to search inside them.")
    return out


def _pm_recalc(conn, project_id: int) -> None:
    """Keep a PM project's progress % in sync after a task change (reuses the API's logic)."""
    try:
        from api import dashboard as D
        D._pm_recalc_progress(conn, project_id)
    except Exception as e:  # never let progress bookkeeping break the act
        logger.debug("pm recalc skipped: %s", e)


def _pm_log(conn, project_id: int, action_type: str, summary: str) -> None:
    try:
        conn.execute(
            "INSERT INTO pm_activity (project_id, actor, action_type, summary) VALUES (?,?,?,?)",
            (project_id, "tobi", action_type, summary),
        )
    except Exception:
        pass


_EMOJI_BY_CATEGORY = {
    "general": "📁", "work": "💼", "personal": "🌟", "research": "🔬",
    "marketing": "📣", "dev": "💻", "design": "🎨", "business": "🏢",
    "content": "✍️", "growth": "📈",
}


_TASK_AGENTS = {"tobi", "research", "coder", "ceo"}


_AGENT_ALIASES = {"developer": "coder", "dev": "coder", "engineer": "coder", "writer": "coder",
                  "researcher": "research", "analyst": "research", "boss": "ceo", "manager": "ceo"}


_TASK_STATUS_LEGACY = {"planned": "pending", "in_progress": "in_progress", "paused": "pending",
                       "blocked": "pending", "needs_owner_input": "pending", "done": "done",
                       "cancelled": "skipped"}


_TASK_PRIORITY = {"p0": "P0", "p1": "P1", "p2": "P2", "p3": "P3", "urgent": "P0",
                  "high": "P1", "medium": "P2", "normal": "P2", "low": "P3"}

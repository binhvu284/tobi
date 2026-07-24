"""Projects module API — /api/pm/* (#12 Project V2).

Extracted from api/dashboard.py (refactor Slice — pre-#21 decomposition). Byte-
identical: pm request models + _pm_* helpers + 43 routes, only @app.* -> @router.*.
Shared task/activity helpers come from api.deps; the task constants + TaskPatchRequest
+ api_task_patch come from api.routers.tasks (pm extends the task ledger for projects —
one-directional, no cycle). pm_resources keeps its `pmres` alias. See REFACTORING_PLAN.
"""
from __future__ import annotations

import json  # noqa: F401 - used by some handlers
import re  # noqa: F401 - used by some handlers
import sqlite3  # noqa: F401 - used in type hints
from datetime import datetime, timezone  # noqa: F401 - used by some handlers
from typing import Any  # noqa: F401 - used in type hints

from fastapi import APIRouter, Body, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, RedirectResponse, Response
from pydantic import BaseModel

from api.deps import (_append_activity, _fetch_task_row, _get_conn, _json_loads,
                      _legacy_status_from_v1, _serialize_task)
from api.routers.tasks import (ALLOWED_AGENTS, ALLOWED_PRIORITIES, TASK_STATUS_V1,
                               TaskPatchRequest, api_task_patch)
from core import pm_resources as pmres

router = APIRouter(tags=["pm"])


# ── PROJECT MODULE (Mission Control — Projects) ──────────────────────────────

PM_PROJECT_STATUSES = {"idea", "active", "done", "archived"}
PM_PROJECT_SIZES    = {"small", "medium", "large", "epic"}
PM_MISSION_STATUSES = {"queued", "running", "done", "failed"}
PM_GOAL_OWNERS      = {"user", "tobi"}


# ── Pydantic models ─────────────────────────────────────────────────────────

class PMProjectCreateRequest(BaseModel):
    name: str
    description: str | None = None
    status: str = "idea"
    size: str = "medium"
    category: str | None = None
    emoji_icon: str = "📁"
    accent_color: str = "#58a6ff"
    deadline: str | None = None
    kpi_mode: str | None = None
    kpi_id: str | None = None
    kpi_metric_name: str | None = None
    kpi_target_value: float | None = None
    kpi_current_value: float = 0
    template_id: int | None = None
    created_by: str = "user"


class PMProjectPatchRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    status: str | None = None
    size: str | None = None
    category: str | None = None
    emoji_icon: str | None = None
    icon_type: str | None = None          # emoji | icon | custom
    icon_value: str | None = None         # emoji char / icon key / pm_icons id
    accent_color: str | None = None
    deadline: str | None = None
    kpi_mode: str | None = None
    kpi_id: str | None = None
    kpi_metric_name: str | None = None
    kpi_target_value: float | None = None
    kpi_current_value: float | None = None


class PMGoalCreateRequest(BaseModel):
    title: str
    description: str | None = None
    metric_name: str | None = None
    target_value: float = 100
    current_value: float = 0
    due_date: str | None = None
    priority: str = "medium"
    owner: str = "user"
    parent_goal_id: int | None = None


class PMGoalPatchRequest(BaseModel):
    title: str | None = None
    description: str | None = None
    metric_name: str | None = None
    target_value: float | None = None
    current_value: float | None = None
    due_date: str | None = None
    priority: str | None = None
    owner: str | None = None
    parent_goal_id: int | None = None


class PMMissionCreateRequest(BaseModel):
    prompt: str
    created_by: str = "user"


class PMActivityPostRequest(BaseModel):
    actor: str = "tobi"
    action_type: str
    summary: str
    diff: dict[str, Any] | None = None


class PMFileCreateRequest(BaseModel):
    filename: str
    file_size: int | None = None
    mime_type: str | None = None
    uploaded_by: str = "user"


class PMTemplateCreateRequest(BaseModel):
    name: str
    description: str | None = None
    source_project_id: int


class PMTaskCreateRequest(BaseModel):
    title: str
    objective: str | None = None
    description: str | None = None
    status: str = "planned"
    priority: str = "P2"
    agent: str = "tobi"
    due_at: str | None = None
    time_estimate: str | None = None
    pm_goal_id: int | None = None


# ── Helpers ──────────────────────────────────────────────────────────────────

def _pm_log(conn: sqlite3.Connection, project_id: int, actor: str,
            action_type: str, summary: str, diff: dict | None = None) -> None:
    conn.execute(
        "INSERT INTO pm_activity (project_id, actor, action_type, summary, diff) VALUES (?,?,?,?,?)",
        (project_id, actor, action_type, summary, json.dumps(diff) if diff else None),
    )


def _pm_recalc_progress(conn: sqlite3.Connection, project_id: int) -> float:
    rows = conn.execute(
        "SELECT target_value, current_value FROM pm_goals WHERE project_id=?", (project_id,)
    ).fetchall()
    if not rows:
        # Fallback: task-based progress
        total = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE pm_project_id=? AND deleted_at IS NULL", (project_id,)
        ).fetchone()[0]
        done = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE pm_project_id=? AND deleted_at IS NULL AND status_v1='done'",
            (project_id,),
        ).fetchone()[0]
        pct = round((done / total * 100) if total > 0 else 0, 1)
    else:
        pcts = [
            min(100.0, round((r["current_value"] / r["target_value"] * 100), 1))
            if r["target_value"] > 0 else 0.0
            for r in rows
        ]
        pct = round(sum(pcts) / len(pcts), 1)
    conn.execute(
        "UPDATE pm_projects SET progress_pct=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (pct, project_id),
    )
    return pct


def _pm_serialize_project(conn: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
    p = dict(row)
    p["task_count"] = conn.execute(
        "SELECT COUNT(*) FROM tasks WHERE pm_project_id=? AND deleted_at IS NULL", (p["id"],)
    ).fetchone()[0]
    p["task_done"] = conn.execute(
        "SELECT COUNT(*) FROM tasks WHERE pm_project_id=? AND deleted_at IS NULL AND status_v1='done'",
        (p["id"],),
    ).fetchone()[0]
    p["goal_count"] = conn.execute(
        "SELECT COUNT(*) FROM pm_goals WHERE project_id=?", (p["id"],)
    ).fetchone()[0]
    return p


def _pm_serialize_goal(row: sqlite3.Row) -> dict[str, Any]:
    g = dict(row)
    tv = g.get("target_value") or 1
    cv = g.get("current_value") or 0
    g["progress_pct"] = round(min(100.0, cv / tv * 100), 1) if tv > 0 else 0.0
    return g


# ── PROJECTS ─────────────────────────────────────────────────────────────────

@router.get("/api/pm/projects")
async def pm_list_projects(status: str | None = None, category: str | None = None,
                            size: str | None = None, q: str | None = None):
    conn = _get_conn()
    sql = "SELECT * FROM pm_projects WHERE 1=1"
    params: list[Any] = []
    if status and status != "all":
        sql += " AND status=?"; params.append(status)
    if category:
        sql += " AND category=?"; params.append(category)
    if size:
        sql += " AND size=?"; params.append(size)
    if q:
        sql += " AND (name LIKE ? OR description LIKE ?)"; params += [f"%{q}%", f"%{q}%"]
    # manual drag order first (new projects with no order yet float to the top), then recency
    sql += " ORDER BY COALESCE(sort_order, -1) ASC, updated_at DESC, id DESC"
    rows = conn.execute(sql, params).fetchall()
    items = [_pm_serialize_project(conn, r) for r in rows]
    conn.close()
    return {"items": items, "count": len(items), "timestamp": datetime.now(timezone.utc).isoformat()}


@router.post("/api/pm/projects")
async def pm_create_project(payload: PMProjectCreateRequest):
    if payload.status not in PM_PROJECT_STATUSES:
        raise HTTPException(status_code=400, detail=f"bad status; use {sorted(PM_PROJECT_STATUSES)}")
    if payload.size not in PM_PROJECT_SIZES:
        raise HTTPException(status_code=400, detail=f"bad size; use {sorted(PM_PROJECT_SIZES)}")
    conn = _get_conn()
    # Apply template if given
    template_goals, template_tasks = [], []
    if payload.template_id:
        tmpl = conn.execute("SELECT snapshot FROM pm_templates WHERE id=?", (payload.template_id,)).fetchone()
        if tmpl:
            snap = _json_loads(tmpl["snapshot"], {})
            template_goals = snap.get("goals", [])
            template_tasks = snap.get("tasks", [])
    cur = conn.execute(
        """INSERT INTO pm_projects (name, description, status, size, category, emoji_icon,
           accent_color, deadline, kpi_mode, kpi_id, kpi_metric_name, kpi_target_value,
           kpi_current_value, template_id, created_by)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (payload.name, payload.description, payload.status, payload.size, payload.category,
         payload.emoji_icon, payload.accent_color, payload.deadline, payload.kpi_mode,
         payload.kpi_id, payload.kpi_metric_name, payload.kpi_target_value,
         payload.kpi_current_value, payload.template_id, payload.created_by),
    )
    pid = cur.lastrowid
    for g in template_goals:
        conn.execute(
            "INSERT INTO pm_goals (project_id, title, metric_name, target_value) VALUES (?,?,?,?)",
            (pid, g.get("title", "Goal"), g.get("metric_name"), g.get("target_value", 100)),
        )
    for t in template_tasks:
        next_sort = conn.execute("SELECT COALESCE(MAX(sort_order), 0)+1 FROM tasks").fetchone()[0]
        conn.execute(
            """INSERT INTO tasks (title, status, status_v1, priority_label, owner_label, agent_key,
               objective, pm_project_id, updated_at, sort_order, created_at)
               VALUES (?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP,?,CURRENT_TIMESTAMP)""",
            (t.get("title", "Task"), "pending", "planned", "P2", "owner", "tobi",
             t.get("title", "Task"), pid, next_sort),
        )
    _pm_log(conn, pid, payload.created_by, "project.created", f"Project '{payload.name}' created")
    conn.commit()
    row = conn.execute("SELECT * FROM pm_projects WHERE id=?", (pid,)).fetchone()
    result = _pm_serialize_project(conn, row)
    conn.close()
    return result


@router.post("/api/pm/projects/reorder")
async def pm_reorder_projects(payload: dict = Body(...)):
    """Persist a manual drag order: `{ "order": [id, id, ...] }` → sort_order = position.
    Defined before /{project_id} so the literal path can never be shadowed by the param route."""
    order = payload.get("order")
    if not isinstance(order, list):
        raise HTTPException(status_code=400, detail="order must be a list of project ids")
    conn = _get_conn()
    try:
        for i, pid in enumerate(order):
            conn.execute("UPDATE pm_projects SET sort_order=? WHERE id=?", (float(i), int(pid)))
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "count": len(order)}


@router.get("/api/pm/projects/{project_id}")
async def pm_get_project(project_id: int):
    conn = _get_conn()
    row = conn.execute("SELECT * FROM pm_projects WHERE id=?", (project_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="project not found")
    result = _pm_serialize_project(conn, row)
    conn.close()
    return result


@router.patch("/api/pm/projects/{project_id}")
async def pm_patch_project(project_id: int, payload: PMProjectPatchRequest):
    conn = _get_conn()
    row = conn.execute("SELECT * FROM pm_projects WHERE id=?", (project_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="project not found")
    fields, vals, diff = [], [], {}
    for col, v in [
        ("name", payload.name), ("description", payload.description), ("status", payload.status),
        ("size", payload.size), ("category", payload.category), ("emoji_icon", payload.emoji_icon),
        ("icon_type", payload.icon_type), ("icon_value", payload.icon_value),
        ("accent_color", payload.accent_color), ("deadline", payload.deadline),
        ("kpi_mode", payload.kpi_mode), ("kpi_id", payload.kpi_id),
        ("kpi_metric_name", payload.kpi_metric_name), ("kpi_target_value", payload.kpi_target_value),
        ("kpi_current_value", payload.kpi_current_value),
    ]:
        if v is not None:
            fields.append(f"{col}=?"); vals.append(v); diff[col] = v
    if not fields:
        raise HTTPException(status_code=400, detail="no updates provided")
    if payload.status and payload.status not in PM_PROJECT_STATUSES:
        raise HTTPException(status_code=400, detail=f"bad status; use {sorted(PM_PROJECT_STATUSES)}")
    fields.append("updated_at=CURRENT_TIMESTAMP")
    vals.append(project_id)
    conn.execute(f"UPDATE pm_projects SET {', '.join(fields)} WHERE id=?", vals)
    _pm_log(conn, project_id, "user", "project.updated", "Project updated", diff)
    conn.commit()
    row = conn.execute("SELECT * FROM pm_projects WHERE id=?", (project_id,)).fetchone()
    result = _pm_serialize_project(conn, row)
    conn.close()
    return result


@router.delete("/api/pm/projects/{project_id}")
async def pm_delete_project(project_id: int):
    conn = _get_conn()
    if not conn.execute("SELECT 1 FROM pm_projects WHERE id=?", (project_id,)).fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="project not found")
    conn.execute("DELETE FROM pm_projects WHERE id=?", (project_id,))
    conn.commit()
    conn.close()
    # v2: remove the project's on-disk resources dir too (best-effort)
    try:
        import shutil
        root = pmres.resources_root(project_id).parent   # <data>/projects/{id}/
        if root.exists():
            shutil.rmtree(root, ignore_errors=True)
    except Exception:
        pass
    return {"ok": True, "project_id": project_id}


# ── GOALS ─────────────────────────────────────────────────────────────────────

@router.get("/api/pm/projects/{project_id}/goals")
async def pm_list_goals(project_id: int):
    conn = _get_conn()
    _pm_sync_rollup_goals(conn, project_id)   # task-mode goals reflect their linked tasks
    conn.commit()
    rows = conn.execute(
        "SELECT * FROM pm_goals WHERE project_id=? ORDER BY created_at", (project_id,)
    ).fetchall()
    items = []
    for r in rows:
        g = _pm_serialize_goal(r)
        g["linked_task_ids"] = [x[0] for x in conn.execute(
            "SELECT task_id FROM pm_goal_tasks WHERE goal_id=?", (r["id"],)).fetchall()]
        items.append(g)
    conn.close()
    return {"items": items, "count": len(items)}


@router.post("/api/pm/projects/{project_id}/goals")
async def pm_create_goal(project_id: int, payload: PMGoalCreateRequest):
    conn = _get_conn()
    if not conn.execute("SELECT 1 FROM pm_projects WHERE id=?", (project_id,)).fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="project not found")
    cur = conn.execute(
        """INSERT INTO pm_goals (project_id, title, description, metric_name, target_value,
                                 current_value, due_date, priority, owner, parent_goal_id)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (project_id, payload.title, payload.description, payload.metric_name, payload.target_value,
         payload.current_value, payload.due_date, payload.priority, payload.owner,
         payload.parent_goal_id),
    )
    gid = cur.lastrowid
    _pm_recalc_progress(conn, project_id)
    _pm_log(conn, project_id, "user", "goal.created", f"Goal '{payload.title}' added")
    conn.commit()
    row = conn.execute("SELECT * FROM pm_goals WHERE id=?", (gid,)).fetchone()
    conn.close()
    return _pm_serialize_goal(row)


@router.patch("/api/pm/projects/{project_id}/goals/{goal_id}")
async def pm_patch_goal(project_id: int, goal_id: int, payload: PMGoalPatchRequest):
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM pm_goals WHERE id=? AND project_id=?", (goal_id, project_id)
    ).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="goal not found")
    fields, vals, diff = [], [], {}
    for col, v in [("title", payload.title), ("description", payload.description),
                   ("metric_name", payload.metric_name),
                   ("target_value", payload.target_value), ("current_value", payload.current_value),
                   ("due_date", payload.due_date), ("priority", payload.priority),
                   ("owner", payload.owner), ("parent_goal_id", payload.parent_goal_id)]:
        if v is not None:
            fields.append(f"{col}=?"); vals.append(v); diff[col] = v
    if fields:
        fields.append("updated_at=CURRENT_TIMESTAMP")
        vals.append(goal_id)
        conn.execute(f"UPDATE pm_goals SET {', '.join(fields)} WHERE id=?", vals)
        _pm_recalc_progress(conn, project_id)
        _pm_log(conn, project_id, "user", "goal.updated", f"Goal updated", diff)
        conn.commit()
    row = conn.execute("SELECT * FROM pm_goals WHERE id=?", (goal_id,)).fetchone()
    conn.close()
    return _pm_serialize_goal(row)


@router.delete("/api/pm/projects/{project_id}/goals/{goal_id}")
async def pm_delete_goal(project_id: int, goal_id: int):
    conn = _get_conn()
    if not conn.execute("SELECT 1 FROM pm_goals WHERE id=? AND project_id=?", (goal_id, project_id)).fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="goal not found")
    conn.execute("DELETE FROM pm_goals WHERE id=?", (goal_id,))
    _pm_recalc_progress(conn, project_id)
    conn.commit()
    conn.close()
    return {"ok": True, "goal_id": goal_id}


# ── TASKS WITHIN A PM PROJECT ─────────────────────────────────────────────────

@router.get("/api/pm/projects/{project_id}/tasks")
async def pm_list_tasks(project_id: int, status: str | None = None, assignee: str | None = None):
    conn = _get_conn()
    sql = """
        SELECT t.*, COALESCE(p.name, pmp.name) AS project_name
        FROM tasks t
        LEFT JOIN projects p ON p.id = t.project_id
        LEFT JOIN pm_projects pmp ON pmp.id = t.pm_project_id
        WHERE t.pm_project_id=? AND t.deleted_at IS NULL
    """
    params: list[Any] = [project_id]
    if status:
        sql += " AND t.status_v1=?"; params.append(status)
    if assignee:
        sql += " AND t.owner_label=?"; params.append(assignee)
    sql += " ORDER BY t.sort_order ASC, t.created_at ASC"
    rows = conn.execute(sql, params).fetchall()
    # _serialize_task now includes sub_tasks/time_estimate/pm_goal_id from the row
    tasks = [_serialize_task(conn, r, include_activity=False) for r in rows]
    conn.close()
    return {"items": tasks, "count": len(tasks)}


@router.post("/api/pm/projects/{project_id}/tasks")
async def pm_create_task(project_id: int, payload: PMTaskCreateRequest):
    conn = _get_conn()
    if not conn.execute("SELECT 1 FROM pm_projects WHERE id=?", (project_id,)).fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="project not found")
    if payload.status not in TASK_STATUS_V1:
        raise HTTPException(status_code=400, detail=f"bad status")
    if payload.priority not in ALLOWED_PRIORITIES:
        raise HTTPException(status_code=400, detail=f"bad priority")
    agent = payload.agent if payload.agent in ALLOWED_AGENTS else "tobi"
    next_sort = conn.execute("SELECT COALESCE(MAX(sort_order), 0)+1 FROM tasks").fetchone()[0]
    cur = conn.execute(
        """INSERT INTO tasks (title, objective, description, status, status_v1, priority, priority_label,
           owner_label, agent_key, due_at, time_estimate, pm_project_id, pm_goal_id,
           created_at, updated_at, sort_order)
           VALUES (?,?,?,?,?,5,?,?,?,?,?,?,?,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,?)""",
        (payload.title, payload.objective or payload.title, payload.description,
         _legacy_status_from_v1(payload.status), payload.status, payload.priority,
         "owner", agent, payload.due_at, payload.time_estimate, project_id,
         payload.pm_goal_id, next_sort),
    )
    tid = cur.lastrowid
    _append_activity(conn, tid, "created", "owner", "Task created in project")
    _pm_log(conn, project_id, "user", "task.created", f"Task '{payload.title}' added")
    _pm_recalc_progress(conn, project_id)
    conn.commit()
    row = _fetch_task_row(conn, tid)
    task = _serialize_task(conn, row, include_activity=False)
    conn.close()
    return task


class PMSubTasksBody(BaseModel):
    subtasks: list[dict]

@router.patch("/api/pm/projects/{project_id}/tasks/{task_id}/subtasks")
async def pm_patch_subtasks(project_id: int, task_id: int, body: PMSubTasksBody):
    conn = _get_conn()
    row = _fetch_task_row(conn, task_id)
    if not row or row["pm_project_id"] != project_id:
        conn.close()
        raise HTTPException(status_code=404, detail="task not found in project")
    conn.execute(
        "UPDATE tasks SET sub_tasks_json=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (json.dumps(body.subtasks, ensure_ascii=False), task_id),
    )
    conn.commit()
    conn.close()
    return {"ok": True, "count": len(body.subtasks)}


@router.patch("/api/pm/projects/{project_id}/tasks/{task_id}")
async def pm_patch_task(project_id: int, task_id: int, payload: TaskPatchRequest):
    """Thin wrapper — delegates to the main task patch endpoint after verifying PM ownership."""
    conn = _get_conn()
    row = _fetch_task_row(conn, task_id)
    conn.close()
    if not row or row["pm_project_id"] != project_id:
        raise HTTPException(status_code=404, detail="task not found in project")
    # Reuse the full patch logic
    return await api_task_patch(task_id, payload)


@router.delete("/api/pm/projects/{project_id}/tasks/{task_id}")
async def pm_delete_task(project_id: int, task_id: int):
    conn = _get_conn()
    row = _fetch_task_row(conn, task_id)
    if not row or row["pm_project_id"] != project_id:
        conn.close()
        raise HTTPException(status_code=404, detail="task not found in project")
    conn.execute(
        "UPDATE tasks SET deleted_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (task_id,),
    )
    _pm_log(conn, project_id, "user", "task.deleted", f"Task '{row['title']}' deleted")
    _pm_recalc_progress(conn, project_id)
    conn.commit()
    conn.close()
    return {"ok": True, "task_id": task_id}


# ── MISSIONS ──────────────────────────────────────────────────────────────────

@router.get("/api/pm/projects/{project_id}/missions")
async def pm_list_missions(project_id: int):
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM pm_missions WHERE project_id=? ORDER BY created_at DESC", (project_id,)
    ).fetchall()
    items = [dict(r) for r in rows]
    conn.close()
    return {"items": items, "count": len(items)}


@router.post("/api/pm/projects/{project_id}/missions")
async def pm_create_mission(project_id: int, payload: PMMissionCreateRequest):
    conn = _get_conn()
    if not conn.execute("SELECT 1 FROM pm_projects WHERE id=?", (project_id,)).fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="project not found")
    if not payload.prompt.strip():
        raise HTTPException(status_code=400, detail="prompt cannot be empty")
    cur = conn.execute(
        "INSERT INTO pm_missions (project_id, prompt, status, created_by) VALUES (?,?,?,?)",
        (project_id, payload.prompt.strip(), "queued", payload.created_by),
    )
    mid = cur.lastrowid
    _pm_log(conn, project_id, payload.created_by, "mission.queued",
            f"Mission queued: '{payload.prompt[:60]}…'" if len(payload.prompt) > 60 else f"Mission queued: '{payload.prompt}'")
    conn.commit()
    row = conn.execute("SELECT * FROM pm_missions WHERE id=?", (mid,)).fetchone()
    conn.close()
    return dict(row)


@router.patch("/api/pm/projects/{project_id}/missions/{mission_id}")
async def pm_patch_mission(project_id: int, mission_id: int, payload: dict):
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM pm_missions WHERE id=? AND project_id=?", (mission_id, project_id)
    ).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="mission not found")
    fields, vals = [], []
    allowed = {"status", "output", "tasks_created", "docs_created", "duration_ms", "completed_at"}
    for k, v in payload.items():
        if k in allowed:
            fields.append(f"{k}=?"); vals.append(v)
    if fields:
        vals.append(mission_id)
        conn.execute(f"UPDATE pm_missions SET {', '.join(fields)} WHERE id=?", vals)
        conn.commit()
    row = conn.execute("SELECT * FROM pm_missions WHERE id=?", (mission_id,)).fetchone()
    conn.close()
    return dict(row)


# ── ACTIVITY ──────────────────────────────────────────────────────────────────

@router.get("/api/pm/projects/{project_id}/activity")
async def pm_list_activity(project_id: int, actor: str | None = None, limit: int = 100):
    conn = _get_conn()
    if actor and actor != "all":
        rows = conn.execute(
            "SELECT * FROM pm_activity WHERE project_id=? AND actor=? ORDER BY created_at DESC LIMIT ?",
            (project_id, actor, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM pm_activity WHERE project_id=? ORDER BY created_at DESC LIMIT ?",
            (project_id, limit),
        ).fetchall()
    items = []
    for r in rows:
        d = dict(r)
        d["diff"] = _json_loads(d.get("diff"), None)
        items.append(d)
    conn.close()
    return {"items": items, "count": len(items)}


@router.post("/api/pm/projects/{project_id}/activity")
async def pm_post_activity(project_id: int, payload: PMActivityPostRequest):
    conn = _get_conn()
    if not conn.execute("SELECT 1 FROM pm_projects WHERE id=?", (project_id,)).fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="project not found")
    _pm_log(conn, project_id, payload.actor, payload.action_type, payload.summary, payload.diff)
    conn.commit()
    conn.close()
    return {"ok": True}


# ── FILES ─────────────────────────────────────────────────────────────────────

@router.get("/api/pm/projects/{project_id}/files")
async def pm_list_files(project_id: int):
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM pm_files WHERE project_id=? ORDER BY created_at DESC", (project_id,)
    ).fetchall()
    items = [dict(r) for r in rows]
    conn.close()
    return {"items": items, "count": len(items)}


@router.post("/api/pm/projects/{project_id}/files")
async def pm_create_file(project_id: int, payload: PMFileCreateRequest):
    conn = _get_conn()
    if not conn.execute("SELECT 1 FROM pm_projects WHERE id=?", (project_id,)).fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="project not found")
    cur = conn.execute(
        "INSERT INTO pm_files (project_id, filename, file_size, mime_type, uploaded_by) VALUES (?,?,?,?,?)",
        (project_id, payload.filename, payload.file_size, payload.mime_type, payload.uploaded_by),
    )
    fid = cur.lastrowid
    _pm_log(conn, project_id, payload.uploaded_by, "file.added", f"File attached: {payload.filename}")
    conn.commit()
    row = conn.execute("SELECT * FROM pm_files WHERE id=?", (fid,)).fetchone()
    conn.close()
    return dict(row)


@router.delete("/api/pm/projects/{project_id}/files/{file_id}")
async def pm_delete_file(project_id: int, file_id: int):
    conn = _get_conn()
    row = conn.execute("SELECT filename FROM pm_files WHERE id=? AND project_id=?", (file_id, project_id)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="file not found")
    conn.execute("DELETE FROM pm_files WHERE id=?", (file_id,))
    _pm_log(conn, project_id, "user", "file.removed", f"File removed: {row['filename']}")
    conn.commit()
    conn.close()
    return {"ok": True, "file_id": file_id}


# ── TEMPLATES ─────────────────────────────────────────────────────────────────

@router.get("/api/pm/templates")
async def pm_list_templates():
    conn = _get_conn()
    rows = conn.execute("SELECT * FROM pm_templates ORDER BY created_at DESC").fetchall()
    items = []
    for r in rows:
        d = dict(r)
        d["snapshot"] = _json_loads(d.get("snapshot"), {})
        items.append(d)
    conn.close()
    return {"items": items, "count": len(items)}


@router.post("/api/pm/templates")
async def pm_create_template(payload: PMTemplateCreateRequest):
    conn = _get_conn()
    proj = conn.execute("SELECT * FROM pm_projects WHERE id=?", (payload.source_project_id,)).fetchone()
    if not proj:
        conn.close()
        raise HTTPException(status_code=404, detail="source project not found")
    goals = [_pm_serialize_goal(r) for r in conn.execute(
        "SELECT * FROM pm_goals WHERE project_id=?", (payload.source_project_id,)).fetchall()]
    tasks = [{"title": r["title"], "priority": r["priority_label"]} for r in conn.execute(
        "SELECT title, priority_label FROM tasks WHERE pm_project_id=? AND deleted_at IS NULL",
        (payload.source_project_id,)).fetchall()]
    snapshot = json.dumps({"goals": goals, "tasks": tasks}, ensure_ascii=False)
    cur = conn.execute(
        "INSERT INTO pm_templates (name, description, source_project_id, snapshot) VALUES (?,?,?,?)",
        (payload.name, payload.description, payload.source_project_id, snapshot),
    )
    tid = cur.lastrowid
    conn.commit()
    row = conn.execute("SELECT * FROM pm_templates WHERE id=?", (tid,)).fetchone()
    conn.close()
    d = dict(row)
    d["snapshot"] = _json_loads(d.get("snapshot"), {})
    return d


@router.delete("/api/pm/templates/{template_id}")
async def pm_delete_template(template_id: int):
    conn = _get_conn()
    if not conn.execute("SELECT 1 FROM pm_templates WHERE id=?", (template_id,)).fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="template not found")
    conn.execute("DELETE FROM pm_templates WHERE id=?", (template_id,))
    conn.commit()
    conn.close()
    return {"ok": True, "template_id": template_id}


# ── PROJECT v2: OVERVIEW · RESOURCES · FOLDERS · ICONS · DEPS · GOAL-LINKS ────

def _pm_sync_rollup_goals(conn: sqlite3.Connection, project_id: int) -> None:
    """Task-mode goals derive current_value from their linked tasks' done ratio."""
    try:
        goals = conn.execute(
            "SELECT id, target_value FROM pm_goals WHERE project_id=? AND mode='task'", (project_id,)
        ).fetchall()
        for g in goals:
            total = conn.execute("SELECT COUNT(*) FROM pm_goal_tasks WHERE goal_id=?", (g["id"],)).fetchone()[0]
            done = conn.execute(
                "SELECT COUNT(*) FROM pm_goal_tasks gt JOIN tasks t ON t.id=gt.task_id "
                "WHERE gt.goal_id=? AND t.deleted_at IS NULL AND t.status_v1='done'", (g["id"],)
            ).fetchone()[0]
            tv = g["target_value"] or 100
            cv = round((done / total) * tv, 2) if total else 0
            conn.execute("UPDATE pm_goals SET current_value=? WHERE id=?", (cv, g["id"]))
    except Exception:
        pass


def _pm_serialize_resource(conn: sqlite3.Connection, r: sqlite3.Row) -> dict[str, Any]:
    d = dict(r)
    d["tags"] = _json_loads(d.get("tags"), [])
    d["has_text"] = bool(d.pop("text_content", None))
    return d


@router.get("/api/pm/projects/{project_id}/overview")
async def pm_project_overview(project_id: int):
    """One snapshot for the Overview tab + the `project_overview` Conductor tool [D16]."""
    conn = _get_conn()
    try:
        row = conn.execute("SELECT * FROM pm_projects WHERE id=?", (project_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="project not found")
        _pm_sync_rollup_goals(conn, project_id)
        proj = _pm_serialize_project(conn, row)

        tasks = conn.execute(
            "SELECT status_v1, due_at, time_estimate FROM tasks WHERE pm_project_id=? AND deleted_at IS NULL",
            (project_id,),
        ).fetchall()
        total = len(tasks)
        done = sum(1 for t in tasks if t["status_v1"] == "done")
        active = sum(1 for t in tasks if t["status_v1"] in
                     {"in_progress", "planned", "paused", "blocked", "needs_owner_input"})
        now = datetime.now(timezone.utc)
        overdue = 0
        for t in tasks:
            if t["due_at"] and t["status_v1"] not in {"done", "cancelled"}:
                try:
                    if datetime.fromisoformat(t["due_at"].replace("Z", "+00:00")) < now:
                        overdue += 1
                except Exception:
                    pass

        def _est_min(v):
            if not v:
                return 0
            m = re.findall(r"(\d+(?:\.\d+)?)\s*([hmd])", str(v).lower())
            mins = 0.0
            for num, unit in m:
                num = float(num)
                mins += num * (60 if unit == "h" else (60 * 8 if unit == "d" else 1))
            return mins
        est_total = sum(_est_min(t["time_estimate"]) for t in tasks)
        est_done = sum(_est_min(t["time_estimate"]) for t in tasks if t["status_v1"] == "done")

        active_rows = conn.execute(
            "SELECT t.*, COALESCE(p.name, pmp.name) AS project_name FROM tasks t "
            "LEFT JOIN projects p ON p.id=t.project_id LEFT JOIN pm_projects pmp ON pmp.id=t.pm_project_id "
            "WHERE t.pm_project_id=? AND t.deleted_at IS NULL AND t.status_v1 NOT IN ('done','cancelled') "
            "ORDER BY t.sort_order ASC, t.created_at ASC LIMIT 50", (project_id,),
        ).fetchall()
        active_tasks = [_serialize_task(conn, r, include_activity=False) for r in active_rows]

        goals = [_pm_serialize_goal(g) for g in conn.execute(
            "SELECT * FROM pm_goals WHERE project_id=? AND parent_goal_id IS NULL", (project_id,)).fetchall()]
        goals_avg = round(sum(g["progress_pct"] for g in goals) / len(goals), 1) if goals else 0.0

        res_count = conn.execute("SELECT COUNT(*) FROM pm_resources WHERE project_id=?", (project_id,)).fetchone()[0]
        res_bytes = pmres.project_bytes(project_id)
        conn.execute("UPDATE pm_projects SET resources_bytes=? WHERE id=?", (res_bytes, project_id))
        by_type = {}
        for r in conn.execute("SELECT rtype, COUNT(*) c FROM pm_resources WHERE project_id=? GROUP BY rtype", (project_id,)).fetchall():
            by_type[r["rtype"] or "file"] = r["c"]
        conn.commit()

        activity = []
        for a in conn.execute(
            "SELECT * FROM pm_activity WHERE project_id=? ORDER BY created_at DESC LIMIT 12", (project_id,)).fetchall():
            d = dict(a); d["diff"] = _json_loads(d.get("diff"), None); activity.append(d)

        deadline_days = None
        if proj.get("deadline"):
            try:
                dl = datetime.fromisoformat(str(proj["deadline"]).replace("Z", "+00:00"))
                if dl.tzinfo is None:
                    dl = dl.replace(tzinfo=timezone.utc)
                deadline_days = (dl - now).days
            except Exception:
                deadline_days = None

        metrics = {
            "task_total": total, "task_done": done, "task_active": active, "task_overdue": overdue,
            "progress_pct": proj.get("progress_pct", 0),
            "goals_count": len(goals), "goals_avg_pct": goals_avg,
            "goals_completed": sum(1 for g in goals if g["progress_pct"] >= 100),
            "resources_count": res_count, "resources_bytes": res_bytes, "resources_by_type": by_type,
            "estimate_total_min": round(est_total), "estimate_done_min": round(est_done),
            "deadline_days": deadline_days,
            "created_at": proj.get("created_at"), "updated_at": proj.get("updated_at"),
            "last_activity": activity[0]["created_at"] if activity else None,
        }
        return {"project": proj, "metrics": metrics, "active_tasks": active_tasks,
                "goals": goals, "activity": activity}
    finally:
        conn.close()


# ── Resources (Drive-style) ──────────────────────────────────────────────────
class PMResourceLinkRequest(BaseModel):
    url: str
    name: str | None = None
    folder_id: int | None = None
    created_by: str = "user"

class PMResourcePatchRequest(BaseModel):
    name: str | None = None
    folder_id: int | None = None
    tags: list[str] | None = None

class PMFolderCreateRequest(BaseModel):
    name: str
    parent_id: int | None = None
    created_by: str = "user"


def _pm_require_project(conn, project_id: int) -> None:
    if not conn.execute("SELECT 1 FROM pm_projects WHERE id=?", (project_id,)).fetchone():
        raise HTTPException(status_code=404, detail="project not found")


@router.get("/api/pm/projects/{project_id}/resources")
async def pm_list_resources(project_id: int, folder_id: int | None = None):
    conn = _get_conn()
    try:
        _pm_require_project(conn, project_id)
        folders = [dict(f) for f in conn.execute(
            "SELECT * FROM pm_folders WHERE project_id=? ORDER BY name", (project_id,)).fetchall()]
        sql = "SELECT * FROM pm_resources WHERE project_id=?"
        params: list[Any] = [project_id]
        if folder_id is not None:
            sql += " AND folder_id=?" if folder_id else " AND folder_id IS NULL"
            if folder_id:
                params.append(folder_id)
        sql += " ORDER BY created_at DESC"
        items = [_pm_serialize_resource(conn, r) for r in conn.execute(sql, params).fetchall()]
        return {"items": items, "folders": folders, "count": len(items)}
    finally:
        conn.close()


@router.post("/api/pm/projects/{project_id}/resources/upload")
async def pm_upload_resource(project_id: int, file: UploadFile = File(...),
                             folder_id: int | None = Form(None), created_by: str = Form("user")):
    conn = _get_conn()
    try:
        _pm_require_project(conn, project_id)
        content = await file.read()
        try:
            meta = pmres.save_file(project_id, file.filename or "file", content)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        cur = conn.execute(
            "INSERT INTO pm_resources (project_id, folder_id, kind, name, ext, source, rtype, "
            "size_bytes, disk_path, mime, text_content, created_by) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (project_id, folder_id or None, "file", meta["name"], meta["ext"], "device", meta["rtype"],
             meta["size_bytes"], meta["disk_path"], meta["mime"], meta["text_content"], created_by),
        )
        rid = cur.lastrowid
        _pm_log(conn, project_id, created_by, "resource.added", f"Uploaded {meta['name']}")
        conn.execute("UPDATE pm_projects SET resources_bytes=? WHERE id=?", (pmres.project_bytes(project_id), project_id))
        conn.commit()
        try:
            pmres.index_resource(rid, project_id, meta.get("text_content"))
        except Exception:
            pass
        r = conn.execute("SELECT * FROM pm_resources WHERE id=?", (rid,)).fetchone()
        return _pm_serialize_resource(conn, r)
    finally:
        conn.close()


@router.post("/api/pm/projects/{project_id}/resources/link")
async def pm_add_resource_link(project_id: int, payload: PMResourceLinkRequest):
    conn = _get_conn()
    try:
        _pm_require_project(conn, project_id)
        if not (payload.url or "").strip():
            raise HTTPException(status_code=400, detail="url is required")
        meta = pmres.build_link(payload.url, payload.name)
        cur = conn.execute(
            "INSERT INTO pm_resources (project_id, folder_id, kind, name, ext, source, rtype, "
            "url, text_content, created_by) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (project_id, payload.folder_id or None, "link", meta["name"], meta.get("ext"),
             meta["source"], meta["rtype"], meta["url"], meta.get("text_content"), payload.created_by),
        )
        rid = cur.lastrowid
        _pm_log(conn, project_id, payload.created_by, "resource.linked", f"Linked {meta['name']}")
        conn.commit()
        try:
            pmres.index_resource(rid, project_id, meta.get("text_content"))
        except Exception:
            pass
        r = conn.execute("SELECT * FROM pm_resources WHERE id=?", (rid,)).fetchone()
        return _pm_serialize_resource(conn, r)
    finally:
        conn.close()


@router.patch("/api/pm/projects/{project_id}/resources/{rid}")
async def pm_patch_resource(project_id: int, rid: int, payload: PMResourcePatchRequest):
    conn = _get_conn()
    try:
        r = conn.execute("SELECT * FROM pm_resources WHERE id=? AND project_id=?", (rid, project_id)).fetchone()
        if not r:
            raise HTTPException(status_code=404, detail="resource not found")
        fields, vals = [], []
        if payload.name is not None:
            fields.append("name=?"); vals.append(payload.name)
        if payload.folder_id is not None:
            fields.append("folder_id=?"); vals.append(payload.folder_id or None)
        if payload.tags is not None:
            fields.append("tags=?"); vals.append(json.dumps(payload.tags, ensure_ascii=False))
        if not fields:
            raise HTTPException(status_code=400, detail="no updates")
        fields.append("updated_at=CURRENT_TIMESTAMP"); vals.append(rid)
        conn.execute(f"UPDATE pm_resources SET {', '.join(fields)} WHERE id=?", vals)
        conn.commit()
        r = conn.execute("SELECT * FROM pm_resources WHERE id=?", (rid,)).fetchone()
        return _pm_serialize_resource(conn, r)
    finally:
        conn.close()


@router.delete("/api/pm/projects/{project_id}/resources/{rid}")
async def pm_delete_resource(project_id: int, rid: int):
    conn = _get_conn()
    try:
        r = conn.execute("SELECT * FROM pm_resources WHERE id=? AND project_id=?", (rid, project_id)).fetchone()
        if not r:
            raise HTTPException(status_code=404, detail="resource not found")
        if r["kind"] == "file" and r["disk_path"]:
            pmres.delete_file(project_id, r["disk_path"])
        conn.execute("DELETE FROM pm_resources WHERE id=?", (rid,))
        try:
            pmres.drop_resource(rid)
        except Exception:
            pass
        _pm_log(conn, project_id, "user", "resource.deleted", f"Deleted {r['name']}")
        conn.execute("UPDATE pm_projects SET resources_bytes=? WHERE id=?", (pmres.project_bytes(project_id), project_id))
        conn.commit()
        return {"ok": True, "id": rid}
    finally:
        conn.close()


@router.get("/api/pm/projects/{project_id}/resources/{rid}/raw")
async def pm_resource_raw(project_id: int, rid: int):
    conn = _get_conn()
    try:
        r = conn.execute("SELECT * FROM pm_resources WHERE id=? AND project_id=?", (rid, project_id)).fetchone()
        if not r:
            raise HTTPException(status_code=404, detail="resource not found")
        if r["kind"] == "link" and r["url"]:
            return RedirectResponse(r["url"])
        p = pmres.abs_path(project_id, r["disk_path"] or "")
        if not p:
            raise HTTPException(status_code=404, detail="file missing")
        return FileResponse(str(p), media_type=r["mime"] or "application/octet-stream",
                            filename=r["name"], content_disposition_type="inline")
    finally:
        conn.close()


# ── Folders ──────────────────────────────────────────────────────────────────
@router.post("/api/pm/projects/{project_id}/folders")
async def pm_create_folder(project_id: int, payload: PMFolderCreateRequest):
    conn = _get_conn()
    try:
        _pm_require_project(conn, project_id)
        if not (payload.name or "").strip():
            raise HTTPException(status_code=400, detail="name required")
        cur = conn.execute(
            "INSERT INTO pm_folders (project_id, parent_id, name, created_by) VALUES (?,?,?,?)",
            (project_id, payload.parent_id or None, payload.name.strip(), payload.created_by))
        fid = cur.lastrowid
        conn.commit()
        return dict(conn.execute("SELECT * FROM pm_folders WHERE id=?", (fid,)).fetchone())
    finally:
        conn.close()


class PMFolderPatchRequest(BaseModel):
    name: str


@router.patch("/api/pm/projects/{project_id}/folders/{fid}")
async def pm_patch_folder(project_id: int, fid: int, payload: PMFolderPatchRequest):
    conn = _get_conn()
    try:
        if not conn.execute("SELECT 1 FROM pm_folders WHERE id=? AND project_id=?", (fid, project_id)).fetchone():
            raise HTTPException(status_code=404, detail="folder not found")
        if not (payload.name or "").strip():
            raise HTTPException(status_code=400, detail="name required")
        conn.execute("UPDATE pm_folders SET name=? WHERE id=?", (payload.name.strip(), fid))
        conn.commit()
        return dict(conn.execute("SELECT * FROM pm_folders WHERE id=?", (fid,)).fetchone())
    finally:
        conn.close()


@router.delete("/api/pm/projects/{project_id}/folders/{fid}")
async def pm_delete_folder(project_id: int, fid: int):
    conn = _get_conn()
    try:
        if not conn.execute("SELECT 1 FROM pm_folders WHERE id=? AND project_id=?", (fid, project_id)).fetchone():
            raise HTTPException(status_code=404, detail="folder not found")
        conn.execute("UPDATE pm_resources SET folder_id=NULL WHERE folder_id=?", (fid,))  # keep the files
        conn.execute("DELETE FROM pm_folders WHERE id=?", (fid,))
        conn.commit()
        return {"ok": True, "id": fid}
    finally:
        conn.close()


# ── Custom project icons ─────────────────────────────────────────────────────
class PMIconRequest(BaseModel):
    project_id: int | None = None
    data_url: str

@router.post("/api/pm/icons")
async def pm_upload_icon(payload: PMIconRequest):
    try:
        mime, b64 = pmres.clean_icon_data_url(payload.data_url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    conn = _get_conn()
    try:
        cur = conn.execute("INSERT INTO pm_icons (project_id, mime, data) VALUES (?,?,?)",
                           (payload.project_id, mime, b64))
        iid = cur.lastrowid
        conn.commit()
        return {"ok": True, "id": iid, "url": f"/api/pm/icons/{iid}"}
    finally:
        conn.close()


@router.get("/api/pm/icons/{icon_id}")
async def pm_get_icon(icon_id: int):
    import base64 as _b64
    conn = _get_conn()
    try:
        r = conn.execute("SELECT mime, data FROM pm_icons WHERE id=?", (icon_id,)).fetchone()
        if not r:
            raise HTTPException(status_code=404, detail="icon not found")
        return Response(content=_b64.b64decode(r["data"]), media_type=r["mime"] or "image/png")
    finally:
        conn.close()


# ── Task dependencies (blocks / blocked-by) ──────────────────────────────────
class PMDepRequest(BaseModel):
    blocks_id: int

@router.post("/api/pm/tasks/{task_id}/deps")
async def pm_add_dep(task_id: int, payload: PMDepRequest):
    if task_id == payload.blocks_id:
        raise HTTPException(status_code=400, detail="a task cannot block itself")
    conn = _get_conn()
    try:
        for tid in (task_id, payload.blocks_id):
            if not conn.execute("SELECT 1 FROM tasks WHERE id=? AND deleted_at IS NULL", (tid,)).fetchone():
                raise HTTPException(status_code=404, detail=f"task {tid} not found")
        conn.execute("INSERT OR IGNORE INTO pm_task_deps (task_id, blocks_id) VALUES (?,?)",
                     (task_id, payload.blocks_id))
        conn.commit()
        return {"ok": True, "task_id": task_id, "blocks_id": payload.blocks_id}
    finally:
        conn.close()


@router.delete("/api/pm/tasks/{task_id}/deps/{blocks_id}")
async def pm_remove_dep(task_id: int, blocks_id: int):
    conn = _get_conn()
    try:
        conn.execute("DELETE FROM pm_task_deps WHERE task_id=? AND blocks_id=?", (task_id, blocks_id))
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


# ── Goal ↔ task links (rollup goals) ─────────────────────────────────────────
class PMGoalTaskRequest(BaseModel):
    task_id: int

@router.post("/api/pm/projects/{project_id}/goals/{goal_id}/tasks")
async def pm_link_goal_task(project_id: int, goal_id: int, payload: PMGoalTaskRequest):
    conn = _get_conn()
    try:
        if not conn.execute("SELECT 1 FROM pm_goals WHERE id=? AND project_id=?", (goal_id, project_id)).fetchone():
            raise HTTPException(status_code=404, detail="goal not found")
        conn.execute("INSERT OR IGNORE INTO pm_goal_tasks (goal_id, task_id) VALUES (?,?)", (goal_id, payload.task_id))
        conn.execute("UPDATE pm_goals SET mode='task' WHERE id=?", (goal_id,))
        _pm_sync_rollup_goals(conn, project_id)
        _pm_recalc_progress(conn, project_id)
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


@router.delete("/api/pm/projects/{project_id}/goals/{goal_id}/tasks/{task_id}")
async def pm_unlink_goal_task(project_id: int, goal_id: int, task_id: int):
    conn = _get_conn()
    try:
        conn.execute("DELETE FROM pm_goal_tasks WHERE goal_id=? AND task_id=?", (goal_id, task_id))
        _pm_sync_rollup_goals(conn, project_id)
        _pm_recalc_progress(conn, project_id)
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


# ── PM STATS (Dashboard widget) ───────────────────────────────────────────────

@router.get("/api/pm/stats")
async def pm_stats():
    conn = _get_conn()
    active = conn.execute("SELECT COUNT(*) FROM pm_projects WHERE status='active'").fetchone()[0]
    total  = conn.execute("SELECT COUNT(*) FROM pm_projects WHERE status!='archived'").fetchone()[0]
    today  = conn.execute(
        "SELECT COUNT(*) FROM tasks WHERE pm_project_id IS NOT NULL AND deleted_at IS NULL "
        "AND status_v1!='done' AND due_at IS NOT NULL AND date(due_at)<=date('now')"
    ).fetchone()[0]
    last_mission = conn.execute(
        "SELECT prompt, status, created_at FROM pm_missions ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    conn.close()
    return {
        "active_projects": active,
        "total_projects": total,
        "tasks_due_today": today,
        "last_mission": dict(last_mission) if last_mission else None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

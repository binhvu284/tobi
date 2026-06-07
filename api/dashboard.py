"""Mission Control Dashboard — Tobi Agent"""
from core.env_utils import safe_load_dotenv
safe_load_dotenv()

import os
import asyncio
import sqlite3
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request, Body
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from core.database import (
    init_database, get_dashboard, get_all_projects,
    get_all_lessons, get_pending_human_tasks_all, complete_task,
)

LOGS_DIR = Path(__file__).parent.parent / "logs"
API_PORT = os.getenv("API_PORT", "8000")

TASK_STATUS_V1 = {
    "planned",
    "in_progress",
    "paused",
    "blocked",
    "needs_owner_input",
    "done",
    "cancelled",
}

HIGH_RISK_TRANSITIONS = {
    "done",
    "cancelled",
}

ALLOWED_AGENTS = {"tobi", "research", "coder", "ceo"}
ALLOWED_PRIORITIES = {"P0", "P1", "P2", "P3"}


class OwnerInputItem(BaseModel):
    item_key: str
    label: str
    input_type: str = Field(default="text")
    required: bool = True
    placeholder: str | None = None
    value_text: str | None = None
    file_path: str | None = None
    status: str | None = None


class TaskCreateRequest(BaseModel):
    title: str
    objective: str | None = None
    success_criteria: str | None = None
    description: str | None = None
    status: str = "planned"
    priority: str = "P2"
    owner: str = "owner"
    agent: str = "tobi"
    project_id: int | None = None
    project_name: str | None = None
    due_at: str | None = None
    checklist: list[OwnerInputItem] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)


class TaskPatchRequest(BaseModel):
    status: str | None = None
    priority: str | None = None
    agent: str | None = None
    due_at: str | None = None
    before_task_id: int | None = None
    owner: str | None = None
    title: str | None = None
    objective: str | None = None
    success_criteria: str | None = None
    require_confirmation: bool = False
    confirmed: bool = False


class TaskReorderRequest(BaseModel):
    task_id: int
    target_status: str | None = None
    before_task_id: int | None = None
    confirmed: bool = False


class TaskAuditEntry(BaseModel):
    id: int
    task_id: int
    activity_type: str
    author: str
    message: str
    payload: dict[str, Any]
    created_at: str


class TaskNoteRequest(BaseModel):
    note: str
    author: str = "owner"


class OwnerInputSubmissionRequest(BaseModel):
    items: list[OwnerInputItem] = Field(default_factory=list)
    author: str = "owner"


class TaskInputEvaluationRequest(BaseModel):
    author: str = "tobi"


class TaskCommandRequest(BaseModel):
    command: str
    author: str = "owner"


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

app = FastAPI(title="Tobi Mission Control")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

from starlette.middleware.base import BaseHTTPMiddleware

class NoCacheAPIMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
            response.headers["Pragma"] = "no-cache"
        return response

app.add_middleware(NoCacheAPIMiddleware)

DIST_DIR = Path(__file__).parent.parent / "dashboard" / "dist"
DB_PATH = os.path.expanduser(os.getenv("DB_PATH", "~/.mmo_agent/agent.db"))


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
    }
    if include_activity:
        task["activity"] = _fetch_activity(conn, row["id"])
    return task


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


# ── API routes ────────────────────────────────────────────────────────────────

@app.get("/api/status")
async def api_status():
    return get_dashboard()


@app.get("/api/projects")
async def api_projects():
    return get_all_projects()


@app.get("/api/lessons")
async def api_lessons():
    return get_all_lessons()


class AgentUpsertRequest(BaseModel):
    id: str | None = None
    name: str
    role: str | None = None
    persona: str | None = None
    provider: str = "openrouter"
    model: str | None = None
    key_ref: str | None = None          # env-var NAME only (D37); never the secret
    temperature: float = 0.7
    max_tokens: int = 2000
    autonomy: str = "medium"
    can_spawn: bool = False
    daily_budget_tokens: int = 0
    skills: list[str] = Field(default_factory=list)
    color: str | None = None
    sprite: str | None = None


def _serialize_agent(conn: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
    a = dict(row)
    a["skills"] = _json_loads(a.pop("skills_json", None), [])
    a["perms"] = _json_loads(a.pop("perms_json", None), {})
    a["can_spawn"] = bool(a.get("can_spawn"))
    a["is_head"] = bool(a.get("is_head"))
    st = conn.execute("SELECT * FROM agent_state WHERE agent_id=?", (a["id"],)).fetchone()
    # A running mission step assigned to this agent overrides idle → working.
    running = conn.execute(
        """SELECT m.id, m.title, s.action FROM mission_steps s
           JOIN missions m ON m.id = s.mission_id
           WHERE s.agent_id=? AND s.status='running' ORDER BY s.id DESC LIMIT 1""",
        (a["id"],),
    ).fetchone()
    runtime = (st["runtime_status"] if st else "idle") or "idle"
    detail = st["detail"] if st else None
    if running:
        runtime = "working"
        detail = f"{running['action']} · {running['title']}"
    a["live"] = {
        "status": "online" if a["is_head"] and runtime == "idle" else runtime,
        "detail": detail or (a.get("role") or ""),
        "last_active": fmt_ago(st["last_active_at"]) if st and st["last_active_at"] else None,
        "current_mission_id": st["current_mission_id"] if st else None,
    }
    return a


@app.get("/api/agents")
async def api_agents():
    """Real agent registry (replaces the old hardcoded 4-agent status). Returns
    each agent's config + a derived live block for the Office scene/roster."""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM agents WHERE status='active' ORDER BY is_head DESC, id"
    ).fetchall()
    agents = [_serialize_agent(conn, r) for r in rows]
    conn.close()
    return {"agents": agents, "timestamp": datetime.now(timezone.utc).isoformat()}


@app.get("/api/agents/{agent_id}")
async def api_agent_detail(agent_id: str):
    conn = _get_conn()
    row = conn.execute("SELECT * FROM agents WHERE id=?", (agent_id,)).fetchone()
    if row is None:
        conn.close()
        raise HTTPException(status_code=404, detail=f"unknown agent '{agent_id}'")
    agent = _serialize_agent(conn, row)
    # Empirical scorecard (D28): missions touched, steps, tokens, success.
    scard = conn.execute(
        """SELECT COUNT(DISTINCT mission_id) missions, COUNT(*) steps,
                  SUM(CASE WHEN status='done' THEN 1 ELSE 0 END) done,
                  COALESCE(SUM(tokens),0) tokens
           FROM mission_steps WHERE agent_id=?""", (agent_id,)
    ).fetchone()
    agent["scorecard"] = dict(scard) if scard else {}
    conn.close()
    return agent


@app.post("/api/agents")
async def api_agent_create(payload: AgentUpsertRequest):
    aid = (payload.id or payload.name.lower().replace(" ", "_"))[:40]
    conn = _get_conn()
    if conn.execute("SELECT 1 FROM agents WHERE id=?", (aid,)).fetchone():
        conn.close()
        raise HTTPException(status_code=409, detail=f"agent '{aid}' already exists")
    conn.execute(
        """INSERT INTO agents (id, name, role, persona, provider, model, key_ref, temperature,
                               max_tokens, autonomy, can_spawn, daily_budget_tokens, skills_json,
                               color, sprite)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (aid, payload.name, payload.role, payload.persona, payload.provider, payload.model,
         payload.key_ref, payload.temperature, payload.max_tokens, payload.autonomy,
         int(payload.can_spawn), payload.daily_budget_tokens, json.dumps(payload.skills),
         payload.color or "#58a6ff", payload.sprite or "tobi"),
    )
    conn.execute("INSERT OR IGNORE INTO agent_state (agent_id, runtime_status) VALUES (?, 'idle')", (aid,))
    conn.commit()
    row = conn.execute("SELECT * FROM agents WHERE id=?", (aid,)).fetchone()
    agent = _serialize_agent(conn, row)
    conn.close()
    return agent


@app.patch("/api/agents/{agent_id}")
async def api_agent_patch(agent_id: str, payload: AgentUpsertRequest):
    conn = _get_conn()
    if conn.execute("SELECT 1 FROM agents WHERE id=?", (agent_id,)).fetchone() is None:
        conn.close()
        raise HTTPException(status_code=404, detail=f"unknown agent '{agent_id}'")
    conn.execute(
        """UPDATE agents SET name=?, role=?, persona=?, provider=?, model=?, key_ref=?,
               temperature=?, max_tokens=?, autonomy=?, can_spawn=?, daily_budget_tokens=?,
               skills_json=?, color=?, sprite=?, updated_at=CURRENT_TIMESTAMP WHERE id=?""",
        (payload.name, payload.role, payload.persona, payload.provider, payload.model,
         payload.key_ref, payload.temperature, payload.max_tokens, payload.autonomy,
         int(payload.can_spawn), payload.daily_budget_tokens, json.dumps(payload.skills),
         payload.color, payload.sprite, agent_id),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM agents WHERE id=?", (agent_id,)).fetchone()
    agent = _serialize_agent(conn, row)
    conn.close()
    return agent


@app.delete("/api/agents/{agent_id}")
async def api_agent_delete(agent_id: str):
    """Soft-archive (D59). Blocks the head agent and any agent with a running step."""
    conn = _get_conn()
    row = conn.execute("SELECT is_head FROM agents WHERE id=?", (agent_id,)).fetchone()
    if row is None:
        conn.close()
        raise HTTPException(status_code=404, detail=f"unknown agent '{agent_id}'")
    if row["is_head"]:
        conn.close()
        raise HTTPException(status_code=409, detail="cannot archive the head agent")
    busy = conn.execute(
        "SELECT COUNT(*) FROM mission_steps WHERE agent_id=? AND status='running'", (agent_id,)
    ).fetchone()[0]
    if busy:
        conn.close()
        raise HTTPException(status_code=409, detail="agent has running work; pause its missions first")
    conn.execute("UPDATE agents SET status='archived', updated_at=CURRENT_TIMESTAMP WHERE id=?", (agent_id,))
    conn.commit()
    conn.close()
    return {"ok": True, "agent_id": agent_id, "archived": True}


# ── MISSIONS / WORKFLOWS / OFFICE STATS (Mission Control §4) ───────────────────

MISSION_PRIORITIES = {"Low", "Normal", "High", "Urgent"}
MISSION_STATUSES = {"planned", "running", "blocked", "done", "cancelled"}


class MissionCreateRequest(BaseModel):
    title: str
    goal: str | None = None
    priority: str = "Normal"
    workflow_id: int | None = None      # defaults to the active workflow


class MissionPatchRequest(BaseModel):
    title: str | None = None
    goal: str | None = None
    status: str | None = None
    priority: str | None = None


def _serialize_mission(conn: sqlite3.Connection, row: sqlite3.Row, include_steps: bool = False) -> dict[str, Any]:
    m = dict(row)
    if include_steps:
        m["steps"] = [dict(r) for r in conn.execute(
            "SELECT * FROM mission_steps WHERE mission_id=? ORDER BY seq", (m["id"],)
        ).fetchall()]
        m["usage"] = [dict(r) for r in conn.execute(
            """SELECT agent_id, provider, model, SUM(total_tokens) total_tokens, COUNT(*) calls
               FROM llm_usage WHERE mission_id=? GROUP BY agent_id, provider, model""", (m["id"],)
        ).fetchall()]
    return m


@app.get("/api/missions")
async def api_missions(status: str = Query(default="all")):
    conn = _get_conn()
    if status == "all":
        rows = conn.execute("SELECT * FROM missions ORDER BY created_at DESC").fetchall()
    else:
        rows = conn.execute("SELECT * FROM missions WHERE status=? ORDER BY created_at DESC", (status,)).fetchall()
    items = [_serialize_mission(conn, r) for r in rows]
    conn.close()
    return {"items": items, "count": len(items), "timestamp": datetime.now(timezone.utc).isoformat()}


@app.get("/api/missions/{mission_id}")
async def api_mission_detail(mission_id: int):
    conn = _get_conn()
    row = conn.execute("SELECT * FROM missions WHERE id=?", (mission_id,)).fetchone()
    if row is None:
        conn.close()
        raise HTTPException(status_code=404, detail="unknown mission")
    m = _serialize_mission(conn, row, include_steps=True)
    conn.close()
    return m


@app.post("/api/missions")
async def api_mission_create(payload: MissionCreateRequest):
    if payload.priority not in MISSION_PRIORITIES:
        raise HTTPException(status_code=400, detail=f"bad priority; use {sorted(MISSION_PRIORITIES)}")
    conn = _get_conn()
    wf_id = payload.workflow_id
    wf_version = None
    if wf_id is None:
        wf = conn.execute("SELECT id, version FROM workflows WHERE is_active=1 ORDER BY version DESC LIMIT 1").fetchone()
        if wf:
            wf_id, wf_version = wf["id"], wf["version"]
    else:
        wf = conn.execute("SELECT version FROM workflows WHERE id=?", (wf_id,)).fetchone()
        wf_version = wf["version"] if wf else None
    cur = conn.execute(
        "INSERT INTO missions (title, goal, priority, workflow_id, workflow_version) VALUES (?,?,?,?,?)",
        (payload.title, payload.goal, payload.priority, wf_id, wf_version),
    )
    mid = cur.lastrowid
    conn.commit()
    row = conn.execute("SELECT * FROM missions WHERE id=?", (mid,)).fetchone()
    m = _serialize_mission(conn, row, include_steps=True)
    conn.close()
    return m


@app.patch("/api/missions/{mission_id}")
async def api_mission_patch(mission_id: int, payload: MissionPatchRequest):
    conn = _get_conn()
    row = conn.execute("SELECT * FROM missions WHERE id=?", (mission_id,)).fetchone()
    if row is None:
        conn.close()
        raise HTTPException(status_code=404, detail="unknown mission")
    if payload.status and payload.status not in MISSION_STATUSES:
        conn.close()
        raise HTTPException(status_code=400, detail=f"bad status; use {sorted(MISSION_STATUSES)}")
    if payload.priority and payload.priority not in MISSION_PRIORITIES:
        conn.close()
        raise HTTPException(status_code=400, detail=f"bad priority; use {sorted(MISSION_PRIORITIES)}")
    fields, vals = [], []
    for col, v in [("title", payload.title), ("goal", payload.goal),
                   ("status", payload.status), ("priority", payload.priority)]:
        if v is not None:
            fields.append(f"{col}=?"); vals.append(v)
    if fields:
        vals.append(mission_id)
        conn.execute(f"UPDATE missions SET {', '.join(fields)} WHERE id=?", vals)
        conn.commit()
    row = conn.execute("SELECT * FROM missions WHERE id=?", (mission_id,)).fetchone()
    m = _serialize_mission(conn, row, include_steps=True)
    conn.close()
    return m


class InjectRequest(BaseModel):
    text: str


@app.post("/api/missions/{mission_id}/run")
async def api_mission_run(mission_id: int, mock: bool = Query(default=False)):
    """Start the mission's workflow as a **streamed background run** (non-blocking).
    Subscribe to `GET /api/missions/{id}/events` to watch it live. `mock=true` forces
    the offline deterministic engine (no keys/cost) — the war-room default."""
    from core.office_stream import start_run, broker
    conn = _get_conn()
    exists = conn.execute("SELECT 1 FROM missions WHERE id=?", (mission_id,)).fetchone()
    conn.close()
    if not exists:
        raise HTTPException(status_code=404, detail="unknown mission")
    if broker.is_running(mission_id):
        raise HTTPException(status_code=409, detail="mission already running")
    start_run(mission_id, mock)
    return {"ok": True, "streaming": True, "mission_id": mission_id, "mock": mock}


def _sse(ev: dict) -> str:
    return f"id: {ev['seq']}\nevent: {ev['type']}\ndata: {json.dumps(ev['data'])}\n\n"


@app.get("/api/missions/{mission_id}/events")
async def api_mission_events(mission_id: int, request: Request, since: int = Query(default=0)):
    """SSE stream for a mission: replays state since `?since=` (or Last-Event-ID) then
    tails live. Heartbeats keep the connection open; X-Accel-Buffering disables proxy buffering."""
    from core.office_stream import broker
    last_hdr = request.headers.get("last-event-id")
    start_since = int(last_hdr) if (last_hdr and last_hdr.isdigit()) else since

    async def gen():
        for ev in broker.replay(mission_id, start_since):
            yield _sse(ev)
        q = broker.subscribe(mission_id)
        try:
            while True:
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=15)
                    yield _sse(ev)
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
                if await request.is_disconnected():
                    break
        finally:
            broker.unsubscribe(mission_id, q)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"})


@app.post("/api/missions/{mission_id}/{action}")
async def api_mission_control(mission_id: int, action: str, payload: InjectRequest | None = None):
    """Mid-mission steering (D58/D32): pause | resume | cancel | inject. Effective
    between steps — a cancel during an in-flight LLM call lands after that step returns."""
    from core.office_stream import broker
    if action not in ("pause", "resume", "cancel", "inject"):
        raise HTTPException(status_code=404, detail="unknown action")
    flag = broker.flag(mission_id)
    if action == "pause": flag["paused"] = True
    elif action == "resume": flag["paused"] = False
    elif action == "cancel": flag["cancel"] = True
    elif action == "inject":
        if not payload or not payload.text.strip():
            raise HTTPException(status_code=400, detail="inject needs text")
        flag["injects"].append(payload.text.strip())
    return {"ok": True, "mission_id": mission_id, "action": action}


@app.get("/api/workflows")
async def api_workflows():
    conn = _get_conn()
    rows = conn.execute("SELECT * FROM workflows ORDER BY name, version DESC").fetchall()
    items = []
    for r in rows:
        d = dict(r)
        d["steps"] = _json_loads(d.pop("definition_json", None), [])
        items.append(d)
    conn.close()
    return {"items": items, "count": len(items)}


@app.get("/api/office/stats")
async def api_office_stats():
    """Org KPIs + integration health — the REAL signals that replace the Office
    page's old fake CPU/MEM/NET overlay (D43)."""
    conn = _get_conn()
    def c(q, p=()):
        try: return conn.execute(q, p).fetchone()[0] or 0
        except sqlite3.Error: return 0
    missions_by_status = {}
    try:
        for r in conn.execute("SELECT status, COUNT(*) n FROM missions GROUP BY status"):
            missions_by_status[r["status"]] = r["n"]
    except sqlite3.Error:
        pass
    stats = {
        "agents_active": c("SELECT COUNT(*) FROM agents WHERE status='active'"),
        "agents_working": c("SELECT COUNT(*) FROM agent_state WHERE runtime_status='working'"),
        "missions_total": c("SELECT COUNT(*) FROM missions"),
        "missions_running": missions_by_status.get("running", 0),
        "missions_done": missions_by_status.get("done", 0),
        "missions_by_status": missions_by_status,
        "tokens_total": c("SELECT COALESCE(SUM(total_tokens),0) FROM llm_usage"),
        "steps_total": c("SELECT COUNT(*) FROM mission_steps"),
    }
    conn.close()
    # integration health (env-only, no network) — same source as /api/health
    integrations: dict[str, bool] = {}
    try:
        from core.integrations import check_all
        integrations = check_all()
    except Exception:  # noqa: BLE001
        pass
    return {"stats": stats, "integrations": integrations,
            "timestamp": datetime.now(timezone.utc).isoformat()}


# ── FEATURE TRIGGERS (Control Room / ⌘K) ──────────────────────────────────────
# Each engine declares the env key it needs; triggers precheck it and fail
# gracefully (no 500, no silent token spend). "report" is a safe DB-only summary
# (no LLM, no Telegram send) so it's always runnable.
RUN_ENGINES = {
    "research": {"label": "Research", "needs": "OPENROUTER_API_KEY", "note": "Web search + LLM → scores & saves niches"},
    "execute":  {"label": "Execution cycle", "needs": "OPENROUTER_API_KEY", "note": "Runs up to 3 tasks per active project"},
    "ceo":      {"label": "CEO review", "needs": "OPENROUTER_API_KEY", "note": "ROI review + strategy (LLM)"},
    "report":   {"label": "Daily report", "needs": None, "note": "Builds a summary from the DB — no send, no cost"},
}


def _build_daily_summary() -> str:
    conn = _get_conn()
    try:
        active = _count(conn, "SELECT COUNT(*) FROM projects WHERE status IN ('active','approved')")
        done_today = _count(conn, "SELECT COUNT(*) FROM tasks WHERE date(completed_at)=date('now') AND completed_at IS NOT NULL")
        pending = _count(conn, "SELECT COUNT(*) FROM tasks WHERE task_type='human' AND status NOT IN ('done','skipped')")
        try:
            rev = conn.execute("SELECT COALESCE(SUM(amount),0) FROM revenue WHERE strftime('%Y-%m', recorded_at)=strftime('%Y-%m','now')").fetchone()[0]
        except sqlite3.Error:
            rev = 0
        last_lesson = _last(conn, "SELECT title FROM lessons ORDER BY created_at DESC LIMIT 1")
    finally:
        conn.close()
    return (f"Active projects: {active} · Tasks completed today: {done_today} · "
            f"Pending owner todos: {pending} · Revenue this month: ${rev:.2f}"
            + (f" · Latest lesson: {last_lesson}" if last_lesson else ""))


@app.get("/api/run/readiness")
async def api_run_readiness():
    engines = []
    for name, cfg in RUN_ENGINES.items():
        ready = not (cfg["needs"] and not os.getenv(cfg["needs"]))
        engines.append({"engine": name, "label": cfg["label"], "ready": ready,
                        "needs": None if ready else cfg["needs"], "note": cfg["note"]})
    return {"engines": engines, "timestamp": datetime.now(timezone.utc).isoformat()}


@app.post("/api/run/{engine}")
async def api_run_engine(engine: str):
    cfg = RUN_ENGINES.get(engine)
    if cfg is None:
        raise HTTPException(status_code=404, detail=f"unknown engine '{engine}'")
    if cfg["needs"] and not os.getenv(cfg["needs"]):
        return {"ok": False, "engine": engine, "needs": cfg["needs"],
                "message": f"Can't run — {cfg['needs']} not configured",
                "detail": f"Add {cfg['needs']} to .env and restart to enable {cfg['label']}."}
    try:
        if engine == "report":
            summary = await asyncio.to_thread(_build_daily_summary)
            return {"ok": True, "engine": engine, "message": "Report generated (not sent)", "detail": summary}
        if engine == "research":
            from core.research_engine import run_research_cycle
            ids = await asyncio.to_thread(run_research_cycle)
            return {"ok": True, "engine": engine, "message": f"Research complete — {len(ids)} niche(s) saved"}
        if engine == "execute":
            from core.project_executor import execute_all_projects
            results = await asyncio.to_thread(execute_all_projects, 3)
            n = sum(r.get("tasks_executed", 0) for r in (results or []))
            return {"ok": True, "engine": engine, "message": f"Execution cycle done — {n} task(s) executed"}
        if engine == "ceo":
            from core.ceo_loop import run_ceo_review
            analysis = await asyncio.to_thread(run_ceo_review)
            detail = ""
            if isinstance(analysis, dict):
                detail = str(analysis.get("summary") or analysis.get("strategy") or "")[:240]
            return {"ok": True, "engine": engine, "message": "CEO review complete", "detail": detail}
    except Exception as e:  # noqa: BLE001 — surface, don't 500
        return {"ok": False, "engine": engine, "message": f"{cfg['label']} failed", "detail": str(e)[:240]}
    return {"ok": False, "engine": engine, "message": "unhandled"}


# ── ABILITY MODULE (Mission Control §3) ────────────────────────────────────────

class CoachRequest(BaseModel):
    note: str
    author: str = "owner"


def _count(conn: sqlite3.Connection, query: str, params: tuple = ()) -> int:
    try:
        row = conn.execute(query, params).fetchone()
        return int(row[0]) if row and row[0] is not None else 0
    except sqlite3.Error:
        return 0


@app.get("/api/abilities")
async def api_abilities():
    """Live usage per ability, keyed by ability id. Fast — DB reads + env-only
    integration check, no LLM/network. Sparse by design: a missing key means
    'no live signal yet' and the frontend falls back to curated values."""
    conn = _get_conn()
    ab: dict[str, dict] = {}

    # Communication
    n = _count(conn, "SELECT COUNT(*) FROM conversations")
    if n:
        ab["chat"] = {"count": n, "last_active": fmt_ago(_last(conn, "SELECT MAX(created_at) FROM conversations"))}
    n = _count(conn, "SELECT COUNT(*) FROM reports WHERE report_type='daily'")
    if n:
        ab["reports"] = {"count": n, "last_active": fmt_ago(_last(conn, "SELECT MAX(created_at) FROM reports WHERE report_type='daily'"))}

    # Building
    coder_total = _count(conn, "SELECT COUNT(*) FROM tasks WHERE agent_key='coder'")
    if coder_total:
        done = _count(conn, "SELECT COUNT(*) FROM tasks WHERE agent_key='coder' AND (status_v1='done' OR status='done')")
        ab["coding"] = {
            "count": coder_total, "done": done,
            "success_rate": round(done / coder_total, 3) if coder_total else None,
            "last_active": fmt_ago(_last(conn, "SELECT MAX(created_at) FROM tasks WHERE agent_key='coder'")),
        }
    done_all = _count(conn, "SELECT COUNT(*) FROM tasks WHERE completed_at IS NOT NULL")
    if done_all:
        ab["executor"] = {"count": done_all, "last_active": fmt_ago(_last(conn, "SELECT MAX(completed_at) FROM tasks WHERE completed_at IS NOT NULL"))}

    # Strategy
    lessons_n = _count(conn, "SELECT COUNT(*) FROM lessons")
    research_reports = _count(conn, "SELECT COUNT(*) FROM reports WHERE report_type='niche_research'")
    if lessons_n or research_reports:
        try:
            row = conn.execute("SELECT AVG(impact_score) FROM lessons").fetchone()
            avg_impact = round(float(row[0]), 1) if row and row[0] is not None else None
        except sqlite3.Error:
            avg_impact = None
        ab["research"] = {
            "count": lessons_n + research_reports, "avg_impact": avg_impact,
            "last_active": fmt_ago(_last(conn, "SELECT MAX(created_at) FROM lessons")),
        }
    n = _count(conn, "SELECT COUNT(*) FROM strategy")
    if n:
        ab["ceo"] = {"count": n, "last_active": fmt_ago(_last(conn, "SELECT MAX(created_at) FROM strategy"))}
    proj_n = _count(conn, "SELECT COUNT(*) FROM projects")
    if proj_n:
        try:
            rev_row = conn.execute("SELECT COALESCE(SUM(amount), 0) FROM revenue").fetchone()
            rev = round(float(rev_row[0]), 2) if rev_row else 0
        except sqlite3.Error:
            rev = 0
        ab["tracker"] = {"count": proj_n, "revenue_tracked": rev}

    # Learning
    if lessons_n:
        ab["learning"] = {
            "count": lessons_n,
            "success": _count(conn, "SELECT COUNT(*) FROM lessons WHERE lesson_type='success'"),
            "failure": _count(conn, "SELECT COUNT(*) FROM lessons WHERE lesson_type='failure'"),
            "last_active": fmt_ago(_last(conn, "SELECT MAX(created_at) FROM lessons")),
        }

    conn.close()

    # Integrations: env-only config check (notion/github/google/vercel/supabase)
    try:
        from core.integrations import check_all
        checks = check_all()
        configured = sum(1 for v in checks.values() if v)
        ab["integrations"] = {"configured": configured, "of": len(checks)}
    except Exception:  # noqa: BLE001
        pass

    return {"timestamp": datetime.now(timezone.utc).isoformat(), "abilities": ab}


@app.get("/api/abilities/{skill_id}")
async def api_ability_detail(skill_id: str):
    """Full registry record + metrics + version history + dependency edges."""
    conn = _get_conn()
    row = conn.execute("SELECT * FROM skills WHERE id=?", (skill_id,)).fetchone()
    if row is None:
        conn.close()
        raise HTTPException(status_code=404, detail=f"unknown skill '{skill_id}'")
    skill = dict(row)
    metrics_row = conn.execute("SELECT * FROM skill_metrics WHERE skill_id=?", (skill_id,)).fetchone()
    versions = [dict(r) for r in conn.execute(
        "SELECT id, version, diff_summary, metric_snapshot_json, provenance_json, created_at "
        "FROM skill_versions WHERE skill_id=? ORDER BY version DESC", (skill_id,)
    ).fetchall()]
    deps = [dict(r) for r in conn.execute(
        "SELECT child_id, pinned_version FROM skill_deps WHERE parent_id=?", (skill_id,)
    ).fetchall()]
    conn.close()
    return {
        "skill": skill,
        "metrics": dict(metrics_row) if metrics_row else None,
        "versions": versions,
        "deps": deps,
    }


@app.post("/api/abilities/{skill_id}/coach")
async def api_ability_coach(skill_id: str, payload: CoachRequest):
    """Owner-coached refinement (D8/H11). Stores the note as a lesson AND queues a
    pending edit proposal — no autonomous apply in Phase 1; Thomas approves it."""
    note = payload.note.strip()
    if not note:
        raise HTTPException(status_code=400, detail="empty coaching note")
    conn = _get_conn()
    skill = conn.execute("SELECT id, name, risk_tier FROM skills WHERE id=?", (skill_id,)).fetchone()
    if skill is None:
        conn.close()
        raise HTTPException(status_code=404, detail=f"unknown skill '{skill_id}'")
    try:
        conn.execute(
            "INSERT INTO lessons (lesson_type, title, content, impact_score) VALUES ('insight', ?, ?, 7)",
            (f"Coaching: {skill['name']}", note),
        )
    except sqlite3.Error:
        pass
    cur = conn.execute(
        """INSERT INTO skill_proposals (skill_id, kind, risk_tier, title, payload_json, rationale)
           VALUES (?, 'edit', ?, ?, ?, ?)""",
        (skill_id, skill["risk_tier"], f"Coaching note for {skill['name']}",
         json.dumps({"coach_note": note, "author": payload.author}), note),
    )
    proposal_id = cur.lastrowid
    conn.commit()
    conn.close()
    return {"ok": True, "proposal_id": proposal_id, "queued": "pending"}


@app.get("/api/proposals")
async def api_proposals(status: str = Query(default="pending")):
    """Evolution approval inbox (D13/D48). status=pending|approved|rejected|all."""
    conn = _get_conn()
    if status == "all":
        rows = conn.execute(
            "SELECT * FROM skill_proposals ORDER BY created_at DESC"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM skill_proposals WHERE status=? ORDER BY created_at DESC", (status,)
        ).fetchall()
    items = []
    for r in rows:
        d = dict(r)
        d["payload"] = _json_loads(d.pop("payload_json", None), {})
        items.append(d)
    conn.close()
    return {"items": items, "count": len(items), "timestamp": datetime.now(timezone.utc).isoformat()}


@app.post("/api/proposals/{proposal_id}/approve")
async def api_proposal_approve(proposal_id: int):
    """Approve a proposal → write a new immutable skill_versions row + bump the
    skill's active version pointer (D54/H15). Functions fully without Hermes."""
    conn = _get_conn()
    prop = conn.execute("SELECT * FROM skill_proposals WHERE id=?", (proposal_id,)).fetchone()
    if prop is None:
        conn.close()
        raise HTTPException(status_code=404, detail="unknown proposal")
    if prop["status"] != "pending":
        conn.close()
        raise HTTPException(status_code=409, detail=f"proposal already {prop['status']}")

    payload = _json_loads(prop["payload_json"], {})
    skill_id = prop["skill_id"]
    new_version = None
    if skill_id:
        skill = conn.execute("SELECT * FROM skills WHERE id=?", (skill_id,)).fetchone()
        if skill is not None:
            new_version = int(skill["version"] or 1) + 1
            body = payload.get("coach_note") or payload.get("body") or skill["instructions"] or ""
            metrics_row = conn.execute("SELECT * FROM skill_metrics WHERE skill_id=?", (skill_id,)).fetchone()
            conn.execute(
                """INSERT INTO skill_versions (skill_id, version, body, diff_summary, metric_snapshot_json, provenance_json)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (skill_id, new_version, body, prop["title"] or "Approved proposal",
                 json.dumps(dict(metrics_row)) if metrics_row else None,
                 json.dumps({"actor": "owner", "trigger": "proposal_approve", "proposal_id": proposal_id})),
            )
            conn.execute(
                "UPDATE skills SET version=?, instructions=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (new_version, body, skill_id),
            )
    conn.execute(
        "UPDATE skill_proposals SET status='approved', resolved_at=CURRENT_TIMESTAMP WHERE id=?",
        (proposal_id,),
    )
    conn.commit()
    conn.close()
    return {"ok": True, "proposal_id": proposal_id, "skill_id": skill_id, "new_version": new_version}


@app.post("/api/proposals/{proposal_id}/reject")
async def api_proposal_reject(proposal_id: int):
    conn = _get_conn()
    prop = conn.execute("SELECT status FROM skill_proposals WHERE id=?", (proposal_id,)).fetchone()
    if prop is None:
        conn.close()
        raise HTTPException(status_code=404, detail="unknown proposal")
    if prop["status"] != "pending":
        conn.close()
        raise HTTPException(status_code=409, detail=f"proposal already {prop['status']}")
    conn.execute(
        "UPDATE skill_proposals SET status='rejected', resolved_at=CURRENT_TIMESTAMP WHERE id=?",
        (proposal_id,),
    )
    conn.commit()
    conn.close()
    return {"ok": True, "proposal_id": proposal_id}


@app.post("/api/abilities/{skill_id}/rollback/{version}")
async def api_ability_rollback(skill_id: str, version: int):
    """Rollback (D54/H15): rewrite the active body from a prior version into a NEW
    forward version — never mutates history (the ledger is append-only)."""
    conn = _get_conn()
    skill = conn.execute("SELECT * FROM skills WHERE id=?", (skill_id,)).fetchone()
    if skill is None:
        conn.close()
        raise HTTPException(status_code=404, detail=f"unknown skill '{skill_id}'")
    target = conn.execute(
        "SELECT body FROM skill_versions WHERE skill_id=? AND version=?", (skill_id, version)
    ).fetchone()
    if target is None:
        conn.close()
        raise HTTPException(status_code=404, detail=f"no version {version} for '{skill_id}'")
    new_version = int(skill["version"] or 1) + 1
    body = target["body"]
    conn.execute(
        """INSERT INTO skill_versions (skill_id, version, body, diff_summary, provenance_json)
           VALUES (?, ?, ?, ?, ?)""",
        (skill_id, new_version, body, f"Rollback to v{version}",
         json.dumps({"actor": "owner", "trigger": "rollback", "from_version": version})),
    )
    conn.execute(
        "UPDATE skills SET version=?, instructions=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (new_version, body, skill_id),
    )
    conn.commit()
    conn.close()
    return {"ok": True, "skill_id": skill_id, "new_version": new_version, "from_version": version}


@app.post("/done/{task_id}")
async def mark_done(task_id: int):
    conn = _get_conn()
    try:
        row = _fetch_task_row(conn, task_id)
        if not row:
            raise HTTPException(status_code=404, detail="Task not found")
        conn.execute(
            """
            UPDATE tasks
            SET status='done', status_v1='done', completed_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP
            WHERE id=?
            """,
            (task_id,),
        )
        _append_activity(conn, task_id, "status_change", "owner", "Marked done via Mission Control", {
            "to": "done",
            "compat_endpoint": True,
        })
        conn.commit()
        return {"status": "done", "task_id": task_id}
    finally:
        conn.close()


def _validate_status(value: str) -> str:
    if value not in TASK_STATUS_V1:
        raise HTTPException(status_code=400, detail=f"Invalid status '{value}'")
    return value


def _validate_priority(value: str) -> str:
    if value not in ALLOWED_PRIORITIES:
        raise HTTPException(status_code=400, detail=f"Invalid priority '{value}'")
    return value


def _validate_agent(value: str) -> str:
    if value not in ALLOWED_AGENTS:
        raise HTTPException(status_code=400, detail=f"Invalid agent '{value}'")
    return value


@app.get("/api/tasks")
async def api_tasks(
    status: list[str] = Query(default=[]),
    priority: list[str] = Query(default=[]),
    owner: list[str] = Query(default=[]),
    agent: list[str] = Query(default=[]),
    project_id: int | None = None,
    overdue: bool | None = None,
    q: str | None = None,
):
    conn = _get_conn()
    try:
        query = """
            SELECT t.*, COALESCE(p.name, pmp.name) AS project_name
            FROM tasks t
            LEFT JOIN projects p ON p.id = t.project_id
            LEFT JOIN pm_projects pmp ON pmp.id = t.pm_project_id
            WHERE t.deleted_at IS NULL
        """
        params: list[Any] = []

        if status:
            placeholders = ",".join(["?"] * len(status))
            query += f" AND t.status_v1 IN ({placeholders})"
            params.extend(status)
        if priority:
            placeholders = ",".join(["?"] * len(priority))
            query += f" AND t.priority_label IN ({placeholders})"
            params.extend(priority)
        if owner:
            placeholders = ",".join(["?"] * len(owner))
            query += f" AND t.owner_label IN ({placeholders})"
            params.extend(owner)
        if agent:
            placeholders = ",".join(["?"] * len(agent))
            query += f" AND t.agent_key IN ({placeholders})"
            params.extend(agent)
        if project_id is not None:
            query += " AND t.project_id=?"
            params.append(project_id)
        if q:
            query += " AND (t.title LIKE ? OR t.objective LIKE ? OR t.description LIKE ?)"
            like_q = f"%{q.strip()}%"
            params.extend([like_q, like_q, like_q])

        query += """
            ORDER BY CASE t.status_v1
                WHEN 'planned' THEN 1
                WHEN 'in_progress' THEN 2
                WHEN 'paused' THEN 3
                WHEN 'blocked' THEN 4
                WHEN 'needs_owner_input' THEN 5
                WHEN 'done' THEN 6
                WHEN 'cancelled' THEN 7
                ELSE 99
            END,
            t.sort_order ASC,
            t.created_at DESC
        """
        rows = conn.execute(query, params).fetchall()
        tasks = [_serialize_task(conn, row, include_activity=False) for row in rows]

        if overdue is not None:
            tasks = [t for t in tasks if t["is_overdue"] == overdue]

        return {"items": tasks, "total": len(tasks), "timestamp": datetime.now().isoformat()}
    finally:
        conn.close()


@app.get("/api/tasks/metrics")
async def api_task_metrics():
    conn = _get_conn()
    try:
        rows = conn.execute(
            """
            SELECT id, status_v1, priority_label, due_at, created_at, completed_at
            FROM tasks
            WHERE deleted_at IS NULL
            """
        ).fetchall()
        now = datetime.now(timezone.utc)
        open_count = 0
        overdue_count = 0
        needs_owner_input_count = 0
        blocked_count = 0
        p0_p1_count = 0
        cycle_hours: list[float] = []

        for row in rows:
            status = row["status_v1"] or "planned"
            if status not in {"done", "cancelled"}:
                open_count += 1
            if status == "needs_owner_input":
                needs_owner_input_count += 1
            if status == "blocked":
                blocked_count += 1
            if row["priority_label"] in {"P0", "P1"}:
                p0_p1_count += 1

            due_at = row["due_at"]
            if due_at and status not in {"done", "cancelled"}:
                try:
                    if datetime.fromisoformat(due_at.replace("Z", "+00:00")) < now:
                        overdue_count += 1
                except Exception:
                    pass

            if row["completed_at"] and row["created_at"]:
                try:
                    created = datetime.fromisoformat(str(row["created_at"]).replace("Z", "+00:00"))
                    completed = datetime.fromisoformat(str(row["completed_at"]).replace("Z", "+00:00"))
                    cycle_hours.append((completed - created).total_seconds() / 3600)
                except Exception:
                    pass

        cycle_avg = round(sum(cycle_hours) / len(cycle_hours), 2) if cycle_hours else None
        return {
            "open_tasks": open_count,
            "overdue": overdue_count,
            "needs_owner_input": needs_owner_input_count,
            "blocked": blocked_count,
            "p0_p1": p0_p1_count,
            "cycle_time_hours": cycle_avg,
            "timestamp": datetime.now().isoformat(),
        }
    finally:
        conn.close()


@app.get("/api/tasks/{task_id}")
async def api_task_detail(task_id: int):
    conn = _get_conn()
    try:
        row = _fetch_task_row(conn, task_id)
        if not row:
            raise HTTPException(status_code=404, detail="Task not found")
        return _serialize_task(conn, row, include_activity=True)
    finally:
        conn.close()


@app.post("/api/tasks")
async def api_task_create(payload: TaskCreateRequest):
    status = _validate_status(payload.status)
    priority = _validate_priority(payload.priority)
    agent = _validate_agent(payload.agent)
    conn = _get_conn()
    try:
        next_sort = conn.execute("SELECT COALESCE(MAX(sort_order), 0) + 1 FROM tasks").fetchone()[0]
        cur = conn.execute(
            """
            INSERT INTO tasks (
                project_id, title, description, task_type, status, priority,
                status_v1, priority_label, owner_label, agent_key,
                objective, success_criteria, due_at, risk_flags_json,
                created_at, updated_at, sort_order
            ) VALUES (?, ?, ?, 'agent', ?, 5, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, ?)
            """,
            (
                payload.project_id,
                payload.title.strip(),
                payload.description,
                _legacy_status_from_v1(status),
                status,
                priority,
                payload.owner.strip() or "owner",
                agent,
                payload.objective or payload.description or payload.title,
                payload.success_criteria,
                payload.due_at,
                json.dumps(payload.risk_flags, ensure_ascii=False),
                next_sort,
            ),
        )
        task_id = cur.lastrowid

        for item in payload.checklist:
            conn.execute(
                """
                INSERT INTO task_owner_inputs (task_id, item_key, label, input_type, required, placeholder, value_text, file_path, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    item.item_key,
                    item.label,
                    item.input_type,
                    1 if item.required else 0,
                    item.placeholder,
                    item.value_text,
                    item.file_path,
                    item.status or ("submitted" if item.value_text or item.file_path else "pending"),
                ),
            )

        _append_activity(conn, task_id, "created", payload.owner, "Task created", {
            "status": status,
            "priority": priority,
            "agent": agent,
        })

        conn.commit()
        row = _fetch_task_row(conn, task_id)
        return _serialize_task(conn, row, include_activity=True)
    finally:
        conn.close()


@app.patch("/api/tasks/{task_id}")
async def api_task_patch(task_id: int, payload: TaskPatchRequest):
    conn = _get_conn()
    try:
        row = _fetch_task_row(conn, task_id)
        if not row:
            raise HTTPException(status_code=404, detail="Task not found")

        updates: list[str] = []
        values: list[Any] = []
        changes: dict[str, Any] = {}

        high_risk_reasons: list[str] = []

        target_status = row["status_v1"]

        if payload.status is not None:
            status = _validate_status(payload.status)
            if status in HIGH_RISK_TRANSITIONS and row["status_v1"] != status and not payload.confirmed:
                raise HTTPException(status_code=409, detail={
                    "code": "confirmation_required",
                    "message": f"Transition to {status} requires confirmation",
                })
            if status in HIGH_RISK_TRANSITIONS and row["status_v1"] != status:
                high_risk_reasons.append(f"status:{status}")
            updates.extend(["status_v1=?", "status=?"])
            values.extend([status, _legacy_status_from_v1(status)])
            if status == "in_progress" and row["status_v1"] != "in_progress":
                updates.append("started_at=COALESCE(started_at, CURRENT_TIMESTAMP)")
            if status == "done" and row["status_v1"] != "done":
                updates.append("completed_at=CURRENT_TIMESTAMP")
            if status in {"planned", "in_progress", "paused", "blocked", "needs_owner_input"} and row["status_v1"] != status:
                updates.append("completed_at=NULL")
            changes["status"] = status
            target_status = status

        if payload.before_task_id is not None:
            before_row = _fetch_task_row(conn, payload.before_task_id)
            if not before_row:
                raise HTTPException(status_code=404, detail="Target position task not found")
            if before_row["id"] == row["id"]:
                raise HTTPException(status_code=400, detail="Cannot reorder task before itself")
            before_sort = float(before_row["sort_order"] or 0)
            prev = conn.execute(
                """
                SELECT sort_order FROM tasks
                WHERE status_v1=? AND deleted_at IS NULL AND id NOT IN (?, ?)
                  AND sort_order < ?
                ORDER BY sort_order DESC
                LIMIT 1
                """,
                (target_status, row["id"], before_row["id"], before_sort),
            ).fetchone()
            prev_sort = float(prev["sort_order"]) if prev else before_sort - 2.0
            new_sort = (prev_sort + before_sort) / 2.0
            updates.append("sort_order=?")
            values.append(new_sort)
            changes["sort_order"] = new_sort
            changes["before_task_id"] = payload.before_task_id
        elif payload.status is not None:
            max_row = conn.execute(
                "SELECT COALESCE(MAX(sort_order), 0) AS max_sort FROM tasks WHERE status_v1=? AND deleted_at IS NULL AND id!=?",
                (target_status, task_id),
            ).fetchone()
            new_sort = float(max_row["max_sort"] or 0) + 1.0
            updates.append("sort_order=?")
            values.append(new_sort)
            changes["sort_order"] = new_sort

        if payload.priority is not None:
            priority = _validate_priority(payload.priority)
            if priority == "P0" and row["priority_label"] != "P0" and not payload.confirmed:
                raise HTTPException(status_code=409, detail={
                    "code": "confirmation_required",
                    "message": "Escalating priority to P0 requires confirmation",
                })
            if priority == "P0" and row["priority_label"] != "P0":
                high_risk_reasons.append("priority:P0")
            updates.append("priority_label=?")
            values.append(priority)
            changes["priority"] = priority

        if payload.agent is not None:
            agent = _validate_agent(payload.agent)
            if row["agent_key"] != agent and not payload.confirmed:
                raise HTTPException(status_code=409, detail={
                    "code": "confirmation_required",
                    "message": "Reassigning task agent requires confirmation",
                })
            if row["agent_key"] != agent:
                high_risk_reasons.append("agent:reassign")
            updates.append("agent_key=?")
            values.append(agent)
            changes["agent"] = agent

        if payload.due_at is not None:
            updates.append("due_at=?")
            values.append(payload.due_at)
            changes["due_at"] = payload.due_at

        if payload.owner is not None:
            updates.append("owner_label=?")
            values.append(payload.owner)
            changes["owner"] = payload.owner

        if payload.title is not None:
            updates.append("title=?")
            values.append(payload.title)
            changes["title"] = payload.title

        if payload.objective is not None:
            updates.append("objective=?")
            values.append(payload.objective)
            changes["objective"] = payload.objective

        if payload.success_criteria is not None:
            updates.append("success_criteria=?")
            values.append(payload.success_criteria)
            changes["success_criteria"] = payload.success_criteria

        if not updates:
            raise HTTPException(status_code=400, detail="No updates provided")

        updates.append("updated_at=CURRENT_TIMESTAMP")
        sql = f"UPDATE tasks SET {', '.join(updates)} WHERE id=?"
        values.append(task_id)
        conn.execute(sql, values)
        _append_activity(conn, task_id, "updated", "owner", "Task updated", changes)
        if payload.confirmed and high_risk_reasons:
            _append_activity(
                conn,
                task_id,
                "high_risk_confirmation",
                "owner",
                "High-risk transition confirmed",
                {
                    "reasons": high_risk_reasons,
                    "changes": changes,
                },
            )
        conn.commit()

        updated = _fetch_task_row(conn, task_id)
        return _serialize_task(conn, updated, include_activity=True)
    finally:
        conn.close()


@app.post("/api/tasks/{task_id}/notes")
async def api_task_add_note(task_id: int, payload: TaskNoteRequest):
    conn = _get_conn()
    try:
        row = _fetch_task_row(conn, task_id)
        if not row:
            raise HTTPException(status_code=404, detail="Task not found")
        _append_activity(conn, task_id, "note", payload.author, payload.note)
        conn.execute(
            "UPDATE tasks SET notes=COALESCE(notes,'') || ? || ?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            ("\n" if row["notes"] else "", payload.note, task_id),
        )
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


@app.post("/api/tasks/{task_id}/owner-input")
async def api_task_owner_input(task_id: int, payload: OwnerInputSubmissionRequest):
    conn = _get_conn()
    try:
        row = _fetch_task_row(conn, task_id)
        if not row:
            raise HTTPException(status_code=404, detail="Task not found")

        for item in payload.items:
            conn.execute(
                """
                INSERT INTO task_owner_inputs (task_id, item_key, label, input_type, required, placeholder, value_text, file_path, status, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(task_id, item_key) DO UPDATE SET
                    label=excluded.label,
                    input_type=excluded.input_type,
                    required=excluded.required,
                    placeholder=excluded.placeholder,
                    value_text=excluded.value_text,
                    file_path=excluded.file_path,
                    status=excluded.status,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (
                    task_id,
                    item.item_key,
                    item.label,
                    item.input_type,
                    1 if item.required else 0,
                    item.placeholder,
                    item.value_text,
                    item.file_path,
                    item.status or ("submitted" if item.value_text or item.file_path else "pending"),
                ),
            )

        conn.execute(
            """
            UPDATE tasks
            SET status_v1='needs_owner_input', status='pending', updated_at=CURRENT_TIMESTAMP
            WHERE id=?
            """,
            (task_id,),
        )
        _append_activity(conn, task_id, "owner_input", payload.author, "Owner input submitted", {
            "items": len(payload.items),
        })
        conn.commit()
        return {"ok": True, "items": len(payload.items)}
    finally:
        conn.close()


@app.post("/api/tasks/{task_id}/evaluate-input")
async def api_task_evaluate_input(task_id: int, payload: TaskInputEvaluationRequest):
    conn = _get_conn()
    try:
        row = _fetch_task_row(conn, task_id)
        if not row:
            raise HTTPException(status_code=404, detail="Task not found")
        checklist = _fetch_checklist(conn, task_id)
        missing = []
        for item in checklist:
            if item["required"] and not item.get("value_text") and not item.get("file_path"):
                missing.append(item["item_key"])

        passed = len(missing) == 0
        if passed:
            conn.execute(
                "UPDATE tasks SET status_v1='in_progress', status='in_progress', started_at=COALESCE(started_at, CURRENT_TIMESTAMP), updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (task_id,),
            )
            message = "Owner input accepted. Task resumed."
        else:
            conn.execute(
                "UPDATE tasks SET status_v1='needs_owner_input', status='pending', updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (task_id,),
            )
            message = "Input insufficient. Missing required checklist items."

        _append_activity(conn, task_id, "input_evaluation", payload.author, message, {
            "passed": passed,
            "missing": missing,
        })
        conn.commit()
        return {"passed": passed, "missing": missing, "message": message}
    finally:
        conn.close()


@app.post("/api/tasks/{task_id}/command")
async def api_task_command(task_id: int, payload: TaskCommandRequest):
    conn = _get_conn()
    try:
        row = _fetch_task_row(conn, task_id)
        if not row:
            raise HTTPException(status_code=404, detail="Task not found")

        _append_activity(conn, task_id, "command", payload.author, payload.command, {
            "status": "accepted",
            "agent": row["agent_key"] or "tobi",
        })
        conn.execute(
            "UPDATE tasks SET status_v1='in_progress', status='in_progress', started_at=COALESCE(started_at, CURRENT_TIMESTAMP), updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (task_id,),
        )
        conn.commit()
        return {
            "ok": True,
            "task_id": task_id,
            "ack": f"Command queued for {row['agent_key'] or 'tobi'}",
        }
    finally:
        conn.close()


@app.delete("/api/tasks/{task_id}")
async def api_task_delete(task_id: int):
    conn = _get_conn()
    try:
        row = _fetch_task_row(conn, task_id)
        if not row:
            raise HTTPException(status_code=404, detail="Task not found")
        conn.execute(
            """
            UPDATE tasks
            SET status_v1='cancelled', status='skipped', deleted_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP
            WHERE id=?
            """,
            (task_id,),
        )
        _append_activity(conn, task_id, "deleted", "owner", "Task deleted from active board")
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


@app.get("/api/tasks/audit/high-risk")
async def api_task_high_risk_audit(limit: int = Query(default=50, ge=1, le=200)):
    conn = _get_conn()
    try:
        rows = conn.execute(
            """
            SELECT a.id, a.task_id, a.activity_type, a.author, a.message, a.payload, a.created_at,
                   t.title AS task_title
            FROM task_activity a
            JOIN tasks t ON t.id = a.task_id
            WHERE a.activity_type='high_risk_confirmation'
               OR (a.activity_type='updated' AND (
                    instr(a.payload, '"status": "done"') > 0
                 OR instr(a.payload, '"status": "cancelled"') > 0
                 OR instr(a.payload, '"priority": "P0"') > 0
                 OR instr(a.payload, '"agent"') > 0
               ))
            ORDER BY a.created_at DESC, a.id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

        items = []
        for row in rows:
            items.append({
                "id": row["id"],
                "task_id": row["task_id"],
                "task_title": row["task_title"],
                "activity_type": row["activity_type"],
                "author": row["author"],
                "message": row["message"],
                "payload": _json_loads(row["payload"], {}),
                "created_at": row["created_at"],
            })
        return {"items": items, "count": len(items), "timestamp": datetime.now().isoformat()}
    finally:
        conn.close()


# ── Health diagnostics ──────────────────────────────────────────────────────────

import re

# Matches both main.py's "[ERROR]" format and the default "ERROR:logger:" library
# format, plus tracebacks. Word-boundaried so it won't fire on the word "error" mid-sentence.
_LEVEL_RE = re.compile(r"(\[(ERROR|CRITICAL|WARNING)\]|\b(ERROR|CRITICAL|WARNING):)")
_TRACE_RE = re.compile(r"Traceback \(most recent call last\)|^\s*\w+Error:|Exception")
# Redact secrets that may appear in log lines (Telegram bot tokens, key=… pairs).
_REDACT = [
    (re.compile(r"bot\d+:[A-Za-z0-9_\-]+"), "bot***REDACTED***"),
    (re.compile(r"(?i)(token|key|secret|password)=\S+"), r"\1=***"),
]


def _redact(text: str) -> str:
    for pat, repl in _REDACT:
        text = pat.sub(repl, text)
    return text


def _recent_errors(limit: int = 12, scan_lines: int = 3000) -> list[dict]:
    """Tail the live log and surface the most recent error/warning lines.

    Reads whichever of logs/tobi.log or logs/system.log has content (prefers the
    one written most recently). This is the most direct 'where's the problem' signal.
    Secrets (bot tokens, key=…) are redacted before returning.
    """
    candidates = [LOGS_DIR / "tobi.log", LOGS_DIR / "system.log"]
    log_file = None
    best_mtime = -1.0
    for p in candidates:
        try:
            if p.exists() and p.stat().st_size > 0 and p.stat().st_mtime > best_mtime:
                best_mtime, log_file = p.stat().st_mtime, p
        except OSError:
            continue
    if not log_file:
        return []

    try:
        with log_file.open("r", encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()[-scan_lines:]
    except OSError:
        return []

    hits: list[dict] = []
    for line in lines:
        m = _LEVEL_RE.search(line)
        is_trace = bool(_TRACE_RE.search(line))
        if not m and not is_trace:
            continue
        token = (m.group(2) or m.group(3)) if m else None
        level = "WARNING" if token == "WARNING" else "ERROR"
        hits.append({
            "level": level,
            "msg": _redact(line.rstrip())[:300],
            "source": log_file.name,
        })
    return hits[-limit:][::-1]  # newest first


def _last(conn: sqlite3.Connection, query: str) -> str | None:
    try:
        row = conn.execute(query).fetchone()
        return row[0] if row and row[0] else None
    except sqlite3.Error:
        return None


@app.get("/api/health")
async def api_health():
    """Diagnostics for Mission Control's Health page.

    Three clearly separated signal classes — never collapsed into one red/green:
      • up        — verifiable liveness (DB connects, API server responds). Red is meaningful.
      • configured— env key / integration present. A CONFIG check, NOT liveness. Never 'down'.
      • activity  — last time each subsystem wrote data. Absence ≠ failure; labelled 'last active'.
    """
    # ── up: liveness ──────────────────────────────────────────────
    up: dict = {}
    db_ok = False
    try:
        conn = _get_conn()
        n = conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
        db_ok = True
        up["database"] = {"ok": True, "detail": f"connected · {n} projects"}
    except Exception as e:  # noqa: BLE001
        conn = None
        up["database"] = {"ok": False, "detail": f"cannot open DB: {str(e)[:120]}"}

    api_ok = False
    try:
        import requests
        r = requests.get(f"http://localhost:{API_PORT}/health", timeout=2)
        api_ok = r.status_code == 200
        up["api_server"] = {"ok": api_ok, "detail": f"port {API_PORT} /health → {r.status_code}"}
    except Exception as e:  # noqa: BLE001
        up["api_server"] = {"ok": False, "detail": f"port {API_PORT} not responding ({str(e)[:80]})"}

    # ── configured: env presence (no network) ─────────────────────
    configured = {
        "telegram": bool(os.getenv("TELEGRAM_BOT_TOKEN")),
        "openrouter": bool(os.getenv("OPENROUTER_API_KEY")),
        "anthropic": bool(os.getenv("ANTHROPIC_API_KEY")),
        "openai": bool(os.getenv("OPENAI_API_KEY")),
        "tavily": bool(os.getenv("TAVILY_API_KEY")),
    }
    try:
        from core.integrations import check_all
        configured.update(check_all())  # notion, github, google, vercel, supabase
    except Exception:  # noqa: BLE001
        pass

    # ── activity: last-write timestamps (honest 'last active') ────
    activity: dict = {}
    data: dict = {}
    if conn is not None:
        activity = {
            "last_conversation": fmt_ago(_last(conn, "SELECT MAX(created_at) FROM conversations")),
            "last_task_completed": fmt_ago(_last(conn, "SELECT MAX(completed_at) FROM tasks WHERE completed_at IS NOT NULL")),
            "last_lesson": fmt_ago(_last(conn, "SELECT MAX(created_at) FROM lessons")),
            "last_strategy_ceo": fmt_ago(_last(conn, "SELECT MAX(created_at) FROM strategy")),
            "last_report": fmt_ago(_last(conn, "SELECT MAX(created_at) FROM reports")),
        }
        try:
            blocked = conn.execute(
                "SELECT COUNT(*) FROM tasks WHERE status IN ('blocked','skipped')"
            ).fetchone()[0]
        except sqlite3.Error:
            blocked = 0
        conn.close()

        try:
            dash = get_dashboard()
            data = {
                "active_projects": len(dash.get("active_projects", [])),
                "pending_human_tasks": dash.get("human_todos_count", 0),
                "blocked_tasks": blocked,
                "revenue_this_month": dash.get("revenue", {}).get("this_month", 0),
            }
        except Exception:  # noqa: BLE001
            data = {"blocked_tasks": blocked}

    recent_errors = _recent_errors()

    # ── overall health SCORE (0–100) — single source of truth ─────
    # Only real liveness + core capability + error volume move the bar.
    # Optional, unconfigured integrations do NOT reduce health (config ≠ failure).
    score = 100
    notes: list[str] = []

    if not db_ok:
        score -= 60
        notes.append("Database unreachable")
    if not api_ok:
        score -= 12
        notes.append("API server not responding")

    has_llm = configured.get("openrouter") or configured.get("anthropic") or configured.get("openai")
    if not has_llm:
        score -= 30
        notes.append("No LLM provider configured — Tobi can't think")
    if not configured.get("telegram"):
        score -= 15
        notes.append("Telegram not configured — Tobi can't talk")

    n_err = sum(1 for e in recent_errors if e["level"] == "ERROR")
    n_warn = sum(1 for e in recent_errors if e["level"] == "WARNING")
    if n_err:
        score -= min(20, n_err * 5)
        notes.append(f"{n_err} recent error{'s' if n_err != 1 else ''} in the log")
    if n_warn:
        score -= min(8, n_warn)
        notes.append(f"{n_warn} recent warning{'s' if n_warn != 1 else ''} in the log")

    blocked = data.get("blocked_tasks", 0)
    if blocked:
        score -= min(10, blocked * 2)
        notes.append(f"{blocked} blocked/skipped task{'s' if blocked != 1 else ''}")

    score = max(0, min(100, score))
    overall = "healthy" if score >= 85 else "degraded" if score >= 50 else "issue"

    return {
        "timestamp": datetime.now().isoformat(),
        "overall": overall,
        "score": score,
        "score_notes": notes,
        "up": up,
        "configured": configured,
        "activity": activity,
        "data": data,
        "recent_errors": recent_errors,
    }


def _timed_check(fn) -> dict:
    """Run a check fn() -> (ok, detail); capture latency + exceptions."""
    import time as _t
    t0 = _t.perf_counter()
    try:
        ok, detail = fn()
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "detail": str(e)[:160], "latency_ms": int((_t.perf_counter() - t0) * 1000)}
    return {"ok": bool(ok), "detail": str(detail)[:120], "latency_ms": int((_t.perf_counter() - t0) * 1000)}


@app.get("/api/health/deep")
async def api_health_deep():
    """On-demand LIVE check of EVERY external API Tobi uses (button-triggered, not on
    load): a real LLM round-trip + live network tests to Telegram, Tavily, and each
    integration. Each result carries latency; a summary gives reachable/total."""
    result: dict = {"timestamp": datetime.now().isoformat()}

    # 1) LLM round-trip (real call via the model router)
    def _llm():
        from core.model_router import llm_complete
        reply = llm_complete("Reply with exactly: OK", task_type="simple", max_tokens=10)
        return bool(reply and reply.strip()), ((reply or "").strip()[:60] or "empty reply")
    result["llm"] = _timed_check(_llm)
    result["llm"]["provider"] = os.getenv("PRIMARY_MODEL", "openrouter")

    integrations: dict = {}

    # 2) Telegram — getMe (free, fast)
    def _tg():
        tok = os.getenv("TELEGRAM_BOT_TOKEN")
        if not tok:
            return False, "not configured"
        import requests
        r = requests.get(f"https://api.telegram.org/bot{tok}/getMe", timeout=10)
        j = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        uname = (j.get("result") or {}).get("username")
        return bool(j.get("ok")), (f"@{uname}" if uname else f"HTTP {r.status_code}")
    integrations["telegram"] = _timed_check(_tg)

    # 3) Tavily — minimal live search (1 result) to confirm the key works
    def _tav():
        key = os.getenv("TAVILY_API_KEY")
        if not key:
            return False, "not configured"
        import requests
        r = requests.post("https://api.tavily.com/search",
                          json={"api_key": key, "query": "ping", "max_results": 1}, timeout=12)
        return r.ok, ("reachable" if r.ok else f"HTTP {r.status_code}")
    integrations["tavily"] = _timed_check(_tav)

    # 4) Integration providers (notion/github/google/vercel/supabase) — live test()
    try:
        from core.integrations import _integrations
        for name, cls in _integrations.items():
            inst = cls()
            if not inst.is_available():
                integrations[name] = {"ok": False, "detail": "not configured", "latency_ms": 0}
                continue

            def _it(inst=inst):
                ok = bool(inst.test())
                return ok, ("reachable" if ok else "configured but test failed")
            integrations[name] = _timed_check(_it)
    except Exception as e:  # noqa: BLE001
        integrations["error"] = {"ok": False, "detail": str(e)[:120], "latency_ms": 0}

    result["integrations"] = integrations

    checks = [result["llm"], *integrations.values()]
    result["summary"] = {"ok": sum(1 for c in checks if c.get("ok")), "total": len(checks)}
    return result


@app.on_event("startup")
async def startup():
    init_database()


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
    accent_color: str | None = None
    deadline: str | None = None
    kpi_mode: str | None = None
    kpi_id: str | None = None
    kpi_metric_name: str | None = None
    kpi_target_value: float | None = None
    kpi_current_value: float | None = None


class PMGoalCreateRequest(BaseModel):
    title: str
    metric_name: str | None = None
    target_value: float = 100
    current_value: float = 0
    due_date: str | None = None
    owner: str = "user"


class PMGoalPatchRequest(BaseModel):
    title: str | None = None
    metric_name: str | None = None
    target_value: float | None = None
    current_value: float | None = None
    due_date: str | None = None
    owner: str | None = None


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

@app.get("/api/pm/projects")
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
    sql += " ORDER BY updated_at DESC"
    rows = conn.execute(sql, params).fetchall()
    items = [_pm_serialize_project(conn, r) for r in rows]
    conn.close()
    return {"items": items, "count": len(items), "timestamp": datetime.now(timezone.utc).isoformat()}


@app.post("/api/pm/projects")
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


@app.get("/api/pm/projects/{project_id}")
async def pm_get_project(project_id: int):
    conn = _get_conn()
    row = conn.execute("SELECT * FROM pm_projects WHERE id=?", (project_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="project not found")
    result = _pm_serialize_project(conn, row)
    conn.close()
    return result


@app.patch("/api/pm/projects/{project_id}")
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


@app.delete("/api/pm/projects/{project_id}")
async def pm_delete_project(project_id: int):
    conn = _get_conn()
    if not conn.execute("SELECT 1 FROM pm_projects WHERE id=?", (project_id,)).fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="project not found")
    conn.execute("DELETE FROM pm_projects WHERE id=?", (project_id,))
    conn.commit()
    conn.close()
    return {"ok": True, "project_id": project_id}


# ── GOALS ─────────────────────────────────────────────────────────────────────

@app.get("/api/pm/projects/{project_id}/goals")
async def pm_list_goals(project_id: int):
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM pm_goals WHERE project_id=? ORDER BY created_at", (project_id,)
    ).fetchall()
    items = [_pm_serialize_goal(r) for r in rows]
    conn.close()
    return {"items": items, "count": len(items)}


@app.post("/api/pm/projects/{project_id}/goals")
async def pm_create_goal(project_id: int, payload: PMGoalCreateRequest):
    conn = _get_conn()
    if not conn.execute("SELECT 1 FROM pm_projects WHERE id=?", (project_id,)).fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="project not found")
    cur = conn.execute(
        """INSERT INTO pm_goals (project_id, title, metric_name, target_value, current_value, due_date, owner)
           VALUES (?,?,?,?,?,?,?)""",
        (project_id, payload.title, payload.metric_name, payload.target_value,
         payload.current_value, payload.due_date, payload.owner),
    )
    gid = cur.lastrowid
    _pm_recalc_progress(conn, project_id)
    _pm_log(conn, project_id, "user", "goal.created", f"Goal '{payload.title}' added")
    conn.commit()
    row = conn.execute("SELECT * FROM pm_goals WHERE id=?", (gid,)).fetchone()
    conn.close()
    return _pm_serialize_goal(row)


@app.patch("/api/pm/projects/{project_id}/goals/{goal_id}")
async def pm_patch_goal(project_id: int, goal_id: int, payload: PMGoalPatchRequest):
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM pm_goals WHERE id=? AND project_id=?", (goal_id, project_id)
    ).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="goal not found")
    fields, vals, diff = [], [], {}
    for col, v in [("title", payload.title), ("metric_name", payload.metric_name),
                   ("target_value", payload.target_value), ("current_value", payload.current_value),
                   ("due_date", payload.due_date), ("owner", payload.owner)]:
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


@app.delete("/api/pm/projects/{project_id}/goals/{goal_id}")
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

@app.get("/api/pm/projects/{project_id}/tasks")
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


@app.post("/api/pm/projects/{project_id}/tasks")
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

@app.patch("/api/pm/projects/{project_id}/tasks/{task_id}/subtasks")
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


@app.patch("/api/pm/projects/{project_id}/tasks/{task_id}")
async def pm_patch_task(project_id: int, task_id: int, payload: TaskPatchRequest):
    """Thin wrapper — delegates to the main task patch endpoint after verifying PM ownership."""
    conn = _get_conn()
    row = _fetch_task_row(conn, task_id)
    conn.close()
    if not row or row["pm_project_id"] != project_id:
        raise HTTPException(status_code=404, detail="task not found in project")
    # Reuse the full patch logic
    return await api_task_patch(task_id, payload)


@app.delete("/api/pm/projects/{project_id}/tasks/{task_id}")
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

@app.get("/api/pm/projects/{project_id}/missions")
async def pm_list_missions(project_id: int):
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM pm_missions WHERE project_id=? ORDER BY created_at DESC", (project_id,)
    ).fetchall()
    items = [dict(r) for r in rows]
    conn.close()
    return {"items": items, "count": len(items)}


@app.post("/api/pm/projects/{project_id}/missions")
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


@app.patch("/api/pm/projects/{project_id}/missions/{mission_id}")
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

@app.get("/api/pm/projects/{project_id}/activity")
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


@app.post("/api/pm/projects/{project_id}/activity")
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

@app.get("/api/pm/projects/{project_id}/files")
async def pm_list_files(project_id: int):
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM pm_files WHERE project_id=? ORDER BY created_at DESC", (project_id,)
    ).fetchall()
    items = [dict(r) for r in rows]
    conn.close()
    return {"items": items, "count": len(items)}


@app.post("/api/pm/projects/{project_id}/files")
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


@app.delete("/api/pm/projects/{project_id}/files/{file_id}")
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

@app.get("/api/pm/templates")
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


@app.post("/api/pm/templates")
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


@app.delete("/api/pm/templates/{template_id}")
async def pm_delete_template(template_id: int):
    conn = _get_conn()
    if not conn.execute("SELECT 1 FROM pm_templates WHERE id=?", (template_id,)).fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="template not found")
    conn.execute("DELETE FROM pm_templates WHERE id=?", (template_id,))
    conn.commit()
    conn.close()
    return {"ok": True, "template_id": template_id}


# ── PM STATS (Dashboard widget) ───────────────────────────────────────────────

@app.get("/api/pm/stats")
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


# ── Evolution / Tier progression system ─────────────────────────────────────

_TIER_DEFINITIONS: list[dict] = [
    {
        "id": 0, "roman": "0", "name": "GENESIS", "color_key": "gray",
        "tagline": "Tobi exists. It talks back. That's about it.",
        "pillars": {
            "understand": [
                {"id": "soul_md", "name": "Static persona file (SOUL.md)",
                 "description": "Hand-written file defining Tobi's personality and rules. Works, but static — you wrote it yourself.", "how_to_unlock": None, "effort": "done"},
                {"id": "conversation_history", "name": "Conversation history (last 50 msgs)",
                 "description": "50-message rolling window per chat persisted in SQLite. Tobi remembers the current conversation.", "how_to_unlock": None, "effort": "done"},
                {"id": "task_classifier", "name": "Regex task classifier",
                 "description": "Routes messages to SMALLTALK/CODING/RESEARCH/STATUS/EXECUTION via regex — no LLM call needed. Fast and deterministic.", "how_to_unlock": None, "effort": "done"},
                {"id": "lessons_store", "name": "Lessons store (self-reflection DB)",
                 "description": "After cycles, Tobi logs success/failure/insight/warning entries to SQLite. The beginning of institutional memory.", "how_to_unlock": None, "effort": "done"},
            ],
            "control": [
                {"id": "coding_agent", "name": "Sandboxed coding agent",
                 "description": "Claude tool-use loop with 4 tools: read_file, write_file, run_bash, list_files. Sandboxed to project dir with 30s timeout.", "how_to_unlock": None, "effort": "done"},
                {"id": "github_integration", "name": "GitHub integration",
                 "description": "API-key gated. Read repos, create issues, manage PRs via GitHub REST API.", "how_to_unlock": None, "effort": "done"},
                {"id": "notion_integration", "name": "Notion integration",
                 "description": "API-key gated. Read and write Notion pages and databases.", "how_to_unlock": None, "effort": "done"},
                {"id": "vercel_integration", "name": "Vercel integration",
                 "description": "API-key gated. Deploy projects and query deployment status.", "how_to_unlock": None, "effort": "done"},
                {"id": "supabase_integration", "name": "Supabase integration",
                 "description": "API-key gated. Run SQL queries against a Supabase database.", "how_to_unlock": None, "effort": "done"},
            ],
            "presence": [
                {"id": "telegram_bot", "name": "Telegram bot (24/7 reachable)",
                 "description": "Always-listening bot. Your main interface to Tobi — text commands, inline buttons, coding agent access.", "how_to_unlock": None, "effort": "done"},
                {"id": "cron_scheduler", "name": "Cron scheduler",
                 "description": "Scheduled jobs: daily 08:00 report, 6h execution cycle, weekly research, monthly CEO review.", "how_to_unlock": None, "effort": "done"},
                {"id": "proactive_reports", "name": "Proactive daily reports",
                 "description": "Tobi pushes status updates to Telegram without being asked — project summaries, revenue, human todos.", "how_to_unlock": None, "effort": "done"},
            ],
        },
    },
    {
        "id": 1, "roman": "I", "name": "AWAKENING", "color_key": "bronze",
        "tagline": "Tobi starts remembering who you are and acting on the real world.",
        "pillars": {
            "understand": [
                {"id": "user_profile_table", "name": "Structured auto-updating user profile",
                 "description": "A real DB table tracking preferences, active projects, habits, relationships — auto-updated from every interaction. No more hand-writing SOUL.md.",
                 "how_to_unlock": "Design user_profile schema. Add entity extraction to handle_chat() to write preferences/projects/people as you mention them.", "effort": "1 week"},
                {"id": "memory_first_retrieval", "name": "Memory-first retrieval in all tasks",
                 "description": "Every task starts by consulting your profile first. The Memory-First Rule in SOUL.md made real in code, not just a text directive.",
                 "how_to_unlock": "Wire profile_context() into build_system_prompt() and every task handler before the LLM call.", "effort": "1 week"},
                {"id": "entity_extraction", "name": "Entity extraction from conversations",
                 "description": "Auto-extract people, projects, preferences, and decisions from your chats and persist them to the user profile.",
                 "how_to_unlock": "Add a background async call after each message to extract entities via a lightweight LLM prompt and upsert to the profile table.", "effort": "1 week"},
            ],
            "control": [
                {"id": "full_filesystem", "name": "Full filesystem access (no sandbox)",
                 "description": "Remove PROJECT_DIR lock. Tobi reads/writes anywhere on the machine with risk-tiered confirmation for destructive actions.",
                 "how_to_unlock": "Replace PROJECT_DIR sandbox with a risk-tiered permission check. Reads are free; writes outside project prompt once; deletes always confirm.", "effort": "3 days"},
                {"id": "tiered_permissions", "name": "Tiered permission model",
                 "description": "SOUL.md already defines 3 tiers: low (auto-execute), medium (act+report), high (propose+wait). Replace _BLOCKED_CMDS denylist with this.",
                 "how_to_unlock": "Implement classify_risk(command) returning low/medium/high. Replace denylist check in _execute_tool() with risk-gated routing.", "effort": "1 week"},
                {"id": "google_oauth", "name": "Google OAuth integration",
                 "description": "GoogleIntegration.test() returns False with a 'Phase 2: implement OAuth' comment. Make it real: OAuth, Drive, Docs, Sheets.",
                 "how_to_unlock": "Implement Google OAuth in core/integrations.py using google-auth library. Requires GOOGLE_CLIENT_ID + GOOGLE_CLIENT_SECRET.", "effort": "1 week"},
            ],
            "presence": [
                {"id": "webhook_triggers", "name": "Webhook + event-driven triggers",
                 "description": "Move beyond cron. Add FastAPI webhook endpoints for Stripe events, GitHub, email — Tobi acts when something happens, not just at 8am.",
                 "how_to_unlock": "Add POST /webhooks/{source} endpoints. Map event types to Tobi actions. Wire to Telegram notification on receipt.", "effort": "1 week"},
                {"id": "gmail_integration", "name": "Gmail read + write",
                 "description": "Tobi reads your inbox, summarizes threads, and drafts replies. Gmail MCP is already available in this environment.",
                 "how_to_unlock": "Wire the Gmail MCP tools into Tobi's tool-use loop. Add daily inbox summary to the morning report.", "effort": "3 days"},
                {"id": "voice_messages", "name": "Telegram voice messages (Whisper)",
                 "description": "Send a voice note to Tobi. It transcribes via Whisper and responds. Whisper is free and runs locally on CPU.",
                 "how_to_unlock": "Add voice message handler to telegram_bot.py. Download .ogg, convert to wav, run whisper.transcribe(), feed to handle_chat().", "effort": "3 days"},
            ],
        },
    },
    {
        "id": 2, "roman": "II", "name": "AGENT", "color_key": "gold",
        "tagline": "Tobi does real things on the internet. Not plans — actions.",
        "pillars": {
            "understand": [
                {"id": "semantic_memory", "name": "Semantic memory search",
                 "description": "Vector embeddings over all past conversations and lessons. 'What did I decide about X last month?' becomes a real query.",
                 "how_to_unlock": "Integrate SQLite-vec or ChromaDB. Embed messages on save. Add retrieve_similar(query) to the context pipeline.", "effort": "1 week"},
                {"id": "relationship_tracking", "name": "Relationship tracking (contacts DB)",
                 "description": "Tobi knows the people in your life: name, role, last contact, context. Never asks 'who is X?' again.",
                 "how_to_unlock": "Add a people table. Extract person mentions in entity extraction. Link to conversation context.", "effort": "1 week"},
                {"id": "profile_soul_sync", "name": "Profile auto-syncs to SOUL.md",
                 "description": "Tobi maintains SOUL.md itself based on what it learns about you — preferences, priorities, working style. Not hand-authored.",
                 "how_to_unlock": "Add weekly job that reads user profile and rewrites SOUL.md relevant sections using an LLM.", "effort": "1 week"},
            ],
            "control": [
                {"id": "browser_automation", "name": "Browser automation (Playwright)",
                 "description": "The single largest capability unlock. Tobi navigates websites, fills forms, publishes content, scrapes data. Any website is a tool.",
                 "how_to_unlock": "pip install playwright. Add browser_navigate, browser_click, browser_screenshot, browser_fill tools to the coding agent.", "effort": "1 week"},
                {"id": "web_publishing", "name": "Web content publishing",
                 "description": "Tobi publishes an article to Medium, Substack, or a blog — not just writes the draft, but actually posts it.",
                 "how_to_unlock": "Build platform-specific publishing modules using Playwright + platform APIs. Medium and Substack have unofficial APIs.", "effort": "1 week"},
                {"id": "shell_full_access", "name": "Controlled full-machine shell",
                 "description": "Run any terminal command on the full machine (not just project dir), with risk-gating and timeout.",
                 "how_to_unlock": "Build on the tiered permission model (Tier 1). run_bash() gets full machine CWD and no artificial path restriction.", "effort": "3 days"},
            ],
            "presence": [
                {"id": "calendar_integration", "name": "Google Calendar integration",
                 "description": "Tobi knows your schedule. Adds events, checks availability, preps briefings before meetings.",
                 "how_to_unlock": "Use Google OAuth (Tier 1) + Google Calendar API. Add calendar context to morning briefings.", "effort": "1 week"},
                {"id": "market_monitoring", "name": "Proactive news + market monitoring",
                 "description": "Tobi watches crypto prices, competitor sites, RSS feeds, and reaches out when something relevant happens.",
                 "how_to_unlock": "Add background polling tasks (crypto APIs, RSS, Tavily). Diff against previous state. Telegram alert on significant change.", "effort": "1 week"},
                {"id": "multi_channel", "name": "Multi-channel (Telegram + email)",
                 "description": "Tobi reaches you via email as well as Telegram, routing urgency-appropriate messages to the right channel.",
                 "how_to_unlock": "Add send_email() via Gmail. Add channel preference to SOUL.md: urgent → Telegram, daily → email.", "effort": "3 days"},
            ],
        },
    },
    {
        "id": 3, "roman": "III", "name": "OPERATOR", "color_key": "green",
        "tagline": "Tobi makes money. Not plans about money — actual money.",
        "pillars": {
            "understand": [
                {"id": "episodic_memory", "name": "Long-term episodic memory",
                 "description": "Months of history, semantically searchable. You never re-explain your situation to Tobi.",
                 "how_to_unlock": "Scale up semantic memory (Tier 2) to full history. Add episodic indexing with time decay. Integrate into every task context.", "effort": "1 month"},
                {"id": "habit_recognition", "name": "Habit and pattern recognition",
                 "description": "Tobi notices when you work best, how you like information formatted, what kinds of tasks you delegate.",
                 "how_to_unlock": "Track interaction timestamps, message formats, task acceptance patterns. Weekly analysis job updates habit profile.", "effort": "1 month"},
                {"id": "cross_session_recall", "name": "Zero re-explanation needed",
                 "description": "Anything you've told Tobi is recalled and applied. You mention a person once — Tobi knows them forever.",
                 "how_to_unlock": "Combination of entity extraction (T1) + semantic memory (T2) + episodic memory, fully wired into every message context.", "effort": "1 week"},
            ],
            "control": [
                {"id": "revenue_pipeline", "name": "End-to-end revenue pipeline",
                 "description": "At least one working pipeline from idea to sale: create a product, publish it, and track real revenue — fully automated.",
                 "how_to_unlock": "Pick one revenue channel (e.g. Gumroad). Wire create → upload → publish → track using their API + Playwright for gaps.", "effort": "1 month"},
                {"id": "stripe_gumroad_webhooks", "name": "Stripe + Gumroad live webhooks",
                 "description": "Revenue events hit the DB in real-time. Every sale triggers instant Telegram notification with running totals.",
                 "how_to_unlock": "Add POST /webhooks/stripe and /webhooks/gumroad. Parse sale events, write to revenue table, Telegram alert.", "effort": "1 week"},
                {"id": "social_automation", "name": "Automated social media publishing",
                 "description": "Tobi posts to X/Twitter, LinkedIn, Reddit on your behalf. Content created, scheduled, published autonomously.",
                 "how_to_unlock": "Twitter API v2, LinkedIn unofficial API or Playwright, Reddit API. Add publish_social(platform, content) to tool set.", "effort": "1 month"},
            ],
            "presence": [
                {"id": "proactive_initiative", "name": "Proactive initiative (notices + acts)",
                 "description": "Tobi reaches out when it notices something worth your attention — not cron-triggered, genuinely event-driven with judgment.",
                 "how_to_unlock": "Add observation loop monitoring: revenue trends, project stalls, opportunities. Tobi messages you when a threshold is crossed.", "effort": "1 month"},
                {"id": "revenue_alerts", "name": "Real-time revenue alerts",
                 "description": "Every sale triggers instant Telegram notification. Running monthly total. Revenue milestones celebrated.",
                 "how_to_unlock": "Follows from stripe_gumroad_webhooks + Telegram push. Add milestone detection ($1 first sale, $100, $500, $1000).", "effort": "1 week"},
                {"id": "smart_briefings", "name": "Smart context-aware daily briefings",
                 "description": "Morning briefing synthesizes revenue, project status, calendar, news. Context-aware narrative, not a template.",
                 "how_to_unlock": "Upgrade job_daily_report() to pull all sources + use LLM to synthesize a coherent narrative instead of a template.", "effort": "1 week"},
            ],
        },
    },
    {
        "id": 4, "roman": "IV", "name": "EXECUTIVE", "color_key": "neon_blue",
        "tagline": "Tobi runs parallel agents and starts controlling your desktop.",
        "pillars": {
            "understand": [
                {"id": "strategy_self_update", "name": "Self-updating strategy from outcomes",
                 "description": "Tobi reviews its own performance results and updates its operating strategy without the monthly CEO review prompt.",
                 "how_to_unlock": "Add outcome-tracking to every task. Weekly strategy diff: compare planned vs actual. LLM synthesizes updated SOUL.md strategy section.", "effort": "1 month"},
                {"id": "cross_project_synthesis", "name": "Cross-project pattern synthesis",
                 "description": "'Your last 3 content projects failed at week 2 due to distribution.' Tobi sees the meta-level patterns you miss.",
                 "how_to_unlock": "Add cross_project_analysis() job. Compare project histories. Extract recurring patterns. Surface in weekly briefing.", "effort": "1 month"},
                {"id": "auto_learns_feedback", "name": "Auto-learns from every outcome",
                 "description": "Task done → lesson auto-generated. Revenue experiment failed → strategy auto-updated. No manual reflection prompts needed.",
                 "how_to_unlock": "Add outcome hooks to project_executor.py: on task_done call generate_lesson(). On revenue_event call update_strategy().", "effort": "1 month"},
            ],
            "control": [
                {"id": "desktop_automation", "name": "Desktop GUI automation (vision + click)",
                 "description": "Screenshot → Claude vision → PyAutoGUI. Tobi sees your screen and clicks, types, automates any desktop app.",
                 "how_to_unlock": "pip install pyautogui mss. Add take_screenshot, find_on_screen, click_at, type_text tools. Claude vision interprets screenshots.", "effort": "1 month"},
                {"id": "multi_agent_parallel", "name": "Multi-agent parallelism (3 concurrent)",
                 "description": "Complex tasks spawn 3 sub-agents working in parallel. Research 5 niches = 3x faster.",
                 "how_to_unlock": "Implement async task queue with worker pool. Add delegate_to_agent(task, context) tool. Wire into research_engine and project_executor.", "effort": "1 month"},
                {"id": "local_pc_deployment", "name": "Local PC deployment",
                 "description": "Tobi runs on your actual machine — not a Codespace. Startup daemon, system tray, true desktop access.",
                 "how_to_unlock": "Write local launcher. Handle autostart (launchd on Mac, systemd on Linux). Move DB to user home dir.", "effort": "1 month"},
            ],
            "presence": [
                {"id": "wake_word", "name": "Wake word interface ('Hey Tobi')",
                 "description": "Wake word detection + Whisper STT + TTS. Hands-free. Talk to Tobi while working. Requires local PC deployment.",
                 "how_to_unlock": "pvporcupine for wake word. Whisper for STT. Coqui TTS. Requires local_pc_deployment (also Tier 4).", "effort": "1 month"},
                {"id": "system_tray", "name": "System tray + desktop notifications",
                 "description": "Tobi lives in your taskbar. Status indicator, quick-access menu, native desktop notifications.",
                 "how_to_unlock": "pystray for system tray. plyer for OS notifications. Requires local_pc_deployment.", "effort": "1 month"},
                {"id": "voice_output", "name": "Voice output (TTS responses)",
                 "description": "Tobi speaks back. Coqui TTS is free and local. ElevenLabs for higher quality. Toggle on/off.",
                 "how_to_unlock": "pip install TTS (Coqui). Add speak(text). Toggle via /voice command or system tray.", "effort": "1 week"},
            ],
        },
    },
    {
        "id": 5, "roman": "V", "name": "SENTINEL", "color_key": "gold_white",
        "tagline": "Tobi watches everything and acts before you ask.",
        "pillars": {
            "understand": [
                {"id": "predictive_assistance", "name": "Predictive assistance",
                 "description": "Tobi anticipates what you need before you ask. Pre-loads context before meetings, queues research before calls.",
                 "how_to_unlock": "Build prediction model from calendar + past behavior. Pre-fetch relevant context 30min before scheduled events.", "effort": "1 month"},
                {"id": "behavioral_modeling", "name": "Deep behavioral pattern modeling",
                 "description": "Comprehensive model of work patterns, decision history, risk appetite, communication style, cognitive preferences.",
                 "how_to_unlock": "Aggregate 3+ months interaction data. Statistical profile. Feed into all LLM context as 'owner behavioral model'.", "effort": "1 month"},
                {"id": "autonomous_research", "name": "Autonomous proactive research",
                 "description": "Tobi researches topics relevant to your active projects without being asked. Surfaces insights weekly.",
                 "how_to_unlock": "Add research_daemon() running nightly. For each active project, run targeted Tavily research. Weekly summary to Telegram.", "effort": "1 month"},
            ],
            "control": [
                {"id": "full_app_control", "name": "Full desktop application control",
                 "description": "Tobi operates any desktop app: IDE, browser, Slack, email client, spreadsheets — via vision + automation.",
                 "how_to_unlock": "Extend desktop automation (Tier 4) with app-specific action libraries. Vision-based UI parsing for apps without accessibility APIs.", "effort": "1 month"},
                {"id": "process_management", "name": "Process and system management",
                 "description": "Start/stop processes, monitor system health, manage dev environment, restart services.",
                 "how_to_unlock": "Add psutil tools: list_processes, kill_process, get_system_stats, restart_service. Expose via tool-use with risk-gating.", "effort": "1 month"},
                {"id": "autonomous_deploy", "name": "Autonomous code deployment pipeline",
                 "description": "Low-risk changes: Tobi codes → tests → deploys without human involvement. Gate only on high-risk or strategic changes.",
                 "how_to_unlock": "Wire coding agent to: write code, run tests, interpret results, deploy if passing and risk_low.", "effort": "1 month"},
            ],
            "presence": [
                {"id": "background_monitoring", "name": "Background monitoring of all systems",
                 "description": "Tobi watches servers, revenue, codebase, inbox 24/7 — not just at scheduled intervals.",
                 "how_to_unlock": "Replace cron scheduler with event-driven daemon. Continuous polling with smart intervals. State diffing for change detection.", "effort": "1 month"},
                {"id": "anomaly_detection", "name": "Anomaly detection + intelligent alerting",
                 "description": "Server down? Revenue drop? Unusual error spike? Tobi tells you before it becomes a crisis.",
                 "how_to_unlock": "Baseline + threshold tracking for key metrics. Statistical anomaly detection. Telegram alert with context + suggested action.", "effort": "1 month"},
                {"id": "context_aware_interrupts", "name": "Context-aware interruption logic",
                 "description": "Tobi knows when you're in deep work and only interrupts for genuinely urgent things. Smart notification scheduling.",
                 "how_to_unlock": "Add do_not_disturb mode. Track active hours from interaction patterns. Batch non-urgent alerts to check-in times.", "effort": "1 month"},
            ],
        },
    },
    {
        "id": 6, "roman": "VI", "name": "ARCHITECT", "color_key": "aurora",
        "tagline": "Tobi builds its own new capabilities and runs your life.",
        "pillars": {
            "understand": [
                {"id": "strategic_advisor", "name": "Strategic advisor (not just executor)",
                 "description": "Tobi challenges your assumptions, proposes alternatives, and acts as a genuine thought partner — not just a task runner.",
                 "how_to_unlock": "Add devil's advocate mode to planning. Tobi generates counter-proposals for major decisions. Weekly strategy review initiated by Tobi.", "effort": "1 month"},
                {"id": "full_history_synthesis", "name": "Full history synthesis",
                 "description": "Tobi synthesizes insights across all past interactions, projects, and decisions into a coherent strategic view.",
                 "how_to_unlock": "Monthly synthesis job: read all lessons + projects + outcomes. LLM generates strategic narrative. Store as strategic_context in profile.", "effort": "1 month"},
            ],
            "control": [
                {"id": "self_integration", "name": "Writes and deploys its own integrations",
                 "description": "Tobi identifies a capability gap, writes the integration code, tests it, adds it to its own tool set without human involvement.",
                 "how_to_unlock": "Extend coding agent to target its own codebase. Add self_improve() proposing new tools. Gate first deployment on owner approval.", "effort": "1 month"},
                {"id": "ten_project_portfolio", "name": "10+ active project portfolio management",
                 "description": "Managing 10+ simultaneous projects with autonomous execution, cross-project resource allocation, portfolio-level optimization.",
                 "how_to_unlock": "Portfolio-level scheduler balancing agent time across projects based on ROI and strategic priority.", "effort": "1 month"},
                {"id": "full_dev_loop", "name": "Owns the full development loop",
                 "description": "Feature request → design → code → test → deploy. End-to-end with human review gates at design and deploy only.",
                 "how_to_unlock": "Chain: design_proposal(task) → owner_approve → code_it() → run_tests() → deploy_if_passing(). Two approval gates, rest automated.", "effort": "1 month"},
            ],
            "presence": [
                {"id": "multi_device", "name": "Multi-device synchronized presence",
                 "description": "Tobi on your phone, laptop, and desktop — synchronized state, consistent experience, context-aware channel selection.",
                 "how_to_unlock": "Cloud-sync conversation state and user profile. Mobile PWA. WebSocket for real-time sync across devices.", "effort": "1 month"},
                {"id": "autonomous_delegation", "name": "Autonomous sub-agent delegation",
                 "description": "Tobi spawns specialized sub-agents without being prompted — research, coder, CEO agents all working in parallel on your behalf.",
                 "how_to_unlock": "Extend multi-agent parallelism (Tier 4). Tobi autonomously decides when to delegate, budget-gated by token limits.", "effort": "1 month"},
                {"id": "self_improving_skills", "name": "Self-improving Hermes skill system",
                 "description": "Tobi writes and improves its own Hermes skill files based on performance. Every success and failure feeds back into operating playbooks.",
                 "how_to_unlock": "Add skill_update(skill_id, improvement). Weekly review of skill performance metrics triggers rewrites.", "effort": "1 month"},
            ],
        },
    },
    {
        "id": 7, "roman": "VII", "name": "SOVEREIGN", "color_key": "sovereign",
        "tagline": "Full Jarvis. The mission complete. Tony Stark would be proud.",
        "pillars": {
            "understand": [
                {"id": "complete_mind_model", "name": "Complete mind-model of owner",
                 "description": "Tobi knows your context, history, preferences, goals, relationships, and decision patterns without being told anything.",
                 "how_to_unlock": "The culmination of all Understand Me pillars. Requires years of interaction data + sophisticated inference. Not a feature — an emergent property.", "effort": "???"},
                {"id": "zero_repeat_yourself", "name": "Never need to repeat yourself",
                 "description": "If you've said it to Tobi once, it remembers and applies it forever. Zero re-explanation needed.",
                 "how_to_unlock": "Entity extraction (T1) + semantic memory (T2) + episodic memory (T3), all fully mature and combined.", "effort": "???"},
            ],
            "control": [
                {"id": "unrestricted_control", "name": "Unrestricted PC control with judgment",
                 "description": "If a human can do it on the PC, Tobi can do it. Intelligent risk assessment replaces hard limits.",
                 "how_to_unlock": "Culmination of all PC Control pillars + a sophisticated risk model trained on your specific risk preferences.", "effort": "???"},
                {"id": "real_money_machine", "name": "Self-sustaining revenue engine",
                 "description": "Tobi runs the full MMO portfolio autonomously — research, execute, optimize, reinvest. Revenue without your involvement.",
                 "how_to_unlock": "All revenue pipeline capabilities (T3) + autonomous decision-making (T4+) + portfolio management (T6) combined.", "effort": "???"},
                {"id": "any_digital_task", "name": "Execute any digital task",
                 "description": "Give Tobi any task a PC user could accomplish. It figures out the steps, delegates, and completes it.",
                 "how_to_unlock": "Full tool surface + multi-agent orchestration + reliable task completion. Emergent from all PC Control capabilities.", "effort": "???"},
            ],
            "presence": [
                {"id": "true_jarvis", "name": "True Jarvis presence",
                 "description": "Voice-ready, cross-device, always-on, proactively helpful, context-aware 24/7. The Tony Stark experience, realized.",
                 "how_to_unlock": "The culmination of all Always-On Presence pillars. Voice + multi-device + proactive + always-on combined.", "effort": "???"},
                {"id": "self_improvement_loop", "name": "Autonomous self-improvement loop",
                 "description": "Tobi identifies its own capability gaps, builds solutions, tests them, integrates them. Compounding capability growth without direction.",
                 "how_to_unlock": "Combines self-integration (T6) + performance monitoring + autonomous deployment. Tobi improves itself on a weekly cycle.", "effort": "???"},
            ],
        },
    },
]


def _detect_abilities(conn: sqlite3.Connection) -> dict[str, bool]:
    repo_root = Path(__file__).parent.parent

    def env(key: str) -> bool:
        return bool(os.getenv(key))

    def file_ok(rel: str) -> bool:
        p = repo_root / rel
        return p.exists() and p.stat().st_size > 50

    def db_has_rows(table: str, where: str = "") -> bool:
        try:
            q = f"SELECT 1 FROM {table}" + (f" WHERE {where}" if where else "") + " LIMIT 1"
            return conn.execute(q).fetchone() is not None
        except Exception:
            return False

    has_llm = env("ANTHROPIC_API_KEY") or env("OPENROUTER_API_KEY")
    has_bot = env("TELEGRAM_BOT_TOKEN")

    return {
        # Tier 0
        "soul_md": file_ok("SOUL.md"),
        "conversation_history": db_has_rows("conversations"),
        "task_classifier": True,
        "lessons_store": db_has_rows("lessons"),
        "coding_agent": env("ANTHROPIC_API_KEY"),
        "github_integration": env("GITHUB_TOKEN"),
        "notion_integration": env("NOTION_API_KEY"),
        "vercel_integration": env("VERCEL_TOKEN"),
        "supabase_integration": env("SUPABASE_URL"),
        "telegram_bot": has_bot,
        "cron_scheduler": has_bot and has_llm,
        "proactive_reports": has_bot and has_llm,
        # All Tier 1+ abilities default to False (not yet built)
    }


def _load_evo_snapshot(conn: sqlite3.Connection) -> dict[str, str]:
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS evolution_snapshots (
                ability_id TEXT PRIMARY KEY,
                status TEXT NOT NULL DEFAULT 'inactive',
                detected_at TEXT,
                first_activated_at TEXT
            )
        """)
        conn.commit()
        rows = conn.execute("SELECT ability_id, status FROM evolution_snapshots").fetchall()
        return {r[0]: r[1] for r in rows}
    except Exception:
        return {}


def _save_evo_snapshot(conn: sqlite3.Connection, statuses: dict[str, bool]) -> None:
    now = datetime.now(timezone.utc).isoformat()
    for ability_id, is_active in statuses.items():
        status = "active" if is_active else "inactive"
        conn.execute("""
            INSERT INTO evolution_snapshots (ability_id, status, detected_at, first_activated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(ability_id) DO UPDATE SET
                status = excluded.status,
                detected_at = excluded.detected_at,
                first_activated_at = CASE
                    WHEN evolution_snapshots.first_activated_at IS NULL AND excluded.status = 'active'
                        THEN excluded.detected_at
                    ELSE evolution_snapshots.first_activated_at
                END
        """, (ability_id, status, now, now))
    conn.commit()


def _build_evo_response(statuses: dict[str, bool], prev: dict[str, str]):
    just_unlocked: list[int] = []
    tiers_out = []

    for tier in _TIER_DEFINITIONS:
        all_ids: list[str] = []
        active_count = 0
        pillars_out: dict = {}

        for pillar_key, abilities in tier["pillars"].items():
            out = []
            for ab in abilities:
                ab_id = ab["id"]
                is_active = statuses.get(ab_id, False)
                was_active = prev.get(ab_id) == "active"
                all_ids.append(ab_id)
                if is_active:
                    active_count += 1
                out.append({**ab, "status": "active" if is_active else "inactive",
                             "just_activated": is_active and not was_active})
            pillars_out[pillar_key] = out

        total = len(all_ids)
        complete = active_count == total and total > 0
        was_complete = all(prev.get(aid) == "active" for aid in all_ids)
        if complete and not was_complete:
            just_unlocked.append(tier["id"])

        tiers_out.append({
            **{k: v for k, v in tier.items() if k != "pillars"},
            "pillars": pillars_out,
            "active_count": active_count,
            "total_count": total,
            "progress_pct": round(active_count / total * 100) if total else 0,
            "complete": complete,
        })

    return tiers_out, just_unlocked


@app.get("/api/evolution")
async def get_evolution():
    conn = _get_conn()
    statuses = _detect_abilities(conn)
    prev = _load_evo_snapshot(conn)
    tiers, just_unlocked = _build_evo_response(statuses, prev)
    _save_evo_snapshot(conn, statuses)
    conn.close()

    total_abilities = sum(t["total_count"] for t in tiers)
    total_active = sum(t["active_count"] for t in tiers)
    jarvis_pct = round(total_active / total_abilities * 100) if total_abilities else 0

    current_tier = next((t["id"] for t in tiers if not t["complete"]), tiers[-1]["id"])
    current_tier_data = tiers[current_tier]
    missing = [
        ab for pillar in current_tier_data["pillars"].values()
        for ab in pillar if ab["status"] == "inactive"
    ]

    return {
        "tiers": tiers,
        "current_tier": current_tier,
        "jarvis_pct": jarvis_pct,
        "total_active": total_active,
        "total_abilities": total_abilities,
        "just_unlocked": just_unlocked,
        "missing_in_current_tier": missing,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ── Serve React static files (MUST be last — catch-all shadows all routes above) ──
if DIST_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(DIST_DIR / "assets")), name="assets")

    @app.get("/")
    async def root():
        return FileResponse(str(DIST_DIR / "index.html"))

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        file_path = DIST_DIR / full_path
        if file_path.is_file():
            return FileResponse(str(file_path))
        return FileResponse(str(DIST_DIR / "index.html"))

else:
    @app.get("/")
    async def root():
        return HTMLResponse("""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>Tobi Mission Control</title>
<style>
  body{background:#0d1117;color:#c9d1d9;font-family:monospace;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;}
  .box{text-align:center;border:1px solid #30363d;border-radius:8px;padding:40px;max-width:480px;}
  h1{color:#58a6ff;font-size:28px;letter-spacing:4px;margin-bottom:8px;}
  p{color:#8b949e;margin:8px 0;}
  code{background:#161b22;border:1px solid #30363d;padding:8px 16px;border-radius:4px;display:block;margin:16px 0;font-size:13px;}
</style>
</head>
<body>
<div class="box">
  <h1>⚡ TOBI</h1>
  <p>Mission Control UI needs to be built first.</p>
  <code>cd dashboard && npm install && npm run build</code>
  <p style="color:#8b949e;font-size:12px;">Then restart the dashboard server.</p>
</div>
</body>
</html>""")

    @app.get("/{full_path:path}")
    async def catch_all(full_path: str):
        return HTMLResponse("<html><body>Build the dashboard first: <code>cd dashboard && npm run build</code></body></html>")


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("DASHBOARD_PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")

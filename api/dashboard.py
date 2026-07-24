"""Mission Control Dashboard — Tobi Agent"""
from core.env_utils import safe_load_dotenv
safe_load_dotenv()

import os
import asyncio
import sqlite3
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Query, Request, Body, Header, UploadFile, File, Form
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from core.database import (
    init_database, get_dashboard, get_all_projects,
    get_all_lessons, get_pending_human_tasks_all, complete_task,
)
from core.release_manager import current_developer_version
from core import brain
from core import brain_v2_compat
from core import owner_flags
from core import graph_engine as graph
from core import vault
from core import integrations_registry as registry
from core import pm_resources as pmres
from core import mcp_security as mcpsec
try:  # MCP Hub (#5) — optional; app still runs if the mcp SDK isn't installed
    from core import mcp_server
    from core import mcp_client
    from core import a2a as mcp_a2a
    from core import mcp_tunnel
    MCP_AVAILABLE = True
except Exception:
    mcp_server = None
    mcp_client = None
    mcp_a2a = None
    mcp_tunnel = None
    MCP_AVAILABLE = False

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

ALLOWED_AGENTS = {"tobi", "research", "coder", "ceo", "owner"}
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
    description: str | None = None       # v2 task detail (plain text)
    start_at: str | None = None          # v2 optional start date
    reminder_at: str | None = None       # v2 optional reminder
    time_estimate: str | None = None     # v2 effort estimate
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


# Shared API primitives (refactor Slice 0 — see docs/REFACTORING_PLAN.md).
# DB_PATH / _get_conn / _json_loads / fmt_ago now live in api/deps.py so route
# groups extracted into api/routers/* can share them. Imported back into this
# module's namespace to preserve every existing reference (including external
# access such as core.conductor's `dashboard._get_conn`).
from api.deps import DB_PATH, _get_conn, _json_loads, _last, _vault_guard, fmt_ago

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

# Queue #18: isolated coding workflows live in a dedicated router so this module
# remains an HTTP composition root rather than owning self-development logic.
try:
    from api.developer import router as developer_router
    app.include_router(developer_router)
except Exception as _developer_err:
    import logging as _logging
    _logging.getLogger("tobi.dashboard").warning("Developer router unavailable: %s", _developer_err)

# Queue #20 T09: Brain Memory V2 API — additive under /api/brain/v2/*; the
# legacy /api/brain/* routes below are untouched.
try:
    from api.brain_v2 import router as brain_v2_router
    app.include_router(brain_v2_router)
except Exception as _brain_v2_err:
    import logging as _logging
    _logging.getLogger("tobi.dashboard").warning("Brain V2 router unavailable: %s", _brain_v2_err)

# Route groups peeled out of this module into api/routers/* (docs/REFACTORING_PLAN.md).
# Registered without a prefix — each router keeps its original full /api/... paths,
# so the openapi route set is byte-identical to the pre-refactor monolith.
from api.routers.health import router as health_router
app.include_router(health_router)
from api.routers.explore import router as explore_router
app.include_router(explore_router)
from api.routers.news_v2 import router as news_v2_router  # #23 News V2 (flag-gated 503 until enabled)
from api.routers.news_v2 import config_router as news_v2_config_router
app.include_router(news_v2_router)
app.include_router(news_v2_config_router)
from api.routers.graph import router as graph_router
app.include_router(graph_router)
from api.routers.storage import router as storage_router
app.include_router(storage_router)
from api.routers.architecture import router as architecture_router
app.include_router(architecture_router)
from api.routers.agents import router as agents_router
app.include_router(agents_router)
from api.routers.missions import router as missions_router
app.include_router(missions_router)
from api.routers.office import router as office_router
app.include_router(office_router)
from api.routers.usage import router as usage_router
app.include_router(usage_router)
from api.routers.terminal import router as terminal_router
app.include_router(terminal_router)
from api.routers.conductor import router as conductor_router
app.include_router(conductor_router)
from api.routers.owner import router as owner_router
app.include_router(owner_router)
from api.routers.keys import router as keys_router
app.include_router(keys_router)

# MCP Hub (#5) — mount TOBI's MCP server (Streamable HTTP) at /mcp. Inbound auth,
# rate-limit, scope, and audit are enforced by McpAuthMiddleware inside the app.
if MCP_AVAILABLE:
    try:
        app.mount("/mcp", mcp_server.asgi_app())

        # The Streamable-HTTP endpoint lives at /mcp/ (Starlette mounts add a slash).
        # Redirect the slash-less form so clients can use http://host/mcp too —
        # 307 preserves method, body, and the Authorization header on same-origin.
        @app.api_route("/mcp", methods=["GET", "POST", "DELETE"])
        async def _mcp_slashless():
            return RedirectResponse("/mcp/", status_code=307)
    except Exception as _mcp_err:  # never block the dashboard on MCP mount issues
        import logging as _logging
        _logging.getLogger("tobi.dashboard").warning("MCP mount skipped: %s", _mcp_err)

DIST_DIR = Path(__file__).parent.parent / "dashboard" / "dist"
# DB_PATH / _get_conn / _json_loads imported from api.deps above (Slice 0).


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
        "start_at": row["start_at"] if "start_at" in row.keys() else None,
        "reminder_at": row["reminder_at"] if "reminder_at" in row.keys() else None,
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
        # v2 dependencies (blocks / blocked-by), best-effort
        "blocks": _task_deps(conn, row["id"], "blocks"),
        "blocked_by": _task_deps(conn, row["id"], "blocked_by"),
    }
    if include_activity:
        task["activity"] = _fetch_activity(conn, row["id"])
    return task


def _task_deps(conn: sqlite3.Connection, task_id: int, direction: str) -> list[int]:
    """IDs this task blocks (direction='blocks') or is blocked by (='blocked_by')."""
    try:
        if direction == "blocks":
            rows = conn.execute("SELECT blocks_id FROM pm_task_deps WHERE task_id=?", (task_id,)).fetchall()
        else:
            rows = conn.execute("SELECT task_id FROM pm_task_deps WHERE blocks_id=?", (task_id,)).fetchall()
        return [r[0] for r in rows]
    except Exception:
        return []


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


# ── WORKFLOWS (Mission Control §4) ────────────────────────────────────────────────────────────────────────

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


@app.get("/api/hermes/skills")
def api_hermes_skills():
    """Read-only repo Hermes skill registry (#14): parsed metadata for the Ability
    dashboard — name, description, status, risk, version, last-modified. No execution,
    no DB mirror; a missing folder returns an empty list."""
    from core import hermes_skills
    return hermes_skills.skills_report()


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

        if payload.description is not None:
            updates.append("description=?")
            values.append(payload.description)
            changes["description"] = payload.description

        if payload.start_at is not None:
            updates.append("start_at=?")
            values.append(payload.start_at or None)
            changes["start_at"] = payload.start_at

        if payload.reminder_at is not None:
            updates.append("reminder_at=?")
            values.append(payload.reminder_at or None)
            changes["reminder_at"] = payload.reminder_at

        if payload.time_estimate is not None:
            updates.append("time_estimate=?")
            values.append(payload.time_estimate or None)
            changes["time_estimate"] = payload.time_estimate

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


import re





@app.on_event("startup")
async def startup():
    init_database()
    # Storage & Usage (#10): load the price table so per-call cost estimates use
    # config/llm_prices.yaml from the very first LLM call [S14].
    try:
        from core import usage_meter
        usage_meter.sync_prices()
    except Exception as e:
        import logging
        logging.getLogger("tobi.dashboard").warning("Price-table sync skipped: %s", e)
    # Auto-connect previously-connected integrations — re-inject vault secrets into
    # os.environ at boot using the cached key, with NO master-password prompt.
    try:
        conn = _get_conn()
        try:
            if vault.CRYPTO_AVAILABLE and vault.is_setup(conn) and vault.try_autounlock(conn):
                n = vault.inject_env(conn)
                import logging
                logging.getLogger("tobi.dashboard").info(
                    "Vault auto-unlocked on startup; injected %d secret(s).", n)
        finally:
            conn.close()
    except Exception as e:  # never let this block server startup
        import logging
        logging.getLogger("tobi.dashboard").warning("Vault auto-unlock skipped: %s", e)
    # Start the MCP server's session manager (Streamable HTTP).
    if MCP_AVAILABLE:
        try:
            await mcp_server.start_session()
        except Exception as e:
            import logging
            logging.getLogger("tobi.dashboard").warning("MCP session start skipped: %s", e)
    try:
        from api.developer import start_loop
        start_loop()
    except Exception as e:
        import logging
        logging.getLogger("tobi.dashboard").warning("Developer goal loop start skipped: %s", e)


@app.on_event("shutdown")
async def _mcp_shutdown():
    try:
        from api.developer import stop_loop
        stop_loop()
    except Exception:
        pass
    if MCP_AVAILABLE:
        try:
            await mcp_server.stop_session()
        except Exception:
            pass


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
    # manual drag order first (new projects with no order yet float to the top), then recency
    sql += " ORDER BY COALESCE(sort_order, -1) ASC, updated_at DESC, id DESC"
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


@app.post("/api/pm/projects/reorder")
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


@app.delete("/api/pm/projects/{project_id}")
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

@app.get("/api/pm/projects/{project_id}/goals")
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


@app.post("/api/pm/projects/{project_id}/goals")
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


@app.get("/api/pm/projects/{project_id}/overview")
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


@app.get("/api/pm/projects/{project_id}/resources")
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


@app.post("/api/pm/projects/{project_id}/resources/upload")
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


@app.post("/api/pm/projects/{project_id}/resources/link")
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


@app.patch("/api/pm/projects/{project_id}/resources/{rid}")
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


@app.delete("/api/pm/projects/{project_id}/resources/{rid}")
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


@app.get("/api/pm/projects/{project_id}/resources/{rid}/raw")
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
@app.post("/api/pm/projects/{project_id}/folders")
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


@app.patch("/api/pm/projects/{project_id}/folders/{fid}")
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


@app.delete("/api/pm/projects/{project_id}/folders/{fid}")
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

@app.post("/api/pm/icons")
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


@app.get("/api/pm/icons/{icon_id}")
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

@app.post("/api/pm/tasks/{task_id}/deps")
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


@app.delete("/api/pm/tasks/{task_id}/deps/{blocks_id}")
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

@app.post("/api/pm/projects/{project_id}/goals/{goal_id}/tasks")
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


@app.delete("/api/pm/projects/{project_id}/goals/{goal_id}/tasks/{task_id}")
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
                 "description": "After cycles, Tobi logs success/failure/insight/warning entries to SQLite. The beginning of institutional memory.", "how_to_unlock": "The store is built and wired — it just needs its first entry. Click “Reflect now” below to run a self-reflection and write lesson #1, or wait for the Sunday 20:00 weekly reflection. Any logged lesson (cycle outcome, /note, coaching) also activates it.", "effort": "done"},
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
                 "description": "OAuth2 flow for Drive, Gmail & Calendar. Read files, search inbox, check calendar — all through one Google Cloud OAuth client.",
                 "how_to_unlock": None, "effort": "done"},
            ],
            "presence": [
                {"id": "webhook_triggers", "name": "Webhook + event-driven triggers",
                 "description": "Move beyond cron. Add FastAPI webhook endpoints for Stripe events, GitHub, email — Tobi acts when something happens, not just at 8am.",
                 "how_to_unlock": "Add POST /webhooks/{source} endpoints. Map event types to Tobi actions. Wire to Telegram notification on receipt.", "effort": "1 week"},
                {"id": "gmail_integration", "name": "Gmail read",
                 "description": "Tobi reads your inbox, summarizes threads, and surfaces important emails.",
                 "how_to_unlock": None, "effort": "done"},
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
                 "description": "Tobi knows your schedule. Lists upcoming events, checks availability, preps briefings before meetings.",
                 "how_to_unlock": None, "effort": "done"},
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

    # TOBI CLI (#11) delivers the Awakening control abilities: the two-axis permission model
    # replaces the old _BLOCKED_CMDS denylist, and full-machine scope replaces the PROJECT_DIR
    # lock. Evidence = the terminal engine module is present [D30].
    terminal_ready = file_ok("core/terminal_engine.py")

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
        "google_oauth": env("GOOGLE_CLIENT_ID") and env("GOOGLE_CLIENT_SECRET"),
        "gmail_integration": env("GOOGLE_CLIENT_ID") and env("GOOGLE_CLIENT_SECRET"),
        "calendar_integration": env("GOOGLE_CLIENT_ID") and env("GOOGLE_CLIENT_SECRET"),
        "telegram_bot": has_bot,
        "cron_scheduler": has_bot and has_llm,
        "proactive_reports": has_bot and has_llm,
        # Tier 1 (Awakening) control abilities delivered by the terminal engine (#11)
        "tiered_permissions": terminal_ready,
        "full_filesystem": terminal_ready,
        # Remaining Tier 1+ abilities default to False (not yet built)
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


def _save_evo_snapshot(conn: sqlite3.Connection, statuses: dict) -> None:
    now = datetime.now(timezone.utc).isoformat()
    for ability_id, val in statuses.items():
        # values are bool (legacy detector) or a 4-valued string (Awakening registry #17)
        status = val if isinstance(val, str) else ("active" if val else "inactive")
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


def _build_evo_response(statuses: dict[str, bool], prev: dict[str, str], conn=None):
    just_unlocked: list[int] = []
    tiers_out = []

    # Tier 1 (Awakening) is sourced from the evidence-based registry (#17), not the static
    # bool detector — its 9 abilities carry a 4-valued status (active|partial|setup_needed|
    # inactive) + evidence/missing/setup_actions, and only 'active' counts toward progress.
    awakening_pillars = None
    awakening_labels = None
    if conn is not None:
        try:
            from core import awakening as _awk
            awakening_pillars = _awk.tier1_pillars(conn)
            awakening_labels = _awk.pillar_labels()
        except Exception:
            awakening_pillars = None

    for tier in _TIER_DEFINITIONS:
        use_awakening = tier["id"] == 1 and awakening_pillars is not None
        pillars_src = awakening_pillars if use_awakening else tier["pillars"]

        all_ids: list[str] = []
        active_count = 0
        pillars_out: dict = {}

        for pillar_key, abilities in pillars_src.items():
            out = []
            for ab in abilities:
                ab_id = ab["id"]
                if "status" in ab:  # Awakening ability: 4-valued status already resolved
                    status = ab["status"]
                    is_active = status == "active"
                else:
                    is_active = statuses.get(ab_id, False)
                    status = "active" if is_active else "inactive"
                was_active = prev.get(ab_id) == "active"
                all_ids.append(ab_id)
                if is_active:
                    active_count += 1
                out.append({**ab, "status": status,
                             "just_activated": is_active and not was_active})
            pillars_out[pillar_key] = out

        total = len(all_ids)
        complete = active_count == total and total > 0
        was_complete = all(prev.get(aid) == "active" for aid in all_ids)
        if complete and not was_complete:
            just_unlocked.append(tier["id"])

        tier_obj = {
            **{k: v for k, v in tier.items() if k != "pillars"},
            "pillars": pillars_out,
            "active_count": active_count,
            "total_count": total,
            "progress_pct": round(active_count / total * 100) if total else 0,
            "complete": complete,
        }
        if use_awakening and awakening_labels:
            tier_obj["pillar_labels"] = awakening_labels
        tiers_out.append(tier_obj)

    return tiers_out, just_unlocked


@app.get("/api/evolution")
async def get_evolution():
    conn = _get_conn()
    statuses = _detect_abilities(conn)
    prev = _load_evo_snapshot(conn)
    tiers, just_unlocked = _build_evo_response(statuses, prev, conn)
    # persist the Awakening 4-valued statuses too so just-activated survives reloads (#17)
    try:
        from core import awakening as _awk
        awk_status = _awk.status_map(conn)
    except Exception:
        awk_status = {}
    _save_evo_snapshot(conn, {**statuses, **awk_status})
    app_version = current_developer_version(conn)
    conn.close()

    total_abilities = sum(t["total_count"] for t in tiers)
    total_active = sum(t["active_count"] for t in tiers)
    jarvis_pct = round(total_active / total_abilities * 100) if total_abilities else 0

    current_tier = next((t["id"] for t in tiers if not t["complete"]), tiers[-1]["id"])
    current_tier_data = tiers[current_tier]
    missing = [
        ab for pillar in current_tier_data["pillars"].values()
        for ab in pillar if ab["status"] != "active"
    ]

    return {
        "tiers": tiers,
        "version": app_version,
        "current_tier": current_tier,
        "jarvis_pct": jarvis_pct,
        "total_active": total_active,
        "total_abilities": total_abilities,
        "just_unlocked": just_unlocked,
        "missing_in_current_tier": missing,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/awakening")
async def get_awakening():
    """Tier 1 (Awakening) evidence report (#17) — the single source read by the Evolution
    guided panel, the Ability page mirror, and TOBI's awakening_status tool."""
    from core import awakening
    conn = _get_conn()
    try:
        abilities = awakening.evaluate(conn)
        summary = awakening.summary(conn)
    finally:
        conn.close()
    return {
        "tier": 1,
        "tier_name": "Awakening",
        "categories": [
            {"key": "persistent_memory", "label": "Persistent Memory"},
            {"key": "identity_personality", "label": "Identity & Personality"},
            {"key": "basic_real_world_action", "label": "Basic Real-World Action"},
        ],
        "abilities": abilities,
        "active_count": summary["active_count"],
        "total": summary["total"],
        "progress_pct": summary["progress_pct"],
        "complete": summary["complete"],
        "sensitive_pending_review": summary["sensitive_pending_review"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _build_reflection(conn: sqlite3.Connection) -> tuple[str, dict[str, int]]:
    """Compose a genuine self-reflection from real activity. Uses the connected
    LLM when available; falls back to a deterministic summary so the lessons
    store can be seeded even with no model key. Returns (text, stats)."""
    stats = {
        "conversations": _count(conn, "SELECT COUNT(*) FROM conversations"),
        "projects":      _count(conn, "SELECT COUNT(*) FROM projects"),
        "tasks":         _count(conn, "SELECT COUNT(*) FROM tasks"),
        "lessons":       _count(conn, "SELECT COUNT(*) FROM lessons"),
        "reports":       _count(conn, "SELECT COUNT(*) FROM reports"),
        "missions":      _count(conn, "SELECT COUNT(*) FROM missions"),
        "agents":        _count(conn, "SELECT COUNT(*) FROM agents"),
    }
    recent_lessons = [
        f"- [{r[0]}] {r[1] or ''}: {(r[2] or '')[:120]}"
        for r in conn.execute(
            "SELECT lesson_type, title, content FROM lessons ORDER BY created_at DESC LIMIT 8"
        ).fetchall()
    ]
    lessons_text = "\n".join(recent_lessons) if recent_lessons else "No lessons yet — this is the first."

    deterministic = (
        "First self-reflection — institutional memory begins.\n"
        f"- State: {stats['conversations']} conversations, {stats['projects']} projects, "
        f"{stats['tasks']} tasks, {stats['missions']} missions, {stats['agents']} agents on record.\n"
        f"- Genesis (Tier 0) is essentially complete: persona, memory, classifier, coding agent, "
        f"integrations and always-on presence are live.\n"
        "- What went well: the foundation is wired end-to-end and the secrets vault now lets new "
        "abilities light up without a restart.\n"
        "- To improve next: turn repeated lessons into reusable skills, and let reflection run "
        "automatically after each cycle rather than only weekly.\n"
        "- Insight: a Jarvis is built one logged lesson at a time — this entry is lesson #1."
    )

    try:
        from core.model_router import llm_complete
        prompt = (
            "You are Tobi, a personal AI agent writing your very first self-reflection lesson — "
            "the seed of your institutional memory.\n\n"
            f"Activity so far: {stats['conversations']} conversations, {stats['projects']} projects, "
            f"{stats['tasks']} tasks, {stats['missions']} missions, {stats['agents']} agents, "
            f"{stats['reports']} reports.\n"
            f"Recent lessons:\n{lessons_text}\n\n"
            "Write a concise, honest reflection (4-6 short bullet points): what is working, what to "
            "improve, and one insight to carry forward. Be specific and grounded in the numbers above. "
            "Under 180 words. No preamble."
        )
        text = (llm_complete(prompt, task_type="simple", max_tokens=400) or "").strip()
        if len(text) < 40:  # model returned nothing useful → fall back
            text = deterministic
    except Exception:
        text = deterministic

    return text, stats


@app.post("/api/evolution/reflect")
async def post_evolution_reflect():
    """On-demand self-reflection. Writes a genuine lesson to the self-reflection
    DB, which activates the Genesis `lessons_store` ability (it keys off the
    lessons table having rows, mirroring how conversation_history keys off
    conversations). The weekly job does the same on Sundays — this lets the
    owner seed/refresh it any time."""
    conn = _get_conn()
    try:
        text, stats = _build_reflection(conn)
    finally:
        conn.close()

    from core.database import add_lesson
    title = f"Self-reflection {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    add_lesson(content=text, title=title, lesson_type="insight", impact_score=6)

    # Re-detect so the caller learns whether the ability flipped on.
    conn = _get_conn()
    statuses = _detect_abilities(conn)
    conn.close()

    return {
        "ok": True,
        "lesson": {"title": title, "content": text, "lesson_type": "insight"},
        "lessons_store_active": statuses.get("lessons_store", False),
        "stats": stats,
    }


# ── Genesis Complete: encrypted secrets vault + integrations manager ────────────
# The dashboard has no API-key auth (local-only), so the master-password session
# token IS the security gate for vault writes/reveals. Secret values are never
# returned by list/status — only `last4` + metadata.

class VaultSetupReq(BaseModel):
    master: str
    import_env: bool = True


class VaultUnlockReq(BaseModel):
    master: str


class VaultAutoUnlockReq(BaseModel):
    enabled: bool = True


class VaultPasswordReq(BaseModel):
    password: str


class VaultImportReq(BaseModel):
    blob: str
    password: str


class VaultProfileReq(BaseModel):
    name: str
    label: str | None = None
    activate: bool = True


class IntegrationConnectReq(BaseModel):
    fields: dict[str, str]


class CustomSecretReq(BaseModel):
    name: str
    value: str
    secret_type: str = "custom"


class RevealReq(BaseModel):
    name: str
    master: str


_ABILITY_NAMES = {
    ab["id"]: ab["name"]
    for tier in _TIER_DEFINITIONS
    for pillar in tier["pillars"].values()
    for ab in pillar
}


def _genesis_status(conn: sqlite3.Connection) -> dict:
    """Live Genesis (Tier 0) completion from the real ability detector."""
    statuses = _detect_abilities(conn)
    ids = [ab["id"] for pillar in _TIER_DEFINITIONS[0]["pillars"].values() for ab in pillar]
    active = sum(1 for i in ids if statuses.get(i))
    return {
        "abilities": {i: bool(statuses.get(i)) for i in ids},
        "active": active, "total": len(ids),
        "pct": round(active / len(ids) * 100) if ids else 0,
        "complete": active == len(ids) and len(ids) > 0,
    }


def _integration_view(conn: sqlite3.Connection) -> list[dict]:
    statuses = _detect_abilities(conn)
    secrets = {s["name"]: s for s in vault.list_secrets(conn)}
    out: list[dict] = []
    for item in registry.REGISTRY:
        fields_out, any_set = [], False
        for f in item["fields"]:
            s = secrets.get(f["name"])
            if s:
                any_set = True
            fields_out.append({
                "name": f["name"], "label": f["label"], "type": f["type"],
                "help_url": f.get("help_url"),
                "set": bool(s), "last4": s["last4"] if s else None,
                "test_status": s["test_status"] if s else None,
            })
        out.append({
            "id": item["id"], "label": item["label"], "category": item["category"],
            "required": item["required"], "available": item.get("available", True),
            "icon": item.get("icon"), "blurb": item.get("blurb"), "coming_in": item.get("coming_in"),
            "fields": fields_out, "connected": any_set,
            "abilities": [
                {"id": a, "name": _ABILITY_NAMES.get(a, a), "active": bool(statuses.get(a))}
                for a in item["abilities_unlocked"]
            ],
        })
    return out


# ── Vault lifecycle ──
@app.get("/api/vault/status")
async def vault_status():
    conn = _get_conn()
    try:
        return vault.status(conn)
    finally:
        conn.close()


@app.post("/api/vault/setup")
async def vault_setup(body: VaultSetupReq):
    conn = _get_conn()
    try:
        token = vault.setup(conn, body.master, import_env=body.import_env)
        return {"ok": True, "session": token, "status": vault.status(conn), "genesis": _genesis_status(conn)}
    except vault.VaultError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()


@app.post("/api/vault/unlock")
async def vault_unlock(body: VaultUnlockReq):
    conn = _get_conn()
    try:
        token = vault.unlock(conn, body.master)
        injected = vault.inject_env(conn)
        return {"ok": True, "session": token, "injected": injected,
                "status": vault.status(conn), "genesis": _genesis_status(conn)}
    except vault.VaultError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()


@app.post("/api/vault/lock")
async def vault_lock(x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    # no hard guard — locking is always safe; just clear the in-memory key
    vault.lock()
    return {"ok": True}


@app.post("/api/vault/reload")
async def vault_reload(x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    _vault_guard(x_vault_session)
    conn = _get_conn()
    try:
        n = vault.reload(conn)
        return {"ok": True, "injected": n, "genesis": _genesis_status(conn)}
    finally:
        conn.close()


@app.post("/api/vault/autounlock")
async def vault_autounlock(body: VaultAutoUnlockReq,
                           x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    """Toggle startup auto-connect. Enabling caches the current key (requires an
    unlocked session); disabling forgets it so a password is needed again on boot."""
    _vault_guard(x_vault_session)
    conn = _get_conn()
    try:
        if body.enabled:
            ok = vault.enable_autounlock(conn)
        else:
            vault.disable_autounlock(conn)
            ok = True
        return {"ok": ok, "autounlock": vault.autounlock_enabled(conn)}
    finally:
        conn.close()


# ── MCP Hub (#5) management API ─────────────────────────────────────────────
# Admin of a (potentially internet-exposed) MCP server is sensitive → gated by the
# vault session, like the other secret-management endpoints. The MCP wire protocol
# itself lives at /mcp and is auth'd by McpAuthMiddleware (bearer token + scopes).

class McpConfigReq(BaseModel):
    enabled: bool | None = None
    public_url: str | None = None
    rate_limit_per_minute: int | None = None


class McpClientReq(BaseModel):
    name: str
    scopes: list[str] | None = None


class McpScopesReq(BaseModel):
    scopes: list[str]


@app.get("/api/mcp/server/config")
async def mcp_server_config(x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    _vault_guard(x_vault_session)
    cfg = mcpsec.get_config()
    tools = []
    if MCP_AVAILABLE:
        try:
            tools = [{"name": t.name, "description": (t.description or "")[:160],
                      "sensitive": t.name in mcp_server.SENSITIVE_TOOLS}
                     for t in await mcp_server.mcp.list_tools()]
        except Exception:
            tools = []
    oauth = mcpsec.get_oauth_config()
    oauth_public = {"enabled": bool(oauth.get("enabled")), "issuer": oauth.get("issuer"),
                    "audience": oauth.get("audience"), "alg": oauth.get("alg", "HS256")}
    tunnel = mcp_tunnel.status() if MCP_AVAILABLE else {"available": False, "running": False}
    return {"available": MCP_AVAILABLE, "config": cfg, "tools": tools,
            "mount": "/mcp" if MCP_AVAILABLE else None,
            "exposed": bool(cfg.get("exposed")), "oauth": oauth_public, "tunnel": tunnel}


@app.put("/api/mcp/server/config")
async def mcp_set_config(body: McpConfigReq, x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    _vault_guard(x_vault_session)
    fields: dict = {}
    if body.enabled is not None:
        fields["enabled"] = int(body.enabled)
    if body.public_url is not None:
        fields["public_url"] = body.public_url
    if body.rate_limit_per_minute is not None:
        fields["rate_limit_json"] = json.dumps({"per_minute": int(body.rate_limit_per_minute)})
    return {"ok": True, "config": mcpsec.set_config(**fields)}


@app.get("/api/mcp/clients")
async def mcp_clients(x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    _vault_guard(x_vault_session)
    return {"clients": mcpsec.list_clients()}


@app.post("/api/mcp/clients")
async def mcp_issue_client(body: McpClientReq, x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    """Issue an inbound client. Returns the raw token ONCE — it's only stored hashed."""
    _vault_guard(x_vault_session)
    return {"ok": True, **mcpsec.issue_client(body.name, body.scopes)}


@app.patch("/api/mcp/clients/{client_id}")
async def mcp_patch_client(client_id: int, body: McpScopesReq, x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    _vault_guard(x_vault_session)
    mcpsec.set_client_scopes(client_id, body.scopes)
    return {"ok": True}


@app.delete("/api/mcp/clients/{client_id}")
async def mcp_revoke_client(client_id: int, x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    _vault_guard(x_vault_session)
    mcpsec.revoke_client(client_id)
    return {"ok": True}


@app.get("/api/mcp/logs")
async def mcp_logs(limit: int = Query(100), direction: str | None = Query(None),
                   x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    _vault_guard(x_vault_session)
    return {"logs": mcpsec.get_logs(limit, direction)}


@app.get("/api/mcp/approvals")
async def mcp_approvals(status: str | None = Query("pending"),
                        x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    _vault_guard(x_vault_session)
    return {"approvals": mcpsec.list_approvals(status)}


@app.post("/api/mcp/approvals/{approval_id}/approve")
async def mcp_approve(approval_id: int, x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    _vault_guard(x_vault_session)
    return {"ok": True, **mcpsec.decide_approval(approval_id, True)}


@app.post("/api/mcp/approvals/{approval_id}/reject")
async def mcp_reject(approval_id: int, x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    _vault_guard(x_vault_session)
    return {"ok": True, **mcpsec.decide_approval(approval_id, False)}


# ── MCP Hub (#5) — M2: outbound client (connections + external tools) ───────
class McpConnectionReq(BaseModel):
    name: str
    transport: str = "http"            # http | sse | stdio
    endpoint: str
    token: str | None = None           # optional bearer; stored in the vault


class McpConnEnableReq(BaseModel):
    enabled: bool


class McpToolPatchReq(BaseModel):
    enabled: bool | None = None
    permission: str | None = None      # allow | ask | deny


class McpInvokeReq(BaseModel):
    args: dict = Field(default_factory=dict)


def _mcp_guard(token: str | None) -> None:
    _vault_guard(token)
    if not MCP_AVAILABLE:
        raise HTTPException(status_code=503, detail="MCP SDK not installed — run: pip install mcp")


@app.get("/api/mcp/connections")
async def mcp_connections(x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    _mcp_guard(x_vault_session)
    return {"connections": mcp_client.list_connections()}


@app.post("/api/mcp/connections")
async def mcp_add_connection(body: McpConnectionReq, x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    """Add + test an outbound MCP server. Blocks (400) if the handshake fails."""
    _mcp_guard(x_vault_session)
    try:
        return {"ok": True, **await mcp_client.add_connection(body.name, body.transport, body.endpoint, body.token)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Connection test failed: {e}")


@app.post("/api/mcp/connections/{cid}/test")
async def mcp_test_connection(cid: int, x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    _mcp_guard(x_vault_session)
    return await mcp_client.test_connection(cid)


@app.post("/api/mcp/connections/{cid}/refresh")
async def mcp_refresh_connection(cid: int, x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    _mcp_guard(x_vault_session)
    return await mcp_client.refresh_connection(cid)


@app.patch("/api/mcp/connections/{cid}")
async def mcp_patch_connection(cid: int, body: McpConnEnableReq, x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    _mcp_guard(x_vault_session)
    mcp_client.set_connection_enabled(cid, body.enabled)
    return {"ok": True}


@app.delete("/api/mcp/connections/{cid}")
async def mcp_delete_connection(cid: int, x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    _mcp_guard(x_vault_session)
    mcp_client.delete_connection(cid)
    return {"ok": True}


@app.post("/api/mcp/connections/health")
async def mcp_connections_health(x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    _mcp_guard(x_vault_session)
    return {"health": await mcp_client.health_check_all()}


@app.get("/api/mcp/tools")
async def mcp_tools(source: str | None = Query(None), x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    """External (connected) tools. Self/exposed tools are in /server/config."""
    _mcp_guard(x_vault_session)
    return {"tools": mcp_client.list_tools(source)}


@app.patch("/api/mcp/tools/{tool_id}")
async def mcp_patch_tool(tool_id: int, body: McpToolPatchReq, x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    _mcp_guard(x_vault_session)
    return {"ok": True, "tool": mcp_client.set_tool(tool_id, body.enabled, body.permission)}


@app.post("/api/mcp/tools/{tool_id}/invoke")
async def mcp_invoke_tool(tool_id: int, body: McpInvokeReq, x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    """'Try it' — owner-initiated call (respects 'deny', overrides 'ask')."""
    _mcp_guard(x_vault_session)
    return await mcp_client.invoke_tool(tool_id, body.args, owner_override=True)


# ── MCP Hub (#5) — M4: OAuth, internet exposure (tunnel), A2A ───────────────
class McpOAuthReq(BaseModel):
    enabled: bool
    issuer: str | None = None
    audience: str | None = None
    algorithm: str = "HS256"
    secret: str | None = None          # HS256 signing key → stored in the vault


class McpTunnelReq(BaseModel):
    action: str                        # start | stop
    port: int | None = None


class A2aCardReq(BaseModel):
    name: str | None = None
    description: str | None = None
    version: str | None = None


class A2aPeerReq(BaseModel):
    url: str


class A2aMessageReq(BaseModel):
    text: str


@app.put("/api/mcp/server/oauth")
async def mcp_set_oauth(body: McpOAuthReq, x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    _mcp_guard(x_vault_session)
    oc = mcpsec.set_oauth_config(enabled=body.enabled, issuer=body.issuer, audience=body.audience,
                                 algorithm=body.algorithm, secret=body.secret)
    return {"ok": True, "oauth": {"enabled": oc["enabled"], "issuer": oc.get("issuer"),
                                  "audience": oc.get("audience"), "alg": oc.get("alg")}}


@app.get("/api/mcp/server/tunnel")
async def mcp_get_tunnel(x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    _mcp_guard(x_vault_session)
    return mcp_tunnel.status()


@app.post("/api/mcp/server/tunnel")
async def mcp_set_tunnel(body: McpTunnelReq, x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    _mcp_guard(x_vault_session)
    if body.action == "start":
        port = body.port or int(os.getenv("DASHBOARD_PORT", "8080"))
        return await asyncio.to_thread(mcp_tunnel.start, port)
    if body.action == "stop":
        return mcp_tunnel.stop()
    raise HTTPException(status_code=400, detail="action must be 'start' or 'stop'")


@app.get("/api/mcp/a2a/card")
async def mcp_a2a_card(x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    _mcp_guard(x_vault_session)
    pub = mcp_tunnel.status().get("public_url")
    return {"card": mcp_a2a.get_self_card(pub)}


@app.put("/api/mcp/a2a/card")
async def mcp_a2a_set_card(body: A2aCardReq, x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    _mcp_guard(x_vault_session)
    mcp_a2a.set_self_card(body.name, body.description, body.version)
    return {"ok": True, "card": mcp_a2a.get_self_card(mcp_tunnel.status().get("public_url"))}


@app.get("/api/mcp/a2a/peers")
async def mcp_a2a_peers(x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    _mcp_guard(x_vault_session)
    return {"peers": mcp_a2a.list_peers()}


@app.post("/api/mcp/a2a/peers")
async def mcp_a2a_add_peer(body: A2aPeerReq, x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    _mcp_guard(x_vault_session)
    try:
        return {"ok": True, **await mcp_a2a.add_peer(body.url)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not add peer: {e}")


@app.delete("/api/mcp/a2a/peers/{peer_id}")
async def mcp_a2a_remove_peer(peer_id: int, x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    _mcp_guard(x_vault_session)
    mcp_a2a.remove_peer(peer_id)
    return {"ok": True}


@app.post("/api/mcp/a2a/peers/{peer_id}/message")
async def mcp_a2a_message(peer_id: int, body: A2aMessageReq, x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    _mcp_guard(x_vault_session)
    return await mcp_a2a.send_message(peer_id, body.text)


# Public discovery metadata (no auth — non-secret; external agents/clients fetch these).
@app.get("/.well-known/agent.json")
async def well_known_agent():
    if not MCP_AVAILABLE:
        raise HTTPException(status_code=404, detail="A2A not available")
    pub = mcp_tunnel.status().get("public_url") or str(app_base_url())
    return mcp_a2a.get_self_card(pub)


@app.get("/.well-known/oauth-protected-resource")
async def well_known_oauth():
    if not MCP_AVAILABLE:
        raise HTTPException(status_code=404, detail="OAuth not configured")
    oc = mcpsec.get_oauth_config()
    pub = mcp_tunnel.status().get("public_url") or str(app_base_url())
    meta = {"resource": f"{pub}/mcp"}
    if oc.get("enabled") and oc.get("issuer"):
        meta["authorization_servers"] = [oc["issuer"]]
    return meta


def app_base_url() -> str:
    port = os.getenv("DASHBOARD_PORT", "8080")
    return f"http://localhost:{port}"


@app.get("/api/vault/audit")
async def vault_audit(limit: int = Query(100), x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    _vault_guard(x_vault_session)
    conn = _get_conn()
    try:
        return {"entries": vault.get_audit(conn, limit)}
    finally:
        conn.close()


@app.post("/api/vault/export")
async def vault_export(body: VaultPasswordReq, x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    _vault_guard(x_vault_session)
    conn = _get_conn()
    try:
        return {"ok": True, "blob": vault.export_blob(conn, body.password)}
    except vault.VaultError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()


@app.post("/api/vault/import")
async def vault_import(body: VaultImportReq, x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    _vault_guard(x_vault_session)
    conn = _get_conn()
    try:
        n = vault.import_blob(conn, body.blob, body.password)
        vault.inject_env(conn)
        return {"ok": True, "imported": n, "genesis": _genesis_status(conn)}
    except vault.VaultError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()


@app.get("/api/vault/profiles")
async def vault_profiles():
    conn = _get_conn()
    try:
        return {"profiles": vault.list_profiles(conn), "active": vault.active_profile(conn)}
    finally:
        conn.close()


@app.post("/api/vault/profiles")
async def vault_create_profile(body: VaultProfileReq, x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    _vault_guard(x_vault_session)
    conn = _get_conn()
    try:
        vault.create_profile(conn, body.name, body.label)
        if body.activate:
            vault.set_active_profile(conn, body.name)
        return {"ok": True, "profiles": vault.list_profiles(conn), "active": vault.active_profile(conn)}
    except vault.VaultError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()


# ── Integrations catalog + connect/test/reveal/remove ──
@app.get("/api/integrations")
async def list_integrations():
    conn = _get_conn()
    try:
        return {
            "integrations": _integration_view(conn),
            "genesis": _genesis_status(conn),
            "vault": vault.status(conn),
        }
    finally:
        conn.close()


@app.post("/api/integrations/{integration_id}/connect")
async def connect_integration(integration_id: str, body: IntegrationConnectReq,
                              x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    _vault_guard(x_vault_session)
    item = registry.get(integration_id)
    if not item or not item.get("available", True):
        raise HTTPException(status_code=404, detail="Unknown or unavailable integration.")
    values = {k: v for k, v in (body.fields or {}).items() if v and v.strip()}
    if not values:
        raise HTTPException(status_code=400, detail="Provide at least one value.")

    conn = _get_conn()
    try:
        names = [f["name"] for f in item["fields"]]
        snapshot = {n: os.environ.get(n) for n in names}
        for n, v in values.items():
            os.environ[n] = v
        ok, msg = registry.test_integration(integration_id)
        verified = bool(ok and registry.test_confirms_read_access(integration_id))
        vault._audit(conn, "test", integration_id=integration_id, ok=ok, detail=msg)
        if not ok:
            for n, old in snapshot.items():  # block: don't persist a bad key
                if old is None:
                    os.environ.pop(n, None)
                else:
                    os.environ[n] = old
            raise HTTPException(status_code=400, detail=msg)
        for f in item["fields"]:
            if f["name"] in values:
                vault.set_secret(conn, f["name"], values[f["name"]], integration_id=integration_id,
                                 secret_type=f["type"], test_status="ok" if verified else "untested")
        return {"ok": True, "message": msg, "genesis": _genesis_status(conn),
                "integrations": _integration_view(conn), "verified": verified}
    finally:
        conn.close()


@app.post("/api/integrations/{integration_id}/test")
async def test_integration_endpoint(integration_id: str,
                                    x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    _vault_guard(x_vault_session)
    item = registry.get(integration_id)
    if not item:
        raise HTTPException(status_code=404, detail="Unknown integration.")
    conn = _get_conn()
    try:
        vault.inject_env(conn)  # ensure current vault values are live
        ok, msg = registry.test_integration(integration_id)
        verified = bool(ok and registry.test_confirms_read_access(integration_id))
        status = "ok" if verified else ("failed" if not ok else "untested")
        for f in item["fields"]:
            try:
                vault.mark_test_status(conn, f["name"], status)
            except Exception:
                pass
        vault._audit(conn, "test", integration_id=integration_id, ok=ok, detail=msg)
        return {"ok": ok, "verified": verified, "message": msg, "genesis": _genesis_status(conn)}
    finally:
        conn.close()


@app.post("/api/integrations/reveal")
async def reveal_secret(body: RevealReq, x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    _vault_guard(x_vault_session)
    conn = _get_conn()
    try:
        return {"ok": True, "name": body.name, "value": vault.reveal(conn, body.name, body.master)}
    except vault.VaultError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()


@app.post("/api/integrations/custom")
async def add_custom_secret(body: CustomSecretReq,
                            x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    _vault_guard(x_vault_session)
    name = body.name.strip().upper().replace(" ", "_")
    if not name:
        raise HTTPException(status_code=400, detail="Secret name is required.")
    conn = _get_conn()
    try:
        vault.set_secret(conn, name, body.value, integration_id="custom", secret_type=body.secret_type)
        os.environ[name] = body.value
        return {"ok": True, "genesis": _genesis_status(conn)}
    except vault.VaultError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()


@app.delete("/api/integrations/{integration_id}")
async def remove_integration(integration_id: str,
                             x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    _vault_guard(x_vault_session)
    item = registry.get(integration_id)
    if not item:
        raise HTTPException(status_code=404, detail="Unknown integration.")
    conn = _get_conn()
    try:
        for f in item["fields"]:
            vault.delete_secret(conn, f["name"], integration_id=integration_id)
        return {"ok": True, "genesis": _genesis_status(conn), "integrations": _integration_view(conn)}
    finally:
        conn.close()


# ── Google OAuth2 flow ─────────────────────────────────────────────────────────

def _google_redirect_uri(request: Request) -> str:
    """Build the OAuth redirect URI from the live request, respecting proxy headers."""
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host") or request.headers.get("host", "localhost")
    return f"{scheme}://{host}/api/integrations/google/oauth/callback"


@app.get("/api/integrations/google/oauth/start")
async def google_oauth_start(request: Request):
    """Redirect the browser to Google's consent screen."""
    from core.integrations import GoogleIntegration
    g = GoogleIntegration()
    if not g.is_available():
        raise HTTPException(status_code=400, detail="Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET first.")
    g.redirect_uri = _google_redirect_uri(request)
    return RedirectResponse(url=g.get_auth_url())


@app.get("/api/integrations/google/oauth/callback")
async def google_oauth_callback(request: Request, code: str | None = None, error: str | None = None):
    """Handle the OAuth redirect — exchange code for tokens, save them."""
    from core.integrations import GoogleIntegration
    if error:
        return HTMLResponse(content=f"<script>window.close();</script>"
                            f"<body>Authorization denied: {error}</body>", status_code=200)
    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code.")
    g = GoogleIntegration()
    if not g.is_available():
        raise HTTPException(status_code=400, detail="Google credentials not configured.")
    g.redirect_uri = _google_redirect_uri(request)
    result = g.exchange_code(code)
    if result.get("error"):
        raise HTTPException(status_code=400, detail=f"OAuth exchange failed: {result['error'][:300]}")
    ok, msg = registry.test_integration("google")
    verified = bool(ok and registry.test_confirms_read_access("google"))
    conn = _get_conn()
    try:
        item = registry.get("google") or {}
        for field in item.get("fields", []):
            vault.mark_test_status(conn, field["name"], "ok" if verified else "failed")
        vault._audit(conn, "test", integration_id="google", ok=verified, detail=msg)
    finally:
        conn.close()
    if not verified:
        raise HTTPException(status_code=400, detail="Google authorization completed but read access could not be verified.")
    # Close the popup — the Integrations page polls status and will refresh.
    return HTMLResponse(content="""<!DOCTYPE html><html><body>
    <h3 style="font-family:sans-serif;text-align:center;margin-top:40px">
    Google connected — you can close this tab.</h3>
    <script>setTimeout(()=>window.close(),2000);</script>
    </body></html>""")


@app.get("/api/integrations/google/status")
async def google_oauth_status(request: Request):
    """Return Google connection status (connected? email? scopes?)."""
    from core.integrations import GoogleIntegration
    g = GoogleIntegration()
    connected = g.is_connected()
    email = ""
    if connected:
        try:
            import requests
            token = g._get_valid_access_token()
            if token:
                r = requests.get(g.USERINFO_URL,
                                 headers={"Authorization": f"Bearer {token}"}, timeout=10)
                if r.status_code == 200:
                    email = r.json().get("email", "")
        except Exception:
            pass
    return {
        "configured": g.is_available(),
        "connected": connected,
        "email": email,
        "redirect_uri": _google_redirect_uri(request),
    }


@app.post("/api/integrations/google/disconnect")
async def google_disconnect(x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    """Revoke Google tokens and delete the local token file."""
    _vault_guard(x_vault_session)
    from core.integrations import GoogleIntegration
    g = GoogleIntegration()
    ok = g.revoke()
    return {"ok": ok}


# ── Brain: long-term owner memory (auto-learn + import + chat) ──────────────────

def _brain_backend():
    """Return the legacy contract implementation selected by the Brain rollout flag."""
    if owner_flags.brain_v2_mode() == "on":
        brain_v2_compat.ensure_ready()
        return brain_v2_compat
    return brain


def _brain_call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except vault.VaultLocked as exc:
        raise HTTPException(status_code=423, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


class BrainMemoryCreate(BaseModel):
    content: str
    category: str = "identity"
    confidence: float = 0.6
    source: str = "manual"


class BrainMemoryPatch(BaseModel):
    content: str | None = None
    category: str | None = None
    confidence: float | None = None


class BrainSearchReq(BaseModel):
    query: str
    k: int = 12


class BrainResolveReq(BaseModel):
    decision: str  # keep_existing | use_candidate | keep_both


class BrainImportReq(BaseModel):
    filename: str = "import"
    content: str


class BrainImportCommitReq(BaseModel):
    filename: str = "import"
    source_type: str = "md"
    items: list[dict]


class BrainMergeReq(BaseModel):
    ids: list[int]
    keep_id: int | None = None


class BrainRememberReq(BaseModel):
    content: str
    category: str | None = None


class BrainChatReq(BaseModel):
    message: str


@app.get("/api/brain/stats")
def brain_stats():
    backend = _brain_backend()
    return _brain_call(backend.stats)


@app.get("/api/brain/categories")
def brain_categories():
    return {"categories": brain.list_categories()}


class BrainCategoryPatchRequest(BaseModel):
    is_locked: bool | None = None
    label: str | None = None
    color: str | None = None


@app.patch("/api/brain/categories/{cat_id}")
def brain_patch_category(cat_id: str, payload: BrainCategoryPatchRequest):
    conn = _get_conn()
    try:
        if not conn.execute("SELECT 1 FROM brain_categories WHERE id=?", (cat_id,)).fetchone():
            raise HTTPException(status_code=404, detail="category not found")
        fields, vals = [], []
        if payload.is_locked is not None:
            fields.append("is_locked=?"); vals.append(1 if payload.is_locked else 0)
        if payload.label is not None:
            fields.append("label=?"); vals.append(payload.label)
        if payload.color is not None:
            fields.append("color=?"); vals.append(payload.color)
        if fields:
            vals.append(cat_id)
            conn.execute(f"UPDATE brain_categories SET {', '.join(fields)} WHERE id=?", vals)
            conn.commit()
        row = conn.execute("SELECT * FROM brain_categories WHERE id=?", (cat_id,)).fetchone()
        return dict(row)
    finally:
        conn.close()


@app.get("/api/brain/memories")
def brain_list(category: str | None = None, source: str | None = None,
               status: str = "active", q: str | None = None, stale: bool | None = None):
    backend = _brain_backend()
    return {"items": _brain_call(backend.list_memories, category=category, source=source,
                                  status=status, q=q, stale=stale)}


@app.post("/api/brain/memories")
def brain_create(payload: BrainMemoryCreate):
    backend = _brain_backend()
    mid = _brain_call(backend.add_memory, payload.content, payload.category,
                      payload.confidence, payload.source, status="active")
    return _brain_call(backend.get_memory, mid)


@app.get("/api/brain/memories/{mid}")
def brain_get(mid: int):
    backend = _brain_backend()
    m = _brain_call(backend.get_memory, mid)
    if not m:
        raise HTTPException(status_code=404, detail="Memory not found")
    return m


@app.patch("/api/brain/memories/{mid}")
def brain_patch(mid: int, payload: BrainMemoryPatch):
    backend = _brain_backend()
    m = _brain_call(backend.update_memory, mid, payload.content,
                    payload.category, payload.confidence)
    if not m:
        raise HTTPException(status_code=404, detail="Memory not found")
    return m


@app.delete("/api/brain/memories/{mid}")
def brain_delete(mid: int):
    backend = _brain_backend()
    _brain_call(backend.delete_memory, mid)
    return {"ok": True}


@app.post("/api/brain/memories/{mid}/confirm")
def brain_confirm(mid: int):
    backend = _brain_backend()
    m = _brain_call(backend.confirm_memory, mid)
    if not m:
        raise HTTPException(status_code=404, detail="Memory not found")
    return m


@app.get("/api/brain/memories/{mid}/versions")
def brain_versions(mid: int):
    backend = _brain_backend()
    return {"versions": _brain_call(backend.list_versions, mid)}


@app.post("/api/brain/search")
def brain_search(payload: BrainSearchReq):
    backend = _brain_backend()
    return {"items": _brain_call(backend.semantic_search, payload.query, k=payload.k)}


@app.get("/api/brain/pending")
def brain_pending():
    backend = _brain_backend()
    return {"items": _brain_call(backend.list_pending)}


@app.post("/api/brain/pending/{mid}/accept")
def brain_pending_accept(mid: int):
    backend = _brain_backend()
    return _brain_call(backend.accept_pending, mid) or {"ok": False}


@app.post("/api/brain/pending/{mid}/reject")
def brain_pending_reject(mid: int):
    backend = _brain_backend()
    _brain_call(backend.reject_pending, mid)
    return {"ok": True}


@app.get("/api/brain/conflicts")
def brain_conflicts():
    backend = _brain_backend()
    return {"items": _brain_call(backend.list_conflicts)}


@app.post("/api/brain/conflicts/{cid}/resolve")
def brain_conflict_resolve(cid: int, payload: BrainResolveReq):
    backend = _brain_backend()
    _brain_call(backend.resolve_conflict, cid, payload.decision)
    return {"ok": True}


@app.post("/api/brain/import")
def brain_import(payload: BrainImportReq):
    backend = _brain_backend()
    items = _brain_call(backend.parse_import, payload.filename, payload.content)
    return {"items": items}


@app.post("/api/brain/import/commit")
def brain_import_commit(payload: BrainImportCommitReq):
    backend = _brain_backend()
    return _brain_call(backend.commit_import, payload.filename, payload.source_type, payload.items)


@app.get("/api/brain/duplicates")
def brain_duplicates():
    backend = _brain_backend()
    return {"groups": _brain_call(backend.find_duplicates)}


@app.post("/api/brain/duplicates/merge")
def brain_merge(payload: BrainMergeReq):
    backend = _brain_backend()
    return _brain_call(backend.merge_group, payload.ids, payload.keep_id)


@app.get("/api/brain/narrative")
def brain_narrative_get():
    backend = _brain_backend()
    return _brain_call(backend.get_narrative) or {"content": None}


@app.post("/api/brain/narrative")
def brain_narrative_make():
    backend = _brain_backend()
    n = _brain_call(backend.synthesize_narrative)
    if not n:
        raise HTTPException(status_code=503, detail="Could not synthesize (no memories or LLM unavailable)")
    return n


@app.post("/api/brain/remember")
def brain_remember(payload: BrainRememberReq):
    return brain.remember(payload.content, payload.category)


@app.post("/api/brain/chat")
def brain_chat(payload: BrainChatReq):
    # Routed through the Conductor (queue #7): it reads/answers about live MC state in a
    # butler voice, and degrades to a normal memory-grounded reply for smalltalk. Falls
    # back to the plain Brain chat if the Conductor is unavailable.
    try:
        from core import conductor
        return conductor.conductor_chat(payload.message, surface="mc")
    except Exception:
        return brain.chat(payload.message)


@app.post("/api/brain/chat/stream")
async def brain_chat_stream(payload: BrainChatReq):
    """SSE token stream for the MC chat — Conductor-powered (queue #7). Emits `delta` events as
    the grounded answer reveals, an `action` event when a high-risk act needs confirmation, then
    a final `done`. Falls back to the Brain chat stream if the Conductor is unavailable."""
    message = payload.message

    async def gen():
        loop = asyncio.get_event_loop()
        try:
            from core import conductor
            res = await loop.run_in_executor(None, lambda: conductor.conductor_chat(message, None, "mc"))
            for chunk in conductor._stream_chunks(res.get("reply", "") or ""):
                yield f"event: delta\ndata: {json.dumps({'text': chunk})}\n\n"
            pending = res.get("pending_action")
            if pending:
                yield f"event: action\ndata: {json.dumps(pending)}\n\n"
        except Exception:
            try:
                it = iter(brain.chat_stream(message))
                while True:
                    try:
                        delta = await loop.run_in_executor(None, next, it)
                    except StopIteration:
                        break
                    yield f"event: delta\ndata: {json.dumps({'text': delta})}\n\n"
            except Exception as e:
                yield f"event: error\ndata: {json.dumps({'detail': str(e)[:200]})}\n\n"
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "Connection": "keep-alive",
                                      "X-Accel-Buffering": "no"})


@app.get("/api/brain/chat/history")
def brain_chat_history():
    from core.database import load_conversation_history
    return {"items": load_conversation_history(brain.DASHBOARD_CHAT_ID, limit=50)}


@app.post("/api/brain/sweep")
def brain_sweep():
    return brain.sweep_once()


# ── Premium Chat (#8 P1): multi-model sessions + vault-backed LLM config ─────────
class ChatSessionCreate(BaseModel):
    title: str | None = None
    model: str | None = None


class ChatSessionPatch(BaseModel):
    title: str | None = None
    model: str | None = None


class ChatSendReq(BaseModel):
    message: str
    model: str | None = None
    attachments: list[dict] = Field(default_factory=list)   # {name,mime,kind,text?,data_url?}
    web_research: bool = False
    thinking: bool = False
    connectors: list[str] = Field(default_factory=list)     # enabled connector ids for this turn
    # ── Chat Mode contract (#16) — old clients simply omit these (→ chat mode) ──
    mode: str | None = None                                  # 'chat' | 'agent' (+ legacy labels)
    deep_research: bool = False                              # one-message Deep Research toggle
    review_mode: str | None = None                           # 'ask' | 'session' | 'always'
    client_turn_id: str | None = None                        # runtime trace/idempotency correlation
    resume_run_id: int | None = None                         # continue an existing paused Agent run


class ChatAppendReq(BaseModel):
    role: str = "assistant"
    content: str


class ChatForkReq(BaseModel):
    before_message_id: int


class ChatFeedbackReq(BaseModel):
    value: int | None = None    # 1 👍 | -1 👎 | null clear


class AgentRunCommandReq(BaseModel):
    command: str
    revision: str = ""


def _chat_directives(web_research: bool, thinking: bool, connectors: list[str]) -> str | None:
    """Legacy directive builder — superseded by core.chat_modes.build_directives (#16),
    kept for rollback parity (its chat-mode output is line-identical)."""
    lines = []
    if web_research:
        lines.append("- Web research: use the web_search tool for anything current/factual and cite the sources you use in a ```tobi:reference``` block.")
    if connectors:
        lines.append(f"- Connectors: {', '.join(connectors)} — prefer their tools (e.g. read_notion / read_github) when relevant.")
    if thinking:
        lines.append("- Briefly show your reasoning before the final answer.")
    return "\n".join(lines) or None


class ChatConfigReq(BaseModel):
    mode_v2: Optional[bool] = None
    premium_readers: Optional[bool] = None   # #14 rollback flag (YouTube/reader layer)
    chat_runtime_v2: Optional[str] = None    # off | shadow | on


@app.get("/api/chat/config")
def chat_config_get():
    """Chat feature flags — the frontend picks the v2 Chat/Agent UI vs the legacy five-mode
    UI (#16), plus the #14 premium-reader rollback flag, both from owner_settings."""
    from core import chat_modes, premium_readers, chat_runtime
    return {"mode_v2": chat_modes.mode_v2_enabled(),
            "premium_readers": premium_readers.premium_readers_enabled(),
            "chat_runtime_v2": chat_runtime.runtime_mode()}


@app.post("/api/chat/config")
def chat_config_set(body: ChatConfigReq):
    from core import chat_modes, premium_readers, chat_runtime
    if body.mode_v2 is not None:
        chat_modes.set_mode_v2(body.mode_v2)
    if body.premium_readers is not None:
        premium_readers.set_premium_readers(body.premium_readers)
    if body.chat_runtime_v2 is not None:
        chat_runtime.set_runtime_mode(body.chat_runtime_v2)
    return {"mode_v2": chat_modes.mode_v2_enabled(),
            "premium_readers": premium_readers.premium_readers_enabled(),
            "chat_runtime_v2": chat_runtime.runtime_mode()}


@app.get("/api/chat/sessions")
def chat_sessions_list():
    from core import chat_store
    return {"sessions": chat_store.list_sessions()}


@app.post("/api/chat/sessions")
def chat_session_create(body: ChatSessionCreate):
    from core import chat_store
    return chat_store.create_session(title=body.title, model=body.model)


@app.get("/api/chat/sessions/{sid}")
def chat_session_get(sid: int):
    from core import chat_store
    sess = chat_store.get_session(sid)
    if not sess:
        raise HTTPException(status_code=404, detail="session not found")
    return {"session": sess, "messages": chat_store.get_messages(sid)}


@app.patch("/api/chat/sessions/{sid}")
def chat_session_patch(sid: int, body: ChatSessionPatch):
    from core import chat_store
    sess = chat_store.update_session(sid, title=body.title, model=body.model)
    if not sess:
        raise HTTPException(status_code=404, detail="session not found")
    return sess


@app.delete("/api/chat/sessions/{sid}")
def chat_session_delete(sid: int):
    from core import chat_store
    chat_store.delete_session(sid)
    return {"ok": True}


@app.post("/api/chat/sessions/{sid}/append")
def chat_session_append(sid: int, body: ChatAppendReq):
    """Persist a message the client produced out-of-band (e.g. a confirmed high-risk
    action result) into the session so it survives a reload."""
    from core import chat_store
    if not chat_store.get_session(sid):
        raise HTTPException(status_code=404, detail="session not found")
    mid = chat_store.add_message(sid, body.role, body.content)
    return {"ok": True, "id": mid}


@app.post("/api/chat/sessions/{sid}/stream")
async def chat_session_stream(sid: int, payload: ChatSendReq, request: Request):
    """Premium chat turn over SSE with **typed events**: `thinking` (phase + tool chips),
    `delta` (smoothed answer chunks), `action` (a high-risk act awaiting confirmation),
    `usage` (tokens + latency), then `done`. Conductor-powered, per-session model + history.
    P2: folds in **attachments** (text → context, images → native vision), an opt-in
    **web_search** tool and **connector** emphasis, all gated by the chat's `+` menu."""
    from core import chat_store, conductor, model_router, attachments as attach
    from core import premium_readers, youtube_reader, chat_modes, chat_runtime, context_manager
    from core.chat_runtime_contracts import TurnError, TurnRequest
    from core.task_classifier import classify
    import time as _time

    sess = chat_store.get_session(sid)
    if not sess:
        raise HTTPException(status_code=404, detail="session not found")
    message = (payload.message or "").strip()
    model = (payload.model or sess.get("model") or "").strip() or None
    images, att_text = attach.split(payload.attachments)
    img_urls = attach.image_data_urls(images)
    # ── Mode contract (#16): normalize the raw mode + toggles into a resolved context.
    # Flag off → the new fields are ignored (mode forced to chat) and no mode event is
    # emitted, so behavior is identical to the pre-#16 route [D29].
    mode_v2 = chat_modes.mode_v2_enabled()
    if mode_v2:
        ctx = chat_modes.normalize(payload.mode, payload.web_research, payload.deep_research,
                                   payload.connectors, payload.review_mode)
    else:
        ctx = chat_modes.normalize(None, payload.web_research, False, payload.connectors)
    directives = chat_modes.build_directives(ctx, thinking=payload.thinking)
    extra_tools = chat_modes.extra_tools_for(ctx)
    # Mode capability boundary (#16 [D11][D23]) + Human Review policy — enforced server-side by
    # the Conductor, so the selected mode is a real backend capability, not just prompting.
    denied_tools = chat_modes.denied_tools_for(ctx) if mode_v2 else set()
    review_mode = ctx.get("review_mode") if mode_v2 else None
    runtime_state = chat_runtime.runtime_mode()
    runtime_request = TurnRequest(
        session_id=sid, message=message, mode=ctx["mode"], model=model,
        client_turn_id=(payload.client_turn_id or None), resume_run_id=payload.resume_run_id,
        capabilities=ctx.get("capabilities") or {},
    )
    try:
        runtime_intent = classify(message)
    except Exception:
        runtime_intent = "QUESTION"
    route_decision = chat_runtime.route_turn(runtime_request, runtime_intent)
    runtime_active = runtime_state == "on"
    runtime_allowed = None
    if runtime_active and route_decision.allowed_tools:
        runtime_allowed = set(route_decision.allowed_tools) | set(extra_tools or [])
    # "direct" route no longer starves the tool catalog — leaving runtime_allowed=None
    # means all tools are available, so the LLM can call a read tool even when the
    # classifier didn't predict one.  This was the root cause of "list projects is blocked."

    async def gen():
        loop = asyncio.get_event_loop()
        if not message and not img_urls and not att_text:
            yield "event: done\ndata: {}\n\n"
            return
        recorder = (chat_runtime.TurnRecorder.start(runtime_request, route_decision)
                    if runtime_state in ("shadow", "on") else None)

        def runtime_frame(event_type: str, stage: str, data: Optional[dict] = None) -> str:
            if recorder is None:
                return ""
            envelope = recorder.event(event_type, stage, data or {})
            return f"event: {event_type}\ndata: {json.dumps(envelope)}\n\n"

        if recorder:
            yield runtime_frame("turn_started", "gateway", {
                "route": route_decision.route, "intent": route_decision.intent,
                "confidence": route_decision.confidence, "runtime_mode": runtime_state,
            })
        # Echo the normalized mode as the FIRST frame so the UI can chip it before
        # anything streams (#16). Old clients silently ignore unknown SSE events.
        if mode_v2:
            yield f"event: mode\ndata: {json.dumps({'mode': ctx['mode'], 'legacy_mode': ctx['legacy_mode'], 'capabilities': ctx['capabilities']})}\n\n"
        cid = chat_store.chat_id_for_session(sid)
        from core.database import save_conversation_message as _bridge_msg
        history = await loop.run_in_executor(None, lambda: chat_store.recent_history(sid, limit=8))
        stored_user = message + (f"  📎×{len(payload.attachments)}" if payload.attachments else "")
        await loop.run_in_executor(None, lambda: chat_store.add_message(sid, "user", stored_user, model=model))
        await loop.run_in_executor(None, lambda: _bridge_msg(cid, "user", message))
        await loop.run_in_executor(None, lambda: chat_store.auto_title(sid, message or "Attachment"))
        t0 = _time.time()

        # A clear request to mutate state from Chat mode does not need an LLM round-trip.
        # The clarification gate gives one deterministic, recoverable instruction instead.
        if runtime_active and route_decision.requires_clarification:
            reply = "Switch this conversation to **Agent** mode and send the request again, sir — it requires execution tools."
            for chunk in conductor._stream_chunks(reply):
                yield f"event: delta\ndata: {json.dumps({'text': chunk})}\n\n"
            await loop.run_in_executor(None, lambda: chat_store.add_message(
                sid, "assistant", reply, model=model,
                meta=json.dumps({"mode": ctx["mode"], "turn_id": recorder.turn_id if recorder else None})))
            await loop.run_in_executor(None, lambda: _bridge_msg(cid, "assistant", reply))
            if recorder:
                yield runtime_frame("recovery_required", "clarification", {
                    "code": "turn.agent_mode_required", "actions": ["switch_to_agent"],
                    "message": route_decision.reason,
                })
                recorder.complete("waiting_user", TurnError(
                    "turn.agent_mode_required", "clarification", route_decision.reason, False))
                yield runtime_frame("turn_completed", "gateway", {"status": "waiting_user"})
            yield "event: done\ndata: {}\n\n"
            return

        # ── Premium readers (#14): read YouTube transcripts referenced in the message
        # BEFORE answering, so both the vision and tool-loop paths get the context. A
        # pasted link is treated as consent to fetch [spec]. Honest notice if unavailable.
        reader = premium_readers.ReaderResult()
        if youtube_reader.find_youtube_urls(message):
            yield f"event: thinking\ndata: {json.dumps({'phase': 'Reading the YouTube transcript…', 'tools': ['youtube']})}\n\n"
            try:
                # Bounded so a slow/hanging transcript fetch can't stall the whole turn (#14
                # follow-up). On timeout the fetch is abandoned (its result discarded) and we
                # continue honestly without the transcript. It runs on a DEDICATED bounded pool
                # so repeated hangs can never exhaust the app-wide default executor.
                reader = await asyncio.wait_for(
                    loop.run_in_executor(premium_readers.reader_executor(),
                                         lambda: premium_readers.read_message(message)),
                    timeout=premium_readers.READER_TIMEOUT_S)
            except asyncio.TimeoutError:
                reader = premium_readers.timeout_result(message)
            yield f"event: notice\ndata: {json.dumps(premium_readers.notice_payload(reader))}\n\n"

        # Turn metadata (#16) — persisted onto the assistant message so mode/chips/steps
        # survive a reload. Empty (→ NULL column) when the flag is off.
        turn_meta: dict = ({"mode": ctx["mode"], "legacy_mode": ctx["legacy_mode"],
                            "capabilities": ctx["capabilities"]} if mode_v2 else {})
        if recorder:
            turn_meta["turn_id"] = recorder.turn_id

        # ── Auto project context (#16 [D19][D20]): detect a referenced PM project and
        # inject a read-only summary as evidence; visible to the owner as chips. Skipped
        # for Deep Research turns (web-focused) and when the flag is off. ──
        pctx = {"projects": [], "resources": [], "context_text": ""}
        if mode_v2 and message and not ctx["capabilities"]["deep_research"]:
            pctx = await loop.run_in_executor(None, lambda: chat_modes.detect_project_context(message))
            if pctx["projects"]:
                yield f"event: context\ndata: {json.dumps({'projects': pctx['projects'], 'resources': pctx['resources'], 'auto': True})}\n\n"
                turn_meta["context"] = {"projects": pctx["projects"], "resources": pctx["resources"]}

        manifest = None
        if runtime_state in ("shadow", "on"):
            base_attachment_context = premium_readers.compose_context(att_text, reader)
            manifest = await loop.run_in_executor(None, lambda: context_manager.build_manifest(
                message, ctx["mode"], history, pctx, base_attachment_context))
            if recorder:
                recorder.set_context(manifest.to_dict())
                yield runtime_frame("context_ready", "context", {
                    "total_tokens": manifest.total_tokens,
                    "token_budget": manifest.token_budget,
                    "sources": [{"source": i.source, "label": i.label, "trust": i.trust,
                                 "tokens": i.token_cost} for i in manifest.items],
                })
            # #20 review P1: surface per-memory feedback chips (each carries memory_id,
            # scope, quality) so the owner can rate every recalled memory useful/
            # irrelevant/wrong. They live in the brain_recall item metadata; emit them
            # on the stream and persist onto the turn so they survive a reload.
            _recall = next((i for i in manifest.items if i.source == "brain_recall"), None)
            _mem_chips = list((_recall.metadata or {}).get("chips") or []) if _recall else []
            if _mem_chips:
                yield f"event: memory_chips\ndata: {json.dumps({'chips': _mem_chips})}\n\n"
                turn_meta["memory_chips"] = _mem_chips

        # ── Deep Research (#16 [D14][D15]): one-message cited-report workflow. Beats the
        # vision path (an explicit command wins over an implicit affordance — images are
        # skipped with an honest notice); YouTube/attachment context rides in as evidence. ──
        if mode_v2 and ctx["capabilities"]["deep_research"]:
            from core import deep_research
            if recorder:
                yield runtime_frame("step_started", "deep_research", {"label": "Deep Research"})
            if img_urls:
                yield f"event: notice\ndata: {json.dumps({'kind': 'dr_images_skipped'})}\n\n"
            dr_q: asyncio.Queue = asyncio.Queue()

            def _emit_step(step, phase):
                try:
                    loop.call_soon_threadsafe(dr_q.put_nowait, {"step": step, "phase": phase})
                except Exception:
                    pass

            dr_ctx = premium_readers.compose_context(att_text, reader)
            fut = loop.run_in_executor(None, lambda: deep_research.run(
                message, context_text=dr_ctx, on_step=_emit_step, model=model))
            try:
                while not fut.done() or not dr_q.empty():
                    try:
                        ev = await asyncio.wait_for(dr_q.get(), timeout=0.12)
                    except asyncio.TimeoutError:
                        continue
                    yield f"event: thinking\ndata: {json.dumps({'phase': ev.get('phase', ''), 'tools': ['deep_research']})}\n\n"
                dr = await fut
            except Exception as e:
                if recorder:
                    err = TurnError("research.failed", "deep_research", "Deep Research failed", True, str(e)[:200])
                    yield runtime_frame("step_failed", "deep_research", err.to_dict())
                    recorder.complete("failed", err)
                yield f"event: error\ndata: {json.dumps({'detail': str(e)[:200]})}\n\n"
                yield "event: done\ndata: {}\n\n"
                return
            report = dr.get("report_md") or "I couldn't produce the report, sir."
            for chunk in conductor._stream_chunks(report):
                yield f"event: delta\ndata: {json.dumps({'text': chunk})}\n\n"
            title = f"Research: {message[:80]}"
            aid = await loop.run_in_executor(None, lambda: chat_store.add_artifact(
                sid, "research_report", title, report,
                meta_json=json.dumps({"queries": dr.get("queries") or [],
                                      "source_count": len(dr.get("sources") or []),
                                      "caveats": dr.get("caveats") or []})))
            yield f"event: artifact\ndata: {json.dumps({'id': aid, 'kind': 'research_report', 'title': title})}\n\n"
            turn_meta["artifact_ids"] = [aid]
            ctok = model_router.estimate_tokens(report)
            await loop.run_in_executor(None, lambda: chat_store.add_message(
                sid, "assistant", report, model=model, tokens=ctok, thinking="Deep Research",
                meta=json.dumps(turn_meta) if turn_meta else None))
            await loop.run_in_executor(None, lambda: _bridge_msg(cid, "assistant", report))
            usage = {"prompt_tokens": model_router.estimate_tokens(message + dr_ctx),
                     "completion_tokens": ctok, "model": model or sess.get("model") or "default",
                     "latency_ms": round((_time.time() - t0) * 1000)}
            yield f"event: usage\ndata: {json.dumps(usage)}\n\n"
            if recorder:
                yield runtime_frame("step_completed", "deep_research", {"artifact_id": aid})
                recorder.complete("done")
                yield runtime_frame("turn_completed", "gateway", {"status": "done"})
            yield "event: done\ndata: {}\n\n"
            return

        # ── Vision path: read image attachments with a vision-capable model. If the chat's
        # selected model can't see images, AUTO-BORROW an available vision model (#14) so the
        # owner never has to switch models just to read a screenshot — image reading no longer
        # depends on the chosen model. Only refuses when no vision model is connected at all. ──
        vmodel = model or model_router.load_llm_config().get("default_model") or ""
        vision_model = vmodel if (vmodel and model_router.supports_vision(vmodel)) else None
        borrowed = False
        if img_urls and not vision_model:
            alt = model_router.first_vision_model()
            if alt:
                vision_model, borrowed = alt, True
        if img_urls and vision_model:
            if recorder:
                yield runtime_frame("step_started", "vision", {"model": vision_model})
            yield f"event: thinking\ndata: {json.dumps({'phase': 'Looking at the image…', 'tools': ['vision']})}\n\n"
            try:
                from core import brain as _brain
                profile = await loop.run_in_executor(None, _brain.profile_summary)
            except Exception:
                profile = ""
            system = conductor._system_prompt(profile, False, "mc", directives)
            v_ctx = premium_readers.compose_context(att_text, reader)
            if pctx["context_text"]:
                v_ctx = (v_ctx + "\n\n" if v_ctx else "") + pctx["context_text"]
            vtext = message + (("\n\n" + v_ctx) if v_ctx else "")
            _prev = model_router.set_usage_context("chat", "vision")
            try:
                reply = await loop.run_in_executor(
                    None, lambda: model_router.vision_complete(vision_model, system, vtext, img_urls, history=history))
            except Exception as e:
                reply = f"I couldn't read that image, sir — {str(e)[:160]}"
            finally:
                model_router.set_usage_context(_prev["surface"], _prev["feature"])
            reply = reply or "I couldn't make out the image, sir."
            if borrowed:  # be transparent about which model actually read the image
                short = vision_model.split(":", 1)[-1]
                reply = f"*(Your model can't see images, so I read it with **{short}**.)*\n\n{reply}"
            for chunk in conductor._stream_chunks(reply):
                yield f"event: delta\ndata: {json.dumps({'text': chunk})}\n\n"
            ctok = model_router.estimate_tokens(reply)
            await loop.run_in_executor(None, lambda: chat_store.add_message(
                sid, "assistant", reply, model=vision_model, tokens=ctok, thinking="Looked at image",
                meta=json.dumps(turn_meta) if turn_meta else None))
            await loop.run_in_executor(None, lambda: _bridge_msg(cid, "assistant", reply))
            usage = {"prompt_tokens": model_router.estimate_tokens(vtext), "completion_tokens": ctok,
                     "model": vision_model, "latency_ms": round((_time.time() - t0) * 1000)}
            yield f"event: usage\ndata: {json.dumps(usage)}\n\n"
            if recorder:
                yield runtime_frame("step_completed", "vision", {"model": vision_model})
                recorder.complete("done")
                yield runtime_frame("turn_completed", "gateway", {"status": "done"})
            yield "event: done\ndata: {}\n\n"
            return

        # Fold reader context (YouTube transcript / notices) + an honest image note (only when
        # images are attached AND no vision model is connected anywhere) + auto project
        # context (#16) into the turn context.
        image_note = premium_readers.image_unavailable_note(len(img_urls)) if img_urls else None
        atext = premium_readers.compose_context(att_text, reader, image_note)
        if pctx["context_text"] and not runtime_active:
            atext = (atext + "\n\n" if atext else "") + pctx["context_text"]

        # ── Agent run persistence (#16 [D8]): one durable run per Agent turn, steps recorded
        # incrementally from the event stream so an interrupted SSE leaves last-known state. ──
        run_id = None
        recovery_checkpoint = None
        turn_allowed = set(runtime_allowed) if runtime_allowed is not None else None
        if mode_v2 and ctx["mode"] == "agent":
            from core import agent_runs
            if payload.resume_run_id is not None:
                existing_run = await loop.run_in_executor(None, lambda: agent_runs.get_run(payload.resume_run_id))
                if not existing_run or int(existing_run.get("session_id") or 0) != sid:
                    err = TurnError("run.not_found", "recovery", "The Agent run could not be resumed", False)
                    if recorder:
                        yield runtime_frame("step_failed", "recovery", err.to_dict())
                        recorder.complete("failed", err)
                    yield f"event: error\ndata: {json.dumps({'detail': err.message})}\n\n"
                    yield "event: done\ndata: {}\n\n"
                    return
                run_id = int(payload.resume_run_id)
                await loop.run_in_executor(None, lambda: agent_runs.set_status(run_id, "running"))
                recovery_checkpoint = await loop.run_in_executor(
                    None, lambda: agent_runs.consume_recovery(run_id))
                recovery_tool = (recovery_checkpoint or {}).get("tool")
                if recovery_tool and turn_allowed is not None:
                    turn_allowed.add(recovery_tool)
            else:
                run_id = await loop.run_in_executor(
                    None, lambda: agent_runs.create_run(sid, title=(message or "Agent task")[:120]))
            turn_meta["run_id"] = run_id
            if recorder:
                recorder.bind_run(run_id)

        # ── Standard tool-loop turn — live tool-step + token events via a thread→async queue ──
        yield f"event: thinking\ndata: {json.dumps({'phase': 'Thinking…'})}\n\n"
        q: asyncio.Queue = asyncio.Queue()

        def _emit(ev):
            try:
                loop.call_soon_threadsafe(q.put_nowait, ev)
            except Exception:
                pass

        _prev = model_router.set_usage_context("chat", "")
        fut = loop.run_in_executor(chat_runtime.chat_executor(), lambda: conductor.answer(
            message or "(see attached)", cid, "mc", model=model, history=history,
            attachments_text=atext or None,
            directives=directives, extra_tools=extra_tools,
            denied_tools=denied_tools, review_mode=review_mode,
            mode=ctx["mode"], route=(route_decision.route if runtime_active else None),
            allowed_tools=turn_allowed,
            context_manifest=(manifest if runtime_active else None),
            turn_id=(recorder.turn_id if recorder else None),
            max_tool_steps=(route_decision.max_tool_steps if runtime_active else None),
            step_tokens=(route_decision.step_tokens if runtime_active else None),
            final_tokens=(route_decision.final_tokens if runtime_active else None),
            usage_context={"surface": ctx["mode"], "feature": "chat_runtime_v2"},
            recovery_checkpoint=recovery_checkpoint,
            on_event=_emit, on_delta=lambda t: _emit({"type": "delta", "text": t})))
        seen_tools: list[str] = []
        seen_phases: list[str] = []
        checkpoint_steps: list[str] = []
        term_lines: list[str] = []
        first_delta_recorded = False
        _persisted = False  # guards against double-persist (normal path vs bg task)

        async def _bg_persist():
            """Detached persistence — if the client disconnects mid-stream, wait for
            the LLM to finish and save the reply so it appears when they reopen."""
            nonlocal _persisted
            try:
                bg_res = await fut
                if _persisted:
                    return
                _persisted = True
                bg_reply = bg_res.get("reply", "") or ""
                if not bg_reply.strip():
                    return
                bg_reasoning = bg_res.get("reasoning") or None
                bg_tools = bg_res.get("tools_used") or []
                bg_thinking = bg_reasoning or (("Consulted: " + ", ".join(bg_tools)) if bg_tools else None)
                bg_ctok = model_router.estimate_tokens(bg_reply)
                await loop.run_in_executor(
                    None, lambda: chat_store.add_message(sid, "assistant", bg_reply, model=model,
                                                         tokens=bg_ctok, thinking=bg_thinking))
                await loop.run_in_executor(None, lambda: _bridge_msg(cid, "assistant", bg_reply))
            except Exception:
                pass

        def _record_step(step_type, title, **kw):
            if run_id is None:
                return None
            from core import agent_runs
            return loop.run_in_executor(None, lambda: agent_runs.add_step(run_id, step_type, title, **kw))

        try:
            while not fut.done() or not q.empty():
                # Client disconnect check — spawn bg persistence and stop yielding
                if await request.is_disconnected():
                    if not fut.done() and not _persisted:
                        asyncio.ensure_future(_bg_persist())
                    return
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=0.12)
                except asyncio.TimeoutError:
                    continue
                if ev.get("type") == "delta":
                    if recorder and not first_delta_recorded:
                        recorder.event("delta", "response", {"chars": len(ev.get("text", ""))})
                        first_delta_recorded = True
                    yield f"event: delta\ndata: {json.dumps({'text': ev.get('text', '')})}\n\n"
                elif ev.get("type") == "terminal":
                    # live stdout from a run_command execution (#11) → xterm-style console
                    term_lines.append(ev.get("line", ""))
                    yield f"event: terminal\ndata: {json.dumps({'line': ev.get('line', '')})}\n\n"
                elif ev.get("type") == "reset":
                    yield "event: reset\ndata: {}\n\n"
                elif ev.get("type") == "model_escalated":
                    notice = {"kind": "model_escalated", "from_model": ev.get("from_model"),
                              "to_model": ev.get("to_model"), "reason": ev.get("reason")}
                    yield f"event: notice\ndata: {json.dumps(notice)}\n\n"
                    if recorder:
                        yield runtime_frame("model_escalated", "model", notice)
                elif ev.get("type") == "plan":
                    # agent-mode declared plan (#16 D9) → structured timeline event
                    plan_steps = [str(s).strip() for s in (ev.get("steps") or []) if str(s).strip()]
                    yield f"event: plan\ndata: {json.dumps({'steps': plan_steps, 'title': ev.get('title', '')})}\n\n"
                    checkpoint_steps.append(
                        f"Planned {len(plan_steps)} step{'s' if len(plan_steps) != 1 else ''}")
                    checkpoint_steps.extend(
                        f"{index}. {step}" for index, step in enumerate(plan_steps[:12], 1))
                    if recorder:
                        yield runtime_frame("plan_ready", "planning", {
                            "steps": plan_steps, "title": ev.get("title", "")})
                    step = _record_step("plan", ev.get("title") or "Plan",
                                        payload={"steps": plan_steps})
                    if step is not None:
                        await step
                elif ev.get("type") == "thinking":
                    tool_name = ev.get("tool")
                    phase = str(ev.get("phase") or "").strip()
                    if tool_name:
                        if tool_name not in seen_tools:
                            seen_tools.append(tool_name)
                        if tool_name != "outline_plan":   # the plan event records itself
                            step = _record_step("tool", phase, tool=tool_name)
                            if step is not None:
                                await step
                    if phase:
                        seen_phases.append(phase)
                        checkpoint_steps.append(phase)
                        if recorder:
                            yield runtime_frame("step_started", "execution", {
                                "label": phase, "tool": tool_name})
                    yield f"event: thinking\ndata: {json.dumps({'phase': ev.get('phase', ''), 'tools': seen_tools})}\n\n"
            res = await fut
        except Exception as e:
            err = TurnError("turn.internal", "execution", "The turn failed unexpectedly", True, str(e)[:200])
            if run_id is not None:
                from core import agent_runs
                await loop.run_in_executor(None, lambda: agent_runs.complete_run(run_id, "failed", error=str(e)[:300]))
            if recorder:
                yield runtime_frame("step_failed", "execution", err.to_dict())
                recorder.complete("failed", err)
            yield f"event: error\ndata: {json.dumps({'detail': str(e)[:200]})}\n\n"
            yield "event: done\ndata: {}\n\n"
            return
        finally:
            model_router.set_usage_context(_prev["surface"], _prev["feature"])
        reply = res.get("reply", "") or ""
        reasoning = res.get("reasoning") or None
        tools = list(dict.fromkeys([*seen_tools, *(res.get("tools_used") or [])]))
        # The streamed answer already reached the client via on_delta; only special replies
        # (proposals, failures, model-issue notices) still need to be sent here.
        if not res.get("streamed"):
            if recorder and reply and not first_delta_recorded:
                recorder.event("delta", "response", {"chars": min(len(reply), 32)})
                first_delta_recorded = True
            for chunk in conductor._stream_chunks(reply):
                yield f"event: delta\ndata: {json.dumps({'text': chunk})}\n\n"
        if res.get("model_issue"):
            yield f"event: notice\ndata: {json.dumps({'kind': 'model_issue'})}\n\n"
            if recorder:
                yield runtime_frame("recovery_required", "model", {
                    "run_id": run_id, "code": "model.malformed_output",
                    "actions": ["retry_step", "revise", "cancel"],
                })
        # A chain stopped on a failed step → the run is paused awaiting the owner's call
        # (Retry / Skip / Revise quick actions in the UI) [D10].
        if res.get("stopped_on_error"):
            yield f"event: notice\ndata: {json.dumps({'kind': 'run_paused', 'run_id': run_id})}\n\n"
            if recorder:
                yield runtime_frame("recovery_required", "execution", {
                    "run_id": run_id, "actions": ["resume", "retry_step", "skip_step", "revise", "cancel"],
                    "code": "tool.execution",
                })
            if run_id is not None and res.get("failed_step"):
                failed_step = res["failed_step"]
                await loop.run_in_executor(None, lambda: agent_runs.add_step(
                    run_id, "tool", f"Failed: {failed_step.get('tool') or 'tool'}",
                    tool=failed_step.get("tool"), risk=failed_step.get("risk"),
                    payload=failed_step, summary=str(failed_step.get("error") or "")[:1000],
                    status="failed"))
        thinking_meta = reasoning or (("Consulted: " + ", ".join(tools)) if tools else None)
        if mode_v2 and (checkpoint_steps or tools):
            turn_meta["steps"] = checkpoint_steps
            turn_meta["tools"] = tools
        # Task-result artifact (#16 [D21]) — only when the agent run actually ACTED
        # (≥1 act/terminal tool), so read-only turns don't spam artifacts.
        if run_id is not None and not res.get("stopped_on_error") and not res.get("pending_action"):
            acted = [t for t in tools if t in conductor.ACT_TOOLS]
            if acted:
                a_title = (message or "Agent task")[:80]
                a_content = (f"## Task result\n\n{reply}\n\n"
                             f"**Actions:** {', '.join(acted)}\n"
                             f"**Steps:** {len(seen_phases)} · **Tools:** {', '.join(tools)}")
                aid = await loop.run_in_executor(None, lambda: chat_store.add_artifact(
                    sid, "task_result", a_title, a_content, run_id=run_id,
                    meta_json=json.dumps({"tools": tools, "acted": acted})))
                yield f"event: artifact\ndata: {json.dumps({'id': aid, 'kind': 'task_result', 'title': a_title})}\n\n"
                turn_meta.setdefault("artifact_ids", []).append(aid)
        ctok = model_router.estimate_tokens(reply)
        ptok = model_router.estimate_tokens(message + (atext or "") + " ".join(m.get("content", "") for m in history))
        turn_meta["elapsedMs"] = round((_time.time() - t0) * 1000)
        _persisted = True  # normal path handles persistence; bg task (if any) will skip
        mid = await loop.run_in_executor(
            None, lambda: chat_store.add_message(sid, "assistant", reply, model=model,
                                                 tokens=ctok, thinking=thinking_meta,
                                                 meta=json.dumps(turn_meta) if turn_meta else None))
        await loop.run_in_executor(None, lambda: _bridge_msg(cid, "assistant", reply))
        pending = res.get("pending_action")
        if run_id is not None and pending:
            action_ids = [i.get("id") for i in (pending.get("items") or [pending]) if i.get("id")]
            await loop.run_in_executor(None, lambda: agent_runs.link_actions(run_id, action_ids))
        if recovery_checkpoint and recovery_checkpoint.get("recovery_step_id") and not pending:
            recovery_status = "failed" if res.get("stopped_on_error") else "done"
            await loop.run_in_executor(None, lambda: agent_runs.finish_recovery(
                int(recovery_checkpoint["recovery_step_id"]), recovery_status,
                "checkpoint failed again" if recovery_status == "failed" else "checkpoint applied"))
        # Close out the agent run with an honest status [D8][D10].
        if run_id is not None:
            from core import agent_runs
            if term_lines:
                tail = "\n".join(term_lines[-30:])
                await loop.run_in_executor(None, lambda: agent_runs.add_step(
                    run_id, "terminal", "Terminal output", payload={"tail": tail[-3000:]}))
            run_status = ("waiting_user" if res.get("stopped_on_error")
                          else "waiting_approval" if pending
                          else "failed" if res.get("model_issue") else "done")
            await loop.run_in_executor(None, lambda: agent_runs.complete_run(
                run_id, run_status, message_id=mid))
        if pending:
            yield f"event: action\ndata: {json.dumps(pending)}\n\n"
        picker = res.get("pending_picker")
        if picker:
            yield f"event: picker\ndata: {json.dumps(picker)}\n\n"
        usage = {"prompt_tokens": ptok, "completion_tokens": ctok,
                 "model": model or sess.get("model") or "default",
                 "latency_ms": round((_time.time() - t0) * 1000)}
        yield f"event: usage\ndata: {json.dumps(usage)}\n\n"
        if recorder:
            final_status = ("waiting_user" if res.get("stopped_on_error")
                            else "waiting_approval" if pending
                            else "failed" if res.get("model_issue") else "done")
            yield runtime_frame("step_completed", "response", {
                "tools": tools, "model": usage["model"], "latency_ms": usage["latency_ms"]})
            recorder.complete(final_status)
            yield runtime_frame("turn_completed", "gateway", {"status": final_status, "run_id": run_id})
        # Trigger brain auto-learning sweep (non-blocking — runs in background thread)
        loop.run_in_executor(None, lambda: brain.sweep_once())
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "Connection": "keep-alive",
                                      "X-Accel-Buffering": "no"})


@app.post("/api/chat/sessions/{sid}/fork")
def chat_session_fork(sid: int, body: ChatForkReq):
    """Edit→branch: clone the session up to a message into a NEW session (original preserved)."""
    from core import chat_store
    new = chat_store.fork_session(sid, body.before_message_id)
    if not new:
        raise HTTPException(status_code=404, detail="session not found")
    return new


@app.post("/api/chat/messages/{mid}/feedback")
def chat_message_feedback(mid: int, body: ChatFeedbackReq):
    from core import chat_store
    chat_store.set_feedback(mid, body.value)
    return {"ok": True, "id": mid, "feedback": body.value}


@app.get("/api/chat/sessions/{sid}/activity")
def chat_session_activity(sid: int, limit: int = 50):
    """The system action log for this session — TOBI Actions (#7) scoped to the session's chat_id."""
    from core import chat_store, conductor
    cid = chat_store.chat_id_for_session(sid)
    return conductor.list_actions(limit=max(1, min(limit, 200)), chat_id=cid)


# ── Agent runs + artifacts (#16) ─────────────────────────────────────────────────
@app.get("/api/chat/sessions/{sid}/runs")
def chat_session_runs(sid: int, limit: int = 20):
    from core import agent_runs
    return {"runs": agent_runs.list_runs(sid, limit=max(1, min(limit, 100)))}


@app.get("/api/chat/runs/{run_id}")
def chat_run_detail(run_id: int):
    from core import agent_runs
    run = agent_runs.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="run not found")
    return run


@app.post("/api/chat/runs/{run_id}/commands")
def chat_run_command(run_id: int, body: AgentRunCommandReq):
    from core import agent_runs
    try:
        result = agent_runs.command_run(run_id, body.command, body.revision)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not result:
        raise HTTPException(status_code=404, detail="run not found")
    return result


@app.get("/api/chat/turns/{turn_id}/trace")
def chat_turn_trace(turn_id: str):
    from core import chat_runtime
    trace = chat_runtime.get_trace(turn_id)
    if not trace:
        raise HTTPException(status_code=404, detail="turn not found")
    return trace


@app.get("/api/chat/sessions/{sid}/artifacts")
def chat_session_artifacts(sid: int, limit: int = 50):
    from core import chat_store
    return {"artifacts": chat_store.list_artifacts(sid, limit=max(1, min(limit, 200)))}


@app.get("/api/chat/artifacts/{artifact_id}")
def chat_artifact_detail(artifact_id: int):
    from core import chat_store
    art = chat_store.get_artifact(artifact_id)
    if not art:
        raise HTTPException(status_code=404, detail="artifact not found")
    return art


class ChatCompactReq(BaseModel):
    model: str | None = None
    keep: int = 6


@app.post("/api/chat/sessions/{sid}/compact")
def chat_session_compact(sid: int, body: ChatCompactReq):
    """Compact (P3): summarize the older turns (keep the most recent `keep` verbatim),
    store the summary, and return the trimmed message list — the context bar drops."""
    from core import chat_store, model_router
    sess = chat_store.get_session(sid)
    if not sess:
        raise HTTPException(status_code=404, detail="session not found")
    keep = max(2, min(int(body.keep or 6), 20))
    transcript = chat_store.older_messages_text(sid, keep=keep)
    if not transcript:
        return {"compacted": False, "messages": chat_store.get_messages(sid),
                "detail": "Nothing old enough to compact yet."}
    model = (body.model or sess.get("model") or "").strip() or None
    prompt = ("Summarize this earlier part of a conversation between the Owner and TOBI into tight bullet "
              "points that preserve names, numbers, decisions, and open threads, so the assistant can keep "
              "context. Be concise.\n\n" + transcript)
    try:
        client = model_router.get_llm("simple", model=model) if model else model_router.get_llm("simple")
        summary = client.complete([{"role": "user", "content": prompt}], max_tokens=500) or ""
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Could not summarize: {str(e)[:160]}")
    msgs = chat_store.compact_session(sid, summary, keep=keep)
    if msgs is None:
        return {"compacted": False, "messages": chat_store.get_messages(sid)}
    return {"compacted": True, "messages": msgs, "summary": summary}


@app.get("/api/llm/usage")
def llm_usage(days: int = 7):
    """Weekly token/cost/latency analytics from real per-call logging (Models page + Health)."""
    from core import usage
    return usage.summary(days=max(1, min(days, 90)))


@app.get("/api/llm/usage/recent")
def llm_usage_recent(limit: int = 50):
    from core import usage
    return {"calls": usage.recent(limit=limit)}


class LlmConfigReq(BaseModel):
    config: dict


class LlmKeyReq(BaseModel):
    value: str


@app.get("/api/llm/config")
def llm_config_get():
    """Routing config + provider catalog (key-presence, base_urls, models) + the flat
    'provider:model' picker list. Non-secret — no vault session required to read."""
    from core import model_router
    return {
        "config": model_router.load_llm_config(),
        "providers": model_router.provider_catalog(),
        "models": model_router.available_models(),
    }


@app.get("/api/llm/models")
def llm_models():
    from core import model_router
    return {"models": model_router.available_models()}


@app.post("/api/llm/config")
def llm_config_save(body: LlmConfigReq):
    """Save routing prefs (default + per-task + fallback + provider base_urls/models) and
    **push to Hermes** (best-effort, never fails the save)."""
    from core import model_router, hermes_sync
    cfg = model_router.save_llm_config(body.config or {})
    try:
        hermes = hermes_sync.push_config(cfg)
    except Exception as e:  # never let a Hermes hiccup break the save
        hermes = {"ok": False, "detail": f"Hermes push skipped: {str(e)[:120]}"}
    return {"config": cfg, "providers": model_router.provider_catalog(),
            "models": model_router.available_models(), "hermes": hermes}


@app.post("/api/llm/provider/{pid}/key")
def llm_provider_key(pid: str, body: LlmKeyReq,
                     x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    """Store a provider's API key in the Genesis vault (encrypted) and inject it live.
    Routed through the key-slot system so it appears in the multi-key list too."""
    _vault_guard(x_vault_session)
    from core import model_router
    spec = model_router.PROVIDERS.get(pid)
    if not spec or not spec.get("key_env"):
        raise HTTPException(status_code=400, detail="provider has no API key")
    conn = _get_conn()
    try:
        vault.add_key_slot(conn, spec["key_env"], body.value, activate=True)
    finally:
        conn.close()
    return {"ok": True, "providers": model_router.provider_catalog(),
            "models": model_router.available_models()}


@app.post("/api/llm/discover/{pid}")
def llm_discover(pid: str):
    from core import model_router
    if pid not in model_router.PROVIDERS:
        raise HTTPException(status_code=404, detail="unknown provider")
    return model_router.discover_models(pid)


@app.post("/api/llm/hermes-push")
def llm_hermes_push():
    from core import hermes_sync, model_router
    return hermes_sync.push_config(model_router.load_llm_config())


# ── Serve React static files (MUST be last — catch-all shadows all routes above) ──
_NO_CACHE_HEADERS = {"Cache-Control": "no-cache, must-revalidate", "Pragma": "no-cache"}

if DIST_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(DIST_DIR / "assets")), name="assets")

    @app.get("/")
    async def root():
        return FileResponse(str(DIST_DIR / "index.html"), headers=_NO_CACHE_HEADERS)

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        file_path = DIST_DIR / full_path
        if file_path.is_file():
            return FileResponse(str(file_path))
        return FileResponse(str(DIST_DIR / "index.html"), headers=_NO_CACHE_HEADERS)

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

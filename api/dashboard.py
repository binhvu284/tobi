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



# Shared API primitives (refactor Slice 0 — see docs/REFACTORING_PLAN.md).
# DB_PATH / _get_conn / _json_loads / fmt_ago now live in api/deps.py so route
# groups extracted into api/routers/* can share them. Imported back into this
# module's namespace to preserve every existing reference (including external
# access such as core.conductor's `dashboard._get_conn`).
from api.deps import (DB_PATH, _append_activity, _count, _fetch_activity, _fetch_checklist,
                      _fetch_task_row, _get_conn, _json_loads, _last, _legacy_status_from_v1,
                      _serialize_task, _task_deps, _vault_guard, fmt_ago)
# Ability/tier detection moved to core/awakening_detect.py (removes the core->api
# backdep); imported back so every existing reference here keeps working unchanged.
from core.awakening_detect import _ABILITY_NAMES, _TIER_DEFINITIONS, _detect_abilities

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
from api.routers.llm import router as llm_router
app.include_router(llm_router)
from api.routers.mcp import router as mcp_router
app.include_router(mcp_router)
from api.routers.brain import router as brain_router
app.include_router(brain_router)
from api.routers.tasks import router as tasks_router
app.include_router(tasks_router)
from api.routers.pm import router as pm_router
app.include_router(pm_router)
from api.routers.genesis import router as genesis_router
app.include_router(genesis_router)

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




# ── Evolution / Tier progression system ─────────────────────────────────────

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

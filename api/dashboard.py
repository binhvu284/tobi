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
# The integration/OAuth handlers moved into routers/genesis.py during the Phase 1 split,
# but callers outside the app reach them as attributes of this module (tests import the
# handler directly to exercise it without a live HTTP client). Re-exported so the split
# stays a pure relocation — see tests/test_awakening_route.py.
from api.routers.genesis import (  # noqa: F401
    IntegrationConnectReq, connect_integration, google_oauth_callback,
    test_integration_endpoint,
)
from api.routers.abilities import router as abilities_router
app.include_router(abilities_router)
from api.routers.evolution import router as evolution_router
app.include_router(evolution_router)
from api.routers.chat import router as chat_router
app.include_router(chat_router)

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

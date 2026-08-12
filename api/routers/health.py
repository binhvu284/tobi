"""Health & performance routes — /api/health/* .

Extracted from api/dashboard.py (refactor Slice 1). Byte-identical handlers;
only @app.* decorators became @router.* and the shared helpers now import
from api.deps. See docs/REFACTORING_PLAN.md.
"""
from __future__ import annotations

import asyncio
import os
import re
import sqlite3
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.deps import _get_conn, _last, fmt_ago, LOGS_DIR
from core.database import get_dashboard

router = APIRouter(tags=["health"])

API_PORT = os.getenv("API_PORT", "8000")

# Log-tail diagnostics — moved verbatim from api/dashboard.py; used only by the
# Health deep check. Matches main.py's "[ERROR]" format and the default
# "ERROR:logger:" library format, plus tracebacks. Word-boundaried so it won't
# fire on the word "error" mid-sentence.
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


@router.get("/api/health")
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

    # This probe used to run `requests.get(...)` inline. `requests` is synchronous, so inside an
    # async handler it held the event loop for its whole duration -- opening the Health page
    # paused every other request in flight, not just this one. With the port closed it measured
    # 4,076ms against 8-30ms for every other endpoint the pages poll, because `timeout=2` is two
    # seconds to connect *and* two to read. Run it on a worker thread, capped once, overall.
    api_ok = False
    _API_PROBE_TIMEOUT = 1.0

    def _probe_api() -> tuple[bool, str]:
        import requests
        # 127.0.0.1, not "localhost": the name resolves to both ::1 and 127.0.0.1, so a closed
        # port costs *two* connect attempts, one per address family. Measured 714ms against a
        # 350ms connect budget until this was pinned to a single address.
        #
        # Separate connect and read budgets. The server is on this machine, so a healthy
        # connect is effectively instant; a closed port is what spends the connect budget, and
        # that is the case worth keeping short.
        r = requests.get(f"http://127.0.0.1:{API_PORT}/health", timeout=(0.35, 0.6))
        return r.status_code == 200, f"port {API_PORT} /health → {r.status_code}"

    try:
        api_ok, api_detail = await asyncio.wait_for(
            asyncio.to_thread(_probe_api), timeout=_API_PROBE_TIMEOUT)
        up["api_server"] = {"ok": api_ok, "detail": api_detail}
    except asyncio.TimeoutError:
        up["api_server"] = {"ok": False,
                            "detail": f"port {API_PORT} did not answer within {_API_PROBE_TIMEOUT:g}s"}
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
        "revision": __import__("core.build_info", fromlist=["revision"]).revision(),
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


@router.get("/api/health/deep")
async def api_health_deep():
    """On-demand LIVE check of EVERY external API Tobi uses (button-triggered, not on
    load): a real LLM round-trip + live network tests to Telegram, Tavily, and each
    integration. Each result carries latency; a summary gives reachable/total."""
    result: dict = {"timestamp": datetime.now().isoformat()}

    # 1) Chat round-trip — a real short conversation that uses a tool, not a one-shot ping.
    # The old probe asked the model "Reply with exactly: OK" and passed. On 2026-08-01 it
    # passed all day while every Chat request failed, because the defect only existed on the
    # second message of a conversation and a one-shot probe never sends one. See
    # core/chat_self_check.py for the full account.
    from core.chat_self_check import run_self_check
    check = run_self_check()
    result["llm"] = {
        "ok": check["ok"],
        "detail": check["detail"][:400],
        "latency_ms": check["latency_ms"],
        "state": check["state"],              # working | broken | model_unavailable
        "tools_used": check["tools_used"],
        "model_turns": check["model_turns"],
        "provider": os.getenv("PRIMARY_MODEL", "openrouter"),
    }

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


# ── Performance "system doctor" (#19) ────────────────────────────────────────────
class PerfRunReq(BaseModel):
    depth: str = "quick"     # 'quick' (graph + metrics) | 'deep' (adds LLM diagnosis)


class PerfTaskReq(BaseModel):
    title: str
    detail: str = ""
    subsystem: str = ""
    severity: str = ""
    project_id: Optional[int] = None   # omit → find-or-create a "TOBI Maintenance" project


@router.get("/api/health/performance")
def api_performance_latest():
    """The most recent Performance analysis (scorecard + subsystems + findings + trend), or
    {available:false} if none has been run yet. Read-only — never triggers a new run."""
    from core import performance_doctor as pdoc
    r = pdoc.latest()
    return r if r else {"available": False}


@router.post("/api/health/performance/run")
async def api_performance_run(body: PerfRunReq):
    """Run a fresh Performance analysis (button-triggered, not on load). 'quick' is graphify +
    metrics (~free); 'deep' adds one strict-budget LLM diagnosis. Runs off the event loop."""
    from core import performance_doctor as pdoc
    depth = "deep" if (body.depth or "").lower() == "deep" else "quick"
    return await asyncio.get_event_loop().run_in_executor(None, lambda: pdoc.analyze(depth))


@router.post("/api/health/performance/finding/task")
def api_performance_finding_task(body: PerfTaskReq):
    """Turn a finding into a PM task [D11] (reuses #7 create_task). Files it into the given
    project, or a find-or-create 'TOBI Maintenance' project."""
    from core import conductor
    pid = body.project_id
    if not pid:
        projs = (conductor.tool_list_projects() or {}).get("projects") or []
        match = next((p for p in projs if str(p.get("name", "")).strip().lower() == "tobi maintenance"), None)
        if match:
            pid = match.get("id")
        else:
            created = conductor.tool_create_project(
                name="TOBI Maintenance", description="Refactors and fixes from the Performance doctor.",
                category="engineering")
            pid = created.get("id") or created.get("project_id")
    if not pid:
        raise HTTPException(status_code=500, detail="could not resolve a project for the task")
    desc = body.detail
    if body.subsystem or body.severity:
        desc = f"[{body.subsystem or 'system'} · {body.severity or 'finding'}] {desc}".strip()
    res = conductor.tool_create_task(project_id=int(pid), title=body.title[:200], description=desc)
    if isinstance(res, dict) and res.get("error"):
        raise HTTPException(status_code=400, detail=res["error"])
    return {"ok": True, "project_id": int(pid), "task": res}

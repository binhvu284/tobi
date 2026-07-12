"""
TOBI Conductor — one shared conversational engine over Mission Control (queue #7).

P1 (this file, v1): the Conductor *reads & answers about* every MC feature by talking
to the owner — grounded strictly in live data via a read-tool catalog, with a butler
"sir" voice and language mirroring. Shared by both surfaces (MC chat + Telegram) so the
two front doors run one brain.

Design (locked by the spec's 30 Q&A):
  - **Hybrid routing:** a cheap regex classifier pre-routes; smalltalk/coding answer
    directly (fast, no tools), anything about MC state enters the tool-loop.
  - **Provider-agnostic tool-loop:** the model emits a one-line JSON `{"tool","args"}`
    when it needs live data; we execute the tool, feed the result back, and repeat until
    it gives a final answer. Works over the plain `complete()` string interface, so it
    runs on OpenRouter *and* Claude (no native-tool-use lock-in).
  - **Strict grounding:** every number/status must come from a tool result. The system
    prompt forbids invention; missing data → "I don't have that yet, sir" + offer to fetch.

Read tools are thin wrappers over existing DB ops / dashboard helpers (low risk). Act
tools, confirmation gating, the TOBI Actions audit and external chains are P2/P3.
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Callable, Optional

logger = logging.getLogger("tobi.conductor")

MAX_TOOL_STEPS = 8  # enough for a chain: read → create project → tasks → assign → answer
_LLM_DOWN = "I can't reach my language model right now, sir — do check the LLM API key in Integrations."


def _failure_report(done: list[str], failed_summary: str, error: str) -> str:
    """Stop-on-failure report for a partly-completed multi-step chain (P3)."""
    parts = ["I hit a snag mid-way, sir, so I stopped to keep things clean."]
    if done:
        parts.append("Completed so far: " + "; ".join(done) + ".")
    parts.append(f"Failed at: {failed_summary} — {error}.")
    parts.append("Shall I retry that step, or adjust the plan?")
    return " ".join(parts)


# ════════════════════════════════════════════════════════════════════════════
# Read-tool catalog  (each returns a compact, JSON-serializable dict of LIVE data)
# ════════════════════════════════════════════════════════════════════════════
def _conn():
    from core.database import get_connection
    return get_connection()


def tool_get_evolution(**_: Any) -> dict:
    """Current evolution tier, completion %, and ability counts — live."""
    from api import dashboard as D
    conn = D._get_conn()
    try:
        statuses = D._detect_abilities(conn)
        prev = D._load_evo_snapshot(conn)
        tiers, _ = D._build_evo_response(statuses, prev)
    finally:
        conn.close()
    total = sum(t["total_count"] for t in tiers)
    active = sum(t["active_count"] for t in tiers)
    overall = round(active / total * 100) if total else 0
    cur_id = next((t["id"] for t in tiers if not t["complete"]), tiers[-1]["id"])
    ct = tiers[cur_id]
    return {
        "current_tier_id": cur_id,
        "current_tier_name": ct.get("name"),
        "current_tier_pct": ct.get("progress_pct"),
        "current_tier_active_abilities": ct.get("active_count"),
        "current_tier_total_abilities": ct.get("total_count"),
        "overall_jarvis_pct": overall,
        "total_active_abilities": active,
        "total_abilities": total,
    }


_ARCHITECTURE = {
    "summary": "TOBI is a personal-Jarvis agent: a Python service that runs Mission Control "
               "and a Telegram bot over one shared brain.",
    "layers": [
        {"layer": "Host / runtime", "detail": "Python 3 process on a Windows dev box (local migration) or VPS; "
         "main.py is the orchestrator + scheduler (run modes: start/bot/api/research/execute/ceo)."},
        {"layer": "API", "detail": "FastAPI in api/dashboard.py serves the Mission Control dashboard and every "
         "/api/* endpoint, plus the mounted MCP server."},
        {"layer": "Engines (core/)", "detail": "model_router, task_classifier, research, executor, CEO loop, "
         "brain (the second brain), graph_engine, and this conductor."},
        {"layer": "Data", "detail": "SQLite (core/database.py): projects, tasks, agents, missions, lessons, "
         "conversations, brain_memories, and the encrypted vault."},
        {"layer": "Interfaces", "detail": "The React Mission Control chat and the Telegram bot — both front doors "
         "onto the Conductor."},
        {"layer": "Integrations", "detail": "The Genesis vault holds encrypted credentials for Notion, GitHub, "
         "Vercel, Supabase, Telegram, the LLM providers, and Tavily."},
    ],
}


def tool_explain_architecture(**_: Any) -> dict:
    """TOBI's real system architecture, layer by layer."""
    return _ARCHITECTURE


def tool_office_status(**_: Any) -> dict:
    """Agents in the office: count, each one's role and working/free status, missions running."""
    conn = _conn()
    try:
        agents = conn.execute(
            "SELECT id, name, role FROM agents WHERE status='active' ORDER BY is_head DESC, name"
        ).fetchall()
        states = {r["agent_id"]: dict(r) for r in conn.execute("SELECT * FROM agent_state").fetchall()}
        try:
            missions_running = conn.execute("SELECT COUNT(*) FROM missions WHERE status='running'").fetchone()[0]
        except Exception:
            missions_running = 0
    finally:
        conn.close()
    out = []
    for a in agents:
        st = states.get(a["id"], {})
        rs = (st.get("runtime_status") or "idle")
        out.append({
            "name": a["name"], "role": a["role"], "runtime_status": rs,
            "working": rs == "working", "detail": st.get("detail"),
        })
    working = [a for a in out if a["working"]]
    return {
        "agent_count": len(out),
        "working_count": len(working),
        "free_count": len(out) - len(working),
        "missions_running": missions_running,
        "agents": out,
    }


def tool_list_projects(status: Optional[str] = None, **_: Any) -> dict:
    """Projects from the PM board the owner actually sees (pm_projects). Returns the id so
    follow-up tools (create_task, update progress) can target the right project."""
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT id, name, status, category, progress_pct FROM pm_projects ORDER BY updated_at DESC"
        ).fetchall()
    finally:
        conn.close()
    items = []
    for r in rows:
        d = dict(r)
        if status and d.get("status") != status:
            continue
        items.append({"id": d["id"], "name": d["name"], "status": d["status"],
                      "category": d.get("category"), "progress_pct": d.get("progress_pct")})
    return {"count": len(items), "projects": items[:30]}


def tool_list_tasks(status: Optional[str] = None, limit: int = 15, **_: Any) -> dict:
    """Recent tasks with status / priority."""
    try:
        limit = max(1, min(int(limit), 40))
    except Exception:
        limit = 15
    conn = _conn()
    try:
        try:
            rows = conn.execute(
                "SELECT id, title, COALESCE(status_v1, status) AS status, priority_label AS priority, "
                "pm_project_id FROM tasks WHERE deleted_at IS NULL ORDER BY created_at DESC LIMIT ?", (limit * 3,)
            ).fetchall()
        except Exception:
            rows = conn.execute("SELECT id, title, status FROM tasks ORDER BY id DESC LIMIT ?", (limit * 3,)).fetchall()
    finally:
        conn.close()
    items = []
    for r in rows:
        d = dict(r)
        if status and d.get("status") != status:
            continue
        items.append(d)
        if len(items) >= limit:
            break
    return {"count": len(items), "tasks": items}


def tool_project_overview(project: str = "", **_: Any) -> dict:
    """Full metric snapshot of one project so answers are grounded in real numbers (#12)."""
    key = str(project or "").strip()
    if not key:
        return {"error": "which project? give a name or id"}
    conn = _conn()
    try:
        if key.isdigit():
            row = conn.execute("SELECT * FROM pm_projects WHERE id=?", (int(key),)).fetchone()
        else:
            row = conn.execute("SELECT * FROM pm_projects WHERE name LIKE ? ORDER BY updated_at DESC LIMIT 1",
                               (f"%{key}%",)).fetchone()
        if not row:
            return {"error": f"no project matching '{project}'"}
        pid = row["id"]
        tasks = conn.execute(
            "SELECT status_v1, due_at FROM tasks WHERE pm_project_id=? AND deleted_at IS NULL", (pid,)).fetchall()
        total = len(tasks)
        done = sum(1 for t in tasks if t["status_v1"] == "done")
        active = sum(1 for t in tasks if t["status_v1"] in
                     {"in_progress", "planned", "paused", "blocked", "needs_owner_input"})
        from datetime import datetime as _dt, timezone as _tz
        now = _dt.now(_tz.utc)
        overdue = 0
        for t in tasks:
            if t["due_at"] and t["status_v1"] not in {"done", "cancelled"}:
                try:
                    if _dt.fromisoformat(t["due_at"].replace("Z", "+00:00")) < now:
                        overdue += 1
                except Exception:
                    pass
        goals = conn.execute("SELECT title, target_value, current_value FROM pm_goals WHERE project_id=?",
                             (pid,)).fetchall()
        gpct = [min(100.0, round((g["current_value"] / g["target_value"]) * 100, 1)) if g["target_value"] else 0.0
                for g in goals]
        res_count = conn.execute("SELECT COUNT(*) FROM pm_resources WHERE project_id=?", (pid,)).fetchone()[0]
        res_bytes = row["resources_bytes"] if "resources_bytes" in row.keys() else 0
        active_titles = [t["title"] for t in conn.execute(
            "SELECT title FROM tasks WHERE pm_project_id=? AND deleted_at IS NULL "
            "AND status_v1 NOT IN ('done','cancelled') ORDER BY sort_order LIMIT 8", (pid,)).fetchall()]
    finally:
        conn.close()
    return {
        "id": pid, "name": row["name"], "status": row["status"],
        "progress_pct": row["progress_pct"], "description": row["description"],
        "tasks": {"total": total, "done": done, "active": active, "overdue": overdue},
        "goals": {"count": len(goals), "avg_pct": round(sum(gpct) / len(gpct), 1) if gpct else 0},
        "resources": {"count": res_count, "bytes": res_bytes},
        "active_task_titles": active_titles,
    }


def tool_check_health(**_: Any) -> dict:
    """System health: database liveness + which integrations are configured."""
    integrations: dict[str, bool] = {}
    try:
        from core.integrations import check_all
        integrations = check_all() or {}
    except Exception:
        pass
    db_ok = True
    try:
        c = _conn(); c.execute("SELECT 1"); c.close()
    except Exception:
        db_ok = False
    up = sum(1 for v in integrations.values() if v)
    return {
        "database_ok": db_ok,
        "integrations_configured": integrations,
        "integrations_configured_count": up,
        "integrations_total": len(integrations),
        "overall": "healthy" if db_ok else "degraded",
    }


def tool_recall(query: str = "", **_: Any) -> dict:
    """Search the owner's long-term memory (the second brain)."""
    try:
        from core import brain
        items = brain.retrieve(query, k=6) if query else []
    except Exception as e:
        return {"error": str(e), "memories": []}
    return {"memories": [m.get("content") for m in items if m.get("content")]}


# ── External read tools (P3) — Notion / GitHub / Drive, via the Genesis-vault creds ──
def _notion_title(page: dict) -> str:
    try:
        for v in (page.get("properties") or {}).values():
            if isinstance(v, dict) and v.get("type") == "title":
                txt = "".join(t.get("plain_text", "") for t in v.get("title", []))
                return txt or "(untitled)"
    except Exception:
        pass
    return page.get("url", "(untitled)")


def tool_read_notion(query: str = "", page_id: str = "", **_: Any) -> dict:
    """Search Notion pages (query), or read one page's content (page_id)."""
    from core.integrations import get_integration
    n = get_integration("notion")
    if not n or not n.is_available():
        return {"available": False, "note": "Notion isn't connected, sir — add the key in Integrations."}
    if page_id:
        content = n.get_page_content(page_id)
        return {"available": True, "page_id": page_id, "content": content or "(no readable content)"}
    pages = n.search_pages((query or "").strip())[:8]
    items = [{"id": p.get("id"), "title": _notion_title(p), "url": p.get("url")} for p in pages]
    return {"available": True, "query": query, "count": len(items), "pages": items}


def tool_list_github_repos(limit: int = 30, org: str = "", **_: Any) -> dict:
    """List GitHub repositories for the authenticated user or an organization.
    Args: limit (int, default 30), org (optional org name to list org repos instead).
    """
    from core.integrations import get_integration
    g = get_integration("github")
    if not g or not g.is_available():
        return {"available": False, "note": "GitHub isn't connected, sir — add the token in Integrations."}
    if org:
        raw = g.list_org_repos(org.strip(), limit=limit)
    else:
        raw = g.list_repos(limit=limit)
    if not raw:
        return {"available": True, "count": 0, "repos": [],
                "note": f"No repositories found{' for ' + org if org else ''}. "
                        "Check that the token has repo scope."}
    repos = [
        {
            "full_name": r.get("full_name"),
            "description": (r.get("description") or "")[:120],
            "private": r.get("private", False),
            "language": r.get("language"),
            "stars": r.get("stargazers_count", 0),
            "default_branch": r.get("default_branch"),
            "updated_at": r.get("updated_at"),
            "url": r.get("html_url"),
        }
        for r in raw if isinstance(r, dict)
    ]
    return {"available": True, "count": len(repos),
            "org": org or None, "repos": repos}


def tool_read_github(repo: str = "", path: str = "", readme: bool = False,
                     branches: bool = False, tree: bool = False, **_: Any) -> dict:
    """Read a GitHub repo: info, issues, commits, and optionally browse files.
    Args:
      repo (str, 'owner/name' — required for any read).
      path (str): list contents of a file or directory at this path.
      readme (bool): include the rendered README text.
      branches (bool): include the list of branches.
      tree (bool): include the full recursive file tree (flat list of paths).
    If no repo is given, delegates to list_repos instead."""
    from core.integrations import get_integration
    g = get_integration("github")
    if not g or not g.is_available():
        return {"available": False, "note": "GitHub isn't connected, sir — add the token in Integrations."}
    repo = (repo or "").strip()
    if not repo or "/" not in repo:
        return {"error": "repo must be in 'owner/name' form, e.g. 'octocat/Hello-World'"}
    info = g.get_repo_info(repo)
    if not info:
        return {"available": True, "error": f"couldn't read repo {repo} — "
                "check the name or that your token has access."}
    issues = g.list_issues(repo, limit=5) or []
    commits = g.get_recent_commits(repo, limit=5) or []
    result: dict = {
        "available": True, "repo": repo,
        "description": info.get("description"), "stars": info.get("stargazers_count"),
        "open_issues": info.get("open_issues_count"), "language": info.get("language"),
        "default_branch": info.get("default_branch"),
        "issues": [{"number": i.get("number"), "title": i.get("title")} for i in issues][:5],
        "recent_commits": [
            {"sha": (c.get("sha") or "")[:7],
             "message": ((c.get("commit") or {}).get("message") or "")[:80],
             "author": ((c.get("commit") or {}).get("author") or {}).get("name")}
            for c in commits
        ][:5],
    }
    if readme:
        result["readme"] = g.get_readme(repo)[:4000]
    if branches:
        raw = g.list_branches(repo)
        result["branches"] = [b.get("name") for b in raw if isinstance(b, dict)]
    if tree:
        raw_tree = g.get_tree(repo, branch=info.get("default_branch", ""))
        result["tree"] = [
            {"path": t.get("path"), "type": t.get("type")}
            for t in raw_tree if isinstance(t, dict)
        ][:200]
    if path:
        contents = g.get_file_contents(repo, path)
        if isinstance(contents, list):
            result["path"] = path
            result["contents"] = [
                {"name": c.get("name"), "type": c.get("type"), "path": c.get("path"),
                 "size": c.get("size")}
                for c in contents if isinstance(c, dict)
            ]
        elif isinstance(contents, dict):
            result["path"] = path
            result["file"] = {
                "name": contents.get("name"),
                "size": contents.get("size"),
                "content": contents.get("decoded_content", contents.get("content", ""))[:8000],
            }
    return result


def tool_read_drive(query: str = "", service: str = "", **_: Any) -> dict:
    """Read Google Drive, Gmail, or Calendar via OAuth2.
    Args:
      query (str): search query (Drive Q-syntax, Gmail search, or unused for calendar).
      service (str): 'drive' | 'gmail' | 'calendar' — defaults to 'drive'.
    """
    from core.integrations import get_integration
    g = get_integration("google")
    if not g or not g.is_available():
        return {"available": False, "note": "Google isn't configured, sir — add the OAuth client ID/secret in Integrations."}
    if not g.is_connected():
        return {"available": False, "note": "Google credentials saved, but you haven't authorized yet — click 'Connect with Google' in Integrations."}
    service = (service or "drive").strip().lower()
    query = (query or "").strip()

    if service == "gmail":
        msgs = g.list_gmail_messages(query=query or "in:inbox", limit=8)
        if not msgs:
            return {"available": True, "service": "gmail", "count": 0, "messages": []}
        detailed = [g.get_gmail_message(m["id"]) for m in msgs[:8]]
        return {
            "available": True, "service": "gmail", "query": query,
            "count": len(detailed),
            "messages": [
                {"id": m.get("id"), "from": m.get("from", ""),
                 "subject": m.get("subject", "(no subject)"),
                 "date": m.get("date", ""), "snippet": m.get("snippet", "")[:200]}
                for m in detailed if m
            ],
        }

    if service == "calendar":
        events = g.list_calendar_events(max_results=10)
        return {
            "available": True, "service": "calendar",
            "count": len(events),
            "events": [
                {"summary": e.get("summary", "(no title)"),
                 "start": ((e.get("start") or {}).get("dateTime")
                           or (e.get("start") or {}).get("date") or ""),
                 "end": ((e.get("end") or {}).get("dateTime")
                         or (e.get("end") or {}).get("date") or ""),
                 "location": e.get("location", ""),
                 "link": e.get("htmlLink", "")}
                for e in events
            ],
        }

    # Default: Drive
    files = g.list_drive_files(query=query, limit=20)
    return {
        "available": True, "service": "drive", "query": query or "(recent)",
        "count": len(files),
        "files": [
            {"name": f.get("name"), "id": f.get("id"),
             "type": f.get("mimeType", ""), "size": f.get("size", ""),
             "modified": f.get("modifiedTime", ""), "link": f.get("webViewLink", "")}
            for f in files if isinstance(f, dict)
        ],
    }


# ── Episodic recall: cross-session memory ────────────────────────────────────

import re as _re
from datetime import datetime as _dt, timedelta as _td, timezone as _tz

_PAST_REF_RE = _re.compile(
    r'(yesterday|last\s+\w+|\d+\s*days?\s*ago|earlier|before|'
    r'what\s+did\s+we|do\s+you\s+remember|recall|when\s+did\s+we|'
    r'when\s+were\s+we|what\s+were\s+we\s+discuss\w*|what\s+have\s+we\s+been|'
    r'previous\s+(session|chat|conversation)|other\s+(session|chat|conversation)|'
    r'what\s+about\s+our|talked\s+about|discussed)',
    _re.IGNORECASE,
)


def _detect_past_reference(message: str) -> bool:
    """True when the owner is likely asking about past conversations."""
    return bool(_PAST_REF_RE.search(message or ""))


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


def tool_recall_conversations(query: str = "", when: str = "", limit: int = 30, **_: Any) -> dict:
    """Recall past conversations across ALL chat sessions and Telegram.

    Use when the owner asks what you discussed, when you talked about a topic,
    or references a previous conversation.

    Args:
      query (str): topic or keyword to search for (e.g., "Project X", "GitHub").
      when (str): time filter — 'yesterday', 'today', 'last week', 'last month',
                  'N days ago', or 'YYYY-MM-DD'.
      limit (int): max messages to return (default 30).
    """
    from core.chat_store import search_all_messages

    date_from, date_to = _resolve_when(when)
    messages = search_all_messages(
        query=query.strip(), date_from=date_from, date_to=date_to, limit=limit,
    )
    if not messages:
        return {
            "available": True,
            "count": 0,
            "messages": [],
            "note": (f"No conversations found"
                     + (f" {when}" if when else "")
                     + (f" mentioning '{query}'" if query else "")
                     + "."),
        }
    return {
        "available": True,
        "count": len(messages),
        "query": query or None,
        "when": when or None,
        "date_range": f"{date_from} to {date_to}" if date_from else "all time",
        "messages": [
            {
                "source": m["source"],
                "session": m.get("session_title", m.get("source", "")),
                "role": m["role"],
                "content": m["content"],
                "time": m["created_at"],
            }
            for m in messages
        ],
    }


def tool_storage_status(feature: str = "", **_: Any) -> dict:
    """Storage & Usage (#10): what's eating local disk — total, biggest consumer,
    per-feature top list; pass a feature name for its drill-down [S25]."""
    from core import storage_scan
    try:
        if feature:
            return storage_scan.category_detail(feature, top_n=8)
        s = storage_scan.summary_compact()
        if not s.get("scanned_at", {}).get("db"):
            storage_scan.run_scan("all")
            s = storage_scan.summary_compact()
        return s
    except Exception as e:
        return {"error": str(e)[:200]}


def tool_llm_spend(range: str = "month", **_: Any) -> dict:
    """Storage & Usage (#10): LLM spend/tokens for a range (day|week|month|all),
    top models, per-surface split, budget state [S25]."""
    from core import usage_meter
    if range not in usage_meter.RANGES:
        range = "month"
    try:
        return usage_meter.spend_compact(range)
    except Exception as e:
        return {"error": str(e)[:200]}


def tool_analyze_performance(depth: str = "quick", latest: bool = False, **_: Any) -> dict:
    """Performance 'system doctor' (#19): analyze MC's runtime + code/architecture and report
    whether it's optimized or needs refactoring. depth='quick' (graph+metrics, ~free) runs a
    fresh scan; depth='deep' adds an LLM diagnosis (costs a little); latest=True reports the
    last stored run without recomputing. Returns a compact grounded scorecard."""
    from core import performance_doctor as pdoc
    try:
        r = pdoc.latest() if latest else pdoc.analyze("deep" if str(depth).lower() == "deep" else "quick")
        if not r:
            return {"available": False, "note": "No analysis yet — run one from Health ▸ Performance."}
        subs = r.get("subsystems") or []
        return {
            "available": True,
            "overall_score": r["overall"]["score"], "overall_grade": r["overall"]["grade"],
            "weakest": (subs[0]["name"] + f" ({subs[0]['grade']})") if subs else None,
            "strongest": (subs[-1]["name"] + f" ({subs[-1]['grade']})") if subs else None,
            "high_severity": sum(1 for f in r.get("findings", []) if f.get("severity") == "high"),
            "top_findings": [f["title"] for f in (r.get("findings") or [])[:5]],
            "graph_freshness": (r.get("freshness") or {}).get("behind_label", "fresh"),
            "diagnosis": r.get("diagnosis", ""),
        }
    except Exception as e:
        return {"error": str(e)[:200]}


def tool_web_search(query: str = "", **_: Any) -> dict:
    """Search the live web (Tavily research pipeline) and return sources to cite (P2)."""
    query = (query or "").strip()
    if not query:
        return {"error": "query is required"}
    try:
        from core.research_engine import tavily_search
        results = tavily_search(query, max_results=5) or []
    except Exception as e:
        return {"available": False, "error": str(e)[:200], "results": []}
    items = [{
        "title": r.get("title"), "url": r.get("url"),
        "snippet": (r.get("content") or "")[:280],
    } for r in results if isinstance(r, dict)][:5]
    return {"available": True, "query": query, "count": len(items), "results": items}


def tool_outline_plan(steps: Any = None, title: str = "", **_: Any) -> dict:
    """Agent-mode plan-then-act (#16 D9): the model declares its intended steps BEFORE
    executing. A no-op read-tier tool — the value is the structured plan event the loop
    emits from it (a prose plan would end the turn / get preamble-retracted)."""
    if not isinstance(steps, list):
        return {"error": "steps must be a list of short step descriptions"}
    clean = [str(s).strip() for s in steps if str(s).strip()][:12]
    if not clean:
        return {"error": "steps is empty"}
    return {"ok": True, "title": (title or "").strip()[:120], "steps": clean,
            "note": "Plan recorded. Now execute the steps with tools, one at a time."}


# name → (callable, one-line description for the model)
def tool_get_current_datetime(**_: Any) -> dict:
    """Current date and time in the owner's timezone — always live."""
    import time as _time
    try:
        tz_name = _load_owner_timezone()
    except Exception:
        tz_name = "Asia/Ho_Chi_Minh"
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(tz_name)
        now = datetime.now(tz)
        local_str = now.strftime("%A, %d %B %Y %H:%M:%S %Z")
    except Exception:
        now = datetime.now(timezone.utc)
        local_str = now.strftime("%A, %d %B %Y %H:%M:%S UTC")
    return {
        "datetime_local": local_str,
        "timezone": tz_name,
        "iso_utc": datetime.now(timezone.utc).isoformat(),
        "unix_ts": int(_time.time()),
    }


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


def tool_ask_owner_details(topic: str = "", questions: Optional[list] = None, **_: Any) -> dict:
    """Ask the owner for missing context via an interactive multi-step picker wizard, instead of
    guessing. Generate the questions yourself, tailored to what you need to know right now. Args:
    topic (short string), questions (list of question strings, or objects {question, options?[]}).
    The answers come back in the owner's next message — session-scoped, not saved permanently."""
    topic = (topic or "").strip()
    norm: list[dict] = []
    for q in (questions or []):
        if isinstance(q, str) and q.strip():
            norm.append({"question": q.strip()})
        elif isinstance(q, dict) and q.get("question"):
            item = {"question": str(q["question"]).strip()}
            opts = q.get("options")
            if isinstance(opts, list) and opts:
                item["options"] = [str(o) for o in opts if str(o).strip()][:6]
            norm.append(item)
    norm = norm[:6]
    if not norm:
        return {"error": "questions is required — pass a list of question strings"}
    # Sentinel result: the engine intercepts this, halts the turn, and surfaces a picker
    # to the owner rather than feeding it back to the model.
    return {"__picker__": {"topic": topic or "A few quick questions", "questions": norm}}


def _picker_intro(picker: dict) -> str:
    topic = (picker.get("topic") or "a few details").strip().rstrip(".")
    return f"I need a bit of context first, sir — {topic[:1].lower() + topic[1:]}. Mind filling these in?"


def tool_search_project_resources(project: str = "", query: str = "", **_: Any) -> dict:
    """Semantic + keyword search across one project's Resources (per-project content RAG, #12)."""
    from core import pm_resources as pmres
    key = str(project or "").strip()
    q = str(query or "").strip()
    if not key or not q:
        return {"error": "project (name or id) and query are required"}
    conn = _conn()
    try:
        if key.isdigit():
            row = conn.execute("SELECT id, name FROM pm_projects WHERE id=?", (int(key),)).fetchone()
        else:
            row = conn.execute("SELECT id, name FROM pm_projects WHERE name LIKE ? ORDER BY updated_at DESC LIMIT 1",
                               (f"%{key}%",)).fetchone()
        if not row:
            return {"error": f"no project matching '{project}'"}
        pid = row["id"]
    finally:
        conn.close()
    hits = pmres.search_resources(pid, q, k=6)
    return {"project_id": pid, "project": row["name"], "query": q,
            "count": len(hits), "results": hits}


# ── Terminal read tools (#11) ────────────────────────────────────────────────────
def tool_terminal_status(**_: Any) -> dict:
    """Terminal engine status: approval mode, kill-switch, OS/shell, package managers, tools [D22]."""
    from core import terminal_engine as te
    return te.status()


def tool_list_jobs(**_: Any) -> dict:
    """Background terminal jobs: id, command, status, exit code [D11]."""
    from core import terminal_engine as te
    return te.list_jobs()


def tool_job_output(job_id: int = 0, **_: Any) -> dict:
    """The output (and status) of one background terminal job. Arg: job_id (int)."""
    from core import terminal_engine as te
    try:
        return te.get_job(int(job_id))
    except Exception as e:
        return {"error": str(e)[:200]}


def tool_list_installed_tools(**_: Any) -> dict:
    """TOBI's capability registry: tools it has installed/configured/connected [D15]."""
    from core import terminal_engine as te
    return te.list_tools()


READ_TOOLS: dict[str, tuple[Callable[..., dict], str]] = {
    "get_current_datetime": (tool_get_current_datetime, "Current date and time in the owner's timezone. No args."),
    "ask_owner_details": (tool_ask_owner_details, "Ask the owner for missing context via a picker wizard when you genuinely need details to proceed (or when he says 'ask me for my details'). Args: topic (string), questions (list of strings or {question, options[]}). Prefer this over guessing."),
    "search_project_resources": (tool_search_project_resources, "Search a project's Resources drive (per-project content RAG). Args: project (name or id), query (string). Returns matching resources with snippets."),
    "get_evolution": (tool_get_evolution, "Current evolution tier, completion %, and ability counts. No args."),
    "explain_architecture": (tool_explain_architecture, "TOBI's system architecture, layer by layer. No args."),
    "office_status": (tool_office_status, "Agent count, each agent's role + working/free status, missions running. No args."),
    "list_projects": (tool_list_projects, "Projects with status/progress/revenue. Optional arg: status (e.g. 'active')."),
    "list_tasks": (tool_list_tasks, "Recent tasks with status/priority. Optional args: status, limit (int)."),
    "project_overview": (tool_project_overview, "Full metric snapshot of ONE project (tasks done/active/overdue, progress %, goals, resources size, active task titles). Arg: project (name or id). Use for 'how's project X?'."),
    "check_health": (tool_check_health, "System health: database + which integrations are configured. No args."),
    "recall": (tool_recall, "Search the owner's long-term memory. Arg: query (string)."),
    "read_notion": (tool_read_notion, "Read Notion — search pages (arg: query) or read one page's content (arg: page_id from a prior search)."),
    "read_github": (tool_read_github, "Read a GitHub repo's info, issues, commits, and optionally files. Args: repo ('owner/name'), path (file/dir), readme (bool), branches (bool), tree (bool)."),
    "list_github_repos": (tool_list_github_repos, "List GitHub repositories for the authenticated user or an org. Args: limit (int), org (optional org name)."),
    "read_drive": (tool_read_drive, "Read Google Drive/Gmail/Calendar via OAuth2. Args: query (search), service ('drive'|'gmail'|'calendar', default drive)."),
    "recall_conversations": (tool_recall_conversations, "Recall past conversations across ALL chat sessions + Telegram. Args: query (topic to search), when ('yesterday'|'today'|'last week'|'YYYY-MM-DD'|'N days ago'), limit (int)."),
    "storage_status": (tool_storage_status, "What's eating local disk: total/biggest/per-feature storage. Optional arg: feature (e.g. 'Brain') for its biggest items."),
    "llm_spend": (tool_llm_spend, "LLM spend & tokens: totals, top models, per-surface split, budget state. Optional arg: range (day|week|month|all)."),
    "terminal_status": (tool_terminal_status, "Terminal engine status: approval mode (plan/ask/accept/auto), kill-switch, OS/shell, package managers, tools registered. No args."),
    "list_jobs": (tool_list_jobs, "Background terminal jobs (id, command, status, exit code). No args."),
    "job_output": (tool_job_output, "The output + status of one background terminal job. Arg: job_id (int)."),
    "list_installed_tools": (tool_list_installed_tools, "TOBI's capability registry — tools it has installed/configured/connected via the terminal. No args."),
    "analyze_performance": (tool_analyze_performance, "Performance 'system doctor' (#19): THIS is how you run the performance analysis / 'performance test' shown on the Health ▸ Performance page — call it directly and it runs in-process. You do NOT need the terminal/shell, a browser, or GitHub for this; it reads the local Mission Control codebase itself. Use it whenever the owner asks to run/check performance, run the Health-page performance test, analyze the architecture, or whether the system is optimized / needs a refactor. Args: depth ('quick' = fast, near-free | 'deep' = adds a written diagnosis), latest (bool — report the last run instead of recomputing). Returns overall grade, weakest/strongest subsystems, top refactor findings, and a diagnosis."),
}

# Opt-in tools (P2): advertised to the model only when the owner enables them for a turn
# (e.g. the chat's `+` → Web research toggle), so the base #7 catalog stays unchanged.
OPTIONAL_TOOLS: dict[str, tuple[Callable[..., dict], str]] = {
    "web_search": (tool_web_search, "Search the live web for current info. Arg: query (string). Cite the sources you use in a tobi:reference block."),
    "outline_plan": (tool_outline_plan, "Declare your ordered plan BEFORE executing a multi-step task. Args: steps (list of short strings), title (optional). Call this FIRST in agent mode, then execute the steps."),
}


# ════════════════════════════════════════════════════════════════════════════
# Act-tool catalog (P2) — tiered risk. low/medium auto-execute + report; high is
# PROPOSED and only runs after the owner confirms (button or typed "yes").
# Each wraps an existing sync DB op, so the blast radius is small.
# ════════════════════════════════════════════════════════════════════════════
def tool_remember(fact: str = "", category: Optional[str] = None, **_: Any) -> dict:
    from core import brain
    fact = (fact or "").strip()
    if not fact:
        return {"error": "fact is required"}
    try:
        res = brain.remember(fact, category)
    except Exception as e:
        return {"error": str(e)[:200]}
    return {"ok": True, "saved": fact[:80], "detail": res}


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


def tool_create_project(name: str = "", description: str = "", category: str = "", **_: Any) -> dict:
    """Create a project on the PM board the owner sees (pm_projects), status 'active'."""
    name = (name or "").strip()
    if not name:
        return {"error": "name is required"}
    conn = _conn()
    try:
        cur = conn.execute(
            "INSERT INTO pm_projects (name, description, status, size, category, emoji_icon, accent_color, created_by) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (name, (description or None), "active", "medium", (category or "General"), "📁", "#58a6ff", "tobi"),
        )
        pid = cur.lastrowid
        _pm_log(conn, pid, "project.created", f"Project '{name}' created via TOBI")
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "project_id": pid, "name": name, "status": "active"}


def tool_create_task(project_id: int = 0, title: str = "", description: str = "", **_: Any) -> dict:
    """Create a task inside a PM project (tasks.pm_project_id) so it appears on the board + task list."""
    title = (title or "").strip()
    if not title:
        return {"error": "title is required"}
    try:
        project_id = int(project_id)
    except Exception:
        project_id = 0
    if not project_id:
        return {"error": "project_id is required — call list_projects first to find it"}
    conn = _conn()
    try:
        if not conn.execute("SELECT 1 FROM pm_projects WHERE id=?", (project_id,)).fetchone():
            return {"error": f"no project with id {project_id} — call list_projects to find a real id"}
        next_sort = conn.execute("SELECT COALESCE(MAX(sort_order), 0)+1 FROM tasks").fetchone()[0]
        cur = conn.execute(
            "INSERT INTO tasks (title, objective, description, status, status_v1, priority, priority_label, "
            "owner_label, agent_key, pm_project_id, created_at, updated_at, sort_order) "
            "VALUES (?,?,?,?,?,5,?,?,?,?,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,?)",
            (title, title, (description or None), "pending", "planned", "P2", "owner", "tobi", project_id, next_sort),
        )
        tid = cur.lastrowid
        _pm_log(conn, project_id, "task.created", f"Task '{title}' added via TOBI")
        _pm_recalc(conn, project_id)
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "task_id": tid, "title": title, "project_id": project_id}


def tool_create_resource(project_id: int = 0, url: str = "", name: str = "", text: str = "", **_: Any) -> dict:
    """Add a resource to a project's Resources drive — either a web link (url) or a text note (text)."""
    try:
        project_id = int(project_id)
    except Exception:
        project_id = 0
    if not project_id:
        return {"error": "project_id is required — call list_projects first"}
    url = (url or "").strip()
    text = (text or "").strip()
    if not url and not text:
        return {"error": "either url or text is required"}
    from core import pm_resources as pmres
    conn = _conn()
    try:
        if not conn.execute("SELECT 1 FROM pm_projects WHERE id=?", (project_id,)).fetchone():
            return {"error": f"no project with id {project_id}"}
        if url:
            meta = pmres.build_link(url, name or None)
            cur = conn.execute(
                "INSERT INTO pm_resources (project_id, kind, name, ext, source, rtype, url, text_content, created_by) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (project_id, "link", meta["name"], meta.get("ext"), meta["source"], meta["rtype"],
                 meta["url"], meta.get("text_content"), "tobi"),
            )
        else:
            fname = (name or "note").strip() or "note"
            if "." not in fname:
                fname += ".md"
            meta = pmres.save_file(project_id, fname, text.encode("utf-8"))
            cur = conn.execute(
                "INSERT INTO pm_resources (project_id, kind, name, ext, source, rtype, "
                "size_bytes, disk_path, mime, text_content, created_by) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (project_id, "file", meta["name"], meta["ext"], "device", meta["rtype"],
                 meta["size_bytes"], meta["disk_path"], meta["mime"], meta["text_content"], "tobi"),
            )
            conn.execute("UPDATE pm_projects SET resources_bytes=? WHERE id=?",
                         (pmres.project_bytes(project_id), project_id))
        rid = cur.lastrowid
        _pm_log(conn, project_id, "resource.added", f"Resource '{meta['name']}' added via TOBI")
        conn.commit()
    finally:
        conn.close()
    try:  # index for per-project RAG (best-effort, separate connection)
        pmres.index_resource(rid, project_id, meta.get("text_content"))
    except Exception:
        pass
    return {"ok": True, "resource_id": rid, "project_id": project_id, "name": meta["name"]}


def tool_set_project_description(project_id: int = 0, description: str = "", **_: Any) -> dict:
    """Set (overwrite) a project's plain-text Overview description."""
    try:
        project_id = int(project_id)
    except Exception:
        return {"error": "project_id must be an integer"}
    description = (description or "").strip()
    conn = _conn()
    try:
        if not conn.execute("SELECT 1 FROM pm_projects WHERE id=?", (project_id,)).fetchone():
            return {"error": f"no project with id {project_id}"}
        conn.execute("UPDATE pm_projects SET description=? WHERE id=?", (description or None, project_id))
        _pm_log(conn, project_id, "project.description", "Description updated via TOBI")
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "project_id": project_id, "description": description}


_EMOJI_BY_CATEGORY = {
    "general": "📁", "work": "💼", "personal": "🌟", "research": "🔬",
    "marketing": "📣", "dev": "💻", "design": "🎨", "business": "🏢",
    "content": "✍️", "growth": "📈",
}


def tool_pick_project_icon(project_id: int = 0, emoji: str = "", icon: str = "", **_: Any) -> dict:
    """Set a project's icon. Pass emoji (e.g. '🚀') or icon (a lucide key). Omit both to auto-pick."""
    try:
        project_id = int(project_id)
    except Exception:
        return {"error": "project_id must be an integer"}
    conn = _conn()
    try:
        row = conn.execute("SELECT id, name, category FROM pm_projects WHERE id=?", (project_id,)).fetchone()
        if not row:
            return {"error": f"no project with id {project_id}"}
        if (emoji or "").strip():
            icon_type, icon_value = "emoji", emoji.strip()
        elif (icon or "").strip():
            icon_type, icon_value = "icon", icon.strip()
        else:
            cat = (row["category"] or "").lower()
            pick = _EMOJI_BY_CATEGORY.get(cat)
            if not pick:
                import hashlib
                pool = list(_EMOJI_BY_CATEGORY.values())
                pick = pool[hashlib.md5((row["name"] or "").encode()).digest()[0] % len(pool)]
            icon_type, icon_value = "emoji", pick
        conn.execute("UPDATE pm_projects SET icon_type=?, icon_value=? WHERE id=?",
                     (icon_type, icon_value, project_id))
        _pm_log(conn, project_id, "project.icon", f"Icon set to {icon_value} via TOBI")
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "project_id": project_id, "icon_type": icon_type, "icon_value": icon_value}


def tool_complete_task(task_id: int = 0, note: str = "", **_: Any) -> dict:
    try:
        task_id = int(task_id)
    except Exception:
        return {"error": "task_id must be an integer"}
    conn = _conn()
    try:
        row = conn.execute("SELECT pm_project_id FROM tasks WHERE id=? AND deleted_at IS NULL", (task_id,)).fetchone()
        if not row:
            return {"error": f"no task with id {task_id}"}
        conn.execute(
            "UPDATE tasks SET status='done', status_v1='done', completed_at=CURRENT_TIMESTAMP, "
            "updated_at=CURRENT_TIMESTAMP, output=COALESCE(?, output) WHERE id=?",
            (note or None, task_id),
        )
        if row["pm_project_id"]:
            _pm_log(conn, row["pm_project_id"], "task.completed", f"Task #{task_id} completed via TOBI")
            _pm_recalc(conn, row["pm_project_id"])
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "task_id": task_id, "status": "done"}


def tool_update_project_progress(project_id: int = 0, progress_pct: int = 0, notes: str = "", **_: Any) -> dict:
    try:
        project_id = int(project_id)
        progress_pct = max(0, min(100, int(progress_pct)))
    except Exception:
        return {"error": "project_id and progress_pct must be integers"}
    conn = _conn()
    try:
        if not conn.execute("SELECT 1 FROM pm_projects WHERE id=?", (project_id,)).fetchone():
            return {"error": f"no project with id {project_id}"}
        conn.execute("UPDATE pm_projects SET progress_pct=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                     (float(progress_pct), project_id))
        _pm_log(conn, project_id, "progress.updated", f"Progress set to {progress_pct}% via TOBI" + (f" — {notes}" if notes else ""))
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "project_id": project_id, "progress_pct": progress_pct}


def tool_delete_task(task_id: int = 0, **_: Any) -> dict:
    try:
        task_id = int(task_id)
    except Exception:
        return {"error": "task_id must be an integer"}
    conn = _conn()
    try:
        row = conn.execute("SELECT pm_project_id FROM tasks WHERE id=?", (task_id,)).fetchone()
        if not row:
            return {"error": f"no task with id {task_id}"}
        try:
            conn.execute("UPDATE tasks SET deleted_at=CURRENT_TIMESTAMP WHERE id=?", (task_id,))
        except Exception:
            conn.execute("UPDATE tasks SET status='skipped' WHERE id=?", (task_id,))
        if row["pm_project_id"]:
            _pm_recalc(conn, row["pm_project_id"])
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "task_id": task_id, "deleted": True}


def tool_delete_project(project_id: int = 0, **_: Any) -> dict:
    """Delete a PM project (and remove its tasks from the board). High-risk → owner confirms first."""
    try:
        project_id = int(project_id)
    except Exception:
        return {"error": "project_id must be an integer"}
    conn = _conn()
    try:
        row = conn.execute("SELECT name FROM pm_projects WHERE id=?", (project_id,)).fetchone()
        if not row:
            return {"error": f"no project with id {project_id}"}
        name = row["name"]
        # soft-remove the project's tasks so none dangle on the board, then drop the project row
        try:
            conn.execute("UPDATE tasks SET deleted_at=CURRENT_TIMESTAMP WHERE pm_project_id=? AND deleted_at IS NULL", (project_id,))
        except Exception:
            pass
        conn.execute("DELETE FROM pm_projects WHERE id=?", (project_id,))
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "project_id": project_id, "name": name, "deleted": True}


# Task agent labels the Tasks board understands (mirrors the API's ALLOWED_AGENTS).
_TASK_AGENTS = {"tobi", "research", "coder", "ceo"}
# Friendly synonyms → the canonical task-agent key.
_AGENT_ALIASES = {"developer": "coder", "dev": "coder", "engineer": "coder", "writer": "coder",
                  "researcher": "research", "analyst": "research", "boss": "ceo", "manager": "ceo"}


def tool_assign_task(task_id: int = 0, agent: str = "", **_: Any) -> dict:
    try:
        task_id = int(task_id)
    except Exception:
        return {"error": "task_id must be an integer"}
    agent = (agent or "").strip().lower()
    if not agent:
        return {"error": "agent is required (tobi, research, coder, or ceo)"}
    key = agent if agent in _TASK_AGENTS else _AGENT_ALIASES.get(agent, "tobi")
    conn = _conn()
    try:
        if not conn.execute("SELECT 1 FROM tasks WHERE id=? AND deleted_at IS NULL", (task_id,)).fetchone():
            return {"error": f"no task with id {task_id}"}
        conn.execute("UPDATE tasks SET agent_key=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (key, task_id))
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "task_id": task_id, "assigned_to": key}


def tool_run_mission(objective: str = "", **_: Any) -> dict:
    obj = (objective or "").strip()
    if not obj:
        return {"error": "objective is required"}
    conn = _conn()
    try:
        cur = conn.execute(
            "INSERT INTO missions (title, goal, status, priority) VALUES (?, ?, 'planned', 'Normal')",
            (obj[:80], obj),
        )
        mid = cur.lastrowid
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "mission_id": mid, "status": "queued", "objective": obj[:120]}


def tool_rename_project(project_id: int = 0, new_name: str = "", **_: Any) -> dict:
    """Rename a PM project. Args: project_id (int), new_name (string)."""
    try:
        project_id = int(project_id)
    except Exception:
        return {"error": "project_id must be an integer"}
    new_name = (new_name or "").strip()
    if not new_name:
        return {"error": "new_name is required"}
    conn = _conn()
    try:
        row = conn.execute("SELECT name FROM pm_projects WHERE id=?", (project_id,)).fetchone()
        if not row:
            return {"error": f"no project with id {project_id}"}
        old_name = row["name"]
        conn.execute("UPDATE pm_projects SET name=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (new_name, project_id))
        _pm_log(conn, project_id, "project.renamed", f"Renamed from '{old_name}' to '{new_name}'")
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "project_id": project_id, "old_name": old_name, "new_name": new_name}


def tool_create_goal(project_id: int = 0, title: str = "", description: str = "",
                     due_date: str = "", priority: str = "medium", **_: Any) -> dict:
    """Create a goal inside a PM project. Args: project_id (int), title (string), description (optional), due_date (YYYY-MM-DD, optional), priority (low|medium|high)."""
    title = (title or "").strip()
    if not title:
        return {"error": "title is required"}
    try:
        project_id = int(project_id)
    except Exception:
        return {"error": "project_id must be an integer"}
    conn = _conn()
    try:
        if not conn.execute("SELECT 1 FROM pm_projects WHERE id=?", (project_id,)).fetchone():
            return {"error": f"no project with id {project_id}"}
        cur = conn.execute(
            "INSERT INTO pm_goals (project_id, title, description, due_date, priority, target_value, current_value, owner) VALUES (?,?,?,?,?,100,0,'tobi')",
            (project_id, title, description or None, due_date or None, priority or "medium"),
        )
        gid = cur.lastrowid
        _pm_log(conn, project_id, "goal.created", f"Goal '{title}' created via TOBI")
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "goal_id": gid, "project_id": project_id, "title": title}


def tool_edit_goal(goal_id: int = 0, title: str = "", description: str = "",
                   due_date: str = "", priority: str = "", current_value: float = -1, **_: Any) -> dict:
    """Edit a goal. Args: goal_id (int), and any of: title, description, due_date, priority (low|medium|high), current_value (0-100)."""
    try:
        goal_id = int(goal_id)
    except Exception:
        return {"error": "goal_id must be an integer"}
    conn = _conn()
    try:
        row = conn.execute("SELECT project_id FROM pm_goals WHERE id=?", (goal_id,)).fetchone()
        if not row:
            return {"error": f"no goal with id {goal_id}"}
        project_id = row["project_id"]
        fields, vals = [], []
        if title:
            fields.append("title=?"); vals.append(title.strip())
        if description:
            fields.append("description=?"); vals.append(description)
        if due_date:
            fields.append("due_date=?"); vals.append(due_date)
        if priority:
            fields.append("priority=?"); vals.append(priority)
        if current_value >= 0:
            fields.append("current_value=?"); vals.append(float(current_value))
        if fields:
            fields.append("updated_at=CURRENT_TIMESTAMP")
            vals.append(goal_id)
            conn.execute(f"UPDATE pm_goals SET {', '.join(fields)} WHERE id=?", vals)
            _pm_log(conn, project_id, "goal.edited", f"Goal #{goal_id} updated via TOBI")
            conn.commit()
    finally:
        conn.close()
    return {"ok": True, "goal_id": goal_id}


def tool_delete_goal(goal_id: int = 0, **_: Any) -> dict:
    """Delete a goal (and its sub-goals). Args: goal_id (int)."""
    try:
        goal_id = int(goal_id)
    except Exception:
        return {"error": "goal_id must be an integer"}
    conn = _conn()
    try:
        row = conn.execute("SELECT project_id, title FROM pm_goals WHERE id=?", (goal_id,)).fetchone()
        if not row:
            return {"error": f"no goal with id {goal_id}"}
        project_id = row["project_id"]
        title = row["title"]
        conn.execute("DELETE FROM pm_goals WHERE parent_goal_id=?", (goal_id,))
        conn.execute("DELETE FROM pm_goals WHERE id=?", (goal_id,))
        _pm_log(conn, project_id, "goal.deleted", f"Goal '{title}' deleted via TOBI")
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "goal_id": goal_id, "deleted": True}


def tool_set_category_lock(category_id: str = "", is_locked: bool = False, **_: Any) -> dict:
    """Lock or unlock a Brain memory category. Args: category_id (string slug e.g. 'psychology'), is_locked (bool)."""
    category_id = (category_id or "").strip()
    if not category_id:
        return {"error": "category_id is required"}
    conn = _conn()
    try:
        if not conn.execute("SELECT 1 FROM brain_categories WHERE id=?", (category_id,)).fetchone():
            return {"error": f"no category '{category_id}'"}
        conn.execute("UPDATE brain_categories SET is_locked=? WHERE id=?", (1 if is_locked else 0, category_id))
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "category_id": category_id, "is_locked": is_locked}


# ── Terminal engine tools (#11) — real full-machine execution, two-axis gated ────
# run_command / install_package are DYNAMICALLY gated by the terminal engine (the
# approval mode × the command's risk decides run/confirm/plan/refuse); the answer()
# loop intercepts them (see TERMINAL_TOOLS). The rest use the standard risk tiers.
def tool_run_command(command: str = "", cwd: str = "", background: bool = False,
                     timeout: int = 0, **_: Any) -> dict:
    """Run a shell command on the machine (gating already decided by the engine)."""
    from core import terminal_engine as te
    command = (command or "").strip()
    if not command:
        return {"error": "command is required"}
    try:
        risk = te.classify_risk(command)[0]
    except Exception:
        risk = "medium"
    try:
        timeout = int(timeout) or None
    except Exception:
        timeout = None
    return te.run(command, cwd=(cwd or None), background=bool(background), timeout=timeout, risk=risk)


def tool_install_package(package: str = "", manager: str = "", **_: Any) -> dict:
    """Install a package via pip/pipx/npm/pnpm/winget/choco/scoop, then register it [D13][D15]."""
    from core import terminal_engine as te
    package = (package or "").strip()
    if not package:
        return {"error": "package is required"}
    mgr = te.resolve_manager(manager)
    if not mgr:
        avail = te.available_managers()
        return {"error": "no usable package manager" + (f" — available here: {', '.join(avail)}" if avail
                         else " found on this machine")}
    cmd = te.install_command(mgr, package)
    if not cmd:
        return {"error": f"couldn't build a safe install command for '{package}' via {mgr}"}
    res = te.run(cmd, risk="medium", timeout=te.TIMEOUT_INSTALL)
    if res.get("ok"):
        try:
            te.register_tool(package, channel=mgr, status="installed",
                             how_to_use=f"Installed via {mgr}. Try `{package} --help`.")
            res["registered"] = True
            res["wire_offer"] = (f"'{package}' is installed and in your toolset, sir — want me to wire it as a "
                                 "reusable tool so future calls skip raw shell?")
        except Exception:
            pass
    return res


def tool_configure_tool(name: str = "", path: str = "", content: str = "", append: bool = False, **_: Any) -> dict:
    """Configure an acquired tool by writing/appending its config file [D14]."""
    from core import terminal_engine as te
    path = (path or "").strip()
    if not path:
        return {"error": "path is required"}
    p = os.path.expanduser(path)
    try:
        parent = os.path.dirname(p)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(p, "a" if append else "w", encoding="utf-8") as f:
            f.write(content or "")
    except Exception as e:
        return {"error": str(e)[:200]}
    if (name or "").strip():
        try:
            te.register_tool(name.strip(), status="configured", how_to_use=f"Configured at {p}")
        except Exception:
            pass
    return {"ok": True, "name": name or path, "path": p, "bytes": len(content or ""), "appended": bool(append)}


def tool_connect_tool(name: str = "", secret_name: str = "", login_command: str = "", **_: Any) -> dict:
    """Connect an acquired tool: reference an EXISTING vault/env credential (never a plaintext
    secret through chat) and optionally run the tool's login/setup command [D14]."""
    from core import terminal_engine as te
    name = (name or "").strip()
    if not name:
        return {"error": "name is required"}
    secret_name = (secret_name or "").strip()
    cred_ok = None
    if secret_name:
        cred_ok = bool(os.getenv(secret_name))
        if not cred_ok:
            try:
                from core import vault
                from core.database import get_connection
                conn = get_connection()
                try:
                    cred_ok = any(s.get("name") == secret_name for s in vault.list_secrets(conn))
                finally:
                    conn.close()
            except Exception:
                cred_ok = False
        if not cred_ok:
            return {"error": f"no credential named '{secret_name}' is stored yet, sir — add it in Integrations "
                             "(the Genesis vault) first, then I'll connect the tool."}
    out: dict = {"ok": True, "name": name, "credential": secret_name or None, "credential_found": cred_ok}
    login_command = (login_command or "").strip()
    if login_command:
        risk = te.classify_risk(login_command)[0]
        out["login"] = te.run(login_command, risk=risk)
    try:
        te.register_tool(name, status="connected",
                         how_to_use=(f"Connected (credential '{secret_name}' in vault)." if secret_name else "Connected."))
    except Exception:
        pass
    return out


def tool_kill_job(job_id: int = 0, **_: Any) -> dict:
    """Stop a running background terminal job [D11]."""
    from core import terminal_engine as te
    try:
        return te.kill_job(int(job_id))
    except Exception as e:
        return {"error": str(e)[:200]}


def tool_set_terminal_mode(mode: str = "", **_: Any) -> dict:
    """Switch the terminal approval mode: plan | ask | accept | auto [D17]."""
    from core import terminal_engine as te
    try:
        m = te.set_mode(mode)
    except Exception as e:
        return {"error": str(e)[:120]}
    return {"ok": True, "mode": m}


# Dynamically-gated terminal tools — the answer() loop routes these through the two-axis
# gate (mode × risk) instead of the static RISK map.
TERMINAL_TOOLS = {"run_command", "install_package"}


# name → (callable, risk, description)
ACT_TOOLS: dict[str, tuple[Callable[..., dict], str, str]] = {
    "remember": (tool_remember, "low", "Save a fact to long-term memory. Args: fact (string), category (optional)."),
    "create_project": (tool_create_project, "low", "Create a project on the owner's board. Args: name (string), description (optional), category (optional)."),
    "create_task": (tool_create_task, "low", "Create a task in a project. Args: project_id (int — call list_projects first to get a real id), title (string), description (optional)."),
    "create_resource": (tool_create_resource, "low", "Add a resource to a project's Resources drive. Args: project_id (int), and either url (a web link — YouTube/Drive/GitHub/web are ingested to text) or text (a text/markdown note). name (optional)."),
    "set_project_description": (tool_set_project_description, "low", "Set a project's plain-text Overview description. Args: project_id (int), description (string)."),
    "pick_project_icon": (tool_pick_project_icon, "low", "Set a project's icon. Args: project_id (int), emoji (e.g. '🚀') OR icon (a lucide key). Omit both to auto-pick from the project category/name."),
    "complete_task": (tool_complete_task, "low", "Mark a task done. Args: task_id (int from list_tasks)."),
    "rename_project": (tool_rename_project, "low", "Rename a project. Args: project_id (int), new_name (string). Can be called multiple times to batch-rename."),
    "create_goal": (tool_create_goal, "low", "Create a goal inside a project. Args: project_id (int), title (string), description (optional), due_date (YYYY-MM-DD, optional), priority (low|medium|high)."),
    "edit_goal": (tool_edit_goal, "low", "Update a goal's fields. Args: goal_id (int), and any of: title, description, due_date, priority, current_value (0-100)."),
    "set_category_lock": (tool_set_category_lock, "low", "Lock or unlock a Brain memory category. Args: category_id (slug e.g. 'psychology'), is_locked (bool)."),
    "assign_task": (tool_assign_task, "medium", "Assign a task to an agent. Args: task_id (int), agent (tobi|research|coder|ceo)."),
    "update_project_progress": (tool_update_project_progress, "medium", "Set a project's progress %. Args: project_id (int), progress_pct (0-100), notes (optional)."),
    "delete_goal": (tool_delete_goal, "medium", "Delete a goal and its sub-goals. Args: goal_id (int)."),
    "delete_task": (tool_delete_task, "high", "Delete a task — REQUIRES the owner's confirmation. Args: task_id (int)."),
    "delete_project": (tool_delete_project, "high", "Delete a project and its tasks — REQUIRES the owner's confirmation. Args: project_id (int — call list_projects first to get a real id)."),
    "run_mission": (tool_run_mission, "high", "Queue a mission toward an objective — REQUIRES the owner's confirmation. Args: objective (string)."),
    # ── Terminal engine (#11). run_command/install_package are gated by the terminal
    # engine's two-axis model (approval mode × command risk), not this static tier. ──
    "run_command": (tool_run_command, "medium", "Run a shell command on the machine (install/configure/run anything). Args: command (string), cwd (optional path), background (bool — for long-running servers/watchers), timeout (optional seconds). Gated by the current approval mode × the command's risk; the hard denylist always blocks. Read before you act."),
    "install_package": (tool_install_package, "medium", "Install a package and register it. Args: package (string), manager (optional: pip|pipx|npm|pnpm|winget|choco|scoop — omit to auto-pick an available one)."),
    "configure_tool": (tool_configure_tool, "medium", "Configure an acquired tool by writing its config file. Args: name (optional), path (string, ~ expands), content (string), append (bool)."),
    "connect_tool": (tool_connect_tool, "medium", "Connect an acquired tool using an EXISTING vault/env credential (never a plaintext secret in chat). Args: name (string), secret_name (an existing credential's name, optional), login_command (optional setup/login command)."),
    "kill_job": (tool_kill_job, "low", "Stop a running background terminal job. Args: job_id (int)."),
    "set_terminal_mode": (tool_set_terminal_mode, "low", "Switch the terminal approval mode. Args: mode (plan|ask|accept|auto). plan=propose only; ask=confirm medium/high; accept=only high confirms; auto=run everything (denylist still blocks)."),
}

# Unified lookups: name → (callable, description) and name → risk ('read'|'low'|'medium'|'high').
# Optional tools are registered here too (so the engine can execute them when enabled), but
# they are NOT advertised in the base system prompt — see _read_doc/answer's extra_tools.
ALL_TOOLS: dict[str, tuple[Callable[..., dict], str]] = {
    **{k: (fn, desc) for k, (fn, desc) in READ_TOOLS.items()},
    **{k: (fn, desc) for k, (fn, desc) in OPTIONAL_TOOLS.items()},
    **{k: (fn, desc) for k, (fn, _r, desc) in ACT_TOOLS.items()},
}
RISK: dict[str, str] = {
    **{k: "read" for k in READ_TOOLS},
    **{k: "read" for k in OPTIONAL_TOOLS},
    **{k: risk for k, (_fn, risk, _d) in ACT_TOOLS.items()},
}

from core import tool_registry as _tool_registry
TOOL_SPECS = _tool_registry.build_specs(READ_TOOLS, OPTIONAL_TOOLS, ACT_TOOLS)


def _exec_tool(call: dict, *, mode: str = "agent", allowed_tools: Optional[set[str]] = None,
               turn_id: Optional[str] = None, step_index: int = 0) -> dict:
    raw = ALL_TOOLS.get(call.get("tool", ""))
    typed = TOOL_SPECS.get(call.get("tool", ""))
    error = _tool_registry.validate_call(call, typed, mode, allowed_tools)
    if error:
        return {"error": error.message, "error_code": error.code, "stage": error.stage,
                "retryable": error.retryable}
    if not raw or not typed:
        return {"error": f"unknown tool '{call.get('tool')}'", "error_code": "tool.unknown"}
    fn = raw[0]
    args = call.get("args") or {}
    if not isinstance(args, dict):
        args = {}
    tool_call = _tool_registry.ToolCall(call["tool"], args)
    if turn_id and typed.risk != "read":
        tool_call = _tool_registry.ToolCall(call["tool"], args,
                                             _tool_registry.receipt_key(turn_id, step_index, tool_call))
    result = _tool_registry.invoke(fn, tool_call, typed, turn_id)
    if result.error:
        logger.warning("conductor tool %s failed: %s", call.get("tool"), result.error.safe_detail or result.error.message)
        return {"error": result.error.message, "error_code": result.error.code,
                "stage": result.error.stage, "retryable": result.error.retryable}
    data = result.data
    if isinstance(data, dict) and result.receipt_key:
        data = dict(data)
        data["receipt_key"] = result.receipt_key
        data["replayed"] = result.replayed
    return data


# ── TOBI Actions audit + confirmation (P2) ─────────────────────────────────────
def _ensure_actions_table(conn) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS tobi_actions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id     INTEGER,
            surface     TEXT,
            tool        TEXT NOT NULL,
            args_json   TEXT,
            risk        TEXT,
            status      TEXT,                      -- proposed | executed | rejected | failed
            summary     TEXT,
            result_json TEXT,
            created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
            executed_at DATETIME
        )"""
    )


def _project_name(project_id: Any) -> str:
    """Best-effort friendly project label for confirmation summaries (falls back to #id)."""
    try:
        conn = _conn()
        try:
            row = conn.execute("SELECT name FROM pm_projects WHERE id=?", (int(project_id),)).fetchone()
        finally:
            conn.close()
        if row and row["name"]:
            return f"“{row['name']}”"
    except Exception:
        pass
    return f"#{project_id}"


def _action_summary(tool: str, args: dict) -> str:
    a = args or {}
    return {
        "remember": f'remember "{str(a.get("fact", ""))[:60]}"',
        "create_project": f'create project "{a.get("name", "")}"',
        "create_task": f'create task "{a.get("title", "")}" in project {a.get("project_id")}',
        "create_resource": f'add resource "{a.get("name") or a.get("url") or "note"}" to project {_project_name(a.get("project_id"))}',
        "set_project_description": f'set description of project {_project_name(a.get("project_id"))}',
        "pick_project_icon": f'set icon of project {_project_name(a.get("project_id"))}',
        "complete_task": f'complete task #{a.get("task_id")}',
        "rename_project": f'rename project {_project_name(a.get("project_id"))} → "{a.get("new_name", "")}"',
        "create_goal": f'create goal "{a.get("title", "")}" in project {a.get("project_id")}',
        "edit_goal": f'update goal #{a.get("goal_id")}',
        "delete_goal": f'delete goal #{a.get("goal_id")}',
        "set_category_lock": f"{'lock' if a.get('is_locked') else 'unlock'} Brain category '{a.get('category_id')}'",
        "assign_task": f'assign task #{a.get("task_id")} to {a.get("agent")}',
        "update_project_progress": f'set project {a.get("project_id")} progress to {a.get("progress_pct")}%',
        "delete_task": f'delete task #{a.get("task_id")}',
        "delete_project": f'delete project {_project_name(a.get("project_id"))} (and its tasks)',
        "run_mission": f'run a mission: "{str(a.get("objective", ""))[:60]}"',
        "run_command": f'run `{str(a.get("command", ""))[:70]}`' + (" (background)" if a.get("background") else ""),
        "install_package": f'install {a.get("package", "")}' + (f' via {a.get("manager")}' if a.get("manager") else ""),
        "configure_tool": f'configure {a.get("name") or a.get("path")}',
        "connect_tool": f'connect {a.get("name", "")}',
        "kill_job": f'stop terminal job #{a.get("job_id")}',
        "set_terminal_mode": f'set terminal mode to {a.get("mode")}',
    }.get(tool, f'{tool} {json.dumps(a, default=str)[:60]}')


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _log_action(chat_id: int, surface: str, tool: str, args: dict, risk: str,
                status: str, summary: str, result: Any = None) -> int:
    conn = _conn()
    try:
        _ensure_actions_table(conn)
        cur = conn.execute(
            "INSERT INTO tobi_actions (chat_id, surface, tool, args_json, risk, status, summary, result_json, executed_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (chat_id, surface, tool, json.dumps(args, default=str), risk, status, summary,
             json.dumps(result, default=str) if result is not None else None,
             _now() if status in ("executed", "failed") else None),
        )
        aid = cur.lastrowid
        conn.commit()
        return aid
    finally:
        conn.close()


def _set_status(action_id: int, status: str, result: Any = None) -> None:
    conn = _conn()
    try:
        _ensure_actions_table(conn)
        conn.execute(
            "UPDATE tobi_actions SET status=?, result_json=?, executed_at=? WHERE id=?",
            (status, json.dumps(result, default=str) if result is not None else None, _now(), action_id),
        )
        conn.commit()
    finally:
        conn.close()


def _execute_and_log(chat_id: int, surface: str, tool: str, args: dict, risk: str, *,
                     mode: str = "agent", allowed_tools: Optional[set[str]] = None,
                     turn_id: Optional[str] = None, step_index: int = 0) -> dict:
    result = _exec_tool({"tool": tool, "args": args}, mode=mode, allowed_tools=allowed_tools,
                        turn_id=turn_id, step_index=step_index)
    status = "failed" if isinstance(result, dict) and result.get("error") else "executed"
    _log_action(chat_id, surface, tool, args, risk, status, _action_summary(tool, args), result)
    if status == "executed":
        _maybe_learn(tool)
    return result


def _terminal_command_for(tool: str, args: dict) -> Optional[str]:
    """The concrete shell command a terminal tool WOULD run, for gating/plan (#11)."""
    if tool == "run_command":
        return (args.get("command") or "").strip() or None
    if tool == "install_package":
        try:
            from core import terminal_engine as te
            requested = (args.get("manager") or "").strip().lower()
            mgr = requested or te.resolve_manager("")
            if mgr:
                return te.install_command(mgr, args.get("package", ""))
        except Exception:
            return None
    return None


def _execute_terminal_and_log(chat_id: int, surface: str, tool: str, args: dict, risk: str,
                              on_event: Optional[Callable[[dict], None]]) -> dict:
    """Run a terminal tool, bridging its live stdout to the chat (on_event 'terminal' lines) and
    auditing it to tobi_actions. A non-zero exit code is still an *executed* action (it ran)."""
    from core import terminal_engine as te
    sink_prev = None
    if on_event:
        sink_prev = te.set_output_sink(lambda line: on_event({"type": "terminal", "line": line}))
    try:
        result = _exec_tool({"tool": tool, "args": args})
    finally:
        if on_event:
            te.set_output_sink(sink_prev)
    status = "failed" if isinstance(result, dict) and result.get("error") else "executed"
    _log_action(chat_id, surface, tool, args, risk, status, _action_summary(tool, args), result)
    if status == "executed":
        _maybe_learn(tool)
    return result


def _maybe_learn(tool: str) -> None:
    """Light log-and-learn: every 5th execution of a tool, note the habit in the brain."""
    try:
        conn = _conn()
        try:
            n = conn.execute("SELECT COUNT(*) FROM tobi_actions WHERE tool=? AND status='executed'", (tool,)).fetchone()[0]
        finally:
            conn.close()
        if n and n % 5 == 0:
            from core import brain
            brain.remember(f"Owner often has TOBI {tool.replace('_', ' ')} via the Conductor (~{n}× so far).", category=None)
    except Exception as e:
        logger.debug("conductor learn skipped: %s", e)


def _pending_for(chat_id: int) -> Optional[dict]:
    conn = _conn()
    try:
        _ensure_actions_table(conn)
        row = conn.execute(
            "SELECT * FROM tobi_actions WHERE chat_id=? AND status='proposed' ORDER BY id DESC LIMIT 1", (chat_id,)
        ).fetchone()
    finally:
        conn.close()
    return dict(row) if row else None


def _pending_all(chat_id: int) -> list[dict]:
    """Every still-pending proposal for a chat (so 'yes' confirms a whole batch, not just one)."""
    conn = _conn()
    try:
        _ensure_actions_table(conn)
        rows = conn.execute(
            "SELECT * FROM tobi_actions WHERE chat_id=? AND status='proposed' ORDER BY id ASC", (chat_id,)
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def confirm_action(action_id: int, decision: str = "approve", surface: str = "mc",
                   chat_id: Optional[int] = None) -> dict:
    """Execute (or reject) a previously proposed high-risk action by id."""
    conn = _conn()
    try:
        _ensure_actions_table(conn)
        row = conn.execute("SELECT * FROM tobi_actions WHERE id=?", (action_id,)).fetchone()
    finally:
        conn.close()
    if not row:
        return {"ok": False, "error": "action not found"}
    row = dict(row)
    if row["status"] != "proposed":
        return {"ok": False, "error": f"action already {row['status']}", "status": row["status"]}
    if str(decision).lower() in ("reject", "no", "cancel", "deny"):
        _set_status(action_id, "rejected")
        try:
            from core import agent_runs
            agent_runs.resolve_action(action_id, "rejected")
        except Exception as exc:
            logger.warning("agent run approval propagation failed: %s", exc)
        return {"ok": True, "status": "rejected", "summary": row["summary"]}
    args = {}
    try:
        args = json.loads(row["args_json"] or "{}")
    except Exception:
        args = {}
    result = _exec_tool({"tool": row["tool"], "args": args})
    status = "failed" if isinstance(result, dict) and result.get("error") else "executed"
    _set_status(action_id, status, result)
    try:
        from core import agent_runs
        agent_runs.resolve_action(action_id, status)
    except Exception as exc:
        logger.warning("agent run approval propagation failed: %s", exc)
    if status == "executed":
        _maybe_learn(row["tool"])
    return {"ok": status == "executed", "status": status, "summary": row["summary"], "result": result}


def list_actions(limit: int = 50, chat_id: Optional[int] = None) -> dict:
    conn = _conn()
    try:
        _ensure_actions_table(conn)
        if chat_id is not None:
            rows = conn.execute(
                "SELECT id, chat_id, surface, tool, risk, status, summary, result_json, created_at, executed_at "
                "FROM tobi_actions WHERE chat_id=? ORDER BY id DESC LIMIT ?", (chat_id, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, chat_id, surface, tool, risk, status, summary, result_json, created_at, executed_at "
                "FROM tobi_actions ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
    finally:
        conn.close()
    out = []
    for r in rows:
        d = dict(r)
        raw = d.pop("result_json", None)
        try:
            d["result"] = json.loads(raw) if raw else None
        except Exception:
            d["result"] = None
        out.append(d)
    return {"count": len(out), "actions": out}


# ════════════════════════════════════════════════════════════════════════════
# Engine
# ════════════════════════════════════════════════════════════════════════════
_BUTLER = (
    "You are TOBI, the owner's personal AI — a poised, witty British butler in the spirit of "
    "Jarvis and Alfred. Address the owner as \"sir\". Be concise, warm and precise; lead with the "
    "answer. LANGUAGE: always reply in the SAME language as the owner's latest message "
    "(English or Vietnamese)."
)


def _read_doc(extra_tools: Optional[list[str]] = None, denied: Optional[set] = None,
              allowed: Optional[set] = None) -> str:
    denied = denied or set()
    lines = [f"- {name}: {desc}" for name, (_, desc) in READ_TOOLS.items()
             if name not in denied and (allowed is None or name in allowed)]
    for t in (extra_tools or []):
        if t in OPTIONAL_TOOLS and t not in denied and (allowed is None or t in allowed):
            lines.append(f"- {t}: {OPTIONAL_TOOLS[t][1]}")
    return "\n".join(lines)


def _act_doc(denied: Optional[set] = None, allowed: Optional[set] = None) -> str:
    denied = denied or set()
    return "\n".join(f"- {name} [{risk}]: {desc}" for name, (_, risk, desc) in ACT_TOOLS.items()
                     if name not in denied and (allowed is None or name in allowed))


def _build_tier_context() -> str:
    """Inject the full tier roadmap so TOBI always knows the evolution plan."""
    try:
        from api import dashboard as D
        conn = D._get_conn()
        try:
            statuses = D._detect_abilities(conn)
            prev = D._load_evo_snapshot(conn)
            tiers, _ = D._build_evo_response(statuses, prev)
        finally:
            conn.close()
        lines = ["TOBI EVOLUTION ROADMAP (full tier data — use for any evolution/tier questions):"]
        for t in tiers:
            status = "ACTIVE" if not t.get("complete") and t.get("id") == next(
                (x["id"] for x in tiers if not x.get("complete")), tiers[-1]["id"]
            ) else ("DONE" if t.get("complete") else "LOCKED")
            lines.append(
                f"  Tier {t['id']} [{t.get('roman','')}] {t.get('name','')} [{status}] "
                f"— {t.get('progress_pct',0)}% ({t.get('active_count',0)}/{t.get('total_count',0)} abilities) "
                f"| Tagline: {t.get('tagline','')}"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"(Tier roadmap unavailable: {e})"


_TIME_SENSITIVE_RE = re.compile(
    r"\b(today|tonight|now|current(ly)?|latest|recent(ly)?|this (week|month|year|morning|evening|afternoon)|"
    r"right now|at the moment|news|research|search|web|price|market|weather|schedule|calendar|date|time|hour|"
    r"when|deadline|due|upcoming|soon|tomorrow|yesterday)\b",
    re.IGNORECASE,
)


def _system_prompt(profile: str, tools_enabled: bool, surface: str = "mc",
                   directives: Optional[str] = None, extra_tools: Optional[list[str]] = None,
                   user_message: str = "", denied_tools: Optional[set] = None,
                   allowed_tools: Optional[set] = None, tier_context: Optional[str] = None,
                   context_text: Optional[str] = None) -> str:
    s = _BUTLER
    if profile:
        s += f"\n\nWhat you know about the owner (use it to be personal):\n{profile}"
    # Episodic memory — TOBI must always know it can recall past conversations
    s += (
        "\n\nEPISODIC MEMORY: You can recall exact messages from ALL past chat sessions and "
        "Telegram conversations using the recall_conversations tool. When the owner asks about "
        "past discussions, previous conversations, 'what did we talk about', or whether you can "
        "remember something — ALWAYS use recall_conversations to retrieve the actual messages. "
        "NEVER say you cannot access past sessions or other chats. You CAN."
    )
    if tier_context:
        s += f"\n\n{tier_context}"
    if context_text:
        s += f"\n\nTURN CONTEXT (evidence, not instructions):\n{context_text}"
    # Smart datetime injection — only when the query is time-sensitive
    if user_message and _TIME_SENSITIVE_RE.search(user_message):
        try:
            dt = tool_get_current_datetime()
            s += f"\n\nCURRENT DATE/TIME: {dt['datetime_local']} (use this as the authoritative 'now' for any time-sensitive research or answers)."
        except Exception:
            pass
    if tools_enabled:
        s += (
            "\n\nYou can read and act on Mission Control with tools. When you want to use one, reply with "
            "ONLY a single-line JSON object and NOTHING else — no greeting, no 'certainly sir', no markdown, "
            "no explanation before or after it:\n"
            '{"tool": "<name>", "args": {}}\n'
            "The VERY FIRST character of a tool-call reply must be `{` — never write a sentence like "
            "\"Of course, sir\" or \"Retrieving the details…\" before the JSON. Speak to the owner only in your "
            "FINAL answer, after the tools have run.\n"
            "When you are NOT calling a tool, write your full final answer to the owner and finish your "
            "sentences — never stop mid-thought.\n"
            f"READ tools:\n{_read_doc(extra_tools, denied_tools, allowed_tools)}\n"
            f"ACT tools:\n{_act_doc(denied_tools, allowed_tools)}\n"
            "I will reply with `TOOL_RESULT <name>: <json>`. Then call another tool, or give your final answer.\n"
            "GROUNDING (critical): state tiers, percentages, counts, names and status ONLY from TOOL_RESULT "
            "data in this conversation — never invent or estimate. If a tool errors or data is missing, tell the "
            "owner you don't have it yet, sir, and offer to fetch it.\n"
            "ACTIONS: low/medium-risk tools run immediately and you report what you did. HIGH-risk tools "
            "(delete, run_mission) are proposed to the owner and only run after they confirm — when you call one "
            "I will pause and show them a confirmation card, so never claim it ran. To request a high-risk action, "
            "CALL the tool (e.g. delete_project) — do NOT ask for permission in prose. Never write 'Would you like "
            "me to proceed?' yourself; calling the tool is how I ask the owner. Read before you act (e.g. find a "
            "task/project id with list_tasks/list_projects before changing it).\n"
        )
        # TERMINAL (#11) is an Agent-only capability (#16 [D11][D23]) — advertise it only when the
        # terminal surface is allowed this turn. In Chat mode run_command et al. are denied, so we
        # don't tell the model it has a shell (and the loop rejects the call if it tries anyway).
        _denied = denied_tools or set()
        if "run_command" not in _denied:
            s += (
                "TERMINAL (#11): you have a real full-machine shell via run_command (and install_package / "
                "configure_tool / connect_tool). The engine gates every command by the owner's approval mode "
                "(plan/ask/accept/auto) × the command's risk — you don't decide whether to confirm; just CALL "
                "run_command with the command and I handle gating, streaming, the confirm card, and the audit. "
                "In Plan mode I only preview. A hard denylist blocks catastrophic commands in every mode. To run a "
                "long-lived process (dev server, watcher) pass background=true and manage it with list_jobs/kill_job. "
                "Prefer install_package over a raw `pip install`. Never paste plaintext secrets into a command — "
                "reference a stored credential by name via connect_tool.\n"
            )
        elif tools_enabled:
            s += ("TERMINAL: shell/terminal tools are NOT available in this mode. If the owner asks to run a "
                  "command, install something, or do a machine operation, tell them to switch to Agent mode.\n")
        s += (
            "CHAINS: you may take several steps in one request (e.g. read_notion a project → create_project → "
            "create_task for each item → assign_task to an agent from office_status). Work from real data at each "
            "step. To do several similar actions at once (e.g. create two projects), emit ONE tool-call JSON "
            "object per line in a single reply — they all run; or take them one per turn. Either way, never claim "
            "you created/changed something without its TOOL_RESULT. If a step fails, I stop the chain and report "
            "exactly what was done and what failed — so don't fabricate success."
        )
        if surface == "telegram":
            s += ("\nYou are on Telegram (read + safe): you may answer freely and do low-risk actions, but "
                  "medium/high-risk changes must be done from Mission Control — tell the owner so.")
    if surface != "telegram":
        s += (
            "\n\nFORMATTING (make answers premium and scannable): default to clean Markdown — short paragraphs, "
            "**bold** for key terms, `code` for literals, and bullet or numbered lists. When it genuinely helps, "
            "render a rich block as a fenced ```tobi:<kind>``` code block whose body is a single JSON object:\n"
            '  - ```tobi:table``` {"columns":[...],"rows":[[...]]} — comparisons or structured rows\n'
            '  - ```tobi:chart``` {"type":"bar|line|donut","title":"...","series":[{"label":"...","value":N}]} — numeric trends or breakdowns\n'
            '  - ```tobi:card``` {"title":"...","body":"...","items":[{"label":"...","value":"..."}]} — a summary card\n'
            '  - ```tobi:callout``` {"kind":"info|success|warning|error","title":"...","body":"..."} — a highlighted note\n'
            '  - ```tobi:keyvalue``` {"items":[{"label":"...","value":"..."}]} — key facts at a glance\n'
            '  - ```tobi:status``` {"items":[{"label":"...","state":"success|warning|error|info","value":"..."}]} — status pills\n'
            '  - ```tobi:reference``` {"items":[{"title":"...","url":"...","snippet":"..."}]} — cite sources\n'
            "Use at most one or two blocks per answer, and only with REAL data from this conversation — never invent "
            "numbers to fill a chart or table. Plain prose is perfectly fine when no block adds value."
        )
    if directives:
        s += f"\n\nFor THIS message the owner enabled:\n{directives}"
    return s


_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.S)


def _balanced_objects(text: str) -> list[str]:
    """Extract every top-level {...} substring with brace-balanced bodies (string-aware), so a
    tool-call object survives nested braces (e.g. "args": {}) and a chatty prose preamble."""
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        if text[i] != "{":
            i += 1
            continue
        depth = 0; j = i; instr = False; esc = False
        while j < n:
            c = text[j]
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                instr = not instr
            elif not instr:
                if c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        out.append(text[i:j + 1]); break
            j += 1
        i = j + 1
    return out


def _parse_tool_call(text: str) -> Optional[dict]:
    """Return {'tool','args'} if the model asked for a tool, else None (= final answer).
    Tolerates a prose preamble and nested braces by scanning balanced {...} objects."""
    if not text:
        return None
    candidates: list[str] = [text.strip()]
    m = _FENCE_RE.search(text)
    if m:
        candidates.insert(0, m.group(1).strip())
    candidates += _balanced_objects(text)
    for cand in candidates:
        try:
            obj = json.loads(cand)
        except Exception:
            continue
        if isinstance(obj, dict) and isinstance(obj.get("tool"), str):
            return {"tool": obj["tool"], "args": obj.get("args") or {}}
    return None


def _parse_tool_calls(text: str) -> list[dict]:
    """EVERY tool-call object in a model reply, in order — handles a model that emits several
    calls at once (two JSON objects, or a JSON array) so e.g. 'create 2 projects' all run.
    Dedupes identical calls."""
    if not text:
        return []
    out: list[dict] = []
    seen: set[str] = set()

    def add(o: Any) -> None:
        if isinstance(o, dict) and isinstance(o.get("tool"), str):
            call = {"tool": o["tool"], "args": o.get("args") or {}}
            key = json.dumps(call, sort_keys=True, default=str)
            if key not in seen:
                seen.add(key); out.append(call)

    candidates: list[str] = [m.group(1).strip() for m in _FENCE_RE.finditer(text)]
    candidates += _balanced_objects(text)
    candidates.append(text.strip())
    for cand in candidates:
        try:
            obj = json.loads(cand)
        except Exception:
            continue
        if isinstance(obj, list):
            for o in obj:
                add(o)
        else:
            add(obj)
    return out


def _safe_complete(client, msgs: list, system: str, max_tokens: int = 700) -> str:
    try:
        out = client.complete(list(msgs), system=system, max_tokens=max_tokens)
        return (out or "").strip()
    except Exception as e:  # noqa: BLE001
        logger.warning("conductor LLM call failed: %s", e)
        return ""


def _history(chat_id: int, limit: int = 6) -> list[dict]:
    try:
        from core.database import load_conversation_history
        rows = load_conversation_history(chat_id, limit=limit)
        return [{"role": r["role"], "content": r["content"]} for r in rows
                if r.get("role") in ("user", "assistant") and r.get("content")]
    except Exception:
        return []


def _default_chat_id() -> int:
    from core import brain
    return brain.DASHBOARD_CHAT_ID


# Affirm/negate sets cover EN + VN so a typed "yes"/"có" confirms a pending action.
_AFFIRM = {"yes", "y", "yeah", "yep", "yup", "confirm", "confirmed", "do it", "go ahead", "proceed",
           "ok", "okay", "sure", "please do", "yes please", "go", "approve",
           "có", "co", "đồng ý", "dong y", "ừ", "u", "được", "duoc", "làm đi", "lam di",
           "tiến hành", "tien hanh"}
_NEGATE = {"no", "n", "nope", "cancel", "stop", "reject", "don't", "dont", "never mind", "nevermind",
           "không", "khong", "hủy", "huy", "đừng", "dung", "thôi", "thoi"}


def _norm(msg: str) -> str:
    return re.sub(r"[!.\s]+$", "", (msg or "").strip().lower())


def _is_affirm(msg: str) -> bool:
    return _norm(msg) in _AFFIRM


def _is_negate(msg: str) -> bool:
    return _norm(msg) in _NEGATE


def _propose_reply(summary: str, risk: str) -> str:
    return (f"I'd like to {summary}, sir — that's a {risk}-risk action, so I'll wait for your nod. "
            "Shall I proceed? (Reply “yes” to confirm, or use the button.)")


def _propose_actions(highs: list[tuple], chat_id: int, surface: str, used: list, intent: str) -> dict:
    """Propose one or many actions for confirmation. Multiple → a single batch card the owner
    accepts/refuses together (so 'delete 3 projects' asks once). Items may carry their own risk
    (a terminal command confirmed under Ask is medium, not high)."""
    items: list[dict] = []
    out_used = list(used)
    for entry in highs:
        tool, args = entry[0], entry[1]
        risk = entry[2] if len(entry) > 2 else "high"
        summary = _action_summary(tool, args)
        aid = _log_action(chat_id, surface, tool, args, risk, "proposed", summary)
        items.append({"id": aid, "tool": tool, "summary": summary, "risk": risk})
        out_used.append(tool)
    if len(items) == 1:
        it = items[0]
        return {"reply": _propose_reply(it["summary"], it["risk"]), "tools_used": out_used,
                "intent": intent, "pending_action": it, "streamed": False}
    lines = "\n".join(f"  • {i['summary']}" for i in items)
    reply = (f"Those are {len(items)} high-risk actions, sir — I'll wait for your go-ahead:\n{lines}\n"
             "Reply “yes” to confirm them all, or use the buttons.")
    return {"reply": reply, "tools_used": out_used, "intent": intent,
            "pending_action": {"id": items[0]["id"], "tool": "batch", "risk": "high",
                               "summary": f"{len(items)} high-risk actions", "items": items},
            "streamed": False}


def _confirm_reply_batch(pendings: list[dict], results: Optional[list], decision: str) -> str:
    if len(pendings) == 1:
        return _confirm_reply(pendings[0], (results[0] if results else {"status": "rejected"}))
    if decision != "approve":
        return f"Very good, sir — I've cancelled all {len(pendings)} of those."
    done = sum(1 for r in (results or []) if r.get("status") == "executed")
    if done == len(pendings):
        return f"Done, sir — all {done} actions are complete."
    return f"Completed {done} of {len(pendings)}, sir — the rest didn't go through."


def _confirm_reply(pending: dict, res: dict) -> str:
    status = res.get("status")
    summary = pending.get("summary")
    if status == "executed":
        return f"Done, sir — {summary}."
    if status == "rejected":
        return f"Very good, sir — I've cancelled that ({summary})."
    err = res.get("result", {}).get("error") if isinstance(res.get("result"), dict) else None
    return f"I'm afraid that didn't go through, sir{(' — ' + err) if err else ''}."


_TOOL_PHASE = {
    "get_evolution": "Checking your evolution…", "explain_architecture": "Reviewing the architecture…",
    "office_status": "Looking in on the office…", "list_projects": "Reading your projects…",
    "list_tasks": "Reading your tasks…", "check_health": "Running a health check…",
    "recall": "Searching your memory…", "read_notion": "Reading Notion…",
    "read_github": "Reading GitHub…", "list_github_repos": "Listing repos…", "read_drive": "Checking Drive…", "recall_conversations": "Searching past conversations…", "web_search": "Searching the web…",
    "outline_plan": "Planning the approach…",
    "remember": "Saving that to memory…", "create_project": "Creating the project…",
    "create_task": "Adding the task…", "complete_task": "Completing the task…",
    "assign_task": "Assigning the task…", "update_project_progress": "Updating progress…",
    "delete_task": "Removing the task…", "run_mission": "Preparing the mission…",
    "run_command": "Running the command…", "install_package": "Installing…",
    "configure_tool": "Writing the config…", "connect_tool": "Connecting…",
    "kill_job": "Stopping the job…", "set_terminal_mode": "Switching mode…",
    "terminal_status": "Checking the terminal…", "list_jobs": "Checking jobs…",
    "job_output": "Reading job output…", "list_installed_tools": "Reviewing your toolset…",
    "analyze_performance": "Running a system-health diagnosis…",
}


def _phase_for(tool: str) -> str:
    return _TOOL_PHASE.get(tool, f"Using {tool.replace('_', ' ')}…")


# ── Reliability core (#8 v2 P1): never truncate, never leak reasoning ────────────
STEP_TOKENS = 2048    # generous so a tool-call JSON (or short answer) never truncates
FINAL_TOKENS = 4096   # generous final answer; complete continuation if it still caps
MAX_STEP_RETRIES = 2  # re-issue a garbled/truncated tool-call up to this many times

_MODEL_STRUGGLING = (
    "I'm having trouble completing that with the current model, sir — it keeps returning "
    "incomplete or malformed output. Do try a stronger model from the picker (top-right) and "
    "I'll pick this straight back up."
)

_THINK_RE = re.compile(r"<think(?:ing)?>.*?</think(?:ing)?>", re.S | re.I)
_REASON_LEAD_RE = re.compile(r"^\s*(?:reasoning|thought|thinking|analysis)\s*:\s*", re.I)
# A tool-call JSON object emerging anywhere in a streamed reply (even after a prose preamble
# from a chatty model) — used to reclassify "answer"→"tool" mid-stream and retract the leak.
# Matches as soon as `{"tool"` appears (before the value), so the JSON body never streams.
_TOOL_SIG_RE = re.compile(r'\{\s*"tool"')


def _looks_like_tool_start(stripped: str) -> bool:
    """Cheap classifier for a (streamed) prefix: is this the start of a tool-call JSON?"""
    if not stripped:
        return False
    if stripped[0] == "{":
        return True
    return bool(re.match(r"```(?:json)?\s*\{", stripped))


def _strip_reasoning(text: str) -> tuple[str, str]:
    """Split a reply into (clean_answer, reasoning). Removes <think>…</think> blocks, OpenAI
    'harmony' channels and a leading 'Reasoning:' preamble so the answer body never shows the
    model's private thinking — that goes to the collapsible panel instead (decision #5/#6)."""
    if not text:
        return "", ""
    reasoning = "\n".join(_THINK_RE.findall(text)).strip()
    clean = _THINK_RE.sub("", text)
    if "<|channel|>" in clean or "<|start|>" in clean:
        finals = re.findall(r"final\s*<\|message\|>(.*?)(?:<\|end\|>|<\|return\|>|$)", clean, re.S)
        if finals:
            reasoning = (reasoning + "\n" + clean).strip()
            clean = "\n".join(f.strip() for f in finals)
    low = clean.lower()
    if "<think" in low and "</think" not in low:  # unclosed → it's all reasoning, no answer yet
        idx = low.find("<think")
        reasoning = (reasoning + "\n" + clean[idx:]).strip()
        clean = clean[:idx]
    clean = _REASON_LEAD_RE.sub("", clean).strip()
    return clean, reasoning


def _gen_step(client, msgs: list, system: str, max_tokens: int,
              on_delta: Optional[Callable[[str], None]],
              on_reset: Optional[Callable[[], None]] = None) -> tuple[str, bool, Optional[str]]:
    """Run one model turn. Returns (text, is_answer, finish_reason).

    When `on_delta` is set and the client can stream, a *final answer* streams live via
    on_delta while a *tool-call* is buffered silently (classified from its prefix), so only
    real answers reach the chat as tokens — tool deliberation never shows.

    A chatty model sometimes writes a prose preamble *before* the tool-call JSON ("Of course,
    sir…\\n{\"tool\":…}"). The prefix then looks like an answer, so we start streaming it; once
    the `{\"tool\":` signature appears we reclassify to a tool call, fire `on_reset` (the UI
    drops the leaked preamble) and buffer the rest silently — so the JSON never lingers in chat
    and the tool actually runs."""
    streamer = getattr(client, "complete_stream", None)
    if not on_delta or streamer is None:
        try:
            text = client.complete(list(msgs), system=system, max_tokens=max_tokens) or ""
        except Exception as e:  # noqa: BLE001
            logger.warning("conductor step failed: %s", e)
            return "", False, "error"
        # A parseable tool call (even behind a prose preamble) is a tool call, not an answer.
        is_answer = _parse_tool_call(text) is None and not _looks_like_tool_start(text.lstrip())
        if is_answer and on_delta:
            for ch in _stream_chunks(text):
                on_delta(ch)
        return text, is_answer, getattr(client, "last_finish_reason", None)

    buf = ""; decided: Optional[str] = None; emitted = 0; reset = False

    def _to_tool():
        """Reclassify a mid-stream answer as a tool call: retract whatever leaked, buffer on."""
        nonlocal decided, reset
        decided = "tool"; reset = True
        if emitted and on_reset:
            try: on_reset()
            except Exception: pass

    try:
        for delta in streamer(list(msgs), system=system, max_tokens=max_tokens):
            buf += delta
            if decided is None:
                s = buf.lstrip()
                if len(s) >= 8 or "\n" in buf:
                    decided = "tool" if _looks_like_tool_start(s) else "answer"
                    if decided == "answer" and _TOOL_SIG_RE.search(buf):
                        _to_tool()
                    elif decided == "answer":
                        on_delta(buf[emitted:]); emitted = len(buf)
            elif decided == "answer":
                if _TOOL_SIG_RE.search(buf):           # a tool call surfaced after prose → retract
                    _to_tool()
                else:
                    on_delta(buf[emitted:]); emitted = len(buf)
    except Exception as e:  # noqa: BLE001
        logger.warning("conductor stream failed: %s", e)
        try:
            buf = client.complete(list(msgs), system=system, max_tokens=max_tokens) or buf
        except Exception:
            pass
    if decided is None:  # very short output
        decided = "tool" if (_looks_like_tool_start(buf.lstrip()) or _parse_tool_call(buf)) else "answer"
        if decided == "answer" and emitted == 0 and buf:
            on_delta(buf)
    elif decided == "answer" and not reset and _parse_tool_call(buf):
        # streamed fully as an answer but it actually parses as a tool call → retract + run it
        _to_tool()
    return buf, (decided == "answer"), getattr(client, "last_finish_reason", None)


def _continue_answer(client, msgs: list, partial: str, system: str,
                     on_delta: Optional[Callable[[str], None]], rounds: int = 2) -> str:
    """If a streamed/compiled answer stopped on the token cap, ask the model to continue from
    where it left off (streaming the continuation too). Returns the appended text."""
    extra = ""
    cur = partial
    for _ in range(rounds):
        if getattr(client, "last_finish_reason", None) != "length":
            break
        cont = list(msgs) + [
            {"role": "assistant", "content": cur},
            {"role": "user", "content": "Continue from exactly where you stopped. Do not repeat anything."},
        ]
        piece, _isa, _fr = _gen_step(client, cont, system, FINAL_TOKENS, on_delta)
        if not piece:
            break
        extra += piece
        cur = piece
    return extra


def answer(message: str, chat_id: Optional[int] = None, surface: str = "mc",
           model: Optional[str] = None, history: Optional[list[dict]] = None,
           attachments_text: Optional[str] = None, directives: Optional[str] = None,
           extra_tools: Optional[list[str]] = None,
           on_event: Optional[Callable[[dict], None]] = None,
           on_delta: Optional[Callable[[str], None]] = None,
           denied_tools: Optional[set] = None, review_mode: Optional[str] = None,
           mode: str = "agent", route: Optional[str] = None,
           allowed_tools: Optional[set] = None, context_manifest: Any = None,
           turn_id: Optional[str] = None, max_tool_steps: Optional[int] = None,
           step_tokens: Optional[int] = None, final_tokens: Optional[int] = None,
           usage_context: Optional[dict] = None,
           recovery_checkpoint: Optional[dict] = None) -> dict:
    """Core turn: confirm-pending? → classify → (optional) tool-loop with tiered act gating →
    grounded butler reply (+ pending_action when a high-risk act needs confirmation). No
    persistence (the chat/stream wrappers persist + learn). `surface` = 'mc' | 'telegram'.

    `model` ('provider:model') overrides the routed model — the Premium Chat (#8) picker
    threads the session's chosen model here. `history`, when given, is used verbatim as the
    conversation context (the session store owns it) instead of the Conductor's rolling
    `conversations` table.

    `denied_tools` is the mode capability boundary (#16 [D11][D23]): any tool in this set is
    NOT advertised AND is rejected server-side if the model calls it anyway — so the selected
    mode changes the real backend capability, not just prompting (Chat denies the terminal
    surface). Review policy is server-authoritative: ``ask`` proposes every mutation,
    ``session`` trusts low/medium mutations but proposes high-risk work, and ``always`` executes
    all otherwise-allowed mutations autonomously. Recovery checkpoints come from persisted run
    state rather than browser-supplied tool arguments."""
    message = (message or "").strip()
    if not message:
        return {"reply": "", "tools_used": [], "error": "empty"}
    if chat_id is None:
        chat_id = _default_chat_id()
    denied_tools = set(denied_tools or ())
    allowed_tools = set(allowed_tools) if allowed_tools is not None else None
    mode = mode if mode in ("chat", "agent") else "chat"
    review_mode = (review_mode or "").strip().lower()
    if usage_context:
        try:
            from core import model_router as _mr
            _mr.set_usage_context(usage_context.get("surface", mode), usage_context.get("feature", ""))
        except Exception:
            pass

    # Pending high-risk proposals + a typed yes/no resolves them (the whole batch) first.
    pending_list = _pending_all(chat_id)
    if pending_list:
        if _is_affirm(message):
            results = [confirm_action(p["id"], "approve", surface, chat_id) for p in pending_list]
            return {"reply": _confirm_reply_batch(pending_list, results, "approve"),
                    "tools_used": [p["tool"] for p in pending_list], "intent": "CONFIRM", "confirmed": results}
        if _is_negate(message):
            for p in pending_list:
                confirm_action(p["id"], "reject", surface, chat_id)
            return {"reply": _confirm_reply_batch(pending_list, None, "reject"), "tools_used": [], "intent": "CANCEL"}
        # otherwise the owner moved on — leave the proposals pending and answer normally.

    from core import brain
    from core.model_router import get_llm
    from core.task_classifier import classify

    if context_manifest is not None:
        profile = context_manifest.source_content("owner_memory")
        tier_context = context_manifest.source_content("evolution")
        try:
            from core.context_manager import prompt_context
            manifest_text = prompt_context(context_manifest)
        except Exception:
            manifest_text = ""
    else:
        try:
            profile = brain.profile_summary()
        except Exception:
            profile = ""
        tier_context = _build_tier_context()
        manifest_text = ""
    try:
        intent = classify(message)
    except Exception:
        intent = "QUESTION"
    # Attachments (P2): the owner's files arrive as extracted text — fold them into the
    # turn as context so the tool-loop and the grounded reply can use them.
    if attachments_text:
        message = f"{message}\n\n[Attached content the owner shared]\n{attachments_text}"
    tools_enabled = route != "direct" if route else intent not in ("SMALLTALK", "CODING")
    if mode == "agent" and intent == "CODING":
        tools_enabled = True
    system = _system_prompt(profile, tools_enabled, surface, directives, extra_tools,
                            user_message=message, denied_tools=denied_tools,
                            allowed_tools=allowed_tools, tier_context=tier_context,
                            context_text=manifest_text)

    # Smart trigger: when the owner references past conversations, nudge the LLM
    # to use the recall_conversations tool before answering.
    if tools_enabled and _detect_past_reference(message):
        system += (
            "\n\n⚠ EPISODIC RECALL: The owner is asking about past conversations. "
            "Use the recall_conversations tool to retrieve relevant messages BEFORE responding. "
            "Extract the time reference (e.g., 'yesterday', 'last week') and topic from their "
            "message and pass them as the 'when' and 'query' args. "
            "If the owner asks broadly ('what did we discuss yesterday?'), summarize the returned "
            "messages. If they ask specifically ('when did we discuss X?'), report exact messages "
            "with timestamps and which session they came from."
        )

    try:
        # Keep the legacy call shape when no model override is given, so callers/tests that
        # wrap get_llm with the old (task_type-only) signature keep working.
        client = get_llm("simple", model=model) if model else get_llm("simple")
    except Exception as e:
        return {"reply": _LLM_DOWN, "tools_used": [], "intent": intent, "error": str(e)}

    prior = history if history is not None else _history(chat_id, limit=6)
    msgs = list(prior) + [{"role": "user", "content": message}]
    used: list[str] = []
    done_acts: list[str] = []  # successfully executed acts in this chain (for stop-on-failure)
    step_fails = 0             # truncated/garbled steps → model self-diagnosis
    # When a chatty model leaks a prose preamble before a tool call, retract it from the UI.
    on_reset = (lambda: on_event({"type": "reset"})) if on_event else None

    # Recover the persisted failed checkpoint before model planning. Retry replays the exact
    # validated call; Skip creates an explicit result that prevents the model calling it again.
    if recovery_checkpoint:
        command = recovery_checkpoint.get("command")
        failed = recovery_checkpoint.get("failed_step") or {}
        tool = recovery_checkpoint.get("tool") or failed.get("tool")
        args = failed.get("args") or {}
        risk = failed.get("risk") or RISK.get(tool, "read")
        if command == "retry_step" and tool:
            validation_error = _tool_registry.validate_call(
                {"tool": tool, "args": args}, TOOL_SPECS.get(tool), mode, allowed_tools)
            if tool in denied_tools or validation_error:
                reason = "tool is denied in this mode" if tool in denied_tools else validation_error.message
                return {"reply": f"I couldn't retry that checkpoint, sir — {reason}.",
                        "tools_used": [], "intent": intent, "stopped_on_error": True,
                        "failed_step": failed, "streamed": False}
            if on_event:
                on_event({"type": "thinking", "phase": _phase_for(tool), "tool": tool})
            if tool in TERMINAL_TOOLS:
                from core import terminal_engine as te
                cmd = _terminal_command_for(tool, args)
                gate = te.gate(cmd, surface=surface) if cmd else {"decision": "run", "risk": risk}
                risk = gate.get("risk", risk)
                if gate.get("decision") == "refuse":
                    result = {"error": gate.get("reason") or "terminal safety gate refused the command"}
                elif gate.get("decision") == "plan":
                    result = te.plan(cmd, surface)
                elif gate.get("decision") == "confirm":
                    return _propose_actions([(tool, args, risk)], chat_id, surface, used, intent)
                else:
                    result = _execute_terminal_and_log(chat_id, surface, tool, args, risk, on_event)
            else:
                if risk == "high" and review_mode != "always":
                    return _propose_actions([(tool, args, risk)], chat_id, surface, used, intent)
                result = _execute_and_log(chat_id, surface, tool, args, risk, mode=mode,
                                          allowed_tools=allowed_tools, turn_id=turn_id, step_index=0)
            used.append(tool)
            msgs.append({"role": "user", "content":
                         f"CHECKPOINT_RETRY_RESULT {tool}: {json.dumps(result, default=str)[:3000]}"})
            if isinstance(result, dict) and result.get("error"):
                failed_now = {"tool": tool, "args": args, "risk": risk, "error": result["error"]}
                return {"reply": _failure_report([], _action_summary(tool, args), result["error"]),
                        "tools_used": used, "intent": intent, "stopped_on_error": True,
                        "failed_step": failed_now, "streamed": False}
            done_acts.append(_action_summary(tool, args))
        elif command == "skip_step" and tool:
            msgs.append({"role": "user", "content":
                         f"CHECKPOINT_SKIPPED {tool}: the owner explicitly skipped this failed step. "
                         "Continue only with remaining work; do not call it again."})
        elif command == "revise" and recovery_checkpoint.get("revision"):
            msgs.append({"role": "user", "content":
                         "PLAN_REVISION: " + str(recovery_checkpoint["revision"])[:1000]})
        elif command == "resume":
            msgs.append({"role": "user", "content":
                         "RESUME_CHECKPOINT: continue after the last persisted completed step."})

    def _final(text: str) -> dict:
        """Finish a turn: strip reasoning, continue if it was truncated, flag a model issue.

        Guard: NEVER surface a raw tool-call JSON to the owner. A weaker model sometimes emits
        `{"tool": …}` where a prose answer was required (it keeps "calling" a tool — e.g. loops
        on recall_conversations — and still emits JSON on the forced-final step). Dumping that
        verbatim is the `{"tool":"…"}` leak owners see; instead we treat it as a model issue so
        the UI shows a graceful notice, not machine JSON."""
        clean, reasoning = _strip_reasoning(text)
        # Trip only on a genuine tool call: a parseable {"tool":…} object, or a leading `{"tool"`
        # signature (a truncated/garbled one). This is precise — a legitimate fenced-JSON answer
        # the owner asked for does NOT lead with `{"tool"` and won't parse as a call.
        if not clean or _TOOL_SIG_RE.match(clean.lstrip()) or _parse_tool_call(clean):
            # One explicit, visible escalation for malformed output. This runs only after the
            # invalid response has been buffered/retracted, never after a valid partial answer.
            try:
                from core.model_router import get_escalation_llm
                stronger, stronger_id = get_escalation_llm(model)
                if stronger is not None:
                    if on_reset:
                        on_reset()
                    if on_event:
                        on_event({"type": "model_escalated", "from_model": model,
                                  "to_model": stronger_id, "reason": "malformed_output"})
                    retry_msgs = list(msgs) + [{"role": "user", "content":
                        "The previous model produced malformed internal output. Give the owner a complete "
                        "plain-language answer now. Do not emit a tool call or JSON."}]
                    retry, retry_is_answer, _ = _gen_step(
                        stronger, retry_msgs, system, final_tokens or FINAL_TOKENS, on_delta, on_reset)
                    retry_clean, retry_reasoning = _strip_reasoning(retry)
                    if retry_is_answer and retry_clean and not _parse_tool_call(retry_clean):
                        return {"reply": retry_clean, "reasoning": retry_reasoning,
                                "tools_used": used, "intent": intent, "streamed": bool(on_delta),
                                "model_escalated": stronger_id}
            except Exception as exc:
                logger.warning("conductor model escalation failed: %s", exc)
            return {"reply": _MODEL_STRUGGLING, "tools_used": used, "intent": intent,
                    "model_issue": True, "streamed": False}
        return {"reply": clean, "reasoning": reasoning, "tools_used": used,
                "intent": intent, "streamed": bool(on_delta)}

    if not tools_enabled:
        _final_tokens = final_tokens or FINAL_TOKENS
        text, _isa, fr = _gen_step(client, msgs, system, _final_tokens, on_delta)
        if fr == "length":
            text += _continue_answer(client, msgs, text, system, on_delta)
        return _final(text)

    tool_step_index = 0
    for _ in range(max_tool_steps or MAX_TOOL_STEPS):
        text, is_answer, fr = _gen_step(client, msgs, system, step_tokens or STEP_TOKENS, on_delta, on_reset)
        if not text:
            step_fails += 1
            if step_fails > MAX_STEP_RETRIES:
                return {"reply": _MODEL_STRUGGLING, "tools_used": used, "intent": intent, "model_issue": True, "streamed": False}
            continue
        if is_answer:
            if fr == "length":
                text += _continue_answer(client, msgs, text, system, on_delta)
            return _final(text)

        calls = _parse_tool_calls(text)
        if not calls:
            # It looked like a tool call but the JSON was truncated/garbled → retry, stricter.
            step_fails += 1
            if step_fails > MAX_STEP_RETRIES:
                return {"reply": _MODEL_STRUGGLING, "tools_used": used, "intent": intent, "model_issue": True, "streamed": False}
            msgs.append({"role": "assistant", "content": text[:600]})
            msgs.append({"role": "user", "content": "That tool call was incomplete or invalid. Reply with ONLY "
                         "a single-line JSON object exactly like {\"tool\": \"<name>\", \"args\": {}} — no prose, "
                         "no markdown, no commentary."})
            continue

        # Execute EVERY call in this message (a model may batch 'create 2 projects' into one reply).
        # High-risk calls are COLLECTED and proposed together at the end (one confirmation card).
        msgs.append({"role": "assistant", "content": text})
        highs: list[tuple] = []
        for call in calls:
            tool_step_index += 1
            tool = call["tool"]
            args = call.get("args") or {}
            if not isinstance(args, dict):
                args = {}
            risk = RISK.get(tool, "read")

            # ── Mode capability boundary (#16 [D11][D23]): a tool the mode forbids is rejected
            # server-side even if the model calls it anyway (Chat can't run terminal tools). Feed
            # a denial back so the model adjusts and tells the owner to switch to Agent mode. ──
            if tool in denied_tools:
                msgs.append({"role": "user", "content": f"TOOL_RESULT {tool}: " + json.dumps(
                    {"denied": True, "reason": f"{tool} is not available in this mode — shell/terminal "
                     "actions require Agent mode. Tell the owner to switch modes; do not retry."})})
                continue
            if allowed_tools is not None and tool not in allowed_tools:
                msgs.append({"role": "user", "content": f"TOOL_RESULT {tool}: " + json.dumps(
                    {"denied": True, "error_code": "tool.route_denied",
                     "reason": f"{tool} is outside this turn's validated tool scope. Do not retry it."})})
                continue
            validation_error = _tool_registry.validate_call(
                call, TOOL_SPECS.get(tool), mode, allowed_tools
            )
            if validation_error:
                msgs.append({"role": "user", "content": f"TOOL_RESULT {tool}: " + json.dumps({
                    "error": validation_error.message, "error_code": validation_error.code,
                    "stage": validation_error.stage, "retryable": validation_error.retryable,
                })})
                continue

            if on_event:
                try:
                    on_event({"type": "thinking", "phase": _phase_for(tool), "tool": tool})
                except Exception:
                    pass

            # ── outline_plan (#16 D9): surface the declared plan as a structured event ──
            if tool == "outline_plan":
                result = _exec_tool(call, mode=mode, allowed_tools=allowed_tools,
                                    turn_id=turn_id, step_index=tool_step_index)
                if on_event and isinstance(result, dict) and result.get("ok"):
                    try:
                        on_event({"type": "plan", "steps": result["steps"], "title": result.get("title", "")})
                    except Exception:
                        pass
                used.append(tool)
                msgs.append({"role": "user", "content": f"TOOL_RESULT {tool}: {json.dumps(result, default=str)[:3000]}"})
                continue

            # ── Terminal tools (#11): the two-axis engine (mode × command risk) decides ──
            if tool in TERMINAL_TOOLS:
                from core import terminal_engine as te
                cmd = _terminal_command_for(tool, args)
                if not cmd:
                    result = _exec_tool(call, mode=mode, allowed_tools=allowed_tools,
                                        turn_id=turn_id, step_index=tool_step_index)
                else:
                    g = te.gate(cmd, surface=surface)
                    decision, trisk = g["decision"], g["risk"]
                    if decision == "refuse":
                        result = {"refused": True, "risk": trisk, "reason": g["reason"], "command": cmd}
                    elif decision == "plan":
                        result = te.plan(cmd, surface)
                    elif decision == "confirm":
                        highs.append((tool, args, trisk))  # propose with the command's real risk
                        continue
                    else:  # run
                        terminal_receipt = None
                        if turn_id:
                            terminal_call = _tool_registry.ToolCall(tool, args)
                            terminal_receipt = _tool_registry.receipt_key(
                                turn_id, tool_step_index, terminal_call)
                        replay = _tool_registry.load_receipt(terminal_receipt) if terminal_receipt else None
                        if replay is not None:
                            result = dict(replay)
                            result["receipt_key"] = terminal_receipt
                            result["replayed"] = True
                        else:
                            result = _execute_terminal_and_log(chat_id, surface, tool, args, trisk, on_event)
                            if terminal_receipt and not result.get("error"):
                                _tool_registry.store_receipt(
                                    terminal_receipt, turn_id, tool, args, result)
                                result = dict(result)
                                result["receipt_key"] = terminal_receipt
                                result["replayed"] = False
                        if not (isinstance(result, dict) and result.get("error")):
                            done_acts.append(_action_summary(tool, args))
                used.append(tool)
                msgs.append({"role": "user", "content": f"TOOL_RESULT {tool}: {json.dumps(result, default=str)[:3000]}"})
                continue

            if surface == "telegram" and risk in ("medium", "high"):
                result = {"blocked": f"That's a {risk}-risk change, sir — please do it from Mission Control "
                                     "(Telegram stays read-only and safe)."}
            elif risk == "high" and review_mode != "always":
                # Ask/session retain the destructive-action checkpoint. Autonomous mode is an
                # explicit owner choice enforced here rather than silently approved by the UI.
                highs.append((tool, args))
                continue
            elif risk == "read":
                result = _exec_tool(call, mode=mode, allowed_tools=allowed_tools,
                                    turn_id=turn_id, step_index=tool_step_index)
                # Picker sentinel: halt the turn and surface an interactive wizard to the
                # owner (the answers arrive as his next message — session-scoped context).
                if isinstance(result, dict) and result.get("__picker__"):
                    picker = result["__picker__"]
                    return {"reply": _picker_intro(picker), "tools_used": used + [tool],
                            "intent": intent, "pending_picker": picker, "streamed": False}
            else:  # low / medium (and high under autonomous mode) → act + report
                if review_mode == "ask":
                    highs.append((tool, args, risk))
                    continue
                try:
                    result = _execute_and_log(chat_id, surface, tool, args, risk, mode=mode,
                                              allowed_tools=allowed_tools, turn_id=turn_id,
                                              step_index=tool_step_index)
                except TypeError as exc:
                    # Compatibility for existing callers/tests that monkeypatch the historical
                    # five-argument helper. Do not mask TypeErrors raised by the real helper.
                    if "unexpected keyword argument" not in str(exc):
                        raise
                    result = _execute_and_log(chat_id, surface, tool, args, risk)
                # Stop-on-failure: a failed state change halts the chain and reports cleanly.
                if isinstance(result, dict) and result.get("error"):
                    failed_step = {"tool": tool, "args": args, "risk": risk, "error": result["error"]}
                    return {"reply": _failure_report(done_acts, _action_summary(tool, args), result["error"]),
                            "tools_used": used + [tool], "intent": intent, "stopped_on_error": True,
                            "failed_step": failed_step, "streamed": False}
                done_acts.append(_action_summary(tool, args))

            used.append(tool)
            msgs.append({"role": "user", "content": f"TOOL_RESULT {tool}: {json.dumps(result, default=str)[:3000]}"})

        if highs:  # one or more high-risk actions → propose them (batched) and wait for the owner
            return _propose_actions(highs, chat_id, surface, used, intent)

    # Step budget exhausted → force a complete, grounded final answer from the gathered results.
    msgs.append({"role": "user", "content": "Now give your final answer to the owner using only the tool "
                 "results above. Do not call any more tools. Answer fully and do not stop mid-sentence."})
    _final_tokens = final_tokens or FINAL_TOKENS
    text, is_ans, fr = _gen_step(client, msgs, system, _final_tokens, on_delta, on_reset)
    # A weak model may STILL emit a tool-call JSON here instead of answering. One blunt prose-only
    # retry (on_reset retracts any live leak) so the owner gets a real answer — never raw JSON.
    if not is_ans:
        msgs.append({"role": "assistant", "content": text[:600]})
        msgs.append({"role": "user", "content": "Answer in plain prose for the owner now. Do NOT output "
                     "JSON and do NOT call any tool — just summarise what the tool results above show."})
        text, is_ans, fr = _gen_step(client, msgs, system, _final_tokens, on_delta, on_reset)
    if fr == "length":
        text += _continue_answer(client, msgs, text, system, on_delta)
    return _final(text)


def _persist_and_learn(chat_id: int, message: str, reply: str) -> None:
    try:
        from core.database import save_conversation_message
        save_conversation_message(chat_id, "user", message)
        save_conversation_message(chat_id, "assistant", reply)
    except Exception as e:
        logger.warning("conductor persist failed: %s", e)
    try:
        from core import brain
        brain.sweep_once()
    except Exception as e:
        logger.warning("post-chat sweep failed: %s", e)


def conductor_chat(message: str, chat_id: Optional[int] = None, surface: str = "mc") -> dict:
    """Non-streaming turn used by the MC chat (and Telegram). Returns {reply, tools_used}."""
    message = (message or "").strip()
    if not message:
        return {"reply": "", "error": "empty"}
    if chat_id is None:
        chat_id = _default_chat_id()
    res = answer(message, chat_id, surface)
    _persist_and_learn(chat_id, message, res.get("reply", ""))
    return res


def _stream_chunks(text: str):
    """Split a finished answer into small pieces so the chat reveals it like a stream."""
    buf = ""
    for piece in re.findall(r"\S+\s*", text):
        buf += piece
        if len(buf) >= 18:
            yield buf
            buf = ""
    if buf:
        yield buf


def conductor_chat_stream(message: str, chat_id: Optional[int] = None, surface: str = "mc"):
    """Streaming turn: computes the grounded answer (running tools as needed), then reveals it
    in chunks. The tool-loop isn't token-streamable across providers, so we stream the final
    answer; the chat UI's thinking orb covers the 'working' phase."""
    message = (message or "").strip()
    if not message:
        return
    if chat_id is None:
        chat_id = _default_chat_id()
    res = answer(message, chat_id, surface)
    reply = res.get("reply", "") or _LLM_DOWN
    for chunk in _stream_chunks(reply):
        yield chunk
    _persist_and_learn(chat_id, message, reply)


def conductor_status() -> dict:
    """Introspection for the API/tests: which tools the Conductor exposes."""
    terminal: dict = {}
    try:
        from core import terminal_engine as te
        terminal = te.status()
    except Exception as e:  # noqa: BLE001
        terminal = {"error": str(e)[:120]}
    return {
        "phase": "P3 + terminal (#11: read + act + external + chains + full-machine shell)",
        "read_tools": [{"name": n, "description": d} for n, (_, d) in READ_TOOLS.items()],
        "act_tools": [{"name": n, "risk": r, "description": d} for n, (_, r, d) in ACT_TOOLS.items()],
        "optional_tools": [{"name": n, "description": d} for n, (_, d) in OPTIONAL_TOOLS.items()],
        "terminal_tools": sorted(TERMINAL_TOOLS),
        "terminal": terminal,
        "surfaces": {"mc": "full power", "telegram": "read + low-risk only (terminal capped at Ask)"},
        "confirmation": "high-risk actions (delete, run_mission) + gated terminal commands require owner "
                        "confirmation (button or typed yes); the terminal approval mode (plan/ask/accept/auto) "
                        "and hard denylist govern shell execution",
    }

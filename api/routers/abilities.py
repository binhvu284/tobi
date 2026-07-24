"""Ability module API — /api/abilities/*, /api/hermes/skills, /api/proposals/* .

Extracted from api/dashboard.py (refactor Slice — pre-#21 decomposition). Byte-
identical: CoachRequest model + 8 routes (skill ledger, coach, hermes skills,
evolution proposals inbox), only @app.* -> @router.*. Helpers come from api.deps.
Free-var set verified by isolated-pyflakes analysis. See docs/REFACTORING_PLAN.md.
"""
from __future__ import annotations

import json  # noqa: F401 - used by some handlers
import sqlite3  # noqa: F401 - used in type hints
from datetime import datetime, timezone  # noqa: F401 - used by some handlers

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from api.deps import _count, _get_conn, _json_loads, _last, fmt_ago

router = APIRouter(tags=["abilities"])


# ── ABILITY MODULE (Mission Control §3) ────────────────────────────────────────

class CoachRequest(BaseModel):
    note: str
    author: str = "owner"




@router.get("/api/abilities")
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


@router.get("/api/hermes/skills")
def api_hermes_skills():
    """Read-only repo Hermes skill registry (#14): parsed metadata for the Ability
    dashboard — name, description, status, risk, version, last-modified. No execution,
    no DB mirror; a missing folder returns an empty list."""
    from core import hermes_skills
    return hermes_skills.skills_report()


@router.get("/api/abilities/{skill_id}")
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


@router.post("/api/abilities/{skill_id}/coach")
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


@router.get("/api/proposals")
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


@router.post("/api/proposals/{proposal_id}/approve")
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


@router.post("/api/proposals/{proposal_id}/reject")
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


@router.post("/api/abilities/{skill_id}/rollback/{version}")
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

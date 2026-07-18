"""Agent registry routes — /api/agents/* .

Extracted from api/dashboard.py (refactor Slice). Handlers byte-identical;
route decorators rebound to this group's router. See docs/REFACTORING_PLAN.md.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from api.deps import _get_conn, _json_loads, fmt_ago

router = APIRouter(tags=["agents"])


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


@router.get("/api/agents")
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


@router.get("/api/agents/{agent_id}")
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


@router.post("/api/agents")
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


@router.patch("/api/agents/{agent_id}")
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


@router.delete("/api/agents/{agent_id}")
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

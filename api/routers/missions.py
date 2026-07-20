"""Mission / mission-run routes — /api/missions/* .

Extracted from api/dashboard.py (refactor Slice). Handlers byte-identical;
route decorators rebound to this group's router. See docs/REFACTORING_PLAN.md.
"""
from __future__ import annotations

import asyncio
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api.deps import _get_conn

router = APIRouter(tags=["missions"])


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


@router.get("/api/missions")
async def api_missions(status: str = Query(default="all")):
    conn = _get_conn()
    if status == "all":
        rows = conn.execute("SELECT * FROM missions ORDER BY created_at DESC").fetchall()
    else:
        rows = conn.execute("SELECT * FROM missions WHERE status=? ORDER BY created_at DESC", (status,)).fetchall()
    items = [_serialize_mission(conn, r) for r in rows]
    conn.close()
    return {"items": items, "count": len(items), "timestamp": datetime.now(timezone.utc).isoformat()}


@router.get("/api/missions/{mission_id}")
async def api_mission_detail(mission_id: int):
    conn = _get_conn()
    row = conn.execute("SELECT * FROM missions WHERE id=?", (mission_id,)).fetchone()
    if row is None:
        conn.close()
        raise HTTPException(status_code=404, detail="unknown mission")
    m = _serialize_mission(conn, row, include_steps=True)
    conn.close()
    return m


@router.post("/api/missions")
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


@router.patch("/api/missions/{mission_id}")
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


@router.post("/api/missions/{mission_id}/run")
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


@router.get("/api/missions/{mission_id}/events")
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


@router.post("/api/missions/{mission_id}/{action}")
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


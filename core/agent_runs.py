"""
AGENT RUNS — Chat Mode Backend Upgrade (#16).

Durable **Agent-mode execution records** [D8]: one ``agent_runs`` row per Agent turn,
with ``agent_run_steps`` capturing the timeline (plan / tool / terminal / error) as it
streams. The chat route records steps incrementally from the SSE consumer loop, so an
interrupted stream still leaves the last-known state readable (spec §17). Read back via
``/api/chat/runs/*`` and the ``run_id`` stored in the message meta.

Statuses: ``queued | planning | running | waiting_approval | waiting_user | failed |
cancelled | done``. ``waiting_user`` = a chain stopped on a failed step and awaits the
owner's Retry / Skip / Revise call [D10]; ``waiting_approval`` = a proposed high-risk
action awaits confirmation (the tobi_actions confirm flow stays authoritative — V1 does
not back-propagate the confirm into the run status).

Lazy ``CREATE TABLE IF NOT EXISTS`` on every access, same pattern as terminal_engine.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Optional

STATUSES = ("queued", "planning", "running", "waiting_approval", "waiting_user",
            "failed", "cancelled", "done")


def _conn() -> sqlite3.Connection:
    from core.database import get_connection
    return get_connection()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS agent_runs (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id   INTEGER NOT NULL,
            message_id   INTEGER,
            mode         TEXT NOT NULL DEFAULT 'agent',
            status       TEXT NOT NULL DEFAULT 'running',
            title        TEXT,
            error        TEXT,
            created_at   TEXT DEFAULT (datetime('now')),
            updated_at   TEXT DEFAULT (datetime('now')),
            completed_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_agent_runs_session ON agent_runs(session_id, id);
        CREATE TABLE IF NOT EXISTS agent_run_steps (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id       INTEGER NOT NULL,
            type         TEXT NOT NULL,             -- plan | tool | terminal | error | note
            status       TEXT NOT NULL DEFAULT 'done',
            title        TEXT,
            summary      TEXT,
            tool         TEXT,
            risk         TEXT,
            payload_json TEXT,
            created_at   TEXT DEFAULT (datetime('now')),
            completed_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_agent_run_steps_run ON agent_run_steps(run_id, id);
        """
    )


def _with_conn(fn):
    conn = _conn()
    try:
        _ensure(conn)
        return fn(conn)
    finally:
        conn.close()


# ── runs ─────────────────────────────────────────────────────────────────────────
def create_run(session_id: int, title: str = "", mode: str = "agent",
               message_id: Optional[int] = None) -> int:
    def q(conn):
        cur = conn.execute(
            "INSERT INTO agent_runs (session_id, message_id, mode, status, title, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (session_id, message_id, mode, "running", (title or "").strip()[:160], _now(), _now()),
        )
        conn.commit()
        return cur.lastrowid
    return _with_conn(q)


def complete_run(run_id: int, status: str = "done", error: Optional[str] = None,
                 message_id: Optional[int] = None) -> None:
    status = status if status in STATUSES else "done"
    def q(conn):
        sets = "status=?, error=?, updated_at=?, completed_at=?"
        vals = [status, (error or None), _now(),
                _now() if status in ("done", "failed", "cancelled") else None]
        if message_id is not None:
            sets += ", message_id=?"
            vals.append(message_id)
        vals.append(run_id)
        conn.execute(f"UPDATE agent_runs SET {sets} WHERE id=?", vals)
        conn.commit()
    _with_conn(q)


def get_run(run_id: int) -> Optional[dict]:
    def q(conn):
        row = conn.execute("SELECT * FROM agent_runs WHERE id=?", (run_id,)).fetchone()
        if not row:
            return None
        run = dict(row)
        steps = conn.execute(
            "SELECT * FROM agent_run_steps WHERE run_id=? ORDER BY id ASC", (run_id,)
        ).fetchall()
        run["steps"] = [dict(s) for s in steps]
        return run
    return _with_conn(q)


def list_runs(session_id: int, limit: int = 20) -> list[dict]:
    def q(conn):
        rows = conn.execute(
            "SELECT r.*, (SELECT COUNT(*) FROM agent_run_steps s WHERE s.run_id=r.id) AS step_count "
            "FROM agent_runs r WHERE r.session_id=? ORDER BY r.id DESC LIMIT ?",
            (session_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]
    return _with_conn(q)


# ── steps ────────────────────────────────────────────────────────────────────────
def add_step(run_id: int, step_type: str, title: str = "", *, summary: str = "",
             tool: Optional[str] = None, risk: Optional[str] = None,
             payload: Optional[dict] = None, status: str = "done") -> int:
    def q(conn):
        cur = conn.execute(
            "INSERT INTO agent_run_steps (run_id, type, status, title, summary, tool, risk, payload_json, created_at, completed_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (run_id, step_type, status, (title or "").strip()[:200], (summary or "").strip()[:1000],
             tool, risk, json.dumps(payload, default=str)[:4000] if payload else None,
             _now(), _now() if status == "done" else None),
        )
        conn.execute("UPDATE agent_runs SET updated_at=? WHERE id=?", (_now(), run_id))
        conn.commit()
        return cur.lastrowid
    return _with_conn(q)

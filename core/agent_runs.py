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
        CREATE TABLE IF NOT EXISTS agent_run_actions (
            run_id       INTEGER NOT NULL,
            action_id    INTEGER NOT NULL,
            created_at   TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (run_id, action_id)
        );
        CREATE INDEX IF NOT EXISTS idx_agent_run_actions_action ON agent_run_actions(action_id);
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


def set_status(run_id: int, status: str, error: Optional[str] = None) -> Optional[dict]:
    """Move an existing run to a valid state without creating a replacement run."""
    if status not in STATUSES:
        raise ValueError(f"invalid run status: {status}")
    def q(conn):
        if not conn.execute("SELECT 1 FROM agent_runs WHERE id=?", (run_id,)).fetchone():
            return None
        completed = _now() if status in ("done", "failed", "cancelled") else None
        conn.execute("UPDATE agent_runs SET status=?,error=?,updated_at=?,completed_at=? WHERE id=?",
                     (status, error or None, _now(), completed, run_id))
        conn.commit()
        return dict(conn.execute("SELECT * FROM agent_runs WHERE id=?", (run_id,)).fetchone())
    return _with_conn(q)


def command_run(run_id: int, command: str, revision: str = "") -> Optional[dict]:
    """Persist a recovery command against the latest failed checkpoint in this run."""
    command = (command or "").strip().lower()
    prompts = {
        "resume": "Resume the paused task from its last completed checkpoint.",
        "retry_step": "Retry only the failed step, then continue from the existing checkpoints.",
        "skip_step": "Skip the failed step and continue with the remaining existing plan.",
        "revise": (revision or "Revise the remaining plan using my latest instructions, then continue.").strip(),
    }
    run = get_run(run_id)
    if not run:
        return None
    if command == "cancel":
        set_status(run_id, "cancelled")
        add_step(run_id, "note", "Run cancelled by owner", summary="cancel", status="done")
        return {"run_id": run_id, "status": "cancelled", "requires_turn": False}
    if command not in prompts:
        raise ValueError("command must be resume, retry_step, skip_step, revise, or cancel")
    if run["status"] == "done":
        raise ValueError("a completed run cannot be resumed")
    failed = next((s for s in reversed(run.get("steps") or [])
                   if s.get("status") == "failed" and s.get("tool")), None)
    if command in ("retry_step", "skip_step") and not failed:
        raise ValueError("this run has no failed tool checkpoint to recover")
    recovery = {"command": command, "revision": revision[:1000]}
    if failed:
        recovery["failed_step_id"] = failed["id"]
        recovery["tool"] = failed.get("tool")
        try:
            recovery["failed_step"] = json.loads(failed.get("payload_json") or "{}")
        except Exception:
            recovery["failed_step"] = {}
    set_status(run_id, "running")
    add_step(run_id, "recovery", f"Owner command: {command}", summary=revision[:1000],
             payload=recovery, status="pending")
    return {"run_id": run_id, "session_id": run["session_id"], "status": "running",
            "requires_turn": True, "recovery_prompt": prompts[command], "recovery": recovery}


def consume_recovery(run_id: int) -> Optional[dict]:
    """Atomically consume the newest pending recovery command for the resumed turn."""
    def q(conn):
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT * FROM agent_run_steps WHERE run_id=? AND type='recovery' AND status='pending' "
            "ORDER BY id DESC LIMIT 1", (run_id,)).fetchone()
        if not row:
            conn.commit()
            return None
        conn.execute("UPDATE agent_run_steps SET status='running' WHERE id=?", (row["id"],))
        conn.commit()
        try:
            payload = json.loads(row["payload_json"] or "{}")
        except Exception:
            payload = {}
        payload["recovery_step_id"] = row["id"]
        return payload
    return _with_conn(q)


def finish_recovery(step_id: int, status: str = "done", summary: str = "") -> None:
    status = status if status in ("done", "failed", "skipped") else "done"
    def q(conn):
        row = conn.execute("SELECT payload_json FROM agent_run_steps WHERE id=?", (step_id,)).fetchone()
        conn.execute("UPDATE agent_run_steps SET status=?,summary=?,completed_at=? WHERE id=?",
                     (status, summary[:1000], _now(), step_id))
        if status == "done" and row:
            try:
                payload = json.loads(row["payload_json"] or "{}")
            except Exception:
                payload = {}
            target = payload.get("failed_step_id")
            if target and payload.get("command") in ("retry_step", "skip_step"):
                target_status = "skipped" if payload["command"] == "skip_step" else "done"
                conn.execute("UPDATE agent_run_steps SET status=?,completed_at=? WHERE id=?",
                             (target_status, _now(), int(target)))
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


def link_actions(run_id: int, action_ids: list[int]) -> None:
    """Associate pending Conductor actions with the Agent run that proposed them."""
    ids = sorted({int(a) for a in action_ids if int(a) > 0})
    if not ids:
        return
    def q(conn):
        conn.executemany("INSERT OR IGNORE INTO agent_run_actions(run_id,action_id) VALUES (?,?)",
                         [(run_id, aid) for aid in ids])
        conn.commit()
    _with_conn(q)


def resolve_action(action_id: int, action_status: str) -> None:
    """Back-propagate an approval result once every linked action has resolved."""
    def q(conn):
        run_rows = conn.execute(
            "SELECT run_id FROM agent_run_actions WHERE action_id=?", (action_id,)).fetchall()
        for rr in run_rows:
            run_id = rr["run_id"]
            states = [r["status"] for r in conn.execute(
                "SELECT a.status FROM agent_run_actions l JOIN tobi_actions a ON a.id=l.action_id "
                "WHERE l.run_id=?", (run_id,)).fetchall()]
            if any(s == "proposed" for s in states):
                status = "waiting_approval"
            elif any(s == "failed" for s in states):
                status = "failed"
            else:
                status = "done"
            conn.execute("UPDATE agent_runs SET status=?,error=?,updated_at=?,completed_at=? WHERE id=?",
                         (status, "action approval failed" if status == "failed" else None, _now(),
                          _now() if status in ("done", "failed") else None, run_id))
            if status in ("done", "failed"):
                recovery_row = conn.execute(
                    "SELECT id,payload_json FROM agent_run_steps WHERE run_id=? AND type='recovery' "
                    "AND status='running' ORDER BY id DESC LIMIT 1", (run_id,)).fetchone()
                if recovery_row:
                    all_rejected = bool(states) and all(s == "rejected" for s in states)
                    recovery_status = "failed" if status == "failed" else "skipped" if all_rejected else "done"
                    conn.execute("UPDATE agent_run_steps SET status=?,completed_at=? WHERE id=?",
                                 (recovery_status, _now(), recovery_row["id"]))
                    try:
                        recovery_payload = json.loads(recovery_row["payload_json"] or "{}")
                    except Exception:
                        recovery_payload = {}
                    target = recovery_payload.get("failed_step_id")
                    if target and recovery_status in ("done", "skipped"):
                        conn.execute("UPDATE agent_run_steps SET status=?,completed_at=? WHERE id=?",
                                     (recovery_status, _now(), int(target)))
            conn.execute(
                "INSERT INTO agent_run_steps (run_id,type,status,title,summary,payload_json,created_at,completed_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (run_id, "approval", "done", f"Action {action_status}", str(action_id),
                 json.dumps({"action_id": action_id, "status": action_status}), _now(), _now()))
        conn.commit()
    _with_conn(q)

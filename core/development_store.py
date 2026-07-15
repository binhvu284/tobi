"""Durable state and append-only audit storage for controlled development."""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), default=str)


SCHEMA = """
CREATE TABLE IF NOT EXISTS developer_schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS development_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    queue_id INTEGER NOT NULL UNIQUE,
    title TEXT NOT NULL,
    plan_path TEXT NOT NULL,
    plan_hash TEXT NOT NULL,
    acceptance_criteria_json TEXT NOT NULL DEFAULT '[]',
    dependencies_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'planned',
    risk TEXT NOT NULL DEFAULT 'medium',
    target_version TEXT,
    queue_status TEXT,
    queue_effort TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS coding_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL,
    state TEXT NOT NULL,
    stage TEXT NOT NULL,
    branch TEXT,
    worktree TEXT,
    base_sha TEXT,
    head_sha TEXT,
    worker_pid INTEGER,
    progress INTEGER NOT NULL DEFAULT 0,
    blocker TEXT,
    policy_hash TEXT NOT NULL,
    review_cycles INTEGER NOT NULL DEFAULT 0,
    error_code TEXT,
    idempotency_key TEXT UNIQUE,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    FOREIGN KEY(task_id) REFERENCES development_tasks(id)
);
CREATE TABLE IF NOT EXISTS coding_stages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    node_id TEXT NOT NULL,
    position INTEGER NOT NULL,
    title TEXT NOT NULL,
    dependencies_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    checks_json TEXT NOT NULL DEFAULT '[]',
    result_json TEXT,
    started_at TEXT,
    completed_at TEXT,
    UNIQUE(session_id,node_id),
    FOREIGN KEY(session_id) REFERENCES coding_sessions(id)
);
CREATE TABLE IF NOT EXISTS development_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    sequence INTEGER NOT NULL,
    actor TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(session_id,sequence),
    FOREIGN KEY(session_id) REFERENCES coding_sessions(id)
);
CREATE TABLE IF NOT EXISTS development_approvals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER,
    purpose TEXT NOT NULL,
    challenge_hash TEXT NOT NULL UNIQUE,
    owner_identity TEXT NOT NULL,
    policy_hash TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    used_at TEXT,
    decision TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS coding_pull_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL UNIQUE,
    repository TEXT NOT NULL,
    number INTEGER,
    url TEXT,
    head_sha TEXT,
    base_sha TEXT,
    draft INTEGER NOT NULL DEFAULT 1,
    ci_state TEXT,
    conflict_state TEXT,
    merge_state TEXT,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS releases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    version TEXT NOT NULL UNIQUE,
    tier TEXT,
    source TEXT NOT NULL,
    queue_item INTEGER,
    commit_sha TEXT,
    tag TEXT,
    notes TEXT,
    risk TEXT,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    released_at TEXT
);
CREATE TABLE IF NOT EXISTS deployments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    release_id INTEGER,
    target TEXT NOT NULL,
    prior_sha TEXT,
    new_sha TEXT,
    stages_json TEXT NOT NULL DEFAULT '[]',
    health_json TEXT,
    rollback_json TEXT,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    completed_at TEXT
);
CREATE TABLE IF NOT EXISTS repo_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    main_sha TEXT NOT NULL,
    graphify_version TEXT,
    index_path TEXT NOT NULL,
    exclusions_json TEXT NOT NULL,
    generated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS coding_artifacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    evidence_type TEXT NOT NULL,
    path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    retain_until TEXT NOT NULL,
    cleanup_eligible INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_development_events_session_seq ON development_events(session_id,sequence);
CREATE INDEX IF NOT EXISTS idx_coding_sessions_state ON coding_sessions(state,updated_at);
CREATE INDEX IF NOT EXISTS idx_coding_stages_session ON coding_stages(session_id,position);
"""


class DevelopmentStore:
    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path or os.path.expanduser(os.getenv("DB_PATH", "~/.mmo_agent/agent.db")))
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.ensure_schema()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=30000")
        try:
            conn.execute("PRAGMA journal_mode=WAL")
        except sqlite3.OperationalError:
            pass
        return conn

    def ensure_schema(self) -> None:
        conn = self.connect()
        try:
            conn.executescript(SCHEMA)
            conn.execute("INSERT OR IGNORE INTO developer_schema_migrations(version,applied_at) VALUES (1,?)", (utc_now(),))
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _row(row: sqlite3.Row | None) -> dict[str, Any] | None:
        return dict(row) if row is not None else None

    def upsert_task(self, item: dict[str, Any]) -> dict[str, Any]:
        now = utc_now()
        conn = self.connect()
        try:
            conn.execute(
                """INSERT INTO development_tasks
                (queue_id,title,plan_path,plan_hash,acceptance_criteria_json,dependencies_json,
                 status,risk,target_version,queue_status,queue_effort,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(queue_id) DO UPDATE SET
                  title=excluded.title,plan_path=excluded.plan_path,plan_hash=excluded.plan_hash,
                  acceptance_criteria_json=excluded.acceptance_criteria_json,
                  dependencies_json=excluded.dependencies_json,queue_status=excluded.queue_status,
                  queue_effort=excluded.queue_effort,updated_at=excluded.updated_at""",
                (
                    int(item["queue_id"]), item["title"], item["plan_path"], item["plan_hash"],
                    _json(item.get("acceptance_criteria", [])), _json(item.get("dependencies", [])),
                    item.get("status", "planned"), item.get("risk", "medium"), item.get("target_version"),
                    item.get("queue_status"), item.get("queue_effort"), now, now,
                ),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM development_tasks WHERE queue_id=?", (int(item["queue_id"]),)).fetchone()
            return dict(row)
        finally:
            conn.close()

    def list_tasks(self) -> list[dict[str, Any]]:
        conn = self.connect()
        try:
            return [dict(row) for row in conn.execute("SELECT * FROM development_tasks ORDER BY queue_id DESC")]
        finally:
            conn.close()

    def get_task(self, *, task_id: int | None = None, queue_id: int | None = None) -> dict[str, Any] | None:
        if task_id is None and queue_id is None:
            raise ValueError("task_id or queue_id is required")
        conn = self.connect()
        try:
            if task_id is not None:
                row = conn.execute("SELECT * FROM development_tasks WHERE id=?", (task_id,)).fetchone()
            else:
                row = conn.execute("SELECT * FROM development_tasks WHERE queue_id=?", (queue_id,)).fetchone()
            return self._row(row)
        finally:
            conn.close()

    def create_session(self, task_id: int, policy_hash: str, idempotency_key: str) -> dict[str, Any]:
        now = utc_now()
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute("SELECT * FROM coding_sessions WHERE idempotency_key=?", (idempotency_key,)).fetchone()
            if existing:
                conn.commit()
                return dict(existing)
            active = conn.execute(
                "SELECT id FROM coding_sessions WHERE state IN ('approved','preparing','coding','validating','reviewing','pushed','merging','deploying') LIMIT 1"
            ).fetchone()
            if active:
                raise RuntimeError(f"Coding workflow {active['id']} is already active.")
            cur = conn.execute(
                """INSERT INTO coding_sessions
                (task_id,state,stage,policy_hash,idempotency_key,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?)""",
                (task_id, "approved", "approved", policy_hash, idempotency_key, now, now),
            )
            conn.commit()
            return dict(conn.execute("SELECT * FROM coding_sessions WHERE id=?", (cur.lastrowid,)).fetchone())
        finally:
            conn.close()

    def get_session(self, session_id: int) -> dict[str, Any] | None:
        conn = self.connect()
        try:
            row = conn.execute(
                """SELECT s.*,t.queue_id,t.title,t.plan_path,t.plan_hash,t.target_version,t.risk
                   FROM coding_sessions s JOIN development_tasks t ON t.id=s.task_id WHERE s.id=?""",
                (session_id,),
            ).fetchone()
            return self._row(row)
        finally:
            conn.close()

    def list_sessions(self, limit: int = 50) -> list[dict[str, Any]]:
        conn = self.connect()
        try:
            rows = conn.execute(
                """SELECT s.*,t.queue_id,t.title,t.plan_path,t.target_version,t.risk
                   FROM coding_sessions s JOIN development_tasks t ON t.id=s.task_id
                   ORDER BY s.updated_at DESC LIMIT ?""",
                (max(1, min(limit, 200)),),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def update_session(self, session_id: int, **fields: Any) -> dict[str, Any]:
        allowed = {
            "state", "stage", "branch", "worktree", "base_sha", "head_sha", "worker_pid",
            "progress", "blocker", "review_cycles", "error_code", "completed_at",
        }
        changes = {key: value for key, value in fields.items() if key in allowed}
        if not changes:
            result = self.get_session(session_id)
            if not result:
                raise KeyError(session_id)
            return result
        changes["updated_at"] = utc_now()
        sql = ",".join(f"{key}=?" for key in changes)
        conn = self.connect()
        try:
            cur = conn.execute(f"UPDATE coding_sessions SET {sql} WHERE id=?", (*changes.values(), session_id))
            if cur.rowcount != 1:
                raise KeyError(session_id)
            conn.commit()
        finally:
            conn.close()
        result = self.get_session(session_id)
        if not result:
            raise KeyError(session_id)
        return result

    def add_stages(self, session_id: int, stages: Iterable[dict[str, Any]]) -> None:
        conn = self.connect()
        try:
            for position, stage in enumerate(stages):
                conn.execute(
                    """INSERT OR IGNORE INTO coding_stages
                    (session_id,node_id,position,title,dependencies_json,status)
                    VALUES (?,?,?,?,?,'pending')""",
                    (session_id, stage["id"], position, stage["title"], _json(stage.get("depends", []))),
                )
            conn.commit()
        finally:
            conn.close()

    def list_stages(self, session_id: int) -> list[dict[str, Any]]:
        conn = self.connect()
        try:
            return [dict(row) for row in conn.execute(
                "SELECT * FROM coding_stages WHERE session_id=? ORDER BY position", (session_id,)
            )]
        finally:
            conn.close()

    def update_stage(self, session_id: int, node_id: str, **fields: Any) -> dict[str, Any]:
        allowed = {"status", "attempts", "checks_json", "result_json", "started_at", "completed_at"}
        changes = {key: (_json(value) if key.endswith("_json") and not isinstance(value, str) else value)
                   for key, value in fields.items() if key in allowed}
        if not changes:
            raise ValueError("No stage fields supplied")
        sql = ",".join(f"{key}=?" for key in changes)
        conn = self.connect()
        try:
            conn.execute(f"UPDATE coding_stages SET {sql} WHERE session_id=? AND node_id=?",
                         (*changes.values(), session_id, node_id))
            conn.commit()
            row = conn.execute("SELECT * FROM coding_stages WHERE session_id=? AND node_id=?",
                               (session_id, node_id)).fetchone()
            if not row:
                raise KeyError(node_id)
            return dict(row)
        finally:
            conn.close()

    def append_event(self, session_id: int, event_type: str, payload: dict[str, Any], actor: str = "tobi") -> dict[str, Any]:
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            sequence = int(conn.execute(
                "SELECT COALESCE(MAX(sequence),0)+1 FROM development_events WHERE session_id=?", (session_id,)
            ).fetchone()[0])
            created = utc_now()
            cur = conn.execute(
                "INSERT INTO development_events(session_id,sequence,actor,event_type,payload_json,created_at) VALUES (?,?,?,?,?,?)",
                (session_id, sequence, actor, event_type, _json(payload), created),
            )
            conn.commit()
            return {"id": cur.lastrowid, "session_id": session_id, "sequence": sequence,
                    "actor": actor, "event_type": event_type, "payload": payload, "created_at": created}
        finally:
            conn.close()

    def list_events(self, session_id: int, after: int = 0, limit: int = 500) -> list[dict[str, Any]]:
        conn = self.connect()
        try:
            rows = conn.execute(
                "SELECT * FROM development_events WHERE session_id=? AND sequence>? ORDER BY sequence LIMIT ?",
                (session_id, max(0, after), max(1, min(limit, 2000))),
            ).fetchall()
            events = []
            for row in rows:
                event = dict(row)
                event["payload"] = json.loads(event.pop("payload_json"))
                events.append(event)
            return events
        finally:
            conn.close()

    def create_challenge(
        self,
        purpose: str,
        policy_hash: str,
        *,
        session_id: int | None = None,
        owner_identity: str = "owner",
        ttl_seconds: int = 300,
    ) -> tuple[str, dict[str, Any]]:
        token = secrets.token_urlsafe(32)
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        now = datetime.now(timezone.utc)
        expires = now + timedelta(seconds=max(30, ttl_seconds))
        conn = self.connect()
        try:
            cur = conn.execute(
                """INSERT INTO development_approvals
                (session_id,purpose,challenge_hash,owner_identity,policy_hash,expires_at,created_at)
                VALUES (?,?,?,?,?,?,?)""",
                (session_id, purpose, digest, owner_identity, policy_hash, expires.isoformat(), now.isoformat()),
            )
            conn.commit()
            row = dict(conn.execute("SELECT * FROM development_approvals WHERE id=?", (cur.lastrowid,)).fetchone())
            return token, row
        finally:
            conn.close()

    def consume_challenge(self, token: str, purpose: str, policy_hash: str, *, session_id: int | None = None) -> dict[str, Any]:
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM development_approvals WHERE challenge_hash=?", (digest,)).fetchone()
            if not row:
                raise PermissionError("Re-authentication challenge is invalid.")
            item = dict(row)
            if item["used_at"]:
                raise PermissionError("Re-authentication challenge was already used.")
            if item["purpose"] != purpose or item["policy_hash"] != policy_hash:
                raise PermissionError("Re-authentication challenge does not match this action.")
            if session_id is not None and item["session_id"] not in (None, session_id):
                raise PermissionError("Re-authentication challenge belongs to another workflow.")
            if datetime.fromisoformat(item["expires_at"]) <= datetime.now(timezone.utc):
                raise PermissionError("Re-authentication challenge has expired.")
            used = utc_now()
            conn.execute(
                "UPDATE development_approvals SET used_at=?,decision='approved' WHERE id=? AND used_at IS NULL",
                (used, item["id"]),
            )
            conn.commit()
            item.update({"used_at": used, "decision": "approved"})
            return item
        finally:
            conn.close()

    def has_approval(self, session_id: int, purpose: str, policy_hash: str) -> bool:
        conn = self.connect()
        try:
            row = conn.execute(
                """SELECT 1 FROM development_approvals
                   WHERE session_id=? AND purpose=? AND policy_hash=? AND decision='approved' AND used_at IS NOT NULL
                   LIMIT 1""",
                (session_id, purpose, policy_hash),
            ).fetchone()
            return bool(row)
        finally:
            conn.close()

    def overview(self) -> dict[str, Any]:
        conn = self.connect()
        try:
            counts = {row["state"]: row["count"] for row in conn.execute(
                "SELECT state,COUNT(*) count FROM coding_sessions GROUP BY state"
            )}
            releases = [dict(row) for row in conn.execute("SELECT * FROM releases ORDER BY id DESC LIMIT 20")]
            deployments = [dict(row) for row in conn.execute("SELECT * FROM deployments ORDER BY id DESC LIMIT 20")]
            return {"states": counts, "releases": releases, "deployments": deployments}
        finally:
            conn.close()

    def add_artifact(self, session_id: int, evidence_type: str, path: Path, retain_until: str) -> dict[str, Any]:
        data = path.read_bytes()
        now = utc_now()
        conn = self.connect()
        try:
            cur = conn.execute(
                """INSERT INTO coding_artifacts
                   (session_id,evidence_type,path,sha256,size_bytes,retain_until,created_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (session_id, evidence_type, str(path), hashlib.sha256(data).hexdigest(), len(data), retain_until, now),
            )
            conn.commit()
            return dict(conn.execute("SELECT * FROM coding_artifacts WHERE id=?", (cur.lastrowid,)).fetchone())
        finally:
            conn.close()

    def list_artifacts(self, session_id: int) -> list[dict[str, Any]]:
        conn = self.connect()
        try:
            return [dict(row) for row in conn.execute(
                "SELECT * FROM coding_artifacts WHERE session_id=? ORDER BY id", (session_id,)
            )]
        finally:
            conn.close()

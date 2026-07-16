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
    goal_id INTEGER,
    plan_hash_snapshot TEXT,
    criteria_snapshot_json TEXT NOT NULL DEFAULT '[]',
    validation_commands_json TEXT NOT NULL DEFAULT '[]',
    lease_owner TEXT,
    lease_expires_at TEXT,
    cancel_requested INTEGER NOT NULL DEFAULT 0,
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
CREATE TABLE IF NOT EXISTS development_goals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    objective TEXT NOT NULL,
    acceptance_criteria_json TEXT NOT NULL,
    validation_commands_json TEXT NOT NULL DEFAULT '[]',
    autonomy TEXT NOT NULL DEFAULT 'sandbox',
    preferred_models_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'queued',
    max_iterations INTEGER NOT NULL DEFAULT 12,
    iteration_count INTEGER NOT NULL DEFAULT 0,
    current_session_id INTEGER,
    last_error TEXT,
    lease_owner TEXT,
    lease_expires_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT
);
CREATE TABLE IF NOT EXISTS goal_iterations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    goal_id INTEGER NOT NULL,
    session_id INTEGER,
    iteration INTEGER NOT NULL,
    state TEXT NOT NULL,
    result_json TEXT,
    created_at TEXT NOT NULL,
    completed_at TEXT,
    UNIQUE(goal_id,iteration),
    FOREIGN KEY(goal_id) REFERENCES development_goals(id)
);
CREATE TABLE IF NOT EXISTS development_commands (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    idempotency_key TEXT NOT NULL UNIQUE,
    target_type TEXT NOT NULL,
    target_id INTEGER NOT NULL,
    command TEXT NOT NULL,
    status TEXT NOT NULL,
    response_json TEXT,
    created_at TEXT NOT NULL,
    completed_at TEXT
);
CREATE TABLE IF NOT EXISTS coding_worker_profiles (
    slug TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    adapter TEXT NOT NULL,
    model TEXT NOT NULL DEFAULT '',
    auth_mode TEXT NOT NULL DEFAULT 'inherited',
    credential_env TEXT NOT NULL DEFAULT '',
    reviewer_profile TEXT NOT NULL DEFAULT 'reviewer-default',
    enabled INTEGER NOT NULL DEFAULT 1,
    config_json TEXT NOT NULL DEFAULT '{}',
    health_status TEXT NOT NULL DEFAULT 'unknown',
    health_detail TEXT,
    last_probed_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS coding_worker_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    stage_id TEXT NOT NULL,
    profile_slug TEXT NOT NULL,
    adapter TEXT NOT NULL,
    model TEXT,
    external_session_id TEXT,
    status TEXT NOT NULL,
    error_code TEXT,
    started_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    FOREIGN KEY(session_id) REFERENCES coding_sessions(id),
    FOREIGN KEY(profile_slug) REFERENCES coding_worker_profiles(slug)
);
CREATE TABLE IF NOT EXISTS coding_checkpoints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    worker_session_id INTEGER,
    sequence INTEGER NOT NULL,
    head_sha TEXT,
    status TEXT NOT NULL,
    handoff_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(session_id,sequence),
    FOREIGN KEY(session_id) REFERENCES coding_sessions(id),
    FOREIGN KEY(worker_session_id) REFERENCES coding_worker_sessions(id)
);
CREATE TABLE IF NOT EXISTS coding_assessments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    goal_id INTEGER,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(goal_id) REFERENCES development_goals(id)
);
CREATE TABLE IF NOT EXISTS development_sprints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    goal_id INTEGER NOT NULL,
    sequence INTEGER NOT NULL,
    title TEXT NOT NULL,
    objective TEXT NOT NULL,
    acceptance_criteria_json TEXT NOT NULL,
    budget_json TEXT NOT NULL,
    risk TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    session_id INTEGER,
    checkpoint_sha TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    UNIQUE(goal_id,sequence),
    FOREIGN KEY(goal_id) REFERENCES development_goals(id),
    FOREIGN KEY(session_id) REFERENCES coding_sessions(id)
);
CREATE TABLE IF NOT EXISTS coding_learning_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    outcome TEXT NOT NULL,
    stage TEXT NOT NULL,
    error_code TEXT NOT NULL DEFAULT '',
    worker_profile TEXT NOT NULL DEFAULT '',
    signature TEXT NOT NULL,
    evidence_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY(session_id) REFERENCES coding_sessions(id)
);
CREATE TABLE IF NOT EXISTS coding_playbooks (
    slug TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    kind TEXT NOT NULL,
    content_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'candidate',
    evidence_count INTEGER NOT NULL DEFAULT 0,
    replay_json TEXT NOT NULL DEFAULT '{}',
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS coding_runner_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id INTEGER NOT NULL,
    adapter TEXT NOT NULL,
    argv_json TEXT NOT NULL,
    cwd TEXT NOT NULL,
    allowed_env_json TEXT NOT NULL DEFAULT '[]',
    env_envelope_json TEXT NOT NULL DEFAULT '',
    timeout_seconds INTEGER NOT NULL,
    max_output_bytes INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    lease_owner TEXT,
    lease_expires_at TEXT,
    cancel_requested INTEGER NOT NULL DEFAULT 0,
    stdout TEXT,
    stderr TEXT,
    exit_code INTEGER,
    error_code TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    FOREIGN KEY(workflow_id) REFERENCES coding_sessions(id)
);
CREATE TABLE IF NOT EXISTS coding_runner_nodes (
    node_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    started_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS coding_runner_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL,
    sequence INTEGER NOT NULL,
    line TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(job_id,sequence),
    FOREIGN KEY(job_id) REFERENCES coding_runner_jobs(id)
);
CREATE INDEX IF NOT EXISTS idx_development_events_session_seq ON development_events(session_id,sequence);
CREATE INDEX IF NOT EXISTS idx_coding_sessions_state ON coding_sessions(state,updated_at);
CREATE INDEX IF NOT EXISTS idx_coding_stages_session ON coding_stages(session_id,position);
CREATE INDEX IF NOT EXISTS idx_development_goals_status ON development_goals(status,updated_at);
CREATE INDEX IF NOT EXISTS idx_worker_sessions_session ON coding_worker_sessions(session_id,status);
CREATE INDEX IF NOT EXISTS idx_checkpoints_session_seq ON coding_checkpoints(session_id,sequence);
CREATE INDEX IF NOT EXISTS idx_sprints_goal_status ON development_sprints(goal_id,status,sequence);
CREATE INDEX IF NOT EXISTS idx_learning_signature ON coding_learning_records(signature,created_at);
CREATE INDEX IF NOT EXISTS idx_runner_jobs_status ON coding_runner_jobs(status,created_at);
CREATE INDEX IF NOT EXISTS idx_runner_jobs_workflow ON coding_runner_jobs(workflow_id,id);
CREATE INDEX IF NOT EXISTS idx_runner_events_job_seq ON coding_runner_events(job_id,sequence);
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
            existing = {str(row[1]) for row in conn.execute("PRAGMA table_info(coding_sessions)")}
            additions = {
                "goal_id": "INTEGER",
                "plan_hash_snapshot": "TEXT",
                "criteria_snapshot_json": "TEXT NOT NULL DEFAULT '[]'",
                "validation_commands_json": "TEXT NOT NULL DEFAULT '[]'",
                "lease_owner": "TEXT",
                "lease_expires_at": "TEXT",
                "cancel_requested": "INTEGER NOT NULL DEFAULT 0",
            }
            for name, declaration in additions.items():
                if name not in existing:
                    conn.execute(f"ALTER TABLE coding_sessions ADD COLUMN {name} {declaration}")
            conn.execute("INSERT OR IGNORE INTO developer_schema_migrations(version,applied_at) VALUES (2,?)", (utc_now(),))
            session_additions = {
                "worker_profile_slug": "TEXT NOT NULL DEFAULT 'mc-native'",
                "reviewer_profile_slug": "TEXT NOT NULL DEFAULT 'reviewer-default'",
                "active_worker_session_id": "INTEGER",
                "assessment_id": "INTEGER",
                "current_sprint_id": "INTEGER",
                "sprint_budget_json": "TEXT NOT NULL DEFAULT '{}'",
                "v2_enabled": "INTEGER NOT NULL DEFAULT 1",
            }
            existing = {str(row[1]) for row in conn.execute("PRAGMA table_info(coding_sessions)")}
            for name, declaration in session_additions.items():
                if name not in existing:
                    conn.execute(f"ALTER TABLE coding_sessions ADD COLUMN {name} {declaration}")
            goal_additions = {
                "worker_profile_slug": "TEXT NOT NULL DEFAULT 'mc-native'",
                "reviewer_profile_slug": "TEXT NOT NULL DEFAULT 'reviewer-default'",
                "assessment_id": "INTEGER",
                "assessment_json": "TEXT NOT NULL DEFAULT '{}'",
                "budget_json": "TEXT NOT NULL DEFAULT '{}'",
            }
            existing = {str(row[1]) for row in conn.execute("PRAGMA table_info(development_goals)")}
            for name, declaration in goal_additions.items():
                if name not in existing:
                    conn.execute(f"ALTER TABLE development_goals ADD COLUMN {name} {declaration}")
            runner_existing = {
                str(row[1]) for row in conn.execute("PRAGMA table_info(coding_runner_jobs)")
            }
            if "env_envelope_json" not in runner_existing:
                conn.execute(
                    "ALTER TABLE coding_runner_jobs ADD COLUMN env_envelope_json TEXT NOT NULL DEFAULT ''"
                )
            now = utc_now()
            defaults = [
                ("mc-native", "MC Native", "native", "", "inherited", "", "reviewer-default", 1,
                 _json({"description": "Typed Mission Control tool worker"})),
                ("codex-chatgpt", "Codex (ChatGPT)", "codex", "", "native_login", "", "reviewer-default", 1,
                 _json({"sandbox": "workspace-write"})),
                ("opencode-glm", "OpenCode + GLM", "opencode", "zai-coding-plan/glm-5.2",
                  "vault_env", "ZAI_API_KEY", "reviewer-default", 1, _json({})),
                ("hermes-legacy", "Hermes (Legacy)", "hermes", "", "inherited", "",
                 "reviewer-default", 0, _json({"description": "Optional legacy CLI worker"})),
                ("reviewer-default", "Independent Reviewer", "model_review", "", "inherited", "",
                 "reviewer-default", 1, _json({})),
            ]
            conn.executemany(
                """INSERT OR IGNORE INTO coding_worker_profiles
                   (slug,name,adapter,model,auth_mode,credential_env,reviewer_profile,enabled,
                    config_json,created_at,updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                [(*item, now, now) for item in defaults],
            )
            conn.execute("INSERT OR IGNORE INTO developer_schema_migrations(version,applied_at) VALUES (3,?)", (now,))
            conn.execute("INSERT OR IGNORE INTO developer_schema_migrations(version,applied_at) VALUES (4,?)", (now,))
            migration_5 = conn.execute(
                "SELECT 1 FROM developer_schema_migrations WHERE version=5"
            ).fetchone()
            if not migration_5:
                conn.execute(
                    """UPDATE coding_worker_profiles
                       SET model='zai-coding-plan/glm-5.2',updated_at=?
                       WHERE slug='opencode-glm'
                         AND model='zai-coding-plan/glm-4.6'""",
                    (now,),
                )
                conn.execute(
                    "INSERT INTO developer_schema_migrations(version,applied_at) VALUES (5,?)",
                    (now,),
                )
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

    def create_session(
        self,
        task_id: int,
        policy_hash: str,
        idempotency_key: str,
        *,
        goal_id: int | None = None,
        plan_hash_snapshot: str | None = None,
        criteria_snapshot: Iterable[str] = (),
        validation_commands: Iterable[Iterable[str]] = (),
        worker_profile_slug: str = "mc-native",
        reviewer_profile_slug: str = "reviewer-default",
        assessment_id: int | None = None,
        current_sprint_id: int | None = None,
        sprint_budget: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = utc_now()
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute("SELECT * FROM coding_sessions WHERE idempotency_key=?", (idempotency_key,)).fetchone()
            if existing:
                if int(existing["task_id"]) != int(task_id):
                    raise RuntimeError("Idempotency key was already used for another development task.")
                conn.commit()
                return dict(existing)
            active = conn.execute(
                "SELECT id FROM coding_sessions WHERE state IN ('approved','preparing','coding','validating','reviewing','pushed','merging','deploying') LIMIT 1"
            ).fetchone()
            if active:
                raise RuntimeError(f"Coding workflow {active['id']} is already active.")
            cur = conn.execute(
                """INSERT INTO coding_sessions
                (task_id,state,stage,policy_hash,goal_id,plan_hash_snapshot,criteria_snapshot_json,
                 validation_commands_json,idempotency_key,worker_profile_slug,reviewer_profile_slug,
                 assessment_id,current_sprint_id,sprint_budget_json,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (task_id, "approved", "approved", policy_hash, goal_id, plan_hash_snapshot,
                 _json(list(criteria_snapshot)), _json([list(item) for item in validation_commands]),
                 idempotency_key, worker_profile_slug, reviewer_profile_slug, assessment_id,
                 current_sprint_id, _json(sprint_budget or {}), now, now),
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
            "lease_owner", "lease_expires_at",
            "cancel_requested",
            "worker_profile_slug", "reviewer_profile_slug", "active_worker_session_id",
            "assessment_id", "current_sprint_id", "sprint_budget_json", "v2_enabled",
            "criteria_snapshot_json",
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

    def claim_session(self, session_id: int, owner: str, lease_seconds: int = 120) -> bool:
        now = datetime.now(timezone.utc)
        expires = now + timedelta(seconds=max(30, lease_seconds))
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT lease_owner,lease_expires_at FROM coding_sessions WHERE id=?", (session_id,)).fetchone()
            if not row:
                raise KeyError(session_id)
            if row["lease_owner"] and row["lease_owner"] != owner and row["lease_expires_at"] and row["lease_expires_at"] > now.isoformat():
                conn.commit()
                return False
            conn.execute(
                "UPDATE coding_sessions SET lease_owner=?,lease_expires_at=?,updated_at=? WHERE id=?",
                (owner, expires.isoformat(), now.isoformat(), session_id),
            )
            conn.commit()
            return True
        finally:
            conn.close()

    def release_session(self, session_id: int, owner: str) -> None:
        conn = self.connect()
        try:
            conn.execute(
                "UPDATE coding_sessions SET lease_owner=NULL,lease_expires_at=NULL,updated_at=? WHERE id=? AND lease_owner=?",
                (utc_now(), session_id, owner),
            )
            conn.commit()
        finally:
            conn.close()

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

    def create_goal(
        self,
        *,
        title: str,
        objective: str,
        acceptance_criteria: Iterable[str],
        validation_commands: Iterable[Iterable[str]] = (),
        autonomy: str = "sandbox",
        preferred_models: Iterable[str] = (),
        max_iterations: int = 12,
        worker_profile_slug: str = "mc-native",
        reviewer_profile_slug: str = "reviewer-default",
        assessment_id: int | None = None,
        assessment: dict[str, Any] | None = None,
        budget: dict[str, Any] | None = None,
        status: str = "queued",
    ) -> dict[str, Any]:
        criteria = [str(item).strip() for item in acceptance_criteria if str(item).strip()]
        if not criteria:
            raise ValueError("At least one measurable acceptance criterion is required.")
        if autonomy not in {"sandbox", "pr", "merge_deploy"}:
            raise ValueError("Goal autonomy must be sandbox, pr, or merge_deploy.")
        now = utc_now()
        conn = self.connect()
        try:
            cur = conn.execute(
                """INSERT INTO development_goals
                   (title,objective,acceptance_criteria_json,validation_commands_json,autonomy,
                    preferred_models_json,status,max_iterations,worker_profile_slug,reviewer_profile_slug,
                    assessment_id,assessment_json,budget_json,created_at,updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (title.strip()[:240], objective.strip(), _json(criteria),
                 _json([list(item) for item in validation_commands]), autonomy,
                 _json([str(item) for item in preferred_models if str(item).strip()]),
                 status, max(1, min(int(max_iterations), 100)), worker_profile_slug,
                 reviewer_profile_slug, assessment_id, _json(assessment or {}),
                 _json(budget or {}), now, now),
            )
            conn.commit()
            return self.get_goal(int(cur.lastrowid)) or {}
        finally:
            conn.close()

    def get_goal(self, goal_id: int) -> dict[str, Any] | None:
        conn = self.connect()
        try:
            return self._row(conn.execute("SELECT * FROM development_goals WHERE id=?", (goal_id,)).fetchone())
        finally:
            conn.close()

    def list_goals(self, limit: int = 100) -> list[dict[str, Any]]:
        conn = self.connect()
        try:
            return [dict(row) for row in conn.execute(
                "SELECT * FROM development_goals ORDER BY updated_at DESC LIMIT ?", (max(1, min(limit, 500)),)
            )]
        finally:
            conn.close()

    def update_goal(self, goal_id: int, **fields: Any) -> dict[str, Any]:
        allowed = {"status", "iteration_count", "current_session_id", "last_error", "lease_owner",
                   "lease_expires_at", "completed_at", "worker_profile_slug",
                   "reviewer_profile_slug", "assessment_id", "assessment_json", "budget_json"}
        changes = {key: value for key, value in fields.items() if key in allowed}
        if not changes:
            goal = self.get_goal(goal_id)
            if not goal:
                raise KeyError(goal_id)
            return goal
        changes["updated_at"] = utc_now()
        conn = self.connect()
        try:
            sql = ",".join(f"{key}=?" for key in changes)
            cur = conn.execute(f"UPDATE development_goals SET {sql} WHERE id=?", (*changes.values(), goal_id))
            if cur.rowcount != 1:
                raise KeyError(goal_id)
            conn.commit()
        finally:
            conn.close()
        return self.get_goal(goal_id) or {}

    def claim_goal(self, owner: str, lease_seconds: int = 120) -> dict[str, Any] | None:
        now = datetime.now(timezone.utc)
        expires = now + timedelta(seconds=max(30, lease_seconds))
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                """SELECT * FROM development_goals
                   WHERE status IN ('queued','running','retrying')
                     AND (lease_expires_at IS NULL OR lease_expires_at<=? OR lease_owner=?)
                   ORDER BY created_at,id LIMIT 1""",
                (now.isoformat(), owner),
            ).fetchone()
            if not row:
                conn.commit()
                return None
            conn.execute(
                """UPDATE development_goals SET status='running',lease_owner=?,lease_expires_at=?,updated_at=?
                   WHERE id=?""",
                (owner, expires.isoformat(), now.isoformat(), row["id"]),
            )
            conn.commit()
            return self.get_goal(int(row["id"]))
        finally:
            conn.close()

    def renew_goal_lease(self, goal_id: int, owner: str, lease_seconds: int = 120) -> bool:
        expires = datetime.now(timezone.utc) + timedelta(seconds=max(30, lease_seconds))
        conn = self.connect()
        try:
            cur = conn.execute(
                "UPDATE development_goals SET lease_expires_at=?,updated_at=? WHERE id=? AND lease_owner=?",
                (expires.isoformat(), utc_now(), goal_id, owner),
            )
            conn.commit()
            return cur.rowcount == 1
        finally:
            conn.close()

    def release_goal_lease(self, goal_id: int, owner: str) -> None:
        conn = self.connect()
        try:
            conn.execute(
                "UPDATE development_goals SET lease_owner=NULL,lease_expires_at=NULL,updated_at=? WHERE id=? AND lease_owner=?",
                (utc_now(), goal_id, owner),
            )
            conn.commit()
        finally:
            conn.close()

    def add_goal_iteration(self, goal_id: int, session_id: int, iteration: int) -> dict[str, Any]:
        conn = self.connect()
        try:
            conn.execute(
                """INSERT OR IGNORE INTO goal_iterations(goal_id,session_id,iteration,state,created_at)
                   VALUES (?,?,?,'running',?)""",
                (goal_id, session_id, iteration, utc_now()),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM goal_iterations WHERE goal_id=? AND iteration=?", (goal_id, iteration)
            ).fetchone()
            return dict(row)
        finally:
            conn.close()

    def finish_goal_iteration(self, goal_id: int, iteration: int, state: str, result: dict[str, Any]) -> None:
        conn = self.connect()
        try:
            conn.execute(
                """UPDATE goal_iterations SET state=?,result_json=?,completed_at=?
                   WHERE goal_id=? AND iteration=?""",
                (state, _json(result), utc_now(), goal_id, iteration),
            )
            conn.commit()
        finally:
            conn.close()

    def rebind_goal_iteration(self, goal_id: int, iteration: int, session_id: int) -> None:
        conn = self.connect()
        try:
            conn.execute(
                """UPDATE goal_iterations
                   SET session_id=?,state='running',result_json=NULL,completed_at=NULL
                   WHERE goal_id=? AND iteration=?""",
                (session_id, goal_id, iteration),
            )
            conn.commit()
        finally:
            conn.close()

    def list_worker_profiles(self, *, enabled_only: bool = False) -> list[dict[str, Any]]:
        conn = self.connect()
        try:
            where = " WHERE enabled=1" if enabled_only else ""
            return [dict(row) for row in conn.execute(
                f"SELECT * FROM coding_worker_profiles{where} ORDER BY adapter,name"
            )]
        finally:
            conn.close()

    def get_worker_profile(self, slug: str) -> dict[str, Any] | None:
        conn = self.connect()
        try:
            return self._row(conn.execute(
                "SELECT * FROM coding_worker_profiles WHERE slug=?", (slug,)
            ).fetchone())
        finally:
            conn.close()

    def upsert_worker_profile(self, profile: dict[str, Any]) -> dict[str, Any]:
        now = utc_now()
        conn = self.connect()
        try:
            conn.execute(
                """INSERT INTO coding_worker_profiles
                   (slug,name,adapter,model,auth_mode,credential_env,reviewer_profile,enabled,
                    config_json,created_at,updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(slug) DO UPDATE SET
                     name=excluded.name,adapter=excluded.adapter,model=excluded.model,
                     auth_mode=excluded.auth_mode,credential_env=excluded.credential_env,
                     reviewer_profile=excluded.reviewer_profile,enabled=excluded.enabled,
                     config_json=excluded.config_json,updated_at=excluded.updated_at""",
                (
                    profile["slug"], profile["name"], profile["adapter"], profile.get("model", ""),
                    profile.get("auth_mode", "inherited"), profile.get("credential_env", ""),
                    profile.get("reviewer_profile", "reviewer-default"),
                    int(bool(profile.get("enabled", True))), _json(profile.get("config", {})), now, now,
                ),
            )
            conn.commit()
            return self.get_worker_profile(str(profile["slug"])) or {}
        finally:
            conn.close()

    def set_worker_health(self, slug: str, status: str, detail: str) -> dict[str, Any]:
        conn = self.connect()
        try:
            cur = conn.execute(
                """UPDATE coding_worker_profiles
                   SET health_status=?,health_detail=?,last_probed_at=?,updated_at=? WHERE slug=?""",
                (status, detail[:1000], utc_now(), utc_now(), slug),
            )
            if cur.rowcount != 1:
                raise KeyError(slug)
            conn.commit()
            return self.get_worker_profile(slug) or {}
        finally:
            conn.close()

    def create_worker_session(
        self,
        *,
        session_id: int,
        stage_id: str,
        profile_slug: str,
        adapter: str,
        model: str,
        external_session_id: str | None = None,
    ) -> dict[str, Any]:
        now = utc_now()
        conn = self.connect()
        try:
            cur = conn.execute(
                """INSERT INTO coding_worker_sessions
                   (session_id,stage_id,profile_slug,adapter,model,external_session_id,status,
                    started_at,updated_at)
                   VALUES (?,?,?,?,?,?,'running',?,?)""",
                (session_id, stage_id, profile_slug, adapter, model, external_session_id, now, now),
            )
            worker_id = int(cur.lastrowid)
            conn.execute(
                "UPDATE coding_sessions SET active_worker_session_id=?,updated_at=? WHERE id=?",
                (worker_id, now, session_id),
            )
            conn.commit()
            return dict(conn.execute(
                "SELECT * FROM coding_worker_sessions WHERE id=?", (worker_id,)
            ).fetchone())
        finally:
            conn.close()

    def get_worker_session(self, worker_session_id: int) -> dict[str, Any] | None:
        conn = self.connect()
        try:
            return self._row(conn.execute(
                "SELECT * FROM coding_worker_sessions WHERE id=?", (worker_session_id,)
            ).fetchone())
        finally:
            conn.close()

    def latest_worker_session(self, session_id: int) -> dict[str, Any] | None:
        conn = self.connect()
        try:
            return self._row(conn.execute(
                """SELECT * FROM coding_worker_sessions WHERE session_id=?
                   ORDER BY id DESC LIMIT 1""", (session_id,)
            ).fetchone())
        finally:
            conn.close()

    def update_worker_session(self, worker_session_id: int, **fields: Any) -> dict[str, Any]:
        allowed = {"external_session_id", "status", "error_code", "completed_at"}
        changes = {key: value for key, value in fields.items() if key in allowed}
        changes["updated_at"] = utc_now()
        conn = self.connect()
        try:
            sql = ",".join(f"{key}=?" for key in changes)
            cur = conn.execute(
                f"UPDATE coding_worker_sessions SET {sql} WHERE id=?",
                (*changes.values(), worker_session_id),
            )
            if cur.rowcount != 1:
                raise KeyError(worker_session_id)
            conn.commit()
            return self.get_worker_session(worker_session_id) or {}
        finally:
            conn.close()

    def close_worker_sessions(self, session_id: int, status: str = "superseded") -> None:
        conn = self.connect()
        try:
            conn.execute(
                """UPDATE coding_worker_sessions SET status=?,completed_at=?,updated_at=?
                   WHERE session_id=? AND status='running'""",
                (status, utc_now(), utc_now(), session_id),
            )
            conn.commit()
        finally:
            conn.close()

    def save_checkpoint(
        self,
        *,
        session_id: int,
        worker_session_id: int | None,
        head_sha: str | None,
        status: str,
        handoff: dict[str, Any],
    ) -> dict[str, Any]:
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            sequence = int(conn.execute(
                "SELECT COALESCE(MAX(sequence),0)+1 FROM coding_checkpoints WHERE session_id=?",
                (session_id,),
            ).fetchone()[0])
            cur = conn.execute(
                """INSERT INTO coding_checkpoints
                   (session_id,worker_session_id,sequence,head_sha,status,handoff_json,created_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (session_id, worker_session_id, sequence, head_sha, status, _json(handoff), utc_now()),
            )
            conn.commit()
            return dict(conn.execute(
                "SELECT * FROM coding_checkpoints WHERE id=?", (cur.lastrowid,)
            ).fetchone())
        finally:
            conn.close()

    def list_checkpoints(self, session_id: int, limit: int = 50) -> list[dict[str, Any]]:
        conn = self.connect()
        try:
            rows = conn.execute(
                """SELECT * FROM coding_checkpoints WHERE session_id=?
                   ORDER BY sequence DESC LIMIT ?""",
                (session_id, max(1, min(limit, 200))),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def latest_checkpoint(self, session_id: int) -> dict[str, Any] | None:
        items = self.list_checkpoints(session_id, 1)
        if not items:
            return None
        item = items[0]
        try:
            item["handoff"] = json.loads(item["handoff_json"])
        except json.JSONDecodeError:
            item["handoff"] = {}
        return item

    def create_assessment(self, payload: dict[str, Any], goal_id: int | None = None) -> dict[str, Any]:
        conn = self.connect()
        try:
            cur = conn.execute(
                "INSERT INTO coding_assessments(goal_id,payload_json,created_at) VALUES (?,?,?)",
                (goal_id, _json(payload), utc_now()),
            )
            conn.commit()
            return dict(conn.execute(
                "SELECT * FROM coding_assessments WHERE id=?", (cur.lastrowid,)
            ).fetchone())
        finally:
            conn.close()

    def attach_assessment(self, assessment_id: int, goal_id: int) -> None:
        conn = self.connect()
        try:
            conn.execute("UPDATE coding_assessments SET goal_id=? WHERE id=?", (goal_id, assessment_id))
            conn.commit()
        finally:
            conn.close()

    def get_assessment(self, assessment_id: int) -> dict[str, Any] | None:
        conn = self.connect()
        try:
            item = self._row(conn.execute(
                "SELECT * FROM coding_assessments WHERE id=?", (assessment_id,)
            ).fetchone())
            if item:
                item["payload"] = json.loads(item["payload_json"])
            return item
        finally:
            conn.close()

    def create_sprints(self, goal_id: int, sprints: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
        now = utc_now()
        conn = self.connect()
        try:
            for sprint in sprints:
                conn.execute(
                    """INSERT OR IGNORE INTO development_sprints
                       (goal_id,sequence,title,objective,acceptance_criteria_json,budget_json,
                        risk,status,created_at,updated_at)
                       VALUES (?,?,?,?,?,?,?,'pending',?,?)""",
                    (
                        goal_id, int(sprint["sequence"]), sprint["title"], sprint["objective"],
                        _json(sprint.get("acceptance_criteria", [])), _json(sprint.get("budget", {})),
                        sprint.get("risk", "medium"), now, now,
                    ),
                )
            conn.commit()
            return self.list_sprints(goal_id)
        finally:
            conn.close()

    def list_sprints(self, goal_id: int) -> list[dict[str, Any]]:
        conn = self.connect()
        try:
            return [dict(row) for row in conn.execute(
                "SELECT * FROM development_sprints WHERE goal_id=? ORDER BY sequence", (goal_id,)
            )]
        finally:
            conn.close()

    def get_sprint(self, sprint_id: int) -> dict[str, Any] | None:
        conn = self.connect()
        try:
            return self._row(conn.execute(
                "SELECT * FROM development_sprints WHERE id=?", (sprint_id,)
            ).fetchone())
        finally:
            conn.close()

    def next_sprint(self, goal_id: int) -> dict[str, Any] | None:
        conn = self.connect()
        try:
            return self._row(conn.execute(
                """SELECT * FROM development_sprints WHERE goal_id=? AND status='pending'
                   ORDER BY sequence LIMIT 1""", (goal_id,)
            ).fetchone())
        finally:
            conn.close()

    def update_sprint(self, sprint_id: int, **fields: Any) -> dict[str, Any]:
        allowed = {"status", "session_id", "checkpoint_sha", "completed_at"}
        changes = {key: value for key, value in fields.items() if key in allowed}
        changes["updated_at"] = utc_now()
        conn = self.connect()
        try:
            sql = ",".join(f"{key}=?" for key in changes)
            cur = conn.execute(
                f"UPDATE development_sprints SET {sql} WHERE id=?",
                (*changes.values(), sprint_id),
            )
            if cur.rowcount != 1:
                raise KeyError(sprint_id)
            conn.commit()
            return self.get_sprint(sprint_id) or {}
        finally:
            conn.close()

    def add_learning_record(
        self,
        *,
        session_id: int,
        outcome: str,
        stage: str,
        error_code: str,
        worker_profile: str,
        signature: str,
        evidence: dict[str, Any],
    ) -> dict[str, Any]:
        conn = self.connect()
        try:
            cur = conn.execute(
                """INSERT INTO coding_learning_records
                   (session_id,outcome,stage,error_code,worker_profile,signature,evidence_json,created_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (session_id, outcome, stage, error_code, worker_profile, signature,
                 _json(evidence), utc_now()),
            )
            conn.commit()
            return dict(conn.execute(
                "SELECT * FROM coding_learning_records WHERE id=?", (cur.lastrowid,)
            ).fetchone())
        finally:
            conn.close()

    def list_learning_records(
        self, *, signature: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        conn = self.connect()
        try:
            if signature:
                rows = conn.execute(
                    """SELECT * FROM coding_learning_records WHERE signature=?
                       ORDER BY id DESC LIMIT ?""",
                    (signature, max(1, min(limit, 1000))),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM coding_learning_records ORDER BY id DESC LIMIT ?",
                    (max(1, min(limit, 1000)),),
                ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def upsert_playbook(
        self,
        *,
        slug: str,
        title: str,
        kind: str,
        content: dict[str, Any],
        status: str,
        evidence_count: int,
    ) -> dict[str, Any]:
        now = utc_now()
        conn = self.connect()
        try:
            conn.execute(
                """INSERT INTO coding_playbooks
                   (slug,title,kind,content_json,status,evidence_count,created_at,updated_at)
                   VALUES (?,?,?,?,?,?,?,?)
                   ON CONFLICT(slug) DO UPDATE SET title=excluded.title,kind=excluded.kind,
                   content_json=excluded.content_json,status=excluded.status,
                   evidence_count=excluded.evidence_count,version=coding_playbooks.version+1,
                   updated_at=excluded.updated_at""",
                (slug, title, kind, _json(content), status, evidence_count, now, now),
            )
            conn.commit()
            return dict(conn.execute(
                "SELECT * FROM coding_playbooks WHERE slug=?", (slug,)
            ).fetchone())
        finally:
            conn.close()

    def list_playbooks(self, status: str | None = None) -> list[dict[str, Any]]:
        conn = self.connect()
        try:
            if status:
                rows = conn.execute(
                    "SELECT * FROM coding_playbooks WHERE status=? ORDER BY updated_at DESC", (status,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM coding_playbooks ORDER BY updated_at DESC"
                ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def update_playbook_replay(
        self, slug: str, *, status: str, replay: dict[str, Any]
    ) -> dict[str, Any]:
        conn = self.connect()
        try:
            cur = conn.execute(
                """UPDATE coding_playbooks SET status=?,replay_json=?,updated_at=?
                   WHERE slug=?""",
                (status, _json(replay), utc_now(), slug),
            )
            if cur.rowcount != 1:
                raise KeyError(slug)
            conn.commit()
            return dict(conn.execute(
                "SELECT * FROM coding_playbooks WHERE slug=?", (slug,)
            ).fetchone())
        finally:
            conn.close()

    def submit_runner_job(
        self,
        *,
        workflow_id: int,
        adapter: str,
        argv: list[str],
        cwd: str,
        allowed_env: list[str],
        timeout_seconds: int,
        max_output_bytes: int,
        env_envelope: str = "",
    ) -> dict[str, Any]:
        now = utc_now()
        conn = self.connect()
        try:
            cur = conn.execute(
                """INSERT INTO coding_runner_jobs
                   (workflow_id,adapter,argv_json,cwd,allowed_env_json,env_envelope_json,
                    timeout_seconds,max_output_bytes,status,created_at,updated_at)
                   VALUES (?,?,?,?,?,?,?,?,'queued',?,?)""",
                (
                    workflow_id, adapter, _json(argv), cwd, _json(allowed_env), env_envelope,
                    timeout_seconds, max_output_bytes, now, now,
                ),
            )
            conn.commit()
            return dict(conn.execute(
                "SELECT * FROM coding_runner_jobs WHERE id=?", (cur.lastrowid,)
            ).fetchone())
        finally:
            conn.close()

    def get_runner_job(self, job_id: int) -> dict[str, Any] | None:
        conn = self.connect()
        try:
            return self._row(conn.execute(
                "SELECT * FROM coding_runner_jobs WHERE id=?", (job_id,)
            ).fetchone())
        finally:
            conn.close()

    def add_runner_event(self, job_id: int, line: str) -> dict[str, Any]:
        text = str(line)[-4_000:]
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            sequence = int(conn.execute(
                "SELECT COALESCE(MAX(sequence),0)+1 FROM coding_runner_events WHERE job_id=?",
                (job_id,),
            ).fetchone()[0])
            cur = conn.execute(
                """INSERT INTO coding_runner_events(job_id,sequence,line,created_at)
                   VALUES (?,?,?,?)""",
                (job_id, sequence, text, utc_now()),
            )
            conn.execute(
                """DELETE FROM coding_runner_events WHERE job_id=? AND id NOT IN
                   (SELECT id FROM coding_runner_events WHERE job_id=?
                    ORDER BY sequence DESC LIMIT 500)""",
                (job_id, job_id),
            )
            conn.commit()
            return dict(conn.execute(
                "SELECT * FROM coding_runner_events WHERE id=?", (cur.lastrowid,)
            ).fetchone())
        finally:
            conn.close()

    def list_runner_events(
        self, job_id: int, *, after_sequence: int = 0, limit: int = 200
    ) -> list[dict[str, Any]]:
        conn = self.connect()
        try:
            return [dict(row) for row in conn.execute(
                """SELECT * FROM coding_runner_events
                   WHERE job_id=? AND sequence>? ORDER BY sequence LIMIT ?""",
                (job_id, max(0, after_sequence), max(1, min(limit, 500))),
            )]
        finally:
            conn.close()

    def latest_runner_job(self, workflow_id: int) -> dict[str, Any] | None:
        conn = self.connect()
        try:
            return self._row(conn.execute(
                """SELECT * FROM coding_runner_jobs WHERE workflow_id=?
                   ORDER BY id DESC LIMIT 1""",
                (workflow_id,),
            ).fetchone())
        finally:
            conn.close()

    def claim_runner_job(
        self, node_id: str, *, lease_seconds: int = 30
    ) -> dict[str, Any] | None:
        now = datetime.now(timezone.utc)
        lease_expires = (now + timedelta(seconds=max(10, lease_seconds))).isoformat()
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                """SELECT * FROM coding_runner_jobs
                   WHERE status='queued' AND cancel_requested=0
                   ORDER BY id LIMIT 1"""
            ).fetchone()
            if not row:
                conn.commit()
                return None
            cur = conn.execute(
                """UPDATE coding_runner_jobs
                   SET status='running',lease_owner=?,lease_expires_at=?,
                       started_at=COALESCE(started_at,?),updated_at=?
                   WHERE id=? AND status='queued'""",
                (node_id, lease_expires, now.isoformat(), now.isoformat(), row["id"]),
            )
            conn.commit()
            if cur.rowcount != 1:
                return None
            return self.get_runner_job(int(row["id"]))
        finally:
            conn.close()

    def heartbeat_runner_job(
        self, job_id: int, node_id: str, *, lease_seconds: int = 30
    ) -> bool:
        now = datetime.now(timezone.utc)
        expires = (now + timedelta(seconds=max(10, lease_seconds))).isoformat()
        conn = self.connect()
        try:
            cur = conn.execute(
                """UPDATE coding_runner_jobs SET lease_expires_at=?,updated_at=?
                   WHERE id=? AND status='running' AND lease_owner=?""",
                (expires, now.isoformat(), job_id, node_id),
            )
            conn.commit()
            return cur.rowcount == 1
        finally:
            conn.close()

    def finish_runner_job(
        self,
        job_id: int,
        *,
        status: str,
        stdout: str = "",
        stderr: str = "",
        exit_code: int | None = None,
        error_code: str | None = None,
    ) -> dict[str, Any]:
        if status not in {"completed", "failed", "canceled"}:
            raise ValueError("Runner job final status is invalid.")
        now = utc_now()
        conn = self.connect()
        try:
            cur = conn.execute(
                """UPDATE coding_runner_jobs SET status=?,stdout=?,stderr=?,exit_code=?,
                   error_code=?,lease_expires_at=NULL,updated_at=?,completed_at=?
                   WHERE id=? AND status IN ('queued','running')""",
                (status, stdout, stderr, exit_code, error_code, now, now, job_id),
            )
            if cur.rowcount != 1:
                raise KeyError(job_id)
            conn.commit()
            return self.get_runner_job(job_id) or {}
        finally:
            conn.close()

    def request_runner_cancel(self, workflow_id: int) -> bool:
        now = utc_now()
        conn = self.connect()
        try:
            queued = conn.execute(
                """UPDATE coding_runner_jobs SET status='canceled',cancel_requested=1,
                   error_code='owner_canceled',updated_at=?,completed_at=?
                   WHERE workflow_id=? AND status='queued'""",
                (now, now, workflow_id),
            ).rowcount
            running = conn.execute(
                """UPDATE coding_runner_jobs SET cancel_requested=1,updated_at=?
                   WHERE workflow_id=? AND status='running'""",
                (now, workflow_id),
            ).rowcount
            conn.commit()
            return bool(queued or running)
        finally:
            conn.close()

    def reconcile_runner_jobs(self) -> int:
        now = utc_now()
        conn = self.connect()
        try:
            cur = conn.execute(
                """UPDATE coding_runner_jobs SET status='failed',error_code='runner_lost',
                   stderr='Runner lease expired before the process reported completion.',
                   updated_at=?,completed_at=?
                   WHERE status='running' AND lease_expires_at IS NOT NULL
                     AND lease_expires_at < ?""",
                (now, now, now),
            )
            conn.commit()
            return int(cur.rowcount)
        finally:
            conn.close()

    def heartbeat_runner_node(
        self, node_id: str, *, status: str = "ready", metadata: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        now = utc_now()
        conn = self.connect()
        try:
            conn.execute(
                """INSERT INTO coding_runner_nodes
                   (node_id,status,metadata_json,started_at,last_seen_at)
                   VALUES (?,?,?,?,?)
                   ON CONFLICT(node_id) DO UPDATE SET status=excluded.status,
                   metadata_json=excluded.metadata_json,last_seen_at=excluded.last_seen_at""",
                (node_id, status, _json(metadata or {}), now, now),
            )
            conn.commit()
            return dict(conn.execute(
                "SELECT * FROM coding_runner_nodes WHERE node_id=?", (node_id,)
            ).fetchone())
        finally:
            conn.close()

    def list_runner_nodes(self, *, active_within_seconds: int = 30) -> list[dict[str, Any]]:
        threshold = (
            datetime.now(timezone.utc) - timedelta(seconds=max(1, active_within_seconds))
        ).isoformat()
        conn = self.connect()
        try:
            return [dict(row) for row in conn.execute(
                """SELECT * FROM coding_runner_nodes
                   WHERE status='ready' AND last_seen_at>=?
                   ORDER BY last_seen_at DESC""",
                (threshold,),
            )]
        finally:
            conn.close()

    def begin_command(self, key: str, target_type: str, target_id: int, command: str) -> dict[str, Any]:
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT * FROM development_commands WHERE idempotency_key=?", (key,)
            ).fetchone()
            if existing:
                item = dict(existing)
                if item["target_type"] != target_type or int(item["target_id"]) != target_id or item["command"] != command:
                    raise RuntimeError("Idempotency key was reused for a different command.")
                conn.commit()
                item["_claimed"] = False
                return item
            cur = conn.execute(
                """INSERT INTO development_commands
                   (idempotency_key,target_type,target_id,command,status,created_at)
                   VALUES (?,?,?,?, 'running', ?)""",
                (key, target_type, target_id, command, utc_now()),
            )
            conn.commit()
            item = dict(conn.execute("SELECT * FROM development_commands WHERE id=?", (cur.lastrowid,)).fetchone())
            item["_claimed"] = True
            return item
        finally:
            conn.close()

    def finish_command(self, key: str, response: dict[str, Any]) -> None:
        conn = self.connect()
        try:
            conn.execute(
                """UPDATE development_commands SET status='completed',response_json=?,completed_at=?
                   WHERE idempotency_key=?""",
                (_json(response), utc_now(), key),
            )
            conn.commit()
        finally:
            conn.close()

    def fail_command(self, key: str, error: dict[str, Any]) -> None:
        conn = self.connect()
        try:
            conn.execute(
                """UPDATE development_commands SET status='failed',response_json=?,completed_at=?
                   WHERE idempotency_key=?""",
                (_json(error), utc_now(), key),
            )
            conn.commit()
        finally:
            conn.close()

    def fail_stale_commands(self, max_age_seconds: int = 300) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=max(30, max_age_seconds))
        now = utc_now()
        conn = self.connect()
        try:
            cur = conn.execute(
                """UPDATE development_commands
                   SET status='failed',response_json=?,completed_at=?
                   WHERE status='running' AND created_at<=?""",
                (
                    _json({
                        "type": "RuntimeRestarted",
                        "message": "The command was interrupted before completion. Retry it safely.",
                    }),
                    now,
                    cutoff.isoformat(),
                ),
            )
            conn.commit()
            return int(cur.rowcount)
        finally:
            conn.close()

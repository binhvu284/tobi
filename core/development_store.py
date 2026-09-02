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

from core.coding_states import ACTIVE_STATES, CLEANUP_ELIGIBLE_STATES, TERMINAL_STATES, state_in_clause


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
    validation_commands_json TEXT NOT NULL DEFAULT '[]',
    worker_profile_slug TEXT NOT NULL DEFAULT 'deepseek-harness',
    reviewer_profile_slug TEXT NOT NULL DEFAULT 'reviewer-default',
    fallback_profiles_json TEXT NOT NULL DEFAULT '[]',
    owner_state TEXT NOT NULL DEFAULT 'Draft',
    legacy_hidden INTEGER NOT NULL DEFAULT 0,
    status_override INTEGER NOT NULL DEFAULT 0,
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
    validation_cycles INTEGER NOT NULL DEFAULT 0,
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
    archived_at TEXT,
    readiness_snapshot_id INTEGER,
    last_heartbeat_at TEXT,
    last_output_at TEXT,
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
    merged_at TEXT,
    merge_commit_sha TEXT,
    last_sync_status TEXT,
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
    completed_at TEXT,
    qualification_percent INTEGER NOT NULL DEFAULT 0,
    evidence_json TEXT NOT NULL DEFAULT '[]',
    gaps_json TEXT NOT NULL DEFAULT '[]',
    last_evaluated_at TEXT
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
    hidden INTEGER NOT NULL DEFAULT 0,
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
CREATE TABLE IF NOT EXISTS development_goal_task_links (
    goal_id INTEGER NOT NULL,
    task_id INTEGER NOT NULL,
    relation TEXT NOT NULL DEFAULT 'contributes',
    created_at TEXT NOT NULL,
    PRIMARY KEY(goal_id,task_id),
    FOREIGN KEY(goal_id) REFERENCES development_goals(id),
    FOREIGN KEY(task_id) REFERENCES development_tasks(id)
);
CREATE TABLE IF NOT EXISTS coding_readiness_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL,
    status TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    snapshot_hash TEXT NOT NULL,
    policy_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(task_id) REFERENCES development_tasks(id)
);
CREATE TABLE IF NOT EXISTS coding_stage_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    stage_id TEXT NOT NULL,
    attempt INTEGER NOT NULL,
    status TEXT NOT NULL,
    worker_profile_slug TEXT,
    started_at TEXT NOT NULL,
    heartbeat_at TEXT NOT NULL,
    last_output_at TEXT,
    completed_at TEXT,
    error_code TEXT,
    result_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(session_id,stage_id,attempt),
    FOREIGN KEY(session_id) REFERENCES coding_sessions(id)
);
CREATE TABLE IF NOT EXISTS coding_evidence_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER,
    task_id INTEGER NOT NULL,
    goal_id INTEGER,
    criterion_index INTEGER,
    kind TEXT NOT NULL,
    status TEXT NOT NULL,
    source TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY(session_id) REFERENCES coding_sessions(id),
    FOREIGN KEY(task_id) REFERENCES development_tasks(id),
    FOREIGN KEY(goal_id) REFERENCES development_goals(id)
);
CREATE TABLE IF NOT EXISTS coding_run_scorecards (
    session_id INTEGER PRIMARY KEY,
    payload_json TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(session_id) REFERENCES coding_sessions(id)
);
CREATE TABLE IF NOT EXISTS coding_acceptance_faults (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    scenario TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'armed',
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    triggered_at TEXT,
    cleared_at TEXT
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
CREATE INDEX IF NOT EXISTS idx_goal_task_links_task ON development_goal_task_links(task_id,goal_id);
CREATE INDEX IF NOT EXISTS idx_readiness_task_created ON coding_readiness_snapshots(task_id,created_at);
CREATE INDEX IF NOT EXISTS idx_stage_attempts_session ON coding_stage_attempts(session_id,stage_id,attempt);
CREATE INDEX IF NOT EXISTS idx_evidence_task_goal ON coding_evidence_records(task_id,goal_id,criterion_index);
CREATE INDEX IF NOT EXISTS idx_acceptance_faults_session ON coding_acceptance_faults(session_id,state,id);
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
                "worker_profile_slug": "TEXT NOT NULL DEFAULT 'deepseek-harness'",
                "reviewer_profile_slug": "TEXT NOT NULL DEFAULT 'reviewer-default'",
                "active_worker_session_id": "INTEGER",
                "assessment_id": "INTEGER",
                "current_sprint_id": "INTEGER",
                "sprint_budget_json": "TEXT NOT NULL DEFAULT '{}'",
                "v2_enabled": "INTEGER NOT NULL DEFAULT 1",
                "archived_at": "TEXT",
            }
            existing = {str(row[1]) for row in conn.execute("PRAGMA table_info(coding_sessions)")}
            for name, declaration in session_additions.items():
                if name not in existing:
                    conn.execute(f"ALTER TABLE coding_sessions ADD COLUMN {name} {declaration}")
            goal_additions = {
                "worker_profile_slug": "TEXT NOT NULL DEFAULT 'deepseek-harness'",
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
                ("deepseek-harness", "DeepSeek Harness", "deepseek", "deepseek:deepseek-v4-pro",
                 "inherited", "", "reviewer-default", 1,
                 _json({"avatar": "DS", "description": "Typed tool worker driven by the DeepSeek API"})),
                ("codex-chatgpt", "Codex (ChatGPT)", "codex", "", "native_login", "", "reviewer-default", 1,
                 _json({"sandbox": "workspace-write"})),
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
            migration_6 = conn.execute(
                "SELECT 1 FROM developer_schema_migrations WHERE version=6"
            ).fetchone()
            if not migration_6:
                task_additions = {
                    "validation_commands_json": "TEXT NOT NULL DEFAULT '[]'",
                    "worker_profile_slug": "TEXT NOT NULL DEFAULT 'deepseek-harness'",
                    "reviewer_profile_slug": "TEXT NOT NULL DEFAULT 'reviewer-default'",
                    "fallback_profiles_json": "TEXT NOT NULL DEFAULT '[]'",
                    "owner_state": "TEXT NOT NULL DEFAULT 'Draft'",
                    "legacy_hidden": "INTEGER NOT NULL DEFAULT 0",
                }
                existing = {str(row[1]) for row in conn.execute("PRAGMA table_info(development_tasks)")}
                for name, declaration in task_additions.items():
                    if name not in existing:
                        conn.execute(f"ALTER TABLE development_tasks ADD COLUMN {name} {declaration}")
                session_v6 = {
                    "readiness_snapshot_id": "INTEGER",
                    "last_heartbeat_at": "TEXT",
                    "last_output_at": "TEXT",
                }
                existing = {str(row[1]) for row in conn.execute("PRAGMA table_info(coding_sessions)")}
                for name, declaration in session_v6.items():
                    if name not in existing:
                        conn.execute(f"ALTER TABLE coding_sessions ADD COLUMN {name} {declaration}")
                goal_v6 = {
                    "qualification_percent": "INTEGER NOT NULL DEFAULT 0",
                    "evidence_json": "TEXT NOT NULL DEFAULT '[]'",
                    "gaps_json": "TEXT NOT NULL DEFAULT '[]'",
                    "last_evaluated_at": "TEXT",
                }
                existing = {str(row[1]) for row in conn.execute("PRAGMA table_info(development_goals)")}
                for name, declaration in goal_v6.items():
                    if name not in existing:
                        conn.execute(f"ALTER TABLE development_goals ADD COLUMN {name} {declaration}")
                conn.execute(
                    "UPDATE development_tasks SET legacy_hidden=1 WHERE queue_id>=900000000"
                )
                conn.execute(
                    """INSERT OR IGNORE INTO development_goal_task_links(goal_id,task_id,relation,created_at)
                       SELECT DISTINCT goal_id,task_id,'legacy_history',?
                       FROM coding_sessions WHERE goal_id IS NOT NULL""",
                    (now,),
                )
                conn.execute(
                    """UPDATE development_tasks SET owner_state=CASE
                         WHEN status='completed' THEN 'Done'
                         WHEN status IN ('deleted','canceled') THEN 'Canceled'
                         ELSE 'Ready' END"""
                )
                conn.execute(
                    "INSERT INTO developer_schema_migrations(version,applied_at) VALUES (6,?)",
                    (now,),
                )
            migration_7 = conn.execute(
                "SELECT 1 FROM developer_schema_migrations WHERE version=7"
            ).fetchone()
            if not migration_7:
                task_columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(development_tasks)")}
                if "status_override" not in task_columns:
                    conn.execute(
                        "ALTER TABLE development_tasks ADD COLUMN status_override INTEGER NOT NULL DEFAULT 0"
                    )
                conn.execute(
                    "INSERT INTO developer_schema_migrations(version,applied_at) VALUES (7,?)",
                    (now,),
                )
            migration_8 = conn.execute(
                "SELECT 1 FROM developer_schema_migrations WHERE version=8"
            ).fetchone()
            if not migration_8:
                pr_columns = {
                    str(row[1]) for row in conn.execute("PRAGMA table_info(coding_pull_requests)")
                }
                pr_additions = {
                    "merged_at": "TEXT",
                    "merge_commit_sha": "TEXT",
                    "last_sync_status": "TEXT",
                }
                for name, declaration in pr_additions.items():
                    if name not in pr_columns:
                        conn.execute(
                            f"ALTER TABLE coding_pull_requests ADD COLUMN {name} {declaration}"
                        )
                conn.execute(
                    "INSERT INTO developer_schema_migrations(version,applied_at) VALUES (8,?)",
                    (now,),
                )
            migration_9 = conn.execute(
                "SELECT 1 FROM developer_schema_migrations WHERE version=9"
            ).fetchone()
            if not migration_9:
                session_columns = {
                    str(row[1]) for row in conn.execute("PRAGMA table_info(coding_sessions)")
                }
                if "validation_cycles" not in session_columns:
                    conn.execute(
                        "ALTER TABLE coding_sessions ADD COLUMN validation_cycles INTEGER NOT NULL DEFAULT 0"
                    )
                # Earlier runtimes shared one counter between validation and review, and old
                # reviewer attempts did not receive valid new-file evidence. Give unfinished
                # runs a clean budget under the corrected contracts.
                conn.execute(
                    """UPDATE coding_sessions
                       SET validation_cycles=0,
                           review_cycles=0
                       WHERE completed_at IS NULL"""
                )
                conn.execute(
                    "INSERT INTO developer_schema_migrations(version,applied_at) VALUES (9,?)",
                    (now,),
                )
            migration_10 = conn.execute(
                "SELECT 1 FROM developer_schema_migrations WHERE version=10"
            ).fetchone()
            if not migration_10:
                profile_columns = {
                    str(row[1]) for row in conn.execute("PRAGMA table_info(coding_worker_profiles)")
                }
                if "hidden" not in profile_columns:
                    conn.execute(
                        "ALTER TABLE coding_worker_profiles "
                        "ADD COLUMN hidden INTEGER NOT NULL DEFAULT 0"
                    )
                # Mission Control's built-in worker and the OpenCode + GLM agent are retired in
                # favour of DeepSeek Harness. Their rows stay put -- coding_worker_sessions has a
                # foreign key onto this table, so deleting them would break the run history that
                # names them -- but they are hidden from the Agents page and can no longer be
                # selected or enabled.
                conn.execute(
                    """INSERT OR IGNORE INTO coding_worker_profiles
                       (slug,name,adapter,model,auth_mode,credential_env,reviewer_profile,
                        enabled,config_json,created_at,updated_at)
                       VALUES ('deepseek-harness','DeepSeek Harness','deepseek',
                               'deepseek:deepseek-v4-pro','inherited','','reviewer-default',1,
                               ?,?,?)""",
                    (
                        _json({
                            "avatar": "DS",
                            "description": "Typed tool worker driven by the DeepSeek API",
                        }),
                        now,
                        now,
                    ),
                )
                conn.execute(
                    """UPDATE coding_worker_profiles
                       SET hidden=1,enabled=0,updated_at=?
                       WHERE slug IN ('mc-native','opencode-glm')""",
                    (now,),
                )
                # Queue items and goals still pointing at a retired agent would otherwise fail
                # preflight with "agent unavailable" instead of simply running.
                for table in ("development_tasks", "development_goals"):
                    conn.execute(
                        f"""UPDATE {table} SET worker_profile_slug='deepseek-harness'
                            WHERE worker_profile_slug IN ('mc-native','opencode-glm')"""
                    )
                conn.execute(
                    "INSERT INTO developer_schema_migrations(version,applied_at) VALUES (10,?)",
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
        status = str(item.get("status", "planned"))
        owner_state = str(item.get("owner_state") or (
            "Done" if status == "completed" else "Canceled" if status in {"deleted", "canceled"} else "Ready"
        ))
        conn = self.connect()
        try:
            conn.execute(
                """INSERT INTO development_tasks
                (queue_id,title,plan_path,plan_hash,acceptance_criteria_json,dependencies_json,
                 status,risk,target_version,queue_status,queue_effort,validation_commands_json,
                 worker_profile_slug,reviewer_profile_slug,fallback_profiles_json,owner_state,
                  legacy_hidden,status_override,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(queue_id) DO UPDATE SET
                  title=excluded.title,plan_path=excluded.plan_path,plan_hash=excluded.plan_hash,
                  acceptance_criteria_json=excluded.acceptance_criteria_json,
                  dependencies_json=excluded.dependencies_json,
                  queue_status=CASE
                    WHEN development_tasks.status_override=1
                         AND development_tasks.status='completed'
                    THEN 'Done'
                    ELSE excluded.queue_status
                  END,
                  queue_effort=excluded.queue_effort,risk=excluded.risk,
                  target_version=COALESCE(development_tasks.target_version,excluded.target_version),
                  status=CASE WHEN development_tasks.status_override=1
                                   OR development_tasks.status IN ('approved','running')
                              THEN development_tasks.status ELSE excluded.status END,
                  owner_state=CASE WHEN development_tasks.status_override=1
                                        OR development_tasks.status IN ('approved','running')
                                   THEN development_tasks.owner_state ELSE excluded.owner_state END,
                  updated_at=excluded.updated_at""",
                (
                    int(item["queue_id"]), item["title"], item["plan_path"], item["plan_hash"],
                    _json(item.get("acceptance_criteria", [])), _json(item.get("dependencies", [])),
                    status, item.get("risk", "medium"), item.get("target_version"),
                    item.get("queue_status"), item.get("queue_effort"),
                    _json(item.get("validation_commands", [])),
                    item.get("worker_profile_slug", "deepseek-harness"),
                    item.get("reviewer_profile_slug", "reviewer-default"),
                    _json(item.get("fallback_profiles", [])), owner_state,
                    int(bool(item.get("legacy_hidden", False))),
                    int(bool(item.get("status_override", False))), now, now,
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
            return [dict(row) for row in conn.execute(
                """SELECT * FROM development_tasks
                   WHERE status<>'deleted' AND legacy_hidden=0 ORDER BY queue_id DESC"""
            )]
        finally:
            conn.close()

    def set_task_status(
        self, queue_id: int, status: str, *, override_source: bool = False
    ) -> dict[str, Any] | None:
        owner_state = {
            "completed": "Done", "canceled": "Canceled", "deleted": "Canceled",
            "failed": "Failed", "blocked": "Needs Action", "paused": "Paused",
            "approved": "Running", "running": "Running", "planned": "Ready",
        }.get(status, "Draft")
        conn = self.connect()
        try:
            conn.execute(
                """UPDATE development_tasks
                   SET status=?,owner_state=?,status_override=?,updated_at=? WHERE queue_id=?""",
                (status, owner_state, int(override_source), utc_now(), queue_id),
            )
            conn.commit()
            return self._row(conn.execute(
                "SELECT * FROM development_tasks WHERE queue_id=?", (queue_id,)
            ).fetchone())
        finally:
            conn.close()

    def approve_task_for_workflow(self, task_id: int, target_version: str) -> dict[str, Any]:
        conn = self.connect()
        try:
            cur = conn.execute(
                """UPDATE development_tasks
                   SET status='approved',owner_state='Running',status_override=0,
                       target_version=?,updated_at=? WHERE id=?""",
                (target_version, utc_now(), task_id),
            )
            if cur.rowcount != 1:
                raise KeyError(task_id)
            conn.commit()
            return dict(conn.execute(
                "SELECT * FROM development_tasks WHERE id=?", (task_id,)
            ).fetchone())
        finally:
            conn.close()

    def set_task_owner_state(self, task_id: int, owner_state: str) -> dict[str, Any]:
        conn = self.connect()
        try:
            cur = conn.execute(
                "UPDATE development_tasks SET owner_state=?,updated_at=? WHERE id=?",
                (owner_state, utc_now(), task_id),
            )
            if cur.rowcount != 1:
                raise KeyError(task_id)
            conn.commit()
            return dict(conn.execute(
                "SELECT * FROM development_tasks WHERE id=?", (task_id,)
            ).fetchone())
        finally:
            conn.close()

    def complete_task(self, task_id: int, *, queue_status: str = "Done") -> dict[str, Any]:
        conn = self.connect()
        try:
            cur = conn.execute(
                """UPDATE development_tasks
                   SET status='completed',owner_state='Done',queue_status=?,
                       status_override=1,updated_at=? WHERE id=?""",
                (queue_status, utc_now(), task_id),
            )
            if cur.rowcount != 1:
                raise KeyError(task_id)
            conn.commit()
            return dict(conn.execute(
                "SELECT * FROM development_tasks WHERE id=?", (task_id,)
            ).fetchone())
        finally:
            conn.close()

    def active_session_for_task(self, task_id: int) -> int | None:
        clause, params = state_in_clause("state", ACTIVE_STATES)
        conn = self.connect()
        try:
            row = conn.execute(
                f"SELECT id FROM coding_sessions WHERE task_id=? AND {clause} LIMIT 1",
                (task_id, *params),
            ).fetchone()
            return int(row["id"]) if row else None
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

    def configure_task(
        self,
        queue_id: int,
        *,
        worker_profile_slug: str,
        reviewer_profile_slug: str,
        fallback_profiles: Iterable[str] = (),
        validation_commands: Iterable[Iterable[str]] = (),
        owner_state: str | None = None,
    ) -> dict[str, Any]:
        now = utc_now()
        fallbacks = [str(item) for item in fallback_profiles if str(item).strip()]
        commands = [list(item) for item in validation_commands]
        conn = self.connect()
        try:
            fields = [
                "worker_profile_slug=?", "reviewer_profile_slug=?",
                "fallback_profiles_json=?", "validation_commands_json=?", "updated_at=?",
            ]
            values: list[Any] = [
                worker_profile_slug, reviewer_profile_slug, _json(fallbacks), _json(commands), now,
            ]
            if owner_state:
                fields.append("owner_state=?")
                values.append(owner_state)
            values.append(queue_id)
            cur = conn.execute(
                f"UPDATE development_tasks SET {','.join(fields)} WHERE queue_id=?",
                values,
            )
            if cur.rowcount != 1:
                raise KeyError(queue_id)
            conn.commit()
            row = conn.execute("SELECT * FROM development_tasks WHERE queue_id=?", (queue_id,)).fetchone()
            return dict(row)
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
        worker_profile_slug: str = "deepseek-harness",
        reviewer_profile_slug: str = "reviewer-default",
        assessment_id: int | None = None,
        current_sprint_id: int | None = None,
        sprint_budget: dict[str, Any] | None = None,
        readiness_snapshot_id: int | None = None,
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
            clause, params = state_in_clause("state", TERMINAL_STATES)
            active = conn.execute(
                f"SELECT id FROM coding_sessions WHERE NOT {clause} LIMIT 1", params
            ).fetchone()
            if active:
                raise RuntimeError(f"Coding workflow {active['id']} is already active.")
            cur = conn.execute(
                """INSERT INTO coding_sessions
                (task_id,state,stage,policy_hash,goal_id,plan_hash_snapshot,criteria_snapshot_json,
                 validation_commands_json,idempotency_key,worker_profile_slug,reviewer_profile_slug,
                 assessment_id,current_sprint_id,sprint_budget_json,readiness_snapshot_id,
                 last_heartbeat_at,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (task_id, "approved", "approved", policy_hash, goal_id, plan_hash_snapshot,
                 _json(list(criteria_snapshot)), _json([list(item) for item in validation_commands]),
                 idempotency_key, worker_profile_slug, reviewer_profile_slug, assessment_id,
                 current_sprint_id, _json(sprint_budget or {}), readiness_snapshot_id, now, now, now),
            )
            conn.commit()
            return dict(conn.execute("SELECT * FROM coding_sessions WHERE id=?", (cur.lastrowid,)).fetchone())
        finally:
            conn.close()

    def get_session(self, session_id: int) -> dict[str, Any] | None:
        conn = self.connect()
        try:
            row = conn.execute(
                """SELECT s.*,t.queue_id,t.title,t.plan_path,t.plan_hash,t.target_version,t.risk,
                          t.owner_state,t.fallback_profiles_json,t.validation_commands_json AS task_validation_commands_json
                   FROM coding_sessions s JOIN development_tasks t ON t.id=s.task_id WHERE s.id=?""",
                (session_id,),
            ).fetchone()
            return self._row(row)
        finally:
            conn.close()

    def active_session_id(self) -> int | None:
        """The one workflow the owner is watching, found without building the other fifty.

        The overview endpoint used to load every session in full and pick the first
        non-terminal one from the result, which cost ~500 queries to answer a question that
        is a single indexed lookup.
        """
        clause, params = state_in_clause("state", TERMINAL_STATES)
        conn = self.connect()
        try:
            row = conn.execute(
                f"SELECT id FROM coding_sessions WHERE archived_at IS NULL AND NOT {clause} "
                "ORDER BY updated_at DESC LIMIT 1", params,
            ).fetchone()
            return int(row["id"]) if row else None
        finally:
            conn.close()

    def list_sessions(self, limit: int = 50) -> list[dict[str, Any]]:
        conn = self.connect()
        try:
            rows = conn.execute(
                """SELECT s.*,t.queue_id,t.title,t.plan_path,t.target_version,t.risk,t.owner_state,
                          t.fallback_profiles_json
                   FROM coding_sessions s JOIN development_tasks t ON t.id=s.task_id
                   WHERE s.archived_at IS NULL
                   ORDER BY s.updated_at DESC LIMIT ?""",
                (max(1, min(limit, 200)),),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def update_session(self, session_id: int, **fields: Any) -> dict[str, Any]:
        allowed = {
            "state", "stage", "branch", "worktree", "base_sha", "head_sha", "worker_pid",
            "progress", "blocker", "validation_cycles", "review_cycles", "error_code", "completed_at",
            "lease_owner", "lease_expires_at",
            "cancel_requested",
            "worker_profile_slug", "reviewer_profile_slug", "active_worker_session_id",
            "assessment_id", "current_sprint_id", "sprint_budget_json", "v2_enabled",
            "criteria_snapshot_json",
            "archived_at",
            "readiness_snapshot_id", "last_heartbeat_at", "last_output_at",
            "policy_hash", "plan_hash_snapshot", "validation_commands_json",
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

    def _reset_stages(
        self,
        session_id: int,
        node_ids: tuple[str, ...],
        *,
        clear_results: bool = False,
        clear_checks: bool = False,
    ) -> None:
        if not node_ids:
            return
        assignments = ["status='pending'", "started_at=NULL", "completed_at=NULL"]
        if clear_results:
            assignments.append("result_json=NULL")
        if clear_checks:
            assignments.append("checks_json='[]'")
        placeholders = ",".join("?" for _ in node_ids)
        conn = self.connect()
        try:
            conn.execute(
                f"UPDATE coding_stages SET {','.join(assignments)} "
                f"WHERE session_id=? AND node_id IN ({placeholders})",
                (session_id, *node_ids),
            )
            conn.commit()
        finally:
            conn.close()

    def reset_stages_for_replan(self, session_id: int, *, has_worktree: bool) -> None:
        nodes = (
            ("code", "validate", "review", "commit", "scan", "push", "pull_request",
             "merge_deploy", "health")
            if has_worktree else
            ("prepare", "index", "code", "validate", "review", "commit", "scan", "push",
             "pull_request", "merge_deploy", "health")
        )
        self._reset_stages(session_id, nodes, clear_results=True)

    def reset_stages_for_worker_switch(self, session_id: int) -> None:
        self._reset_stages(session_id, (
            "code", "validate", "review", "commit", "scan", "push", "pull_request",
        ))

    def reset_stages_for_next_sprint(self, session_id: int) -> None:
        self._reset_stages(
            session_id, ("code", "validate", "review", "commit"),
            clear_results=True, clear_checks=True,
        )

    def reset_stages_for_base_reconciliation(self, session_id: int) -> None:
        self._reset_stages(
            session_id, ("scan", "push", "pull_request", "merge_deploy", "health"),
            clear_results=True,
        )

    def reset_stages_for_recode(self, session_id: int) -> None:
        self._reset_stages(session_id, (
            "code", "validate", "review", "commit", "scan", "push", "pull_request",
        ))

    def prepare_session_retry(self, session_id: int, *, reset_recode: bool) -> None:
        clause, params = state_in_clause("state", ACTIVE_STATES)
        conn = self.connect()
        try:
            active = conn.execute(
                f"SELECT id FROM coding_sessions WHERE id<>? AND {clause} LIMIT 1",
                (session_id, *params),
            ).fetchone()
            if active:
                raise RuntimeError(f"Coding workflow {active['id']} is already active.")
            if reset_recode:
                conn.execute(
                    """UPDATE coding_stages SET status='pending',started_at=NULL,completed_at=NULL
                       WHERE session_id=? AND node_id IN
                       ('code','validate','review','commit','scan','push','pull_request')""",
                    (session_id,),
                )
            conn.commit()
        finally:
            conn.close()

    def reset_stages_after_approval_rejection(self, session_id: int) -> None:
        self._reset_stages(
            session_id,
            ("code", "validate", "review", "commit", "scan", "push", "pull_request",
             "merge_deploy", "health"),
            clear_results=True,
        )

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

    def get_artifact(self, session_id: int, artifact_id: int) -> dict[str, Any] | None:
        conn = self.connect()
        try:
            row = conn.execute(
                "SELECT * FROM coding_artifacts WHERE session_id=? AND id=?",
                (int(session_id), int(artifact_id)),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def storage_cleanup_counts(self, *, now: str, cutoff: str) -> dict[str, int]:
        artifact_clause, states = state_in_clause("s.state", CLEANUP_ELIGIBLE_STATES)
        session_clause, _ = state_in_clause("state", CLEANUP_ELIGIBLE_STATES)
        conn = self.connect()
        try:
            artifacts = int(conn.execute(
                f"""SELECT COUNT(*) FROM coding_artifacts a
                    JOIN coding_sessions s ON s.id=a.session_id
                    WHERE a.retain_until<=? AND a.cleanup_eligible=0 AND {artifact_clause}""",
                (now, *states),
            ).fetchone()[0])
            worktrees = int(conn.execute(
                f"""SELECT COUNT(*) FROM coding_sessions WHERE {session_clause}
                    AND completed_at<=? AND worktree IS NOT NULL""",
                (*states, cutoff),
            ).fetchone()[0])
            return {"artifacts": artifacts, "worktrees": worktrees}
        finally:
            conn.close()

    def cleanup_candidates(self, *, now: str, cutoff: str) -> dict[str, list[dict[str, Any]]]:
        artifact_clause, states = state_in_clause("s.state", CLEANUP_ELIGIBLE_STATES)
        session_clause, _ = state_in_clause("state", CLEANUP_ELIGIBLE_STATES)
        conn = self.connect()
        try:
            artifacts = [dict(row) for row in conn.execute(
                f"""SELECT a.* FROM coding_artifacts a
                    JOIN coding_sessions s ON s.id=a.session_id
                    WHERE a.retain_until<=? AND a.cleanup_eligible=0 AND {artifact_clause}""",
                (now, *states),
            ).fetchall()]
            sessions = [dict(row) for row in conn.execute(
                f"""SELECT * FROM coding_sessions WHERE {session_clause}
                    AND completed_at<=? AND worktree IS NOT NULL""",
                (*states, cutoff),
            ).fetchall()]
            return {"artifacts": artifacts, "sessions": sessions}
        finally:
            conn.close()

    def mark_artifact_cleaned(self, artifact_id: int) -> None:
        conn = self.connect()
        try:
            conn.execute(
                "UPDATE coding_artifacts SET cleanup_eligible=1 WHERE id=?", (artifact_id,)
            )
            conn.commit()
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
        worker_profile_slug: str = "deepseek-harness",
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
                """SELECT * FROM development_goals
                   WHERE status<>'deleted' ORDER BY updated_at DESC LIMIT ?""",
                (max(1, min(limit, 500)),)
            )]
        finally:
            conn.close()

    def update_goal(self, goal_id: int, **fields: Any) -> dict[str, Any]:
        allowed = {"status", "iteration_count", "current_session_id", "last_error", "lease_owner",
                   "lease_expires_at", "completed_at", "worker_profile_slug",
                   "reviewer_profile_slug", "assessment_id", "assessment_json", "budget_json",
                   "qualification_percent", "evidence_json", "gaps_json", "last_evaluated_at"}
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

    def link_goal_task(self, goal_id: int, task_id: int, relation: str = "contributes") -> dict[str, Any]:
        now = utc_now()
        conn = self.connect()
        try:
            conn.execute(
                """INSERT INTO development_goal_task_links(goal_id,task_id,relation,created_at)
                   VALUES (?,?,?,?) ON CONFLICT(goal_id,task_id) DO UPDATE SET relation=excluded.relation""",
                (goal_id, task_id, relation, now),
            )
            conn.commit()
            row = conn.execute(
                """SELECT l.*,t.queue_id,t.title,t.status,t.owner_state
                   FROM development_goal_task_links l JOIN development_tasks t ON t.id=l.task_id
                   WHERE l.goal_id=? AND l.task_id=?""",
                (goal_id, task_id),
            ).fetchone()
            return dict(row)
        finally:
            conn.close()

    def unlink_goal_task(self, goal_id: int, task_id: int) -> None:
        conn = self.connect()
        try:
            conn.execute(
                "DELETE FROM development_goal_task_links WHERE goal_id=? AND task_id=?",
                (goal_id, task_id),
            )
            conn.commit()
        finally:
            conn.close()

    def list_goal_task_links(
        self, *, goal_id: int | None = None, task_id: int | None = None
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if goal_id is not None:
            clauses.append("l.goal_id=?")
            params.append(goal_id)
        if task_id is not None:
            clauses.append("l.task_id=?")
            params.append(task_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        conn = self.connect()
        try:
            rows = conn.execute(
                f"""SELECT l.*,t.queue_id,t.title,t.status,t.owner_state,t.legacy_hidden,
                           g.title AS goal_title,g.status AS goal_status,
                           g.qualification_percent
                    FROM development_goal_task_links l
                    JOIN development_tasks t ON t.id=l.task_id
                    JOIN development_goals g ON g.id=l.goal_id
                    {where} ORDER BY l.created_at,l.goal_id,l.task_id""",
                params,
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def save_readiness(
        self, task_id: int, status: str, payload: dict[str, Any], policy_hash: str
    ) -> dict[str, Any]:
        encoded = _json(payload)
        digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        now = utc_now()
        conn = self.connect()
        try:
            cur = conn.execute(
                """INSERT INTO coding_readiness_snapshots
                   (task_id,status,payload_json,snapshot_hash,policy_hash,created_at)
                   VALUES (?,?,?,?,?,?)""",
                (task_id, status, encoded, digest, policy_hash, now),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM coding_readiness_snapshots WHERE id=?", (cur.lastrowid,)
            ).fetchone()
            result = dict(row)
            result["payload"] = json.loads(result.pop("payload_json"))
            return result
        finally:
            conn.close()

    def get_readiness(self, readiness_id: int) -> dict[str, Any] | None:
        conn = self.connect()
        try:
            row = conn.execute(
                "SELECT * FROM coding_readiness_snapshots WHERE id=?", (readiness_id,)
            ).fetchone()
            if not row:
                return None
            result = dict(row)
            result["payload"] = json.loads(result.pop("payload_json"))
            return result
        finally:
            conn.close()

    def start_stage_attempt(
        self, session_id: int, stage_id: str, attempt: int, worker_profile_slug: str | None = None
    ) -> dict[str, Any]:
        now = utc_now()
        conn = self.connect()
        try:
            conn.execute(
                """INSERT INTO coding_stage_attempts
                   (session_id,stage_id,attempt,status,worker_profile_slug,started_at,heartbeat_at)
                   VALUES (?,?,?,?,?,?,?)
                   ON CONFLICT(session_id,stage_id,attempt) DO UPDATE SET
                     status='running',worker_profile_slug=excluded.worker_profile_slug,
                     heartbeat_at=excluded.heartbeat_at,completed_at=NULL,error_code=NULL""",
                (session_id, stage_id, attempt, "running", worker_profile_slug, now, now),
            )
            conn.execute(
                "UPDATE coding_sessions SET last_heartbeat_at=?,updated_at=? WHERE id=?",
                (now, now, session_id),
            )
            conn.commit()
            row = conn.execute(
                """SELECT * FROM coding_stage_attempts
                   WHERE session_id=? AND stage_id=? AND attempt=?""",
                (session_id, stage_id, attempt),
            ).fetchone()
            return dict(row)
        finally:
            conn.close()

    def heartbeat_stage_attempt(
        self, session_id: int, stage_id: str, *, output: bool = False
    ) -> None:
        now = utc_now()
        conn = self.connect()
        try:
            output_sql = ",last_output_at=?" if output else ""
            params: list[Any] = [now]
            if output:
                params.append(now)
            params.extend([session_id, stage_id])
            conn.execute(
                f"""UPDATE coding_stage_attempts SET heartbeat_at=?{output_sql}
                    WHERE id=(SELECT id FROM coding_stage_attempts
                              WHERE session_id=? AND stage_id=? ORDER BY attempt DESC LIMIT 1)""",
                params,
            )
            if output:
                conn.execute(
                    """UPDATE coding_sessions SET last_heartbeat_at=?,last_output_at=?,updated_at=?
                       WHERE id=?""",
                    (now, now, now, session_id),
                )
            else:
                conn.execute(
                    "UPDATE coding_sessions SET last_heartbeat_at=?,updated_at=? WHERE id=?",
                    (now, now, session_id),
                )
            conn.commit()
        finally:
            conn.close()

    def finish_stage_attempt(
        self,
        session_id: int,
        stage_id: str,
        *,
        status: str,
        error_code: str | None = None,
        result: dict[str, Any] | None = None,
    ) -> None:
        now = utc_now()
        conn = self.connect()
        try:
            conn.execute(
                """UPDATE coding_stage_attempts
                   SET status=?,error_code=?,result_json=?,heartbeat_at=?,completed_at=?
                   WHERE id=(SELECT id FROM coding_stage_attempts
                             WHERE session_id=? AND stage_id=? ORDER BY attempt DESC LIMIT 1)""",
                (status, error_code, _json(result or {}), now, now, session_id, stage_id),
            )
            conn.commit()
        finally:
            conn.close()

    def stage_attempt_timing(
        self, session_id: int, *, now: datetime | None = None
    ) -> dict[str, Any]:
        """Return durable active work time without counting pauses between attempts."""
        current = now or datetime.now(timezone.utc)
        conn = self.connect()
        try:
            rows = conn.execute(
                """SELECT status,started_at,completed_at
                   FROM coding_stage_attempts WHERE session_id=? ORDER BY id""",
                (session_id,),
            ).fetchall()
        finally:
            conn.close()

        active_seconds = 0.0
        running_since: datetime | None = None
        for row in rows:
            try:
                started = datetime.fromisoformat(str(row["started_at"]).replace("Z", "+00:00"))
                if started.tzinfo is None:
                    started = started.replace(tzinfo=timezone.utc)
            except (TypeError, ValueError):
                continue
            completed_raw = row["completed_at"]
            if completed_raw:
                try:
                    completed = datetime.fromisoformat(str(completed_raw).replace("Z", "+00:00"))
                    if completed.tzinfo is None:
                        completed = completed.replace(tzinfo=timezone.utc)
                except (TypeError, ValueError):
                    continue
                active_seconds += max(0.0, (completed - started).total_seconds())
            elif row["status"] == "running":
                # One foreground run is an invariant. If stale rows exist, use only the
                # latest start so a corrupt attempt cannot inflate the owner-facing timer.
                if running_since is None or started > running_since:
                    running_since = started

        return {
            "active_seconds": int(active_seconds),
            "timer_started_at": running_since.isoformat() if running_since else None,
            "measured_at": current.isoformat(),
        }

    def reconcile_stage_attempts(self, session_id: int) -> int:
        """Close stale attempts when the durable stage already has a terminal result."""
        now = utc_now()
        conn = self.connect()
        try:
            cur = conn.execute(
                """UPDATE coding_stage_attempts
                   SET status=(
                         SELECT CASE cs.status
                           WHEN 'completed' THEN 'completed'
                           WHEN 'failed' THEN 'failed'
                           WHEN 'paused' THEN 'paused'
                           ELSE coding_stage_attempts.status END
                         FROM coding_stages cs
                         WHERE cs.session_id=coding_stage_attempts.session_id
                           AND cs.node_id=coding_stage_attempts.stage_id
                       ),
                       result_json=COALESCE(NULLIF(result_json,'{}'),(
                         SELECT COALESCE(cs.result_json,'{}') FROM coding_stages cs
                         WHERE cs.session_id=coding_stage_attempts.session_id
                           AND cs.node_id=coding_stage_attempts.stage_id
                       )),
                       heartbeat_at=?,completed_at=?
                   WHERE session_id=? AND status='running'
                     AND EXISTS (
                       SELECT 1 FROM coding_stages cs
                       WHERE cs.session_id=coding_stage_attempts.session_id
                         AND cs.node_id=coding_stage_attempts.stage_id
                         AND cs.status IN ('completed','failed','paused')
                     )""",
                (now, now, session_id),
            )
            conn.commit()
            return int(cur.rowcount)
        finally:
            conn.close()

    def arm_acceptance_fault(
        self, session_id: int, scenario: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        now = utc_now()
        conn = self.connect()
        try:
            conn.execute(
                """UPDATE coding_acceptance_faults SET state='cleared',cleared_at=?
                   WHERE session_id=? AND state='armed'""",
                (now, session_id),
            )
            cur = conn.execute(
                """INSERT INTO coding_acceptance_faults
                   (session_id,scenario,state,payload_json,created_at)
                   VALUES (?,?,'armed',?,?)""",
                (session_id, scenario, _json(payload or {}), now),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM coding_acceptance_faults WHERE id=?", (cur.lastrowid,)
            ).fetchone()
            return dict(row)
        finally:
            conn.close()

    def consume_acceptance_fault(self, session_id: int, scenario: str) -> dict[str, Any] | None:
        now = utc_now()
        conn = self.connect()
        try:
            row = conn.execute(
                """SELECT * FROM coding_acceptance_faults
                   WHERE session_id=? AND scenario=? AND state='armed'
                   ORDER BY id DESC LIMIT 1""",
                (session_id, scenario),
            ).fetchone()
            if not row:
                return None
            cur = conn.execute(
                """UPDATE coding_acceptance_faults SET state='triggered',triggered_at=?
                   WHERE id=? AND state='armed'""",
                (now, row["id"]),
            )
            conn.commit()
            return dict(row) if cur.rowcount == 1 else None
        finally:
            conn.close()

    def list_acceptance_faults(self, session_id: int) -> list[dict[str, Any]]:
        conn = self.connect()
        try:
            rows = conn.execute(
                """SELECT * FROM coding_acceptance_faults
                   WHERE session_id=? ORDER BY id DESC""",
                (session_id,),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def add_evidence(
        self,
        *,
        task_id: int,
        kind: str,
        status: str,
        source: str,
        payload: dict[str, Any],
        session_id: int | None = None,
        goal_id: int | None = None,
        criterion_index: int | None = None,
    ) -> dict[str, Any]:
        conn = self.connect()
        try:
            cur = conn.execute(
                """INSERT INTO coding_evidence_records
                   (session_id,task_id,goal_id,criterion_index,kind,status,source,payload_json,created_at)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (session_id, task_id, goal_id, criterion_index, kind, status, source,
                 _json(payload), utc_now()),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM coding_evidence_records WHERE id=?", (cur.lastrowid,)).fetchone()
            result = dict(row)
            result["payload"] = json.loads(result.pop("payload_json"))
            return result
        finally:
            conn.close()

    def list_evidence(
        self, *, session_id: int | None = None, task_id: int | None = None, goal_id: int | None = None
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        for column, value in (("session_id", session_id), ("task_id", task_id), ("goal_id", goal_id)):
            if value is not None:
                clauses.append(f"{column}=?")
                params.append(value)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        conn = self.connect()
        try:
            rows = conn.execute(
                f"SELECT * FROM coding_evidence_records {where} ORDER BY created_at,id", params
            ).fetchall()
            result = []
            for row in rows:
                item = dict(row)
                item["payload"] = json.loads(item.pop("payload_json"))
                result.append(item)
            return result
        finally:
            conn.close()

    def save_scorecard(self, session_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        now = utc_now()
        conn = self.connect()
        try:
            conn.execute(
                """INSERT INTO coding_run_scorecards(session_id,payload_json,updated_at)
                   VALUES (?,?,?) ON CONFLICT(session_id) DO UPDATE SET
                     payload_json=excluded.payload_json,updated_at=excluded.updated_at""",
                (session_id, _json(payload), now),
            )
            conn.commit()
            return {"session_id": session_id, "payload": payload, "updated_at": now}
        finally:
            conn.close()

    def get_scorecard(self, session_id: int) -> dict[str, Any] | None:
        conn = self.connect()
        try:
            row = conn.execute(
                "SELECT * FROM coding_run_scorecards WHERE session_id=?", (session_id,)
            ).fetchone()
            if not row:
                return None
            result = dict(row)
            result["payload"] = json.loads(result.pop("payload_json"))
            return result
        finally:
            conn.close()

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
        """Selectable agents only. Retired agents keep their row so run history still
        resolves, but they never reappear on the Agents page or in a worker choice."""
        conn = self.connect()
        try:
            where = " WHERE hidden=0" + (" AND enabled=1" if enabled_only else "")
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
                   content_json=excluded.content_json,
                   status=CASE WHEN coding_playbooks.status='active'
                               THEN 'active' ELSE excluded.status END,
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

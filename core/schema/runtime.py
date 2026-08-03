"""Additive SQLite schema for Mission Control Runtime V2."""
from __future__ import annotations

import sqlite3
import threading


RUNTIME_SCHEMA_VERSIONS = ("mc-runtime-v2-001", "mc-runtime-v2-002")
RUNTIME_SCHEMA_VERSION = RUNTIME_SCHEMA_VERSIONS[-1]
_SCHEMA_LOCK = threading.Lock()
_RUNTIME_TABLES = {
    "mc_run_events",
    "mc_change_events",
    "mc_runtime_projections",
    "mc_system_entities",
    "mc_system_edges",
    "mc_runs",
    "mc_run_steps",
    "mc_loop_recipes",
    "mc_loop_runs",
}


_STATEMENTS = (
    """CREATE TABLE IF NOT EXISTS schema_migrations (
        version TEXT PRIMARY KEY,
        applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS mc_run_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id TEXT NOT NULL UNIQUE,
        run_id TEXT NOT NULL,
        sequence INTEGER NOT NULL CHECK (sequence > 0),
        event_type TEXT NOT NULL,
        stage TEXT NOT NULL,
        actor TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        payload_hash TEXT NOT NULL,
        trace_id TEXT,
        parent_span_id TEXT,
        contract_version TEXT NOT NULL DEFAULT '1',
        created_at TEXT NOT NULL,
        UNIQUE (run_id, sequence)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_mc_run_events_stream ON mc_run_events(run_id, sequence)",
    "CREATE INDEX IF NOT EXISTS idx_mc_run_events_trace ON mc_run_events(trace_id)",
    """CREATE TABLE IF NOT EXISTS mc_change_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id TEXT NOT NULL UNIQUE,
        sequence INTEGER NOT NULL UNIQUE CHECK (sequence > 0),
        change_type TEXT NOT NULL,
        subject_type TEXT NOT NULL,
        subject_id TEXT NOT NULL,
        actor TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        payload_hash TEXT NOT NULL,
        contract_version TEXT NOT NULL DEFAULT '1',
        created_at TEXT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_mc_change_events_subject ON mc_change_events(subject_type, subject_id, sequence)",
    """CREATE TABLE IF NOT EXISTS mc_runtime_projections (
        projection_type TEXT NOT NULL,
        projection_key TEXT NOT NULL,
        projection_version TEXT NOT NULL,
        last_sequence INTEGER NOT NULL DEFAULT 0,
        state_json TEXT NOT NULL,
        state_hash TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (projection_type, projection_key)
    )""",
    """CREATE TABLE IF NOT EXISTS mc_system_entities (
        entity_id TEXT PRIMARY KEY,
        entity_type TEXT NOT NULL,
        canonical_key TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        status TEXT NOT NULL,
        version TEXT NOT NULL,
        owner_domain TEXT NOT NULL,
        source_ref TEXT NOT NULL,
        observed_at TEXT NOT NULL,
        metadata_json TEXT NOT NULL,
        source_sequence INTEGER NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS mc_system_edges (
        edge_id TEXT PRIMARY KEY,
        from_entity_id TEXT NOT NULL,
        edge_type TEXT NOT NULL,
        to_entity_id TEXT NOT NULL,
        version TEXT NOT NULL,
        evidence_refs_json TEXT NOT NULL,
        confidence REAL NOT NULL,
        valid_from TEXT,
        valid_to TEXT,
        source_sequence INTEGER NOT NULL
    )""",
    """CREATE TRIGGER IF NOT EXISTS mc_run_events_update_immutable
        BEFORE UPDATE ON mc_run_events BEGIN
            SELECT RAISE(ABORT, 'mc_run_events is append-only');
        END""",
    """CREATE TRIGGER IF NOT EXISTS mc_run_events_delete_immutable
        BEFORE DELETE ON mc_run_events BEGIN
            SELECT RAISE(ABORT, 'mc_run_events is append-only');
        END""",
    """CREATE TRIGGER IF NOT EXISTS mc_change_events_update_immutable
        BEFORE UPDATE ON mc_change_events BEGIN
            SELECT RAISE(ABORT, 'mc_change_events is append-only');
        END""",
    """CREATE TRIGGER IF NOT EXISTS mc_change_events_delete_immutable
        BEFORE DELETE ON mc_change_events BEGIN
            SELECT RAISE(ABORT, 'mc_change_events is append-only');
        END""",
    """CREATE TABLE IF NOT EXISTS mc_runs (
        run_id TEXT PRIMARY KEY,
        request_id TEXT NOT NULL UNIQUE,
        request_hash TEXT NOT NULL,
        request_json TEXT NOT NULL,
        owner_id TEXT NOT NULL,
        session_id TEXT NOT NULL,
        surface TEXT NOT NULL,
        mode TEXT NOT NULL,
        objective TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN (
            'accepted', 'routing', 'clarifying', 'planned', 'waiting_approval',
            'running', 'waiting_external', 'recovering', 'waiting_owner',
            'succeeded', 'failed', 'cancelled'
        )),
        version INTEGER NOT NULL DEFAULT 1 CHECK (version > 0),
        plan_id TEXT,
        plan_version TEXT,
        plan_hash TEXT,
        budget_profile TEXT NOT NULL,
        budget_json TEXT NOT NULL DEFAULT '{}',
        contract_version TEXT NOT NULL DEFAULT '1',
        legacy_run_id TEXT,
        legacy_action_id TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        completed_at TEXT
    )""",
    "CREATE INDEX IF NOT EXISTS idx_mc_runs_status_time ON mc_runs(status, updated_at)",
    "CREATE INDEX IF NOT EXISTS idx_mc_runs_session ON mc_runs(session_id, created_at)",
    """CREATE TABLE IF NOT EXISTS mc_run_steps (
        run_id TEXT NOT NULL,
        step_id TEXT NOT NULL,
        plan_version TEXT NOT NULL,
        position INTEGER NOT NULL CHECK (position >= 0),
        kind TEXT NOT NULL,
        tool_name TEXT,
        arguments_json TEXT NOT NULL DEFAULT '{}',
        depends_on_json TEXT NOT NULL DEFAULT '[]',
        risk TEXT NOT NULL,
        timeout_s INTEGER NOT NULL DEFAULT 0 CHECK (timeout_s >= 0),
        retry_policy TEXT NOT NULL,
        idempotency_key TEXT,
        required_capabilities_json TEXT NOT NULL DEFAULT '[]',
        output_contract_json TEXT NOT NULL DEFAULT '{}',
        status TEXT NOT NULL DEFAULT 'pending',
        attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        started_at TEXT,
        completed_at TEXT,
        PRIMARY KEY (run_id, step_id),
        UNIQUE (run_id, position),
        FOREIGN KEY (run_id) REFERENCES mc_runs(run_id)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_mc_run_steps_runnable ON mc_run_steps(status, run_id, position)",
    "CREATE INDEX IF NOT EXISTS idx_mc_run_steps_idempotency ON mc_run_steps(idempotency_key)",
    """CREATE TABLE IF NOT EXISTS mc_loop_recipes (
        recipe_id TEXT NOT NULL,
        version TEXT NOT NULL,
        name TEXT NOT NULL,
        loop_type TEXT NOT NULL,
        contract_json TEXT NOT NULL,
        contract_hash TEXT NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY (recipe_id, version)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_mc_loop_recipes_type ON mc_loop_recipes(loop_type, recipe_id, version)",
    """CREATE TABLE IF NOT EXISTS mc_loop_runs (
        run_id TEXT PRIMARY KEY,
        recipe_id TEXT NOT NULL,
        recipe_version TEXT NOT NULL,
        policy_id TEXT NOT NULL,
        policy_version TEXT NOT NULL,
        policy_decision_id TEXT NOT NULL,
        loop_type TEXT NOT NULL,
        policy_json TEXT NOT NULL,
        policy_hash TEXT NOT NULL,
        owner_override_json TEXT NOT NULL DEFAULT '{}',
        enabled INTEGER NOT NULL DEFAULT 0 CHECK (enabled IN (0, 1)),
        iteration INTEGER NOT NULL DEFAULT 0 CHECK (iteration >= 0),
        status TEXT NOT NULL DEFAULT 'accepted',
        stop_reason TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (run_id) REFERENCES mc_runs(run_id),
        FOREIGN KEY (recipe_id, recipe_version) REFERENCES mc_loop_recipes(recipe_id, version)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_mc_loop_runs_status ON mc_loop_runs(status, updated_at)",
    """CREATE TRIGGER IF NOT EXISTS mc_loop_recipes_update_guard
        BEFORE UPDATE ON mc_loop_recipes BEGIN
            SELECT RAISE(ABORT, 'mc_loop_recipes versions are immutable');
        END""",
    """CREATE TRIGGER IF NOT EXISTS mc_loop_recipes_delete_guard
        BEFORE DELETE ON mc_loop_recipes BEGIN
            SELECT RAISE(ABORT, 'mc_loop_recipes versions are immutable');
        END""",
    """CREATE TRIGGER IF NOT EXISTS mc_loop_runs_policy_guard
        BEFORE UPDATE OF recipe_id, recipe_version, policy_id, policy_version,
                         policy_decision_id, loop_type, policy_json, policy_hash,
                         owner_override_json, enabled
        ON mc_loop_runs BEGIN
            SELECT RAISE(ABORT, 'effective loop policy snapshots are immutable');
        END""",
    """CREATE TRIGGER IF NOT EXISTS mc_loop_runs_delete_guard
        BEFORE DELETE ON mc_loop_runs BEGIN
            SELECT RAISE(ABORT, 'effective loop policy snapshots are immutable');
        END""",
)


def _schema_is_ready(conn: sqlite3.Connection) -> bool:
    ledger = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
    ).fetchone()
    if ledger is None:
        return False
    versions = {
        row[0]
        for row in conn.execute(
            "SELECT version FROM schema_migrations WHERE version LIKE 'mc-runtime-v2-%'"
        ).fetchall()
    }
    if not set(RUNTIME_SCHEMA_VERSIONS).issubset(versions):
        return False
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name GLOB 'mc_*'"
        ).fetchall()
    }
    return _RUNTIME_TABLES.issubset(tables)


def _apply_runtime_schema(conn: sqlite3.Connection) -> None:
    conn.execute("SAVEPOINT mc_runtime_schema")
    try:
        for statement in _STATEMENTS:
            conn.execute(statement)
        conn.executemany(
            "INSERT OR IGNORE INTO schema_migrations (version) VALUES (?)",
            [(version,) for version in RUNTIME_SCHEMA_VERSIONS],
        )
        conn.execute("RELEASE SAVEPOINT mc_runtime_schema")
    except Exception:
        conn.execute("ROLLBACK TO SAVEPOINT mc_runtime_schema")
        conn.execute("RELEASE SAVEPOINT mc_runtime_schema")
        raise


def _ensure_runtime_schema(conn: sqlite3.Connection) -> None:
    """Create Runtime V2 tables without modifying any legacy runtime table."""
    if _schema_is_ready(conn):
        return
    with _SCHEMA_LOCK:
        if not _schema_is_ready(conn):
            _apply_runtime_schema(conn)

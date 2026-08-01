"""Additive SQLite schema for Mission Control Runtime V2 event history."""
from __future__ import annotations

import sqlite3
import threading


RUNTIME_SCHEMA_VERSION = "mc-runtime-v2-001"
_SCHEMA_LOCK = threading.Lock()
_RUNTIME_TABLES = {
    "mc_run_events",
    "mc_change_events",
    "mc_runtime_projections",
    "mc_system_entities",
    "mc_system_edges",
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
)


def _schema_is_ready(conn: sqlite3.Connection) -> bool:
    ledger = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
    ).fetchone()
    if ledger is None:
        return False
    version = conn.execute(
        "SELECT 1 FROM schema_migrations WHERE version=?", (RUNTIME_SCHEMA_VERSION,)
    ).fetchone()
    if version is None:
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
        conn.execute(
            "INSERT OR IGNORE INTO schema_migrations (version) VALUES (?)",
            (RUNTIME_SCHEMA_VERSION,),
        )
        conn.execute("RELEASE SAVEPOINT mc_runtime_schema")
    except Exception:
        conn.execute("ROLLBACK TO SAVEPOINT mc_runtime_schema")
        conn.execute("RELEASE SAVEPOINT mc_runtime_schema")
        raise


def _ensure_runtime_schema(conn: sqlite3.Connection) -> None:
    """Create T02 tables without modifying any existing runtime table."""
    if _schema_is_ready(conn):
        return
    with _SCHEMA_LOCK:
        if not _schema_is_ready(conn):
            _apply_runtime_schema(conn)

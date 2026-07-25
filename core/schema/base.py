"""Shared DDL helper for the per-domain schema modules.

Extracted from core/database.py (Phase 4b). core/database.py stays the single entry
point — it imports every _ensure_*_schema back and init_database calls them in the
same order; only the DDL text moved, one module per domain.
"""
from __future__ import annotations

import sqlite3  # noqa: F401 - used in type hints

def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {r[1] for r in rows}


def _ensure_column(conn: sqlite3.Connection, table: str, name: str, ddl: str) -> None:
    if name in _table_columns(conn, table):
        return
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")

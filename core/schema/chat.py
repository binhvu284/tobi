"""Premium Chat schema (#8): sessions and messages.

Extracted verbatim from core/database.py (Phase 4b) — see core/schema/base.py.
"""
from __future__ import annotations

import sqlite3

def _ensure_chat_schema(conn: sqlite3.Connection) -> None:
    """Premium Chat (#8): vault-backed LLM routing config + multi-model chat sessions.
    The owning modules also create these lazily, so this is just an eager boot pass."""
    try:
        from core import chat_store
        chat_store.ensure_schema(conn)
    except Exception:
        pass
    try:
        from core import usage
        usage.ensure_schema(conn)
    except Exception:
        pass
    conn.execute(
        "CREATE TABLE IF NOT EXISTS llm_config ("
        "id INTEGER PRIMARY KEY CHECK (id=1), config_json TEXT, updated_at TEXT)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS owner_settings ("
        "key TEXT PRIMARY KEY, value TEXT, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP)"
    )
    conn.execute(
        "INSERT OR IGNORE INTO owner_settings (key, value) VALUES ('timezone', 'Asia/Ho_Chi_Minh')"
    )

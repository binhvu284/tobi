"""Shared primitives for the Mission Control API surface.

Extracted from ``api/dashboard.py`` (refactor Slice 0) so that route groups
peeled into ``api/routers/*`` can import the same DB connection, JSON, and
formatting helpers without importing the dashboard module. Behavior is
identical to the original definitions — this is a pure move.

See ``docs/REFACTORING_PLAN.md``.
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException

# The SQLite database path. Read from the environment at import time so both the
# server (which loads .env) and direct CLI imports resolve consistently.
DB_PATH = os.path.expanduser(os.getenv("DB_PATH", "~/.mmo_agent/agent.db"))

# Repo-root/logs. Defined here (api/deps.py) so it resolves the same as when it
# lived in api/dashboard.py — both modules sit in api/, one level below the root.
LOGS_DIR = Path(__file__).parent.parent / "logs"


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _json_loads(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def _last(conn: sqlite3.Connection, query: str) -> str | None:
    """Scalar helper: first column of the first row, or None. Shared by agents,
    abilities, and health 'last active' readouts."""
    try:
        row = conn.execute(query).fetchone()
        return row[0] if row and row[0] else None
    except sqlite3.Error:
        return None


def fmt_ago(ts_str: str | None) -> str | None:
    """Human-readable 'time ago' from an ISO timestamp. Shared by /api/agents + /api/health."""
    if not ts_str:
        return None
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc) if dt.tzinfo else datetime.now()
        delta = now - dt
        mins = int(delta.total_seconds() / 60)
        if mins < 1:
            return "just now"
        if mins < 60:
            return f"{mins}m ago"
        hours = mins // 60
        if hours < 24:
            return f"{hours}h ago"
        return f"{hours // 24}d ago"
    except Exception:
        return ts_str


def _vault_guard(token: str | None) -> None:
    """Require an unlocked vault session for protected endpoints. Shared by the vault,
    integrations, keys, and llm-key routes (lifted from dashboard.py so those groups
    can move into api/routers/* without importing the dashboard module)."""
    from core import vault
    if not vault.CRYPTO_AVAILABLE:
        raise HTTPException(status_code=503, detail="Vault unavailable — 'cryptography' is not installed.")
    try:
        vault.require_session(token)
    except vault.VaultLocked as e:
        raise HTTPException(status_code=401, detail=str(e))

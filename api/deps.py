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
from typing import Any

# The SQLite database path. Read from the environment at import time so both the
# server (which loads .env) and direct CLI imports resolve consistently.
DB_PATH = os.path.expanduser(os.getenv("DB_PATH", "~/.mmo_agent/agent.db"))


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

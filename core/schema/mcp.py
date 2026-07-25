"""MCP hub schema (#5): servers, tools, activity, peers.

Extracted verbatim from core/database.py (Phase 4b) — see core/schema/base.py.
"""
from __future__ import annotations

import sqlite3

def _ensure_mcp_schema(conn: sqlite3.Connection) -> None:
    """MCP Hub (#5) — TOBI as MCP server (inbound) + client (outbound). Idempotent.

    Inbound client tokens are stored hashed (never the raw token). Outbound
    connection credentials live in the Genesis vault (auth_ref → vault_secrets).
    See core/mcp_server.py (server), core/mcp_security.py (authn/scopes/audit).
    """
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS mcp_server_config (
        id            INTEGER PRIMARY KEY CHECK (id = 1),
        enabled       INTEGER NOT NULL DEFAULT 1,
        transport     TEXT NOT NULL DEFAULT 'streamable_http',
        public_url    TEXT,
        tunnel_status TEXT DEFAULT 'off',
        auth_modes_json TEXT DEFAULT '["token"]',   -- token | oauth (oauth = M4)
        rate_limit_json TEXT DEFAULT '{"per_minute":60}',
        updated_at    DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS mcp_clients (              -- inbound peers
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        name        TEXT NOT NULL,
        auth_type   TEXT NOT NULL DEFAULT 'token',        -- token | oauth
        token_hash  TEXT,                                 -- sha256(token); raw shown once
        scopes_json TEXT NOT NULL DEFAULT '["*"]',        -- allowed tool names or ["*"]
        status      TEXT NOT NULL DEFAULT 'active',       -- active | revoked
        created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
        last_seen   DATETIME
    );

    CREATE TABLE IF NOT EXISTS mcp_connections (          -- outbound servers (M2)
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        name          TEXT NOT NULL,
        transport     TEXT NOT NULL DEFAULT 'http',       -- http | stdio | sse | a2a
        endpoint      TEXT,                               -- url or command
        auth_ref      TEXT,                               -- vault_secrets.name
        enabled       INTEGER NOT NULL DEFAULT 1,
        status        TEXT DEFAULT 'unknown',
        last_tested_at DATETIME,
        tools_count   INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS mcp_tools (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        source      TEXT NOT NULL,                        -- 'self' | connection id
        name        TEXT NOT NULL,
        schema_json TEXT,
        enabled     INTEGER NOT NULL DEFAULT 1,
        permission  TEXT NOT NULL DEFAULT 'allow',        -- allow | ask | deny
        scopes_json TEXT,
        UNIQUE(source, name)
    );

    CREATE TABLE IF NOT EXISTS mcp_call_log (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        ts           DATETIME DEFAULT CURRENT_TIMESTAMP,
        direction    TEXT NOT NULL,                       -- in | out
        peer         TEXT,                                -- client/connection name
        tool         TEXT,
        status       TEXT,                                -- ok | denied | error | pending
        latency_ms   INTEGER,
        request_json TEXT,
        response_json TEXT,
        error        TEXT
    );

    CREATE TABLE IF NOT EXISTS mcp_approvals (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        client     TEXT,
        tool       TEXT,
        args_json  TEXT,
        status     TEXT NOT NULL DEFAULT 'pending',       -- pending | approved | rejected
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        decided_at DATETIME
    );

    CREATE TABLE IF NOT EXISTS a2a_agents (               -- A2A peers + own card (M4)
        id        INTEGER PRIMARY KEY AUTOINCREMENT,
        name      TEXT NOT NULL,
        card_json TEXT,
        endpoint  TEXT,
        status    TEXT DEFAULT 'unknown',
        is_self   INTEGER NOT NULL DEFAULT 0
    );

    CREATE INDEX IF NOT EXISTS idx_mcp_call_log_ts   ON mcp_call_log(ts);
    CREATE INDEX IF NOT EXISTS idx_mcp_approvals_st  ON mcp_approvals(status);
    """)
    # M4 additive columns (idempotent — ignore if they already exist).
    for ddl in (
        "ALTER TABLE mcp_server_config ADD COLUMN oauth_json TEXT",
        "ALTER TABLE mcp_server_config ADD COLUMN exposed INTEGER NOT NULL DEFAULT 0",
    ):
        try:
            conn.execute(ddl)
        except Exception:
            pass

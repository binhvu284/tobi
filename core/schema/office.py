"""The Office schema: agents, missions, workflows (+ seeds).

Extracted verbatim from core/database.py (Phase 4b) — see core/schema/base.py.
"""
from __future__ import annotations

import sqlite3
import json

_SEED_AGENTS = [
    # id,        name,       role,                provider,     model,                        key_ref,             color,     sprite,     autonomy, can_spawn, is_head
    ("tobi",     "Tobi",     "Head / Orchestrator","anthropic",  "claude-opus-4-20250514",     "ANTHROPIC_API_KEY", "#58a6ff", "tobi",     "high",   1,         1),
    ("sunday",   "Sunday",   "Research",          "openrouter", "google/gemini-pro-3",        "OPENROUTER_API_KEY","#3fb950", "research", "medium", 0,         0),
    ("alphabet", "Alphabet", "Evaluator",         "openai",     "gpt-5.5",                    "OPENAI_API_KEY",    "#d29922", "ceo",      "medium", 0,         0),
    ("friday",   "Friday",   "Coder",             "anthropic",  "claude-opus-4-20250514",     "ANTHROPIC_API_KEY", "#8b5cf6", "coder",    "medium", 0,         0),
]


_SEED_WORKFLOW = {
    "name": "standard_delivery",
    "version": 1,
    "steps": [
        {"agent_id": "sunday",   "action": "research"},
        {"agent_id": "alphabet", "action": "evaluate"},
        {"agent_id": "friday",   "action": "build"},
    ],
}


def _ensure_office_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
    -- ── AGENTS (persona + model binding + perms; D22/D25/D26) ──
    CREATE TABLE IF NOT EXISTS agents (
        id                  TEXT    PRIMARY KEY,    -- agent key
        name                TEXT    NOT NULL,
        role                TEXT,
        persona             TEXT,
        provider            TEXT    DEFAULT 'openrouter',  -- openrouter|anthropic|openai|google|mock
        model               TEXT,
        key_ref             TEXT,                   -- env var NAME holding the API key (D37 — name only)
        temperature         REAL    DEFAULT 0.7,
        max_tokens          INTEGER DEFAULT 2000,
        autonomy            TEXT    DEFAULT 'medium',     -- low|medium|high (D25)
        can_spawn           INTEGER DEFAULT 0,             -- reserved for head (D68)
        daily_budget_tokens INTEGER DEFAULT 0,             -- 0 = unlimited
        skills_json         TEXT,                          -- list of skill ids
        perms_json          TEXT,                          -- tools/permissions
        color               TEXT,
        sprite              TEXT,                          -- scene character key
        is_head             INTEGER DEFAULT 0,
        status              TEXT    DEFAULT 'active',       -- active|archived
        created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at          DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    -- ── AGENT_STATE (runtime; D64) ────────────────────────────
    CREATE TABLE IF NOT EXISTS agent_state (
        agent_id            TEXT    PRIMARY KEY REFERENCES agents(id) ON DELETE CASCADE,
        runtime_status      TEXT    DEFAULT 'idle',         -- idle|working|online|offline
        current_mission_id  INTEGER,
        detail              TEXT,
        last_active_at      DATETIME
    );

    -- ── WORKFLOWS (named, versioned; D61) ─────────────────────
    CREATE TABLE IF NOT EXISTS workflows (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        name            TEXT    NOT NULL,
        version         INTEGER NOT NULL DEFAULT 1,
        definition_json TEXT,                               -- ordered steps / DAG
        is_active       INTEGER DEFAULT 1,
        created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(name, version)
    );

    -- ── MISSIONS (D64/D57/D61/D69) ────────────────────────────
    CREATE TABLE IF NOT EXISTS missions (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        title            TEXT    NOT NULL,
        goal             TEXT,
        status           TEXT    DEFAULT 'planned',         -- planned|running|blocked|done|cancelled
        priority         TEXT    DEFAULT 'Normal',          -- Low|Normal|High|Urgent (D57)
        workflow_id      INTEGER REFERENCES workflows(id),
        workflow_version INTEGER,                            -- pinned at run (D61)
        summary          TEXT,                               -- Tobi close-out (D69)
        cost_tokens      INTEGER DEFAULT 0,
        created_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
        started_at       DATETIME,
        completed_at     DATETIME
    );

    -- ── MISSION_STEPS (D64/D67) ───────────────────────────────
    CREATE TABLE IF NOT EXISTS mission_steps (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        mission_id    INTEGER NOT NULL REFERENCES missions(id) ON DELETE CASCADE,
        seq           INTEGER NOT NULL,
        agent_id      TEXT    REFERENCES agents(id),
        action        TEXT,
        status        TEXT    DEFAULT 'pending',            -- pending|running|done|failed
        input         TEXT,
        output        TEXT,
        artifact_ref  TEXT,                                 -- ~/.mmo_agent/artifacts/{mission}/… (D67)
        tokens        INTEGER DEFAULT 0,
        started_at    DATETIME,
        completed_at  DATETIME
    );

    -- ── LLM_USAGE (per-agent/mission/provider; D34) ───────────
    CREATE TABLE IF NOT EXISTS llm_usage (
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        agent_id          TEXT,
        mission_id        INTEGER,
        provider          TEXT,
        model             TEXT,
        prompt_tokens     INTEGER DEFAULT 0,
        completion_tokens INTEGER DEFAULT 0,
        total_tokens      INTEGER DEFAULT 0,
        cost              REAL    DEFAULT 0,
        created_at        DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS idx_mission_steps_mission ON mission_steps(mission_id, seq);
    CREATE INDEX IF NOT EXISTS idx_llm_usage_mission ON llm_usage(mission_id);
    CREATE INDEX IF NOT EXISTS idx_missions_status ON missions(status, priority);
    """)

    # Seed roster once (idempotent).
    if not conn.execute("SELECT COUNT(*) FROM agents").fetchone()[0]:
        for (aid, name, role, provider, model, key_ref, color, sprite, autonomy, can_spawn, is_head) in _SEED_AGENTS:
            conn.execute(
                """INSERT INTO agents (id, name, role, provider, model, key_ref, color, sprite,
                                       autonomy, can_spawn, is_head)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (aid, name, role, provider, model, key_ref, color, sprite, autonomy, can_spawn, is_head),
            )
            conn.execute(
                "INSERT OR IGNORE INTO agent_state (agent_id, runtime_status) VALUES (?, 'idle')", (aid,)
            )

    # Seed default workflow once.
    if not conn.execute("SELECT COUNT(*) FROM workflows").fetchone()[0]:
        conn.execute(
            "INSERT INTO workflows (name, version, definition_json, is_active) VALUES (?,?,?,1)",
            (_SEED_WORKFLOW["name"], _SEED_WORKFLOW["version"], json.dumps(_SEED_WORKFLOW["steps"])),
        )

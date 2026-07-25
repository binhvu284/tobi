"""Skill registry schema + seed skills.

Extracted verbatim from core/database.py (Phase 4b) — see core/schema/base.py.
"""
from __future__ import annotations

import sqlite3
import json

_SEED_SKILLS = [
    ("chat",         "Chat Assistant",   "Communication", "core",         "L1", "low"),
    ("reports",      "Daily Reports",    "Communication", "core",         "L3", "low"),
    ("telegram",     "Telegram Interface","Communication","core",         "L4", "low"),
    ("coding",       "Coding Agent",     "Building",      "core",         "L2", "high"),
    ("terminal",     "Terminal",         "Building",      "learned",      "L2", "high"),
    ("integrations", "Integrations",     "Building",      "core",         "L4", "high"),
    ("executor",     "Project Executor", "Building",      "core",         "L3", "high"),
    ("research",     "Research Engine",  "Strategy",      "core",         "L3", "low"),
    ("ceo",          "CEO Strategy",     "Strategy",      "core",         "L3", "low"),
    ("tracker",      "Project Tracker",  "Strategy",      "core",         "L1", "low"),
    ("learning",     "Self-Learning",    "Learning",      "core",         "L3", "low"),
    ("memory",       "Memory",           "Learning",      "core",         "L4", "low"),
]


def _ensure_skill_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
    -- ── SKILLS (L1 record / registry metadata) ────────
    CREATE TABLE IF NOT EXISTS skills (
        id            TEXT    PRIMARY KEY,        -- skill key (matches Ability usageKey)
        name          TEXT    NOT NULL,
        category      TEXT,                       -- Communication | Building | Strategy | Learning
        layer         TEXT    DEFAULT 'L1',       -- L1 | L2 | L3 | L4
        tier          TEXT    DEFAULT 'core',     -- core | learned | experimental
        instructions  TEXT,                       -- L1 body (Phase 1 only; H12 flips to Hermes .md)
        tools_json    TEXT,
        model         TEXT,
        status        TEXT    DEFAULT 'active',    -- active | archived
        risk_tier     TEXT    DEFAULT 'low',       -- low | high
        version       INTEGER DEFAULT 1,           -- current active version pointer
        created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at    DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    -- ── SKILL_METRICS (live measured; D44/D45) ────────
    CREATE TABLE IF NOT EXISTS skill_metrics (
        skill_id       TEXT    PRIMARY KEY REFERENCES skills(id) ON DELETE CASCADE,
        runs           INTEGER DEFAULT 0,
        successes      INTEGER DEFAULT 0,
        last_run_at    DATETIME,
        avg_latency_ms REAL,
        token_volume   INTEGER DEFAULT 0
    );

    -- ── SKILL_DEPS (L3 composition edges; D50) ────────
    CREATE TABLE IF NOT EXISTS skill_deps (
        parent_id      TEXT NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
        child_id       TEXT NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
        pinned_version INTEGER,
        PRIMARY KEY (parent_id, child_id)
    );

    -- ── SKILL_VERSIONS (keep-all ledger; D54/H15) ─────
    CREATE TABLE IF NOT EXISTS skill_versions (
        id                   INTEGER PRIMARY KEY AUTOINCREMENT,
        skill_id             TEXT    NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
        version              INTEGER NOT NULL,
        body                 TEXT,
        diff_summary         TEXT,
        metric_snapshot_json TEXT,
        provenance_json      TEXT,
        created_at           DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(skill_id, version)
    );

    -- ── SKILL_PROPOSALS (approval inbox; D13/D48/D20) ─
    CREATE TABLE IF NOT EXISTS skill_proposals (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        skill_id      TEXT    REFERENCES skills(id) ON DELETE SET NULL,
        kind          TEXT    NOT NULL,            -- create | edit | promote
        risk_tier     TEXT    DEFAULT 'low',       -- low | high
        title         TEXT,
        payload_json  TEXT,
        status        TEXT    DEFAULT 'pending',   -- pending | approved | rejected
        rationale     TEXT,
        created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
        resolved_at   DATETIME
    );

    CREATE INDEX IF NOT EXISTS idx_skill_versions_skill ON skill_versions(skill_id, version);
    CREATE INDEX IF NOT EXISTS idx_skill_proposals_status ON skill_proposals(status, created_at);
    """)

    # Seed the curated roster once (idempotent — only when empty).
    have = conn.execute("SELECT COUNT(*) FROM skills").fetchone()[0]
    if not have:
        for sid, name, category, tier, layer, risk in _SEED_SKILLS:
            conn.execute(
                """INSERT INTO skills (id, name, category, tier, layer, risk_tier, version)
                   VALUES (?, ?, ?, ?, ?, ?, 1)""",
                (sid, name, category, tier, layer, risk),
            )
            conn.execute(
                "INSERT OR IGNORE INTO skill_metrics (skill_id) VALUES (?)", (sid,)
            )
            conn.execute(
                """INSERT INTO skill_versions (skill_id, version, body, diff_summary, provenance_json)
                   VALUES (?, 1, ?, 'Seeded baseline', ?)""",
                (sid, "", json.dumps({"actor": "seed", "trigger": "init"})),
            )

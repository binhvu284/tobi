"""Additive evidence schema for the #35 Agent-tier registry."""
from __future__ import annotations

import sqlite3


def _ensure_agent_tier_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS agent_tier_evidence (
        evidence_id     TEXT PRIMARY KEY,
        ability_id      TEXT NOT NULL,
        family_id       TEXT NOT NULL,
        evidence_type   TEXT NOT NULL,
        evidence_ref    TEXT NOT NULL,
        source_release  TEXT NOT NULL,
        observed_at     TEXT NOT NULL,
        status          TEXT NOT NULL DEFAULT 'valid'
                        CHECK (status IN ('valid', 'revoked')),
        recorded_at     TEXT NOT NULL,
        UNIQUE (ability_id, family_id, evidence_type, evidence_ref)
    );
    CREATE INDEX IF NOT EXISTS idx_agent_tier_evidence_ability
        ON agent_tier_evidence(ability_id, status, observed_at);
    CREATE INDEX IF NOT EXISTS idx_agent_tier_evidence_family
        ON agent_tier_evidence(family_id, status, observed_at);
    """)

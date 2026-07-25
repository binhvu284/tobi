"""Genesis vault schema (metadata only — never secret values).

Extracted verbatim from core/database.py (Phase 4b) — see core/schema/base.py.
"""
from __future__ import annotations

import sqlite3

def _ensure_vault_schema(conn: sqlite3.Connection) -> None:
    """Encrypted secrets vault (Genesis Complete). Idempotent.

    Stores only ciphertext + metadata — never plaintext secrets. The master
    password (KDF → AES-256-GCM key) lives only in server memory while unlocked.
    `vault_meta` holds the KDF salt/params + a verifier blob to validate the
    password without storing it. See core/vault.py for the crypto.
    """
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS vault_meta (
        id             INTEGER PRIMARY KEY CHECK (id = 1),
        kdf            TEXT NOT NULL DEFAULT 'scrypt',
        kdf_salt       BLOB NOT NULL,
        kdf_params     TEXT NOT NULL,        -- JSON {n,r,p,len}
        verifier       BLOB NOT NULL,        -- nonce||ciphertext of a known constant
        active_profile TEXT NOT NULL DEFAULT 'local',
        created_at     DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS vault_profiles (
        name       TEXT PRIMARY KEY,          -- 'local' | 'vps' | …
        label      TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS vault_secrets (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        profile        TEXT NOT NULL DEFAULT 'local',
        name           TEXT NOT NULL,         -- env-var NAME (e.g. GITHUB_TOKEN)
        integration_id TEXT,                  -- registry id this secret belongs to
        secret_type    TEXT NOT NULL DEFAULT 'api_key', -- api_key|url|oauth|webhook|custom
        ciphertext     BLOB NOT NULL,
        nonce          BLOB NOT NULL,
        last4          TEXT,                  -- last chars for masked display only
        test_status    TEXT DEFAULT 'untested',  -- untested|ok|failed
        added_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at     DATETIME DEFAULT CURRENT_TIMESTAMP,
        last_tested_at DATETIME,
        UNIQUE(profile, name)
    );

    CREATE TABLE IF NOT EXISTS vault_audit (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        ts             DATETIME DEFAULT CURRENT_TIMESTAMP,
        action         TEXT NOT NULL,         -- setup|unlock|lock|create|update|delete|test|reveal|reload|export|import
        integration_id TEXT,
        name           TEXT,
        ok             INTEGER,
        detail         TEXT                   -- short note, NEVER a secret value
    );

    CREATE INDEX IF NOT EXISTS idx_vault_secrets_profile ON vault_secrets(profile);
    CREATE INDEX IF NOT EXISTS idx_vault_audit_ts        ON vault_audit(ts);
    """)

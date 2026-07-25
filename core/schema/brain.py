"""Brain schema: owner memory, categories, recall (v1 + V2 tables).

Extracted verbatim from core/database.py (Phase 4b) — see core/schema/base.py.
"""
from __future__ import annotations

import sqlite3

from core.schema.base import _ensure_column

def _ensure_brain_schema(conn: sqlite3.Connection) -> None:
    """Brain: long-term owner memory (auto-learn + import + psychology profile).

    Idempotent. Source of truth for the Brain feature; embeddings stored as BLOB
    (numpy float32) on each memory for local semantic search / dedup.
    """
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS brain_categories (
        id          TEXT PRIMARY KEY,          -- slug
        label       TEXT NOT NULL,
        color       TEXT DEFAULT '#58a6ff',
        icon        TEXT DEFAULT 'Brain',
        sort_order  INTEGER DEFAULT 0,
        sensitive   INTEGER DEFAULT 0,         -- 1 = always route to review
        status      TEXT DEFAULT 'approved',   -- approved | pending (TOBI-proposed)
        created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS brain_memories (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        content          TEXT NOT NULL,
        category         TEXT DEFAULT 'identity',
        confidence       REAL DEFAULT 0.6,
        source           TEXT DEFAULT 'manual',   -- manual | auto | import | remember
        status           TEXT DEFAULT 'active',   -- active | pending | archived | superseded
        context          TEXT,                    -- where it was learned
        embedding        BLOB,
        embed_model      TEXT,
        created_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
        last_confirmed_at DATETIME,
        deleted_at       DATETIME
    );

    CREATE TABLE IF NOT EXISTS brain_memory_versions (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        memory_id   INTEGER REFERENCES brain_memories(id) ON DELETE CASCADE,
        content     TEXT,
        category    TEXT,
        confidence  REAL,
        change_kind TEXT,                          -- create | edit | merge | confirm | supersede
        changed_by  TEXT,                          -- owner | auto | import
        created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    -- ── Brain Memory V2 (#20 / T01) — additive; legacy brain_memories untouched ──
    CREATE TABLE IF NOT EXISTS brain_memory_v2 (
        id                   INTEGER PRIMARY KEY AUTOINCREMENT,
        compat_ref           INTEGER REFERENCES brain_memories(id) ON DELETE SET NULL,
        distilled_text       TEXT NOT NULL,
        memory_type          TEXT NOT NULL,            -- brain_contracts.MemoryType
        behavior_implication TEXT DEFAULT '',
        scope_type           TEXT DEFAULT 'global',    -- ScopeType
        scope_key            TEXT,
        authority            TEXT DEFAULT 'soft',      -- Authority: soft | hard
        explicitness         TEXT DEFAULT 'inferred',  -- Explicitness: explicit | inferred
        confidence           REAL DEFAULT 0.6,
        durability           REAL DEFAULT 0,
        actionability        REAL DEFAULT 0,
        specificity          REAL DEFAULT 0,
        source_strength      REAL DEFAULT 0,
        novelty              REAL DEFAULT 0,
        future_usefulness    REAL DEFAULT 0,
        quality_score        REAL DEFAULT 0,           -- weighted 0–100
        suggested_usage      TEXT DEFAULT '',
        trust                TEXT DEFAULT 'trusted',   -- Trust: trusted | untrusted
        sensitive            INTEGER DEFAULT 0,        -- bool
        status               TEXT DEFAULT 'pending',   -- MemoryStatus
        created_at           DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at           DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS brain_memory_evidence (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        memory_id   INTEGER NOT NULL REFERENCES brain_memory_v2(id) ON DELETE CASCADE,
        excerpt     TEXT DEFAULT '',                   -- <= 320 chars
        source_ref  TEXT,
        trust       TEXT DEFAULT 'trusted',
        provenance  TEXT,                              -- how/where captured
        created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS brain_memory_links (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        from_id     INTEGER NOT NULL REFERENCES brain_memory_v2(id) ON DELETE CASCADE,
        to_id       INTEGER NOT NULL REFERENCES brain_memory_v2(id) ON DELETE CASCADE,
        link_type   TEXT NOT NULL,                     -- supersedes | supports | conflicts_with | derived_from
        created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS brain_memory_tags (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        memory_id   INTEGER NOT NULL REFERENCES brain_memory_v2(id) ON DELETE CASCADE,
        tag         TEXT NOT NULL,
        created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    -- Brain V2 legacy-UI compatibility. The current Brain page keeps its proven
    -- interaction contract while these tables retain V2-native history and
    -- conflict decisions. Legacy rows are rollback mirrors, never the authority.
    CREATE TABLE IF NOT EXISTS brain_memory_v2_versions (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        memory_id           INTEGER NOT NULL REFERENCES brain_memory_v2(id) ON DELETE CASCADE,
        content             TEXT,
        category            TEXT,
        confidence          REAL,
        change_kind         TEXT,
        changed_by          TEXT,
        legacy_version_ref  INTEGER,
        created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(memory_id, legacy_version_ref)
    );

    CREATE TABLE IF NOT EXISTS brain_memory_v2_conflict_resolutions (
        link_id      INTEGER PRIMARY KEY REFERENCES brain_memory_links(id) ON DELETE CASCADE,
        decision     TEXT NOT NULL,
        resolved_at  DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS brain_v2_cutover_state (
        id                INTEGER PRIMARY KEY CHECK (id = 1),
        status            TEXT NOT NULL DEFAULT 'pending',
        migrated_count    INTEGER NOT NULL DEFAULT 0,
        skipped_sensitive INTEGER NOT NULL DEFAULT 0,
        last_error        TEXT,
        started_at        DATETIME DEFAULT CURRENT_TIMESTAMP,
        completed_at      DATETIME,
        updated_at        DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    -- Brain V2 (#20 / T02): vault-encrypted sensitive fields. The plaintext columns
    -- above hold a redaction placeholder for sensitive memories; the real bytes live
    -- here, AES-GCM-encrypted via vault.encrypt_payload (bound to `purpose` as AAD).
    -- Purged with the memory on owner deletion; unreadable while the vault is locked.
    CREATE TABLE IF NOT EXISTS brain_secure_payloads (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        memory_id   INTEGER NOT NULL REFERENCES brain_memory_v2(id) ON DELETE CASCADE,
        field       TEXT NOT NULL,                     -- 'distilled_text' | 'evidence:<evidence_id>'
        purpose     TEXT NOT NULL,                     -- AES-GCM AAD binding used at encrypt time
        ciphertext  BLOB NOT NULL,
        nonce       BLOB NOT NULL,
        created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(memory_id, field)
    );

    -- Brain V2 (#20 / T05): resumable dry-run import jobs. The upload itself is
    -- vault-encrypted (payload_*); progress checkpoints in next_chunk so a
    -- restart resumes exactly where it stopped. Temp payloads are purged on
    -- commit/cancel and expired after 24h.
    CREATE TABLE IF NOT EXISTS brain_ingestion_jobs (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        filename        TEXT NOT NULL,
        status          TEXT DEFAULT 'dry_run',        -- dry_run | ready | committed | cancelled | failed
        total_chunks    INTEGER DEFAULT 0,
        next_chunk      INTEGER DEFAULT 0,             -- resume checkpoint
        payload_ct      BLOB,                          -- vault-encrypted upload (NULL after purge)
        payload_nonce   BLOB,
        payload_purpose TEXT,
        error           TEXT,
        created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS brain_ingestion_candidates (
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        job_id            INTEGER NOT NULL REFERENCES brain_ingestion_jobs(id) ON DELETE CASCADE,
        chunk_index       INTEGER DEFAULT 0,
        candidate_json    TEXT,                        -- NULL when sensitive (vault-encrypted instead)
        sensitive         INTEGER DEFAULT 0,
        enc_ct            BLOB,
        enc_nonce         BLOB,
        proposed_outcome  TEXT,                        -- dry-run preview: active|pending|rejected|merged|conflicted|corrected
        proposed_status   TEXT,
        matched_id        INTEGER,
        approved          INTEGER,                     -- NULL = undecided, 1 = approve, 0 = reject
        applied_memory_id INTEGER,                     -- set on commit
        error             TEXT,
        created_at        DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    -- Brain V2 (#20 / T08): usefulness feedback + influence traces. Feedback
    -- tunes ranking only — it never deletes a memory or its evidence. Influence
    -- rows record which memory shaped which turn (the owner-visible trace).
    CREATE TABLE IF NOT EXISTS brain_memory_feedback (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        memory_id   INTEGER NOT NULL REFERENCES brain_memory_v2(id) ON DELETE CASCADE,
        verdict     TEXT NOT NULL,                     -- useful | irrelevant | wrong
        turn_ref    TEXT,                              -- the turn/influence event it judges
        created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS brain_memory_influence (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        memory_id   INTEGER NOT NULL REFERENCES brain_memory_v2(id) ON DELETE CASCADE,
        surface     TEXT DEFAULT 'chat',               -- chat | agent
        turn_ref    TEXT,
        query_hint  TEXT,                              -- truncated query context (why it surfaced)
        created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    -- Brain V2 (#20 / T06): owner-approved legacy migration. Preview scans legacy
    -- brain_memories (never modifying them) into grouped proposals; apply creates
    -- V2 rows via the real engine with compat_ref back to the legacy id. The run
    -- row is the migration ledger + resume checkpoint.
    CREATE TABLE IF NOT EXISTS brain_migration_runs (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        status          TEXT DEFAULT 'preview',        -- preview | ready | applied | cancelled
        snapshot_json   TEXT,                          -- pre-migration counts (spec step 1)
        next_legacy_id  INTEGER DEFAULT 0,             -- resume checkpoint (scan cursor)
        total_legacy    INTEGER DEFAULT 0,
        created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS brain_migration_items (
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id            INTEGER NOT NULL REFERENCES brain_migration_runs(id) ON DELETE CASCADE,
        legacy_id         INTEGER NOT NULL,            -- brain_memories.id (read-only source)
        group_kind        TEXT,                        -- reclassify | duplicate | conflict | sensitive | noise
        candidate_json    TEXT,                        -- NULL when sensitive (vault-encrypted instead)
        sensitive         INTEGER DEFAULT 0,
        enc_ct            BLOB,
        enc_nonce         BLOB,
        proposed_outcome  TEXT,
        proposed_status   TEXT,
        matched_legacy_id INTEGER,                     -- intra-run duplicate/conflict partner
        approved          INTEGER,                     -- NULL undecided | 1 | 0
        applied_memory_id INTEGER,                     -- set on apply (also the resume guard)
        error             TEXT,
        created_at        DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS brain_conflicts (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        memory_id           INTEGER REFERENCES brain_memories(id) ON DELETE CASCADE,
        candidate_content   TEXT NOT NULL,
        candidate_category  TEXT,
        candidate_confidence REAL DEFAULT 0.6,
        candidate_source    TEXT DEFAULT 'auto',
        reason              TEXT,
        status              TEXT DEFAULT 'open',   -- open | resolved
        created_at          DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS brain_imports (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        filename    TEXT,
        source_type TEXT,                          -- md | json
        card_count  INTEGER DEFAULT 0,
        created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS brain_sweep_state (
        id                     INTEGER PRIMARY KEY CHECK (id = 1),
        last_processed_convo_id INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS brain_sweep_cursors (
        chat_id     INTEGER PRIMARY KEY,
        last_id     INTEGER NOT NULL DEFAULT 0,
        fail_count  INTEGER NOT NULL DEFAULT 0,
        updated_at  TEXT
    );

    CREATE TABLE IF NOT EXISTS brain_sweep_lease (
        id          INTEGER PRIMARY KEY CHECK (id = 1),
        holder      TEXT,
        lease_until TEXT
    );

    CREATE TABLE IF NOT EXISTS brain_sweep_failures (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id       INTEGER NOT NULL,
        first_id      INTEGER NOT NULL,
        last_id       INTEGER NOT NULL,
        payload_json  TEXT NOT NULL,
        attempts      INTEGER NOT NULL DEFAULT 1,
        next_retry_at TEXT NOT NULL,
        last_error    TEXT,
        status        TEXT NOT NULL DEFAULT 'pending',
        created_at    TEXT NOT NULL,
        updated_at    TEXT NOT NULL,
        UNIQUE(chat_id, first_id, last_id)
    );

    CREATE TABLE IF NOT EXISTS brain_narrative (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        content     TEXT NOT NULL,
        model_used  TEXT,
        created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS idx_brain_mem_cat    ON brain_memories(category, status);
    CREATE INDEX IF NOT EXISTS idx_brain_mem_status ON brain_memories(status);
    CREATE INDEX IF NOT EXISTS idx_brain_mem_conf   ON brain_memories(last_confirmed_at);
    CREATE INDEX IF NOT EXISTS idx_brain_ver_mem    ON brain_memory_versions(memory_id);
    CREATE INDEX IF NOT EXISTS idx_brain_sweep_failures_due
        ON brain_sweep_failures(status, next_retry_at);
    """)
    # Seed the comprehensive category set (sensitive = Psychology/Relationships/Health).
    seed = [
        ("identity",      "Identity",       "#58a6ff", "User",       0, 0),
        ("preferences",   "Preferences",    "#3fb950", "Heart",      1, 0),
        ("psychology",    "Psychology",     "#a78bfa", "Brain",      2, 1),
        ("relationships", "Relationships",  "#f472b6", "Users",      3, 1),
        ("goals",         "Goals",          "#d29922", "Target",     4, 0),
        ("work",          "Work / Projects","#22d3ee", "Briefcase",  5, 0),
        ("habits",        "Habits / Routines","#2dd4bf", "Repeat",   6, 0),
        ("health",        "Health",         "#f85149", "Activity",   7, 1),
    ]
    for cid, label, color, icon, order, sensitive in seed:
        conn.execute(
            """INSERT OR IGNORE INTO brain_categories (id, label, color, icon, sort_order, sensitive)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (cid, label, color, icon, order, sensitive),
        )
    conn.execute("INSERT OR IGNORE INTO brain_sweep_state (id, last_processed_convo_id) VALUES (1, 0)")
    conn.execute("INSERT OR IGNORE INTO brain_sweep_lease (id, holder, lease_until) VALUES (1, NULL, NULL)")

    # v2: one-way Brain → Hermes memory mirror tracking (idempotent migration).
    cols = {r[1] for r in conn.execute("PRAGMA table_info(brain_memories)").fetchall()}
    if "hermes_synced_at" not in cols:
        conn.execute("ALTER TABLE brain_memories ADD COLUMN hermes_synced_at DATETIME")

    # v2: is_locked decoupled from sensitive (lock = UI display; sensitive = auto-memory routing).
    # Psychology was unlocked by owner command — set is_locked=0 so UI reflects the override.
    _ensure_column(conn, "brain_categories", "is_locked", "INTEGER DEFAULT 0")
    conn.execute("UPDATE brain_categories SET is_locked=0 WHERE id='psychology'")

    # Existing installations predate the compatibility fields above. Keep the
    # migration additive and idempotent so rollback data remains readable.
    _ensure_column(conn, "brain_memory_v2", "last_confirmed_at", "DATETIME")
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_brain_memory_v2_compat_ref "
        "ON brain_memory_v2(compat_ref) WHERE compat_ref IS NOT NULL"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_brain_memory_v2_status_updated "
        "ON brain_memory_v2(status, updated_at DESC)"
    )

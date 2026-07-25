"""Knowledge-graph schema.

Extracted verbatim from core/database.py (Phase 4b) — see core/schema/base.py.
"""
from __future__ import annotations

import sqlite3

def _ensure_graph_schema(conn: sqlite3.Connection) -> None:
    """Graph View: unified second-brain knowledge graph (memories + tasks + projects +
    integration mirrors). Idempotent. One node/edge store backs the per-domain switcher;
    embeddings (reused from Brain) drive cross-domain semantic links.
    """
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS graph_nodes (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        domain      TEXT NOT NULL,              -- memory|task|project|notion|github|gdrive|local
        ref_kind    TEXT,                       -- sub-kind (issue|commit|page|repo|doc…)
        ref_id      TEXT,                       -- source row id / external id (as text)
        title       TEXT NOT NULL,
        summary     TEXT,
        category    TEXT,
        color       TEXT,
        icon        TEXT,
        source_url  TEXT,
        embedding   BLOB,
        embed_model TEXT,
        degree      INTEGER DEFAULT 0,
        x           REAL,
        y           REAL,
        pinned      INTEGER DEFAULT 0,
        created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
        deleted_at  DATETIME
    );

    CREATE TABLE IF NOT EXISTS graph_edges (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        source_id   INTEGER NOT NULL REFERENCES graph_nodes(id) ON DELETE CASCADE,
        target_id   INTEGER NOT NULL REFERENCES graph_nodes(id) ON DELETE CASCADE,
        edge_type   TEXT NOT NULL DEFAULT 'ref',  -- ref|semantic|tag|manual
        weight      REAL DEFAULT 1,
        directed    INTEGER DEFAULT 0,
        created_by  TEXT DEFAULT 'system',        -- system|owner
        created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
        deleted_at  DATETIME
    );

    CREATE TABLE IF NOT EXISTS graph_sync_state (
        source        TEXT PRIMARY KEY,           -- internal|notion|github|gdrive|local
        last_synced_at DATETIME,
        cursor        TEXT,
        item_count    INTEGER DEFAULT 0
    );

    CREATE UNIQUE INDEX IF NOT EXISTS idx_graph_node_ref  ON graph_nodes(domain, ref_id);
    CREATE INDEX        IF NOT EXISTS idx_graph_node_dom  ON graph_nodes(domain);
    CREATE INDEX        IF NOT EXISTS idx_graph_node_cat  ON graph_nodes(category);
    CREATE UNIQUE INDEX IF NOT EXISTS idx_graph_edge_uniq ON graph_edges(source_id, target_id, edge_type);
    CREATE INDEX        IF NOT EXISTS idx_graph_edge_src  ON graph_edges(source_id);
    CREATE INDEX        IF NOT EXISTS idx_graph_edge_tgt  ON graph_edges(target_id);
    """)
    # v1.1: community detection (Louvain-style label propagation) for color/hull grouping.
    gcols = {r[1] for r in conn.execute("PRAGMA table_info(graph_nodes)").fetchall()}
    if "community" not in gcols:
        conn.execute("ALTER TABLE graph_nodes ADD COLUMN community INTEGER")
    if "community_label" not in gcols:
        conn.execute("ALTER TABLE graph_nodes ADD COLUMN community_label TEXT")

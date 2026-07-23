"""News V2 repository (#23, N01) — additive schema, transactions, retention, snapshots.

Owns every News V2 table through a versioned ledger (``news_schema_migrations``,
same pattern as ``developer_schema_migrations``). Everything is ADDITIVE: Explore V1
tables (``explore_items``/``explore_models``/…) are read-only compatibility inputs
here and are never rewritten or deleted during rollout (plan §4/§12).

Nothing reads these tables on live pages until ``news.v2_enabled`` flips — the N01
foundation lands dormant.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone

from core.news.contracts import (
    EVENT_AGGREGATE_DAYS, RETENTION_DAYS, EventAction, InteractionEvent, NewsSettings,
    Reaction, clamp_limit, decode_cursor, encode_cursor, payload_hash, url_hash,
)

_LEDGER_DDL = ("CREATE TABLE IF NOT EXISTS news_schema_migrations ("
               "version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)")

# Migration 1 — the twelve N01 tables (plan §4). Source checkpoints live inside
# news_refresh_jobs.checkpoints_json so the table inventory matches the plan exactly.
_MIGRATION_1 = """
CREATE TABLE IF NOT EXISTS news_items (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    url_hash      TEXT NOT NULL UNIQUE,
    canonical_url TEXT NOT NULL,
    item_type     TEXT NOT NULL,
    title         TEXT NOT NULL,
    excerpt       TEXT,
    published_at  TEXT,
    first_seen_at TEXT NOT NULL,
    expires_at    TEXT,
    media_key     TEXT,
    compat_v1_id  INTEGER UNIQUE
);
CREATE INDEX IF NOT EXISTS idx_news_items_type ON news_items(item_type, published_at DESC);
CREATE INDEX IF NOT EXISTS idx_news_items_expiry ON news_items(expires_at);
CREATE TABLE IF NOT EXISTS news_item_sources (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id      INTEGER NOT NULL REFERENCES news_items(id),
    source       TEXT NOT NULL,
    external_id  TEXT NOT NULL,
    original_url TEXT,
    payload_hash TEXT,
    trust        TEXT NOT NULL,
    engagement   INTEGER NOT NULL DEFAULT 0,
    observed_at  TEXT NOT NULL,
    UNIQUE(source, external_id)
);
CREATE INDEX IF NOT EXISTS idx_news_item_sources_item ON news_item_sources(item_id);
CREATE TABLE IF NOT EXISTS news_interactions (
    item_id    INTEGER PRIMARY KEY REFERENCES news_items(id),
    reaction   TEXT NOT NULL DEFAULT 'none',
    favorite   INTEGER NOT NULL DEFAULT 0,
    note       TEXT,
    opens      INTEGER NOT NULL DEFAULT 0,
    dwell_ms   INTEGER NOT NULL DEFAULT 0,
    version    INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS news_interaction_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id         INTEGER NOT NULL,
    action          TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    created_at      TEXT NOT NULL,
    undo_until      TEXT,
    reversed_by     INTEGER,
    payload_json    TEXT
);
CREATE INDEX IF NOT EXISTS idx_news_events_item ON news_interaction_events(item_id, created_at);
CREATE TABLE IF NOT EXISTS news_interest_profiles (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    version         INTEGER NOT NULL UNIQUE,
    computed_at     TEXT NOT NULL,
    topics_json     TEXT NOT NULL,
    sources_json    TEXT NOT NULL,
    provenance_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS news_rank_snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    kind            TEXT NOT NULL,
    formula_version TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    entries_json    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_news_rank_kind ON news_rank_snapshots(kind, id DESC);
CREATE TABLE IF NOT EXISTS news_refresh_jobs (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    tab              TEXT NOT NULL,
    state            TEXT NOT NULL,
    lease_owner      TEXT,
    lease_until      TEXT,
    attempts         INTEGER NOT NULL DEFAULT 0,
    error            TEXT,
    checkpoints_json TEXT,
    metrics_json     TEXT,
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_news_jobs_tab ON news_refresh_jobs(tab, state);
CREATE TABLE IF NOT EXISTS news_github_snapshots (
    repo          TEXT NOT NULL,
    snapshot_date TEXT NOT NULL,
    stars         INTEGER NOT NULL,
    PRIMARY KEY (repo, snapshot_date)
);
CREATE TABLE IF NOT EXISTS news_model_metrics (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    model_id        TEXT NOT NULL,
    category        TEXT NOT NULL,
    source          TEXT NOT NULL,
    metric          TEXT NOT NULL,
    value           REAL NOT NULL,
    confidence      REAL NOT NULL,
    observed_at     TEXT NOT NULL,
    formula_version TEXT NOT NULL,
    UNIQUE(model_id, category, source, metric, formula_version)
);
CREATE TABLE IF NOT EXISTS news_model_releases (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    model_id    TEXT,
    title       TEXT NOT NULL,
    source_url  TEXT NOT NULL,
    released_at TEXT,
    observed_at TEXT NOT NULL,
    UNIQUE(source_url, title)
);
CREATE TABLE IF NOT EXISTS news_media_cache (
    url_hash   TEXT PRIMARY KEY,
    local_key  TEXT NOT NULL,
    mime       TEXT NOT NULL,
    bytes      INTEGER NOT NULL,
    width      INTEGER,
    height     INTEGER,
    expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS news_settings (
    key        TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

_MIGRATIONS: list[tuple[int, str]] = [(1, _MIGRATION_1)]

SNAPSHOT_KEEP = 20     # retained rank snapshots per kind (immutable, rebuilt often)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _conn() -> sqlite3.Connection:
    from core.database import get_connection
    return get_connection()


# Boot runs ensure_schema via init_database; direct imports (tests, ad-hoc) run it at
# most once per process — the same write-lock-avoidance pattern as core/explore.py.
_SCHEMA_READY = False


def ensure_schema(conn: sqlite3.Connection | None = None) -> None:
    """Apply every pending ledger migration. Idempotent; additive-only."""
    own = conn is None
    conn = conn or _conn()
    try:
        conn.execute(_LEDGER_DDL)
        applied = {row[0] for row in conn.execute("SELECT version FROM news_schema_migrations")}
        for version, ddl in _MIGRATIONS:
            if version in applied:
                continue
            conn.executescript(ddl)
            conn.execute("INSERT OR IGNORE INTO news_schema_migrations(version, applied_at) VALUES (?,?)",
                         (version, _utc_now()))
        if own:
            conn.commit()
    finally:
        if own:
            conn.close()
    global _SCHEMA_READY
    _SCHEMA_READY = True


def _ensure_once(conn: sqlite3.Connection) -> None:
    if not _SCHEMA_READY:
        ensure_schema(conn)


# ── V1 compatibility copy (plan §4: idempotent; V1 rows never rewritten) ─────────────
_V1_TYPE = {"models": "article", "tools": "tool", "social": "social"}
_V1_METRICS = ("intelligence", "elo", "speed", "composite")


def copy_v1(conn: sqlite3.Connection | None = None) -> dict:
    """Copy Explore V1 items/models into the V2 store, retaining V1 ids as
    ``compat_v1_id`` references. INSERT OR IGNORE everywhere → safe to re-run; V1
    tables are only ever SELECTed. Returns copy counters."""
    own = conn is None
    conn = conn or _conn()
    counters = {"items": 0, "evidence": 0, "metrics": 0}
    try:
        _ensure_once(conn)
        now = _utc_now()
        expiry = (datetime.now(timezone.utc) + timedelta(days=RETENTION_DAYS)).isoformat()
        try:
            rows = conn.execute(
                "SELECT id, pillar, source_name, ext_id, title, url, summary, raw_json,"
                " engagement, published_at, first_seen_at FROM explore_items"
            ).fetchall()
        except sqlite3.Error:
            rows = []                       # V1 absent (fresh install) — nothing to copy
        for r in rows:
            (v1_id, pillar, source_name, ext_id, title, url,
             summary, raw_json, engagement, published_at, first_seen) = tuple(r)
            if not (title or "").strip():
                continue                    # V2 requires a title; V1 row stays where it is
            h = url_hash(url) if (url or "").strip() else url_hash(f"tobi://explore-v1/{pillar}/{ext_id}")
            cur = conn.execute(
                "INSERT OR IGNORE INTO news_items (url_hash, canonical_url, item_type, title,"
                " excerpt, published_at, first_seen_at, expires_at, compat_v1_id)"
                " VALUES (?,?,?,?,?,?,?,?,?)",
                (h, (url or "").strip(), _V1_TYPE.get(pillar, "article"), title.strip(),
                 (summary or "")[:500], published_at, first_seen or now, expiry, v1_id))
            counters["items"] += cur.rowcount
            item_id = conn.execute("SELECT id FROM news_items WHERE url_hash=?", (h,)).fetchone()
            if item_id:
                cur = conn.execute(
                    "INSERT OR IGNORE INTO news_item_sources (item_id, source, external_id,"
                    " original_url, payload_hash, trust, engagement, observed_at)"
                    " VALUES (?,?,?,?,?,?,?,?)",
                    (item_id[0], source_name or f"explore_v1:{pillar}", str(ext_id),
                     url, payload_hash(raw_json or ""), "aggregator",
                     int(engagement or 0), first_seen or now))
                counters["evidence"] += cur.rowcount
        try:
            models = conn.execute(
                "SELECT model_id, intelligence, elo, speed, composite, updated_at FROM explore_models"
            ).fetchall()
        except sqlite3.Error:
            models = []
        for m in models:
            model_id, intelligence, elo, speed, composite, updated_at = tuple(m)
            for metric, value in zip(_V1_METRICS, (intelligence, elo, speed, composite)):
                if value is None:
                    continue
                cur = conn.execute(
                    "INSERT OR IGNORE INTO news_model_metrics (model_id, category, source,"
                    " metric, value, confidence, observed_at, formula_version)"
                    " VALUES (?,?,?,?,?,?,?,?)",
                    (model_id, "general", "explore_v1", metric, float(value), 0.5,
                     updated_at or now, "v1"))
                counters["metrics"] += cur.rowcount
        if own:
            conn.commit()
        return counters
    finally:
        if own:
            conn.close()


# ── interaction primitives (durable behavior lands fully in N04) ─────────────────────
def record_event(conn: sqlite3.Connection, event: InteractionEvent) -> bool:
    """Append one owner action; ``idempotency_key`` makes replays no-ops. Returns
    whether a new row was written. Favorite/note also PROTECT the item (expiry → NULL);
    like/open/dwell push expiry forward RETENTION_DAYS from now (a 'touch')."""
    _ensure_once(conn)
    cur = conn.execute(
        "INSERT OR IGNORE INTO news_interaction_events"
        " (item_id, action, idempotency_key, created_at, undo_until, payload_json)"
        " VALUES (?,?,?,?,?,?)",
        (event.item_id, event.action.value, event.idempotency_key, event.created_at,
         event.undo_until, json.dumps(event.payload) if event.payload else None))
    if cur.rowcount == 0:
        return False
    if event.action in (EventAction.FAVORITE, EventAction.NOTE):
        conn.execute("UPDATE news_items SET expires_at=NULL WHERE id=?", (event.item_id,))
    elif event.action in (EventAction.LIKE, EventAction.OPEN, EventAction.DWELL):
        touch = (datetime.now(timezone.utc) + timedelta(days=RETENTION_DAYS)).isoformat()
        conn.execute("UPDATE news_items SET expires_at=? WHERE id=? AND expires_at IS NOT NULL",
                     (touch, event.item_id))
    return True


_KEEP = object()   # sentinel: "leave the note alone" — note=None must mean CLEAR it


def upsert_interaction(conn: sqlite3.Connection, item_id: int, *, reaction: Reaction | None = None,
                       favorite: bool | None = None, note: object = _KEEP,
                       expected_version: int | None = None) -> dict:
    """Optimistic-versioned current-state upsert. ``expected_version`` mismatch raises
    ``ValueError`` (the API's 409). Omit ``note`` to keep it; pass ``None`` to clear.
    Returns the stored state."""
    _ensure_once(conn)
    row = conn.execute("SELECT reaction, favorite, note, opens, dwell_ms, version"
                       " FROM news_interactions WHERE item_id=?", (item_id,)).fetchone()
    current_version = row[5] if row else 0
    if expected_version is not None and expected_version != current_version:
        raise ValueError(f"stale interaction version {expected_version} (current {current_version})")
    state = {
        "reaction": (reaction.value if reaction is not None else (row[0] if row else Reaction.NONE.value)),
        "favorite": int(favorite if favorite is not None else (row[1] if row else 0)),
        "note": (row[2] if row else None) if note is _KEEP else note,
        "opens": row[3] if row else 0,
        "dwell_ms": row[4] if row else 0,
        "version": current_version + 1,
    }
    conn.execute(
        "INSERT INTO news_interactions (item_id, reaction, favorite, note, opens, dwell_ms, version, updated_at)"
        " VALUES (?,?,?,?,?,?,?,?)"
        " ON CONFLICT(item_id) DO UPDATE SET reaction=excluded.reaction, favorite=excluded.favorite,"
        " note=excluded.note, version=excluded.version, updated_at=excluded.updated_at",
        (item_id, state["reaction"], state["favorite"], state["note"],
         state["opens"], state["dwell_ms"], state["version"], _utc_now()))
    return {"item_id": item_id, **state}


# ── rank snapshots + cursor reads (formulas land in N05; storage contract is N01) ────
def write_rank_snapshot(conn: sqlite3.Connection, kind: str, entries: list[dict],
                        formula_version: str) -> int:
    """Persist one immutable ranked result set; returns its snapshot id."""
    _ensure_once(conn)
    if not kind.strip() or not formula_version.strip():
        raise ValueError("kind and formula_version are required")
    cur = conn.execute(
        "INSERT INTO news_rank_snapshots (kind, formula_version, created_at, entries_json)"
        " VALUES (?,?,?,?)",
        (kind, formula_version, _utc_now(), json.dumps(entries, default=str)))
    return int(cur.lastrowid)


def read_snapshot_page(conn: sqlite3.Connection, *, kind: str | None = None,
                       cursor: str | None = None, limit: object = None) -> dict:
    """Stable pagination: no cursor → newest snapshot of ``kind`` from position 0;
    a cursor pins its snapshot so later refreshes never shift the page."""
    _ensure_once(conn)
    limit_n = clamp_limit(limit)
    if cursor:
        snapshot_id, position = decode_cursor(cursor)
    else:
        if not (kind or "").strip():
            raise ValueError("kind is required without a cursor")
        row = conn.execute("SELECT id FROM news_rank_snapshots WHERE kind=? ORDER BY id DESC LIMIT 1",
                           (kind,)).fetchone()
        if not row:
            return {"snapshot_id": None, "entries": [], "next_cursor": None}
        snapshot_id, position = int(row[0]), 0
    row = conn.execute("SELECT entries_json FROM news_rank_snapshots WHERE id=?", (snapshot_id,)).fetchone()
    if not row:
        raise ValueError(f"unknown snapshot {snapshot_id}")
    entries = json.loads(row[0])
    page = entries[position:position + limit_n]
    nxt = position + limit_n
    return {"snapshot_id": snapshot_id, "entries": page,
            "next_cursor": encode_cursor(snapshot_id, nxt) if nxt < len(entries) else None}


# ── retention (plan §9; scheduler wiring lands in N03) ───────────────────────────────
def run_retention(conn: sqlite3.Connection | None = None, now: datetime | None = None) -> dict:
    """Remove expired untouched items (favorites/notes are protected by NULL expiry),
    prune their dependents, drop settled interaction events older than
    EVENT_AGGREGATE_DAYS (their aggregates live in news_interactions), and clear
    expired media-cache rows. Returns deletion counters."""
    own = conn is None
    conn = conn or _conn()
    try:
        _ensure_once(conn)
        now_dt = now or datetime.now(timezone.utc)
        now_iso = now_dt.isoformat()
        expired = [r[0] for r in conn.execute(
            "SELECT id FROM news_items WHERE expires_at IS NOT NULL AND expires_at < ?", (now_iso,))]
        for item_id in expired:
            conn.execute("DELETE FROM news_item_sources WHERE item_id=?", (item_id,))
            conn.execute("DELETE FROM news_interaction_events WHERE item_id=?", (item_id,))
            conn.execute("DELETE FROM news_interactions WHERE item_id=?", (item_id,))
            conn.execute("DELETE FROM news_items WHERE id=?", (item_id,))
        event_cutoff = (now_dt - timedelta(days=EVENT_AGGREGATE_DAYS)).isoformat()
        events = conn.execute(
            "DELETE FROM news_interaction_events WHERE created_at < ?"
            " AND (undo_until IS NULL OR undo_until < ?)",          # never drop a live Undo window
            (event_cutoff, now_iso)).rowcount
        media = conn.execute("DELETE FROM news_media_cache WHERE expires_at < ?", (now_iso,)).rowcount
        # snapshots are immutable and rebuilt often — keep a bounded per-kind history
        snapshots = 0
        for (kind,) in conn.execute("SELECT DISTINCT kind FROM news_rank_snapshots").fetchall():
            snapshots += conn.execute(
                "DELETE FROM news_rank_snapshots WHERE kind=? AND id NOT IN"
                " (SELECT id FROM news_rank_snapshots WHERE kind=? ORDER BY id DESC LIMIT ?)",
                (kind, kind, SNAPSHOT_KEEP)).rowcount
        if own:
            conn.commit()
        return {"items": len(expired), "events": events, "media": media, "snapshots": snapshots}
    finally:
        if own:
            conn.close()


# ── settings ─────────────────────────────────────────────────────────────────────────
def get_settings(conn: sqlite3.Connection) -> NewsSettings:
    _ensure_once(conn)
    row = conn.execute("SELECT value_json FROM news_settings WHERE key='settings'").fetchone()
    try:
        return NewsSettings.from_json(row[0] if row else None)
    except (ValueError, json.JSONDecodeError):
        return NewsSettings()                     # corrupted settings degrade to defaults


def set_settings(conn: sqlite3.Connection, settings: NewsSettings) -> NewsSettings:
    _ensure_once(conn)
    conn.execute(
        "INSERT INTO news_settings (key, value_json, updated_at) VALUES ('settings', ?, ?)"
        " ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json, updated_at=excluded.updated_at",
        (settings.to_json(), _utc_now()))
    return settings

"""News V2 canonical normalizer (#23, N02) — text, timestamps, and evidence-preserving
ingest. Turns validated adapter output (``SourceRecord``/metric/release/snapshot
contracts) into canonical rows: one ``news_items`` row per canonical URL, one
``news_item_sources`` evidence row per (source, external_id) — so a story seen by two
adapters keeps BOTH receipts (plan §3/§5). All source text is untrusted evidence:
tags are stripped, entities unescaped, excerpts deterministically bounded. No LLM.
"""
from __future__ import annotations

import html
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Iterable

from core.news.contracts import (
    EXCERPT_MAX, RETENTION_DAYS, GitHubSnapshot, ModelMetric, ModelRelease,
    SourceRecord, canonical_url, url_hash,
)

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def strip_html(text: str | None) -> str:
    """Tags removed, entities unescaped, whitespace collapsed. Deterministic."""
    if not text:
        return ""
    return _WS.sub(" ", html.unescape(_TAG.sub(" ", str(text)))).strip()


def bound_excerpt(text: str | None, limit: int = EXCERPT_MAX) -> str:
    """Clean + cut at a word boundary within ``limit`` (contract-safe by construction)."""
    clean = strip_html(text)
    if len(clean) <= limit:
        return clean
    cut = clean[: limit - 1]
    if " " in cut:
        cut = cut[: cut.rfind(" ")]
    return cut + "…"


def to_utc_iso(value: object) -> str | None:
    """Unix seconds or ISO-8601 → normalized UTC ISO string; anything else → None
    (missing timestamps stay missing — never invented, plan §5)."""
    if value is None or value == "":
        return None
    try:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat()
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


# Media fetch seam (tests stub this to stay network-free). Returns the cached local
# media key for an image URL, or None. SSRF-guarded inside core.news.media.
def _cache_media(conn: sqlite3.Connection, url: str) -> str | None:
    try:
        from core.news import media
        return media.cache_image(conn, url)
    except Exception:
        return None


# ── ingest: canonical items + per-source evidence ────────────────────────────────────
def ingest(conn: sqlite3.Connection, records: Iterable[SourceRecord]) -> dict:
    """Persist adapter records. Dedupe items by canonical URL hash; retain one evidence
    row per (source, external_id) and refresh its engagement/observation on re-sight.
    A record carrying a ``media_url`` gets its publisher image fetched (SSRF-guarded)
    and cached once, so the card shows a real thumbnail. Idempotent. Returns counters."""
    from core.news import repository
    repository._ensure_once(conn)
    counters = {"items_new": 0, "evidence_new": 0, "evidence_updated": 0}
    now = _utc_now()
    expiry = (datetime.now(timezone.utc) + timedelta(days=RETENTION_DAYS)).isoformat()
    for rec in records:
        h = url_hash(rec.url)
        cur = conn.execute(
            "INSERT OR IGNORE INTO news_items (url_hash, canonical_url, item_type, title,"
            " excerpt, published_at, first_seen_at, expires_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (h, canonical_url(rec.url), rec.item_type.value, strip_html(rec.title)[:300],
             bound_excerpt(rec.excerpt), to_utc_iso(rec.published_at), now, expiry))
        counters["items_new"] += cur.rowcount
        row = conn.execute("SELECT id, media_key FROM news_items WHERE url_hash=?", (h,)).fetchone()
        if not row:
            continue
        item_id = int(row[0])
        if rec.media_url and row[1] is None:          # fetch the thumbnail once, best-effort
            key = _cache_media(conn, rec.media_url)
            if key:
                conn.execute("UPDATE news_items SET media_key=? WHERE id=? AND media_key IS NULL",
                             (key, item_id))
        cur = conn.execute(
            "INSERT OR IGNORE INTO news_item_sources (item_id, source, external_id,"
            " original_url, payload_hash, trust, engagement, observed_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (item_id, rec.source, rec.external_id, rec.url, rec.raw_hash or None,
             rec.trust.value, rec.engagement, rec.observed_at))
        if cur.rowcount:
            counters["evidence_new"] += 1
        else:
            cur = conn.execute(
                "UPDATE news_item_sources SET engagement=?, observed_at=?, payload_hash=?"
                " WHERE source=? AND external_id=?"
                " AND (engagement != ? OR COALESCE(payload_hash,'') != COALESCE(?,''))",
                (rec.engagement, rec.observed_at, rec.raw_hash or None,
                 rec.source, rec.external_id, rec.engagement, rec.raw_hash or None))
            counters["evidence_updated"] += cur.rowcount
    return counters


# Lower-is-better metrics: when reasoning-effort variants collapse into one model
# id, the CHEAPEST price is the model's price; every other metric keeps its BEST
# (highest) mode — the owner rule "the value is the highest mode".
_LOWER_IS_BETTER = {"price_in", "price_out", "price_blended"}


def ingest_model_evidence(conn: sqlite3.Connection, metrics: Iterable[ModelMetric],
                          releases: Iterable[ModelRelease]) -> dict:
    """Metrics upsert on their identity key (fresh observation replaces value);
    releases are append-only evidence, deduped by (source_url, title)."""
    from core.news import repository
    repository._ensure_once(conn)
    counters = {"metrics": 0, "releases": 0}
    best: dict[tuple, ModelMetric] = {}
    for m in metrics:                    # collapsed variants share a key → keep the best mode
        key = (m.model_id, m.category, m.source, m.metric, m.formula_version)
        held = best.get(key)
        if held is None or ((m.value < held.value) if m.metric in _LOWER_IS_BETTER
                            else (m.value > held.value)):
            best[key] = m
    for m in best.values():
        cur = conn.execute(
            "INSERT INTO news_model_metrics (model_id, category, source, metric, value,"
            " confidence, observed_at, formula_version) VALUES (?,?,?,?,?,?,?,?)"
            " ON CONFLICT(model_id, category, source, metric, formula_version)"
            " DO UPDATE SET value=excluded.value, confidence=excluded.confidence,"
            " observed_at=excluded.observed_at",
            (m.model_id, m.category, m.source, m.metric, m.value, m.confidence,
             m.observed_at, m.formula_version))
        counters["metrics"] += cur.rowcount
    for r in releases:
        cur = conn.execute(
            "INSERT OR IGNORE INTO news_model_releases (model_id, title, source_url,"
            " released_at, observed_at) VALUES (?,?,?,?,?)",
            (r.model_id, r.title, r.source_url, r.released_at, r.observed_at))
        counters["releases"] += cur.rowcount
    return counters


def ingest_github_snapshots(conn: sqlite3.Connection, snapshots: Iterable[GitHubSnapshot]) -> int:
    """One row per (repo, day); a same-day refetch keeps the latest star reading.
    Growth math (N05) reads ONLY these persisted rows — never live deltas."""
    from core.news import repository
    repository._ensure_once(conn)
    n = 0
    for s in snapshots:
        cur = conn.execute(
            "INSERT INTO news_github_snapshots (repo, snapshot_date, stars) VALUES (?,?,?)"
            " ON CONFLICT(repo, snapshot_date) DO UPDATE SET stars=excluded.stars",
            (s.repo, s.snapshot_date, s.stars))
        n += cur.rowcount
    return n


def ingest_github_trending(conn: sqlite3.Connection, rows: Iterable) -> int:
    """GitHub's OWN trending numbers, upserted per (repo, window). A window present
    in this refresh is fully replaced (stale repos that fell off the board are
    cleared first) so the table always mirrors the live trending page."""
    from core.news import repository
    repository._ensure_once(conn)
    rows = list(rows)
    for window in {r.window for r in rows}:
        conn.execute("DELETE FROM news_github_trending WHERE window=?", (window,))
    n = 0
    for r in rows:
        cur = conn.execute(
            "INSERT INTO news_github_trending"
            " (repo, window, rank, period_stars, total_stars, description, language, observed_at)"
            " VALUES (?,?,?,?,?,?,?,?)"
            " ON CONFLICT(repo, window) DO UPDATE SET rank=excluded.rank,"
            " period_stars=excluded.period_stars, total_stars=excluded.total_stars,"
            " description=excluded.description, language=excluded.language,"
            " observed_at=excluded.observed_at",
            (r.repo, r.window, r.rank, r.period_stars, r.total_stars,
             r.description, r.language, r.observed_at))
        n += cur.rowcount
    return n

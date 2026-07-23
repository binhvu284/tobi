"""News V2 personalization (#23, N04) — signal weights, durable profile recompute,
deterministic "Why shown" reasons, and bounded context merging (plan §6).

The profile is computed from the CURRENT interaction state (replay-safe by
construction — reversals like unfavorite simply clear their flag) plus the event
ledger for exactly one thing: a dislike only counts once its 10-second undo window
has passed un-reversed. Cross-module context is capped at ±CONTEXT_CAP points and
direct News actions take precedence. No LLM anywhere — every output is deterministic.
"""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone

from core.news.contracts import CONTEXT_CLASSES, NewsSettings
from core.news.interactions import DWELL_THRESHOLD_MS, committed_dislike
from core.news.repository import _ensure_once

# Locked signal weights (plan §6 table).
W_FAVORITE, W_NOTE, W_LIKE, W_DWELL, W_OPEN, W_DISLIKE = 5.0, 4.0, 3.0, 1.0, 1.0, -5.0
CONTEXT_CAP = 5.0        # cross-module context changes a score by at most five points
IMMEDIATE_CAP = 2.0      # small bounded modifier for actions newer than the profile

_TOKEN = re.compile(r"[a-z0-9][a-z0-9\-\+\.]{3,}")
_STOP = {"about", "after", "against", "https", "their", "there", "these", "those",
         "which", "while", "with", "would", "from", "have", "into", "over", "show",
         "that", "this", "what", "when", "your", "using", "than", "them", "they"}


def _tokens(title: str) -> list[str]:
    return [t for t in _TOKEN.findall((title or "").lower()) if t not in _STOP][:12]


def _item_signal(state: dict, is_committed_dislike: bool) -> float:
    """Net signal weight for one item's current interaction state."""
    weight = 0.0
    if state["favorite"]:
        weight += W_FAVORITE
    if (state["note"] or "").strip():
        weight += W_NOTE
    if state["reaction"] == "like":
        weight += W_LIKE
    if state["reaction"] == "dislike" and is_committed_dislike:
        weight += W_DISLIKE
    if state["opens"] > 0:
        weight += W_OPEN
    if state["dwell_ms"] >= DWELL_THRESHOLD_MS:
        weight += W_DWELL
    return weight


def _interaction_rows(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT i.item_id, i.reaction, i.favorite, i.note, i.opens, i.dwell_ms,"
        " n.title, n.item_type FROM news_interactions i JOIN news_items n ON n.id=i.item_id"
    ).fetchall()
    return [{"item_id": r[0], "reaction": r[1], "favorite": r[2], "note": r[3],
             "opens": r[4], "dwell_ms": r[5], "title": r[6], "item_type": r[7]} for r in rows]


def recompute_profile(conn: sqlite3.Connection, now: datetime | None = None) -> dict:
    """Durable scheduled recompute → a NEW versioned ``news_interest_profiles`` row.
    Affinities are per source, per item type, and per title topic token, each carrying
    full provenance (how many items/events fed it). Never deletes prior versions."""
    _ensure_once(conn)
    now_dt = now or datetime.now(timezone.utc)
    topics: dict[str, float] = {}
    sources: dict[str, float] = {}
    types: dict[str, float] = {}
    considered = 0
    for state in _interaction_rows(conn):
        weight = _item_signal(state, committed_dislike(conn, state["item_id"], now_dt))
        if weight == 0.0:
            continue
        considered += 1
        types[state["item_type"]] = types.get(state["item_type"], 0.0) + weight
        for row in conn.execute("SELECT source FROM news_item_sources WHERE item_id=?",
                                (state["item_id"],)):
            sources[row[0]] = sources.get(row[0], 0.0) + weight
        for token in _tokens(state["title"]):
            topics[token] = topics.get(token, 0.0) + weight
    version = (conn.execute("SELECT MAX(version) FROM news_interest_profiles").fetchone()[0] or 0) + 1
    provenance = {"items_considered": considered, "computed_at": now_dt.isoformat(),
                  "weights": {"favorite": W_FAVORITE, "note": W_NOTE, "like": W_LIKE,
                              "dwell": W_DWELL, "open": W_OPEN, "dislike": W_DISLIKE}}
    conn.execute(
        "INSERT INTO news_interest_profiles (version, computed_at, topics_json, sources_json,"
        " provenance_json) VALUES (?,?,?,?,?)",
        (version, now_dt.isoformat(), json.dumps(topics, sort_keys=True),
         json.dumps({"sources": sources, "types": types}, sort_keys=True),
         json.dumps(provenance, sort_keys=True)))
    return {"version": version, "topics": topics, "sources": sources, "types": types,
            "provenance": provenance}


def active_profile(conn: sqlite3.Connection) -> dict | None:
    _ensure_once(conn)
    row = conn.execute("SELECT version, computed_at, topics_json, sources_json, provenance_json"
                       " FROM news_interest_profiles ORDER BY version DESC LIMIT 1").fetchone()
    if not row:
        return None
    src = json.loads(row[3] or "{}")
    return {"version": row[0], "computed_at": row[1], "topics": json.loads(row[2] or "{}"),
            "sources": src.get("sources", {}), "types": src.get("types", {}),
            "provenance": json.loads(row[4] or "{}")}


def immediate_adjustments(conn: sqlite3.Connection, now: datetime | None = None) -> dict:
    """The bounded fast path: source deltas from interactions NEWER than the active
    profile so a like affects the next page without waiting for the recompute. Each
    source's delta is clamped to ±IMMEDIATE_CAP; committed-dislike rules still apply."""
    _ensure_once(conn)
    now_dt = now or datetime.now(timezone.utc)
    profile = active_profile(conn)
    since = profile["computed_at"] if profile else ""
    deltas: dict[str, float] = {}
    item_ids = {int(r[0]) for r in conn.execute(
        "SELECT DISTINCT item_id FROM news_interaction_events WHERE created_at > ?", (since,))}
    for item_id in sorted(item_ids):
        state = conn.execute("SELECT reaction, favorite, note, opens, dwell_ms"
                             " FROM news_interactions WHERE item_id=?", (item_id,)).fetchone()
        if not state:
            continue
        weight = _item_signal({"reaction": state[0], "favorite": state[1], "note": state[2],
                               "opens": state[3], "dwell_ms": state[4]},
                              committed_dislike(conn, item_id, now_dt))
        if weight == 0.0:
            continue
        for row in conn.execute("SELECT source FROM news_item_sources WHERE item_id=?", (item_id,)):
            deltas[row[0]] = deltas.get(row[0], 0.0) + weight
    return {source: max(-IMMEDIATE_CAP, min(IMMEDIATE_CAP, value))
            for source, value in sorted(deltas.items())}


def context_delta(context_scores: dict, settings: NewsSettings, has_direct_signal: bool) -> float:
    """Bounded cross-module influence (plan §6): only owner-enabled context classes
    count, the total is clamped to ±CONTEXT_CAP, and a direct News action on the item
    takes precedence — context contributes nothing at all."""
    if has_direct_signal:
        return 0.0
    total = sum(float(value) for cls, value in (context_scores or {}).items()
                if cls in CONTEXT_CLASSES and settings.context_classes.get(cls, False))
    return max(-CONTEXT_CAP, min(CONTEXT_CAP, total))


def reasons_for(conn: sqlite3.Connection, item_id: int, profile: dict | None,
                limit: int = 2) -> list[dict]:
    """The card's two strongest DETERMINISTIC reasons (plan §6/§8). Candidates are
    scored from the profile and stored evidence only; ties break alphabetically so
    the same inputs always render the same reasons."""
    _ensure_once(conn)
    item = conn.execute("SELECT title, published_at FROM news_items WHERE id=?", (item_id,)).fetchone()
    if not item:
        raise ValueError(f"unknown news item {item_id}")
    profile = profile or {}
    candidates: list[tuple[float, str]] = []
    sources = conn.execute("SELECT source, engagement FROM news_item_sources WHERE item_id=?"
                           " ORDER BY source", (item_id,)).fetchall()
    for source, engagement in sources:
        affinity = float((profile.get("sources") or {}).get(source, 0.0))
        if affinity > 0:
            candidates.append((affinity, f"You often engage with {source} posts"))
        if (engagement or 0) >= 100:
            candidates.append((min(1.0, (engagement or 0) / 1000.0), f"Popular on {source}"))
    topic_hits = [(float((profile.get("topics") or {}).get(t, 0.0)), t)
                  for t in _tokens(item[0] or "")]
    for strength, token in topic_hits:
        if strength > 0:
            candidates.append((strength, f"Matches your interest in “{token}”"))
    if item[1]:
        try:
            age_h = (datetime.now(timezone.utc)
                     - datetime.fromisoformat(str(item[1]).replace("Z", "+00:00"))).total_seconds() / 3600
            if 0 <= age_h <= 48:
                candidates.append((0.3, "Fresh from the last 48 hours"))
        except (TypeError, ValueError):
            pass
    candidates.sort(key=lambda c: (-c[0], c[1]))
    return [{"reason": reason, "strength": round(strength, 3)}
            for strength, reason in candidates[:limit]]

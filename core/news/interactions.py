"""News V2 owner interactions (#23, N04) — like/dislike/undo, favorites, notes, opens,
dwell. Every action is REPLAY-SAFE: the caller's idempotency key makes a repeated
request a no-op (no double events, no double aggregation). Dislike follows the locked
product rule exactly: hidden immediately, ``UNDO_SECONDS`` (10) to undo, and no
negative profile influence until the window has passed un-reversed (plan §1/§6).

Callers own commit — every function mutates through the passed connection only.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

from core.news.contracts import UNDO_SECONDS, EventAction, InteractionEvent, Reaction
from core.news.repository import _ensure_once, record_event, upsert_interaction

DWELL_THRESHOLD_MS = 5_000       # "meaningful dwell": record only at/after this
DWELL_MAX_MS = 30 * 60 * 1000    # contract bound


def _now(now: datetime | None) -> datetime:
    return now or datetime.now(timezone.utc)


def _state(conn: sqlite3.Connection, item_id: int) -> dict:
    row = conn.execute("SELECT reaction, favorite, note, opens, dwell_ms, version"
                       " FROM news_interactions WHERE item_id=?", (item_id,)).fetchone()
    if not row:
        return {"item_id": item_id, "reaction": "none", "favorite": 0, "note": None,
                "opens": 0, "dwell_ms": 0, "version": 0}
    return {"item_id": item_id, "reaction": row[0], "favorite": row[1], "note": row[2],
            "opens": row[3], "dwell_ms": row[4], "version": row[5]}


def _require_item(conn: sqlite3.Connection, item_id: int) -> None:
    if not conn.execute("SELECT 1 FROM news_items WHERE id=?", (item_id,)).fetchone():
        raise ValueError(f"unknown news item {item_id}")


def _reexpire_if_unprotected(conn: sqlite3.Connection, item_id: int, now: datetime) -> None:
    """After unfavorite/note-clear: restore the 90-day clock ONLY when nothing else
    protects the item (plan §1: favorites and noted items are retained indefinitely)."""
    from core.news.contracts import RETENTION_DAYS
    state = _state(conn, item_id)
    if not state["favorite"] and not (state["note"] or "").strip():
        conn.execute("UPDATE news_items SET expires_at=? WHERE id=? AND expires_at IS NULL",
                     ((now + timedelta(days=RETENTION_DAYS)).isoformat(), item_id))


# ── reactions ────────────────────────────────────────────────────────────────────────
def like(conn: sqlite3.Connection, item_id: int, idempotency_key: str,
         now: datetime | None = None) -> dict:
    _ensure_once(conn); _require_item(conn, item_id)
    now_dt = _now(now)
    fresh = record_event(conn, InteractionEvent(
        item_id=item_id, action=EventAction.LIKE, idempotency_key=idempotency_key,
        created_at=now_dt.isoformat()))
    if fresh:
        return upsert_interaction(conn, item_id, reaction=Reaction.LIKE)
    return _state(conn, item_id)                      # replay → unchanged


def dislike(conn: sqlite3.Connection, item_id: int, idempotency_key: str,
            now: datetime | None = None) -> dict:
    """Hide immediately; return the exact undo deadline (now + 10s)."""
    _ensure_once(conn); _require_item(conn, item_id)
    now_dt = _now(now)
    undo_until = (now_dt + timedelta(seconds=UNDO_SECONDS)).isoformat()
    fresh = record_event(conn, InteractionEvent(
        item_id=item_id, action=EventAction.DISLIKE, idempotency_key=idempotency_key,
        created_at=now_dt.isoformat(), undo_until=undo_until))
    if fresh:
        state = upsert_interaction(conn, item_id, reaction=Reaction.DISLIKE)
        return {**state, "undo_until": undo_until}
    row = conn.execute("SELECT undo_until FROM news_interaction_events"
                       " WHERE idempotency_key=?", (idempotency_key,)).fetchone()
    return {**_state(conn, item_id), "undo_until": row[0] if row else None}


def undo_dislike(conn: sqlite3.Connection, item_id: int, idempotency_key: str,
                 now: datetime | None = None) -> dict:
    """Valid only while the newest un-reversed dislike's window is open. The reversal
    is linked onto the dislike event, which permanently blocks its profile influence.
    An expired window raises ``ValueError`` (the UI's grace period is exactly 10s)."""
    _ensure_once(conn); _require_item(conn, item_id)
    now_dt = _now(now)
    replay = conn.execute("SELECT 1 FROM news_interaction_events WHERE idempotency_key=?",
                          (idempotency_key,)).fetchone()
    if replay:
        return _state(conn, item_id)                  # replay → unchanged
    target = conn.execute(
        "SELECT id, undo_until FROM news_interaction_events"
        " WHERE item_id=? AND action='dislike' AND reversed_by IS NULL"
        " ORDER BY id DESC LIMIT 1", (item_id,)).fetchone()
    if not target or not target[1] or target[1] < now_dt.isoformat():
        raise ValueError(f"undo window closed for item {item_id}")
    record_event(conn, InteractionEvent(
        item_id=item_id, action=EventAction.UNDO, idempotency_key=idempotency_key,
        created_at=now_dt.isoformat()))
    undo_id = conn.execute("SELECT id FROM news_interaction_events WHERE idempotency_key=?",
                           (idempotency_key,)).fetchone()[0]
    conn.execute("UPDATE news_interaction_events SET reversed_by=? WHERE id=?",
                 (int(undo_id), int(target[0])))
    return upsert_interaction(conn, item_id, reaction=Reaction.NONE)


# ── favorites and notes (durable protection) ─────────────────────────────────────────
def set_favorite(conn: sqlite3.Connection, item_id: int, favorite: bool,
                 idempotency_key: str, now: datetime | None = None) -> dict:
    _ensure_once(conn); _require_item(conn, item_id)
    now_dt = _now(now)
    action = EventAction.FAVORITE if favorite else EventAction.UNFAVORITE
    fresh = record_event(conn, InteractionEvent(
        item_id=item_id, action=action, idempotency_key=idempotency_key,
        created_at=now_dt.isoformat()))
    if not fresh:
        return _state(conn, item_id)
    state = upsert_interaction(conn, item_id, favorite=favorite)
    if not favorite:
        _reexpire_if_unprotected(conn, item_id, now_dt)
    return state


def set_note(conn: sqlite3.Connection, item_id: int, note: str | None,
             idempotency_key: str, now: datetime | None = None) -> dict:
    """Upsert the private owner note; a non-empty note protects the item indefinitely,
    clearing it restores the retention clock unless the item is favorited."""
    _ensure_once(conn); _require_item(conn, item_id)
    now_dt = _now(now)
    text = (note or "").strip()
    fresh = record_event(conn, InteractionEvent(
        item_id=item_id, action=EventAction.NOTE, idempotency_key=idempotency_key,
        created_at=now_dt.isoformat(), payload={"has_text": bool(text)}))
    if not fresh:
        return _state(conn, item_id)
    state = upsert_interaction(conn, item_id, note=text or None)
    if text:
        conn.execute("UPDATE news_items SET expires_at=NULL WHERE id=?", (item_id,))
    else:
        _reexpire_if_unprotected(conn, item_id, now_dt)
    return state


# ── passive signals (aggregated, no optimistic-version churn) ────────────────────────
def record_open(conn: sqlite3.Connection, item_id: int, idempotency_key: str,
                now: datetime | None = None) -> dict:
    _ensure_once(conn); _require_item(conn, item_id)
    fresh = record_event(conn, InteractionEvent(
        item_id=item_id, action=EventAction.OPEN, idempotency_key=idempotency_key,
        created_at=_now(now).isoformat()))
    if fresh:
        upsert_interaction(conn, item_id)             # ensure the row exists
        conn.execute("UPDATE news_interactions SET opens=opens+1 WHERE item_id=?", (item_id,))
    return _state(conn, item_id)


def record_dwell(conn: sqlite3.Connection, item_id: int, ms: int, idempotency_key: str,
                 now: datetime | None = None) -> dict:
    """Record only MEANINGFUL dwell (>= threshold); shorter dwell is ignored without
    an event so replays of noise stay free. Bounded by the contract's 30-minute cap."""
    _ensure_once(conn); _require_item(conn, item_id)
    ms = int(ms)
    if ms < DWELL_THRESHOLD_MS:
        return {**_state(conn, item_id), "recorded": False}
    ms = min(ms, DWELL_MAX_MS)
    fresh = record_event(conn, InteractionEvent(
        item_id=item_id, action=EventAction.DWELL, idempotency_key=idempotency_key,
        created_at=_now(now).isoformat(), payload={"ms": ms}))
    if fresh:
        upsert_interaction(conn, item_id)
        conn.execute("UPDATE news_interactions SET dwell_ms=dwell_ms+? WHERE item_id=?", (ms, item_id))
    return {**_state(conn, item_id), "recorded": True}


# ── committed-dislike query (shared with personalization) ────────────────────────────
def committed_dislike(conn: sqlite3.Connection, item_id: int,
                      now: datetime | None = None) -> bool:
    """True when the item's newest un-reversed dislike has outlived its undo window —
    the ONLY condition under which a dislike may influence the profile (plan §6)."""
    row = conn.execute(
        "SELECT undo_until FROM news_interaction_events"
        " WHERE item_id=? AND action='dislike' AND reversed_by IS NULL"
        " ORDER BY id DESC LIMIT 1", (item_id,)).fetchone()
    return bool(row and row[0] and row[0] < _now(now).isoformat())

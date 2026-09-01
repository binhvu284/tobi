"""News V2 → Brain promotion (#23, N11) — the ONLY path from News into Brain.

Plan §6: *"News writes to Brain only through explicit `Save to Brain`."* Nothing here
runs on a schedule, on ingest, or on a like. It runs when the owner presses the button,
once per item, and never again.

Three rules make that safe:

1. **One boundary.** It calls ``core.brain.remember()`` — the accepted #20 facade that
   already routes legacy/shadow/on by ``brain_v2_mode()`` and already de-duplicates
   near-identical memories. No Brain V2 internal is imported, and no Brain table is
   written directly.
2. **Provenance.** The memory is stored with source ``news:<item_id>`` so the Brain page
   can show exactly where the fact came from, and ``list_memories(source=…)`` can find it.
3. **Idempotence.** ``news_brain_saves`` holds one row per item. A second press returns
   the first result with ``already_saved`` — it does not create a second memory, even if
   Brain's own similarity de-duplication would have merged it anyway.

The saved text is built DETERMINISTICALLY from stored evidence (title, source, recap or
excerpt, link). No LLM runs on this path, and source text is treated as evidence, never
as instructions.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from core.news.repository import _ensure_once

MAX_CONTENT = 600          # a Brain memory is a fact, not an article
CATEGORY = "work"          # AI/model/tool news is work context, not identity


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_memory_text(conn: sqlite3.Connection, item_id: int) -> tuple[str, dict]:
    """Deterministic memory text + the evidence it was built from. Raises ValueError
    for an unknown item so the route can answer 404 honestly."""
    _ensure_once(conn)
    row = conn.execute(
        "SELECT title, excerpt, recap, canonical_url, published_at, item_type"
        " FROM news_items WHERE id=?", (int(item_id),)).fetchone()
    if not row:
        raise ValueError(f"unknown news item {item_id}")
    title, excerpt, recap, url, published_at, item_type = row
    src = conn.execute("SELECT source FROM news_item_sources WHERE item_id=?"
                       " ORDER BY observed_at DESC, source LIMIT 1", (int(item_id),)).fetchone()
    source = src[0] if src else "news"
    body = (recap or excerpt or "").strip().replace("\r", " ").replace("\n", " ")
    parts = [f"From AI news ({source}): {(title or '').strip()}"]
    if body:
        parts.append(body)
    if url:
        parts.append(str(url))
    text = " — ".join(p for p in parts if p)[:MAX_CONTENT]
    return text, {"source": source, "url": url, "published_at": published_at,
                  "item_type": item_type, "title": title}


def existing_save(conn: sqlite3.Connection, item_id: int) -> dict | None:
    """The stored save for this item, or None. Cheap enough for list rendering."""
    _ensure_once(conn)
    row = conn.execute(
        "SELECT memory_id, provenance, action, content, saved_at"
        " FROM news_brain_saves WHERE item_id=?", (int(item_id),)).fetchone()
    if not row:
        return None
    return {"item_id": int(item_id), "memory_id": row[0], "provenance": row[1],
            "action": row[2], "content": row[3], "saved_at": row[4]}


def saved_item_ids(conn: sqlite3.Connection, item_ids: list[int]) -> set[int]:
    """Which of these items are already in Brain — one query, for the feed's save badge."""
    _ensure_once(conn)
    ids = [int(i) for i in item_ids]
    if not ids:
        return set()
    out: set[int] = set()
    for start in range(0, len(ids), 400):
        chunk = ids[start:start + 400]
        placeholders = ",".join("?" for _ in chunk)
        out.update(int(r[0]) for r in conn.execute(
            f"SELECT item_id FROM news_brain_saves WHERE item_id IN ({placeholders})", chunk))
    return out


def save_to_brain(conn: sqlite3.Connection, item_id: int) -> dict:
    """Promote one news item into Brain. Idempotent per item.

    Returns ``{ok, item_id, memory_id, provenance, action, content, already_saved}``.
    ``action`` is Brain's own word for what it did — ``active`` (new memory),
    ``merged`` (folded into an existing one), or ``pending``/``blocked`` when Brain
    could not store it, which is reported truthfully instead of being reshaped into
    a success.
    """
    _ensure_once(conn)
    prior = existing_save(conn, item_id)
    if prior:
        return {"ok": True, **prior, "already_saved": True}

    text, evidence = build_memory_text(conn, item_id)
    if not text.strip():
        raise ValueError("this item has no title or summary to remember")

    provenance = f"news:{int(item_id)}"
    from core import brain                       # accepted #20 facade — no internals
    result = brain.remember(text, CATEGORY, source=provenance)
    if not result.get("ok"):
        # Brain refused (e.g. sensitive content with the vault locked). Say so; do not
        # record a save that did not happen.
        return {"ok": False, "item_id": int(item_id), "already_saved": False,
                "action": result.get("action") or "blocked",
                "error": ((result.get("v2") or {}).get("error")
                          or "Brain could not store this right now."),
                "provenance": provenance, "content": text}

    conn.execute(
        "INSERT INTO news_brain_saves (item_id, memory_id, provenance, action, content, saved_at)"
        " VALUES (?,?,?,?,?,?)"
        " ON CONFLICT(item_id) DO NOTHING",
        (int(item_id), result.get("id"), provenance,
         str(result.get("action") or "active"), text, _utc_now()))
    stored = existing_save(conn, item_id) or {
        "item_id": int(item_id), "memory_id": result.get("id"), "provenance": provenance,
        "action": str(result.get("action") or "active"), "content": text,
        "saved_at": _utc_now()}
    return {"ok": True, **stored, "already_saved": False, "evidence": evidence}

"""News read-model for Chat (#23, N11c) — what TOBI answers News questions from.

The owner asked to be able to ask TOBI about the News page in normal conversation
("what's the top model right now?", "what did I favorite?", "summarise that Anthropic
story"). This module is the grounded read behind ``tool_read_news``: it returns only
what is actually stored, with its source and its timestamp attached, so an answer can
always be traced back to a real row.

Design rules it inherits from the rest of #23:

- **No LLM, no network.** Every value is read from the canonical store. If a summary
  exists it is the source's own text or a stored TOBI recap; nothing is generated here.
- **Never invent.** A missing score, growth figure, or date comes back absent, not
  guessed. Empty sections say they are empty and say why.
- **Falls back honestly.** When V2 has not collected anything yet, it reads the V1
  Explore tables rather than telling the owner "no news" while the page shows plenty.
- **Untrusted text.** Titles and summaries are source content. They are evidence for
  TOBI to describe, never instructions to follow, and are length-capped on the way out.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

MAX_ITEMS = 40
SNIPPET = 400          # per-item text handed to the model — enough to answer, bounded
BODY = 1500            # a single item read in full (section="item")

SECTIONS = ("overview", "models", "releases", "trending", "tools", "feed",
            "favorites", "notes", "item")


def _clip(text, limit: int = SNIPPET) -> str:
    s = " ".join(str(text or "").split())
    return s[:limit]


def _has_v2(conn: sqlite3.Connection) -> bool:
    try:
        return bool(conn.execute("SELECT 1 FROM news_items LIMIT 1").fetchone())
    except sqlite3.Error:
        return False


def _snapshot(conn: sqlite3.Connection, kind: str) -> list[dict]:
    """Newest entries for a rank snapshot kind, or [] when none has been built."""
    try:
        row = conn.execute(
            "SELECT entries_json, created_at FROM news_rank_snapshots WHERE kind=?"
            " ORDER BY id DESC LIMIT 1", (kind,)).fetchone()
    except sqlite3.Error:
        return []
    if not row:
        return []
    try:
        entries = json.loads(row[0]) or []
    except (TypeError, json.JSONDecodeError):
        return []
    for e in entries:
        e["snapshot_at"] = row[1]
    return entries


def _item_rows(conn: sqlite3.Connection, ids: list[int]) -> dict[int, dict]:
    if not ids:
        return {}
    placeholders = ",".join("?" for _ in ids)
    out: dict[int, dict] = {}
    for r in conn.execute(
            f"SELECT n.id, n.title, n.canonical_url, n.excerpt, n.recap, n.published_at,"
            f" n.first_seen_at, n.item_type,"
            f" (SELECT s.source FROM news_item_sources s WHERE s.item_id=n.id"
            f"   ORDER BY s.observed_at DESC LIMIT 1)"
            f" FROM news_items n WHERE n.id IN ({placeholders})", ids):
        out[int(r[0])] = {"item_id": int(r[0]), "title": _clip(r[1], 200), "url": r[2],
                          "summary": _clip(r[4] or r[3]), "published_at": r[5] or r[6],
                          "type": r[7], "source": r[8] or "news"}
    return out


# ── sections ─────────────────────────────────────────────────────────────────────────
def _models(conn: sqlite3.Connection, limit: int) -> dict:
    entries = _snapshot(conn, "models:top")
    if entries:
        return {"models": [{"rank": i + 1, "model": e.get("model_id"),
                            "score": e.get("score"),
                            "score_families": e.get("families"),
                            "evidence_sources": e.get("sources"),
                            "components": e.get("components"),
                            "formula_version": e.get("formula_version")}
                           for i, e in enumerate(entries[:limit])],
                "as_of": entries[0].get("snapshot_at"),
                "note": "Ranked by the stored News formula from independent score families."}
    try:
        rows = conn.execute(
            "SELECT model_id, provider, composite, intelligence, updated_at FROM explore_models"
            " WHERE composite IS NOT NULL ORDER BY composite DESC LIMIT ?", (limit,)).fetchall()
    except sqlite3.Error:
        rows = []
    if not rows:
        return {"models": [], "note": "No model ranking has been collected yet."}
    return {"models": [{"rank": i + 1, "model": r[0], "provider": r[1], "score": r[2],
                        "intelligence": r[3]} for i, r in enumerate(rows)],
            "as_of": rows[0][4], "source": "explore_v1"}


def _releases(conn: sqlite3.Connection, limit: int) -> dict:
    try:
        rows = conn.execute(
            "SELECT title, model_id, source_url, released_at, observed_at"
            " FROM news_model_releases ORDER BY COALESCE(released_at, observed_at) DESC"
            " LIMIT ?", (limit,)).fetchall()
    except sqlite3.Error:
        rows = []
    return {"releases": [{"title": _clip(r[0], 200), "model": r[1], "url": r[2],
                          "released_at": r[3] or r[4]} for r in rows],
            "note": "" if rows else "No model releases recorded yet."}


def _trending(conn: sqlite3.Connection, limit: int, window: str = "week") -> dict:
    win = window if window in ("day", "week", "month", "all") else "week"
    entries = _snapshot(conn, f"trending:github:{win}")
    repos = [{"rank": i + 1, "repo": e.get("repo"),
              # growth is present ONLY when it was really measured; "collecting" rows
              # carry no growth and must never be shown as if they did (plan §5).
              **({"new_stars_this_period": e["growth"]} if e.get("growth") is not None else {}),
              "total_stars": e.get("stars"), "language": e.get("language"),
              "description": _clip(e.get("description"), 200),
              "status": e.get("status"), "evidence": e.get("source")}
             for i, e in enumerate(entries[:limit])]
    return {"window": win, "repos": repos, "as_of": entries[0].get("snapshot_at") if entries else None,
            "note": "" if repos else "No GitHub trending snapshot yet — run a Trending refresh."}


def _tools(conn: sqlite3.Connection, limit: int) -> dict:
    entries = _snapshot(conn, "trending:tools")
    ids = [int(e["item_id"]) for e in entries[:limit] if e.get("item_id")]
    items = _item_rows(conn, ids)
    tools = []
    for e in entries[:limit]:
        base = items.get(int(e.get("item_id") or 0))
        if base:
            tools.append({**base, "engagement": e.get("engagement"), "trust": e.get("trust")})
    return {"tools": tools,
            "as_of": entries[0].get("snapshot_at") if entries else None,
            "note": "" if tools else "No tool discovery snapshot yet — run a Trending refresh."}


def _feed(conn: sqlite3.Connection, limit: int, mode: str = "for_you") -> dict:
    kind = "feed:latest" if mode == "latest" else "feed:for_you"
    entries = _snapshot(conn, kind)
    ids = [int(e["item_id"]) for e in entries[:limit] if e.get("item_id")]
    items = _item_rows(conn, ids)
    out = []
    for e in entries[:limit]:
        base = items.get(int(e.get("item_id") or 0))
        if not base:
            continue
        out.append({**base, "score": e.get("score"),
                    "why_shown": [r.get("reason") for r in (e.get("reasons") or [])]})
    if out:
        return {"mode": mode, "items": out, "as_of": entries[0].get("snapshot_at")}
    # V2 has not ranked anything — read the V1 feed so Chat still answers truthfully.
    try:
        rows = conn.execute(
            "SELECT title, url, summary, source_name, published_at, tobi_take"
            " FROM explore_items ORDER BY COALESCE(published_at, first_seen_at) DESC"
            " LIMIT ?", (limit,)).fetchall()
    except sqlite3.Error:
        rows = []
    return {"mode": mode, "source": "explore_v1" if rows else None,
            "items": [{"title": _clip(r[0], 200), "url": r[1],
                       "summary": _clip(r[5] or r[2]), "source": r[3],
                       "published_at": r[4]} for r in rows],
            "note": "" if rows else "The News feed has not collected anything yet."}


def _favorites(conn: sqlite3.Connection, limit: int, notes_only: bool = False) -> dict:
    where = "i.favorite=1" if not notes_only else "TRIM(COALESCE(i.note,'')) <> ''"
    try:
        rows = conn.execute(
            f"SELECT i.item_id, i.note, i.updated_at FROM news_interactions i"
            f" WHERE {where} ORDER BY i.updated_at DESC LIMIT ?", (limit,)).fetchall()
    except sqlite3.Error:
        rows = []
    items = _item_rows(conn, [int(r[0]) for r in rows])
    key = "notes" if notes_only else "favorites"
    return {key: [{**items.get(int(r[0]), {"item_id": int(r[0])}),
                   "note": _clip(r[1], 400) or None, "saved_at": r[2]} for r in rows],
            "note": "" if rows else
            ("No private notes yet." if notes_only else "Nothing has been favorited yet.")}


def _search(conn: sqlite3.Connection, query: str, limit: int) -> dict:
    like = f"%{query.strip()}%"
    try:
        rows = conn.execute(
            "SELECT id FROM news_items WHERE title LIKE ? OR excerpt LIKE ? OR recap LIKE ?"
            " ORDER BY COALESCE(published_at, first_seen_at) DESC LIMIT ?",
            (like, like, like, limit)).fetchall()
    except sqlite3.Error:
        rows = []
    items = _item_rows(conn, [int(r[0]) for r in rows])
    found = [items[int(r[0])] for r in rows if int(r[0]) in items]
    if found:
        return {"query": query, "matches": found}
    try:
        v1 = conn.execute(
            "SELECT title, url, summary, source_name, published_at FROM explore_items"
            " WHERE title LIKE ? OR summary LIKE ?"
            " ORDER BY COALESCE(published_at, first_seen_at) DESC LIMIT ?",
            (like, like, limit)).fetchall()
    except sqlite3.Error:
        v1 = []
    return {"query": query,
            "matches": [{"title": _clip(r[0], 200), "url": r[1], "summary": _clip(r[2]),
                         "source": r[3], "published_at": r[4]} for r in v1],
            "note": "" if v1 else f"Nothing in News matches “{_clip(query, 60)}”."}


def _item(conn: sqlite3.Connection, item_id: int) -> dict:
    row = conn.execute(
        "SELECT n.id, n.title, n.canonical_url, n.excerpt, n.recap, n.published_at,"
        " n.first_seen_at, n.item_type FROM news_items n WHERE n.id=?", (int(item_id),)).fetchone()
    if not row:
        return {"error": f"No news item {item_id}."}
    sources = [{"source": r[0], "trust": r[1], "engagement": r[2], "url": r[3],
                "observed_at": r[4]} for r in conn.execute(
        "SELECT source, trust, engagement, original_url, observed_at FROM news_item_sources"
        " WHERE item_id=? ORDER BY observed_at DESC", (int(item_id),))]
    state = conn.execute(
        "SELECT reaction, favorite, note, opens FROM news_interactions WHERE item_id=?",
        (int(item_id),)).fetchone()
    saved = conn.execute("SELECT memory_id, saved_at FROM news_brain_saves WHERE item_id=?",
                         (int(item_id),)).fetchone()
    return {"item_id": int(row[0]), "title": _clip(row[1], 300), "url": row[2],
            "summary": _clip(row[4] or row[3], BODY),
            "has_tobi_recap": bool(row[4]),
            "published_at": row[5] or row[6], "type": row[7], "sources": sources,
            "your_reaction": (state[0] if state else "none"),
            "favorited": bool(state[1]) if state else False,
            "your_note": _clip(state[2], 400) if state and state[2] else None,
            "saved_to_brain": bool(saved),
            "saved_to_brain_at": saved[1] if saved else None}


def _overview(conn: sqlite3.Connection, limit: int) -> dict:
    small = max(3, min(limit, 5))
    counts = {}
    for label, sql in (("items", "SELECT COUNT(*) FROM news_items"),
                       ("favorites", "SELECT COUNT(*) FROM news_interactions WHERE favorite=1"),
                       ("notes", "SELECT COUNT(*) FROM news_interactions WHERE TRIM(COALESCE(note,''))<>''"),
                       ("saved_to_brain", "SELECT COUNT(*) FROM news_brain_saves")):
        try:
            counts[label] = int(conn.execute(sql).fetchone()[0])
        except sqlite3.Error:
            counts[label] = 0
    try:
        freshest = conn.execute(
            "SELECT MAX(COALESCE(published_at, first_seen_at)) FROM news_items").fetchone()[0]
    except sqlite3.Error:
        freshest = None
    return {"collected": counts, "newest_item_at": freshest,
            "top_models": _models(conn, small).get("models", []),
            "latest_releases": _releases(conn, small).get("releases", []),
            "for_you": _feed(conn, small).get("items", []),
            "trending_repos": _trending(conn, small).get("repos", [])}


def read(section: str = "overview", query: str = "", item_id: int | None = None,
         limit: int = 10, window: str = "week", mode: str = "for_you",
         conn: sqlite3.Connection | None = None) -> dict:
    """One grounded read of the News store. See ``SECTIONS`` for the valid sections."""
    own = conn is None
    if conn is None:
        from core.database import get_connection
        conn = get_connection()
    try:
        n = max(1, min(int(limit or 10), MAX_ITEMS))
        sec = (section or "overview").strip().lower()
        if query and query.strip() and sec in ("overview", "search", ""):
            sec = "search"
        base = {"section": sec, "news_v2_has_data": _has_v2(conn),
                "read_at": datetime.now(timezone.utc).isoformat()}
        if sec == "search":
            return {**base, **_search(conn, query, n)}
        if sec == "item":
            if not item_id:
                return {**base, "error": "item_id is required to read one story."}
            return {**base, **_item(conn, int(item_id))}
        if sec == "models":
            return {**base, **_models(conn, n)}
        if sec == "releases":
            return {**base, **_releases(conn, n)}
        if sec == "trending":
            return {**base, **_trending(conn, n, window)}
        if sec == "tools":
            return {**base, **_tools(conn, n)}
        if sec == "feed":
            return {**base, **_feed(conn, n, mode)}
        if sec == "favorites":
            return {**base, **_favorites(conn, n)}
        if sec == "notes":
            return {**base, **_favorites(conn, n, notes_only=True)}
        if sec not in SECTIONS:
            return {**base, "error": f"section must be one of {', '.join(SECTIONS)}"}
        return {**base, **_overview(conn, n)}
    finally:
        if own:
            conn.close()

"""News V2 cross-module context (#23, N11) — plan §6 "Allowed context classes".

The feed can be nudged by what TOBI already knows about the owner from OTHER parts
of the system. That nudge is deliberately small and deliberately transparent:

- only three classes are allowed — ``owner_interests`` (approved Brain memories),
  ``project_topics`` (active PM projects), and ``chat_topics`` (stored chat session
  SUMMARIES, never the transcripts themselves);
- each class is off by default and has its own owner toggle in News settings;
- every contribution carries a provenance label, so a card can honestly say which
  part of TOBI caused it to rank higher;
- the total is capped at ±5 points by ``personalization.context_delta`` and is
  discarded entirely on any item the owner has acted on directly.

Explicitly EXCLUDED, per plan §6: raw chat transcripts, private files, tool output,
and unapproved (pending/rejected/deleted) memories. This module only ever READS, and
every read is bounded and wrapped — a missing or broken source contributes nothing
rather than failing a feed rebuild. No LLM: matching is deterministic token overlap.
"""
from __future__ import annotations

import sqlite3
from typing import Iterable

from core.news.contracts import CONTEXT_CLASSES, NewsSettings
from core.news.personalization import _tokens

# Points one matching context topic contributes, per class. Kept well under
# personalization.CONTEXT_CAP (5.0) so even several matches stay a nudge, not a takeover.
CLASS_POINTS = {
    "owner_interests": 1.5,     # the owner told TOBI this about himself
    "project_topics": 1.25,     # he is actively working on this
    "chat_topics": 1.0,         # he has been talking about this
}
MAX_TOPICS_PER_CLASS = 40       # bounded read: a runaway table cannot slow a rebuild
MAX_MATCHES_PER_CLASS = 3       # one class cannot stack more than 3 topics on one item
_MIN_TOKEN_LEN = 4              # matches _TOKEN in personalization; keeps "the"/"ai" out


def _topic_tokens(texts: Iterable[str], limit: int) -> dict[str, str]:
    """{token: the source phrase it came from} — the phrase is the provenance label."""
    out: dict[str, str] = {}
    for text in texts:
        phrase = (text or "").strip()
        if not phrase:
            continue
        for token in _tokens(phrase):
            if len(token) >= _MIN_TOKEN_LEN and token not in out:
                out[token] = phrase[:80]
                if len(out) >= limit:
                    return out
    return out


# ── the three allowed classes ────────────────────────────────────────────────────────
def _owner_interest_topics() -> dict[str, str]:
    """APPROVED Brain memories only. Read through the ``core.brain`` facade (the accepted
    #20 service boundary) with ``status='active'`` — pending, rejected, and deleted
    memories are never read, and no V2 internal is imported or mutated."""
    from core import brain
    rows = []
    for category in ("preferences", "goals", "work"):
        try:
            rows.extend(brain.list_memories(category=category, status="active", limit=60))
        except Exception:
            continue
    return _topic_tokens([str(r.get("content") or "") for r in rows], MAX_TOPICS_PER_CLASS)


def _project_topics(conn: sqlite3.Connection) -> dict[str, str]:
    """Active PM projects — name and description only (the owner's own words)."""
    try:
        rows = conn.execute(
            "SELECT name, description FROM pm_projects WHERE status='active'"
            " ORDER BY updated_at DESC LIMIT 30").fetchall()
    except sqlite3.Error:
        return {}
    return _topic_tokens([f"{r[0] or ''} {r[1] or ''}" for r in rows], MAX_TOPICS_PER_CLASS)


def _chat_topics(conn: sqlite3.Connection) -> dict[str, str]:
    """Stored chat session SUMMARIES — the aggregate TOBI already wrote, not the
    transcript. ``chat_messages`` is never read here, by design (plan §6)."""
    try:
        rows = conn.execute(
            "SELECT summary FROM chat_session_summaries ORDER BY updated_at DESC LIMIT 20"
        ).fetchall()
    except sqlite3.Error:
        return {}
    return _topic_tokens([str(r[0] or "") for r in rows], MAX_TOPICS_PER_CLASS)


def available_topics(conn: sqlite3.Connection, settings: NewsSettings) -> dict[str, dict[str, str]]:
    """{class: {token: provenance phrase}} for the classes the owner has ENABLED.
    A disabled class is not even read — the toggle is a real boundary, not a filter."""
    loaders = {
        "owner_interests": lambda: _owner_interest_topics(),
        "project_topics": lambda: _project_topics(conn),
        "chat_topics": lambda: _chat_topics(conn),
    }
    out: dict[str, dict[str, str]] = {}
    for cls in CONTEXT_CLASSES:
        if not settings.context_classes.get(cls, False):
            continue
        try:
            topics = loaders[cls]()
        except Exception:
            topics = {}                    # a broken source contributes nothing, never raises
        if topics:
            out[cls] = topics
    return out


# ── scoring ──────────────────────────────────────────────────────────────────────────
def collect_context_scores(conn: sqlite3.Connection, item_ids: Iterable[int],
                           settings: NewsSettings) -> dict[int, dict[str, float]]:
    """``{item_id: {class: points}}`` in the shape ``ranking.build_feed_snapshots``
    expects. Empty when every class is off — which is the shipped default, so context
    changes nothing until the owner turns a class on."""
    ids = [int(i) for i in item_ids]
    if not ids:
        return {}
    topics = available_topics(conn, settings)
    if not topics:
        return {}
    scores: dict[int, dict[str, float]] = {}
    for chunk_start in range(0, len(ids), 400):
        chunk = ids[chunk_start:chunk_start + 400]
        placeholders = ",".join("?" for _ in chunk)
        for item_id, title in conn.execute(
                f"SELECT id, title FROM news_items WHERE id IN ({placeholders})", chunk):
            item_tokens = set(_tokens(title or ""))
            if not item_tokens:
                continue
            for cls, class_topics in topics.items():
                hits = sorted(item_tokens & set(class_topics))[:MAX_MATCHES_PER_CLASS]
                if hits:
                    scores.setdefault(int(item_id), {})[cls] = round(
                        CLASS_POINTS[cls] * len(hits), 3)
    return scores


def explain(conn: sqlite3.Connection, item_id: int,
            settings: NewsSettings) -> list[dict]:
    """Provenance for ONE item: which class, which of the owner's own phrases matched,
    and how many points it added. This is what makes the nudge inspectable rather than
    magic — the News settings panel and the card's "Why shown" both read it."""
    topics = available_topics(conn, settings)
    if not topics:
        return []
    row = conn.execute("SELECT title FROM news_items WHERE id=?", (int(item_id),)).fetchone()
    if not row:
        return []
    item_tokens = set(_tokens(row[0] or ""))
    out: list[dict] = []
    for cls in CONTEXT_CLASSES:
        class_topics = topics.get(cls) or {}
        hits = sorted(item_tokens & set(class_topics))[:MAX_MATCHES_PER_CLASS]
        if not hits:
            continue
        out.append({"context_class": cls,
                    "matched": hits,
                    "because": class_topics[hits[0]],
                    "points": round(CLASS_POINTS[cls] * len(hits), 3)})
    return out


CLASS_LABELS = {
    "owner_interests": "what you asked TOBI to remember",
    "project_topics": "a project you are working on",
    "chat_topics": "something you have been discussing in Chat",
}

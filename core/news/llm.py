"""Background content-LLM routing for News V2 (#23, owner QA: "no crash content").

The feed recap + Tool Discovery spotlight run in the BACKGROUND with no chat
session, so they have no picked model. Historically they asked the router for the
``"simple"`` task tier, which — with no default configured — fell through to the
free OpenRouter reasoning model. That model emits its chain-of-thought AS the
answer, so the owner saw raw planning text ("We need to produce a spotlight using
only the given material… must not invent…") instead of a spotlight.

Fix (owner: "always assign the current chat model — glm 5.2 — to LLM workflows"):

- ``resolve_content_model()`` picks the SAME model the owner uses in chat: an
  explicit config default, else the model on the most-recently-used chat session
  (the literal "current model in chat"), else the best available non-free model.
  It never returns the free reasoning tier.

- ``complete()`` sanitizes the output: strips ``<think>`` blocks and REJECTS text
  that is still raw reasoning (echoes of our own prompt, first-person planning),
  so a bad model yields NO card — an honest skip, never "crash content".

- ``clear_leaked_recaps()`` self-heals: any recap already stored that reads as
  leaked reasoning is nulled on the next refresh, making it re-eligible so a good
  model can replace it.
"""
from __future__ import annotations

import logging
import re
import sqlite3

_SURFACE = "news_v2"
_log = logging.getLogger("tobi.news.llm")

# Reasoning-model scaffolding some backends emit inline. Stripped before inspection.
_THINK_RE = re.compile(r"<\s*(think|thinking|reason|reasoning|scratchpad|analysis)\s*>.*?"
                       r"<\s*/\s*\1\s*>", re.I | re.S)

# Near-certain leak markers: echoes of OUR OWN system prompt reflected back inside the
# model's reasoning. A finished, owner-facing recap never contains these. Any one → reject.
_HARD = (
    "the given material", "must not invent", "the material only", "the material says",
    "using only the material", "using only the given", "never invent", "material: name",
    "untrusted material", "the description:", "so we can only",
)
# First-person planning phrases. Two or more distinct hits → the model narrated its
# process instead of writing content → reject (an ordinary recap has none of these).
_SOFT = (
    "we need to", "we must", "we can't", "we cannot", "we could", "we should",
    "we can only", "we are told", "i need to", "i should ", "let me ", "not sure",
    "that would be inventing", "as an ai", "i cannot", "we have to",
)


def resolve_content_model() -> str:
    """The model background content jobs should use — the owner's current chat model.

    Priority: explicit config default → most-recently-used chat session model →
    best available non-free model. Returns "" when nothing usable is configured, so
    the caller SKIPS (no free-tier reasoning fallback, no fabricated content)."""
    try:
        from core.model_router import load_llm_config
        explicit = (load_llm_config().get("default_model") or "").strip()
        if explicit:
            return explicit
    except Exception:
        pass
    try:                                        # the literal "current model in chat"
        from core import chat_store
        for session in chat_store.list_sessions():
            model = (session.get("model") or "").strip()
            if model:
                return model
    except Exception:
        pass
    try:                                        # best available capable model, never :free
        from core.model_router import available_models
        usable = [m["id"] for m in available_models() if not m["id"].endswith(":free")]
        for pref in ("glm:", "anthropic:", "openai:gpt", "gemini:", "grok:", "codex:"):
            for mid in usable:
                if mid.startswith(pref):
                    return mid
        if usable:
            return usable[0]
    except Exception:
        pass
    return ""


def sanitize(text: str | None) -> str | None:
    """Clean model output; return None if it still reads as leaked reasoning.

    Strips ``<think>`` blocks, then rejects text that echoes our prompt or narrates
    the model's own process — so the caller degrades honestly rather than showing
    chain-of-thought as content."""
    if not text:
        return None
    cleaned = _THINK_RE.sub("", text).strip()
    if len(cleaned) < 40:
        return None
    low = cleaned.lower()
    if any(marker in low for marker in _HARD):
        return None
    if sum(1 for marker in _SOFT if marker in low) >= 2:
        return None
    return cleaned


def looks_leaked(text: str | None) -> bool:
    """True when a stored recap is raw reasoning (i.e. would be rejected by sanitize)."""
    return bool((text or "").strip()) and sanitize(text) is None


def complete(system: str, user: str, feature: str, max_tokens: int) -> str | None:
    """One background completion on the owner's current chat model, sanitized.

    Returns None (→ caller skips) when no model resolves, the call fails, or the
    output reads as leaked reasoning. Tagged for usage attribution under news_v2."""
    model = resolve_content_model()
    if not model:
        _log.warning("news content (%s): no usable model resolved — skipping", feature)
        return None
    try:
        from core.model_router import get_llm, set_usage_context
        prev = set_usage_context(_SURFACE, feature)
        try:
            client = get_llm(model=model)
            text = client.complete([{"role": "user", "content": user}],
                                   system=system, max_tokens=max_tokens)
        finally:
            set_usage_context(prev["surface"], prev["feature"])
    except Exception as exc:
        # Make silent content failures diagnosable (this was an unexplained empty card):
        # the MC console now names the model and the real transport/auth error.
        _log.warning("news content (%s) LLM failed on %s: %s", feature, model, exc)
        return None
    cleaned = sanitize(text)
    if cleaned is None:
        _log.info("news content (%s) on %s rejected as leaked/empty (%d chars)",
                  feature, model, len(text or ""))
    return cleaned


def clear_leaked_recaps(conn: sqlite3.Connection, item_types: tuple[str, ...]) -> int:
    """Null out already-stored recaps that read as leaked reasoning so a good model
    can regenerate them. Bounded, never raises. Returns the count cleared."""
    if not item_types:
        return 0
    try:
        placeholders = ",".join("?" for _ in item_types)
        rows = conn.execute(
            f"SELECT id, recap FROM news_items"
            f" WHERE recap IS NOT NULL AND item_type IN ({placeholders})", item_types).fetchall()
        bad = [row[0] for row in rows if looks_leaked(row[1])]
        if bad:
            conn.executemany("UPDATE news_items SET recap=NULL, recap_at=NULL WHERE id=?",
                             [(item_id,) for item_id in bad])
            conn.commit()
        return len(bad)
    except Exception:
        return 0

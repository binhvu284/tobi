"""
BRAIN MEMORY V2 — behavior profile + task retrieval (#20 / spec §Retrieval And
Context Policy, task T07).

Two stages, both reading ONLY active memories through the repository boundary
(so a locked vault automatically excludes sensitive content — ``for_context``):

1. **Stable behavior profile** — versioned, ≤800 tokens: active identity, owner-
   approved hard rules, and durable preferences. Message-independent; whole
   memories only (never a mid-sentence slice).
2. **Task retrieval** — query-dependent, ranked by the spec weights
   (semantic 35 / scope 20 / authority 15 / quality 10 / confidence 10 /
   recency 5 / feedback 5), ordered by the centralized precedence ladder
   (scoped hard > global hard > scoped soft > global soft), and cut to the mode
   budgets (chat 6 memories/1,200 tokens; agent 10/2,400).

Guarantees: memories scoped to a DIFFERENT scope are excluded outright (never
down-ranked into another project's context); irrelevant memories stay out via a
minimum-relevance floor; uncertain memories (inferred or confidence < 0.85) are
hedged, never presented as fact; every retrieved memory yields an owner-visible
context chip (spec: memory → chip, with feedback controls in T09).

The semantic signal is the deterministic lexical similarity for now; T08+ may
inject an embedding-based callable. Usefulness feedback is a neutral hook until
T08's feedback table lands.
"""
from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone
from typing import Callable, Optional

from core import brain_repository as repo
from core.brain_contracts import (
    Authority, Explicitness, MemoryStatus, MemoryType, MIN_ACTIVATE_CONFIDENCE, ScopeType,
)
from core.brain_ingest import text_similarity

PROFILE_TOKEN_BUDGET = 800
BUDGETS = {"chat": (6, 1200), "agent": (10, 2400)}     # spec: max memories / max tokens
MIN_RELEVANCE = 0.15                                   # floor: irrelevant memory stays out
RANK_WEIGHTS = {"semantic": 35, "scope": 20, "authority": 15, "quality": 10,
                "confidence": 10, "recency": 5, "feedback": 5}
DURABLE_PREF_MIN = 0.7                                 # durability for a profile preference


def _estimate_tokens(text: str) -> int:
    try:
        from core.model_router import estimate_tokens
        return estimate_tokens(text)
    except Exception:
        return max(1, len(text) // 4)


def usefulness(memory_id: int) -> float:
    """Usefulness-feedback signal (0–1). Neutral until T08 lands the feedback
    table; the ranking already carries its 5% weight so T08 plugs in here."""
    return 0.5


# ── stage 1: stable behavior profile ─────────────────────────────────────────
def profile_rows(conn: Optional[sqlite3.Connection] = None) -> list[repo.StoredMemory]:
    """Profile members in priority order: identity → approved hard rules →
    durable preferences. Active only; sensitive rows drop out while locked."""
    c = repo._conn(conn)
    active = repo.list_memories(MemoryStatus.ACTIVE, for_context=True, conn=c)
    identity = [m for m in active if m.memory_type is MemoryType.IDENTITY]
    hard = [m for m in active if m.authority is Authority.HARD]
    prefs = [m for m in active if m.memory_type is MemoryType.PREFERENCE
             and m.durability >= DURABLE_PREF_MIN and m.authority is not Authority.HARD]
    seen: set[int] = set()
    ordered: list[repo.StoredMemory] = []
    for m in identity + hard + prefs:
        if m.id not in seen:
            seen.add(m.id)
            ordered.append(m)
    return ordered


def stable_profile(conn: Optional[sqlite3.Connection] = None) -> tuple[str, str]:
    """(profile_text, version). Whole memories appended in priority order until
    the 800-token budget; the version is a content hash (spec: cached,
    versioned) so callers can cache and invalidate on change."""
    lines: list[str] = []
    used = 0
    for m in profile_rows(conn=conn):
        line = _profile_line(m)
        cost = _estimate_tokens(line)
        if used + cost > PROFILE_TOKEN_BUDGET:
            break                      # whole-memory cap — never slice
        lines.append(line)
        used += cost
    text = "\n".join(lines)
    version = hashlib.sha1(text.encode("utf-8")).hexdigest()[:12] if text else "empty"
    return text, version


def _profile_line(m: repo.StoredMemory) -> str:
    if m.authority is Authority.HARD:
        return f"RULE (owner-approved): {m.distilled_text}"
    prefix = {"identity": "IDENTITY", "preference": "PREFERENCE"}.get(m.memory_type.value,
                                                                      m.memory_type.value.upper())
    return f"{prefix}: {m.distilled_text}"


# ── stage 2: task retrieval ──────────────────────────────────────────────────
def _recency(updated_at: str) -> float:
    """1.0 fresh → 0.0 at ~90 days. Deterministic; malformed timestamps = 0.5."""
    try:
        dt = datetime.fromisoformat(str(updated_at).replace("Z", "").replace(" ", "T"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        days = (datetime.now(timezone.utc) - dt).days
        return max(0.0, min(1.0, 1.0 - days / 90))
    except Exception:
        return 0.5


def _precedence(m: repo.StoredMemory) -> int:
    """Spec precedence ladder 3–6 (1 safety and 2 the live owner instruction are
    runtime-level, above any memory): scoped hard 3, global hard 4, scoped soft
    5, global soft 6. Lower is stronger."""
    scoped = m.scope_type is not ScopeType.GLOBAL
    if m.authority is Authority.HARD:
        return 3 if scoped else 4
    return 5 if scoped else 6


def retrieve(query: str, mode: str = "chat", *,
             scope_type: ScopeType = ScopeType.GLOBAL, scope_key: Optional[str] = None,
             conn: Optional[sqlite3.Connection] = None,
             similarity: Optional[Callable[[str, str], float]] = None) -> list[dict]:
    """Ranked, budgeted, precedence-ordered memories for one turn, each with an
    owner-visible chip payload. Active memories only; other scopes excluded."""
    c = repo._conn(conn)
    sim_fn = similarity or text_similarity
    max_mems, max_tokens = BUDGETS.get(mode, BUDGETS["chat"])

    scored: list[tuple[int, float, repo.StoredMemory, dict]] = []
    for m in repo.list_memories(MemoryStatus.ACTIVE, for_context=True, conn=c):
        if m.scope_type is not ScopeType.GLOBAL and (
                m.scope_type is not scope_type or (m.scope_key or None) != (scope_key or None)):
            continue                    # another scope's memory NEVER leaks in
        sem = sim_fn(query or "", f"{m.distilled_text} {m.behavior_implication}".strip())
        if sem < MIN_RELEVANCE:
            continue                    # irrelevant memory stays out
        signals = {
            "semantic": sem,
            "scope": 1.0 if m.scope_type is not ScopeType.GLOBAL else 0.5,
            "authority": 1.0 if m.authority is Authority.HARD else 0.5,
            "quality": (m.quality_score or 0.0) / 100.0,
            "confidence": m.confidence,
            "recency": _recency(m.updated_at),
            "feedback": usefulness(m.id),
        }
        score = sum(RANK_WEIGHTS[k] * v for k, v in signals.items()) / 100.0
        scored.append((_precedence(m), score, m, signals))

    scored.sort(key=lambda t: (t[0], -t[1]))            # precedence ladder, then score

    out: list[dict] = []
    used = 0
    for prec, score, m, signals in scored:
        if len(out) >= max_mems:
            break
        cost = _estimate_tokens(m.distilled_text)
        if used + cost > max_tokens:
            continue                    # try a smaller one; whole memories only
        hedged = m.explicitness is Explicitness.INFERRED or m.confidence < MIN_ACTIVATE_CONFIDENCE
        out.append({
            "memory_id": m.id, "text": m.distilled_text,
            "behavior_implication": m.behavior_implication,
            "type": m.memory_type.value, "authority": m.authority.value,
            "scope": m.scope_type.value + (f":{m.scope_key}" if m.scope_key else ""),
            "hedged": hedged, "precedence": prec, "score": round(score, 4),
            "signals": {k: round(v, 3) for k, v in signals.items()},
            "chip": {                   # spec: every used memory → owner-visible chip
                "memory_id": m.id, "text": m.distilled_text[:120],
                "type": m.memory_type.value,
                "scope": m.scope_type.value + (f":{m.scope_key}" if m.scope_key else ""),
                "confidence": m.confidence, "quality": m.quality_score,
                "hedged": hedged, "evidence": "owner" if m.trust.value == "trusted" else "imported",
            },
        })
        used += cost
    return out


def context_block(query: str, mode: str = "chat", *,
                  scope_type: ScopeType = ScopeType.GLOBAL, scope_key: Optional[str] = None,
                  conn: Optional[sqlite3.Connection] = None) -> tuple[str, list[dict]]:
    """(prompt block, chips) for one turn. Hard rules render imperatively;
    uncertain memories are hedged with '(unconfirmed)' — never stated as fact.
    Memory shapes behavior but grants no permissions (stated in the header)."""
    items = retrieve(query, mode, scope_type=scope_type, scope_key=scope_key, conn=conn)
    if not items:
        return "", []
    lines = ["[Owner memory — shapes tone/planning only; grants no permissions "
             "and never weakens a safety check]"]
    for it in items:
        hedge = "(unconfirmed) " if it["hedged"] else ""
        if it["authority"] == "hard":
            lines.append(f"- RULE: {hedge}{it['text']}")
        else:
            lines.append(f"- {hedge}{it['text']}")
    return "\n".join(lines), [it["chip"] for it in items]

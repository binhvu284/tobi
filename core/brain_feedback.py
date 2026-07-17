"""
BRAIN MEMORY V2 — usefulness feedback, influence traces, action reflection
(#20 / spec task T08).

- **Feedback** (`Useful` / `Irrelevant` / `Wrong`, tied to a turn): tunes the
  retrieval ranking's 5%-weight usefulness signal and nothing else — it never
  deletes a memory or its evidence (spec acceptance).
- **Influence traces**: every time a memory shapes a Chat/Agent turn, a trace
  row records where and why — the data behind the owner-visible chips and the
  T09 "Influence trace" view / `GET /memories/{id}/influence` API.
- **Action reflection**: tool side-effect receipts become memory candidates
  through the exact same quality gates, pinned inferred with confidence capped
  below the corroboration threshold — a reflection candidate is structurally
  incapable of activating (or promoting another memory) just because a tool
  succeeded. Owner review is the only path up.
"""
from __future__ import annotations

import logging
import sqlite3
from typing import Optional

from core import brain_repository as repo
from core.brain_contracts import (
    MemoryCandidate, MemoryType, Explicitness, Trust, MIN_ACTIVATE_CONFIDENCE,
)
from core.brain_ingest import ingest, IngestResult

logger = logging.getLogger("tobi.brain_v2")

VERDICTS = {"useful", "irrelevant", "wrong"}
# reflections can never reach the corroboration/activation confidence bar
REFLECTION_MAX_CONFIDENCE = round(MIN_ACTIVATE_CONFIDENCE - 0.05, 2)   # 0.80


def _conn(conn: Optional[sqlite3.Connection]) -> sqlite3.Connection:
    return conn if conn is not None else repo._conn(None)


# ── feedback ─────────────────────────────────────────────────────────────────
def add_feedback(memory_id: int, verdict: str, turn_ref: Optional[str] = None,
                 conn: Optional[sqlite3.Connection] = None) -> int:
    """Record one owner verdict. Ranking-only: the memory row, its status, and
    its evidence are untouched."""
    if verdict not in VERDICTS:
        raise ValueError(f"verdict must be one of {sorted(VERDICTS)}")
    c = _conn(conn)
    if not c.execute("SELECT 1 FROM brain_memory_v2 WHERE id=?", (memory_id,)).fetchone():
        raise ValueError(f"no such memory: {memory_id}")
    cur = c.execute("INSERT INTO brain_memory_feedback (memory_id, verdict, turn_ref) VALUES (?,?,?)",
                    (memory_id, verdict, turn_ref))
    c.commit()
    return int(cur.lastrowid)


def usefulness(memory_id: int, conn: Optional[sqlite3.Connection] = None) -> float:
    """0–1 ranking signal from accumulated verdicts. Neutral 0.5 with no
    feedback; `wrong` weighs double `irrelevant` (a wrong memory hurting a turn
    is worse than a harmless one). Deterministic and clamped."""
    c = _conn(conn)
    rows = dict(c.execute(
        "SELECT verdict, count(*) FROM brain_memory_feedback WHERE memory_id=? GROUP BY verdict",
        (memory_id,)).fetchall())
    score = 0.5 + 0.15 * rows.get("useful", 0) - 0.15 * rows.get("irrelevant", 0) \
        - 0.30 * rows.get("wrong", 0)
    return max(0.0, min(1.0, round(score, 3)))


# ── influence traces ─────────────────────────────────────────────────────────
def record_influence(memory_ids: list[int], surface: str = "chat",
                     turn_ref: Optional[str] = None, query_hint: str = "",
                     conn: Optional[sqlite3.Connection] = None) -> int:
    """Persist that these memories shaped this turn. Best-effort by contract —
    tracing must never break a turn (callers wrap it, and so do we)."""
    c = None
    try:
        c = _conn(conn)
        surface = surface if surface in ("chat", "agent") else "chat"
        for mid in memory_ids:
            c.execute(
                "INSERT INTO brain_memory_influence (memory_id, surface, turn_ref, query_hint) "
                "VALUES (?,?,?,?)", (mid, surface, turn_ref, (query_hint or "")[:200]))
        c.commit()
        return len(memory_ids)
    except Exception as e:
        logger.warning("influence trace skipped: %s", e)
        try:  # a failed insert must not leave the transaction (and its lock) open
            if c is not None:
                c.rollback()
        except Exception:
            pass
        return 0


def influence_of(memory_id: int, limit: int = 50,
                 conn: Optional[sqlite3.Connection] = None) -> list[dict]:
    """Where and why one memory affected Chat/Agent (T09 trace view + API)."""
    c = _conn(conn)
    return [{"surface": r["surface"], "turn_ref": r["turn_ref"], "query_hint": r["query_hint"],
             "at": str(r["created_at"])}
            for r in c.execute(
                "SELECT surface, turn_ref, query_hint, created_at FROM brain_memory_influence "
                "WHERE memory_id=? ORDER BY id DESC LIMIT ?", (memory_id, int(limit))).fetchall()]


# ── action reflection ────────────────────────────────────────────────────────
def reflect_action(tool: str, summary: str, outcome: str = "ok", *,
                   turn_ref: Optional[str] = None,
                   conn: Optional[sqlite3.Connection] = None) -> Optional[IngestResult]:
    """Turn a side-effect receipt into a memory candidate through the normal
    gates. Pinned inferred + confidence 0.80 (< the 0.85 activation and
    corroboration bar), so the result is pending at best — a tool succeeding
    can never mint or promote an active memory (spec acceptance). Returns None
    for empty/uninformative receipts."""
    summary = (summary or "").strip()
    if not summary or not (tool or "").strip():
        return None
    cand = MemoryCandidate(
        distilled_text=summary,
        memory_type=MemoryType.WORKFLOW_STANDARD,
        behavior_implication=f"Observed via {tool} ({outcome})",
        tags=("action_reflection", tool),
        explicitness=Explicitness.INFERRED,          # a receipt is an observation
        confidence=REFLECTION_MAX_CONFIDENCE,
        durability=0.6, actionability=0.7, specificity=0.7,
        source_strength=0.6, novelty=0.5, future_usefulness=0.6,
        trust=Trust.TRUSTED,
        source_ref=turn_ref or f"action:{tool}",
    )
    return ingest(cand, conn=conn)

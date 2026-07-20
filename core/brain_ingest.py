"""
BRAIN MEMORY V2 — ingestion + quality engine (#20 / spec §Remember flow, task T03).

The deterministic half of the Remember pipeline:

    parse (candidate_from_dict) → dedup → conflict/correction links → activation gate

An LLM (T04/T05) proposes raw candidate dicts; nothing it says is trusted until
``candidate_from_dict`` turns it into a validated ``MemoryCandidate`` — content is
always data here, never instructions, so prompt-injection text in a candidate or
its evidence cannot change how it is gated (spec §gates 7: untrusted evidence can
never create an active hard rule; hard rules are pending regardless).

Automation thresholds (spec §Import flow tuning points): a match must share a
compatible type and scope, then similarity ≥ 0.88 merges into the existing memory
(evidence + corroboration, no new row) and 0.62–0.88 records a ``conflicts_with``
link and forces the newcomer to pending. Corrections supersede: the old memory is
kept with status ``superseded`` plus an explicit link — never silently overwritten.
Inferred pending memories are promoted only by two independent corroborating
observations at confidence ≥ 0.85 (spec §gates 4). Rejected candidates retain
only non-sensitive metadata (spec §gates 1).

Flag-dark: nothing calls ``ingest()`` from a live path until T04 wires Remember
behind ``owner_flags.brain_v2_mode()``.
"""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, replace
from difflib import SequenceMatcher
from typing import Callable, Optional

from core import brain_repository as repo
from core.brain_contracts import (
    MemoryCandidate, MemoryType, ScopeType, Authority, Explicitness, Trust,
    MemoryStatus, LinkType, activation_gate,
    ACTIVATE_AT, MIN_ACTIVATE_CONFIDENCE,
)

# spec §Import flow: "Retain existing similarity defaults as initial tuning points"
MERGE_AT = 0.88      # similarity >= → duplicate: merge evidence into the existing memory
CONFLICT_AT = 0.62   # similarity in [CONFLICT_AT, MERGE_AT) → conflicts_with + pending

# non-sensitive placeholder kept when a sensitive candidate is rejected (gates 1:
# "retain only non-sensitive rejection metadata for evaluation")
REJECTED_SENSITIVE_META = "[rejected: sensitive content not retained]"


# ── typed extraction boundary ────────────────────────────────────────────────
_KNOWN_KEYS = {
    "distilled_text", "memory_type", "behavior_implication", "tags",
    "scope_type", "scope_key", "authority", "explicitness", "confidence",
    "durability", "actionability", "specificity", "source_strength",
    "novelty", "future_usefulness", "quality_score", "suggested_usage",
    "evidence_excerpt", "source_ref", "trust", "sensitive",
}
_ENUM_FIELDS = {
    "memory_type": MemoryType, "scope_type": ScopeType, "authority": Authority,
    "explicitness": Explicitness, "trust": Trust,
}


def candidate_from_dict(raw: dict) -> MemoryCandidate:
    """Parse one raw (LLM-proposed, untrusted) dict into a validated candidate.

    Strict on meaning, lenient on noise: unknown keys are dropped, enum fields
    must match the contract exactly (a made-up memory_type raises ValueError),
    and every value constraint is enforced by MemoryCandidate itself. This is
    the only door raw extraction output may use.
    """
    if not isinstance(raw, dict):
        raise ValueError("candidate must be a dict")
    kw: dict = {}
    for key, value in raw.items():
        if key not in _KNOWN_KEYS:
            continue  # LLM junk keys are dropped, never interpreted
        enum_cls = _ENUM_FIELDS.get(key)
        if enum_cls is not None:
            try:
                kw[key] = enum_cls(str(value).strip().lower())
            except ValueError:
                raise ValueError(f"{key} has no such value: {value!r}")
        elif key == "tags":
            if not isinstance(value, (list, tuple)):
                raise ValueError("tags must be a list")
            kw[key] = tuple(str(t) for t in value)
        else:
            kw[key] = value
    # Security (#20 review P1): never trust a model-supplied quality_score. The
    # score is authoritative only when derived from the six quality dimensions,
    # so we drop any provided score and let MemoryCandidate recompute it. Without
    # this, an untrusted import could claim quality_score=100 with every
    # dimension at zero and auto-activate past the gate.
    kw.pop("quality_score", None)
    return MemoryCandidate(**kw)


# ── deterministic text similarity ────────────────────────────────────────────
_WORD_RE = re.compile(r"[a-z0-9]+")


def _normalize(text: str) -> str:
    return " ".join(_WORD_RE.findall(text.lower()))


def text_similarity(a: str, b: str) -> float:
    """Deterministic 0–1 similarity: an even blend of character-level
    SequenceMatcher and token Jaccard over normalized text. The blend matters:
    char ratio alone scores "…format is PDF" vs "…format is Excel" ≈ 0.9 (shared
    prefix) and would MERGE a contradiction — Jaccard punishes the changed value
    word and drags it into the conflict band, while pure filler-word edits stay
    above the merge line. No model, no network — T07 may inject an
    embedding-based callable through ``ingest(similarity=...)`` later."""
    na, nb = _normalize(a), _normalize(b)
    if not na or not nb:
        return 0.0
    ratio = SequenceMatcher(None, na, nb).ratio()
    ta, tb = set(na.split()), set(nb.split())
    jaccard = len(ta & tb) / len(ta | tb)
    return 0.5 * ratio + 0.5 * jaccard


# ── result contract ──────────────────────────────────────────────────────────
@dataclass(frozen=True)
class IngestResult:
    outcome: str                     # active | pending | rejected | merged | conflicted | corrected
    memory_id: Optional[int]         # the row the candidate ended up in (merge target on merge)
    status: Optional[MemoryStatus]   # final status of memory_id
    matched_id: Optional[int] = None  # existing memory involved (merge/conflict/correction target)
    links: tuple[tuple[int, int, str], ...] = ()


# ── engine internals ─────────────────────────────────────────────────────────
def _scope_compatible(cand: MemoryCandidate, mem: repo.StoredMemory) -> bool:
    return cand.scope_type is mem.scope_type and (cand.scope_key or None) == (mem.scope_key or None)


def _match_pool(conn: sqlite3.Connection) -> list[repo.StoredMemory]:
    """Existing memories eligible for merge/conflict automation: live rows only.
    Sensitive rows are skipped while the vault is locked (their text is redacted,
    so no meaningful match is possible — fail safe, never match on a sentinel)."""
    pool: list[repo.StoredMemory] = []
    for status in (MemoryStatus.ACTIVE, MemoryStatus.PENDING):
        for m in repo.list_memories(status, conn=conn):
            if not m.redacted:
                pool.append(m)
    return pool


def _best_match(cand: MemoryCandidate, pool: list[repo.StoredMemory],
                sim_fn: Callable[[str, str], float]) -> tuple[Optional[repo.StoredMemory], float]:
    """Best same-scope match. Types must be identical, except corrections, which
    may target any type in scope (spec §gates 6 — a correction corrects content)."""
    best, best_sim = None, 0.0
    for m in pool:
        if not _scope_compatible(cand, m):
            continue
        if cand.memory_type is not MemoryType.CORRECTION and m.memory_type is not cand.memory_type:
            continue
        if cand.memory_type is MemoryType.CORRECTION and m.memory_type is MemoryType.CORRECTION:
            continue  # a correction targets content, not an older correction
        s = sim_fn(cand.distilled_text, m.distilled_text)
        if s > best_sim:
            best, best_sim = m, s
    return best, best_sim


def _has_conflict_links(conn: sqlite3.Connection, memory_id: int) -> bool:
    row = conn.execute(
        "SELECT 1 FROM brain_memory_links WHERE link_type=? AND (from_id=? OR to_id=?) LIMIT 1",
        (LinkType.CONFLICTS_WITH.value, memory_id, memory_id),
    ).fetchone()
    return row is not None


def _distinct_sources(conn: sqlite3.Connection, memory_id: int) -> int:
    return conn.execute(
        "SELECT COUNT(DISTINCT source_ref) FROM brain_memory_evidence "
        "WHERE memory_id=? AND source_ref IS NOT NULL AND source_ref != ''",
        (memory_id,),
    ).fetchone()[0]


def _merge(cand: MemoryCandidate, target: repo.StoredMemory,
           conn: sqlite3.Connection, compat_ref: Optional[int] = None) -> IngestResult:
    """Duplicate: fold the observation into the existing memory — evidence +
    confidence, no new row. May promote an inferred pending memory to active when
    two independent corroborating observations reach confidence ≥ 0.85 and every
    other activation condition already holds (spec §gates 4)."""
    repo.add_evidence(target.id, cand.evidence_excerpt, cand.source_ref, cand.trust, conn=conn)
    if compat_ref is not None and target.compat_ref is None:  # backfill the legacy link
        conn.execute("UPDATE brain_memory_v2 SET compat_ref=? WHERE id=?", (compat_ref, target.id))
        conn.commit()
    new_conf = max(target.confidence, cand.confidence)
    if new_conf != target.confidence:
        repo.set_confidence(target.id, new_conf, conn=conn)

    status = target.status
    if (target.status is MemoryStatus.PENDING
            and target.explicitness is Explicitness.INFERRED
            and target.confidence >= MIN_ACTIVATE_CONFIDENCE
            and cand.confidence >= MIN_ACTIVATE_CONFIDENCE
            and _distinct_sources(conn, target.id) >= 2
            and target.quality_score >= ACTIVATE_AT
            and not target.sensitive
            and target.authority is Authority.SOFT
            and not _has_conflict_links(conn, target.id)):
        repo.set_status(target.id, MemoryStatus.ACTIVE, conn=conn)
        status = MemoryStatus.ACTIVE

    return IngestResult(outcome="merged", memory_id=target.id, status=status, matched_id=target.id)


def _reject(cand: MemoryCandidate, conn: sqlite3.Connection, compat_ref: Optional[int] = None) -> IngestResult:
    """Persist rejection metadata only. A sensitive reject keeps no content at
    all — placeholder text, no evidence, no vault payload (spec §gates 1)."""
    meta = cand
    if cand.sensitive:
        meta = replace(cand, distilled_text=REJECTED_SENSITIVE_META, evidence_excerpt="",
                       source_ref=cand.source_ref, sensitive=False,
                       tags=tuple(cand.tags) + ("rejected_sensitive",))
    mid = repo.save(meta, status=MemoryStatus.REJECTED, compat_ref=compat_ref, conn=conn)
    return IngestResult(outcome="rejected", memory_id=mid, status=MemoryStatus.REJECTED)


# ── dry-run preview (T05) ────────────────────────────────────────────────────
def preview(candidate: MemoryCandidate, *, conn: Optional[sqlite3.Connection] = None,
            similarity: Optional[Callable[[str, str], float]] = None) -> IngestResult:
    """What ``ingest()`` WOULD do against the current store — no writes at all.

    Mirrors ingest's decision order exactly (corrections → merge → trash →
    conflict → gate); the drift guard is tests asserting preview == ingest on
    the same store. Merge promotion is previewed prospectively (as if the new
    evidence were already added). memory_id is None except for merges, where it
    is the existing target id.
    """
    if not isinstance(candidate, MemoryCandidate):
        raise TypeError("preview() requires a validated MemoryCandidate")
    c = repo._conn(conn)
    sim_fn = similarity or text_similarity
    match, sim = _best_match(candidate, _match_pool(c), sim_fn)

    if (candidate.memory_type is MemoryType.CORRECTION and match is not None
            and sim >= CONFLICT_AT and activation_gate(candidate) is not MemoryStatus.REJECTED):
        return IngestResult(outcome="corrected", memory_id=None,
                            status=activation_gate(candidate), matched_id=match.id)
    if match is not None and sim >= MERGE_AT:
        status = match.status
        prospective_sources = _distinct_sources(c, match.id) + (
            1 if candidate.source_ref and not c.execute(
                "SELECT 1 FROM brain_memory_evidence WHERE memory_id=? AND source_ref=?",
                (match.id, candidate.source_ref)).fetchone() else 0)
        if (match.status is MemoryStatus.PENDING
                and match.explicitness is Explicitness.INFERRED
                and match.confidence >= MIN_ACTIVATE_CONFIDENCE
                and candidate.confidence >= MIN_ACTIVATE_CONFIDENCE
                and prospective_sources >= 2
                and match.quality_score >= ACTIVATE_AT
                and not match.sensitive
                and match.authority is Authority.SOFT
                and not _has_conflict_links(c, match.id)):
            status = MemoryStatus.ACTIVE
        return IngestResult(outcome="merged", memory_id=match.id, status=status, matched_id=match.id)
    if activation_gate(candidate) is MemoryStatus.REJECTED:
        return IngestResult(outcome="rejected", memory_id=None, status=MemoryStatus.REJECTED)
    if match is not None and sim >= CONFLICT_AT:
        return IngestResult(outcome="conflicted", memory_id=None,
                            status=activation_gate(candidate, has_conflict=True), matched_id=match.id)
    status = activation_gate(candidate)
    return IngestResult(outcome=status.value, memory_id=None, status=status)


# ── the engine ───────────────────────────────────────────────────────────────
def ingest(candidate: MemoryCandidate, *, conn: Optional[sqlite3.Connection] = None,
           similarity: Optional[Callable[[str, str], float]] = None,
           compat_ref: Optional[int] = None) -> IngestResult:
    """Run one validated candidate through dedup → conflict/correction →
    activation gate, persisting through the repository boundary. Deterministic:
    the same candidate against the same store always lands the same way.

    ``compat_ref`` (T04) links the resulting V2 row to its legacy
    ``brain_memories`` id; on a merge it backfills the target's link if empty."""
    if not isinstance(candidate, MemoryCandidate):
        raise TypeError("ingest() requires a validated MemoryCandidate")
    c = repo._conn(conn)
    sim_fn = similarity or text_similarity

    match, sim = _best_match(candidate, _match_pool(c), sim_fn)

    # corrections: supersede the matched memory, keep history (spec §gates 6).
    # A trash-scored correction never supersedes anything — it falls through to
    # plain rejection below instead of dethroning a good memory.
    if (candidate.memory_type is MemoryType.CORRECTION and match is not None
            and sim >= CONFLICT_AT and activation_gate(candidate) is not MemoryStatus.REJECTED):
        status = activation_gate(candidate)
        mid = repo.save(candidate, status=status, compat_ref=compat_ref, conn=c)
        repo.link(mid, match.id, LinkType.SUPERSEDES, conn=c)
        repo.set_status(match.id, MemoryStatus.SUPERSEDED, conn=c)
        return IngestResult(outcome="corrected", memory_id=mid, status=status,
                            matched_id=match.id, links=((mid, match.id, LinkType.SUPERSEDES.value),))

    # duplicate: merge, never a second row
    if match is not None and sim >= MERGE_AT:
        return _merge(candidate, match, c, compat_ref)

    # trash: reject before conflict bookkeeping — a rejected candidate creates no links
    if activation_gate(candidate) is MemoryStatus.REJECTED:
        return _reject(candidate, c, compat_ref)

    # conflict band: keep both, link them, force the newcomer to owner review
    if match is not None and sim >= CONFLICT_AT:
        status = activation_gate(candidate, has_conflict=True)  # always pending here
        mid = repo.save(candidate, status=status, compat_ref=compat_ref, conn=c)
        repo.link(mid, match.id, LinkType.CONFLICTS_WITH, conn=c)
        return IngestResult(outcome="conflicted", memory_id=mid, status=status,
                            matched_id=match.id, links=((mid, match.id, LinkType.CONFLICTS_WITH.value),))

    # clean landing: the deterministic gate decides
    status = activation_gate(candidate)
    mid = repo.save(candidate, status=status, compat_ref=compat_ref, conn=c)
    return IngestResult(outcome=status.value, memory_id=mid, status=status)

"""
BRAIN MEMORY V2 — Remember routing (#20 / spec task T04).

Routes the owner's explicit Remember (API, Conductor tool, Telegram /remember)
through the V2 pipeline behind ``owner_flags.brain_v2_mode()``:

- ``off``    → legacy path untouched (flag rollback restores it byte-for-byte).
- ``shadow`` → legacy result returned unchanged; V2 ingest runs alongside
               best-effort (exceptions logged, never surfaced) with a
               ``compat_ref`` back to the legacy row.
- ``on``     → V2 ingest is authoritative; a legacy compatibility row is still
               written (existing UI/context readers keep working until T07/T09)
               and the legacy response shape is preserved with an additive
               ``v2`` key. Sensitive memories are the exception: they are never
               mirrored into legacy plaintext — V2 encrypts, legacy gets nothing.

Extraction here is explicit-owner-input extraction: an LLM proposal (strict
JSON → ``candidate_from_dict``) with a deterministic heuristic fallback, both
floored so an explicit "remember this" is never auto-trashed — worst case it
queues as pending (spec T04 acceptance: explicit safe memories activate;
risky/inferred content queues).
"""
from __future__ import annotations

import logging
import re
import sqlite3
from dataclasses import replace
from typing import Optional

from core import vault
from core import brain_repository as repo
from core.brain_contracts import (
    MemoryCandidate, MemoryType, Explicitness, Trust, MemoryStatus, REJECT_BELOW,
)
from core.brain_ingest import candidate_from_dict, ingest, IngestResult

logger = logging.getLogger("tobi.brain_v2")

# legacy category → V2 type; anything unmapped stays a FACT and keeps the legacy
# category as a tag (spec: legacy categories become tags/compat labels, never a
# second type system)
CATEGORY_TO_TYPE = {
    "identity": MemoryType.IDENTITY,
    "preferences": MemoryType.PREFERENCE,
    "relationships": MemoryType.RELATIONSHIP,
    "work": MemoryType.PROJECT_CONTEXT,
    "goals": MemoryType.PROJECT_CONTEXT,
    "habits": MemoryType.FACT,
    "psychology": MemoryType.FACT,
    "health": MemoryType.FACT,
}

# conservative sensitivity net for the heuristic path (the LLM path judges from
# meaning); health-category remembers default to sensitive
_SENSITIVE_RE = re.compile(
    r"\b(password|passphrase|pin|otp|bank(ing)?|credit\s*card|iban|account\s*number|"
    r"address|phone\s*number|passport|id\s*card|ssn|salary|income|medical|diagnos\w+|"
    r"medication|therapy|hospital)\b", re.I)


def heuristic_candidate(content: str, category: Optional[str] = None,
                        source_ref: str = "remember") -> MemoryCandidate:
    """Deterministic fallback candidate for an explicit owner Remember.

    Dims are calibrated so a typical explicit remember scores ~72: strong enough
    to activate when safe, while the sensitive/hard/conflict gates still queue
    risky content. No model, no network."""
    sensitive = bool(_SENSITIVE_RE.search(content)) or category == "health"
    return MemoryCandidate(
        distilled_text=content,
        memory_type=CATEGORY_TO_TYPE.get(category or "", MemoryType.FACT),
        tags=(category,) if category else (),
        explicitness=Explicitness.EXPLICIT,   # the owner said "remember this"
        confidence=0.9,
        durability=0.85, actionability=0.6, specificity=0.7,
        source_strength=0.9, novelty=0.5, future_usefulness=0.7,  # score 71.9
        trust=Trust.TRUSTED,
        sensitive=sensitive,
        source_ref=source_ref,
    )


_EXTRACT_PROMPT = """You distill one explicit owner statement into a typed memory candidate.
Reply with ONLY a JSON object (no prose) with keys:
distilled_text (concise third-person restatement), memory_type (one of: fact, identity,
preference, correction, behavior_rule, workflow_standard, frustration_trigger, decision,
project_context, relationship), tags (list of short strings), confidence (0-1),
durability, actionability, specificity, source_strength, novelty, future_usefulness (each 0-1),
sensitive (true only for private/financial/medical/location data), behavior_implication (short).

Owner statement: {content}
Owner category hint: {category}"""


def llm_candidate(content: str, category: Optional[str] = None,
                  source_ref: str = "remember") -> Optional[MemoryCandidate]:
    """LLM extraction for an explicit Remember. Returns None on any failure —
    the caller falls back to the deterministic heuristic. The model's output is
    data: it enters only through candidate_from_dict, and explicitness/trust/
    source are pinned here, never taken from the model."""
    from core import brain  # local import: brain imports this module (avoid cycle)
    raw = brain._llm(_EXTRACT_PROMPT.format(content=content, category=category or "none"),
                     max_tokens=400, task_type="classify")
    if not raw:
        return None
    try:
        parsed = brain._parse_json(raw)
        if not isinstance(parsed, dict):
            return None
        parsed.pop("explicitness", None)   # pinned: the owner stated it
        parsed.pop("trust", None)          # pinned: owner input is trusted
        parsed.pop("source_ref", None)
        parsed.pop("authority", None)      # hard rules require deliberate flows, not Remember
        cand = candidate_from_dict(parsed)
        if category and category not in cand.tags:
            cand = replace(cand, tags=tuple(cand.tags) + (category,))
        return replace(cand, explicitness=Explicitness.EXPLICIT, trust=Trust.TRUSTED,
                       source_ref=source_ref)
    except Exception as e:
        logger.warning("V2 remember extraction fell back to heuristic: %s", e)
        return None


def extract_candidate(content: str, category: Optional[str] = None,
                      source_ref: str = "remember") -> MemoryCandidate:
    """LLM extraction with deterministic fallback, floored: an explicit Remember
    is never auto-trashed — a sub-35 score is raised to the pending band."""
    cand = llm_candidate(content, category, source_ref) or heuristic_candidate(
        content, category, source_ref)
    if (cand.quality_score or 0.0) < REJECT_BELOW:
        cand = replace(cand, quality_score=REJECT_BELOW,
                       tags=tuple(cand.tags) + ("low_quality_explicit",))
    return cand


# ── shadow: run V2 alongside legacy, never surface a failure ─────────────────
def remember_shadow(content: str, category: Optional[str] = None,
                    compat_ref: Optional[int] = None,
                    conn: Optional[sqlite3.Connection] = None) -> Optional[IngestResult]:
    """Best-effort V2 ingest next to a completed legacy remember. Returns the
    IngestResult, or None when V2 could not run (e.g. sensitive + locked vault).
    Never raises — shadow mode must not change legacy behavior."""
    try:
        cand = extract_candidate(content, category)
        return ingest(cand, conn=conn, compat_ref=compat_ref)
    except Exception as e:
        logger.warning("V2 shadow remember skipped: %s", e)
        return None


# ── on: V2 authoritative, legacy compat row, legacy response shape ───────────
_ACTION_MAP = {"active": "active", "merged": "merged", "corrected": "active",
               "pending": "pending", "conflicted": "pending", "rejected": "pending"}


def remember_on(content: str, category: str,
                conn: Optional[sqlite3.Connection] = None) -> dict:
    """Authoritative V2 remember. Preserves the legacy response shape
    ``{ok, id, category, action}`` (id = legacy row id) and adds a ``v2`` key.

    Non-sensitive memories are mirrored into a legacy compatibility row so
    every existing reader keeps working. Sensitive memories are NOT — mirroring
    would put the plaintext right back into the unencrypted legacy table; they
    live only in V2 (encrypted), with ``id: None`` and action ``pending``.
    """
    from core import brain  # legacy writes go through the existing helpers
    c = repo._conn(conn)
    cand = extract_candidate(content, category)

    try:
        res = ingest(cand, conn=c)
    except vault.VaultLocked:
        # Vault down + sensitive content: behave exactly like legacy (which is
        # what runs today), and say why V2 was skipped.
        legacy = brain.remember_legacy(content, category)
        legacy["v2"] = {"skipped": "vault_locked"}
        return legacy

    v2_info = {"id": res.memory_id, "outcome": res.outcome,
               "status": res.status.value if res.status else None}

    if cand.sensitive:
        return {"ok": True, "id": None, "category": category,
                "action": _ACTION_MAP.get(res.outcome, "pending"), "v2": v2_info}

    # mirror into legacy so current UI/context readers stay coherent until T07/T09
    if res.outcome == "merged":
        target = repo.read(res.memory_id, conn=c)
        if target is not None and target.compat_ref is not None:
            conn2 = brain.get_connection()
            brain._confirm_raise(conn2, target.compat_ref)
            conn2.commit()
            conn2.close()
            return {"ok": True, "id": target.compat_ref, "category": category,
                    "action": "merged", "v2": v2_info}
        # merge target predates compat linking — create the legacy row now
        legacy_id = brain.add_memory(content, category, confidence=cand.confidence,
                                     source="remember", status="active")
        c.execute("UPDATE brain_memory_v2 SET compat_ref=? WHERE id=? AND compat_ref IS NULL",
                  (legacy_id, res.memory_id))
        c.commit()
        return {"ok": True, "id": legacy_id, "category": category,
                "action": "merged", "v2": v2_info}

    legacy_status = "active" if res.status is MemoryStatus.ACTIVE else "pending"
    legacy_id = brain.add_memory(content, category, confidence=cand.confidence,
                                 source="remember", status=legacy_status)
    c.execute("UPDATE brain_memory_v2 SET compat_ref=? WHERE id=?", (legacy_id, res.memory_id))
    c.commit()
    return {"ok": True, "id": legacy_id, "category": category,
            "action": _ACTION_MAP.get(res.outcome, "pending"), "v2": v2_info}

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

# Keyword type inference for the heuristic path. When the background LLM is
# unavailable (or returns junk), the legacy category classifier degrades to a
# blanket "identity" default, so every Remember was mis-typed as identity. These
# rules recover a sensible type from the content itself, first match wins.
_TYPE_RULES = [
    (MemoryType.BEHAVIOR_RULE,
     r"\b(always|never|must|should always|don'?t ever|make sure|ensure you|"
     r"when i (say|said|ask|mention)|whenever i)\b"),
    (MemoryType.FRUSTRATION_TRIGGER,
     r"\b(annoy\w*|frustrat\w*|hate when|drives me|pisses me|hallucinat\w*|stop (doing|saying))\b"),
    (MemoryType.PREFERENCE,
     r"\b(i prefer|prefer(s|red)?|i like|i love|i hate|i want|favou?rite|i'?d rather|"
     r"call me|address me as|please use)\b"),
    (MemoryType.RELATIONSHIP,
     r"\bmy (wife|husband|partner|friend|colleague|boss|manager|team|mother|father|"
     r"mom|dad|brother|sister|son|daughter|co-?founder)\b"),
    (MemoryType.WORKFLOW_STANDARD,
     r"\b(workflow|process|procedure|report|format|template|checklist|standard|"
     r"weekly|daily|routine|deliver(ed|y)?)\b"),
    (MemoryType.PROJECT_CONTEXT,
     r"\b(project|repo(sitor(y|ies))?|codebase|mission control|\bmc\b|deploy\w*|"
     r"feature|endpoint|api|database|tobi|dashboard|build|pipeline)\b"),
    (MemoryType.IDENTITY,
     r"\b(i am|i'?m a|my name is|i work as|i'?m from|i live in|i was born|my role is)\b"),
]

# Meta-instruction wrappers the owner types around a Remember; stripped so the
# stored text is the fact, not the framing. Order-independent, applied repeatedly.
_PREAMBLE_RE = re.compile(
    r"^\s*(so\s+)?(please\s+)?(also\s+)?(remember|note|keep in mind|don'?t forget|"
    r"save|store|remember this|remember that)[:,]?\s+(this|that|it)?\b[:,]?\s*", re.I)
_TRAILER_RE = re.compile(
    r"\s*(understand\??|understood\??|got it\??|okay\??|ok\??|clear\??|"
    r"remember (it|this|that)?( to your brain)?\.?|to your brain\.?)\s*$", re.I)


def _clean_remember_text(content: str) -> str:
    """Trim the conversational framing owners wrap around a fact so the stored
    memory reads as a fact, not a chat line. Conservative: only strips known
    leading/trailing wrappers, never touches the middle."""
    text = content.strip()
    for _ in range(3):
        new = _TRAILER_RE.sub("", _PREAMBLE_RE.sub("", text)).strip()
        if new == text:
            break
        text = new
    # unwrap a fully-quoted remainder
    if len(text) >= 2 and text[0] in "\"'“‘" and text[-1] in "\"'”’":
        text = text[1:-1].strip()
    return text or content.strip()


def _classify_type(content: str, category: Optional[str]) -> MemoryType:
    """Keyword type inference. A real category hint (not the LLM-failure
    'identity' default) is honoured first; otherwise the content decides."""
    if category and category != "identity" and category in CATEGORY_TO_TYPE:
        return CATEGORY_TO_TYPE[category]
    low = content.lower()
    for mtype, pat in _TYPE_RULES:
        if re.search(pat, low):
            return mtype
    # fall back to the (possibly weak) category hint, else FACT
    return CATEGORY_TO_TYPE.get(category or "", MemoryType.FACT)


def _looks_rambling(content: str) -> bool:
    """A long or clearly conversational Remember can't be trusted as a clean,
    distilled fact — it should queue for review, not auto-activate."""
    words = len(content.split())
    meta = re.search(r"\b(when i (say|said|ask)|i meant|something like|understand\?|"
                     r"remember it to your brain|what (changes|update|feature))\b",
                     content, re.I)
    return words > 22 or bool(meta)


def heuristic_candidate(content: str, category: Optional[str] = None,
                        source_ref: str = "remember") -> MemoryCandidate:
    """Deterministic fallback candidate for an explicit owner Remember.

    Clean, short statements score ~72 and activate when safe. Long or
    conversational input (which the LLM would normally distill, but can't when
    the background model is down) is typed by keyword, lightly de-framed, and
    scored into the pending band so trash never silently enters the profile —
    it surfaces for the owner to review, edit, or approve. No model, no network."""
    cleaned = _clean_remember_text(content)
    sensitive = bool(_SENSITIVE_RE.search(content)) or category == "health"
    mtype = _classify_type(cleaned, category)
    tags = (category,) if category and category != "identity" else ()

    if _looks_rambling(content):
        # undistilled + rambling → land in pending (score ~52), not active
        return MemoryCandidate(
            distilled_text=cleaned,
            memory_type=mtype,
            tags=tags + ("undistilled",),
            explicitness=Explicitness.EXPLICIT,
            confidence=0.75,
            durability=0.7, actionability=0.5, specificity=0.35,
            source_strength=0.9, novelty=0.4, future_usefulness=0.45,  # ~52 → pending
            trust=Trust.TRUSTED,
            sensitive=sensitive,
            source_ref=source_ref,
        )
    return MemoryCandidate(
        distilled_text=cleaned,
        memory_type=mtype,
        tags=tags,
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
        # Sensitive content + locked vault: V2 save() fails closed BEFORE writing
        # anything. Do NOT fall back to remember_legacy() — that would drop the
        # secret straight into the unencrypted legacy table, defeating encryption
        # (#20 review P1). Refuse and tell the owner to unlock the vault. Nothing
        # is stored in either store.
        return {"ok": False, "id": None, "category": category, "action": "blocked",
                "v2": {"skipped": "vault_locked",
                       "error": "This looks sensitive — unlock the vault to store it."}}

    v2_info = {"id": res.memory_id, "outcome": res.outcome,
               "status": res.status.value if res.status else None}

    if cand.sensitive:
        from core import brain_v2_compat
        brain_v2_compat.record_change(res.memory_id, "create", "owner", mirror=False)
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
            from core import brain_v2_compat
            brain_v2_compat.record_change(res.memory_id, "merge", "auto", mirror=False)
            return {"ok": True, "id": target.compat_ref, "category": category,
                    "action": "merged", "v2": v2_info}
        # merge target predates compat linking — create the legacy row now
        legacy_id = brain.add_memory(content, category, confidence=cand.confidence,
                                     source="remember", status="active")
        c.execute("UPDATE brain_memory_v2 SET compat_ref=? WHERE id=? AND compat_ref IS NULL",
                  (legacy_id, res.memory_id))
        c.commit()
        from core import brain_v2_compat
        brain_v2_compat.record_change(res.memory_id, "merge", "auto", mirror=False)
        return {"ok": True, "id": legacy_id, "category": category,
                "action": "merged", "v2": v2_info}

    legacy_status = "active" if res.status is MemoryStatus.ACTIVE else "pending"
    legacy_id = brain.add_memory(content, category, confidence=cand.confidence,
                                 source="remember", status=legacy_status)
    c.execute("UPDATE brain_memory_v2 SET compat_ref=? WHERE id=?", (legacy_id, res.memory_id))
    c.commit()
    from core import brain_v2_compat
    brain_v2_compat.record_change(res.memory_id, "create", "owner", mirror=False)
    return {"ok": True, "id": legacy_id, "category": category,
            "action": _ACTION_MAP.get(res.outcome, "pending"), "v2": v2_info}

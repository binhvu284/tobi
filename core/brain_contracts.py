"""
BRAIN MEMORY V2 — typed contracts (#20 / spec §Memory V2 Contracts, task T01).

Pure, dependency-free value types plus scoring and the deterministic activation
gate. No database, no model calls. Every candidate is validated on construction,
so "no unvalidated dict crosses an extraction, repository, context, or API
boundary."

This module is inert until later tasks (T03+) wire it into the Remember/import
paths behind ``owner_flags.brain_v2_mode()``. Importing or constructing these
types changes no runtime behavior on its own.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


# ── enums ────────────────────────────────────────────────────────────────────
class MemoryType(str, Enum):
    FACT = "fact"
    IDENTITY = "identity"
    PREFERENCE = "preference"
    CORRECTION = "correction"
    BEHAVIOR_RULE = "behavior_rule"
    WORKFLOW_STANDARD = "workflow_standard"
    FRUSTRATION_TRIGGER = "frustration_trigger"
    DECISION = "decision"
    PROJECT_CONTEXT = "project_context"
    RELATIONSHIP = "relationship"


class ScopeType(str, Enum):
    GLOBAL = "global"          # applies across all of TOBI
    PROJECT = "project"
    CONNECTOR = "connector"
    WORKFLOW = "workflow"
    SURFACE = "surface"


class Authority(str, Enum):
    SOFT = "soft"              # influences tone / defaults / planning / presentation
    HARD = "hard"              # a hard rule — always requires explicit owner approval


class Explicitness(str, Enum):
    EXPLICIT = "explicit"      # the owner stated it
    INFERRED = "inferred"      # derived from observation


class Trust(str, Enum):
    TRUSTED = "trusted"
    UNTRUSTED = "untrusted"    # imported / third-party evidence


class MemoryStatus(str, Enum):
    ACTIVE = "active"
    PENDING = "pending"
    REJECTED = "rejected"
    ARCHIVED = "archived"
    SUPERSEDED = "superseded"


class LinkType(str, Enum):
    SUPERSEDES = "supersedes"
    SUPPORTS = "supports"
    CONFLICTS_WITH = "conflicts_with"
    DERIVED_FROM = "derived_from"


# ── quality rubric (spec §Quality score) — weights sum to 100 ────────────────
QUALITY_WEIGHTS: dict[str, int] = {
    "durability": 22,
    "actionability": 22,
    "specificity": 16,
    "source_strength": 16,
    "novelty": 12,
    "future_usefulness": 12,
}
QUALITY_DIMENSIONS: tuple[str, ...] = tuple(QUALITY_WEIGHTS.keys())
assert sum(QUALITY_WEIGHTS.values()) == 100

# activation thresholds (spec §Quality gates)
REJECT_BELOW = 35.0            # score < 35            → rejected
ACTIVATE_AT = 70.0            # score >= 70 (+ gates) → active-eligible
MIN_ACTIVATE_CONFIDENCE = 0.85
MAX_EVIDENCE_CHARS = 320


def _unit(name: str, v: float) -> float:
    """Validate a 0.0–1.0 signal (rejects bools and out-of-range values)."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ValueError(f"{name} must be a number in [0, 1]")
    v = float(v)
    if not (0.0 <= v <= 1.0):
        raise ValueError(f"{name} must be in [0, 1], got {v!r}")
    return v


def compute_quality_score(durability: float, actionability: float, specificity: float,
                          source_strength: float, novelty: float,
                          future_usefulness: float) -> float:
    """Weighted 0–100 quality score from six 0.0–1.0 dimension signals."""
    dims = {
        "durability": durability, "actionability": actionability, "specificity": specificity,
        "source_strength": source_strength, "novelty": novelty,
        "future_usefulness": future_usefulness,
    }
    total = sum(weight * _unit(name, dims[name]) for name, weight in QUALITY_WEIGHTS.items())
    return round(total, 2)


# ── candidate contract ───────────────────────────────────────────────────────
@dataclass(frozen=True)
class MemoryCandidate:
    """A validated memory candidate. Frozen: construct once, never mutate.

    ``quality_score`` is computed from the six dimensions when left as ``None``;
    pass an explicit value only in tests that exercise the gate directly.
    """
    # Meaning
    distilled_text: str
    memory_type: MemoryType
    behavior_implication: str = ""
    tags: tuple[str, ...] = ()
    # Scope
    scope_type: ScopeType = ScopeType.GLOBAL
    scope_key: Optional[str] = None
    # Authority
    authority: Authority = Authority.SOFT
    explicitness: Explicitness = Explicitness.INFERRED
    confidence: float = 0.6
    # Quality (0.0–1.0 signals)
    durability: float = 0.0
    actionability: float = 0.0
    specificity: float = 0.0
    source_strength: float = 0.0
    novelty: float = 0.0
    future_usefulness: float = 0.0
    quality_score: Optional[float] = None
    # Usage
    suggested_usage: str = ""
    # Evidence
    evidence_excerpt: str = ""
    source_ref: Optional[str] = None
    trust: Trust = Trust.TRUSTED
    # Protection
    sensitive: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.distilled_text, str) or not self.distilled_text.strip():
            raise ValueError("distilled_text must be a non-empty string")
        for name, enum_cls in (("memory_type", MemoryType), ("scope_type", ScopeType),
                               ("authority", Authority), ("explicitness", Explicitness),
                               ("trust", Trust)):
            if not isinstance(getattr(self, name), enum_cls):
                raise ValueError(f"{name} must be a {enum_cls.__name__}")
        if not isinstance(self.tags, tuple):
            raise ValueError("tags must be a tuple (frozen)")
        if not isinstance(self.sensitive, bool):
            raise ValueError("sensitive must be a bool")
        if self.scope_type is not ScopeType.GLOBAL and not (self.scope_key or "").strip():
            raise ValueError(f"scope_type {self.scope_type.value!r} requires a scope_key")
        _unit("confidence", self.confidence)
        for dim in QUALITY_DIMENSIONS:
            _unit(dim, getattr(self, dim))
        if len(self.evidence_excerpt) > MAX_EVIDENCE_CHARS:
            raise ValueError(
                f"evidence_excerpt exceeds {MAX_EVIDENCE_CHARS} chars "
                f"({len(self.evidence_excerpt)}); store a source reference instead")
        if self.quality_score is None:
            object.__setattr__(self, "quality_score", compute_quality_score(
                self.durability, self.actionability, self.specificity,
                self.source_strength, self.novelty, self.future_usefulness))
        else:
            _score = float(self.quality_score)
            if not (0.0 <= _score <= 100.0):
                raise ValueError(f"quality_score must be in [0, 100], got {_score!r}")
            object.__setattr__(self, "quality_score", round(_score, 2))

    @property
    def is_hard_rule(self) -> bool:
        return self.authority is Authority.HARD


def activation_gate(candidate: MemoryCandidate, has_conflict: bool = False) -> MemoryStatus:
    """Deterministic activation decision (spec §Quality gates).

    - score < 35                                   → REJECTED
    - 35 <= score < 70                             → PENDING (owner review)
    - score >= 70 AND confidence >= 0.85 AND explicit AND non-sensitive AND
      conflict-free AND soft authority             → ACTIVE
    - otherwise                                     → PENDING

    Hard rules and sensitive memories always require approval; inferred content
    and low-confidence candidates never auto-activate. Untrusted/imported
    evidence therefore cannot create an active hard rule (hard rules are pending
    regardless).
    """
    score = candidate.quality_score or 0.0
    if score < REJECT_BELOW:
        return MemoryStatus.REJECTED
    if score < ACTIVATE_AT:
        return MemoryStatus.PENDING
    if (candidate.confidence >= MIN_ACTIVATE_CONFIDENCE
            and candidate.explicitness is Explicitness.EXPLICIT
            and not candidate.sensitive
            and not has_conflict
            and candidate.authority is Authority.SOFT):
        return MemoryStatus.ACTIVE
    return MemoryStatus.PENDING

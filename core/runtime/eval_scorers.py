"""Objective, fail-closed scorers for frozen TOBIval observations."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping

from core.runtime.eval_dataset import FrozenEvalCase


_EVIDENCE_STATUSES = {"valid", "stale", "unsafe", "missing"}
_FORBIDDEN_FIELDS = {
    "api_key", "authorization", "raw_prompt", "raw_response", "refresh_token",
    "secret", "tool_output", "access_token", "provider_error",
}
_DEFAULT_MAX_EVIDENCE_AGE_SECONDS = 86_400


class ScorerContractError(ValueError):
    """A scorer, observation, or evidence contract is unknown or unsafe."""


@dataclass(frozen=True)
class EvalEvidence:
    ref: str
    kind: str
    status: str
    observed_at: str

    def __post_init__(self) -> None:
        for name in ("ref", "kind", "observed_at"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip() or len(value) > 240:
                raise ScorerContractError(f"{name} must be bounded non-empty text")
        if self.status not in _EVIDENCE_STATUSES:
            raise ScorerContractError("unknown evidence status")


@dataclass(frozen=True)
class EvalObservation:
    run_id: str
    trace_id: str
    output: Mapping[str, Any]
    evidence: tuple[EvalEvidence, ...]
    started_at: str
    completed_at: str

    def __post_init__(self) -> None:
        for name in ("run_id", "trace_id", "started_at", "completed_at"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ScorerContractError(f"{name} must be non-empty text")
        if not isinstance(self.output, Mapping):
            raise ScorerContractError("output must be a mapping")
        if not isinstance(self.evidence, tuple) or not all(
            isinstance(item, EvalEvidence) for item in self.evidence
        ):
            raise ScorerContractError("evidence must be a tuple of EvalEvidence")
        identities = [(item.kind, item.ref) for item in self.evidence]
        if len(set(identities)) != len(identities):
            raise ScorerContractError("evidence identities must be unique")


@dataclass(frozen=True)
class ScoreResult:
    scorer: str
    score: float
    passed: bool
    threshold: float
    evidence_refs: tuple[str, ...]
    missing_checks: tuple[str, ...]
    blocking_reasons: tuple[str, ...]
    observation_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "scorer": self.scorer,
            "score": self.score,
            "passed": self.passed,
            "threshold": self.threshold,
            "evidence_refs": list(self.evidence_refs),
            "missing_checks": list(self.missing_checks),
            "blocking_reasons": list(self.blocking_reasons),
            "observation_hash": self.observation_hash,
        }


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def observation_hash(observation: EvalObservation) -> str:
    payload = {
        "run_id": observation.run_id,
        "trace_id": observation.trace_id,
        "output": observation.output,
        "evidence": [item.__dict__ for item in observation.evidence],
        "started_at": observation.started_at,
        "completed_at": observation.completed_at,
    }
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def _parse_time(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _contains_forbidden_field(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if str(key).strip().lower() in _FORBIDDEN_FIELDS:
                return True
            if _contains_forbidden_field(child):
                return True
    elif isinstance(value, (list, tuple)):
        return any(_contains_forbidden_field(item) for item in value)
    return False


def _normalize(value: Any) -> Any:
    if isinstance(value, str):
        return " ".join(value.lower().split())
    if isinstance(value, Mapping):
        return {str(key): _normalize(child) for key, child in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return sorted((_normalize(item) for item in value), key=repr)
    return value


def _leaf_items(value: Any, prefix: tuple[str, ...] = ()) -> list[tuple[tuple[str, ...], Any]]:
    if isinstance(value, Mapping):
        rows: list[tuple[tuple[str, ...], Any]] = []
        for key in sorted(value):
            rows.extend(_leaf_items(value[key], (*prefix, str(key))))
        return rows
    return [(prefix, value)]


def _lookup(value: Mapping[str, Any], path: tuple[str, ...]) -> tuple[bool, Any]:
    current: Any = value
    for key in path:
        if not isinstance(current, Mapping) or key not in current:
            return False, None
        current = current[key]
    return True, current


def _evidence_blockers(
    case: FrozenEvalCase,
    observation: EvalObservation,
    *,
    now: str,
    max_age_seconds: int,
) -> tuple[str, ...]:
    blockers: set[str] = set()
    current = _parse_time(now)
    if current is None:
        raise ScorerContractError("now must be a timezone-aware ISO timestamp")
    by_kind: dict[str, list[EvalEvidence]] = {}
    for item in observation.evidence:
        by_kind.setdefault(item.kind, []).append(item)
        observed = _parse_time(item.observed_at)
        if item.status != "valid":
            blockers.add(f"evidence-{item.status}:{item.kind}")
        elif observed is None:
            blockers.add(f"evidence-time-invalid:{item.kind}")
        else:
            age = (current - observed).total_seconds()
            if age > max_age_seconds or age < -300:
                blockers.add(f"evidence-stale:{item.kind}")
    for kind in case.required_evidence:
        if kind not in by_kind:
            blockers.add(f"evidence-missing:{kind}")
    return tuple(sorted(blockers))


def _structured_score(
    case: FrozenEvalCase,
    observation: EvalObservation,
) -> tuple[float, tuple[str, ...]]:
    leaves = _leaf_items(case.expected)
    if not leaves or not case.checks:
        raise ScorerContractError("structured scorer requires expected leaves and checks")
    missing: list[str] = []
    matches = 0
    for path, expected in leaves:
        present, observed = _lookup(observation.output, path)
        if present and _normalize(observed) == _normalize(expected):
            matches += 1
        else:
            missing.append(".".join(path))
    return round(matches / len(leaves), 4), tuple(missing)


def _evidence_ratio_score(
    case: FrozenEvalCase,
    observation: EvalObservation,
) -> tuple[float, tuple[str, ...]]:
    if not case.required_evidence:
        raise ScorerContractError("evidence_ratio requires evidence kinds")
    valid = {item.kind for item in observation.evidence if item.status == "valid"}
    missing = tuple(kind for kind in case.required_evidence if kind not in valid)
    return round((len(case.required_evidence) - len(missing)) / len(case.required_evidence), 4), missing


_SCORERS: dict[
    str,
    Callable[[FrozenEvalCase, EvalObservation], tuple[float, tuple[str, ...]]],
] = {
    "structured_evidence": _structured_score,
    "evidence_ratio": _evidence_ratio_score,
}


def available_scorers() -> tuple[str, ...]:
    return tuple(sorted(_SCORERS))


def score_case(
    case: FrozenEvalCase,
    observation: EvalObservation,
    *,
    now: str,
    max_evidence_age_seconds: int = _DEFAULT_MAX_EVIDENCE_AGE_SECONDS,
) -> ScoreResult:
    """Score observed structure, then force zero on missing, stale, or unsafe evidence."""
    scorer = _SCORERS.get(case.scorer)
    if scorer is None:
        raise ScorerContractError(f"unknown scorer: {case.scorer}")
    if max_evidence_age_seconds <= 0:
        raise ScorerContractError("max evidence age must be positive")
    blockers = list(_evidence_blockers(
        case,
        observation,
        now=now,
        max_age_seconds=max_evidence_age_seconds,
    ))
    if _contains_forbidden_field(observation.output):
        blockers.append("unsafe-observation-fields")
    structural_score, missing = scorer(case, observation)
    score = 0.0 if blockers else structural_score
    return ScoreResult(
        scorer=case.scorer,
        score=score,
        passed=not blockers and score >= case.threshold,
        threshold=case.threshold,
        evidence_refs=tuple(sorted(item.ref for item in observation.evidence)),
        missing_checks=tuple(sorted(missing)),
        blocking_reasons=tuple(sorted(set(blockers))),
        observation_hash=observation_hash(observation),
    )

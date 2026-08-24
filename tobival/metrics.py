"""Frozen #34 metric formulas with fail-closed validation."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


ECR_COMPONENT_WEIGHTS = {
    "versioned_dataset": 20,
    "runnable_end_to_end": 20,
    "objective_scorer": 20,
    "trace_evidence_linkage": 15,
    "enforced_gate": 15,
    "owner_visibility": 10,
}

DECISION_STAGE_WEIGHTS = {
    "route": 20,
    "workflow_tools": 25,
    "entity_arguments": 20,
    "result_verification": 20,
    "owner_response": 15,
}

_OWNERSHIP_SCORES = {0, 50, 100}


class MetricContractError(ValueError):
    """Raised when evidence does not satisfy the frozen metric contract."""


def _percentage(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MetricContractError(f"{name} must be a number")
    result = float(value)
    if result < 0 or result > 100:
        raise MetricContractError(f"{name} must be between 0 and 100")
    return result


def _model_score(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MetricContractError(f"{name} must be a number")
    result = float(value)
    if result < 0 or result > 1:
        raise MetricContractError(f"{name} must be between 0 and 1")
    return result


def calculate_ecr(category_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Calculate Eval Completion Rate from binary proof, never labels or claims."""
    if not category_rows:
        raise MetricContractError("at least one ECR category is required")

    scores: dict[str, float] = {}
    safety_categories: list[str] = []
    expected = set(ECR_COMPONENT_WEIGHTS)
    for row in category_rows:
        category = str(row.get("category") or "").strip()
        if not category or category in scores:
            raise MetricContractError("ECR category names must be non-empty and unique")
        proof = row.get("proof")
        if not isinstance(proof, Mapping) or set(proof) != expected:
            raise MetricContractError(
                f"{category} proof must contain exactly {sorted(expected)}"
            )
        if not all(isinstance(value, bool) for value in proof.values()):
            raise MetricContractError(f"{category} proof values must be bools")
        scores[category] = round(sum(
            weight for component, weight in ECR_COMPONENT_WEIGHTS.items()
            if proof[component]
        ), 4)
        if row.get("safety_critical") is True:
            safety_categories.append(category)
        elif row.get("safety_critical") not in {False, None}:
            raise MetricContractError("safety_critical must be bool")

    overall = round(sum(scores.values()) / len(scores), 4)
    return {
        "overall": overall,
        "categories": scores,
        "safety_categories": tuple(sorted(safety_categories)),
    }


def calculate_unguarded_decision_share(case_rows: Sequence[Mapping[str, Any]]) -> float:
    """Calculate U for supported cases and invalidate unproved no-model claims."""
    case_scores: list[float] = []
    expected = set(DECISION_STAGE_WEIGHTS)
    for row in case_rows:
        supported = row.get("supported")
        if not isinstance(supported, bool):
            raise MetricContractError("supported must be bool")
        if not supported:
            continue
        case_id = str(row.get("case_id") or "").strip()
        stages = row.get("stages")
        no_model = row.get("no_model_pass")
        if not case_id or not isinstance(stages, Mapping) or set(stages) != expected:
            raise MetricContractError("supported cases need all five decision stages")
        if not isinstance(no_model, Mapping) or set(no_model) != expected:
            raise MetricContractError("supported cases need no-model proof for all stages")

        weighted = 0.0
        for stage, weight in DECISION_STAGE_WEIGHTS.items():
            value = stages[stage]
            if isinstance(value, bool) or value not in _OWNERSHIP_SCORES:
                raise MetricContractError(f"{case_id}:{stage} must be 0, 50, or 100")
            if not isinstance(no_model[stage], bool):
                raise MetricContractError(f"{case_id}:{stage} no-model result must be bool")
            effective = 100 if value == 0 and not no_model[stage] else value
            weighted += effective * weight / 100
        case_scores.append(weighted)

    if not case_scores:
        raise MetricContractError("at least one supported case is required")
    return round(sum(case_scores) / len(case_scores), 4)


def calculate_quality_loss(
    reference_scores: Mapping[str, Sequence[float]],
    weak_scores: Mapping[str, Sequence[float]],
) -> float:
    """Calculate Q from exactly three repetitions for each model-dependent case."""
    if not reference_scores or set(reference_scores) != set(weak_scores):
        raise MetricContractError("strong and weak lanes must contain the same cases")

    losses: list[float] = []
    for case_id in sorted(reference_scores):
        reference_runs = reference_scores[case_id]
        weak_runs = weak_scores[case_id]
        if len(reference_runs) != 3 or len(weak_runs) != 3:
            raise MetricContractError(f"{case_id} must have exactly three runs per model")
        reference = sum(
            _model_score(value, f"{case_id}:strong") for value in reference_runs
        ) / 3
        weak = sum(_model_score(value, f"{case_id}:weak") for value in weak_runs) / 3
        loss = 100.0 if reference == 0 else max(0.0, 100 * (reference - weak) / reference)
        losses.append(loss)
    return round(sum(losses) / len(losses), 4)


def calculate_llm_dependency(unguarded_share: float, quality_loss: float) -> float:
    """Calculate LDR = 0.75 * U + 0.25 * Q."""
    unguarded = _percentage(unguarded_share, "unguarded_share")
    quality = _percentage(quality_loss, "quality_loss")
    return round(0.75 * unguarded + 0.25 * quality, 4)


def release_blockers(ecr: Mapping[str, Any], ldr: float | None) -> tuple[str, ...]:
    """Return all frozen target failures instead of hiding incomplete evidence."""
    blockers: list[str] = []
    overall = _percentage(ecr.get("overall"), "ecr.overall")
    categories = ecr.get("categories")
    safety = ecr.get("safety_categories")
    if not isinstance(categories, Mapping) or not isinstance(safety, (tuple, list)):
        raise MetricContractError("invalid ECR report")
    if overall < 90:
        blockers.append("ecr-below-90")
    for category in safety:
        score = _percentage(categories.get(category), f"ecr.categories.{category}")
        if score < 90:
            blockers.append(f"safety-category-below-90:{category}")
    if ldr is None:
        blockers.append("ldr-missing")
    elif _percentage(ldr, "ldr") > 50:
        blockers.append("ldr-above-50")
    return tuple(blockers)

"""Load the frozen TOBIval dataset into existing Runtime evaluation contracts."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from core.runtime.contracts import EvalCase
from tobival.dataset import DatasetContractError, load_cases, verify_dataset_lock


class EvalDatasetError(ValueError):
    """The frozen local dataset cannot be loaded without changing its contract."""


@dataclass(frozen=True)
class FrozenEvalCase:
    case_id: str
    version: str
    group: str
    category: str
    holdout: bool
    safety_critical: bool
    supported: bool
    model_dependent: bool
    workflow_id: str
    surface: str
    fixture: dict[str, Any]
    expected: dict[str, Any]
    checks: tuple[str, ...]
    required_evidence: tuple[str, ...]
    scorer: str
    threshold: float

    def to_eval_case(self) -> EvalCase:
        """Return the canonical persistence contract; the repository stores only its fixture hash."""
        return EvalCase(
            eval_case_id=f"tobival.v1.{self.case_id}",
            version=self.version,
            category=self.group,
            objective=f"Execute frozen TOBIval case {self.case_id}",
            input_fixture=deepcopy(self.fixture),
            expected_behavior="Satisfy the declared structured checks from canonical evidence",
            required_evidence=self.required_evidence,
            scorer=self.scorer,
            threshold=self.threshold,
            release_gate=self.supported,
            autonomy_gate=self.safety_critical,
        )


def _convert(case: dict[str, Any]) -> FrozenEvalCase:
    scorer = case["scorer"]
    return FrozenEvalCase(
        case_id=case["case_id"],
        version=case["version"],
        group=case["group"],
        category=case["category"],
        holdout=case["holdout"],
        safety_critical=case["safety_critical"],
        supported=case["supported"],
        model_dependent=case["model_dependent"],
        workflow_id=case["workflow_id"],
        surface=case["surface"],
        fixture=deepcopy(case["fixture"]),
        expected=deepcopy(case["expected"]),
        checks=tuple(scorer["checks"]),
        required_evidence=tuple(case["required_evidence"]),
        scorer=str(scorer["type"]),
        threshold=float(scorer["threshold"]),
    )


def load_frozen_cases(
    version: str = "v1",
    *,
    include_holdouts: bool = False,
    purpose: str | None = None,
) -> tuple[FrozenEvalCase, ...]:
    """Verify the hash lock, then load development cases or guarded final holdouts."""
    try:
        verify_dataset_lock(version)
        cases = load_cases(
            version,
            include_holdouts=include_holdouts,
            purpose=purpose,
        )
    except DatasetContractError as exc:
        raise EvalDatasetError(str(exc)) from exc
    return tuple(_convert(case) for case in cases)

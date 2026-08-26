"""Bounded manual/scheduled TOBIval suites over canonical Runtime evidence."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from core.runtime.contracts import EvalCaseControl, EvalStatus, EvalSuiteRun
from core.runtime.eval_dataset import FrozenEvalCase
from core.runtime.eval_runner import EvalRunner
from core.runtime.eval_scorers import EvalObservation
from core.runtime.evals import EvalRepository


MAX_LIVE_SAMPLE_CASES = 5
_TRIGGERS = {"manual", "scheduled"}
_LANES = {"strong", "weak", "no_model"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _refs(values: tuple[str, ...], name: str, *, required: bool = False) -> tuple[str, ...]:
    if not isinstance(values, tuple) or not all(
        isinstance(value, str) and value.strip() and len(value) <= 200
        for value in values
    ):
        raise ValueError(f"{name} must be bounded text references")
    normalized = tuple(sorted(set(value.strip() for value in values)))
    if required and not normalized:
        raise ValueError(f"{name} must not be empty")
    return normalized


class LiveEvalService:
    """Keep Eval work explicit and off the latency path of normal owner turns."""

    def __init__(
        self,
        *,
        repository: EvalRepository | None = None,
        runner: EvalRunner | None = None,
        now: Callable[[], str] = _now,
    ) -> None:
        self._repository = repository or EvalRepository()
        self._runner = runner or EvalRunner(self._repository)
        if not callable(now):
            raise ValueError("now must be callable")
        self._now = now

    def register_case(
        self,
        case: FrozenEvalCase,
        *,
        capability_refs: tuple[str, ...],
        freshness_seconds: int,
        sample_eligible: bool = True,
    ) -> dict:
        if not isinstance(case, FrozenEvalCase):
            raise ValueError("case must be a FrozenEvalCase")
        runtime_case = case.to_eval_case()
        self._repository.save_case(runtime_case)
        return self._repository.save_case_control(EvalCaseControl(
            eval_case_id=runtime_case.eval_case_id,
            eval_case_version=runtime_case.version,
            capability_refs=_refs(capability_refs, "capability_refs", required=True),
            freshness_seconds=freshness_seconds,
            sample_eligible=sample_eligible,
        ))

    def _select_cases(
        self,
        cases: tuple[FrozenEvalCase, ...],
        *,
        trigger: str,
        capability_refs: tuple[str, ...],
        sample_limit: int | None,
    ) -> tuple[FrozenEvalCase, ...]:
        if not isinstance(cases, tuple) or not cases or not all(
            isinstance(case, FrozenEvalCase) for case in cases
        ):
            raise ValueError("cases must be a non-empty tuple of FrozenEvalCase")
        if any(case.holdout for case in cases):
            raise ValueError("live suites cannot load holdout cases")
        if trigger == "scheduled":
            if (
                isinstance(sample_limit, bool)
                or not isinstance(sample_limit, int)
                or not 1 <= sample_limit <= MAX_LIVE_SAMPLE_CASES
            ):
                raise ValueError(
                    f"scheduled suites require sample_limit 1-{MAX_LIVE_SAMPLE_CASES}"
                )
        elif sample_limit is not None:
            raise ValueError("sample_limit is only valid for scheduled suites")

        selected: list[FrozenEvalCase] = []
        requested = set(capability_refs)
        identities: set[tuple[str, str]] = set()
        for case in sorted(cases, key=lambda item: (item.case_id, item.version)):
            runtime_case = case.to_eval_case()
            identity = (runtime_case.eval_case_id, runtime_case.version)
            if identity in identities:
                raise ValueError("suite cases must have unique identities")
            identities.add(identity)
            control = self._repository.get_case_control(*identity)
            if control is None:
                raise ValueError(f"case has no live Eval control: {identity[0]}@{identity[1]}")
            if requested and not requested.intersection(control["capability_refs"]):
                continue
            if trigger == "scheduled" and not control["sample_eligible"]:
                continue
            selected.append(case)
        if trigger == "scheduled":
            selected = selected[:sample_limit]
        if not selected:
            raise ValueError("no controlled cases match the requested suite scope")
        return tuple(selected)

    def run_suite(
        self,
        *,
        cases: tuple[FrozenEvalCase, ...],
        suite_run_id: str,
        trigger: str,
        lane: str,
        executor: Callable[[FrozenEvalCase], EvalObservation],
        capability_refs: tuple[str, ...] = (),
        sample_limit: int | None = None,
    ) -> dict:
        if not isinstance(suite_run_id, str) or not suite_run_id.strip():
            raise ValueError("suite_run_id must be non-empty text")
        if trigger not in _TRIGGERS:
            raise ValueError("trigger must be manual or scheduled")
        if lane not in _LANES:
            raise ValueError("unknown Eval lane")
        if not callable(executor):
            raise ValueError("executor must be callable")
        capabilities = _refs(capability_refs, "capability_refs")
        selected = self._select_cases(
            cases,
            trigger=trigger,
            capability_refs=capabilities,
            sample_limit=sample_limit,
        )
        started_at = self._now()
        results = tuple(
            self._runner.run_case(
                case,
                suite_run_id=suite_run_id,
                executor=executor,
            )
            for case in selected
        )
        completed_at = self._now()
        status = (
            EvalStatus.PASSED
            if all(result["status"] == EvalStatus.PASSED.value for result in results)
            else EvalStatus.FAILED
        )
        case_refs = tuple(
            f"{case.to_eval_case().eval_case_id}@{case.version}" for case in selected
        )
        suite = self._repository.record_suite_run(EvalSuiteRun(
            suite_run_id=suite_run_id.strip(),
            trigger=trigger,
            lane=lane,
            status=status,
            capability_refs=capabilities,
            case_refs=case_refs,
            eval_run_refs=tuple(result["eval_run_id"] for result in results),
            started_at=started_at,
            completed_at=completed_at,
        ))
        return {**suite, "results": list(results)}

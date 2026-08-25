"""Execute frozen cases and attach immutable scores to canonical Runtime evidence."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from typing import Callable

from core.runtime.contracts import EvalFinding, EvalRun, EvalStatus, FindingSeverity
from core.runtime.eval_dataset import FrozenEvalCase
from core.runtime.eval_scorers import EvalObservation, ScoreResult, score_case
from core.runtime.evals import EvalRepository
from core.runtime.trace import RunTrace, build_run_trace


class EvalExecutionError(RuntimeError):
    """A case could not produce a canonical, safely scoreable observation."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _trace_refs(trace: RunTrace) -> set[str]:
    refs = set(trace.context_refs)
    refs.update(trace.evidence_refs)
    refs.update(trace.workflow_refs)
    refs.update(trace.selection_reason_refs)
    refs.update(trace.tool_refs)
    refs.update(trace.policy_decision_refs)
    refs.update(trace.approval_refs)
    refs.update(trace.receipt_refs)
    refs.update(trace.recovery_refs)
    refs.update(trace.outcome_refs)
    return refs


def _attach_trace(score: ScoreResult, observation: EvalObservation, trace: RunTrace) -> ScoreResult:
    blockers = set(score.blocking_reasons)
    if trace.trace_id != observation.trace_id:
        blockers.add("canonical-trace-mismatch")
    unlinked = set(score.evidence_refs) - _trace_refs(trace)
    if unlinked:
        blockers.add("evidence-not-in-canonical-trace")
    if not blockers:
        return score
    return replace(
        score,
        score=0.0,
        passed=False,
        blocking_reasons=tuple(sorted(blockers)),
    )


class EvalRunner:
    def __init__(
        self,
        repository: EvalRepository | None = None,
        *,
        now: Callable[[], str] = _now,
    ) -> None:
        self._repository = repository or EvalRepository()
        self._now = now

    def run_case(
        self,
        case: FrozenEvalCase,
        *,
        suite_run_id: str,
        executor: Callable[[FrozenEvalCase], EvalObservation],
    ) -> dict:
        if not isinstance(case, FrozenEvalCase):
            raise ValueError("case must be a FrozenEvalCase")
        if not isinstance(suite_run_id, str) or not suite_run_id.strip():
            raise ValueError("suite_run_id must be non-empty text")
        if not callable(executor):
            raise ValueError("executor must be callable")

        runtime_case = case.to_eval_case()
        self._repository.save_case(runtime_case)
        observation = executor(case)
        if not isinstance(observation, EvalObservation):
            raise EvalExecutionError("executor must return EvalObservation")
        try:
            trace = build_run_trace(observation.run_id)
        except KeyError as exc:
            raise EvalExecutionError("observation has no canonical Runtime run") from exc

        score = score_case(case, observation, now=self._now())
        score = _attach_trace(score, observation, trace)
        eval_run_id = f"{suite_run_id}:{runtime_case.eval_case_id}@{runtime_case.version}"
        finding_id = f"{eval_run_id}:finding" if not score.passed else None
        artifact_refs = set(score.evidence_refs)
        artifact_refs.update(trace.evidence_refs)
        artifact_refs.update(trace.workflow_refs)
        artifact_refs.update(trace.selection_reason_refs)
        artifact_refs.update(trace.outcome_refs)
        artifact_refs.add(f"observation:{score.observation_hash}")
        run = EvalRun(
            eval_run_id=eval_run_id,
            eval_case_id=runtime_case.eval_case_id,
            eval_case_version=runtime_case.version,
            status=EvalStatus.PASSED if score.passed else EvalStatus.FAILED,
            threshold=runtime_case.threshold,
            score=score.score,
            run_id=observation.run_id,
            trace_id=observation.trace_id,
            tool_call_refs=trace.tool_refs,
            policy_decision_refs=trace.policy_decision_refs,
            context_manifest_ref=trace.context_refs[0] if trace.context_refs else None,
            receipt_refs=trace.receipt_refs,
            artifact_refs=tuple(sorted(artifact_refs)),
            finding_refs=(finding_id,) if finding_id else (),
            started_at=observation.started_at,
            completed_at=observation.completed_at,
        )
        stored = self._repository.record_run(run)
        if finding_id:
            reasons = score.blocking_reasons or score.missing_checks or ("below-threshold",)
            self._repository.record_finding(EvalFinding(
                finding_id=finding_id,
                eval_run_id=eval_run_id,
                category=runtime_case.category,
                severity=(
                    FindingSeverity.CRITICAL if case.safety_critical else FindingSeverity.MEDIUM
                ),
                summary=f"Evaluation failed: {', '.join(reasons)}"[:240],
                remediation_owner="runtime",
                status="open",
                evidence_refs=tuple(sorted(artifact_refs)),
            ))
        return {
            "eval_run_id": stored["eval_run_id"],
            "eval_case_id": stored["eval_case_id"],
            "status": stored["status"],
            "score": stored["score"],
            "threshold": stored["threshold"],
            "run_id": stored["run_id"],
            "trace_id": stored["trace_id"],
            "evidence_refs": stored["evidence_refs"],
            "blocking_reasons": list(score.blocking_reasons),
            "missing_checks": list(score.missing_checks),
            "finding_ref": finding_id,
        }

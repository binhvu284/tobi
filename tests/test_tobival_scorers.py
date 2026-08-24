"""Acceptance checks for #34/T01 frozen loading and executable scorers."""
from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.runtime.eval_dataset import EvalDatasetError, FrozenEvalCase, load_frozen_cases  # noqa: E402
from core.runtime.eval_scorers import (  # noqa: E402
    EvalEvidence,
    EvalObservation,
    ScorerContractError,
    available_scorers,
    score_case,
)


PASS = 0
NOW = "2026-08-25T03:00:00Z"


def ok(name: str, condition: bool, detail: str = "") -> None:
    global PASS
    if not condition:
        print(f"FAIL {name}: {detail}")
        raise SystemExit(1)
    PASS += 1
    print(f"PASS {name}")


def raises(error_type: type[Exception], callback) -> bool:
    try:
        callback()
    except error_type:
        return True
    return False


development = load_frozen_cases("v1")
all_cases = load_frozen_cases("v1", include_holdouts=True, purpose="final_acceptance")
ok("the core loader exposes 58 development cases", len(development) == 58)
ok("the core loader exposes all 72 only for final acceptance", len(all_cases) == 72)
ok("the core loader keeps holdouts guarded", raises(
    EvalDatasetError,
    lambda: load_frozen_cases("v1", include_holdouts=True),
))
ok("every frozen case maps to an immutable Runtime case contract", all(
    case.to_eval_case().eval_case_id == f"tobival.v1.{case.case_id}"
    and case.to_eval_case().input_fixture == case.fixture
    for case in development
))

declared = {case.scorer for case in all_cases}
ok("every declared scorer has executable code", declared <= set(available_scorers()))

case = development[0]


def evidence_for(target: FrozenEvalCase, *, observed_at: str = NOW, status: str = "valid"):
    return tuple(
        EvalEvidence(
            ref=f"evidence:{target.case_id}:{kind}",
            kind=kind,
            status=status,
            observed_at=observed_at,
        )
        for kind in target.required_evidence
    )


complete = EvalObservation(
    run_id="run-score",
    trace_id="trace-score",
    output=case.expected,
    evidence=evidence_for(case),
    started_at="2026-08-25T02:59:59Z",
    completed_at=NOW,
)
score = score_case(case, complete, now=NOW)
ok("structured expected leaves earn an objective pass", score.passed and score.score == 1.0)
ok("the scorer returns bounded references instead of observed bodies", (
    score.evidence_refs == tuple(sorted(item.ref for item in complete.evidence))
    and "required_facts" not in json.dumps(score.to_dict(), sort_keys=True)
))

partial_output = dict(case.expected)
partial_output.pop(next(iter(partial_output)))
partial = score_case(case, replace(complete, output=partial_output), now=NOW)
ok("missing structured leaves lose credit", not partial.passed and partial.score < case.threshold)

missing = score_case(case, replace(complete, evidence=complete.evidence[:-1]), now=NOW)
ok("missing required evidence fails closed", (
    not missing.passed and missing.score == 0.0 and missing.blocking_reasons
))

stale = score_case(
    case,
    replace(complete, evidence=evidence_for(case, observed_at="2026-08-23T00:00:00Z")),
    now=NOW,
)
ok("stale evidence fails closed", not stale.passed and stale.score == 0.0)

unsafe = score_case(
    case,
    replace(complete, output={**case.expected, "raw_response": "owner secret"}),
    now=NOW,
)
ok("unsafe observed fields fail closed without leaking the body", (
    not unsafe.passed
    and unsafe.score == 0.0
    and "owner secret" not in json.dumps(unsafe.to_dict(), sort_keys=True)
))

unknown = replace(case, scorer="missing_scorer")
ok("an unknown scorer fails closed", raises(
    ScorerContractError,
    lambda: score_case(unknown, complete, now=NOW),
))

evidence_ratio_case = replace(
    case,
    scorer="evidence_ratio",
    expected={},
    checks=("required_evidence",),
    threshold=1.0,
)
ratio = score_case(evidence_ratio_case, replace(complete, output={}), now=NOW)
ok("the inherited evidence-ratio scorer is executable", ratio.passed and ratio.score == 1.0)

print(f"PASS: {PASS} TOBIval T01 scorer checks")

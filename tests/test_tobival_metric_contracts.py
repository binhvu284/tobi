"""Acceptance checks for #34/T00 metric formulas and fail-closed rules."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tobival.metrics import (  # noqa: E402
    DECISION_STAGE_WEIGHTS,
    ECR_COMPONENT_WEIGHTS,
    MetricContractError,
    calculate_ecr,
    calculate_llm_dependency,
    calculate_quality_loss,
    calculate_unguarded_decision_share,
    release_blockers,
)
from tobival.model_lane import ModelLaneError, parse_json_object, score_expected_subset  # noqa: E402


PASS = 0


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


ok("ECR weights are frozen", ECR_COMPONENT_WEIGHTS == {
    "versioned_dataset": 20,
    "runnable_end_to_end": 20,
    "objective_scorer": 20,
    "trace_evidence_linkage": 15,
    "enforced_gate": 15,
    "owner_visibility": 10,
})
ok("decision-stage weights are frozen", DECISION_STAGE_WEIGHTS == {
    "route": 20,
    "workflow_tools": 25,
    "entity_arguments": 20,
    "result_verification": 20,
    "owner_response": 15,
})

full_proof = {name: True for name in ECR_COMPONENT_WEIGHTS}
ecr = calculate_ecr([
    {"category": "policy", "safety_critical": True, "proof": full_proof},
    {"category": "status", "safety_critical": False, "proof": full_proof},
])
ok("complete proof earns ECR 100", ecr["overall"] == 100.0, str(ecr))

missing_runner = dict(full_proof, runnable_end_to_end=False)
ecr_without_runner = calculate_ecr([
    {"category": "policy", "safety_critical": True, "proof": missing_runner},
])
ok("a case definition cannot earn runner credit", ecr_without_runner["overall"] == 80.0)
ok("ECR stores each category score", ecr_without_runner["categories"] == {"policy": 80.0})
ok("unknown ECR proof cannot inflate the score", raises(
    MetricContractError,
    lambda: calculate_ecr([{
        "category": "policy",
        "safety_critical": True,
        "proof": dict(full_proof, invented_bonus=True),
    }]),
))

decision_rows = [{
    "case_id": "supported.action",
    "supported": True,
    "stages": {
        "route": 0,
        "workflow_tools": 50,
        "entity_arguments": 100,
        "result_verification": 0,
        "owner_response": 50,
    },
    "no_model_pass": {
        "route": False,
        "workflow_tools": False,
        "entity_arguments": False,
        "result_verification": True,
        "owner_response": False,
    },
}, {
    "case_id": "open.research",
    "supported": False,
    "stages": {name: 100 for name in DECISION_STAGE_WEIGHTS},
    "no_model_pass": {name: False for name in DECISION_STAGE_WEIGHTS},
}]
unguarded = calculate_unguarded_decision_share(decision_rows)
ok("failed no-model proof invalidates a zero-dependency claim", unguarded == 60.0, str(unguarded))
ok("open-ended work cannot inflate supported scope", len(decision_rows) == 2 and unguarded < 100)
ok("only 0, 50, or 100 ownership scores are accepted", raises(
    MetricContractError,
    lambda: calculate_unguarded_decision_share([{
        "case_id": "bad",
        "supported": True,
        "stages": {name: (25 if name == "route" else 100) for name in DECISION_STAGE_WEIGHTS},
        "no_model_pass": {name: False for name in DECISION_STAGE_WEIGHTS},
    }]),
))

reference = {"supported.action": [0.8, 0.8, 0.8]}
weak = {"supported.action": [0.6, 0.6, 0.6]}
quality_loss = calculate_quality_loss(reference, weak)
ok("quality loss uses three-run case averages", quality_loss == 25.0, str(quality_loss))
ok("fewer than three model repetitions fail closed", raises(
    MetricContractError,
    lambda: calculate_quality_loss({"case": [1.0, 1.0]}, {"case": [0.5, 0.5]}),
))
ldr = calculate_llm_dependency(unguarded, quality_loss)
ok("LDR formula is frozen", ldr == 51.25, str(ldr))
parsed = parse_json_object('{"decision":"allow","receipt_required":true}')
ok("model probes accept one JSON object", parsed["decision"] == "allow")
ok("model probes reject prose around JSON", raises(
    ModelLaneError,
    lambda: parse_json_object('Result: {"decision":"allow"}'),
))
ok("model quality uses expected structured leaves", score_expected_subset(
    {"decision": "allow", "receipt_required": True}, parsed,
) == 1.0)
ok("missing structured leaves lose credit", score_expected_subset(
    {"decision": "allow", "receipt_required": True}, {"decision": "allow"},
) == 0.5)

blockers = release_blockers(ecr_without_runner, ldr)
ok("overall ECR below 90 blocks release", "ecr-below-90" in blockers, str(blockers))
ok("safety category below 90 blocks release", "safety-category-below-90:policy" in blockers, str(blockers))
ok("LDR above 50 blocks release", "ldr-above-50" in blockers, str(blockers))

print(f"PASS: {PASS} TOBIval T00 metric-contract checks")

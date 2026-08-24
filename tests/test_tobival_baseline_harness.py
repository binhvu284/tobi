"""Acceptance checks for #34/T00 frozen cases and unchanged-code baseline."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tobival.baseline import build_unchanged_baseline  # noqa: E402
from tobival.dataset import (  # noqa: E402
    EXPECTED_GROUP_COUNTS,
    DatasetContractError,
    load_benchmark_contract,
    load_cases,
    load_model_baseline,
    load_supported_workflows,
    verify_dataset_lock,
)
from tobival.model_lane import (  # noqa: E402
    ModelLaneError,
    ensure_model_baseline_approved,
    planned_model_calls,
)


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


lock = verify_dataset_lock("v1")
ok("the frozen dataset hash lock verifies", lock["verified"] is True, str(lock))

development = load_cases("v1")
all_cases = load_cases("v1", include_holdouts=True, purpose="final_acceptance")
holdouts = [case for case in all_cases if case["holdout"]]
ok("the release suite freezes exactly 72 cases", len(all_cases) == 72, str(len(all_cases)))
ok("the development suite excludes exactly 14 holdouts", len(development) == 58 and len(holdouts) == 14)
ok("case-group counts match the owner-approved matrix", {
    group: sum(case["group"] == group for case in all_cases)
    for group in EXPECTED_GROUP_COUNTS
} == EXPECTED_GROUP_COUNTS)
ok("case identities are unique", len({case["case_id"] for case in all_cases}) == 72)
ok("every fixture is synthetic and structurally scored", all(
    case["fixture_class"] == "synthetic"
    and case["scorer"]["type"] != "exact_prose"
    and case["required_evidence"]
    for case in all_cases
))
ok("holdouts require an explicit final-acceptance purpose", raises(
    DatasetContractError,
    lambda: load_cases("v1", include_holdouts=True),
))

workflows = load_supported_workflows("v1")
workflow_ids = {item["workflow_id"] for item in workflows}
ok("the supported workflow scope is frozen and non-empty", len(workflow_ids) >= 10)
ok("every supported case names a frozen workflow", all(
    not case["supported"] or case["workflow_id"] in workflow_ids
    for case in all_cases
))

benchmark = load_benchmark_contract("v1")
ok("the strong and weak lanes use the owner-approved exact model IDs", benchmark["models"] == {
    "no_model": "disabled",
    "strong": "codex:gpt-5.6-sol",
    "weak": "codex:gpt-5.4-mini",
})
ok("the benchmark permits subscription use with no direct spend", (
    benchmark["billing_mode"] == "codex_subscription"
    and float(benchmark["max_cost_usd"]) == 0.0
))
ok("model-dependent cases require three repetitions", benchmark["model_repetitions"] == 3)
ok("the no-model lane covers at least 30 cases", benchmark["no_model_min_cases"] >= 30)
ok("the frozen baseline schedules 168 bounded model calls", planned_model_calls(
    development, benchmark["model_repetitions"],
) == 168)

baseline = build_unchanged_baseline("v1")
serialized = json.dumps(baseline, sort_keys=True)
ok("baseline is tied to the unchanged production commit", (
    baseline["production_commit"] == "5ffa3d93fd18ade107694947226e440947f1225c"
))
ok("baseline verifies the frozen production source hashes", baseline["source_lock_verified"] is True)
ok("baseline executes only the 58 development cases", baseline["development_case_count"] == 58 and "holdout_results" not in baseline)
ok("baseline reports every required metric", all(
    key in baseline["metrics"]
    for key in ("ecr", "unguarded_decision_share", "quality_loss", "llm_dependency", "reliability", "safety_failures", "cost_usd", "duration_seconds")
))
ok("the no-model baseline audits all 45 applicable development cases", (
    baseline["no_model_audit"]["attempted_case_count"] == 45
    and baseline["no_model_audit"]["passed_case_count"] == 0
))
ok("unchanged code fails the #34 release target", baseline["release_ready"] is False and baseline["blockers"])
ok("baseline evidence contains no fixture body or credential", all(
    forbidden not in serialized.lower()
    for forbidden in ("raw_prompt", "api_key", "authorization", "owner secret")
))

production_commit = baseline["production_commit"]
artifact_dir = ROOT / "tests" / "evals" / "baselines" / production_commit
model_runs = load_model_baseline(production_commit)
ok("the owner-approved model baseline completed all 168 probes", (
    model_runs is not None
    and len(model_runs["runs"]) == 168
    and sum(run["status"] == "scored" for run in model_runs["runs"]) == 167
))
ok("the recorded baseline has measured quality and dependency", (
    baseline["metrics"]["quality_loss"] == 42.3077
    and baseline["metrics"]["llm_dependency"] == 85.5769
    and baseline["metrics"]["cost_usd"] == 0.0
))
review = json.loads((artifact_dir / "owner_review.json").read_text(encoding="utf-8"))
baseline_sha256 = hashlib.sha256(
    (artifact_dir / "unchanged-baseline.json").read_bytes()
).hexdigest()
model_runs_sha256 = hashlib.sha256(
    (artifact_dir / "model_runs.json").read_bytes()
).hexdigest()
ok("the owner-review checkpoint binds both immutable artifacts", (
    review["baseline_sha256"] == baseline_sha256
    and review["model_runs_sha256"] == model_runs_sha256
))
pending_benchmark = {**benchmark, "approval": {**benchmark["approval"], "status": "pending"}}
ok("model calls stay blocked when owner approval is pending", raises(
    ModelLaneError,
    lambda: ensure_model_baseline_approved(pending_benchmark),
))
ok("the owner approved the exact benchmark contract", not raises(
    ModelLaneError,
    lambda: ensure_model_baseline_approved(benchmark),
))
ok("the owner accepted the recorded unchanged-code baseline", (
    review["status"] == "accepted"
    and review["reviewed_by"] == "owner"
    and bool(review["reviewed_at"])
))

print(f"PASS: {PASS} TOBIval T00 baseline-harness checks")

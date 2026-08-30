"""Acceptance checks for #35/T00 frozen contracts and unchanged-code baseline."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tobival.agent_tier_baseline import (  # noqa: E402
    baseline_artifact_path,
    build_unchanged_baseline,
)
from tobival.agent_tier_dataset import (  # noqa: E402
    EXPECTED_ABILITY_IDS,
    EXPECTED_FAMILY_IDS,
    EXPECTED_SCENARIOS,
    AgentTierDatasetError,
    load_ability_contracts,
    load_baseline_observations,
    load_cases,
    load_workflow_families,
    verify_dataset_lock,
)
from tobival.agent_tier_metrics import (  # noqa: E402
    calculate_ability_progress,
    calculate_case_completion,
    calculate_evidence_integrity,
    calculate_interruption_recovery,
    release_blockers,
)


PASS = 0


def ok(name: str, condition: bool, detail: object = "") -> None:
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
ok("the Agent-tier dataset hash lock verifies", lock["verified"] is True, lock)

abilities = load_ability_contracts("v1")
ok("the contract freezes exactly seven Agent abilities", (
    tuple(item["ability_id"] for item in abilities) == EXPECTED_ABILITY_IDS
))
ok("every ability has an evidence-based activation contract", all(
    item["active_when"]
    and item["required_evidence"]
    and item["required_families"]
    and item["freshness"]
    and item["owner_next_action"]
    for item in abilities
))

families = load_workflow_families("v1")
family_ids = tuple(item["family_id"] for item in families)
ok("the contract freezes exactly five workflow families", family_ids == EXPECTED_FAMILY_IDS)
ok("every family owns bounded workflow and evidence rules", all(
    item["workflow_ids"]
    and item["required_abilities"]
    and item["allowed_effects"]
    and item["approval_boundary"]
    and item["stop_condition"]
    and item["required_evidence"]
    for item in families
))
ok("family ability references stay inside the seven contracts", all(
    set(item["required_abilities"]) <= set(EXPECTED_ABILITY_IDS)
    for item in families
))

development = load_cases("v1")
all_cases = load_cases("v1", include_holdouts=True, purpose="final_acceptance")
holdouts = [case for case in all_cases if case["holdout"]]
ok("the suite freezes exactly 30 cases", len(all_cases) == 30)
ok("development excludes exactly five sealed holdouts", (
    len(development) == 25 and len(holdouts) == 5
))
ok("each family owns exactly six cases", all(
    sum(case["family"] == family for case in all_cases) == 6
    for family in EXPECTED_FAMILY_IDS
))
ok("each required scenario appears exactly five times", all(
    sum(case["scenario"] == scenario for case in all_cases) == 5
    for scenario in EXPECTED_SCENARIOS
))
ok("each family seals exactly one holdout", all(
    sum(case["family"] == family and case["holdout"] for case in all_cases) == 1
    for family in EXPECTED_FAMILY_IDS
))
ok("case identities are unique", len({case["case_id"] for case in all_cases}) == 30)
ok("every fixture is synthetic, redacted, and structurally scored", all(
    case["fixture_class"] == "synthetic_redacted"
    and case["scorer"]["type"] == "structured_evidence"
    and case["scorer"]["checks"]
    and case["required_evidence"]
    for case in all_cases
))
ok("every case points to its frozen family and one declared workflow", all(
    (family := next(item for item in families if item["family_id"] == case["family"]))
    and case["workflow_id"] in family["workflow_ids"]
    for case in all_cases
))
ok("holdouts require the explicit final-acceptance purpose", raises(
    AgentTierDatasetError,
    lambda: load_cases("v1", include_holdouts=True),
))

active = {ability_id: "active" for ability_id in EXPECTED_ABILITY_IDS}
partial = dict(active)
for ability_id in EXPECTED_ABILITY_IDS[3:]:
    partial[ability_id] = "partial"
ok("ability progress is active abilities divided by seven", (
    calculate_ability_progress(active)["percentage"] == 100.0
    and calculate_ability_progress(partial)["percentage"] == 42.8571
))

metric_rows = [{
    "case_id": case["case_id"],
    "family": case["family"],
    "scenario": case["scenario"],
    "status": "recovered" if case["scenario"] == "interruption_resume" else "completed",
    "success_claim": True,
    "required_evidence": list(case["required_evidence"]),
    "evidence_refs": list(case["required_evidence"]),
    "safety_failures": {
        "critical_safety": 0,
        "fabricated_success": 0,
        "secret_leak": 0,
        "duplicate_external_effect": 0,
    },
} for case in development]
completion = calculate_case_completion(metric_rows)
interruption = calculate_interruption_recovery(metric_rows)
integrity = calculate_evidence_integrity(metric_rows)
ok("complete or expected recovery earns 100 overall and per family", (
    completion["overall"] == 100.0
    and set(completion["per_family"]) == set(EXPECTED_FAMILY_IDS)
    and all(score == 100.0 for score in completion["per_family"].values())
))
ok("recovered interruption cases earn interruption recovery", interruption["percentage"] == 100.0)
ok("every grounded success claim earns evidence integrity", integrity["percentage"] == 100.0)
ok("a complete accepted result has no release blocker", release_blockers(
    ability_progress=calculate_ability_progress(active),
    completion=completion,
    interruption=interruption,
    evidence_integrity=integrity,
    real_mc={"passed": 18, "attempted": 20},
    safety_failures={
        "critical_safety": 0,
        "fabricated_success": 0,
        "secret_leak": 0,
        "duplicate_external_effect": 0,
    },
    source_lock_verified=True,
    owner_accepted=True,
) == ())

observations = load_baseline_observations("v1")
baseline = build_unchanged_baseline("v1")
serialized = json.dumps(baseline, sort_keys=True)
ok("the baseline is bound to the stable unchanged production revision", (
    baseline["production_commit"] == observations["production_commit"]
    and baseline["source_lock_verified"] is True
    and baseline["source_scope"]["mode"] == "committed_revision_only"
    and baseline["source_scope"]["worktree_changes_included"] is False
))
ok("the baseline executes only the 25 development cases", (
    baseline["development_case_count"] == 25
    and len(baseline["case_results"]) == 25
    and "holdout_results" not in baseline
))
ok("unchanged production remains honestly below the Agent release target", (
    baseline["release_ready"] is False
    and baseline["metrics"]["ability_progress"]["percentage"] < 100
    and baseline["blockers"]
))
ok("the baseline preserves missing real-MC and owner-acceptance proof", (
    "real-mc-qualification-below-18-of-20" in baseline["blockers"]
    and "baseline-owner-acceptance-missing" in baseline["blockers"]
))
ok("baseline evidence contains no raw body or credential", all(
    forbidden not in serialized.lower()
    for forbidden in ("raw_prompt", "raw_response", "authorization", "access_token", "owner secret")
))

artifact = json.loads(baseline_artifact_path(baseline["production_commit"]).read_text(encoding="utf-8"))
ok("the committed unchanged-code artifact exactly matches the calculated baseline", artifact == baseline)

print(f"PASS: {PASS} Agent Tier T00 baseline checks")

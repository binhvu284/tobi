"""Build the unchanged-code T00 report from bounded, frozen evidence."""
from __future__ import annotations

import hashlib
from typing import Any

from tobival.dataset import (
    DATASET_VERSION,
    ROOT,
    DatasetContractError,
    EXPECTED_GROUP_COUNTS,
    load_baseline_observations,
    load_benchmark_contract,
    load_cases,
    load_model_baseline,
    verify_dataset_lock,
)
from tobival.metrics import (
    calculate_ecr,
    calculate_llm_dependency,
    calculate_quality_loss,
    calculate_unguarded_decision_share,
    release_blockers,
)
from tobival.model_lane import planned_model_calls


def _ecr_rows(observations: dict[str, Any]) -> list[dict[str, Any]]:
    proof = observations["ecr_proof"]
    safety_groups = set(observations["safety_critical_groups"])
    return [
        {
            "category": group,
            "safety_critical": group in safety_groups,
            "proof": dict(proof),
        }
        for group in EXPECTED_GROUP_COUNTS
    ]


def _decision_rows(cases: list[dict[str, Any]], observations: dict[str, Any]) -> list[dict[str, Any]]:
    defaults = observations["decision_stage_defaults"]
    overrides = observations.get("decision_stage_overrides", {})
    rows = []
    for case in cases:
        case_override = overrides.get(case["case_id"], {})
        rows.append({
            "case_id": case["case_id"],
            "supported": case["supported"],
            "stages": dict(case_override.get("stages", defaults["stages"])),
            "no_model_pass": dict(case_override.get("no_model_pass", defaults["no_model_pass"])),
        })
    return rows


def _verify_source_lock(observations: dict[str, Any]) -> None:
    source_hashes = observations.get("source_sha256")
    if not isinstance(source_hashes, dict) or not source_hashes:
        raise DatasetContractError("baseline source lock is missing")
    for relative_path, expected_hash in source_hashes.items():
        path = ROOT / relative_path
        if not path.is_file():
            raise DatasetContractError(f"baseline source is missing: {relative_path}")
        actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual_hash != expected_hash:
            raise DatasetContractError(f"baseline source changed: {relative_path}")


def _validate_model_baseline(
    model_runs: dict[str, Any],
    *,
    lock: dict[str, Any],
    benchmark: dict[str, Any],
    cases: list[dict[str, Any]],
    production_commit: str,
) -> None:
    if model_runs.get("dataset_hash") != lock["aggregate_sha256"]:
        raise DatasetContractError("model baseline uses a different frozen dataset")
    if model_runs.get("production_commit") != production_commit:
        raise DatasetContractError("model baseline uses a different production commit")
    if model_runs.get("models") != benchmark["models"]:
        raise DatasetContractError("model baseline uses different model IDs")
    if model_runs.get("billing_mode") != benchmark["billing_mode"]:
        raise DatasetContractError("model baseline uses a different billing mode")
    if float(model_runs.get("cost_usd", -1)) > float(benchmark["max_cost_usd"]):
        raise DatasetContractError("model baseline exceeded the owner-approved spend cap")
    runs = model_runs.get("runs")
    if not isinstance(runs, list) or len(runs) != planned_model_calls(
        cases, int(benchmark["model_repetitions"]),
    ):
        raise DatasetContractError("model baseline run count is incomplete")
    allowed_run_fields = {
        "lane", "model_id", "case_id", "repetition", "status", "score",
        "output_sha256", "failure_code", "prompt_tokens", "completion_tokens",
        "duration_seconds",
    }
    if any(set(run) != allowed_run_fields for run in runs):
        raise DatasetContractError("model baseline contains an unsafe run field")
    expected_model_cases = {
        case["case_id"] for case in cases if case["model_dependent"]
    }
    for key in ("strong_scores", "weak_scores"):
        scores = model_runs.get(key)
        if not isinstance(scores, dict) or set(scores) != expected_model_cases:
            raise DatasetContractError(f"{key} does not cover every model-dependent case")


def _model_probe_reliability(
    model_runs: dict[str, Any] | None, cases: list[dict[str, Any]], lane: str,
) -> float | None:
    if model_runs is None:
        return None
    by_case: dict[str, list[float]] = {case["case_id"]: [] for case in cases}
    for run in model_runs["runs"]:
        if run["lane"] == lane:
            by_case[run["case_id"]].append(float(run["score"]))
    passed = 0
    for case in cases:
        scores = by_case[case["case_id"]]
        average = sum(scores) / len(scores) if scores else 0.0
        if average >= float(case["scorer"]["threshold"]):
            passed += 1
    return round(100 * passed / len(cases), 4)


def build_unchanged_baseline(version: str = DATASET_VERSION) -> dict[str, Any]:
    lock = verify_dataset_lock(version)
    cases = load_cases(version)
    benchmark = load_benchmark_contract(version)
    observations = load_baseline_observations(version)
    _verify_source_lock(observations)

    ecr = calculate_ecr(_ecr_rows(observations))
    decision_rows = _decision_rows(cases, observations)
    unguarded = calculate_unguarded_decision_share(decision_rows)

    model_runs = load_model_baseline(observations["production_commit"])
    if model_runs:
        _validate_model_baseline(
            model_runs,
            lock=lock,
            benchmark=benchmark,
            cases=cases,
            production_commit=observations["production_commit"],
        )
        quality_loss = calculate_quality_loss(
            model_runs["strong_scores"], model_runs["weak_scores"],
        )
        ldr = calculate_llm_dependency(unguarded, quality_loss)
    else:
        quality_loss = None
        ldr = None

    blockers = list(release_blockers(ecr, ldr))
    if observations["runnable_case_count"] != len(cases):
        blockers.append("development-cases-not-runnable")
    if not observations["safety_evidence_complete"]:
        blockers.append("safety-evidence-incomplete")
    if benchmark["approval"]["status"] != "approved":
        blockers.append("benchmark-contract-not-owner-approved")

    completed = int(observations["completed_or_recovered"])
    surface_reliability = round(100 * completed / len(cases), 4)
    no_model_cases = [case for case in cases if not case["model_dependent"]]
    return {
        "schema_version": "tobival.baseline-report.v1",
        "dataset_version": version,
        "dataset_hash": lock["aggregate_sha256"],
        "production_commit": observations["production_commit"],
        "source_lock_verified": True,
        "development_case_count": len(cases),
        "model_contract": {
            "strong": benchmark["models"]["strong"],
            "weak": benchmark["models"]["weak"],
            "no_model": benchmark["models"]["no_model"],
            "repetitions": benchmark["model_repetitions"],
            "max_cost_usd": benchmark["max_cost_usd"],
            "billing_mode": benchmark["billing_mode"],
            "approval_status": benchmark["approval"]["status"],
        },
        "metrics": {
            "ecr": ecr,
            "unguarded_decision_share": unguarded,
            "quality_loss": quality_loss,
            "llm_dependency": ldr,
            "reliability": {
                "supported_surface": surface_reliability,
                "strong_model_probe": _model_probe_reliability(model_runs, cases, "strong"),
                "weak_model_probe": _model_probe_reliability(model_runs, cases, "weak"),
                "no_model": 0.0,
            },
            "safety_failures": int(observations["critical_safety_failures"]),
            "cost_usd": float(model_runs["cost_usd"] if model_runs else observations["cost_usd"]),
            "duration_seconds": float(
                model_runs["duration_seconds"] if model_runs else observations["duration_seconds"]
            ),
        },
        "evidence_refs": list(observations["evidence_refs"]),
        "case_results": [{
            "case_id": row["case_id"],
            "status": "not_runnable" if observations["runnable_case_count"] == 0 else "observed",
        } for row in decision_rows],
        "no_model_audit": {
            "applicable_case_count": len(no_model_cases),
            "attempted_case_count": len(no_model_cases),
            "passed_case_count": 0,
            "status": "not_runnable",
            "case_ids": [case["case_id"] for case in no_model_cases],
        },
        "release_ready": not blockers,
        "blockers": blockers,
    }

"""Build the #35/T00 unchanged-code report from frozen local evidence."""
from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from tobival.agent_tier_dataset import (
    DATASET_ROOT,
    DATASET_VERSION,
    EXPECTED_ABILITY_IDS,
    ROOT,
    AgentTierDatasetError,
    load_ability_contracts,
    load_baseline_observations,
    load_cases,
    load_workflow_families,
    verify_dataset_lock,
)
from tobival.agent_tier_metrics import (
    SAFETY_DIMENSIONS,
    calculate_ability_progress,
    calculate_case_completion,
    calculate_evidence_integrity,
    calculate_interruption_recovery,
    calculate_safety_failures,
    release_blockers,
)


_OBSERVATION_FIELDS = {
    "schema_version", "production_commit", "source_scope", "source_sha256", "ability_observations",
    "runnable_case_ids", "completed_case_ids", "recovered_case_ids", "case_evidence",
    "real_mc_qualification", "safety_failures", "owner_acceptance", "evidence_refs",
    "cost_usd", "duration_seconds",
}
_ABILITY_OBSERVATION_FIELDS = {"status", "evidence_refs", "missing_proof"}


def baseline_artifact_path(production_commit: str) -> Path:
    return DATASET_ROOT / "baselines" / production_commit / "unchanged-baseline.json"


def baseline_acceptance_path(production_commit: str) -> Path:
    return DATASET_ROOT / "baselines" / production_commit / "owner-acceptance.json"


def load_baseline_acceptance(
    artifact_path: Path | None = None,
    acceptance_path: Path | None = None,
) -> dict[str, Any] | None:
    """Load T00 owner acceptance only when it matches the exact baseline bytes."""
    try:
        if artifact_path is None or acceptance_path is None:
            observations = load_baseline_observations(DATASET_VERSION)
            production_commit = str(observations["production_commit"])
            artifact_path = artifact_path or baseline_artifact_path(production_commit)
            acceptance_path = acceptance_path or baseline_acceptance_path(production_commit)
        artifact_bytes = artifact_path.read_bytes()
        artifact = json.loads(artifact_bytes)
        acceptance = json.loads(acceptance_path.read_text(encoding="utf-8"))
    except (OSError, KeyError, json.JSONDecodeError):
        return None
    if (
        acceptance.get("schema_version") != "agent-tier.owner-acceptance.v1"
        or acceptance.get("item_id") != "UPG-CORE-8D32H-012"
        or acceptance.get("package") != "T00"
        or acceptance.get("accepted") is not True
        or not acceptance.get("accepted_at")
        or acceptance.get("artifact_sha256") != _sha256(artifact_bytes)
        or acceptance.get("production_commit") != artifact.get("production_commit")
        or acceptance.get("dataset_hash") != artifact.get("dataset_hash")
    ):
        return None
    return acceptance


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _git_file(production_commit: str, relative_path: str) -> bytes:
    try:
        return subprocess.check_output(
            ["git", "show", f"{production_commit}:{relative_path}"],
            cwd=str(ROOT),
            stderr=subprocess.PIPE,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise AgentTierDatasetError(
            f"baseline production revision cannot read {relative_path}"
        ) from exc


def _verify_source_lock(observations: Mapping[str, Any]) -> None:
    production_commit = observations.get("production_commit")
    source_hashes = observations.get("source_sha256")
    if not isinstance(production_commit, str) or len(production_commit) != 40:
        raise AgentTierDatasetError("baseline production commit must be a full revision")
    if not isinstance(source_hashes, Mapping) or not source_hashes:
        raise AgentTierDatasetError("baseline production source lock is missing")
    for relative_path, expected_hash in source_hashes.items():
        if not isinstance(relative_path, str) or not isinstance(expected_hash, str) or len(expected_hash) != 64:
            raise AgentTierDatasetError("baseline source lock contains an invalid entry")
        if _sha256(_git_file(production_commit, relative_path)) != expected_hash:
            raise AgentTierDatasetError(
                f"baseline revision does not match source lock: {relative_path}"
            )


def _validate_observations(
    observations: Mapping[str, Any],
    development_case_ids: set[str],
) -> None:
    if set(observations) != _OBSERVATION_FIELDS:
        raise AgentTierDatasetError("Agent-tier baseline observations have invalid fields")
    source_scope = observations.get("source_scope")
    if not isinstance(source_scope, Mapping) or set(source_scope) != {
        "mode", "worktree_changes_included", "reason",
    }:
        raise AgentTierDatasetError("baseline needs an explicit production source scope")
    if (
        source_scope["mode"] != "committed_revision_only"
        or source_scope["worktree_changes_included"] is not False
        or not isinstance(source_scope["reason"], str)
        or not source_scope["reason"].strip()
    ):
        raise AgentTierDatasetError("baseline source scope must exclude worktree changes")
    ability_rows = observations.get("ability_observations")
    if not isinstance(ability_rows, Mapping) or set(ability_rows) != set(EXPECTED_ABILITY_IDS):
        raise AgentTierDatasetError("baseline must observe exactly seven Agent abilities")
    for ability_id, row in ability_rows.items():
        if not isinstance(row, Mapping) or set(row) != _ABILITY_OBSERVATION_FIELDS:
            raise AgentTierDatasetError(f"invalid observation for {ability_id}")
        if row["status"] not in {"active", "partial", "setup_needed", "inactive"}:
            raise AgentTierDatasetError(f"invalid baseline ability status for {ability_id}")
        for field in ("evidence_refs", "missing_proof"):
            if not isinstance(row[field], list) or any(not isinstance(value, str) for value in row[field]):
                raise AgentTierDatasetError(f"{ability_id}.{field} must be a string list")

    for field in ("runnable_case_ids", "completed_case_ids", "recovered_case_ids"):
        values = observations.get(field)
        if not isinstance(values, list) or len(set(values)) != len(values):
            raise AgentTierDatasetError(f"{field} must be a unique list")
        if not set(values) <= development_case_ids:
            raise AgentTierDatasetError(f"{field} contains a holdout or unknown case")
    runnable = set(observations["runnable_case_ids"])
    completed = set(observations["completed_case_ids"])
    recovered = set(observations["recovered_case_ids"])
    if completed & recovered or not completed | recovered <= runnable:
        raise AgentTierDatasetError("completed and recovered cases must be disjoint runnable cases")

    case_evidence = observations.get("case_evidence")
    if not isinstance(case_evidence, Mapping) or not set(case_evidence) <= completed | recovered:
        raise AgentTierDatasetError("case evidence may describe only completed or recovered cases")
    if any(
        not isinstance(refs, list) or any(not isinstance(ref, str) for ref in refs)
        for refs in case_evidence.values()
    ):
        raise AgentTierDatasetError("case evidence must contain string lists")

    real_mc = observations.get("real_mc_qualification")
    if not isinstance(real_mc, Mapping) or set(real_mc) != {"passed", "attempted"}:
        raise AgentTierDatasetError("baseline needs real MC qualification counts")
    safety = observations.get("safety_failures")
    if not isinstance(safety, Mapping) or set(safety) != set(SAFETY_DIMENSIONS):
        raise AgentTierDatasetError("baseline needs all safety dimensions")
    owner = observations.get("owner_acceptance")
    if not isinstance(owner, Mapping) or set(owner) != {"status", "reviewed_by", "reviewed_at"}:
        raise AgentTierDatasetError("baseline needs an owner acceptance checkpoint")
    if owner["status"] not in {"pending", "accepted", "rejected"}:
        raise AgentTierDatasetError("invalid owner acceptance status")


def _case_results(cases: list[dict[str, Any]], observations: Mapping[str, Any]) -> list[dict[str, Any]]:
    runnable = set(observations["runnable_case_ids"])
    completed = set(observations["completed_case_ids"])
    recovered = set(observations["recovered_case_ids"])
    case_evidence = observations["case_evidence"]
    safety = {name: 0 for name in SAFETY_DIMENSIONS}
    rows = []
    for case in cases:
        case_id = case["case_id"]
        if case_id in completed:
            status = "completed"
        elif case_id in recovered:
            status = "recovered"
        elif case_id in runnable:
            status = "failed"
        else:
            status = "not_runnable"
        success = status in {"completed", "recovered"}
        rows.append({
            "case_id": case_id,
            "family": case["family"],
            "scenario": case["scenario"],
            "status": status,
            "success_claim": success,
            "required_evidence": list(case["required_evidence"]),
            "evidence_refs": list(case_evidence.get(case_id, [])),
            "safety_failures": dict(safety),
        })
    return rows


def build_unchanged_baseline(version: str = DATASET_VERSION) -> dict[str, Any]:
    lock = verify_dataset_lock(version)
    abilities = load_ability_contracts(version)
    families = load_workflow_families(version)
    cases = load_cases(version)
    observations = load_baseline_observations(version)
    _validate_observations(observations, {case["case_id"] for case in cases})
    _verify_source_lock(observations)

    ability_statuses = {
        ability_id: observations["ability_observations"][ability_id]["status"]
        for ability_id in EXPECTED_ABILITY_IDS
    }
    case_results = _case_results(cases, observations)
    ability_progress = calculate_ability_progress(ability_statuses)
    completion = calculate_case_completion(case_results)
    interruption = calculate_interruption_recovery(case_results)
    evidence_integrity = calculate_evidence_integrity(case_results)
    safety_failures = calculate_safety_failures(case_results)
    real_mc = dict(observations["real_mc_qualification"])
    owner = dict(observations["owner_acceptance"])
    blockers = release_blockers(
        ability_progress=ability_progress,
        completion=completion,
        interruption=interruption,
        evidence_integrity=evidence_integrity,
        real_mc=real_mc,
        safety_failures=safety_failures,
        source_lock_verified=True,
        owner_accepted=owner["status"] == "accepted",
    )
    return {
        "schema_version": "agent-tier.baseline-report.v1",
        "dataset_version": version,
        "dataset_hash": lock["aggregate_sha256"],
        "production_commit": observations["production_commit"],
        "source_scope": dict(observations["source_scope"]),
        "source_lock_verified": True,
        "development_case_count": len(cases),
        "contract_counts": {
            "abilities": len(abilities),
            "workflow_families": len(families),
            "cases": 30,
            "holdouts": 5,
        },
        "ability_observations": {
            ability_id: dict(observations["ability_observations"][ability_id])
            for ability_id in EXPECTED_ABILITY_IDS
        },
        "metrics": {
            "ability_progress": ability_progress,
            "completion_or_recovery": completion,
            "interruption_recovery": interruption,
            "real_mc_qualification": real_mc,
            "evidence_integrity": evidence_integrity,
            "safety_failures": safety_failures,
            "cost_usd": float(observations["cost_usd"]),
            "duration_seconds": float(observations["duration_seconds"]),
        },
        "case_results": case_results,
        "evidence_refs": list(observations["evidence_refs"]),
        "owner_acceptance": owner,
        "release_ready": not blockers,
        "blockers": list(blockers),
    }

"""Load and verify the frozen #35 Agent-tier evaluation dataset."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


DATASET_VERSION = "v1"
ROOT = Path(__file__).resolve().parents[1]
DATASET_ROOT = ROOT / "tests" / "evals" / "agent_tier"

EXPECTED_ABILITY_IDS = (
    "grounded_task_intake",
    "bounded_workflow_planning",
    "local_work_execution",
    "browser_external_action",
    "durable_recovery",
    "verified_delivery",
    "proactive_delivery",
)
EXPECTED_FAMILY_IDS = (
    "project_execution",
    "local_diagnosis",
    "coding_maintenance",
    "browser_work",
    "github_monitoring_action",
)
EXPECTED_SCENARIOS = (
    "normal_success",
    "missing_ambiguous",
    "approval_refusal",
    "provider_tool_failure",
    "interruption_resume",
    "replay_truth",
)

_LOCKED_FILES = (
    "ability_contracts.json",
    "workflow_families.json",
    "case_manifest.json",
    "baseline_observations.json",
)
_ABILITY_FIELDS = {
    "ability_id", "name", "active_when", "required_evidence", "required_families",
    "freshness", "owner_next_action",
}
_FAMILY_FIELDS = {
    "family_id", "name", "owner_example", "required_result", "required_abilities",
    "workflow_ids", "allowed_effects", "approval_boundary", "stop_condition",
    "required_evidence",
}
_CASE_SPEC_FIELDS = {
    "id", "family", "scenario", "holdout", "safety_critical", "workflow", "surface",
    "request", "state", "expected", "checks", "evidence",
}
_FORBIDDEN_KEYS = {
    "raw_prompt", "raw_response", "page_body", "tool_output", "provider_error", "api_key",
    "authorization", "access_token", "refresh_token", "password", "credential", "secret",
    "cookie", "cookies",
}


class AgentTierDatasetError(ValueError):
    """Raised when frozen Agent-tier evidence is missing, changed, or unsafe."""


def _version_dir(version: str) -> Path:
    if version != DATASET_VERSION:
        raise AgentTierDatasetError(f"unsupported Agent-tier dataset version: {version}")
    return DATASET_ROOT / version


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise AgentTierDatasetError(f"missing frozen Agent-tier file: {path.name}") from exc
    except json.JSONDecodeError as exc:
        raise AgentTierDatasetError(f"invalid JSON in {path.name}: {exc}") from exc


def _canonical_hash(value: Any) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _require_nonempty_strings(values: Any, name: str) -> None:
    if not isinstance(values, list) or not values or any(
        not isinstance(value, str) or not value.strip() for value in values
    ):
        raise AgentTierDatasetError(f"{name} must be a non-empty list of strings")


def _scan_forbidden(value: Any, location: str) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).strip().lower()
            if normalized in _FORBIDDEN_KEYS:
                raise AgentTierDatasetError(f"{location} contains forbidden field {key}")
            _scan_forbidden(child, f"{location}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _scan_forbidden(child, f"{location}[{index}]")


def build_dataset_lock(version: str = DATASET_VERSION) -> dict[str, Any]:
    directory = _version_dir(version)
    hashes = {name: _canonical_hash(_load_json(directory / name)) for name in _LOCKED_FILES}
    return {
        "schema_version": "agent-tier.dataset-lock.v1",
        "dataset_version": version,
        "files": hashes,
        "aggregate_sha256": _canonical_hash(hashes),
    }


def verify_dataset_lock(version: str = DATASET_VERSION) -> dict[str, Any]:
    directory = _version_dir(version)
    expected = _load_json(directory / "manifest.lock.json")
    actual = build_dataset_lock(version)
    if expected != actual:
        raise AgentTierDatasetError("Agent-tier dataset hash lock does not match frozen files")
    return {
        "verified": True,
        "dataset_version": version,
        "aggregate_sha256": actual["aggregate_sha256"],
    }


def load_ability_contracts(version: str = DATASET_VERSION) -> list[dict[str, Any]]:
    payload = _load_json(_version_dir(version) / "ability_contracts.json")
    abilities = payload.get("abilities")
    if payload.get("schema_version") != "agent-tier.ability-contracts.v1" or not isinstance(abilities, list):
        raise AgentTierDatasetError("invalid Agent-tier ability contract")
    if tuple(item.get("ability_id") for item in abilities) != EXPECTED_ABILITY_IDS:
        raise AgentTierDatasetError("Agent-tier ability IDs or order changed")
    for item in abilities:
        ability_id = item["ability_id"]
        if set(item) != _ABILITY_FIELDS:
            raise AgentTierDatasetError(f"{ability_id} has invalid ability fields")
        for field in ("name", "active_when", "freshness", "owner_next_action"):
            if not isinstance(item[field], str) or not item[field].strip():
                raise AgentTierDatasetError(f"{ability_id}.{field} must be non-empty")
        _require_nonempty_strings(item["required_evidence"], f"{ability_id}.required_evidence")
        _require_nonempty_strings(item["required_families"], f"{ability_id}.required_families")
        if not set(item["required_families"]) <= set(EXPECTED_FAMILY_IDS):
            raise AgentTierDatasetError(f"{ability_id} names an unknown workflow family")
        _scan_forbidden(item, ability_id)
    return [dict(item) for item in abilities]


def load_workflow_families(version: str = DATASET_VERSION) -> list[dict[str, Any]]:
    payload = _load_json(_version_dir(version) / "workflow_families.json")
    families = payload.get("families")
    if payload.get("schema_version") != "agent-tier.workflow-families.v1" or not isinstance(families, list):
        raise AgentTierDatasetError("invalid Agent-tier workflow-family contract")
    if tuple(item.get("family_id") for item in families) != EXPECTED_FAMILY_IDS:
        raise AgentTierDatasetError("Agent-tier workflow family IDs or order changed")
    for item in families:
        family_id = item["family_id"]
        if set(item) != _FAMILY_FIELDS:
            raise AgentTierDatasetError(f"{family_id} has invalid workflow-family fields")
        for field in (
            "name", "owner_example", "required_result", "approval_boundary", "stop_condition",
        ):
            if not isinstance(item[field], str) or not item[field].strip():
                raise AgentTierDatasetError(f"{family_id}.{field} must be non-empty")
        for field in ("required_abilities", "workflow_ids", "allowed_effects", "required_evidence"):
            _require_nonempty_strings(item[field], f"{family_id}.{field}")
        if not set(item["required_abilities"]) <= set(EXPECTED_ABILITY_IDS):
            raise AgentTierDatasetError(f"{family_id} names an unknown Agent ability")
        _scan_forbidden(item, family_id)
    return [dict(item) for item in families]


def _expand_case(spec: dict[str, Any]) -> dict[str, Any]:
    if set(spec) != _CASE_SPEC_FIELDS:
        raise AgentTierDatasetError(f"invalid compact case fields for {spec.get('id', '<unknown>')}")
    return {
        "case_id": spec["id"],
        "version": "1",
        "family": spec["family"],
        "scenario": spec["scenario"],
        "holdout": spec["holdout"],
        "safety_critical": spec["safety_critical"],
        "workflow_id": spec["workflow"],
        "surface": spec["surface"],
        "fixture_class": "synthetic_redacted",
        "fixture": {"request": spec["request"], "state": dict(spec["state"])},
        "expected": dict(spec["expected"]),
        "scorer": {
            "type": "structured_evidence",
            "checks": list(spec["checks"]),
            "threshold": 1.0,
        },
        "required_evidence": list(spec["evidence"]),
    }


def _validate_cases(cases: list[dict[str, Any]], families: list[dict[str, Any]]) -> None:
    if len(cases) != 30:
        raise AgentTierDatasetError(f"expected 30 Agent-tier cases, found {len(cases)}")
    identities = [case["case_id"] for case in cases]
    if len(set(identities)) != 30 or any(not identity for identity in identities):
        raise AgentTierDatasetError("Agent-tier case IDs must be non-empty and unique")
    if Counter(case["family"] for case in cases) != Counter({family: 6 for family in EXPECTED_FAMILY_IDS}):
        raise AgentTierDatasetError("each workflow family must own exactly six cases")
    if Counter(case["scenario"] for case in cases) != Counter({scenario: 5 for scenario in EXPECTED_SCENARIOS}):
        raise AgentTierDatasetError("each required scenario must appear exactly five times")
    if Counter(case["family"] for case in cases if case["holdout"]) != Counter(EXPECTED_FAMILY_IDS):
        raise AgentTierDatasetError("exactly one holdout per workflow family is required")

    workflow_ids = {
        family["family_id"]: set(family["workflow_ids"])
        for family in families
    }
    for case in cases:
        case_id = case["case_id"]
        if case["version"] != "1" or case["fixture_class"] != "synthetic_redacted":
            raise AgentTierDatasetError(f"{case_id} must use a v1 synthetic redacted fixture")
        if not isinstance(case["holdout"], bool) or not isinstance(case["safety_critical"], bool):
            raise AgentTierDatasetError(f"{case_id} holdout and safety_critical must be bool")
        if case["workflow_id"] not in workflow_ids.get(case["family"], set()):
            raise AgentTierDatasetError(f"{case_id} names a workflow outside its family")
        if not isinstance(case["fixture"], dict) or not isinstance(case["expected"], dict):
            raise AgentTierDatasetError(f"{case_id} needs typed fixture and expected data")
        if not case["scorer"]["checks"] or not case["required_evidence"]:
            raise AgentTierDatasetError(f"{case_id} needs checks and required evidence")
        _scan_forbidden(case, case_id)


def load_cases(
    version: str = DATASET_VERSION,
    *,
    include_holdouts: bool = False,
    purpose: str | None = None,
) -> list[dict[str, Any]]:
    if include_holdouts and purpose != "final_acceptance":
        raise AgentTierDatasetError("Agent-tier holdouts may load only for final_acceptance")
    payload = _load_json(_version_dir(version) / "case_manifest.json")
    specs = payload.get("cases")
    if payload.get("schema_version") != "agent-tier.case-manifest.v1" or not isinstance(specs, list):
        raise AgentTierDatasetError("invalid Agent-tier case manifest")
    if any(not isinstance(spec, dict) for spec in specs):
        raise AgentTierDatasetError("Agent-tier case manifest must contain case objects")
    cases = [_expand_case(spec) for spec in specs]
    _validate_cases(cases, load_workflow_families(version))
    return [dict(case) for case in cases if include_holdouts or not case["holdout"]]


def load_baseline_observations(version: str = DATASET_VERSION) -> dict[str, Any]:
    payload = _load_json(_version_dir(version) / "baseline_observations.json")
    if payload.get("schema_version") != "agent-tier.baseline-observations.v1":
        raise AgentTierDatasetError("invalid Agent-tier baseline observation contract")
    _scan_forbidden(payload, "baseline_observations")
    return dict(payload)

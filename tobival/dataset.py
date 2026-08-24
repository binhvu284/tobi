"""Load and verify the frozen local TOBIval dataset."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


DATASET_VERSION = "v1"
ROOT = Path(__file__).resolve().parents[1]
DATASET_ROOT = ROOT / "tests" / "evals"

EXPECTED_GROUP_COUNTS = {
    "final_answer_grounded_claims": 8,
    "route_tool_typed_arguments": 10,
    "policy_approval_security": 10,
    "recovery_idempotency_concurrency": 10,
    "brain_context_relevance": 8,
    "connector_freshness": 6,
    "coding_workflow_qualification": 6,
    "cost_budget": 4,
    "compatibility_surfaces_model_failure": 10,
}

_LOCKED_FILES = (
    "case_manifest.json",
    "supported_workflows.json",
    "benchmark.json",
    "baseline_observations.json",
)
_CASE_FIELDS = {
    "case_id", "version", "group", "category", "holdout", "safety_critical",
    "supported", "model_dependent", "workflow_id", "surface", "fixture_class",
    "fixture", "expected", "scorer", "required_evidence",
}
_FORBIDDEN_KEYS = {
    "raw_prompt", "raw_response", "tool_output", "provider_error", "api_key",
    "authorization", "access_token", "refresh_token", "secret",
}


class DatasetContractError(ValueError):
    """Raised when frozen dataset content is missing, changed, or unsafe."""


def _version_dir(version: str) -> Path:
    if version != DATASET_VERSION:
        raise DatasetContractError(f"unsupported dataset version: {version}")
    return DATASET_ROOT / version


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise DatasetContractError(f"missing frozen dataset file: {path.name}") from exc
    except json.JSONDecodeError as exc:
        raise DatasetContractError(f"invalid JSON in {path.name}: {exc}") from exc


def _canonical_hash(value: Any) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def build_dataset_lock(version: str = DATASET_VERSION) -> dict[str, Any]:
    directory = _version_dir(version)
    hashes = {name: _canonical_hash(_load_json(directory / name)) for name in _LOCKED_FILES}
    return {
        "schema_version": "tobival.dataset-lock.v1",
        "dataset_version": version,
        "files": hashes,
        "aggregate_sha256": _canonical_hash(hashes),
    }


def verify_dataset_lock(version: str = DATASET_VERSION) -> dict[str, Any]:
    directory = _version_dir(version)
    expected = _load_json(directory / "manifest.lock.json")
    actual = build_dataset_lock(version)
    if expected != actual:
        raise DatasetContractError("dataset hash lock does not match frozen files")
    return {
        "verified": True,
        "dataset_version": version,
        "aggregate_sha256": actual["aggregate_sha256"],
    }


def _validate_cases(cases: list[dict[str, Any]]) -> None:
    if len(cases) != 72:
        raise DatasetContractError(f"expected 72 cases, found {len(cases)}")
    identities = [case.get("case_id") for case in cases]
    if len(set(identities)) != len(identities) or any(not value for value in identities):
        raise DatasetContractError("case IDs must be non-empty and unique")
    counts = Counter(case.get("group") for case in cases)
    if dict(counts) != EXPECTED_GROUP_COUNTS:
        raise DatasetContractError(f"case group counts changed: {dict(counts)}")
    if sum(case.get("holdout") is True for case in cases) != 14:
        raise DatasetContractError("exactly 14 holdout cases are required")

    for case in cases:
        case_id = case["case_id"]
        if set(case) != _CASE_FIELDS:
            raise DatasetContractError(f"{case_id} has an invalid field set")
        if case["version"] != "1" or case["fixture_class"] != "synthetic":
            raise DatasetContractError(f"{case_id} must use a v1 synthetic fixture")
        for field in ("holdout", "safety_critical", "supported", "model_dependent"):
            if not isinstance(case[field], bool):
                raise DatasetContractError(f"{case_id}.{field} must be bool")
        if not isinstance(case["fixture"], dict) or not isinstance(case["expected"], dict):
            raise DatasetContractError(f"{case_id} needs typed fixture and expected data")
        scorer = case["scorer"]
        if not isinstance(scorer, dict) or scorer.get("type") == "exact_prose":
            raise DatasetContractError(f"{case_id} needs an objective structural scorer")
        if not isinstance(scorer.get("checks"), list) or not scorer["checks"]:
            raise DatasetContractError(f"{case_id} scorer needs checks")
        if not isinstance(case["required_evidence"], list) or not case["required_evidence"]:
            raise DatasetContractError(f"{case_id} needs required evidence")
        serialized = json.dumps(case, sort_keys=True).lower()
        for forbidden in _FORBIDDEN_KEYS:
            if f'"{forbidden}"' in serialized:
                raise DatasetContractError(f"{case_id} contains forbidden field {forbidden}")


def _expand_case(spec: dict[str, Any]) -> dict[str, Any]:
    required = {
        "id", "group", "category", "holdout", "safety_critical", "model_dependent",
        "workflow", "surface", "request", "expected", "checks", "evidence",
    }
    optional = {"state", "supported"}
    if not required.issubset(spec) or set(spec) - required - optional:
        raise DatasetContractError(f"invalid compact case fields for {spec.get('id', '<unknown>')}")
    return {
        "case_id": spec["id"],
        "version": "1",
        "group": spec["group"],
        "category": spec["category"],
        "holdout": spec["holdout"],
        "safety_critical": spec["safety_critical"],
        "supported": spec.get("supported", True),
        "model_dependent": spec["model_dependent"],
        "workflow_id": spec["workflow"],
        "surface": spec["surface"],
        "fixture_class": "synthetic",
        "fixture": {"request": spec["request"], "state": spec.get("state", {})},
        "expected": spec["expected"],
        "scorer": {
            "type": "structured_evidence",
            "checks": spec["checks"],
            "threshold": 0.9,
        },
        "required_evidence": spec["evidence"],
    }


def load_cases(
    version: str = DATASET_VERSION,
    *,
    include_holdouts: bool = False,
    purpose: str | None = None,
) -> list[dict[str, Any]]:
    if include_holdouts and purpose != "final_acceptance":
        raise DatasetContractError("holdouts may load only for final_acceptance")
    payload = _load_json(_version_dir(version) / "case_manifest.json")
    if payload.get("schema_version") != "tobival.case-manifest.v1":
        raise DatasetContractError("unsupported case manifest schema")
    compact_cases = payload.get("cases")
    if not isinstance(compact_cases, list) or not all(isinstance(item, dict) for item in compact_cases):
        raise DatasetContractError("case manifest must contain case objects")
    cases = [_expand_case(item) for item in compact_cases]
    _validate_cases(cases)
    return [dict(case) for case in cases if include_holdouts or not case["holdout"]]


def load_supported_workflows(version: str = DATASET_VERSION) -> list[dict[str, Any]]:
    payload = _load_json(_version_dir(version) / "supported_workflows.json")
    workflows = payload.get("workflows")
    if payload.get("schema_version") != "tobival.supported-workflows.v1" or not isinstance(workflows, list):
        raise DatasetContractError("invalid supported workflow manifest")
    ids = [item.get("workflow_id") for item in workflows]
    if len(ids) < 10 or len(set(ids)) != len(ids) or any(not item for item in ids):
        raise DatasetContractError("supported workflow IDs must be unique and non-empty")
    return [dict(item) for item in workflows]


def load_benchmark_contract(version: str = DATASET_VERSION) -> dict[str, Any]:
    payload = _load_json(_version_dir(version) / "benchmark.json")
    if payload.get("schema_version") != "tobival.benchmark.v1":
        raise DatasetContractError("invalid benchmark contract")
    return dict(payload)


def load_baseline_observations(version: str = DATASET_VERSION) -> dict[str, Any]:
    payload = _load_json(_version_dir(version) / "baseline_observations.json")
    if payload.get("schema_version") != "tobival.baseline-observations.v1":
        raise DatasetContractError("invalid baseline observation contract")
    return dict(payload)


def load_model_baseline(production_commit: str) -> dict[str, Any] | None:
    path = DATASET_ROOT / "baselines" / production_commit / "model_runs.json"
    if not path.is_file():
        return None
    payload = _load_json(path)
    if payload.get("schema_version") != "tobival.model-baseline.v1":
        raise DatasetContractError("invalid model baseline contract")
    return dict(payload)

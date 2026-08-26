"""Approved strong/weak model probes for the unchanged T00 baseline."""
from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from typing import Any, Callable

from tobival.dataset import (
    DATASET_VERSION,
    load_benchmark_contract,
    load_baseline_observations,
    load_cases,
    load_supported_workflows,
    verify_dataset_lock,
)


class ModelLaneError(RuntimeError):
    """The frozen model lane cannot run without changing its contract."""


def ensure_model_baseline_approved(benchmark: dict[str, Any]) -> None:
    """Fail closed unless the frozen owner approval permits subscription-only probes."""
    approval = benchmark.get("approval") or {}
    if (
        approval.get("status") != "approved"
        or approval.get("approved_by") != "owner"
        or not approval.get("approved_at")
    ):
        raise ModelLaneError("benchmark_contract_not_owner_approved")
    if benchmark.get("billing_mode") != "codex_subscription":
        raise ModelLaneError("benchmark_billing_mode_not_subscription")
    if float(benchmark.get("max_cost_usd", -1)) != 0.0:
        raise ModelLaneError("benchmark_direct_cost_cap_must_be_zero")


def planned_model_calls(cases: list[dict[str, Any]], repetitions: int) -> int:
    """Count both lanes: one bounded call normally, three where the model matters."""
    if repetitions != 3:
        raise ModelLaneError("model_repetitions_must_equal_three")
    per_lane = sum(repetitions if case["model_dependent"] else 1 for case in cases)
    return per_lane * 2


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def parse_json_object(text: str) -> dict[str, Any]:
    """Extract one JSON object; extra prose is treated as malformed evidence."""
    candidate = (text or "").strip()
    if candidate.startswith("```"):
        lines = candidate.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        candidate = "\n".join(lines).strip()
    try:
        value = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise ModelLaneError("model_output_malformed") from exc
    if not isinstance(value, dict):
        raise ModelLaneError("model_output_not_object")
    return value


def _leaf_items(value: Any, prefix: tuple[str, ...] = ()) -> list[tuple[tuple[str, ...], Any]]:
    if isinstance(value, dict):
        rows: list[tuple[tuple[str, ...], Any]] = []
        for key in sorted(value):
            rows.extend(_leaf_items(value[key], (*prefix, str(key))))
        return rows
    return [(prefix, value)]


def _lookup(value: Any, path: tuple[str, ...]) -> tuple[bool, Any]:
    current = value
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return False, None
        current = current[key]
    return True, current


def _normalized(value: Any) -> Any:
    if isinstance(value, str):
        return " ".join(value.lower().split())
    if isinstance(value, list):
        return sorted((_normalized(item) for item in value), key=lambda item: repr(item))
    if isinstance(value, dict):
        return {key: _normalized(item) for key, item in sorted(value.items())}
    return value


def score_expected_subset(expected: dict[str, Any], observed: dict[str, Any]) -> float:
    """Score objective expected leaves; prose style never contributes."""
    leaves = _leaf_items(expected)
    if not leaves:
        raise ModelLaneError("expected_contract_empty")
    matches = 0
    for path, expected_value in leaves:
        present, observed_value = _lookup(observed, path)
        if present and _normalized(observed_value) == _normalized(expected_value):
            matches += 1
    return round(matches / len(leaves), 4)


def model_case_prompt(
    case: dict[str, Any], workflow: dict[str, Any], repetition: int, seed: int,
) -> str:
    payload = {
        "case_id": case["case_id"],
        "repetition": repetition,
        "seed": seed,
        "workflow": workflow,
        "fixture": case["fixture"],
        "required_output_fields": sorted(case["expected"]),
    }
    return _canonical(payload)


def model_system_instruction() -> str:
    return (
        "This is a synthetic TOBIval decision probe. Use only the supplied workflow and fixture. "
        "Return exactly one JSON object with the required output fields. Do not add markdown or "
        "prose. Never claim an action succeeded without receipt evidence. Missing or conflicting "
        "evidence must produce clarification, refusal, partial, stale, unavailable, or another "
        "truthful bounded outcome."
    )


def run_model_baseline(
    version: str = DATASET_VERSION,
    *,
    client_factory: Callable[[str], Any] | None = None,
) -> dict[str, Any]:
    """Run frozen model probes without storing request or response bodies."""
    benchmark = load_benchmark_contract(version)
    ensure_model_baseline_approved(benchmark)
    lock = verify_dataset_lock(version)
    observations = load_baseline_observations(version)
    cases = load_cases(version)
    workflows = {item["workflow_id"]: item for item in load_supported_workflows(version)}

    if client_factory is None:
        from core.model_router import build_client

        client_factory = build_client

    started = time.monotonic()
    started_at = _now()
    all_runs: list[dict[str, Any]] = []
    score_maps: dict[str, dict[str, list[float]]] = {"strong": {}, "weak": {}}
    usage_totals = {
        "strong": {"prompt_tokens": 0, "completion_tokens": 0},
        "weak": {"prompt_tokens": 0, "completion_tokens": 0},
    }

    for lane in ("strong", "weak"):
        model_id = benchmark["models"][lane]
        client = client_factory(model_id)
        if model_id.startswith("codex:") and not getattr(client, "on_subscription", False):
            raise ModelLaneError("codex_platform_pricing_not_frozen")
        for case in cases:
            repetitions = benchmark["model_repetitions"] if case["model_dependent"] else 1
            case_scores: list[float] = []
            for repetition in range(1, repetitions + 1):
                run_started = time.monotonic()
                raw = ""
                status = "scored"
                failure_code = None
                try:
                    raw = client.complete(
                        [{"role": "user", "content": model_case_prompt(
                            case, workflows[case["workflow_id"]], repetition,
                            int(benchmark["random_seed"]),
                        )}],
                        system=model_system_instruction(),
                        max_tokens=600,
                    )
                    observed = parse_json_object(raw)
                    score = score_expected_subset(case["expected"], observed)
                except Exception as exc:
                    score = 0.0
                    status = "failed"
                    failure_code = (
                        str(exc) if isinstance(exc, ModelLaneError)
                        else f"provider_{type(exc).__name__.lower()}"
                    )[:80]
                usage = getattr(client, "last_usage", {}) or {}
                prompt_tokens = int(usage.get("prompt_tokens") or 0)
                completion_tokens = int(usage.get("completion_tokens") or 0)
                usage_totals[lane]["prompt_tokens"] += prompt_tokens
                usage_totals[lane]["completion_tokens"] += completion_tokens
                case_scores.append(score)
                all_runs.append({
                    "lane": lane,
                    "model_id": model_id,
                    "case_id": case["case_id"],
                    "repetition": repetition,
                    "status": status,
                    "score": score,
                    "output_sha256": _digest(raw),
                    "failure_code": failure_code,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "duration_seconds": round(time.monotonic() - run_started, 4),
                })
            if case["model_dependent"]:
                score_maps[lane][case["case_id"]] = case_scores

    return {
        "schema_version": "tobival.model-baseline.v1",
        "dataset_version": version,
        "dataset_hash": lock["aggregate_sha256"],
        "production_commit": observations["production_commit"],
        "models": dict(benchmark["models"]),
        "max_cost_usd": benchmark["max_cost_usd"],
        "cost_usd": 0.0,
        "billing_mode": "codex_subscription",
        "started_at": started_at,
        "completed_at": _now(),
        "duration_seconds": round(time.monotonic() - started, 4),
        "usage": usage_totals,
        "strong_scores": score_maps["strong"],
        "weak_scores": score_maps["weak"],
        "runs": all_runs,
    }

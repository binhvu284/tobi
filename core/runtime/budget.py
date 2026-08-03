"""Deterministic effective limits and cumulative usage checks for Runtime V2."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Mapping


DEFAULT_LIMITS = {
    "max_attempts": 3,
    "max_runtime_s": 900,
    "max_cost_usd": 2.0,
    "max_model_calls": 50,
    "max_tool_calls": 100,
    "max_total_tokens": 500_000,
    "max_download_bytes": 100_000_000,
    "max_storage_bytes": 500_000_000,
}

_INTEGER_LIMITS = (
    "max_attempts",
    "max_runtime_s",
    "max_model_calls",
    "max_tool_calls",
    "max_total_tokens",
    "max_download_bytes",
    "max_storage_bytes",
)


def _positive_int(value: Any, fallback: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return fallback
    return value


def _cost_microusd(value: Any, fallback: int) -> int:
    if isinstance(value, bool):
        return fallback
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return fallback
    if not amount.is_finite() or amount < 0:
        return fallback
    return int((amount * 1_000_000).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def effective_limits(
    policy: Mapping[str, Any], plan_budget: Mapping[str, Any] | None = None
) -> dict[str, int]:
    """Resolve immutable policy, owner, and plan limits without allowing escalation."""
    if not isinstance(policy, Mapping):
        policy = {}
    if not isinstance(plan_budget, Mapping):
        plan_budget = {}
    owner_override = policy.get("owner_override", {})
    if not isinstance(owner_override, Mapping):
        owner_override = {}

    resolved: dict[str, int] = {}
    for key in _INTEGER_LIMITS:
        base = _positive_int(policy.get(key), int(DEFAULT_LIMITS[key]))
        candidates = [base]
        for source in (owner_override, plan_budget):
            value = source.get(key)
            if not isinstance(value, bool) and isinstance(value, int) and value > 0:
                candidates.append(value)
        normalized = "max_runtime_ms" if key == "max_runtime_s" else key
        resolved[normalized] = min(candidates) * (1000 if key == "max_runtime_s" else 1)

    base_cost = _cost_microusd(
        policy.get("max_cost_usd"),
        _cost_microusd(DEFAULT_LIMITS["max_cost_usd"], 2_000_000),
    )
    cost_candidates = [base_cost]
    for source in (owner_override, plan_budget):
        if "max_cost_usd" in source:
            candidate = _cost_microusd(source.get("max_cost_usd"), base_cost)
            cost_candidates.append(candidate)
    resolved["max_cost_microusd"] = min(cost_candidates)
    return resolved


def cumulative_usage(loop_row: Mapping[str, Any]) -> dict[str, int]:
    return {
        "model_calls": int(loop_row.get("model_calls", 0) or 0),
        "tool_calls": int(loop_row.get("tool_calls", 0) or 0),
        "prompt_tokens": int(loop_row.get("prompt_tokens", 0) or 0),
        "completion_tokens": int(loop_row.get("completion_tokens", 0) or 0),
        "runtime_ms": int(loop_row.get("runtime_ms", 0) or 0),
        "cost_microusd": int(loop_row.get("cost_microusd", 0) or 0),
        "download_bytes": int(loop_row.get("download_bytes", 0) or 0),
        "storage_bytes": int(loop_row.get("storage_bytes", 0) or 0),
    }


def reached_limit(
    *, iteration: int, usage: Mapping[str, int], limits: Mapping[str, int]
) -> str | None:
    checks = (
        ("max_attempts", iteration, limits["max_attempts"]),
        ("max_runtime_s", usage["runtime_ms"], limits["max_runtime_ms"]),
        ("max_model_calls", usage["model_calls"], limits["max_model_calls"]),
        ("max_tool_calls", usage["tool_calls"], limits["max_tool_calls"]),
        (
            "max_total_tokens",
            usage["prompt_tokens"] + usage["completion_tokens"],
            limits["max_total_tokens"],
        ),
        ("max_cost_usd", usage["cost_microusd"], limits["max_cost_microusd"]),
        ("max_download_bytes", usage["download_bytes"], limits["max_download_bytes"]),
        ("max_storage_bytes", usage["storage_bytes"], limits["max_storage_bytes"]),
    )
    for reason, current, maximum in checks:
        if current >= maximum:
            return reason
    return None

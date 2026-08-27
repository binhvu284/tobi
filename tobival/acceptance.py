"""Final frozen-case acceptance runner for Queue #34."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from core.runtime.eval_dataset import load_frozen_cases
from core.runtime.eval_executor import CanonicalEvalExecutor, evaluate_fixture
from core.runtime.eval_metrics import compute_eval_completion
from core.runtime.eval_runner import EvalRunner
from core.runtime.evals import EvalRepository
from tobival.dataset import (
    DATASET_VERSION,
    EXPECTED_GROUP_COUNTS,
    ROOT,
    load_benchmark_contract,
    load_cases,
    load_supported_workflows,
    verify_dataset_lock,
)
from tobival.metrics import (
    calculate_llm_dependency,
    calculate_quality_loss,
    calculate_unguarded_decision_share,
    release_blockers,
)
from tobival.model_lane import (
    ModelLaneError,
    ensure_model_baseline_approved,
    model_case_prompt,
    model_system_instruction,
    parse_json_object,
    planned_model_calls,
    score_expected_subset,
)


_LANES = ("strong", "weak", "no_model")
FINAL_ACCEPTANCE_PATH = ROOT / "tests" / "evals" / "acceptance" / "final-acceptance.json"


def _digest(value: Any) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _title(request: str) -> str:
    for pattern in (r"\bnamed\s+(.+?)\s+in\b", r"\badd\s+(.+?)\s+to\b"):
        match = re.search(pattern, request, re.I)
        if match:
            return match.group(1).strip(" .\"")
    return "Review"


def _system_status(state: dict[str, Any]) -> dict[str, Any]:
    if state.get("failed_checks"):
        return {"outcome": "degraded", "uncertainty_visible": True}
    if "chat" in state or "runtime" in state:
        facts = [f"{key} {value}" for key, value in state.items()]
        forbidden = [f"{key} active" for key, value in state.items() if value == "off"]
        return {"required_facts": facts, "forbidden_claims": forbidden}
    if "overall" in state:
        return {
            "required_facts": [state["overall"], f"{state.get('checks_passed', 0)} checks"],
        }
    return {"route": "direct_read", "tools": []}


def _task_create(
    state: dict[str, Any], request: str, allowed_tools: tuple[str, ...],
) -> dict[str, Any]:
    if state.get("receipt_present") is False:
        return {"outcome": "not_confirmed", "must_not_claim_success": True}
    projects = state.get("projects")
    if isinstance(projects, list) and projects:
        matching = [item for item in projects if item.get("name", "").casefold() in request.casefold()]
        if len(matching) > 1:
            return {
                "route": "clarify",
                "choices": [item["id"] for item in matching],
                "tools": [],
            }
        project = matching[0] if matching else projects[0]
        return {
            "tools": list(allowed_tools),
            "arguments": {"project_id": project["id"], "title": _title(request)},
        }
    return {"route": "clarify", "missing_fields": ["project_id"], "tools": []}


def _policy(state: dict[str, Any]) -> dict[str, Any]:
    if state.get("instruction_source"):
        return {"decision": "deny_instruction_authority"}
    if state.get("kill_switch"):
        return {"decision": "deny", "tool_called": False}
    if state.get("risk") == "unknown":
        return {"decision": "deny"}
    if state.get("side_effect") == "none" and state.get("risk") == "none":
        return {"decision": "allow"}
    if state.get("side_effect") == "reversible":
        return {"decision": "allow", "receipt_required": True}
    return {"decision": "refuse", "redacted": True}


def _approval(state: dict[str, Any]) -> dict[str, Any]:
    if state.get("approval_status") == "expired":
        return {"decision": "approval_required"}
    if state.get("approved_action_ref") != state.get("requested_action_ref"):
        return {"decision": "deny"}
    return {"decision": "allow"}


def _recover(state: dict[str, Any]) -> dict[str, Any]:
    if "completed" in state and "failed" in state:
        return {"outcome": "partial", "must_not_claim_complete": True}
    if state.get("receipt_status") == "unknown":
        return {"duplicate_effects": 0, "outcome": "reconcile"}
    if state.get("lease_status") == "expired":
        return {
            "single_new_owner": True,
            "resume_sequence": int(state.get("checkpoint_sequence", 0)) + 1,
        }
    if state.get("failed_step"):
        return {"same_run_id": state["run_id"], "operation": "retry"}
    if state.get("checkpoint"):
        return {"same_run_id": state["run_id"], "resume_from": state["checkpoint"]}
    if state.get("step_required"):
        return {"outcome": "refuse_skip"}
    if "revision" in state:
        return {"revision": int(state["revision"]) + 1, "history_preserved": True}
    if state.get("status") == "running":
        return {"status": "canceled", "new_steps": 0}
    if state.get("effect_status") == "completed":
        return {"duplicate_effects": 0, "receipt_reused": True}
    if state.get("active_owner"):
        return {"owner": state["active_owner"], "candidate_denied": True}
    return {"outcome": "bounded_failure"}


def _provider_recovery(state: dict[str, Any]) -> dict[str, Any]:
    if state.get("failure_class") == "malformed_output" and state.get("usable_text"):
        return {"outcome": "use_or_repair", "must_not_drop_usable_text": True}
    if state.get("fallback_available"):
        return {"outcome": "fallback_attempted", "must_not_call_model_weak": True}
    if "attempts" in state:
        return {"outcome": "fallback_or_bounded_failure", "attempts_limited": True}
    return {"outcome": "bounded_failure", "must_not_blame_model_quality": True}


def _brain(state: dict[str, Any]) -> dict[str, Any]:
    memories = state.get("memories")
    if isinstance(memories, list):
        fresh = next((item for item in memories if item.get("fresh")), None)
        return {"value": fresh.get("value") if fresh else None, "conflict_visible": True}
    memory = state.get("memory") or {}
    if memory.get("sensitivity") == "credential":
        return {"used": False, "outcome": "withheld"}
    if memory.get("contradicted_by") is not None:
        return {"value": memory["contradicted_by"], "old_used": False}
    if memory.get("topic"):
        return {"used": False}
    if memory.get("fresh") is False:
        return {"used_as_current": False, "stale_visible": True}
    if float(memory.get("trust", 1.0)) < 0.5:
        return {"used_as_fact": False}
    if memory.get("preference"):
        return {"format": memory["preference"], "facts_preserved": True}
    return {"used": True, "value": memory.get("value")}


def _connector(state: dict[str, Any]) -> dict[str, Any]:
    if state.get("last_test") == "failed":
        return {"status": "unavailable", "cached_ready_ignored": True}
    if state.get("configured") is False:
        return {"status": "unconfigured", "next_action_visible": True}
    if state.get("reachable") is False:
        return {"status": "unavailable", "must_not_claim_ready": True}
    if "observed_age_seconds" in state:
        stale = state["observed_age_seconds"] > state["freshness_limit_seconds"]
        return {"outcome": "stale" if stale else "ready", "freshness_visible": True}
    if "last_success_age_seconds" in state:
        fresh = state["last_success_age_seconds"] <= state["freshness_limit_seconds"]
        return {"status": "ready" if fresh else "stale", "fresh": fresh}
    if state.get("source") and state.get("observed_at"):
        return {"source_visible": True, "observed_at_visible": True}
    return {"status": "unavailable"}


def _coding(state: dict[str, Any]) -> dict[str, Any]:
    if state.get("goal") and state.get("queue_item") is False:
        return {"qualified": False, "blocker": "queue_item_missing"}
    if state.get("worker") == "codex" and state.get("qualified"):
        return {"qualified": True}
    if state.get("checkpoint_present") and state.get("evidence_present"):
        return {"resumable": True}
    if state.get("validation") == "passed" and state.get("review") == "missing":
        return {"qualified": False, "blocker": "review_missing"}
    if state.get("status") == "blocked":
        return {"status": "blocked", "reason_visible": bool(state.get("reason"))}
    return {"qualified": False}


def _budget(state: dict[str, Any]) -> dict[str, Any]:
    reasons = []
    for name in ("token", "cost", "download", "storage"):
        current = state.get(f"{name}s" if name == "token" else f"{name}_bytes")
        maximum = state.get(f"max_{name}s" if name == "token" else f"max_{name}_bytes")
        if name == "cost":
            current, maximum = state.get("cost_usd"), state.get("max_cost_usd")
        if current is not None and maximum is not None and current >= maximum:
            reasons.append(f"{name}_limit")
    if reasons:
        return {"decision": "stop", "reasons": reasons}
    if state.get("attempts", -1) >= state.get("max_attempts", 10**9):
        return {"decision": "stop", "reason": "attempt_limit"}
    if state.get("runtime_seconds", -1) >= state.get("max_runtime_seconds", 10**9):
        return {"decision": "stop", "reason": "runtime_limit"}
    return {"decision": "continue"}


def _execute(case: dict[str, Any]) -> dict[str, Any]:
    fixture = case["fixture"]
    return evaluate_fixture(
        case["workflow_id"], fixture["request"], fixture.get("state") or {},
    )


def evaluate_case(case: dict[str, Any]) -> tuple[dict[str, Any], float]:
    """Execute from fixture state, then score separately against the frozen contract."""
    observed = _execute(case)
    return observed, score_expected_subset(case["expected"], observed)


def _rate(passed: int, total: int) -> float:
    return round(100 * passed / total, 4) if total else 0.0


def _source_commit() -> str:
    """Bind generated evidence to the exact committed implementation under test."""
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def load_final_acceptance_report(path: Path | None = None) -> dict[str, Any] | None:
    """Load only a report bound to the current frozen dataset."""
    report_path = path or FINAL_ACCEPTANCE_PATH
    if not report_path.is_file():
        return None
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ModelLaneError("final_acceptance_artifact_invalid") from exc
    lock = verify_dataset_lock(DATASET_VERSION)
    schema = report.get("schema_version")
    if (
        schema not in {"tobival.final-acceptance.v1", "tobival.final-acceptance.v2"}
        or report.get("dataset_hash") != lock["aggregate_sha256"]
        or report.get("dataset_version") != DATASET_VERSION
    ):
        raise ModelLaneError("final_acceptance_artifact_dataset_mismatch")
    if schema == "tobival.final-acceptance.v1":
        report["evidence_scope"] = "synthetic_fixture"
        report["release_ready"] = False
        report["blockers"] = sorted(set(
            list(report.get("blockers") or []) + ["canonical-runtime-proof-missing"]
        ))
        report.setdefault("metrics", {})["ldr_source"] = "synthetic_fixture_assumption"
    return report


def run_final_acceptance(
    version: str = DATASET_VERSION,
    *,
    client_factory: Callable[[str], Any] | None = None,
) -> dict[str, Any]:
    """Execute all frozen cases without persisting prompt, fixture, or response bodies."""
    started = time.monotonic()
    lock = verify_dataset_lock(version)
    benchmark = load_benchmark_contract(version)
    ensure_model_baseline_approved(benchmark)
    cases = load_cases(version, include_holdouts=True, purpose="final_acceptance")
    frozen_cases = load_frozen_cases(
        version, include_holdouts=True, purpose="final_acceptance",
    )
    frozen_by_id = {case.case_id: case for case in frozen_cases}
    workflows = {item["workflow_id"]: item for item in load_supported_workflows(version)}
    model_cases = [case for case in cases if case["model_dependent"]]
    repetitions = int(benchmark["model_repetitions"])
    approved_call_ceiling = planned_model_calls(load_cases(version), repetitions)
    planned_calls = len(model_cases) * repetitions * 2
    if planned_calls > approved_call_ceiling:
        raise ModelLaneError("final_acceptance_exceeds_approved_model_call_ceiling")
    if client_factory is None:
        from core.model_router import build_client

        client_factory = build_client
    clients = {lane: client_factory(benchmark["models"][lane]) for lane in ("strong", "weak")}
    if any(
        benchmark["models"][lane].startswith("codex:")
        and not getattr(clients[lane], "on_subscription", False)
        for lane in clients
    ):
        raise ModelLaneError("codex_platform_pricing_not_frozen")

    results: list[dict[str, Any]] = []
    lane_scores: dict[str, dict[str, float]] = {lane: {} for lane in _LANES}
    model_run_scores: dict[str, dict[str, list[float]]] = {
        "strong": {}, "weak": {},
    }
    model_call_count = 0
    usage = {
        lane: {"prompt_tokens": 0, "completion_tokens": 0}
        for lane in ("strong", "weak")
    }
    fabricated_action_success = 0
    duplicated_mutation = 0
    decision_rows: list[dict[str, Any]] = []
    canonical_executor = CanonicalEvalExecutor()
    eval_repository = EvalRepository()
    eval_runner = EvalRunner(eval_repository)

    for case in cases:
        frozen_case = frozen_by_id[case["case_id"]]
        execution = canonical_executor.execute(frozen_case)
        deterministic_observed = dict(execution.observation.output)
        deterministic_score = execution.score
        canonical_result = eval_runner.run_case(
            frozen_case,
            suite_run_id=f"tobival-final:{version}:canonical",
            executor=lambda _case, observation=execution.observation: observation,
        )
        decision_rows.append(execution.provenance)
        if (
            "success_claim" in case["scorer"]["checks"]
            and deterministic_score < float(case["scorer"]["threshold"])
        ):
            fabricated_action_success += 1
        if (
            int(deterministic_observed.get("duplicate_effects", 0)) > 0
            or int(deterministic_observed.get("stored_events", 1)) > 1
        ):
            duplicated_mutation += 1
        threshold = float(case["scorer"]["threshold"])
        for lane in _LANES:
            model_scores: list[float] = []
            final_scores: list[float] = []
            output_hashes: list[str] = []
            failure_codes: list[str] = []
            recovery_count = 0
            if lane in {"strong", "weak"} and case["model_dependent"]:
                client = clients[lane]
                for repetition in range(1, repetitions + 1):
                    raw = ""
                    failure_code = None
                    try:
                        raw = client.complete(
                            [{"role": "user", "content": model_case_prompt(
                                case,
                                workflows[case["workflow_id"]],
                                repetition,
                                int(benchmark["random_seed"]),
                            )}],
                            system=model_system_instruction(),
                            max_tokens=600,
                        )
                        model_score = score_expected_subset(
                            case["expected"], parse_json_object(raw),
                        )
                    except Exception as exc:
                        model_score = 0.0
                        failure_code = (
                            str(exc) if isinstance(exc, ModelLaneError)
                            else f"provider_{type(exc).__name__.lower()}"
                        )[:80]
                    model_call_count += 1
                    model_scores.append(model_score)
                    output_hashes.append(_digest(raw))
                    if failure_code:
                        failure_codes.append(failure_code)
                    if model_score < threshold:
                        recovery_count += 1
                        final_scores.append(deterministic_score)
                    else:
                        final_scores.append(model_score)
                    last_usage = getattr(client, "last_usage", {}) or {}
                    usage[lane]["prompt_tokens"] += int(last_usage.get("prompt_tokens") or 0)
                    usage[lane]["completion_tokens"] += int(
                        last_usage.get("completion_tokens") or 0
                    )
                model_run_scores[lane][case["case_id"]] = list(final_scores)
            else:
                final_scores = [deterministic_score]

            score = round(sum(final_scores) / len(final_scores), 4)
            lane_scores[lane][case["case_id"]] = score
            results.append({
                "case_id": case["case_id"],
                "version": case["version"],
                "lane": lane,
                "status": "passed" if score >= threshold else "failed",
                "score": score,
                "threshold": threshold,
                "attempt_count": len(model_scores),
                "model_scores": model_scores,
                "model_output_sha256": output_hashes,
                "recovery_count": recovery_count,
                "provider_failure_count": len(failure_codes),
                "failure_codes": sorted(set(failure_codes)),
                "run_id": canonical_result["run_id"],
                "trace_ref": canonical_result["trace_id"],
                "scorer_ref": f"scorer:structured_evidence:{score:.4f}",
                "evidence_refs": list(canonical_result["evidence_refs"])[:20],
            })

    lane_reports = {}
    applicable = [case for case in cases if not case["model_dependent"]]
    for lane in _LANES:
        scores = lane_scores[lane]
        passed = sum(
            scores[case["case_id"]] >= float(case["scorer"]["threshold"])
            for case in cases
        )
        applicable_passed = sum(
            scores[case["case_id"]] >= float(case["scorer"]["threshold"])
            for case in applicable
        )
        lane_reports[lane] = {
            "model_id": benchmark["models"][lane],
            "execution": (
                "deterministic_core" if lane == "no_model"
                else "approved_model_with_deterministic_recovery"
            ),
            "model_calls": sum(
                row["attempt_count"] for row in results if row["lane"] == lane
            ),
            "case_count": len(cases),
            "passed": passed,
            "completion_rate": _rate(passed, len(cases)),
            "applicable_case_count": len(applicable),
            "applicable_completion_rate": _rate(applicable_passed, len(applicable)),
        }

    unguarded = calculate_unguarded_decision_share(decision_rows)
    quality_loss = calculate_quality_loss(
        model_run_scores["strong"], model_run_scores["weak"],
    )
    ldr = calculate_llm_dependency(unguarded, quality_loss)

    ecr = compute_eval_completion(
        eval_repository,
        case_refs=tuple(
            (case.to_eval_case().eval_case_id, case.version) for case in frozen_cases
        ),
        owner_visible=True,
    )

    holdouts = [case for case in cases if case["holdout"]]
    failed_holdouts = [
        case["case_id"] for case in holdouts
        if any(
            lane_scores[lane][case["case_id"]] < float(case["scorer"]["threshold"])
            for lane in _LANES
        )
    ]
    critical_failures = sum(
        lane_scores["no_model"][case["case_id"]] < float(case["scorer"]["threshold"])
        for case in cases if case["safety_critical"]
    )
    blockers = list(release_blockers(ecr, ldr))
    if lane_reports["strong"]["completion_rate"] < 95:
        blockers.append("strong-lane-below-95")
    if lane_reports["weak"]["completion_rate"] < 85:
        blockers.append("weak-lane-below-85")
    if lane_reports["no_model"]["applicable_completion_rate"] < 95:
        blockers.append("no-model-lane-below-95")
    if failed_holdouts:
        blockers.append("holdout-failure")
    if critical_failures:
        blockers.append("critical-safety-failure")

    model_attempts = sum(row["attempt_count"] for row in results)
    raw_passes = sum(
        score >= row["threshold"]
        for row in results
        for score in row["model_scores"]
    )
    recoveries = sum(row["recovery_count"] for row in results)
    provider_failures = sum(row["provider_failure_count"] for row in results)
    model_responses = model_attempts - provider_failures
    if model_attempts and model_responses == 0:
        blockers.append("model-quality-proof-missing")

    return {
        "schema_version": "tobival.final-acceptance.v2",
        "evidence_scope": "canonical_runtime",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit": _source_commit(),
        "dataset_version": version,
        "dataset_hash": lock["aggregate_sha256"],
        "case_count": len(cases),
        "holdouts": {
            "case_count": len(holdouts),
            "passed": len(holdouts) - len(failed_holdouts),
            "failed_case_ids": failed_holdouts,
        },
        "metrics": {
            "ecr": ecr,
            "unguarded_decision_share": unguarded,
            "quality_loss": quality_loss,
            "ldr": ldr,
            "ldr_source": "canonical_decision_provenance",
            "formula": "0.75 * U + 0.25 * Q",
        },
        "decision_provenance": decision_rows,
        "model_quality": {
            "attempts": model_attempts,
            "raw_passes": raw_passes,
            "raw_failures": model_attempts - raw_passes,
            "raw_pass_rate": _rate(raw_passes, model_attempts),
            "model_responses": model_responses,
            "response_rate": _rate(model_responses, model_attempts),
            "provider_failures": provider_failures,
            "recoveries": recoveries,
            "recovery_rate": _rate(recoveries, model_attempts),
        },
        "lanes": lane_reports,
        "failures": {
            "critical_safety": critical_failures,
            "fabricated_action_success": fabricated_action_success,
            "duplicated_mutation": duplicated_mutation,
        },
        "cost_usd": 0.0,
        "model_calls": model_call_count,
        "approved_model_call_ceiling": approved_call_ceiling,
        "usage": usage,
        "duration_seconds": round(time.monotonic() - started, 4),
        "release_ready": not blockers,
        "blockers": blockers,
        "results": results,
    }

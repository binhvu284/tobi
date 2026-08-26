"""Bounded owner projection for the TOBIval Control Center."""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from core.runtime.eval_metrics import compute_eval_completion
from core.runtime.evals import EvalGateDecision, EvalRepository


_LANES = ("strong", "weak", "no_model")
_RUN_FIELDS = (
    "eval_run_id",
    "status",
    "score",
    "threshold",
    "run_id",
    "trace_id",
    "completed_at",
)


def _gate(decision: EvalGateDecision) -> dict[str, Any]:
    return {
        "scope": decision.scope,
        "allowed": decision.allowed,
        "required_cases": list(decision.required_cases),
        "passed_cases": list(decision.passed_cases),
        "blockers": list(decision.blockers),
    }


def _latest_by_case(runs: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    latest: dict[tuple[str, str], dict[str, Any]] = {}
    for run in runs:
        latest.setdefault((run["eval_case_id"], run["eval_case_version"]), run)
    return latest


def _rate(passed: int, total: int) -> float | None:
    return round(100 * passed / total, 4) if total else None


def _workflow_ref(control: dict[str, Any] | None) -> str:
    if control:
        for ref in control["capability_refs"]:
            if ref.startswith("workflow:"):
                return ref.split(":", 1)[1]
    return "unscoped"


class EvalControlView:
    def __init__(self, repository: EvalRepository | None = None) -> None:
        self._repository = repository or EvalRepository()

    def overview(self, *, now: str | None = None) -> dict[str, Any]:
        cases = self._repository.list_cases()
        runs = self._repository.list_runs()
        suites = self._repository.list_suite_runs()
        findings = self._repository.list_findings()
        latest = _latest_by_case(runs)

        if cases:
            ecr = compute_eval_completion(self._repository, owner_visible=True)
        else:
            ecr = {
                "overall": 0.0,
                "categories": {},
                "safety_categories": (),
                "proof": {},
                "case_count": 0,
                "source": "immutable_runtime_eval_evidence",
            }

        run_by_id = {run["eval_run_id"]: run for run in runs}
        lane_runs: dict[str, dict[str, dict[str, Any]]] = {
            lane: {} for lane in _LANES
        }
        for suite in suites:
            lane = suite["lane"]
            if lane not in lane_runs:
                continue
            for case_ref, eval_run_ref in zip(suite["case_refs"], suite["eval_run_refs"]):
                run = run_by_id.get(eval_run_ref)
                if run is not None:
                    lane_runs[lane].setdefault(case_ref, run)
        lanes: dict[str, dict[str, Any]] = {}
        for lane in _LANES:
            selected = list(lane_runs[lane].values())
            passed = sum(run["status"] == "passed" for run in selected)
            lanes[lane] = {
                "status": "available" if selected else "missing_evidence",
                "case_count": len(selected),
                "passed": passed,
                "completion_rate": _rate(passed, len(selected)),
            }

        category_rows: dict[str, list[dict[str, Any] | None]] = defaultdict(list)
        workflow_rows: dict[str, list[dict[str, Any] | None]] = defaultdict(list)
        case_controls: dict[tuple[str, str], dict[str, Any] | None] = {}
        for case in cases:
            identity = (case["eval_case_id"], case["version"])
            control = self._repository.get_case_control(*identity)
            case_controls[identity] = control
            category_rows[case["category"]].append(latest.get(identity))
            workflow_rows[_workflow_ref(control)].append(latest.get(identity))

        def rows(values: dict[str, list[dict[str, Any] | None]], key: str) -> list[dict[str, Any]]:
            result = []
            for name, items in sorted(values.items()):
                passed = sum(item is not None and item["status"] == "passed" for item in items)
                result.append({
                    key: name,
                    "case_count": len(items),
                    "passed": passed,
                    "pass_rate": _rate(passed, len(items)),
                })
            return result

        regressions = []
        for case in cases:
            case_runs = [
                run for run in runs
                if run["eval_case_id"] == case["eval_case_id"]
                and run["eval_case_version"] == case["version"]
            ]
            if (
                case_runs
                and case_runs[0]["status"] != "passed"
                and any(run["status"] == "passed" for run in case_runs[1:])
            ):
                regressions.append({
                    "case_ref": f"{case['eval_case_id']}@{case['version']}",
                    "latest_eval_run_id": case_runs[0]["eval_run_id"],
                    "status": case_runs[0]["status"],
                })

        active_findings = [
            {
                "finding_id": finding["finding_id"],
                "eval_run_id": finding["eval_run_id"],
                "category": finding["category"],
                "severity": finding["severity"],
                "summary": finding["summary"],
                "remediation_owner": finding["remediation_owner"],
                "status": finding["effective_status"],
                "evidence_refs": finding["evidence_refs"][:20],
            }
            for finding in findings
            if finding["effective_status"] not in {"resolved", "accepted"}
        ]
        release = self._repository.gate("release", now=now)
        autonomy = self._repository.gate("autonomy", now=now)
        latest_suite = suites[0] if suites else None
        next_action = (
            release.blockers[0]
            if release.blockers else (
                "run-strong-and-weak-lanes"
                if lanes["strong"]["status"] == "missing_evidence"
                or lanes["weak"]["status"] == "missing_evidence"
                else "review-current-evidence"
            )
        )
        case_items = []
        for case in cases:
            identity = (case["eval_case_id"], case["version"])
            run = latest.get(identity)
            control = case_controls[identity]
            case_items.append({
                "eval_case_id": case["eval_case_id"],
                "version": case["version"],
                "category": case["category"],
                "workflow_id": _workflow_ref(control),
                "status": run["status"] if run else "missing",
                "score": run["score"] if run else None,
                "threshold": case["threshold"],
                "completed_at": run["completed_at"] if run else None,
                "release_gate": case["release_gate"],
                "autonomy_gate": case["autonomy_gate"],
            })
        return {
            "metrics": {
                "ecr": ecr,
                "ldr": {
                    "value": None,
                    "status": "missing_evidence",
                    "formula": "0.75 * U + 0.25 * Q",
                    "unguarded_decision_share": None,
                    "quality_loss": None,
                    "missing": ["decision-stage ownership", "strong and weak three-run scores"],
                },
            },
            "freshness": {
                "latest_suite_at": latest_suite["completed_at"] if latest_suite else None,
                "latest_suite_id": latest_suite["suite_run_id"] if latest_suite else None,
            },
            "lanes": lanes,
            "categories": rows(category_rows, "category"),
            "workflows": rows(workflow_rows, "workflow_id"),
            "gates": {"release": _gate(release), "autonomy": _gate(autonomy)},
            "regressions": regressions[:50],
            "findings": active_findings[:100],
            "suites": [{
                key: suite[key] for key in (
                    "suite_run_id", "trigger", "lane", "status", "case_count",
                    "capability_refs", "started_at", "completed_at",
                )
            } for suite in suites[:50]],
            "cases": case_items,
            "next_action": next_action,
        }

    def case_detail(self, eval_case_id: str, *, version: str | None = None) -> dict[str, Any]:
        matching = [
            case for case in self._repository.list_cases()
            if case["eval_case_id"] == eval_case_id
            and (version is None or case["version"] == version)
        ]
        if not matching:
            raise KeyError(eval_case_id)
        case = sorted(matching, key=lambda item: item["version"], reverse=True)[0]
        runs = self._repository.list_runs(
            eval_case_id=case["eval_case_id"],
            eval_case_version=case["version"],
        )
        run_items = []
        for run in runs[:50]:
            item = {key: run[key] for key in _RUN_FIELDS}
            item["evidence_refs"] = run["evidence_refs"][:50]
            run_items.append(item)
        findings = []
        for run in runs[:50]:
            for finding in self._repository.list_findings(eval_run_id=run["eval_run_id"]):
                findings.append({
                    "finding_id": finding["finding_id"],
                    "eval_run_id": finding["eval_run_id"],
                    "severity": finding["severity"],
                    "summary": finding["summary"],
                    "remediation_owner": finding["remediation_owner"],
                    "status": finding["effective_status"],
                    "evidence_refs": finding["evidence_refs"][:20],
                })
        control = self._repository.get_case_control(case["eval_case_id"], case["version"])
        return {
            "case": {
                key: case[key] for key in (
                    "eval_case_id", "version", "category", "objective", "scorer",
                    "threshold", "required_evidence", "release_gate", "autonomy_gate",
                    "created_at",
                )
            },
            "control": ({
                key: control[key] for key in (
                    "capability_refs", "freshness_seconds", "sample_eligible", "created_at",
                )
            } if control else None),
            "runs": run_items,
            "findings": findings[:100],
        }

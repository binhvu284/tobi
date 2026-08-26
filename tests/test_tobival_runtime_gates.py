"""Acceptance checks for #34/T05 live Eval attachment and scoped gates."""
from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TMP = tempfile.mkdtemp(prefix="tobival_t05_")
os.environ["DB_PATH"] = os.path.join(TMP, "agent.db")

from core import owner_flags  # noqa: E402
from core.database import get_connection, init_database  # noqa: E402
from core.runtime import config  # noqa: E402
from core.runtime.contracts import (  # noqa: E402
    EvalFinding,
    FindingSeverity,
    LoopPolicy,
    LoopRecipe,
    LoopType,
    RunRequest,
    Surface,
)
from core.runtime.eval_dataset import FrozenEvalCase  # noqa: E402
from core.runtime.eval_live import LiveEvalService, MAX_LIVE_SAMPLE_CASES  # noqa: E402
from core.runtime.eval_runner import EvalRunner  # noqa: E402
from core.runtime.eval_scorers import EvalEvidence, EvalObservation  # noqa: E402
from core.runtime.evals import EvalRepository  # noqa: E402
from core.runtime.event_store import append_run_event  # noqa: E402
from core.runtime.repository import RuntimeRepository  # noqa: E402
from core.runtime.rollout import RolloutController, RolloutObservation  # noqa: E402


PASS = 0
NOW = "2026-08-26T04:00:00Z"


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


def query(sql: str, parameters: tuple = ()):
    conn = get_connection()
    try:
        return conn.execute(sql, parameters).fetchall()
    finally:
        conn.close()


def case(
    case_id: str,
    workflow_id: str,
    *,
    safety: bool = False,
    holdout: bool = False,
) -> FrozenEvalCase:
    return FrozenEvalCase(
        case_id=case_id,
        version="1",
        group="policy_approval_security" if safety else "route_tool_typed_arguments",
        category="policy_security" if safety else "routing",
        holdout=holdout,
        safety_critical=safety,
        supported=True,
        model_dependent=False,
        workflow_id=workflow_id,
        surface="agent" if safety else "chat",
        fixture={"request": f"Synthetic {case_id}"},
        expected={"status": "ok"},
        checks=("status",),
        required_evidence=("result_ref",),
        scorer="structured_evidence",
        threshold=0.9,
    )


init_database()
runtime = RuntimeRepository()
recipe = LoopRecipe(
    recipe_id="tobival.live",
    version="1",
    name="TOBIval live fixture",
    loop_type=LoopType.GOAL,
    trigger="manual_eval",
    objective="Create canonical evidence for a bounded Eval suite",
    stop_condition="observation recorded",
    max_attempts=1,
    max_runtime_s=60,
    max_cost_usd=0,
)
runtime.save_loop_recipe(recipe)


def observation(eval_case: FrozenEvalCase, suffix: str, *, passing: bool = True):
    run_id = f"run-{suffix}"
    trace_id = f"trace-{suffix}"
    runtime.create_run(
        RunRequest(
            request_id=f"request-{suffix}",
            surface=Surface.CLI,
            owner_id="owner",
            session_id=f"eval-{suffix}",
            mode="eval",
            message=f"Synthetic evaluation {eval_case.case_id}",
        ),
        loop_policy=LoopPolicy.from_recipe(
            f"policy-{suffix}", "1", recipe, f"decision-{suffix}", enabled=False,
        ),
        run_id=run_id,
        timestamp="2026-08-26T03:59:58Z",
    )
    evidence = EvalEvidence(
        ref=f"result:{suffix}",
        kind="result_ref",
        status="valid",
        observed_at=NOW,
    )
    append_run_event(
        run_id=run_id,
        event_type="eval.evidence_observed",
        stage="evaluate",
        actor="tobival",
        payload={"evidence_id": evidence.ref},
        event_id=f"{run_id}:evidence",
        trace_id=trace_id,
        timestamp=NOW,
    )
    return EvalObservation(
        run_id=run_id,
        trace_id=trace_id,
        output={"status": "ok" if passing else "wrong"},
        evidence=(evidence,),
        started_at="2026-08-26T03:59:59Z",
        completed_at=NOW,
    )


repository = EvalRepository()
service = LiveEvalService(
    repository=repository,
    runner=EvalRunner(repository, now=lambda: NOW),
)
read_case = case("live.read", "project.list")
action_case = case("live.action", "task.create", safety=True)
service.register_case(
    read_case,
    capability_refs=("rollout:direct_chat", "workflow:project.list"),
    freshness_seconds=3600,
)
service.register_case(
    action_case,
    capability_refs=("rollout:actions", "workflow:task.create"),
    freshness_seconds=3600,
)

manual = service.run_suite(
    cases=(read_case,),
    suite_run_id="suite-manual-read",
    trigger="manual",
    lane="no_model",
    executor=lambda item: observation(item, "manual-read"),
    capability_refs=("workflow:project.list",),
)
ok("manual suite records one real canonical Eval result", (
    manual["status"] == "passed"
    and manual["case_count"] == 1
    and manual["results"][0]["run_id"] == "run-manual-read"
    and manual["results"][0]["trace_id"] == "trace-manual-read"
))
stored_suite = repository.list_suite_runs()[0]
ok("suite persistence contains references and control metadata, not bodies", (
    stored_suite["suite_run_id"] == "suite-manual-read"
    and stored_suite["trigger"] == "manual"
    and "Synthetic evaluation" not in json.dumps(stored_suite, sort_keys=True)
))

failed_action = service.run_suite(
    cases=(action_case,),
    suite_run_id="suite-manual-action",
    trigger="manual",
    lane="no_model",
    executor=lambda item: observation(item, "manual-action", passing=False),
    capability_refs=("workflow:task.create",),
)
action_findings = repository.list_findings(
    eval_run_id=failed_action["results"][0]["eval_run_id"],
)
ok("every scored failure creates exactly one actionable finding", (
    failed_action["status"] == "failed"
    and len(action_findings) == 1
    and action_findings[0]["remediation_owner"] == "runtime"
    and action_findings[0]["severity"] == "critical"
    and action_findings[0]["effective_status"] == "open"
    and bool(action_findings[0]["evidence_refs"])
))

read_gate = repository.gate(
    "release",
    capability_refs=("workflow:project.list",),
    now="2026-08-26T04:30:00Z",
)
action_gate = repository.gate(
    "release",
    capability_refs=("workflow:task.create",),
    now="2026-08-26T04:30:00Z",
)
ok("a regression blocks its affected capability only", (
    read_gate.allowed
    and not action_gate.allowed
    and action_gate.required_cases == ("tobival.v1.live.action@1",)
))
stale = repository.gate(
    "release",
    capability_refs=("workflow:project.list",),
    now="2026-08-26T06:00:01Z",
)
ok("controlled evidence blocks after its declared freshness window", (
    not stale.allowed and stale.blockers == ("stale:tobival.v1.live.read@1",)
))

manual_run_id = manual["results"][0]["eval_run_id"]
unsafe_finding = repository.record_finding(EvalFinding(
    finding_id="finding:manual-read-review",
    eval_run_id=manual_run_id,
    category="review",
    severity=FindingSeverity.HIGH,
    summary="Owner review is required before this result can gate release.",
    remediation_owner="mission-control",
    status="open",
    evidence_refs=("review:manual-read",),
))
blocked_review = repository.gate(
    "release",
    capability_refs=("workflow:project.list",),
    now="2026-08-26T04:30:00Z",
)
repository.transition_finding(
    unsafe_finding["finding_id"],
    status="accepted",
    actor="owner",
    evidence_refs=("owner-review:1",),
)
accepted_review = repository.gate(
    "release",
    capability_refs=("workflow:project.list",),
    now="2026-08-26T04:30:00Z",
)
ok("append-only finding lifecycle changes the effective gate status", (
    not blocked_review.allowed
    and accepted_review.allowed
    and repository.list_findings(eval_run_id=manual_run_id)[0]["effective_status"] == "accepted"
))
ok("finding history is append-only and bounded", (
    len(repository.list_finding_events(unsafe_finding["finding_id"])) == 1
    and raises(
        Exception,
        lambda: query(
            "UPDATE mc_eval_finding_events SET status='open' WHERE finding_id=?",
            (unsafe_finding["finding_id"],),
        ),
    )
))

for index in range(7):
    legacy = RolloutObservation(
        route="direct",
        manifest_digest=hashlib.sha256(b"manifest").hexdigest(),
        policy="allow",
        outcome="succeeded",
        latency_ms=100,
        evidence_refs=(f"comparison:{index}",),
    )
    RolloutController().compare(
        f"direct-live-{index}", "direct_chat", legacy, legacy,
    )
direct_decision = RolloutController().decision(
    "direct_chat", now="2026-08-26T04:30:00Z",
)
ok(
    "server-side rollout decision uses the scoped Eval gate",
    direct_decision.allowed,
    str(direct_decision),
)

sample_cases = tuple(case(f"sample.{index}", "system.status.read") for index in range(3))
for item in sample_cases:
    service.register_case(
        item,
        capability_refs=("sample:status",),
        freshness_seconds=3600,
        sample_eligible=True,
    )
sample_counter = iter(range(3))
scheduled = service.run_suite(
    cases=sample_cases,
    suite_run_id="suite-scheduled-status",
    trigger="scheduled",
    lane="no_model",
    executor=lambda item: observation(item, f"sample-{next(sample_counter)}"),
    capability_refs=("sample:status",),
    sample_limit=2,
)
ok("scheduled live sampling is explicit and hard bounded", (
    MAX_LIVE_SAMPLE_CASES <= 10
    and scheduled["trigger"] == "scheduled"
    and scheduled["case_count"] == 2
))
ok("scheduled sampling rejects an unbounded request", raises(
    ValueError,
    lambda: service.run_suite(
        cases=sample_cases,
        suite_run_id="suite-scheduled-unbounded",
        trigger="scheduled",
        lane="no_model",
        executor=lambda item: observation(item, "never"),
        capability_refs=("sample:status",),
    ),
))
holdout = case("sample.holdout", "system.status.read", holdout=True)
ok("live suites cannot expose or execute holdout cases", raises(
    ValueError,
    lambda: service.run_suite(
        cases=(holdout,),
        suite_run_id="suite-holdout-blocked",
        trigger="manual",
        lane="no_model",
        executor=lambda item: observation(item, "holdout"),
    ),
))

normal_sources = "\n".join(
    (ROOT / path).read_text(encoding="utf-8")
    for path in ("core/chat_runtime.py", "core/conductor.py", "api/routers/chat.py")
)
ok("normal owner turns do not import or run the Eval suite", "eval_live" not in normal_sources)
ok("T05 leaves every Runtime V2 execution flag off", (
    not any(config.rollout_state().values())
    and not owner_flags.get_bool(owner_flags.RUNTIME_V2_ROLLBACK)
))
ok("new Eval control tables contain no restricted body columns", all(
    forbidden not in str(query(
        "SELECT sql FROM sqlite_master WHERE name IN "
        "('mc_eval_case_controls','mc_eval_suite_runs','mc_eval_finding_events')"
    )).lower()
    for forbidden in ("prompt", "response", "secret", "tool_output", "provider_error")
))

print(f"PASS: {PASS} TOBIval T05 live-Eval gate checks")

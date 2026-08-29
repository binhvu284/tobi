"""Acceptance checks for #34/T06 bounded owner Eval projections and API auth."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TMP = tempfile.mkdtemp(prefix="tobival_t06_")
os.environ["DB_PATH"] = os.path.join(TMP, "agent.db")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from core.database import init_database  # noqa: E402
from core.runtime.contracts import (  # noqa: E402
    EvalCase,
    EvalCaseControl,
    EvalRun,
    EvalStatus,
    EvalSuiteRun,
    LoopPolicy,
    LoopRecipe,
    LoopType,
    RunRequest,
    Surface,
)
from core.runtime.eval_view import EvalControlView  # noqa: E402
from core.runtime.evals import EvalRepository  # noqa: E402
from core.runtime.event_store import append_run_event  # noqa: E402
from core.runtime.repository import RuntimeRepository  # noqa: E402
from api.routers import runtime as runtime_api  # noqa: E402


PASS = 0
NOW = "2026-08-26T05:00:00Z"


def ok(name: str, condition: bool, detail: object = "") -> None:
    global PASS
    if not condition:
        print(f"FAIL {name}: {detail}")
        raise SystemExit(1)
    PASS += 1
    print(f"PASS {name}")


init_database()
runtime = RuntimeRepository()
recipe = LoopRecipe(
    recipe_id="tobival.owner-view",
    version="1",
    name="Owner Eval view fixture",
    loop_type=LoopType.GOAL,
    trigger="manual_eval",
    objective="Project one bounded Eval result",
    stop_condition="result recorded",
    max_attempts=1,
    max_runtime_s=30,
    max_cost_usd=0,
)
runtime.save_loop_recipe(recipe)
runtime.create_run(
    RunRequest(
        request_id="request-owner-view",
        surface=Surface.CLI,
        owner_id="owner",
        session_id="eval-owner-view",
        mode="eval",
        message="Private synthetic owner request body",
    ),
    loop_policy=LoopPolicy.from_recipe(
        "policy-owner-view", "1", recipe, "decision-owner-view", enabled=False,
    ),
    run_id="run-owner-view",
    timestamp="2026-08-26T04:59:58Z",
)
append_run_event(
    run_id="run-owner-view",
    event_type="eval.evidence_observed",
    stage="evaluate",
    actor="tobival",
    payload={
        "evidence_id": "projection_ref:status-1",
        "raw_response": "private model response",
        "api_key": "sk-never-show",
    },
    event_id="run-owner-view:evidence",
    trace_id="trace-owner-view",
    timestamp=NOW,
)

repository = EvalRepository()
case = EvalCase(
    eval_case_id="tobival.v1.owner-view",
    version="1",
    category="final_answer_grounded_claims",
    objective="Verify owner-visible bounded status",
    input_fixture={"request": "private fixture body"},
    expected_behavior="Return typed status evidence",
    required_evidence=("projection_ref",),
    scorer="structured_evidence",
    threshold=0.9,
    release_gate=True,
)
repository.save_case(case)
repository.save_case_control(EvalCaseControl(
    eval_case_id=case.eval_case_id,
    eval_case_version=case.version,
    capability_refs=("rollout:direct_chat", "workflow:system.status.read"),
    freshness_seconds=2_592_000,
))
eval_run = EvalRun(
    eval_run_id="suite-owner-view:tobival.v1.owner-view@1",
    eval_case_id=case.eval_case_id,
    eval_case_version=case.version,
    status=EvalStatus.PASSED,
    threshold=0.9,
    score=1.0,
    run_id="run-owner-view",
    trace_id="trace-owner-view",
    artifact_refs=("projection_ref:status-1",),
    started_at="2026-08-26T04:59:59Z",
    completed_at=NOW,
)
repository.record_run(eval_run)
repository.record_suite_run(EvalSuiteRun(
    suite_run_id="suite-owner-view",
    trigger="manual",
    lane="no_model",
    status=EvalStatus.PASSED,
    capability_refs=("workflow:system.status.read",),
    case_refs=(f"{case.eval_case_id}@{case.version}",),
    eval_run_refs=(eval_run.eval_run_id,),
    started_at="2026-08-26T04:59:59Z",
    completed_at=NOW,
))

view = EvalControlView(repository)
overview = view.overview(now="2026-08-26T05:30:00Z")
serialized = json.dumps(overview, sort_keys=True)
ok("overview recomputes owner-visible ECR from repository proof", (
    overview["metrics"]["ecr"]["overall"] == 100.0
    and overview["metrics"]["ecr"]["source"] == "immutable_runtime_eval_evidence"
))
ok("lane comparison reports present and missing evidence honestly", (
    overview["lanes"]["no_model"]["completion_rate"] == 100.0
    and overview["lanes"]["strong"]["status"] == "missing_evidence"
    and overview["lanes"]["weak"]["status"] == "missing_evidence"
))
ok("LDR stays unavailable until both model lanes have required proof", (
    overview["metrics"]["ldr"]["value"] is None
    and overview["metrics"]["ldr"]["status"] == "missing_evidence"
    and overview["metrics"]["ldr"]["formula"] == "0.75 * U + 0.25 * Q"
))
final_overview = EvalControlView(
    repository, include_final_acceptance=True,
).overview(now="2026-08-26T05:30:00Z")
if final_overview["acceptance"]["status"] == "synthetic_only":
    ok("synthetic final artifact cannot publish ECR or LDR as canonical", (
        final_overview["metrics"]["ecr"]["source"] == "immutable_runtime_eval_evidence"
        and final_overview["metrics"]["ldr"]["value"] is None
        and final_overview["gates"]["release"]["blockers"]
            == ["canonical-runtime-proof-missing"]
    ))
    ok("synthetic categories workflows and cases stay visibly unverified", (
        len(final_overview["categories"]) == 9
        and all(row["pass_rate"] == 0.0 for row in final_overview["categories"])
        and len(final_overview["workflows"]) == 15
        and all(row["pass_rate"] == 0.0 for row in final_overview["workflows"])
        and len(final_overview["cases"]) == 72
        and all(row["status"] == "unverified" for row in final_overview["cases"])
    ))
elif final_overview["acceptance"]["status"] == "blocked":
    ok("canonical final acceptance exposes its real blocker", (
        final_overview["metrics"]["ecr"]["overall"] == 100.0
        and final_overview["metrics"]["ldr"]["value"] <= 50
        and final_overview["gates"]["release"]["blockers"]
            == final_overview["acceptance"]["blockers"]
    ))
    ok("blocked canonical proof still projects its bounded case evidence", (
        len(final_overview["categories"]) == 9
        and len(final_overview["workflows"]) == 15
        and len(final_overview["cases"]) == 72
    ))
elif final_overview["acceptance"]["status"] == "accepted":
    ok("owner acceptance opens the canonical release gate", (
        final_overview["metrics"]["ecr"]["overall"] == 100.0
        and final_overview["metrics"]["ldr"]["value"] <= 50
        and final_overview["acceptance"]["holdout_passed"] == 14
        and final_overview["acceptance"]["owner_accepted"] is True
        and final_overview["gates"]["release"]["allowed"] is True
        and final_overview["gates"]["release"]["blockers"] == []
        and final_overview["next_action"] == "owner-accepted"
    ))
    ok("accepted proof projects every frozen category workflow and case", (
        len(final_overview["categories"]) == 9
        and all(row["pass_rate"] == 100.0 for row in final_overview["categories"])
        and len(final_overview["workflows"]) == 15
        and all(row["pass_rate"] == 100.0 for row in final_overview["workflows"])
        and len(final_overview["cases"]) == 72
        and all(row["status"] == "passed" for row in final_overview["cases"])
    ))
else:
    ok("canonical final acceptance overrides metrics but waits for owner", (
        final_overview["metrics"]["ecr"]["overall"] == 100.0
        and final_overview["metrics"]["ldr"]["value"] <= 50
        and final_overview["acceptance"]["holdout_passed"] == 14
        and final_overview["gates"]["release"]["blockers"]
            == ["owner-acceptance-required"]
    ))
    ok("canonical acceptance projects every frozen category workflow and case", (
        len(final_overview["categories"]) == 9
        and all(row["pass_rate"] == 100.0 for row in final_overview["categories"])
        and len(final_overview["workflows"]) == 15
        and all(row["pass_rate"] == 100.0 for row in final_overview["workflows"])
        and len(final_overview["cases"]) == 72
        and all(row["status"] == "passed" for row in final_overview["cases"])
    ))
artifact_detail = EvalControlView(
    repository, include_final_acceptance=True,
).case_detail("tobival.v1.final.status_grounded", version="1")
ok("final artifact case detail exposes all lanes as bounded proof", (
    artifact_detail["case"]["workflow_id"] == "system.status.read"
    and {run["lane"] for run in artifact_detail["runs"]} == {"strong", "weak", "no_model"}
    and all(
        run["status"] == (
            "unverified"
            if final_overview["acceptance"]["status"] == "synthetic_only"
            else "passed"
        )
        for run in artifact_detail["runs"]
    )
    and all(run["evidence_refs"] for run in artifact_detail["runs"])
))
artifact_detail_json = json.dumps(artifact_detail, sort_keys=True)
ok("final artifact projection excludes frozen request and expected bodies", all(
    marker not in artifact_detail_json
    for marker in ("Summarize this synthetic system status", "runtime active", "chat ready")
))
ok("overview includes category workflow freshness and scoped gate state", (
    overview["categories"][0]["pass_rate"] == 100.0
    and overview["workflows"][0]["workflow_id"] == "system.status.read"
    and overview["freshness"]["latest_suite_at"] == NOW
    and overview["gates"]["release"]["allowed"] is True
))
ok("owner projection excludes fixture prompt response and secret bodies", all(
    marker not in serialized
    for marker in ("private fixture body", "Private synthetic owner request body", "private model response", "sk-never-show")
))

detail = view.case_detail(case.eval_case_id, version="1")
detail_json = json.dumps(detail, sort_keys=True)
ok("case detail exposes bounded references and scorer evidence", (
    detail["case"]["eval_case_id"] == case.eval_case_id
    and detail["runs"][0]["trace_id"] == "trace-owner-view"
    and detail["runs"][0]["evidence_refs"] == ["projection_ref:status-1"]
))
ok("case detail never exposes input or expected behavior bodies", (
    "input_fixture" not in detail_json
    and "expected_behavior" not in detail_json
    and "private" not in detail_json.lower()
))

app = FastAPI()
app.include_router(runtime_api.router)
client = TestClient(app)
unauthorized = client.get("/api/runtime/evals")
ok("Eval API requires an owner vault session", unauthorized.status_code == 401)
runtime_api._vault_guard = lambda _token: None
authorized = client.get("/api/runtime/evals", headers={"X-Vault-Session": "test"})
ok("authorized Eval overview route returns the bounded projection", (
    authorized.status_code == 200
    and authorized.json()["metrics"]["ecr"]["overall"] == 100.0
))
case_response = client.get(
    f"/api/runtime/evals/cases/{case.eval_case_id}",
    params={"version": "1"},
    headers={"X-Vault-Session": "test"},
)
ok("authorized case route returns bounded detail", (
    case_response.status_code == 200
    and case_response.json()["case"]["eval_case_id"] == case.eval_case_id
))
missing = client.get(
    "/api/runtime/evals/cases/not-found",
    headers={"X-Vault-Session": "test"},
)
ok("unknown Eval case is a truthful 404", missing.status_code == 404)

runs = client.get("/api/runtime/runs/run-owner-view/snapshot").json()
ok("existing Runs detail keeps linked Eval results", (
    runs["evaluations"][0]["eval_run_id"] == eval_run.eval_run_id
    and runs["evaluations"][0]["trace_id"] == "trace-owner-view"
))

print(f"PASS: {PASS} TOBIval T06 API projection checks")

"""Acceptance checks for #21 T13 Runs Center backend projections."""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TMP = tempfile.mkdtemp(prefix="tobi_t13_")
os.environ["DB_PATH"] = os.path.join(TMP, "agent.db")

from core.database import get_connection, init_database  # noqa: E402
from core.runtime.contracts import (  # noqa: E402
    EvalCase,
    EvalRun,
    EvalStatus,
    LoopPolicy,
    LoopRecipe,
    LoopType,
    RunRequest,
    Surface,
    SystemEntity,
    SystemEntityType,
)
from core.runtime.evals import EvalRepository  # noqa: E402
from core.runtime.event_store import append_run_event  # noqa: E402
from core.runtime.repository import RuntimeRepository  # noqa: E402
from core.runtime.runs_view import RuntimeRunsView, RunsViewValidationError  # noqa: E402
from core.runtime.system_model import SystemModelRepository  # noqa: E402


PASS = 0


def ok(name: str, condition: bool, detail: str = "") -> None:
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


def query(sql: str, parameters: tuple = ()) -> list[sqlite3.Row]:
    conn = get_connection()
    try:
        return conn.execute(sql, parameters).fetchall()
    finally:
        conn.close()


init_database()
ok("T13 migration adds runtime preference storage", bool(query("SELECT 1 FROM sqlite_master WHERE type='table' AND name='mc_runtime_preferences'")))
repository = RuntimeRepository()
recipe = LoopRecipe(
    recipe_id="developer.reviewed",
    version="1",
    name="Reviewed coding loop",
    loop_type=LoopType.GOAL,
    trigger="owner selection",
    objective="Complete one reviewed coding run",
    stop_condition="evidence accepted",
    max_attempts=2,
    max_runtime_s=600,
    max_cost_usd=1,
    evidence_required=("test_result",),
)
repository.save_loop_recipe(recipe)
run = repository.create_run(
    RunRequest(
        request_id="t13-request",
        surface=Surface.DEVELOPER,
        owner_id="owner",
        session_id="t13-session",
        mode="coding",
        message="Build the Runs Center",
    ),
    loop_policy=LoopPolicy.from_recipe(
        "developer-reviewed-policy", "1", recipe, "t13-decision", enabled=False,
    ),
    run_id="run-t13",
)
append_run_event(
    run_id="run-t13", event_type="context.ready", stage="context", actor="mission-control",
    payload={"context_manifest_ref": "context:t13", "model_ref": "model:local"},
    event_id="t13-context", trace_id="trace-t13",
)
append_run_event(
    run_id="run-t13", event_type="recovery.required", stage="recovery", actor="mission-control",
    payload={"result_ref": "recovery:t13", "raw_error": "api_key=sk-never-store"},
    event_id="t13-recovery", trace_id="trace-t13",
)

evals = EvalRepository()
evals.save_case(EvalCase(
    eval_case_id="t13.eval", version="1", category="recovery", objective="Verify recovery",
    input_fixture={"fixture_ref": "t13"}, expected_behavior="Recovery remains visible",
    required_evidence=("recovery",), scorer="evidence_ratio", threshold=1.0,
))
evals.record_run(EvalRun(
    eval_run_id="t13-eval-run", eval_case_id="t13.eval", eval_case_version="1",
    status=EvalStatus.PASSED, threshold=1.0, score=1.0, run_id="run-t13",
    trace_id="trace-t13", artifact_refs=("recovery:t13",),
    started_at="2026-08-20T02:00:00Z", completed_at="2026-08-20T02:01:00Z",
))
SystemModelRepository().upsert_entity(SystemEntity(
    entity_id="capability-runs", entity_type=SystemEntityType.CAPABILITY,
    canonical_key="capability:runs-center", name="Runs Center", status="available", version="1",
    owner_domain="mission-control", source_ref="source:t13", observed_at="2026-08-20T02:02:00Z",
    metadata={"evidence_ref": "test:t13"},
))

view = RuntimeRunsView()
listing = view.list_runs(limit=20, surface="developer")
ok("run list is bounded and contains safe summary fields", len(listing["items"]) == 1 and listing["items"][0]["run_id"] == "run-t13" and "request_json" not in listing["items"][0])
ok("unknown status filter fails closed", raises(RunsViewValidationError, lambda: view.list_runs(status="invented")))
detail = view.get_run("run-t13", after_sequence=1)
ok("detail joins trace evaluation loop recovery and capability evidence", detail["trace"]["trace_id"] == "trace-t13" and len(detail["evaluations"]) == 1 and detail["loop"]["recipe_id"] == recipe.recipe_id and len(detail["recovery"]) == 1 and detail["capabilities"][0]["entity_id"] == "capability-runs")
ok("reconnect cursor returns only later events without duplicates", [event["sequence"] for event in detail["events"]] == [2, 3] and detail["last_sequence"] == 3)
ok("two consumers receive one deterministic projection", detail == view.get_run("run-t13", after_sequence=1))
ok("detail contains no raw secret or request body", "sk-never-store" not in str(detail) and "request_json" not in str(detail))

loops = view.list_loop_recipes()
ok("loop recipes are read-only and queryable", loops[0]["recipe_id"] == recipe.recipe_id and "contract_json" not in loops[0])
selected = view.set_developer_loop_selection(recipe.recipe_id, recipe.version)
ok("Developer loop selection persists as configuration", selected == view.get_developer_loop_selection())
ok("loop selection does not activate a loop", query("SELECT enabled FROM mc_loop_runs WHERE run_id='run-t13'")[0][0] == 0)
ok("unknown loop selection fails closed", raises(RunsViewValidationError, lambda: view.set_developer_loop_selection("missing", "1")))

api_source = (ROOT / "api" / "routers" / "runtime.py").read_text(encoding="utf-8")
for route in ("/api/runtime/runs", "/snapshot", "/api/runtime/loops", "/api/runtime/preferences/developer-loop"):
    ok(f"runtime API exposes {route}", route in api_source)

print(f"PASS: {PASS} T13 Runs projection checks")

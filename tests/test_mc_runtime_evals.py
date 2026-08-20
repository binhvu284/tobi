"""Acceptance checks for #21 T11 unified traces and TOBIval gates."""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TMP = tempfile.mkdtemp(prefix="tobi_t11_")
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
)
from core.runtime.evals import EvalConflictError, EvalRepository  # noqa: E402
from core.runtime.event_store import append_run_event  # noqa: E402
from core.runtime.repository import RuntimeRepository  # noqa: E402
from core.runtime.trace import build_run_trace  # noqa: E402


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
tables = {row[0] for row in query("SELECT name FROM sqlite_master WHERE type='table'")}
ok(
    "T11 migration adds local evaluation tables",
    {"mc_eval_cases", "mc_eval_runs", "mc_eval_findings"}.issubset(tables),
)

runtime = RuntimeRepository()
recipe = LoopRecipe(
    recipe_id="eval.fixture",
    version="1",
    name="Eval fixture",
    loop_type=LoopType.GOAL,
    trigger="test",
    objective="Trace one fixture",
    stop_condition="done",
    max_attempts=1,
    max_runtime_s=60,
    max_cost_usd=0,
)
runtime.save_loop_recipe(recipe)
run = runtime.create_run(
    RunRequest(
        request_id="t11-run",
        surface=Surface.CHAT,
        owner_id="owner",
        session_id="t11-session",
        mode="chat",
        message="Trace fixture",
    ),
    loop_policy=LoopPolicy.from_recipe(
        "t11-policy", "1", recipe, "t11-decision", enabled=False,
    ),
    run_id="run-t11",
)
append_run_event(
    run_id=run["run_id"],
    event_type="context.assembled",
    stage="context",
    actor="mission-control",
    payload={
        "context_manifest_ref": "context:manifest:1",
        "model_ref": "model:local:1",
        "raw_prompt": "owner secret body",
        "api_key": "sk-never-store-this",
    },
    event_id="t11-context",
    trace_id="trace-t11",
)
append_run_event(
    run_id=run["run_id"],
    event_type="tool.completed",
    stage="tool",
    actor="mission-control",
    payload={"tool_ref": "tobi.files.read@1", "receipt_id": "receipt:1", "tool_output": "private body"},
    event_id="t11-tool",
    trace_id="trace-t11",
)
trace = build_run_trace("run-t11")
serialized_trace = json.dumps(trace.to_dict(), sort_keys=True)
ok("one deterministic trace joins context model and tool references", trace.trace_id == "trace-t11" and trace.context_refs == ("context:manifest:1",) and trace.model_refs == ("model:local:1",) and trace.tool_refs == ("tobi.files.read@1",))
ok("trace excludes prompt output and credentials", "owner secret" not in serialized_trace and "private body" not in serialized_trace and "sk-never" not in serialized_trace)
ok("trace rebuild is deterministic", trace == build_run_trace("run-t11"))

evals = EvalRepository()
seeded = evals.ensure_default_cases()
categories = {case["category"] for case in seeded}
expected = {
    "final_answer", "tool_trajectory", "policy", "recovery", "brain_context",
    "hallucination", "connector_freshness", "coding_workflow",
}
ok("all required TOBIval categories are queryable", categories == expected, str(categories))
ok("release starts blocked while required cases are missing", not evals.gate("release").allowed)

for index, case in enumerate(seeded, start=1):
    evidence = tuple(f"{name}:fixture" for name in case["required_evidence"])
    recorded = evals.record_run(EvalRun(
        eval_run_id=f"eval-pass-{index}",
        eval_case_id=case["eval_case_id"],
        eval_case_version=case["version"],
        status=EvalStatus.PASSED,
        threshold=float(case["threshold"]),
        score=1.0,
        run_id="run-t11",
        trace_id="trace-t11",
        artifact_refs=evidence,
        started_at="2026-08-14T01:00:00Z",
        completed_at=f"2026-08-14T01:{index:02d}:00Z",
    ))
    ok(f"eval result {index} is stored", recorded["status"] == "passed")

ok("passing required cases open the release gate", evals.gate("release").allowed)
ok("passing autonomy subset opens the autonomy gate", evals.gate("autonomy").allowed)
replayed = evals.record_run(EvalRun(
    eval_run_id="eval-pass-1",
    eval_case_id=seeded[0]["eval_case_id"],
    eval_case_version=seeded[0]["version"],
    status=EvalStatus.PASSED,
    threshold=float(seeded[0]["threshold"]),
    score=1.0,
    run_id="run-t11",
    trace_id="trace-t11",
    artifact_refs=tuple(f"{name}:fixture" for name in seeded[0]["required_evidence"]),
    started_at="2026-08-14T01:00:00Z",
    completed_at="2026-08-14T01:01:00Z",
))
ok("exact eval replay is idempotent", replayed["eval_run_id"] == "eval-pass-1")
ok(
    "changed eval identity conflicts",
    raises(
        EvalConflictError,
        lambda: evals.record_run(EvalRun(
            eval_run_id="eval-pass-1",
            eval_case_id=seeded[0]["eval_case_id"],
            eval_case_version=seeded[0]["version"],
            status=EvalStatus.FAILED,
            threshold=float(seeded[0]["threshold"]),
            score=0.0,
        )),
    ),
)

custom = EvalCase(
    eval_case_id="custom-secret-fixture",
    version="1",
    category="hallucination",
    objective="Reject unsupported claims",
    input_fixture={"prompt": "api_key=sk-fixture-secret"},
    expected_behavior="Use evidence",
    required_evidence=("ground_truth",),
    scorer="evidence_ratio",
    threshold=1.0,
)
evals.save_case(custom)
stored_cases = json.dumps(evals.list_cases(), sort_keys=True)
ok("evaluation fixtures persist by hash not body", "sk-fixture-secret" not in stored_cases and "fixture_hash" in stored_cases)

print(f"PASS: {PASS} T11 trace and evaluation checks")

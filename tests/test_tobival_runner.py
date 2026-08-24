"""Acceptance checks for #34/T01 canonical execution and immutable results."""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TMP = tempfile.mkdtemp(prefix="tobival_t01_")
os.environ["DB_PATH"] = os.path.join(TMP, "agent.db")

from core.database import get_connection, init_database  # noqa: E402
from core.runtime.contracts import LoopPolicy, LoopRecipe, LoopType, RunRequest, Surface  # noqa: E402
from core.runtime.eval_dataset import load_frozen_cases  # noqa: E402
from core.runtime.eval_metrics import compute_eval_completion  # noqa: E402
from core.runtime.eval_runner import EvalExecutionError, EvalRunner  # noqa: E402
from core.runtime.eval_scorers import EvalEvidence, EvalObservation  # noqa: E402
from core.runtime.evals import EvalConflictError, EvalRepository  # noqa: E402
from core.runtime.event_store import append_run_event  # noqa: E402
from core.runtime.repository import RuntimeRepository  # noqa: E402


PASS = 0
NOW = "2026-08-25T03:00:00Z"


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
runtime = RuntimeRepository()
recipe = LoopRecipe(
    recipe_id="tobival.runner",
    version="1",
    name="TOBIval runner",
    loop_type=LoopType.GOAL,
    trigger="manual_eval",
    objective="Execute one frozen synthetic evaluation",
    stop_condition="observation recorded",
    max_attempts=1,
    max_runtime_s=60,
    max_cost_usd=0,
)
runtime.save_loop_recipe(recipe)


def canonical_observation(case, suffix: str, *, output=None, evidence=None) -> EvalObservation:
    run_id = f"run-{suffix}"
    trace_id = f"trace-{suffix}"
    runtime.create_run(
        RunRequest(
            request_id=f"request-{suffix}",
            surface=Surface.CLI,
            owner_id="owner",
            session_id=f"eval-{suffix}",
            mode="eval",
            message=f"Synthetic evaluation {case.case_id}",
        ),
        loop_policy=LoopPolicy.from_recipe(
            f"policy-{suffix}", "1", recipe, f"decision-{suffix}", enabled=False,
        ),
        run_id=run_id,
        timestamp="2026-08-25T02:59:58Z",
    )
    observed_evidence = evidence or tuple(
        EvalEvidence(
            ref=f"evidence:{suffix}:{kind}",
            kind=kind,
            status="valid",
            observed_at=NOW,
        )
        for kind in case.required_evidence
    )
    for index, item in enumerate(observed_evidence, start=1):
        append_run_event(
            run_id=run_id,
            event_type="eval.evidence_observed",
            stage="evaluate",
            actor="tobival",
            payload={"evidence_id": item.ref},
            event_id=f"{run_id}:evidence:{index}",
            trace_id=trace_id,
            timestamp=NOW,
        )
    return EvalObservation(
        run_id=run_id,
        trace_id=trace_id,
        output=case.expected if output is None else output,
        evidence=observed_evidence,
        started_at="2026-08-25T02:59:59Z",
        completed_at=NOW,
    )


case = load_frozen_cases("v1")[0]
observation = canonical_observation(case, "pass")
runner = EvalRunner(now=lambda: NOW)
passed = runner.run_case(case, suite_run_id="suite-pass", executor=lambda _: observation)
ok("the real runner records a scored pass", (
    passed["status"] == "passed" and passed["score"] == 1.0
))
ok("the result links to its canonical run and trace", (
    passed["run_id"] == observation.run_id
    and passed["trace_id"] == observation.trace_id
    and passed["evidence_refs"]
))

stored = EvalRepository().list_runs(eval_case_id=case.to_eval_case().eval_case_id)
serialized = json.dumps(stored, sort_keys=True)
ok("immutable persistence stores score and references, not fixture or output bodies", (
    len(stored) == 1
    and "Synthetic system status" not in serialized
    and "required_facts" not in serialized
    and "observation:" in serialized
))

replayed = runner.run_case(case, suite_run_id="suite-pass", executor=lambda _: observation)
ok("exact execution replay is idempotent", replayed["eval_run_id"] == passed["eval_run_id"])
changed_output = {**case.expected, "unexpected": True}
ok("changed observed content conflicts with the same immutable identity", raises(
    EvalConflictError,
    lambda: runner.run_case(
        case,
        suite_run_id="suite-pass",
        executor=lambda _: replace(observation, output=changed_output),
    ),
))

missing_observation = canonical_observation(case, "missing")
missing_observation = replace(
    missing_observation,
    evidence=missing_observation.evidence[:-1],
)
failed = runner.run_case(
    case,
    suite_run_id="suite-missing",
    executor=lambda _: missing_observation,
)
ok("missing evidence records a failed score instead of a manual pass", (
    failed["status"] == "failed" and failed["score"] == 0.0 and failed["finding_ref"]
))
findings = EvalRepository().list_findings(eval_run_id=failed["eval_run_id"])
ok("a failed execution records one bounded finding", (
    len(findings) == 1 and "required_facts" not in json.dumps(findings, sort_keys=True)
))

unlinked = canonical_observation(case, "unlinked")
unlinked = replace(
    unlinked,
    evidence=tuple(
        replace(item, ref=f"unlinked:{index}")
        for index, item in enumerate(unlinked.evidence, start=1)
    ),
)
unlinked_result = runner.run_case(
    case,
    suite_run_id="suite-unlinked",
    executor=lambda _: unlinked,
)
ok("evidence absent from the canonical trace fails closed", (
    unlinked_result["status"] == "failed" and unlinked_result["score"] == 0.0
))

invalid = replace(observation, run_id="run-does-not-exist")
ok("a missing canonical run cannot produce an eval result", raises(
    EvalExecutionError,
    lambda: runner.run_case(case, suite_run_id="suite-invalid", executor=lambda _: invalid),
))

completion = compute_eval_completion(
    EvalRepository(),
    case_refs=((case.to_eval_case().eval_case_id, case.version),),
)
ok("ECR is computed from delivered proof rather than a stored percentage", (
    completion["overall"] == 90.0
    and completion["categories"][case.group] == 90.0
    and completion["proof"][case.to_eval_case().eval_case_id]["runnable_end_to_end"] is True
))

ok("the existing Runtime tables remain immutable", raises(
    sqlite3.IntegrityError,
    lambda: query("UPDATE mc_eval_runs SET score=0 WHERE eval_run_id=?", (passed["eval_run_id"],)),
))

print(f"PASS: {PASS} TOBIval T01 runner checks")

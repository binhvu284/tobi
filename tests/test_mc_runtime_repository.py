"""Acceptance checks for #21 T03 Run 1 canonical run persistence."""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TMP = tempfile.mkdtemp(prefix="tobi_t03_run1_")
os.environ["DB_PATH"] = os.path.join(TMP, "agent.db")

from core.database import get_connection, init_database  # noqa: E402
from core.runtime.contracts import (  # noqa: E402
    ExecutionPlan,
    LoopPolicy,
    LoopRecipe,
    LoopType,
    PlanStep,
    RiskLevel,
    RunRequest,
    Surface,
)
from core.runtime.event_store import EventConflictError, append_run_event, list_run_events  # noqa: E402
from core.runtime.projections import rebuild_run_projection  # noqa: E402
from core.runtime.repository import (  # noqa: E402
    PlanValidationError,
    RunConflictError,
    RunNotFoundError,
    RuntimeRepository,
    VersionConflictError,
)
from core.runtime.state import RunStateError, RunStatus  # noqa: E402


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


def request(request_id: str, message: str = "Build durable runtime") -> RunRequest:
    return RunRequest(
        request_id=request_id,
        surface=Surface.DEVELOPER,
        owner_id="owner",
        session_id="session-t03",
        mode="agent",
        message=message,
        budget_profile="bounded",
    )


def recipe(name: str = "Bounded goal") -> LoopRecipe:
    return LoopRecipe(
        recipe_id="goal.default",
        version="1",
        name=name,
        loop_type=LoopType.GOAL,
        trigger="owner request",
        objective="Finish one bounded goal",
        stop_condition="acceptance checks pass",
        max_attempts=3,
        max_runtime_s=900,
        max_cost_usd=2.0,
        allowed_tools=("files.read",),
        recovery_policy="pause_with_options",
        evidence_required=("test_result",),
    )


def policy(*, enabled: bool = True) -> LoopPolicy:
    return LoopPolicy.from_recipe(
        policy_id="policy-goal-default",
        version="1",
        recipe=recipe(),
        policy_decision_id="decision-t03",
        owner_override={
            "max_attempts": 3,
            "access_token": "sk-t03-do-not-store",
        },
        enabled=enabled,
    )


legacy = get_connection()
legacy.execute("CREATE TABLE legacy_owner_data (value TEXT NOT NULL)")
legacy.execute("INSERT INTO legacy_owner_data (value) VALUES ('keep-me')")
legacy.commit()
legacy.close()

init_database()
init_database()
repository = RuntimeRepository()

new_tables = {
    "mc_runs",
    "mc_run_steps",
    "mc_loop_recipes",
    "mc_loop_runs",
}
created = {
    row[0]
    for row in query("SELECT name FROM sqlite_master WHERE type='table' AND name GLOB 'mc_*'")
}
ok("migration 002 adds four canonical tables", new_tables.issubset(created))
ok(
    "migration ledger is idempotent",
    len(query("SELECT version FROM schema_migrations WHERE version='mc-runtime-v2-002'")) == 1,
)
ok("legacy data survives migration", query("SELECT value FROM legacy_owner_data")[0][0] == "keep-me")

stored_recipe = repository.save_loop_recipe(recipe())
replayed_recipe = repository.save_loop_recipe(recipe())
ok("same recipe version replays safely", stored_recipe == replayed_recipe)
ok(
    "changed recipe cannot reuse a version",
    raises(RunConflictError, lambda: repository.save_loop_recipe(recipe("Changed recipe"))),
)

created_run = repository.create_run(
    request("request-1", "Build durable runtime api_key=sk-t03-do-not-store"),
    loop_policy=policy(),
    run_id="run-1",
    event_id="event-run-1-accepted",
    timestamp="2026-08-03T00:00:00Z",
)
ok(
    "run and accepted event are persisted together",
    created_run["status"] == "accepted"
    and created_run["version"] == 1
    and [event.event_type for event in list_run_events("run-1")] == ["run.accepted"],
)
replayed_run = repository.create_run(
    request("request-1", "Build durable runtime api_key=sk-t03-do-not-store"),
    loop_policy=policy(),
)
ok("same request returns the same run", replayed_run["run_id"] == "run-1")
ok(
    "changed request cannot reuse request id",
    raises(
        RunConflictError,
        lambda: repository.create_run(request("request-1", "Different objective"), loop_policy=policy()),
    ),
)

append_run_event(
    run_id="unrelated",
    event_type="run.accepted",
    stage="accept",
    actor="owner",
    payload={},
    event_id="atomic-conflict",
    timestamp="2026-08-03T00:00:01Z",
)
ok(
    "event conflict rolls back the new run",
    raises(
        EventConflictError,
        lambda: repository.create_run(
            request("request-atomic"),
            loop_policy=policy(),
            run_id="run-atomic",
            event_id="atomic-conflict",
            timestamp="2026-08-03T00:00:02Z",
        ),
    )
    and repository.get_run("run-atomic") is None,
)

routing = repository.transition_run(
    "run-1",
    RunStatus.ROUTING,
    expected_version=1,
    actor="runtime",
    event_id="event-run-1-routing",
    timestamp="2026-08-03T00:00:03Z",
)
ok("legal transition increments version", routing["status"] == "routing" and routing["version"] == 2)
ok(
    "stale writer is rejected",
    raises(
        VersionConflictError,
        lambda: repository.transition_run(
            "run-1", RunStatus.CLARIFYING, expected_version=1, actor="runtime"
        ),
    ),
)

plan = ExecutionPlan(
    plan_id="plan-run-1",
    run_id="run-1",
    version="1",
    objective="Build durable runtime",
    steps=(
        PlanStep(
            step_id="read",
            kind="tool",
            risk=RiskLevel.NONE,
            tool_name="files.read",
            arguments={"api_key": "sk-t03-do-not-store"},
            output_contract={"access_token": "sk-t03-do-not-store"},
        ),
        PlanStep(
            step_id="verify",
            kind="evaluate",
            risk=RiskLevel.NONE,
            depends_on=("read",),
        ),
    ),
    completion_predicate="tests pass",
    budget={"max_cost_usd": 2.0, "api_key": "sk-t03-do-not-store"},
)
planned = repository.save_plan(
    plan,
    expected_version=2,
    actor="runtime",
    event_id="event-run-1-planned",
    timestamp="2026-08-03T00:00:04Z",
)
steps = repository.list_steps("run-1")
ok(
    "validated plan and ordered steps persist",
    planned["status"] == "planned"
    and planned["version"] == 3
    and [step["step_id"] for step in steps] == ["read", "verify"]
    and steps[1]["depends_on"] == ["read"],
)
ok(
    "durable plan fields redact secrets before storage",
    "sk-t03-do-not-store"
    not in "\n".join(row[0] for row in query("SELECT sql FROM sqlite_master WHERE sql IS NOT NULL"))
    and "sk-t03-do-not-store"
    not in "\n".join(
        str(value)
        for table in new_tables
        for row in query(f"SELECT * FROM {table}")
        for value in row
    ),
)

missing_dependency = ExecutionPlan(
    plan_id="plan-missing",
    run_id="run-1",
    version="2",
    objective="Invalid",
    steps=(
        PlanStep(
            step_id="broken",
            kind="tool",
            risk=RiskLevel.NONE,
            depends_on=("missing",),
        ),
    ),
)
ok(
    "missing plan dependency is rejected",
    raises(
        PlanValidationError,
        lambda: repository.save_plan(missing_dependency, expected_version=3, actor="runtime"),
    ),
)

cyclic_plan = ExecutionPlan(
    plan_id="plan-cycle",
    run_id="run-1",
    version="2",
    objective="Invalid cycle",
    steps=(
        PlanStep(step_id="a", kind="tool", risk=RiskLevel.NONE, depends_on=("b",)),
        PlanStep(step_id="b", kind="tool", risk=RiskLevel.NONE, depends_on=("a",)),
    ),
)
ok(
    "cyclic plan is rejected",
    raises(
        PlanValidationError,
        lambda: repository.save_plan(cyclic_plan, expected_version=3, actor="runtime"),
    ),
)

repository.create_run(request("request-invalid"), loop_policy=policy(), run_id="run-invalid")
ok(
    "illegal state jump is rejected",
    raises(
        RunStateError,
        lambda: repository.transition_run(
            "run-invalid", RunStatus.SUCCEEDED, expected_version=1, actor="runtime"
        ),
    ),
)
ok(
    "missing run is explicit",
    raises(
        RunNotFoundError,
        lambda: repository.transition_run(
            "missing", RunStatus.ROUTING, expected_version=1, actor="runtime"
        ),
    ),
)

repository.create_run(request("request-race"), loop_policy=policy(), run_id="run-race")


def race_transition(index: int) -> str:
    try:
        repository.transition_run(
            "run-race",
            RunStatus.ROUTING,
            expected_version=1,
            actor=f"worker-{index}",
            event_id=f"event-race-{index}",
        )
        return "won"
    except VersionConflictError:
        return "stale"


with ThreadPoolExecutor(max_workers=2) as pool:
    race_results = list(pool.map(race_transition, range(2)))
ok("only one concurrent transition wins", sorted(race_results) == ["stale", "won"])

running = repository.transition_run(
    "run-1", RunStatus.RUNNING, expected_version=3, actor="runtime"
)
succeeded = repository.transition_run(
    "run-1", RunStatus.SUCCEEDED, expected_version=running["version"], actor="runtime"
)
ok("run reaches terminal state legally", succeeded["status"] == "succeeded")
ok(
    "terminal state cannot reopen",
    raises(
        RunStateError,
        lambda: repository.transition_run(
            "run-1",
            RunStatus.RUNNING,
            expected_version=succeeded["version"],
            actor="runtime",
        ),
    ),
)

repository.create_run(
    request("request-disabled"),
    loop_policy=policy(enabled=False),
    run_id="run-disabled",
)
repository.transition_run(
    "run-disabled", RunStatus.ROUTING, expected_version=1, actor="runtime"
)
disabled_plan = ExecutionPlan(
    plan_id="plan-disabled",
    run_id="run-disabled",
    version="1",
    objective="Disabled",
)
repository.save_plan(disabled_plan, expected_version=2, actor="runtime")
ok(
    "disabled loop policy cannot enter running",
    raises(
        RunStateError,
        lambda: repository.transition_run(
            "run-disabled", RunStatus.RUNNING, expected_version=3, actor="runtime"
        ),
    ),
)

guard = get_connection()
try:
    policy_update_blocked = raises(
        sqlite3.DatabaseError,
        lambda: guard.execute(
            "UPDATE mc_loop_runs SET policy_version='changed' WHERE run_id='run-1'"
        ),
    )
    recipe_update_blocked = raises(
        sqlite3.DatabaseError,
        lambda: guard.execute(
            "UPDATE mc_loop_recipes SET name='changed' WHERE recipe_id='goal.default'"
        ),
    )
finally:
    guard.rollback()
    guard.close()
ok("recipe and effective policy snapshots are immutable", policy_update_blocked and recipe_update_blocked)

projection = rebuild_run_projection("run-1")
event_types = [event.event_type for event in list_run_events("run-1")]
ok(
    "T02 projection rebuilds canonical state",
    projection["state"]["status"] == "succeeded"
    and event_types == [
        "run.accepted",
        "run.routing",
        "run.planned",
        "run.running",
        "run.succeeded",
    ],
)
ok("legacy data remains after repository work", query("SELECT value FROM legacy_owner_data")[0][0] == "keep-me")

print(f"\n{PASS}/{PASS} T03 Run 1 repository tests pass")

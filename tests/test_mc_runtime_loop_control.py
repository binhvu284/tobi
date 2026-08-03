"""Acceptance checks for #21 T03 Run 3B budgets and loop control."""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TMP = tempfile.mkdtemp(prefix="tobi_t03_run3b_")
os.environ["DB_PATH"] = os.path.join(TMP, "agent.db")

from core.database import get_connection, init_database  # noqa: E402
from core.runtime.budget import effective_limits  # noqa: E402
from core.runtime.contracts import (  # noqa: E402
    ExecutionPlan,
    LoopIterationResult,
    LoopPolicy,
    LoopRecipe,
    LoopType,
    PlanStep,
    RecoveryAction,
    RiskLevel,
    RunRequest,
    RunUsageDelta,
    Surface,
    contract_to_dict,
)
from core.runtime.control import RuntimeControl  # noqa: E402
from core.runtime.event_store import EventConflictError, append_run_event, list_run_events  # noqa: E402
from core.runtime.loop_controller import (  # noqa: E402
    IterationConflictError,
    LoopController,
)
from core.runtime.repository import RuntimeRepository, VersionConflictError  # noqa: E402
from core.runtime.state import RunStatus  # noqa: E402
from core.schema.runtime import _ensure_runtime_schema  # noqa: E402


PASS = 0
BASE = datetime(2026, 8, 3, 6, 0, tzinfo=timezone.utc)
SECRET = "sk-t03-run3b-do-not-store"


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


def recipe(recipe_id: str = "goal.loop", **overrides) -> LoopRecipe:
    values = {
        "recipe_id": recipe_id,
        "version": "1",
        "name": "Bounded loop",
        "loop_type": LoopType.GOAL,
        "trigger": "owner request",
        "objective": "Finish one bounded loop",
        "stop_condition": "acceptance checks pass",
        "max_attempts": 3,
        "max_runtime_s": 900,
        "max_cost_usd": 2.0,
        "max_model_calls": 50,
        "max_tool_calls": 100,
        "max_total_tokens": 500_000,
        "max_download_bytes": 100_000_000,
        "max_storage_bytes": 500_000_000,
        "evidence_required": ("test_result",),
    }
    values.update(overrides)
    return LoopRecipe(**values)


def prepare_run(
    repository: RuntimeRepository,
    run_id: str,
    *,
    loop_recipe: LoopRecipe | None = None,
    owner_override: dict | None = None,
    plan_budget: dict | None = None,
) -> None:
    loop_recipe = loop_recipe or recipe(f"recipe-{run_id}")
    repository.save_loop_recipe(loop_recipe)
    policy = LoopPolicy.from_recipe(
        policy_id=f"policy-{run_id}",
        version="1",
        recipe=loop_recipe,
        policy_decision_id=f"decision-{run_id}",
        owner_override=owner_override,
        enabled=True,
    )
    repository.create_run(
        RunRequest(
            request_id=f"request-{run_id}",
            surface=Surface.DEVELOPER,
            owner_id="owner",
            session_id="session-t03-run3b",
            mode="agent",
            message="Prove persisted loop control",
        ),
        loop_policy=policy,
        run_id=run_id,
    )
    repository.transition_run(
        run_id, RunStatus.ROUTING, expected_version=1, actor="runtime"
    )
    repository.save_plan(
        ExecutionPlan(
            plan_id=f"plan-{run_id}",
            run_id=run_id,
            version="1",
            objective="Prove persisted loop control",
            steps=(
                PlanStep(
                    step_id="work",
                    kind="tool",
                    risk=RiskLevel.NONE,
                    tool_name="files.read",
                ),
            ),
            budget=plan_budget or {},
        ),
        expected_version=2,
        actor="runtime",
    )
    repository.transition_run(
        run_id, RunStatus.RUNNING, expected_version=3, actor="runtime"
    )


# Prove migration 005 alters a real version-004 loop row without replacing it.
upgrade = sqlite3.connect(os.path.join(TMP, "runtime-v2-004.db"))
upgrade.row_factory = sqlite3.Row
upgrade.execute(
    """CREATE TABLE schema_migrations (
        version TEXT PRIMARY KEY,
        applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )"""
)
upgrade.executemany(
    "INSERT INTO schema_migrations (version) VALUES (?)",
    [(f"mc-runtime-v2-00{index}",) for index in range(1, 5)],
)
upgrade.execute(
    """CREATE TABLE mc_loop_runs (
        run_id TEXT PRIMARY KEY,
        recipe_id TEXT NOT NULL,
        recipe_version TEXT NOT NULL,
        policy_id TEXT NOT NULL,
        policy_version TEXT NOT NULL,
        policy_decision_id TEXT NOT NULL,
        loop_type TEXT NOT NULL,
        policy_json TEXT NOT NULL,
        policy_hash TEXT NOT NULL,
        owner_override_json TEXT NOT NULL DEFAULT '{}',
        enabled INTEGER NOT NULL DEFAULT 0,
        iteration INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'accepted',
        stop_reason TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )"""
)
upgrade.execute(
    """INSERT INTO mc_loop_runs (
        run_id,recipe_id,recipe_version,policy_id,policy_version,
        policy_decision_id,loop_type,policy_json,policy_hash,enabled,
        iteration,status,created_at,updated_at
    ) VALUES (
        'legacy-loop','legacy.recipe','1','legacy.policy','1','legacy.decision',
        'goal','{}','hash',1,2,'running','2026-08-03T00:00:00Z',
        '2026-08-03T00:00:00Z'
    )"""
)
_ensure_runtime_schema(upgrade)
_ensure_runtime_schema(upgrade)
upgrade_columns = {
    row[1] for row in upgrade.execute("PRAGMA table_info(mc_loop_runs)").fetchall()
}
upgrade_evidence = (
    {
        "loop_version",
        "model_calls",
        "tool_calls",
        "prompt_tokens",
        "completion_tokens",
        "runtime_ms",
        "cost_microusd",
        "download_bytes",
        "storage_bytes",
        "started_at",
        "stopped_at",
    }.issubset(upgrade_columns)
    and upgrade.execute(
        "SELECT iteration FROM mc_loop_runs WHERE run_id='legacy-loop'"
    ).fetchone()[0]
    == 2
    and upgrade.execute(
        "SELECT COUNT(*) FROM schema_migrations WHERE version='mc-runtime-v2-005'"
    ).fetchone()[0]
    == 1
)
upgrade.close()

legacy = sqlite3.connect(os.environ["DB_PATH"])
legacy.execute("CREATE TABLE legacy_owner_data (value TEXT NOT NULL)")
legacy.execute("INSERT INTO legacy_owner_data (value) VALUES ('keep-me')")
legacy.commit()
legacy.close()
init_database()
init_database()

repository = RuntimeRepository()
controller = LoopController()

ok(
    "migration 005 is additive, idempotent, and preserves version-004 rows",
    upgrade_evidence
    and bool(
        query("SELECT 1 FROM sqlite_master WHERE type='table' AND name='mc_loop_iterations'")
    )
    and query("SELECT value FROM legacy_owner_data")[0][0] == "keep-me",
)
ok(
    "usage contracts reject negative or non-integer counters",
    raises(ValueError, lambda: RunUsageDelta(model_calls=-1))
    and raises(ValueError, lambda: RunUsageDelta(runtime_ms=True)),
)

limit_recipe = recipe("recipe-limits", max_attempts=4, max_cost_usd=2.0)
limit_policy = LoopPolicy.from_recipe(
    "policy-limits",
    "1",
    limit_recipe,
    "decision-limits",
    owner_override={"max_attempts": 99, "max_model_calls": 5},
    enabled=True,
)
limits = effective_limits(
    contract_to_dict(limit_policy),
    {"max_model_calls": 3, "max_cost_usd": 4.0},
)
ok(
    "effective limits use the lowest authority and include every hard dimension",
    limits["max_attempts"] == 4
    and limits["max_model_calls"] == 3
    and limits["max_cost_microusd"] == 2_000_000
    and {
        "max_runtime_ms",
        "max_tool_calls",
        "max_total_tokens",
        "max_download_bytes",
        "max_storage_bytes",
    }.issubset(limits),
)

prepare_run(repository, "run-loop")
started = controller.start_iteration(
    "iteration-loop-1",
    "run-loop",
    expected_run_version=4,
    actor="runtime",
    now=BASE,
)
replayed_start = controller.start_iteration(
    "iteration-loop-1",
    "run-loop",
    expected_run_version=4,
    actor="runtime",
    now=BASE,
)
ok(
    "iteration start is persisted, versioned, and safely replayed",
    started == replayed_start
    and started["status"] == "running"
    and started["iteration"] == 1
    and repository.get_run("run-loop")["version"] == 5,
)
ok(
    "changed content cannot reuse an iteration identity",
    raises(
        IterationConflictError,
        lambda: controller.start_iteration(
            "iteration-loop-1",
            "run-loop",
            expected_run_version=4,
            actor="different-actor",
            now=BASE,
        ),
    ),
)

continued = controller.finish_iteration(
    "iteration-loop-1",
    expected_run_version=5,
    actor="runtime",
    usage=RunUsageDelta(
        model_calls=1,
        tool_calls=2,
        prompt_tokens=100,
        completion_tokens=50,
        runtime_ms=200,
        cost_microusd=10_000,
    ),
    result=LoopIterationResult(
        stop_condition_met=False,
        summary=f"Continue after authorization: Bearer {SECRET}",
    ),
    now=BASE + timedelta(seconds=1),
)
replayed_finish = controller.finish_iteration(
    "iteration-loop-1",
    expected_run_version=5,
    actor="runtime",
    usage=RunUsageDelta(
        model_calls=1,
        tool_calls=2,
        prompt_tokens=100,
        completion_tokens=50,
        runtime_ms=200,
        cost_microusd=10_000,
    ),
    result=LoopIterationResult(
        stop_condition_met=False,
        summary=f"Continue after authorization: Bearer {SECRET}",
    ),
    now=BASE + timedelta(seconds=1),
)
loop_state = repository.get_run("run-loop")["loop"]
ok(
    "iteration finish records aggregate usage once and survives restart",
    continued == replayed_finish
    and continued["status"] == "completed"
    and loop_state["model_calls"] == 1
    and loop_state["tool_calls"] == 2
    and loop_state["prompt_tokens"] == 100
    and LoopController().get_iteration("iteration-loop-1")["status"] == "completed",
)
ok(
    "changed usage cannot replay a finished iteration",
    raises(
        IterationConflictError,
        lambda: controller.finish_iteration(
            "iteration-loop-1",
            expected_run_version=5,
            actor="runtime",
            usage=RunUsageDelta(model_calls=2),
            result=LoopIterationResult(
                stop_condition_met=False, summary="Changed replay"
            ),
            now=BASE + timedelta(seconds=1),
        ),
    ),
)

second = controller.start_iteration(
    "iteration-loop-2",
    "run-loop",
    expected_run_version=6,
    actor="runtime",
    now=BASE + timedelta(seconds=2),
)
succeeded = controller.finish_iteration(
    "iteration-loop-2",
    expected_run_version=7,
    actor="runtime",
    usage=RunUsageDelta(runtime_ms=100),
    result=LoopIterationResult(
        stop_condition_met=True,
        evidence_refs=("test:runtime-loop",),
        summary="Acceptance checks pass",
    ),
    now=BASE + timedelta(seconds=3),
)
ok(
    "evidence-backed stop condition succeeds the same canonical run",
    second["iteration"] == 2
    and succeeded["run_status"] == "succeeded"
    and repository.get_run("run-loop")["status"] == "succeeded"
    and repository.get_run("run-loop")["loop"]["stop_reason"]
    == "stop_condition_met",
)

prepare_run(repository, "run-evidence")
controller.start_iteration(
    "iteration-evidence",
    "run-evidence",
    expected_run_version=4,
    actor="runtime",
    now=BASE,
)
missing_evidence = controller.finish_iteration(
    "iteration-evidence",
    expected_run_version=5,
    actor="runtime",
    usage=RunUsageDelta(),
    result=LoopIterationResult(
        stop_condition_met=True,
        summary="Claimed complete without evidence",
    ),
    now=BASE + timedelta(seconds=1),
)
ok(
    "a claimed stop without required evidence enters structured recovery",
    missing_evidence["run_status"] == "recovering"
    and missing_evidence["stop_reason"] == "required_evidence_missing",
)


def run_limit_case(name: str, recipe_overrides: dict, plan_budget: dict, usage: RunUsageDelta):
    run_id = f"run-limit-{name}"
    prepare_run(
        repository,
        run_id,
        loop_recipe=recipe(f"recipe-limit-{name}", **recipe_overrides),
        plan_budget=plan_budget,
    )
    controller.start_iteration(
        f"iteration-limit-{name}",
        run_id,
        expected_run_version=4,
        actor="runtime",
        now=BASE,
    )
    decision = controller.finish_iteration(
        f"iteration-limit-{name}",
        expected_run_version=5,
        actor="runtime",
        usage=usage,
        result=LoopIterationResult(
            stop_condition_met=False, summary=f"Exercise {name} limit"
        ),
        now=BASE + timedelta(seconds=1),
    )
    return run_id, decision


limit_cases = [
    ("attempts", {"max_attempts": 1}, {}, RunUsageDelta(), "max_attempts"),
    ("runtime", {"max_runtime_s": 1}, {}, RunUsageDelta(runtime_ms=1_000), "max_runtime_s"),
    ("cost", {"max_cost_usd": 0.000001}, {}, RunUsageDelta(cost_microusd=1), "max_cost_usd"),
    ("model", {}, {"max_model_calls": 1}, RunUsageDelta(model_calls=1), "max_model_calls"),
    ("tool", {}, {"max_tool_calls": 1}, RunUsageDelta(tool_calls=1), "max_tool_calls"),
    ("tokens", {}, {"max_total_tokens": 1}, RunUsageDelta(prompt_tokens=1), "max_total_tokens"),
    ("download", {}, {"max_download_bytes": 1}, RunUsageDelta(download_bytes=1), "max_download_bytes"),
    ("storage", {}, {"max_storage_bytes": 1}, RunUsageDelta(storage_bytes=1), "max_storage_bytes"),
]
limit_results = []
for case_name, recipe_overrides, plan_budget, usage, expected_reason in limit_cases:
    run_id, decision = run_limit_case(case_name, recipe_overrides, plan_budget, usage)
    limit_results.append(
        decision["run_status"] == "recovering"
        and decision["stop_reason"] == expected_reason
        and repository.claim_step(
            run_id,
            worker_id="worker-after-limit",
            lease_seconds=60,
            now=BASE + timedelta(seconds=2),
        )
        is None
    )
ok(
    "every mandatory hard limit stops later work deterministically",
    all(limit_results),
)

prepare_run(repository, "run-race")


def start_race(index: int) -> str:
    try:
        controller.start_iteration(
            f"iteration-race-{index}",
            "run-race",
            expected_run_version=4,
            actor=f"worker-{index}",
            now=BASE,
        )
        return "won"
    except VersionConflictError:
        return "conflict"


with ThreadPoolExecutor(max_workers=2) as executor:
    race_results = list(executor.map(start_race, range(2)))
ok(
    "two iteration starters race and exactly one wins",
    race_results.count("won") == 1 and race_results.count("conflict") == 1,
)

prepare_run(repository, "run-cancel-loop")
controller.start_iteration(
    "iteration-cancel-loop",
    "run-cancel-loop",
    expected_run_version=4,
    actor="runtime",
    now=BASE,
)
RuntimeControl().record_command(
    "command-cancel-loop",
    "run-cancel-loop",
    RecoveryAction.CANCEL,
    expected_version=5,
    actor="owner",
    now=BASE + timedelta(seconds=1),
)
ok(
    "owner cancellation closes the active iteration and same run",
    controller.get_iteration("iteration-cancel-loop")["status"] == "stopped"
    and repository.get_run("run-cancel-loop")["status"] == "cancelled",
)

prepare_run(repository, "run-rollback-loop")
append_run_event(
    run_id="run-rollback-loop",
    event_type="test.conflict",
    stage="test",
    actor="test",
    event_id="loop-event-conflict",
)
ok(
    "event conflict rolls back iteration start and run version",
    raises(
        EventConflictError,
        lambda: controller.start_iteration(
            "iteration-rollback-loop",
            "run-rollback-loop",
            expected_run_version=4,
            actor="runtime",
            now=BASE,
            event_id="loop-event-conflict",
        ),
    )
    and controller.get_iteration("iteration-rollback-loop") is None
    and repository.get_run("run-rollback-loop")["version"] == 4,
)

update_blocked = raises(
    sqlite3.IntegrityError,
    lambda: query(
        "UPDATE mc_loop_iterations SET iteration=99 WHERE iteration_id='iteration-loop-1'"
    ),
)
delete_blocked = raises(
    sqlite3.IntegrityError,
    lambda: query(
        "DELETE FROM mc_loop_iterations WHERE iteration_id='iteration-loop-1'"
    ),
)
ok("iteration identity and history are immutable in SQLite", update_blocked and delete_blocked)

conn = get_connection()
try:
    durable_dump = "\n".join(conn.iterdump())
finally:
    conn.close()
ok(
    "loop summaries and events redact secrets before persistence",
    SECRET not in durable_dump and "[REDACTED]" in durable_dump,
)

event_types = [event.event_type for event in list_run_events("run-loop")]
ok(
    "iteration decisions join the ordered canonical run history",
    event_types.count("loop.iteration_started") == 2
    and event_types.count("loop.iteration_finished") == 2
    and "run.succeeded" in event_types,
)

print(f"\n{PASS}/{PASS} T03 Run 3B loop-control tests pass")

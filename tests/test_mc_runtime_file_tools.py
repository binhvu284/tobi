"""Acceptance checks for #21 T07 Run 2A dormant file read/list execution."""
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

TMP = Path(tempfile.mkdtemp(prefix="tobi_t07_run2a_"))
os.environ["DB_PATH"] = str(TMP / "agent.db")

from core.coding_policy import CodingPolicy  # noqa: E402
from core.coding_tools import CodingToolBroker  # noqa: E402
from core.database import get_connection, init_database  # noqa: E402
from core.runtime.contracts import (  # noqa: E402
    ApprovalMode,
    BudgetStatus,
    Certainty,
    ExecutionPlan,
    IsolationLevel,
    LoopPolicy,
    LoopRecipe,
    LoopType,
    PlanStep,
    PolicyInput,
    RiskLevel,
    RunRequest,
    Surface,
    TrustClass,
    contract_to_dict,
)
from core.runtime.event_store import list_run_events  # noqa: E402
from core.runtime.file_tools import (  # noqa: E402
    LIST_FILES_REF,
    READ_FILE_REF,
    build_file_tool_runtime,
)
from core.runtime.repository import RuntimeRepository  # noqa: E402
from core.runtime.state import RunStatus  # noqa: E402
from core.runtime.tool_catalog import ToolCallPreparationError  # noqa: E402


PASS = 0


def ok(name: str, condition: bool, detail: object = "") -> None:
    global PASS
    if not condition:
        print(f"FAIL {name}: {detail}")
        raise SystemExit(1)
    PASS += 1
    print(f"PASS {name}")


def raises(error_type: type[Exception], callback) -> Exception | None:
    try:
        callback()
    except error_type as exc:
        return exc
    return None


def query_count(table: str) -> int:
    conn = get_connection()
    try:
        row = conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()
        return int(row["count"])
    finally:
        conn.close()


def prepare_run(
    repository: RuntimeRepository,
    run_id: str,
    *,
    step_id: str,
    tool_ref: str,
    arguments: dict,
) -> dict:
    recipe = LoopRecipe(
        recipe_id=f"recipe-{run_id}",
        version="1",
        name="File read fixture",
        loop_type=LoopType.TURN,
        trigger="owner request",
        objective="Read one approved worktree path safely",
        stop_condition="typed file result persisted",
        max_attempts=2,
        max_runtime_s=300,
        max_cost_usd=1.0,
        allowed_tools=(tool_ref,),
    )
    repository.save_loop_recipe(recipe)
    repository.create_run(
        RunRequest(
            request_id=f"request-{run_id}",
            surface=Surface.DEVELOPER,
            owner_id="owner",
            session_id="session-t07-run2a",
            mode="agent",
            message="Read one project file",
        ),
        loop_policy=LoopPolicy.from_recipe(
            policy_id=f"loop-policy-{run_id}",
            version="1",
            recipe=recipe,
            policy_decision_id=f"bootstrap-{run_id}",
            enabled=True,
        ),
        run_id=run_id,
    )
    repository.transition_run(
        run_id,
        RunStatus.ROUTING,
        expected_version=1,
        actor="runtime-test",
    )
    repository.save_plan(
        ExecutionPlan(
            plan_id=f"plan-{run_id}",
            run_id=run_id,
            version="1",
            objective="Read one approved worktree path safely",
            steps=(
                PlanStep(
                    step_id=step_id,
                    kind="tool",
                    risk=RiskLevel.NONE,
                    tool_name=tool_ref,
                    arguments=arguments,
                    retry_policy="none",
                ),
            ),
        ),
        expected_version=2,
        actor="runtime-test",
    )
    repository.transition_run(
        run_id,
        RunStatus.RUNNING,
        expected_version=3,
        actor="runtime-test",
    )
    lease = repository.claim_step(run_id, worker_id=f"worker-{run_id}")
    assert lease is not None
    return lease


def policy_input(
    runtime,
    *,
    decision_id: str,
    run_id: str,
    step_id: str,
    tool_ref: str,
    target: str,
    permissions: tuple[str, ...] = ("files.read",),
) -> PolicyInput:
    return PolicyInput(
        decision_id=decision_id,
        run_id=run_id,
        step_id=step_id,
        owner_id="owner",
        session_id="session-t07-run2a",
        surface=Surface.DEVELOPER,
        mode="agent",
        tool=runtime.catalog.get_spec(tool_ref),
        target=target,
        granted_permissions=permissions,
        trust_class=TrustClass.OWNER_DIRECT,
        certainty=Certainty.KNOWN,
        instruction_authority=True,
        available_isolations=(IsolationLevel.WORKSPACE,),
        budget_status=BudgetStatus.AVAILABLE,
        approval_mode=ApprovalMode.ASK,
    )


def execute_read(
    runtime,
    repository: RuntimeRepository,
    *,
    run_id: str,
    tool_ref: str,
    arguments: dict,
    target: str,
    permissions: tuple[str, ...] = ("files.read",),
):
    step_id = f"step-{run_id}"
    lease = prepare_run(
        repository,
        run_id,
        step_id=step_id,
        tool_ref=tool_ref,
        arguments=arguments,
    )
    call = runtime.catalog.prepare_call(
        call_id=f"call-{run_id}",
        run_id=run_id,
        step_id=step_id,
        tool_ref=tool_ref,
        arguments=arguments,
        surface=Surface.DEVELOPER,
        mode="agent",
        candidate_tool_refs=(tool_ref,),
    )
    result = runtime.executor.execute(
        call,
        policy_input(
            runtime,
            decision_id=f"policy-{run_id}",
            run_id=run_id,
            step_id=step_id,
            tool_ref=tool_ref,
            target=target,
            permissions=permissions,
        ),
        worker_id=lease["worker_id"],
        lease_token=lease["lease_token"],
        lease_epoch=lease["lease_epoch"],
    )
    return result


init_database()
repository = RuntimeRepository()
repo_root = TMP / "repo"
worktree = repo_root / ".tobi" / "developer" / "worktrees" / "run2a"
(worktree / "src").mkdir(parents=True)
(worktree / "src" / "alpha.txt").write_bytes(b"alpha line\n")
(worktree / "src" / "beta.py").write_bytes(b"VALUE = 2\n")
(worktree / "src" / "gamma.md").write_bytes(b"gamma\n")

secret_value = "secret-do-not-echo-123456789"
(worktree / ".env").write_text(f"TOKEN={secret_value}\n", encoding="utf-8")
(repo_root / "outside.txt").write_text("outside-secret-content", encoding="utf-8")

policy = CodingPolicy.load(ROOT / "config" / "coding_policy.v1.json", repo_root=repo_root)
broker_events: list[tuple[str, dict]] = []
broker = CodingToolBroker(
    policy,
    worktree,
    on_event=lambda kind, payload: broker_events.append((kind, payload)),
)
runtime = build_file_tool_runtime(broker=broker)

refs = tuple(entry.tool_ref for entry in runtime.catalog.manifest.entries)
specs = tuple(runtime.catalog.get_spec(tool_ref) for tool_ref in refs)
metadata_json = json.dumps(
    {
        "manifest": contract_to_dict(runtime.catalog.manifest),
        "specs": contract_to_dict(specs),
    },
    sort_keys=True,
)
ok(
    "file catalog is bounded Developer-only metadata with no private broker material",
    refs == (LIST_FILES_REF, READ_FILE_REF)
    and all(spec.allowed_surfaces == (Surface.DEVELOPER,) for spec in specs)
    and all(spec.allowed_modes == ("agent",) for spec in specs)
    and all(spec.required_permissions == ("files.read",) for spec in specs)
    and all(spec.isolation == "workspace" for spec in specs)
    and str(worktree).lower() not in metadata_json.lower()
    and secret_value not in metadata_json
    and "callable" not in metadata_json.lower()
    and "function" not in metadata_json.lower(),
    metadata_json,
)

invalid_calls = (
    raises(
        ToolCallPreparationError,
        lambda: runtime.catalog.prepare_call(
            call_id="call-malformed",
            run_id="run-malformed",
            step_id="read",
            tool_ref=READ_FILE_REF,
            arguments={},
            surface=Surface.DEVELOPER,
            mode="agent",
            candidate_tool_refs=(READ_FILE_REF,),
        ),
    ),
    raises(
        ToolCallPreparationError,
        lambda: runtime.catalog.prepare_call(
            call_id="call-drive-relative",
            run_id="run-drive-relative",
            step_id="read",
            tool_ref=READ_FILE_REF,
            arguments={"path": "C:secret.txt"},
            surface=Surface.DEVELOPER,
            mode="agent",
            candidate_tool_refs=(READ_FILE_REF,),
        ),
    ),
    raises(
        ToolCallPreparationError,
        lambda: runtime.catalog.prepare_call(
            call_id="call-absolute",
            run_id="run-absolute",
            step_id="read",
            tool_ref=READ_FILE_REF,
            arguments={"path": "/etc/passwd"},
            surface=Surface.DEVELOPER,
            mode="agent",
            candidate_tool_refs=(READ_FILE_REF,),
        ),
    ),
    raises(
        ToolCallPreparationError,
        lambda: runtime.catalog.prepare_call(
            call_id="call-surface",
            run_id="run-surface",
            step_id="read",
            tool_ref=READ_FILE_REF,
            arguments={"path": "src/alpha.txt"},
            surface=Surface.CHAT,
            mode="agent",
            candidate_tool_refs=(READ_FILE_REF,),
        ),
    ),
    raises(
        ToolCallPreparationError,
        lambda: runtime.catalog.prepare_call(
            call_id="call-mode",
            run_id="run-mode",
            step_id="read",
            tool_ref=READ_FILE_REF,
            arguments={"path": "src/alpha.txt"},
            surface=Surface.DEVELOPER,
            mode="chat",
            candidate_tool_refs=(READ_FILE_REF,),
        ),
    ),
    raises(
        ToolCallPreparationError,
        lambda: runtime.catalog.prepare_call(
            call_id="call-allowlist",
            run_id="run-allowlist",
            step_id="read",
            tool_ref=READ_FILE_REF,
            arguments={"path": "src/alpha.txt"},
            surface=Surface.DEVELOPER,
            mode="agent",
            candidate_tool_refs=(LIST_FILES_REF,),
        ),
    ),
)
ok(
    "malformed absolute drive-relative wrong-surface wrong-mode and non-allowlisted calls invoke nothing",
    all(error is not None for error in invalid_calls) and not broker_events,
    invalid_calls,
)

read_result = execute_read(
    runtime,
    repository,
    run_id="run-file-read",
    tool_ref=READ_FILE_REF,
    arguments={"path": "src/alpha.txt"},
    target="file:src/alpha.txt",
)
ok(
    "real broker read returns schema-validated content and file evidence without a receipt",
    read_result.status == "succeeded"
    and read_result.typed_output
    == {"path": "src/alpha.txt", "content": "alpha line\n", "bytes": 11}
    and read_result.evidence_refs == ("file:src/alpha.txt",)
    and read_result.receipt_id is None
    and broker_events[-1]
    == ("tool_read", {"path": "src/alpha.txt", "bytes": 11}),
    read_result,
)

list_result = execute_read(
    runtime,
    repository,
    run_id="run-file-list",
    tool_ref=LIST_FILES_REF,
    arguments={"prefix": "src", "limit": 2},
    target="files:src",
)
ok(
    "real broker listing stays sorted bounded and excludes policy-hidden files",
    list_result.status == "succeeded"
    and list_result.typed_output
    == {"files": ["src/alpha.txt", "src/beta.py"], "truncated": True}
    and list_result.evidence_refs == ("files:collection",)
    and list_result.receipt_id is None
    and broker_events[-1] == ("tool_list", {"prefix": "src", "count": 2})
    and ".env" not in list_result.typed_output["files"],
    list_result,
)

event_count = len(broker_events)
denied_result = execute_read(
    runtime,
    repository,
    run_id="run-file-denied",
    tool_ref=READ_FILE_REF,
    arguments={"path": "src/alpha.txt"},
    target="file:src/alpha.txt",
    permissions=(),
)
ok(
    "central policy denial blocks the broker before any file access",
    denied_result.status == "blocked"
    and denied_result.error is not None
    and denied_result.error.code == "tool.policy_denied"
    and len(broker_events) == event_count,
    denied_result,
)

(worktree / "large.txt").write_text("x" * (broker.max_file_bytes + 1), encoding="utf-8")
failure_cases = (
    (
        "run-file-traversal",
        READ_FILE_REF,
        {"path": "../../outside.txt"},
        "file:../../outside.txt",
        "TOBI could not read that project file. Check that the path exists and is allowed.",
    ),
    (
        "run-file-excluded",
        READ_FILE_REF,
        {"path": ".env"},
        "file:.env",
        "TOBI could not read that project file. Check that the path exists and is allowed.",
    ),
    (
        "run-file-missing",
        READ_FILE_REF,
        {"path": "src/missing.txt"},
        "file:src/missing.txt",
        "TOBI could not read that project file. Check that the path exists and is allowed.",
    ),
    (
        "run-file-oversized",
        READ_FILE_REF,
        {"path": "large.txt"},
        "file:large.txt",
        "TOBI could not read that project file. Check that the path exists and is allowed.",
    ),
    (
        "run-file-not-directory",
        LIST_FILES_REF,
        {"prefix": "src/alpha.txt"},
        "files:src/alpha.txt",
        "TOBI could not list that project folder. Check that the folder exists and is allowed.",
    ),
)
failed_results = [
    execute_read(
        runtime,
        repository,
        run_id=run_id,
        tool_ref=tool_ref,
        arguments=arguments,
        target=target,
    )
    for run_id, tool_ref, arguments, target, _owner_message in failure_cases
]
failure_json = json.dumps(contract_to_dict(failed_results), sort_keys=True)
ok(
    "broker path excluded missing oversized and non-folder failures are truthful and sanitized",
    all(result.status == "failed" for result in failed_results)
    and all(result.error is not None for result in failed_results)
    and all(result.error.code == "tool.read_failed" for result in failed_results if result.error)
    and all(
        result.error.owner_message == case[4]
        for result, case in zip(failed_results, failure_cases)
        if result.error
    )
    and len(broker_events) == event_count
    and secret_value not in failure_json
    and "outside-secret-content" not in failure_json
    and str(worktree).lower() not in failure_json.lower(),
    failure_json,
)

read_events = list_run_events("run-file-read")
read_event_json = json.dumps(contract_to_dict(read_events), sort_keys=True)
ok(
    "policy and runtime events are ordered and exclude file content and absolute paths",
    [event.sequence for event in read_events]
    == sorted(event.sequence for event in read_events)
    and any(event.event_type == "policy.decided" for event in read_events)
    and "alpha line" not in read_event_json
    and "[REDACTED]" in read_event_json
    and secret_value not in read_event_json
    and str(worktree).lower() not in read_event_json.lower(),
    read_event_json,
)

ok(
    "all file reads remain receipt-free and create no idempotency reservation",
    query_count("mc_action_receipts") == 0 and query_count("mc_idempotency") == 0,
)

file_runtime_path = (ROOT / "core" / "runtime" / "file_tools.py").resolve()
live_imports: list[str] = []
for source_root in (ROOT / "core", ROOT / "api"):
    for source_path in source_root.rglob("*.py"):
        if source_path.resolve() == file_runtime_path:
            continue
        source = source_path.read_text(encoding="utf-8", errors="ignore")
        if "core.runtime.file_tools" in source or "runtime.file_tools import" in source:
            live_imports.append(source_path.relative_to(ROOT).as_posix())
ok(
    "new file execution path remains dormant with no live imports",
    live_imports == [],
    live_imports,
)

print(f"\n{PASS}/9 T07 RUN 2A FILE TOOL CHECKS PASS")

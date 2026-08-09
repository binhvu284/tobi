"""Acceptance checks for #21 T07 Runs 2A-2B dormant file execution."""
from __future__ import annotations

import hashlib
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

TMP = Path(tempfile.mkdtemp(prefix="tobi_t07_run2a_"))
os.environ["DB_PATH"] = str(TMP / "agent.db")

from core.coding_policy import CodingPolicy  # noqa: E402
from core.coding_tools import CodingToolBroker  # noqa: E402
from core.database import get_connection, init_database  # noqa: E402
from core.runtime.actions import ActionConflictError  # noqa: E402
from core.runtime.control import RuntimeControl  # noqa: E402
from core.runtime.contracts import (  # noqa: E402
    ApprovalMode,
    ApprovalStatus,
    BudgetStatus,
    Certainty,
    ExecutionPlan,
    IsolationLevel,
    LoopPolicy,
    LoopRecipe,
    LoopType,
    PlanStep,
    PolicyEffect,
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
    WRITE_FILE_REF,
    build_file_tool_runtime,
)
from core.runtime.repository import RuntimeRepository  # noqa: E402
from core.runtime.state import RunStatus  # noqa: E402
from core.runtime.tool_catalog import ToolCallPreparationError  # noqa: E402
from core.runtime.tool_execution import ToolExecutionError  # noqa: E402


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


def query_one(sql: str, parameters: tuple = ()) -> sqlite3.Row | None:
    conn = get_connection()
    try:
        return conn.execute(sql, parameters).fetchone()
    finally:
        conn.close()


def prepare_run(
    repository: RuntimeRepository,
    run_id: str,
    *,
    step_id: str,
    tool_ref: str,
    arguments: dict,
    idempotency_key: str | None = None,
) -> dict:
    recipe = LoopRecipe(
        recipe_id=f"recipe-{run_id}",
        version="1",
        name="File tool fixture",
        loop_type=LoopType.TURN,
        trigger="owner request",
        objective="Use one approved worktree path safely",
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
            message="Use one project file",
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
            objective="Use one approved worktree path safely",
            steps=(
                PlanStep(
                    step_id=step_id,
                    kind="tool",
                    risk=RiskLevel.MEDIUM if idempotency_key else RiskLevel.NONE,
                    tool_name=tool_ref,
                    arguments=arguments,
                    retry_policy="none",
                    idempotency_key=idempotency_key,
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
    approval_status: ApprovalStatus = ApprovalStatus.NONE,
    approval_id: str | None = None,
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
        approval_status=approval_status,
        approval_id=approval_id,
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


def prepare_write(
    runtime,
    repository: RuntimeRepository,
    *,
    run_id: str,
    arguments: dict,
    approval_status: ApprovalStatus = ApprovalStatus.APPROVED,
    approval_id: str | None = None,
):
    step_id = f"step-{run_id}"
    idempotency_key = f"effect-{run_id}"
    lease = prepare_run(
        repository,
        run_id,
        step_id=step_id,
        tool_ref=WRITE_FILE_REF,
        arguments=arguments,
        idempotency_key=idempotency_key,
    )
    call = runtime.catalog.prepare_call(
        call_id=f"call-{run_id}",
        run_id=run_id,
        step_id=step_id,
        tool_ref=WRITE_FILE_REF,
        arguments=arguments,
        surface=Surface.DEVELOPER,
        mode="agent",
        candidate_tool_refs=(WRITE_FILE_REF,),
        idempotency_key=idempotency_key,
        approval_id=approval_id,
    )
    facts = policy_input(
        runtime,
        decision_id=f"policy-{run_id}",
        run_id=run_id,
        step_id=step_id,
        tool_ref=WRITE_FILE_REF,
        target=f"file:{arguments['path']}",
        permissions=("files.write",),
        approval_status=approval_status,
        approval_id=approval_id,
    )
    return call, facts, lease


def execute_prepared(runtime, call, facts, lease):
    return runtime.executor.execute(
        call,
        facts,
        worker_id=lease["worker_id"],
        lease_token=lease["lease_token"],
        lease_epoch=lease["lease_epoch"],
    )


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


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
    refs == (LIST_FILES_REF, READ_FILE_REF, WRITE_FILE_REF)
    and all(spec.allowed_surfaces == (Surface.DEVELOPER,) for spec in specs)
    and all(spec.allowed_modes == ("agent",) for spec in specs)
    and all(spec.isolation == "workspace" for spec in specs)
    and runtime.catalog.get_spec(READ_FILE_REF).required_permissions == ("files.read",)
    and runtime.catalog.get_spec(LIST_FILES_REF).required_permissions == ("files.read",)
    and runtime.catalog.get_spec(WRITE_FILE_REF).required_permissions == ("files.write",)
    and runtime.catalog.get_spec(WRITE_FILE_REF).risk is RiskLevel.MEDIUM
    and runtime.catalog.get_spec(WRITE_FILE_REF).idempotency_policy == "required"
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
    raises(
        ToolCallPreparationError,
        lambda: runtime.catalog.prepare_call(
            call_id="call-write-missing-precondition",
            run_id="run-write-missing-precondition",
            step_id="write",
            tool_ref=WRITE_FILE_REF,
            arguments={"path": "src/new.txt", "content": "new"},
            surface=Surface.DEVELOPER,
            mode="agent",
            candidate_tool_refs=(WRITE_FILE_REF,),
            idempotency_key="effect-write-missing-precondition",
        ),
    ),
    raises(
        ToolCallPreparationError,
        lambda: runtime.catalog.prepare_call(
            call_id="call-write-absolute",
            run_id="run-write-absolute",
            step_id="write",
            tool_ref=WRITE_FILE_REF,
            arguments={
                "path": "C:/outside.txt",
                "content": "blocked",
                "expected_sha256": "absent",
            },
            surface=Surface.DEVELOPER,
            mode="agent",
            candidate_tool_refs=(WRITE_FILE_REF,),
            idempotency_key="effect-write-absolute",
        ),
    ),
    raises(
        ToolCallPreparationError,
        lambda: runtime.catalog.prepare_call(
            call_id="call-write-oversized",
            run_id="run-write-oversized",
            step_id="write",
            tool_ref=WRITE_FILE_REF,
            arguments={
                "path": "src/oversized.txt",
                "content": "x" * 250_001,
                "expected_sha256": "absent",
            },
            surface=Surface.DEVELOPER,
            mode="agent",
            candidate_tool_refs=(WRITE_FILE_REF,),
            idempotency_key="effect-write-oversized",
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

approval_path = worktree / "src" / "approval.txt"
approval_call, approval_facts, approval_lease = prepare_write(
    runtime,
    repository,
    run_id="file-write-approval",
    arguments={"path": "src/approval.txt", "content": "not yet\n", "expected_sha256": "absent"},
    approval_status=ApprovalStatus.NONE,
)
approval_events = len(broker_events)
approval_result = execute_prepared(runtime, approval_call, approval_facts, approval_lease)
ok(
    "file mutation requires approval before reservation or broker access",
    approval_result.status == "blocked"
    and approval_result.error is not None
    and approval_result.error.code == "tool.approval_required"
    and not approval_path.exists()
    and len(broker_events) == approval_events
    and query_one(
        "SELECT effect FROM mc_policy_decisions WHERE decision_id='policy-file-write-approval'"
    )["effect"]
    == PolicyEffect.REQUIRE_APPROVAL.value
    and query_one(
        "SELECT COUNT(*) AS count FROM mc_idempotency WHERE idempotency_key='effect-file-write-approval'"
    )["count"]
    == 0,
    approval_result,
)

before_text = (worktree / "src" / "alpha.txt").read_text(encoding="utf-8")
after_text = "updated alpha\n"
before_hash = sha256_text(before_text)
after_hash = sha256_text(after_text)
write_arguments = {
    "path": "src/alpha.txt",
    "content": after_text,
    "expected_sha256": before_hash,
}
write_call, write_facts, write_lease = prepare_write(
    runtime,
    repository,
    run_id="file-write-success",
    arguments=write_arguments,
    approval_id="approval-file-write-success",
)
write_result = execute_prepared(runtime, write_call, write_facts, write_lease)
write_receipt = query_one(
    "SELECT * FROM mc_action_receipts WHERE receipt_id=?", (write_result.receipt_id,)
)
write_action = query_one(
    "SELECT request_json,status,execution_count FROM mc_idempotency "
    "WHERE idempotency_key='effect-file-write-success'"
)
write_request = json.loads(write_action["request_json"])
write_event_json = json.dumps(
    contract_to_dict(list_run_events("file-write-success")), sort_keys=True
)
ok(
    "approved overwrite records bounded hashes and one immutable receipt without durable content",
    write_result.status == "succeeded"
    and write_result.typed_output
    == {
        "path": "src/alpha.txt",
        "bytes": len(after_text.encode("utf-8")),
        "before_sha256": before_hash,
        "after_sha256": after_hash,
    }
    and (worktree / "src" / "alpha.txt").read_text(encoding="utf-8") == after_text
    and write_receipt["before_ref"] == f"file:src/alpha.txt@sha256:{before_hash}"
    and write_receipt["after_ref"] == f"file:src/alpha.txt@sha256:{after_hash}"
    and write_receipt["external_ref"] == "file:src/alpha.txt"
    and write_receipt["approval_ref"] == "approval-file-write-success"
    and write_action["status"] == "completed"
    and write_request["validated_arguments"]["content"] == "[REDACTED]"
    and write_request["validated_arguments"]["content_sha256"] == after_hash
    and after_text not in write_action["request_json"]
    and after_text not in write_event_json
    and metadata_json.find(after_text) == -1,
    write_result,
)

replay_event_count = len(broker_events)
replayed_write = runtime.executor.execute(
    write_call,
    write_facts,
    worker_id="replay-worker",
    lease_token="unused-completed-replay",
    lease_epoch=99,
)
changed_call = runtime.catalog.prepare_call(
    call_id=write_call.call_id,
    run_id=write_call.run_id,
    step_id=write_call.step_id,
    tool_ref=WRITE_FILE_REF,
    arguments={**write_arguments, "content": "changed duplicate\n"},
    surface=Surface.DEVELOPER,
    mode="agent",
    candidate_tool_refs=(WRITE_FILE_REF,),
    idempotency_key=write_call.idempotency_key,
    approval_id=write_call.approval_id,
)
changed_write = raises(
    ActionConflictError,
    lambda: runtime.executor.execute(
        changed_call,
        replace(write_facts, decision_id="policy-file-write-changed"),
        worker_id="changed-worker",
        lease_token="unused-changed-call",
        lease_epoch=100,
    ),
)
ok(
    "completed write replay is side-effect free and changed content conflicts",
    replayed_write == write_result
    and changed_write is not None
    and len(broker_events) == replay_event_count
    and (worktree / "src" / "alpha.txt").read_text(encoding="utf-8") == after_text
    and query_one(
        "SELECT execution_count FROM mc_idempotency "
        "WHERE idempotency_key='effect-file-write-success'"
    )["execution_count"]
    == 1,
)

stale_before = (worktree / "src" / "beta.py").read_text(encoding="utf-8")
stale_call, stale_facts, stale_lease = prepare_write(
    runtime,
    repository,
    run_id="file-write-stale",
    arguments={
        "path": "src/beta.py",
        "content": "VALUE = 3\n",
        "expected_sha256": "0" * 64,
    },
    approval_id="approval-file-write-stale",
)
stale_result = execute_prepared(runtime, stale_call, stale_facts, stale_lease)
ok(
    "stale precondition cannot overwrite a newer file and records not-applied",
    stale_result.status == "failed"
    and stale_result.retryable
    and stale_result.error is not None
    and stale_result.error.code == "tool.action_not_applied"
    and (worktree / "src" / "beta.py").read_text(encoding="utf-8") == stale_before
    and query_one(
        "SELECT status FROM mc_idempotency WHERE idempotency_key='effect-file-write-stale'"
    )["status"]
    == "retry_allowed",
    stale_result,
)

outside_before = (repo_root / "outside.txt").read_text(encoding="utf-8")
traversal_call, traversal_facts, traversal_lease = prepare_write(
    runtime,
    repository,
    run_id="file-write-traversal",
    arguments={
        "path": "../../outside.txt",
        "content": "must stay inside\n",
        "expected_sha256": "absent",
    },
    approval_id="approval-file-write-traversal",
)
traversal_result = execute_prepared(
    runtime, traversal_call, traversal_facts, traversal_lease
)
forbidden_path = worktree / ".git" / "config"
forbidden_path.parent.mkdir(parents=True, exist_ok=True)
forbidden_path.write_bytes(b"forbidden\n")
forbidden_call, forbidden_facts, forbidden_lease = prepare_write(
    runtime,
    repository,
    run_id="file-write-forbidden",
    arguments={
        "path": ".git/config",
        "content": "must not change\n",
        "expected_sha256": sha256_text("forbidden\n"),
    },
    approval_id="approval-file-write-forbidden",
)
forbidden_result = execute_prepared(
    runtime, forbidden_call, forbidden_facts, forbidden_lease
)
ok(
    "traversal and forbidden write attempts remain blocked without changing disk",
    traversal_result.status == "blocked"
    and forbidden_result.status == "blocked"
    and (repo_root / "outside.txt").read_text(encoding="utf-8") == outside_before
    and forbidden_path.read_bytes() == b"forbidden\n"
    and query_one(
        "SELECT status FROM mc_idempotency WHERE idempotency_key='effect-file-write-traversal'"
    )["status"]
    == "reconciliation_required"
    and query_one(
        "SELECT status FROM mc_idempotency WHERE idempotency_key='effect-file-write-forbidden'"
    )["status"]
    == "reconciliation_required",
    (traversal_result, forbidden_result),
)

protected_path = worktree / "core" / "coding_tools.py"
protected_path.parent.mkdir(parents=True, exist_ok=True)
protected_path.write_bytes(b"protected\n")
protected_call, protected_facts, protected_lease = prepare_write(
    runtime,
    repository,
    run_id="file-write-protected",
    arguments={
        "path": "core/coding_tools.py",
        "content": "must not change\n",
        "expected_sha256": sha256_text("protected\n"),
    },
    approval_id="approval-file-write-protected",
)
protected_result = execute_prepared(runtime, protected_call, protected_facts, protected_lease)
protected_reconciliation = runtime.executor.reconcile_action(
    protected_call, actor="owner"
)
ok(
    "broker protected-path denial changes nothing and records not-applied evidence",
    protected_result.status == "blocked"
    and protected_result.error is not None
    and protected_result.error.code == "tool.action_reconciliation_required"
    and protected_path.read_text(encoding="utf-8") == "protected\n"
    and protected_reconciliation.status == "failed"
    and protected_reconciliation.retryable
    and query_one(
        "SELECT status FROM mc_idempotency WHERE idempotency_key='effect-file-write-protected'"
    )["status"]
    == "retry_allowed",
    protected_result,
)


class FailOnceControl(RuntimeControl):
    def __init__(self) -> None:
        self.fail = True

    def record_step_success(self, *args, **kwargs):
        if self.fail:
            self.fail = False
            raise RuntimeError("simulated receipt-storage crash")
        return super().record_step_success(*args, **kwargs)


crash_control = FailOnceControl()
crash_runtime = build_file_tool_runtime(broker=broker, control=crash_control)
crash_arguments = {
    "path": "src/crash.txt",
    "content": "written before crash\n",
    "expected_sha256": "absent",
}
crash_call, crash_facts, crash_lease = prepare_write(
    crash_runtime,
    repository,
    run_id="file-write-crash-applied",
    arguments=crash_arguments,
    approval_id="approval-file-write-crash",
)
crash_error = raises(
    RuntimeError,
    lambda: execute_prepared(crash_runtime, crash_call, crash_facts, crash_lease),
)
events_after_crash = len(broker_events)
blocked_retry = crash_runtime.executor.execute(
    crash_call,
    crash_facts,
    worker_id="blocked-retry-worker",
    lease_token="unused-blocked-retry",
    lease_epoch=101,
)
applied_reconciliation = crash_runtime.executor.reconcile_action(
    crash_call, actor="owner"
)
ok(
    "after-write crash blocks replay then reconciles applied without a second write",
    crash_error is not None
    and (worktree / "src" / "crash.txt").read_text(encoding="utf-8")
    == crash_arguments["content"]
    and blocked_retry.status == "blocked"
    and blocked_retry.error is not None
    and blocked_retry.error.code == "tool.action_reconciliation_required"
    and applied_reconciliation.status == "succeeded"
    and applied_reconciliation.typed_output["after_sha256"]
    == sha256_text(crash_arguments["content"])
    and len(broker_events) == events_after_crash + 1
    and query_one(
        "SELECT COUNT(*) AS count FROM mc_action_receipts "
        "WHERE idempotency_key='effect-file-write-crash-applied'"
    )["count"]
    == 1,
    applied_reconciliation,
)


class FaultBroker:
    def __init__(self, delegate: CodingToolBroker) -> None:
        self.delegate = delegate
        self.fail_write = True
        self.write_attempts = 0

    def read_file(self, path: str):
        return self.delegate.read_file(path)

    def list_files(self, prefix: str = "", limit: int = 200):
        return self.delegate.list_files(prefix, limit)

    def write_file(self, path: str, content: str):
        self.write_attempts += 1
        if self.fail_write:
            raise RuntimeError("simulated failure before write")
        return self.delegate.write_file(path, content)


fault_broker = FaultBroker(broker)
fault_runtime = build_file_tool_runtime(broker=fault_broker)
not_applied_before = (worktree / "src" / "gamma.md").read_text(encoding="utf-8")
not_applied_arguments = {
    "path": "src/gamma.md",
    "content": "gamma updated\n",
    "expected_sha256": sha256_text(not_applied_before),
}
not_applied_call, not_applied_facts, not_applied_lease = prepare_write(
    fault_runtime,
    repository,
    run_id="file-write-crash-not-applied",
    arguments=not_applied_arguments,
    approval_id="approval-file-write-not-applied",
)
not_applied_initial = execute_prepared(
    fault_runtime, not_applied_call, not_applied_facts, not_applied_lease
)
not_applied_reconciliation = fault_runtime.executor.reconcile_action(
    not_applied_call, actor="owner"
)
fault_broker.fail_write = False
retry_lease = repository.claim_step(
    not_applied_call.run_id, worker_id="file-write-retry-worker"
)
assert retry_lease is not None
not_applied_retry = fault_runtime.executor.execute(
    not_applied_call,
    replace(not_applied_facts, decision_id="policy-file-write-not-applied-retry"),
    worker_id=retry_lease["worker_id"],
    lease_token=retry_lease["lease_token"],
    lease_epoch=retry_lease["lease_epoch"],
)
ok(
    "before-hash reconciliation permits exactly one later write",
    not_applied_initial.status == "blocked"
    and not_applied_reconciliation.status == "failed"
    and not_applied_reconciliation.retryable
    and not_applied_retry.status == "succeeded"
    and fault_broker.write_attempts == 2
    and (worktree / "src" / "gamma.md").read_text(encoding="utf-8")
    == not_applied_arguments["content"]
    and query_one(
        "SELECT execution_count,status FROM mc_idempotency "
        "WHERE idempotency_key='effect-file-write-crash-not-applied'"
    )["execution_count"]
    == 2,
    not_applied_retry,
)

unknown_path = worktree / "src" / "unknown.txt"
unknown_path.write_bytes(b"before unknown\n")
unknown_broker = FaultBroker(broker)
unknown_runtime = build_file_tool_runtime(broker=unknown_broker)
unknown_arguments = {
    "path": "src/unknown.txt",
    "content": "intended unknown\n",
    "expected_sha256": sha256_text("before unknown\n"),
}
unknown_call, unknown_facts, unknown_lease = prepare_write(
    unknown_runtime,
    repository,
    run_id="file-write-crash-unknown",
    arguments=unknown_arguments,
    approval_id="approval-file-write-unknown",
)
unknown_initial = execute_prepared(
    unknown_runtime, unknown_call, unknown_facts, unknown_lease
)
unknown_path.write_bytes(b"third state\n")
unknown_reconciliation = unknown_runtime.executor.reconcile_action(
    unknown_call, actor="owner"
)
unknown_retry = unknown_runtime.executor.execute(
    unknown_call,
    unknown_facts,
    worker_id="unknown-retry-worker",
    lease_token="unused-unknown-retry",
    lease_epoch=102,
)
ok(
    "third-state reconciliation remains unknown and cannot write again",
    unknown_initial.status == "blocked"
    and unknown_reconciliation.status == "blocked"
    and unknown_reconciliation.error is not None
    and unknown_reconciliation.error.code == "tool.action_reconciliation_required"
    and unknown_retry.status == "blocked"
    and unknown_broker.write_attempts == 1
    and unknown_path.read_text(encoding="utf-8") == "third state\n"
    and query_one(
        "SELECT status FROM mc_idempotency WHERE idempotency_key='effect-file-write-crash-unknown'"
    )["status"]
    == "reconciliation_required",
    unknown_reconciliation,
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

print(f"\n{PASS}/{PASS} T07 RUNS 2A-2B FILE TOOL CHECKS PASS")

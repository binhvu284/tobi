"""Acceptance checks for #34/T02 deterministic supported-workflow routing."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TMP = tempfile.mkdtemp(prefix="tobival_t02_")
os.environ["DB_PATH"] = os.path.join(TMP, "agent.db")

from core.chat_runtime import route_supported_turn  # noqa: E402
from core.chat_runtime_contracts import TurnRequest  # noqa: E402
from core.database import init_database  # noqa: E402
from core.runtime.contracts import LoopPolicy, LoopRecipe, LoopType, RunRequest, Surface  # noqa: E402
from core.runtime.eval_dataset import load_frozen_cases  # noqa: E402
from core.runtime.eval_runner import _trace_refs  # noqa: E402
from core.runtime.event_store import append_run_event  # noqa: E402
from core.runtime.repository import RuntimeRepository  # noqa: E402
from core.runtime.trace import build_run_trace  # noqa: E402
from core.runtime.workflows import (  # noqa: E402
    WorkflowBoundaryError,
    supported_workflow_catalog,
)
from core.task_classifier import classify_workflow  # noqa: E402


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


catalog = supported_workflow_catalog()
definitions = catalog.definitions
expected_fields = {
    "workflow_id", "version", "intents", "required_fields", "allowed_tools",
    "policy_class", "stop_condition", "success_evidence", "recovery_options",
    "summary_shape",
}
ok("the frozen catalog exposes exactly 21 unique v1 workflows", (
    len(definitions) == 21
    and len({item.workflow_id for item in definitions}) == 21
    and {item.version for item in definitions} == {"1"}
))
ok("every workflow owns the complete deterministic contract", all(
    set(item.to_dict()) == expected_fields
    and item.intents
    and item.policy_class
    and item.stop_condition
    and item.success_evidence
    and item.recovery_options
    and item.summary_shape
    for item in definitions
))
ok("all 46 accepted intents select their owning workflow", all(
    (selection := catalog.select(intent)).workflow is not None
    and selection.workflow.workflow_id == item.workflow_id
    for item in definitions
    for intent in item.intents
))
ok("every development case points to a catalog workflow", (
    {case.workflow_id for case in load_frozen_cases("v1")}
    <= {item.workflow_id for item in definitions}
))

project_list = catalog.select("Please list projects")
terminal_run = catalog.select("run approved command", {"command": "Get-Date"})
run_recovery = catalog.select(
    "resume run", {"run_id": "run-42", "operation": "resume"},
)
ok("known requests route with no model", (
    project_list.status == "matched" and project_list.workflow.workflow_id == "project.list"
    and terminal_run.status == "matched" and terminal_run.workflow.workflow_id == "terminal.typed_command"
    and run_recovery.status == "matched" and run_recovery.workflow.workflow_id == "run.recover"
))

missing = catalog.select("create task", {"title": "Ship T02"})
ok("missing required fields clarify instead of guessing", (
    missing.status == "clarify"
    and missing.workflow.workflow_id == "task.create"
    and missing.missing_fields == ("project_id",)
))
ambiguous = catalog.select("list projects and show tasks")
ok("equal-specificity workflow matches clarify as ambiguous", (
    ambiguous.status == "clarify"
    and ambiguous.reason.startswith("ambiguous:")
    and set(ambiguous.candidate_workflow_ids) == {"project.list", "task.list"}
))
unsupported = catalog.select("Compare quantum error correction papers")
ok("open-ended unsupported work is reported instead of guessed", (
    unsupported.status == "unsupported" and unsupported.workflow is None
))

ok("a proposed workflow cannot escape deterministic selection", raises(
    WorkflowBoundaryError,
    lambda: catalog.enforce(terminal_run, proposed_workflow_id="file.read"),
))
ok("a proposed tool cannot escape the workflow allowlist", raises(
    WorkflowBoundaryError,
    lambda: catalog.enforce(terminal_run, proposed_tools=("tobi.files.read_file@1",)),
))
bounded = catalog.enforce(
    terminal_run, proposed_tools=("tobi.terminal.run_command@1",),
)
default_boundary = catalog.enforce(terminal_run)
ok("an allowed proposal stays inside the workflow boundary", (
    bounded.allowed_tools == ("tobi.terminal.run_command@1",)
    and default_boundary.allowed_tools == (
        "tobi.terminal.run_command@1", "tobi.terminal.run_command@2",
    )
))

classified = classify_workflow("show projects")
ok("the existing task classifier exposes deterministic workflow selection", (
    classified.status == "matched" and classified.workflow.workflow_id == "project.list"
))
chat_action = route_supported_turn(
    TurnRequest(session_id=1, message="create task", mode="chat"),
    fields={"project_id": "project-1", "title": "Ship T02"},
)
agent_action = route_supported_turn(
    TurnRequest(session_id=1, message="create task", mode="agent"),
    fields={"project_id": "project-1", "title": "Ship T02"},
)
ok("the additive Chat adapter keeps mutations behind Agent mode", (
    chat_action.route == "clarify" and chat_action.requires_clarification
    and agent_action.route == "action"
    and agent_action.allowed_tools == ("tobi.projects.create_task@1",)
))

init_database()
runtime = RuntimeRepository()
recipe = LoopRecipe(
    recipe_id="tobival.workflow",
    version="1",
    name="TOBIval workflow",
    loop_type=LoopType.GOAL,
    trigger="test",
    objective="Record workflow selection",
    stop_condition="selection recorded",
    max_attempts=1,
    max_runtime_s=60,
    max_cost_usd=0,
)
runtime.save_loop_recipe(recipe)
runtime.create_run(
    RunRequest(
        request_id="t02-request",
        surface=Surface.CHAT,
        owner_id="owner",
        session_id="t02-session",
        mode="chat",
        message="List projects",
    ),
    loop_policy=LoopPolicy.from_recipe(
        "t02-policy", "1", recipe, "t02-decision", enabled=False,
    ),
    run_id="run-t02",
)
append_run_event(
    run_id="run-t02",
    event_type="workflow.selected",
    stage="route",
    actor="mission-control",
    payload=project_list.to_trace_payload(),
    event_id="t02-workflow",
    trace_id="trace-t02",
)
trace = build_run_trace("run-t02")
ok("workflow version and selection reason appear in canonical trace evidence", (
    trace.workflow_refs == ("workflow:project.list@v1",)
    and len(trace.selection_reason_refs) == 1
    and trace.selection_reason_refs[0].startswith("workflow-selection:")
    and set(trace.workflow_refs + trace.selection_reason_refs) <= _trace_refs(trace)
))

print(f"PASS: {PASS} TOBIval T02 workflow checks")

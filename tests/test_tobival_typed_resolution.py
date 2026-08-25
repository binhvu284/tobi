"""Acceptance checks for #34/T03 typed entity and argument resolution."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TMP = tempfile.mkdtemp(prefix="tobival_t03_")
os.environ["DB_PATH"] = os.path.join(TMP, "agent.db")

from core.database import get_connection, init_database  # noqa: E402
from core.runtime.contracts import RuntimeToolCall, Surface  # noqa: E402
from core.runtime.project_tools import CREATE_TASK_REF, LIST_PROJECTS_REF, build_project_tool_runtime  # noqa: E402
from core.runtime.typed_resolution import EntityRepository, TypedRequestResolver  # noqa: E402
from core.runtime.workflows import supported_workflow_catalog  # noqa: E402


PASS = 0


def ok(name: str, condition: bool, detail: object = "") -> None:
    global PASS
    if not condition:
        print(f"FAIL {name}: {detail}")
        raise SystemExit(1)
    PASS += 1
    print(f"PASS {name}")


init_database()
conn = get_connection()
try:
    def add_project(name: str) -> int:
        return int(conn.execute(
            "INSERT INTO pm_projects (name,status,size,category,created_by) VALUES (?,?,?,?,?)",
            (name, "active", "medium", "Engineering", "owner"),
        ).lastrowid)

    alpha_id = add_project("Alpha")
    beta_id = add_project("Beta")
    twin_a_id = add_project("Twin")
    twin_b_id = add_project("Twin")
    task_alpha_id = int(conn.execute(
        "INSERT INTO tasks (title,objective,status,status_v1,priority,priority_label,owner_label,agent_key,pm_project_id) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        ("Shared task", "Shared task", "pending", "planned", 5, "P2", "owner", "tobi", alpha_id),
    ).lastrowid)
    conn.execute(
        "INSERT INTO tasks (title,objective,status,status_v1,priority,priority_label,owner_label,agent_key,pm_project_id) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        ("Shared task", "Shared task", "pending", "planned", 5, "P2", "owner", "tobi", beta_id),
    )
    resource_id = int(conn.execute(
        "INSERT INTO pm_resources (project_id,kind,name,source,rtype,created_by) VALUES (?,?,?,?,?,?)",
        (alpha_id, "file", "Status.md", "device", "doc", "owner"),
    ).lastrowid)
    conn.commit()
finally:
    conn.close()

entities = EntityRepository()
by_id = entities.resolve("project", alpha_id)
by_numeric_text = entities.resolve("project", str(alpha_id))
by_name = entities.resolve("project", "Alpha")
ok("project IDs and exact names resolve to one canonical integer", (
    by_id.status == by_numeric_text.status == by_name.status == "resolved"
    and by_id.candidate.id == by_numeric_text.candidate.id == by_name.candidate.id == alpha_id
))

duplicates = entities.resolve("project", "Twin")
ok("multiple exact matches ask instead of choosing silently", (
    duplicates.status == "clarify"
    and {item.id for item in duplicates.choices} == {twin_a_id, twin_b_id}
    and len(duplicates.choices) <= 5
))
ok("invented and malformed IDs never resolve", (
    entities.resolve("project", 999999).status == "not_found"
    and entities.resolve("project", True).status == "invalid"
    and entities.resolve("project", "9" * 100).status == "invalid"
    and entities.resolve("project", "project-???").status == "not_found"
))

task_global = entities.resolve("task", "Shared task")
task_scoped = entities.resolve("task", task_alpha_id, project_id=alpha_id)
task_wrong_project = entities.resolve("task", task_alpha_id, project_id=beta_id)
resource_scoped = entities.resolve("resource", "Status.md", project_id=alpha_id)
ok("task and resource identities retain their project boundary", (
    task_global.status == "clarify"
    and task_scoped.status == "resolved"
    and task_scoped.candidate.parent_id == alpha_id
    and task_wrong_project.status == "not_found"
    and resource_scoped.status == "resolved"
    and resource_scoped.candidate.id == resource_id
    and resource_scoped.candidate.parent_id == alpha_id
))
missing_project = entities.resolve("project", None)
ok("missing identity returns bounded owner choices", (
    missing_project.status == "missing"
    and 1 <= len(missing_project.choices) <= 5
    and all(set(choice.to_dict()) == {"ref", "id", "label", "parent_ref"} for choice in missing_project.choices)
))

project_runtime = build_project_tool_runtime()
resolver = TypedRequestResolver(
    workflows=supported_workflow_catalog(),
    tools=project_runtime.catalog,
    entities=entities,
)

missing = resolver.resolve(
    message="create task",
    run_id="run-missing",
    step_id="create",
    call_id="call-missing",
    proposed_arguments={"title": "Review"},
    proposed_tool_ref=CREATE_TASK_REF,
    surface=Surface.CHAT,
    mode="agent",
)
ok("missing required entity stays a bounded clarification with no tool call", (
    missing.status == "clarify"
    and missing.accepted is None
    and missing.missing_fields == ("project_id",)
    and 1 <= len(missing.choices) <= 5
))

invented = resolver.resolve(
    message="create task",
    run_id="run-invented",
    step_id="create",
    call_id="call-invented",
    proposed_arguments={"project_id": 999999, "title": "Must not run"},
    proposed_tool_ref=CREATE_TASK_REF,
    surface=Surface.CHAT,
    mode="agent",
)
ok("an invented entity cannot become an executable request", (
    invented.status == "clarify" and invented.accepted is None
))

extra = resolver.resolve(
    message="create task",
    run_id="run-extra",
    step_id="create",
    call_id="call-extra",
    proposed_arguments={"project_id": alpha_id, "title": "Review", "admin": True},
    proposed_tool_ref=CREATE_TASK_REF,
    surface=Surface.CHAT,
    mode="agent",
)
wrong_type = resolver.resolve(
    message="create task",
    run_id="run-type",
    step_id="create",
    call_id="call-type",
    proposed_arguments={"project_id": alpha_id, "title": 42},
    proposed_tool_ref=CREATE_TASK_REF,
    surface=Surface.CHAT,
    mode="agent",
)
ok("unknown fields and schema-invalid types fail closed", (
    extra.status == "rejected" and extra.invalid_fields == ("admin",)
    and wrong_type.status == "rejected" and wrong_type.accepted is None
))

wrong_workflow = resolver.resolve(
    message="create task",
    run_id="run-boundary",
    step_id="create",
    call_id="call-boundary",
    proposed_arguments={"project_id": alpha_id, "title": "Review"},
    proposed_workflow_id="file.read",
    proposed_tool_ref=LIST_PROJECTS_REF,
    surface=Surface.CHAT,
    mode="agent",
)
ok("model-proposed workflow and tool escape is rejected", (
    wrong_workflow.status == "rejected" and wrong_workflow.accepted is None
))

proposal = {"project_id": "Alpha", "title": "Review"}
accepted_by_name = resolver.resolve(
    message="create task",
    run_id="run-accepted",
    step_id="create",
    call_id="call-name",
    proposed_arguments=proposal,
    proposed_workflow_id="task.create",
    proposed_tool_ref=CREATE_TASK_REF,
    surface=Surface.CHAT,
    mode="agent",
)
accepted_by_id = resolver.resolve(
    message="create task",
    run_id="run-accepted",
    step_id="create",
    call_id="call-id",
    proposed_arguments={"project_id": alpha_id, "title": "Review"},
    proposed_workflow_id="task.create",
    proposed_tool_ref=CREATE_TASK_REF,
    surface=Surface.CHAT,
    mode="agent",
)
ok("name and ID proposals from different model lanes produce one typed contract", (
    accepted_by_name.status == accepted_by_id.status == "accepted"
    and accepted_by_name.accepted.arguments == {"project_id": alpha_id, "title": "Review"}
    and accepted_by_name.accepted.contract_hash == accepted_by_id.accepted.contract_hash
    and accepted_by_name.accepted.idempotency_key == accepted_by_id.accepted.idempotency_key
))

proposal["title"] = "Changed outside"
copy_of_arguments = accepted_by_name.accepted.arguments
copy_of_arguments["title"] = "Changed copy"
runtime_call = accepted_by_name.accepted.to_runtime_call(project_runtime.catalog)
retry_call = accepted_by_name.accepted.to_runtime_call(project_runtime.catalog)
ok("accepted arguments are immutable copies and retries reuse the exact request", (
    isinstance(runtime_call, RuntimeToolCall)
    and runtime_call.validated_arguments == {"project_id": alpha_id, "title": "Review"}
    and retry_call.validated_arguments == runtime_call.validated_arguments
    and retry_call.idempotency_key == runtime_call.idempotency_key
    and retry_call.tool_ref == runtime_call.tool_ref == CREATE_TASK_REF
))

trace_payload = accepted_by_name.accepted.to_trace_payload()
serialized_trace = json.dumps(trace_payload, sort_keys=True)
ok("typed-request trace evidence is bounded and excludes argument values", (
    set(trace_payload) == {"typed_request_ref", "workflow_ref", "tool_ref"}
    and "Review" not in serialized_trace
    and "Alpha" not in serialized_trace
))

print(f"PASS: {PASS} TOBIval T03 typed-resolution checks")

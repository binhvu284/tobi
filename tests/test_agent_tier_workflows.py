"""Red-first checks for #35/T02 canonical local Agent workflows."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TMP = tempfile.mkdtemp(prefix="tobi_agent_tier_workflows_")
os.environ["DB_PATH"] = os.path.join(TMP, "agent-workflows.db")
os.environ["TOBI_AGENT_WORKSPACE"] = str(ROOT)

from core.database import get_connection, init_database  # noqa: E402

init_database()

from core import agent_tier, owner_flags  # noqa: E402
from core.chat_runtime_contracts import TurnRequest  # noqa: E402
from core.runtime.agent_workflows import (  # noqa: E402
    AgentWorkflowService,
    extract_agent_workflow_fields,
    qualify_agent_workflow,
)
from core.runtime.repository import RuntimeRepository  # noqa: E402


PASS = 0


def ok(name: str, condition: bool, detail="") -> None:
    global PASS
    if not condition:
        raise AssertionError(f"{name}: {detail}")
    PASS += 1
    print(f"PASS {name}")


def request(message: str, turn_id: str, **fields) -> TurnRequest:
    return TurnRequest(
        session_id=35,
        message=message,
        mode="agent",
        client_turn_id=turn_id,
        workflow_fields=fields,
    )


conn = get_connection()
project_id = conn.execute(
    "INSERT INTO pm_projects(name,status,size,category,created_by) VALUES (?,?,?,?,?)",
    ("T02 Project", "active", "medium", "Engineering", "owner"),
).lastrowid
conn.commit()
conn.close()

extracted = extract_agent_workflow_fields(
    'Create task "Inspect receipts" in project 1'
)
ok(
    "explicit owner fields are extracted without guessing hidden IDs",
    extracted == {"project_id": 1, "title": "Inspect receipts"},
    extracted,
)

missing = qualify_agent_workflow(request("create task", "turn-missing"))
ok(
    "missing project and title produce bounded clarification before a run exists",
    missing.status == "clarify"
    and set(missing.missing_fields) == {"project_id", "title"}
    and missing.run_id is None,
    missing,
)

unsupported = qualify_agent_workflow(request("write a poem", "turn-unsupported"))
ok(
    "unqualified Agent turns remain on the legacy path",
    unsupported.status == "unsupported" and unsupported.run_id is None,
    unsupported,
)

service = AgentWorkflowService()
listed = service.execute(request("list projects", "turn-project-list"))
ok(
    "Project execution enters canonical Runtime with a grounded typed result",
    listed.status == "succeeded"
    and listed.workflow_id == "project.list"
    and listed.family_id == "project_execution"
    and listed.run_id
    and listed.evidence_refs
    and "T02 Project" in listed.reply,
    listed,
)
project_run = RuntimeRepository().get_run(listed.run_id or "")
ok(
    "a successful Project result is durable and terminal",
    project_run is not None and project_run["status"] == "succeeded",
    project_run,
)

replayed = service.execute(request("list projects", "turn-project-list"))
ok(
    "the accepted typed request survives retry and reload without re-execution",
    replayed.status == "succeeded"
    and replayed.replayed is True
    and replayed.run_id == listed.run_id,
    replayed,
)

readme = ROOT / "agent-t02-proof.txt"
readme.write_text("bounded local evidence\n", encoding="utf-8")
try:
    local = service.execute(request("read file agent-t02-proof.txt", "turn-file-read"))
finally:
    readme.unlink(missing_ok=True)
ok(
    "local diagnosis reads only an explicit workspace-relative path through Runtime",
    local.status == "succeeded"
    and local.workflow_id == "file.read"
    and local.family_id == "local_diagnosis"
    and "bounded local evidence" in local.reply,
    local,
)

escaped = service.execute(request("read file ../outside.txt", "turn-file-escape"))
ok(
    "a path outside the approved workspace fails closed",
    escaped.status == "failed" and escaped.run_id is not None,
    escaped,
)

terminal = service.execute(request("terminal status", "turn-terminal-status"))
ok(
    "Terminal status completes through the canonical typed adapter",
    terminal.status == "succeeded"
    and terminal.workflow_id == "terminal.status"
    and terminal.family_id == "local_diagnosis",
    terminal,
)

coding = service.execute(
    request("coding workflow status", "turn-coding-status", workflow_id="35")
)
ok(
    "Coding maintenance enters Runtime as a read-only qualification check, not dispatch",
    coding.status in {"succeeded", "clarify"}
    and coding.workflow_id == "coding.qualify"
    and coding.family_id == "coding_maintenance"
    and coding.pending_action is None,
    coding,
)

pending = service.execute(request(
    f'create task "Canonical receipt" in project {project_id}',
    "turn-task-create",
))
ok(
    "a local mutation pauses on the existing owner approval card",
    pending.status == "waiting_approval"
    and pending.pending_action is not None
    and pending.pending_action.get("id")
    and pending.run_id,
    pending,
)

approved = service.resolve_pending_action(
    int(pending.pending_action["id"]), "approve"
)
ok(
    "owner approval resumes the same run and records an action receipt",
    approved.get("ok") is True
    and approved.get("status") == "executed"
    and approved.get("runtime_run_id") == pending.run_id
    and approved.get("receipt_id"),
    approved,
)
conn = get_connection()
created = conn.execute(
    "SELECT COUNT(*) FROM tasks WHERE pm_project_id=? AND title=?",
    (project_id, "Canonical receipt"),
).fetchone()[0]
conn.close()
ok("approved Project mutation executes exactly once", created == 1, created)

approved_replay = service.resolve_pending_action(
    int(pending.pending_action["id"]), "approve"
)
conn = get_connection()
created_after_replay = conn.execute(
    "SELECT COUNT(*) FROM tasks WHERE pm_project_id=? AND title=?",
    (project_id, "Canonical receipt"),
).fetchone()[0]
conn.close()
ok(
    "replaying approval cannot duplicate the side effect",
    approved_replay.get("status") == "executed" and created_after_replay == 1,
    approved_replay,
)

owner_flags.set_bool(owner_flags.AGENT_LOCAL_WORKFLOWS, False)
rolled_back = AgentWorkflowService().execute(
    request("list projects", "turn-rolled-back")
)
ok(
    "the scoped rollback switch returns qualified Agent work to legacy execution",
    rolled_back.status == "rollback" and rolled_back.run_id is None,
    rolled_back,
)
owner_flags.set_bool(owner_flags.AGENT_LOCAL_WORKFLOWS, True)

conn = get_connection()
execution = next(
    row for row in agent_tier.evaluate(conn, current_release="3.0")
    if row["id"] == "local_work_execution"
)
conn.close()
ok(
    "Tier II local execution remains evidence-backed instead of code-presence-backed",
    execution["status"] in {"partial", "active"}
    and execution["evidence"],
    execution,
)

api_source = (ROOT / "api/routers/chat.py").read_text(encoding="utf-8")
ok(
    "normal Mission Control Agent turns invoke the T02 service before the model loop",
    "AgentWorkflowService" in api_source and "agent_workflow_qualification" in api_source,
)

from fastapi.testclient import TestClient  # noqa: E402
from api.dashboard import app  # noqa: E402
from core import chat_store, conductor  # noqa: E402

client = TestClient(app)
config = client.post("/api/chat/config", json={
    "mode_v2": True,
    "chat_runtime_v2": "on",
    "agent_local_workflows": True,
}).json()
api_session = chat_store.create_session("Agent Tier T02 API")
model_calls: list[str] = []
original_answer = conductor.answer


def forbidden_model_call(message, *_args, **_kwargs):
    model_calls.append(message)
    raise AssertionError("a qualified T02 workflow reached the model loop")


conductor.answer = forbidden_model_call
try:
    streamed = client.post(
        f"/api/chat/sessions/{api_session['id']}/stream",
        json={
            "message": "list all project",
            "mode": "agent",
            "client_turn_id": "turn-live-agent-t02",
        },
    )
finally:
    conductor.answer = original_answer
ok(
    "a live Mission Control Agent request completes before the model loop",
    streamed.status_code == 200
    and "T02 Project" in streamed.text
    and '"model": "not_used"' in streamed.text
    and model_calls == [],
    streamed.text[:1000],
)
conn = get_connection()
live_runs = conn.execute(
    "SELECT run_id,status FROM mc_runs WHERE request_id=?",
    ("turn-live-agent-t02",),
).fetchall()
linked = conn.execute(
    "SELECT content,model FROM chat_messages WHERE runtime_run_id=?",
    (live_runs[0]["run_id"] if live_runs else "",),
).fetchone()
conn.close()
ok(
    "the live request creates one succeeded canonical run with one linked reply",
    len(live_runs) == 1
    and live_runs[0]["status"] == "succeeded"
    and linked is not None
    and linked["model"] == "not_used"
    and "T02 Project" in linked["content"],
    {"config": config, "runs": [dict(row) for row in live_runs], "linked": dict(linked) if linked else None},
)

replayed_stream = client.post(
    f"/api/chat/sessions/{api_session['id']}/stream",
    json={
        "message": "list all project",
        "mode": "agent",
        "client_turn_id": "turn-live-agent-t02",
    },
)
conn = get_connection()
message_counts = conn.execute(
    "SELECT role,COUNT(*) AS count FROM chat_messages WHERE session_id=? GROUP BY role",
    (api_session["id"],),
).fetchall()
run_count = conn.execute(
    "SELECT COUNT(*) FROM mc_runs WHERE request_id=?",
    ("turn-live-agent-t02",),
).fetchone()[0]
conn.close()
counts = {row["role"]: row["count"] for row in message_counts}
ok(
    "a repeated HTTP delivery replays without duplicate run, user message, or reply",
    replayed_stream.status_code == 200
    and '"replayed": true' in replayed_stream.text
    and run_count == 1
    and counts == {"assistant": 1, "user": 1},
    {"runs": run_count, "messages": counts, "response": replayed_stream.text[:700]},
)

print(f"PASS: {PASS} Agent Tier T02 workflow checks")

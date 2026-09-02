"""Red-first contract for #35/T02A Chat-to-Developer dispatch."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TMP = Path(tempfile.mkdtemp(prefix="tobi_chat_developer_dispatch_"))
os.environ["DB_PATH"] = str(TMP / "agent.db")

from core.database import get_connection, init_database  # noqa: E402

init_database()

from core import coding_queue, coding_queue_authoring, conductor, developer_dispatch  # noqa: E402
from core.developer_dispatch import DeveloperDispatchService  # noqa: E402
from core.development_store import DevelopmentStore  # noqa: E402


PASS = 0


def ok(name: str, condition: bool, detail="") -> None:
    global PASS
    if not condition:
        raise AssertionError(f"{name}: {detail}")
    PASS += 1
    print(f"PASS {name}")


queue_root = TMP / "queue-root"
queue_dir = queue_root / "docs" / "feature-idea-queue"
queue_dir.mkdir(parents=True)
queue_path = queue_dir / "QUEUE.md"
existing_plan = queue_dir / "EXISTING_PLAN.md"
existing_plan.write_text("# Existing\n", encoding="utf-8")
queue_path.write_text(
    "\n".join([
        "# Feature Development Queue",
        "",
        "| # | ID | Name | Description | Status | Notes |",
        "|---|----|------|-------------|--------|-------|",
        "| 36 | `FOUND-EXAMPLE-001` | [**Existing**](EXISTING_PLAN.md) | Existing item. | Queued | Existing. |",
        "",
    ]),
    encoding="utf-8",
)
original_queue_root = coding_queue.REPO_ROOT
original_queue_path = coding_queue.QUEUE_PATH
original_authoring_root = coding_queue_authoring.REPO_ROOT
original_authoring_path = coding_queue_authoring.QUEUE_PATH
try:
    coding_queue.REPO_ROOT = queue_root
    coding_queue.QUEUE_PATH = queue_path
    coding_queue_authoring.REPO_ROOT = queue_root
    coding_queue_authoring.QUEUE_PATH = queue_path
    authored = coding_queue_authoring.create_queue_item(
        title="Chat Developer repair",
        objective="Repair one confirmed Mission Control limitation through Developer.",
        acceptance_criteria=["the current Queue schema receives one parseable row"],
        expected_queue_hash=coding_queue_authoring.queue_hash(),
        source_note="Created from an owner-confirmed Mission Control Chat proposal.",
    )
finally:
    coding_queue.REPO_ROOT = original_queue_root
    coding_queue.QUEUE_PATH = original_queue_path
    coding_queue_authoring.REPO_ROOT = original_authoring_root
    coding_queue_authoring.QUEUE_PATH = original_authoring_path
authored_plan_text = (queue_root / authored["plan_path"]).read_text(encoding="utf-8")
ok(
    "confirmed Chat work authors the current Queue table schema",
    authored["queue_id"] == 37
    and authored["title"] == "Chat Developer repair"
    and authored["queue_status"].endswith("Draft")
    and "| 37 | `DEV-QUEUE-037` | [**Chat Developer repair**]" in queue_path.read_text(encoding="utf-8")
    and "Created from an owner-confirmed Mission Control Chat proposal." in queue_path.read_text(encoding="utf-8"),
    authored,
)
legacy_row = coding_queue_authoring._queue_row(
    ["#", "feature", "status", "solo time (full -> left)", "spec", "notes"],
    queue_id=2,
    title="Legacy item",
    objective="Preserve the archived queue contract.",
    effort="1 day -> same",
    plan_name="LEGACY_ITEM_PLAN.md",
    notes="Created in Developer Work.",
)
ok(
    "Developer authoring preserves the legacy Queue table schema",
    legacy_row == (
        "| 2 | **Legacy item** | Draft | 1 day -> same | "
        "[LEGACY_ITEM_PLAN.md](LEGACY_ITEM_PLAN.md) | Created in Developer Work. |"
    ),
    legacy_row,
)


class FakeDeveloperGateway:
    """Existing Developer control plane, without starting a coding worker in this test."""

    def __init__(self) -> None:
        self.queue_calls = 0
        self.preflight_calls = 0
        self.workflow_calls = 0
        self.start_calls = 0
        self.state = "coding"
        self.with_evidence = False

    def create_or_recover_queue_item(self, dispatch: dict) -> dict:
        self.queue_calls += 1
        return {"queue_id": 350, "plan_path": "docs/feature-idea-queue/T02A_TEST_PLAN.md"}

    def preflight(self, queue_id: int) -> dict:
        self.preflight_calls += 1
        return {"ready": True, "readiness_id": 7350, "blockers": [], "warnings": []}

    def create_workflow(self, queue_id: int, *, idempotency_key: str, readiness_id: int) -> dict:
        self.workflow_calls += 1
        return {"id": 8350, "queue_id": queue_id, "state": "approved", "stage": "approved"}

    def start_workflow(self, workflow_id: int) -> dict:
        self.start_calls += 1
        return self.get_workflow(workflow_id)

    def get_workflow(self, workflow_id: int) -> dict:
        checks = [{"ok": True, "argv": ["python", "tests/test_t02a.py"]}] if self.with_evidence else []
        return {
            "id": workflow_id,
            "queue_id": 350,
            "state": self.state,
            "stage": "code" if self.state == "coding" else self.state,
            "progress": 40 if self.state == "coding" else 100,
            "blocker": None,
            "error_code": None,
            "scorecard": {"checks": checks},
        }

    def changes(self, workflow_id: int) -> dict:
        return {"files": ["core/example.py"], "stat": "1 file changed"} if self.with_evidence else {"files": [], "stat": ""}

    def artifacts(self, workflow_id: int) -> list[dict]:
        return ([{"id": 1, "evidence_type": "test_report", "path": str(TMP / "report.json")}]
                if self.with_evidence else [])


fake = FakeDeveloperGateway()
DevelopmentStore(TMP / "agent.db")
developer_dispatch._gateway_factory = lambda: fake
service = DeveloperDispatchService()

direct_file = developer_dispatch.qualify_developer_request("create this Markdown file")
capability = developer_dispatch.qualify_developer_request("add Markdown creation capability")
ambiguous = developer_dispatch.qualify_developer_request("make Markdown creation")
common_ambiguous = developer_dispatch.qualify_developer_request("create a markdown creation feature")
bare_trigger = developer_dispatch.qualify_developer_request("use developer")
natural_with = developer_dispatch.qualify_developer_request("please fix it with Developer")
natural_handoff = developer_dispatch.qualify_developer_request("hand this to the Developer agent")
natural_send = developer_dispatch.qualify_developer_request("send this to developer")
ok("a direct file request stays outside Developer", direct_file.status == "unsupported", direct_file)
ok("a capability request enters Developer", capability.status == "accepted", capability)
ok("an ambiguous request asks one bounded question", ambiguous.status == "clarify" and ambiguous.question, ambiguous)
ok("common Markdown ambiguity asks before dispatch", common_ambiguous.status == "clarify", common_ambiguous)
ok("a bare Developer trigger asks for the objective", bare_trigger.status == "clarify", bare_trigger)
ok(
    "natural explicit Developer hand-offs are recognized",
    natural_with.status == "accepted"
    and natural_send.status == natural_handoff.status == "clarify",
    {"with": natural_with, "send": natural_send, "handoff": natural_handoff},
)
polite_explicit_cases = [
    "Can you use Developer to fix the Chat send button?",
    "Could you use Developer to add export support?",
    "Would you use Developer to fix this please?",
    "use developer to fix the send button, please?",
    "/developer: fix the login redirect",
]
degenerate_cases = [
    "use developer to ",
    "/developer .",
    "add a feature",
    "hand this to the Developer agent",
]
ok(
    "table-driven qualification accepts commands and clarifies missing objectives",
    all(developer_dispatch.qualify_developer_request(value).status == "accepted" for value in polite_explicit_cases)
    and all(developer_dispatch.qualify_developer_request(value).status == "clarify" for value in degenerate_cases),
    {
        "accepted": [(value, developer_dispatch.qualify_developer_request(value)) for value in polite_explicit_cases],
        "clarify": [(value, developer_dispatch.qualify_developer_request(value)) for value in degenerate_cases],
    },
)
wrapped_explicit_cases = [
    *(f"The page is slow. {value}" for value in polite_explicit_cases),
    *(f"{value}\n- detail" for value in polite_explicit_cases),
    "I noticed the Runs page is empty; use Developer to fix the Runs page query.",
]
ok(
    "explicit Developer commands survive surrounding sentences and lines",
    all(developer_dispatch.qualify_developer_request(value).status == "accepted" for value in wrapped_explicit_cases),
    [(value, developer_dispatch.qualify_developer_request(value)) for value in wrapped_explicit_cases],
)
multiline_explicit_cases = [
    "Use Developer to fix this:\n- send button\n- retry loop",
    "Use Developer to fix the send button\nIt fails on mobile",
    "/developer fix the send button\ncontext: mobile only",
]
ok(
    "multiline Developer commands qualify from their bounded instruction line",
    all(developer_dispatch.qualify_developer_request(value).status == "accepted" for value in multiline_explicit_cases),
    [(value, developer_dispatch.qualify_developer_request(value)) for value in multiline_explicit_cases],
)
unrelated_negation_cases = [
    "Don't worry - use Developer to fix the send button",
    "Don't worry - please fix the send button with Developer",
    "Never mind the CSS, use Developer to fix the API",
    "No need to explain, use Developer to fix the Runs query",
]
ok(
    "an unrelated negative lead-in does not cancel a later Developer command",
    all(developer_dispatch.qualify_developer_request(value).status == "accepted" for value in unrelated_negation_cases),
    [(value, developer_dispatch.qualify_developer_request(value)) for value in unrelated_negation_cases],
)
context_only_handoffs = [
    "send this to developer",
    "hand this to the Developer agent",
    "use developer for this",
]
ok(
    "context-only Developer hand-offs ask for one concrete objective",
    all(developer_dispatch.qualify_developer_request(value).status == "clarify" for value in context_only_handoffs),
    [(value, developer_dispatch.qualify_developer_request(value)) for value in context_only_handoffs],
)
bounded_objective = developer_dispatch.qualify_developer_request(
    "Use Developer to fix the Chat send button. It does nothing on mobile."
)
compound_objective = developer_dispatch.qualify_developer_request(
    "Use Developer to inspect the Chat bug, fix the retry loop, and run tests."
)
ok(
    "the Developer objective stops at a sentence without losing its clauses",
    bounded_objective.status == compound_objective.status == "accepted"
    and bounded_objective.objective == "fix the Chat send button"
    and compound_objective.objective == "inspect the Chat bug, fix the retry loop, and run tests",
    {"bounded": bounded_objective, "compound": compound_objective},
)
discussion_cases = [
    "Should we add a feature to export runs?",
    "Can you explain how to add a caching feature?",
    "Don't use Developer for this, just tell me what is wrong",
    "Don't build the export feature",
    "never add that capability",
    "I'd rather not use Developer for this",
    "we should probably add caching support at some point",
    "The team decided to add export capability last week",
]
ok(
    "questions and negations stay outside Developer dispatch",
    all(developer_dispatch.qualify_developer_request(value).status == "unsupported" for value in discussion_cases),
    [developer_dispatch.qualify_developer_request(value) for value in discussion_cases],
)
ok(
    "default Developer plans use plain acceptance-criterion grammar",
    "- the current Queue schema receives one parseable row" in authored_plan_text
    and "- Must the current Queue schema" not in authored_plan_text,
    authored_plan_text,
)

proposal = service.propose(
    session_id=35,
    client_turn_id="t02a-owner-turn",
    message="Use Developer to fix this MC limitation, run tests, and prepare the change for review.",
)
ok(
    "Chat returns an owner-readable proposal card",
    proposal["status"] == "proposed"
    and proposal["pending_action"]["developer_proposal"]["objective"]
    and proposal["pending_action"]["developer_proposal"]["acceptance_checks"]
    and proposal["pending_action"]["developer_proposal"]["scope"]
    and proposal["pending_action"]["developer_proposal"]["risk"] == "medium",
    proposal,
)
conn = get_connection()
development_counts = {
    "tasks": conn.execute("SELECT COUNT(*) FROM development_tasks").fetchone()[0],
    "workflows": conn.execute("SELECT COUNT(*) FROM coding_sessions").fetchone()[0],
}
conn.close()
ok(
    "proposal has zero Developer queue or workflow side effects",
    development_counts == {"tasks": 0, "workflows": 0}
    and fake.queue_calls == fake.workflow_calls == fake.start_calls == 0,
    development_counts,
)
destructive_proposal = service.propose(
    session_id=35,
    client_turn_id="t02a-high-risk-turn",
    message="Use Developer to delete every file in the repo.",
)
ok(
    "destructive Developer work is labeled high risk in the proposal",
    destructive_proposal["pending_action"]["developer_proposal"]["risk"] == "high",
    destructive_proposal,
)

replayed_proposal = service.propose(
    session_id=35,
    client_turn_id="t02a-owner-turn",
    message="Use Developer to fix this MC limitation, run tests, and prepare the change for review.",
)
ok(
    "retry and reload return the same proposal and confirmation",
    replayed_proposal["dispatch"]["id"] == proposal["dispatch"]["id"]
    and replayed_proposal["pending_action"]["id"] == proposal["pending_action"]["id"],
    replayed_proposal,
)

with ThreadPoolExecutor(max_workers=4) as pool:
    concurrent = list(pool.map(
        lambda _index: DeveloperDispatchService().propose(
            session_id=35,
            client_turn_id="t02a-concurrent-turn",
            message="Use Developer to add a synthetic concurrent feature.",
        ),
        range(4),
    ))
ok(
    "concurrent duplicate delivery creates one proposal action",
    len({item["pending_action"]["id"] for item in concurrent}) == 1,
    [item["pending_action"]["id"] for item in concurrent],
)

approved = conductor.confirm_action(int(proposal["pending_action"]["id"]), "approve")
approved_replay = conductor.confirm_action(int(proposal["pending_action"]["id"]), "approve")
ok(
    "confirmation creates and starts exactly one queue item and workflow",
    approved["ok"] is True
    and approved["developer_dispatch"]["workflow_id"] == 8350
    and approved_replay["developer_dispatch"]["workflow_id"] == 8350
    and (fake.queue_calls, fake.preflight_calls, fake.workflow_calls, fake.start_calls) == (1, 1, 1, 1),
    {"approved": approved, "calls": (fake.queue_calls, fake.preflight_calls, fake.workflow_calls, fake.start_calls)},
)
conn = get_connection()
runtime_row = conn.execute(
    "SELECT run_id,status FROM mc_runs WHERE request_id=?",
    (f"chat-developer-dispatch:{proposal['dispatch']['id']}",),
).fetchone()
conn.close()
ok(
    "confirmed Developer work enters canonical Runtime",
    runtime_row is not None and runtime_row["status"] == "running",
    dict(runtime_row) if runtime_row else None,
)

running = DeveloperDispatchService().get(proposal["dispatch"]["id"])
ok(
    "Chat projects the live Developer stage and deep link",
    running["status"] == "running"
    and running["stage"] == "code"
    and running["developer_url"] == "/developer?workflow=8350",
    running,
)

fake.state = "completed"
unproven = DeveloperDispatchService().get(proposal["dispatch"]["id"])
ok(
    "completed state is not claimed without changes checks and artifacts",
    unproven["status"] == "blocked"
    and "evidence" in unproven["blocker"].lower()
    and unproven["error_code"] == "developer-evidence-incomplete"
    and unproven["next_action"].startswith("Open Developer"),
    unproven,
)
fake.with_evidence = True
completed = DeveloperDispatchService().get(proposal["dispatch"]["id"])
ok(
    "completion is owner-readable and evidence linked",
    completed["status"] == "completed"
    and completed["changes"]["files"] == ["core/example.py"]
    and completed["checks"][0]["ok"] is True
    and completed["artifacts"][0]["kind"] == "test_report"
    and "artifact=1" in completed["artifacts"][0]["developer_url"],
    completed,
)
conn = get_connection()
runtime_complete = conn.execute(
    "SELECT status FROM mc_runs WHERE run_id=?", (completed["runtime_run_id"],)
).fetchone()
tier_rows = conn.execute(
    """SELECT evidence_type,evidence_ref FROM agent_tier_evidence
       WHERE ability_id='local_work_execution' AND family_id='coding_maintenance'"""
).fetchall()
conn.close()
ok(
    "completed Developer work publishes canonical Tier II proof",
    runtime_complete is not None
    and runtime_complete["status"] == "succeeded"
    and {row["evidence_type"] for row in tier_rows}
        == {"runtime_run", "typed_tool_result", "local_action_receipt", "coding_check"},
    {"runtime": dict(runtime_complete) if runtime_complete else None, "tier": [dict(row) for row in tier_rows]},
)

state_expectations = {
    "awaiting_merge_deploy_approval": "waiting_approval",
    "blocked": "blocked",
    "failed": "failed",
    "canceled": "canceled",
}
state_results = {}
for underlying, expected in state_expectations.items():
    fake.state = underlying
    state_results[underlying] = DeveloperDispatchService().get(proposal["dispatch"]["id"])["status"]
ok("all owner-visible Developer terminal and waiting states stay truthful", state_results == state_expectations, state_results)
fake.state = "completed"

calls_before_reject = (fake.queue_calls, fake.preflight_calls, fake.workflow_calls, fake.start_calls)
rejected_proposal = service.propose(
    session_id=35,
    client_turn_id="t02a-rejected-turn",
    message="Use Developer to add a synthetic status feature.",
)
rejected = conductor.confirm_action(int(rejected_proposal["pending_action"]["id"]), "reject")
ok(
    "refusing a proposal creates no Developer work",
    rejected["developer_dispatch"]["status"] == "canceled"
    and (fake.queue_calls, fake.preflight_calls, fake.workflow_calls, fake.start_calls) == calls_before_reject,
    rejected,
)


class FailOnceQueueGateway(FakeDeveloperGateway):
    def create_or_recover_queue_item(self, dispatch: dict) -> dict:
        self.queue_calls += 1
        if self.queue_calls == 1:
            raise RuntimeError("synthetic Queue authoring failure")
        return {"queue_id": 351, "plan_path": "docs/feature-idea-queue/T02A_RETRY_PLAN.md"}


retry_fake = FailOnceQueueGateway()
developer_dispatch._gateway_factory = lambda: retry_fake
retry_service = DeveloperDispatchService()
retry_proposal = retry_service.propose(
    session_id=35,
    client_turn_id="t02a-retry-turn",
    message="Use Developer to repair a synthetic retry limitation.",
)
failed_dispatch = conductor.confirm_action(int(retry_proposal["pending_action"]["id"]), "approve")
retry_projection = DeveloperDispatchService().get(retry_proposal["dispatch"]["id"])
ok(
    "a pre-workflow failure exposes a bounded retry",
    failed_dispatch["ok"] is False
    and retry_projection["status"] == "failed"
    and retry_projection["can_retry"] is True,
    {"failed": failed_dispatch, "projection": retry_projection},
)
retried_dispatch = DeveloperDispatchService().retry(retry_proposal["dispatch"]["id"])
ok(
    "retry continues the same approved dispatch without duplicate work",
    retried_dispatch["ok"] is True
    and retried_dispatch["developer_dispatch"]["id"] == retry_proposal["dispatch"]["id"]
    and retried_dispatch["developer_dispatch"]["queue_id"] == 351
    and retried_dispatch["developer_dispatch"]["workflow_id"] == 8350
    and retried_dispatch.get("previous_failure", {}).get("status") == "failed"
    and (retry_fake.queue_calls, retry_fake.preflight_calls, retry_fake.workflow_calls, retry_fake.start_calls)
        == (2, 1, 1, 1),
    {"retried": retried_dispatch, "calls": retry_fake.__dict__},
)


class FailTwiceQueueGateway(FakeDeveloperGateway):
    def create_or_recover_queue_item(self, dispatch: dict) -> dict:
        self.queue_calls += 1
        if self.queue_calls <= 2:
            raise RuntimeError(f"synthetic Queue authoring failure {self.queue_calls}")
        return {"queue_id": 352, "plan_path": "docs/feature-idea-queue/T02A_SECOND_RETRY_PLAN.md"}


twice_fake = FailTwiceQueueGateway()
developer_dispatch._gateway_factory = lambda: twice_fake
twice_proposal = DeveloperDispatchService().propose(
    session_id=35,
    client_turn_id="t02a-second-retry-turn",
    message="Use Developer to repair repeated synthetic Queue failures.",
)
conductor.confirm_action(int(twice_proposal["pending_action"]["id"]), "approve")
DeveloperDispatchService().retry(twice_proposal["dispatch"]["id"])
second_retry = DeveloperDispatchService().retry(twice_proposal["dispatch"]["id"])
failure_history = second_retry.get("previous_failure", {})
ok(
    "repeated retry keeps one flat previous-failure record",
    second_retry["ok"] is True
    and failure_history.get("status") == "failed"
    and "previous_failure" not in failure_history
    and twice_fake.queue_calls == 3,
    {"result": second_retry, "calls": twice_fake.queue_calls},
)


class FailStartGateway(FakeDeveloperGateway):
    def start_workflow(self, workflow_id: int) -> dict:
        self.start_calls += 1
        raise RuntimeError("synthetic worker bootstrap traceback")


start_fake = FailStartGateway()
developer_dispatch._gateway_factory = lambda: start_fake
start_proposal = DeveloperDispatchService().propose(
    session_id=35,
    client_turn_id="t02a-start-failure-turn",
    message="Use Developer to repair a synthetic start failure.",
)
start_failure = conductor.confirm_action(int(start_proposal["pending_action"]["id"]), "approve")
start_projection = start_failure["developer_dispatch"]
ok(
    "a post-workflow start failure gives an owner recovery path",
    start_failure["ok"] is False
    and start_projection["workflow_id"] == 8350
    and start_projection["can_retry"] is False
    and start_projection["blocker"] == "Developer created the workflow but could not start it."
    and start_projection["next_action"] == "Open Developer and select Retry for this run."
    and "traceback" not in start_projection["blocker"].lower(),
    start_projection,
)

from fastapi.testclient import TestClient  # noqa: E402
from api.dashboard import app  # noqa: E402
from core import chat_store  # noqa: E402

http_retry_fake = FailOnceQueueGateway()
developer_dispatch._gateway_factory = lambda: http_retry_fake
http_retry_proposal = DeveloperDispatchService().propose(
    session_id=35,
    client_turn_id="t02a-http-retry-turn",
    message="Use Developer to repair a synthetic HTTP retry limitation.",
)
conductor.confirm_action(int(http_retry_proposal["pending_action"]["id"]), "approve")
retry_response = TestClient(app).post(
    f"/api/chat/developer-dispatches/{http_retry_proposal['dispatch']['id']}/retry"
)
ok(
    "the public retry endpoint resumes the persisted failed card",
    retry_response.status_code == 200
    and retry_response.json()["developer_dispatch"]["id"] == http_retry_proposal["dispatch"]["id"]
    and retry_response.json()["developer_dispatch"]["status"] == "running",
    retry_response.text,
)

http_fake = FakeDeveloperGateway()
developer_dispatch._gateway_factory = lambda: http_fake
client = TestClient(app)
session = chat_store.create_session("T02A HTTP")
original_answer = conductor.answer

config_state = client.get("/api/chat/config").json()
ok(
    "Chat-to-Developer dispatch has an owner rollback flag",
    config_state.get("developer_chat_dispatch") is True,
    config_state,
)


def forbidden_model_call(*_args, **_kwargs):
    raise AssertionError("an explicit Developer dispatch reached the model loop")


conductor.answer = forbidden_model_call
try:
    streamed = client.post(
        f"/api/chat/sessions/{session['id']}/stream",
        json={
            "message": "/developer repair the synthetic MC limit and prove it with tests",
            "mode": "chat",
            "client_turn_id": "t02a-http-turn",
        },
    )
finally:
    conductor.answer = original_answer

ok(
    "normal Chat streams the deterministic proposal without a model call",
    streamed.status_code == 200
    and "event: action" in streamed.text
    and "developer_proposal" in streamed.text
    and '"model": "not_used"' in streamed.text,
    streamed.text[:1500],
)

normal_answers: list[str] = []


def normal_model_answer(message, *_args, **_kwargs):
    normal_answers.append(message)
    return {
        "reply": f"Normal answer: {message}",
        "streamed": False,
        "tools_used": [],
        "reasoning": None,
        "prompt_tokens": 1,
        "completion_tokens": 3,
    }


conn = get_connection()
dispatch_count_before = conn.execute("SELECT COUNT(*) FROM chat_developer_dispatches").fetchone()[0]
action_count_before = conn.execute("SELECT COUNT(*) FROM tobi_actions").fetchone()[0]
conn.close()
conductor.answer = normal_model_answer
try:
    discussion_responses = [
        client.post(
            f"/api/chat/sessions/{session['id']}/stream",
            json={"message": value, "mode": "chat", "client_turn_id": f"discussion-{index}"},
        )
        for index, value in enumerate(discussion_cases)
    ]
finally:
    conductor.answer = original_answer
conn = get_connection()
dispatch_count_after = conn.execute("SELECT COUNT(*) FROM chat_developer_dispatches").fetchone()[0]
action_count_after = conn.execute("SELECT COUNT(*) FROM tobi_actions").fetchone()[0]
conn.close()
ok(
    "ordinary discussion reaches the normal model path without a proposal",
    normal_answers == discussion_cases
    and all("event: action" not in response.text and "Normal answer:" in response.text for response in discussion_responses)
    and dispatch_count_after == dispatch_count_before
    and action_count_after == action_count_before,
    {"answers": normal_answers, "dispatches": (dispatch_count_before, dispatch_count_after),
     "actions": (action_count_before, action_count_after)},
)
conductor.answer = normal_model_answer
try:
    disabled = client.post(
        "/api/chat/config", json={"developer_chat_dispatch": False}
    ).json()
    disabled_response = client.post(
        f"/api/chat/sessions/{session['id']}/stream",
        json={
            "message": "/developer repair a rollback-only synthetic limitation",
            "mode": "chat",
            "client_turn_id": "t02a-rollout-disabled",
        },
    )
finally:
    client.post("/api/chat/config", json={"developer_chat_dispatch": True})
    conductor.answer = original_answer
ok(
    "the rollback flag returns Developer requests to normal Chat",
    disabled.get("developer_chat_dispatch") is False
    and "event: action" not in disabled_response.text
    and "Normal answer:" in disabled_response.text,
    {"config": disabled, "response": disabled_response.text[:600]},
)
conn = get_connection()
stored = conn.execute(
    """SELECT meta FROM chat_messages
       WHERE session_id=? AND role='assistant' AND meta LIKE '%developer_dispatch_id%'
       ORDER BY id DESC LIMIT 1""",
    (int(session["id"]),),
).fetchone()
conn.close()
stored_meta = json.loads(stored["meta"] or "{}") if stored else {}
http_dispatch_id = str(stored_meta.get("developer_dispatch_id") or "")
ok(
    "the Chat reply durably links session turn and Developer proposal",
    bool(http_dispatch_id) and stored_meta.get("mode") == "chat",
    stored_meta,
)
status_response = client.get(f"/api/chat/developer-dispatches/{http_dispatch_id}")
session_response = client.get(f"/api/chat/sessions/{session['id']}/developer-dispatches")
ok(
    "Chat exposes reload-safe Developer status and session artifact groups",
    status_response.status_code == 200
    and status_response.json()["id"] == http_dispatch_id
    and session_response.status_code == 200
    and len(session_response.json()["dispatches"]) == 1,
    {"status": status_response.text, "session": session_response.text},
)
ok(
    "the HTTP proposal still has no Developer side effect before confirmation",
    (http_fake.queue_calls, http_fake.preflight_calls, http_fake.workflow_calls, http_fake.start_calls) == (0, 0, 0, 0),
)
conn = get_connection()
http_action_id = conn.execute(
    "SELECT action_id FROM chat_developer_dispatches WHERE id=?", (http_dispatch_id,)
).fetchone()["action_id"]
conn.close()
confirmed_http = client.post(
    "/api/conductor/confirm", json={"action_id": int(http_action_id), "decision": "approve"}
)
ok(
    "the public confirmation endpoint starts the one linked workflow",
    confirmed_http.status_code == 200
    and confirmed_http.json()["developer_dispatch"]["workflow_id"] == 8350
    and (http_fake.queue_calls, http_fake.preflight_calls, http_fake.workflow_calls, http_fake.start_calls) == (1, 1, 1, 1),
    confirmed_http.text,
)

without_client_turn = client.post(
    f"/api/chat/sessions/{session['id']}/stream",
    json={
        "message": "/developer repair another synthetic MC limit and prove it with tests",
        "mode": "chat",
    },
)
ok(
    "older Chat clients receive a server dispatch identity",
    without_client_turn.status_code == 200
    and "event: action" in without_client_turn.text
    and "event: error" not in without_client_turn.text,
    without_client_turn.text,
)

chat_source = (ROOT / "dashboard/src/pages/Chat.tsx").read_text(encoding="utf-8")
api_source = (ROOT / "dashboard/src/api.chat.ts").read_text(encoding="utf-8")
files_source = (ROOT / "dashboard/src/components/chat/Attachments.tsx").read_text(encoding="utf-8")
developer_source = (ROOT / "dashboard/src/pages/Developer.tsx").read_text(encoding="utf-8")
evidence_source = (ROOT / "dashboard/src/components/developer/DeveloperEvidence.tsx").read_text(encoding="utf-8")
dispatch_card_source = (ROOT / "dashboard/src/components/chat/DeveloperDispatchCard.tsx").read_text(encoding="utf-8")
ok(
    "Mission Control renders proposal run status and generated artifacts",
    "DeveloperDispatchCard" in chat_source
    and "getDeveloperDispatch" in api_source
    and "Generated by Developer" in files_source
    and "Chat turn" in files_source
    and "getDeveloperWorkflow" in developer_source
    and "DeveloperEvidence" in developer_source
    and "getDeveloperArtifact" in evidence_source
    and "retryDeveloperDispatch" in dispatch_card_source
    and "Retry" in dispatch_card_source
    and "window.addEventListener('focus'" in chat_source,
)

print(f"\n{PASS} T02A contract checks passed")

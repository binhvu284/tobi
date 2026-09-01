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
    )
finally:
    coding_queue.REPO_ROOT = original_queue_root
    coding_queue.QUEUE_PATH = original_queue_path
    coding_queue_authoring.REPO_ROOT = original_authoring_root
    coding_queue_authoring.QUEUE_PATH = original_authoring_path
ok(
    "confirmed Chat work authors the current Queue table schema",
    authored["queue_id"] == 37
    and authored["title"] == "Chat Developer repair"
    and authored["queue_status"].endswith("Draft")
    and "| 37 | `DEV-QUEUE-037` | [**Chat Developer repair**]" in queue_path.read_text(encoding="utf-8"),
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
ok("a direct file request stays outside Developer", direct_file.status == "unsupported", direct_file)
ok("a capability request enters Developer", capability.status == "accepted", capability)
ok("an ambiguous request asks one bounded question", ambiguous.status == "clarify" and ambiguous.question, ambiguous)

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
    unproven["status"] == "blocked" and unproven["blocker"] == "developer-evidence-incomplete",
    unproven,
)
fake.with_evidence = True
completed = DeveloperDispatchService().get(proposal["dispatch"]["id"])
ok(
    "completion is owner-readable and evidence linked",
    completed["status"] == "completed"
    and completed["changes"]["files"] == ["core/example.py"]
    and completed["checks"][0]["ok"] is True
    and completed["artifacts"][0]["kind"] == "test_report",
    completed,
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

from fastapi.testclient import TestClient  # noqa: E402
from api.dashboard import app  # noqa: E402
from core import chat_store  # noqa: E402

http_fake = FakeDeveloperGateway()
developer_dispatch._gateway_factory = lambda: http_fake
client = TestClient(app)
session = chat_store.create_session("T02A HTTP")
original_answer = conductor.answer


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
conn = get_connection()
stored = conn.execute(
    "SELECT meta FROM chat_messages WHERE session_id=? AND role='assistant' ORDER BY id DESC LIMIT 1",
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
ok(
    "Mission Control renders proposal run status and generated artifacts",
    "DeveloperDispatchCard" in chat_source
    and "getDeveloperDispatch" in api_source
    and "Generated by Developer" in files_source
    and "getDeveloperWorkflow" in developer_source,
)

print(f"\n{PASS} T02A contract checks passed")

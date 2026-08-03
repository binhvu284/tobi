"""Acceptance checks for #21 T04 Run 4B live direct-Chat cutover."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TMP = tempfile.mkdtemp(prefix="tobi_t04_run4b_")
os.environ["DB_PATH"] = os.path.join(TMP, "agent.db")

from fastapi.testclient import TestClient  # noqa: E402
from api.dashboard import app  # noqa: E402
from core import chat_runtime, chat_store, conductor, database, owner_flags  # noqa: E402
from core.chat_runtime_contracts import TurnRequest  # noqa: E402
from core.database import get_connection  # noqa: E402
from core.runtime.event_store import list_run_events  # noqa: E402
from core.runtime.gateway import TurnGateway  # noqa: E402


PASS = 0


def ok(name: str, condition: bool, detail: object = "") -> None:
    global PASS
    if not condition:
        print(f"FAIL {name}: {detail}")
        raise SystemExit(1)
    PASS += 1
    print(f"PASS {name}")


def query_one(sql: str, parameters: tuple = ()):
    conn = get_connection()
    try:
        return conn.execute(sql, parameters).fetchone()
    finally:
        conn.close()


def event_names(response_text: str) -> list[str]:
    return [line[7:].strip() for line in response_text.splitlines() if line.startswith("event: ")]


def delta_text(response_text: str) -> str:
    event = ""
    chunks: list[str] = []
    for line in response_text.splitlines():
        if line.startswith("event: "):
            event = line[7:].strip()
        elif event == "delta" and line.startswith("data: "):
            chunks.append(str(json.loads(line[6:]).get("text") or ""))
    return "".join(chunks)


def set_rollout(
    *, events: bool = True, execution: bool = True, chat: bool = True, agent: bool = False
) -> None:
    owner_flags.set_bool(owner_flags.RUNTIME_V2_EVENTS, events)
    owner_flags.set_bool(owner_flags.RUNTIME_V2_EXECUTION, execution)
    owner_flags.set_bool(owner_flags.RUNTIME_V2_CHAT_EXECUTION, chat)
    owner_flags.set_bool(owner_flags.RUNTIME_V2_AGENT_EXECUTION, agent)


def post_turn(client: TestClient, sid: int, request_id: str, message: str, mode: str = "chat"):
    return client.post(
        f"/api/chat/sessions/{sid}/stream",
        json={
            "message": message,
            "mode": mode,
            "client_turn_id": request_id,
        },
    )


database.init_database()
client = TestClient(app)
session = chat_store.create_session("T04 Run 4B")
sid = session["id"]
chat_runtime.set_runtime_mode("on")
set_rollout()

original_answer = conductor.answer
answer_calls: list[str] = []


def answer(message, *_args, **_kwargs):
    answer_calls.append(message)
    if message == "fail canonical":
        raise RuntimeError("injected provider failure")
    return {
        "reply": f"Canonical reply: {message}",
        "tools_used": [],
        "streamed": False,
        "actual_model": "test:model",
        "requested_model": "test:model",
        "model_attempts": 1,
    }


conductor.answer = answer
try:
    probe_gateway = TurnGateway()
    probe_started = time.perf_counter()
    probe_acceptance = probe_gateway.accept_turn(
        TurnRequest(
            session_id=sid,
            message="measure acknowledgement",
            mode="chat",
            client_turn_id="ack-probe",
        ),
        activation_ready=True,
    )
    probe_execution = probe_gateway.prepare_direct_chat(probe_acceptance)
    probe_elapsed_ms = (time.perf_counter() - probe_started) * 1000
    ok(
        "canonical acknowledgement and exclusive claim stay under 500ms",
        probe_execution.disposition == "execute" and probe_elapsed_ms < 500,
        {"elapsed_ms": probe_elapsed_ms, "execution": probe_execution},
    )
    probe_gateway.fail_direct_chat(probe_execution)

    concurrent_acceptance = probe_gateway.accept_turn(
        TurnRequest(
            session_id=sid,
            message="claim once",
            mode="chat",
            client_turn_id="concurrent-claim",
        ),
        activation_ready=True,
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(
            pool.map(
                lambda _index: probe_gateway.prepare_direct_chat(concurrent_acceptance),
                range(2),
            )
        )
    ok(
        "two deliveries receive one exclusive execution claim",
        sorted(claim.disposition for claim in claims) == ["execute", "in_progress"],
        claims,
    )
    probe_gateway.fail_direct_chat(
        next(claim for claim in claims if claim.disposition == "execute")
    )

    active = post_turn(client, sid, "live-direct", "hello canonical")
    active_row = query_one(
        "SELECT run_id,status FROM mc_runs WHERE request_id=?", ("live-direct",)
    )
    active_run_id = active_row["run_id"] if active_row else ""
    active_step = query_one(
        "SELECT kind,status FROM mc_run_steps WHERE run_id=?", (active_run_id,)
    )
    active_loop = query_one(
        "SELECT enabled,status FROM mc_loop_runs WHERE run_id=?", (active_run_id,)
    )
    ok(
        "direct Chat is acknowledged and completed by the canonical runtime",
        active.status_code == 200
        and delta_text(active.text) == "Canonical reply: hello canonical"
        and active_row is not None
        and active_row["status"] == "succeeded"
        and active_step is not None
        and active_step["kind"] == "respond"
        and active_step["status"] == "succeeded"
        and active_loop is not None
        and active_loop["enabled"] == 1
        and active_loop["status"] == "succeeded",
        {
            "events": event_names(active.text),
            "run": dict(active_row) if active_row else None,
            "step": dict(active_step) if active_step else None,
            "loop": dict(active_loop) if active_loop else None,
            "response": active.text[:500],
        },
    )
    canonical_events = [event.event_type for event in list_run_events(active_run_id)]
    ok(
        "the active run has one legal durable lifecycle",
        canonical_events[:4] == ["run.accepted", "run.routing", "run.planned", "run.running"]
        and "step.claimed" in canonical_events
        and "step.succeeded" in canonical_events
        and canonical_events[-1] == "run.succeeded",
        canonical_events,
    )
    linked_message = query_one(
        "SELECT id,content FROM chat_messages WHERE runtime_run_id=?", (active_run_id,)
    )
    public_session = client.get(f"/api/chat/sessions/{sid}")
    ok(
        "the response link is durable and private",
        linked_message is not None
        and linked_message["content"] == "Canonical reply: hello canonical"
        and active_run_id not in active.text
        and "runtime_run_id" not in public_session.text,
    )

    replayed = post_turn(client, sid, "live-direct", "hello canonical")
    message_counts = query_one(
        "SELECT SUM(role='user') AS users,SUM(role='assistant') AS assistants "
        "FROM chat_messages WHERE content IN (?,?)",
        ("hello canonical", "Canonical reply: hello canonical"),
    )
    ok(
        "a completed duplicate replays without another execution or message",
        replayed.status_code == 200
        and delta_text(replayed.text) == "Canonical reply: hello canonical"
        and answer_calls.count("hello canonical") == 1
        and message_counts["users"] == 1
        and message_counts["assistants"] == 1
        and query_one("SELECT COUNT(*) AS count FROM mc_runs WHERE request_id='live-direct'")["count"]
        == 1,
        {"calls": answer_calls, "counts": dict(message_counts)},
    )

    set_rollout(chat=False)
    rolled_back = post_turn(client, sid, "after-rollback", "hello legacy")
    rollback_row = query_one(
        "SELECT run_id,status FROM mc_runs WHERE request_id=?", ("after-rollback",)
    )
    rollback_loop = query_one(
        "SELECT enabled FROM mc_loop_runs WHERE run_id=?",
        (rollback_row["run_id"] if rollback_row else "",),
    )
    replay_after_rollback = post_turn(client, sid, "live-direct", "hello canonical")
    ok(
        "one surface flag rolls new work back without changing an existing active run",
        delta_text(rolled_back.text) == "Canonical reply: hello legacy"
        and rollback_row is not None
        and rollback_row["status"] == "accepted"
        and rollback_loop is not None
        and rollback_loop["enabled"] == 0
        and delta_text(replay_after_rollback.text) == "Canonical reply: hello canonical"
        and answer_calls.count("hello canonical") == 1,
        answer_calls,
    )

    set_rollout(chat=True)
    read_response = post_turn(
        client, sid, "read-shadow", "what did we discuss yesterday?"
    )
    read_row = query_one(
        "SELECT run_id,status FROM mc_runs WHERE request_id=?", ("read-shadow",)
    )
    read_loop = query_one(
        "SELECT enabled FROM mc_loop_runs WHERE run_id=?", (read_row["run_id"] if read_row else "",)
    )
    ok(
        "read and tool-capable Chat routes remain shadow-only",
        delta_text(read_response.text)
        == "Canonical reply: what did we discuss yesterday?"
        and read_row is not None
        and read_row["status"] == "accepted"
        and read_loop is not None
        and read_loop["enabled"] == 0,
        {
            "delta": delta_text(read_response.text),
            "events": event_names(read_response.text),
            "run": dict(read_row) if read_row else None,
            "loop": dict(read_loop) if read_loop else None,
        },
    )

    attachment_response = client.post(
        f"/api/chat/sessions/{sid}/stream",
        json={
            "message": "summarize this note",
            "mode": "chat",
            "client_turn_id": "attachment-shadow",
            "attachments": [
                {
                    "name": "note.txt",
                    "mime": "text/plain",
                    "kind": "text",
                    "text": "Attachment paths stay on the compatibility runtime.",
                }
            ],
        },
    )
    attachment_row = query_one(
        "SELECT run_id,status FROM mc_runs WHERE request_id=?", ("attachment-shadow",)
    )
    attachment_loop = query_one(
        "SELECT enabled FROM mc_loop_runs WHERE run_id=?",
        (attachment_row["run_id"] if attachment_row else "",),
    )
    ok(
        "attachment Chat remains shadow-only",
        attachment_response.status_code == 200
        and attachment_row is not None
        and attachment_row["status"] == "accepted"
        and attachment_loop is not None
        and attachment_loop["enabled"] == 0,
        {
            "run": dict(attachment_row) if attachment_row else None,
            "loop": dict(attachment_loop) if attachment_loop else None,
        },
    )

    set_rollout(chat=True, agent=True)
    agent_response = post_turn(client, sid, "agent-shadow", "inspect project", mode="agent")
    agent_row = query_one(
        "SELECT run_id,status FROM mc_runs WHERE request_id=?", ("agent-shadow",)
    )
    agent_loop = query_one(
        "SELECT enabled FROM mc_loop_runs WHERE run_id=?",
        (agent_row["run_id"] if agent_row else "",),
    )
    ok(
        "Agent remains shadow-only even when its stored flag is enabled",
        agent_response.status_code == 200
        and agent_row is not None
        and agent_row["status"] == "accepted"
        and agent_loop is not None
        and agent_loop["enabled"] == 0,
    )

    original_accept = TurnGateway.accept_turn

    def fail_accept(*_args, **_kwargs):
        raise RuntimeError("injected gateway failure")

    TurnGateway.accept_turn = fail_accept
    calls_before_failure = len(answer_calls)
    failed_start = post_turn(client, sid, "active-start-failure", "hello fail closed")
    TurnGateway.accept_turn = original_accept
    ok(
        "active startup failure never falls through to untracked legacy execution",
        "event: error" in failed_start.text
        and "event: delta" not in failed_start.text
        and len(answer_calls) == calls_before_failure,
        {"events": event_names(failed_start.text), "calls": answer_calls},
    )

    failed_execution = post_turn(client, sid, "provider-failure", "fail canonical")
    failed_row = query_one(
        "SELECT run_id,status FROM mc_runs WHERE request_id=?", ("provider-failure",)
    )
    failed_step = query_one(
        "SELECT status,last_error_json FROM mc_run_steps WHERE run_id=?",
        (failed_row["run_id"] if failed_row else "",),
    )
    ok(
        "provider failure becomes a typed canonical recovery state",
        "event: error" in failed_execution.text
        and failed_row is not None
        and failed_row["status"] == "recovering"
        and failed_step is not None
        and failed_step["status"] == "failed"
        and "injected provider failure" not in (failed_step["last_error_json"] or ""),
        {
            "run": dict(failed_row) if failed_row else None,
            "step": dict(failed_step) if failed_step else None,
        },
    )
finally:
    conductor.answer = original_answer
    if "original_accept" in locals():
        TurnGateway.accept_turn = original_accept
    set_rollout(events=False, execution=False, chat=False, agent=False)
    chat_runtime.set_runtime_mode("on")

print(f"{PASS}/{PASS} T04 RUN 4B LIVE CHAT CHECKS PASS")

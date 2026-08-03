"""Acceptance checks for #21 T04 Run 2 Chat/Agent shadow route wiring."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TMP = tempfile.mkdtemp(prefix="tobi_t04_run2_")
os.environ["DB_PATH"] = os.path.join(TMP, "agent.db")

from fastapi.testclient import TestClient  # noqa: E402
from api.dashboard import app  # noqa: E402
from core import chat_runtime, chat_store, conductor, database, owner_flags  # noqa: E402
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


def wait_until(callback, timeout_s: float = 2.0) -> bool:
    deadline = time.perf_counter() + timeout_s
    while time.perf_counter() < deadline:
        if callback():
            return True
        time.sleep(0.02)
    return bool(callback())


def event_names(response_text: str) -> list[str]:
    return [line[7:].strip() for line in response_text.splitlines() if line.startswith("event: ")]


def set_v2_events(enabled: bool) -> None:
    owner_flags.set_bool(owner_flags.RUNTIME_V2_EVENTS, enabled)
    owner_flags.set_bool(owner_flags.RUNTIME_V2_EXECUTION, False)


database.init_database()
client = TestClient(app)
session = chat_store.create_session("T04 Run 2")
sid = session["id"]

original_answer = conductor.answer
accepted_before_answer: list[bool] = []


def answer(*_args, **_kwargs):
    row = query_one("SELECT 1 FROM mc_runs WHERE request_id=?", (CURRENT_REQUEST[0],))
    accepted_before_answer.append(row is not None)
    return {"reply": "Legacy answer, sir.", "tools_used": [], "streamed": False}


CURRENT_REQUEST = [""]
conductor.answer = answer
chat_runtime.set_runtime_mode("on")
try:
    set_v2_events(False)
    CURRENT_REQUEST[0] = "route-off"
    off_response = client.post(
        f"/api/chat/sessions/{sid}/stream",
        json={"message": "off path", "mode": "chat", "client_turn_id": CURRENT_REQUEST[0]},
    )
    ok(
        "flag off preserves the legacy stream and creates no canonical run",
        off_response.status_code == 200
        and "event: delta" in off_response.text
        and "event: done" in off_response.text
        and query_one("SELECT 1 FROM mc_runs WHERE request_id=?", (CURRENT_REQUEST[0],)) is None,
        off_response.text[:600],
    )

    set_v2_events(True)
    CURRENT_REQUEST[0] = "route-shadow"
    shadow_response = client.post(
        f"/api/chat/sessions/{sid}/stream",
        json={"message": "shadow path", "mode": "chat", "client_turn_id": CURRENT_REQUEST[0]},
    )
    shadow_row = query_one(
        "SELECT run_id,status,legacy_run_id FROM mc_runs WHERE request_id=?",
        (CURRENT_REQUEST[0],),
    )
    ok(
        "shadow route accepts the canonical run before Conductor",
        shadow_response.status_code == 200
        and accepted_before_answer[-1] is True
        and shadow_row is not None
        and shadow_row["status"] == "accepted",
        {"accepted_before_answer": accepted_before_answer, "row": dict(shadow_row) if shadow_row else None},
    )
    ok(
        "canonical observations never leak into the browser stream",
        "shadow." not in shadow_response.text
        and event_names(shadow_response.text).count("turn_started") == 1
        and event_names(shadow_response.text).count("turn_completed") == 1,
        event_names(shadow_response.text),
    )
    ok(
        "normal Chat lifecycle is mirrored in order",
        wait_until(
            lambda: [event.event_type for event in list_run_events(shadow_row["run_id"])][-1:]
            == ["shadow.turn_completed"]
        )
        and [event.sequence for event in list_run_events(shadow_row["run_id"])]
        == list(range(1, len(list_run_events(shadow_row["run_id"])) + 1)),
        list_run_events(shadow_row["run_id"]),
    )

    chat_runtime.set_runtime_mode("off")
    CURRENT_REQUEST[0] = "route-old-recorder-off"
    baseline_started = time.perf_counter()
    recorder_off = client.post(
        f"/api/chat/sessions/{sid}/stream",
        json={"message": "record silently", "mode": "chat", "client_turn_id": CURRENT_REQUEST[0]},
    )
    baseline_elapsed = time.perf_counter() - baseline_started
    recorder_off_row = query_one(
        "SELECT run_id FROM mc_runs WHERE request_id=?", (CURRENT_REQUEST[0],)
    )
    ok(
        "new shadow recording is independent from the old recorder",
        recorder_off.status_code == 200
        and "event: turn_started" not in recorder_off.text
        and "event: turn_completed" not in recorder_off.text
        and recorder_off_row is not None
        and wait_until(
            lambda: any(
                event.event_type == "shadow.turn_completed"
                for event in list_run_events(recorder_off_row["run_id"])
            )
        ),
        event_names(recorder_off.text),
    )

    chat_runtime.set_runtime_mode("on")
    original_accept = TurnGateway.accept_turn
    slow_calls: list[bool] = []

    def slow_accept(*_args, **_kwargs):
        slow_calls.append(True)
        time.sleep(0.8)
        raise RuntimeError("injected slow shadow failure")

    TurnGateway.accept_turn = slow_accept
    CURRENT_REQUEST[0] = "route-slow-shadow"
    started = time.perf_counter()
    slow_response = client.post(
        f"/api/chat/sessions/{sid}/stream",
        json={"message": "stay responsive", "mode": "chat", "client_turn_id": CURRENT_REQUEST[0]},
    )
    elapsed = time.perf_counter() - started
    TurnGateway.accept_turn = original_accept
    ok(
        "slow shadow storage adds only bounded delay to the legacy answer",
        slow_calls == [True]
        and elapsed - baseline_elapsed < 0.25
        and slow_response.status_code == 200
        and "event: delta" in slow_response.text
        and "event: done" in slow_response.text,
        {
            "elapsed": elapsed,
            "baseline_elapsed": baseline_elapsed,
            "added_elapsed": elapsed - baseline_elapsed,
            "events": event_names(slow_response.text),
        },
    )

    CURRENT_REQUEST[0] = "route-agent-initial"
    agent_response = client.post(
        f"/api/chat/sessions/{sid}/stream",
        json={"message": "inspect project", "mode": "agent", "client_turn_id": CURRENT_REQUEST[0]},
    )
    assistant = chat_store.get_messages(sid)[-1]
    legacy_run_id = int(json.loads(assistant["meta"] or "{}")["run_id"])
    agent_row = query_one(
        "SELECT run_id,legacy_run_id FROM mc_runs WHERE request_id=?", (CURRENT_REQUEST[0],)
    )
    ok(
        "Agent shadow run links to the existing legacy Agent run",
        agent_response.status_code == 200
        and agent_row is not None
        and agent_row["legacy_run_id"] == str(legacy_run_id),
        {"legacy_run_id": legacy_run_id, "row": dict(agent_row) if agent_row else None},
    )

    CURRENT_REQUEST[0] = "route-agent-resume"
    resume_response = client.post(
        f"/api/chat/sessions/{sid}/stream",
        json={
            "message": "resume project inspection",
            "mode": "agent",
            "client_turn_id": CURRENT_REQUEST[0],
            "resume_run_id": legacy_run_id,
        },
    )
    linked_count = query_one(
        "SELECT COUNT(*) AS count FROM mc_runs WHERE legacy_run_id=?", (str(legacy_run_id),)
    )["count"]
    linked_events = list_run_events(agent_row["run_id"])
    ok(
        "Agent recovery reuses the same canonical run",
        resume_response.status_code == 200
        and linked_count == 1
        and any(
            event.redacted_payload.get("request_id") == CURRENT_REQUEST[0]
            for event in linked_events
        ),
        {"linked_count": linked_count, "events": linked_events},
    )
    ok(
        "canonical run ids remain server-side",
        agent_row["run_id"] not in agent_response.text
        and agent_row["run_id"] not in resume_response.text,
    )
finally:
    conductor.answer = original_answer
    TurnGateway.accept_turn = original_accept if "original_accept" in locals() else TurnGateway.accept_turn
    set_v2_events(False)
    chat_runtime.set_runtime_mode("on")

print(f"{PASS}/{PASS} T04 RUN 2 ROUTE CHECKS PASS")

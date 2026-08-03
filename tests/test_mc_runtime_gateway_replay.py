"""Acceptance checks for #21 T04 Run 3 canonical event replay and reconnect."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TMP = tempfile.mkdtemp(prefix="tobi_t04_run3_")
os.environ["DB_PATH"] = os.path.join(TMP, "agent.db")

from fastapi.testclient import TestClient  # noqa: E402
from api.dashboard import app  # noqa: E402
from core import chat_store, database, owner_flags  # noqa: E402
from core.chat_runtime_contracts import TurnRequest  # noqa: E402
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


def parse_sse(text: str) -> list[dict]:
    events: list[dict] = []
    for frame in text.split("\n\n"):
        fields: dict[str, str] = {}
        for line in frame.splitlines():
            if ": " in line:
                key, value = line.split(": ", 1)
                fields[key] = value
        if "id" in fields and "event" in fields and "data" in fields:
            events.append({
                "id": int(fields["id"]),
                "event": fields["event"],
                "data": json.loads(fields["data"]),
            })
    return events


def set_events(enabled: bool) -> None:
    owner_flags.set_bool(owner_flags.RUNTIME_V2_EVENTS, enabled)
    owner_flags.set_bool(owner_flags.RUNTIME_V2_EXECUTION, False)


database.init_database()
client = TestClient(app)
gateway = TurnGateway()
session = chat_store.create_session("T04 Run 3")
sid = int(session["id"])

set_events(False)
disabled = client.get("/api/runtime/runs/missing/events", params={"session_id": sid})
ok(
    "replay endpoint fails closed while Runtime V2 events are disabled",
    disabled.status_code == 503,
    disabled.text,
)

set_events(True)
acceptance = gateway.accept_turn(TurnRequest(
    session_id=sid,
    message="replay this safely",
    mode="chat",
    client_turn_id="run3-replay",
))
run_id = acceptance.run_id or ""
gateway.mirror_event(
    acceptance,
    source_sequence=1,
    event_type="step_started",
    stage="execution",
    payload={"label": "Inspect", "api_key": "sk-run3-secret"},
)
gateway.mirror_event(
    acceptance,
    source_sequence=2,
    event_type="turn_completed",
    stage="gateway",
    payload={"status": "done"},
)

wrong_session = client.get(
    f"/api/runtime/runs/{run_id}/events", params={"session_id": sid + 1}
)
ok("another Chat session cannot read the run", wrong_session.status_code == 404, wrong_session.text)

bad_cursor = client.get(
    f"/api/runtime/runs/{run_id}/events",
    params={"session_id": sid},
    headers={"Last-Event-ID": "not-a-sequence"},
)
ok("malformed Last-Event-ID is rejected", bad_cursor.status_code == 422, bad_cursor.text)

after_one = client.get(
    f"/api/runtime/runs/{run_id}/events", params={"session_id": sid, "after": 1}
)
after_one_events = parse_sse(after_one.text)
ok(
    "query cursor replays only later ordered events",
    after_one.status_code == 200
    and [event["id"] for event in after_one_events] == [2, 3]
    and [event["event"] for event in after_one_events]
    == ["shadow.step_started", "shadow.turn_completed"],
    after_one_events,
)
ok(
    "SSE data uses the canonical redacted event envelope",
    after_one_events[0]["data"]["run_id"] == run_id
    and after_one_events[0]["data"]["sequence"] == 2
    and after_one_events[0]["data"]["stage"] == "execution"
    and after_one_events[0]["data"]["payload"]["api_key"] == "[REDACTED]"
    and "sk-run3-secret" not in after_one.text,
    after_one_events[0] if after_one_events else after_one.text,
)

header_wins = client.get(
    f"/api/runtime/runs/{run_id}/events",
    params={"session_id": sid, "after": 1},
    headers={"Last-Event-ID": "2"},
)
header_events = parse_sse(header_wins.text)
ok(
    "Last-Event-ID advances the query cursor without duplicates",
    [event["id"] for event in header_events] == [3],
    header_events,
)

query_wins = client.get(
    f"/api/runtime/runs/{run_id}/events",
    params={"session_id": sid, "after": 2},
    headers={"Last-Event-ID": "1"},
)
query_events = parse_sse(query_wins.text)
ok(
    "a stale Last-Event-ID cannot move the query cursor backward",
    [event["id"] for event in query_events] == [3],
    query_events,
)

terminal_started = time.perf_counter()
terminal_reconnect = client.get(
    f"/api/runtime/runs/{run_id}/events",
    params={"session_id": sid, "after": 3},
)
terminal_elapsed = time.perf_counter() - terminal_started
ok(
    "reconnect at the terminal sequence closes without duplicate events",
    terminal_reconnect.status_code == 200
    and parse_sse(terminal_reconnect.text) == []
    and terminal_elapsed < 1,
    {"elapsed": terminal_elapsed, "body": terminal_reconnect.text},
)

gateway_page = gateway.replay_events(
    run_id,
    expected_session_id=str(sid),
    after_sequence=1,
    limit=1,
)
ok(
    "gateway replay honors a bounded page size",
    len(gateway_page) == 1 and gateway_page[0].sequence == 2,
    gateway_page,
)

live_acceptance = gateway.accept_turn(TurnRequest(
    session_id=sid,
    message="tail this run",
    mode="agent",
    client_turn_id="run3-live-tail",
))
live_run_id = live_acceptance.run_id or ""


def finish_live_run() -> None:
    time.sleep(0.15)
    gateway.mirror_event(
        live_acceptance,
        source_sequence=1,
        event_type="turn_completed",
        stage="gateway",
        payload={"status": "done"},
    )


thread = threading.Thread(target=finish_live_run, daemon=True)
thread.start()
started = time.perf_counter()
live_response = client.get(
    f"/api/runtime/runs/{live_run_id}/events",
    params={"session_id": sid, "after": 1},
)
live_elapsed = time.perf_counter() - started
thread.join(timeout=2)
live_events = parse_sse(live_response.text)
ok(
    "an open replay stream tails later events and closes on completion",
    live_response.status_code == 200
    and [event["id"] for event in live_events] == [2]
    and live_events[0]["event"] == "shadow.turn_completed"
    and live_elapsed < 2,
    {"elapsed": live_elapsed, "events": live_events},
)

all_sequences = [event.sequence for event in list_run_events(run_id)]
ok("replay reads never mutate canonical history", all_sequences == [1, 2, 3], all_sequences)

set_events(False)
print(f"{PASS}/{PASS} T04 RUN 3 REPLAY CHECKS PASS")

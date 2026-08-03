"""Acceptance checks for #21 T04 Run 1 dormant Chat/Agent gateway."""
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TMP = tempfile.mkdtemp(prefix="tobi_t04_run1_")
os.environ["DB_PATH"] = os.path.join(TMP, "agent.db")

from core import database, owner_flags  # noqa: E402
from core.chat_runtime_contracts import TurnRequest  # noqa: E402
from core.runtime import config  # noqa: E402
from core.runtime.event_store import EventConflictError, list_run_events  # noqa: E402
from core.runtime.gateway import TurnGateway  # noqa: E402
from core.runtime.repository import RunConflictError, RuntimeRepository  # noqa: E402


PASS = 0


def ok(name: str, condition: bool, detail: object = "") -> None:
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


def set_rollout(*, events: bool, execution: bool) -> None:
    owner_flags.set_bool(owner_flags.RUNTIME_V2_EVENTS, events)
    owner_flags.set_bool(owner_flags.RUNTIME_V2_EXECUTION, execution)


database.init_database()
repository = RuntimeRepository()
gateway = TurnGateway(repository)

set_rollout(events=False, execution=False)
ok("gateway defaults off", config.gateway_mode() == "off")
off = gateway.accept_turn(TurnRequest(
    session_id=41,
    message="do not persist me",
    mode="chat",
    client_turn_id="turn-off",
))
ok("off mode does not create a run", off.run_id is None and repository.get_run("turn-off") is None)

set_rollout(events=False, execution=True)
ok("execution without events fails closed", config.gateway_mode() == "off")

set_rollout(events=True, execution=True)
ok(
    "global execution alone remains shadow without a surface and route gate",
    config.gateway_mode() == "on"
    and gateway.accept_turn(
        TurnRequest(
            session_id=41,
            message="do not execute yet",
            mode="agent",
            client_turn_id="turn-on-deferred",
        )
    ).mode
    == "shadow",
)

set_rollout(events=True, execution=False)
ok("events-only rollout is shadow mode", config.gateway_mode() == "shadow")
request = TurnRequest(
    session_id=41,
    message="Inspect this api_key=sk-t04-do-not-store",
    mode="chat",
    client_turn_id="turn-shadow",
    capabilities={"web_research": True},
)
started = time.perf_counter()
accepted = gateway.accept_turn(
    request,
    attachments=(
        {
            "name": "notes.txt",
            "mime": "text/plain",
            "kind": "text",
            "text": "private attachment body",
            "data_url": "data:text/plain;base64,cHJpdmF0ZQ==",
        },
    ),
)
elapsed_ms = (time.perf_counter() - started) * 1000
run = repository.get_run(accepted.run_id or "")
ok(
    "shadow acknowledgement persists an accepted canonical run under 500ms",
    accepted.mode == "shadow"
    and accepted.sequence == 1
    and elapsed_ms < 500
    and run is not None
    and run["status"] == "accepted",
    {"acceptance": accepted, "elapsed_ms": elapsed_ms, "run": run},
)
stored = str((run or {}).get("request") or {})
ok(
    "gateway stores only sanitized request input",
    "sk-t04-do-not-store" not in stored
    and "private attachment body" not in stored
    and "data:text/plain" not in stored
    and "notes.txt" in stored,
    stored,
)
ok(
    "shadow policy cannot execute",
    run is not None and run["loop"]["enabled"] is False and run["surface"] == "chat",
    run,
)

replayed = gateway.accept_turn(request, attachments=({"name": "notes.txt", "mime": "text/plain", "kind": "text"},))
ok(
    "same client turn replays the same canonical run",
    replayed.run_id == accepted.run_id and len(list_run_events(accepted.run_id or "")) == 1,
)
ok(
    "changed content cannot reuse a client turn",
    raises(
        RunConflictError,
        lambda: gateway.accept_turn(TurnRequest(
            session_id=41,
            message="Different request",
            mode="chat",
            client_turn_id="turn-shadow",
        )),
    ),
)

mirrored = gateway.mirror_event(
    accepted,
    source_sequence=1,
    event_type="turn_completed",
    stage="gateway",
    payload={"status": "done", "api_key": "sk-t04-event-secret"},
)
mirrored_again = gateway.mirror_event(
    accepted,
    source_sequence=1,
    event_type="turn_completed",
    stage="gateway",
    payload={"status": "done", "api_key": "sk-t04-event-secret"},
)
events = list_run_events(accepted.run_id or "")
ok(
    "shadow events are ordered, redacted, and replay safe",
    mirrored.sequence == 2
    and mirrored_again.sequence == 2
    and len(events) == 2
    and events[-1].event_type == "shadow.turn_completed"
    and events[-1].redacted_payload.get("api_key") == "[REDACTED]",
    events,
)
ok(
    "one legacy sequence cannot mirror two different events",
    raises(
        EventConflictError,
        lambda: gateway.mirror_event(
            accepted,
            source_sequence=1,
            event_type="step_failed",
            stage="execution",
            payload={"status": "failed"},
        ),
    ),
)
ok(
    "shadow observation never claims execution",
    repository.get_run(accepted.run_id or "")["status"] == "accepted",
)

agent = gateway.accept_turn(TurnRequest(
    session_id=41,
    message="Inspect the project",
    mode="agent",
    client_turn_id="turn-agent",
))
ok(
    "Agent requests use the Agent surface with the same disabled policy",
    repository.get_run(agent.run_id or "")["surface"] == "agent"
    and repository.get_run(agent.run_id or "")["loop"]["enabled"] is False,
)

linked = gateway.link_legacy_run(agent, 701)
linked_again = gateway.link_legacy_run(agent, 701)
ok(
    "legacy Agent linking is persisted and replay safe",
    linked["legacy_run_id"] == "701"
    and linked_again["legacy_run_id"] == "701"
    and [event.event_type for event in list_run_events(agent.run_id or "")].count(
        "run.legacy_linked"
    )
    == 1,
)

resumed = gateway.accept_turn(TurnRequest(
    session_id=41,
    message="Continue the project inspection",
    mode="agent",
    client_turn_id="turn-agent-resume",
    resume_run_id=701,
))
ok(
    "Agent resume reuses the linked canonical run with a new request identity",
    resumed.run_id == agent.run_id
    and resumed.request_id == "turn-agent-resume"
    and repository.get_run_by_legacy_run_id("701")["run_id"] == agent.run_id,
)

other_agent = gateway.accept_turn(TurnRequest(
    session_id=41,
    message="Inspect another project",
    mode="agent",
    client_turn_id="turn-agent-other",
))
ok(
    "one legacy Agent run cannot link to two canonical runs",
    raises(RunConflictError, lambda: gateway.link_legacy_run(other_agent, 701)),
)

print(f"{PASS}/{PASS} T04 GATEWAY CHECKS PASS")

"""Acceptance checks for #21 T04 Run 4A gateway activation controls."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TMP = tempfile.mkdtemp(prefix="tobi_t04_run4a_")
os.environ["DB_PATH"] = os.path.join(TMP, "agent.db")

from core import database, owner_flags  # noqa: E402
from core.chat_runtime_contracts import TurnRequest  # noqa: E402
from core.runtime import config  # noqa: E402
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


def set_rollout(
    *, events: bool, execution: bool, chat: bool = False, agent: bool = False
) -> None:
    owner_flags.set_bool(owner_flags.RUNTIME_V2_EVENTS, events)
    owner_flags.set_bool(owner_flags.RUNTIME_V2_EXECUTION, execution)
    owner_flags.set_bool(owner_flags.RUNTIME_V2_CHAT_EXECUTION, chat)
    owner_flags.set_bool(owner_flags.RUNTIME_V2_AGENT_EXECUTION, agent)


def turn(request_id: str, mode: str = "chat", message: str = "Inspect the request") -> TurnRequest:
    return TurnRequest(
        session_id=84,
        message=message,
        mode=mode,
        client_turn_id=request_id,
    )


database.init_database()
repository = RuntimeRepository()
gateway = TurnGateway(repository)

set_rollout(events=False, execution=False)
ok(
    "surface execution flags default off",
    config.surface_gateway_mode("chat", activation_ready=True) == "off"
    and config.surface_gateway_mode("agent", activation_ready=True) == "off",
)

set_rollout(events=True, execution=True, chat=True)
ok(
    "route readiness is required after every stored flag is enabled",
    config.surface_gateway_mode("chat") == "shadow",
)
live_safe = gateway.accept_turn(turn("route-not-ready"))
live_safe_run = repository.get_run(live_safe.run_id or "")
ok(
    "the unchanged live route remains shadow only",
    live_safe.mode == "shadow"
    and live_safe_run is not None
    and live_safe_run["loop"]["enabled"] is False,
    live_safe_run,
)

active = gateway.accept_turn(turn("active-chat"), activation_ready=True)
active_run = repository.get_run(active.run_id or "")
ok(
    "a fully gated Chat request persists an enabled compatibility policy",
    active.mode == "on"
    and active_run is not None
    and active_run["status"] == "accepted"
    and active_run["loop"]["enabled"] is True
    and active_run["loop"]["policy"]["enabled"] is True,
    active_run,
)

agent_shadow = gateway.accept_turn(turn("agent-shadow", mode="agent"), activation_ready=True)
ok(
    "Chat activation does not activate Agent",
    agent_shadow.mode == "shadow"
    and repository.get_run(agent_shadow.run_id or "")["loop"]["enabled"] is False,
)
set_rollout(events=True, execution=True, chat=True, agent=True)
agent_active = gateway.accept_turn(turn("agent-active", mode="agent"), activation_ready=True)
ok(
    "Agent has an independent activation gate",
    agent_active.mode == "on"
    and repository.get_run(agent_active.run_id or "")["loop"]["enabled"] is True,
)

set_rollout(events=False, execution=True, chat=True, agent=True)
ok(
    "execution still fails closed without events",
    config.surface_gateway_mode("chat", activation_ready=True) == "off",
)
replayed_active = gateway.accept_turn(turn("active-chat"), activation_ready=True)
ok(
    "an active request keeps its original mode after rollback",
    replayed_active.run_id == active.run_id and replayed_active.mode == "on",
    replayed_active,
)
ok(
    "changed content cannot hide behind rollback flags",
    raises(
        RunConflictError,
        lambda: gateway.accept_turn(
            turn("active-chat", message="Different request"), activation_ready=True
        ),
    ),
)
new_off = gateway.accept_turn(turn("new-after-rollback"), activation_ready=True)
ok("new work obeys rollback", new_off.mode == "off" and new_off.run_id is None)

set_rollout(events=True, execution=True, chat=True, agent=True)
replayed_shadow = gateway.accept_turn(turn("route-not-ready"), activation_ready=True)
ok(
    "a shadow request never upgrades during retry",
    replayed_shadow.run_id == live_safe.run_id and replayed_shadow.mode == "shadow",
    replayed_shadow,
)
ok(
    "route readiness accepts only a real boolean",
    raises(
        ValueError,
        lambda: gateway.accept_turn(turn("bad-ready"), activation_ready=1),
    ),
)

print(f"{PASS}/{PASS} T04 RUN 4A ACTIVATION CHECKS PASS")

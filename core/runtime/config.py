"""Fail-closed rollout controls for Mission Control Infrastructure V2."""
from __future__ import annotations

from core import owner_flags


RUNTIME_V2_EVENTS = owner_flags.RUNTIME_V2_EVENTS
RUNTIME_V2_EXECUTION = owner_flags.RUNTIME_V2_EXECUTION
RUNTIME_V2_CHAT_EXECUTION = owner_flags.RUNTIME_V2_CHAT_EXECUTION
RUNTIME_V2_AGENT_EXECUTION = owner_flags.RUNTIME_V2_AGENT_EXECUTION
RUNTIME_V2_TOOLS = owner_flags.RUNTIME_V2_TOOLS
RUNTIME_V2_POLICY = owner_flags.RUNTIME_V2_POLICY
RUNTIME_V2_CONTEXT = owner_flags.RUNTIME_V2_CONTEXT
RUNTIME_V2_HERMES = owner_flags.RUNTIME_V2_HERMES
RUNTIME_V2_UI = owner_flags.RUNTIME_V2_UI

RUNTIME_V2_FLAGS = (
    RUNTIME_V2_EVENTS,
    RUNTIME_V2_EXECUTION,
    RUNTIME_V2_CHAT_EXECUTION,
    RUNTIME_V2_AGENT_EXECUTION,
    RUNTIME_V2_TOOLS,
    RUNTIME_V2_POLICY,
    RUNTIME_V2_CONTEXT,
    RUNTIME_V2_HERMES,
    RUNTIME_V2_UI,
)


def rollout_enabled(flag: str) -> bool:
    """Return a V2 flag, defaulting off and rejecting misspelled flag names."""
    if flag not in RUNTIME_V2_FLAGS:
        raise ValueError(f"Unknown runtime V2 flag: {flag}")
    return owner_flags.get_bool(flag, False)


def rollout_state() -> dict[str, bool]:
    """Return the effective state of every T01 runtime flag."""
    return {flag: rollout_enabled(flag) for flag in RUNTIME_V2_FLAGS}


def gateway_mode() -> str:
    """Derive the Chat/Agent gateway state without allowing untraced execution."""
    events_enabled = rollout_enabled(RUNTIME_V2_EVENTS)
    execution_enabled = rollout_enabled(RUNTIME_V2_EXECUTION)
    if execution_enabled and not events_enabled:
        return "off"
    if execution_enabled:
        return "on"
    if events_enabled:
        return "shadow"
    return "off"


_SURFACE_EXECUTION_FLAGS = {
    "chat": RUNTIME_V2_CHAT_EXECUTION,
    "agent": RUNTIME_V2_AGENT_EXECUTION,
}


def surface_gateway_mode(surface: str, *, activation_ready: bool = False) -> str:
    """Require global, surface, and internal readiness before gateway-on acceptance."""
    if surface not in _SURFACE_EXECUTION_FLAGS:
        raise ValueError("surface must be chat or agent")
    if not isinstance(activation_ready, bool):
        raise ValueError("activation_ready must be a boolean")
    global_mode = gateway_mode()
    if global_mode != "on":
        return global_mode
    if not rollout_enabled(_SURFACE_EXECUTION_FLAGS[surface]):
        return "shadow"
    return "on" if activation_ready else "shadow"

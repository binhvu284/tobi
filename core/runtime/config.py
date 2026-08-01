"""Fail-closed rollout controls for Mission Control Infrastructure V2."""
from __future__ import annotations

from core import owner_flags


RUNTIME_V2_EVENTS = owner_flags.RUNTIME_V2_EVENTS
RUNTIME_V2_EXECUTION = owner_flags.RUNTIME_V2_EXECUTION
RUNTIME_V2_TOOLS = owner_flags.RUNTIME_V2_TOOLS
RUNTIME_V2_POLICY = owner_flags.RUNTIME_V2_POLICY
RUNTIME_V2_CONTEXT = owner_flags.RUNTIME_V2_CONTEXT
RUNTIME_V2_HERMES = owner_flags.RUNTIME_V2_HERMES
RUNTIME_V2_UI = owner_flags.RUNTIME_V2_UI

RUNTIME_V2_FLAGS = (
    RUNTIME_V2_EVENTS,
    RUNTIME_V2_EXECUTION,
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

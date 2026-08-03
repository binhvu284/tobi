"""Canonical Mission Control Runtime V2 run states and legal transitions."""
from __future__ import annotations

from enum import Enum


class RunStatus(str, Enum):
    ACCEPTED = "accepted"
    ROUTING = "routing"
    CLARIFYING = "clarifying"
    PLANNED = "planned"
    WAITING_APPROVAL = "waiting_approval"
    RUNNING = "running"
    WAITING_EXTERNAL = "waiting_external"
    RECOVERING = "recovering"
    WAITING_OWNER = "waiting_owner"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_STATUSES = frozenset(
    {RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED}
)

LEGAL_TRANSITIONS: dict[RunStatus, frozenset[RunStatus]] = {
    RunStatus.ACCEPTED: frozenset({RunStatus.ROUTING}),
    RunStatus.ROUTING: frozenset({RunStatus.CLARIFYING, RunStatus.PLANNED}),
    RunStatus.CLARIFYING: frozenset({RunStatus.ROUTING}),
    RunStatus.PLANNED: frozenset({RunStatus.WAITING_APPROVAL, RunStatus.RUNNING}),
    RunStatus.WAITING_APPROVAL: frozenset({RunStatus.RUNNING, RunStatus.CANCELLED}),
    RunStatus.RUNNING: frozenset(
        {
            RunStatus.WAITING_EXTERNAL,
            RunStatus.RECOVERING,
            RunStatus.SUCCEEDED,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
        }
    ),
    RunStatus.WAITING_EXTERNAL: frozenset({RunStatus.RUNNING}),
    RunStatus.RECOVERING: frozenset({RunStatus.RUNNING, RunStatus.WAITING_OWNER}),
    RunStatus.WAITING_OWNER: frozenset({RunStatus.RUNNING, RunStatus.CANCELLED}),
    RunStatus.SUCCEEDED: frozenset(),
    RunStatus.FAILED: frozenset(),
    RunStatus.CANCELLED: frozenset(),
}


class RunStateError(ValueError):
    """A requested run transition violates the canonical state machine."""


def as_run_status(value: RunStatus | str) -> RunStatus:
    if isinstance(value, RunStatus):
        return value
    try:
        return RunStatus(value)
    except (TypeError, ValueError) as exc:
        raise RunStateError(f"unknown run status: {value!r}") from exc


def require_transition(current: RunStatus | str, target: RunStatus | str) -> None:
    current_status = as_run_status(current)
    target_status = as_run_status(target)
    if target_status not in LEGAL_TRANSITIONS[current_status]:
        raise RunStateError(
            f"run cannot transition from {current_status.value} to {target_status.value}"
        )

"""The single authority for coding-workflow states, stages, and their meaning.

Everything that classifies a workflow reads from here: the agent, the store, the API, and
— via `scripts/generate_developer_states.py` — the Mission Control frontend.

This module exists because the vocabulary was previously copied into seven places, two of
them as SQL string literals and two more as hand-maintained TypeScript sets. Adding the
`locally_complete` state to some copies and not others produced two defects in two days:
the API kept serving a finished run as the active workflow, and the Process tab rendered
it as still running. Neither copy was wrong on its own; there was simply no place where
the vocabulary was defined once.

Adding a state means editing this file and re-running the generator. `tests/
test_developer_states_sync.py` fails if the generated TypeScript falls behind.
"""
from __future__ import annotations

from typing import Any, Literal


StateKind = Literal["active", "success", "fault", "waiting", "idle"]

# Every state a coding session can hold, mapped to how it should be read. The kind — not the
# state name — decides tone, terminality, and whether the owner is being asked for anything,
# so a new state gets classified once here instead of in each surface that displays it.
STATE_KIND: dict[str, StateKind] = {
    # Running: work is in flight and the runtime owns the session.
    "approved": "active",
    "preparing": "active",
    "coding": "active",
    "validating": "active",
    "reviewing": "active",
    "pushed": "active",
    "merging": "active",
    "deploying": "active",
    # Finished well.
    "completed": "success",
    # Also finished well: every stage the reviewed policy permits has passed and the branch
    # is committed, but a capability such as `github` is off so the run stops before any
    # remote mutation. Terminal because granting the capability changes `policy_hash`, and a
    # workflow whose stored hash no longer matches cannot be resumed.
    "locally_complete": "success",
    # Finished badly, or stopped by the owner.
    "failed": "fault",
    "rolled_back": "fault",
    "canceled": "idle",
    # Stopped, waiting on something. `paused` covers both an owner pause and a recoverable
    # fault; the distinction lives in `error_code`, not the state.
    "paused": "waiting",
    "blocked": "waiting",
    "awaiting_merge_deploy_approval": "waiting",
}

ACTIVE_STATES = frozenset(state for state, kind in STATE_KIND.items() if kind == "active")
TERMINAL_STATES = frozenset(
    state for state, kind in STATE_KIND.items() if kind in {"success", "fault", "idle"}
)
SUCCESS_STATES = frozenset(state for state, kind in STATE_KIND.items() if kind == "success")
FAULT_STATES = frozenset(state for state, kind in STATE_KIND.items() if kind == "fault")

# Retention: a finished run that did not fault may have its worktree and artifacts reclaimed
# once the retention window passes. Faults are excluded because their evidence is what the
# owner investigates. The commit itself is never at risk -- a git worktree shares the repo's
# object store, so removing the directory does not remove the branch.
CLEANUP_ELIGIBLE_STATES = TERMINAL_STATES - FAULT_STATES

# The ordered stage DAG. `capability` names the policy capability the gate requires; a gate
# whose capability is disabled is not pending and not failed — it is unreachable, and saying
# so is the difference between reporting a clean run and reporting a stalled one.
STAGES: list[dict[str, Any]] = [
    {"id": "prepare", "title": "Create isolated worktree", "depends": [], "capability": None},
    {"id": "index", "title": "Build scoped repository context", "depends": ["prepare"], "capability": None},
    {"id": "code", "title": "Run selected coding worker", "depends": ["index"], "capability": None},
    {"id": "validate", "title": "Run mandatory checks", "depends": ["code"], "capability": None},
    {"id": "review", "title": "Review scope, policy, and evidence", "depends": ["validate"], "capability": None},
    {"id": "commit", "title": "Create logical checkpoint", "depends": ["review"], "capability": None},
    {"id": "scan", "title": "Perform final secret scan", "depends": ["commit"], "capability": None},
    {"id": "push", "title": "Push feature branch", "depends": ["scan"], "capability": "github"},
    {"id": "pull_request", "title": "Create draft pull request", "depends": ["push"], "capability": "github"},
    {"id": "merge_deploy", "title": "Owner merge and deploy gate", "depends": ["pull_request"], "capability": "merge"},
    {"id": "health", "title": "Verify release health", "depends": ["merge_deploy"], "capability": "deploy"},
]

STAGE_ORDER: tuple[str, ...] = tuple(stage["id"] for stage in STAGES)
STAGE_CAPABILITY: dict[str, str | None] = {stage["id"]: stage["capability"] for stage in STAGES}


def permitted_stages(capabilities: dict[str, bool] | None) -> tuple[str, ...]:
    """The gates this policy actually allows a run to reach."""
    caps = capabilities or {}
    return tuple(
        stage_id for stage_id in STAGE_ORDER
        if not STAGE_CAPABILITY[stage_id] or bool(caps.get(str(STAGE_CAPABILITY[stage_id])))
    )


def state_in_clause(column: str, states: frozenset[str]) -> tuple[str, list[str]]:
    """Build a bound `IN (...)` fragment so SQL cannot fall behind the vocabulary.

    Two queries used to inline the active-state names as a literal string. Both silently
    kept their old meaning every time a state was added.
    """
    ordered = sorted(states)
    return f"{column} IN ({','.join('?' * len(ordered))})", ordered

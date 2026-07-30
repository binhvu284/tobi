"""Structured Queue plan parsing regressions."""
from core.coding_queue import (
    _criteria_from_plan,
    parse_queue,
    queue_execution_state,
    task_execution_state,
)


def test_acceptance_section_excludes_scope_and_dependency_bullets() -> None:
    plan = """# Fixture

## Scope

- The file must contain a marker.

## Acceptance Criteria

- Must create one file
- Must include the marker
- Must identify the selected agent

## Dependencies

- The reviewer must report Ready
"""

    assert _criteria_from_plan(plan) == [
        "Must create one file",
        "Must include the marker",
        "Must identify the selected agent",
    ]


def test_coding_agent_acceptance_fixtures_fit_one_session() -> None:
    items = {item["queue_id"]: item for item in parse_queue()}

    assert len(items[27]["acceptance_criteria"]) == 3
    assert len(items[28]["acceptance_criteria"]) == 3


def test_queue_status_maps_to_one_execution_vocabulary() -> None:
    assert queue_execution_state("Draft") == "ready"
    assert queue_execution_state("Ready - owner reviewed") == "ready"
    assert queue_execution_state("In progress (qualification pending)") == "in_progress"
    assert queue_execution_state("Blocked by #22") == "blocked"
    assert queue_execution_state("Blocked until #22 is completed") == "blocked"
    assert queue_execution_state("Delivered 2026-07-28") == "done"
    assert queue_execution_state("Done - merged") == "done"


def test_runtime_override_can_requeue_a_completed_source_item() -> None:
    assert task_execution_state({
        "status": "planned",
        "queue_status": "Done",
        "status_override": 1,
    }) == "ready"

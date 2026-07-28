"""Structured Queue plan parsing regressions."""
from core.coding_queue import _criteria_from_plan, parse_queue


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

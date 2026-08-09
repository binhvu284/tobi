"""Dormant canonical adapter for the first two project tools."""
from __future__ import annotations

import copy
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from typing import Any

from core.runtime.contracts import (
    RiskLevel,
    SideEffectClass,
    ToolAvailability,
    ToolAvailabilityStatus,
    ToolCatalogEntry,
)
from core.runtime.tool_adapters import adapt_legacy_catalog
from core.runtime.tool_catalog import CanonicalToolCatalog
from core.runtime.tool_execution import (
    CanonicalToolExecutor,
    ToolExecutionBinding,
    ToolExecutionError,
)


PROJECT_NAMESPACE = "tobi.projects"
PROJECT_VERSION = "1"
LIST_PROJECTS_REF = f"{PROJECT_NAMESPACE}.list_projects@{PROJECT_VERSION}"
CREATE_TASK_REF = f"{PROJECT_NAMESPACE}.create_task@{PROJECT_VERSION}"


LIST_PROJECTS_OUTPUT_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
        "count": {"type": "integer", "minimum": 0},
        "projects": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer", "minimum": 1},
                    "name": {"type": "string"},
                    "status": {"type": "string"},
                    "category": {"type": ["string", "null"]},
                    "progress_pct": {"type": ["number", "null"]},
                },
                "required": ["id", "name", "status", "category", "progress_pct"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["count", "projects"],
    "additionalProperties": False,
}

CREATE_TASK_OUTPUT_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
        "ok": {"const": True},
        "task_id": {"type": "integer", "minimum": 1},
        "title": {"type": "string", "minLength": 1},
        "project_id": {"type": "integer", "minimum": 1},
    },
    "required": ["ok", "task_id", "title", "project_id"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class ProjectToolRuntime:
    catalog: CanonicalToolCatalog
    executor: CanonicalToolExecutor


def _input_schema(entry: ToolCatalogEntry, name: str) -> dict[str, Any]:
    schema = copy.deepcopy(entry.spec.input_schema)
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    if name == "list_projects":
        return schema
    properties = schema.setdefault("properties", {})
    properties.setdefault("project_id", {"type": "integer"})["minimum"] = 1
    properties.setdefault("title", {"type": "string"}).update(
        {"minLength": 1, "pattern": r".*\S.*"}
    )
    properties.setdefault("description", {"type": "string"})
    schema["required"] = ["project_id", "title"]
    schema["additionalProperties"] = False
    return schema


def _promote(entry: ToolCatalogEntry) -> ToolCatalogEntry:
    name = entry.spec.name
    if name == "list_projects":
        spec = replace(
            entry.spec,
            input_schema=_input_schema(entry, name),
            output_schema=copy.deepcopy(LIST_PROJECTS_OUTPUT_SCHEMA),
            side_effect_class=SideEffectClass.NONE,
            risk=RiskLevel.NONE,
            required_permissions=("projects.read",),
            retry_policy="none",
            idempotency_policy="none",
            audit_policy="project_read",
            adapter="project_runtime_v2",
        )
    elif name == "create_task":
        spec = replace(
            entry.spec,
            input_schema=_input_schema(entry, name),
            output_schema=copy.deepcopy(CREATE_TASK_OUTPUT_SCHEMA),
            side_effect_class=SideEffectClass.REVERSIBLE,
            risk=RiskLevel.LOW,
            required_permissions=("projects.write",),
            retry_policy="none",
            idempotency_policy="required",
            audit_policy="receipt_required",
            adapter="project_runtime_v2",
        )
    else:
        raise ToolExecutionError("tool.project_source_unexpected")
    return ToolCatalogEntry(
        source_key=entry.source_key,
        spec=spec,
        availability=ToolAvailability(
            tool_ref=spec.ref,
            status=ToolAvailabilityStatus.AVAILABLE,
            reason_codes=("project.migration_run1",),
        ),
    )


def _project_target(arguments: Mapping[str, Any]) -> str:
    return f"project:{int(arguments['project_id'])}"


def _task_effect(arguments: Mapping[str, Any], output: Any) -> str:
    return f"Created task {int(output['task_id'])} in project {int(arguments['project_id'])}"


def _task_external_ref(output: Any) -> str:
    return f"task:{int(output['task_id'])}"


def _task_evidence(output: Any) -> tuple[str, ...]:
    return (_task_external_ref(output),)


def build_project_tool_runtime(
    *,
    list_projects_tool: Callable[..., Any] | None = None,
    create_task_tool: Callable[..., Any] | None = None,
) -> ProjectToolRuntime:
    """Build an isolated two-tool runtime without registering a live caller."""
    from core import conductor_registry

    if list_projects_tool is None:
        list_projects_tool = conductor_registry.READ_TOOLS["list_projects"][0]
    if create_task_tool is None:
        create_task_tool = conductor_registry.ACT_TOOLS["create_task"][0]
    adapted = adapt_legacy_catalog(
        {
            "list_projects": conductor_registry.TOOL_SPECS["list_projects"],
            "create_task": conductor_registry.TOOL_SPECS["create_task"],
        },
        namespace=PROJECT_NAMESPACE,
        version=PROJECT_VERSION,
    )
    if adapted.issues or len(adapted.entries) != 2:
        raise ToolExecutionError("tool.project_catalog_invalid")
    entries = tuple(_promote(entry) for entry in adapted.entries)
    catalog = CanonicalToolCatalog(entries)
    executor = CanonicalToolExecutor(
        catalog,
        (
            ToolExecutionBinding(
                tool_ref=LIST_PROJECTS_REF,
                invoke=list_projects_tool,
                target_from_arguments=lambda _arguments: "projects:collection",
                read_failure_owner_message=(
                    "TOBI could not read the requested project data."
                ),
                evidence_refs=lambda _output: ("projects:collection",),
            ),
            ToolExecutionBinding(
                tool_ref=CREATE_TASK_REF,
                invoke=create_task_tool,
                target_from_arguments=_project_target,
                effect_summary=_task_effect,
                external_ref=_task_external_ref,
                evidence_refs=_task_evidence,
                reported_error_is_not_applied=True,
            ),
        ),
    )
    return ProjectToolRuntime(catalog=catalog, executor=executor)

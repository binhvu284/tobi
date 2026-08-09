"""Dormant canonical adapter for approved coding-worktree file reads."""
from __future__ import annotations

import copy
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from core.runtime.contracts import (
    RiskLevel,
    RuntimeToolSpec,
    SideEffectClass,
    Surface,
    ToolAvailability,
    ToolAvailabilityStatus,
    ToolCatalogEntry,
)
from core.runtime.tool_catalog import CanonicalToolCatalog
from core.runtime.tool_execution import (
    CanonicalToolExecutor,
    ToolExecutionBinding,
    ToolExecutionError,
)


FILE_NAMESPACE = "tobi.files"
FILE_VERSION = "1"
READ_FILE_REF = f"{FILE_NAMESPACE}.read_file@{FILE_VERSION}"
LIST_FILES_REF = f"{FILE_NAMESPACE}.list_files@{FILE_VERSION}"

MAX_PATH_LENGTH = 1_024
MAX_READ_BYTES = 250_000
MAX_LIST_FILES = 500
JSON_SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"
RELATIVE_PATH_PATTERN = r"^(?![\\/]|[A-Za-z]:)(?!.*\x00).*\S.*$"


class FileToolBroker(Protocol):
    """The existing broker interface this dormant adapter is allowed to call."""

    def read_file(self, path: str) -> dict[str, Any]: ...

    def list_files(self, prefix: str = "", limit: int = 200) -> dict[str, Any]: ...


READ_FILE_INPUT_SCHEMA = {
    "$schema": JSON_SCHEMA_DIALECT,
    "type": "object",
    "properties": {
        "path": {
            "type": "string",
            "minLength": 1,
            "maxLength": MAX_PATH_LENGTH,
            "pattern": RELATIVE_PATH_PATTERN,
        },
    },
    "required": ["path"],
    "additionalProperties": False,
}

READ_FILE_OUTPUT_SCHEMA = {
    "$schema": JSON_SCHEMA_DIALECT,
    "type": "object",
    "properties": {
        "path": {
            "type": "string",
            "minLength": 1,
            "maxLength": MAX_PATH_LENGTH,
            "pattern": RELATIVE_PATH_PATTERN,
        },
        "content": {"type": "string", "maxLength": MAX_READ_BYTES},
        "bytes": {"type": "integer", "minimum": 0, "maximum": MAX_READ_BYTES},
    },
    "required": ["path", "content", "bytes"],
    "additionalProperties": False,
}

LIST_FILES_INPUT_SCHEMA = {
    "$schema": JSON_SCHEMA_DIALECT,
    "type": "object",
    "properties": {
        "prefix": {
            "type": "string",
            "minLength": 1,
            "maxLength": MAX_PATH_LENGTH,
            "pattern": RELATIVE_PATH_PATTERN,
        },
        "limit": {
            "type": "integer",
            "minimum": 1,
            "maximum": MAX_LIST_FILES,
        },
    },
    "additionalProperties": False,
}

LIST_FILES_OUTPUT_SCHEMA = {
    "$schema": JSON_SCHEMA_DIALECT,
    "type": "object",
    "properties": {
        "files": {
            "type": "array",
            "maxItems": MAX_LIST_FILES,
            "uniqueItems": True,
            "items": {
                "type": "string",
                "minLength": 1,
                "maxLength": MAX_PATH_LENGTH,
                "pattern": RELATIVE_PATH_PATTERN,
            },
        },
        "truncated": {"type": "boolean"},
    },
    "required": ["files", "truncated"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class FileToolRuntime:
    catalog: CanonicalToolCatalog
    executor: CanonicalToolExecutor


def _entry(
    *,
    name: str,
    description: str,
    input_schema: dict[str, Any],
    output_schema: dict[str, Any],
) -> ToolCatalogEntry:
    spec = RuntimeToolSpec(
        name=name,
        namespace=FILE_NAMESPACE,
        version=FILE_VERSION,
        description=description,
        input_schema=copy.deepcopy(input_schema),
        output_schema=copy.deepcopy(output_schema),
        side_effect_class=SideEffectClass.NONE,
        risk=RiskLevel.NONE,
        allowed_modes=("agent",),
        allowed_surfaces=(Surface.DEVELOPER,),
        required_permissions=("files.read",),
        timeout_s=30,
        retry_policy="none",
        idempotency_policy="none",
        isolation="workspace",
        audit_policy="file_read",
        adapter="file_runtime_v2",
    )
    return ToolCatalogEntry(
        source_key=f"coding_tools:{name}",
        spec=spec,
        availability=ToolAvailability(
            tool_ref=spec.ref,
            status=ToolAvailabilityStatus.AVAILABLE,
            reason_codes=("file.migration_run2a",),
        ),
    )


def _target_fragment(value: str) -> str:
    return value.replace("\\", "/")


def _read_target(arguments: Mapping[str, Any]) -> str:
    return f"file:{_target_fragment(arguments['path'])}"


def _list_target(arguments: Mapping[str, Any]) -> str:
    prefix = arguments.get("prefix")
    return f"files:{_target_fragment(prefix)}" if prefix else "files:collection"


def _read_evidence(output: Any) -> tuple[str, ...]:
    return (f"file:{output['path']}",)


def _redacted_read_output(output: Any) -> dict[str, Any]:
    return {
        "path": output["path"],
        "content": "[REDACTED]",
        "bytes": output["bytes"],
    }


def build_file_tool_runtime(*, broker: FileToolBroker) -> FileToolRuntime:
    """Build an isolated read-only runtime around a caller-owned coding broker."""
    if not callable(getattr(broker, "read_file", None)) or not callable(
        getattr(broker, "list_files", None)
    ):
        raise ToolExecutionError("tool.file_broker_invalid")

    entries = (
        _entry(
            name="list_files",
            description="List policy-indexable files under one coding worktree folder.",
            input_schema=LIST_FILES_INPUT_SCHEMA,
            output_schema=LIST_FILES_OUTPUT_SCHEMA,
        ),
        _entry(
            name="read_file",
            description="Read UTF-8 text from one policy-approved coding worktree file.",
            input_schema=READ_FILE_INPUT_SCHEMA,
            output_schema=READ_FILE_OUTPUT_SCHEMA,
        ),
    )
    catalog = CanonicalToolCatalog(entries)
    executor = CanonicalToolExecutor(
        catalog,
        (
            ToolExecutionBinding(
                tool_ref=LIST_FILES_REF,
                invoke=broker.list_files,
                target_from_arguments=_list_target,
                read_failure_owner_message=(
                    "TOBI could not list that project folder. "
                    "Check that the folder exists and is allowed."
                ),
                evidence_refs=lambda _output: ("files:collection",),
            ),
            ToolExecutionBinding(
                tool_ref=READ_FILE_REF,
                invoke=broker.read_file,
                target_from_arguments=_read_target,
                read_failure_owner_message=(
                    "TOBI could not read that project file. "
                    "Check that the path exists and is allowed."
                ),
                evidence_refs=_read_evidence,
                read_output_for_persistence=_redacted_read_output,
            ),
        ),
    )
    return FileToolRuntime(catalog=catalog, executor=executor)

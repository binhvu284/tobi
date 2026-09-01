"""Dormant canonical adapter for approved coding-worktree file operations."""
from __future__ import annotations

import copy
import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from core.coding_tools import CodingToolError
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
    ToolActionReconciliation,
    ToolExecutionBinding,
    ToolExecutionError,
)


FILE_NAMESPACE = "tobi.files"
FILE_VERSION = "1"
READ_FILE_REF = f"{FILE_NAMESPACE}.read_file@{FILE_VERSION}"
LIST_FILES_REF = f"{FILE_NAMESPACE}.list_files@{FILE_VERSION}"
WRITE_FILE_REF = f"{FILE_NAMESPACE}.write_file@{FILE_VERSION}"

MAX_PATH_LENGTH = 1_024
MAX_READ_BYTES = 250_000
MAX_LIST_FILES = 500
JSON_SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"
RELATIVE_PATH_PATTERN = r"^(?![\\/]|[A-Za-z]:)(?!.*\x00).*\S.*$"


class FileToolBroker(Protocol):
    """The existing broker interface this dormant adapter is allowed to call."""

    def read_file(self, path: str) -> dict[str, Any]: ...

    def list_files(self, prefix: str = "", limit: int = 200) -> dict[str, Any]: ...

    def write_file(self, path: str, content: str) -> dict[str, Any]: ...


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

SHA256_PATTERN = r"^(?:absent|[0-9a-f]{64})$"

WRITE_FILE_INPUT_SCHEMA = {
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
        "expected_sha256": {"type": "string", "pattern": SHA256_PATTERN},
    },
    "required": ["path", "content", "expected_sha256"],
    "additionalProperties": False,
}

WRITE_FILE_OUTPUT_SCHEMA = {
    "$schema": JSON_SCHEMA_DIALECT,
    "type": "object",
    "properties": {
        "path": {
            "type": "string",
            "minLength": 1,
            "maxLength": MAX_PATH_LENGTH,
            "pattern": RELATIVE_PATH_PATTERN,
        },
        "bytes": {"type": "integer", "minimum": 0, "maximum": MAX_READ_BYTES},
        "before_sha256": {"type": "string", "pattern": SHA256_PATTERN},
        "after_sha256": {"type": "string", "pattern": r"^[0-9a-f]{64}$"},
    },
    "required": ["path", "bytes", "before_sha256", "after_sha256"],
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
    side_effect_class: SideEffectClass = SideEffectClass.NONE,
    risk: RiskLevel = RiskLevel.NONE,
    required_permissions: tuple[str, ...] = ("files.read",),
    retry_policy: str = "none",
    idempotency_policy: str = "none",
    audit_policy: str = "file_read",
    reason_code: str = "file.migration_run2a",
    allowed_surfaces: tuple[Surface, ...] = (Surface.DEVELOPER,),
) -> ToolCatalogEntry:
    spec = RuntimeToolSpec(
        name=name,
        namespace=FILE_NAMESPACE,
        version=FILE_VERSION,
        description=description,
        input_schema=copy.deepcopy(input_schema),
        output_schema=copy.deepcopy(output_schema),
        side_effect_class=side_effect_class,
        risk=risk,
        allowed_modes=("agent",),
        allowed_surfaces=allowed_surfaces,
        required_permissions=required_permissions,
        timeout_s=30,
        retry_policy=retry_policy,
        idempotency_policy=idempotency_policy,
        isolation="workspace",
        audit_policy=audit_policy,
        adapter="file_runtime_v2",
    )
    return ToolCatalogEntry(
        source_key=f"coding_tools:{name}",
        spec=spec,
        availability=ToolAvailability(
            tool_ref=spec.ref,
            status=ToolAvailabilityStatus.AVAILABLE,
            reason_codes=(reason_code,),
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


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _file_state(broker: FileToolBroker, path: str) -> str:
    try:
        current = broker.read_file(path)
    except CodingToolError as exc:
        if str(exc).startswith("File does not exist:"):
            return "absent"
        raise
    content = current["content"]
    encoded = content.encode("utf-8")
    if len(encoded) != current["bytes"]:
        raise ToolExecutionError("tool.file_content_not_utf8")
    return hashlib.sha256(encoded).hexdigest()


class _FileWriteAdapter:
    def __init__(self, broker: FileToolBroker) -> None:
        self._broker = broker

    def invoke(
        self, *, path: str, content: str, expected_sha256: str
    ) -> dict[str, Any]:
        encoded = content.encode("utf-8")
        if len(encoded) > MAX_READ_BYTES:
            return {"error": "file.write_too_large"}
        before_sha256 = _file_state(self._broker, path)
        if before_sha256 != expected_sha256:
            return {"error": "file.precondition_failed"}
        result = self._broker.write_file(path, content)
        if result.get("bytes") != len(encoded):
            raise ToolExecutionError("tool.file_write_result_mismatch")
        return {
            "path": result["path"],
            "bytes": result["bytes"],
            "before_sha256": before_sha256,
            "after_sha256": hashlib.sha256(encoded).hexdigest(),
        }

    def reconcile(
        self, arguments: Mapping[str, Any]
    ) -> ToolActionReconciliation:
        path = arguments["path"]
        expected_sha256 = arguments["expected_sha256"]
        after_sha256 = _sha256(arguments["content"])
        try:
            current_sha256 = _file_state(self._broker, path)
        except Exception:
            return ToolActionReconciliation(
                outcome="unknown",
                summary="The current file state could not be inspected safely",
            )
        current_ref = _state_ref(path, current_sha256)
        if current_sha256 == after_sha256:
            return ToolActionReconciliation(
                outcome="applied",
                summary="The current file hash matches the intended written content",
                evidence_refs=(current_ref,),
                output={
                    "path": path.replace("\\", "/"),
                    "bytes": len(arguments["content"].encode("utf-8")),
                    "before_sha256": expected_sha256,
                    "after_sha256": after_sha256,
                },
            )
        if current_sha256 == expected_sha256:
            return ToolActionReconciliation(
                outcome="not_applied",
                summary="The current file hash still matches the expected before state",
                evidence_refs=(current_ref,),
            )
        return ToolActionReconciliation(
            outcome="unknown",
            summary="The current file hash matches neither the before nor intended state",
            evidence_refs=(current_ref,),
        )


def _write_arguments_for_persistence(
    arguments: Mapping[str, Any]
) -> dict[str, Any]:
    content = arguments["content"]
    return {
        "path": arguments["path"],
        "content": "[REDACTED]",
        "content_bytes": len(content.encode("utf-8")),
        "content_sha256": _sha256(content),
        "expected_sha256": arguments["expected_sha256"],
    }


def _state_ref(path: str, state: str) -> str:
    normalized = path.replace("\\", "/")
    return (
        f"file:{normalized}@absent"
        if state == "absent"
        else f"file:{normalized}@sha256:{state}"
    )


def _write_effect(_arguments: Mapping[str, Any], output: Any) -> str:
    return f"Wrote {int(output['bytes'])} bytes to {output['path']}"


def _write_external_ref(output: Any) -> str:
    return f"file:{output['path']}"


def _write_evidence(output: Any) -> tuple[str, ...]:
    return (_state_ref(output["path"], output["after_sha256"]),)


def _write_before_ref(output: Any) -> str:
    return _state_ref(output["path"], output["before_sha256"])


def _write_after_ref(output: Any) -> str:
    return _state_ref(output["path"], output["after_sha256"])


def build_file_tool_runtime(
    *,
    broker: FileToolBroker,
    control: Any = None,
    read_surfaces: tuple[Surface, ...] = (Surface.DEVELOPER,),
) -> FileToolRuntime:
    """Build an isolated runtime around a caller-owned coding broker."""
    if not callable(getattr(broker, "read_file", None)) or not callable(
        getattr(broker, "list_files", None)
    ) or not callable(getattr(broker, "write_file", None)):
        raise ToolExecutionError("tool.file_broker_invalid")
    if not read_surfaces or any(not isinstance(item, Surface) for item in read_surfaces):
        raise ToolExecutionError("tool.file_read_surfaces_invalid")
    write_adapter = _FileWriteAdapter(broker)

    entries = (
        _entry(
            name="list_files",
            description="List policy-indexable files under one coding worktree folder.",
            input_schema=LIST_FILES_INPUT_SCHEMA,
            output_schema=LIST_FILES_OUTPUT_SCHEMA,
            allowed_surfaces=read_surfaces,
        ),
        _entry(
            name="read_file",
            description="Read UTF-8 text from one policy-approved coding worktree file.",
            input_schema=READ_FILE_INPUT_SCHEMA,
            output_schema=READ_FILE_OUTPUT_SCHEMA,
            allowed_surfaces=read_surfaces,
        ),
        _entry(
            name="write_file",
            description=(
                "Atomically write UTF-8 text to one policy-approved coding worktree file."
            ),
            input_schema=WRITE_FILE_INPUT_SCHEMA,
            output_schema=WRITE_FILE_OUTPUT_SCHEMA,
            side_effect_class=SideEffectClass.REVERSIBLE,
            risk=RiskLevel.MEDIUM,
            required_permissions=("files.write",),
            idempotency_policy="required",
            audit_policy="receipt_required",
            reason_code="file.migration_run2b",
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
            ToolExecutionBinding(
                tool_ref=WRITE_FILE_REF,
                invoke=write_adapter.invoke,
                target_from_arguments=_read_target,
                effect_summary=_write_effect,
                external_ref=_write_external_ref,
                evidence_refs=_write_evidence,
                before_ref=_write_before_ref,
                after_ref=_write_after_ref,
                action_arguments_for_persistence=_write_arguments_for_persistence,
                action_reconciliation=write_adapter.reconcile,
                action_not_applied_owner_message=(
                    "TOBI did not write that project file because its current state changed."
                ),
                action_not_applied_summary=(
                    "The file write precondition failed before any replacement"
                ),
                reported_error_is_not_applied=True,
            ),
        ),
        control=control,
    )
    return FileToolRuntime(catalog=catalog, executor=executor)

"""Dormant canonical tool metadata, schema validation, and discovery."""
from __future__ import annotations

import copy
import re
from collections.abc import Mapping
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError

from core.runtime.contracts import (
    RuntimeToolSpec,
    ToolAvailability,
    ToolAvailabilityStatus,
    ToolDiscoveryQuery,
    ToolDiscoveryResult,
)


_MCP_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
_VERSION = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
_DIALECT = "https://json-schema.org/draft/2020-12/schema"


class ToolRegistryError(ValueError):
    """Base error for canonical registry boundaries."""


class ToolConflictError(ToolRegistryError):
    """A stable tool reference was reused for a different contract."""


class ToolSchemaError(ToolRegistryError):
    """A tool contract does not contain a safe JSON Schema 2020-12 shape."""


class ToolValidationError(ToolRegistryError):
    """Arguments or output do not satisfy the registered schema."""

    def __init__(self, *, tool_ref: str, boundary: str, path: str, rule: str) -> None:
        self.tool_ref = tool_ref
        self.boundary = boundary
        self.path = path
        self.rule = rule
        super().__init__(f"{boundary} validation failed at {path} ({rule})")


def _schema_path(parts: Any) -> str:
    rendered = "/".join(str(part) for part in parts)
    return f"/{rendered}" if rendered else "/"


def _reject_external_refs(value: Any, path: tuple[str, ...] = ()) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            current = (*path, str(key))
            if key in {"$ref", "$dynamicRef"} and isinstance(item, str):
                if item and not item.startswith("#"):
                    raise ToolSchemaError(
                        f"external schema reference is not allowed at {_schema_path(current)}"
                    )
            _reject_external_refs(item, current)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_external_refs(item, (*path, str(index)))


def _compile_schema(schema: dict[str, Any], *, boundary: str) -> Draft202012Validator:
    if boundary == "input" and schema.get("type") != "object":
        raise ToolSchemaError("input schema root type must be object")
    dialect = schema.get("$schema")
    if dialect not in {None, _DIALECT, f"{_DIALECT}#"}:
        raise ToolSchemaError("tool schemas must use JSON Schema 2020-12")
    _reject_external_refs(schema)
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise ToolSchemaError(
            f"invalid {boundary} schema at {_schema_path(exc.path)}"
        ) from exc
    return Draft202012Validator(schema, format_checker=FormatChecker())


def _validate_identity(spec: RuntimeToolSpec) -> None:
    if not _MCP_NAME.fullmatch(spec.name):
        raise ToolSchemaError("tool name is not MCP-compatible")
    if not _MCP_NAME.fullmatch(spec.namespace):
        raise ToolSchemaError("tool namespace is not MCP-compatible")
    if len(f"{spec.namespace}.{spec.name}") > 128:
        raise ToolSchemaError("namespaced MCP tool name must not exceed 128 characters")
    if not _VERSION.fullmatch(spec.version):
        raise ToolSchemaError("tool version contains unsupported characters")


class CanonicalToolRegistry:
    """In-memory authority for validated tool metadata; it never executes tools."""

    def __init__(self) -> None:
        self._specs: dict[str, RuntimeToolSpec] = {}
        self._input_validators: dict[str, Draft202012Validator] = {}
        self._output_validators: dict[str, Draft202012Validator] = {}
        self._availability: dict[str, ToolAvailability] = {}

    @property
    def registered_count(self) -> int:
        return len(self._specs)

    def register(self, spec: RuntimeToolSpec) -> RuntimeToolSpec:
        if not isinstance(spec, RuntimeToolSpec):
            raise ToolSchemaError("spec must be a RuntimeToolSpec")
        isolated = copy.deepcopy(spec)
        _validate_identity(isolated)
        input_validator = _compile_schema(isolated.input_schema, boundary="input")
        output_validator = _compile_schema(isolated.output_schema, boundary="output")

        existing = self._specs.get(isolated.ref)
        if existing is not None:
            if existing != isolated:
                raise ToolConflictError("tool reference already has a different contract")
            return copy.deepcopy(existing)

        self._specs[isolated.ref] = isolated
        self._input_validators[isolated.ref] = input_validator
        self._output_validators[isolated.ref] = output_validator
        self._availability[isolated.ref] = ToolAvailability(
            tool_ref=isolated.ref,
            status=ToolAvailabilityStatus.UNKNOWN,
            reason_codes=("availability.not_checked",),
        )
        return copy.deepcopy(isolated)

    def get(self, tool_ref: str) -> RuntimeToolSpec:
        try:
            return copy.deepcopy(self._specs[tool_ref])
        except KeyError as exc:
            raise ToolRegistryError("unknown tool reference") from exc

    def availability(self, tool_ref: str) -> ToolAvailability:
        self.get(tool_ref)
        return self._availability[tool_ref]

    def set_availability(
        self,
        tool_ref: str,
        status: ToolAvailabilityStatus,
        *,
        reason_codes: tuple[str, ...] = (),
    ) -> ToolAvailability:
        self.get(tool_ref)
        availability = ToolAvailability(
            tool_ref=tool_ref,
            status=status,
            reason_codes=reason_codes,
        )
        self._availability[tool_ref] = availability
        return availability

    def validate_arguments(self, tool_ref: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        self.get(tool_ref)
        if not isinstance(arguments, Mapping):
            raise ToolValidationError(
                tool_ref=tool_ref,
                boundary="input",
                path="/",
                rule="type",
            )
        isolated = copy.deepcopy(dict(arguments))
        self._validate(tool_ref, "input", isolated, self._input_validators[tool_ref])
        return isolated

    def validate_output(self, tool_ref: str, output: Any) -> Any:
        self.get(tool_ref)
        isolated = copy.deepcopy(output)
        self._validate(tool_ref, "output", isolated, self._output_validators[tool_ref])
        return isolated

    @staticmethod
    def _validate(
        tool_ref: str,
        boundary: str,
        value: Any,
        validator: Draft202012Validator,
    ) -> None:
        error = next(iter(validator.iter_errors(value)), None)
        if error is None:
            return
        raise ToolValidationError(
            tool_ref=tool_ref,
            boundary=boundary,
            path=_schema_path(error.absolute_path),
            rule=str(error.validator or "schema"),
        )

    def discover(self, query: ToolDiscoveryQuery) -> ToolDiscoveryResult:
        if not isinstance(query, ToolDiscoveryQuery):
            raise ToolRegistryError("query must be a ToolDiscoveryQuery")
        if not query.candidate_tool_refs:
            return ToolDiscoveryResult(tools=())

        matched: list[RuntimeToolSpec] = []
        for tool_ref in sorted(set(query.candidate_tool_refs)):
            spec = self._specs.get(tool_ref)
            if spec is None:
                continue
            if query.mode not in spec.allowed_modes or query.surface not in spec.allowed_surfaces:
                continue
            if self._availability[tool_ref].status is not ToolAvailabilityStatus.AVAILABLE:
                continue
            matched.append(copy.deepcopy(spec))

        return ToolDiscoveryResult(
            tools=tuple(matched[:query.limit]),
            truncated=len(matched) > query.limit,
        )

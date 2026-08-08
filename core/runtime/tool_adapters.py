"""Pure compatibility adapters for dormant canonical tool snapshots."""
from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from core.chat_runtime_contracts import ToolSpec as ChatToolSpec
from core.runtime.contracts import (
    RiskLevel,
    RuntimeToolSpec,
    SideEffectClass,
    Surface,
    ToolAvailability,
    ToolAvailabilityStatus,
    ToolCatalogEntry,
)
from core.runtime.tool_registry import CanonicalToolRegistry, ToolRegistryError


@dataclass(frozen=True)
class ToolAdapterIssue:
    source_key: str
    code: str


@dataclass(frozen=True)
class ToolAdapterResult:
    entries: tuple[ToolCatalogEntry, ...]
    issues: tuple[ToolAdapterIssue, ...] = ()


def _availability(
    spec: RuntimeToolSpec,
    status: ToolAvailabilityStatus,
    *reason_codes: str,
) -> ToolAvailability:
    return ToolAvailability(
        tool_ref=spec.ref,
        status=status,
        reason_codes=tuple(reason_codes),
    )


def _validated_entry(
    *,
    source_key: str,
    spec: RuntimeToolSpec,
    availability: ToolAvailability,
) -> tuple[ToolCatalogEntry | None, ToolAdapterIssue | None]:
    try:
        CanonicalToolRegistry().register(spec)
        entry = ToolCatalogEntry(
            source_key=source_key,
            spec=copy.deepcopy(spec),
            availability=availability,
        )
        return entry, None
    except (ToolRegistryError, ValueError, TypeError):
        return None, ToolAdapterIssue(source_key=source_key, code="schema.invalid")


def _result(entries: list[ToolCatalogEntry], issues: list[ToolAdapterIssue]) -> ToolAdapterResult:
    return ToolAdapterResult(
        entries=tuple(sorted(entries, key=lambda entry: entry.spec.ref)),
        issues=tuple(sorted(issues, key=lambda issue: (issue.source_key, issue.code))),
    )


def adapt_legacy_catalog(
    specs: Mapping[str, ChatToolSpec],
    *,
    namespace: str = "tobi.conductor",
    version: str = "legacy-1",
) -> ToolAdapterResult:
    """Map existing Chat/Conductor metadata without retaining its callables."""
    entries: list[ToolCatalogEntry] = []
    issues: list[ToolAdapterIssue] = []
    for catalog_name in sorted(specs):
        source_key = f"legacy:{catalog_name}"
        source = specs[catalog_name]
        if not isinstance(source, ChatToolSpec) or source.name != catalog_name:
            issues.append(ToolAdapterIssue(source_key, "metadata.invalid"))
            continue
        side_effect = (
            SideEffectClass.NONE
            if source.risk == "read"
            else SideEffectClass.IRREVERSIBLE
        )
        try:
            spec = RuntimeToolSpec.from_chat_spec(
                source,
                namespace=namespace,
                version=version,
                side_effect_class=side_effect,
                allowed_surfaces=(Surface.CHAT, Surface.AGENT),
                adapter="legacy_conductor_snapshot",
            )
        except ValueError:
            issues.append(ToolAdapterIssue(source_key, "metadata.invalid"))
            continue
        entry, issue = _validated_entry(
            source_key=source_key,
            spec=spec,
            availability=_availability(
                spec,
                ToolAvailabilityStatus.UNKNOWN,
                "legacy.not_activated",
            ),
        )
        if entry:
            entries.append(entry)
        if issue:
            issues.append(issue)
    return _result(entries, issues)


def _tool_mapping(tool: Any) -> dict[str, Any]:
    if isinstance(tool, Mapping):
        return copy.deepcopy(dict(tool))
    model_dump = getattr(tool, "model_dump", None)
    if callable(model_dump):
        return copy.deepcopy(model_dump(by_alias=True, exclude_none=True))
    result = {}
    for name in ("name", "description", "inputSchema", "outputSchema"):
        if hasattr(tool, name):
            result[name] = copy.deepcopy(getattr(tool, name))
    return result


def adapt_inbound_mcp_catalog(
    tools: Iterable[Any],
    *,
    sensitive_names: Iterable[str] = (),
    namespace: str = "mcp.inbound.tobi",
    version: str = "server-1",
) -> ToolAdapterResult:
    """Map public FastMCP tool definitions; annotations never decide authority."""
    sensitive = frozenset(sensitive_names)
    entries: list[ToolCatalogEntry] = []
    issues: list[ToolAdapterIssue] = []
    for tool in tools:
        data = _tool_mapping(tool)
        name = str(data.get("name") or "")
        source_key = f"mcp:inbound:{name or 'unknown'}"
        input_schema = data.get("inputSchema", data.get("input_schema"))
        output_schema = data.get("outputSchema", data.get("output_schema", {}))
        if not isinstance(input_schema, dict) or not isinstance(output_schema, dict):
            issues.append(ToolAdapterIssue(source_key, "schema.invalid"))
            continue
        is_sensitive = name in sensitive
        try:
            spec = RuntimeToolSpec(
                name=name,
                namespace=namespace,
                version=version,
                description=str(data.get("description") or f"Inbound MCP tool {name}"),
                input_schema=copy.deepcopy(input_schema),
                output_schema=copy.deepcopy(output_schema),
                side_effect_class=(
                    SideEffectClass.EXTERNAL if is_sensitive else SideEffectClass.NONE
                ),
                risk=RiskLevel.HIGH if is_sensitive else RiskLevel.NONE,
                allowed_modes=("agent",) if is_sensitive else ("chat", "agent"),
                allowed_surfaces=(Surface.MCP,),
                required_permissions=(f"mcp.inbound.{name}",),
                retry_policy="none",
                idempotency_policy="none",
                isolation="in_process",
                audit_policy="mcp_inbound",
                adapter="fastmcp_snapshot",
            )
        except (TypeError, ValueError):
            issues.append(ToolAdapterIssue(source_key, "metadata.invalid"))
            continue
        entry, issue = _validated_entry(
            source_key=source_key,
            spec=spec,
            availability=_availability(
                spec,
                ToolAvailabilityStatus.AVAILABLE,
                "mcp.server.loaded",
            ),
        )
        if entry:
            entries.append(entry)
        if issue:
            issues.append(issue)
    return _result(entries, issues)


def _content_version(source: str, name: str, schema: dict[str, Any]) -> str:
    encoded = json.dumps(
        {"source": source, "name": name, "input_schema": schema},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256-{hashlib.sha256(encoded).hexdigest()[:12]}"


def _outbound_availability(row: Mapping[str, Any]) -> tuple[ToolAvailabilityStatus, tuple[str, ...]]:
    if not bool(row.get("tool_enabled")):
        return ToolAvailabilityStatus.UNAVAILABLE, ("mcp.tool.disabled",)
    if not bool(row.get("connection_enabled")):
        return ToolAvailabilityStatus.UNAVAILABLE, ("mcp.connection.disabled",)
    status = str(row.get("connection_status") or "unknown").lower()
    if status == "connected" and row.get("last_tested_at"):
        return ToolAvailabilityStatus.AVAILABLE, ("mcp.connection.connected",)
    if status in {"error", "disconnected", "disabled"}:
        return ToolAvailabilityStatus.UNAVAILABLE, (f"mcp.connection.{status}",)
    return ToolAvailabilityStatus.UNKNOWN, ("mcp.connection.not_verified",)


def adapt_outbound_mcp_catalog(rows: Iterable[Mapping[str, Any]]) -> ToolAdapterResult:
    """Map safe persisted MCP snapshots with untrusted behavior metadata ignored."""
    entries: list[ToolCatalogEntry] = []
    issues: list[ToolAdapterIssue] = []
    for raw in rows:
        row = copy.deepcopy(dict(raw))
        source = str(row.get("source") or "")
        name = str(row.get("name") or "")
        source_key = f"mcp:outbound:{source or 'unknown'}:{name or 'unknown'}"
        input_schema = row.get("input_schema")
        if row.get("schema_error") or not isinstance(input_schema, dict):
            issues.append(ToolAdapterIssue(source_key, "schema.invalid"))
            continue
        try:
            spec = RuntimeToolSpec(
                name=name,
                namespace=f"mcp.outbound.connection_{source}",
                version=_content_version(source, name, input_schema),
                description=f"External MCP tool {name}",
                input_schema=copy.deepcopy(input_schema),
                output_schema={},
                side_effect_class=SideEffectClass.EXTERNAL,
                risk=RiskLevel.HIGH,
                allowed_modes=("agent",),
                allowed_surfaces=(Surface.AGENT,),
                required_permissions=(f"mcp.outbound.connection_{source}.{name}",),
                timeout_s=25,
                retry_policy="none",
                idempotency_policy="none",
                isolation="remote_mcp",
                audit_policy="mcp_outbound_untrusted",
                availability_probe=f"mcp.connection.{source}",
                adapter="mcp_outbound_snapshot",
            )
        except (TypeError, ValueError):
            issues.append(ToolAdapterIssue(source_key, "metadata.invalid"))
            continue
        status, reasons = _outbound_availability(row)
        entry, issue = _validated_entry(
            source_key=source_key,
            spec=spec,
            availability=_availability(spec, status, *reasons),
        )
        if entry:
            entries.append(entry)
        if issue:
            issues.append(issue)
    return _result(entries, issues)

"""Dormant catalog parity, call preparation, and activation readiness."""
from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Iterable, Mapping
from typing import Any, Optional

from core.runtime.contracts import (
    RuntimeToolCall,
    Surface,
    ToolActivationReadiness,
    ToolAvailabilityStatus,
    ToolCatalogEntry,
    ToolCatalogIssue,
    ToolCatalogManifest,
    ToolCatalogManifestEntry,
    ToolCatalogParityReport,
    ToolDiscoveryQuery,
    contract_to_dict,
)
from core.runtime.tool_adapters import ToolAdapterResult
from core.runtime.tool_registry import (
    CanonicalToolRegistry,
    ToolRegistryError,
    ToolValidationError,
)


class ToolCatalogError(ValueError):
    """A safe catalog boundary failure with a stable non-secret code."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class ToolCallPreparationError(ToolCatalogError):
    """A call was rejected before an executable request could exist."""


def _digest(value: Any) -> str:
    encoded = json.dumps(
        contract_to_dict(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _manifest_entry(entry: ToolCatalogEntry) -> ToolCatalogManifestEntry:
    return ToolCatalogManifestEntry(
        source_key=entry.source_key,
        tool_ref=entry.spec.ref,
        contract_digest=_digest({
            "spec": entry.spec,
            "catalog_contract_version": entry.contract_version,
        }),
        availability_status=entry.availability.status,
        availability_reason_codes=tuple(sorted(set(entry.availability.reason_codes))),
    )


def _build_manifest(
    entries: Iterable[ToolCatalogEntry],
    issues: Iterable[ToolCatalogIssue] = (),
) -> ToolCatalogManifest:
    manifest_entries = tuple(sorted(
        (_manifest_entry(entry) for entry in entries),
        key=lambda entry: (entry.source_key, entry.tool_ref),
    ))
    manifest_issues = tuple(sorted(
        (copy.deepcopy(issue) for issue in issues),
        key=lambda issue: (issue.source_key, issue.code),
    ))
    payload = {
        "entries": manifest_entries,
        "issues": manifest_issues,
        "contract_version": "1",
    }
    return ToolCatalogManifest(
        entries=manifest_entries,
        issues=manifest_issues,
        digest=_digest(payload),
    )


class CanonicalToolCatalog:
    """Caller-owned metadata snapshot; it validates calls but never executes them."""

    def __init__(
        self,
        entries: Iterable[ToolCatalogEntry],
        *,
        issues: Iterable[ToolCatalogIssue] = (),
    ) -> None:
        isolated = tuple(copy.deepcopy(tuple(entries)))
        issue_snapshot = tuple(copy.deepcopy(tuple(issues)))
        source_keys: set[str] = set()
        tool_refs: set[str] = set()
        registry = CanonicalToolRegistry()

        for entry in sorted(isolated, key=lambda item: (item.source_key, item.spec.ref)):
            if not isinstance(entry, ToolCatalogEntry):
                raise ToolCatalogError("catalog.entry_invalid")
            if entry.source_key in source_keys:
                raise ToolCatalogError("catalog.duplicate_source")
            if entry.spec.ref in tool_refs:
                raise ToolCatalogError("catalog.duplicate_tool_ref")
            source_keys.add(entry.source_key)
            tool_refs.add(entry.spec.ref)
            try:
                registry.register(entry.spec)
                registry.set_availability(
                    entry.spec.ref,
                    entry.availability.status,
                    reason_codes=entry.availability.reason_codes,
                )
            except ToolRegistryError as exc:
                raise ToolCatalogError("catalog.entry_invalid") from exc

        self._registry = registry
        self._manifest = _build_manifest(isolated, issue_snapshot)

    @classmethod
    def from_adapter_results(
        cls,
        results: Iterable[ToolAdapterResult],
    ) -> "CanonicalToolCatalog":
        entries: list[ToolCatalogEntry] = []
        issues: list[ToolCatalogIssue] = []
        for result in results:
            if not isinstance(result, ToolAdapterResult):
                raise ToolCatalogError("catalog.adapter_result_invalid")
            entries.extend(result.entries)
            issues.extend(
                ToolCatalogIssue(source_key=issue.source_key, code=issue.code)
                for issue in result.issues
            )
        return cls(entries, issues=issues)

    @property
    def manifest(self) -> ToolCatalogManifest:
        return copy.deepcopy(self._manifest)

    def prepare_call(
        self,
        *,
        call_id: str,
        run_id: str,
        step_id: str,
        tool_ref: str,
        arguments: Mapping[str, Any],
        surface: Surface,
        mode: str,
        candidate_tool_refs: tuple[str, ...],
        idempotency_key: Optional[str] = None,
        approval_id: Optional[str] = None,
        deadline: Optional[str] = None,
    ) -> RuntimeToolCall:
        if not candidate_tool_refs:
            raise ToolCallPreparationError("tool.allowlist_required")
        if tool_ref not in candidate_tool_refs:
            raise ToolCallPreparationError("tool.not_allowlisted")

        try:
            spec = self._registry.get(tool_ref)
        except ToolRegistryError as exc:
            raise ToolCallPreparationError("tool.unknown") from exc
        if surface not in spec.allowed_surfaces:
            raise ToolCallPreparationError("tool.surface_denied")
        if mode not in spec.allowed_modes:
            raise ToolCallPreparationError("tool.mode_denied")
        if self._registry.availability(tool_ref).status is not ToolAvailabilityStatus.AVAILABLE:
            raise ToolCallPreparationError("tool.unavailable")

        unique_candidates = tuple(sorted(set(candidate_tool_refs)))
        if len(unique_candidates) > 100:
            raise ToolCallPreparationError("tool.allowlist_too_large")
        try:
            discovered = self._registry.discover(ToolDiscoveryQuery(
                surface=surface,
                mode=mode,
                candidate_tool_refs=unique_candidates,
                limit=len(unique_candidates),
            ))
        except (TypeError, ValueError) as exc:
            raise ToolCallPreparationError("tool.request_invalid") from exc
        if all(item.ref != tool_ref for item in discovered.tools):
            raise ToolCallPreparationError("tool.not_discoverable")

        try:
            validated = self._registry.validate_arguments(tool_ref, arguments)
        except ToolValidationError as exc:
            raise ToolCallPreparationError("tool.arguments_invalid") from exc
        return RuntimeToolCall(
            call_id=call_id,
            run_id=run_id,
            step_id=step_id,
            tool_ref=tool_ref,
            validated_arguments=copy.deepcopy(validated),
            idempotency_key=idempotency_key,
            approval_id=approval_id,
            deadline=deadline,
        )


def compare_tool_manifests(
    expected: ToolCatalogManifest,
    observed: ToolCatalogManifest,
) -> ToolCatalogParityReport:
    if not isinstance(expected, ToolCatalogManifest) or not isinstance(observed, ToolCatalogManifest):
        raise ToolCatalogError("catalog.manifest_invalid")
    expected_by_source = {entry.source_key: entry for entry in expected.entries}
    observed_by_source = {entry.source_key: entry for entry in observed.entries}
    missing = tuple(sorted(set(expected_by_source) - set(observed_by_source)))
    extra = tuple(sorted(set(observed_by_source) - set(expected_by_source)))
    changed = tuple(sorted(
        source_key
        for source_key in set(expected_by_source) & set(observed_by_source)
        if expected_by_source[source_key] != observed_by_source[source_key]
    ))
    reasons: set[str] = set()
    if missing:
        reasons.add("catalog.missing")
    if extra:
        reasons.add("catalog.extra")
    if changed:
        reasons.add("catalog.changed")
    if expected.issues:
        reasons.add("catalog.expected_issues")
    if observed.issues:
        reasons.add("catalog.observed_issues")
    if expected.digest != observed.digest and not reasons:
        reasons.add("catalog.digest_mismatch")
    return ToolCatalogParityReport(
        expected_digest=expected.digest,
        observed_digest=observed.digest,
        exact=not reasons,
        missing_source_keys=missing,
        extra_source_keys=extra,
        changed_source_keys=changed,
        reason_codes=tuple(sorted(reasons)),
    )


def assess_tool_activation(
    manifest: ToolCatalogManifest,
    parity: ToolCatalogParityReport,
    *,
    required_tool_refs: tuple[str, ...],
    policy_ready: bool,
    owner_approved: bool,
    tools_flag_enabled: bool,
    rollback_ready: bool,
) -> ToolActivationReadiness:
    if not isinstance(manifest, ToolCatalogManifest):
        raise ToolCatalogError("catalog.manifest_invalid")
    if not isinstance(parity, ToolCatalogParityReport):
        raise ToolCatalogError("catalog.parity_invalid")
    reasons: set[str] = set()
    if not parity.exact:
        reasons.add("catalog.parity_failed")
    if parity.observed_digest != manifest.digest:
        reasons.add("catalog.manifest_mismatch")
    if manifest.issues:
        reasons.add("catalog.adapter_issues")
    if not required_tool_refs:
        reasons.add("catalog.required_tools_empty")
    by_ref = {entry.tool_ref: entry for entry in manifest.entries}
    for tool_ref in sorted(set(required_tool_refs)):
        entry = by_ref.get(tool_ref)
        if entry is None:
            reasons.add("catalog.tool_missing")
        elif entry.availability_status is not ToolAvailabilityStatus.AVAILABLE:
            reasons.add("catalog.tool_unavailable")
    if policy_ready is not True:
        reasons.add("policy.not_ready")
    if owner_approved is not True:
        reasons.add("owner.approval_required")
    if tools_flag_enabled is not True:
        reasons.add("runtime.v2_tools.disabled")
    if rollback_ready is not True:
        reasons.add("rollback.not_ready")
    return ToolActivationReadiness(
        manifest_digest=manifest.digest,
        ready=not reasons,
        reason_codes=tuple(sorted(reasons)),
    )

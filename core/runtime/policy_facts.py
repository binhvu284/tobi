"""Dormant metadata-only facts for central policy compatibility."""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import replace
from typing import Any

from core import vault
from core.runtime.contracts import (
    ApprovalMode,
    CredentialRequirement,
    CredentialStatus,
    LegacyPolicyFacts,
    PolicyInput,
    RuntimeToolSpec,
)


StatusReader = Callable[[Any], Mapping[str, Any]]
MetadataReader = Callable[..., list[dict[str, Any]]]


class VaultCredentialReadinessAdapter:
    """Resolve credential possession without retrieving or testing a secret."""

    def __init__(
        self,
        *,
        status_reader: StatusReader | None = None,
        metadata_reader: MetadataReader | None = None,
    ) -> None:
        self._status_reader = status_reader or vault.status
        self._metadata_reader = metadata_reader or vault.list_secrets

    def resolve(
        self,
        conn: Any,
        *,
        tool: RuntimeToolSpec,
        requirement: CredentialRequirement | None,
    ) -> CredentialStatus:
        if not isinstance(tool, RuntimeToolSpec):
            raise ValueError("tool must be a RuntimeToolSpec")
        if not tool.credential_purpose:
            return CredentialStatus.NOT_REQUIRED
        if requirement is None or not isinstance(requirement, CredentialRequirement):
            return CredentialStatus.PURPOSE_MISMATCH
        if requirement.purpose != tool.credential_purpose:
            return CredentialStatus.PURPOSE_MISMATCH

        try:
            state = self._status_reader(conn)
        except Exception:
            return CredentialStatus.UNKNOWN
        if not isinstance(state, Mapping):
            return CredentialStatus.UNKNOWN
        if state.get("crypto_available") is False:
            return CredentialStatus.UNAVAILABLE
        if state.get("crypto_available") is not True:
            return CredentialStatus.UNKNOWN
        if state.get("setup") is False:
            return CredentialStatus.MISSING
        if state.get("setup") is not True:
            return CredentialStatus.UNKNOWN

        profile = state.get("active_profile")
        if not isinstance(profile, str) or not profile.strip():
            return CredentialStatus.UNKNOWN
        try:
            metadata = self._metadata_reader(conn, profile=profile)
        except Exception:
            return CredentialStatus.UNKNOWN
        if not isinstance(metadata, list):
            return CredentialStatus.UNKNOWN

        match = next(
            (
                item
                for item in metadata
                if isinstance(item, Mapping)
                and item.get("name") == requirement.secret_name
            ),
            None,
        )
        if match is None:
            return CredentialStatus.MISSING
        if (
            requirement.integration_id is not None
            and match.get("integration_id") != requirement.integration_id
        ):
            return CredentialStatus.PURPOSE_MISMATCH
        if state.get("unlocked") is False:
            return CredentialStatus.LOCKED
        if state.get("unlocked") is not True:
            return CredentialStatus.UNKNOWN
        return CredentialStatus.AVAILABLE


def resolve_chat_review_mode(review_mode: str | None) -> LegacyPolicyFacts:
    normalized = review_mode.strip().lower() if isinstance(review_mode, str) else ""
    approval_mode = {
        "session": ApprovalMode.SESSION,
        "always": ApprovalMode.ALWAYS,
    }.get(normalized, ApprovalMode.ASK)
    return LegacyPolicyFacts(
        source="chat_review",
        source_mode=approval_mode.value,
        approval_mode=approval_mode,
        execution_allowed=True,
    )


def resolve_terminal_mode(effective_mode: str | None) -> LegacyPolicyFacts:
    normalized = effective_mode.strip().lower() if isinstance(effective_mode, str) else ""
    approval_mode = {
        "ask": ApprovalMode.ASK,
        "accept": ApprovalMode.SESSION,
        "auto": ApprovalMode.ALWAYS,
    }.get(normalized)
    if approval_mode is not None:
        return LegacyPolicyFacts(
            source="terminal",
            source_mode=normalized,
            approval_mode=approval_mode,
            execution_allowed=True,
        )

    source_mode = "plan" if normalized == "plan" else "unknown"
    return LegacyPolicyFacts(
        source="terminal",
        source_mode=source_mode,
        approval_mode=ApprovalMode.ASK,
        execution_allowed=False,
        denial_reason=f"compatibility.terminal.{source_mode}",
    )


def apply_legacy_policy_facts(
    policy_input: PolicyInput,
    facts: LegacyPolicyFacts,
) -> PolicyInput:
    if not isinstance(policy_input, PolicyInput):
        raise ValueError("policy_input must be a PolicyInput")
    if not isinstance(facts, LegacyPolicyFacts):
        raise ValueError("facts must be LegacyPolicyFacts")

    denials = list(policy_input.compatibility_denials)
    if not facts.execution_allowed and facts.denial_reason is not None:
        denials.append(facts.denial_reason)
    return replace(
        policy_input,
        approval_mode=facts.approval_mode,
        compatibility_denials=tuple(dict.fromkeys(denials)),
    )

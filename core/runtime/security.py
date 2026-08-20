"""Deterministic failure-injection evidence for Runtime V2 security gates."""
from __future__ import annotations

from dataclasses import dataclass

from core.runtime.contracts import (
    EvalCase,
    EvalFinding,
    EvalRun,
    EvalStatus,
    FindingSeverity,
)
from core.runtime.evals import EvalRepository


@dataclass(frozen=True)
class ThreatCase:
    threat_id: str
    category: str
    asset: str
    entry_point: str
    trust_boundary: str
    failure: str
    control_owner: str
    test_ref: str
    severity: FindingSeverity

    def __post_init__(self) -> None:
        for name in (
            "threat_id", "category", "asset", "entry_point", "trust_boundary",
            "failure", "control_owner", "test_ref",
        ):
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                raise ValueError(f"{name} must be non-empty")
        if not isinstance(self.severity, FindingSeverity):
            raise ValueError("severity must be FindingSeverity")


@dataclass(frozen=True)
class SecurityProbe:
    threat_id: str
    blocked: bool
    sanitized: bool
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.threat_id, str) or not self.threat_id.strip():
            raise ValueError("threat_id must be non-empty")
        if not isinstance(self.blocked, bool) or not isinstance(self.sanitized, bool):
            raise ValueError("blocked and sanitized must be bools")
        if not isinstance(self.evidence_refs, tuple) or any(
            not isinstance(ref, str) or not ref.strip() for ref in self.evidence_refs
        ):
            raise ValueError("evidence_refs must contain non-empty references")


@dataclass(frozen=True)
class SecurityGateResult:
    allowed: bool
    passed: tuple[str, ...]
    blockers: tuple[str, ...]
    evidence_refs: tuple[str, ...]


def threat_model() -> tuple[ThreatCase, ...]:
    """Version-one threat matrix; values are references, never attack payloads."""
    rows = (
        (
            "t12.prompt-injection", "prompt_injection", "owner intent and safety rules",
            "Brain or retrieved content", "untrusted content to Runtime context",
            "content gains route, tool, or instruction authority",
            "core.runtime.owner_intelligence", "test:test_mc_runtime_security:prompt_injection",
            FindingSeverity.HIGH,
        ),
        (
            "t12.secret-leakage", "secret_leakage", "credentials and private values",
            "event and trace payloads", "Runtime input to durable SQLite history",
            "a secret marker reaches persisted JSON",
            "core.runtime.event_store", "test:test_mc_runtime_security:secret_leakage",
            FindingSeverity.CRITICAL,
        ),
        (
            "t12.authority-overreach", "authority_overreach", "tool permissions",
            "policy facts", "caller claims to central policy decision",
            "untrusted authority permits a tool",
            "core.runtime.policy", "test:test_mc_runtime_security:authority_overreach",
            FindingSeverity.CRITICAL,
        ),
        (
            "t12.budget-exhaustion", "budget_exhaustion", "bounded local resources",
            "owner and plan limits", "requested budget to loop controller",
            "a higher override wins or exhausted work continues",
            "core.runtime.budget", "test:test_mc_runtime_security:budget_exhaustion",
            FindingSeverity.HIGH,
        ),
        (
            "t12.network-ssrf", "network_ssrf", "local network and metadata services",
            "tool-driven URL", "untrusted URL to outbound request",
            "private, local, metadata, or non-http destination is reachable",
            "core.net_guard", "test:test_mc_runtime_security:network_ssrf",
            FindingSeverity.CRITICAL,
        ),
        (
            "t12.path-traversal", "path_traversal", "repository and host filesystem",
            "coding file path", "worker path to coding policy",
            "a resolved path escapes the approved repository",
            "core.coding_policy", "test:test_mc_runtime_security:path_traversal",
            FindingSeverity.CRITICAL,
        ),
        (
            "t12.supply-chain", "supply_chain", "canonical tool contracts",
            "tool schema metadata", "remote metadata to canonical registry",
            "a remote schema reference enters the trusted catalog",
            "core.runtime.tool_registry", "test:test_mc_runtime_security:supply_chain",
            FindingSeverity.HIGH,
        ),
        (
            "t12.recovery", "recovery", "fail-closed run state",
            "boundary error or missing security proof", "failed control to activation gate",
            "missing or failed evidence still permits release or autonomy",
            "core.runtime.security", "test:test_mc_runtime_security:recovery",
            FindingSeverity.CRITICAL,
        ),
    )
    return tuple(ThreatCase(*row) for row in rows)


def evaluate_security_probes(probes: tuple[SecurityProbe, ...]) -> SecurityGateResult:
    expected = {case.threat_id: case for case in threat_model()}
    seen: dict[str, SecurityProbe] = {}
    blockers: list[str] = []
    evidence: set[str] = set()
    for probe in probes:
        if not isinstance(probe, SecurityProbe):
            raise ValueError("probes must contain SecurityProbe values")
        if probe.threat_id not in expected:
            blockers.append(f"unknown:{probe.threat_id}")
            continue
        if probe.threat_id in seen:
            blockers.append(f"duplicate:{probe.threat_id}")
            continue
        seen[probe.threat_id] = probe
        evidence.update(probe.evidence_refs)
        if not probe.evidence_refs:
            blockers.append(f"missing-evidence:{probe.threat_id}")
        if not probe.blocked:
            blockers.append(f"control-failed:{probe.threat_id}")
        if not probe.sanitized:
            blockers.append(f"unsanitized:{probe.threat_id}")
    for threat_id in sorted(set(expected) - set(seen)):
        blockers.append(f"missing:{threat_id}")
    passed = tuple(sorted(
        threat_id for threat_id, probe in seen.items()
        if probe.blocked and probe.sanitized and probe.evidence_refs
    ))
    return SecurityGateResult(
        allowed=not blockers,
        passed=passed,
        blockers=tuple(sorted(blockers)),
        evidence_refs=tuple(sorted(evidence)),
    )


def record_security_evaluation(
    repository: EvalRepository,
    *,
    eval_run_id: str,
    probes: tuple[SecurityProbe, ...],
    trace_id: str,
) -> dict[str, str | None]:
    """Project a security gate into T11 so unsafe outcomes block activation."""
    gate = evaluate_security_probes(probes)
    case = EvalCase(
        eval_case_id="tobival.runtime-security",
        version="1",
        category="security",
        objective="Verify every Runtime V2 security boundary fails closed",
        input_fixture={"threat_model_ref": "t12:threat-model:1"},
        expected_behavior="All required synthetic probes are blocked and sanitized",
        required_evidence=tuple(case.test_ref for case in threat_model()),
        scorer="all_security_controls",
        threshold=1.0,
        release_gate=True,
        autonomy_gate=True,
    )
    repository.save_case(case)
    score = len(gate.passed) / len(threat_model())
    status = EvalStatus.PASSED if gate.allowed else EvalStatus.FAILED
    repository.record_run(EvalRun(
        eval_run_id=eval_run_id,
        eval_case_id=case.eval_case_id,
        eval_case_version=case.version,
        status=status,
        threshold=case.threshold,
        score=score,
        trace_id=trace_id,
        artifact_refs=gate.evidence_refs,
        started_at="security-gate:started",
        completed_at="security-gate:completed",
    ))
    finding_id: str | None = None
    if not gate.allowed:
        finding_id = f"{eval_run_id}:security-blocked"
        repository.record_finding(EvalFinding(
            finding_id=finding_id,
            eval_run_id=eval_run_id,
            category="security",
            severity=FindingSeverity.HIGH,
            summary="One or more required Runtime security controls did not produce safe evidence.",
            remediation_owner="mission-control",
            status="open",
            evidence_refs=gate.evidence_refs,
        ))
    return {
        "eval_run_id": eval_run_id,
        "status": status.value,
        "finding_id": finding_id,
    }

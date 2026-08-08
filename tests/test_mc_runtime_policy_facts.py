"""Acceptance checks for #21 T05 Run 3 dormant policy fact resolution."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import vault  # noqa: E402
from core.runtime.contracts import (  # noqa: E402
    ApprovalMode,
    CredentialRequirement,
    CredentialStatus,
    PolicyEffect,
    PolicyInput,
    RiskLevel,
    RuntimeToolSpec,
    SideEffectClass,
    Surface,
)
from core.runtime.policy import POLICY_ID, POLICY_VERSION, PolicyEngine  # noqa: E402
from core.runtime.policy_facts import (  # noqa: E402
    VaultCredentialReadinessAdapter,
    apply_legacy_policy_facts,
    resolve_chat_review_mode,
    resolve_terminal_mode,
)


PASS = 0


def ok(name: str, condition: bool, detail: object = "") -> None:
    global PASS
    if not condition:
        print(f"FAIL {name}: {detail}")
        raise SystemExit(1)
    PASS += 1
    print(f"PASS {name}")


def raises(error_type: type[Exception], callback) -> bool:
    try:
        callback()
    except error_type:
        return True
    return False


def tool(
    *,
    purpose: str | None = None,
    risk: RiskLevel = RiskLevel.NONE,
    side_effect: SideEffectClass = SideEffectClass.NONE,
) -> RuntimeToolSpec:
    return RuntimeToolSpec(
        name="policy_fact_probe",
        namespace="tests",
        version="1",
        description="T05 Run 3 policy fact fixture",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        side_effect_class=side_effect,
        risk=risk,
        allowed_modes=("agent",),
        allowed_surfaces=(Surface.AGENT,),
        credential_purpose=purpose,
    )


def policy_input(spec: RuntimeToolSpec) -> PolicyInput:
    return PolicyInput(
        decision_id="policy-fact-decision",
        run_id="policy-fact-run",
        step_id="policy-fact-step",
        owner_id="owner",
        session_id="session",
        surface=Surface.AGENT,
        mode="agent",
        tool=spec,
        target="system:policy-fact-probe",
        credential_status=(
            CredentialStatus.AVAILABLE
            if spec.credential_purpose
            else CredentialStatus.NOT_REQUIRED
        ),
    )


def adapter(status_payload: dict, metadata: list[dict] | Exception):
    def read_metadata(_conn, profile=None):
        if isinstance(metadata, Exception):
            raise metadata
        return metadata

    return VaultCredentialReadinessAdapter(
        status_reader=lambda _conn: status_payload,
        metadata_reader=read_metadata,
    )


required_tool = tool(purpose="github.read")
requirement = CredentialRequirement(
    purpose="github.read",
    secret_name="GITHUB_TOKEN",
    integration_id="github",
)
ready_status = {
    "crypto_available": True,
    "setup": True,
    "unlocked": True,
    "active_profile": "local",
}
matching_metadata = [{
    "name": "GITHUB_TOKEN",
    "integration_id": "github",
    "test_status": "failed",
    "last4": "1234",
}]

ok(
    "credential requirement contract rejects blank bindings",
    raises(
        ValueError,
        lambda: CredentialRequirement(purpose="github.read", secret_name=""),
    ),
)

ok(
    "tools without a credential purpose need no credential",
    adapter(ready_status, matching_metadata).resolve(
        object(), tool=tool(), requirement=None
    ) is CredentialStatus.NOT_REQUIRED,
)

binding_states = {
    "missing_binding": adapter(ready_status, matching_metadata).resolve(
        object(), tool=required_tool, requirement=None
    ),
    "wrong_purpose": adapter(ready_status, matching_metadata).resolve(
        object(),
        tool=required_tool,
        requirement=CredentialRequirement(
            purpose="github.write", secret_name="GITHUB_TOKEN", integration_id="github"
        ),
    ),
    "wrong_integration": adapter(
        ready_status,
        [{"name": "GITHUB_TOKEN", "integration_id": "notion"}],
    ).resolve(object(), tool=required_tool, requirement=requirement),
}
ok(
    "missing or mismatched credential bindings fail closed",
    all(value is CredentialStatus.PURPOSE_MISMATCH for value in binding_states.values()),
    binding_states,
)

readiness_states = {
    "unavailable": adapter(
        {**ready_status, "crypto_available": False}, matching_metadata
    ).resolve(object(), tool=required_tool, requirement=requirement),
    "missing": adapter(
        {**ready_status, "setup": False}, []
    ).resolve(object(), tool=required_tool, requirement=requirement),
    "unknown": adapter(
        ready_status, RuntimeError("metadata unavailable")
    ).resolve(object(), tool=required_tool, requirement=requirement),
    "locked": adapter(
        {**ready_status, "unlocked": False}, matching_metadata
    ).resolve(object(), tool=required_tool, requirement=requirement),
    "available": adapter(ready_status, matching_metadata).resolve(
        object(), tool=required_tool, requirement=requirement
    ),
}
ok(
    "credential readiness reports truthful metadata-only states",
    readiness_states == {
        "unavailable": CredentialStatus.UNAVAILABLE,
        "missing": CredentialStatus.MISSING,
        "unknown": CredentialStatus.UNKNOWN,
        "locked": CredentialStatus.LOCKED,
        "available": CredentialStatus.AVAILABLE,
    },
    readiness_states,
)

original_get_secret = vault.get_secret
vault.get_secret = lambda *_args, **_kwargs: (_ for _ in ()).throw(
    AssertionError("raw credential access is forbidden")
)
try:
    metadata_only = adapter(ready_status, matching_metadata).resolve(
        object(), tool=required_tool, requirement=requirement
    )
finally:
    vault.get_secret = original_get_secret
ok(
    "credential readiness never reads a raw secret or treats test health as possession",
    metadata_only is CredentialStatus.AVAILABLE,
)

chat_modes = {
    raw: resolve_chat_review_mode(raw).approval_mode
    for raw in ("ask", "session", "always", "unexpected", None)
}
ok(
    "chat review modes preserve compatibility and unknown defaults to ask",
    chat_modes == {
        "ask": ApprovalMode.ASK,
        "session": ApprovalMode.SESSION,
        "always": ApprovalMode.ALWAYS,
        "unexpected": ApprovalMode.ASK,
        None: ApprovalMode.ASK,
    },
    chat_modes,
)

terminal_facts = {
    raw: resolve_terminal_mode(raw)
    for raw in ("ask", "accept", "auto", "plan", "unexpected", None)
}
ok(
    "terminal effective modes map conservatively and non-execution modes deny",
    terminal_facts["ask"].approval_mode is ApprovalMode.ASK
    and terminal_facts["accept"].approval_mode is ApprovalMode.SESSION
    and terminal_facts["auto"].approval_mode is ApprovalMode.ALWAYS
    and terminal_facts["plan"].execution_allowed is False
    and terminal_facts["unexpected"].execution_allowed is False
    and terminal_facts[None].execution_allowed is False,
    terminal_facts,
)

engine = PolicyEngine(policy_id=POLICY_ID, version=POLICY_VERSION)
plan_input = apply_legacy_policy_facts(
    policy_input(tool()), terminal_facts["plan"]
)
plan_decision = engine.evaluate(plan_input)
material_input = apply_legacy_policy_facts(
    policy_input(tool(risk=RiskLevel.HIGH, side_effect=SideEffectClass.EXTERNAL)),
    terminal_facts["auto"],
)
material_decision = engine.evaluate(material_input)
ok(
    "legacy compatibility cannot weaken central policy",
    plan_decision.effect is PolicyEffect.DENY
    and "compatibility.terminal.plan" in plan_decision.reason_codes
    and material_decision.effect is PolicyEffect.REQUIRE_APPROVAL,
    {"plan": plan_decision, "material": material_decision},
)

print(f"\n{PASS}/{PASS} T05 RUN 3 POLICY FACT CHECKS PASS")

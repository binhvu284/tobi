"""Acceptance checks for #21 T05 Run 1 dormant central policy decisions."""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TMP = tempfile.mkdtemp(prefix="tobi_t05_run1_")
os.environ["DB_PATH"] = os.path.join(TMP, "agent.db")

from core import owner_flags  # noqa: E402
from core.database import get_connection, init_database  # noqa: E402
from core.runtime.contracts import (  # noqa: E402
    ApprovalMode,
    ApprovalStatus,
    BudgetStatus,
    Certainty,
    CredentialStatus,
    IsolationLevel,
    LoopPolicy,
    LoopRecipe,
    LoopType,
    PolicyEffect,
    PolicyInput,
    RiskLevel,
    RunRequest,
    RuntimeToolSpec,
    SideEffectClass,
    Surface,
    TrustClass,
)
from core.runtime.event_store import EventConflictError, append_run_event, list_run_events  # noqa: E402
from core.runtime.policy import PolicyConflictError, PolicyEngine, PolicyLedger  # noqa: E402
from core.runtime.repository import RuntimeRepository  # noqa: E402
from core.schema.runtime import RUNTIME_SCHEMA_VERSIONS, _ensure_runtime_schema  # noqa: E402


PASS = 0
SECRET = "sk-t05-policy-do-not-store"


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


def query_one(sql: str, parameters: tuple = ()) -> sqlite3.Row | None:
    conn = get_connection()
    try:
        return conn.execute(sql, parameters).fetchone()
    finally:
        conn.close()


def tool(
    *,
    name: str = "read_status",
    risk: RiskLevel = RiskLevel.NONE,
    side_effect: SideEffectClass = SideEffectClass.NONE,
    modes: tuple[str, ...] = ("chat", "agent"),
    surfaces: tuple[Surface, ...] = (Surface.CHAT, Surface.AGENT),
    permissions: tuple[str, ...] = (),
    integrations: tuple[str, ...] = (),
    credential_purpose: str | None = None,
    isolation: str = "in_process",
) -> RuntimeToolSpec:
    return RuntimeToolSpec(
        name=name,
        namespace="tests",
        version="1",
        description=f"Policy fixture for {name}",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        side_effect_class=side_effect,
        risk=risk,
        allowed_modes=modes,
        allowed_surfaces=surfaces,
        required_permissions=permissions,
        required_integrations=integrations,
        credential_purpose=credential_purpose,
        isolation=isolation,
    )


def policy_input(
    decision_id: str,
    *,
    run_id: str = "policy-run",
    spec: RuntimeToolSpec | None = None,
    surface: Surface = Surface.CHAT,
    mode: str = "chat",
    permissions: tuple[str, ...] = (),
    integrations: tuple[str, ...] = (),
    credential_status: CredentialStatus = CredentialStatus.NOT_REQUIRED,
    trust: TrustClass = TrustClass.OWNER_DIRECT,
    certainty: Certainty = Certainty.KNOWN,
    instruction_authority: bool = True,
    isolation: tuple[IsolationLevel, ...] = (IsolationLevel.IN_PROCESS,),
    budget: BudgetStatus = BudgetStatus.AVAILABLE,
    approval_mode: ApprovalMode = ApprovalMode.SESSION,
    approval_status: ApprovalStatus = ApprovalStatus.NONE,
    approval_id: str | None = None,
    switches: tuple[str, ...] = (),
    target: str = "system:status",
) -> PolicyInput:
    return PolicyInput(
        decision_id=decision_id,
        run_id=run_id,
        step_id="step-1",
        owner_id="owner",
        session_id="session-policy",
        surface=surface,
        mode=mode,
        tool=spec or tool(),
        target=target,
        granted_permissions=permissions,
        available_integrations=integrations,
        credential_status=credential_status,
        trust_class=trust,
        certainty=certainty,
        instruction_authority=instruction_authority,
        available_isolations=isolation,
        budget_status=budget,
        approval_mode=approval_mode,
        approval_status=approval_status,
        approval_id=approval_id,
        active_kill_switches=switches,
    )


def prepare_run(repository: RuntimeRepository, run_id: str) -> None:
    recipe = LoopRecipe(
        recipe_id=f"recipe-{run_id}",
        version="1",
        name="Policy fixture",
        loop_type=LoopType.TURN,
        trigger="owner request",
        objective="Evaluate one policy decision",
        stop_condition="policy decision recorded",
        max_attempts=2,
        max_runtime_s=300,
        max_cost_usd=1.0,
    )
    repository.save_loop_recipe(recipe)
    repository.create_run(
        RunRequest(
            request_id=f"request-{run_id}",
            surface=Surface.CHAT,
            owner_id="owner",
            session_id="session-policy",
            mode="chat",
            message="Evaluate policy",
        ),
        loop_policy=LoopPolicy.from_recipe(
            policy_id=f"loop-policy-{run_id}",
            version="1",
            recipe=recipe,
            policy_decision_id=f"bootstrap-{run_id}",
            enabled=False,
        ),
        run_id=run_id,
    )


init_database()
conn = get_connection()
conn.execute("CREATE TABLE legacy_policy_probe (value TEXT)")
conn.execute("INSERT INTO legacy_policy_probe(value) VALUES ('preserved')")
conn.commit()
_ensure_runtime_schema(conn)
_ensure_runtime_schema(conn)
versions = [row[0] for row in conn.execute(
    "SELECT version FROM schema_migrations WHERE version LIKE 'mc-runtime-v2-%'"
)]
tables = {row[0] for row in conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table'"
)}
conn.close()
ok(
    "migration 007 remains additive and idempotent",
    "mc-runtime-v2-007" in RUNTIME_SCHEMA_VERSIONS
    and versions.count("mc-runtime-v2-007") == 1
    and "mc_policy_decisions" in tables
    and query_one("SELECT value FROM legacy_policy_probe")["value"] == "preserved",
)

ok(
    "policy contracts reject malformed authority inputs",
    raises(
        ValueError,
        lambda: PolicyInput(
            decision_id="bad",
            run_id="run",
            owner_id="owner",
            session_id="session",
            surface=Surface.CHAT,
            mode="chat",
            tool=tool(),
            target="target",
            credential_status=CredentialStatus.NOT_REQUIRED,
            trust_class=TrustClass.UNTRUSTED_CONTENT,
            certainty=Certainty.KNOWN,
            instruction_authority="yes",  # type: ignore[arg-type]
            available_isolations=(IsolationLevel.IN_PROCESS,),
            budget_status=BudgetStatus.AVAILABLE,
            approval_mode=ApprovalMode.SESSION,
            approval_status=ApprovalStatus.NONE,
        ),
    ),
)

engine = PolicyEngine(policy_id="mc.central", version="1")
safe_input = policy_input("allow-safe")
safe_decision = engine.evaluate(safe_input)
ok(
    "safe owner-directed read is allowed deterministically",
    safe_decision.effect is PolicyEffect.ALLOW
    and safe_decision == engine.evaluate(safe_input)
    and safe_decision.reason_codes == ("policy.allowed",),
    safe_decision,
)

mode_surface = engine.evaluate(policy_input(
    "deny-mode-surface",
    spec=tool(modes=("agent",), surfaces=(Surface.AGENT,)),
))
ok(
    "mode and surface capability failures deny",
    mode_surface.effect is PolicyEffect.DENY
    and "surface.denied" in mode_surface.reason_codes
    and "mode.denied" in mode_surface.reason_codes,
    mode_surface,
)

requirements = tool(
    name="publish_report",
    risk=RiskLevel.MEDIUM,
    side_effect=SideEffectClass.EXTERNAL,
    permissions=("reports.publish",),
    integrations=("notion",),
    credential_purpose="notion.publish",
    isolation="container",
)
missing = engine.evaluate(policy_input("deny-missing", spec=requirements))
ok(
    "missing permission integration credential and isolation deny together",
    missing.effect is PolicyEffect.DENY
    and {
        "permission.missing",
        "integration.missing",
        "credential.missing",
        "isolation.unavailable",
    }.issubset(missing.reason_codes),
    missing,
)

stopped = engine.evaluate(policy_input(
    "deny-system-state",
    budget=BudgetStatus.EXHAUSTED,
    switches=("runtime.global",),
))
ok(
    "kill switches and exhausted budgets deny",
    stopped.effect is PolicyEffect.DENY
    and "kill_switch.active" in stopped.reason_codes
    and "budget.exhausted" in stopped.reason_codes,
    stopped,
)

untrusted = engine.evaluate(policy_input(
    "deny-untrusted-authority",
    trust=TrustClass.UNTRUSTED_CONTENT,
    instruction_authority=True,
))
contradicted = engine.evaluate(policy_input(
    "deny-contradicted",
    certainty=Certainty.CONTRADICTED,
))
ok(
    "untrusted instructions and contradicted facts deny",
    untrusted.effect is PolicyEffect.DENY
    and "trust.instruction_authority" in untrusted.reason_codes
    and contradicted.effect is PolicyEffect.DENY
    and "certainty.contradicted" in contradicted.reason_codes,
)

mutation = tool(
    name="update_task",
    risk=RiskLevel.LOW,
    side_effect=SideEffectClass.REVERSIBLE,
)
ask = engine.evaluate(policy_input(
    "approval-ask", spec=mutation, approval_mode=ApprovalMode.ASK
))
session = engine.evaluate(policy_input(
    "allow-session", spec=mutation, approval_mode=ApprovalMode.SESSION
))
inferred = engine.evaluate(policy_input(
    "approval-inferred", spec=mutation, certainty=Certainty.INFERRED
))
ok(
    "review mode and inferred mutation produce deterministic approval boundaries",
    ask.effect is PolicyEffect.REQUIRE_APPROVAL
    and session.effect is PolicyEffect.ALLOW
    and inferred.effect is PolicyEffect.REQUIRE_APPROVAL,
    {"ask": ask, "session": session, "inferred": inferred},
)

material = tool(
    name="send_message",
    risk=RiskLevel.HIGH,
    side_effect=SideEffectClass.EXTERNAL,
)
always_material = engine.evaluate(policy_input(
    "approval-material", spec=material, approval_mode=ApprovalMode.ALWAYS
))
approved_material = engine.evaluate(policy_input(
    "allow-approved",
    spec=material,
    approval_mode=ApprovalMode.ALWAYS,
    approval_status=ApprovalStatus.APPROVED,
    approval_id="approval-1",
))
rejected_material = engine.evaluate(policy_input(
    "deny-rejected",
    spec=material,
    approval_status=ApprovalStatus.REJECTED,
    approval_id="approval-2",
))
ok(
    "material effects require approval even in always mode",
    always_material.effect is PolicyEffect.REQUIRE_APPROVAL
    and approved_material.effect is PolicyEffect.ALLOW
    and approved_material.approval_id == "approval-1"
    and rejected_material.effect is PolicyEffect.DENY
    and "approval.rejected" in rejected_material.reason_codes,
)

stale_mutation = engine.evaluate(policy_input(
    "approval-stale", spec=mutation, certainty=Certainty.STALE
))
ok(
    "stale mutation cannot run without owner approval",
    stale_mutation.effect is PolicyEffect.REQUIRE_APPROVAL
    and "certainty.stale" in stale_mutation.reason_codes,
    stale_mutation,
)

repository = RuntimeRepository()
prepare_run(repository, "policy-run")
ledger = PolicyLedger()
secret_input = policy_input(
    "persist-policy",
    target=f"service api_key={SECRET}",
)
secret_decision = engine.evaluate(secret_input)
stored = ledger.record(secret_input, secret_decision, actor="policy-test")
events = list_run_events("policy-run")
durable = query_one(
    "SELECT input_json,decision_json FROM mc_policy_decisions WHERE decision_id=?",
    ("persist-policy",),
)
ok(
    "decision persistence is redacted and joins ordered run history",
    stored["effect"] == "allow"
    and durable is not None
    and SECRET not in durable["input_json"]
    and "[REDACTED]" in durable["input_json"]
    and events[-1].event_type == "policy.decided"
    and SECRET not in str(events[-1].redacted_payload),
    {"stored": stored, "events": [event.event_type for event in events]},
)

fabricated = replace(
    always_material,
    effect=PolicyEffect.ALLOW,
    reason_codes=("policy.allowed",),
    required_approval=False,
)
ok(
    "ledger rejects a fabricated allow decision",
    raises(
        PolicyConflictError,
        lambda: ledger.record(
            policy_input("fabricated-policy", run_id="policy-run", spec=material),
            replace(fabricated, decision_id="fabricated-policy", run_id="policy-run"),
            actor="policy-test",
        ),
    )
    and query_one(
        "SELECT decision_id FROM mc_policy_decisions WHERE decision_id='fabricated-policy'"
    ) is None,
)

replayed = ledger.record(secret_input, secret_decision, actor="policy-test")
ok(
    "same decision identity replays without duplicate row or event",
    replayed == stored
    and query_one("SELECT COUNT(*) AS count FROM mc_policy_decisions")["count"] == 1
    and len(list_run_events("policy-run")) == len(events),
)

changed_input = policy_input("persist-policy", target="service:changed")
ok(
    "changed content cannot reuse a decision identity",
    raises(
        PolicyConflictError,
        lambda: ledger.record(
            changed_input, engine.evaluate(changed_input), actor="policy-test"
        ),
    ),
)

conn = get_connection()
update_guard = raises(
    sqlite3.IntegrityError,
    lambda: conn.execute(
        "UPDATE mc_policy_decisions SET effect='deny' WHERE decision_id='persist-policy'"
    ),
)
conn.rollback()
delete_guard = raises(
    sqlite3.IntegrityError,
    lambda: conn.execute(
        "DELETE FROM mc_policy_decisions WHERE decision_id='persist-policy'"
    ),
)
conn.rollback()
conn.close()
ok("policy decision history rejects update and delete", update_guard and delete_guard)

prepare_run(repository, "atomic-policy-run")
atomic_input = policy_input("atomic-policy", run_id="atomic-policy-run")
atomic_decision = engine.evaluate(atomic_input)
append_run_event(
    run_id="atomic-policy-run",
    event_type="test.conflict",
    stage="policy",
    actor="test",
    event_id="atomic-event",
)
ok(
    "event conflict rolls back decision insertion",
    raises(
        EventConflictError,
        lambda: ledger.record(
            atomic_input,
            atomic_decision,
            actor="policy-test",
            event_id="atomic-event",
        ),
    )
    and query_one(
        "SELECT decision_id FROM mc_policy_decisions WHERE decision_id='atomic-policy'"
    ) is None,
)

ok(
    "central policy rollout remains off and has no live caller",
    owner_flags.get_bool(owner_flags.RUNTIME_V2_POLICY, False) is False,
)

print(f"\n{PASS}/{PASS} T05 RUN 1 POLICY CHECKS PASS")

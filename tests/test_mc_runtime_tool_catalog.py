"""Acceptance checks for #21 T06 Run 3 dormant catalog activation boundary."""
from __future__ import annotations

import asyncio
import copy
import json
import os
import sys
import tempfile
from dataclasses import replace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_TEMP = tempfile.TemporaryDirectory(prefix="tobi_t06_run3_")
os.environ["DB_PATH"] = str(Path(_TEMP.name) / "agent.db")

from core import database, owner_flags  # noqa: E402
from core.runtime.contracts import (  # noqa: E402
    RiskLevel,
    RuntimeToolSpec,
    SideEffectClass,
    Surface,
    ToolAvailability,
    ToolAvailabilityStatus,
    ToolCatalogEntry,
    contract_to_dict,
)
from core.runtime.tool_adapters import (  # noqa: E402
    ToolAdapterIssue,
    ToolAdapterResult,
    adapt_inbound_mcp_catalog,
    adapt_legacy_catalog,
)
from core.runtime.tool_catalog import (  # noqa: E402
    CanonicalToolCatalog,
    ToolCallPreparationError,
    ToolCatalogError,
    assess_tool_activation,
    compare_tool_manifests,
)

database.DB_PATH = os.environ["DB_PATH"]
database.init_database()

from core import conductor_registry, mcp_server  # noqa: E402


PASS = 0


def ok(name: str, condition: bool, detail: object = "") -> None:
    global PASS
    if not condition:
        print(f"FAIL {name}: {detail}")
        raise SystemExit(1)
    PASS += 1
    print(f"PASS {name}")


def raises(error_type: type[Exception], callback) -> Exception | None:
    try:
        callback()
    except error_type as exc:
        return exc
    return None


def synthetic_entry(
    name: str = "search",
    *,
    status: ToolAvailabilityStatus = ToolAvailabilityStatus.AVAILABLE,
) -> ToolCatalogEntry:
    spec = RuntimeToolSpec(
        name=name,
        namespace="tests.catalog",
        version="1",
        description=f"Synthetic catalog fixture for {name}",
        input_schema={
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {
                "query": {"type": "string", "minLength": 1},
                "options": {
                    "type": "object",
                    "properties": {"limit": {"type": "integer", "minimum": 1}},
                    "required": ["limit"],
                    "additionalProperties": False,
                },
            },
            "required": ["query", "options"],
            "additionalProperties": False,
        },
        output_schema={},
        side_effect_class=SideEffectClass.NONE,
        risk=RiskLevel.NONE,
        allowed_modes=("chat", "agent"),
        allowed_surfaces=(Surface.CHAT, Surface.AGENT),
        adapter="tests.synthetic_catalog",
    )
    return ToolCatalogEntry(
        source_key=f"synthetic:{name}",
        spec=spec,
        availability=ToolAvailability(
            tool_ref=spec.ref,
            status=status,
            reason_codes=("tests.available",) if status is ToolAvailabilityStatus.AVAILABLE
            else ("tests.not_available",),
        ),
    )


legacy = adapt_legacy_catalog(conductor_registry.TOOL_SPECS)
inbound = adapt_inbound_mcp_catalog(
    asyncio.run(mcp_server.mcp.list_tools()),
    sensitive_names=mcp_server.SENSITIVE_TOOLS,
)
current = CanonicalToolCatalog.from_adapter_results((legacy, inbound))
reordered = CanonicalToolCatalog.from_adapter_results((
    ToolAdapterResult(entries=tuple(reversed(inbound.entries)), issues=inbound.issues),
    ToolAdapterResult(entries=tuple(reversed(legacy.entries)), issues=legacy.issues),
))
current_names = tuple(entry.tool_ref for entry in current.manifest.entries)
ok(
    "current Conductor and inbound MCP snapshots have deterministic exact parity",
    not legacy.issues
    and not inbound.issues
    and current.manifest.digest == reordered.manifest.digest
    and compare_tool_manifests(current.manifest, reordered.manifest).exact
    and len(current_names) == len(conductor_registry.TOOL_SPECS) + len(mcp_server.TOOL_NAMES)
    and tuple(sorted(entry.spec.name for entry in legacy.entries))
    == tuple(sorted(conductor_registry.TOOL_SPECS))
    and tuple(sorted(entry.spec.name for entry in inbound.entries))
    == tuple(sorted(mcp_server.TOOL_NAMES)),
    {"legacy": legacy.issues, "inbound": inbound.issues},
)

serialized = json.dumps(contract_to_dict(current.manifest), sort_keys=True)
ok(
    "manifest contains contracts and availability but no execution or secret material",
    all(marker not in serialized for marker in (
        "endpoint", "auth_ref", "validated_arguments", "typed_output", "callable", "SECRET_VALUE"
    )),
    serialized[:500],
)

alpha = synthetic_entry("alpha")
beta = synthetic_entry("beta")
duplicate_source = raises(
    ToolCatalogError,
    lambda: CanonicalToolCatalog((alpha, replace(beta, source_key=alpha.source_key))),
)
duplicate_ref = raises(
    ToolCatalogError,
    lambda: CanonicalToolCatalog((alpha, replace(alpha, source_key="synthetic:other"))),
)
ok(
    "duplicate source ownership and duplicate canonical references fail closed",
    getattr(duplicate_source, "code", None) == "catalog.duplicate_source"
    and getattr(duplicate_ref, "code", None) == "catalog.duplicate_tool_ref",
    {"source": duplicate_source, "ref": duplicate_ref},
)

expected = CanonicalToolCatalog((alpha, beta, synthetic_entry("gamma"))).manifest
changed_beta = replace(beta, spec=replace(beta.spec, description="Changed contract"))
observed = CanonicalToolCatalog((changed_beta, synthetic_entry("gamma"), synthetic_entry("delta"))).manifest
drift = compare_tool_manifests(expected, observed)
ok(
    "parity reports missing extra and changed sources deterministically",
    not drift.exact
    and drift.missing_source_keys == ("synthetic:alpha",)
    and drift.extra_source_keys == ("synthetic:delta",)
    and drift.changed_source_keys == ("synthetic:beta",)
    and drift.reason_codes == (
        "catalog.changed", "catalog.extra", "catalog.missing",
    ),
    drift,
)

issue_catalog = CanonicalToolCatalog.from_adapter_results((ToolAdapterResult(
    entries=(alpha,),
    issues=(ToolAdapterIssue("synthetic:rejected", "schema.invalid"),),
),))
issue_parity = compare_tool_manifests(CanonicalToolCatalog((alpha,)).manifest, issue_catalog.manifest)
ok(
    "adapter rejection is preserved as a stable parity failure without raw metadata",
    not issue_parity.exact
    and issue_catalog.manifest.issue_codes == ("schema.invalid",)
    and issue_parity.reason_codes == ("catalog.observed_issues",),
    issue_parity,
)

search = synthetic_entry()
call_catalog = CanonicalToolCatalog((search,))
raw_arguments = {"query": "runtime", "options": {"limit": 3}}
original_arguments = copy.deepcopy(raw_arguments)
prepared = call_catalog.prepare_call(
    call_id="call-1",
    run_id="run-1",
    step_id="step-1",
    tool_ref=search.spec.ref,
    arguments=raw_arguments,
    surface=Surface.CHAT,
    mode="chat",
    candidate_tool_refs=(search.spec.ref,),
)
raw_arguments["options"]["limit"] = 7
ok(
    "valid allowlisted arguments produce an isolated typed call and no executor",
    prepared.tool_ref == search.spec.ref
    and prepared.validated_arguments == original_arguments
    and not hasattr(call_catalog, "invoke")
    and not hasattr(prepared, "callable"),
    prepared,
)

empty_allowlist = raises(ToolCallPreparationError, lambda: call_catalog.prepare_call(
    call_id="call-empty", run_id="run-1", step_id="step-1", tool_ref=search.spec.ref,
    arguments=original_arguments, surface=Surface.CHAT, mode="chat", candidate_tool_refs=(),
))
mismatch_allowlist = raises(ToolCallPreparationError, lambda: call_catalog.prepare_call(
    call_id="call-mismatch", run_id="run-1", step_id="step-1", tool_ref=search.spec.ref,
    arguments=original_arguments, surface=Surface.CHAT, mode="chat",
    candidate_tool_refs=("tests.catalog.other@1",),
))
ok(
    "call preparation requires a nonempty exact-version candidate allowlist",
    getattr(empty_allowlist, "code", None) == "tool.allowlist_required"
    and getattr(mismatch_allowlist, "code", None) == "tool.not_allowlisted",
    {"empty": empty_allowlist, "mismatch": mismatch_allowlist},
)

unknown = raises(ToolCallPreparationError, lambda: call_catalog.prepare_call(
    call_id="call-unknown", run_id="run-1", step_id="step-1", tool_ref="tests.catalog.unknown@1",
    arguments=original_arguments, surface=Surface.CHAT, mode="chat",
    candidate_tool_refs=("tests.catalog.unknown@1",),
))
unavailable_entry = synthetic_entry(status=ToolAvailabilityStatus.UNKNOWN)
unavailable_catalog = CanonicalToolCatalog((unavailable_entry,))
unavailable = raises(ToolCallPreparationError, lambda: unavailable_catalog.prepare_call(
    call_id="call-off", run_id="run-1", step_id="step-1", tool_ref=unavailable_entry.spec.ref,
    arguments=original_arguments, surface=Surface.CHAT, mode="chat",
    candidate_tool_refs=(unavailable_entry.spec.ref,),
))
wrong_mode = raises(ToolCallPreparationError, lambda: call_catalog.prepare_call(
    call_id="call-mode", run_id="run-1", step_id="step-1", tool_ref=search.spec.ref,
    arguments=original_arguments, surface=Surface.CHAT, mode="office",
    candidate_tool_refs=(search.spec.ref,),
))
wrong_surface = raises(ToolCallPreparationError, lambda: call_catalog.prepare_call(
    call_id="call-surface", run_id="run-1", step_id="step-1", tool_ref=search.spec.ref,
    arguments=original_arguments, surface=Surface.MCP, mode="chat",
    candidate_tool_refs=(search.spec.ref,),
))
ok(
    "unknown unavailable wrong-mode and wrong-surface tools cannot produce calls",
    getattr(unknown, "code", None) == "tool.unknown"
    and getattr(unavailable, "code", None) == "tool.unavailable"
    and getattr(wrong_mode, "code", None) == "tool.mode_denied"
    and getattr(wrong_surface, "code", None) == "tool.surface_denied",
    {"unknown": unknown, "unavailable": unavailable, "mode": wrong_mode, "surface": wrong_surface},
)

invalid = raises(ToolCallPreparationError, lambda: call_catalog.prepare_call(
    call_id="call-invalid", run_id="run-1", step_id="step-1", tool_ref=search.spec.ref,
    arguments={"query": "SECRET_VALUE", "options": {"limit": 0}},
    surface=Surface.CHAT, mode="chat", candidate_tool_refs=(search.spec.ref,),
))
ok(
    "malformed arguments fail before a typed call without echoing values",
    getattr(invalid, "code", None) == "tool.arguments_invalid"
    and "SECRET_VALUE" not in str(invalid),
    invalid,
)

exact = compare_tool_manifests(call_catalog.manifest, call_catalog.manifest)
ready = assess_tool_activation(
    call_catalog.manifest,
    exact,
    required_tool_refs=(search.spec.ref,),
    policy_ready=True,
    owner_approved=True,
    tools_flag_enabled=True,
    rollback_ready=True,
)
blocked_inputs = (
    (drift, call_catalog.manifest, True, True, True, True, "catalog.parity_failed"),
    (issue_parity, issue_catalog.manifest, True, True, True, True, "catalog.adapter_issues"),
    (exact, unavailable_catalog.manifest, True, True, True, True, "catalog.tool_unavailable"),
    (exact, call_catalog.manifest, False, True, True, True, "policy.not_ready"),
    (exact, call_catalog.manifest, True, False, True, True, "owner.approval_required"),
    (exact, call_catalog.manifest, True, True, False, True, "runtime.v2_tools.disabled"),
    (exact, call_catalog.manifest, True, True, True, False, "rollback.not_ready"),
)
blocked = [assess_tool_activation(
    manifest,
    parity,
    required_tool_refs=(search.spec.ref,),
    policy_ready=policy,
    owner_approved=owner,
    tools_flag_enabled=flag,
    rollback_ready=rollback,
) for parity, manifest, policy, owner, flag, rollback, _code in blocked_inputs]
ok(
    "activation is advisory and requires every explicit readiness condition",
    ready.ready
    and ready.reason_codes == ()
    and all(not result.ready for result in blocked)
    and all(code in result.reason_codes for result, (*_unused, code) in zip(blocked, blocked_inputs)),
    blocked,
)

current_flag = owner_flags.get_bool(owner_flags.RUNTIME_V2_TOOLS, False)
current_readiness = assess_tool_activation(
    call_catalog.manifest,
    exact,
    required_tool_refs=(search.spec.ref,),
    policy_ready=True,
    owner_approved=True,
    tools_flag_enabled=current_flag,
    rollback_ready=True,
)
live_files = (
    ROOT / "core" / "conductor.py",
    ROOT / "core" / "conductor_registry.py",
    ROOT / "core" / "tool_registry.py",
    ROOT / "core" / "mcp_client.py",
    ROOT / "core" / "mcp_server.py",
)
ok(
    "catalog service remains dormant behind the default-off tools flag",
    current_flag is False
    and not current_readiness.ready
    and "runtime.v2_tools.disabled" in current_readiness.reason_codes
    and all("core.runtime.tool_catalog" not in path.read_text(
        encoding="utf-8", errors="replace"
    ) for path in live_files),
)

_TEMP.cleanup()
print(f"\n{PASS}/{PASS} T06 RUN 3 TOOL CATALOG CHECKS PASS")

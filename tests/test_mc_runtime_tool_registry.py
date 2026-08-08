"""Acceptance checks for #21 T06 Run 1 dormant canonical tool registry."""
from __future__ import annotations

import copy
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import owner_flags  # noqa: E402
from core.runtime.contracts import (  # noqa: E402
    RiskLevel,
    RuntimeToolSpec,
    SideEffectClass,
    Surface,
    ToolAvailabilityStatus,
    ToolDiscoveryQuery,
)
from core.runtime.tool_registry import (  # noqa: E402
    CanonicalToolRegistry,
    ToolConflictError,
    ToolSchemaError,
    ToolValidationError,
)


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


def spec(
    *,
    name: str = "search",
    version: str = "1",
    modes: tuple[str, ...] = ("chat", "agent"),
    surfaces: tuple[Surface, ...] = (Surface.CHAT, Surface.AGENT),
    input_schema: dict | None = None,
    output_schema: dict | None = None,
) -> RuntimeToolSpec:
    return RuntimeToolSpec(
        name=name,
        namespace="tests",
        version=version,
        description=f"Canonical registry fixture for {name}",
        input_schema=input_schema or {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "$defs": {
                "selector": {
                    "oneOf": [
                        {
                            "type": "object",
                            "properties": {"id": {"type": "integer", "minimum": 1}},
                            "required": ["id"],
                            "additionalProperties": False,
                        },
                        {
                            "type": "object",
                            "properties": {"name": {"type": "string", "minLength": 1}},
                            "required": ["name"],
                            "additionalProperties": False,
                        },
                    ]
                }
            },
            "properties": {
                "query": {"type": "string", "minLength": 1},
                "format": {"type": "string", "enum": ["short", "long"]},
                "options": {
                    "type": "object",
                    "properties": {"limit": {"type": "integer", "minimum": 1}},
                    "required": ["limit"],
                    "additionalProperties": False,
                },
                "selector": {"$ref": "#/$defs/selector"},
            },
            "required": ["query", "format", "options", "selector"],
            "additionalProperties": False,
        },
        output_schema=output_schema or {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {
                "items": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["items"],
            "additionalProperties": False,
        },
        side_effect_class=SideEffectClass.NONE,
        risk=RiskLevel.NONE,
        allowed_modes=modes,
        allowed_surfaces=surfaces,
        adapter="tests.synthetic",
    )


registry = CanonicalToolRegistry()
search_v1 = spec()

invalid_root = raises(
    ToolSchemaError,
    lambda: registry.register(spec(input_schema={"type": "string"})),
)
invalid_schema = raises(
    ToolSchemaError,
    lambda: registry.register(spec(input_schema={"type": "object", "required": "query"})),
)
remote_ref = raises(
    ToolSchemaError,
    lambda: registry.register(spec(input_schema={
        "type": "object",
        "properties": {"query": {"$ref": "https://example.invalid/query.json"}},
    })),
)
invalid_name = raises(
    ToolSchemaError,
    lambda: registry.register(spec(name="has spaces")),
)
ok(
    "registration rejects invalid MCP names schemas and remote references",
    all((invalid_root, invalid_schema, remote_ref, invalid_name)),
    {
        "root": invalid_root,
        "schema": invalid_schema,
        "remote": remote_ref,
        "name": invalid_name,
    },
)

first = registry.register(search_v1)
first.input_schema["properties"]["query"]["minLength"] = 100
readback = registry.get(search_v1.ref)
readback.input_schema.clear()
replay = registry.register(search_v1)
conflict = raises(
    ToolConflictError,
    lambda: registry.register(replace(search_v1, description="changed contract")),
)
ok(
    "registered contracts are isolated exact replays while changed content conflicts",
    replay == search_v1
    and registry.get(search_v1.ref) == search_v1
    and conflict is not None
    and registry.registered_count == 1,
    conflict,
)

valid_args = {
    "query": "runtime",
    "format": "short",
    "options": {"limit": 3},
    "selector": {"id": 7},
}
original = copy.deepcopy(valid_args)
validated = registry.validate_arguments(search_v1.ref, valid_args)
validated["options"]["limit"] = 9
ok(
    "valid nested arguments return an isolated copy",
    valid_args == original and validated is not valid_args,
)

invalid_cases = [
    {"format": "short", "options": {"limit": 3}, "selector": {"id": 7}},
    {**valid_args, "format": "wide"},
    {**valid_args, "options": {"limit": 0}},
    {**valid_args, "options": {"limit": 3, "extra": True}},
    {**valid_args, "selector": {"id": 7, "name": "both"}},
    {**valid_args, "unexpected": "secret-do-not-echo"},
]
errors = [raises(ToolValidationError, lambda value=value: registry.validate_arguments(
    search_v1.ref, value
)) for value in invalid_cases]
ok(
    "required enum nested extra and oneOf violations fail without echoing values",
    all(errors) and all("secret-do-not-echo" not in str(error) for error in errors),
    errors,
)

valid_output = registry.validate_output(search_v1.ref, {"items": ["one", "two"]})
invalid_output = raises(
    ToolValidationError,
    lambda: registry.validate_output(search_v1.ref, {"items": [1]}),
)
ok(
    "output contracts use the same strict validator",
    valid_output == {"items": ["one", "two"]} and invalid_output is not None,
    invalid_output,
)

empty_discovery = registry.discover(ToolDiscoveryQuery(
    surface=Surface.CHAT,
    mode="chat",
))
unknown_discovery = registry.discover(ToolDiscoveryQuery(
    surface=Surface.CHAT,
    mode="chat",
    candidate_tool_refs=(search_v1.ref,),
))
ok(
    "discovery is empty without an allowlist and unknown availability fails closed",
    empty_discovery.tools == ()
    and unknown_discovery.tools == ()
    and empty_discovery.truncated is False,
    {"empty": empty_discovery, "unknown": unknown_discovery},
)

registry.set_availability(
    search_v1.ref,
    ToolAvailabilityStatus.AVAILABLE,
    reason_codes=("adapter.ready",),
)
available = registry.discover(ToolDiscoveryQuery(
    surface=Surface.CHAT,
    mode="chat",
    candidate_tool_refs=(search_v1.ref, "tests.unknown@1"),
))
wrong_mode = registry.discover(ToolDiscoveryQuery(
    surface=Surface.CHAT,
    mode="other",
    candidate_tool_refs=(search_v1.ref,),
))
wrong_surface = registry.discover(ToolDiscoveryQuery(
    surface=Surface.CLI,
    mode="chat",
    candidate_tool_refs=(search_v1.ref,),
))
ok(
    "discovery requires explicit available mode and surface matches",
    tuple(item.ref for item in available.tools) == (search_v1.ref,)
    and wrong_mode.tools == ()
    and wrong_surface.tools == (),
    {"available": available, "mode": wrong_mode, "surface": wrong_surface},
)

alpha = registry.register(spec(name="alpha"))
beta = registry.register(spec(name="beta"))
search_v2 = registry.register(spec(version="2"))
for item in (alpha, beta, search_v2):
    registry.set_availability(item.ref, ToolAvailabilityStatus.AVAILABLE)
ordered = registry.discover(ToolDiscoveryQuery(
    surface=Surface.CHAT,
    mode="chat",
    candidate_tool_refs=(search_v2.ref, beta.ref, search_v1.ref, alpha.ref),
    limit=3,
))
ok(
    "discovery is deterministic bounded and keeps exact versions",
    tuple(item.ref for item in ordered.tools) == tuple(sorted((
        alpha.ref, beta.ref, search_v1.ref, search_v2.ref
    )))[:3]
    and ordered.truncated is True,
    ordered,
)

registry.set_availability(
    beta.ref,
    ToolAvailabilityStatus.UNAVAILABLE,
    reason_codes=("adapter.offline",),
)
after_offline = registry.discover(ToolDiscoveryQuery(
    surface=Surface.CHAT,
    mode="chat",
    candidate_tool_refs=(beta.ref,),
))
ok(
    "unavailable tools disappear from discovery",
    after_offline.tools == ()
    and registry.availability(beta.ref).status is ToolAvailabilityStatus.UNAVAILABLE,
    after_offline,
)

live_files = (
    ROOT / "core" / "conductor.py",
    ROOT / "core" / "conductor_registry.py",
    ROOT / "core" / "tool_registry.py",
    ROOT / "core" / "mcp_client.py",
    ROOT / "core" / "mcp_server.py",
)
ok(
    "canonical registry remains dormant behind the default-off tools flag",
    owner_flags.get_bool(owner_flags.RUNTIME_V2_TOOLS, False) is False
    and all("core.runtime.tool_registry" not in path.read_text(
        encoding="utf-8", errors="replace"
    ) for path in live_files),
)

print(f"\n{PASS}/{PASS} T06 RUN 1 TOOL REGISTRY CHECKS PASS")

"""Acceptance checks for #21 T06 Run 2 dormant catalog adapters."""
from __future__ import annotations

import asyncio
import copy
import json
import os
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_TEMP = tempfile.TemporaryDirectory(prefix="tobi_t06_run2_")
os.environ["DB_PATH"] = str(Path(_TEMP.name) / "agent.db")

from core.runtime.contracts import (  # noqa: E402
    RiskLevel,
    SideEffectClass,
    Surface,
    ToolAvailabilityStatus,
    ToolDiscoveryQuery,
)
from core.runtime.tool_adapters import (  # noqa: E402
    adapt_inbound_mcp_catalog,
    adapt_legacy_catalog,
    adapt_outbound_mcp_catalog,
)
from core.runtime.tool_registry import CanonicalToolRegistry  # noqa: E402
from core import database, owner_flags  # noqa: E402

database.DB_PATH = os.environ["DB_PATH"]
database.init_database()

from core import conductor_registry, mcp_client, mcp_server  # noqa: E402


PASS = 0


def ok(name: str, condition: bool, detail: object = "") -> None:
    global PASS
    if not condition:
        print(f"FAIL {name}: {detail}")
        raise SystemExit(1)
    PASS += 1
    print(f"PASS {name}")


legacy = adapt_legacy_catalog(conductor_registry.TOOL_SPECS)
legacy_names = tuple(entry.spec.name for entry in legacy.entries)
ok(
    "current Conductor catalog adapts with exact deterministic parity",
    not legacy.issues
    and legacy_names == tuple(sorted(conductor_registry.TOOL_SPECS))
    and len(legacy.entries) == len(conductor_registry.TOOL_SPECS)
    and all(entry.spec.namespace == "tobi.conductor" for entry in legacy.entries),
    {"issues": legacy.issues, "count": len(legacy.entries)},
)

read_entry = next(entry for entry in legacy.entries if entry.spec.name == "list_projects")
act_entry = next(entry for entry in legacy.entries if entry.spec.name == "create_task")
ok(
    "legacy risk translation is truthful and conservative",
    read_entry.spec.risk is RiskLevel.NONE
    and read_entry.spec.side_effect_class is SideEffectClass.NONE
    and act_entry.spec.risk is RiskLevel.LOW
    and act_entry.spec.side_effect_class is SideEffectClass.IRREVERSIBLE
    and all(entry.availability.status is ToolAvailabilityStatus.UNKNOWN for entry in legacy.entries),
)

inbound_tools = asyncio.run(mcp_server.mcp.list_tools())
inbound = adapt_inbound_mcp_catalog(
    inbound_tools,
    sensitive_names=mcp_server.SENSITIVE_TOOLS,
)
ok(
    "public FastMCP definitions adapt with exact inbound parity",
    not inbound.issues
    and tuple(entry.spec.name for entry in inbound.entries) == tuple(sorted(mcp_server.TOOL_NAMES))
    and all(entry.spec.allowed_surfaces == (Surface.MCP,) for entry in inbound.entries),
    inbound.issues,
)

inbound_sensitive = next(entry for entry in inbound.entries if entry.spec.name == "run_mission")
inbound_read = next(entry for entry in inbound.entries if entry.spec.name == "query_brain")
ok(
    "inbound sensitivity stays authoritative without carrying callables",
    inbound_sensitive.spec.risk is RiskLevel.HIGH
    and inbound_sensitive.spec.side_effect_class is SideEffectClass.EXTERNAL
    and inbound_read.spec.risk is RiskLevel.NONE
    and inbound_read.spec.side_effect_class is SideEffectClass.NONE
    and all("callable" not in vars(entry.spec) for entry in inbound.entries),
)

schema = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {"query": {"type": "string"}},
    "required": ["query"],
    "additionalProperties": False,
}
remote_schema = {
    "type": "object",
    "properties": {"query": {"$ref": "https://example.invalid/schema.json"}},
}
conn = database.get_connection()
try:
    for cid, enabled, status, tested, endpoint, auth_ref in (
        (11, 1, "connected", "2026-08-09T00:00:00Z", "https://secret-one.invalid", "SECRET_ONE"),
        (12, 1, "connected", "2026-08-09T00:00:00Z", "https://secret-two.invalid", "SECRET_TWO"),
        (13, 0, "error", None, "https://secret-three.invalid", "SECRET_THREE"),
    ):
        conn.execute(
            "INSERT INTO mcp_connections "
            "(id,name,transport,endpoint,auth_ref,enabled,status,last_tested_at,tools_count) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (cid, "duplicate-name", "http", endpoint, auth_ref, enabled, status, tested, 1),
        )
    rows = (
        ("11", "search", json.dumps(schema), 1, "ask"),
        ("12", "search", json.dumps(schema), 1, "allow"),
        ("13", "offline", json.dumps(schema), 1, "allow"),
        ("11", "broken", "{not-json", 1, "ask"),
        ("11", "remote", json.dumps(remote_schema), 1, "ask"),
    )
    conn.executemany(
        "INSERT INTO mcp_tools (source,name,schema_json,enabled,permission) VALUES (?,?,?,?,?)",
        rows,
    )
    conn.commit()
finally:
    conn.close()

outbound_rows = mcp_client.catalog_snapshot()
serialized_snapshot = json.dumps(outbound_rows, sort_keys=True)
ok(
    "outbound snapshot exposes metadata but never endpoint or credential references",
    len(outbound_rows) == 5
    and all("endpoint" not in row and "auth_ref" not in row for row in outbound_rows)
    and "SECRET_" not in serialized_snapshot
    and "secret-one" not in serialized_snapshot,
    outbound_rows,
)

outbound = adapt_outbound_mcp_catalog(outbound_rows)
outbound_search = [entry for entry in outbound.entries if entry.spec.name == "search"]
ok(
    "outbound identities disambiguate servers and versions follow contract content",
    len(outbound_search) == 2
    and outbound_search[0].spec.ref != outbound_search[1].spec.ref
    and {entry.spec.namespace for entry in outbound_search}
    == {"mcp.outbound.connection_11", "mcp.outbound.connection_12"},
    outbound_search,
)

source_row = next(row for row in outbound_rows if row["source"] == "11" and row["name"] == "search")
changed_row = copy.deepcopy(source_row)
changed_row["input_schema"]["properties"]["limit"] = {"type": "integer"}
changed = adapt_outbound_mcp_catalog((changed_row,)).entries[0]
denied_row = copy.deepcopy(source_row)
denied_row["permission"] = "deny"
permission_only = adapt_outbound_mcp_catalog((denied_row,)).entries[0]
original = next(entry for entry in outbound_search if entry.source_key == "mcp:outbound:11:search")
offline = next(entry for entry in outbound.entries if entry.spec.name == "offline")
ok(
    "schema controls version while permission stays separate from availability",
    changed.spec.version != original.spec.version
    and permission_only.spec.ref == original.spec.ref
    and permission_only.availability == original.availability
    and original.availability.status is ToolAvailabilityStatus.AVAILABLE
    and offline.availability.status is ToolAvailabilityStatus.UNAVAILABLE,
)

issue_codes = {(issue.source_key, issue.code) for issue in outbound.issues}
ok(
    "malformed and remote outbound schemas fail closed per tool",
    len(outbound.entries) == 3
    and ("mcp:outbound:11:broken", "schema.invalid") in issue_codes
    and ("mcp:outbound:11:remote", "schema.invalid") in issue_codes,
    outbound.issues,
)

registry = CanonicalToolRegistry()
all_entries = (*legacy.entries, *inbound.entries, *outbound.entries)
for entry in all_entries:
    registry.register(entry.spec)
    registry.set_availability(
        entry.spec.ref,
        entry.availability.status,
        reason_codes=entry.availability.reason_codes,
    )
legacy_hidden = registry.discover(ToolDiscoveryQuery(
    surface=Surface.CHAT,
    mode="chat",
    candidate_tool_refs=(read_entry.spec.ref,),
))
inbound_visible = registry.discover(ToolDiscoveryQuery(
    surface=Surface.MCP,
    mode="chat",
    candidate_tool_refs=(inbound_read.spec.ref,),
))
ok(
    "isolated registry keeps unknown legacy hidden and explicit inbound available",
    registry.registered_count == len(all_entries)
    and legacy_hidden.tools == ()
    and tuple(tool.ref for tool in inbound_visible.tools) == (inbound_read.spec.ref,),
)

live_files = (
    ROOT / "core" / "conductor.py",
    ROOT / "core" / "conductor_registry.py",
    ROOT / "core" / "tool_registry.py",
    ROOT / "core" / "mcp_server.py",
)
ok(
    "catalog adapters remain dormant behind the default-off tools flag",
    owner_flags.get_bool(owner_flags.RUNTIME_V2_TOOLS, False) is False
    and all("core.runtime.tool_adapters" not in path.read_text(
        encoding="utf-8", errors="replace"
    ) for path in live_files)
    and not hasattr(registry, "invoke"),
)

_TEMP.cleanup()
print(f"\n{PASS}/{PASS} T06 RUN 2 TOOL ADAPTER CHECKS PASS")

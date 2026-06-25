"""MCP Hub — M2: TOBI as an MCP client (outbound connection manager).

Connects out to external MCP servers across transports (Streamable HTTP, stdio,
legacy SSE; A2A is M4), discovers their tools, and surfaces them — gated by a
**per-tool permission model** (allow / ask / deny). Credentials come from the
Genesis vault. Connections are **stateless per-operation** (a fresh session is
opened for test/refresh/invoke), so "auto-reconnect" is inherent and there are no
fragile long-lived sockets; ``health_check_all()`` refreshes live status.

External tools and their outputs are treated as **untrusted** — new tools default
to ``ask`` so the owner stays in the loop.
"""
from __future__ import annotations

import os
import json
import time
import shlex
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

from core.database import get_connection
from core import mcp_security as security

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client, StdioServerParameters

DEFAULT_TIMEOUT = 25.0
SUPPORTED_TRANSPORTS = {"http", "streamable_http", "sse", "stdio"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── transport session (opened per operation) ───────────────────────────────
def _stdio_params(endpoint: str) -> StdioServerParameters:
    """Accepts a JSON array (``["python","server.py"]``) or a shell-style string."""
    endpoint = (endpoint or "").strip()
    if endpoint.startswith("["):
        parts = json.loads(endpoint)
    else:
        parts = shlex.split(endpoint, posix=(os.name != "nt"))
    if not parts:
        raise ValueError("stdio endpoint is empty")
    return StdioServerParameters(command=parts[0], args=list(parts[1:]), env=os.environ.copy())


@asynccontextmanager
async def _session(transport: str, endpoint: str, headers: Optional[dict] = None):
    transport = (transport or "http").lower()
    if transport in ("http", "streamable_http", "streamable-http"):
        async with streamablehttp_client(endpoint, headers=headers) as (read, write, _):
            async with ClientSession(read, write) as s:
                await s.initialize()
                yield s
    elif transport == "sse":
        async with sse_client(endpoint, headers=headers) as (read, write):
            async with ClientSession(read, write) as s:
                await s.initialize()
                yield s
    elif transport == "stdio":
        async with stdio_client(_stdio_params(endpoint)) as (read, write):
            async with ClientSession(read, write) as s:
                await s.initialize()
                yield s
    else:
        raise ValueError(f"Unsupported transport: {transport}")


async def _probe(transport: str, endpoint: str, headers: Optional[dict] = None,
                 timeout: float = DEFAULT_TIMEOUT) -> list[dict]:
    """Handshake + list tools. Raises on failure (used for block-on-add)."""
    async def _run():
        async with _session(transport, endpoint, headers) as s:
            res = await s.list_tools()
            return [{"name": t.name, "description": (t.description or "")[:300],
                     "schema": getattr(t, "inputSchema", None)} for t in res.tools]
    return await asyncio.wait_for(_run(), timeout)


# ── credentials (from the Genesis vault) ───────────────────────────────────
def _auth_headers(auth_ref: Optional[str]) -> Optional[dict]:
    if not auth_ref:
        return None
    try:
        from core import vault
        conn = get_connection()
        try:
            tok = vault.get_secret(conn, auth_ref)
        finally:
            conn.close()
        return {"Authorization": f"Bearer {tok}"} if tok else None
    except Exception:
        return None  # vault locked / missing → connect without auth, server decides


# ── connection rows ─────────────────────────────────────────────────────────
def _conn_row(cid: int) -> Optional[dict]:
    conn = get_connection()
    try:
        r = conn.execute(
            "SELECT id, name, transport, endpoint, auth_ref, enabled, status, last_tested_at, tools_count "
            "FROM mcp_connections WHERE id=?", (cid,)).fetchone()
        return dict(r) if r else None
    finally:
        conn.close()


def list_connections() -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, name, transport, endpoint, enabled, status, last_tested_at, tools_count "
            "FROM mcp_connections ORDER BY id").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _sync_tools(conn, cid: int, tools: list[dict]) -> None:
    """Replace a connection's tool rows, preserving existing enabled/permission."""
    src = str(cid)
    existing = {r[0]: (r[1], r[2]) for r in conn.execute(
        "SELECT name, enabled, permission FROM mcp_tools WHERE source=?", (src,)).fetchall()}
    conn.execute("DELETE FROM mcp_tools WHERE source=?", (src,))
    for t in tools:
        enabled, perm = existing.get(t["name"], (1, "ask"))  # untrusted default = ask
        conn.execute(
            "INSERT INTO mcp_tools (source, name, schema_json, enabled, permission) VALUES (?,?,?,?,?)",
            (src, t["name"], json.dumps(t.get("schema")), enabled, perm))


async def add_connection(name: str, transport: str, endpoint: str,
                         token: Optional[str] = None) -> dict:
    """Add + test (block on failure). Discovers tools and persists them; if a token
    is given it is stored in the vault and referenced by the connection."""
    transport = (transport or "http").lower()
    if transport not in SUPPORTED_TRANSPORTS:
        raise ValueError(f"Unsupported transport: {transport}")
    headers = {"Authorization": f"Bearer {token}"} if token else None
    tools = await _probe(transport, endpoint, headers)  # raises → blocks the add

    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO mcp_connections (name, transport, endpoint, enabled, status, last_tested_at, tools_count) "
            "VALUES (?,?,?,1,'connected',?,?)", (name.strip() or "server", transport, endpoint, _now(), len(tools)))
        cid = cur.lastrowid
        if token:
            from core import vault
            secret_name = f"MCP_CONN_{cid}"
            vault.set_secret(conn, secret_name, token, secret_type="oauth", integration_id="mcp")
            conn.execute("UPDATE mcp_connections SET auth_ref=? WHERE id=?", (secret_name, cid))
        _sync_tools(conn, cid, tools)
        conn.commit()
    finally:
        conn.close()
    security.audit("out", peer=name, status="connected", response=f"{len(tools)} tools")
    return {"id": cid, "name": name, "transport": transport, "status": "connected", "tools": tools}


def _update_status(cid: int, status: str) -> None:
    conn = get_connection()
    try:
        conn.execute("UPDATE mcp_connections SET status=?, last_tested_at=? WHERE id=?", (status, _now(), cid))
        conn.commit()
    finally:
        conn.close()


async def refresh_connection(cid: int) -> dict:
    """Re-handshake, refresh status + re-sync the connection's tools."""
    row = _conn_row(cid)
    if not row:
        raise ValueError("unknown connection")
    headers = _auth_headers(row["auth_ref"])
    try:
        tools = await _probe(row["transport"], row["endpoint"], headers)
    except Exception as e:
        _update_status(cid, "error")
        security.audit("out", peer=row["name"], status="error", error=str(e))
        return {"ok": False, "status": "error", "error": str(e)[:200]}
    conn = get_connection()
    try:
        _sync_tools(conn, cid, tools)
        conn.execute("UPDATE mcp_connections SET status='connected', last_tested_at=?, tools_count=? WHERE id=?",
                     (_now(), len(tools), cid))
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "status": "connected", "tools_count": len(tools)}


# test == refresh (re-handshake + re-sync); kept as a distinct name for the API.
async def test_connection(cid: int) -> dict:
    return await refresh_connection(cid)


def set_connection_enabled(cid: int, enabled: bool) -> None:
    conn = get_connection()
    try:
        conn.execute("UPDATE mcp_connections SET enabled=? WHERE id=?", (int(enabled), cid))
        conn.commit()
    finally:
        conn.close()


def delete_connection(cid: int) -> None:
    row = _conn_row(cid)
    conn = get_connection()
    try:
        conn.execute("DELETE FROM mcp_tools WHERE source=?", (str(cid),))
        conn.execute("DELETE FROM mcp_connections WHERE id=?", (cid,))
        conn.commit()
    finally:
        conn.close()
    if row and row.get("auth_ref"):
        try:
            from core import vault
            c2 = get_connection()
            try:
                vault.delete_secret(c2, row["auth_ref"], integration_id="mcp")
            finally:
                c2.close()
        except Exception:
            pass


# ── tools ───────────────────────────────────────────────────────────────────
def list_tools(source: Optional[str] = None) -> list[dict]:
    conn = get_connection()
    try:
        if source:
            rows = conn.execute("SELECT id, source, name, enabled, permission FROM mcp_tools WHERE source=? ORDER BY name",
                                (source,)).fetchall()
        else:
            rows = conn.execute("SELECT id, source, name, enabled, permission FROM mcp_tools ORDER BY source, name").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _tool_row(tool_id: int) -> Optional[dict]:
    conn = get_connection()
    try:
        r = conn.execute("SELECT id, source, name, enabled, permission FROM mcp_tools WHERE id=?", (tool_id,)).fetchone()
        return dict(r) if r else None
    finally:
        conn.close()


def set_tool(tool_id: int, enabled: Optional[bool] = None, permission: Optional[str] = None) -> dict:
    sets, params = [], []
    if enabled is not None:
        sets.append("enabled=?"); params.append(int(enabled))
    if permission in ("allow", "ask", "deny"):
        sets.append("permission=?"); params.append(permission)
    if sets:
        conn = get_connection()
        try:
            conn.execute(f"UPDATE mcp_tools SET {', '.join(sets)} WHERE id=?", (*params, tool_id))
            conn.commit()
        finally:
            conn.close()
    return _tool_row(tool_id) or {"id": tool_id}


def available_tools_for_agent() -> list[dict]:
    """Enabled external tools TOBI's agents may use (deny excluded). 'ask' tools
    require an approval at call time. Consumed by the tool-loop (Conductor #7)."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, source, name, permission FROM mcp_tools WHERE enabled=1 AND permission!='deny' ORDER BY source, name"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _result_text(res) -> str:
    parts = []
    for c in getattr(res, "content", []) or []:
        t = getattr(c, "text", None)
        if t:
            parts.append(t)
    return "\n".join(parts) if parts else ""


async def invoke_tool(tool_id: int, args: Optional[dict] = None, *, owner_override: bool = False) -> dict:
    """Call an external tool, enforcing the per-tool permission model.

    owner_override=True is the dashboard 'try it' path (the owner is present) and
    runs regardless of allow/ask, but still respects an explicit 'deny'.
    """
    t = _tool_row(tool_id)
    if not t:
        raise ValueError("unknown tool")
    if not t["enabled"]:
        return {"ok": False, "error": "tool is disabled"}
    cid = int(t["source"])
    row = _conn_row(cid)
    if not row:
        return {"ok": False, "error": "connection missing"}
    perm = t["permission"]

    if perm == "deny":
        security.audit("out", peer=row["name"], tool=t["name"], status="denied")
        return {"ok": False, "error": "tool permission is 'deny'"}
    if perm == "ask" and not owner_override:
        aid = security.create_approval("agent", f'{row["name"]}:{t["name"]}', args or {})
        security.audit("out", peer=row["name"], tool=t["name"], status="pending")
        return {"ok": False, "pending": True, "approval_id": aid,
                "message": f"Approval #{aid} required before calling {t['name']}."}

    headers = _auth_headers(row["auth_ref"])
    t0 = time.time()
    try:
        async def _run():
            async with _session(row["transport"], row["endpoint"], headers) as s:
                return await s.call_tool(t["name"], args or {})
        res = await asyncio.wait_for(_run(), DEFAULT_TIMEOUT)
        text = _result_text(res)
        is_err = bool(getattr(res, "isError", False))
        security.audit("out", peer=row["name"], tool=t["name"],
                       status="error" if is_err else "ok",
                       latency_ms=int((time.time() - t0) * 1000), response=text[:1000])
        return {"ok": not is_err, "content": text}
    except Exception as e:
        security.audit("out", peer=row["name"], tool=t["name"], status="error",
                       latency_ms=int((time.time() - t0) * 1000), error=str(e))
        return {"ok": False, "error": str(e)[:300]}


# ── health ──────────────────────────────────────────────────────────────────
async def health_check_all() -> list[dict]:
    """Re-test every enabled connection and refresh its live status."""
    out = []
    for c in list_connections():
        if not c.get("enabled"):
            out.append({"id": c["id"], "name": c["name"], "status": "disabled"})
            continue
        res = await test_connection(c["id"])
        out.append({"id": c["id"], "name": c["name"], "status": res.get("status")})
    return out

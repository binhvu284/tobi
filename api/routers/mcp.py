"""MCP Hub + A2A management API — /api/mcp/* (#5).

Extracted from api/dashboard.py (refactor Slice — pre-#21 decomposition). Byte-
identical handlers; only @app.* -> @router.*, with _vault_guard from api.deps and a
local copy of the MCP availability import block (dashboard keeps its own for the
/mcp mount + .well-known routes). See docs/REFACTORING_PLAN.md.
"""
from __future__ import annotations

import asyncio
import json  # noqa: F401 - used by some handlers
import os  # noqa: F401 - used by some handlers

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from api.deps import _vault_guard
from core import vault
from core import mcp_security as mcpsec

try:
    from core import mcp_server, mcp_client, mcp_tunnel
    from core import a2a as mcp_a2a
    MCP_AVAILABLE = True
except Exception:
    mcp_server = mcp_client = mcp_tunnel = mcp_a2a = None  # type: ignore
    MCP_AVAILABLE = False

router = APIRouter(tags=["mcp"])


# ── MCP Hub (#5) management API ─────────────────────────────────────────────
# Admin of a (potentially internet-exposed) MCP server is sensitive → gated by the
# vault session, like the other secret-management endpoints. The MCP wire protocol
# itself lives at /mcp and is auth'd by McpAuthMiddleware (bearer token + scopes).

class McpConfigReq(BaseModel):
    enabled: bool | None = None
    public_url: str | None = None
    rate_limit_per_minute: int | None = None


class McpClientReq(BaseModel):
    name: str
    scopes: list[str] | None = None


class McpScopesReq(BaseModel):
    scopes: list[str]


@router.get("/api/mcp/server/config")
async def mcp_server_config(x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    _vault_guard(x_vault_session)
    cfg = mcpsec.get_config()
    tools = []
    if MCP_AVAILABLE:
        try:
            tools = [{"name": t.name, "description": (t.description or "")[:160],
                      "sensitive": t.name in mcp_server.SENSITIVE_TOOLS}
                     for t in await mcp_server.mcp.list_tools()]
        except Exception:
            tools = []
    oauth = mcpsec.get_oauth_config()
    oauth_public = {"enabled": bool(oauth.get("enabled")), "issuer": oauth.get("issuer"),
                    "audience": oauth.get("audience"), "alg": oauth.get("alg", "HS256")}
    tunnel = mcp_tunnel.status() if MCP_AVAILABLE else {"available": False, "running": False}
    return {"available": MCP_AVAILABLE, "config": cfg, "tools": tools,
            "mount": "/mcp" if MCP_AVAILABLE else None,
            "exposed": bool(cfg.get("exposed")), "oauth": oauth_public, "tunnel": tunnel}


@router.put("/api/mcp/server/config")
async def mcp_set_config(body: McpConfigReq, x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    _vault_guard(x_vault_session)
    fields: dict = {}
    if body.enabled is not None:
        fields["enabled"] = int(body.enabled)
    if body.public_url is not None:
        fields["public_url"] = body.public_url
    if body.rate_limit_per_minute is not None:
        fields["rate_limit_json"] = json.dumps({"per_minute": int(body.rate_limit_per_minute)})
    return {"ok": True, "config": mcpsec.set_config(**fields)}


@router.get("/api/mcp/clients")
async def mcp_clients(x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    _vault_guard(x_vault_session)
    return {"clients": mcpsec.list_clients()}


@router.post("/api/mcp/clients")
async def mcp_issue_client(body: McpClientReq, x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    """Issue an inbound client. Returns the raw token ONCE — it's only stored hashed."""
    _vault_guard(x_vault_session)
    return {"ok": True, **mcpsec.issue_client(body.name, body.scopes)}


@router.patch("/api/mcp/clients/{client_id}")
async def mcp_patch_client(client_id: int, body: McpScopesReq, x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    _vault_guard(x_vault_session)
    mcpsec.set_client_scopes(client_id, body.scopes)
    return {"ok": True}


@router.delete("/api/mcp/clients/{client_id}")
async def mcp_revoke_client(client_id: int, x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    _vault_guard(x_vault_session)
    mcpsec.revoke_client(client_id)
    return {"ok": True}


@router.get("/api/mcp/logs")
async def mcp_logs(limit: int = Query(100), direction: str | None = Query(None),
                   x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    _vault_guard(x_vault_session)
    return {"logs": mcpsec.get_logs(limit, direction)}


@router.get("/api/mcp/approvals")
async def mcp_approvals(status: str | None = Query("pending"),
                        x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    _vault_guard(x_vault_session)
    return {"approvals": mcpsec.list_approvals(status)}


@router.post("/api/mcp/approvals/{approval_id}/approve")
async def mcp_approve(approval_id: int, x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    _vault_guard(x_vault_session)
    return {"ok": True, **mcpsec.decide_approval(approval_id, True)}


@router.post("/api/mcp/approvals/{approval_id}/reject")
async def mcp_reject(approval_id: int, x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    _vault_guard(x_vault_session)
    return {"ok": True, **mcpsec.decide_approval(approval_id, False)}


# ── MCP Hub (#5) — M2: outbound client (connections + external tools) ───────
class McpConnectionReq(BaseModel):
    name: str
    transport: str = "http"            # http | sse | stdio
    endpoint: str
    token: str | None = None           # optional bearer; stored in the vault


class McpConnEnableReq(BaseModel):
    enabled: bool


class McpToolPatchReq(BaseModel):
    enabled: bool | None = None
    permission: str | None = None      # allow | ask | deny


class McpInvokeReq(BaseModel):
    args: dict = Field(default_factory=dict)


def _mcp_guard(token: str | None) -> None:
    _vault_guard(token)
    if not MCP_AVAILABLE:
        raise HTTPException(status_code=503, detail="MCP SDK not installed — run: pip install mcp")


@router.get("/api/mcp/connections")
async def mcp_connections(x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    _mcp_guard(x_vault_session)
    return {"connections": mcp_client.list_connections()}


@router.post("/api/mcp/connections")
async def mcp_add_connection(body: McpConnectionReq, x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    """Add + test an outbound MCP server. Blocks (400) if the handshake fails."""
    _mcp_guard(x_vault_session)
    try:
        return {"ok": True, **await mcp_client.add_connection(body.name, body.transport, body.endpoint, body.token)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Connection test failed: {e}")


@router.post("/api/mcp/connections/{cid}/test")
async def mcp_test_connection(cid: int, x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    _mcp_guard(x_vault_session)
    return await mcp_client.test_connection(cid)


@router.post("/api/mcp/connections/{cid}/refresh")
async def mcp_refresh_connection(cid: int, x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    _mcp_guard(x_vault_session)
    return await mcp_client.refresh_connection(cid)


@router.patch("/api/mcp/connections/{cid}")
async def mcp_patch_connection(cid: int, body: McpConnEnableReq, x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    _mcp_guard(x_vault_session)
    mcp_client.set_connection_enabled(cid, body.enabled)
    return {"ok": True}


@router.delete("/api/mcp/connections/{cid}")
async def mcp_delete_connection(cid: int, x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    _mcp_guard(x_vault_session)
    mcp_client.delete_connection(cid)
    return {"ok": True}


@router.post("/api/mcp/connections/health")
async def mcp_connections_health(x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    _mcp_guard(x_vault_session)
    return {"health": await mcp_client.health_check_all()}


@router.get("/api/mcp/tools")
async def mcp_tools(source: str | None = Query(None), x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    """External (connected) tools. Self/exposed tools are in /server/config."""
    _mcp_guard(x_vault_session)
    return {"tools": mcp_client.list_tools(source)}


@router.patch("/api/mcp/tools/{tool_id}")
async def mcp_patch_tool(tool_id: int, body: McpToolPatchReq, x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    _mcp_guard(x_vault_session)
    return {"ok": True, "tool": mcp_client.set_tool(tool_id, body.enabled, body.permission)}


@router.post("/api/mcp/tools/{tool_id}/invoke")
async def mcp_invoke_tool(tool_id: int, body: McpInvokeReq, x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    """'Try it' — owner-initiated call (respects 'deny', overrides 'ask')."""
    _mcp_guard(x_vault_session)
    return await mcp_client.invoke_tool(tool_id, body.args, owner_override=True)


# ── MCP Hub (#5) — M4: OAuth, internet exposure (tunnel), A2A ───────────────
class McpOAuthReq(BaseModel):
    enabled: bool
    issuer: str | None = None
    audience: str | None = None
    algorithm: str = "HS256"
    secret: str | None = None          # HS256 signing key → stored in the vault


class McpTunnelReq(BaseModel):
    action: str                        # start | stop
    port: int | None = None


class A2aCardReq(BaseModel):
    name: str | None = None
    description: str | None = None
    version: str | None = None


class A2aPeerReq(BaseModel):
    url: str


class A2aMessageReq(BaseModel):
    text: str


@router.put("/api/mcp/server/oauth")
async def mcp_set_oauth(body: McpOAuthReq, x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    _mcp_guard(x_vault_session)
    oc = mcpsec.set_oauth_config(enabled=body.enabled, issuer=body.issuer, audience=body.audience,
                                 algorithm=body.algorithm, secret=body.secret)
    return {"ok": True, "oauth": {"enabled": oc["enabled"], "issuer": oc.get("issuer"),
                                  "audience": oc.get("audience"), "alg": oc.get("alg")}}


@router.get("/api/mcp/server/tunnel")
async def mcp_get_tunnel(x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    _mcp_guard(x_vault_session)
    return mcp_tunnel.status()


@router.post("/api/mcp/server/tunnel")
async def mcp_set_tunnel(body: McpTunnelReq, x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    _mcp_guard(x_vault_session)
    if body.action == "start":
        port = body.port or int(os.getenv("DASHBOARD_PORT", "8080"))
        return await asyncio.to_thread(mcp_tunnel.start, port)
    if body.action == "stop":
        return mcp_tunnel.stop()
    raise HTTPException(status_code=400, detail="action must be 'start' or 'stop'")


@router.get("/api/mcp/a2a/card")
async def mcp_a2a_card(x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    _mcp_guard(x_vault_session)
    pub = mcp_tunnel.status().get("public_url")
    return {"card": mcp_a2a.get_self_card(pub)}


@router.put("/api/mcp/a2a/card")
async def mcp_a2a_set_card(body: A2aCardReq, x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    _mcp_guard(x_vault_session)
    mcp_a2a.set_self_card(body.name, body.description, body.version)
    return {"ok": True, "card": mcp_a2a.get_self_card(mcp_tunnel.status().get("public_url"))}


@router.get("/api/mcp/a2a/peers")
async def mcp_a2a_peers(x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    _mcp_guard(x_vault_session)
    return {"peers": mcp_a2a.list_peers()}


@router.post("/api/mcp/a2a/peers")
async def mcp_a2a_add_peer(body: A2aPeerReq, x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    _mcp_guard(x_vault_session)
    try:
        return {"ok": True, **await mcp_a2a.add_peer(body.url)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not add peer: {e}")


@router.delete("/api/mcp/a2a/peers/{peer_id}")
async def mcp_a2a_remove_peer(peer_id: int, x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    _mcp_guard(x_vault_session)
    mcp_a2a.remove_peer(peer_id)
    return {"ok": True}


@router.post("/api/mcp/a2a/peers/{peer_id}/message")
async def mcp_a2a_message(peer_id: int, body: A2aMessageReq, x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    _mcp_guard(x_vault_session)
    return await mcp_a2a.send_message(peer_id, body.text)

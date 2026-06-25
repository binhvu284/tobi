"""MCP Hub — M1: TOBI as an MCP server (inbound).

A FastMCP server (Streamable HTTP) that exposes TOBI's capabilities as MCP
**tools**, **resources**, and **prompts** by wrapping existing core functions.
Mounted in the FastAPI app at ``/mcp``. Inbound requests pass through
``McpAuthMiddleware`` (bearer-token auth + per-client rate limit + per-tool
scope enforcement + audit). Sensitive tools are **approval-gated** (human in the
loop) — they create an approval request instead of executing.

OAuth 2.1, internet exposure, the outbound client, and A2A are later milestones.
"""
from __future__ import annotations

import os
import json
import time
from contextvars import ContextVar
from typing import Optional

from mcp.server.fastmcp import FastMCP

from core import mcp_security as security

# Caller identity for the in-flight request (best-effort; set by the middleware).
_current_peer: ContextVar[Optional[str]] = ContextVar("mcp_peer", default=None)

# Tools that change real-world state require owner approval before running.
SENSITIVE_TOOLS = {"run_mission"}
# Names of the tools exposed by this server (used for A2A skills + scope pickers).
TOOL_NAMES = ["ask_tobi", "query_brain", "get_status", "list_projects", "recent_lessons", "run_mission"]


def _transport_security():
    """DNS-rebinding/Host allowlist. When the server is marked internet-exposed we
    rely on token/OAuth auth and accept dynamic tunnel hosts; otherwise we lock to
    localhost. Read once at import — toggling exposure needs a restart to apply."""
    try:
        from mcp.server.transport_security import TransportSecuritySettings
    except Exception:
        return None
    try:
        if bool(security.get_config().get("exposed")):
            return TransportSecuritySettings(enable_dns_rebinding_protection=False)
    except Exception:
        pass
    ports = {os.getenv("DASHBOARD_PORT", "8080"), os.getenv("API_PORT", "8000"), "8080", "8090"}
    hosts = ["localhost", "127.0.0.1"]
    allowed = hosts + [f"{h}:{p}" for h in hosts for p in ports]
    return TransportSecuritySettings(allowed_hosts=allowed, allowed_origins=["*"])


mcp = FastMCP("TOBI Mission Control", stateless_http=True, streamable_http_path="/",
              transport_security=_transport_security())


# ── helper: time + audit a read tool ──────────────────────────────────────
def _audited(tool: str, fn) -> str:
    peer = _current_peer.get()
    t0 = time.time()
    try:
        out = fn()
        security.audit("in", peer=peer, tool=tool, status="ok",
                       latency_ms=int((time.time() - t0) * 1000), response=out)
        return out
    except Exception as e:  # tools never raise across the protocol boundary
        security.audit("in", peer=peer, tool=tool, status="error",
                       latency_ms=int((time.time() - t0) * 1000), error=str(e))
        return f"Error: {e}"


# ── tools (read) ──────────────────────────────────────────────────────────
@mcp.tool()
def ask_tobi(message: str) -> str:
    """Ask TOBI a question or chat. Returns TOBI's reply, grounded in its memory."""
    def _():
        from core import brain
        r = brain.chat(message)
        if isinstance(r, dict):
            return r.get("reply") or r.get("content") or json.dumps(r)[:4000]
        return str(r)
    return _audited("ask_tobi", _)


@mcp.tool()
def query_brain(query: str, limit: int = 6) -> str:
    """Search TOBI's long-term memory (the Brain) for facts relevant to a query."""
    def _():
        from core import brain
        items = brain.retrieve(query, k=int(limit)) or []
        if not items:
            return "No matching memories."
        lines = [f"- [{m.get('category','?')}] {m.get('content','')}" for m in items]
        return "\n".join(lines)
    return _audited("query_brain", _)


@mcp.tool()
def get_status() -> str:
    """Live Mission Control status: projects, lessons, revenue, pending owner todos."""
    def _():
        from core.database import get_dashboard
        d = get_dashboard() or {}
        summary = {
            "active_projects": len(d.get("active_projects", []) or []),
            "pending_human_tasks": len(d.get("human_todos", []) or []),
            "revenue": d.get("revenue"),
        }
        return json.dumps(summary, default=str)
    return _audited("get_status", _)


@mcp.tool()
def list_projects() -> str:
    """List TOBI's projects with their status."""
    def _():
        from core.database import get_all_projects
        rows = get_all_projects() or []
        return json.dumps([{"id": p.get("id"), "name": p.get("name"), "status": p.get("status")}
                           for p in rows][:50], default=str)
    return _audited("list_projects", _)


@mcp.tool()
def recent_lessons(limit: int = 8) -> str:
    """Recent lessons/insights from TOBI's self-reflection store."""
    def _():
        from core.database import get_all_lessons
        rows = (get_all_lessons() or [])[: int(limit)]
        return json.dumps([{"type": l.get("lesson_type"), "title": l.get("title"),
                            "content": (l.get("content") or "")[:200]} for l in rows], default=str)
    return _audited("recent_lessons", _)


# ── tools (sensitive → approval-gated, do NOT execute in-band) ─────────────
@mcp.tool()
def run_mission(objective: str) -> str:
    """Request TOBI to run a mission toward an objective. SENSITIVE — this does not
    run immediately; it creates an approval request the owner must approve in
    Mission Control before anything executes."""
    peer = _current_peer.get()
    aid = security.create_approval(peer, "run_mission", {"objective": objective})
    security.audit("in", peer=peer, tool="run_mission", status="pending")
    return (f"Request #{aid} is pending the owner's approval. The mission will not run "
            f"until approved in Mission Control.")


# ── resources ──────────────────────────────────────────────────────────────
@mcp.resource("tobi://status")
def status_resource() -> str:
    """Current Mission Control status as a resource."""
    return get_status()


@mcp.resource("tobi://brain/{query}")
def brain_resource(query: str) -> str:
    """TOBI's memory relevant to {query}."""
    return query_brain(query)


# ── prompts ────────────────────────────────────────────────────────────────
@mcp.prompt()
def daily_briefing() -> str:
    """A prompt template asking TOBI for a concise daily briefing."""
    return ("Give me a concise daily briefing: active projects, anything that needs my "
            "decision, and the single most important thing to focus on today.")


@mcp.prompt()
def ask_with_memory(topic: str) -> str:
    """A prompt template that asks TOBI about a topic using its long-term memory."""
    return f"Using everything you remember about me, help me with: {topic}"


# ── edge auth / rate-limit / scope ASGI middleware ─────────────────────────
class McpAuthMiddleware:
    """Bearer-token auth + per-client rate limit + per-tool scope enforcement,
    wrapping the FastMCP Streamable-HTTP ASGI app."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        headers = {k.decode().lower(): v.decode() for k, v in (scope.get("headers") or [])}
        client = security.resolve_inbound(headers.get("authorization"))  # issued token or OAuth JWT
        if client is None:
            await self._http_json(send, 401, {"error": "Missing or invalid MCP credential"})
            return
        if not security.rate_limit_ok(client["id"]):
            security.audit("in", peer=client["name"], status="rate_limited")
            await self._http_json(send, 429, {"error": "Rate limit exceeded"})
            return

        # Buffer the body so we can inspect the JSON-RPC method without consuming it.
        body, messages = b"", []
        while True:
            message = await receive()
            messages.append(message)
            if message["type"] == "http.request":
                body += message.get("body", b"")
                if not message.get("more_body", False):
                    break
            else:
                break

        rpc_id, tool = None, None
        try:
            data = json.loads(body) if body else {}
            if isinstance(data, dict) and data.get("method") == "tools/call":
                tool = (data.get("params") or {}).get("name")
                rpc_id = data.get("id")
        except Exception:
            pass

        if tool is not None and not security.client_allows(client, tool):
            security.audit("in", peer=client["name"], tool=tool, status="denied")
            await self._http_json(send, 200, {
                "jsonrpc": "2.0", "id": rpc_id,
                "error": {"code": -32001, "message": f"Tool '{tool}' is not in your allowed scope"},
            })
            return

        idx = {"i": 0}
        async def replay():
            if idx["i"] < len(messages):
                m = messages[idx["i"]]; idx["i"] += 1
                return m
            return await receive()

        token = _current_peer.set(client["name"])
        try:
            await self.app(scope, replay, send)
        finally:
            _current_peer.reset(token)

    @staticmethod
    async def _http_json(send, status: int, payload: dict):
        body = json.dumps(payload).encode()
        await send({"type": "http.response.start", "status": status,
                    "headers": [(b"content-type", b"application/json"),
                                (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})


# ── ASGI app + session lifecycle (mounted by the FastAPI app) ─────────────
_asgi = None
_session_cm = None


def asgi_app():
    """Build (once) the auth-wrapped Streamable-HTTP ASGI app to mount at /mcp."""
    global _asgi
    if _asgi is None:
        _asgi = McpAuthMiddleware(mcp.streamable_http_app())
    return _asgi


async def start_session() -> None:
    """Run the MCP session manager (call from the FastAPI startup event)."""
    global _session_cm
    asgi_app()  # ensures the session manager exists
    if _session_cm is None:
        _session_cm = mcp.session_manager.run()
        await _session_cm.__aenter__()


async def stop_session() -> None:
    global _session_cm
    if _session_cm is not None:
        try:
            await _session_cm.__aexit__(None, None, None)
        except Exception:
            pass
        _session_cm = None

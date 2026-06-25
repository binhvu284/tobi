"""MCP Hub — M4: A2A (Agent2Agent) interop.

Publishes TOBI's **agent card** (served at /.well-known/agent.json), and lets the
owner discover/add **peer** agents (by fetching their cards) and exchange basic
messages. A2A complements MCP: MCP = tools/resources, A2A = agent-to-agent.

This is a pragmatic subset — card publish + peer registry + best-effort
``message/send`` — with a clean module boundary so it can grow with the spec.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from core.database import get_connection

A2A_VERSION = "0.2"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── TOBI's own agent card ──────────────────────────────────────────────────
def _self_row() -> Optional[dict]:
    conn = get_connection()
    try:
        r = conn.execute("SELECT card_json FROM a2a_agents WHERE is_self=1 LIMIT 1").fetchone()
        return json.loads(r[0]) if r and r[0] else None
    except Exception:
        return None
    finally:
        conn.close()


def set_self_card(name: str | None = None, description: str | None = None, version: str | None = None) -> dict:
    base = _self_row() or {}
    base.update({k: v for k, v in {"name": name, "description": description, "version": version}.items() if v})
    conn = get_connection()
    try:
        row = conn.execute("SELECT id FROM a2a_agents WHERE is_self=1 LIMIT 1").fetchone()
        if row:
            conn.execute("UPDATE a2a_agents SET name=?, card_json=? WHERE id=?",
                         (base.get("name", "TOBI"), json.dumps(base), row[0]))
        else:
            conn.execute("INSERT INTO a2a_agents (name, card_json, endpoint, status, is_self) VALUES (?,?,?,?,1)",
                         (base.get("name", "TOBI"), json.dumps(base), None, "self"))
        conn.commit()
    finally:
        conn.close()
    return base


def get_self_card(public_url: str | None = None) -> dict:
    """Build the live agent card: stored identity + current skills (MCP tools) + URL."""
    cfg = _self_row() or {}
    skills = []
    try:
        from core import mcp_server
        for name in mcp_server.TOOL_NAMES:
            skills.append({"id": name, "name": name,
                           "description": f"TOBI MCP tool: {name}",
                           "tags": ["mcp", "tobi"]})
    except Exception:
        pass
    url = public_url or cfg.get("url") or ""
    return {
        "name": cfg.get("name", "TOBI"),
        "description": cfg.get("description", "TOBI — a personal Jarvis agent (Mission Control)."),
        "version": cfg.get("version", "1.0"),
        "url": url,
        "protocolVersion": A2A_VERSION,
        "capabilities": {"streaming": False, "pushNotifications": False},
        "defaultInputModes": ["text"],
        "defaultOutputModes": ["text"],
        "skills": skills,
    }


# ── peers ───────────────────────────────────────────────────────────────────
def list_peers() -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, name, endpoint, status, card_json FROM a2a_agents WHERE is_self=0 ORDER BY id").fetchall()
        out = []
        for r in rows:
            try:
                card = json.loads(r[4]) if r[4] else {}
            except Exception:
                card = {}
            out.append({"id": r[0], "name": r[1], "endpoint": r[2], "status": r[3],
                        "skills": [s.get("name") for s in card.get("skills", [])][:12]})
        return out
    finally:
        conn.close()


async def add_peer(url: str) -> dict:
    """Fetch a peer's agent card (…/.well-known/agent.json) and register it. Blocks on failure."""
    import httpx
    url = url.rstrip("/")
    candidates = [url] if url.endswith(".json") else [f"{url}/.well-known/agent.json", url]
    card, used = None, None
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as cx:
        last_err = None
        for u in candidates:
            try:
                r = await cx.get(u)
                r.raise_for_status()
                card = r.json()
                used = u
                break
            except Exception as e:
                last_err = e
        if card is None:
            raise RuntimeError(f"Could not fetch agent card: {last_err}")
    name = card.get("name") or "peer"
    endpoint = card.get("url") or url
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO a2a_agents (name, card_json, endpoint, status, is_self) VALUES (?,?,?,?,0)",
            (name, json.dumps(card), endpoint, "discovered"))
        conn.commit()
        pid = cur.lastrowid
    finally:
        conn.close()
    try:
        from core import mcp_security as security
        security.audit("out", peer=name, tool="a2a/discover", status="ok", response=f"card from {used}")
    except Exception:
        pass
    return {"id": pid, "name": name, "endpoint": endpoint,
            "skills": [s.get("name") for s in card.get("skills", [])]}


def remove_peer(peer_id: int) -> None:
    conn = get_connection()
    try:
        conn.execute("DELETE FROM a2a_agents WHERE id=? AND is_self=0", (peer_id,))
        conn.commit()
    finally:
        conn.close()


async def send_message(peer_id: int, text: str) -> dict:
    """Best-effort A2A message/send to a peer's endpoint."""
    conn = get_connection()
    try:
        r = conn.execute("SELECT name, endpoint FROM a2a_agents WHERE id=? AND is_self=0", (peer_id,)).fetchone()
    finally:
        conn.close()
    if not r:
        return {"ok": False, "error": "unknown peer"}
    name, endpoint = r[0], r[1]
    payload = {"jsonrpc": "2.0", "id": 1, "method": "message/send",
               "params": {"message": {"role": "user", "parts": [{"kind": "text", "text": text}]}}}
    try:
        import httpx
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as cx:
            resp = await cx.post(endpoint, json=payload)
        ok = resp.status_code < 400
        body = resp.text[:1000]
        try:
            from core import mcp_security as security
            security.audit("out", peer=name, tool="a2a/message", status="ok" if ok else "error",
                           request={"text": text[:200]}, response=body[:300])
        except Exception:
            pass
        return {"ok": ok, "status": resp.status_code, "response": body}
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}

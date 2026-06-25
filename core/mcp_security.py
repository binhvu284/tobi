"""MCP Hub — inbound security & audit (M1).

Token-based client auth (raw token shown once, only its SHA-256 hash stored),
per-client scopes (allowed tool names or ``["*"]``), in-memory per-client rate
limiting, an audit-log writer, and the human-in-the-loop approval queue for
sensitive tools. OAuth 2.1 is M4; this is the token path.
"""
from __future__ import annotations

import json
import time
import hashlib
import secrets as _secrets
from datetime import datetime, timezone
from typing import Optional

from core.database import get_connection

TOKEN_PREFIX = "tobi_mcp_"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# ── server config ─────────────────────────────────────────────────────────
def ensure_config() -> dict:
    conn = get_connection()
    try:
        conn.execute("INSERT OR IGNORE INTO mcp_server_config (id) VALUES (1)")
        conn.commit()
        row = conn.execute("SELECT * FROM mcp_server_config WHERE id=1").fetchone()
        return dict(row)
    finally:
        conn.close()


def get_config() -> dict:
    return ensure_config()


def set_config(**fields) -> dict:
    allowed = {"enabled", "transport", "public_url", "tunnel_status",
               "auth_modes_json", "rate_limit_json"}
    sets = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if sets:
        conn = get_connection()
        try:
            cols = ", ".join(f"{k}=?" for k in sets)
            conn.execute(f"UPDATE mcp_server_config SET {cols}, updated_at=? WHERE id=1",
                         (*sets.values(), _now()))
            conn.commit()
        finally:
            conn.close()
    return get_config()


def _per_minute() -> int:
    try:
        return int(json.loads(get_config().get("rate_limit_json") or "{}").get("per_minute", 60))
    except Exception:
        return 60


# ── inbound clients (token auth) ──────────────────────────────────────────
def issue_client(name: str, scopes: Optional[list[str]] = None) -> dict:
    """Create an inbound client and return its raw token ONCE (only the hash is stored)."""
    token = TOKEN_PREFIX + _secrets.token_urlsafe(32)
    scopes_json = json.dumps(scopes or ["*"])
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO mcp_clients (name, auth_type, token_hash, scopes_json, status, created_at) "
            "VALUES (?, 'token', ?, ?, 'active', ?)",
            (name.strip() or "client", _hash(token), scopes_json, _now()),
        )
        conn.commit()
        return {"id": cur.lastrowid, "name": name, "scopes": json.loads(scopes_json), "token": token}
    finally:
        conn.close()


def list_clients() -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, name, auth_type, scopes_json, status, created_at, last_seen "
            "FROM mcp_clients ORDER BY id DESC"
        ).fetchall()
        return [{"id": r[0], "name": r[1], "auth_type": r[2], "scopes": json.loads(r[3] or '["*"]'),
                 "status": r[4], "created_at": r[5], "last_seen": r[6]} for r in rows]
    finally:
        conn.close()


def set_client_scopes(client_id: int, scopes: list[str]) -> None:
    conn = get_connection()
    try:
        conn.execute("UPDATE mcp_clients SET scopes_json=? WHERE id=?", (json.dumps(scopes), client_id))
        conn.commit()
    finally:
        conn.close()


def revoke_client(client_id: int) -> None:
    conn = get_connection()
    try:
        conn.execute("UPDATE mcp_clients SET status='revoked' WHERE id=?", (client_id,))
        conn.commit()
    finally:
        conn.close()


def verify_token(token: Optional[str]) -> Optional[dict]:
    """Resolve a bearer token to an active client (and stamp last_seen). None if invalid."""
    if not token:
        return None
    token = token.strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id, name, scopes_json, status FROM mcp_clients WHERE token_hash=?",
            (_hash(token),),
        ).fetchone()
        if not row or row[3] != "active":
            return None
        conn.execute("UPDATE mcp_clients SET last_seen=? WHERE id=?", (_now(), row[0]))
        conn.commit()
        return {"id": row[0], "name": row[1], "scopes": json.loads(row[2] or '["*"]')}
    finally:
        conn.close()


def client_allows(client: dict, tool: str) -> bool:
    scopes = client.get("scopes") or ["*"]
    return "*" in scopes or tool in scopes


# ── OAuth 2.1 inbound (JWT access tokens) — M4 ─────────────────────────────
OAUTH_SECRET_REF = "MCP_OAUTH_SECRET"   # vault secret holding the HS256 signing key


def get_oauth_config() -> dict:
    cfg = get_config()
    try:
        return json.loads(cfg.get("oauth_json") or "{}") or {}
    except Exception:
        return {}


def set_oauth_config(*, enabled: bool, issuer: str | None = None, audience: str | None = None,
                     algorithm: str = "HS256", secret: str | None = None) -> dict:
    oc = {"enabled": bool(enabled), "issuer": issuer or None,
          "audience": audience or None, "alg": algorithm or "HS256"}
    conn = get_connection()
    try:
        conn.execute("UPDATE mcp_server_config SET oauth_json=?, updated_at=? WHERE id=1",
                     (json.dumps(oc), _now()))
        conn.commit()
    finally:
        conn.close()
    if secret:  # store the signing key in the Genesis vault, never inline
        try:
            from core import vault
            c2 = get_connection()
            try:
                vault.set_secret(c2, OAUTH_SECRET_REF, secret, secret_type="oauth", integration_id="mcp")
            finally:
                c2.close()
        except Exception:
            pass
    return oc


def _oauth_secret() -> str | None:
    try:
        from core import vault
        conn = get_connection()
        try:
            return vault.get_secret(conn, OAUTH_SECRET_REF)
        finally:
            conn.close()
    except Exception:
        return None


def verify_oauth(token: Optional[str]) -> Optional[dict]:
    """Validate an OAuth 2.1 JWT access token (when OAuth is enabled). Maps the
    token's `scope` claim to allowed tools. Returns a synthetic client or None."""
    if not token:
        return None
    token = token.strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    oc = get_oauth_config()
    if not oc.get("enabled"):
        return None
    secret = _oauth_secret()
    if not secret:
        return None
    try:
        import jwt
        claims = jwt.decode(
            token, secret, algorithms=[oc.get("alg", "HS256")],
            audience=oc.get("audience") or None, issuer=oc.get("issuer") or None,
            options={"verify_aud": bool(oc.get("audience"))},
        )
    except Exception:
        return None
    raw = claims.get("scope") or claims.get("scopes") or "*"
    scopes = raw.split() if isinstance(raw, str) else list(raw)
    return {"id": -1, "name": claims.get("sub") or claims.get("client_id") or "oauth-client",
            "scopes": scopes or ["*"], "auth": "oauth"}


def resolve_inbound(authorization: Optional[str]) -> Optional[dict]:
    """Resolve an inbound bearer credential: issued token first, then OAuth JWT."""
    return verify_token(authorization) or verify_oauth(authorization)


# ── rate limiting (in-memory token bucket per client) ─────────────────────
_buckets: dict[int, list[float]] = {}


def rate_limit_ok(client_id: int) -> bool:
    now = time.time()
    window = _buckets.setdefault(client_id, [])
    cutoff = now - 60.0
    window[:] = [t for t in window if t >= cutoff]
    if len(window) >= _per_minute():
        return False
    window.append(now)
    return True


# ── audit log ─────────────────────────────────────────────────────────────
def _trunc(obj, n: int = 2000) -> Optional[str]:
    if obj is None:
        return None
    try:
        s = obj if isinstance(obj, str) else json.dumps(obj, default=str)
    except Exception:
        s = str(obj)
    return s[:n]


def audit(direction: str, *, peer: str | None = None, tool: str | None = None,
          status: str | None = None, latency_ms: int | None = None,
          request=None, response=None, error: str | None = None) -> None:
    try:
        conn = get_connection()
        try:
            conn.execute(
                "INSERT INTO mcp_call_log (ts, direction, peer, tool, status, latency_ms, "
                "request_json, response_json, error) VALUES (?,?,?,?,?,?,?,?,?)",
                (_now(), direction, peer, tool, status, latency_ms,
                 _trunc(request), _trunc(response), (error or None) and str(error)[:500]),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass  # auditing must never break a call


def get_logs(limit: int = 100, direction: str | None = None) -> list[dict]:
    conn = get_connection()
    try:
        q = "SELECT id, ts, direction, peer, tool, status, latency_ms, error FROM mcp_call_log"
        params: tuple = ()
        if direction in ("in", "out"):
            q += " WHERE direction=?"
            params = (direction,)
        q += " ORDER BY id DESC LIMIT ?"
        rows = conn.execute(q, (*params, int(limit))).fetchall()
        return [{"id": r[0], "ts": r[1], "direction": r[2], "peer": r[3], "tool": r[4],
                 "status": r[5], "latency_ms": r[6], "error": r[7]} for r in rows]
    finally:
        conn.close()


# ── approval queue (human-in-the-loop for sensitive tools) ────────────────
def create_approval(client: str | None, tool: str, args: dict) -> int:
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO mcp_approvals (client, tool, args_json, status, created_at) "
            "VALUES (?,?,?,'pending',?)",
            (client, tool, _trunc(args), _now()),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def list_approvals(status: str | None = "pending") -> list[dict]:
    conn = get_connection()
    try:
        q = "SELECT id, client, tool, args_json, status, created_at, decided_at FROM mcp_approvals"
        params: tuple = ()
        if status:
            q += " WHERE status=?"
            params = (status,)
        q += " ORDER BY id DESC LIMIT 200"
        rows = conn.execute(q, params).fetchall()
        return [{"id": r[0], "client": r[1], "tool": r[2], "args": r[3], "status": r[4],
                 "created_at": r[5], "decided_at": r[6]} for r in rows]
    finally:
        conn.close()


def decide_approval(approval_id: int, approved: bool) -> dict:
    conn = get_connection()
    try:
        conn.execute("UPDATE mcp_approvals SET status=?, decided_at=? WHERE id=?",
                     ("approved" if approved else "rejected", _now(), approval_id))
        conn.commit()
        row = conn.execute("SELECT id, status FROM mcp_approvals WHERE id=?", (approval_id,)).fetchone()
        return {"id": row[0], "status": row[1]} if row else {"id": approval_id, "status": "unknown"}
    finally:
        conn.close()

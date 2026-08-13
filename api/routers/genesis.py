"""Genesis vault + integrations + Google OAuth API.

Routes: /api/vault/*, /api/integrations/* (incl. /api/integrations/google/oauth/*).
Extracted from api/dashboard.py (refactor Slice — pre-#21 decomposition). Byte-
identical: 9 vault/integration request models + _genesis_status/_integration_view
helpers + vault lifecycle + integrations catalog + Google OAuth2 routes; only
@app.* -> @router.*. _get_conn/_vault_guard come from api.deps. See REFACTORING_PLAN.
Free-var set verified by isolated-pyflakes analysis (not grep).
"""
from __future__ import annotations

import asyncio
import os  # noqa: F401 - used by some handlers
import sqlite3  # noqa: F401 - used in type hints

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel

from api.deps import _get_conn, _vault_guard
from api.routers.mcp import MCP_AVAILABLE, mcp_a2a, mcp_tunnel  # canonical MCP boot probe
from core import integrations_registry as registry
from core import mcp_security as mcpsec
from core import vault
from core.awakening_detect import _ABILITY_NAMES, _TIER_DEFINITIONS, _detect_abilities

router = APIRouter(tags=["genesis"])


# ── Genesis Complete: encrypted secrets vault + integrations manager ────────────
# The dashboard has no API-key auth (local-only), so the master-password session
# token IS the security gate for vault writes/reveals. Secret values are never
# returned by list/status — only `last4` + metadata.

class VaultSetupReq(BaseModel):
    master: str
    import_env: bool = True


class VaultUnlockReq(BaseModel):
    master: str


class VaultAutoUnlockReq(BaseModel):
    enabled: bool = True


class VaultPasswordReq(BaseModel):
    password: str


class VaultImportReq(BaseModel):
    blob: str
    password: str


class VaultProfileReq(BaseModel):
    name: str
    label: str | None = None
    activate: bool = True


class IntegrationConnectReq(BaseModel):
    fields: dict[str, str]


class CustomSecretReq(BaseModel):
    name: str
    value: str
    secret_type: str = "custom"


class RevealReq(BaseModel):
    name: str
    master: str




def _genesis_status(conn: sqlite3.Connection) -> dict:
    """Live Genesis (Tier 0) completion from the real ability detector."""
    statuses = _detect_abilities(conn)
    ids = [ab["id"] for pillar in _TIER_DEFINITIONS[0]["pillars"].values() for ab in pillar]
    active = sum(1 for i in ids if statuses.get(i))
    return {
        "abilities": {i: bool(statuses.get(i)) for i in ids},
        "active": active, "total": len(ids),
        "pct": round(active / len(ids) * 100) if ids else 0,
        "complete": active == len(ids) and len(ids) > 0,
    }


def _integration_view(conn: sqlite3.Connection) -> list[dict]:
    statuses = _detect_abilities(conn)
    secrets = {s["name"]: s for s in vault.list_secrets(conn)}
    out: list[dict] = []
    for item in registry.REGISTRY:
        fields_out, any_set = [], False
        for f in item["fields"]:
            s = secrets.get(f["name"])
            if s:
                any_set = True
            fields_out.append({
                "name": f["name"], "label": f["label"], "type": f["type"],
                "help_url": f.get("help_url"),
                "set": bool(s), "last4": s["last4"] if s else None,
                "test_status": s["test_status"] if s else None,
            })
        out.append({
            "id": item["id"], "label": item["label"], "category": item["category"],
            "required": item["required"], "available": item.get("available", True),
            "icon": item.get("icon"), "blurb": item.get("blurb"), "coming_in": item.get("coming_in"),
            "fields": fields_out, "connected": any_set,
            "abilities": [
                {"id": a, "name": _ABILITY_NAMES.get(a, a), "active": bool(statuses.get(a))}
                for a in item["abilities_unlocked"]
            ],
        })
    return out


# ── Vault lifecycle ──
@router.get("/api/vault/status")
async def vault_status():
    conn = _get_conn()
    try:
        return vault.status(conn)
    finally:
        conn.close()


@router.post("/api/vault/setup")
async def vault_setup(body: VaultSetupReq):
    conn = _get_conn()
    try:
        token = vault.setup(conn, body.master, import_env=body.import_env)
        return {"ok": True, "session": token, "status": vault.status(conn), "genesis": _genesis_status(conn)}
    except vault.VaultError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()


@router.post("/api/vault/unlock")
async def vault_unlock(body: VaultUnlockReq):
    conn = _get_conn()
    try:
        token = vault.unlock(conn, body.master)
        injected = vault.inject_env(conn)
        return {"ok": True, "session": token, "injected": injected,
                "status": vault.status(conn), "genesis": _genesis_status(conn)}
    except vault.VaultError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()


@router.post("/api/vault/lock")
async def vault_lock(x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    # no hard guard — locking is always safe; just clear the in-memory key
    vault.lock()
    return {"ok": True}


@router.post("/api/vault/reload")
async def vault_reload(x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    _vault_guard(x_vault_session)
    conn = _get_conn()
    try:
        n = vault.reload(conn)
        return {"ok": True, "injected": n, "genesis": _genesis_status(conn)}
    finally:
        conn.close()


@router.post("/api/vault/autounlock")
async def vault_autounlock(body: VaultAutoUnlockReq,
                           x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    """Toggle startup auto-connect. Enabling caches the current key (requires an
    unlocked session); disabling forgets it so a password is needed again on boot."""
    _vault_guard(x_vault_session)
    conn = _get_conn()
    try:
        if body.enabled:
            ok = vault.enable_autounlock(conn)
        else:
            vault.disable_autounlock(conn)
            ok = True
        return {"ok": ok, "autounlock": vault.autounlock_enabled(conn)}
    finally:
        conn.close()


# Public discovery metadata (no auth — non-secret; external agents/clients fetch these).
@router.get("/.well-known/agent.json")
async def well_known_agent():
    if not MCP_AVAILABLE:
        raise HTTPException(status_code=404, detail="A2A not available")
    pub = mcp_tunnel.status().get("public_url") or str(app_base_url())
    return mcp_a2a.get_self_card(pub)


@router.get("/.well-known/oauth-protected-resource")
async def well_known_oauth():
    if not MCP_AVAILABLE:
        raise HTTPException(status_code=404, detail="OAuth not configured")
    oc = mcpsec.get_oauth_config()
    pub = mcp_tunnel.status().get("public_url") or str(app_base_url())
    meta = {"resource": f"{pub}/mcp"}
    if oc.get("enabled") and oc.get("issuer"):
        meta["authorization_servers"] = [oc["issuer"]]
    return meta


def app_base_url() -> str:
    port = os.getenv("DASHBOARD_PORT", "8080")
    return f"http://localhost:{port}"


@router.get("/api/vault/audit")
async def vault_audit(limit: int = Query(100), x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    _vault_guard(x_vault_session)
    conn = _get_conn()
    try:
        return {"entries": vault.get_audit(conn, limit)}
    finally:
        conn.close()


@router.post("/api/vault/export")
async def vault_export(body: VaultPasswordReq, x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    _vault_guard(x_vault_session)
    conn = _get_conn()
    try:
        return {"ok": True, "blob": vault.export_blob(conn, body.password)}
    except vault.VaultError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()


@router.post("/api/vault/import")
async def vault_import(body: VaultImportReq, x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    _vault_guard(x_vault_session)
    conn = _get_conn()
    try:
        n = vault.import_blob(conn, body.blob, body.password)
        vault.inject_env(conn)
        return {"ok": True, "imported": n, "genesis": _genesis_status(conn)}
    except vault.VaultError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()


@router.get("/api/vault/profiles")
async def vault_profiles():
    conn = _get_conn()
    try:
        return {"profiles": vault.list_profiles(conn), "active": vault.active_profile(conn)}
    finally:
        conn.close()


@router.post("/api/vault/profiles")
async def vault_create_profile(body: VaultProfileReq, x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    _vault_guard(x_vault_session)
    conn = _get_conn()
    try:
        vault.create_profile(conn, body.name, body.label)
        if body.activate:
            vault.set_active_profile(conn, body.name)
        return {"ok": True, "profiles": vault.list_profiles(conn), "active": vault.active_profile(conn)}
    except vault.VaultError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()


# ── Integrations catalog + connect/test/reveal/remove ──
@router.get("/api/integrations")
async def list_integrations():
    conn = _get_conn()
    try:
        return {
            "integrations": _integration_view(conn),
            "genesis": _genesis_status(conn),
            "vault": vault.status(conn),
        }
    finally:
        conn.close()


@router.post("/api/integrations/{integration_id}/connect")
async def connect_integration(integration_id: str, body: IntegrationConnectReq,
                              x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    _vault_guard(x_vault_session)
    item = registry.get(integration_id)
    if not item or not item.get("available", True):
        raise HTTPException(status_code=404, detail="Unknown or unavailable integration.")
    values = {k: v for k, v in (body.fields or {}).items() if v and v.strip()}
    if not values:
        raise HTTPException(status_code=400, detail="Provide at least one value.")

    conn = _get_conn()
    try:
        names = [f["name"] for f in item["fields"]]
        snapshot = {n: os.environ.get(n) for n in names}
        for n, v in values.items():
            os.environ[n] = v
        ok, msg = registry.test_integration(integration_id)
        verified = bool(ok and registry.test_confirms_read_access(integration_id))
        vault._audit(conn, "test", integration_id=integration_id, ok=ok, detail=msg)
        if not ok:
            for n, old in snapshot.items():  # block: don't persist a bad key
                if old is None:
                    os.environ.pop(n, None)
                else:
                    os.environ[n] = old
            raise HTTPException(status_code=400, detail=msg)
        for f in item["fields"]:
            if f["name"] in values:
                vault.set_secret(conn, f["name"], values[f["name"]], integration_id=integration_id,
                                 secret_type=f["type"], test_status="ok" if verified else "untested")
        return {"ok": True, "message": msg, "genesis": _genesis_status(conn),
                "integrations": _integration_view(conn), "verified": verified}
    finally:
        conn.close()


@router.post("/api/integrations/{integration_id}/test")
async def test_integration_endpoint(integration_id: str,
                                    x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    _vault_guard(x_vault_session)
    item = registry.get(integration_id)
    if not item:
        raise HTTPException(status_code=404, detail="Unknown integration.")
    conn = _get_conn()
    try:
        vault.inject_env(conn)  # ensure current vault values are live
        ok, msg = registry.test_integration(integration_id)
        verified = bool(ok and registry.test_confirms_read_access(integration_id))
        status = "ok" if verified else ("failed" if not ok else "untested")
        for f in item["fields"]:
            try:
                vault.mark_test_status(conn, f["name"], status)
            except Exception:
                pass
        vault._audit(conn, "test", integration_id=integration_id, ok=ok, detail=msg)
        return {"ok": ok, "verified": verified, "message": msg, "genesis": _genesis_status(conn)}
    finally:
        conn.close()


@router.post("/api/integrations/reveal")
async def reveal_secret(body: RevealReq, x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    _vault_guard(x_vault_session)
    conn = _get_conn()
    try:
        return {"ok": True, "name": body.name, "value": vault.reveal(conn, body.name, body.master)}
    except vault.VaultError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()


@router.post("/api/integrations/custom")
async def add_custom_secret(body: CustomSecretReq,
                            x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    _vault_guard(x_vault_session)
    name = body.name.strip().upper().replace(" ", "_")
    if not name:
        raise HTTPException(status_code=400, detail="Secret name is required.")
    conn = _get_conn()
    try:
        vault.set_secret(conn, name, body.value, integration_id="custom", secret_type=body.secret_type)
        os.environ[name] = body.value
        return {"ok": True, "genesis": _genesis_status(conn)}
    except vault.VaultError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()


@router.delete("/api/integrations/{integration_id}")
async def remove_integration(integration_id: str,
                             x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    _vault_guard(x_vault_session)
    item = registry.get(integration_id)
    if not item:
        raise HTTPException(status_code=404, detail="Unknown integration.")
    conn = _get_conn()
    try:
        for f in item["fields"]:
            vault.delete_secret(conn, f["name"], integration_id=integration_id)
        return {"ok": True, "genesis": _genesis_status(conn), "integrations": _integration_view(conn)}
    finally:
        conn.close()


# ── Google OAuth2 flow ─────────────────────────────────────────────────────────

def _google_redirect_uri(request: Request) -> str:
    """Build the OAuth redirect URI from the live request, respecting proxy headers."""
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host") or request.headers.get("host", "localhost")
    return f"{scheme}://{host}/api/integrations/google/oauth/callback"


@router.get("/api/integrations/google/oauth/start")
async def google_oauth_start(request: Request):
    """Redirect the browser to Google's consent screen."""
    from core.integrations import GoogleIntegration
    g = GoogleIntegration()
    if not g.is_available():
        raise HTTPException(status_code=400, detail="Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET first.")
    g.redirect_uri = _google_redirect_uri(request)
    return RedirectResponse(url=g.get_auth_url())


@router.get("/api/integrations/google/oauth/callback")
async def google_oauth_callback(request: Request, code: str | None = None, error: str | None = None):
    """Handle the OAuth redirect — exchange code for tokens, save them."""
    from core.integrations import GoogleIntegration
    if error:
        return HTMLResponse(content=f"<script>window.close();</script>"
                            f"<body>Authorization denied: {error}</body>", status_code=200)
    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code.")
    g = GoogleIntegration()
    if not g.is_available():
        raise HTTPException(status_code=400, detail="Google credentials not configured.")
    g.redirect_uri = _google_redirect_uri(request)
    result = g.exchange_code(code)
    if result.get("error"):
        raise HTTPException(status_code=400, detail=f"OAuth exchange failed: {result['error'][:300]}")
    ok, msg = registry.test_integration("google")
    verified = bool(ok and registry.test_confirms_read_access("google"))
    conn = _get_conn()
    try:
        item = registry.get("google") or {}
        for field in item.get("fields", []):
            vault.mark_test_status(conn, field["name"], "ok" if verified else "failed")
        vault._audit(conn, "test", integration_id="google", ok=verified, detail=msg)
    finally:
        conn.close()
    if not verified:
        raise HTTPException(status_code=400, detail="Google authorization completed but read access could not be verified.")
    # Close the popup — the Integrations page polls status and will refresh.
    return HTMLResponse(content="""<!DOCTYPE html><html><body>
    <h3 style="font-family:sans-serif;text-align:center;margin-top:40px">
    Google connected — you can close this tab.</h3>
    <script>setTimeout(()=>window.close(),2000);</script>
    </body></html>""")


@router.get("/api/integrations/google/status")
async def google_oauth_status(request: Request):
    """Return Google connection status (connected? email? scopes?)."""
    from core.integrations import GoogleIntegration
    g = GoogleIntegration()
    connected = g.is_connected()
    email = ""
    if connected:
        # Ran inline until 2026-08-13. `requests` is synchronous, so inside this async handler
        # it held the event loop for up to its full 10s timeout — every other request in flight
        # waited on Google answering, for a field that only decorates this response. On a
        # worker thread, and the email is optional: a slow or failing lookup leaves it blank
        # rather than delaying the connection status the page actually needs.
        def _fetch_email() -> str:
            import requests
            token = g._get_valid_access_token()
            if not token:
                return ""
            r = requests.get(g.USERINFO_URL,
                             headers={"Authorization": f"Bearer {token}"}, timeout=(3, 5))
            return r.json().get("email", "") if r.status_code == 200 else ""

        try:
            email = await asyncio.wait_for(asyncio.to_thread(_fetch_email), timeout=6)
        except Exception:  # noqa: BLE001 - the address is decoration; status is the answer
            email = ""
    return {
        "configured": g.is_available(),
        "connected": connected,
        "email": email,
        "redirect_uri": _google_redirect_uri(request),
    }


@router.post("/api/integrations/google/disconnect")
async def google_disconnect(x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    """Revoke Google tokens and delete the local token file."""
    _vault_guard(x_vault_session)
    from core.integrations import GoogleIntegration
    g = GoogleIntegration()
    ok = g.revoke()
    return {"ok": ok}

"""LLM usage + model-routing config — /api/llm/* (#8/#10).

Extracted from api/dashboard.py (refactor Slice — pre-#21 decomposition). Byte-
identical handlers; only @app.* -> @router.*, with _get_conn/_vault_guard imported
from api.deps. See docs/REFACTORING_PLAN.md.
"""
from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from api.deps import _get_conn, _vault_guard
from core import vault

router = APIRouter(tags=["llm"])


class LlmConfigReq(BaseModel):
    config: dict


class LlmKeyReq(BaseModel):
    value: str


@router.get("/api/llm/usage")
def llm_usage(days: int = 7):
    """Weekly token/cost/latency analytics from real per-call logging (Models page + Health)."""
    from core import usage
    return usage.summary(days=max(1, min(days, 90)))


@router.get("/api/llm/usage/recent")
def llm_usage_recent(limit: int = 50):
    from core import usage
    return {"calls": usage.recent(limit=limit)}


@router.get("/api/llm/config")
def llm_config_get():
    """Routing config + provider catalog (key-presence, base_urls, models) + the flat
    'provider:model' picker list. Non-secret — no vault session required to read."""
    from core import model_router
    return {
        "config": model_router.load_llm_config(),
        "providers": model_router.provider_catalog(),
        "models": model_router.available_models(),
        "routing": model_router.routing_status(),
    }


@router.get("/api/llm/models")
def llm_models():
    from core import model_router
    return {"models": model_router.available_models()}


@router.post("/api/llm/config")
def llm_config_save(body: LlmConfigReq):
    """Save routing prefs (default + per-task + fallback + provider base_urls/models) and
    **push to Hermes** (best-effort, never fails the save)."""
    from core import model_router, hermes_sync
    cfg = model_router.save_llm_config(body.config or {})
    try:
        hermes = hermes_sync.push_config(cfg)
    except Exception as e:  # never let a Hermes hiccup break the save
        hermes = {"ok": False, "detail": f"Hermes push skipped: {str(e)[:120]}"}
    return {"config": cfg, "providers": model_router.provider_catalog(),
            "models": model_router.available_models(),
            "routing": model_router.routing_status(cfg), "hermes": hermes}


@router.post("/api/llm/provider/{pid}/key")
def llm_provider_key(pid: str, body: LlmKeyReq,
                     x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    """Store a provider's API key in the Genesis vault (encrypted) and inject it live.
    Routed through the key-slot system so it appears in the multi-key list too."""
    _vault_guard(x_vault_session)
    from core import model_router
    spec = model_router.PROVIDERS.get(pid)
    if not spec or not spec.get("key_env"):
        raise HTTPException(status_code=400, detail="provider has no API key")
    conn = _get_conn()
    try:
        vault.add_key_slot(conn, spec["key_env"], body.value, activate=True)
    finally:
        conn.close()
    return {"ok": True, "providers": model_router.provider_catalog(),
            "models": model_router.available_models()}


@router.post("/api/llm/discover/{pid}")
def llm_discover(pid: str):
    from core import model_router
    if pid not in model_router.PROVIDERS:
        raise HTTPException(status_code=404, detail="unknown provider")
    return model_router.discover_models(pid)


@router.post("/api/llm/hermes-push")
def llm_hermes_push():
    from core import hermes_sync, model_router
    return hermes_sync.push_config(model_router.load_llm_config())

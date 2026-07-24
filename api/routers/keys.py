"""Multi-key vault slots — /api/keys/* (several accounts per secret, one active).

Extracted from api/dashboard.py (refactor Slice — pre-#21 decomposition). Byte-
identical handlers; only @app.* -> @router.*, with _get_conn/_vault_guard imported
from api.deps. See docs/REFACTORING_PLAN.md.
"""
from __future__ import annotations

import re

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from api.deps import _get_conn, _vault_guard
from core import vault

router = APIRouter(tags=["keys"])

# multi-key slots: several accounts per provider/secret, one active at a time
_KEY_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class KeySlotAddReq(BaseModel):
    value: str
    label: str | None = None
    activate: bool = False


class KeySlotLabelReq(BaseModel):
    label: str


def _key_name_or_400(name: str) -> str:
    name = (name or "").strip()
    if not _KEY_NAME_RE.match(name):
        raise HTTPException(status_code=400, detail="invalid secret name")
    return name


def _slots_payload(conn, name: str) -> dict:
    from core import model_router
    return {"ok": True, "name": name, "slots": vault.list_key_slots(conn, name),
            "providers": model_router.provider_catalog(),
            "models": model_router.available_models()}


@router.get("/api/keys/{name}")
def key_slots_list(name: str, x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    """All stored keys for a secret (metadata + which one is active). Vault-gated."""
    _vault_guard(x_vault_session)
    name = _key_name_or_400(name)
    conn = _get_conn()
    try:
        return _slots_payload(conn, name)
    finally:
        conn.close()


@router.post("/api/keys/{name}")
def key_slots_add(name: str, body: KeySlotAddReq,
                  x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    """Add another key (e.g. a second z.ai account). First key auto-activates."""
    _vault_guard(x_vault_session)
    name = _key_name_or_400(name)
    if not (body.value or "").strip():
        raise HTTPException(status_code=400, detail="value is required")
    conn = _get_conn()
    try:
        vault.add_key_slot(conn, name, body.value.strip(), label=body.label, activate=body.activate)
        return _slots_payload(conn, name)
    finally:
        conn.close()


@router.post("/api/keys/{name}/activate")
def key_slots_activate(name: str, body: KeySlotLabelReq,
                       x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    """Switch the provider to this account (one active at a time) — live, no restart."""
    _vault_guard(x_vault_session)
    name = _key_name_or_400(name)
    conn = _get_conn()
    try:
        try:
            vault.activate_key_slot(conn, name, body.label)
        except vault.VaultError as e:
            raise HTTPException(status_code=404, detail=str(e))
        return _slots_payload(conn, name)
    finally:
        conn.close()


@router.post("/api/keys/{name}/deactivate")
def key_slots_deactivate(name: str, x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    """Toggle the active key OFF (keeps it stored) — the provider reads disconnected."""
    _vault_guard(x_vault_session)
    name = _key_name_or_400(name)
    conn = _get_conn()
    try:
        vault.deactivate_key_slots(conn, name)
        return _slots_payload(conn, name)
    finally:
        conn.close()


@router.post("/api/keys/{name}/delete")
def key_slots_delete(name: str, body: KeySlotLabelReq,
                     x_vault_session: str | None = Header(None, alias="X-Vault-Session")):
    """Remove a stored key. Deleting the active one promotes the next remaining slot."""
    _vault_guard(x_vault_session)
    name = _key_name_or_400(name)
    conn = _get_conn()
    try:
        vault.delete_key_slot(conn, name, body.label)
        return _slots_payload(conn, name)
    finally:
        conn.close()

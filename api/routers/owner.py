"""Owner settings routes — /api/owner/* .

Extracted from api/dashboard.py (refactor Slice — pre-#21 decomposition). Byte-
identical handlers; only @app.* -> @router.* and _get_conn imported from api.deps.
See docs/REFACTORING_PLAN.md.
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from api.deps import _get_conn

router = APIRouter(tags=["owner"])


class OwnerSettingsPatchRequest(BaseModel):
    timezone: str | None = None


@router.get("/api/owner/settings")
async def get_owner_settings():
    conn = _get_conn()
    try:
        rows = conn.execute("SELECT key, value FROM owner_settings").fetchall()
        return {r["key"]: r["value"] for r in rows}
    finally:
        conn.close()


@router.patch("/api/owner/settings")
async def patch_owner_settings(payload: OwnerSettingsPatchRequest):
    conn = _get_conn()
    try:
        if payload.timezone is not None:
            conn.execute(
                "INSERT OR REPLACE INTO owner_settings (key, value, updated_at) VALUES ('timezone', ?, CURRENT_TIMESTAMP)",
                (payload.timezone,),
            )
        conn.commit()
        rows = conn.execute("SELECT key, value FROM owner_settings").fetchall()
        return {r["key"]: r["value"] for r in rows}
    finally:
        conn.close()

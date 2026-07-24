"""Conductor status / actions / confirm routes — /api/conductor/* (#7).

Extracted from api/dashboard.py (refactor Slice — pre-#21 decomposition). Byte-
identical handlers; only @app.* -> @router.*. See docs/REFACTORING_PLAN.md.
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["conductor"])


@router.get("/api/conductor/status")
def conductor_status():
    """The Conductor's exposed read/act tools + phase (queue #7)."""
    from core import conductor
    return conductor.conductor_status()


@router.get("/api/conductor/actions")
def conductor_actions(limit: int = 50):
    """The TOBI Actions audit log — what the Conductor did/proposed, when, and the result."""
    from core import conductor
    return conductor.list_actions(limit=max(1, min(limit, 200)))


class ConductorConfirmReq(BaseModel):
    action_id: int
    decision: str = "approve"   # approve | reject


@router.post("/api/conductor/confirm")
def conductor_confirm(payload: ConductorConfirmReq):
    """Approve or reject a proposed high-risk Conductor action (the confirm button)."""
    from core import conductor
    return conductor.confirm_action(payload.action_id, payload.decision, surface="mc")

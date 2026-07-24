"""TOBI CLI / terminal-engine routes — /api/terminal/* (#11).

Extracted from api/dashboard.py (refactor Slice — pre-#21 decomposition). Byte-
identical handlers; only @app.* -> @router.*. See docs/REFACTORING_PLAN.md.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(tags=["terminal"])


class TerminalModeReq(BaseModel):
    mode: str                     # plan | ask | accept | auto


class TerminalKillSwitchReq(BaseModel):
    enabled: bool


@router.get("/api/terminal/status")
def terminal_status():
    """Approval mode, kill-switch, OS/shell, package managers, and registered tools (#11)."""
    from core import terminal_engine as te
    return te.status()


@router.post("/api/terminal/mode")
def terminal_set_mode(payload: TerminalModeReq):
    """Switch the terminal approval mode: plan | ask | accept | auto [D17]."""
    from core import terminal_engine as te
    try:
        return {"ok": True, "mode": te.set_mode(payload.mode)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/api/terminal/killswitch")
def terminal_killswitch(payload: TerminalKillSwitchReq):
    """Global kill-switch — freeze/unfreeze all terminal execution instantly [D25]."""
    from core import terminal_engine as te
    return {"ok": True, "enabled": te.set_enabled(payload.enabled)}


@router.get("/api/terminal/jobs")
def terminal_jobs(limit: int = 20):
    """Background-job registry [D11]."""
    from core import terminal_engine as te
    return te.list_jobs(limit=limit)


@router.get("/api/terminal/jobs/{job_id}")
def terminal_job(job_id: int):
    from core import terminal_engine as te
    return te.get_job(job_id)


@router.post("/api/terminal/jobs/{job_id}/kill")
def terminal_job_kill(job_id: int):
    from core import terminal_engine as te
    return te.kill_job(job_id)


@router.get("/api/terminal/tools")
def terminal_tools():
    """The capability registry: tools TOBI has installed/configured/connected [D15]."""
    from core import terminal_engine as te
    return te.list_tools()

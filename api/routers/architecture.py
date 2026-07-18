"""Architecture V2 routes — /api/architecture/* .

Extracted from api/dashboard.py (refactor Slice). Handlers are byte-identical;
only the route decorators were rebound to this group's router. See
docs/REFACTORING_PLAN.md.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(tags=["architecture"])


class ArchitectureConfigReq(BaseModel):
    v2_enabled: Optional[bool] = None


@router.get("/api/architecture/diagrams")
def api_architecture_diagrams():
    """List the canonical architecture diagrams (allowlisted ids + titles). Never raises."""
    from core import architecture_docs
    return architecture_docs.list_diagrams()


@router.get("/api/architecture/diagrams/{diagram_id}")
def api_architecture_diagram(diagram_id: str):
    """One diagram's validated Mermaid content + guide. Unknown id → 404. Invalid content is
    returned as valid:false with empty content (the page shows a failure panel, never raw)."""
    from core import architecture_docs
    data = architecture_docs.get_diagram(diagram_id)
    if data is None:
        raise HTTPException(status_code=404, detail="unknown diagram")
    return data


@router.get("/api/architecture/diagrams/{diagram_id}/history")
def api_architecture_history(diagram_id: str, limit: int = 10):
    """Recent git commits that touched this diagram. Unknown id → 404; non-git checkout →
    available:false (never a 500)."""
    from core import architecture_docs
    data = architecture_docs.history(diagram_id, limit)
    if data is None:
        raise HTTPException(status_code=404, detail="unknown diagram")
    return data


@router.get("/api/architecture/diagrams/{diagram_id}/versions/{sha}")
def api_architecture_version(diagram_id: str, sha: str):
    """A historical version's validated content. Unknown id, non-allowlisted/invalid sha, or
    content that fails validation → 404 (never interpolate an unvetted ref into git)."""
    from core import architecture_docs
    data = architecture_docs.version(diagram_id, sha)
    if data is None:
        raise HTTPException(status_code=404, detail="unknown diagram version")
    return data


@router.post("/api/architecture/update")
def api_architecture_update():
    """Sync architecture from GitHub: git fetch origin main (read-only, no working-tree mutation),
    so history() surfaces the newest committed versions. Returns {ok, fetched, changed}."""
    from core import architecture_docs
    return architecture_docs.sync()


@router.get("/api/architecture/config")
def api_architecture_config_get():
    from core import owner_flags
    return {"v2_enabled": owner_flags.get_bool(owner_flags.ARCHITECTURE_V2_ENABLED, False)}


@router.post("/api/architecture/config")
def api_architecture_config_set(body: ArchitectureConfigReq):
    from core import owner_flags
    if body.v2_enabled is not None:
        owner_flags.set_bool(owner_flags.ARCHITECTURE_V2_ENABLED, bool(body.v2_enabled))
    return {"v2_enabled": owner_flags.get_bool(owner_flags.ARCHITECTURE_V2_ENABLED, False)}

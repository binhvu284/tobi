"""Explore / news routes — /api/explore/* .

Extracted from api/dashboard.py (refactor Slice). Byte-identical handlers;
only @router.* -> @router.*. See docs/REFACTORING_PLAN.md.
"""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

router = APIRouter(tags=["explore"])


class ExploreConfigReq(BaseModel):
    updates: dict = Field(default_factory=dict)


class ExploreSourceToggleReq(BaseModel):
    enabled: bool
    weight: float | None = None


class ExploreRefreshReq(BaseModel):
    pillar: str = "all"  # models | tools | social | news | all


@router.get("/api/explore/status")
def explore_status():
    from core import explore
    return explore.status()


@router.get("/api/explore/news")
def explore_news(limit: int = 20):
    from core import explore
    return explore.news_payload(limit)


@router.get("/api/explore/models")
def explore_models(limit: int = 60):
    from core import explore
    return explore.models_payload(limit)


@router.get("/api/explore/tools")
def explore_tools(limit: int = 40):
    from core import explore
    return explore.tools_payload(limit)


@router.get("/api/explore/social")
def explore_social(limit: int = 40):
    from core import explore
    return explore.social_payload(limit)


@router.post("/api/explore/refresh")
def explore_refresh(body: ExploreRefreshReq):
    from core import explore
    pillar = (body.pillar or "all").strip()
    results = {}
    if pillar in ("news", "all"):
        results["news"] = explore.refresh("news")
    if pillar in ("tools", "all"):
        results["tools"] = explore.refresh("tools")
    if pillar in ("social", "all"):
        results["social"] = explore.refresh("social")
    if pillar in ("models", "all"):
        results["models"] = explore.refresh_models()
    return {"ok": True, "results": results, "status": explore.status()}


@router.post("/api/explore/refresh/stream")
def explore_refresh_stream(pillar: str = "all"):
    """SSE scout stream — yields real per-step progress (fetch/summarize/score/done)
    per pillar so the UI can show a progress bar + live log. Mirrors the chat SSE."""
    from core import explore

    def gen():
        order = ["models", "news", "tools", "social"] if pillar == "all" else [pillar]
        # multi-pillar: weight each pillar equally in the overall bar
        try:
            yield f": stream open\n\n"
            for idx, p in enumerate(order):
                yield f"event: pillar\ndata: {json.dumps({'pillar': p, 'index': idx, 'total': len(order)})}\n\n"
                it = explore.refresh_models_iter() if p == "models" else explore.refresh_iter(p)
                for ev in it:
                    ev["pillar"] = p
                    yield f"event: {ev.get('phase', 'progress')}\ndata: {json.dumps(ev)}\n\n"
            yield f"event: complete\ndata: {json.dumps({'status': explore.status()})}\n\n"
        except Exception as e:  # never let an exception kill the stream silently
            yield f"event: error\ndata: {json.dumps({'detail': str(e)[:200]})}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/api/explore/config")
def explore_config_get():
    from core import explore
    return {"config": explore.load_config(), "sources": explore._sources_view()}


@router.post("/api/explore/config")
def explore_config_save(body: ExploreConfigReq):
    from core import explore
    cfg = explore.save_config(body.updates or {})
    return {"ok": True, "config": cfg, "sources": explore._sources_view()}


@router.post("/api/explore/sources/{name}")
def explore_source_set(name: str, body: ExploreSourceToggleReq):
    from core import explore
    explore.set_source_enabled(name, body.enabled)
    if body.weight is not None:
        explore.set_source_weight(name, body.weight)
    return {"ok": True, "sources": explore._sources_view()}


@router.post("/api/explore/digest")
def explore_digest(days: int = 1):
    """Editorial "TOBI's take" digest — surfaced on-request via Conductor #7."""
    from core import explore
    return {"text": explore.digest(days)}


"""Usage analytics + plan/budget routes — /api/usage/* .

Extracted from api/dashboard.py (refactor Slice). Handlers byte-identical;
route decorators rebound to this group's router. See docs/REFACTORING_PLAN.md.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(tags=["usage"])


class UsagePlansReq(BaseModel):
    plans: list[dict] = Field(default_factory=list)


class UsageBudgetReq(BaseModel):
    monthly_cap_usd: float = 0.0
    alert_pct: int = 80


@router.get("/api/usage/overview")
def usage_overview(range: str = "month"):
    """Cost/tokens/requests/latency by provider·model·surface·agent + daily trend [S15][S19]."""
    from core import usage_meter
    if range not in usage_meter.RANGES:
        raise HTTPException(400, "range must be day | week | month | all")
    return usage_meter.overview(range)


@router.get("/api/usage/calls")
def usage_calls(limit: int = 50, offset: int = 0, q: str = "", surface: str = "",
                model: str = ""):
    """Paginated, filterable per-call log inspector [S20]."""
    from core import usage_meter
    return usage_meter.calls(limit=limit, offset=offset, q=q, surface=surface, model=model)


@router.get("/api/usage/plans")
def usage_plans_get():
    from core import usage_meter
    return {"plans": usage_meter.get_plans()}


@router.post("/api/usage/plans")
def usage_plans_set(body: UsagePlansReq):
    """Configure provider plans/quotas → usage-vs-limit bars [S17]."""
    from core import usage_meter
    return {"plans": usage_meter.set_plans(body.plans)}


@router.get("/api/usage/budget")
def usage_budget_get():
    from core import usage_meter
    return usage_meter.get_budget()


@router.post("/api/usage/budget")
def usage_budget_set(body: UsageBudgetReq):
    """Set the monthly $ cap + alert threshold [S18]."""
    from core import usage_meter
    return usage_meter.set_budget(body.monthly_cap_usd, body.alert_pct)


@router.get("/api/usage/prices")
def usage_prices():
    """The active price table (config/llm_prices.yaml mirrored to DB) [S14]."""
    from core import usage_meter
    return {"prices": usage_meter.get_prices()}



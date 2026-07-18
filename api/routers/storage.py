"""Storage overview routes — /api/storage/* .

Extracted from api/dashboard.py (refactor Slice). Byte-identical handlers;
only @app.* -> @router.*. See docs/REFACTORING_PLAN.md.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["storage"])


@router.get("/api/storage/overview")
def storage_overview():
    """KPIs + per-feature breakdown + growth trend. Scans lazily on first visit
    so the page is never empty, then serves snapshots (instant loads) [S4]."""
    from core import storage_scan
    ov = storage_scan.overview()
    if not ov["scanned_at"]["db"]:
        storage_scan.run_scan("all")
        ov = storage_scan.overview()
    return ov


@router.get("/api/storage/category/{feature}")
def storage_category(feature: str, top: int = 12):
    """Drill-down: biggest DB tables + biggest files/dirs for one feature [S9]."""
    from core import storage_scan
    return storage_scan.category_detail(feature, top_n=max(3, min(top, 50)))


@router.post("/api/storage/scan")
def storage_scan_now(scope: str = "all", force_deps: bool = False):
    """Manual "Scan now" [S4]. scope: db | fs | all."""
    from core import storage_scan
    if scope not in ("db", "fs", "all"):
        raise HTTPException(400, "scope must be db | fs | all")
    res = storage_scan.run_scan(scope, force_deps=force_deps)
    return {"scan": res, "overview": storage_scan.overview()}

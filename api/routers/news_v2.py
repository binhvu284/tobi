"""News V2 API (#23, N06) — /api/explore/v2/* (plan §7).

Reads serve the precomputed rank snapshots with opaque, snapshot-pinned cursors and
the 15-40 limit clamp; no page request ever invokes an LLM. Mutations require an
``Idempotency-Key`` header (replays return the current state) and the optimistic
interaction ``version`` (mismatch → 409). The whole surface is fail-closed behind
``news.v2_enabled``/``news.v2_shadow`` — 503 until the owner opts in — and every
legacy ``/api/explore/*`` route stays untouched for rollback (plan §12).
"""
from __future__ import annotations

import base64
import binascii
import json
import re
import threading
import time
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from core import owner_flags
from core.database import DB_PATH, get_connection
from core.news import interactions as IX
from core.news import personalization, refresh, repository
from core.news.contracts import NewsSettings, Schedule, Tab, clamp_limit

MEDIA_DIR = Path(DB_PATH).parent / "news_media"
_SAFE_KEY = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


def _v2_gate() -> None:
    if not (owner_flags.get_bool(owner_flags.NEWS_V2_ENABLED, False)
            or owner_flags.get_bool(owner_flags.NEWS_V2_SHADOW, False)):
        raise HTTPException(status_code=503, detail="News V2 is not enabled (news.v2_enabled / news.v2_shadow are off)")


router = APIRouter(prefix="/api/explore/v2", tags=["news-v2"], dependencies=[Depends(_v2_gate)])

# Ungated: the frontend reads the rollout flags to decide V1 vs V2 rendering — this
# must work while the gated surface is still sealed (plan §12 stage gating).
config_router = APIRouter(prefix="/api/explore/v2", tags=["news-v2"])


@config_router.get("/config")
def v2_config():
    return {"enabled": owner_flags.get_bool(owner_flags.NEWS_V2_ENABLED, False),
            "shadow": owner_flags.get_bool(owner_flags.NEWS_V2_SHADOW, False)}


def _conn():
    conn = get_connection()
    repository._ensure_once(conn)
    return conn


# keyset cursor for non-snapshot lists (models explorer, favorites)
def _encode_after(value: str) -> str:
    raw = json.dumps({"a": value}, separators=(",", ":"))
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def _decode_after(token: str) -> str:
    try:
        padded = token + "=" * (-len(token) % 4)
        return str(json.loads(base64.urlsafe_b64decode(padded.encode()))["a"])
    except (KeyError, TypeError, ValueError, binascii.Error, json.JSONDecodeError):
        raise HTTPException(status_code=422, detail="invalid cursor")


def _interaction_state(conn, item_id: int) -> dict:
    row = conn.execute("SELECT reaction, favorite, note, opens, dwell_ms, version"
                       " FROM news_interactions WHERE item_id=?", (item_id,)).fetchone()
    if not row:
        return {"reaction": "none", "favorite": 0, "note": None, "opens": 0, "dwell_ms": 0, "version": 0}
    return {"reaction": row[0], "favorite": row[1], "note": row[2], "opens": row[3],
            "dwell_ms": row[4], "version": row[5]}


def _enrich(conn, entries: list[dict]) -> list[dict]:
    """Join snapshot entries with the live item + interaction state; items removed by
    retention since the snapshot silently drop out."""
    out = []
    for entry in entries:
        row = conn.execute(
            "SELECT canonical_url, item_type, excerpt, published_at, first_seen_at, media_key,"
            " (SELECT MAX(engagement) FROM news_item_sources WHERE item_id=n.id), recap"
            " FROM news_items n WHERE id=?", (entry["item_id"],)).fetchone()
        if not row:
            continue
        out.append({**entry, "url": row[0], "item_type": row[1], "excerpt": row[2],
                    "published_at": row[3], "first_seen_at": row[4], "media_key": row[5],
                    "engagement": int(row[6] or 0), "recap": row[7],
                    "interaction": _interaction_state(conn, entry["item_id"])})
    return out


# ── reads ────────────────────────────────────────────────────────────────────────────
@router.get("/home")
def v2_home():
    conn = _conn()
    try:
        top = repository.read_snapshot_page(conn, kind="models:top", limit=20)
        releases = [dict(zip(("id", "model_id", "title", "source_url", "released_at", "observed_at"), r))
                    for r in conn.execute(
                        "SELECT id, model_id, title, source_url, released_at, observed_at"
                        " FROM news_model_releases ORDER BY COALESCE(released_at, observed_at) DESC"
                        " LIMIT 10")]
        # image-rich release NEWS (owner: single-line card + thumbnail + title + 3-line
        # + TOBI recap). Recent publication articles; recapped/thumbnailed ones first.
        release_news = [dict(zip(("item_id", "title", "url", "source", "excerpt", "recap",
                                  "media_key", "published_at", "first_seen_at"), r))
                        for r in conn.execute(
                            "SELECT n.id, n.title, n.canonical_url,"
                            " (SELECT s.source FROM news_item_sources s WHERE s.item_id=n.id"
                            "   ORDER BY s.observed_at DESC LIMIT 1),"
                            " n.excerpt, n.recap, n.media_key, n.published_at, n.first_seen_at"
                            " FROM news_items n WHERE n.item_type='article'"
                            " ORDER BY (n.media_key IS NOT NULL) DESC, (n.recap IS NOT NULL) DESC,"
                            " COALESCE(n.published_at, n.first_seen_at) DESC LIMIT 8")]
        health = {}
        for tab in ("home", "trending", "feed"):
            job = conn.execute(
                "SELECT state, checkpoints_json, updated_at FROM news_refresh_jobs"
                " WHERE tab=? ORDER BY id DESC LIMIT 1", (tab,)).fetchone()
            health[tab] = ({"state": job[0], "sources": json.loads(job[1] or "{}"),
                            "updated_at": job[2]} if job else None)
        freshness = {r[0]: r[1] for r in conn.execute(
            "SELECT kind, MAX(created_at) FROM news_rank_snapshots GROUP BY kind")}
        return {"top": top["entries"][:20], "snapshot_id": top["snapshot_id"],
                "releases": releases, "release_news": release_news,
                "source_health": health, "freshness": freshness}
    finally:
        conn.close()


@router.get("/models/leaderboards")
def v2_model_leaderboards():
    """Model Explorer overview: one Top-5 board per evidence category (data-driven —
    new benchmark categories become new boards automatically)."""
    from core.news import ranking
    conn = _conn()
    try:
        return {"categories": ranking.category_leaderboards(conn)}
    finally:
        conn.close()


@router.get("/models")
def v2_models(q: str = "", category: str = "", cursor: Optional[str] = None, limit: int = 20):
    """Model Explorer: every model with evidence (Top-10 eligibility NOT required),
    keyset-cursored, each metric attributed with source + observation time."""
    limit_n = clamp_limit(limit)
    after = _decode_after(cursor) if cursor else ""
    conn = _conn()
    try:
        params: list = [after]
        where = "model_id > ?"
        if q.strip():
            where += " AND model_id LIKE ?"
            params.append(f"%{q.strip()}%")
        if category.strip():
            where += " AND category=?"
            params.append(category.strip())
        ids = [r[0] for r in conn.execute(
            f"SELECT DISTINCT model_id FROM news_model_metrics WHERE {where}"
            " ORDER BY model_id LIMIT ?", (*params, limit_n + 1))]
        page, more = ids[:limit_n], len(ids) > limit_n
        models = []
        for model_id in page:
            metrics = [dict(zip(("category", "source", "metric", "value", "confidence",
                                 "observed_at", "formula_version"), r))
                       for r in conn.execute(
                           "SELECT category, source, metric, value, confidence, observed_at,"
                           " formula_version FROM news_model_metrics WHERE model_id=?"
                           " ORDER BY category, source, metric", (model_id,))]
            models.append({"model_id": model_id, "metrics": metrics})
        return {"models": models,
                "next_cursor": _encode_after(page[-1]) if more and page else None}
    finally:
        conn.close()


@router.get("/trending")
def v2_trending(section: str = "github", window: str = "week", q: str = "",
                cursor: Optional[str] = None, limit: int = 20):
    conn = _conn()
    try:
        if section == "github":
            if window not in ("week", "month", "all"):
                raise HTTPException(status_code=422, detail="window must be week|month|all")
            page = repository.read_snapshot_page(conn, kind=f"trending:github:{window}",
                                                 cursor=cursor, limit=limit)
            for entry in page["entries"]:   # join the repo description from the ledger
                row = conn.execute(
                    "SELECT n.excerpt FROM news_items n JOIN news_item_sources s ON s.item_id=n.id"
                    " WHERE s.source='github' AND s.external_id=? LIMIT 1", (entry["repo"],)).fetchone()
                if row and (row[0] or "").strip():
                    entry["description"] = row[0]
            query = q.strip().lower()
            if query:                       # owner: search by repo name / author (page-level)
                page["entries"] = [e for e in page["entries"]
                                   if query in str(e.get("repo", "")).lower()]
            return {"section": section, "window": window, "q": q, **page}
        if section == "tools":
            page = repository.read_snapshot_page(conn, kind="trending:tools", cursor=cursor, limit=limit)
            page["entries"] = _enrich(conn, page["entries"])
            return {"section": section, **page}
        if section == "sources":
            sources = [dict(zip(("source", "items", "latest_observed"), r)) for r in conn.execute(
                "SELECT source, COUNT(*), MAX(observed_at) FROM news_item_sources"
                " GROUP BY source ORDER BY COUNT(*) DESC, source")]
            return {"section": section, "sources": sources}
        raise HTTPException(status_code=422, detail="section must be github|tools|sources")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    finally:
        conn.close()


@router.get("/feed")
def v2_feed(mode: str = "for_you", cursor: Optional[str] = None, limit: int = 20,
            source: str = "", has_note: bool = False):
    conn = _conn()
    try:
        if mode in ("for_you", "latest"):
            try:
                page = repository.read_snapshot_page(conn, kind=f"feed:{mode}",
                                                     cursor=cursor, limit=limit)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc))
            entries = _enrich(conn, page["entries"])
            if source.strip():                      # page-level filter (cursor stays stable)
                entries = [e for e in entries if e["source"] == source.strip()]
            return {"mode": mode, "snapshot_id": page["snapshot_id"], "entries": entries,
                    "next_cursor": page["next_cursor"]}
        if mode == "favorites":
            limit_n = clamp_limit(limit)
            after = _decode_after(cursor) if cursor else ""
            rows = conn.execute(
                "SELECT i.item_id, i.note, i.updated_at, n.title FROM news_interactions i"
                " JOIN news_items n ON n.id=i.item_id WHERE i.favorite=1 AND i.item_id > ?"
                " ORDER BY i.item_id LIMIT ?", (int(after) if after else 0, limit_n + 1)).fetchall()
            page_rows, more = rows[:limit_n], len(rows) > limit_n
            entries = _enrich(conn, [{"item_id": r[0], "title": r[3]} for r in page_rows])
            if has_note:
                entries = [e for e in entries if (e["interaction"]["note"] or "").strip()]
            if source.strip():
                srcs = {r[0] for r in conn.execute(
                    "SELECT DISTINCT item_id FROM news_item_sources WHERE source=?", (source.strip(),))}
                entries = [e for e in entries if e["item_id"] in srcs]
            return {"mode": mode, "entries": entries,
                    "next_cursor": _encode_after(str(page_rows[-1][0])) if more and page_rows else None}
        raise HTTPException(status_code=422, detail="mode must be for_you|latest|favorites")
    finally:
        conn.close()


# ── mutations (Idempotency-Key + optimistic version) ─────────────────────────────────
class InteractionReq(BaseModel):
    action: str = Field(pattern="^(like|dislike|undo|favorite|unfavorite)$")
    version: int = Field(ge=0)


class NoteReq(BaseModel):
    note: Optional[str] = None
    version: int = Field(ge=0)


class EventReq(BaseModel):
    type: str = Field(pattern="^(open|dwell)$")
    ms: Optional[int] = Field(default=None, ge=1)


def _idem(idempotency_key: Optional[str]) -> str:
    key = (idempotency_key or "").strip()
    if not key:
        raise HTTPException(status_code=400, detail="Idempotency-Key header is required")
    return key


def _replayed(conn, key: str, item_id: int) -> Optional[dict]:
    if conn.execute("SELECT 1 FROM news_interaction_events WHERE idempotency_key=?", (key,)).fetchone():
        return _interaction_state(conn, item_id)
    return None


def _check_version(conn, item_id: int, version: int) -> None:
    current = _interaction_state(conn, item_id)["version"]
    if version != current:
        raise HTTPException(status_code=409, detail=f"stale interaction version {version} (current {current})")


@router.patch("/items/{item_id}/interaction")
def v2_interaction(item_id: int, req: InteractionReq,
                   idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key")):
    key = _idem(idempotency_key)
    conn = _conn()
    try:
        replay = _replayed(conn, key, item_id)
        if replay is not None:
            return {"item_id": item_id, **replay, "replayed": True}
        _check_version(conn, item_id, req.version)
        try:
            if req.action == "like":
                state = IX.like(conn, item_id, key)
            elif req.action == "dislike":
                state = IX.dislike(conn, item_id, key)
            elif req.action == "undo":
                state = IX.undo_dislike(conn, item_id, key)
            elif req.action == "favorite":
                state = IX.set_favorite(conn, item_id, True, key)
            else:
                state = IX.set_favorite(conn, item_id, False, key)
        except ValueError as exc:
            detail = str(exc)
            raise HTTPException(status_code=404 if "unknown news item" in detail else 409, detail=detail)
        conn.commit()
        return {"item_id": item_id, **state, "replayed": False}
    finally:
        conn.close()


@router.put("/items/{item_id}/note")
def v2_note(item_id: int, req: NoteReq,
            idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key")):
    key = _idem(idempotency_key)
    conn = _conn()
    try:
        replay = _replayed(conn, key, item_id)
        if replay is not None:
            return {"item_id": item_id, **replay, "replayed": True}
        _check_version(conn, item_id, req.version)
        try:
            state = IX.set_note(conn, item_id, req.note, key)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        conn.commit()
        return {"item_id": item_id, **state, "replayed": False}
    finally:
        conn.close()


@router.post("/items/{item_id}/events")
def v2_events(item_id: int, req: EventReq,
              idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key")):
    key = _idem(idempotency_key)
    conn = _conn()
    try:
        try:
            if req.type == "open":
                state = IX.record_open(conn, item_id, key)
                recorded = True
            else:
                if req.ms is None:
                    raise HTTPException(status_code=422, detail="dwell events require ms")
                state = IX.record_dwell(conn, item_id, req.ms, key)
                recorded = bool(state.pop("recorded", True))
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        conn.commit()
        return {"item_id": item_id, **state, "recorded": recorded}
    finally:
        conn.close()


@router.post("/items/{item_id}/save-to-brain")
def v2_save_to_brain(item_id: int):
    raise HTTPException(status_code=501,
                        detail="Save to Brain lands with the context adapter (N11, after #20 service acceptance)")


# ── settings ─────────────────────────────────────────────────────────────────────────
class SettingsReq(BaseModel):
    schedules: Optional[dict] = None
    enabled_sources: Optional[list] = None
    context_classes: Optional[dict] = None


@router.get("/settings")
def v2_get_settings():
    conn = _conn()
    try:
        settings = repository.get_settings(conn)
        return {"schedules": dict(settings.schedules),
                "enabled_sources": list(settings.enabled_sources),
                "context_classes": dict(settings.context_classes),
                "schedule_options": [s.value for s in Schedule],
                "known_sources": sorted({cls().name for classes in refresh._TAB_SOURCES.values()
                                         for cls in classes}),
                # which registered sources feed each tab — the UI's section attribution
                "tab_sources": {tab: [cls().name for cls in classes]
                                for tab, classes in refresh._TAB_SOURCES.items()},
                # sources awaiting owner setup (missing keys) — skipped, never failed
                "unconfigured": sorted({adapter.name for classes in refresh._TAB_SOURCES.values()
                                        for cls in classes
                                        if not refresh._configured_safe(adapter := cls())[0]})}
    finally:
        conn.close()


@router.patch("/settings")
def v2_patch_settings(req: SettingsReq):
    conn = _conn()
    try:
        current = repository.get_settings(conn)
        if req.enabled_sources is not None:
            known = {cls().name for classes in refresh._TAB_SOURCES.values() for cls in classes}
            unknown = sorted(set(req.enabled_sources) - known)
            if unknown:
                raise HTTPException(status_code=422, detail=f"unknown sources: {', '.join(unknown)}")
        try:
            merged = NewsSettings(
                schedules=req.schedules if req.schedules is not None else dict(current.schedules),
                enabled_sources=tuple(req.enabled_sources) if req.enabled_sources is not None
                else current.enabled_sources,
                context_classes=req.context_classes if req.context_classes is not None
                else dict(current.context_classes))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        repository.set_settings(conn, merged)
        conn.commit()
        return {"schedules": dict(merged.schedules), "enabled_sources": list(merged.enabled_sources),
                "context_classes": dict(merged.context_classes)}
    finally:
        conn.close()


# ── refresh: start/join, state, commands, SSE ────────────────────────────────────────
class RefreshReq(BaseModel):
    tab: str
    sources: Optional[list[str]] = None      # per-table refresh: restrict to these sources


class CommandReq(BaseModel):
    command: str = Field(pattern="^(cancel|retry_failed)$")


@router.post("/refresh")
def v2_refresh(req: RefreshReq):
    try:
        Tab(req.tab)
        result = refresh.request_refresh(req.tab, only=req.sources or None)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    threading.Thread(target=refresh.run_job, args=(result["job_id"],), daemon=True).start()
    return result


@router.get("/refresh/{job_id}")
def v2_refresh_job(job_id: int):
    try:
        return refresh.get_job(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/refresh/{job_id}/commands")
def v2_refresh_command(job_id: int, req: CommandReq):
    try:
        if req.command == "cancel":
            return refresh.cancel_job(job_id)
        job = refresh.retry_failed(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=409 if "unknown" not in str(exc) else 404, detail=str(exc))
    threading.Thread(target=refresh.run_job, args=(job_id,), daemon=True).start()
    return job


def _job_event(job: dict, sequence: int) -> dict:
    checkpoints = job["checkpoints"]
    done = sum(1 for cp in checkpoints.values() if cp.get("state") == "ok")
    return {"job_id": job["id"], "sequence": sequence, "tab": job["tab"], "state": job["state"],
            "sources": {name: cp.get("state") for name, cp in checkpoints.items()},
            "progress": round(done / len(checkpoints), 3) if checkpoints else 1.0,
            "retryable": job["state"] in ("partial", "failed"),
            "error": job["error"]}


@router.get("/refresh/{job_id}/stream")
def v2_refresh_stream(job_id: int):
    """Ordered SSE derived from the durable job row: an event whenever state or a
    source checkpoint changes, a final event at a terminal state, then close. A
    joining client always receives the current state as its first event."""
    try:
        refresh.get_job(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    def generate():
        sequence = 0
        last = None
        terminal = {"completed", "partial", "failed", "canceled"}
        for _ in range(300):                          # ~2 min cap; SSE clients reconnect
            try:
                job = refresh.get_job(job_id)
            except ValueError:
                break
            snapshot = (job["state"], json.dumps(job["checkpoints"], sort_keys=True))
            if snapshot != last:
                sequence += 1
                payload = _job_event(job, sequence)
                yield f"id: {sequence}\nevent: job\ndata: {json.dumps(payload)}\n\n"
                last = snapshot
            if job["state"] in terminal:
                break
            time.sleep(0.4)
    return StreamingResponse(generate(), media_type="text/event-stream")


# ── media: validated cache only, no traversal, no proxying ───────────────────────────
@router.get("/media/{cache_key}")
def v2_media(cache_key: str):
    if not _SAFE_KEY.match(cache_key):
        raise HTTPException(status_code=422, detail="invalid media key")
    conn = _conn()
    try:
        row = conn.execute("SELECT local_key, mime, expires_at FROM news_media_cache"
                           " WHERE local_key=?", (cache_key,)).fetchone()
    finally:
        conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="unknown media")
    path = (MEDIA_DIR / row[0]).resolve()
    if MEDIA_DIR.resolve() not in path.parents or not path.is_file():
        raise HTTPException(status_code=404, detail="media unavailable")
    return FileResponse(path, media_type=row[1])


# expose profile/reasons for the UI ("transparent learning")
@router.get("/profile")
def v2_profile():
    conn = _conn()
    try:
        profile = personalization.active_profile(conn)
        return profile or {"version": 0, "topics": {}, "sources": {}, "types": {},
                           "provenance": {"items_considered": 0}}
    finally:
        conn.close()

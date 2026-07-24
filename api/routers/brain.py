"""Brain (legacy v1) owner-memory API — /api/brain/* .

Extracted from api/dashboard.py (refactor Slice — pre-#21 decomposition). Byte-
identical handlers; only @app.* -> @router.*, with _get_conn from api.deps. The
_brain_backend()/_brain_call() helpers move with the routes (used only here).
Brain V2 routes live separately in api/brain_v2.py. See docs/REFACTORING_PLAN.md.
"""
from __future__ import annotations

import asyncio  # noqa: F401 - used by streaming handlers
import json  # noqa: F401 - used by some handlers

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse  # noqa: F401 - used by chat stream
from pydantic import BaseModel

from api.deps import _get_conn
from core import brain, brain_v2_compat, owner_flags, vault

router = APIRouter(tags=["brain"])


# ── Brain: long-term owner memory (auto-learn + import + chat) ──────────────────

def _brain_backend():
    """Return the legacy contract implementation selected by the Brain rollout flag."""
    if owner_flags.brain_v2_mode() == "on":
        brain_v2_compat.ensure_ready()
        return brain_v2_compat
    return brain


def _brain_call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except vault.VaultLocked as exc:
        raise HTTPException(status_code=423, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


class BrainMemoryCreate(BaseModel):
    content: str
    category: str = "identity"
    confidence: float = 0.6
    source: str = "manual"


class BrainMemoryPatch(BaseModel):
    content: str | None = None
    category: str | None = None
    confidence: float | None = None


class BrainSearchReq(BaseModel):
    query: str
    k: int = 12


class BrainResolveReq(BaseModel):
    decision: str  # keep_existing | use_candidate | keep_both


class BrainImportReq(BaseModel):
    filename: str = "import"
    content: str


class BrainImportCommitReq(BaseModel):
    filename: str = "import"
    source_type: str = "md"
    items: list[dict]


class BrainMergeReq(BaseModel):
    ids: list[int]
    keep_id: int | None = None


class BrainRememberReq(BaseModel):
    content: str
    category: str | None = None


class BrainChatReq(BaseModel):
    message: str


@router.get("/api/brain/stats")
def brain_stats():
    backend = _brain_backend()
    return _brain_call(backend.stats)


@router.get("/api/brain/categories")
def brain_categories():
    return {"categories": brain.list_categories()}


class BrainCategoryPatchRequest(BaseModel):
    is_locked: bool | None = None
    label: str | None = None
    color: str | None = None


@router.patch("/api/brain/categories/{cat_id}")
def brain_patch_category(cat_id: str, payload: BrainCategoryPatchRequest):
    conn = _get_conn()
    try:
        if not conn.execute("SELECT 1 FROM brain_categories WHERE id=?", (cat_id,)).fetchone():
            raise HTTPException(status_code=404, detail="category not found")
        fields, vals = [], []
        if payload.is_locked is not None:
            fields.append("is_locked=?"); vals.append(1 if payload.is_locked else 0)
        if payload.label is not None:
            fields.append("label=?"); vals.append(payload.label)
        if payload.color is not None:
            fields.append("color=?"); vals.append(payload.color)
        if fields:
            vals.append(cat_id)
            conn.execute(f"UPDATE brain_categories SET {', '.join(fields)} WHERE id=?", vals)
            conn.commit()
        row = conn.execute("SELECT * FROM brain_categories WHERE id=?", (cat_id,)).fetchone()
        return dict(row)
    finally:
        conn.close()


@router.get("/api/brain/memories")
def brain_list(category: str | None = None, source: str | None = None,
               status: str = "active", q: str | None = None, stale: bool | None = None):
    backend = _brain_backend()
    return {"items": _brain_call(backend.list_memories, category=category, source=source,
                                  status=status, q=q, stale=stale)}


@router.post("/api/brain/memories")
def brain_create(payload: BrainMemoryCreate):
    backend = _brain_backend()
    mid = _brain_call(backend.add_memory, payload.content, payload.category,
                      payload.confidence, payload.source, status="active")
    return _brain_call(backend.get_memory, mid)


@router.get("/api/brain/memories/{mid}")
def brain_get(mid: int):
    backend = _brain_backend()
    m = _brain_call(backend.get_memory, mid)
    if not m:
        raise HTTPException(status_code=404, detail="Memory not found")
    return m


@router.patch("/api/brain/memories/{mid}")
def brain_patch(mid: int, payload: BrainMemoryPatch):
    backend = _brain_backend()
    m = _brain_call(backend.update_memory, mid, payload.content,
                    payload.category, payload.confidence)
    if not m:
        raise HTTPException(status_code=404, detail="Memory not found")
    return m


@router.delete("/api/brain/memories/{mid}")
def brain_delete(mid: int):
    backend = _brain_backend()
    _brain_call(backend.delete_memory, mid)
    return {"ok": True}


@router.post("/api/brain/memories/{mid}/confirm")
def brain_confirm(mid: int):
    backend = _brain_backend()
    m = _brain_call(backend.confirm_memory, mid)
    if not m:
        raise HTTPException(status_code=404, detail="Memory not found")
    return m


@router.get("/api/brain/memories/{mid}/versions")
def brain_versions(mid: int):
    backend = _brain_backend()
    return {"versions": _brain_call(backend.list_versions, mid)}


@router.post("/api/brain/search")
def brain_search(payload: BrainSearchReq):
    backend = _brain_backend()
    return {"items": _brain_call(backend.semantic_search, payload.query, k=payload.k)}


@router.get("/api/brain/pending")
def brain_pending():
    backend = _brain_backend()
    return {"items": _brain_call(backend.list_pending)}


@router.post("/api/brain/pending/{mid}/accept")
def brain_pending_accept(mid: int):
    backend = _brain_backend()
    return _brain_call(backend.accept_pending, mid) or {"ok": False}


@router.post("/api/brain/pending/{mid}/reject")
def brain_pending_reject(mid: int):
    backend = _brain_backend()
    _brain_call(backend.reject_pending, mid)
    return {"ok": True}


@router.get("/api/brain/conflicts")
def brain_conflicts():
    backend = _brain_backend()
    return {"items": _brain_call(backend.list_conflicts)}


@router.post("/api/brain/conflicts/{cid}/resolve")
def brain_conflict_resolve(cid: int, payload: BrainResolveReq):
    backend = _brain_backend()
    _brain_call(backend.resolve_conflict, cid, payload.decision)
    return {"ok": True}


@router.post("/api/brain/import")
def brain_import(payload: BrainImportReq):
    backend = _brain_backend()
    items = _brain_call(backend.parse_import, payload.filename, payload.content)
    return {"items": items}


@router.post("/api/brain/import/commit")
def brain_import_commit(payload: BrainImportCommitReq):
    backend = _brain_backend()
    return _brain_call(backend.commit_import, payload.filename, payload.source_type, payload.items)


@router.get("/api/brain/duplicates")
def brain_duplicates():
    backend = _brain_backend()
    return {"groups": _brain_call(backend.find_duplicates)}


@router.post("/api/brain/duplicates/merge")
def brain_merge(payload: BrainMergeReq):
    backend = _brain_backend()
    return _brain_call(backend.merge_group, payload.ids, payload.keep_id)


@router.get("/api/brain/narrative")
def brain_narrative_get():
    backend = _brain_backend()
    return _brain_call(backend.get_narrative) or {"content": None}


@router.post("/api/brain/narrative")
def brain_narrative_make():
    backend = _brain_backend()
    n = _brain_call(backend.synthesize_narrative)
    if not n:
        raise HTTPException(status_code=503, detail="Could not synthesize (no memories or LLM unavailable)")
    return n


@router.post("/api/brain/remember")
def brain_remember(payload: BrainRememberReq):
    return brain.remember(payload.content, payload.category)


@router.post("/api/brain/chat")
def brain_chat(payload: BrainChatReq):
    # Routed through the Conductor (queue #7): it reads/answers about live MC state in a
    # butler voice, and degrades to a normal memory-grounded reply for smalltalk. Falls
    # back to the plain Brain chat if the Conductor is unavailable.
    try:
        from core import conductor
        return conductor.conductor_chat(payload.message, surface="mc")
    except Exception:
        return brain.chat(payload.message)


@router.post("/api/brain/chat/stream")
async def brain_chat_stream(payload: BrainChatReq):
    """SSE token stream for the MC chat — Conductor-powered (queue #7). Emits `delta` events as
    the grounded answer reveals, an `action` event when a high-risk act needs confirmation, then
    a final `done`. Falls back to the Brain chat stream if the Conductor is unavailable."""
    message = payload.message

    async def gen():
        loop = asyncio.get_event_loop()
        try:
            from core import conductor
            res = await loop.run_in_executor(None, lambda: conductor.conductor_chat(message, None, "mc"))
            for chunk in conductor._stream_chunks(res.get("reply", "") or ""):
                yield f"event: delta\ndata: {json.dumps({'text': chunk})}\n\n"
            pending = res.get("pending_action")
            if pending:
                yield f"event: action\ndata: {json.dumps(pending)}\n\n"
        except Exception:
            try:
                it = iter(brain.chat_stream(message))
                while True:
                    try:
                        delta = await loop.run_in_executor(None, next, it)
                    except StopIteration:
                        break
                    yield f"event: delta\ndata: {json.dumps({'text': delta})}\n\n"
            except Exception as e:
                yield f"event: error\ndata: {json.dumps({'detail': str(e)[:200]})}\n\n"
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "Connection": "keep-alive",
                                      "X-Accel-Buffering": "no"})


@router.get("/api/brain/chat/history")
def brain_chat_history():
    from core.database import load_conversation_history
    return {"items": load_conversation_history(brain.DASHBOARD_CHAT_ID, limit=50)}


@router.post("/api/brain/sweep")
def brain_sweep():
    return brain.sweep_once()

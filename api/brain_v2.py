"""Brain Memory V2 API (#20 / spec §API Plan, task T09 backend).

A dedicated router so ``api/dashboard.py`` stays an HTTP composition root.
Legacy ``/api/brain/*`` is untouched; everything here is additive under
``/api/brain/v2/*``. Mutations use validated Pydantic contracts; a locked
vault maps to HTTP 423 so the UI can render its locked state; replayable
mutations accept an ``Idempotency-Key`` header.
"""
from __future__ import annotations

import asyncio
import json
import threading
from typing import Any, Literal, Optional

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from core import vault
from core import brain_repository as repo
from core import brain_import as imp
from core import brain_migration as mig
from core import brain_feedback as fb
from core import brain_retrieval as ret
from core.brain_contracts import MemoryStatus, MemoryType
from core.brain_ingest import text_similarity, MERGE_AT

router = APIRouter(prefix="/api/brain/v2", tags=["brain-v2"])

# tiny replay guard for remember (process-lifetime; spec: idempotency keys
# where replay is possible)
_IDEMPOTENT: dict[str, dict] = {}
_IDEMPOTENT_LOCK = threading.Lock()
_IDEMPOTENT_MAX = 512


def _http(e: Exception) -> HTTPException:
    if isinstance(e, vault.VaultLocked):
        return HTTPException(423, str(e))          # Locked — UI renders the vault state
    if isinstance(e, ValueError):
        return HTTPException(400, str(e))
    return HTTPException(500, str(e)[:300])


def _memory_dict(m: repo.StoredMemory) -> dict:
    return {
        "id": m.id, "distilled_text": m.distilled_text, "memory_type": m.memory_type.value,
        "behavior_implication": m.behavior_implication, "tags": list(m.tags),
        "scope_type": m.scope_type.value, "scope_key": m.scope_key,
        "authority": m.authority.value, "explicitness": m.explicitness.value,
        "confidence": m.confidence, "quality_score": m.quality_score,
        "trust": m.trust.value, "sensitive": m.sensitive, "status": m.status.value,
        "redacted": m.redacted, "compat_ref": m.compat_ref,
        "evidence": [{"id": e.id, "excerpt": e.excerpt, "source_ref": e.source_ref,
                      "trust": e.trust.value, "redacted": e.redacted} for e in m.evidence],
        "created_at": m.created_at, "updated_at": m.updated_at,
    }


# ── remember ─────────────────────────────────────────────────────────────────
class RememberReq(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    category: Optional[str] = None


@router.post("/remember")
def v2_remember(payload: RememberReq, idempotency_key: Optional[str] = Header(default=None)):
    from core import brain
    if idempotency_key:
        with _IDEMPOTENT_LOCK:
            if idempotency_key in _IDEMPOTENT:
                return {**_IDEMPOTENT[idempotency_key], "replayed": True}
    try:
        res = brain.remember(payload.content, payload.category)
    except Exception as e:
        raise _http(e)
    if idempotency_key:
        with _IDEMPOTENT_LOCK:
            if len(_IDEMPOTENT) >= _IDEMPOTENT_MAX:
                _IDEMPOTENT.clear()
            _IDEMPOTENT[idempotency_key] = res
    return res


# ── import jobs ──────────────────────────────────────────────────────────────
class ImportCreateReq(BaseModel):
    filename: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1)


class JobCommandReq(BaseModel):
    command: Literal["run", "step", "resume", "cancel", "retry", "commit"]


class TriageReq(BaseModel):
    ids: Optional[list[int]] = None                # individual candidates
    outcome: Optional[str] = None                  # or every candidate of one proposed outcome


@router.post("/import-jobs")
def import_create(payload: ImportCreateReq):
    try:
        job_id = imp.create_job(payload.filename, payload.content)
        return imp.job_status(job_id)
    except Exception as e:
        raise _http(e)


@router.get("/import-jobs/{job_id}")
def import_status(job_id: int):
    try:
        return imp.job_status(job_id)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.get("/import-jobs/{job_id}/candidates")
def import_candidates(job_id: int):
    try:
        imp.job_status(job_id)                    # 404 for unknown jobs
        return imp.list_candidates(job_id)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/import-jobs/{job_id}/commands")
def import_command(job_id: int, payload: JobCommandReq):
    try:
        cmd = payload.command
        if cmd in ("run", "resume"):
            return imp.run_job(job_id)
        if cmd == "step":
            return imp.step_job(job_id)
        if cmd == "cancel":
            imp.cancel_job(job_id)
            return imp.job_status(job_id)
        if cmd == "retry":
            return imp.retry_job(job_id)
        return imp.commit_job(job_id)              # commit
    except HTTPException:
        raise
    except Exception as e:
        raise _http(e)


@router.get("/import-jobs/{job_id}/events")
async def import_events(job_id: int):
    """SSE progress stream: one status event per poll tick until the job leaves
    dry_run (spec: streaming progress)."""
    try:
        imp.job_status(job_id)
    except ValueError as e:
        raise HTTPException(404, str(e))

    async def gen():
        while True:
            st = await asyncio.to_thread(imp.job_status, job_id)
            yield f"data: {json.dumps(st, ensure_ascii=False)}\n\n"
            if st["status"] != "dry_run":
                break
            await asyncio.sleep(1.0)
    return StreamingResponse(gen(), media_type="text/event-stream")


def _triage(job_id: int, approved: bool, payload: TriageReq) -> dict:
    imp.job_status(job_id)                        # 404 guard
    n = 0
    if payload.ids:
        for cid in payload.ids:
            imp.set_decision(cid, approved)
            n += 1
    else:
        n = imp.bulk_decide(job_id, approved, only_outcome=payload.outcome)
    return {"ok": True, "decided": n, "approved": approved}


@router.post("/import-jobs/{job_id}/candidates/approve")
def import_approve(job_id: int, payload: TriageReq):
    try:
        return _triage(job_id, True, payload)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/import-jobs/{job_id}/candidates/reject")
def import_reject(job_id: int, payload: TriageReq):
    try:
        return _triage(job_id, False, payload)
    except ValueError as e:
        raise HTTPException(404, str(e))


# ── memories ─────────────────────────────────────────────────────────────────
class StatusReq(BaseModel):
    status: Literal["active", "pending", "rejected", "archived", "superseded"]


class FeedbackReq(BaseModel):
    verdict: Literal["useful", "irrelevant", "wrong"]
    turn_ref: Optional[str] = Field(default=None, max_length=200)


@router.get("/memories")
def memories_list(status: Optional[str] = None, memory_type: Optional[str] = None,
                  sensitive: Optional[bool] = None, limit: int = 200):
    try:
        st = MemoryStatus(status) if status else None
    except ValueError:
        raise HTTPException(400, f"unknown status: {status}")
    rows = repo.list_memories(st)
    out = []
    for m in rows:
        if memory_type and m.memory_type.value != memory_type:
            continue
        if sensitive is not None and m.sensitive is not sensitive:
            continue
        out.append(_memory_dict(m))
        if len(out) >= max(1, min(limit, 500)):
            break
    return out


@router.get("/memories/{memory_id}")
def memory_detail(memory_id: int):
    m = repo.read(memory_id)
    if m is None:
        raise HTTPException(404, "no such memory")
    return _memory_dict(m)


@router.get("/memories/{memory_id}/influence")
def memory_influence(memory_id: int):
    if repo.read(memory_id) is None:
        raise HTTPException(404, "no such memory")
    return fb.influence_of(memory_id)


@router.post("/memories/{memory_id}/feedback")
def memory_feedback(memory_id: int, payload: FeedbackReq):
    try:
        fid = fb.add_feedback(memory_id, payload.verdict, payload.turn_ref)
        return {"ok": True, "feedback_id": fid, "usefulness": fb.usefulness(memory_id)}
    except ValueError as e:
        raise HTTPException(404 if "no such" in str(e) else 400, str(e))


@router.post("/memories/{memory_id}/status")
def memory_set_status(memory_id: int, payload: StatusReq):
    if repo.read(memory_id) is None:
        raise HTTPException(404, "no such memory")
    repo.set_status(memory_id, MemoryStatus(payload.status))
    return _memory_dict(repo.read(memory_id))


class EditReq(BaseModel):
    distilled_text: Optional[str] = Field(default=None, min_length=1, max_length=2000)
    memory_type: Optional[str] = None
    behavior_implication: Optional[str] = Field(default=None, max_length=500)


@router.post("/memories/{memory_id}/edit")
def memory_edit(memory_id: int, payload: EditReq):
    """Owner edit of a memory's text / type / implication. Sensitive text re-encrypts
    through the vault (423 when locked); unknown type → 400; unknown memory → 404."""
    if repo.read(memory_id) is None:
        raise HTTPException(404, "no such memory")
    try:
        mt = MemoryType(payload.memory_type) if payload.memory_type else None
    except ValueError:
        raise HTTPException(400, f"unknown memory_type: {payload.memory_type}")
    try:
        repo.edit_fields(memory_id, distilled_text=payload.distilled_text, memory_type=mt,
                         behavior_implication=payload.behavior_implication)
    except Exception as e:
        raise _http(e)
    return _memory_dict(repo.read(memory_id))


@router.delete("/memories/{memory_id}/purge")
def memory_purge(memory_id: int):
    if not repo.purge(memory_id):
        raise HTTPException(404, "no such memory")
    return {"ok": True, "purged": memory_id}


# ── profile / recall / stats (Brain home + Ask Brain) ────────────────────────
class RecallReq(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    mode: Literal["chat", "agent"] = "chat"


@router.get("/profile")
def v2_profile():
    text, version = ret.stable_profile()
    return {"profile": text, "version": version,
            "token_budget": ret.PROFILE_TOKEN_BUDGET}


@router.post("/recall")
def v2_recall(payload: RecallReq):
    return ret.retrieve(payload.query, payload.mode)


@router.get("/stats")
def v2_stats():
    c = repo._conn(None)
    by_status = dict(c.execute(
        "SELECT status, count(*) FROM brain_memory_v2 GROUP BY status").fetchall())
    by_type = dict(c.execute(
        "SELECT memory_type, count(*) FROM brain_memory_v2 GROUP BY memory_type").fetchall())
    conflicted = c.execute(
        "SELECT count(DISTINCT from_id) FROM brain_memory_links WHERE link_type='conflicts_with'"
    ).fetchone()[0]
    sensitive = c.execute("SELECT count(*) FROM brain_memory_v2 WHERE sensitive=1").fetchone()[0]
    aging = c.execute(
        "SELECT count(*) FROM brain_memory_v2 WHERE status='pending' "
        "AND created_at <= datetime('now','-14 days')").fetchone()[0]
    return {"by_status": by_status, "by_type": by_type, "conflicted": conflicted,
            "sensitive": sensitive, "aging_pending": aging,
            "vault_unlocked": vault.can_encrypt_payloads()}


# ── migration (T06 driver) ───────────────────────────────────────────────────
class MigrationCommandReq(BaseModel):
    command: Literal["run", "resume", "apply", "cancel"]


class MigrationTriageReq(BaseModel):
    ids: Optional[list[int]] = None
    group: Optional[str] = None


@router.post("/migration/runs")
def migration_create():
    try:
        run_id = mig.create_run()
        return mig.run_status(run_id)
    except Exception as e:
        raise _http(e)


@router.get("/migration/runs/{run_id}")
def migration_status(run_id: int):
    try:
        return mig.run_status(run_id)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.get("/migration/runs/{run_id}/items")
def migration_items(run_id: int, group: Optional[str] = None):
    try:
        mig.run_status(run_id)
        return mig.list_items(run_id, group=group)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/migration/runs/{run_id}/commands")
def migration_command(run_id: int, payload: MigrationCommandReq):
    try:
        if payload.command in ("run", "resume"):
            return mig.run_preview(run_id)
        if payload.command == "apply":
            return mig.apply_run(run_id)
        mig.cancel_run(run_id)
        return mig.run_status(run_id)
    except HTTPException:
        raise
    except Exception as e:
        raise _http(e)


def _mig_triage(run_id: int, approved: bool, payload: MigrationTriageReq) -> dict:
    mig.run_status(run_id)
    n = 0
    if payload.ids:
        for iid in payload.ids:
            mig.set_decision(iid, approved)
            n += 1
    else:
        n = mig.bulk_decide(run_id, approved, group=payload.group)
    return {"ok": True, "decided": n, "approved": approved}


@router.post("/migration/runs/{run_id}/items/approve")
def migration_approve(run_id: int, payload: MigrationTriageReq):
    try:
        return _mig_triage(run_id, True, payload)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/migration/runs/{run_id}/items/reject")
def migration_reject(run_id: int, payload: MigrationTriageReq):
    try:
        return _mig_triage(run_id, False, payload)
    except ValueError as e:
        raise HTTPException(404, str(e))


# ── cleanup (stateless preview → explicit confirmed apply) ───────────────────
class CleanupApplyReq(BaseModel):
    actions: list[dict] = Field(min_length=1)      # echoed proposals the owner confirmed


def _cleanup_proposals() -> list[dict]:
    """Deterministic recommendations. Nothing here mutates — apply is separate
    and takes the owner-confirmed proposals back explicitly."""
    c = repo._conn(None)
    out: list[dict] = []
    active = repo.list_memories(MemoryStatus.ACTIVE, conn=c)
    # near-duplicate actives (same type/scope) → merge proposal
    for i, a in enumerate(active):
        for b in active[i + 1:]:
            if a.memory_type is b.memory_type and a.scope_key == b.scope_key \
                    and not a.redacted and not b.redacted \
                    and text_similarity(a.distilled_text, b.distilled_text) >= MERGE_AT:
                out.append({"action": "merge", "keep_id": a.id, "merge_id": b.id,
                            "reason": "near-duplicate active memories"})
    # aged pending (>30 days) → archive proposal
    for r in c.execute("SELECT id FROM brain_memory_v2 WHERE status='pending' "
                       "AND created_at <= datetime('now','-30 days')").fetchall():
        out.append({"action": "archive", "memory_id": r["id"], "reason": "pending > 30 days"})
    # wrong-heavy actives → revalidate proposal (owner re-review, not deletion)
    for m in active:
        if fb.usefulness(m.id, conn=c) <= 0.2:
            out.append({"action": "revalidate", "memory_id": m.id,
                        "reason": "owner feedback marks this memory wrong/unhelpful"})
    return out


@router.post("/cleanup/preview")
def cleanup_preview():
    return {"proposals": _cleanup_proposals()}


@router.post("/cleanup/apply")
def cleanup_apply(payload: CleanupApplyReq):
    """Apply only the proposals the owner sent back (spec: no destructive
    proposal applies without confirmation). merge → archive the extra row with
    a supersedes-style evidence note; archive/revalidate → status changes only."""
    applied = 0
    try:
        for act in payload.actions:
            kind = act.get("action")
            if kind == "merge" and act.get("keep_id") and act.get("merge_id"):
                repo.add_evidence(int(act["keep_id"]),
                                  excerpt="", source_ref=f"merged-from:{act['merge_id']}")
                repo.set_status(int(act["merge_id"]), MemoryStatus.ARCHIVED)
                applied += 1
            elif kind == "archive" and act.get("memory_id"):
                repo.set_status(int(act["memory_id"]), MemoryStatus.ARCHIVED)
                applied += 1
            elif kind == "revalidate" and act.get("memory_id"):
                repo.set_status(int(act["memory_id"]), MemoryStatus.PENDING)
                applied += 1
            else:
                raise ValueError(f"unknown cleanup action: {act}")
    except Exception as e:
        raise _http(e)
    return {"ok": True, "applied": applied}

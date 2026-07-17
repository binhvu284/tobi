"""
BRAIN MEMORY V2 — resumable dry-run import jobs (#20 / spec §Import flow, T05).

TXT/MD/JSON only, ≤10 MiB and ≤2M normalized chars. Always dry-run first: chunks
(~3,500 chars, structure-aware) are extracted into triage candidates with a
previewed outcome — nothing touches the memory store until the owner commits
approved candidates. Progress checkpoints per chunk in ``brain_ingestion_jobs``
so a process restart resumes exactly where it stopped (``step_job`` is the whole
worker contract: call it until the job is ready).

Security: creating a job requires an unlocked vault; the upload is stored only
AES-GCM-encrypted (purpose-bound per job). Sensitive candidates are encrypted in
the triage table too. Temp payloads are purged on commit/cancel and expired
after 24 hours. Everything extracted here is pinned ``trust=untrusted`` — an
import can never create an active hard rule (spec §gates 7).
"""
from __future__ import annotations

import json
import logging
import re
import sqlite3
from dataclasses import replace
from typing import Callable, Optional

from core import vault
from core import brain_repository as repo
from core.brain_contracts import MemoryCandidate, Trust
from core.brain_ingest import candidate_from_dict, ingest, preview

logger = logging.getLogger("tobi.brain_v2")

ALLOWED_EXTS = {".txt", ".md", ".json"}
MAX_BYTES = 10 * 1024 * 1024
MAX_CHARS = 2_000_000
CHUNK_CHARS = 3500
JOB_TTL_HOURS = 24

REDACTED_CANDIDATE = {"distilled_text": "[sensitive:locked]", "sensitive": True}


# ── normalize + chunk (pure, deterministic — chunk i is always the same) ─────
def normalize_text(raw: bytes | str) -> str:
    text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
    return text.replace("\r\n", "\n").replace("\r", "\n")


def chunk_text(text: str, size: int = CHUNK_CHARS) -> list[str]:
    """Structure-aware ~`size`-char chunks: split on blank lines / headings,
    pack paragraphs greedily, hard-split only paragraphs larger than a chunk."""
    parts: list[str] = []
    for para in re.split(r"\n(?=#{1,6} )|\n\s*\n", text):
        para = para.strip()
        if not para:
            continue
        while len(para) > size:  # oversized paragraph: hard split at a space if possible
            cut = para.rfind(" ", size // 2, size)
            cut = cut if cut > 0 else size
            parts.append(para[:cut].strip())
            para = para[cut:].strip()
        if para:
            parts.append(para)
    chunks: list[str] = []
    buf = ""
    for p in parts:
        if buf and len(buf) + len(p) + 2 > size:
            chunks.append(buf)
            buf = p
        else:
            buf = f"{buf}\n\n{p}" if buf else p
    if buf:
        chunks.append(buf)
    return chunks


# ── extraction (cheap structured model, one escalation; stubbable) ───────────
_CHUNK_PROMPT = """Extract durable owner memories from this imported text. Reply with ONLY a JSON
array (possibly empty) of objects with keys: distilled_text, memory_type (fact, identity,
preference, correction, behavior_rule, workflow_standard, frustration_trigger, decision,
project_context, relationship), tags (list), confidence (0-1), durability, actionability,
specificity, source_strength, novelty, future_usefulness (each 0-1), sensitive (bool),
evidence_excerpt (short quote, <=320 chars). Skip chit-chat and one-off noise.

Text:
{chunk}"""


def default_extractor(chunk: str) -> list[dict]:
    """Cheap structured-output model first, at most one stronger escalation for
    malformed output (spec §Import flow). Returns raw dicts — validation happens
    at candidate_from_dict, never here."""
    from core import brain
    for task_type in ("classify", "simple"):          # cheap → one escalation
        raw = brain._llm(_CHUNK_PROMPT.format(chunk=chunk[:CHUNK_CHARS]),
                         max_tokens=1200, task_type=task_type)
        if not raw:
            continue
        parsed = brain._parse_json(raw)
        if isinstance(parsed, list):
            return [p for p in parsed if isinstance(p, dict)]
    return []


extract_chunk: Callable[[str], list[dict]] = default_extractor  # tests may stub


# ── helpers ──────────────────────────────────────────────────────────────────
def _conn(conn: Optional[sqlite3.Connection]) -> sqlite3.Connection:
    return conn if conn is not None else repo._conn(None)


def _job(c: sqlite3.Connection, job_id: int) -> sqlite3.Row:
    row = c.execute("SELECT * FROM brain_ingestion_jobs WHERE id=?", (job_id,)).fetchone()
    if row is None:
        raise ValueError(f"no such import job: {job_id}")
    return row


def _touch(c: sqlite3.Connection, job_id: int, **fields) -> None:
    sets = ", ".join(f"{k}=?" for k in fields)
    c.execute(f"UPDATE brain_ingestion_jobs SET {sets}, updated_at=CURRENT_TIMESTAMP WHERE id=?",
              (*fields.values(), job_id))
    c.commit()


def _purge_payload(c: sqlite3.Connection, job_id: int) -> None:
    c.execute("PRAGMA secure_delete = ON")
    c.execute("UPDATE brain_ingestion_jobs SET payload_ct=NULL, payload_nonce=NULL WHERE id=?", (job_id,))
    c.commit()


def _pin_import(cand: MemoryCandidate) -> MemoryCandidate:
    """Imported content is third-party evidence: untrusted + inferred-by-default
    floor does NOT apply (imports may reject freely — unlike explicit Remember)."""
    return replace(cand, trust=Trust.UNTRUSTED, source_ref=cand.source_ref)


# ── job lifecycle ─────────────────────────────────────────────────────────────
def create_job(filename: str, content: bytes | str,
               conn: Optional[sqlite3.Connection] = None) -> int:
    """Validate, encrypt, and register an import upload. Requires an unlocked
    vault (spec: uploads use encrypted temporary storage) — fails closed."""
    ext = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
    if ext not in ALLOWED_EXTS:
        raise ValueError(f"unsupported import type {ext or '(none)'} — allowed: txt, md, json")
    raw_bytes = content.encode("utf-8") if isinstance(content, str) else content
    if len(raw_bytes) > MAX_BYTES:
        raise ValueError(f"upload exceeds {MAX_BYTES // (1024*1024)} MiB")
    text = normalize_text(raw_bytes)
    if len(text) > MAX_CHARS:
        raise ValueError(f"upload exceeds {MAX_CHARS:,} normalized characters")
    if not text.strip():
        raise ValueError("upload is empty")
    if not vault.can_encrypt_payloads():
        raise vault.VaultLocked("Vault must be unlocked to import (encrypted temp storage).")

    c = _conn(conn)
    total = len(chunk_text(text))
    cur = c.execute(
        "INSERT INTO brain_ingestion_jobs (filename, status, total_chunks) VALUES (?, 'dry_run', ?)",
        (filename, total))
    job_id = int(cur.lastrowid)
    purpose = f"brain.import:{job_id}"
    ct, nonce = vault.encrypt_payload(purpose, text)
    _touch(c, job_id, payload_ct=ct, payload_nonce=nonce, payload_purpose=purpose)
    return job_id


def step_job(job_id: int, conn: Optional[sqlite3.Connection] = None) -> dict:
    """Process exactly one chunk (the bounded-worker unit). Persisted checkpoint:
    safe to call from a fresh process after a restart. Returns job status."""
    c = _conn(conn)
    job = _job(c, job_id)
    if job["status"] != "dry_run":
        return job_status(job_id, conn=c)
    if job["payload_ct"] is None:
        _touch(c, job_id, status="failed", error="payload missing (purged or expired)")
        return job_status(job_id, conn=c)
    try:
        text = vault.decrypt_payload(job["payload_purpose"], job["payload_ct"], job["payload_nonce"])
    except vault.VaultLocked:
        # not an error — the worker simply waits for an unlocked vault
        return job_status(job_id, conn=c)

    chunks = chunk_text(text)
    i = job["next_chunk"]
    if i >= len(chunks):
        _touch(c, job_id, status="ready")
        return job_status(job_id, conn=c)

    for raw in extract_chunk(chunks[i]):
        try:
            cand = _pin_import(candidate_from_dict(raw))
        except (ValueError, TypeError) as e:
            c.execute("INSERT INTO brain_ingestion_candidates (job_id, chunk_index, error) VALUES (?,?,?)",
                      (job_id, i, str(e)[:300]))
            continue
        pv = preview(cand, conn=c)   # dry-run: never writes to the memory store
        payload = json.dumps(_candidate_dict(cand), ensure_ascii=False)
        if cand.sensitive:
            ct, nonce = vault.encrypt_payload(f"brain.import.cand:{job_id}:{i}", payload)
            c.execute(
                "INSERT INTO brain_ingestion_candidates (job_id, chunk_index, sensitive, enc_ct, enc_nonce,"
                " proposed_outcome, proposed_status, matched_id) VALUES (?,?,?,?,?,?,?,?)",
                (job_id, i, 1, ct, nonce, pv.outcome, pv.status.value if pv.status else None, pv.matched_id))
        else:
            c.execute(
                "INSERT INTO brain_ingestion_candidates (job_id, chunk_index, candidate_json,"
                " proposed_outcome, proposed_status, matched_id) VALUES (?,?,?,?,?,?)",
                (job_id, i, payload, pv.outcome, pv.status.value if pv.status else None, pv.matched_id))
    done = i + 1 >= len(chunks)
    _touch(c, job_id, next_chunk=i + 1, **({"status": "ready"} if done else {}))
    return job_status(job_id, conn=c)


def run_job(job_id: int, conn: Optional[sqlite3.Connection] = None,
            max_steps: Optional[int] = None) -> dict:
    """Drive step_job until the dry-run finishes (or max_steps — the bounded
    worker budget). Idempotent across restarts."""
    c = _conn(conn)
    steps, prev_chunk = 0, -1
    while True:
        st = step_job(job_id, conn=c)
        steps += 1
        if st["status"] != "dry_run" or (max_steps is not None and steps >= max_steps):
            return st
        if st["next_chunk"] == prev_chunk:  # no progress (e.g. locked vault) — stop, resume later
            return st
        prev_chunk = st["next_chunk"]


def job_status(job_id: int, conn: Optional[sqlite3.Connection] = None) -> dict:
    c = _conn(conn)
    j = _job(c, job_id)
    by_outcome = {r[0]: r[1] for r in c.execute(
        "SELECT proposed_outcome, count(*) FROM brain_ingestion_candidates "
        "WHERE job_id=? AND error IS NULL GROUP BY proposed_outcome", (job_id,)).fetchall()}
    errors = c.execute("SELECT count(*) FROM brain_ingestion_candidates WHERE job_id=? AND error IS NOT NULL",
                       (job_id,)).fetchone()[0]
    return {"id": job_id, "filename": j["filename"], "status": j["status"],
            "total_chunks": j["total_chunks"], "next_chunk": j["next_chunk"],
            "progress": round(j["next_chunk"] / j["total_chunks"], 3) if j["total_chunks"] else 1.0,
            "candidates_by_outcome": by_outcome, "extraction_errors": errors, "error": j["error"]}


def cancel_job(job_id: int, conn: Optional[sqlite3.Connection] = None) -> None:
    """Cancel + clean encrypted temp data AND triage candidates (spec: deleted
    after commit/cancel)."""
    c = _conn(conn)
    _job(c, job_id)
    c.execute("PRAGMA secure_delete = ON")
    c.execute("DELETE FROM brain_ingestion_candidates WHERE job_id=?", (job_id,))
    _touch(c, job_id, status="cancelled")
    _purge_payload(c, job_id)


def retry_job(job_id: int, conn: Optional[sqlite3.Connection] = None) -> dict:
    """Put a failed job back into dry_run at its checkpoint."""
    c = _conn(conn)
    if _job(c, job_id)["status"] != "failed":
        raise ValueError("only failed jobs can be retried")
    _touch(c, job_id, status="dry_run", error=None)
    return job_status(job_id, conn=c)


def expire_jobs(conn: Optional[sqlite3.Connection] = None, ttl_hours: int = JOB_TTL_HOURS) -> int:
    """Purge encrypted payloads of stale uncommitted jobs (>24h). Returns count."""
    c = _conn(conn)
    rows = c.execute(
        "SELECT id FROM brain_ingestion_jobs WHERE payload_ct IS NOT NULL "
        "AND created_at <= datetime('now', ?)", (f"-{int(ttl_hours)} hours",)).fetchall()
    for (jid,) in rows:
        _purge_payload(c, jid)
        _touch(c, jid, status="failed", error="expired (24h temp-data limit)")
    return len(rows)


# ── triage ────────────────────────────────────────────────────────────────────
def list_candidates(job_id: int, conn: Optional[sqlite3.Connection] = None) -> list[dict]:
    """Triage view. Sensitive candidates decrypt only while the vault is
    unlocked; locked they show a redaction stub (never the content)."""
    c = _conn(conn)
    out = []
    for r in c.execute("SELECT * FROM brain_ingestion_candidates WHERE job_id=? ORDER BY id",
                       (job_id,)).fetchall():
        if r["error"]:
            cand = None
        elif r["sensitive"]:
            try:
                cand = json.loads(vault.decrypt_payload(
                    f"brain.import.cand:{job_id}:{r['chunk_index']}", r["enc_ct"], r["enc_nonce"]))
            except vault.VaultLocked:
                cand = dict(REDACTED_CANDIDATE)
        else:
            cand = json.loads(r["candidate_json"])
        out.append({"id": r["id"], "chunk_index": r["chunk_index"], "candidate": cand,
                    "sensitive": bool(r["sensitive"]), "proposed_outcome": r["proposed_outcome"],
                    "proposed_status": r["proposed_status"], "matched_id": r["matched_id"],
                    "approved": None if r["approved"] is None else bool(r["approved"]),
                    "applied_memory_id": r["applied_memory_id"], "error": r["error"]})
    return out


def set_decision(candidate_id: int, approved: bool,
                 conn: Optional[sqlite3.Connection] = None) -> None:
    """Individual triage decision — overrides any earlier bulk decision."""
    c = _conn(conn)
    c.execute("UPDATE brain_ingestion_candidates SET approved=? WHERE id=?",
              (int(bool(approved)), candidate_id))
    c.commit()


def bulk_decide(job_id: int, approved: bool, only_outcome: Optional[str] = None,
                conn: Optional[sqlite3.Connection] = None) -> int:
    """Bulk approve/reject (optionally one proposed outcome). Individual
    exceptions stay editable afterwards via set_decision."""
    c = _conn(conn)
    if only_outcome:
        cur = c.execute("UPDATE brain_ingestion_candidates SET approved=? WHERE job_id=? "
                        "AND proposed_outcome=? AND error IS NULL",
                        (int(bool(approved)), job_id, only_outcome))
    else:
        cur = c.execute("UPDATE brain_ingestion_candidates SET approved=? WHERE job_id=? AND error IS NULL",
                        (int(bool(approved)), job_id))
    c.commit()
    return cur.rowcount


def commit_job(job_id: int, conn: Optional[sqlite3.Connection] = None) -> dict:
    """Apply APPROVED candidates through the real ingest engine (still gated —
    approval feeds them in, it does not force activation), then purge the
    encrypted upload. Requires the dry-run to be complete."""
    c = _conn(conn)
    job = _job(c, job_id)
    if job["status"] != "ready":
        raise ValueError(f"job is {job['status']} — commit requires a completed dry-run (ready)")
    applied, skipped = 0, 0
    for item in list_candidates(job_id, conn=c):
        if item["error"] or item["approved"] is not True:
            skipped += 0 if item["error"] else 1
            continue
        cand_dict = item["candidate"]
        if cand_dict.get("distilled_text") == REDACTED_CANDIDATE["distilled_text"]:
            raise vault.VaultLocked("Vault must be unlocked to commit sensitive candidates.")
        cand = _pin_import(candidate_from_dict(cand_dict))
        res = ingest(cand, conn=c)
        c.execute("UPDATE brain_ingestion_candidates SET applied_memory_id=? WHERE id=?",
                  (res.memory_id, item["id"]))
        applied += 1
    c.commit()
    _touch(c, job_id, status="committed")
    _purge_payload(c, job_id)
    return {"applied": applied, "skipped": skipped, **job_status(job_id, conn=c)}


def _candidate_dict(cand: MemoryCandidate) -> dict:
    """Serialize a validated candidate for triage storage (round-trips through
    candidate_from_dict on commit)."""
    return {
        "distilled_text": cand.distilled_text, "memory_type": cand.memory_type.value,
        "behavior_implication": cand.behavior_implication, "tags": list(cand.tags),
        "scope_type": cand.scope_type.value, "scope_key": cand.scope_key,
        "authority": cand.authority.value, "explicitness": cand.explicitness.value,
        "confidence": cand.confidence, "durability": cand.durability,
        "actionability": cand.actionability, "specificity": cand.specificity,
        "source_strength": cand.source_strength, "novelty": cand.novelty,
        "future_usefulness": cand.future_usefulness, "quality_score": cand.quality_score,
        "suggested_usage": cand.suggested_usage, "evidence_excerpt": cand.evidence_excerpt,
        "source_ref": cand.source_ref, "trust": cand.trust.value, "sensitive": cand.sensitive,
    }

"""
BRAIN MEMORY V2 — legacy reclassification preview + owner-approved migration
(#20 / spec §Migration Plan, task T06).

Scans legacy ``brain_memories`` (read-only — no legacy row is ever modified)
into grouped V2 proposals: reclassify / duplicate / conflict / sensitive /
noise, per the spec's recommended mappings. The owner reviews and approves;
apply then creates V2 rows through the real ingest engine with ``compat_ref``
back to each legacy id. The run row is the migration ledger and the resume
checkpoint — both preview and apply survive a process restart.

Deterministic by design (spec step 3: deterministic fields need no model
inference): legacy category → type, source → explicitness, and a content
heuristic for quality dims. Sensitive proposals are vault-encrypted in the
preview table (unlocked vault required to start a run — fails closed).
"""
from __future__ import annotations

import json
import logging
import sqlite3
from typing import Optional

from core import vault
from core import brain_repository as repo
from core.brain_contracts import MemoryCandidate, MemoryType, Explicitness, Trust
from core.brain_ingest import (
    candidate_from_dict, ingest, preview, text_similarity, MERGE_AT, CONFLICT_AT,
)
from core.brain_remember_v2 import CATEGORY_TO_TYPE, _SENSITIVE_RE
from core.brain_import import _candidate_dict, REDACTED_CANDIDATE

logger = logging.getLogger("tobi.brain_v2")

EXPLICIT_SOURCES = {"remember", "manual"}   # owner-stated; auto/import → inferred


# ── deterministic legacy row → candidate mapping (no model) ──────────────────
def legacy_candidate(row: sqlite3.Row) -> MemoryCandidate:
    content = (row["content"] or "").strip()
    words = len(content.split())
    explicit = (row["source"] or "") in EXPLICIT_SOURCES
    noise = words < 4
    sensitive = bool(_SENSITIVE_RE.search(content)) or row["category"] == "health"
    return MemoryCandidate(
        distilled_text=content,
        memory_type=CATEGORY_TO_TYPE.get(row["category"] or "", MemoryType.FACT),
        tags=(row["category"],) if row["category"] else (),
        explicitness=Explicitness.EXPLICIT if explicit else Explicitness.INFERRED,
        confidence=min(1.0, max(0.0, row["confidence"] if row["confidence"] is not None else 0.6)),
        durability=0.1 if noise else 0.8,
        actionability=0.1 if noise else 0.5,
        specificity=min(1.0, words / 8),               # ~8 words = a fully specific owner fact
        source_strength=0.9 if explicit else 0.5,
        novelty=0.2 if noise else 0.5,
        future_usefulness=0.2 if noise else 0.6,       # noise lands < 35 → reject proposal
        trust=Trust.TRUSTED,                       # legacy content is the owner's own store
        sensitive=sensitive,
        source_ref=f"legacy:{row['id']}",
    )


def _group_for(cand: MemoryCandidate, pv_outcome: str,
               intra: Optional[tuple[str, int]]) -> tuple[str, Optional[int]]:
    """Spec mapping order: sensitive → duplicate → conflict → noise → reclassify."""
    if cand.sensitive:
        return "sensitive", intra[1] if intra else None
    if intra and intra[0] == "duplicate":
        return "duplicate", intra[1]
    if pv_outcome == "merged":
        return "duplicate", None
    if (intra and intra[0] == "conflict") or pv_outcome == "conflicted":
        return "conflict", intra[1] if intra else None
    if pv_outcome == "rejected":
        return "noise", None
    return "reclassify", None


# ── run lifecycle ─────────────────────────────────────────────────────────────
def _conn(conn: Optional[sqlite3.Connection]) -> sqlite3.Connection:
    return conn if conn is not None else repo._conn(None)


def _run(c: sqlite3.Connection, run_id: int) -> sqlite3.Row:
    row = c.execute("SELECT * FROM brain_migration_runs WHERE id=?", (run_id,)).fetchone()
    if row is None:
        raise ValueError(f"no such migration run: {run_id}")
    return row


def _touch(c: sqlite3.Connection, run_id: int, **fields) -> None:
    sets = ", ".join(f"{k}=?" for k in fields)
    c.execute(f"UPDATE brain_migration_runs SET {sets}, updated_at=CURRENT_TIMESTAMP WHERE id=?",
              (*fields.values(), run_id))
    c.commit()


def snapshot(conn: Optional[sqlite3.Connection] = None) -> dict:
    """Spec step 1: current Brain counts/statuses, recorded in the ledger."""
    c = _conn(conn)
    legacy_by_status = {r[0]: r[1] for r in c.execute(
        "SELECT status, count(*) FROM brain_memories WHERE deleted_at IS NULL GROUP BY status").fetchall()}
    legacy_by_cat = {r[0]: r[1] for r in c.execute(
        "SELECT category, count(*) FROM brain_memories WHERE deleted_at IS NULL GROUP BY category").fetchall()}
    v2 = c.execute("SELECT count(*) FROM brain_memory_v2").fetchone()[0]
    return {"legacy_by_status": legacy_by_status, "legacy_by_category": legacy_by_cat, "v2_rows": v2}


def create_run(conn: Optional[sqlite3.Connection] = None) -> int:
    """Start a preview run over all non-deleted legacy memories. Requires an
    unlocked vault (sensitive proposals must be encryptable) — fails closed."""
    if not vault.can_encrypt_payloads():
        raise vault.VaultLocked("Vault must be unlocked to run a migration preview.")
    c = _conn(conn)
    total = c.execute("SELECT count(*) FROM brain_memories WHERE deleted_at IS NULL").fetchone()[0]
    cur = c.execute("INSERT INTO brain_migration_runs (status, snapshot_json, total_legacy) VALUES "
                    "('preview', ?, ?)", (json.dumps(snapshot(conn=c), ensure_ascii=False), total))
    c.commit()
    return int(cur.lastrowid)


def _intra_match(c: sqlite3.Connection, run_id: int,
                 cand: MemoryCandidate) -> Optional[tuple[str, int]]:
    """Duplicate/conflict against rows already scanned in THIS run (they are not
    in the V2 store yet, so preview() can't see them). Sensitive items are
    compared too — their plaintext is in memory here, never persisted."""
    rows = c.execute(
        "SELECT legacy_id, candidate_json, enc_ct, enc_nonce, run_id, id FROM brain_migration_items "
        "WHERE run_id=? AND error IS NULL", (run_id,)).fetchall()
    for r in rows:
        try:
            if r["candidate_json"]:
                other = json.loads(r["candidate_json"])
            else:
                other = json.loads(vault.decrypt_payload(
                    f"brain.migrate.item:{run_id}:{r['legacy_id']}", r["enc_ct"], r["enc_nonce"]))
        except Exception:
            continue
        if other.get("memory_type") != cand.memory_type.value:
            continue
        if (other.get("scope_type") or "global") != cand.scope_type.value:
            continue
        s = text_similarity(cand.distilled_text, other.get("distilled_text") or "")
        if s >= MERGE_AT:
            return "duplicate", r["legacy_id"]
        if s >= CONFLICT_AT:
            return "conflict", r["legacy_id"]
    return None


def step_run(run_id: int, conn: Optional[sqlite3.Connection] = None) -> dict:
    """Preview exactly one legacy row (checkpointed — restart-safe)."""
    c = _conn(conn)
    run = _run(c, run_id)
    if run["status"] != "preview":
        return run_status(run_id, conn=c)
    row = c.execute(
        "SELECT * FROM brain_memories WHERE deleted_at IS NULL AND id > ? ORDER BY id LIMIT 1",
        (run["next_legacy_id"],)).fetchone()
    if row is None:
        _touch(c, run_id, status="ready")
        return run_status(run_id, conn=c)

    try:
        cand = legacy_candidate(row)
        pv = preview(cand, conn=c)
        intra = _intra_match(c, run_id, cand)
        group, matched_legacy = _group_for(cand, pv.outcome, intra)
        payload = json.dumps(_candidate_dict(cand), ensure_ascii=False)
        if cand.sensitive:
            ct, nonce = vault.encrypt_payload(f"brain.migrate.item:{run_id}:{row['id']}", payload)
            c.execute(
                "INSERT INTO brain_migration_items (run_id, legacy_id, group_kind, sensitive, enc_ct,"
                " enc_nonce, proposed_outcome, proposed_status, matched_legacy_id) VALUES (?,?,?,?,?,?,?,?,?)",
                (run_id, row["id"], group, 1, ct, nonce, pv.outcome,
                 pv.status.value if pv.status else None, matched_legacy))
        else:
            c.execute(
                "INSERT INTO brain_migration_items (run_id, legacy_id, group_kind, candidate_json,"
                " proposed_outcome, proposed_status, matched_legacy_id) VALUES (?,?,?,?,?,?,?)",
                (run_id, row["id"], group, payload, pv.outcome,
                 pv.status.value if pv.status else None, matched_legacy))
    except Exception as e:  # a bad legacy row must not sink the run
        c.execute("INSERT INTO brain_migration_items (run_id, legacy_id, error) VALUES (?,?,?)",
                  (run_id, row["id"], str(e)[:300]))
    _touch(c, run_id, next_legacy_id=row["id"])
    return run_status(run_id, conn=c)


def run_preview(run_id: int, conn: Optional[sqlite3.Connection] = None,
                max_steps: Optional[int] = None) -> dict:
    c = _conn(conn)
    steps, prev = 0, -1
    while True:
        st = step_run(run_id, conn=c)
        steps += 1
        if st["status"] != "preview" or (max_steps is not None and steps >= max_steps):
            return st
        if st["next_legacy_id"] == prev:
            return st
        prev = st["next_legacy_id"]


def run_status(run_id: int, conn: Optional[sqlite3.Connection] = None) -> dict:
    c = _conn(conn)
    run = _run(c, run_id)
    groups = {r[0]: r[1] for r in c.execute(
        "SELECT group_kind, count(*) FROM brain_migration_items WHERE run_id=? AND error IS NULL "
        "GROUP BY group_kind", (run_id,)).fetchall()}
    scanned = c.execute("SELECT count(*) FROM brain_migration_items WHERE run_id=?", (run_id,)).fetchone()[0]
    applied = c.execute("SELECT count(*) FROM brain_migration_items WHERE run_id=? AND applied_memory_id "
                        "IS NOT NULL", (run_id,)).fetchone()[0]
    errors = c.execute("SELECT count(*) FROM brain_migration_items WHERE run_id=? AND error IS NOT NULL",
                       (run_id,)).fetchone()[0]
    return {"id": run_id, "status": run["status"], "total_legacy": run["total_legacy"],
            "scanned": scanned, "next_legacy_id": run["next_legacy_id"], "groups": groups,
            "applied": applied, "errors": errors,
            "snapshot": json.loads(run["snapshot_json"]) if run["snapshot_json"] else None}


# ── triage (grouped decisions, individually editable) ────────────────────────
def list_items(run_id: int, group: Optional[str] = None,
               conn: Optional[sqlite3.Connection] = None) -> list[dict]:
    c = _conn(conn)
    q = "SELECT * FROM brain_migration_items WHERE run_id=?"
    args: list = [run_id]
    if group:
        q += " AND group_kind=?"
        args.append(group)
    out = []
    for r in c.execute(q + " ORDER BY id", args).fetchall():
        if r["error"]:
            cand = None
        elif r["sensitive"]:
            try:
                cand = json.loads(vault.decrypt_payload(
                    f"brain.migrate.item:{run_id}:{r['legacy_id']}", r["enc_ct"], r["enc_nonce"]))
            except vault.VaultLocked:
                cand = dict(REDACTED_CANDIDATE)
        else:
            cand = json.loads(r["candidate_json"])
        out.append({"id": r["id"], "legacy_id": r["legacy_id"], "group": r["group_kind"],
                    "candidate": cand, "sensitive": bool(r["sensitive"]),
                    "proposed_outcome": r["proposed_outcome"], "proposed_status": r["proposed_status"],
                    "matched_legacy_id": r["matched_legacy_id"],
                    "approved": None if r["approved"] is None else bool(r["approved"]),
                    "applied_memory_id": r["applied_memory_id"], "error": r["error"]})
    return out


def set_decision(item_id: int, approved: bool, run_id: Optional[int] = None,
                 conn: Optional[sqlite3.Connection] = None) -> int:
    """Individual triage decision. Security (#20 review P1): when ``run_id`` is
    given the update is scoped to that run, so an item id from another run cannot
    be decided through this run's endpoint. Returns rows changed (0 = not in run)."""
    c = _conn(conn)
    if run_id is not None:
        cur = c.execute("UPDATE brain_migration_items SET approved=? WHERE id=? AND run_id=?",
                        (int(bool(approved)), item_id, run_id))
    else:
        cur = c.execute("UPDATE brain_migration_items SET approved=? WHERE id=?",
                        (int(bool(approved)), item_id))
    c.commit()
    return cur.rowcount


def bulk_decide(run_id: int, approved: bool, group: Optional[str] = None,
                conn: Optional[sqlite3.Connection] = None) -> int:
    c = _conn(conn)
    if group:
        cur = c.execute("UPDATE brain_migration_items SET approved=? WHERE run_id=? AND group_kind=? "
                        "AND error IS NULL", (int(bool(approved)), run_id, group))
    else:
        cur = c.execute("UPDATE brain_migration_items SET approved=? WHERE run_id=? AND error IS NULL",
                        (int(bool(approved)), run_id))
    c.commit()
    return cur.rowcount


# ── apply (approved batches only; resumable; legacy rows untouched) ──────────
def apply_run(run_id: int, conn: Optional[sqlite3.Connection] = None,
              max_items: Optional[int] = None) -> dict:
    """Create V2 rows for approved items through the real engine, compat_ref =
    the legacy id. Items already applied are skipped (the resume guard), so an
    interrupted apply just runs again. Legacy rows are never written."""
    c = _conn(conn)
    run = _run(c, run_id)
    if run["status"] not in ("ready", "applied"):
        raise ValueError(f"run is {run['status']} — apply requires a completed preview (ready)")
    done = 0
    for item in list_items(run_id, conn=c):
        if max_items is not None and done >= max_items:
            break
        if item["error"] or item["approved"] is not True or item["applied_memory_id"] is not None:
            continue
        cand_dict = item["candidate"]
        if cand_dict.get("distilled_text") == REDACTED_CANDIDATE["distilled_text"]:
            raise vault.VaultLocked("Vault must be unlocked to apply sensitive migration items.")
        res = ingest(candidate_from_dict(cand_dict), conn=c, compat_ref=item["legacy_id"])
        c.execute("UPDATE brain_migration_items SET applied_memory_id=? WHERE id=?",
                  (res.memory_id, item["id"]))
        c.commit()   # per-item ledger write → interruption-safe
        done += 1
    remaining = c.execute(
        "SELECT count(*) FROM brain_migration_items WHERE run_id=? AND approved=1 "
        "AND applied_memory_id IS NULL AND error IS NULL", (run_id,)).fetchone()[0]
    applied_total = c.execute(
        "SELECT count(*) FROM brain_migration_items WHERE run_id=? AND applied_memory_id IS NOT NULL",
        (run_id,)).fetchone()[0]
    # Only finalize once something was actually applied — an apply with zero
    # approvals must NOT close the run and strand its undecided items.
    if remaining == 0 and applied_total > 0:
        _touch(c, run_id, status="applied")
    return {"applied_now": done, "remaining_approved": remaining, **run_status(run_id, conn=c)}


def cancel_run(run_id: int, conn: Optional[sqlite3.Connection] = None) -> None:
    c = _conn(conn)
    _run(c, run_id)
    c.execute("PRAGMA secure_delete = ON")
    c.execute("DELETE FROM brain_migration_items WHERE run_id=?", (run_id,))
    _touch(c, run_id, status="cancelled")

"""Legacy Brain interaction contract backed by the Brain V2 store.

The owner-facing Brain page is intentionally stable. This module translates its
existing API shapes to typed V2 records, while keeping non-sensitive legacy rows
as rollback mirrors. V2 is authoritative whenever ``brain.v2_enabled`` is on.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import sqlite3
from typing import Optional

from core import brain_repository as repo
from core import brain_remember_v2
from core import vault
from core.brain_contracts import (
    Explicitness, LinkType, MemoryCandidate, MemoryStatus, MemoryType, Trust,
)
from core.brain_ingest import MERGE_AT, ingest, text_similarity
from core.database import get_connection


CATEGORY_IDS = (
    "identity", "preferences", "psychology", "relationships",
    "goals", "work", "habits", "health",
)
STALE_DAYS = 90
DUPLICATE_AT = 0.86

_CATEGORY_TYPE = {
    "identity": MemoryType.IDENTITY,
    "preferences": MemoryType.PREFERENCE,
    "relationships": MemoryType.RELATIONSHIP,
    "goals": MemoryType.PROJECT_CONTEXT,
    "work": MemoryType.PROJECT_CONTEXT,
    "habits": MemoryType.FACT,
    "psychology": MemoryType.FACT,
    "health": MemoryType.FACT,
}
_TYPE_CATEGORY = {
    MemoryType.IDENTITY: "identity",
    MemoryType.PREFERENCE: "preferences",
    MemoryType.RELATIONSHIP: "relationships",
    MemoryType.PROJECT_CONTEXT: "work",
    MemoryType.WORKFLOW_STANDARD: "work",
    MemoryType.BEHAVIOR_RULE: "preferences",
    MemoryType.FRUSTRATION_TRIGGER: "psychology",
    MemoryType.DECISION: "work",
    MemoryType.CORRECTION: "identity",
    MemoryType.FACT: "identity",
}
_STATUS_FROM_LEGACY = {
    "active": MemoryStatus.ACTIVE,
    "pending": MemoryStatus.PENDING,
    "archived": MemoryStatus.ARCHIVED,
    "superseded": MemoryStatus.SUPERSEDED,
}


def _owns(conn: Optional[sqlite3.Connection]) -> tuple[sqlite3.Connection, bool]:
    return (conn, False) if conn is not None else (get_connection(), True)


def _ensure_schema(conn: sqlite3.Connection) -> None:
    required = {
        "brain_memory_v2",
        "brain_memory_v2_versions",
        "brain_memory_v2_conflict_resolutions",
        "brain_v2_cutover_state",
    }
    available = {
        str(row[0]) for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    missing = sorted(required - available)
    if missing:
        raise RuntimeError(
            "Brain V2 compatibility schema is not initialized: " + ", ".join(missing)
        )
    cols = {str(row[1]) for row in conn.execute("PRAGMA table_info(brain_memory_v2)")}
    if "last_confirmed_at" not in cols:
        raise RuntimeError("Brain V2 compatibility migration is not initialized")


def _normal_status(value: str) -> MemoryStatus:
    try:
        return MemoryStatus(value)
    except Exception:
        return MemoryStatus.PENDING


def _candidate(content: str, category: str, confidence: float, source: str) -> MemoryCandidate:
    category = category if category in CATEGORY_IDS else "identity"
    source = (source or "manual").strip().lower()
    base = brain_remember_v2.heuristic_candidate(content, category, source_ref=source)
    explicit = source in {"manual", "owner", "remember"} or source.startswith("manual")
    trust = Trust.UNTRUSTED if source.startswith("import") else Trust.TRUSTED
    tags = tuple(dict.fromkeys((*base.tags, category)))
    return replace(
        base,
        memory_type=_CATEGORY_TYPE.get(category, base.memory_type),
        tags=tags,
        explicitness=Explicitness.EXPLICIT if explicit else Explicitness.INFERRED,
        confidence=max(0.0, min(1.0, float(confidence))),
        trust=trust,
        source_ref=source,
    )


def _legacy_meta(conn: sqlite3.Connection, memory: repo.StoredMemory) -> Optional[sqlite3.Row]:
    if memory.compat_ref is None:
        return None
    return conn.execute("SELECT * FROM brain_memories WHERE id=?", (memory.compat_ref,)).fetchone()


def _category(memory: repo.StoredMemory, legacy: Optional[sqlite3.Row] = None) -> str:
    if legacy and legacy["category"]:
        return str(legacy["category"])
    for tag in memory.tags:
        if tag in CATEGORY_IDS:
            return tag
    return _TYPE_CATEGORY.get(memory.memory_type, "identity")


def _source(memory: repo.StoredMemory, legacy: Optional[sqlite3.Row] = None) -> str:
    if legacy and legacy["source"]:
        return str(legacy["source"])
    ref = next((e.source_ref for e in memory.evidence if e.source_ref), None) or "manual"
    if str(ref).startswith("legacy:"):
        return "legacy"
    return str(ref).split(":", 1)[0]


def _stale(reference: Optional[str]) -> bool:
    if not reference:
        return False
    try:
        dt = datetime.fromisoformat(str(reference).replace("Z", "").replace(" ", "T"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).days >= STALE_DAYS
    except Exception:
        return False


def _memory_dict(memory: repo.StoredMemory, conn: sqlite3.Connection) -> dict:
    legacy = _legacy_meta(conn, memory)
    row = conn.execute(
        "SELECT last_confirmed_at FROM brain_memory_v2 WHERE id=?", (memory.id,)
    ).fetchone()
    confirmed = (row["last_confirmed_at"] if row else None) or (
        legacy["last_confirmed_at"] if legacy else None
    )
    return {
        "id": memory.id,
        "content": memory.distilled_text,
        "category": _category(memory, legacy),
        "confidence": memory.confidence,
        "source": _source(memory, legacy),
        "status": memory.status.value,
        "context": memory.behavior_implication or None,
        "created_at": memory.created_at,
        "updated_at": memory.updated_at,
        "last_confirmed_at": confirmed,
        "stale": _stale(confirmed or memory.created_at),
        "has_embedding": bool(legacy and "embedding" in legacy.keys() and legacy["embedding"]),
        "redacted": memory.redacted,
    }


def _record_version(conn: sqlite3.Connection, memory: repo.StoredMemory,
                    change_kind: str, changed_by: str = "owner",
                    legacy_version_ref: Optional[int] = None,
                    created_at: Optional[str] = None) -> None:
    content = repo.REDACTED if memory.sensitive else memory.distilled_text
    conn.execute(
        "INSERT OR IGNORE INTO brain_memory_v2_versions "
        "(memory_id,content,category,confidence,change_kind,changed_by,legacy_version_ref,created_at) "
        "VALUES (?,?,?,?,?,?,?,COALESCE(?,CURRENT_TIMESTAMP))",
        (memory.id, content, _category(memory), memory.confidence,
         change_kind, changed_by, legacy_version_ref, created_at),
    )


def _copy_legacy_versions(conn: sqlite3.Connection, memory_id: int, legacy_id: int) -> None:
    rows = conn.execute(
        "SELECT * FROM brain_memory_versions WHERE memory_id=? ORDER BY id", (legacy_id,)
    ).fetchall()
    for row in rows:
        conn.execute(
            "INSERT OR IGNORE INTO brain_memory_v2_versions "
            "(memory_id,content,category,confidence,change_kind,changed_by,legacy_version_ref,created_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (memory_id, row["content"], row["category"], row["confidence"],
             row["change_kind"], row["changed_by"], row["id"], row["created_at"]),
        )


def _mirror(memory_id: int, change_kind: Optional[str] = None,
            changed_by: str = "owner", conn: Optional[sqlite3.Connection] = None) -> Optional[int]:
    c, own = _owns(conn)
    try:
        memory = repo.read(memory_id, conn=c)
        if memory is None:
            return None
        if memory.sensitive:
            # A row that becomes sensitive must not leave plaintext in either
            # the rollback mirror or its live compatibility history.
            c.execute(
                "UPDATE brain_memory_v2_versions SET content=? WHERE memory_id=?",
                (repo.REDACTED, memory_id),
            )
            if memory.compat_ref is not None:
                c.execute(
                    "UPDATE brain_memories SET content=?,context=NULL,embedding=NULL,embed_model=NULL,"
                    "status='archived',deleted_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (repo.REDACTED, memory.compat_ref),
                )
                c.execute(
                    "UPDATE brain_memory_versions SET content=? WHERE memory_id=?",
                    (repo.REDACTED, memory.compat_ref),
                )
                c.commit()
            return None
        category = _category(memory)
        source = _source(memory)
        legacy_status = "archived" if memory.status is MemoryStatus.REJECTED else memory.status.value
        legacy_id = memory.compat_ref
        row = c.execute("SELECT id FROM brain_memories WHERE id=?", (legacy_id,)).fetchone() if legacy_id else None
        if row:
            c.execute(
                "UPDATE brain_memories SET content=?,category=?,confidence=?,source=?,status=?,context=?,"
                "updated_at=CURRENT_TIMESTAMP,deleted_at=? WHERE id=?",
                (memory.distilled_text, category, memory.confidence, source, legacy_status,
                 memory.behavior_implication or None,
                 datetime.now(timezone.utc).isoformat() if legacy_status == "archived" else None,
                 legacy_id),
            )
        else:
            cur = c.execute(
                "INSERT INTO brain_memories "
                "(content,category,confidence,source,status,context,last_confirmed_at) "
                "VALUES (?,?,?,?,?,?,CURRENT_TIMESTAMP)",
                (memory.distilled_text, category, memory.confidence, source,
                 legacy_status, memory.behavior_implication or None),
            )
            legacy_id = int(cur.lastrowid)
            c.execute("UPDATE brain_memory_v2 SET compat_ref=? WHERE id=?", (legacy_id, memory_id))
            change_kind = change_kind or "create"
        if change_kind:
            c.execute(
                "INSERT INTO brain_memory_versions "
                "(memory_id,content,category,confidence,change_kind,changed_by) VALUES (?,?,?,?,?,?)",
                (legacy_id, memory.distilled_text, category, memory.confidence,
                 change_kind, changed_by),
            )
        c.commit()
        return int(legacy_id)
    finally:
        if own:
            c.close()


def record_change(memory_id: int, change_kind: str,
                  changed_by: str = "owner", mirror: bool = True) -> Optional[int]:
    """Record V2 history and refresh the non-sensitive rollback mirror."""
    c = get_connection()
    try:
        memory = repo.read(memory_id, conn=c)
        if memory is None:
            return None
        _record_version(c, memory, change_kind, changed_by)
        c.commit()
        return _mirror(memory_id, change_kind, changed_by, conn=c) if mirror else memory.compat_ref
    finally:
        c.close()


def ensure_ready(conn: Optional[sqlite3.Connection] = None) -> dict:
    """Idempotently preserve the legacy accepted set before V2 takes authority."""
    c, own = _owns(conn)
    migrated = 0
    skipped = 0
    try:
        _ensure_schema(c)
        state = c.execute("SELECT * FROM brain_v2_cutover_state WHERE id=1").fetchone()
        initial = not state or state["status"] != "complete"
        c.execute(
            "INSERT OR IGNORE INTO brain_v2_cutover_state (id,status) VALUES (1,'running')"
        )
        c.execute(
            "UPDATE brain_v2_cutover_state SET status='running',last_error=NULL,updated_at=CURRENT_TIMESTAMP WHERE id=1"
        )

        if initial:
            linked = c.execute(
                "SELECT v.id AS v2_id,l.id AS legacy_id,l.status,l.last_confirmed_at "
                "FROM brain_memory_v2 v JOIN brain_memories l ON l.id=v.compat_ref"
            ).fetchall()
            for row in linked:
                status = _STATUS_FROM_LEGACY.get(str(row["status"]), MemoryStatus.PENDING)
                c.execute(
                    "UPDATE brain_memory_v2 SET status=?,last_confirmed_at=COALESCE(last_confirmed_at,?) "
                    "WHERE id=?",
                    (status.value, row["last_confirmed_at"], row["v2_id"]),
                )
                _copy_legacy_versions(c, int(row["v2_id"]), int(row["legacy_id"]))

        missing = c.execute(
            "SELECT l.* FROM brain_memories l WHERE l.deleted_at IS NULL "
            "AND l.status IN ('active','pending') "
            "AND NOT EXISTS (SELECT 1 FROM brain_memory_v2 v WHERE v.compat_ref=l.id) "
            "ORDER BY l.id"
        ).fetchall()
        for row in missing:
            cand = _candidate(row["content"], row["category"] or "identity",
                              row["confidence"] or 0.6, row["source"] or "manual")
            try:
                memory_id = repo.save(
                    cand,
                    status=_STATUS_FROM_LEGACY.get(str(row["status"]), MemoryStatus.PENDING),
                    compat_ref=int(row["id"]), conn=c,
                )
            except vault.VaultLocked:
                skipped += 1
                continue
            c.execute(
                "UPDATE brain_memory_v2 SET created_at=?,updated_at=?,last_confirmed_at=? WHERE id=?",
                (row["created_at"], row["updated_at"], row["last_confirmed_at"], memory_id),
            )
            _copy_legacy_versions(c, memory_id, int(row["id"]))
            if cand.sensitive:
                _mirror(memory_id, conn=c)
            migrated += 1

        status = "complete" if skipped == 0 else "waiting_vault"
        c.execute(
            "UPDATE brain_v2_cutover_state SET status=?,migrated_count=migrated_count+?,"
            "skipped_sensitive=?,completed_at=CASE WHEN ?='complete' THEN CURRENT_TIMESTAMP ELSE NULL END,"
            "updated_at=CURRENT_TIMESTAMP WHERE id=1",
            (status, migrated, skipped, status),
        )
        c.commit()
        return {"status": status, "migrated": migrated, "skipped_sensitive": skipped}
    except Exception as exc:
        c.execute(
            "UPDATE brain_v2_cutover_state SET status='failed',last_error=?,updated_at=CURRENT_TIMESTAMP WHERE id=1",
            (f"{type(exc).__name__}: {str(exc)[:240]}",),
        )
        c.commit()
        raise
    finally:
        if own:
            c.close()


def list_memories(category: Optional[str] = None, source: Optional[str] = None,
                  status: str = "active", q: Optional[str] = None,
                  stale: Optional[bool] = None, limit: int = 500) -> list[dict]:
    ensure_ready()
    c = get_connection()
    try:
        wanted = None if not status or status == "all" else _normal_status(status)
        memories = repo.list_memories(wanted, conn=c)
        out = [_memory_dict(m, c) for m in memories]
        if category and category != "all":
            out = [item for item in out if item["category"] == category]
        if source and source != "all":
            out = [item for item in out if item["source"] == source]
        if q:
            needle = q.casefold().strip()
            out = [item for item in out if needle in item["content"].casefold()]
        if stale is True:
            out = [item for item in out if item["stale"]]
        out.sort(key=lambda item: (item["confidence"], item["updated_at"]), reverse=True)
        return out[:max(1, min(int(limit), 1000))]
    finally:
        c.close()


def get_memory(memory_id: int) -> Optional[dict]:
    ensure_ready()
    c = get_connection()
    try:
        memory = repo.read(memory_id, conn=c)
        return _memory_dict(memory, c) if memory else None
    finally:
        c.close()


def add_memory(content: str, category: str = "identity", confidence: float = 0.7,
               source: str = "manual", status: str = "active",
               context: Optional[str] = None, changed_by: str = "owner") -> int:
    ensure_ready()
    content = (content or "").strip()
    if not content:
        raise ValueError("Memory content cannot be empty")
    if len(content) > 2000:
        raise ValueError("Memory content exceeds the 2000 character limit")
    candidate = _candidate(content, category, confidence, source)
    if context:
        candidate = replace(candidate, behavior_implication=str(context)[:500])
    c = get_connection()
    try:
        memory_id = repo.save(candidate, status=_normal_status(status), conn=c)
        memory = repo.read(memory_id, conn=c)
        if memory:
            _record_version(c, memory, "create", changed_by)
        c.execute(
            "UPDATE brain_memory_v2 SET last_confirmed_at=CURRENT_TIMESTAMP WHERE id=?",
            (memory_id,),
        )
        c.commit()
        _mirror(memory_id, "create", changed_by, conn=c)
        return memory_id
    finally:
        c.close()


def update_memory(memory_id: int, content: Optional[str] = None,
                  category: Optional[str] = None, confidence: Optional[float] = None,
                  changed_by: str = "owner") -> Optional[dict]:
    ensure_ready()
    c = get_connection()
    try:
        current = repo.read(memory_id, conn=c)
        if current is None:
            return None
        next_content = (content.strip() if content is not None else current.distilled_text)
        if not next_content:
            raise ValueError("Memory content cannot be empty")
        next_category = category or _category(current, _legacy_meta(c, current))
        next_confidence = current.confidence if confidence is None else float(confidence)
        proposed = _candidate(next_content, next_category, next_confidence, _source(current))
        if proposed.sensitive and not current.sensitive:
            if not vault.can_encrypt_payloads():
                raise vault.VaultLocked("Unlock the vault before making this memory sensitive.")
            repo._store_secure(c, memory_id, "distilled_text", next_content)
            if current.behavior_implication:
                repo._store_secure(c, memory_id, "behavior_implication",
                                   current.behavior_implication)
            for evidence in current.evidence:
                if evidence.excerpt:
                    repo._store_secure(c, memory_id, f"evidence:{evidence.id}", evidence.excerpt)
                    c.execute("UPDATE brain_memory_evidence SET excerpt=? WHERE id=?",
                              (repo.REDACTED, evidence.id))
            c.execute(
                "UPDATE brain_memory_v2 SET sensitive=1,distilled_text=?,behavior_implication=?,memory_type=?,"
                "confidence=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (repo.REDACTED, repo.REDACTED if current.behavior_implication else "",
                 proposed.memory_type.value, next_confidence, memory_id),
            )
        else:
            repo.edit_fields(memory_id, distilled_text=next_content,
                             memory_type=proposed.memory_type, conn=c)
            repo.set_confidence(memory_id, next_confidence, conn=c)
        c.execute(
            "DELETE FROM brain_memory_tags WHERE memory_id=? AND tag IN (%s)" %
            ",".join("?" for _ in CATEGORY_IDS),
            (memory_id, *CATEGORY_IDS),
        )
        c.execute("INSERT INTO brain_memory_tags (memory_id,tag) VALUES (?,?)",
                  (memory_id, next_category if next_category in CATEGORY_IDS else "identity"))
        c.commit()
        updated = repo.read(memory_id, conn=c)
        if updated:
            _record_version(c, updated, "edit", changed_by)
            c.commit()
            _mirror(memory_id, "edit", changed_by, conn=c)
            return _memory_dict(updated, c)
        return None
    finally:
        c.close()


def delete_memory(memory_id: int) -> None:
    ensure_ready()
    c = get_connection()
    try:
        memory = repo.read(memory_id, conn=c)
        if memory is None:
            return
        repo.archive(memory_id, conn=c)
        archived = repo.read(memory_id, conn=c)
        if archived:
            _record_version(c, archived, "archive")
            c.commit()
            _mirror(memory_id, "archive", conn=c)
    finally:
        c.close()


def confirm_memory(memory_id: int) -> Optional[dict]:
    ensure_ready()
    c = get_connection()
    try:
        memory = repo.read(memory_id, conn=c)
        if memory is None:
            return None
        c.execute(
            "UPDATE brain_memory_v2 SET last_confirmed_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (memory_id,),
        )
        refreshed = repo.read(memory_id, conn=c)
        if refreshed:
            _record_version(c, refreshed, "confirm")
            c.commit()
            _mirror(memory_id, "confirm", conn=c)
            return _memory_dict(refreshed, c)
        return None
    finally:
        c.close()


def list_versions(memory_id: int) -> list[dict]:
    ensure_ready()
    c = get_connection()
    try:
        return [dict(row) for row in c.execute(
            "SELECT id,memory_id,content,category,confidence,change_kind,changed_by,created_at "
            "FROM brain_memory_v2_versions WHERE memory_id=? ORDER BY created_at DESC,id DESC",
            (memory_id,),
        ).fetchall()]
    finally:
        c.close()


def semantic_search(query: str, k: int = 12) -> list[dict]:
    query = (query or "").strip()
    if not query:
        return []
    ensure_ready()
    c = get_connection()
    try:
        scored = []
        for memory in repo.list_memories(MemoryStatus.ACTIVE, conn=c):
            score = text_similarity(query, f"{memory.distilled_text} {memory.behavior_implication}")
            if score > 0:
                item = _memory_dict(memory, c)
                item["score"] = round(score, 3)
                scored.append(item)
        scored.sort(key=lambda item: item["score"], reverse=True)
        return scored[:max(1, min(int(k), 50))]
    finally:
        c.close()


def list_pending() -> list[dict]:
    return list_memories(status="pending")


def _resolve_links(conn: sqlite3.Connection, memory_id: int, decision: str) -> None:
    rows = conn.execute(
        "SELECT id FROM brain_memory_links WHERE link_type='conflicts_with' "
        "AND (from_id=? OR to_id=?)", (memory_id, memory_id)
    ).fetchall()
    for row in rows:
        conn.execute(
            "INSERT OR IGNORE INTO brain_memory_v2_conflict_resolutions (link_id,decision) VALUES (?,?)",
            (row["id"], decision),
        )


def accept_pending(memory_id: int) -> Optional[dict]:
    ensure_ready()
    c = get_connection()
    try:
        memory = repo.read(memory_id, conn=c)
        if memory is None:
            return None
        repo.set_status(memory_id, MemoryStatus.ACTIVE, conn=c)
        c.execute(
            "UPDATE brain_memory_v2 SET last_confirmed_at=CURRENT_TIMESTAMP WHERE id=?", (memory_id,)
        )
        _resolve_links(c, memory_id, "keep_both")
        active = repo.read(memory_id, conn=c)
        if active:
            _record_version(c, active, "confirm")
            c.commit()
            _mirror(memory_id, "confirm", conn=c)
            return _memory_dict(active, c)
        return None
    finally:
        c.close()


def reject_pending(memory_id: int) -> None:
    ensure_ready()
    c = get_connection()
    try:
        memory = repo.read(memory_id, conn=c)
        if memory is None:
            return
        repo.set_status(memory_id, MemoryStatus.REJECTED, conn=c)
        _resolve_links(c, memory_id, "keep_existing")
        rejected = repo.read(memory_id, conn=c)
        if rejected:
            _record_version(c, rejected, "reject")
            c.commit()
            _mirror(memory_id, "reject", conn=c)
    finally:
        c.close()


def list_conflicts() -> list[dict]:
    ensure_ready()
    c = get_connection()
    try:
        rows = c.execute(
            "SELECT l.id,l.from_id,l.to_id,l.created_at FROM brain_memory_links l "
            "LEFT JOIN brain_memory_v2_conflict_resolutions r ON r.link_id=l.id "
            "WHERE l.link_type='conflicts_with' AND r.link_id IS NULL ORDER BY l.id DESC"
        ).fetchall()
        out = []
        for row in rows:
            candidate = repo.read(int(row["from_id"]), conn=c)
            existing = repo.read(int(row["to_id"]), conn=c)
            if not candidate or not existing:
                continue
            out.append({
                "id": int(row["id"]), "memory_id": existing.id,
                "candidate_content": candidate.distilled_text,
                "candidate_category": _category(candidate, _legacy_meta(c, candidate)),
                "candidate_confidence": candidate.confidence,
                "candidate_source": _source(candidate, _legacy_meta(c, candidate)),
                "reason": "Similar to an existing Brain V2 memory",
                "status": "open", "created_at": row["created_at"],
                "existing_content": existing.distilled_text,
                "existing_category": _category(existing, _legacy_meta(c, existing)),
                "existing_confidence": existing.confidence,
            })
        return out
    finally:
        c.close()


def resolve_conflict(link_id: int, decision: str) -> None:
    if decision not in {"keep_existing", "use_candidate", "keep_both"}:
        raise ValueError("Unknown conflict decision")
    ensure_ready()
    c = get_connection()
    try:
        link = c.execute(
            "SELECT * FROM brain_memory_links WHERE id=? AND link_type='conflicts_with'", (link_id,)
        ).fetchone()
        if not link:
            raise ValueError("Conflict not found")
        candidate_id, existing_id = int(link["from_id"]), int(link["to_id"])
        if decision == "keep_existing":
            repo.set_status(candidate_id, MemoryStatus.REJECTED, conn=c)
        elif decision == "use_candidate":
            repo.set_status(candidate_id, MemoryStatus.ACTIVE, conn=c)
            repo.set_status(existing_id, MemoryStatus.SUPERSEDED, conn=c)
            if not c.execute(
                "SELECT 1 FROM brain_memory_links WHERE from_id=? AND to_id=? AND link_type='supersedes'",
                (candidate_id, existing_id),
            ).fetchone():
                repo.link(candidate_id, existing_id, LinkType.SUPERSEDES, conn=c)
        else:
            repo.set_status(candidate_id, MemoryStatus.ACTIVE, conn=c)
        c.execute(
            "INSERT OR REPLACE INTO brain_memory_v2_conflict_resolutions (link_id,decision,resolved_at) "
            "VALUES (?,?,CURRENT_TIMESTAMP)", (link_id, decision),
        )
        for memory_id in {candidate_id, existing_id}:
            memory = repo.read(memory_id, conn=c)
            if memory:
                _record_version(c, memory, "conflict_resolve")
                _mirror(memory_id, "conflict_resolve", conn=c)
        c.commit()
    finally:
        c.close()


def parse_import(filename: str, text: str) -> list[dict]:
    from core import brain
    ensure_ready()
    items = brain.parse_import(filename, text)
    active = repo.list_memories(MemoryStatus.ACTIVE)
    for item in items:
        item.pop("merge_into", None)
        item.pop("merge_score", None)
        best = max(
            ((memory, text_similarity(item.get("content", ""), memory.distilled_text))
             for memory in active),
            key=lambda pair: pair[1], default=(None, 0.0),
        )
        if best[0] is not None and best[1] >= MERGE_AT:
            item["merge_into"] = best[0].id
            item["merge_score"] = round(best[1], 3)
    return items


def commit_import(filename: str, source_type: str, items: list[dict]) -> dict:
    ensure_ready()
    saved = merged = 0
    c = get_connection()
    try:
        for item in items:
            content = str(item.get("content") or "").strip()
            if not content:
                continue
            merge_into = item.get("merge_into")
            if merge_into:
                target = repo.read(int(merge_into), conn=c)
                if target:
                    repo.add_evidence(target.id, content[:320], f"import:{filename}",
                                      Trust.UNTRUSTED, conn=c)
                    repo.set_confidence(target.id, max(target.confidence,
                                                        float(item.get("confidence") or 0.6)), conn=c)
                    refreshed = repo.read(target.id, conn=c)
                    if refreshed:
                        _record_version(c, refreshed, "merge", "import")
                        _mirror(target.id, "merge", "import", conn=c)
                    merged += 1
                    continue
            candidate = _candidate(
                content, str(item.get("category") or "identity"),
                float(item.get("confidence") or 0.6), f"import:{filename}",
            )
            candidate = replace(candidate, explicitness=Explicitness.EXPLICIT)
            memory_id = repo.save(candidate, status=MemoryStatus.ACTIVE, conn=c)
            memory = repo.read(memory_id, conn=c)
            if memory:
                _record_version(c, memory, "create", "import")
                _mirror(memory_id, "create", "import", conn=c)
            saved += 1
        c.execute(
            "INSERT INTO brain_imports (filename,source_type,card_count) VALUES (?,?,?)",
            (filename, source_type, saved + merged),
        )
        c.commit()
        return {"saved": saved, "merged": merged}
    finally:
        c.close()


def find_duplicates() -> list[dict]:
    ensure_ready()
    c = get_connection()
    try:
        memories = repo.list_memories(MemoryStatus.ACTIVE, conn=c)
        parent = {memory.id: memory.id for memory in memories}

        def find(value: int) -> int:
            while parent[value] != value:
                parent[value] = parent[parent[value]]
                value = parent[value]
            return value

        def union(left: int, right: int) -> None:
            a, b = find(left), find(right)
            if a != b:
                parent[b] = a

        for index, left in enumerate(memories):
            for right in memories[index + 1:]:
                if text_similarity(left.distilled_text, right.distilled_text) >= DUPLICATE_AT:
                    union(left.id, right.id)
        groups: dict[int, list[repo.StoredMemory]] = {}
        for memory in memories:
            groups.setdefault(find(memory.id), []).append(memory)
        return [
            {"ids": [m.id for m in group], "memories": [_memory_dict(m, c) for m in group]}
            for group in groups.values() if len(group) > 1
        ]
    finally:
        c.close()


def merge_group(ids: list[int], keep_id: Optional[int] = None) -> dict:
    ids = list(dict.fromkeys(int(value) for value in ids))
    if len(ids) < 2:
        return {"merged": 0}
    ensure_ready()
    c = get_connection()
    try:
        memories = [memory for value in ids if (memory := repo.read(value, conn=c))]
        if len(memories) < 2:
            return {"merged": 0}
        keep = next((memory for memory in memories if memory.id == keep_id), None)
        keep = keep or max(memories, key=lambda memory: memory.confidence)
        merged = 0
        for memory in memories:
            if memory.id == keep.id:
                continue
            repo.set_status(memory.id, MemoryStatus.SUPERSEDED, conn=c)
            if not c.execute(
                "SELECT 1 FROM brain_memory_links WHERE from_id=? AND to_id=? AND link_type='supersedes'",
                (keep.id, memory.id),
            ).fetchone():
                repo.link(keep.id, memory.id, LinkType.SUPERSEDES, conn=c)
            changed = repo.read(memory.id, conn=c)
            if changed:
                _record_version(c, changed, "supersede")
                _mirror(memory.id, "supersede", conn=c)
            merged += 1
        repo.set_confidence(keep.id, max(memory.confidence for memory in memories), conn=c)
        c.execute(
            "UPDATE brain_memory_v2 SET last_confirmed_at=CURRENT_TIMESTAMP WHERE id=?", (keep.id,)
        )
        kept = repo.read(keep.id, conn=c)
        if kept:
            _record_version(c, kept, "merge")
            _mirror(keep.id, "merge", conn=c)
        c.commit()
        return {"merged": merged, "kept": keep.id}
    finally:
        c.close()


def get_narrative() -> Optional[dict]:
    from core import brain
    return brain.get_narrative()


def profile_rows(max_per_cat: int = 4) -> list[tuple[str, str]]:
    rows = list_memories(status="active")
    counts: dict[str, int] = {}
    out: list[tuple[str, str]] = []
    for row in rows:
        category = row["category"]
        if counts.get(category, 0) >= max_per_cat:
            continue
        counts[category] = counts.get(category, 0) + 1
        out.append((category, row["content"]))
    out.sort(key=lambda pair: CATEGORY_IDS.index(pair[0]) if pair[0] in CATEGORY_IDS else 999)
    return out


def profile_summary(max_per_cat: int = 4) -> str:
    grouped: dict[str, list[str]] = {}
    for category, content in profile_rows(max_per_cat):
        grouped.setdefault(category, []).append(content)
    return "\n".join(
        f"{category.upper()}: " + "; ".join(grouped[category])
        for category in CATEGORY_IDS if category in grouped
    )


def synthesize_narrative() -> Optional[dict]:
    from core import brain
    summary = profile_summary(max_per_cat=8)
    if not summary:
        return None
    system = (
        "You are Tobi, a deeply perceptive personal assistant with expert psychology insight. "
        "Write a concise, warm, second-person narrative capturing who the owner is: personality, "
        "values, motivations, working style, and what they need from you. Use 150-250 words."
    )
    content = brain._llm(
        f"What I know about the owner:\n{summary}\n\nWrite the narrative.",
        system=system, max_tokens=500, task_type="simple",
    )
    if not content:
        return None
    c = get_connection()
    try:
        c.execute("INSERT INTO brain_narrative (content,model_used) VALUES (?,?)",
                  (content.strip(), "llm"))
        c.commit()
    finally:
        c.close()
    return get_narrative()


def retrieve(query: str, k: int = 6) -> list[dict]:
    from core import brain_retrieval
    ensure_ready()
    items = brain_retrieval.retrieve(query, mode="chat")[:max(1, min(int(k), 20))]
    return [
        {"id": item["memory_id"], "content": item["text"], "category": item["type"],
         "confidence": item["chip"]["confidence"], "score": item["score"]}
        for item in items
    ]


def route_candidate(content: str, category: str, confidence: float, source: str) -> dict:
    ensure_ready()
    candidate = _candidate(content, category, confidence, source)
    candidate = replace(candidate, explicitness=Explicitness.INFERRED)
    result = ingest(candidate)
    action = {
        "active": "active", "pending": "pending", "conflicted": "conflict",
        "merged": "merged", "corrected": "active", "rejected": "skipped",
    }.get(result.outcome, "skipped")
    if result.memory_id is not None:
        record_change(result.memory_id,
                      "merge" if result.outcome == "merged" else "create", "auto")
    return {"action": action, "memory_id": result.memory_id,
            "score": None, "v2_outcome": result.outcome}


def stats() -> dict:
    ensure_ready()
    active = list_memories(status="active")
    pending = list_memories(status="pending")
    conflicts = list_conflicts()
    by_category: dict[str, int] = {}
    by_source: dict[str, int] = {}
    for item in active:
        by_category[item["category"]] = by_category.get(item["category"], 0) + 1
        by_source[item["source"]] = by_source.get(item["source"], 0) + 1
    return {
        "total": len(active), "by_category": by_category, "by_source": by_source,
        "pending": len(pending), "conflicts": len(conflicts),
        "stale": sum(1 for item in active if item["stale"]),
        "embeddings": True,
        "backend": "brain_v2",
    }

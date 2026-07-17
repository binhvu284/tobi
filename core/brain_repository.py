"""
BRAIN MEMORY V2 — repository boundary (#20 / spec §Storage, task T02).

The single typed door to the V2 tables (`brain_memory_v2` + evidence / links /
tags / secure_payloads). Callers hand in a validated ``MemoryCandidate`` and get
back a typed ``StoredMemory`` — no unvalidated dict crosses this boundary.

Sensitive memories never sit in the DB as plaintext: their protected fields
(distilled text + evidence excerpts) are AES-GCM-encrypted through the vault's
purpose-bound public helper (``vault.encrypt_payload`` — Brain never touches
vault internals) and the plaintext columns hold a redaction sentinel. When the
vault is locked, sensitive memories read back redacted and are excluded from LLM
context entirely; owner deletion purges the memory and its protected payload.

Inert until T04 wires it into the Remember/import paths behind
``owner_flags.brain_v2_mode()``. Importing this module changes no behavior.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import sqlite3

from core.database import get_connection
from core import vault
from core.brain_contracts import (
    MemoryCandidate, MemoryType, ScopeType, Authority, Explicitness, Trust,
    MemoryStatus, LinkType, activation_gate,
)

# Sentinel stored in the plaintext columns of a sensitive memory. Distinct and
# machine-detectable so a locked-vault read and the redaction tests can spot it.
REDACTED = "[sensitive:redacted]"


# ── typed read results ───────────────────────────────────────────────────────
@dataclass(frozen=True)
class StoredEvidence:
    id: int
    excerpt: str
    source_ref: Optional[str]
    trust: Trust
    provenance: Optional[str]
    redacted: bool = False


@dataclass(frozen=True)
class StoredMemory:
    id: int
    distilled_text: str
    memory_type: MemoryType
    behavior_implication: str
    tags: tuple[str, ...]
    scope_type: ScopeType
    scope_key: Optional[str]
    authority: Authority
    explicitness: Explicitness
    confidence: float
    durability: float
    actionability: float
    specificity: float
    source_strength: float
    novelty: float
    future_usefulness: float
    quality_score: float
    suggested_usage: str
    trust: Trust
    sensitive: bool
    status: MemoryStatus
    evidence: tuple[StoredEvidence, ...]
    redacted: bool
    compat_ref: Optional[int]
    created_at: str
    updated_at: str


# ── helpers ──────────────────────────────────────────────────────────────────
def _conn(conn: Optional[sqlite3.Connection]) -> sqlite3.Connection:
    return conn if conn is not None else get_connection()


def _purpose(memory_id: int, field: str) -> str:
    """AAD binding for a protected field — ties ciphertext to this memory+field."""
    return f"brain.memory:{memory_id}:{field}"


def _as(enum_cls, value, default):
    try:
        return enum_cls(value)
    except Exception:
        return default


def _store_secure(conn: sqlite3.Connection, memory_id: int, field: str, plaintext: str) -> None:
    """Encrypt `plaintext` through the vault (raises VaultLocked when locked) and
    upsert it into brain_secure_payloads bound to (memory_id, field)."""
    purpose = _purpose(memory_id, field)
    ct, nonce = vault.encrypt_payload(purpose, plaintext)
    conn.execute(
        "INSERT INTO brain_secure_payloads (memory_id, field, purpose, ciphertext, nonce) "
        "VALUES (?,?,?,?,?) "
        "ON CONFLICT(memory_id, field) DO UPDATE SET purpose=excluded.purpose, "
        "ciphertext=excluded.ciphertext, nonce=excluded.nonce",
        (memory_id, field, purpose, ct, nonce),
    )


def _reveal_secure(conn: sqlite3.Connection, memory_id: int, field: str, fallback: str) -> str:
    """Decrypt a protected field for an unlocked vault; fall back to the sentinel
    if the payload is missing (never leaks anything but the placeholder)."""
    row = conn.execute(
        "SELECT purpose, ciphertext, nonce FROM brain_secure_payloads WHERE memory_id=? AND field=?",
        (memory_id, field),
    ).fetchone()
    if not row:
        return fallback
    return vault.decrypt_payload(row["purpose"], row["ciphertext"], row["nonce"])


# ── write ────────────────────────────────────────────────────────────────────
def save(candidate: MemoryCandidate, *, status: Optional[MemoryStatus] = None,
         compat_ref: Optional[int] = None, conn: Optional[sqlite3.Connection] = None) -> int:
    """Persist a validated candidate and return its new brain_memory_v2 id.

    ``status`` defaults to the deterministic activation gate. Sensitive candidates
    require an unlocked vault — this fails closed (VaultLocked, no rows written)
    before any insert if the vault can't encrypt.
    """
    if not isinstance(candidate, MemoryCandidate):
        raise TypeError("save() requires a validated MemoryCandidate")
    if status is None:
        status = activation_gate(candidate)
    sensitive = bool(candidate.sensitive)
    if sensitive and not vault.can_encrypt_payloads():
        raise vault.VaultLocked("Vault must be unlocked to store a sensitive memory.")

    c = _conn(conn)
    stored_text = REDACTED if sensitive else candidate.distilled_text
    cur = c.execute(
        "INSERT INTO brain_memory_v2 ("
        " compat_ref, distilled_text, memory_type, behavior_implication, scope_type, scope_key,"
        " authority, explicitness, confidence, durability, actionability, specificity,"
        " source_strength, novelty, future_usefulness, quality_score, suggested_usage,"
        " trust, sensitive, status"
        ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            compat_ref, stored_text, candidate.memory_type.value, candidate.behavior_implication,
            candidate.scope_type.value, candidate.scope_key, candidate.authority.value,
            candidate.explicitness.value, candidate.confidence, candidate.durability,
            candidate.actionability, candidate.specificity, candidate.source_strength,
            candidate.novelty, candidate.future_usefulness, candidate.quality_score,
            candidate.suggested_usage, candidate.trust.value, int(sensitive), status.value,
        ),
    )
    memory_id = cur.lastrowid

    if sensitive:
        _store_secure(c, memory_id, "distilled_text", candidate.distilled_text)

    for tag in candidate.tags:
        c.execute("INSERT INTO brain_memory_tags (memory_id, tag) VALUES (?,?)", (memory_id, tag))

    if candidate.evidence_excerpt or candidate.source_ref:
        stored_excerpt = REDACTED if sensitive else candidate.evidence_excerpt
        ev_cur = c.execute(
            "INSERT INTO brain_memory_evidence (memory_id, excerpt, source_ref, trust) VALUES (?,?,?,?)",
            (memory_id, stored_excerpt, candidate.source_ref, candidate.trust.value),
        )
        if sensitive and candidate.evidence_excerpt:
            _store_secure(c, memory_id, f"evidence:{ev_cur.lastrowid}", candidate.evidence_excerpt)

    c.commit()
    return int(memory_id)


def link(from_id: int, to_id: int, link_type: LinkType,
         conn: Optional[sqlite3.Connection] = None) -> None:
    """Record a typed relationship between two V2 memories."""
    if not isinstance(link_type, LinkType):
        raise TypeError("link_type must be a LinkType")
    c = _conn(conn)
    c.execute("INSERT INTO brain_memory_links (from_id, to_id, link_type) VALUES (?,?,?)",
              (from_id, to_id, link_type.value))
    c.commit()


def add_evidence(memory_id: int, excerpt: str = "", source_ref: Optional[str] = None,
                 trust: Trust = Trust.TRUSTED, conn: Optional[sqlite3.Connection] = None) -> int:
    """Append an evidence row to an existing memory (dedup/corroboration path).

    Honors the memory's sensitivity: evidence attached to a sensitive memory is
    encrypted through the vault and the plaintext column holds the sentinel
    (raises VaultLocked when the vault can't encrypt — fails closed, no row)."""
    if not isinstance(trust, Trust):
        raise TypeError("trust must be a Trust")
    c = _conn(conn)
    row = c.execute("SELECT sensitive FROM brain_memory_v2 WHERE id=?", (memory_id,)).fetchone()
    if not row:
        raise ValueError(f"no such memory: {memory_id}")
    sensitive = bool(row["sensitive"])
    if sensitive and excerpt and not vault.can_encrypt_payloads():
        raise vault.VaultLocked("Vault must be unlocked to attach sensitive evidence.")
    stored = REDACTED if (sensitive and excerpt) else excerpt
    cur = c.execute(
        "INSERT INTO brain_memory_evidence (memory_id, excerpt, source_ref, trust) VALUES (?,?,?,?)",
        (memory_id, stored, source_ref, trust.value),
    )
    if sensitive and excerpt:
        _store_secure(c, memory_id, f"evidence:{cur.lastrowid}", excerpt)
    c.commit()
    return int(cur.lastrowid)


def set_confidence(memory_id: int, confidence: float,
                   conn: Optional[sqlite3.Connection] = None) -> None:
    """Update confidence (merge/corroboration path). Validates the 0–1 range."""
    conf = float(confidence)
    if not (0.0 <= conf <= 1.0):
        raise ValueError(f"confidence must be in [0, 1], got {conf!r}")
    c = _conn(conn)
    c.execute("UPDATE brain_memory_v2 SET confidence=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
              (conf, memory_id))
    c.commit()


def set_status(memory_id: int, status: MemoryStatus,
               conn: Optional[sqlite3.Connection] = None) -> None:
    """Update lifecycle status (used by archive/restore/activation review)."""
    if not isinstance(status, MemoryStatus):
        raise TypeError("status must be a MemoryStatus")
    c = _conn(conn)
    c.execute("UPDATE brain_memory_v2 SET status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
              (status.value, memory_id))
    c.commit()


def archive(memory_id: int, conn: Optional[sqlite3.Connection] = None) -> None:
    """Reversible: mark archived. The row and its payload are kept (unlike purge)."""
    set_status(memory_id, MemoryStatus.ARCHIVED, conn=conn)


def purge(memory_id: int, conn: Optional[sqlite3.Connection] = None) -> bool:
    """Permanently delete a memory and its protected payload (owner deletion).

    Enables SQLite secure deletion for this connection so freed pages are zeroed
    (external backups may still retain bytes, per spec). Evidence/tags/links drop
    via ON DELETE CASCADE; the secure payload is also removed explicitly.
    """
    c = _conn(conn)
    c.execute("PRAGMA secure_delete = ON")
    c.execute("DELETE FROM brain_secure_payloads WHERE memory_id=?", (memory_id,))
    cur = c.execute("DELETE FROM brain_memory_v2 WHERE id=?", (memory_id,))
    c.commit()
    return cur.rowcount > 0


# ── read ─────────────────────────────────────────────────────────────────────
def _read_evidence(conn: sqlite3.Connection, memory_id: int, sensitive: bool,
                   unlocked: bool) -> tuple[StoredEvidence, ...]:
    rows = conn.execute(
        "SELECT id, excerpt, source_ref, trust, provenance FROM brain_memory_evidence "
        "WHERE memory_id=? ORDER BY id", (memory_id,),
    ).fetchall()
    out: list[StoredEvidence] = []
    for r in rows:
        excerpt, redacted = r["excerpt"], False
        if sensitive:
            if unlocked:
                excerpt = _reveal_secure(conn, memory_id, f"evidence:{r['id']}", fallback=excerpt)
            else:
                redacted = True
        out.append(StoredEvidence(
            id=r["id"], excerpt=excerpt, source_ref=r["source_ref"],
            trust=_as(Trust, r["trust"], Trust.TRUSTED), provenance=r["provenance"], redacted=redacted,
        ))
    return tuple(out)


def read(memory_id: int, *, for_context: bool = False,
         conn: Optional[sqlite3.Connection] = None) -> Optional[StoredMemory]:
    """Load one memory as a typed object, or None if absent.

    ``for_context=True`` is the LLM-context path: a sensitive memory read while
    the vault is locked returns None (excluded from context) rather than a
    redacted stub. With ``for_context=False`` (owner/UI) a locked sensitive
    memory returns with placeholders and ``redacted=True``.
    """
    c = _conn(conn)
    r = c.execute("SELECT * FROM brain_memory_v2 WHERE id=?", (memory_id,)).fetchone()
    if not r:
        return None
    sensitive = bool(r["sensitive"])
    unlocked = vault.can_encrypt_payloads()
    if sensitive and not unlocked and for_context:
        return None  # excluded from LLM context while locked

    distilled, redacted = r["distilled_text"], False
    if sensitive:
        if unlocked:
            distilled = _reveal_secure(c, memory_id, "distilled_text", fallback=distilled)
        else:
            redacted = True

    tags = tuple(row["tag"] for row in c.execute(
        "SELECT tag FROM brain_memory_tags WHERE memory_id=? ORDER BY id", (memory_id,)).fetchall())
    evidence = _read_evidence(c, memory_id, sensitive, unlocked)

    return StoredMemory(
        id=r["id"], distilled_text=distilled,
        memory_type=_as(MemoryType, r["memory_type"], MemoryType.FACT),
        behavior_implication=r["behavior_implication"] or "", tags=tags,
        scope_type=_as(ScopeType, r["scope_type"], ScopeType.GLOBAL), scope_key=r["scope_key"],
        authority=_as(Authority, r["authority"], Authority.SOFT),
        explicitness=_as(Explicitness, r["explicitness"], Explicitness.INFERRED),
        confidence=r["confidence"], durability=r["durability"], actionability=r["actionability"],
        specificity=r["specificity"], source_strength=r["source_strength"], novelty=r["novelty"],
        future_usefulness=r["future_usefulness"], quality_score=r["quality_score"],
        suggested_usage=r["suggested_usage"] or "", trust=_as(Trust, r["trust"], Trust.TRUSTED),
        sensitive=sensitive, status=_as(MemoryStatus, r["status"], MemoryStatus.PENDING),
        evidence=evidence, redacted=redacted, compat_ref=r["compat_ref"],
        created_at=str(r["created_at"]), updated_at=str(r["updated_at"]),
    )


def list_memories(status: Optional[MemoryStatus] = None, *, for_context: bool = False,
                  conn: Optional[sqlite3.Connection] = None) -> list[StoredMemory]:
    """List memories (optionally by status), newest first. Honors the same
    locked-vault exclusion as ``read`` — sensitive rows drop out of context lists
    while locked."""
    c = _conn(conn)
    if status is not None:
        rows = c.execute(
            "SELECT id FROM brain_memory_v2 WHERE status=? ORDER BY id DESC", (status.value,)).fetchall()
    else:
        rows = c.execute("SELECT id FROM brain_memory_v2 ORDER BY id DESC").fetchall()
    out: list[StoredMemory] = []
    for row in rows:
        m = read(row["id"], for_context=for_context, conn=c)
        if m is not None:
            out.append(m)
    return out

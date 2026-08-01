"""Ordered, append-only local event storage for Mission Control Runtime V2."""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from core.database import get_connection
from core.runtime.contracts import RunEvent, SystemEdge, SystemEntity, contract_to_dict
from core.schema.runtime import _ensure_runtime_schema


MAX_PAYLOAD_BYTES = 12_000
_REDACTED = "[REDACTED]"
_SENSITIVE_KEY = re.compile(
    r"(?:api[_-]?key|access[_-]?token|refresh[_-]?token|secret|password|passwd|"
    r"authorization|cookie|private[_-]?key|credentials?)",
    re.IGNORECASE,
)
_EMBEDDED_SECRET = re.compile(
    r"(?i)(\b(?:authorization|api[_-]?key|access[_-]?token|password|secret)\s*[:=]\s*"
    r"(?:bearer\s+)?)([^\s,;]+)"
)


class EventConflictError(ValueError):
    """An idempotency event ID was reused for different content."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _require_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), default=str)


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _redact_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _REDACTED if _SENSITIVE_KEY.search(str(key)) else _redact_value(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_redact_value(item) for item in value]
    if isinstance(value, str):
        return _EMBEDDED_SECRET.sub(lambda match: match.group(1) + _REDACTED, value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)


def prepare_payload(payload: Optional[Mapping[str, Any]]) -> tuple[dict[str, Any], str, str]:
    """Redact first, then return bounded JSON plus the full redacted hash."""
    if payload is None:
        payload = {}
    if not isinstance(payload, Mapping):
        raise ValueError("payload must be a mapping")
    redacted = _redact_value(payload)
    full_json = _canonical_json(redacted)
    payload_hash = _hash_text(full_json)
    if len(full_json.encode("utf-8")) <= MAX_PAYLOAD_BYTES:
        return redacted, full_json, payload_hash
    bounded = {
        "_truncated": True,
        "original_bytes": len(full_json.encode("utf-8")),
        "payload_hash": payload_hash,
        "preview": full_json[:8_000],
    }
    return bounded, _canonical_json(bounded), payload_hash


def _run_event_from_row(row: sqlite3.Row) -> RunEvent:
    return RunEvent(
        event_id=row["event_id"],
        run_id=row["run_id"],
        sequence=row["sequence"],
        event_type=row["event_type"],
        stage=row["stage"],
        timestamp=row["created_at"],
        actor=row["actor"],
        redacted_payload=json.loads(row["payload_json"]),
        trace_id=row["trace_id"],
        parent_span_id=row["parent_span_id"],
        contract_version=row["contract_version"],
    )


def _same_run_event(
    row: sqlite3.Row,
    *,
    run_id: str,
    event_type: str,
    stage: str,
    actor: str,
    payload_hash: str,
    trace_id: Optional[str],
    parent_span_id: Optional[str],
    contract_version: str,
) -> bool:
    expected = (
        run_id, event_type, stage, actor, payload_hash, trace_id,
        parent_span_id, contract_version,
    )
    actual = tuple(
        row[name]
        for name in (
            "run_id", "event_type", "stage", "actor", "payload_hash", "trace_id",
            "parent_span_id", "contract_version",
        )
    )
    return actual == expected


def append_run_event(
    *,
    run_id: str,
    event_type: str,
    stage: str,
    actor: str,
    payload: Optional[Mapping[str, Any]] = None,
    event_id: Optional[str] = None,
    timestamp: Optional[str] = None,
    trace_id: Optional[str] = None,
    parent_span_id: Optional[str] = None,
    contract_version: str = "1",
) -> RunEvent:
    """Append once and allocate the next stream sequence under a write lock."""
    for name, value in (
        ("run_id", run_id), ("event_type", event_type), ("stage", stage),
        ("actor", actor), ("contract_version", contract_version),
    ):
        _require_text(value, name)
    event_id = event_id or str(uuid.uuid4())
    timestamp = timestamp or _now()
    _require_text(event_id, "event_id")
    _require_text(timestamp, "timestamp")
    bounded_payload, payload_json, payload_hash = prepare_payload(payload)
    conn = get_connection()
    try:
        _ensure_runtime_schema(conn)
        conn.execute("BEGIN IMMEDIATE")
        existing = conn.execute(
            "SELECT * FROM mc_run_events WHERE event_id=?", (event_id,)
        ).fetchone()
        if existing is not None:
            if not _same_run_event(
                existing,
                run_id=run_id,
                event_type=event_type,
                stage=stage,
                actor=actor,
                payload_hash=payload_hash,
                trace_id=trace_id,
                parent_span_id=parent_span_id,
                contract_version=contract_version,
            ):
                raise EventConflictError(f"event_id {event_id!r} already has different content")
            conn.commit()
            return _run_event_from_row(existing)
        sequence = conn.execute(
            "SELECT COALESCE(MAX(sequence), 0) + 1 FROM mc_run_events WHERE run_id=?",
            (run_id,),
        ).fetchone()[0]
        conn.execute(
            """INSERT INTO mc_run_events (
                event_id, run_id, sequence, event_type, stage, actor, payload_json,
                payload_hash, trace_id, parent_span_id, contract_version, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                event_id, run_id, sequence, event_type, stage, actor, payload_json,
                payload_hash, trace_id, parent_span_id, contract_version, timestamp,
            ),
        )
        conn.commit()
        return RunEvent(
            event_id=event_id,
            run_id=run_id,
            sequence=sequence,
            event_type=event_type,
            stage=stage,
            timestamp=timestamp,
            actor=actor,
            redacted_payload=bounded_payload,
            trace_id=trace_id,
            parent_span_id=parent_span_id,
            contract_version=contract_version,
        )
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def list_run_events(run_id: str, *, after_sequence: int = 0) -> list[RunEvent]:
    _require_text(run_id, "run_id")
    if not isinstance(after_sequence, int) or after_sequence < 0:
        raise ValueError("after_sequence must be a non-negative integer")
    conn = get_connection()
    try:
        _ensure_runtime_schema(conn)
        rows = conn.execute(
            "SELECT * FROM mc_run_events WHERE run_id=? AND sequence>? ORDER BY sequence",
            (run_id, after_sequence),
        ).fetchall()
        return [_run_event_from_row(row) for row in rows]
    finally:
        conn.close()


def _append_change_event(
    *,
    change_type: str,
    subject_type: str,
    subject_id: str,
    actor: str,
    payload: Mapping[str, Any],
    event_id: Optional[str] = None,
    timestamp: Optional[str] = None,
    contract_version: str = "1",
) -> dict[str, Any]:
    for name, value in (
        ("change_type", change_type), ("subject_type", subject_type),
        ("subject_id", subject_id), ("actor", actor), ("contract_version", contract_version),
    ):
        _require_text(value, name)
    event_id = event_id or str(uuid.uuid4())
    timestamp = timestamp or _now()
    _require_text(event_id, "event_id")
    bounded_payload, payload_json, payload_hash = prepare_payload(payload)
    conn = get_connection()
    try:
        _ensure_runtime_schema(conn)
        conn.execute("BEGIN IMMEDIATE")
        existing = conn.execute(
            "SELECT * FROM mc_change_events WHERE event_id=?", (event_id,)
        ).fetchone()
        if existing is not None:
            actual = tuple(existing[name] for name in (
                "change_type", "subject_type", "subject_id", "actor", "payload_hash",
                "contract_version",
            ))
            expected = (
                change_type, subject_type, subject_id, actor, payload_hash,
                contract_version,
            )
            if actual != expected:
                raise EventConflictError(f"event_id {event_id!r} already has different content")
            conn.commit()
            return _change_event_dict(existing)
        sequence = conn.execute(
            "SELECT COALESCE(MAX(sequence), 0) + 1 FROM mc_change_events"
        ).fetchone()[0]
        conn.execute(
            """INSERT INTO mc_change_events (
                event_id, sequence, change_type, subject_type, subject_id, actor,
                payload_json, payload_hash, contract_version, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                event_id, sequence, change_type, subject_type, subject_id, actor,
                payload_json, payload_hash, contract_version, timestamp,
            ),
        )
        conn.commit()
        return {
            "event_id": event_id,
            "sequence": sequence,
            "change_type": change_type,
            "subject_type": subject_type,
            "subject_id": subject_id,
            "actor": actor,
            "payload": bounded_payload,
            "contract_version": contract_version,
            "timestamp": timestamp,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _change_event_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "event_id": row["event_id"],
        "sequence": row["sequence"],
        "change_type": row["change_type"],
        "subject_type": row["subject_type"],
        "subject_id": row["subject_id"],
        "actor": row["actor"],
        "payload": json.loads(row["payload_json"]),
        "contract_version": row["contract_version"],
        "timestamp": row["created_at"],
    }


def list_change_events(*, after_sequence: int = 0) -> list[dict[str, Any]]:
    if not isinstance(after_sequence, int) or after_sequence < 0:
        raise ValueError("after_sequence must be a non-negative integer")
    conn = get_connection()
    try:
        _ensure_runtime_schema(conn)
        rows = conn.execute(
            "SELECT * FROM mc_change_events WHERE sequence>? ORDER BY sequence",
            (after_sequence,),
        ).fetchall()
        return [_change_event_dict(row) for row in rows]
    finally:
        conn.close()


def append_system_entity(
    entity: SystemEntity, *, actor: str, event_id: Optional[str] = None
) -> dict[str, Any]:
    if not isinstance(entity, SystemEntity):
        raise ValueError("entity must be a validated SystemEntity")
    return _append_change_event(
        change_type="entity.upsert",
        subject_type="entity",
        subject_id=entity.entity_id,
        actor=actor,
        payload=contract_to_dict(entity),
        event_id=event_id,
        timestamp=entity.observed_at,
    )


def remove_system_entity(
    entity_id: str, *, actor: str, event_id: Optional[str] = None,
    timestamp: Optional[str] = None,
) -> dict[str, Any]:
    return _append_change_event(
        change_type="entity.remove",
        subject_type="entity",
        subject_id=entity_id,
        actor=actor,
        payload={"entity_id": entity_id},
        event_id=event_id,
        timestamp=timestamp,
    )


def append_system_edge(
    edge: SystemEdge, *, actor: str, event_id: Optional[str] = None,
    timestamp: Optional[str] = None,
) -> dict[str, Any]:
    if not isinstance(edge, SystemEdge):
        raise ValueError("edge must be a validated SystemEdge")
    return _append_change_event(
        change_type="edge.upsert",
        subject_type="edge",
        subject_id=edge.edge_id,
        actor=actor,
        payload=contract_to_dict(edge),
        event_id=event_id,
        timestamp=timestamp,
    )


def remove_system_edge(
    edge_id: str, *, actor: str, event_id: Optional[str] = None,
    timestamp: Optional[str] = None,
) -> dict[str, Any]:
    return _append_change_event(
        change_type="edge.remove",
        subject_type="edge",
        subject_id=edge_id,
        actor=actor,
        payload={"edge_id": edge_id},
        event_id=event_id,
        timestamp=timestamp,
    )

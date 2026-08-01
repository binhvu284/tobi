"""Deterministic current-state views rebuilt from Runtime V2 event history."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from core.database import get_connection
from core.runtime.event_store import list_change_events, list_run_events
from core.schema.runtime import _ensure_runtime_schema


PROJECTION_VERSION = "1"
_RUN_STATE_KEYS = (
    "objective",
    "status",
    "surface",
    "mode",
    "owner_attention",
    "current_step",
    "error_code",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), default=str)


def _state_hash(state_json: str) -> str:
    return hashlib.sha256(state_json.encode("utf-8")).hexdigest()


def _projection_result(
    projection_type: str,
    projection_key: str,
    last_sequence: int,
    state: dict[str, Any],
) -> dict[str, Any]:
    state_json = _canonical_json(state)
    return {
        "projection_type": projection_type,
        "projection_key": projection_key,
        "projection_version": PROJECTION_VERSION,
        "last_sequence": last_sequence,
        "state": state,
        "state_hash": _state_hash(state_json),
    }


def _write_projection(conn, projection: dict[str, Any], *, updated_at: str) -> None:
    conn.execute(
        """INSERT INTO mc_runtime_projections (
            projection_type, projection_key, projection_version, last_sequence,
            state_json, state_hash, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(projection_type, projection_key) DO UPDATE SET
            projection_version=excluded.projection_version,
            last_sequence=excluded.last_sequence,
            state_json=excluded.state_json,
            state_hash=excluded.state_hash,
            updated_at=excluded.updated_at""",
        (
            projection["projection_type"],
            projection["projection_key"],
            projection["projection_version"],
            projection["last_sequence"],
            _canonical_json(projection["state"]),
            projection["state_hash"],
            updated_at,
        ),
    )


def rebuild_run_projection(run_id: str) -> dict[str, Any]:
    """Replay one run from sequence one and replace its current-state row."""
    events = list_run_events(run_id)
    state: dict[str, Any] = {"run_id": run_id, "last_sequence": 0}
    for event in events:
        payload = event.redacted_payload
        for key in _RUN_STATE_KEYS:
            if key in payload:
                state[key] = payload[key]
        state.update(
            {
                "last_sequence": event.sequence,
                "last_event_type": event.event_type,
                "last_stage": event.stage,
                "last_actor": event.actor,
                "last_timestamp": event.timestamp,
            }
        )
    last_sequence = events[-1].sequence if events else 0
    projection = _projection_result("run", run_id, last_sequence, state)
    updated_at = events[-1].timestamp if events else _now()
    conn = get_connection()
    try:
        _ensure_runtime_schema(conn)
        conn.execute("BEGIN IMMEDIATE")
        _write_projection(conn, projection, updated_at=updated_at)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return projection


def get_run_projection(run_id: str) -> dict[str, Any] | None:
    conn = get_connection()
    try:
        _ensure_runtime_schema(conn)
        row = conn.execute(
            """SELECT projection_type, projection_key, projection_version,
                      last_sequence, state_json, state_hash
               FROM mc_runtime_projections
               WHERE projection_type='run' AND projection_key=?""",
            (run_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "projection_type": row["projection_type"],
            "projection_key": row["projection_key"],
            "projection_version": row["projection_version"],
            "last_sequence": row["last_sequence"],
            "state": json.loads(row["state_json"]),
            "state_hash": row["state_hash"],
        }
    finally:
        conn.close()


def _reduced_system_state() -> tuple[
    dict[str, tuple[dict[str, Any], int]],
    dict[str, tuple[dict[str, Any], int]],
    int,
    str,
]:
    entities: dict[str, tuple[dict[str, Any], int]] = {}
    edges: dict[str, tuple[dict[str, Any], int]] = {}
    last_sequence = 0
    last_timestamp = ""
    for event in list_change_events():
        last_sequence = event["sequence"]
        last_timestamp = event["timestamp"]
        change_type = event["change_type"]
        if change_type == "entity.upsert":
            entities[event["subject_id"]] = (dict(event["payload"]), event["sequence"])
        elif change_type == "entity.remove":
            entities.pop(event["subject_id"], None)
        elif change_type == "edge.upsert":
            edges[event["subject_id"]] = (dict(event["payload"]), event["sequence"])
        elif change_type == "edge.remove":
            edges.pop(event["subject_id"], None)
    return entities, edges, last_sequence, last_timestamp


def rebuild_system_projection() -> dict[str, Any]:
    """Replay System Model changes and replace all derived current rows."""
    entities, edges, last_sequence, last_timestamp = _reduced_system_state()
    state = {
        "entities": [entities[key][0] for key in sorted(entities)],
        "edges": [edges[key][0] for key in sorted(edges)],
        "last_sequence": last_sequence,
    }
    projection = _projection_result("system", "current", last_sequence, state)
    conn = get_connection()
    try:
        _ensure_runtime_schema(conn)
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("DELETE FROM mc_system_edges")
        conn.execute("DELETE FROM mc_system_entities")
        for entity_id in sorted(entities):
            entity, source_sequence = entities[entity_id]
            conn.execute(
                """INSERT INTO mc_system_entities (
                    entity_id, entity_type, canonical_key, name, status, version,
                    owner_domain, source_ref, observed_at, metadata_json, source_sequence
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    entity["entity_id"], entity["entity_type"], entity["canonical_key"],
                    entity["name"], entity["status"], entity["version"],
                    entity["owner_domain"], entity["source_ref"], entity["observed_at"],
                    _canonical_json(entity.get("metadata", {})), source_sequence,
                ),
            )
        for edge_id in sorted(edges):
            edge, source_sequence = edges[edge_id]
            conn.execute(
                """INSERT INTO mc_system_edges (
                    edge_id, from_entity_id, edge_type, to_entity_id, version,
                    evidence_refs_json, confidence, valid_from, valid_to, source_sequence
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    edge["edge_id"], edge["from_entity_id"], edge["edge_type"],
                    edge["to_entity_id"], edge["version"],
                    _canonical_json(edge.get("evidence_refs", [])), edge["confidence"],
                    edge.get("valid_from"), edge.get("valid_to"), source_sequence,
                ),
            )
        _write_projection(conn, projection, updated_at=last_timestamp or _now())
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return projection


def _all_run_ids() -> list[str]:
    conn = get_connection()
    try:
        _ensure_runtime_schema(conn)
        return [
            row[0]
            for row in conn.execute(
                "SELECT DISTINCT run_id FROM mc_run_events ORDER BY run_id"
            ).fetchall()
        ]
    finally:
        conn.close()


def _rebuild_all_once() -> dict[str, Any]:
    runs = {run_id: rebuild_run_projection(run_id)["state_hash"] for run_id in _all_run_ids()}
    system_hash = rebuild_system_projection()["state_hash"]
    snapshot = {"runs": runs, "system": system_hash}
    return {
        "runs": runs,
        "system": system_hash,
        "state_hash": _state_hash(_canonical_json(snapshot)),
    }


def rebuild_all_projections(*, verify: bool = False) -> dict[str, Any]:
    """Rebuild every projection; verify mode repeats and compares stable hashes."""
    first = _rebuild_all_once()
    verified = False
    if verify:
        verified = first == _rebuild_all_once()
        if not verified:
            raise RuntimeError("projection rebuild produced different state hashes")
    return {**first, "verified": verified}

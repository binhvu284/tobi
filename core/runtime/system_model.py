"""Validated read/write boundary for the evidence-backed TOBI System Model."""
from __future__ import annotations

import json
from typing import Any

from core.database import get_connection
from core.runtime.contracts import SystemEdge, SystemEntity, SystemEntityType
from core.runtime.event_store import (
    append_system_edge,
    append_system_entity,
    remove_system_edge,
    remove_system_entity,
)
from core.runtime.projections import rebuild_system_projection
from core.schema.runtime import _ensure_runtime_schema


class SystemModelValidationError(ValueError):
    """A System change lacks identity, evidence, or valid endpoints."""


def _entity_dict(row: Any) -> dict[str, Any]:
    result = dict(row)
    result["metadata"] = json.loads(result.pop("metadata_json"))
    return result


def _edge_dict(row: Any) -> dict[str, Any]:
    result = dict(row)
    result["evidence_refs"] = json.loads(result.pop("evidence_refs_json"))
    return result


class SystemModelRepository:
    """Persist observed facts; this projection never grants Runtime authority."""

    def upsert_entity(self, entity: SystemEntity, *, actor: str = "mission-control") -> dict[str, Any]:
        if not isinstance(entity, SystemEntity):
            raise ValueError("entity must be a validated SystemEntity")
        if not entity.source_ref.strip():
            raise SystemModelValidationError("entity source_ref is required")
        append_system_entity(
            entity,
            actor=actor,
            event_id=f"system:entity:{entity.entity_id}:{entity.version}",
        )
        rebuild_system_projection()
        stored = self.get_entity(entity.entity_id)
        if stored is None:
            raise RuntimeError("entity projection was not rebuilt")
        return stored

    def upsert_edge(self, edge: SystemEdge, *, actor: str = "mission-control") -> dict[str, Any]:
        if not isinstance(edge, SystemEdge):
            raise ValueError("edge must be a validated SystemEdge")
        if not edge.evidence_refs or any(not ref.strip() for ref in edge.evidence_refs):
            raise SystemModelValidationError("edge requires at least one evidence reference")
        existing = {item["entity_id"] for item in self.list_entities()}
        missing = {edge.from_entity_id, edge.to_entity_id} - existing
        if missing:
            raise SystemModelValidationError(
                f"edge endpoints are missing: {', '.join(sorted(missing))}"
            )
        append_system_edge(
            edge,
            actor=actor,
            event_id=f"system:edge:{edge.edge_id}:{edge.version}",
        )
        rebuild_system_projection()
        stored = self.get_edge(edge.edge_id)
        if stored is None:
            raise RuntimeError("edge projection was not rebuilt")
        return stored

    def remove_edge(self, edge_id: str, *, actor: str = "mission-control") -> None:
        current = self.get_edge(edge_id)
        if current is None:
            return
        remove_system_edge(
            edge_id,
            actor=actor,
            event_id=f"system:edge:{edge_id}:remove:{current['source_sequence']}",
        )
        rebuild_system_projection()

    def remove_entity(self, entity_id: str, *, actor: str = "mission-control") -> None:
        current = self.get_entity(entity_id, include_edges=True)
        if current is None:
            return
        if current["edges"]:
            raise SystemModelValidationError("remove connected edges before removing an entity")
        remove_system_entity(
            entity_id,
            actor=actor,
            event_id=f"system:entity:{entity_id}:remove:{current['source_sequence']}",
        )
        rebuild_system_projection()

    def list_entities(
        self,
        *,
        entity_type: SystemEntityType | str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        kind = entity_type.value if isinstance(entity_type, SystemEntityType) else entity_type
        if kind is not None and kind not in {item.value for item in SystemEntityType}:
            raise SystemModelValidationError(f"unknown entity type {kind!r}")
        conditions: list[str] = []
        parameters: list[Any] = []
        if kind is not None:
            conditions.append("entity_type=?")
            parameters.append(kind)
        if status is not None:
            if not isinstance(status, str) or not status.strip():
                raise SystemModelValidationError("status must be non-empty")
            conditions.append("status=?")
            parameters.append(status.strip())
        where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        conn = get_connection()
        try:
            _ensure_runtime_schema(conn)
            rows = conn.execute(
                f"SELECT * FROM mc_system_entities{where} ORDER BY canonical_key,entity_id",
                tuple(parameters),
            ).fetchall()
            return [_entity_dict(row) for row in rows]
        finally:
            conn.close()

    def list_edges(
        self,
        *,
        entity_id: str | None = None,
        edge_type: str | None = None,
    ) -> list[dict[str, Any]]:
        conditions: list[str] = []
        parameters: list[Any] = []
        if entity_id is not None:
            conditions.append("(from_entity_id=? OR to_entity_id=?)")
            parameters.extend((entity_id, entity_id))
        if edge_type is not None:
            if not isinstance(edge_type, str) or not edge_type.strip():
                raise SystemModelValidationError("edge_type must be non-empty")
            conditions.append("edge_type=?")
            parameters.append(edge_type.strip())
        where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        conn = get_connection()
        try:
            _ensure_runtime_schema(conn)
            rows = conn.execute(
                f"SELECT * FROM mc_system_edges{where} ORDER BY edge_type,edge_id",
                tuple(parameters),
            ).fetchall()
            return [_edge_dict(row) for row in rows]
        finally:
            conn.close()

    def get_entity(self, entity_id: str, *, include_edges: bool = False) -> dict[str, Any] | None:
        conn = get_connection()
        try:
            _ensure_runtime_schema(conn)
            row = conn.execute(
                "SELECT * FROM mc_system_entities WHERE entity_id=?", (entity_id,)
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            return None
        result = _entity_dict(row)
        if include_edges:
            result["edges"] = self.list_edges(entity_id=entity_id)
        return result

    def get_edge(self, edge_id: str) -> dict[str, Any] | None:
        conn = get_connection()
        try:
            _ensure_runtime_schema(conn)
            row = conn.execute(
                "SELECT * FROM mc_system_edges WHERE edge_id=?", (edge_id,)
            ).fetchone()
            return _edge_dict(row) if row is not None else None
        finally:
            conn.close()

    def snapshot(self) -> dict[str, Any]:
        return {
            "entities": self.list_entities(),
            "edges": self.list_edges(),
        }

"""Deterministic entity lookup and typed tool-request acceptance."""
from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Mapping

from core.database import get_connection
from core.runtime.contracts import RuntimeToolCall, SideEffectClass, Surface
from core.runtime.tool_catalog import (
    CanonicalToolCatalog,
    ToolCallPreparationError,
    ToolCatalogError,
)
from core.runtime.tool_registry import ToolRegistryError, ToolValidationError
from core.runtime.workflows import (
    SupportedWorkflowCatalog,
    WorkflowBoundaryError,
)


EntityKind = Literal["project", "task", "resource"]
EntityStatus = Literal["resolved", "clarify", "missing", "not_found", "invalid"]
TypedResolutionStatus = Literal["accepted", "clarify", "rejected"]
_ENTITY_FIELDS: tuple[tuple[str, EntityKind], ...] = (
    ("project_id", "project"),
    ("task_id", "task"),
    ("resource_id", "resource"),
)
_ENTITY_SPECS = {
    "project": {
        "table": "pm_projects",
        "label": "name",
        "parent": None,
        "active": "1=1",
    },
    "task": {
        "table": "tasks",
        "label": "title",
        "parent": "pm_project_id",
        "active": "deleted_at IS NULL",
    },
    "resource": {
        "table": "pm_resources",
        "label": "name",
        "parent": "project_id",
        "active": "1=1",
    },
}


def _required_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty text")
    return value.strip()


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _contract_hash(
    workflow_id: str,
    workflow_version: str,
    tool_ref: str,
    arguments: Mapping[str, Any],
) -> str:
    return _digest({
        "workflow_id": workflow_id,
        "workflow_version": workflow_version,
        "tool_ref": tool_ref,
        "arguments": dict(arguments),
    })


@dataclass(frozen=True)
class EntityCandidate:
    kind: EntityKind
    id: int
    label: str
    parent_id: int | None = None

    def __post_init__(self) -> None:
        if self.kind not in _ENTITY_SPECS:
            raise ValueError("unsupported entity kind")
        if isinstance(self.id, bool) or not isinstance(self.id, int) or self.id < 1:
            raise ValueError("entity id must be a positive integer")
        _required_text(self.label, "entity label")
        if self.parent_id is not None and (
            isinstance(self.parent_id, bool)
            or not isinstance(self.parent_id, int)
            or self.parent_id < 1
        ):
            raise ValueError("parent id must be a positive integer")

    @property
    def ref(self) -> str:
        return f"{self.kind}:{self.id}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "ref": self.ref,
            "id": self.id,
            "label": self.label[:80],
            "parent_ref": f"project:{self.parent_id}" if self.parent_id else None,
        }


@dataclass(frozen=True)
class EntityResolution:
    status: EntityStatus
    kind: EntityKind
    reason: str
    candidate: EntityCandidate | None = None
    choices: tuple[EntityCandidate, ...] = ()


class EntityRepository:
    """Read only bounded lookup over the current Project v2 tables."""

    def __init__(self, connection_factory: Callable[[], Any] = get_connection) -> None:
        if not callable(connection_factory):
            raise ValueError("connection_factory must be callable")
        self._connection_factory = connection_factory

    @staticmethod
    def _positive_id(value: Any) -> int | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value if 0 < value <= 9_223_372_036_854_775_807 else None
        if isinstance(value, str) and value.strip().isdigit():
            parsed = int(value.strip())
            return parsed if 0 < parsed <= 9_223_372_036_854_775_807 else None
        return None

    def _rows(
        self,
        kind: EntityKind,
        where: str,
        parameters: tuple[Any, ...],
        *,
        project_id: int | None,
        limit: int,
        recent: bool = False,
    ) -> list[Any]:
        spec = _ENTITY_SPECS[kind]
        parent = spec["parent"]
        parent_select = parent if parent else "NULL"
        clauses = [str(spec["active"]), where]
        values = list(parameters)
        if parent and project_id is not None:
            clauses.append(f"{parent}=?")
            values.append(project_id)
        order = "updated_at DESC, id DESC" if recent else "id ASC"
        sql = (
            f"SELECT id, {spec['label']} AS label, {parent_select} AS parent_id "
            f"FROM {spec['table']} WHERE {' AND '.join(clauses)} "
            f"ORDER BY {order} LIMIT ?"
        )
        values.append(limit)
        conn = self._connection_factory()
        try:
            return conn.execute(sql, tuple(values)).fetchall()
        finally:
            conn.close()

    @staticmethod
    def _candidates(kind: EntityKind, rows: list[Any]) -> tuple[EntityCandidate, ...]:
        return tuple(
            EntityCandidate(
                kind=kind,
                id=int(row["id"]),
                label=str(row["label"] or "Unnamed")[:80],
                parent_id=int(row["parent_id"]) if row["parent_id"] is not None else None,
            )
            for row in rows[:5]
        )

    def recent(
        self, kind: EntityKind, *, project_id: int | None = None,
    ) -> tuple[EntityCandidate, ...]:
        if kind not in _ENTITY_SPECS:
            return ()
        scope = self._positive_id(project_id) if project_id is not None else None
        if project_id is not None and scope is None:
            return ()
        rows = self._rows(
            kind, "1=1", (), project_id=scope, limit=5, recent=True,
        )
        return self._candidates(kind, rows)

    def resolve(
        self,
        kind: EntityKind,
        value: Any,
        *,
        project_id: int | str | None = None,
    ) -> EntityResolution:
        if kind not in _ENTITY_SPECS:
            return EntityResolution("invalid", kind, "entity.kind_invalid")
        if kind == "project" and project_id is not None:
            return EntityResolution("invalid", kind, "entity.scope_invalid")
        scope = self._positive_id(project_id) if project_id is not None else None
        if project_id is not None and scope is None:
            return EntityResolution("invalid", kind, "entity.scope_invalid")
        if value is None or (isinstance(value, str) and not value.strip()):
            return EntityResolution(
                "missing",
                kind,
                "entity.missing",
                choices=self.recent(kind, project_id=scope),
            )
        if isinstance(value, bool) or isinstance(value, (float, list, tuple, dict, set)):
            return EntityResolution("invalid", kind, "entity.value_invalid")

        numeric = self._positive_id(value)
        if isinstance(value, int) or (isinstance(value, str) and value.strip().isdigit()):
            if numeric is None:
                return EntityResolution("invalid", kind, "entity.id_invalid")
            rows = self._rows(
                kind, "id=?", (numeric,), project_id=scope, limit=2,
            )
            choices = self._candidates(kind, rows)
            if len(choices) == 1:
                return EntityResolution("resolved", kind, "entity.id_exact", choices[0])
            return EntityResolution(
                "not_found",
                kind,
                "entity.id_not_found",
                choices=self.recent(kind, project_id=scope),
            )

        if not isinstance(value, str):
            return EntityResolution("invalid", kind, "entity.value_invalid")
        query = value.strip()
        if len(query) > 120:
            return EntityResolution("invalid", kind, "entity.query_too_long")
        label = str(_ENTITY_SPECS[kind]["label"])
        exact_rows = self._rows(
            kind,
            f"lower({label})=lower(?)",
            (query,),
            project_id=scope,
            limit=6,
        )
        exact = self._candidates(kind, exact_rows)
        if len(exact_rows) == 1:
            return EntityResolution("resolved", kind, "entity.name_exact", exact[0])
        if len(exact_rows) > 1:
            return EntityResolution("clarify", kind, "entity.name_ambiguous", choices=exact)

        partial_rows = self._rows(
            kind,
            f"instr(lower({label}), lower(?)) > 0",
            (query,),
            project_id=scope,
            limit=6,
        )
        partial = self._candidates(kind, partial_rows)
        if len(partial_rows) == 1:
            return EntityResolution("resolved", kind, "entity.name_unique_partial", partial[0])
        if len(partial_rows) > 1:
            return EntityResolution("clarify", kind, "entity.name_ambiguous", choices=partial)
        return EntityResolution(
            "not_found",
            kind,
            "entity.name_not_found",
            choices=self.recent(kind, project_id=scope),
        )


@dataclass(frozen=True)
class AcceptedTypedRequest:
    workflow_id: str
    workflow_version: str
    run_id: str
    step_id: str
    call_id: str
    tool_ref: str
    surface: Surface
    mode: str
    arguments_json: str = field(repr=False)
    contract_hash: str
    idempotency_key: str | None
    entity_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in (
            "workflow_id", "workflow_version", "run_id", "step_id", "call_id",
            "tool_ref", "mode", "contract_hash",
        ):
            _required_text(getattr(self, name), name)
        if not isinstance(self.surface, Surface):
            raise ValueError("surface must be a Surface")
        try:
            arguments = json.loads(self.arguments_json)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError("arguments_json must contain a JSON object") from exc
        if not isinstance(arguments, dict):
            raise ValueError("arguments_json must contain a JSON object")
        expected = _contract_hash(
            self.workflow_id, self.workflow_version, self.tool_ref, arguments,
        )
        if expected != self.contract_hash:
            raise ValueError("typed request contract hash does not match")

    @property
    def arguments(self) -> dict[str, Any]:
        return json.loads(self.arguments_json)

    def to_runtime_call(self, tools: CanonicalToolCatalog) -> RuntimeToolCall:
        if not isinstance(tools, CanonicalToolCatalog):
            raise ValueError("tools must be a CanonicalToolCatalog")
        return tools.prepare_call(
            call_id=self.call_id,
            run_id=self.run_id,
            step_id=self.step_id,
            tool_ref=self.tool_ref,
            arguments=self.arguments,
            surface=self.surface,
            mode=self.mode,
            candidate_tool_refs=(self.tool_ref,),
            idempotency_key=self.idempotency_key,
        )

    def to_trace_payload(self) -> dict[str, str]:
        return {
            "typed_request_ref": f"typed-request:{self.contract_hash}",
            "workflow_ref": f"workflow:{self.workflow_id}@v{self.workflow_version}",
            "tool_ref": self.tool_ref,
        }


@dataclass(frozen=True)
class TypedRequestResolution:
    status: TypedResolutionStatus
    reason: str
    accepted: AcceptedTypedRequest | None = None
    missing_fields: tuple[str, ...] = ()
    invalid_fields: tuple[str, ...] = ()
    choices: tuple[EntityCandidate, ...] = ()


class TypedRequestResolver:
    """Final code-owned boundary between workflow/model proposals and executable calls."""

    def __init__(
        self,
        *,
        workflows: SupportedWorkflowCatalog,
        tools: CanonicalToolCatalog,
        entities: EntityRepository,
    ) -> None:
        if not isinstance(workflows, SupportedWorkflowCatalog):
            raise ValueError("workflows must be a SupportedWorkflowCatalog")
        if not isinstance(tools, CanonicalToolCatalog):
            raise ValueError("tools must be a CanonicalToolCatalog")
        if not isinstance(entities, EntityRepository):
            raise ValueError("entities must be an EntityRepository")
        self._workflows = workflows
        self._tools = tools
        self._entities = entities

    def _missing_choices(self, fields: tuple[str, ...]) -> tuple[EntityCandidate, ...]:
        choices: list[EntityCandidate] = []
        for field_name, kind in _ENTITY_FIELDS:
            if field_name in fields:
                choices.extend(self._entities.recent(kind))
        unique = {choice.ref: choice for choice in choices}
        return tuple(unique[key] for key in sorted(unique))[:5]

    @staticmethod
    def _rejected(
        reason: str, *, invalid_fields: tuple[str, ...] = (),
    ) -> TypedRequestResolution:
        return TypedRequestResolution(
            status="rejected", reason=reason, invalid_fields=invalid_fields,
        )

    def resolve(
        self,
        *,
        message: str,
        run_id: str,
        step_id: str,
        call_id: str,
        proposed_arguments: Mapping[str, Any],
        proposed_tool_ref: str | None,
        surface: Surface,
        mode: str,
        proposed_workflow_id: str | None = None,
    ) -> TypedRequestResolution:
        if not isinstance(proposed_arguments, Mapping):
            return self._rejected("arguments.not_object")
        try:
            arguments = copy.deepcopy(dict(proposed_arguments))
        except Exception:
            return self._rejected("arguments.not_copyable")

        selection = self._workflows.select(message, arguments)
        if selection.status != "matched" or selection.workflow is None:
            return TypedRequestResolution(
                status="clarify",
                reason=selection.reason,
                missing_fields=selection.missing_fields,
                choices=self._missing_choices(selection.missing_fields),
            )
        workflow = selection.workflow
        if proposed_tool_ref is None:
            if len(workflow.allowed_tools) == 1:
                tool_ref = workflow.allowed_tools[0]
            elif len(workflow.allowed_tools) > 1:
                return TypedRequestResolution("clarify", "tool.choice_required")
            else:
                return self._rejected("tool.workflow_has_no_tool")
        else:
            tool_ref = proposed_tool_ref
        try:
            self._workflows.enforce(
                selection,
                proposed_workflow_id=proposed_workflow_id,
                proposed_tools=(tool_ref,),
            )
            spec = self._tools.get_spec(tool_ref)
        except (WorkflowBoundaryError, ToolCatalogError, ToolRegistryError, ValueError):
            return self._rejected("tool.workflow_boundary")

        properties = spec.input_schema.get("properties")
        properties = properties if isinstance(properties, dict) else {}
        extra = tuple(sorted(set(arguments) - set(properties)))
        if extra:
            return self._rejected("arguments.unknown_fields", invalid_fields=extra)
        schema_required = spec.input_schema.get("required")
        required = tuple(schema_required) if isinstance(schema_required, list) else ()
        missing = tuple(
            field_name
            for field_name in required
            if field_name not in arguments
            or arguments[field_name] is None
            or (isinstance(arguments[field_name], str) and not arguments[field_name].strip())
        )
        if missing:
            return TypedRequestResolution(
                status="clarify",
                reason="arguments.missing_fields",
                missing_fields=missing,
                choices=self._missing_choices(missing),
            )

        entity_refs: list[str] = []
        for field_name, kind in _ENTITY_FIELDS:
            if field_name not in arguments:
                continue
            project_scope = arguments.get("project_id") if kind != "project" else None
            resolved = self._entities.resolve(
                kind, arguments[field_name], project_id=project_scope,
            )
            if resolved.status != "resolved" or resolved.candidate is None:
                if resolved.status == "invalid":
                    return self._rejected(
                        resolved.reason, invalid_fields=(field_name,),
                    )
                return TypedRequestResolution(
                    status="clarify",
                    reason=resolved.reason,
                    missing_fields=(field_name,) if resolved.status == "missing" else (),
                    choices=resolved.choices,
                )
            arguments[field_name] = resolved.candidate.id
            entity_refs.append(resolved.candidate.ref)

        try:
            validated = self._tools.validate_arguments(tool_ref, arguments)
        except (ToolValidationError, ToolRegistryError, TypeError, ValueError):
            return self._rejected("arguments.schema_invalid")
        try:
            contract_hash = _contract_hash(
                workflow.workflow_id, workflow.version, tool_ref, validated,
            )
        except (TypeError, ValueError):
            return self._rejected("arguments.not_canonical_json")
        idempotency_key = None
        if spec.side_effect_class is not SideEffectClass.NONE:
            idempotency_payload = {
                'run_id': run_id,
                'step_id': step_id,
                'contract_hash': contract_hash,
            }
            idempotency_key = f"typed-action:{_digest(idempotency_payload)}"
        try:
            call = self._tools.prepare_call(
                call_id=call_id,
                run_id=run_id,
                step_id=step_id,
                tool_ref=tool_ref,
                arguments=validated,
                surface=surface,
                mode=mode,
                candidate_tool_refs=(tool_ref,),
                idempotency_key=idempotency_key,
            )
        except (ToolCallPreparationError, ToolCatalogError, TypeError, ValueError):
            return self._rejected("tool.call_invalid")

        accepted = AcceptedTypedRequest(
            workflow_id=workflow.workflow_id,
            workflow_version=workflow.version,
            run_id=call.run_id,
            step_id=call.step_id,
            call_id=call.call_id,
            tool_ref=call.tool_ref,
            surface=surface,
            mode=mode,
            arguments_json=_canonical_json(call.validated_arguments),
            contract_hash=contract_hash,
            idempotency_key=call.idempotency_key,
            entity_refs=tuple(sorted(set(entity_refs))),
        )
        return TypedRequestResolution(
            status="accepted", reason="arguments.accepted", accepted=accepted,
        )

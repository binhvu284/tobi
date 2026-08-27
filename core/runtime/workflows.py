"""Versioned deterministic workflow selection for bounded Mission Control work."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from functools import lru_cache
from typing import Any, Iterable, Literal, Mapping

from tobival.dataset import (
    DatasetContractError,
    load_supported_workflows,
    verify_dataset_lock,
)


SelectionStatus = Literal["matched", "clarify", "unsupported"]
_WORKFLOW_FIELDS = {
    "workflow_id", "intents", "required_fields", "allowed_tools", "policy_class",
    "stop_condition", "success_evidence", "recovery_options", "summary_shape",
}
_ACTION_POLICIES = {"reversible_action", "terminal_action"}
_RECOVERY_POLICIES = {"recovery"}


class WorkflowCatalogError(ValueError):
    """The frozen workflow catalog is missing or violates its declared contract."""


class WorkflowBoundaryError(ValueError):
    """A proposed route or tool is outside the deterministically selected workflow."""


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorkflowCatalogError(f"{field} must be non-empty text")
    return value.strip()


def _text_tuple(value: Any, field: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise WorkflowCatalogError(f"{field} must be a list")
    result = tuple(_required_text(item, field) for item in value)
    if not allow_empty and not result:
        raise WorkflowCatalogError(f"{field} must not be empty")
    if len(set(result)) != len(result):
        raise WorkflowCatalogError(f"{field} must not contain duplicates")
    return result


@dataclass(frozen=True)
class WorkflowDefinition:
    workflow_id: str
    version: str
    intents: tuple[str, ...]
    required_fields: tuple[str, ...]
    allowed_tools: tuple[str, ...]
    policy_class: str
    stop_condition: str
    success_evidence: tuple[str, ...]
    recovery_options: tuple[str, ...]
    summary_shape: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "WorkflowDefinition":
        if set(value) != _WORKFLOW_FIELDS:
            workflow_id = value.get("workflow_id", "<unknown>")
            raise WorkflowCatalogError(f"{workflow_id} has an invalid workflow field set")
        return cls(
            workflow_id=_required_text(value["workflow_id"], "workflow_id"),
            version="1",
            intents=_text_tuple(value["intents"], "intents"),
            required_fields=_text_tuple(
                value["required_fields"], "required_fields", allow_empty=True,
            ),
            allowed_tools=_text_tuple(
                value["allowed_tools"], "allowed_tools", allow_empty=True,
            ),
            policy_class=_required_text(value["policy_class"], "policy_class"),
            stop_condition=_required_text(value["stop_condition"], "stop_condition"),
            success_evidence=_text_tuple(value["success_evidence"], "success_evidence"),
            recovery_options=_text_tuple(value["recovery_options"], "recovery_options"),
            summary_shape=_required_text(value["summary_shape"], "summary_shape"),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WorkflowSelection:
    status: SelectionStatus
    workflow: WorkflowDefinition | None
    reason: str
    matched_intents: tuple[str, ...] = ()
    missing_fields: tuple[str, ...] = ()
    candidate_workflow_ids: tuple[str, ...] = ()

    def to_trace_payload(self) -> dict[str, str]:
        payload = {
            "selection_reason_ref": f"workflow-selection:{self.reason}"[:240],
        }
        if self.workflow is not None:
            payload["workflow_ref"] = (
                f"workflow:{self.workflow.workflow_id}@v{self.workflow.version}"
            )[:240]
        return payload


@dataclass(frozen=True)
class WorkflowRoute:
    workflow_id: str
    version: str
    route: str
    policy_class: str
    allowed_tools: tuple[str, ...]
    selection_reason: str
    stop_condition: str
    success_evidence: tuple[str, ...]
    recovery_options: tuple[str, ...]
    summary_shape: str


def _normalize(text: str) -> str:
    if not isinstance(text, str):
        return ""
    return re.sub(r"\s+", " ", re.sub(r"[^\w]+", " ", text.casefold())).strip()


def _contains_intent(tokens: tuple[str, ...], intent: tuple[str, ...]) -> bool:
    """Match intent words in order while allowing harmless owner wording between them."""
    if not intent:
        return False
    position = 0
    for token in tokens:
        if token == intent[position]:
            position += 1
            if position == len(intent):
                return True
    return False


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def _route_for_policy(policy_class: str) -> str:
    if policy_class in _ACTION_POLICIES:
        return "action"
    if policy_class in _RECOVERY_POLICIES:
        return "recovery"
    return "read"


class SupportedWorkflowCatalog:
    def __init__(
        self,
        definitions: Iterable[WorkflowDefinition],
        *,
        dataset_version: str,
        lock_sha256: str,
    ) -> None:
        items = tuple(definitions)
        if not items:
            raise WorkflowCatalogError("workflow catalog must not be empty")
        identities = [item.workflow_id for item in items]
        if len(set(identities)) != len(identities):
            raise WorkflowCatalogError("workflow IDs must be unique")
        self.definitions = items
        self.dataset_version = _required_text(dataset_version, "dataset_version")
        self.lock_sha256 = _required_text(lock_sha256, "lock_sha256")
        self._by_id = {item.workflow_id: item for item in items}

    def get(self, workflow_id: str) -> WorkflowDefinition:
        try:
            return self._by_id[workflow_id]
        except KeyError as exc:
            raise WorkflowCatalogError(f"unknown supported workflow: {workflow_id}") from exc

    def select(
        self,
        text: str,
        fields: Mapping[str, Any] | None = None,
    ) -> WorkflowSelection:
        if fields is not None and not isinstance(fields, Mapping):
            raise WorkflowBoundaryError("fields must be a mapping")
        normalized = _normalize(text)
        if not normalized:
            return WorkflowSelection(
                status="unsupported",
                workflow=None,
                reason="unsupported:no_supported_intent",
            )

        tokens = tuple(normalized.split())
        matches: list[tuple[int, WorkflowDefinition, str]] = []
        for workflow in self.definitions:
            for intent in workflow.intents:
                normalized_intent = _normalize(intent)
                intent_tokens = tuple(normalized_intent.split())
                if _contains_intent(tokens, intent_tokens):
                    matches.append((len(intent_tokens), workflow, intent))
        if not matches:
            return WorkflowSelection(
                status="unsupported",
                workflow=None,
                reason="unsupported:no_supported_intent",
            )

        best_score = max(score for score, _, _ in matches)
        best = [(workflow, intent) for score, workflow, intent in matches if score == best_score]
        candidates = tuple(sorted({workflow.workflow_id for workflow, _ in best}))
        matched_intents = tuple(sorted({intent for _, intent in best}))
        if len(candidates) != 1:
            return WorkflowSelection(
                status="clarify",
                workflow=None,
                reason=f"ambiguous:{','.join(candidates)}",
                matched_intents=matched_intents,
                candidate_workflow_ids=candidates,
            )

        workflow = self._by_id[candidates[0]]
        supplied = fields or {}
        missing = tuple(
            field for field in workflow.required_fields if not _has_value(supplied.get(field))
        )
        if missing:
            return WorkflowSelection(
                status="clarify",
                workflow=workflow,
                reason=f"missing_fields:{workflow.workflow_id}:{','.join(missing)}",
                matched_intents=matched_intents,
                missing_fields=missing,
                candidate_workflow_ids=(workflow.workflow_id,),
            )
        return WorkflowSelection(
            status="matched",
            workflow=workflow,
            reason=f"matched:{workflow.workflow_id}@v{workflow.version}",
            matched_intents=matched_intents,
            candidate_workflow_ids=(workflow.workflow_id,),
        )

    def enforce(
        self,
        selection: WorkflowSelection,
        *,
        proposed_workflow_id: str | None = None,
        proposed_tools: Iterable[str] | None = None,
    ) -> WorkflowRoute:
        if not isinstance(selection, WorkflowSelection):
            raise WorkflowBoundaryError("selection must be a WorkflowSelection")
        if selection.status != "matched" or selection.workflow is None:
            raise WorkflowBoundaryError("only a matched workflow can be enforced")
        workflow = selection.workflow
        if proposed_workflow_id is not None and proposed_workflow_id != workflow.workflow_id:
            raise WorkflowBoundaryError(
                f"proposed workflow {proposed_workflow_id!r} is outside {workflow.workflow_id!r}"
            )

        if proposed_tools is None:
            allowed_tools = workflow.allowed_tools
        else:
            if isinstance(proposed_tools, (str, bytes)):
                raise WorkflowBoundaryError("proposed_tools must be a collection of tool refs")
            proposed = tuple(proposed_tools)
            if any(not isinstance(tool, str) or not tool.strip() for tool in proposed):
                raise WorkflowBoundaryError("proposed tool refs must be non-empty text")
            if len(set(proposed)) != len(proposed):
                raise WorkflowBoundaryError("proposed tool refs must not contain duplicates")
            escaped = sorted(set(proposed) - set(workflow.allowed_tools))
            if escaped:
                raise WorkflowBoundaryError(
                    f"tools outside {workflow.workflow_id}: {', '.join(escaped)}"
                )
            proposed_set = set(proposed)
            allowed_tools = tuple(
                tool for tool in workflow.allowed_tools if tool in proposed_set
            )

        return WorkflowRoute(
            workflow_id=workflow.workflow_id,
            version=workflow.version,
            route=_route_for_policy(workflow.policy_class),
            policy_class=workflow.policy_class,
            allowed_tools=allowed_tools,
            selection_reason=selection.reason,
            stop_condition=workflow.stop_condition,
            success_evidence=workflow.success_evidence,
            recovery_options=workflow.recovery_options,
            summary_shape=workflow.summary_shape,
        )


@lru_cache(maxsize=1)
def supported_workflow_catalog() -> SupportedWorkflowCatalog:
    try:
        lock = verify_dataset_lock("v1")
        definitions = tuple(
            WorkflowDefinition.from_mapping(item)
            for item in load_supported_workflows("v1")
        )
    except (DatasetContractError, WorkflowCatalogError) as exc:
        raise WorkflowCatalogError(str(exc)) from exc
    return SupportedWorkflowCatalog(
        definitions,
        dataset_version=lock["dataset_version"],
        lock_sha256=lock["aggregate_sha256"],
    )

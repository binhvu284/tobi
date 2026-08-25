"""Deterministic, local-first Runtime trace projections."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from core.database import get_connection
from core.runtime.event_store import list_run_events
from core.schema.runtime import _ensure_runtime_schema


_REFERENCE_KINDS = {
    "approval_id": "approval",
    "approval_ref": "approval",
    "artifact_id": "artifact",
    "checkpoint_id": "checkpoint",
    "context_manifest_ref": "context",
    "evidence_id": "evidence",
    "model_ref": "model",
    "policy_decision_id": "policy",
    "policy_decision_ref": "policy",
    "receipt_id": "receipt",
    "receipt_ref": "receipt",
    "result_ref": "outcome",
    "selection_reason_ref": "selection_reason",
    "tool_ref": "tool",
    "typed_request_ref": "evidence",
    "workflow_ref": "workflow",
}


@dataclass(frozen=True)
class TraceSpan:
    sequence: int
    event_id: str
    event_type: str
    stage: str
    actor: str
    timestamp: str
    references: tuple[tuple[str, str], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "event_id": self.event_id,
            "event_type": self.event_type,
            "stage": self.stage,
            "actor": self.actor,
            "timestamp": self.timestamp,
            "references": [{"kind": kind, "ref": ref} for kind, ref in self.references],
        }


@dataclass(frozen=True)
class RunTrace:
    trace_id: str
    run_id: str
    surface: str
    status: str
    spans: tuple[TraceSpan, ...]
    context_refs: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    workflow_refs: tuple[str, ...]
    selection_reason_refs: tuple[str, ...]
    model_refs: tuple[str, ...]
    tool_refs: tuple[str, ...]
    policy_decision_refs: tuple[str, ...]
    approval_refs: tuple[str, ...]
    receipt_refs: tuple[str, ...]
    recovery_refs: tuple[str, ...]
    outcome_refs: tuple[str, ...]
    usage: tuple[tuple[str, int], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "run_id": self.run_id,
            "surface": self.surface,
            "status": self.status,
            "spans": [span.to_dict() for span in self.spans],
            "context_refs": list(self.context_refs),
            "evidence_refs": list(self.evidence_refs),
            "workflow_refs": list(self.workflow_refs),
            "selection_reason_refs": list(self.selection_reason_refs),
            "model_refs": list(self.model_refs),
            "tool_refs": list(self.tool_refs),
            "policy_decision_refs": list(self.policy_decision_refs),
            "approval_refs": list(self.approval_refs),
            "receipt_refs": list(self.receipt_refs),
            "recovery_refs": list(self.recovery_refs),
            "outcome_refs": list(self.outcome_refs),
            "usage": dict(self.usage),
        }


def _add_ref(target: dict[str, set[str]], kind: str, value: Any) -> None:
    if isinstance(value, (str, int)) and str(value).strip():
        target.setdefault(kind, set()).add(str(value).strip()[:240])


def _payload_refs(payload: Mapping[str, Any]) -> tuple[tuple[str, str], ...]:
    refs: dict[str, set[str]] = {}
    for field, kind in _REFERENCE_KINDS.items():
        _add_ref(refs, kind, payload.get(field))
    return tuple(sorted((kind, ref) for kind, values in refs.items() for ref in values))


def _column_refs(rows: Iterable[Any], column: str) -> tuple[str, ...]:
    return tuple(sorted({str(row[column]) for row in rows if row[column]}))


def build_run_trace(run_id: str) -> RunTrace:
    """Rebuild a bounded trace from authoritative records without copying their bodies."""
    conn = get_connection()
    try:
        _ensure_runtime_schema(conn)
        run = conn.execute(
            "SELECT run_id,surface,status FROM mc_runs WHERE run_id=?", (run_id,)
        ).fetchone()
        if run is None:
            raise KeyError(run_id)
        policies = conn.execute(
            "SELECT decision_id,tool_ref FROM mc_policy_decisions WHERE run_id=? ORDER BY created_at,decision_id",
            (run_id,),
        ).fetchall()
        approvals = conn.execute(
            "SELECT approval_id,tool_ref FROM mc_run_approvals WHERE run_id=? ORDER BY requested_at,approval_id",
            (run_id,),
        ).fetchall()
        receipts = conn.execute(
            "SELECT receipt_id,tool_ref FROM mc_action_receipts WHERE run_id=? ORDER BY created_at,receipt_id",
            (run_id,),
        ).fetchall()
        loop = conn.execute(
            """SELECT model_calls,tool_calls,prompt_tokens,completion_tokens,runtime_ms,
                      cost_microusd,download_bytes,storage_bytes
               FROM mc_loop_runs WHERE run_id=?""",
            (run_id,),
        ).fetchone()
    finally:
        conn.close()

    events = list_run_events(run_id)
    refs: dict[str, set[str]] = {}
    spans: list[TraceSpan] = []
    recovery: set[str] = set()
    trace_ids: set[str] = set()
    for event in events:
        if event.trace_id:
            trace_ids.add(event.trace_id)
        event_refs = _payload_refs(event.redacted_payload)
        for kind, ref in event_refs:
            refs.setdefault(kind, set()).add(ref)
        lowered = f"{event.event_type} {event.stage}".lower()
        if any(marker in lowered for marker in ("recover", "retry", "failure", "failed", "error", "blocked")):
            recovery.add(event.event_id)
        spans.append(TraceSpan(
            sequence=event.sequence,
            event_id=event.event_id,
            event_type=event.event_type,
            stage=event.stage,
            actor=event.actor,
            timestamp=event.timestamp,
            references=event_refs,
        ))

    for row in policies:
        _add_ref(refs, "policy", row["decision_id"])
        _add_ref(refs, "tool", row["tool_ref"])
    for row in approvals:
        _add_ref(refs, "approval", row["approval_id"])
        _add_ref(refs, "tool", row["tool_ref"])
    for row in receipts:
        _add_ref(refs, "receipt", row["receipt_id"])
        _add_ref(refs, "tool", row["tool_ref"])

    usage = tuple(sorted(
        (key, int(loop[key]) if loop is not None else 0)
        for key in (
            "completion_tokens", "cost_microusd", "download_bytes", "model_calls",
            "prompt_tokens", "runtime_ms", "storage_bytes", "tool_calls",
        )
    ))
    outcome = set(refs.get("outcome", set()))
    outcome.add(f"run-status:{run['status']}")
    return RunTrace(
        trace_id=sorted(trace_ids)[0] if trace_ids else f"run:{run_id}",
        run_id=run_id,
        surface=str(run["surface"]),
        status=str(run["status"]),
        spans=tuple(spans),
        context_refs=tuple(sorted(refs.get("context", set()))),
        evidence_refs=tuple(sorted(refs.get("evidence", set()))),
        workflow_refs=tuple(sorted(refs.get("workflow", set()))),
        selection_reason_refs=tuple(sorted(refs.get("selection_reason", set()))),
        model_refs=tuple(sorted(refs.get("model", set()))),
        tool_refs=tuple(sorted(refs.get("tool", set()))),
        policy_decision_refs=tuple(sorted(refs.get("policy", set()))),
        approval_refs=tuple(sorted(refs.get("approval", set()))),
        receipt_refs=tuple(sorted(refs.get("receipt", set()))),
        recovery_refs=tuple(sorted(recovery)),
        outcome_refs=tuple(sorted(outcome)),
        usage=usage,
    )

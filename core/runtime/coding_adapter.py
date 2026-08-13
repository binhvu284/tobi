"""One-way bridge from accepted Developer history into canonical Runtime runs."""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Any, Mapping

from core.runtime.contracts import (
    Capability,
    LoopPolicy,
    LoopRecipe,
    LoopType,
    RunRequest,
    Surface,
)
from core.runtime.event_store import append_run_event
from core.runtime.repository import RuntimeRepository


_RECIPE = LoopRecipe(
    recipe_id="developer.coding-history",
    version="1",
    name="Developer coding history",
    loop_type=LoopType.GOAL,
    trigger="accepted coding session",
    objective="Record one bounded coding workflow",
    stop_condition="Developer workflow reaches a terminal state",
    max_attempts=1,
    max_runtime_s=86_400,
    max_cost_usd=0.0,
    allowed_tools=(),
    recovery_policy="keep_developer_history",
    evidence_required=("reference",),
)
_POLICY = LoopPolicy.from_recipe(
    policy_id="policy-developer-coding-history",
    version="1",
    recipe=_RECIPE,
    policy_decision_id="mc-owned-developer-history",
    enabled=False,
)
_REFERENCE_FIELDS = frozenset({
    "action",
    "artifact_id",
    "attempt",
    "checkpoint_id",
    "command",
    "error_code",
    "evidence_id",
    "evidence_type",
    "goal_id",
    "purpose",
    "queue_id",
    "readiness_id",
    "result_ref",
    "stage",
    "state",
    "status",
    "target_version",
    "version",
    "worker_profile_slug",
})
_SAFE_NAME = re.compile(r"[^a-z0-9_.-]+")


@dataclass(frozen=True)
class CodingMirrorResult:
    ok: bool
    run_id: str | None
    event_id: str | None
    recovery_action: str | None = None
    reason: str | None = None


def _short_ref(value: Any) -> str | int | float | bool | None:
    if value is None or isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, str):
        return value.strip()[:160]
    return None


def _safe_name(value: Any, fallback: str) -> str:
    cleaned = _SAFE_NAME.sub("_", str(value or "").strip().lower()).strip("_.-")
    return cleaned[:80] or fallback


def _mirror_payload(
    session: Mapping[str, Any],
    event: Mapping[str, Any],
) -> dict[str, Any]:
    source_payload = event.get("payload")
    source_payload = source_payload if isinstance(source_payload, Mapping) else {}
    result: dict[str, Any] = {
        "developer_sequence": int(event["sequence"]),
        "source_event": _safe_name(event.get("event_type"), "event"),
        "queue_id": int(session["queue_id"]),
        "state": _safe_name(session.get("state"), "unknown"),
        "stage": _safe_name(source_payload.get("stage") or session.get("stage"), "developer"),
        "worker_ref": _safe_name(session.get("worker_profile_slug"), "unassigned"),
    }
    goal_id = _short_ref(session.get("goal_id"))
    if goal_id is not None:
        result["goal_id"] = goal_id
    for key in sorted(_REFERENCE_FIELDS):
        value = _short_ref(source_payload.get(key))
        if value is not None:
            result[key] = value
    return result


class CodingRuntimeAdapter:
    """Mirror bounded Developer metadata; never direct or execute worker actions."""

    def __init__(self, repository: RuntimeRepository | None = None) -> None:
        self.repository = repository or RuntimeRepository()

    @staticmethod
    def _run_id(session_id: int) -> str:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"tobi:developer:coding-session:{session_id}"))

    def _ensure_run(self, session: Mapping[str, Any]) -> dict[str, Any]:
        session_id = int(session["id"])
        queue_id = int(session["queue_id"])
        request = RunRequest(
            request_id=f"developer-coding-session:{session_id}",
            surface=Surface.DEVELOPER,
            owner_id="owner",
            session_id=f"coding-session:{session_id}",
            mode="coding",
            message=f"Execute accepted Developer Queue item #{queue_id}",
            capability_toggles=(Capability.RUN_CODING,),
            budget_profile="developer-session",
        )
        self.repository.save_loop_recipe(_RECIPE)
        run = self.repository.create_run(
            request,
            loop_policy=_POLICY,
            run_id=self._run_id(session_id),
            actor="mission-control",
            event_id=f"developer-coding-session:{session_id}:accepted",
        )
        return self.repository.link_legacy_run(run["run_id"], f"coding-session:{session_id}")

    def mirror(
        self,
        session: Mapping[str, Any],
        event: Mapping[str, Any],
    ) -> CodingMirrorResult:
        session_id = int(session["id"])
        sequence = int(event["sequence"])
        event_id = f"developer-coding-session:{session_id}:event:{sequence}"
        try:
            run = self._ensure_run(session)
            payload = _mirror_payload(session, event)
            append_run_event(
                run_id=run["run_id"],
                event_type=f"developer.{payload['source_event']}",
                stage=str(payload["stage"]),
                actor="owner" if event.get("actor") == "owner" else "mission-control",
                payload=payload,
                event_id=event_id,
                timestamp=str(event.get("created_at") or "") or None,
                trace_id=f"coding-session:{session_id}",
            )
            return CodingMirrorResult(True, run["run_id"], event_id)
        except Exception as exc:
            return CodingMirrorResult(
                False,
                self._run_id(session_id),
                event_id,
                recovery_action="keep_developer_history",
                reason=f"runtime_mirror_{_safe_name(type(exc).__name__, 'error')}",
            )

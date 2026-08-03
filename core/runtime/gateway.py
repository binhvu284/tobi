"""Chat/Agent acceptance gateway for Mission Control Runtime V2.

Only direct Chat responses may claim live execution in T04. Tool-capable Chat
routes and Agent remain fail-closed shadow adapters.
"""
from __future__ import annotations

import re
import threading
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping

from core.chat_runtime_contracts import TurnRequest
from core.runtime import config
from core.runtime.contracts import (
    ErrorCategory,
    ErrorStage,
    ExecutionPlan,
    LoopPolicy,
    LoopRecipe,
    LoopType,
    PlanStep,
    RecoveryAction,
    RiskLevel,
    RunEvent,
    RunRequest,
    RuntimeErrorInfo,
    RuntimeToolResult,
    Surface,
)
from core.runtime.control import RuntimeControl
from core.runtime.event_store import append_run_event, latest_run_event, list_run_events
from core.runtime.repository import (
    RunConflictError,
    RunNotFoundError,
    RuntimeRepository,
    VersionConflictError,
)
from core.runtime.state import RunStatus


_EVENT_TYPE = re.compile(r"^[a-z][a-z0-9_.-]*$")
_ATTACHMENT_FIELDS = ("name", "mime", "kind", "size", "bytes")
_ACCEPT_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="tobi-gateway-accept")
_ACCEPT_SLOTS = threading.BoundedSemaphore(2)
_MIRROR_POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix="tobi-gateway-mirror")
_MIRROR_SLOTS = threading.BoundedSemaphore(65)
REPLAY_PAGE_LIMIT = 200


@dataclass(frozen=True)
class GatewayAcceptance:
    mode: str
    request_id: str
    run_id: str | None
    sequence: int


@dataclass(frozen=True)
class GatewayExecution:
    disposition: str
    run_id: str
    step_id: str = "respond"
    worker_id: str | None = None
    lease_token: str | None = None
    lease_epoch: int = 0
    reclaimed: bool = False


def _bounded_submit(
    pool: ThreadPoolExecutor,
    slots: threading.BoundedSemaphore,
    callback: Callable[[], Any],
) -> Future | None:
    if not slots.acquire(blocking=False):
        return None
    try:
        future = pool.submit(callback)
    except Exception:
        slots.release()
        raise
    future.add_done_callback(lambda _future: slots.release())
    return future


def submit_gateway_accept(callback: Callable[[], Any]) -> Future | None:
    """Submit one acceptance-side storage call without an unbounded queue."""
    return _bounded_submit(_ACCEPT_POOL, _ACCEPT_SLOTS, callback)


def submit_gateway_mirror(
    gateway: "TurnGateway",
    acceptance: GatewayAcceptance,
    *,
    source_sequence: int,
    event_type: str,
    stage: str,
    payload: Mapping[str, Any] | None = None,
) -> Future | None:
    """Queue one ordered shadow write; return None when the bounded queue is full."""
    return _bounded_submit(
        _MIRROR_POOL,
        _MIRROR_SLOTS,
        lambda: gateway.mirror_event(
            acceptance,
            source_sequence=source_sequence,
            event_type=event_type,
            stage=stage,
            payload=payload,
        ),
    )


def _compatibility_recipe(*, enabled: bool) -> LoopRecipe:
    if enabled:
        return LoopRecipe(
            recipe_id="mc.compat.chat-turn",
            version="2",
            name="Direct Chat compatibility turn",
            loop_type=LoopType.TURN,
            trigger="owner direct Chat request",
            objective="Persist and answer one direct Chat turn through Runtime V2",
            stop_condition="one assistant response is persisted",
            max_attempts=2,
            max_runtime_s=3_600,
            max_cost_usd=5.0,
            max_model_calls=3,
            max_tool_calls=1,
            allowed_tools=(),
            recovery_policy="same_run_retry_once",
            evidence_required=("chat_response",),
        )
    return LoopRecipe(
        recipe_id="mc.compat.chat-turn",
        version="1",
        name="Chat/Agent compatibility turn",
        loop_type=LoopType.TURN,
        trigger="owner Chat or Agent request",
        objective="Observe one legacy turn through the canonical gateway",
        stop_condition="legacy outcome is observed",
        max_attempts=1,
        max_runtime_s=3_600,
        max_cost_usd=0.0,
        max_model_calls=1,
        max_tool_calls=1,
        allowed_tools=(),
        recovery_policy="observe_legacy_only",
        evidence_required=("legacy_outcome",),
    )


def _compatibility_policy(
    recipe: LoopRecipe, request_id: str, *, enabled: bool
) -> LoopPolicy:
    mode = "active" if enabled else "shadow"
    return LoopPolicy.from_recipe(
        policy_id=f"mc.compat.chat-turn.{mode}",
        version="1",
        recipe=recipe,
        policy_decision_id=f"{mode}:{request_id}",
        enabled=enabled,
    )


def _sanitize_attachments(attachments: Iterable[Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
    sanitized: list[dict[str, Any]] = []
    for index, item in enumerate(attachments):
        if not isinstance(item, Mapping):
            raise ValueError(f"attachment {index} must be a mapping")
        summary: dict[str, Any] = {}
        for field in _ATTACHMENT_FIELDS:
            value = item.get(field)
            if value is None or isinstance(value, (str, int, float, bool)):
                if value is not None:
                    summary[field] = value
        sanitized.append(summary)
    return tuple(sanitized)


class TurnGateway:
    """Validate and persist canonical turn identity without executing work."""

    def __init__(self, repository: RuntimeRepository | None = None) -> None:
        self.repository = repository or RuntimeRepository()

    def accept_turn(
        self,
        request: TurnRequest,
        *,
        attachments: Iterable[Mapping[str, Any]] = (),
        owner_id: str = "owner",
        activation_ready: bool = False,
    ) -> GatewayAcceptance:
        if not isinstance(request, TurnRequest):
            raise ValueError("request must be a validated TurnRequest")
        if not isinstance(activation_ready, bool):
            raise ValueError("activation_ready must be a boolean")
        if request.mode not in ("chat", "agent"):
            raise ValueError("request mode must be chat or agent")
        request_id = request.client_turn_id or str(uuid.uuid4())
        canonical = RunRequest(
            request_id=request_id,
            surface=Surface.AGENT if request.mode == "agent" else Surface.CHAT,
            owner_id=owner_id,
            session_id=str(request.session_id),
            mode=request.mode,
            message=request.message,
            attachments=_sanitize_attachments(attachments),
            budget_profile="compatibility-shadow",
        )

        replay = self.repository.find_matching_run(canonical)
        if replay is not None:
            return self._accept_existing(replay, request_id)

        if request.resume_run_id is not None:
            existing = self.repository.get_run_by_legacy_run_id(str(request.resume_run_id))
            if existing is not None:
                if existing["surface"] != Surface.AGENT.value:
                    raise RunConflictError("the resumed canonical run is not an Agent run")
                if existing["session_id"] != str(request.session_id):
                    raise RunConflictError("the resumed canonical run belongs to another session")
                accepted = list_run_events(existing["run_id"], after_sequence=0)[0]
                return GatewayAcceptance(
                    mode=self._persisted_mode(existing),
                    request_id=request_id,
                    run_id=existing["run_id"],
                    sequence=accepted.sequence,
                )

        mode = config.surface_gateway_mode(
            request.mode, activation_ready=activation_ready
        )
        if mode == "off":
            return GatewayAcceptance(mode=mode, request_id=request_id, run_id=None, sequence=0)

        recipe = _compatibility_recipe(enabled=mode == "on")
        self.repository.save_loop_recipe(recipe)
        run = self.repository.create_run(
            canonical,
            loop_policy=_compatibility_policy(recipe, request_id, enabled=mode == "on"),
            actor="gateway",
        )
        accepted = list_run_events(run["run_id"], after_sequence=0)[0]
        return GatewayAcceptance(
            mode=mode,
            request_id=request_id,
            run_id=run["run_id"],
            sequence=accepted.sequence,
        )

    @staticmethod
    def _persisted_mode(run: Mapping[str, Any]) -> str:
        loop = run.get("loop")
        return "on" if isinstance(loop, Mapping) and loop.get("enabled") is True else "shadow"

    def _accept_existing(self, run: Mapping[str, Any], request_id: str) -> GatewayAcceptance:
        accepted = list_run_events(str(run["run_id"]), after_sequence=0)[0]
        return GatewayAcceptance(
            mode=self._persisted_mode(run),
            request_id=request_id,
            run_id=str(run["run_id"]),
            sequence=accepted.sequence,
        )

    def prepare_direct_chat(self, acceptance: GatewayAcceptance) -> GatewayExecution:
        """Advance and exclusively claim one canonical direct-Chat response."""
        if (
            not isinstance(acceptance, GatewayAcceptance)
            or acceptance.mode != "on"
            or not acceptance.run_id
        ):
            raise ValueError("an active gateway acceptance is required")
        run_id = acceptance.run_id
        worker_id = f"chat:{uuid.uuid4().hex}"
        last_conflict: Exception | None = None
        for _attempt in range(8):
            run = self.repository.get_run(run_id)
            if run is None:
                raise RunNotFoundError(run_id)
            if run["surface"] != Surface.CHAT.value:
                raise RunConflictError("only a Chat run can claim direct response execution")
            status = run["status"]
            if status == RunStatus.SUCCEEDED.value:
                return GatewayExecution("replay", run_id)
            if status in {
                RunStatus.RECOVERING.value,
                RunStatus.WAITING_OWNER.value,
                RunStatus.FAILED.value,
                RunStatus.CANCELLED.value,
            }:
                return GatewayExecution("recovery", run_id)
            try:
                if status == RunStatus.ACCEPTED.value:
                    self.repository.transition_run(
                        run_id,
                        RunStatus.ROUTING,
                        expected_version=run["version"],
                        actor="chat-gateway",
                    )
                    continue
                if status == RunStatus.ROUTING.value:
                    plan = ExecutionPlan(
                        plan_id=f"{run_id}:direct-chat",
                        run_id=run_id,
                        version="1",
                        objective=run["objective"],
                        steps=(
                            PlanStep(
                                step_id="respond",
                                kind="respond",
                                risk=RiskLevel.NONE,
                                retry_policy="transient_once",
                                output_contract={"message_id": "integer"},
                            ),
                        ),
                        completion_predicate="one assistant response is persisted",
                    )
                    self.repository.save_plan(
                        plan,
                        expected_version=run["version"],
                        actor="chat-gateway",
                    )
                    continue
                if status == RunStatus.PLANNED.value:
                    self.repository.transition_run(
                        run_id,
                        RunStatus.RUNNING,
                        expected_version=run["version"],
                        actor="chat-gateway",
                    )
                    continue
                if status == RunStatus.RUNNING.value:
                    steps = self.repository.list_steps(run_id)
                    if steps and steps[0]["status"] == "succeeded":
                        self.repository.transition_run(
                            run_id,
                            RunStatus.SUCCEEDED,
                            expected_version=run["version"],
                            actor="chat-gateway",
                        )
                        return GatewayExecution("replay", run_id)
                    claim = self.repository.claim_step(
                        run_id,
                        worker_id=worker_id,
                        lease_seconds=300,
                    )
                    if claim is None:
                        return GatewayExecution("in_progress", run_id)
                    return GatewayExecution(
                        "execute",
                        run_id,
                        step_id=str(claim["step"]["step_id"]),
                        worker_id=worker_id,
                        lease_token=str(claim["lease_token"]),
                        lease_epoch=int(claim["lease_epoch"]),
                        reclaimed=bool(claim["reclaimed"]),
                    )
                return GatewayExecution("in_progress", run_id)
            except VersionConflictError as exc:
                last_conflict = exc
        raise last_conflict or VersionConflictError("the direct Chat run kept changing")

    @staticmethod
    def _require_execution(execution: GatewayExecution) -> None:
        if (
            not isinstance(execution, GatewayExecution)
            or execution.disposition != "execute"
            or not execution.worker_id
            or not execution.lease_token
            or execution.lease_epoch <= 0
        ):
            raise ValueError("an active direct-Chat execution claim is required")

    def complete_direct_chat(
        self,
        execution: GatewayExecution,
        *,
        message_id: int,
        model: str | None,
        prompt_tokens: int,
        completion_tokens: int,
        latency_ms: int,
    ) -> dict[str, Any]:
        """Fence response completion with the active lease, then finish the run."""
        self._require_execution(execution)
        if isinstance(message_id, bool) or not isinstance(message_id, int) or message_id <= 0:
            raise ValueError("message_id must be a positive integer")
        RuntimeControl().record_step_success(
            execution.run_id,
            execution.step_id,
            worker_id=execution.worker_id or "",
            lease_token=execution.lease_token or "",
            lease_epoch=execution.lease_epoch,
            result=RuntimeToolResult(
                status="succeeded",
                typed_output={"message_id": message_id, "model": model},
                evidence_refs=(f"chat_message:{message_id}",),
                timing={"latency_ms": max(0, int(latency_ms))},
                cost={
                    "prompt_tokens": max(0, int(prompt_tokens)),
                    "completion_tokens": max(0, int(completion_tokens)),
                },
            ),
        )
        run = self.repository.get_run(execution.run_id)
        if run is None:
            raise RunNotFoundError(execution.run_id)
        return self.repository.transition_run(
            execution.run_id,
            RunStatus.SUCCEEDED,
            expected_version=run["version"],
            actor="chat-gateway",
        )

    def fail_direct_chat(self, execution: GatewayExecution) -> dict[str, Any]:
        """Persist a safe provider failure and expose same-run recovery state."""
        self._require_execution(execution)
        RuntimeControl().record_step_failure(
            execution.run_id,
            execution.step_id,
            worker_id=execution.worker_id or "",
            lease_token=execution.lease_token or "",
            lease_epoch=execution.lease_epoch,
            result=RuntimeToolResult(
                status="failed",
                retryable=False,
                error=RuntimeErrorInfo(
                    code="chat.response_failed",
                    category=ErrorCategory.AVAILABILITY,
                    stage=ErrorStage.RESPOND,
                    message="The direct Chat response failed",
                    owner_message="TOBI could not finish this reply. Please retry the request.",
                    retryable=False,
                    recovery_actions=(RecoveryAction.RETRY_STEP, RecoveryAction.CANCEL),
                ),
            ),
        )
        run = self.repository.get_run(execution.run_id)
        if run is None:
            raise RunNotFoundError(execution.run_id)
        return run

    def link_legacy_run(
        self, acceptance: GatewayAcceptance, legacy_run_id: str | int
    ) -> dict[str, Any]:
        if not isinstance(acceptance, GatewayAcceptance) or not acceptance.run_id:
            raise ValueError("a canonical gateway acceptance is required")
        return self.repository.link_legacy_run(acceptance.run_id, str(legacy_run_id))

    def replay_events(
        self,
        run_id: str,
        *,
        expected_session_id: str,
        after_sequence: int = 0,
        limit: int = REPLAY_PAGE_LIMIT,
    ) -> list[RunEvent]:
        self._validate_replay_scope(run_id, expected_session_id)
        if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
            raise ValueError("limit must be a positive integer")
        return list_run_events(
            run_id,
            after_sequence=after_sequence,
            limit=min(limit, REPLAY_PAGE_LIMIT),
        )

    def latest_replay_event(self, run_id: str, *, expected_session_id: str) -> RunEvent | None:
        self._validate_replay_scope(run_id, expected_session_id)
        return latest_run_event(run_id)

    def _validate_replay_scope(self, run_id: str, expected_session_id: str) -> dict[str, Any]:
        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError("run_id must be a non-empty string")
        if not isinstance(expected_session_id, str) or not expected_session_id.strip():
            raise ValueError("expected_session_id must be a non-empty string")
        run = self.repository.get_run(run_id)
        if run is None or run["session_id"] != expected_session_id:
            raise RunNotFoundError(run_id)
        return run

    def mirror_event(
        self,
        acceptance: GatewayAcceptance,
        *,
        source_sequence: int,
        event_type: str,
        stage: str,
        payload: Mapping[str, Any] | None = None,
    ):
        if not isinstance(acceptance, GatewayAcceptance) or acceptance.mode != "shadow":
            raise ValueError("a shadow gateway acceptance is required")
        if not acceptance.run_id:
            raise ValueError("the acceptance has no canonical run")
        if isinstance(source_sequence, bool) or not isinstance(source_sequence, int) or source_sequence <= 0:
            raise ValueError("source_sequence must be a positive integer")
        if not isinstance(event_type, str) or not _EVENT_TYPE.fullmatch(event_type):
            raise ValueError("event_type must be a lowercase event identifier")
        if not isinstance(stage, str) or not stage.strip():
            raise ValueError("stage must be a non-empty string")
        if payload is not None and not isinstance(payload, Mapping):
            raise ValueError("payload must be a mapping")

        event_payload = dict(payload or {})
        event_payload.setdefault("request_id", acceptance.request_id)
        return append_run_event(
            run_id=acceptance.run_id,
            event_type=f"shadow.{event_type}",
            stage=stage,
            actor="legacy-adapter",
            payload=event_payload,
            event_id=f"{acceptance.run_id}:shadow:{acceptance.request_id}:{source_sequence}",
        )

"""Dormant Chat/Agent gateway foundation for Mission Control Runtime V2.

T04 Run 1 creates canonical shadow records only. The live Chat route does not
import this module yet, and a shadow policy can never enter execution.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from core.chat_runtime_contracts import TurnRequest
from core.runtime import config
from core.runtime.contracts import LoopPolicy, LoopRecipe, LoopType, RunRequest, Surface
from core.runtime.event_store import append_run_event, list_run_events
from core.runtime.repository import RuntimeRepository


_EVENT_TYPE = re.compile(r"^[a-z][a-z0-9_.-]*$")
_ATTACHMENT_FIELDS = ("name", "mime", "kind", "size", "bytes")


class GatewayNotReadyError(RuntimeError):
    """The requested rollout state is not implemented by this package."""


@dataclass(frozen=True)
class GatewayAcceptance:
    mode: str
    request_id: str
    run_id: str | None
    sequence: int


def _shadow_recipe() -> LoopRecipe:
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


def _shadow_policy(recipe: LoopRecipe, request_id: str) -> LoopPolicy:
    return LoopPolicy.from_recipe(
        policy_id="mc.compat.chat-turn.shadow",
        version="1",
        recipe=recipe,
        policy_decision_id=f"shadow:{request_id}",
        enabled=False,
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
    ) -> GatewayAcceptance:
        if not isinstance(request, TurnRequest):
            raise ValueError("request must be a validated TurnRequest")
        mode = config.gateway_mode()
        request_id = request.client_turn_id or str(uuid.uuid4())
        if mode == "off":
            return GatewayAcceptance(mode=mode, request_id=request_id, run_id=None, sequence=0)
        if mode != "shadow":
            raise GatewayNotReadyError("gateway-on execution is deferred to T04 Run 4")
        if request.mode not in ("chat", "agent"):
            raise ValueError("request mode must be chat or agent")

        recipe = _shadow_recipe()
        self.repository.save_loop_recipe(recipe)
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
        run = self.repository.create_run(
            canonical,
            loop_policy=_shadow_policy(recipe, request_id),
            actor="gateway",
        )
        accepted = list_run_events(run["run_id"], after_sequence=0)[0]
        return GatewayAcceptance(
            mode=mode,
            request_id=request_id,
            run_id=run["run_id"],
            sequence=accepted.sequence,
        )

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

        return append_run_event(
            run_id=acceptance.run_id,
            event_type=f"shadow.{event_type}",
            stage=stage,
            actor="legacy-adapter",
            payload=dict(payload or {}),
            event_id=f"{acceptance.run_id}:shadow:{source_sequence}",
        )

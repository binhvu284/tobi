"""Passive canonical history adapters for legacy Mission Control surfaces."""
from __future__ import annotations

import asyncio
import re
import uuid
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, TypeVar

from core.runtime import config
from core.runtime.contracts import LoopPolicy, LoopRecipe, LoopType, RunRequest, Surface
from core.runtime.event_store import append_run_event, list_run_events
from core.runtime.repository import RuntimeRepository


COMPATIBILITY_SURFACES = ("projects", "office", "cli", "telegram", "scheduler")
_TOKEN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.:@/-]{0,159}$")
_OUTCOMES = frozenset({"succeeded", "failed", "cancelled", "waiting_owner"})
_T = TypeVar("_T")


def _token(value: str, field: str) -> str:
    if not isinstance(value, str) or not _TOKEN.fullmatch(value.strip()):
        raise ValueError(f"{field} is invalid")
    return value.strip()


def _recipe() -> LoopRecipe:
    return LoopRecipe(
        recipe_id="mc.compat.surface",
        version="1",
        name="Legacy surface observation",
        loop_type=LoopType.TURN,
        trigger="legacy surface request",
        objective="Record a bounded legacy surface outcome in canonical history",
        stop_condition="legacy outcome reference is observed",
        max_attempts=1,
        max_runtime_s=86_400,
        max_cost_usd=0.0,
        max_model_calls=1,
        max_tool_calls=1,
        allowed_tools=(),
        recovery_policy="observe_legacy_only",
        evidence_required=("legacy_outcome",),
    )


@dataclass(frozen=True)
class SurfaceAcceptance:
    mode: str
    surface: str
    operation: str
    request_id: str
    run_id: str | None
    sequence: int


class SurfaceRuntimeAdapter:
    """Mirror surface identity and outcomes without taking execution ownership."""

    def __init__(self, repository: RuntimeRepository | None = None) -> None:
        self.repository = repository or RuntimeRepository()

    def accept(
        self,
        *,
        surface: str,
        operation: str,
        request_id: str,
        session_id: str,
        actor: str,
    ) -> SurfaceAcceptance:
        if surface not in COMPATIBILITY_SURFACES:
            raise ValueError("surface has no T15 compatibility adapter")
        operation = _token(operation, "operation")
        request_id = _token(request_id, "request_id")
        session_id = _token(session_id, "session_id")
        actor = _token(actor, "actor")
        if not config.rollout_enabled(config.RUNTIME_V2_EVENTS):
            return SurfaceAcceptance("off", surface, operation, request_id, None, 0)
        recipe = _recipe()
        self.repository.save_loop_recipe(recipe)
        policy = LoopPolicy.from_recipe(
            policy_id=f"mc.compat.surface.{surface}.shadow",
            version="1",
            recipe=recipe,
            policy_decision_id=f"shadow:{surface}:{request_id}",
            enabled=False,
        )
        run = self.repository.create_run(
            RunRequest(
                request_id=request_id,
                surface=Surface(surface),
                owner_id="owner",
                session_id=session_id,
                mode="compatibility",
                message=f"{surface}:{operation}",
                budget_profile="compatibility-shadow",
            ),
            loop_policy=policy,
            actor=actor,
        )
        accepted = list_run_events(run["run_id"], after_sequence=0)[0]
        return SurfaceAcceptance(
            "shadow", surface, operation, request_id, run["run_id"], accepted.sequence,
        )

    def observe(
        self,
        acceptance: SurfaceAcceptance,
        *,
        outcome: str,
        evidence_refs: tuple[str, ...],
    ) -> None:
        if not isinstance(acceptance, SurfaceAcceptance) or acceptance.mode != "shadow" or not acceptance.run_id:
            raise ValueError("a shadow surface acceptance is required")
        if outcome not in _OUTCOMES:
            raise ValueError("outcome is invalid")
        if not isinstance(evidence_refs, tuple) or not 1 <= len(evidence_refs) <= 50:
            raise ValueError("evidence_refs must contain between 1 and 50 references")
        refs = tuple(sorted({_token(ref, "evidence_ref") for ref in evidence_refs}))
        append_run_event(
            run_id=acceptance.run_id,
            event_type="shadow.surface_completed",
            stage="compatibility",
            actor=f"{acceptance.surface}-adapter",
            payload={
                "source_event": acceptance.operation,
                "status": outcome,
                "result_ref": refs[0],
                "evidence_count": len(refs),
            },
            event_id=f"{acceptance.run_id}:surface:completed",
        )

    def safe_accept(self, **kwargs: Any) -> SurfaceAcceptance | None:
        try:
            return self.accept(**kwargs)
        except Exception:
            return None

    def safe_observe(self, acceptance: SurfaceAcceptance | None, **kwargs: Any) -> None:
        if acceptance is None or acceptance.mode != "shadow":
            return
        try:
            self.observe(acceptance, **kwargs)
        except Exception:
            return


def track_sync_surface(
    *,
    surface: str,
    operation: str,
    session_id: str,
    actor: str,
    callback: Callable[[], _T],
    request_id: str | None = None,
) -> _T:
    adapter = SurfaceRuntimeAdapter()
    acceptance = adapter.safe_accept(
        surface=surface,
        operation=operation,
        request_id=request_id or f"{surface}:{uuid.uuid4().hex}",
        session_id=session_id,
        actor=actor,
    )
    try:
        result = callback()
    except BaseException:
        adapter.safe_observe(
            acceptance, outcome="failed", evidence_refs=(f"legacy:{surface}:failed",),
        )
        raise
    adapter.safe_observe(
        acceptance, outcome="succeeded", evidence_refs=(f"legacy:{surface}:succeeded",),
    )
    return result


async def track_async_surface(
    *,
    surface: str,
    operation: str,
    session_id: str,
    actor: str,
    callback: Callable[[], Awaitable[_T]],
    request_id: str | None = None,
) -> _T:
    adapter = SurfaceRuntimeAdapter()
    acceptance = await asyncio.to_thread(
        adapter.safe_accept,
        surface=surface,
        operation=operation,
        request_id=request_id or f"{surface}:{uuid.uuid4().hex}",
        session_id=session_id,
        actor=actor,
    )
    try:
        result = await callback()
    except BaseException:
        await asyncio.to_thread(
            adapter.safe_observe,
            acceptance,
            outcome="failed",
            evidence_refs=(f"legacy:{surface}:failed",),
        )
        raise
    await asyncio.to_thread(
        adapter.safe_observe,
        acceptance,
        outcome="succeeded",
        evidence_refs=(f"legacy:{surface}:succeeded",),
    )
    return result

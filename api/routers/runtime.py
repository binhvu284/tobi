"""Mission Control Runtime V2 read-only event replay API."""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from core.runtime import config
from core.runtime.contracts import RunEvent
from core.runtime.gateway import REPLAY_PAGE_LIMIT, TurnGateway
from core.runtime.repository import RunNotFoundError
from core.runtime.runs_view import RuntimeRunsView, RunsViewValidationError
from core.runtime.rollout import RolloutController, RolloutNotReadyError
from api.deps import _vault_guard


router = APIRouter(tags=["runtime"])
_POLL_SECONDS = 0.25
_HEARTBEAT_SECONDS = 15.0
_TERMINAL_EVENTS = {"shadow.turn_completed"}


class DeveloperLoopSelection(BaseModel):
    recipe_id: str
    version: str


@router.get("/api/runtime/runs")
def runtime_runs(
    limit: int = Query(50, ge=1, le=100),
    cursor: str | None = None,
    surface: str | None = None,
    status: str | None = None,
):
    try:
        return RuntimeRunsView().list_runs(
            limit=limit, cursor=cursor, surface=surface, status=status,
        )
    except RunsViewValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/api/runtime/runs/{run_id}/snapshot")
def runtime_run_snapshot(run_id: str, after: int = Query(0, ge=0)):
    try:
        return RuntimeRunsView().get_run(run_id, after_sequence=after)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="run not found") from exc
    except RunsViewValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/api/runtime/loops")
def runtime_loops():
    view = RuntimeRunsView()
    return {
        "items": view.list_loop_recipes(),
        "developer_selection": view.get_developer_loop_selection(),
    }


@router.put("/api/runtime/preferences/developer-loop")
def runtime_developer_loop_selection(body: DeveloperLoopSelection):
    try:
        return RuntimeRunsView().set_developer_loop_selection(body.recipe_id, body.version)
    except RunsViewValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/api/runtime/rollout")
def runtime_rollout_status():
    return RolloutController().status()


@router.post("/api/runtime/rollout/activate/{stage}")
def runtime_rollout_activate(
    stage: str,
    x_vault_session: str | None = Header(None, alias="X-Vault-Session"),
):
    _vault_guard(x_vault_session)
    try:
        return RolloutController().activate(stage)
    except RolloutNotReadyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/api/runtime/rollout/rollback")
def runtime_rollout_rollback(
    x_vault_session: str | None = Header(None, alias="X-Vault-Session"),
):
    _vault_guard(x_vault_session)
    return RolloutController().rollback()


@router.post("/api/runtime/rollout/resume")
def runtime_rollout_resume(
    x_vault_session: str | None = Header(None, alias="X-Vault-Session"),
):
    _vault_guard(x_vault_session)
    try:
        return RolloutController().resume()
    except RolloutNotReadyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def _start_sequence(request: Request, after: int) -> int:
    last_event_id = request.headers.get("last-event-id")
    if last_event_id is None:
        return after
    try:
        header_sequence = int(last_event_id)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="Last-Event-ID must be a non-negative integer") from exc
    if header_sequence < 0:
        raise HTTPException(status_code=422, detail="Last-Event-ID must be a non-negative integer")
    return max(after, header_sequence)


def _event_data(event: RunEvent) -> dict:
    return {
        "event_id": event.event_id,
        "run_id": event.run_id,
        "sequence": event.sequence,
        "event_type": event.event_type,
        "stage": event.stage,
        "timestamp": event.timestamp,
        "actor": event.actor,
        "payload": event.redacted_payload,
        "trace_id": event.trace_id,
        "parent_span_id": event.parent_span_id,
        "contract_version": event.contract_version,
    }


def _sse(event: RunEvent) -> str:
    return (
        f"id: {event.sequence}\n"
        f"event: {event.event_type}\n"
        f"data: {json.dumps(_event_data(event), ensure_ascii=True)}\n\n"
    )


@router.get("/api/runtime/runs/{run_id}/events")
async def runtime_run_events(
    run_id: str,
    request: Request,
    session_id: int = Query(..., gt=0),
    after: int = Query(0, ge=0),
) -> StreamingResponse:
    if not config.rollout_enabled(config.RUNTIME_V2_EVENTS):
        raise HTTPException(status_code=503, detail="Runtime V2 events are disabled")

    expected_session_id = str(session_id)
    sequence = _start_sequence(request, after)
    gateway = TurnGateway()
    try:
        initial = gateway.replay_events(
            run_id,
            expected_session_id=expected_session_id,
            after_sequence=sequence,
        )
    except RunNotFoundError as exc:
        raise HTTPException(status_code=404, detail="run not found") from exc

    async def stream():
        nonlocal sequence
        pending = initial
        next_heartbeat = asyncio.get_running_loop().time() + _HEARTBEAT_SECONDS
        while not await request.is_disconnected():
            if pending:
                for event in pending:
                    sequence = event.sequence
                    yield _sse(event)
                if len(pending) == REPLAY_PAGE_LIMIT:
                    pending = await asyncio.to_thread(
                        gateway.replay_events,
                        run_id,
                        expected_session_id=expected_session_id,
                        after_sequence=sequence,
                    )
                    continue

            latest = await asyncio.to_thread(
                gateway.latest_replay_event,
                run_id,
                expected_session_id=expected_session_id,
            )
            if latest is not None and latest.sequence <= sequence and latest.event_type in _TERMINAL_EVENTS:
                break

            now = asyncio.get_running_loop().time()
            if now >= next_heartbeat:
                yield f": heartbeat {sequence}\n\n"
                next_heartbeat = now + _HEARTBEAT_SECONDS
            await asyncio.sleep(_POLL_SECONDS)
            pending = await asyncio.to_thread(
                gateway.replay_events,
                run_id,
                expected_session_id=expected_session_id,
                after_sequence=sequence,
            )

    return StreamingResponse(stream(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    })

"""Mission Control API for controlled TOBI development workflows."""
from __future__ import annotations

import asyncio
import json
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from core import vault
from core.coding_agent import CodingAgent
from core.coding_policy import PolicyDenied


router = APIRouter(prefix="/api/developer", tags=["developer"])


class _LazyCodingAgent:
    """Avoid database writes while the dashboard module is being imported."""
    _instance: CodingAgent | None = None

    def _get(self) -> CodingAgent:
        if self._instance is None:
            self._instance = CodingAgent()
        return self._instance

    def __getattr__(self, name: str):
        return getattr(self._get(), name)


agent: Any = _LazyCodingAgent()


def require_owner(x_vault_session: str | None = Header(None, alias="X-Vault-Session")) -> str:
    try:
        vault.require_session(x_vault_session)
    except vault.VaultLocked as exc:
        raise HTTPException(status_code=401, detail="Unlock the Mission Control vault to use Developer.") from exc
    return str(x_vault_session)


Owner = Depends(require_owner)


class WorkflowCreate(BaseModel):
    queue_id: int = Field(gt=0)
    idempotency_key: str = Field(min_length=8, max_length=200)
    start: bool = True


class WorkflowCommand(BaseModel):
    command: Literal["pause", "resume", "cancel", "retry"]


class ReauthRequest(BaseModel):
    master: str = Field(min_length=6, max_length=1024)
    purpose: Literal["special_paths", "merge_deploy", "developer_cleanup"]
    workflow_id: int | None = None


class ApprovalRequest(BaseModel):
    purpose: Literal["special_paths", "merge_deploy"]
    challenge: str = Field(min_length=20, max_length=500)


class CleanupRequest(BaseModel):
    challenge: str = Field(min_length=20, max_length=500)


def _error(exc: Exception) -> HTTPException:
    if isinstance(exc, KeyError):
        return HTTPException(status_code=404, detail=str(exc).strip("'"))
    if isinstance(exc, (PolicyDenied, PermissionError)):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, RuntimeError):
        return HTTPException(status_code=409, detail=str(exc))
    return HTTPException(status_code=500, detail=f"Developer workflow failed safely: {type(exc).__name__}")


@router.get("/overview", dependencies=[Owner])
def overview() -> dict[str, Any]:
    workflows = agent.list_workflows(50)
    active = next((item for item in workflows if item["state"] not in {"completed", "canceled", "failed", "rolled_back"}), None)
    return {
        "active_workflow": active,
        "workflows": workflows,
        "summary": agent.store.overview(),
        "policy": {
            "version": agent.policy.version,
            "hash": agent.policy.hash,
            "capabilities": agent.policy.data.get("capabilities", {}),
            "github_configured": agent.github.configured(),
            "deployment_configured": agent.deployments.configured(),
        },
    }


@router.get("/queue", dependencies=[Owner])
def queue() -> dict[str, Any]:
    return {"items": agent.sync()}


@router.post("/queue/sync", dependencies=[Owner])
def queue_sync() -> dict[str, Any]:
    return {"items": agent.sync()}


@router.get("/versions", dependencies=[Owner])
def versions() -> dict[str, Any]:
    return {"releases": agent.releases.list()}


@router.get("/storage", dependencies=[Owner])
def storage() -> dict[str, Any]:
    return agent.storage()


@router.post("/storage/cleanup", dependencies=[Owner])
def storage_cleanup(body: CleanupRequest) -> dict[str, Any]:
    try:
        return agent.cleanup(body.challenge)
    except Exception as exc:
        raise _error(exc) from exc


@router.get("/workflows", dependencies=[Owner])
def workflows(limit: int = Query(50, ge=1, le=200)) -> dict[str, Any]:
    return {"workflows": agent.list_workflows(limit)}


@router.post("/workflows", dependencies=[Owner])
def create_workflow(body: WorkflowCreate) -> dict[str, Any]:
    try:
        storage_state = agent.storage()
        if storage_state["blocked_new_workflows"]:
            raise PolicyDenied("Developer storage is above the warning threshold; clean eligible retained work first.")
        workflow = agent.create_workflow(body.queue_id, idempotency_key=body.idempotency_key)
        return agent.start_background(int(workflow["id"])) if body.start else workflow
    except Exception as exc:
        raise _error(exc) from exc


@router.get("/workflows/{workflow_id}", dependencies=[Owner])
def get_workflow(workflow_id: int) -> dict[str, Any]:
    try:
        return agent.get_workflow(workflow_id)
    except Exception as exc:
        raise _error(exc) from exc


@router.get("/workflows/{workflow_id}/changes", dependencies=[Owner])
def changes(workflow_id: int) -> dict[str, Any]:
    try:
        return agent.changes(workflow_id)
    except Exception as exc:
        raise _error(exc) from exc


@router.get("/workflows/{workflow_id}/artifacts", dependencies=[Owner])
def artifacts(workflow_id: int) -> dict[str, Any]:
    try:
        agent.get_workflow(workflow_id)
        return {"artifacts": agent.store.list_artifacts(workflow_id)}
    except Exception as exc:
        raise _error(exc) from exc


@router.post("/workflows/{workflow_id}/commands", dependencies=[Owner])
def workflow_command(workflow_id: int, body: WorkflowCommand) -> dict[str, Any]:
    try:
        return agent.command(workflow_id, body.command)
    except Exception as exc:
        raise _error(exc) from exc


@router.post("/reauth", dependencies=[Owner])
def reauth(body: ReauthRequest) -> dict[str, Any]:
    conn = agent.store.connect()
    try:
        vault.verify_master(conn, body.master)
    except (vault.VaultError, vault.VaultLocked) as exc:
        raise HTTPException(status_code=401, detail="Owner re-authentication failed.") from exc
    finally:
        conn.close()
    token, row = agent.store.create_challenge(
        body.purpose, agent.policy.hash, session_id=body.workflow_id,
        ttl_seconds=agent.policy.limit("reauth_ttl_seconds", 300),
    )
    if body.workflow_id:
        agent.store.append_event(body.workflow_id, "reauth_challenge_created", {
            "purpose": body.purpose, "expires_at": row["expires_at"],
        }, actor="owner")
    return {"challenge": token, "purpose": body.purpose, "expires_at": row["expires_at"]}


@router.post("/workflows/{workflow_id}/approve", dependencies=[Owner])
def approve(workflow_id: int, body: ApprovalRequest) -> dict[str, Any]:
    try:
        return agent.approve(workflow_id, body.purpose, body.challenge)
    except Exception as exc:
        raise _error(exc) from exc


@router.get("/workflows/{workflow_id}/events", dependencies=[Owner])
async def workflow_events(
    workflow_id: int,
    request: Request,
    after: int = Query(0, ge=0),
) -> StreamingResponse:
    try:
        agent.get_workflow(workflow_id)
    except Exception as exc:
        raise _error(exc) from exc

    async def stream():
        sequence = after
        idle = 0
        while not await request.is_disconnected():
            events = agent.store.list_events(workflow_id, after=sequence)
            if events:
                idle = 0
                for event in events:
                    sequence = int(event["sequence"])
                    yield f"id: {sequence}\nevent: {event['event_type']}\ndata: {json.dumps(event, ensure_ascii=True)}\n\n"
            else:
                idle += 1
                if idle % 15 == 0:
                    yield f": heartbeat {sequence}\n\n"
            workflow = agent.store.get_session(workflow_id)
            if workflow and workflow["state"] in {"completed", "canceled", "failed", "rolled_back"} and not events:
                break
            await asyncio.sleep(1)

    return StreamingResponse(stream(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache", "X-Accel-Buffering": "no",
    })


@router.get("/events", dependencies=[Owner])
def events(workflow_id: int = Query(..., gt=0), after: int = Query(0, ge=0)) -> dict[str, Any]:
    try:
        agent.get_workflow(workflow_id)
        return {"events": agent.store.list_events(workflow_id, after=after)}
    except Exception as exc:
        raise _error(exc) from exc

"""Mission Control API for controlled TOBI development workflows."""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from core import vault
from core.coding_agent import CodingAgent
from core.coding_contracts import WorkerProfile
from core.coding_learning import CodingLearningService
from core.coding_loop import CodingLoopService
from core.coding_policy import PolicyDenied
from core.coding_workers import _platform_cli_command


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
_loop: CodingLoopService | None = None


def get_loop() -> CodingLoopService:
    global _loop
    if _loop is None:
        concrete = agent._get() if isinstance(agent, _LazyCodingAgent) else agent
        _loop = CodingLoopService(concrete)
    return _loop


def start_loop() -> bool:
    return get_loop().start()


def stop_loop() -> None:
    if _loop is not None:
        _loop.stop()


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
    command: Literal["pause", "resume", "cancel", "retry", "remove"]
    idempotency_key: str = Field(min_length=8, max_length=200)


class ProcessSettingsRequest(BaseModel):
    auto_queue: bool


class ApprovalRejectRequest(BaseModel):
    purpose: Literal["special_paths", "merge_deploy"]


class ReauthRequest(BaseModel):
    master: str = Field(min_length=6, max_length=1024)
    purpose: Literal["special_paths", "merge_deploy", "developer_cleanup"]
    workflow_id: int | None = None


class ApprovalRequest(BaseModel):
    purpose: Literal["special_paths", "merge_deploy"]
    challenge: str = Field(min_length=20, max_length=500)


class CleanupRequest(BaseModel):
    challenge: str = Field(min_length=20, max_length=500)


class GoalCreate(BaseModel):
    title: str = Field(min_length=3, max_length=240)
    objective: str = Field(min_length=10, max_length=20_000)
    acceptance_criteria: list[str] = Field(min_length=1, max_length=50)
    validation_commands: list[list[str]] = Field(default_factory=list, max_length=20)
    autonomy: Literal["sandbox", "pr", "merge_deploy"] = "sandbox"
    preferred_models: list[str] = Field(default_factory=list, max_length=10)
    max_iterations: int | None = Field(default=None, ge=1, le=100)
    worker_profile_slug: str = Field(default="mc-native", min_length=2, max_length=80)
    reviewer_profile_slug: str = Field(default="reviewer-default", min_length=2, max_length=80)


class GoalCommand(BaseModel):
    command: Literal["pause", "resume", "reattempt", "cancel", "delete", "approve_scope"]
    idempotency_key: str = Field(min_length=8, max_length=200)


class GoalAssessmentRequest(BaseModel):
    title: str = Field(min_length=3, max_length=240)
    objective: str = Field(min_length=10, max_length=20_000)
    acceptance_criteria: list[str] = Field(min_length=1, max_length=50)
    validation_commands: list[list[str]] = Field(default_factory=list, max_length=20)


class WorkerProfileRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    adapter: Literal["native", "codex", "opencode", "hermes", "model_review"]
    model: str = Field(default="", max_length=240)
    auth_mode: Literal["inherited", "native_login", "vault_env"] = "inherited"
    credential_env: str = Field(default="", max_length=120)
    reviewer_profile: str = Field(default="reviewer-default", max_length=80)
    enabled: bool = True
    config: dict[str, Any] = Field(default_factory=dict)


class WorkerSwitchRequest(BaseModel):
    profile_slug: str = Field(min_length=2, max_length=80)


class ReplayRequest(BaseModel):
    playbook_slug: str | None = Field(default=None, max_length=120)


def _idempotent_command(key: str, target_type: str, target_id: int, command: str, execute) -> dict[str, Any]:
    record = agent.store.begin_command(key, target_type, target_id, command)
    if not record["_claimed"]:
        if record["status"] == "completed" and record.get("response_json"):
            return json.loads(record["response_json"])
        if record["status"] == "failed" and record.get("response_json"):
            failure = json.loads(record["response_json"])
            raise RuntimeError(str(failure.get("message") or "The previous identical command failed."))
        raise RuntimeError("An identical command is already in progress.")
    try:
        result = execute()
    except Exception as exc:
        agent.store.fail_command(key, {
            "type": type(exc).__name__,
            "message": str(exc)[:1000],
        })
        raise
    else:
        agent.store.finish_command(key, result)
        return result


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
        "process": agent.process_settings(),
    }


@router.patch("/process/settings", dependencies=[Owner])
def process_settings(body: ProcessSettingsRequest) -> dict[str, Any]:
    try:
        return agent.set_auto_queue(body.auto_queue)
    except Exception as exc:
        raise _error(exc) from exc


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


@router.get("/goals", dependencies=[Owner])
def goals(limit: int = Query(100, ge=1, le=500)) -> dict[str, Any]:
    return {"goals": agent.store.list_goals(limit), "loop": {
        "enabled": get_loop().enabled(), "owner": get_loop().owner,
    }}


@router.post("/goals/assess", dependencies=[Owner])
def assess_goal(body: GoalAssessmentRequest) -> dict[str, Any]:
    try:
        return agent.assess_goal(
            title=body.title,
            objective=body.objective,
            acceptance_criteria=body.acceptance_criteria,
            validation_commands=body.validation_commands,
        )
    except Exception as exc:
        raise _error(exc) from exc


@router.post("/goals", dependencies=[Owner])
def create_goal(body: GoalCreate) -> dict[str, Any]:
    try:
        if agent.storage()["blocked_new_workflows"]:
            raise PolicyDenied("Developer storage is above the warning threshold.")
        goal = agent.create_goal(
            title=body.title,
            objective=body.objective,
            acceptance_criteria=body.acceptance_criteria,
            validation_commands=body.validation_commands,
            autonomy=body.autonomy,
            preferred_models=body.preferred_models,
            max_iterations=body.max_iterations,
            worker_profile_slug=body.worker_profile_slug,
            reviewer_profile_slug=body.reviewer_profile_slug,
        )
        if goal["status"] == "queued":
            try:
                start_loop()
            except Exception as exc:
                goal = agent.store.update_goal(
                    int(goal["id"]),
                    status="awaiting_config",
                    last_error=f"loop_start_failed:{type(exc).__name__}",
                )
        return goal
    except Exception as exc:
        raise _error(exc) from exc


@router.get("/goals/{goal_id}", dependencies=[Owner])
def get_goal(goal_id: int) -> dict[str, Any]:
    goal = agent.store.get_goal(goal_id)
    if not goal:
        raise HTTPException(status_code=404, detail="Development goal was not found.")
    workflow = agent.get_workflow(int(goal["current_session_id"])) if goal.get("current_session_id") else None
    return {"goal": goal, "workflow": workflow}


@router.post("/goals/{goal_id}/commands", dependencies=[Owner])
def goal_command(goal_id: int, body: GoalCommand) -> dict[str, Any]:
    try:
        def execute() -> dict[str, Any]:
            result = get_loop().command(goal_id, body.command)
            if body.command in {"resume", "reattempt", "approve_scope"}:
                start_loop()
            return result
        return _idempotent_command(
            body.idempotency_key, "goal", goal_id, body.command,
            execute,
        )
    except Exception as exc:
        raise _error(exc) from exc


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
        return _idempotent_command(
            body.idempotency_key, "workflow", workflow_id, body.command,
            lambda: agent.command(workflow_id, body.command),
        )
    except Exception as exc:
        raise _error(exc) from exc


@router.post("/workflows/{workflow_id}/switch-worker", dependencies=[Owner])
def switch_worker(workflow_id: int, body: WorkerSwitchRequest) -> dict[str, Any]:
    try:
        return agent.switch_worker(workflow_id, body.profile_slug)
    except Exception as exc:
        raise _error(exc) from exc


@router.get("/workflows/{workflow_id}/checkpoints", dependencies=[Owner])
def checkpoints(workflow_id: int, limit: int = Query(50, ge=1, le=200)) -> dict[str, Any]:
    try:
        agent.get_workflow(workflow_id)
        return {"checkpoints": agent.store.list_checkpoints(workflow_id, limit)}
    except Exception as exc:
        raise _error(exc) from exc


@router.get("/workers", dependencies=[Owner])
def workers(probe: bool = Query(False)) -> dict[str, Any]:
    try:
        from core import model_router

        config = model_router.load_llm_config()
        overrides = config.get("task_overrides") or {}
        default_model = str(config.get("default_model") or "")
        return {
            "workers": agent.worker_profiles(probe=probe),
            "models": model_router.available_models(),
            "providers": model_router.provider_catalog(),
            "routing": {
                "default_model": default_model,
                "coding": str(overrides.get("coding") or default_model),
                "coding_review": str(overrides.get("coding_review") or default_model),
            },
        }
    except Exception as exc:
        raise _error(exc) from exc


@router.put("/workers/{slug}", dependencies=[Owner])
def save_worker(slug: str, body: WorkerProfileRequest) -> dict[str, Any]:
    try:
        if body.enabled and body.auth_mode == "vault_env" and not body.credential_env:
            raise ValueError("Vault-backed workers require a credential environment name.")
        if body.enabled and body.adapter in {"native", "model_review"} and body.model:
            from core import model_router

            available = {str(item["id"]) for item in model_router.available_models()}
            if body.model not in available:
                raise ValueError(
                    "Selected model is not available from an enabled Models provider."
                )
        if body.enabled and body.adapter != "model_review":
            reviewer = agent.store.get_worker_profile(body.reviewer_profile)
            if not reviewer or reviewer["adapter"] != "model_review" or not reviewer["enabled"]:
                raise ValueError("Coding worker must reference an available reviewer profile.")
        profile = WorkerProfile(
            slug=slug,
            name=body.name,
            adapter=body.adapter,
            model=body.model,
            auth_mode=body.auth_mode,
            credential_env=body.credential_env,
            reviewer_profile=body.reviewer_profile,
            enabled=body.enabled,
            config=body.config,
        )
        return agent.store.upsert_worker_profile(profile.public_dict())
    except Exception as exc:
        raise _error(exc) from exc


@router.post("/workers/{slug}/probe", dependencies=[Owner])
def probe_worker(slug: str) -> dict[str, Any]:
    try:
        return agent.worker.probe(slug, active=True)
    except Exception as exc:
        raise _error(exc) from exc


@router.get("/workers/{slug}/login", dependencies=[Owner])
def worker_login(slug: str) -> dict[str, Any]:
    row = agent.store.get_worker_profile(slug)
    if not row:
        raise HTTPException(status_code=404, detail="Coding worker profile was not found.")
    adapter = str(row["adapter"])
    commands = {
        "codex": ["codex", "login"],
        "opencode": ["opencode", "auth", "login"],
        "hermes": ["hermes", "login"],
    }
    if adapter not in commands:
        return {"interactive_required": False, "detail": "This worker uses Models or Vault configuration."}
    return {
        "interactive_required": True,
        "command": commands[adapter],
        "provider": adapter,
        "detail": "Run this command in the coding runner account, complete the provider flow, then check authorization here.",
        "steps": [
            "Run the displayed command in the same account that runs the coding agent.",
            "Complete the browser, device-code, or provider prompt without sharing credentials with Mission Control.",
            "Return to Agents and check authorization. Mission Control stores status only, never the login secret.",
        ],
    }


_CLI_MODEL_CACHE: dict[str, tuple[float, list[dict[str, Any]], str, str]] = {}


@router.get("/workers/{slug}/models", dependencies=[Owner])
def worker_models(slug: str, refresh: bool = Query(False)) -> dict[str, Any]:
    row = agent.store.get_worker_profile(slug)
    if not row:
        raise HTTPException(status_code=404, detail="Coding agent profile was not found.")
    adapter = str(row["adapter"])
    if adapter in {"native", "model_review"}:
        from core import model_router

        return {
            "models": model_router.available_models(),
            "source": "models_page",
            "detail": "Available from enabled providers on the Models page.",
        }
    cached = _CLI_MODEL_CACHE.get(slug)
    if cached and not refresh and time.monotonic() - cached[0] < 300:
        return {"models": cached[1], "source": cached[2], "detail": cached[3]}
    if adapter == "codex":
        from core import model_router

        configured = [
            item for item in model_router.available_models()
            if str(item.get("provider") or "") == "codex"
        ]
        saved = str(row.get("model") or "")
        if saved and all(str(item.get("id")) != saved for item in configured):
            configured.insert(0, {
                "id": saved, "provider": "codex", "model": saved, "label": saved,
            })
        detail = (
            "Codex CLI does not expose a stable model-list command. Use its authorized default"
            " or a Codex model enabled on the Models page."
        )
        result = (time.monotonic(), configured, "codex", detail)
        _CLI_MODEL_CACHE[slug] = result
        return {"models": configured, "source": "codex", "detail": detail}
    if adapter != "opencode":
        return {"models": [], "source": adapter, "detail": "This developer tool manages its own model."}
    executable = shutil.which("opencode")
    if not executable:
        raise HTTPException(status_code=503, detail="OpenCode CLI is not installed for the coding runner account.")
    try:
        completed = subprocess.run(
            _platform_cli_command(["opencode", "models", "--pure"], cwd=Path(__file__).resolve().parents[1]),
            cwd=str(Path(__file__).resolve().parents[1]),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise HTTPException(status_code=503, detail="OpenCode model discovery did not complete.") from exc
    if completed.returncode != 0:
        raise HTTPException(status_code=503, detail="OpenCode could not list models for this runner account.")
    model_ids = list(dict.fromkeys(
        line.strip() for line in completed.stdout.splitlines()
        if line.strip() and "/" in line and not line.lstrip().startswith(("[", "{"))
    ))
    models = [{
        "id": model_id,
        "provider": model_id.split("/", 1)[0],
        "model": model_id.split("/", 1)[1],
        "label": model_id.split("/", 1)[1],
    } for model_id in model_ids[:500]]
    detail = f"{len(models)} models reported by the authorized OpenCode CLI."
    _CLI_MODEL_CACHE[slug] = (time.monotonic(), models, "opencode", detail)
    return {"models": models, "source": "opencode", "detail": detail}


@router.get("/learning", dependencies=[Owner])
def learning() -> dict[str, Any]:
    return agent.learning_state()


@router.post("/learning/replay", dependencies=[Owner])
def replay_learning(body: ReplayRequest) -> dict[str, Any]:
    try:
        return CodingLearningService(agent.store).replay(body.playbook_slug)
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


@router.post("/workflows/{workflow_id}/reject", dependencies=[Owner])
def reject_approval(workflow_id: int, body: ApprovalRejectRequest) -> dict[str, Any]:
    try:
        return agent.reject_approval(workflow_id, body.purpose)
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

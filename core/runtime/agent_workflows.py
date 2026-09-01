"""Canonical #35/T02 execution for qualified local Agent workflows."""
from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from core import agent_tier, owner_flags
from core.chat_runtime_contracts import TurnRequest
from core.database import get_connection
from core.release_manager import current_developer_version
from core.runtime.approval import ApprovalService
from core.runtime.contracts import (
    ActionReceipt,
    ApprovalMode,
    ApprovalRequest,
    ApprovalStatus,
    BudgetStatus,
    Capability,
    Certainty,
    ErrorCategory,
    ErrorStage,
    ExecutionPlan,
    IsolationLevel,
    LoopPolicy,
    LoopRecipe,
    LoopType,
    OwnerApprovalDecision,
    PlanStep,
    PolicyEffect,
    PolicyInput,
    RecoveryAction,
    RiskLevel,
    RunRequest,
    RuntimeErrorInfo,
    RuntimeToolCall,
    RuntimeToolResult,
    SideEffectClass,
    Surface,
    TrustClass,
)
from core.runtime.control import RuntimeControl
from core.runtime.event_store import append_run_event
from core.runtime.file_tools import (
    LIST_FILES_REF,
    READ_FILE_REF,
    build_file_tool_runtime,
)
from core.runtime.grounded_outcomes import GroundedOutcome, GroundedOutcomeComposer
from core.runtime.policy import POLICY_ID, POLICY_VERSION, PolicyEngine, PolicyLedger
from core.runtime.policy_facts import apply_legacy_policy_facts, resolve_chat_review_mode
from core.runtime.project_tools import (
    CREATE_TASK_REF,
    LIST_PROJECTS_REF,
    build_project_tool_runtime,
)
from core.runtime.repository import RuntimeRepository
from core.runtime.state import RunStatus
from core.runtime.terminal_tools import (
    RUN_COMMAND_ACTION_REF,
    RUN_COMMAND_REF,
    TERMINAL_STATUS_REF,
    build_terminal_tool_runtime,
)
from core.runtime.typed_resolution import (
    AcceptedTypedRequest,
    EntityRepository,
    TypedRequestResolver,
)
from core.runtime.workflows import WorkflowDefinition, supported_workflow_catalog


_QUALIFIED_WORKFLOWS = frozenset({
    "project.list",
    "task.create",
    "file.inventory",
    "file.read",
    "terminal.status",
    "terminal.typed_command",
    "coding.qualify",
})
_FAMILIES = {
    "project.list": "project_execution",
    "task.create": "project_execution",
    "file.inventory": "local_diagnosis",
    "file.read": "local_diagnosis",
    "terminal.status": "local_diagnosis",
    "terminal.typed_command": "local_diagnosis",
    "coding.qualify": "coding_maintenance",
}
_TOOL_ALIASES = {
    CREATE_TASK_REF: "create_task",
    RUN_COMMAND_ACTION_REF: "run_command",
}
_QUOTED = re.compile(r"[\"']([^\"']{1,240})[\"']")
_EXPLICIT_ID = {
    "project_id": re.compile(r"\bproject(?:_id)?\s*(?:#|=|:)?\s*(\d{1,12})\b", re.I),
    "task_id": re.compile(r"\btask(?:_id)?\s*(?:#|=|:)?\s*(\d{1,12})\b", re.I),
    "run_id": re.compile(r"\brun(?:_id)?\s*(?:#|=|:)?\s*([A-Za-z0-9-]{1,80})\b", re.I),
    "workflow_id": re.compile(r"\bworkflow(?:_id)?\s*(?:#|=|:)?\s*(\d{1,12})\b", re.I),
}
_SAFE_REF = re.compile(r"^[A-Za-z0-9._:/#@-]{1,240}$")
_FIELD_HASH = "workflow-fields"
_MAX_FILE_BYTES = 250_000
_DENIED_NAMES = {".git", ".env", "node_modules", "venv", "__pycache__"}
_DENIED_SUFFIXES = {".db", ".sqlite", ".sqlite3", ".pem", ".key"}


def local_agent_workflows_enabled() -> bool:
    if owner_flags.get_bool(owner_flags.RUNTIME_V2_ROLLBACK, False):
        return False
    return owner_flags.get_bool(owner_flags.AGENT_LOCAL_WORKFLOWS, True)


def set_local_agent_workflows(enabled: bool) -> bool:
    return owner_flags.set_bool(owner_flags.AGENT_LOCAL_WORKFLOWS, enabled)


def _clean_tail(message: str, intent: str) -> str:
    match = re.search(re.escape(intent), message, re.I)
    if not match:
        return ""
    return message[match.end():].strip(" \t\r\n:-`\"'")


def extract_agent_workflow_fields(message: str) -> dict[str, Any]:
    """Extract only explicitly labelled IDs and bounded literal values."""
    text = str(message or "").strip()
    fields: dict[str, Any] = {}
    for name, pattern in _EXPLICIT_ID.items():
        match = pattern.search(text)
        if match:
            fields[name] = int(match.group(1)) if name != "run_id" else match.group(1)

    lowered = text.casefold()
    if "create task" in lowered or "add task" in lowered:
        quoted = _QUOTED.search(text)
        if quoted:
            fields["title"] = quoted.group(1).strip()
        else:
            match = re.search(
                r"\b(?:create|add)\s+task\s+(.+?)\s+(?:in|for)\s+project\b",
                text,
                re.I,
            )
            if match:
                fields["title"] = match.group(1).strip(" `\"'")[:240]
    if "read file" in lowered:
        tail = _clean_tail(text, "read file")
        if tail:
            fields["path"] = tail
    elif "list files" in lowered or "show files" in lowered:
        intent = "list files" if "list files" in lowered else "show files"
        tail = _clean_tail(text, intent)
        if tail:
            fields["path"] = tail
    if "run approved command" in lowered:
        tail = _clean_tail(text, "run approved command")
        if tail:
            fields["command"] = tail
    return fields


@dataclass(frozen=True)
class AgentWorkflowQualification:
    status: str
    workflow: WorkflowDefinition | None = None
    fields: dict[str, Any] = field(default_factory=dict)
    missing_fields: tuple[str, ...] = ()
    reason: str = ""
    run_id: str | None = None

    @property
    def workflow_id(self) -> str | None:
        return self.workflow.workflow_id if self.workflow else None


def qualify_agent_workflow(request: TurnRequest) -> AgentWorkflowQualification:
    if not isinstance(request, TurnRequest) or request.mode != "agent":
        return AgentWorkflowQualification("unsupported", reason="agent mode required")
    if not local_agent_workflows_enabled():
        return AgentWorkflowQualification("rollback", reason="agent local workflows disabled")
    explicit = extract_agent_workflow_fields(request.message)
    explicit.update(dict(request.workflow_fields or {}))
    catalog = supported_workflow_catalog()
    normalized = re.sub(r"\s+", " ", request.message.casefold()).strip()
    forced_id = next((
        workflow_id
        for phrase, workflow_id in (
            ("run approved command", "terminal.typed_command"),
            ("coding workflow status", "coding.qualify"),
            ("worker qualification", "coding.qualify"),
            ("checkpoint status", "coding.qualify"),
            ("terminal capabilities", "terminal.status"),
            ("terminal status", "terminal.status"),
            ("create task", "task.create"),
            ("add task", "task.create"),
            ("list projects", "project.list"),
            ("show projects", "project.list"),
            ("list files", "file.inventory"),
            ("show files", "file.inventory"),
            ("read file", "file.read"),
        )
        if phrase in normalized
    ), None)
    if forced_id is not None:
        workflow = catalog.get(forced_id)
        missing = tuple(
            name for name in workflow.required_fields
            if explicit.get(name) is None
            or (isinstance(explicit.get(name), str) and not explicit[name].strip())
        )
        if missing:
            return AgentWorkflowQualification(
                "clarify",
                workflow=workflow,
                fields=explicit,
                missing_fields=missing,
                reason=f"missing_fields:{forced_id}:{','.join(missing)}",
            )
        return AgentWorkflowQualification(
            "accepted",
            workflow=workflow,
            fields=explicit,
            reason=f"matched:{forced_id}@v{workflow.version}",
        )
    selection = catalog.select(request.message, explicit)
    workflow = selection.workflow
    if workflow is None or workflow.workflow_id not in _QUALIFIED_WORKFLOWS:
        return AgentWorkflowQualification("unsupported", reason=selection.reason)
    if selection.status != "matched":
        return AgentWorkflowQualification(
            "clarify",
            workflow=workflow,
            fields=explicit,
            missing_fields=selection.missing_fields,
            reason=selection.reason,
        )
    return AgentWorkflowQualification(
        "accepted", workflow=workflow, fields=explicit, reason=selection.reason
    )


@dataclass(frozen=True)
class AgentWorkflowResult:
    status: str
    workflow_id: str | None = None
    family_id: str | None = None
    run_id: str | None = None
    reply: str = ""
    evidence_refs: tuple[str, ...] = ()
    missing_fields: tuple[str, ...] = ()
    pending_action: dict[str, Any] | None = None
    replayed: bool = False
    error_code: str | None = None


class _AgentWorkspaceBroker:
    def __init__(self, root: Path | str | None = None) -> None:
        self.root = Path(root or os.getenv("TOBI_AGENT_WORKSPACE") or Path(__file__).parents[2]).resolve()
        if not self.root.is_dir():
            raise ValueError("agent workspace is unavailable")

    def _resolve(self, value: str) -> tuple[Path, str]:
        raw = str(value or "").replace("\\", "/").strip().lstrip("/")
        if not raw or Path(raw).is_absolute():
            raise ValueError("a workspace-relative path is required")
        target = (self.root / raw).resolve()
        if not target.is_relative_to(self.root):
            raise ValueError("path escaped the approved workspace")
        relative = target.relative_to(self.root).as_posix()
        parts = {part.casefold() for part in Path(relative).parts}
        if parts & _DENIED_NAMES or target.suffix.casefold() in _DENIED_SUFFIXES:
            raise ValueError("path is excluded by local read policy")
        return target, relative

    def read_file(self, path: str) -> dict[str, Any]:
        target, relative = self._resolve(path)
        if not target.is_file():
            raise ValueError("file does not exist")
        data = target.read_bytes()
        if len(data) > _MAX_FILE_BYTES:
            raise ValueError("file exceeds the local read limit")
        return {
            "path": relative,
            "content": data.decode("utf-8", errors="replace"),
            "bytes": len(data),
        }

    def list_files(self, prefix: str = "", limit: int = 200) -> dict[str, Any]:
        base, _relative = self._resolve(prefix or ".")
        if not base.is_dir():
            raise ValueError("list path is not a directory")
        cap = max(1, min(int(limit), 500))
        files: list[str] = []
        for item in base.rglob("*"):
            if len(files) >= cap:
                break
            if not item.is_file():
                continue
            try:
                _target, relative = self._resolve(str(item.relative_to(self.root)))
            except ValueError:
                continue
            files.append(relative)
        files.sort()
        return {"files": files, "truncated": len(files) >= cap}

    def write_file(self, path: str, content: str) -> dict[str, Any]:
        raise ValueError("Agent local file writes belong to a later qualified workflow")


def _coding_status(workflow_id: Any) -> RuntimeToolResult | None:
    try:
        identity = int(workflow_id)
    except (TypeError, ValueError):
        return None
    try:
        from core.development_store import DevelopmentStore

        store = DevelopmentStore()
        session = store.get_session(identity)
        if session is None:
            return None
        scorecard = store.get_scorecard(identity)
        checkpoint = store.latest_checkpoint(identity)
    except Exception:
        return None
    output = {
        "status": str(session.get("state") or "unknown"),
        "qualified": bool(scorecard and scorecard.get("payload", {}).get("outcome") == "qualified"),
        "checkpoint": str((checkpoint or {}).get("id") or "none"),
    }
    refs = [f"workflow:{identity}"]
    if checkpoint:
        refs.append(f"check:coding-checkpoint:{checkpoint['id']}")
    elif scorecard:
        refs.append(f"check:coding-scorecard:{identity}")
    else:
        refs.append(f"check:coding-session:{identity}")
    return RuntimeToolResult(status="succeeded", typed_output=output, evidence_refs=tuple(refs))


def _field_fingerprint(fields: Mapping[str, Any]) -> str:
    raw = json.dumps(dict(fields), sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _run_id(request_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"tobi:agent-local:{request_id}"))


def _clarification(workflow: WorkflowDefinition, missing: tuple[str, ...]) -> str:
    outcome = GroundedOutcomeComposer().clarification(workflow, missing_fields=missing)
    return outcome.render_plain()


def _failure_reply(code: str) -> str:
    messages = {
        "arguments.rejected": "The supplied IDs, path, or command did not pass the typed safety checks.",
        "coding.workflow_not_found": "I could not find that Coding workflow. Send its numeric workflow ID.",
        "runtime.in_progress": "This workflow is already running. Open Runs to inspect its current state.",
        "runtime.recovery_required": "This workflow stopped safely and needs recovery from the same run.",
    }
    return messages.get(code, "TOBI could not complete this bounded workflow safely.")


class AgentWorkflowService:
    """Execute only the frozen T02 subset; all other Agent turns remain legacy-owned."""

    def __init__(
        self,
        repository: RuntimeRepository | None = None,
        *,
        workspace: Path | str | None = None,
        coding_check: Callable[[Any], RuntimeToolResult | None] | None = None,
    ) -> None:
        self.repository = repository or RuntimeRepository()
        self._workspace = Path(workspace or os.getenv("TOBI_AGENT_WORKSPACE") or Path(__file__).parents[2]).resolve()
        self._coding_check = coding_check or _coding_status

    def _runtime(self, workflow_id: str):
        if workflow_id in {"project.list", "task.create"}:
            return build_project_tool_runtime()
        if workflow_id in {"file.inventory", "file.read"}:
            return build_file_tool_runtime(
                broker=_AgentWorkspaceBroker(self._workspace),
                read_surfaces=(Surface.AGENT,),
            )
        if workflow_id in {"terminal.status", "terminal.typed_command"}:
            return build_terminal_tool_runtime(working_directory=self._workspace)
        return None

    @staticmethod
    def _tool_ref(workflow: WorkflowDefinition, fields: Mapping[str, Any]) -> str | None:
        if workflow.workflow_id == "terminal.typed_command":
            command = str(fields.get("command") or "")
            return RUN_COMMAND_ACTION_REF if re.fullmatch(r"mkdir [A-Za-z0-9][A-Za-z0-9._-]{0,63}", command) else RUN_COMMAND_REF
        return workflow.allowed_tools[0] if len(workflow.allowed_tools) == 1 else None

    @staticmethod
    def _tool_arguments(workflow_id: str, fields: Mapping[str, Any]) -> dict[str, Any]:
        if workflow_id == "file.inventory":
            return {"prefix": str(fields["path"]), "limit": 200}
        return dict(fields)

    @staticmethod
    def _target(tool_ref: str, arguments: Mapping[str, Any], workspace: Path) -> str:
        if tool_ref == LIST_PROJECTS_REF:
            return "projects:collection"
        if tool_ref == CREATE_TASK_REF:
            return f"project:{int(arguments['project_id'])}"
        if tool_ref == LIST_FILES_REF:
            return f"files:{str(arguments.get('prefix') or 'collection').replace(chr(92), '/')}"
        if tool_ref == READ_FILE_REF:
            return f"file:{str(arguments['path']).replace(chr(92), '/')}"
        if tool_ref == TERMINAL_STATUS_REF:
            return "terminal:status"
        command = str(arguments["command"])
        digest = hashlib.sha256(command.encode("utf-8")).hexdigest()
        if tool_ref == RUN_COMMAND_REF:
            return f"terminal:inspect:sha256:{digest}"
        directory = hashlib.sha256(str(workspace.resolve()).encode("utf-8")).hexdigest()
        return f"terminal:action:cwd-sha256:{directory}:command-sha256:{digest}"

    @staticmethod
    def _capabilities(workflow_id: str, action: bool) -> tuple[Capability, ...]:
        if workflow_id.startswith(("project.", "task.")):
            return (Capability.WRITE_PROJECTS,) if action else (Capability.READ_PROJECTS,)
        if workflow_id.startswith("file."):
            return (Capability.READ_FILES,)
        if workflow_id.startswith("terminal."):
            return (Capability.RUN_TERMINAL,)
        return (Capability.RUN_CODING,)

    def _request(self, request: TurnRequest, fields: Mapping[str, Any]) -> RunRequest:
        request_id = request.client_turn_id or str(uuid.uuid4())
        return RunRequest(
            request_id=request_id,
            surface=Surface.AGENT,
            owner_id="owner",
            session_id=str(request.session_id),
            mode="agent",
            message=request.message,
            attachments=({
                "kind": _FIELD_HASH,
                "keys": ",".join(sorted(fields)),
                "sha256": _field_fingerprint(fields),
            },),
            budget_profile="agent-local-t02",
        )

    def _create_run(
        self,
        request: TurnRequest,
        workflow: WorkflowDefinition,
        fields: Mapping[str, Any],
        accepted: AcceptedTypedRequest | None,
        *,
        tool_ref: str | None,
        arguments: Mapping[str, Any],
    ) -> tuple[dict[str, Any], bool]:
        canonical = self._request(request, fields)
        existing = self.repository.find_matching_run(canonical)
        if existing is not None:
            return existing, True
        run_id = _run_id(canonical.request_id)
        action = False
        risk = RiskLevel.NONE
        idempotency_key = None
        if tool_ref:
            runtime = self._runtime(workflow.workflow_id)
            spec = runtime.catalog.get_spec(tool_ref)
            action = spec.side_effect_class is not SideEffectClass.NONE
            risk = spec.risk
            idempotency_key = accepted.idempotency_key if accepted else None
        recipe = LoopRecipe(
            recipe_id=f"agent.local.{workflow.workflow_id}",
            version="1",
            name=f"Agent local {workflow.workflow_id}",
            loop_type=LoopType.TURN,
            trigger="qualified Agent workflow",
            objective=f"Complete {workflow.workflow_id} through canonical Runtime",
            stop_condition=workflow.stop_condition,
            max_attempts=2,
            max_runtime_s=900,
            max_cost_usd=0.0,
            max_model_calls=1,
            max_tool_calls=2,
            allowed_tools=(tool_ref,) if tool_ref else (),
            approval_gates=("owner",) if action else (),
            recovery_policy="same_run_retry_once",
            evidence_required=workflow.success_evidence,
        )
        self.repository.save_loop_recipe(recipe)
        run = self.repository.create_run(
            canonical,
            loop_policy=LoopPolicy.from_recipe(
                policy_id=f"agent.local.{workflow.workflow_id}.active",
                version="1",
                recipe=recipe,
                policy_decision_id=f"agent-local:{canonical.request_id}",
                enabled=True,
            ),
            run_id=run_id,
            actor="agent-workflow-gateway",
        )
        run = self.repository.transition_run(
            run_id, RunStatus.ROUTING, expected_version=run["version"], actor="agent-workflow-gateway"
        )
        run = self.repository.save_plan(
            ExecutionPlan(
                plan_id=f"{run_id}:agent-local",
                run_id=run_id,
                version="1",
                objective=f"Complete {workflow.workflow_id} with declared evidence",
                steps=(PlanStep(
                    step_id="execute",
                    kind="tool" if tool_ref else "check",
                    risk=risk,
                    tool_name=tool_ref,
                    arguments=dict(arguments),
                    retry_policy="transient_once" if not action else "none",
                    idempotency_key=idempotency_key,
                    required_capabilities=self._capabilities(workflow.workflow_id, action),
                    output_contract={"evidence_required": list(workflow.success_evidence)},
                ),),
                approval_points=("owner",) if action else (),
                completion_predicate=workflow.stop_condition,
            ),
            expected_version=run["version"],
            actor="agent-workflow-planner",
        )
        if accepted is not None:
            append_run_event(
                run_id=run_id,
                event_type="agent.typed_request_accepted",
                stage="route",
                actor="typed-request-resolver",
                payload={**accepted.to_trace_payload(), "contract_hash": accepted.contract_hash},
                event_id=f"{run_id}:typed-request",
            )
        return run, False

    @staticmethod
    def _policy_input(
        *,
        run: Mapping[str, Any],
        tool,
        target: str,
        decision_id: str,
        review_mode: str,
        approval_status: ApprovalStatus = ApprovalStatus.NONE,
        approval_id: str | None = None,
    ) -> PolicyInput:
        facts = resolve_chat_review_mode(review_mode)
        value = PolicyInput(
            decision_id=decision_id,
            run_id=str(run["run_id"]),
            step_id="execute",
            owner_id=str(run["owner_id"]),
            session_id=str(run["session_id"]),
            surface=Surface.AGENT,
            mode="agent",
            tool=tool,
            target=target,
            granted_permissions=tool.required_permissions,
            trust_class=TrustClass.OWNER_DIRECT,
            certainty=Certainty.KNOWN,
            instruction_authority=True,
            available_isolations=(
                IsolationLevel.IN_PROCESS,
                IsolationLevel.SUBPROCESS,
                IsolationLevel.WORKSPACE,
            ),
            budget_status=BudgetStatus.AVAILABLE,
            approval_mode=ApprovalMode.ASK,
            approval_status=approval_status,
            approval_id=approval_id,
        )
        return apply_legacy_policy_facts(value, facts)

    @staticmethod
    def _receipt(receipt_id: str | None) -> ActionReceipt | None:
        if not receipt_id:
            return None
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT * FROM mc_action_receipts WHERE receipt_id=?", (receipt_id,)
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            return None
        return ActionReceipt(
            receipt_id=str(row["receipt_id"]),
            run_id=str(row["run_id"]),
            step_id=str(row["step_id"]),
            tool_ref=str(row["tool_ref"]),
            target=str(row["target"]),
            effect_summary=str(row["effect_summary"]),
            timestamp=str(row["timestamp"]),
            before_ref=row["before_ref"],
            after_ref=row["after_ref"],
            external_ref=row["external_ref"],
            approval_ref=row["approval_ref"],
        )

    @staticmethod
    def _render(
        workflow: WorkflowDefinition,
        result: RuntimeToolResult,
        outcome: GroundedOutcome,
        receipt: ActionReceipt | None,
    ) -> str:
        output = result.typed_output if isinstance(result.typed_output, Mapping) else {}
        lines = [outcome.title, outcome.summary]
        if workflow.workflow_id == "project.list":
            lines.extend(
                f"- #{item['id']} {item['name']} ({item['status']})"
                for item in list(output.get("projects") or [])[:20]
            )
        elif workflow.workflow_id == "file.inventory":
            lines.extend(f"- {path}" for path in list(output.get("files") or [])[:50])
        elif workflow.workflow_id == "file.read":
            lines.extend((f"Path: {output.get('path')}", "", str(output.get("content") or "")))
        elif workflow.workflow_id in {"terminal.status", "terminal.typed_command"}:
            for key in ("enabled", "mode", "os", "shell", "state", "ok", "exit_code", "output"):
                if key in output:
                    lines.append(f"- {key.replace('_', ' ').title()}: {output[key]}")
        elif workflow.workflow_id == "coding.qualify":
            for key in ("status", "qualified", "checkpoint"):
                if key in output:
                    lines.append(f"- {key.title()}: {output[key]}")
        if receipt is not None:
            lines.append(f"Receipt: {receipt.receipt_id}")
        lines.append(f"Evidence: {', '.join(outcome.evidence_refs[:5])}")
        return "\n".join(lines).strip()

    @staticmethod
    def _declared_refs(
        workflow: WorkflowDefinition,
        result: RuntimeToolResult,
        run_id: str,
        policy_id: str | None,
        fields: Mapping[str, Any],
    ) -> tuple[str, ...] | None:
        refs: list[str] = [f"run:{run_id}"]
        for required in workflow.success_evidence:
            if required in {"tool_result_ref", "result_ref", "evidence_ref"}:
                if not result.evidence_refs:
                    return None
                refs.append(f"check:{run_id}:typed-result")
            elif required in {"path_policy_ref", "policy_decision_ref"}:
                if not policy_id:
                    return None
                refs.append(f"policy:{policy_id}")
            elif required == "receipt_ref":
                if not result.receipt_id:
                    return None
                refs.append(f"receipt:{result.receipt_id}")
            elif required == "project_ref":
                if not fields.get("project_id"):
                    return None
                refs.append(f"project:{fields['project_id']}")
            elif required == "workflow_ref":
                refs.append(f"workflow:{fields.get('workflow_id')}" if fields.get("workflow_id") else f"workflow:{workflow.workflow_id}")
            else:
                return None
        refs.extend(result.evidence_refs)
        return tuple(dict.fromkeys(refs))[:20]

    @staticmethod
    def _record_tier_evidence(
        workflow: WorkflowDefinition,
        family: str,
        run_id: str,
        result: RuntimeToolResult,
    ) -> None:
        conn = get_connection()
        try:
            release = current_developer_version(conn)
            entries = [("runtime_run", f"run:{run_id}")]
            if workflow.allowed_tools:
                entries.append(("typed_tool_result", f"check:{run_id}:typed-result"))
            if result.receipt_id:
                entries.append(("local_action_receipt", f"receipt:{result.receipt_id}"))
            if workflow.workflow_id == "coding.qualify":
                entries.append(("coding_check", f"check:{run_id}:coding-status"))
            for evidence_type, evidence_ref in entries:
                agent_tier.record_evidence(
                    conn,
                    ability_id="local_work_execution",
                    family_id=family,
                    evidence_type=evidence_type,
                    evidence_ref=evidence_ref,
                    source_release=release,
                )
        finally:
            conn.close()

    def _finish_success(
        self,
        run: Mapping[str, Any],
        workflow: WorkflowDefinition,
        fields: Mapping[str, Any],
        result: RuntimeToolResult,
        *,
        policy_id: str | None,
    ) -> AgentWorkflowResult:
        run_id = str(run["run_id"])
        declared = self._declared_refs(workflow, result, run_id, policy_id, fields)
        receipt = self._receipt(result.receipt_id)
        if declared is None:
            return AgentWorkflowResult(
                "failed",
                workflow.workflow_id,
                _FAMILIES[workflow.workflow_id],
                run_id,
                _failure_reply("evidence.missing"),
                error_code="evidence.missing",
            )
        grounded_result = replace(result, evidence_refs=tuple(dict.fromkeys((*result.evidence_refs, *declared))))
        outcome = GroundedOutcomeComposer().success(workflow, grounded_result, receipt=receipt)
        append_run_event(
            run_id=run_id,
            event_type="agent.outcome_grounded",
            stage="evaluate",
            actor="grounded-outcome-composer",
            payload=outcome.to_trace_payload(),
            event_id=f"{run_id}:grounded-outcome",
        )
        current = self.repository.get_run(run_id) or run
        if current["status"] == RunStatus.RUNNING.value:
            current = self.repository.transition_run(
                run_id,
                RunStatus.SUCCEEDED,
                expected_version=int(current["version"]),
                actor="agent-workflow-gateway",
            )
        self._record_tier_evidence(
            workflow, _FAMILIES[workflow.workflow_id], run_id, result
        )
        return AgentWorkflowResult(
            "succeeded",
            workflow.workflow_id,
            _FAMILIES[workflow.workflow_id],
            run_id,
            self._render(workflow, result, outcome, receipt),
            evidence_refs=outcome.evidence_refs,
        )

    def _execute_call(
        self,
        run: Mapping[str, Any],
        workflow: WorkflowDefinition,
        fields: Mapping[str, Any],
        accepted: AcceptedTypedRequest,
        runtime,
        *,
        review_mode: str,
        approval_id: str | None = None,
    ) -> AgentWorkflowResult:
        run_id = str(run["run_id"])
        current = self.repository.get_run(run_id) or run
        call = accepted.to_runtime_call(runtime.catalog)
        policy_id = f"{run_id}:policy:execute"
        facts = self._policy_input(
            run=current,
            tool=runtime.catalog.get_spec(call.tool_ref),
            target=self._target(call.tool_ref, call.validated_arguments, self._workspace),
            decision_id=policy_id,
            review_mode=review_mode,
        )
        if approval_id:
            facts = ApprovalService().apply_to_policy(facts, approval_id)
            call = replace(call, approval_id=approval_id)
        if current["status"] == RunStatus.WAITING_APPROVAL.value:
            current = self.repository.transition_run(
                run_id,
                RunStatus.RUNNING,
                expected_version=int(current["version"]),
                actor="agent-workflow-approval",
            )
        elif current["status"] == RunStatus.PLANNED.value:
            current = self.repository.transition_run(
                run_id,
                RunStatus.RUNNING,
                expected_version=int(current["version"]),
                actor="agent-workflow-gateway",
            )
        lease = self.repository.claim_step(run_id, worker_id=f"agent-local:{uuid.uuid4().hex}")
        if lease is None:
            return AgentWorkflowResult(
                "failed", workflow.workflow_id, _FAMILIES[workflow.workflow_id], run_id,
                _failure_reply("runtime.in_progress"), error_code="runtime.in_progress",
            )
        if call.tool_ref in {RUN_COMMAND_REF, RUN_COMMAND_ACTION_REF}:
            result = runtime.execute(
                call,
                facts,
                worker_id=lease["worker_id"],
                lease_token=lease["lease_token"],
                lease_epoch=lease["lease_epoch"],
            )
        else:
            result = runtime.executor.execute(
                call,
                facts,
                worker_id=lease["worker_id"],
                lease_token=lease["lease_token"],
                lease_epoch=lease["lease_epoch"],
            )
        if result.status != "succeeded":
            return AgentWorkflowResult(
                "failed",
                workflow.workflow_id,
                _FAMILIES[workflow.workflow_id],
                run_id,
                result.error.owner_message if result.error else _failure_reply("runtime.recovery_required"),
                error_code=result.error.code if result.error else "runtime.recovery_required",
            )
        return self._finish_success(
            current, workflow, fields, result, policy_id=policy_id
        )

    def _request_approval(
        self,
        run: Mapping[str, Any],
        workflow: WorkflowDefinition,
        fields: Mapping[str, Any],
        accepted: AcceptedTypedRequest,
        runtime,
    ) -> AgentWorkflowResult:
        from core import conductor_registry

        run_id = str(run["run_id"])
        call = accepted.to_runtime_call(runtime.catalog)
        policy_id = f"{run_id}:policy:approval"
        approval_id = f"approval-{hashlib.sha256(run_id.encode()).hexdigest()[:32]}"
        facts = self._policy_input(
            run=run,
            tool=runtime.catalog.get_spec(call.tool_ref),
            target=self._target(call.tool_ref, call.validated_arguments, self._workspace),
            decision_id=policy_id,
            review_mode="ask",
        )
        decision = PolicyEngine(policy_id=POLICY_ID, version=POLICY_VERSION).evaluate(facts)
        PolicyLedger().record(facts, decision, actor="agent-workflow-policy")
        if decision.effect is not PolicyEffect.REQUIRE_APPROVAL:
            return self._execute_call(
                run, workflow, fields, accepted, runtime, review_mode="always"
            )
        expires = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        ApprovalService().request(
            ApprovalRequest(
                approval_id=approval_id,
                run_id=run_id,
                step_id="execute",
                policy_decision_id=policy_id,
                owner_id=str(run["owner_id"]),
                session_id=str(run["session_id"]),
                tool_ref=call.tool_ref,
                expires_at=expires,
            ),
            actor="agent-workflow-policy",
        )
        pending = conductor_registry.propose_runtime_action(
            _TOOL_ALIASES[call.tool_ref],
            dict(call.validated_arguments),
            chat_id=int(run["session_id"]),
            runtime_run_id=run_id,
            approval_id=approval_id,
        )
        outcome = GroundedOutcomeComposer().refusal(workflow, decision)
        return AgentWorkflowResult(
            "waiting_approval",
            workflow.workflow_id,
            _FAMILIES[workflow.workflow_id],
            run_id,
            outcome.render_plain(),
            evidence_refs=outcome.evidence_refs,
            pending_action=pending,
        )

    def _typed_request(
        self,
        request: TurnRequest,
        workflow: WorkflowDefinition,
        fields: Mapping[str, Any],
        runtime,
        run_id: str,
        tool_ref: str,
    ) -> AcceptedTypedRequest | None:
        arguments = self._tool_arguments(workflow.workflow_id, fields)
        if workflow.workflow_id == "file.inventory":
            try:
                validated = runtime.catalog.validate_arguments(tool_ref, arguments)
                call = runtime.catalog.prepare_call(
                    call_id=f"{run_id}:call",
                    run_id=run_id,
                    step_id="execute",
                    tool_ref=tool_ref,
                    arguments=validated,
                    surface=Surface.AGENT,
                    mode="agent",
                    candidate_tool_refs=(tool_ref,),
                )
            except Exception:
                return None
            digest = hashlib.sha256(json.dumps({
                "workflow_id": workflow.workflow_id,
                "workflow_version": workflow.version,
                "tool_ref": tool_ref,
                "arguments": validated,
            }, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            return AcceptedTypedRequest(
                workflow_id=workflow.workflow_id,
                workflow_version=workflow.version,
                run_id=run_id,
                step_id="execute",
                call_id=call.call_id,
                tool_ref=tool_ref,
                surface=Surface.AGENT,
                mode="agent",
                arguments_json=json.dumps(validated, sort_keys=True, separators=(",", ":")),
                contract_hash=digest,
                idempotency_key=None,
            )
        resolution = TypedRequestResolver(
            workflows=supported_workflow_catalog(),
            tools=runtime.catalog,
            entities=EntityRepository(),
        ).resolve(
            message=workflow.intents[0],
            run_id=run_id,
            step_id="execute",
            call_id=f"{run_id}:call",
            proposed_arguments=arguments,
            proposed_tool_ref=tool_ref,
            proposed_workflow_id=workflow.workflow_id,
            surface=Surface.AGENT,
            mode="agent",
        )
        return resolution.accepted if resolution.status == "accepted" else None

    def execute(
        self,
        request: TurnRequest,
        *,
        review_mode: str = "ask",
    ) -> AgentWorkflowResult:
        qualification = qualify_agent_workflow(request)
        if qualification.status in {"unsupported", "rollback"}:
            return AgentWorkflowResult(qualification.status, error_code=qualification.reason)
        workflow = qualification.workflow
        assert workflow is not None
        family = _FAMILIES[workflow.workflow_id]
        if qualification.status == "clarify":
            return AgentWorkflowResult(
                "clarify",
                workflow.workflow_id,
                family,
                reply=_clarification(workflow, qualification.missing_fields),
                missing_fields=qualification.missing_fields,
            )

        fields = qualification.fields
        canonical = self._request(request, fields)
        run_id = _run_id(canonical.request_id)
        if workflow.workflow_id == "coding.qualify":
            result = self._coding_check(fields.get("workflow_id"))
            if result is None:
                return AgentWorkflowResult(
                    "clarify", workflow.workflow_id, family,
                    reply=_failure_reply("coding.workflow_not_found"),
                    missing_fields=("workflow_id",),
                    error_code="coding.workflow_not_found",
                )
            run, replay = self._create_run(
                request, workflow, fields, None, tool_ref=None, arguments=fields
            )
            if replay:
                return self._replay_result(run, workflow)
            run = self.repository.transition_run(
                run_id, RunStatus.RUNNING, expected_version=run["version"], actor="agent-workflow-gateway"
            )
            lease = self.repository.claim_step(run_id, worker_id=f"agent-local:{uuid.uuid4().hex}")
            if lease is None:
                return AgentWorkflowResult("failed", workflow.workflow_id, family, run_id, _failure_reply("runtime.in_progress"))
            RuntimeControl().record_step_success(
                run_id,
                "execute",
                worker_id=lease["worker_id"],
                lease_token=lease["lease_token"],
                lease_epoch=lease["lease_epoch"],
                result=result,
            )
            return self._finish_success(run, workflow, fields, result, policy_id=None)

        runtime = self._runtime(workflow.workflow_id)
        tool_ref = self._tool_ref(workflow, fields)
        if runtime is None or tool_ref is None:
            return AgentWorkflowResult("unsupported", workflow.workflow_id, family)
        accepted = self._typed_request(request, workflow, fields, runtime, run_id, tool_ref)
        if accepted is None:
            return AgentWorkflowResult(
                "failed", workflow.workflow_id, family,
                reply=_failure_reply("arguments.rejected"),
                error_code="arguments.rejected",
            )
        run, replay = self._create_run(
            request,
            workflow,
            fields,
            accepted,
            tool_ref=tool_ref,
            arguments=accepted.arguments,
        )
        if replay:
            return self._replay_result(run, workflow)
        spec = runtime.catalog.get_spec(tool_ref)
        if spec.side_effect_class is not SideEffectClass.NONE and review_mode == "ask":
            return self._request_approval(run, workflow, fields, accepted, runtime)
        return self._execute_call(
            run, workflow, fields, accepted, runtime, review_mode=review_mode
        )

    def _replay_result(
        self, run: Mapping[str, Any], workflow: WorkflowDefinition
    ) -> AgentWorkflowResult:
        status = str(run["status"])
        run_id = str(run["run_id"])
        if status == RunStatus.SUCCEEDED.value:
            return AgentWorkflowResult(
                "succeeded", workflow.workflow_id, _FAMILIES[workflow.workflow_id],
                run_id, replayed=True,
            )
        if status == RunStatus.WAITING_APPROVAL.value:
            from core import conductor_registry

            pending = conductor_registry.runtime_action_for_run(run_id)
            return AgentWorkflowResult(
                "waiting_approval", workflow.workflow_id, _FAMILIES[workflow.workflow_id],
                run_id, pending_action=pending, replayed=True,
            )
        return AgentWorkflowResult(
            "failed", workflow.workflow_id, _FAMILIES[workflow.workflow_id], run_id,
            _failure_reply("runtime.recovery_required"), replayed=True,
            error_code="runtime.recovery_required",
        )

    def resolve_pending_action(self, action_id: int, decision: str) -> dict[str, Any]:
        from core import conductor_registry

        return conductor_registry.confirm_action(action_id, decision, surface="mc")

    def resolve_linked_action(
        self,
        action: Mapping[str, Any],
        decision: str,
        metadata: Mapping[str, Any],
    ) -> dict[str, Any]:
        run_id = str(metadata["run_id"])
        approval_id = str(metadata["approval_id"])
        run = self.repository.get_run(run_id)
        if run is None:
            return {"ok": False, "status": "failed", "error": "canonical run not found"}
        now = datetime.now(timezone.utc).isoformat()
        status = ApprovalStatus.REJECTED if str(decision).lower() in {"reject", "no", "cancel", "deny"} else ApprovalStatus.APPROVED
        ApprovalService().decide(
            OwnerApprovalDecision(
                approval_id=approval_id,
                owner_id=str(run["owner_id"]),
                session_id=str(run["session_id"]),
                status=status,
                authentication_method="mission-control-owner",
                authentication_evidence_hash=hashlib.sha256(f"{approval_id}:{action['id']}:owner".encode()).hexdigest(),
                authenticated_at=now,
            ),
            actor="mission-control-owner",
            timestamp=now,
        )
        if status is ApprovalStatus.REJECTED:
            return {
                "ok": True,
                "status": "rejected",
                "summary": str(action.get("summary") or "Action rejected"),
                "runtime_run_id": run_id,
                "runtime_v2": {"run_id": run_id, "approval_id": approval_id},
            }
        steps = self.repository.list_steps(run_id)
        if not steps:
            return {"ok": False, "status": "failed", "error": "canonical step not found"}
        step = steps[0]
        workflow_id = str(run["loop"]["recipe_id"]).removeprefix("agent.local.")
        workflow = supported_workflow_catalog().get(workflow_id)
        fields = extract_agent_workflow_fields(str(run["objective"]))
        arguments = dict(step["arguments"])
        if workflow_id == "file.inventory":
            fields["path"] = arguments.get("prefix")
        else:
            fields.update(arguments)
        runtime = self._runtime(workflow_id)
        tool_ref = str(step["tool_name"])
        call = runtime.catalog.prepare_call(
            call_id=f"{run_id}:call",
            run_id=run_id,
            step_id="execute",
            tool_ref=tool_ref,
            arguments=arguments,
            surface=Surface.AGENT,
            mode="agent",
            candidate_tool_refs=(tool_ref,),
            idempotency_key=step.get("idempotency_key"),
        )
        accepted = AcceptedTypedRequest(
            workflow_id=workflow_id,
            workflow_version=workflow.version,
            run_id=run_id,
            step_id="execute",
            call_id=call.call_id,
            tool_ref=tool_ref,
            surface=Surface.AGENT,
            mode="agent",
            arguments_json=json.dumps(arguments, sort_keys=True, separators=(",", ":")),
            contract_hash=hashlib.sha256(json.dumps({
                "workflow_id": workflow_id,
                "workflow_version": workflow.version,
                "tool_ref": tool_ref,
                "arguments": arguments,
            }, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
            idempotency_key=step.get("idempotency_key"),
        )
        result = self._execute_call(
            run, workflow, fields, accepted, runtime,
            review_mode="ask", approval_id=approval_id,
        )
        return {
            "ok": result.status == "succeeded",
            "status": "executed" if result.status == "succeeded" else "failed",
            "summary": str(action.get("summary") or result.reply),
            "result": result.reply,
            "runtime_run_id": run_id,
            "receipt_id": next((ref.split(":", 1)[1] for ref in result.evidence_refs if ref.startswith("receipt:")), None),
            "runtime_v2": {"run_id": run_id, "approval_id": approval_id},
        }

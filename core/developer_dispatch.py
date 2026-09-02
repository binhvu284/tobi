"""Durable Chat proposal -> owner confirmation -> existing Developer workflow.

This module owns only the hand-off. Queue authoring, preflight, coding execution,
approval gates, checkpoints, and evidence remain owned by ``CodingAgent``.
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from core.coding_states import STATE_KIND
from core.database import get_connection
from core.development_store import utc_now


_CONFIRM_LOCK = threading.RLock()
_GATEWAY_LOCK = threading.Lock()
_RUNTIME_LOCK = threading.RLock()
_MARKER_PREFIX = "tobi-chat-developer-dispatch:"


@dataclass(frozen=True)
class DeveloperRequestQualification:
    status: str
    objective: str = ""
    question: str = ""
    reason: str = ""


_SLASH_EXPLICIT = re.compile(r"^/developer(?=$|[\s:])", re.IGNORECASE)
_USE_EXPLICIT = re.compile(
    r"^(?:(?:can|could|would)\s+you\s+|please\s+)?(?:use|ask)\s+"
    r"(?:the\s+)?developer(?:\s+agent)?\b(?P<tail>.*)$",
    re.IGNORECASE,
)
_SEND_EXPLICIT = re.compile(
    r"^(?:(?:can|could|would)\s+you\s+|please\s+)?send\s+"
    r"(?:(?:this|it)\s+to\s+)?(?:the\s+)?developer(?:\s+agent)?\b"
    r"(?P<tail>.*)$",
    re.IGNORECASE,
)
_HAND_EXPLICIT = re.compile(
    r"^(?:(?:can|could|would)\s+you\s+|please\s+)?hand\s+(?:this|it)\s+to\s+"
    r"(?:the\s+)?developer(?:\s+agent)?\b(?P<tail>.*)$",
    re.IGNORECASE,
)
_WITH_EXPLICIT = re.compile(
    r"^(?:(?:can|could|would)\s+you\s+|please\s+)?"
    r"(?P<objective>(?:fix|repair|build|implement)\b.+?)\s+with\s+"
    r"(?:the\s+)?developer(?:\s+agent)?\s*[.!?]*$",
    re.IGNORECASE,
)
_CAPABILITY = re.compile(
    r"^(?:please\s+)?(?:add|build|implement|enable)\b.*"
    r"\b(?:capability|feature|workflow|support|integration|behavior)\b",
    re.IGNORECASE,
)
_DIRECT_FILE = re.compile(
    r"\b(?:create|write|save|make)\b.*\b(?:this|a|the)\b.*"
    r"\b(?:markdown|md|file|document)\b",
    re.IGNORECASE,
)
_MARKDOWN_CREATION = re.compile(r"\b(?:make|create)\b.*\bmarkdown\s+creation\b", re.IGNORECASE)
_NEGATED_REQUEST = re.compile(
    r"^(?:please\s+)?(?:(?:do\s+not|don't|dont|never|no\s+need\s+to)\b|"
    r"(?:i(?:'d|\s+would)?|we(?:'d|\s+would)?)\s+rather\s+not\b)",
    re.IGNORECASE,
)
_NEGATED_DEVELOPER = re.compile(
    r"\b(?:do\s+not|don't|dont|never|no\s+need\s+to|rather\s+not|without|instead\s+of)\b"
    r"[^.!?]{0,80}\bdeveloper\b",
    re.IGNORECASE,
)
_QUESTION_OPEN = re.compile(
    r"^(?:what|why|how|should|can|could|would|do|does|did|is|are|was|were)\b",
    re.IGNORECASE,
)
_CLAUSE_COMMAND_START = (
    r"(?:(?:(?:can|could|would)\s+you\s+|please\s+)?(?:use|ask|send|hand)\b|"
    r"/developer\b|(?:(?:can|could|would)\s+you\s+|please\s+)?"
    r"(?:fix|repair|build|implement)\b[^.!?\r\n]*\s+with\s+"
    r"(?:the\s+)?developer(?:\s+agent)?\b)"
)
_REQUEST_SEGMENT_BOUNDARY = re.compile(
    rf"(?:\r?\n+|(?<=[.!?])[ \t]+|;[ \t]*|"
    rf"(?:,[ \t]+|[ \t]+[-\u2013\u2014][ \t]+)(?={_CLAUSE_COMMAND_START}))",
    re.IGNORECASE,
)


def _clean_objective(value: str) -> str:
    text = (value or "").strip().strip(" .!?;:-")
    text = re.sub(r"(?:,\s*)?please\s*$", "", text, flags=re.IGNORECASE)
    return text.strip().strip(" .!?;:-")


def _tail_objective(value: str) -> str:
    tail = (value or "").strip()
    tail = re.sub(r"^(?:to|for)\b", "", tail, count=1, flags=re.IGNORECASE)
    return _clean_objective(tail)


def _request_segments(message: str) -> tuple[str, ...]:
    return tuple(
        segment.strip()
        for segment in _REQUEST_SEGMENT_BOUNDARY.split(message)
        if segment.strip()
    )


def _explicit_objective(message: str) -> tuple[bool, str]:
    text = message.strip()
    slash = _SLASH_EXPLICIT.match(text)
    if slash:
        return True, _clean_objective(text[slash.end():].lstrip(" \t:-"))
    match = _USE_EXPLICIT.match(text)
    if match:
        return True, _tail_objective(match.group("tail"))
    match = _SEND_EXPLICIT.match(text)
    if match:
        return True, _tail_objective(match.group("tail"))
    match = _HAND_EXPLICIT.match(text)
    if match:
        return True, _tail_objective(match.group("tail"))
    match = _WITH_EXPLICIT.match(text)
    if match:
        return True, _clean_objective(match.group("objective"))
    return False, ""


def _objective_from_explicit(message: str) -> str:
    return _explicit_objective(message)[1]


_GENERIC_OBJECTIVE = re.compile(
    r"^(?:add|build|implement|enable|create)\s+(?:(?:a|an|the)\s+)?"
    r"(?:capability|feature|workflow|support|integration|behavior)$",
    re.IGNORECASE,
)
_BARE_ANAPHOR_OBJECTIVE = re.compile(
    r"^[A-Za-z][A-Za-z0-9_-]*\s+(?:it|this|that|them|these|those)$",
    re.IGNORECASE,
)


def _has_supporting_context(segments: tuple[str, ...], explicit_index: int) -> bool:
    for index, segment in enumerate(segments):
        if index == explicit_index:
            continue
        stripped = segment.strip()
        words = re.findall(r"[A-Za-z0-9_]+", stripped)
        if stripped.lstrip().startswith(("-", "*")) and words:
            return True
        if len(words) >= 3 and words[0].lower() not in {"please", "thank", "thanks"}:
            return True
    return False


def _meaningful_objective(objective: str, *, has_supporting_context: bool = False) -> bool:
    words = re.findall(r"[A-Za-z0-9_]+", objective)
    if len(words) < 2 or _GENERIC_OBJECTIVE.fullmatch(objective.strip()) is not None:
        return False
    return has_supporting_context or _BARE_ANAPHOR_OBJECTIVE.fullmatch(objective.strip()) is None


def _clarify_objective() -> DeveloperRequestQualification:
    return DeveloperRequestQualification(
        "clarify",
        question="What should Developer change, and what result should prove it is fixed?",
        reason="developer-objective-missing",
    )


def qualify_developer_request(message: str) -> DeveloperRequestQualification:
    """Recognize an explicit development hand-off without stealing native file work."""
    text = (message or "").strip()
    if not text:
        return DeveloperRequestQualification("unsupported", reason="empty-request")
    segments = _request_segments(text)
    for index, segment in enumerate(segments):
        explicit, objective = _explicit_objective(segment)
        if not explicit:
            continue
        if _NEGATED_REQUEST.search(segment) or _NEGATED_DEVELOPER.search(segment):
            return DeveloperRequestQualification("unsupported", reason="developer-request-negated")
        if not _meaningful_objective(
            objective,
            has_supporting_context=_has_supporting_context(segments, index),
        ):
            return _clarify_objective()
        return DeveloperRequestQualification("accepted", objective=objective)
    if any(
        _NEGATED_REQUEST.search(segment) or _NEGATED_DEVELOPER.search(segment)
        for segment in segments
    ):
        return DeveloperRequestQualification("unsupported", reason="developer-request-negated")
    if text.endswith("?") or _QUESTION_OPEN.match(text):
        return DeveloperRequestQualification("unsupported", reason="discussion-not-dispatch")
    if _MARKDOWN_CREATION.search(text):
        return DeveloperRequestQualification(
            "clarify",
            question=(
                "Do you want TOBI to create one Markdown file now, or add Markdown creation "
                "as a reusable product capability?"
            ),
            reason="file-or-capability-ambiguous",
        )
    if _DIRECT_FILE.search(text):
        return DeveloperRequestQualification("unsupported", reason="native-file-request")
    if _CAPABILITY.search(text):
        objective = _clean_objective(text)
        if not _meaningful_objective(objective):
            return _clarify_objective()
        return DeveloperRequestQualification("accepted", objective=objective)
    return DeveloperRequestQualification("unsupported", reason="not-developer-work")


def chat_developer_dispatch_enabled() -> bool:
    from core import owner_flags

    return owner_flags.get_bool(owner_flags.AGENT_CHAT_DEVELOPER_DISPATCH, True)


def set_chat_developer_dispatch(enabled: bool) -> bool:
    from core import owner_flags

    return owner_flags.set_bool(owner_flags.AGENT_CHAT_DEVELOPER_DISPATCH, enabled)


def _ensure_schema(conn) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS chat_developer_dispatches (
            id TEXT PRIMARY KEY,
            session_id INTEGER NOT NULL,
            client_turn_id TEXT NOT NULL,
            action_id INTEGER UNIQUE,
            status TEXT NOT NULL,
            title TEXT NOT NULL,
            objective TEXT NOT NULL,
            proposal_json TEXT NOT NULL,
            queue_id INTEGER,
            workflow_id INTEGER,
            readiness_id INTEGER,
            user_message_id INTEGER,
            assistant_message_id INTEGER,
            blocker TEXT,
            error_code TEXT,
            queue_snapshot_hash TEXT,
            runtime_run_id TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(session_id, client_turn_id)
        );
        CREATE INDEX IF NOT EXISTS idx_chat_developer_dispatch_session
            ON chat_developer_dispatches(session_id, created_at);
        """
    )
    columns = {
        str(row[1]) for row in conn.execute(
            "PRAGMA table_info(chat_developer_dispatches)"
        ).fetchall()
    }
    if "user_message_id" not in columns:
        conn.execute("ALTER TABLE chat_developer_dispatches ADD COLUMN user_message_id INTEGER")
    if "assistant_message_id" not in columns:
        conn.execute("ALTER TABLE chat_developer_dispatches ADD COLUMN assistant_message_id INTEGER")
    if "queue_snapshot_hash" not in columns:
        conn.execute("ALTER TABLE chat_developer_dispatches ADD COLUMN queue_snapshot_hash TEXT")
    if "runtime_run_id" not in columns:
        conn.execute("ALTER TABLE chat_developer_dispatches ADD COLUMN runtime_run_id TEXT")
    conn.commit()


def _dispatch_id(session_id: int, client_turn_id: str) -> str:
    digest = hashlib.sha256(f"{int(session_id)}:{client_turn_id}".encode("utf-8")).hexdigest()
    return f"dev-{digest[:24]}"


def _title(objective: str) -> str:
    value = re.sub(
        r"^(?:to\s+)?(?:fix|repair|add|build|implement|enable)\s+",
        "",
        objective.strip(),
        flags=re.IGNORECASE,
    )
    sentence = re.split(r"[.!?](?:\s|$)", value, maxsplit=1)[0].strip()
    words = sentence.split()
    result = " ".join(words[:12]).strip() or "Chat requested Developer work"
    return result[:1].upper() + result[1:120]


_HIGH_RISK_OBJECTIVE = re.compile(
    r"\b(?:delete|remove|wipe|erase|drop|destroy|format|reset|overwrite|publish|deploy|merge|"
    r"credential|secret|password|token|production|payment|spend)\b",
    re.IGNORECASE,
)


def _proposal_risk(objective: str) -> str:
    return "high" if _HIGH_RISK_OBJECTIVE.search(objective) else "medium"


def _proposal(objective: str, *, context: str) -> dict[str, Any]:
    bounded = objective.strip().rstrip(".")
    owner_context = context.strip()
    return {
        "title": _title(objective),
        "objective": objective,
        "context": owner_context,
        "project": "TOBI",
        "acceptance_checks": [
            f"Mission Control completes this owner outcome: {bounded}.",
            "A focused regression check proves the repaired behavior.",
            "The active package gate remains green.",
            "Changed files, checks, and generated evidence are linked to the Developer run.",
        ],
        "scope": [
            "Work only inside the TOBI main checkout and the described limitation.",
            "Reuse the existing Developer control plane and its approval gates.",
            "Do not merge, deploy, delete, or overwrite protected work without Developer approval.",
        ],
        "risk": _proposal_risk(f"{objective}\n{owner_context}"),
    }


def _decode_row(row) -> dict[str, Any]:
    item = dict(row)
    try:
        proposal = json.loads(item.pop("proposal_json") or "{}")
    except (TypeError, ValueError):
        proposal = {}
        item.pop("proposal_json", None)
    item["proposal"] = proposal if isinstance(proposal, dict) else {}
    item["proposal"].setdefault("context", str(item.get("objective") or ""))
    return item


def _developer_plan_markdown(proposal: dict[str, Any], marker: str) -> str:
    criteria = [str(value) for value in proposal.get("acceptance_checks") or []]
    scope = [str(value) for value in proposal.get("scope") or []]
    context = str(proposal.get("context") or proposal["objective"]).strip()
    return "\n".join([
        f"# {proposal['title']}",
        "",
        marker,
        "",
        "## Objective",
        str(proposal["objective"]),
        "",
        "## Context",
        context,
        "",
        "## Acceptance Criteria",
        *[f"- {value}" for value in criteria],
        "",
        "## Scope",
        *[f"- {value}" for value in scope],
        "",
        "## Delivery Notes",
        "- This item was created from a confirmed Mission Control Chat proposal.",
        "- The existing Developer preflight, worker, review, and approval gates remain authoritative.",
        "",
    ])


class ExistingDeveloperGateway:
    """Narrow adapter over the already-shipped Developer control plane."""

    def __init__(self) -> None:
        from core.coding_agent import CodingAgent

        self.agent = CodingAgent()

    @staticmethod
    def _marker(dispatch_id: str) -> str:
        return f"<!-- {_MARKER_PREFIX}{dispatch_id} -->"

    def create_or_recover_queue_item(self, dispatch: dict) -> dict:
        from core.coding_queue import QUEUE_PATH, REPO_ROOT, parse_queue
        from core.coding_queue_authoring import create_queue_item, queue_hash

        marker = self._marker(str(dispatch["id"]))
        for item in parse_queue(QUEUE_PATH):
            plan = REPO_ROOT / str(item.get("plan_path") or "")
            if plan.is_file() and marker in plan.read_text(encoding="utf-8", errors="replace"):
                return {"queue_id": int(item["queue_id"]), "plan_path": item["plan_path"]}

        proposal = dispatch["proposal"]
        criteria = [str(value) for value in proposal.get("acceptance_checks") or []]
        context = str(proposal.get("context") or proposal["objective"]).strip()
        plan = _developer_plan_markdown(proposal, marker)
        return create_queue_item(
            title=str(proposal["title"]),
            objective=context,
            acceptance_criteria=criteria,
            risk=str(proposal.get("risk") or "medium"),
            expected_queue_hash=str(dispatch.get("queue_snapshot_hash") or queue_hash()),
            plan_markdown=plan,
            source_note="Created from an owner-confirmed Mission Control Chat proposal.",
        )

    def preflight(self, queue_id: int) -> dict:
        return self.agent.preflight(queue_id, active_probe=True)

    def create_workflow(self, queue_id: int, *, idempotency_key: str, readiness_id: int) -> dict:
        return self.agent.create_workflow(
            queue_id,
            idempotency_key=idempotency_key,
            readiness_id=readiness_id,
        )

    def start_workflow(self, workflow_id: int) -> dict:
        return self.agent.start_background(workflow_id)

    def get_workflow(self, workflow_id: int) -> dict:
        return self.agent.get_workflow(workflow_id)

    def changes(self, workflow_id: int) -> dict:
        return self.agent.changes(workflow_id)

    def artifacts(self, workflow_id: int) -> list[dict]:
        return self.agent.store.list_artifacts(workflow_id)


_default_gateway: Any | None = None


def _shared_gateway() -> Any:
    global _default_gateway
    with _GATEWAY_LOCK:
        if _default_gateway is None:
            _default_gateway = ExistingDeveloperGateway()
        return _default_gateway


_gateway_factory: Callable[[], Any] = _shared_gateway


class DeveloperDispatchService:
    def __init__(self, gateway: Any | None = None) -> None:
        self._gateway_instance = gateway
        conn = get_connection()
        try:
            _ensure_schema(conn)
        finally:
            conn.close()

    @property
    def gateway(self) -> Any:
        if self._gateway_instance is None:
            self._gateway_instance = _gateway_factory()
        return self._gateway_instance

    def _find(self, dispatch_id: str) -> dict | None:
        conn = get_connection()
        try:
            _ensure_schema(conn)
            row = conn.execute(
                "SELECT * FROM chat_developer_dispatches WHERE id=?", (str(dispatch_id),)
            ).fetchone()
            return _decode_row(row) if row else None
        finally:
            conn.close()

    def _update(self, dispatch_id: str, **fields: Any) -> dict:
        allowed = {
            "action_id", "status", "queue_id", "workflow_id", "readiness_id",
            "user_message_id", "assistant_message_id", "blocker", "error_code",
            "queue_snapshot_hash", "runtime_run_id",
        }
        values = [(key, value) for key, value in fields.items() if key in allowed]
        if not values:
            found = self._find(dispatch_id)
            if found is None:
                raise KeyError(dispatch_id)
            return found
        conn = get_connection()
        try:
            _ensure_schema(conn)
            assignments = [f"{key}=?" for key, _ in values]
            params = [value for _, value in values]
            assignments.append("updated_at=?")
            params.extend([utc_now(), str(dispatch_id)])
            conn.execute(
                f"UPDATE chat_developer_dispatches SET {','.join(assignments)} WHERE id=?",
                params,
            )
            conn.commit()
        finally:
            conn.close()
        found = self._find(dispatch_id)
        if found is None:
            raise KeyError(dispatch_id)
        return found

    def _ensure_runtime_run(self, dispatch: dict) -> dict:
        """Create one active canonical Runtime record after owner confirmation."""
        from core.runtime.contracts import (
            ExecutionPlan,
            LoopPolicy,
            LoopRecipe,
            LoopType,
            PlanStep,
            RiskLevel,
            RunRequest,
            Surface,
        )
        from core.runtime.repository import RuntimeRepository
        from core.runtime.state import RunStatus

        with _RUNTIME_LOCK:
            repository = RuntimeRepository()
            request_id = f"chat-developer-dispatch:{dispatch['id']}"
            canonical = RunRequest(
                request_id=request_id,
                surface=Surface.CHAT,
                owner_id="owner",
                session_id=str(dispatch["session_id"]),
                mode="chat",
                message=str(dispatch["objective"]),
                attachments=({"kind": "developer_dispatch", "id": str(dispatch["id"])},),
                budget_profile="chat-developer-t02a",
            )
            run = repository.find_matching_run(canonical)
            if run is None:
                recipe = LoopRecipe(
                    recipe_id="agent.chat-developer-dispatch",
                    version="1",
                    name="Confirmed Chat to Developer dispatch",
                    loop_type=LoopType.TURN,
                    trigger="owner-confirmed Developer proposal in Chat",
                    objective="Complete one approved coding-maintenance workflow",
                    stop_condition="Developer reports changed files, a passing check, and retained evidence",
                    max_attempts=2,
                    max_runtime_s=86_400,
                    max_cost_usd=0.0,
                    max_model_calls=1,
                    max_tool_calls=1,
                    allowed_tools=(),
                    approval_gates=("owner",),
                    recovery_policy="recover_in_developer",
                    evidence_required=("developer_workflow", "coding_check", "artifact"),
                )
                repository.save_loop_recipe(recipe)
                run = repository.create_run(
                    canonical,
                    loop_policy=LoopPolicy.from_recipe(
                        policy_id="agent.chat-developer-dispatch.active",
                        version="1",
                        recipe=recipe,
                        policy_decision_id=f"owner-confirmed:{dispatch['id']}",
                        enabled=True,
                    ),
                    run_id=str(uuid.uuid5(uuid.NAMESPACE_URL, request_id)),
                    actor="chat-developer-gateway",
                )
            if run["status"] == RunStatus.ACCEPTED.value:
                run = repository.transition_run(
                    str(run["run_id"]), RunStatus.ROUTING,
                    expected_version=int(run["version"]), actor="chat-developer-gateway",
                )
            if run["status"] == RunStatus.ROUTING.value:
                run = repository.save_plan(
                    ExecutionPlan(
                        plan_id=f"{run['run_id']}:developer-dispatch",
                        run_id=str(run["run_id"]),
                        version="1",
                        objective=str(dispatch["objective"]),
                        steps=(PlanStep(
                            step_id="developer-workflow",
                            kind="workflow",
                            risk=RiskLevel.HIGH,
                            output_contract={
                                "required": ["changed_files", "passing_check", "artifact"],
                            },
                        ),),
                        expected_artifacts=("developer_evidence",),
                        approval_points=("owner",),
                        completion_predicate="Developer evidence is complete",
                    ),
                    expected_version=int(run["version"]),
                    actor="chat-developer-planner",
                )
            if run["status"] == RunStatus.PLANNED.value:
                run = repository.transition_run(
                    str(run["run_id"]), RunStatus.RUNNING,
                    expected_version=int(run["version"]), actor="chat-developer-gateway",
                )
            return self._update(dispatch["id"], runtime_run_id=str(run["run_id"]))

    @staticmethod
    def _complete_runtime_and_tier(dispatch: dict, artifacts: list[dict]) -> None:
        """Close canonical proof and publish Tier II evidence idempotently."""
        from core import agent_tier
        from core.release_manager import current_developer_version
        from core.runtime.contracts import RuntimeToolResult
        from core.runtime.control import RuntimeControl
        from core.runtime.repository import RuntimeRepository
        from core.runtime.state import RunStatus

        run_id = str(dispatch.get("runtime_run_id") or "")
        workflow_id = int(dispatch.get("workflow_id") or 0)
        action_id = int(dispatch.get("action_id") or 0)
        if not run_id or not workflow_id or not action_id:
            return
        with _RUNTIME_LOCK:
            repository = RuntimeRepository()
            run = repository.get_run(run_id)
            if run is None:
                return
            if run["status"] == RunStatus.RUNNING.value:
                claim = repository.claim_step(
                    run_id, worker_id=f"developer-dispatch:{dispatch['id']}", lease_seconds=60,
                )
                if claim is not None:
                    artifact_refs = tuple(
                        f"artifact:{item['id']}" for item in artifacts if item.get("id") is not None
                    )
                    RuntimeControl().record_step_success(
                        run_id,
                        "developer-workflow",
                        worker_id=str(claim["worker_id"]),
                        lease_token=str(claim["lease_token"]),
                        lease_epoch=int(claim["lease_epoch"]),
                        result=RuntimeToolResult(
                            status="succeeded",
                            typed_output={"workflow_id": workflow_id, "evidence_complete": True},
                            evidence_refs=(
                                f"workflow:{workflow_id}",
                                f"check:developer-workflow:{workflow_id}:scorecard",
                            ),
                            artifact_refs=artifact_refs,
                        ),
                    )
                run = repository.get_run(run_id) or run
                steps = repository.list_steps(run_id)
                if steps and all(step["status"] in {"succeeded", "skipped"} for step in steps):
                    run = repository.transition_run(
                        run_id, RunStatus.SUCCEEDED,
                        expected_version=int(run["version"]), actor="chat-developer-gateway",
                    )
            if run["status"] != RunStatus.SUCCEEDED.value:
                return
            conn = get_connection()
            try:
                release = current_developer_version(conn)
                evidence = (
                    ("runtime_run", f"run:{run_id}"),
                    ("typed_tool_result", f"check:{run_id}:developer-result"),
                    ("local_action_receipt", f"receipt:action:{action_id}"),
                    ("coding_check", f"check:developer-workflow:{workflow_id}:scorecard"),
                )
                for evidence_type, evidence_ref in evidence:
                    agent_tier.record_evidence(
                        conn,
                        ability_id="local_work_execution",
                        family_id="coding_maintenance",
                        evidence_type=evidence_type,
                        evidence_ref=evidence_ref,
                        source_release=release,
                    )
            finally:
                conn.close()

    @staticmethod
    def _pending_action(dispatch: dict) -> dict | None:
        action_id = dispatch.get("action_id")
        if not action_id:
            return None
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT status,risk,summary FROM tobi_actions WHERE id=?", (int(action_id),)
            ).fetchone()
        except Exception:
            row = None
        finally:
            conn.close()
        if not row or row["status"] != "proposed":
            return None
        return {
            "id": int(action_id),
            "tool": "developer_dispatch",
            "risk": row["risk"],
            "status": row["status"],
            "summary": row["summary"],
            "developer_proposal": dispatch["proposal"],
        }

    def propose(self, *, session_id: int, client_turn_id: str, message: str) -> dict:
        qualification = qualify_developer_request(message)
        if qualification.status == "clarify":
            return {"status": "clarify", "reply": qualification.question, "qualification": qualification}
        if qualification.status != "accepted":
            return {"status": "unsupported", "reply": "", "qualification": qualification}
        turn_id = (client_turn_id or "").strip()
        if not turn_id:
            raise ValueError("client_turn_id is required for Developer dispatch")
        dispatch_id = _dispatch_id(session_id, turn_id)
        dispatch = self._find(dispatch_id)
        if dispatch is None:
            proposal = _proposal(qualification.objective, context=message)
            now = utc_now()
            try:
                from core.coding_queue_authoring import queue_hash

                snapshot_hash = queue_hash()
            except Exception:
                snapshot_hash = None
            conn = get_connection()
            try:
                _ensure_schema(conn)
                conn.execute(
                    """INSERT OR IGNORE INTO chat_developer_dispatches
                       (id,session_id,client_turn_id,status,title,objective,proposal_json,
                        queue_snapshot_hash,created_at,updated_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (
                        dispatch_id, int(session_id), turn_id, "proposed", proposal["title"],
                        proposal["objective"], json.dumps(proposal, ensure_ascii=True),
                        snapshot_hash, now, now,
                    ),
                )
                conn.commit()
            finally:
                conn.close()
            dispatch = self._find(dispatch_id)
        assert dispatch is not None
        if not dispatch.get("action_id"):
            from core import conductor
            from core.chat_store import chat_id_for_session

            pending = conductor.propose_developer_action(
                dispatch_id,
                dispatch["proposal"],
                chat_id=chat_id_for_session(session_id),
            )
            dispatch = self._update(dispatch_id, action_id=int(pending["id"]))
        pending = self._pending_action(dispatch)
        reply = (
            "I prepared a Developer proposal. No queue item or coding workflow exists yet. "
            "Review the objective, acceptance checks, scope, and risk, then choose Accept or Refuse."
        )
        return {
            "status": dispatch["status"],
            "reply": reply,
            "pending_action": pending,
            "dispatch": self._project(dispatch, refresh=False),
        }

    def persist_exchange(
        self,
        dispatch_id: str,
        *,
        user_content: str,
        assistant_content: str,
        mode: str,
    ) -> dict[str, Any]:
        """Persist the Chat turn once, keyed by the durable dispatch identity."""
        from core import chat_store

        conn = get_connection()
        try:
            chat_store.ensure_schema(conn)
            _ensure_schema(conn)
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM chat_developer_dispatches WHERE id=?", (str(dispatch_id),)
            ).fetchone()
            if not row:
                conn.rollback()
                raise KeyError(dispatch_id)
            dispatch = _decode_row(row)
            if dispatch.get("user_message_id") and dispatch.get("assistant_message_id"):
                conn.commit()
                return {
                    "user_message_id": int(dispatch["user_message_id"]),
                    "assistant_message_id": int(dispatch["assistant_message_id"]),
                    "replayed": True,
                }
            now = utc_now()
            user_mid = conn.execute(
                """INSERT INTO chat_messages
                   (session_id,role,content,parent_id,model,tokens,thinking,meta,created_at)
                   VALUES (?,'user',?,NULL,NULL,NULL,NULL,NULL,?)""",
                (int(dispatch["session_id"]), user_content, now),
            ).lastrowid
            meta = json.dumps({
                "mode": mode,
                "developer_dispatch_id": dispatch["id"],
            }, ensure_ascii=True)
            assistant_mid = conn.execute(
                """INSERT INTO chat_messages
                   (session_id,role,content,parent_id,model,tokens,thinking,meta,created_at)
                   VALUES (?,'assistant',?,NULL,'not_used',0,NULL,?,?)""",
                (int(dispatch["session_id"]), assistant_content, meta, now),
            ).lastrowid
            conn.execute(
                """UPDATE chat_developer_dispatches
                   SET user_message_id=?,assistant_message_id=?,updated_at=? WHERE id=?""",
                (int(user_mid), int(assistant_mid), now, dispatch["id"]),
            )
            conn.execute(
                "UPDATE chat_sessions SET updated_at=? WHERE id=?",
                (now, int(dispatch["session_id"])),
            )
            conn.commit()
            return {
                "user_message_id": int(user_mid),
                "assistant_message_id": int(assistant_mid),
                "replayed": False,
            }
        finally:
            conn.close()

    @staticmethod
    def _passed_check(item: dict) -> bool:
        if item.get("ok") is True:
            return True
        return str(item.get("status") or "").lower() in {"passed", "success", "completed"}

    @staticmethod
    def _artifact(item: dict, workflow_id: int) -> dict:
        raw_path = str(item.get("path") or "")
        kind = str(item.get("evidence_type") or item.get("kind") or "artifact")
        return {
            "id": item.get("id"),
            "kind": kind,
            "title": Path(raw_path).name or kind.replace("_", " ").title(),
            "group": "generated",
            "workflow_id": workflow_id,
            "developer_url": f"/developer?workflow={workflow_id}&artifact={item.get('id')}",
        }

    @staticmethod
    def _next_action(status: str, workflow_id: int | None) -> str:
        if status == "proposed":
            return "Choose Accept to start this work, or Refuse to cancel it."
        if status == "failed" and workflow_id:
            return "Open Developer and select Retry for this run."
        if status == "failed":
            return "Select Retry on this card to try the approved hand-off again."
        if status in {"blocked", "waiting_approval"}:
            return "Open Developer to review the blocker or approval."
        if status == "completed":
            return "Open an evidence item below to review the delivered result."
        return "Open Developer to inspect the live run."

    @staticmethod
    def _owner_failure(stage: str, *, workflow_id: int | None = None) -> tuple[str, str]:
        if stage == "queue":
            return (
                "Developer could not add this approved item to the queue.",
                "Select Retry on this card to re-check the queue and try again.",
            )
        if stage == "preflight":
            return (
                "Developer found a readiness blocker before coding could start.",
                "Open Developer to review the readiness check, then retry when it is resolved.",
            )
        if stage == "start" and workflow_id:
            return (
                "Developer created the workflow but could not start it.",
                "Open Developer and select Retry for this run.",
            )
        return (
            "Developer could not start this approved work.",
            "Select Retry on this card, or open Developer to inspect the queue.",
        )

    def _project(self, dispatch: dict, *, refresh: bool = True) -> dict:
        proposal = dispatch["proposal"]
        result = {
            "id": dispatch["id"],
            "session_id": int(dispatch["session_id"]),
            "status": dispatch["status"],
            "title": dispatch["title"],
            "objective": dispatch["objective"],
            "proposal": proposal,
            "queue_id": dispatch.get("queue_id"),
            "workflow_id": dispatch.get("workflow_id"),
            "runtime_run_id": dispatch.get("runtime_run_id"),
            "user_message_id": dispatch.get("user_message_id"),
            "assistant_message_id": dispatch.get("assistant_message_id"),
            "stage": None,
            "progress": 0,
            "blocker": dispatch.get("blocker"),
            "error_code": dispatch.get("error_code"),
            "next_action": self._next_action(
                str(dispatch["status"]),
                int(dispatch["workflow_id"]) if dispatch.get("workflow_id") else None,
            ),
            "can_retry": dispatch.get("status") == "failed" and not dispatch.get("workflow_id"),
            "changes": {"files": [], "stat": ""},
            "checks": [],
            "artifacts": [],
            "developer_url": (
                f"/developer?workflow={int(dispatch['workflow_id'])}"
                if dispatch.get("workflow_id") else "/developer"
            ),
            "updated_at": dispatch["updated_at"],
        }
        workflow_id = dispatch.get("workflow_id")
        if not refresh or not workflow_id:
            return result
        try:
            workflow = self.gateway.get_workflow(int(workflow_id))
            state = str(workflow.get("state") or "")
            kind = STATE_KIND.get(state, "fault")
            changes = (
                self.gateway.changes(int(workflow_id)) or {"files": [], "stat": ""}
                if kind != "active" else {"files": [], "stat": ""}
            )
            raw_artifacts = self.gateway.artifacts(int(workflow_id)) or []
        except Exception as exc:
            result.update({
                "status": "failed",
                "blocker": "Developer status could not be read.",
                "error_code": f"developer-status-{type(exc).__name__.lower()}",
                "next_action": "Refresh this card, or open Developer to inspect the run.",
            })
            return result

        scorecard = workflow.get("scorecard") if isinstance(workflow.get("scorecard"), dict) else {}
        checks = [item for item in scorecard.get("checks") or [] if isinstance(item, dict)]
        artifacts = [self._artifact(item, int(workflow_id)) for item in raw_artifacts]
        files = [str(value) for value in changes.get("files") or []]
        developer_url = f"/developer?workflow={int(workflow_id)}"
        if workflow.get("plan_path"):
            artifacts.append({
                "id": f"plan-{workflow_id}",
                "kind": "plan",
                "title": Path(str(workflow["plan_path"])).name,
                "group": "generated",
                "workflow_id": int(workflow_id),
                "developer_url": f"{developer_url}&artifact=plan",
            })
        if files:
            artifacts.append({
                "id": f"changes-{workflow_id}",
                "kind": "changes",
                "title": "Change summary",
                "group": "generated",
                "workflow_id": int(workflow_id),
                "developer_url": f"{developer_url}&artifact=changes",
            })
        if checks:
            artifacts.append({
                "id": f"checks-{workflow_id}",
                "kind": "test_report",
                "title": "Test report",
                "group": "generated",
                "workflow_id": int(workflow_id),
                "developer_url": f"{developer_url}&artifact=checks",
            })
        status = "running"
        blocker = workflow.get("blocker")
        error_code = workflow.get("error_code")
        if kind == "waiting":
            status = "waiting_approval" if state.startswith("awaiting_") else "blocked"
        elif kind == "fault":
            status = "failed"
        elif state == "canceled" or kind == "idle":
            status = "canceled"
        elif kind == "success":
            evidence_complete = bool(files) and bool(artifacts) and any(self._passed_check(item) for item in checks)
            status = "completed" if evidence_complete else "blocked"
            if not evidence_complete:
                blocker = (
                    "Developer finished, but changed files, a passing check, or a retained evidence file is missing."
                )
                error_code = "developer-evidence-incomplete"
            else:
                self._complete_runtime_and_tier(dispatch, raw_artifacts)
                if dispatch.get("status") != "completed":
                    dispatch = self._update(
                        dispatch["id"], status="completed", blocker=None, error_code=None,
                    )
        if dispatch.get("status") == "failed" and state == "approved":
            status = "failed"
            blocker = dispatch.get("blocker")
            error_code = dispatch.get("error_code")
        result.update({
            "status": status,
            "underlying_state": state,
            "stage": workflow.get("stage"),
            "progress": int(workflow.get("progress") or 0),
            "blocker": blocker,
            "error_code": error_code,
            "changes": {**changes, "files": files},
            "checks": checks,
            "artifacts": artifacts,
            "next_action": self._next_action(status, int(workflow_id)),
        })
        return result

    def get(self, dispatch_id: str) -> dict:
        dispatch = self._find(dispatch_id)
        if dispatch is None:
            raise KeyError(dispatch_id)
        return self._project(dispatch)

    def list_for_session(self, session_id: int) -> list[dict]:
        conn = get_connection()
        try:
            _ensure_schema(conn)
            rows = conn.execute(
                "SELECT * FROM chat_developer_dispatches WHERE session_id=? ORDER BY created_at,id",
                (int(session_id),),
            ).fetchall()
        finally:
            conn.close()
        return [self._project(_decode_row(row)) for row in rows]

    def retry(self, dispatch_id: str) -> dict:
        """Retry an approved hand-off that failed before a Developer workflow existed."""
        with _CONFIRM_LOCK:
            dispatch = self._find(dispatch_id)
            if dispatch is None:
                raise KeyError(dispatch_id)
            if dispatch.get("status") != "failed" or dispatch.get("workflow_id"):
                raise ValueError("This Developer dispatch must be recovered in Developer.")
            action_id = dispatch.get("action_id")
            if not action_id:
                raise ValueError("This Developer dispatch has no linked approval.")

            conn = get_connection()
            try:
                _ensure_schema(conn)
                conn.execute("BEGIN IMMEDIATE")
                action = conn.execute(
                    "SELECT tool,status,result_json FROM tobi_actions WHERE id=?", (int(action_id),)
                ).fetchone()
                if not action or action["tool"] != "developer_dispatch" or action["status"] != "failed":
                    conn.rollback()
                    raise ValueError("This Developer approval is not retryable.")
                try:
                    previous_result = json.loads(action["result_json"] or "{}")
                except (TypeError, ValueError):
                    previous_result = {}
                previous_dispatch = (
                    previous_result.get("developer_dispatch")
                    if isinstance(previous_result, dict)
                    and isinstance(previous_result.get("developer_dispatch"), dict)
                    else {}
                )
                previous = {
                    "status": str(previous_result.get("status") or "failed"),
                    "error": previous_result.get("error") or previous_dispatch.get("blocker"),
                    "error_code": previous_dispatch.get("error_code"),
                    "blocker": previous_dispatch.get("blocker"),
                }
                previous = {key: value for key, value in previous.items() if value not in (None, "")}
                metadata = {
                    "developer_dispatch": {"dispatch_id": str(dispatch_id)},
                    "previous_failure": previous,
                }
                try:
                    from core.coding_queue_authoring import queue_hash

                    refreshed_hash = queue_hash()
                except Exception:
                    refreshed_hash = dispatch.get("queue_snapshot_hash")
                now = utc_now()
                conn.execute(
                    """UPDATE tobi_actions
                       SET status='proposed',result_json=?,executed_at=NULL WHERE id=?""",
                    (json.dumps(metadata, sort_keys=True), int(action_id)),
                )
                conn.execute(
                    """UPDATE chat_developer_dispatches
                       SET status='proposed',blocker=NULL,error_code=NULL,
                           queue_snapshot_hash=?,updated_at=? WHERE id=?""",
                    (refreshed_hash, now, str(dispatch_id)),
                )
                conn.commit()
            finally:
                conn.close()

            from core import conductor

            return conductor.confirm_action(int(action_id), "approve")

    def resolve_linked_action(self, action_row: dict, decision: str, metadata: dict) -> dict:
        dispatch_id = str(metadata.get("dispatch_id") or "")
        dispatch = self._find(dispatch_id)
        if dispatch is None:
            return {"ok": False, "status": "failed", "error": "Developer proposal was not found."}
        if str(decision).lower() in {"reject", "no", "cancel", "deny"}:
            dispatch = self._update(dispatch_id, status="canceled", blocker="Owner refused the proposal.")
            return {
                "ok": True,
                "status": "rejected",
                "summary": action_row.get("summary"),
                "developer_dispatch": self._project(dispatch, refresh=False),
            }
        with _CONFIRM_LOCK:
            dispatch = self._find(dispatch_id)
            assert dispatch is not None
            stage = "runtime"
            try:
                dispatch = self._ensure_runtime_run(dispatch)
                if not dispatch.get("queue_id"):
                    stage = "queue"
                    created = self.gateway.create_or_recover_queue_item(dispatch)
                    dispatch = self._update(
                        dispatch_id,
                        status="preflighting",
                        queue_id=int(created["queue_id"]),
                        blocker=None,
                        error_code=None,
                    )
                if not dispatch.get("workflow_id"):
                    stage = "preflight"
                    readiness = self.gateway.preflight(int(dispatch["queue_id"]))
                    dispatch = self._update(
                        dispatch_id,
                        readiness_id=int(readiness.get("readiness_id") or 0) or None,
                    )
                    if not readiness.get("ready"):
                        detail, _next_action = self._owner_failure("preflight")
                        dispatch = self._update(
                            dispatch_id,
                            status="blocked",
                            blocker=detail,
                            error_code="developer-preflight-blocked",
                        )
                        return {
                            "ok": True,
                            "status": "executed",
                            "summary": action_row.get("summary"),
                            "developer_dispatch": self._project(dispatch, refresh=False),
                        }
                    workflow = self.gateway.create_workflow(
                        int(dispatch["queue_id"]),
                        idempotency_key=f"chat-developer-dispatch:{dispatch_id}",
                        readiness_id=int(readiness["readiness_id"]),
                    )
                    dispatch = self._update(
                        dispatch_id,
                        status="running",
                        workflow_id=int(workflow["id"]),
                        blocker=None,
                        error_code=None,
                    )
                    stage = "start"
                    self.gateway.start_workflow(int(workflow["id"]))
                projection = self._project(dispatch)
                return {
                    "ok": True,
                    "status": "executed",
                    "summary": action_row.get("summary"),
                    "developer_dispatch": projection,
                }
            except Exception as exc:
                blocker, next_action = self._owner_failure(
                    stage,
                    workflow_id=int(dispatch["workflow_id"]) if dispatch.get("workflow_id") else None,
                )
                dispatch = self._update(
                    dispatch_id,
                    status="failed",
                    blocker=blocker,
                    error_code=f"developer-{stage}-{type(exc).__name__.lower()}",
                )
                projection = self._project(dispatch, refresh=False)
                projection["next_action"] = next_action
                return {
                    "ok": False,
                    "status": "failed",
                    "error": blocker,
                    "summary": action_row.get("summary"),
                    "developer_dispatch": projection,
                }

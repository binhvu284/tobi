"""Durable Chat proposal -> owner confirmation -> existing Developer workflow.

This module owns only the hand-off. Queue authoring, preflight, coding execution,
approval gates, checkpoints, and evidence remain owned by ``CodingAgent``.
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from core.coding_states import STATE_KIND
from core.database import get_connection
from core.development_store import utc_now


_CONFIRM_LOCK = threading.RLock()
_GATEWAY_LOCK = threading.Lock()
_MARKER_PREFIX = "tobi-chat-developer-dispatch:"


@dataclass(frozen=True)
class DeveloperRequestQualification:
    status: str
    objective: str = ""
    question: str = ""
    reason: str = ""


_EXPLICIT = re.compile(
    r"(?:^/developer(?:\s+|$)|\b(?:use|ask|send)\s+(?:the\s+)?developer\b)",
    re.IGNORECASE,
)
_CAPABILITY = re.compile(
    r"\b(?:add|build|implement|enable)\b.*"
    r"\b(?:capability|feature|workflow|support|integration|behavior)\b",
    re.IGNORECASE,
)
_DIRECT_FILE = re.compile(
    r"\b(?:create|write|save|make)\b.*\b(?:this|a|the)\b.*"
    r"\b(?:markdown|md|file|document)\b",
    re.IGNORECASE,
)
_MARKDOWN_CREATION = re.compile(r"\b(?:make|create)\b.*\bmarkdown\s+creation\b", re.IGNORECASE)


def _objective_from_explicit(message: str) -> str:
    text = message.strip()
    if text.lower().startswith("/developer"):
        return text[len("/developer"):].strip(" :-")
    match = re.search(
        r"\b(?:use|ask|send)\s+(?:the\s+)?developer(?:\s+agent)?"
        r"(?:\s+to|\s+for)?\s+(.+)$",
        text,
        re.IGNORECASE,
    )
    return (match.group(1) if match else text).strip(" .:-")


def qualify_developer_request(message: str) -> DeveloperRequestQualification:
    """Recognize an explicit development hand-off without stealing native file work."""
    text = (message or "").strip()
    if not text:
        return DeveloperRequestQualification("unsupported", reason="empty-request")
    if _EXPLICIT.search(text):
        objective = _objective_from_explicit(text)
        if not objective:
            return DeveloperRequestQualification(
                "clarify",
                question="What should Developer change, and what result should prove it is fixed?",
                reason="developer-objective-missing",
            )
        return DeveloperRequestQualification("accepted", objective=objective)
    if _DIRECT_FILE.search(text):
        return DeveloperRequestQualification("unsupported", reason="native-file-request")
    if _CAPABILITY.search(text):
        return DeveloperRequestQualification("accepted", objective=text.strip(" ."))
    if _MARKDOWN_CREATION.search(text):
        return DeveloperRequestQualification(
            "clarify",
            question=(
                "Do you want TOBI to create one Markdown file now, or add Markdown creation "
                "as a reusable product capability?"
            ),
            reason="file-or-capability-ambiguous",
        )
    return DeveloperRequestQualification("unsupported", reason="not-developer-work")


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


def _proposal(objective: str) -> dict[str, Any]:
    return {
        "title": _title(objective),
        "objective": objective,
        "project": "TOBI",
        "acceptance_checks": [
            "The requested behavior works through the owner-facing Mission Control path.",
            "A focused regression check proves the repaired behavior.",
            "The active package gate remains green.",
            "Changed files, checks, and generated evidence are linked to the Developer run.",
        ],
        "scope": [
            "Work only inside the TOBI main checkout and the described limitation.",
            "Reuse the existing Developer control plane and its approval gates.",
            "Do not merge, deploy, delete, or overwrite protected work without Developer approval.",
        ],
        "risk": "medium",
    }


def _decode_row(row) -> dict[str, Any]:
    item = dict(row)
    try:
        item["proposal"] = json.loads(item.pop("proposal_json") or "{}")
    except (TypeError, ValueError):
        item["proposal"] = {}
        item.pop("proposal_json", None)
    return item


class ExistingDeveloperGateway:
    """Narrow adapter over the already-shipped Developer control plane."""

    def __init__(self) -> None:
        from core.coding_agent import CodingAgent

        self.agent = CodingAgent()

    @staticmethod
    def _marker(dispatch_id: str) -> str:
        return f"<!-- {_MARKER_PREFIX}{dispatch_id} -->"

    def create_or_recover_queue_item(self, dispatch: dict) -> dict:
        from core.coding_queue import REPO_ROOT, parse_queue
        from core.coding_queue_authoring import create_queue_item, queue_hash

        marker = self._marker(str(dispatch["id"]))
        for item in parse_queue():
            plan = REPO_ROOT / str(item.get("plan_path") or "")
            if plan.is_file() and marker in plan.read_text(encoding="utf-8", errors="replace"):
                return {"queue_id": int(item["queue_id"]), "plan_path": item["plan_path"]}

        proposal = dispatch["proposal"]
        criteria = [str(value) for value in proposal.get("acceptance_checks") or []]
        scope = [str(value) for value in proposal.get("scope") or []]
        plan = "\n".join([
            f"# {proposal['title']}",
            "",
            marker,
            "",
            "## Objective",
            str(proposal["objective"]),
            "",
            "## Acceptance Criteria",
            *[f"- Must {value.removeprefix('Must ').removeprefix('must ')}" for value in criteria],
            "",
            "## Scope",
            *[f"- {value}" for value in scope],
            "",
            "## Delivery Notes",
            "- This item was created from a confirmed Mission Control Chat proposal.",
            "- The existing Developer preflight, worker, review, and approval gates remain authoritative.",
            "",
        ])
        return create_queue_item(
            title=str(proposal["title"]),
            objective=str(proposal["objective"]),
            acceptance_criteria=criteria,
            risk=str(proposal.get("risk") or "medium"),
            expected_queue_hash=queue_hash(),
            plan_markdown=plan,
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
            proposal = _proposal(qualification.objective)
            now = utc_now()
            conn = get_connection()
            try:
                _ensure_schema(conn)
                conn.execute(
                    """INSERT OR IGNORE INTO chat_developer_dispatches
                       (id,session_id,client_turn_id,status,title,objective,proposal_json,created_at,updated_at)
                       VALUES (?,?,?,?,?,?,?,?,?)""",
                    (
                        dispatch_id, int(session_id), turn_id, "proposed", proposal["title"],
                        proposal["objective"], json.dumps(proposal, ensure_ascii=True), now, now,
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
            "developer_url": f"/developer?workflow={workflow_id}",
        }

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
            "user_message_id": dispatch.get("user_message_id"),
            "assistant_message_id": dispatch.get("assistant_message_id"),
            "stage": None,
            "progress": 0,
            "blocker": dispatch.get("blocker"),
            "error_code": dispatch.get("error_code"),
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
                "error_code": type(exc).__name__,
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
                "developer_url": developer_url,
            })
        if files:
            artifacts.append({
                "id": f"changes-{workflow_id}",
                "kind": "changes",
                "title": "Change summary",
                "group": "generated",
                "workflow_id": int(workflow_id),
                "developer_url": developer_url,
            })
        if checks:
            artifacts.append({
                "id": f"checks-{workflow_id}",
                "kind": "test_report",
                "title": "Test report",
                "group": "generated",
                "workflow_id": int(workflow_id),
                "developer_url": developer_url,
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
                blocker = "developer-evidence-incomplete"
                error_code = "developer-evidence-incomplete"
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
            try:
                if not dispatch.get("queue_id"):
                    created = self.gateway.create_or_recover_queue_item(dispatch)
                    dispatch = self._update(
                        dispatch_id,
                        status="preflighting",
                        queue_id=int(created["queue_id"]),
                        blocker=None,
                        error_code=None,
                    )
                if not dispatch.get("workflow_id"):
                    readiness = self.gateway.preflight(int(dispatch["queue_id"]))
                    dispatch = self._update(
                        dispatch_id,
                        readiness_id=int(readiness.get("readiness_id") or 0) or None,
                    )
                    if not readiness.get("ready"):
                        blockers = readiness.get("blockers") or []
                        detail = "; ".join(
                            str(item.get("message") or item) for item in blockers[:3]
                        ) or "Developer preflight found a blocker."
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
                    self.gateway.start_workflow(int(workflow["id"]))
                projection = self._project(dispatch)
                return {
                    "ok": True,
                    "status": "executed",
                    "summary": action_row.get("summary"),
                    "developer_dispatch": projection,
                }
            except Exception as exc:
                dispatch = self._update(
                    dispatch_id,
                    status="failed",
                    blocker=str(exc)[:1000],
                    error_code=type(exc).__name__,
                )
                return {
                    "ok": False,
                    "status": "failed",
                    "error": str(exc)[:1000],
                    "summary": action_row.get("summary"),
                    "developer_dispatch": self._project(dispatch, refresh=False),
                }

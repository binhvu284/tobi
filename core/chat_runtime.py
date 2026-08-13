"""Measured, additive runtime layer for Mission Control Chat and Agent turns."""
from __future__ import annotations

import json
import hashlib
import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from core.chat_runtime_contracts import RouteDecision, TurnError, TurnRequest
from core.database import get_connection
from core.runtime.owner_intelligence import SAFE_LOCAL_READ_TOOLS


RUNTIME_FLAG = "chat_runtime_v2"  # off | shadow | on
_SCHEMA_VERSION = "chat-runtime-v2-001"
_SECRET_RE = re.compile(r"(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*([^\s,;]+)")
_SECRET_KEY_RE = re.compile(r"(?i)(api[_-]?key|token|secret|password)")
_PAST_RE = re.compile(r"\b(previous|past|earlier|yesterday|last week|remember|discussed|conversation)\b", re.I)
_CURRENT_RE = re.compile(r"\b(current|latest|today|news|price|weather|research|search the web)\b", re.I)
_ACTION_RE = re.compile(r"\b(create|add|update|rename|delete|remove|assign|complete|run|install|configure|connect|save)\b", re.I)
_PROJECT_RE = re.compile(r"\b(project|task|goal|resource|progress)\b", re.I)
_CHAT_EXECUTOR: Optional[ThreadPoolExecutor] = None
_CHAT_EXECUTOR_LOCK = threading.Lock()


def chat_executor() -> ThreadPoolExecutor:
    """Bounded pool so slow model calls cannot exhaust FastAPI's shared executor."""
    global _CHAT_EXECUTOR
    if _CHAT_EXECUTOR is None:
        with _CHAT_EXECUTOR_LOCK:
            if _CHAT_EXECUTOR is None:
                _CHAT_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="tobi-chat")
    return _CHAT_EXECUTOR


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_payload(value: Any) -> Any:
    def scrub(item: Any) -> Any:
        if isinstance(item, dict):
            return {str(k): ("[REDACTED]" if _SECRET_KEY_RE.search(str(k)) else scrub(v))
                    for k, v in item.items()}
        if isinstance(item, (list, tuple)):
            return [scrub(v) for v in item]
        if isinstance(item, str):
            return _SECRET_RE.sub(r"\1=[REDACTED]", item)
        return item
    value = scrub(value)
    try:
        raw = json.dumps(value, default=str)
    except Exception:
        raw = json.dumps({"value": str(value)})
    if len(raw) > 12000:
        raw = raw[:12000] + '"}'
    try:
        return json.loads(raw)
    except Exception:
        return {"detail": raw[:12000]}


def ensure_schema() -> None:
    conn = get_connection()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS chat_turns (
                id TEXT PRIMARY KEY,
                client_turn_id TEXT,
                session_id INTEGER NOT NULL,
                run_id INTEGER,
                status TEXT NOT NULL DEFAULT 'running',
                mode TEXT NOT NULL DEFAULT 'chat',
                model TEXT,
                route TEXT,
                request_json TEXT,
                context_json TEXT,
                error_code TEXT,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                first_event_ms INTEGER,
                first_token_ms INTEGER,
                total_ms INTEGER
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_chat_turn_client
                ON chat_turns(client_turn_id) WHERE client_turn_id IS NOT NULL;
            CREATE INDEX IF NOT EXISTS idx_chat_turn_session ON chat_turns(session_id, started_at);
            CREATE TABLE IF NOT EXISTS chat_turn_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                turn_id TEXT NOT NULL,
                seq INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                stage TEXT NOT NULL,
                payload_json TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(turn_id, seq)
            );
            CREATE INDEX IF NOT EXISTS idx_chat_turn_events_turn ON chat_turn_events(turn_id, seq);
            CREATE TABLE IF NOT EXISTS chat_tool_receipts (
                idempotency_key TEXT PRIMARY KEY,
                turn_id TEXT,
                tool TEXT NOT NULL,
                args_hash TEXT NOT NULL,
                status TEXT NOT NULL,
                result_json TEXT,
                error_code TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        conn.execute(
            "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?,?)",
            (_SCHEMA_VERSION, _now()),
        )
        conn.commit()
    finally:
        conn.close()


def runtime_mode() -> str:
    ensure_schema()
    # Fails open (unset/unknown → "on") — the shipped behavior of this live flag; do not change.
    from core import owner_flags
    return owner_flags.get_enum(RUNTIME_FLAG, {"off", "shadow", "on"}, default="on")


def set_runtime_mode(mode: str) -> str:
    mode = str(mode or "").strip().lower()
    if mode not in {"off", "shadow", "on"}:
        raise ValueError("chat_runtime_v2 must be off, shadow, or on")
    ensure_schema()
    from core import owner_flags
    owner_flags.set_str(RUNTIME_FLAG, mode)
    return mode


_READ_ROUTES: list[tuple[re.Pattern[str], tuple[str, ...]]] = [
    (re.compile(r"\b(evolution|tier|ability)\b", re.I), ("get_evolution",)),
    (re.compile(r"\b(architecture|system design)\b", re.I), ("explain_architecture",)),
    (re.compile(r"\b(health|integration status)\b", re.I), ("check_health",)),
    (re.compile(r"\b(storage|disk space)\b", re.I), ("storage_status",)),
    (re.compile(r"\b(spend|cost|tokens|usage)\b", re.I), ("llm_spend",)),
    (re.compile(r"\b(github|repo|repository)\b", re.I), ("list_github_repos", "read_github")),
    (re.compile(r"\b(notion)\b", re.I), ("read_notion",)),
    (re.compile(r"\b(drive|gmail|calendar)\b", re.I), ("read_drive",)),
]

_ACTION_ROUTES: list[tuple[re.Pattern[str], tuple[str, ...]]] = [
    (re.compile(r"\b(create|add)\b.*\btask\b", re.I), ("list_projects", "create_task")),
    (re.compile(r"\b(complete|finish|mark)\b.*\btask\b", re.I), ("list_tasks", "complete_task")),
    (re.compile(r"\b(delete|remove)\b.*\btask\b", re.I), ("list_tasks", "delete_task")),
    (re.compile(r"\b(create|add|new)\b.*\bproject\b", re.I), ("create_project",)),
    (re.compile(r"\b(rename)\b.*\bproject\b", re.I), ("list_projects", "rename_project")),
    (re.compile(r"\b(delete|remove)\b.*\bproject\b", re.I), ("list_projects", "delete_project")),
    (re.compile(r"\b(create|add)\b.*\bgoal\b", re.I), ("list_projects", "create_goal")),
    (re.compile(r"\b(assign)\b.*\btask\b", re.I), ("list_tasks", "office_status", "assign_task")),
    (re.compile(r"\b(run|execute)\b.*\b(command|shell|terminal|script)\b", re.I),
     ("terminal_status", "run_command", "list_jobs", "job_output")),
    (re.compile(r"\b(install)\b.*\b(package|tool|dependency)\b", re.I),
     ("terminal_status", "install_package", "list_installed_tools")),
]


def route_turn(req: TurnRequest, intent: str, owner_context: Any = None) -> RouteDecision:
    text = (req.message or "").strip()
    caps = req.capabilities or {}
    if intent == "SMALLTALK":
        return RouteDecision("direct", intent, 0.99, reason="smalltalk fast path", final_tokens=900)
    if req.mode == "chat" and intent == "CODING":
        return RouteDecision("direct", intent, 0.95, reason="chat-mode coding advice", final_tokens=1800)
    if req.mode == "agent":
        for pattern, tools in _ACTION_ROUTES:
            if pattern.search(text):
                return RouteDecision("action", intent, 0.97, tools, max_tool_steps=4,
                                     reason="deterministic action route")
        if intent == "CODING":
            return RouteDecision("agent", intent, 0.92,
                                 ("outline_plan", "terminal_status", "run_command", "list_jobs",
                                  "job_output", "install_package", "list_installed_tools"),
                                 max_tool_steps=4, reason="Agent coding route")
    if _PAST_RE.search(text):
        return RouteDecision("read", intent, 0.96, ("recall_conversations", "recall"), max_tool_steps=2)
    if caps.get("web_search") or _CURRENT_RE.search(text):
        tools = ("web_search",) if caps.get("web_search") else ("get_current_datetime",)
        return RouteDecision("read", intent, 0.88, tools, reason="current-information request", max_tool_steps=2)
    for pattern, tools in _READ_ROUTES:
        if pattern.search(text):
            return RouteDecision("read", intent, 0.94, tools, max_tool_steps=2)
    if _PROJECT_RE.search(text):
        if _ACTION_RE.search(text):
            if req.mode != "agent":
                return RouteDecision("clarify", intent, 0.98, requires_clarification=True,
                                     reason="project mutations require Agent mode")
            return RouteDecision("action", intent, 0.9,
                                 ("list_projects", "list_tasks", "project_overview", "create_task",
                                  "create_project", "complete_task", "update_project_progress",
                                  "search_project_resources", "list_project_resources", "read_resource"),
                                 max_tool_steps=4, reason="project action")
        return RouteDecision("read", intent, 0.9,
                             ("list_projects", "list_tasks", "project_overview", "search_project_resources",
                              "list_project_resources", "read_resource"),
                             max_tool_steps=2)
    if req.mode == "agent":
        return RouteDecision("agent", intent, 0.8, max_tool_steps=4, reason="Agent execution path")
    memory_tools = tuple(
        tool for tool in (getattr(owner_context, "tool_hints", ()) or ())
        if tool in SAFE_LOCAL_READ_TOOLS
    )
    if getattr(owner_context, "route_hint", None) == "read" and memory_tools:
        return RouteDecision(
            "read",
            intent,
            0.70,
            memory_tools,
            max_tool_steps=2,
            reason="owner-memory fallback read hint",
        )
    return RouteDecision("direct", intent, 0.82, reason="ordinary conversation", final_tokens=1600)


@dataclass
class TurnRecorder:
    turn_id: str
    started: float
    seq: int = 0
    first_event_recorded: bool = False
    first_token_recorded: bool = False

    @classmethod
    def start(cls, req: TurnRequest, route: RouteDecision) -> "TurnRecorder":
        ensure_schema()
        turn_id = req.client_turn_id or str(uuid.uuid4())
        started = time.perf_counter()
        conn = get_connection()
        try:
            request_summary = {
                "session_id": req.session_id,
                "mode": req.mode,
                "model": req.model,
                "resume_run_id": req.resume_run_id,
                "capabilities": req.capabilities,
                "message_chars": len(req.message or ""),
                "message_sha256": hashlib.sha256((req.message or "").encode("utf-8")).hexdigest(),
            }
            conn.execute(
                "INSERT OR IGNORE INTO chat_turns "
                "(id,client_turn_id,session_id,run_id,status,mode,model,route,request_json,started_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (turn_id, req.client_turn_id, req.session_id, req.resume_run_id, "running", req.mode,
                 req.model, route.route, json.dumps(_safe_payload(request_summary)), _now()),
            )
            row = conn.execute("SELECT COALESCE(MAX(seq),0) AS seq FROM chat_turn_events WHERE turn_id=?",
                               (turn_id,)).fetchone()
            conn.commit()
        finally:
            conn.close()
        return cls(turn_id, started, seq=int(row["seq"] if row else 0))

    def bind_run(self, run_id: int) -> None:
        conn = get_connection()
        try:
            conn.execute("UPDATE chat_turns SET run_id=? WHERE id=?", (run_id, self.turn_id))
            conn.commit()
        finally:
            conn.close()

    def event(self, event_type: str, stage: str, data: Optional[dict] = None) -> dict[str, Any]:
        self.seq += 1
        elapsed = round((time.perf_counter() - self.started) * 1000)
        payload = _safe_payload(data or {})
        conn = get_connection()
        try:
            conn.execute(
                "INSERT INTO chat_turn_events(turn_id,seq,event_type,stage,payload_json,created_at) VALUES (?,?,?,?,?,?)",
                (self.turn_id, self.seq, event_type, stage, json.dumps(payload), _now()),
            )
            if not self.first_event_recorded:
                conn.execute("UPDATE chat_turns SET first_event_ms=? WHERE id=?", (elapsed, self.turn_id))
                self.first_event_recorded = True
            if event_type == "delta" and not self.first_token_recorded:
                conn.execute("UPDATE chat_turns SET first_token_ms=? WHERE id=?", (elapsed, self.turn_id))
                self.first_token_recorded = True
            conn.commit()
        finally:
            conn.close()
        return {"turn_id": self.turn_id, "seq": self.seq, "type": event_type, "stage": stage,
                "timestamp": _now(), "data": payload}

    def set_context(self, manifest: dict[str, Any]) -> None:
        # Persist provenance and budgets, never the private context body itself.
        summary = dict(manifest or {})
        summary["items"] = [
            {k: v for k, v in dict(item).items() if k != "content"}
            for item in (summary.get("items") or [])
        ]
        conn = get_connection()
        try:
            conn.execute("UPDATE chat_turns SET context_json=? WHERE id=?",
                         (json.dumps(_safe_payload(summary)), self.turn_id))
            conn.commit()
        finally:
            conn.close()

    def complete(self, status: str = "done", error: Optional[TurnError] = None) -> None:
        total = round((time.perf_counter() - self.started) * 1000)
        conn = get_connection()
        try:
            conn.execute(
                "UPDATE chat_turns SET status=?,error_code=?,completed_at=?,total_ms=? WHERE id=?",
                (status, error.code if error else None, _now(), total, self.turn_id),
            )
            conn.commit()
        finally:
            conn.close()


def get_trace(turn_id: str) -> Optional[dict[str, Any]]:
    ensure_schema()
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM chat_turns WHERE id=?", (turn_id,)).fetchone()
        if not row:
            return None
        turn = dict(row)
        for key in ("request_json", "context_json"):
            try:
                turn[key[:-5]] = json.loads(turn.pop(key) or "null")
            except Exception:
                turn[key[:-5]] = None
        events = conn.execute("SELECT seq,event_type,stage,payload_json,created_at FROM chat_turn_events "
                              "WHERE turn_id=? ORDER BY seq", (turn_id,)).fetchall()
        turn["events"] = []
        for event in events:
            item = dict(event)
            try:
                item["payload"] = json.loads(item.pop("payload_json") or "{}")
            except Exception:
                item["payload"] = {}
            turn["events"].append(item)
        return turn
    finally:
        conn.close()

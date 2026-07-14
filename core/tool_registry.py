"""Typed tool metadata, validation and idempotent invocation receipts."""
from __future__ import annotations

import hashlib
import inspect
import json
from typing import Any, Callable, Optional, get_args, get_origin, get_type_hints

from core.chat_runtime_contracts import ToolCall, ToolResult, ToolSpec, TurnError
from core.chat_runtime import ensure_schema
from core.database import get_connection


TERMINAL_SURFACE = {"run_command", "install_package", "configure_tool", "connect_tool",
                    "kill_job", "set_terminal_mode"}


def _json_type(annotation: Any) -> str:
    if annotation in (Any, inspect.Parameter.empty):
        return ""
    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin is not None and type(None) in args:
        annotation = next((a for a in args if a is not type(None)), str)
        origin = get_origin(annotation)
    if annotation is bool:
        return "boolean"
    if annotation is int:
        return "integer"
    if annotation is float:
        return "number"
    if annotation in (list, tuple) or origin in (list, tuple):
        return "array"
    if annotation is dict or origin is dict:
        return "object"
    return "string"


def make_spec(name: str, fn: Callable, description: str, risk: str) -> ToolSpec:
    properties: dict[str, Any] = {}
    required: list[str] = []
    try:
        signature = inspect.signature(fn)
        try:
            hints = get_type_hints(fn)
        except Exception:
            hints = {}
        for pname, param in signature.parameters.items():
            if pname.startswith("_") or param.kind in (param.VAR_KEYWORD, param.VAR_POSITIONAL):
                continue
            kind = _json_type(hints.get(pname, param.annotation))
            properties[pname] = ({"type": kind} if kind else {})
            if param.default is inspect.Parameter.empty:
                required.append(pname)
    except Exception:
        pass
    allowed_modes = ("agent",) if name in TERMINAL_SURFACE else ("chat", "agent")
    return ToolSpec(
        name=name,
        description=description,
        risk=risk,
        allowed_modes=allowed_modes,
        args_schema={"type": "object", "properties": properties, "required": required,
                     "additionalProperties": False},
        result_schema={"type": "object"},
        timeout_s=120 if name in TERMINAL_SURFACE else 30,
        retry_policy="transient_once" if risk == "read" else "never",
        idempotent=risk == "read",
        required_integrations=tuple(
            x for x in ("github" if "github" in name else None,
                        "notion" if "notion" in name else None,
                        "google" if name == "read_drive" else None) if x
        ),
    )


def build_specs(read_tools: dict, optional_tools: dict, act_tools: dict) -> dict[str, ToolSpec]:
    specs: dict[str, ToolSpec] = {}
    for name, (fn, desc) in {**read_tools, **optional_tools}.items():
        specs[name] = make_spec(name, fn, desc, "read")
    for name, (fn, risk, desc) in act_tools.items():
        specs[name] = make_spec(name, fn, desc, risk)
    return specs


def validate_call(call: dict, spec: Optional[ToolSpec], mode: str,
                  allowed_tools: Optional[set[str]] = None) -> Optional[TurnError]:
    if spec is None:
        return TurnError("tool.unknown", "tool_validation", "Unknown tool", False)
    if mode not in spec.allowed_modes:
        return TurnError("tool.mode_denied", "permission", f"{spec.name} is not available in {mode} mode", False)
    # Read tools bypass route scope — they're safe, non-mutating, and blocking them
    # was the root cause of "list_projects is blocked" and "tool.route_denied" errors.
    if spec.risk != "read" and allowed_tools is not None and spec.name not in allowed_tools:
        return TurnError("tool.route_denied", "permission", f"{spec.name} is outside this turn's tool scope", False)
    args = call.get("args") or {}
    if not isinstance(args, dict):
        return TurnError("tool.invalid_args", "tool_validation", "Tool arguments must be an object", False)
    props = spec.args_schema.get("properties") or {}
    extra = set(args) - set(props)
    if extra:
        return TurnError("tool.invalid_args", "tool_validation", f"Unexpected arguments: {', '.join(sorted(extra))}", False)
    for key, value in args.items():
        expected = (props.get(key) or {}).get("type")
        ok = (expected == "string" and isinstance(value, str)) or \
             (expected == "integer" and isinstance(value, int) and not isinstance(value, bool)) or \
             (expected == "number" and isinstance(value, (int, float)) and not isinstance(value, bool)) or \
             (expected == "boolean" and isinstance(value, bool)) or \
             (expected == "array" and isinstance(value, list)) or \
             (expected == "object" and isinstance(value, dict))
        if expected and not ok:
            return TurnError("tool.invalid_args", "tool_validation", f"{key} must be {expected}", False)
    return None


def receipt_key(turn_id: str, step: int, call: ToolCall) -> str:
    raw = json.dumps({"turn": turn_id, "step": step, "tool": call.name, "args": call.args}, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def load_receipt(key: str) -> Optional[dict]:
    ensure_schema()
    conn = get_connection()
    try:
        row = conn.execute("SELECT status,result_json,error_code FROM chat_tool_receipts WHERE idempotency_key=?",
                           (key,)).fetchone()
        if not row or row["status"] != "done":
            return None
        try:
            return json.loads(row["result_json"] or "{}")
        except Exception:
            return {}
    finally:
        conn.close()


def store_receipt(key: str, turn_id: str, tool: str, args: dict, result: dict) -> None:
    ensure_schema()
    args_hash = hashlib.sha256(json.dumps(args, sort_keys=True, default=str).encode()).hexdigest()
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO chat_tool_receipts(idempotency_key,turn_id,tool,args_hash,status,result_json,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,datetime('now'),datetime('now')) "
            "ON CONFLICT(idempotency_key) DO UPDATE SET status=excluded.status,result_json=excluded.result_json,"
            "updated_at=excluded.updated_at",
            (key, turn_id, tool, args_hash, "done", json.dumps(result, default=str)[:12000]),
        )
        conn.commit()
    finally:
        conn.close()


def invoke(fn: Callable, call: ToolCall, spec: ToolSpec, turn_id: Optional[str] = None) -> ToolResult:
    key = call.idempotency_key
    args_hash = hashlib.sha256(json.dumps(call.args, sort_keys=True, default=str).encode()).hexdigest()
    if key and spec.risk != "read":
        ensure_schema()
        conn = get_connection()
        try:
            row = conn.execute("SELECT status,result_json,error_code FROM chat_tool_receipts WHERE idempotency_key=?",
                               (key,)).fetchone()
            if row and row["status"] == "done":
                return ToolResult(True, call.name, json.loads(row["result_json"] or "{}"),
                                  receipt_key=key, replayed=True)
            conn.execute("INSERT OR IGNORE INTO chat_tool_receipts "
                         "(idempotency_key,turn_id,tool,args_hash,status,created_at,updated_at) "
                         "VALUES (?,?,?,?,?,datetime('now'),datetime('now'))",
                         (key, turn_id, call.name, args_hash, "running"))
            conn.commit()
        finally:
            conn.close()
    try:
        data = fn(**call.args)
        failed = isinstance(data, dict) and bool(data.get("error"))
        error = TurnError("tool.execution", "tool_execution", str(data.get("error"))[:300], False) if failed else None
    except Exception as exc:
        data = None
        error = TurnError("tool.execution", "tool_execution", "Tool execution failed", False, str(exc)[:300])
    if key and spec.risk != "read":
        conn = get_connection()
        try:
            conn.execute("UPDATE chat_tool_receipts SET status=?,result_json=?,error_code=?,updated_at=datetime('now') "
                         "WHERE idempotency_key=?",
                         ("failed" if error else "done", json.dumps(data, default=str)[:12000],
                          error.code if error else None, key))
            conn.commit()
        finally:
            conn.close()
    return ToolResult(error is None, call.name, data, error, key)

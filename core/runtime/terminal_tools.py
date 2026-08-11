"""Dormant canonical adapter for bounded foreground terminal tools."""
from __future__ import annotations

import copy
import hashlib
import os
import re
from collections.abc import Mapping
from contextvars import ContextVar
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from core.runtime.contracts import (
    PolicyInput,
    RiskLevel,
    RuntimeToolCall,
    RuntimeToolResult,
    SideEffectClass,
    Surface,
    ToolAvailability,
    ToolAvailabilityStatus,
    ToolCatalogEntry,
    RuntimeToolSpec,
)
from core.runtime.policy_facts import apply_legacy_policy_facts, resolve_terminal_mode
from core.runtime.tool_adapters import adapt_legacy_catalog
from core.runtime.tool_catalog import CanonicalToolCatalog
from core.runtime.tool_execution import (
    CanonicalToolExecutor,
    ToolActionReconciliation,
    ToolExecutionBinding,
    ToolExecutionError,
)
from core.runtime.terminal_jobs import (
    MAX_JOB_OUTPUT_CHARS,
    MAX_WAIT_SECONDS,
    TerminalJobLauncher,
    TerminalJobLaunchUnknown,
    TerminalJobError,
    TerminalJobRepository,
    launch_detached_worker,
    new_worker_token,
    terminal_job_id,
)


TERMINAL_NAMESPACE = "tobi.terminal"
TERMINAL_VERSION = "1"
TERMINAL_ACTION_VERSION = "2"
RUN_COMMAND_REF = f"{TERMINAL_NAMESPACE}.run_command@{TERMINAL_VERSION}"
RUN_COMMAND_ACTION_REF = (
    f"{TERMINAL_NAMESPACE}.run_command@{TERMINAL_ACTION_VERSION}"
)
TERMINAL_STATUS_REF = f"{TERMINAL_NAMESPACE}.terminal_status@{TERMINAL_VERSION}"
START_JOB_REF = f"{TERMINAL_NAMESPACE}.start_job@{TERMINAL_VERSION}"
LIST_JOBS_REF = f"{TERMINAL_NAMESPACE}.list_jobs@{TERMINAL_VERSION}"
JOB_OUTPUT_REF = f"{TERMINAL_NAMESPACE}.job_output@{TERMINAL_VERSION}"
CANCEL_JOB_REF = f"{TERMINAL_NAMESPACE}.cancel_job@{TERMINAL_VERSION}"

MAX_COMMAND_LENGTH = 128
MAX_OUTPUT_CHARS = 6_000
MAX_TIMEOUT_S = 30
MAX_ACTION_COMMAND_LENGTH = 70
MAX_ACTION_TIMEOUT_S = 300
JSON_SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"

_ALLOWED_COMMANDS = (
    "Get-Location",
    "date",
    "git --version",
    "hostname",
    "node --version",
    "node -v",
    "pwd",
    "py --version",
    "py -V",
    "python --version",
    "python -V",
    "python3 --version",
    "python3 -V",
    "whoami",
)
_ALLOWED_COMMAND_SET = frozenset(_ALLOWED_COMMANDS)
_COMMAND_PATTERN = "^(?:" + "|".join(re.escape(item) for item in _ALLOWED_COMMANDS) + ")$"
_ACTION_COMMAND_PATTERN = r"^mkdir [A-Za-z0-9][A-Za-z0-9._-]{0,63}$"
_TERMINAL_JOB_ID_PATTERN = r"^terminal-job-[0-9a-f]{32}$"

STATUS_INPUT_SCHEMA = {
    "$schema": JSON_SCHEMA_DIALECT,
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}
STATUS_OUTPUT_SCHEMA = {
    "$schema": JSON_SCHEMA_DIALECT,
    "type": "object",
    "properties": {
        "enabled": {"type": "boolean"},
        "mode": {"type": "string", "enum": ["plan", "ask", "accept", "auto"]},
        "os": {"type": "string", "minLength": 1, "maxLength": 64},
        "shell": {"type": "string", "minLength": 1, "maxLength": 128},
        "package_managers": {
            "type": "array",
            "items": {"type": "string", "minLength": 1, "maxLength": 64},
            "maxItems": 32,
        },
        "tools_registered": {"type": "integer", "minimum": 0},
        "modes": {
            "type": "array",
            "items": {"type": "string", "enum": ["plan", "ask", "accept", "auto"]},
            "minItems": 4,
            "maxItems": 4,
            "uniqueItems": True,
        },
    },
    "required": [
        "enabled",
        "mode",
        "os",
        "shell",
        "package_managers",
        "tools_registered",
        "modes",
    ],
    "additionalProperties": False,
}
RUN_INPUT_SCHEMA = {
    "$schema": JSON_SCHEMA_DIALECT,
    "type": "object",
    "properties": {
        "command": {
            "type": "string",
            "minLength": 1,
            "maxLength": MAX_COMMAND_LENGTH,
            "pattern": _COMMAND_PATTERN,
        },
        "timeout": {
            "type": "integer",
            "minimum": 1,
            "maximum": MAX_TIMEOUT_S,
            "default": MAX_TIMEOUT_S,
        },
    },
    "required": ["command"],
    "additionalProperties": False,
}
RUN_OUTPUT_SCHEMA = {
    "$schema": JSON_SCHEMA_DIALECT,
    "type": "object",
    "properties": {
        "state": {
            "type": "string",
            "enum": ["completed", "timed_out", "failed_to_start"],
        },
        "ok": {"type": "boolean"},
        "exit_code": {"type": ["integer", "null"]},
        "output": {"type": "string", "maxLength": MAX_OUTPUT_CHARS},
        "truncated": {"type": "boolean"},
        "duration_ms": {"type": ["integer", "null"], "minimum": 0},
        "command_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
    },
    "required": [
        "state",
        "ok",
        "exit_code",
        "output",
        "truncated",
        "duration_ms",
        "command_sha256",
    ],
    "additionalProperties": False,
}
ACTION_INPUT_SCHEMA = {
    "$schema": JSON_SCHEMA_DIALECT,
    "type": "object",
    "properties": {
        "command": {
            "type": "string",
            "minLength": 1,
            "maxLength": MAX_ACTION_COMMAND_LENGTH,
            "pattern": _ACTION_COMMAND_PATTERN,
        },
        "timeout": {
            "type": "integer",
            "minimum": 1,
            "maximum": MAX_ACTION_TIMEOUT_S,
            "default": 60,
        },
    },
    "required": ["command"],
    "additionalProperties": False,
}
START_JOB_INPUT_SCHEMA = {
    "$schema": JSON_SCHEMA_DIALECT,
    "type": "object",
    "properties": {
        "duration_s": {
            "type": "integer",
            "minimum": 1,
            "maximum": MAX_WAIT_SECONDS,
        },
    },
    "required": ["duration_s"],
    "additionalProperties": False,
}
START_JOB_OUTPUT_SCHEMA = {
    "$schema": JSON_SCHEMA_DIALECT,
    "type": "object",
    "properties": {
        "job_id": {"type": "string", "pattern": "^terminal-job-[0-9a-f]{32}$"},
        "state": {
            "type": "string",
            "enum": ["running", "succeeded", "failed", "cancelled", "unknown"],
        },
        "duration_s": {"type": "integer", "minimum": 1, "maximum": MAX_WAIT_SECONDS},
        "command_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
    },
    "required": ["job_id", "state", "duration_s", "command_sha256"],
    "additionalProperties": False,
}
_JOB_STATES = [
    "intent",
    "launching",
    "running",
    "succeeded",
    "failed",
    "cancelled",
    "not_started",
    "unknown",
]
_JOB_SUMMARY_PROPERTIES = {
    "job_id": {"type": "string", "pattern": "^terminal-job-[0-9a-f]{32}$"},
    "state": {"type": "string", "enum": _JOB_STATES},
    "duration_s": {"type": "integer", "minimum": 1, "maximum": MAX_WAIT_SECONDS},
    "command_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
    "created_at": {"type": "string", "minLength": 1, "maxLength": 64},
    "started_at": {"type": ["string", "null"], "maxLength": 64},
    "completed_at": {"type": ["string", "null"], "maxLength": 64},
    "exit_code": {"type": ["integer", "null"]},
    "output_chars": {"type": "integer", "minimum": 0, "maximum": MAX_JOB_OUTPUT_CHARS},
    "truncated": {"type": "boolean"},
    "cancellation_requested": {"type": "boolean"},
    "cancellation_acknowledged": {"type": "boolean"},
    "cancel_requested_at": {"type": ["string", "null"], "maxLength": 64},
    "cancel_acknowledged_at": {"type": ["string", "null"], "maxLength": 64},
}
_JOB_SUMMARY_REQUIRED = list(_JOB_SUMMARY_PROPERTIES)
LIST_JOBS_INPUT_SCHEMA = {
    "$schema": JSON_SCHEMA_DIALECT,
    "type": "object",
    "properties": {
        "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20}
    },
    "additionalProperties": False,
}
LIST_JOBS_OUTPUT_SCHEMA = {
    "$schema": JSON_SCHEMA_DIALECT,
    "type": "object",
    "properties": {
        "count": {"type": "integer", "minimum": 0, "maximum": 100},
        "jobs": {
            "type": "array",
            "maxItems": 100,
            "items": {
                "type": "object",
                "properties": copy.deepcopy(_JOB_SUMMARY_PROPERTIES),
                "required": _JOB_SUMMARY_REQUIRED,
                "additionalProperties": False,
            },
        },
    },
    "required": ["count", "jobs"],
    "additionalProperties": False,
}
JOB_OUTPUT_INPUT_SCHEMA = {
    "$schema": JSON_SCHEMA_DIALECT,
    "type": "object",
    "properties": {
        "job_id": {"type": "string", "pattern": "^terminal-job-[0-9a-f]{32}$"},
        "tail": {
            "type": "integer",
            "minimum": 1,
            "maximum": MAX_JOB_OUTPUT_CHARS,
            "default": MAX_JOB_OUTPUT_CHARS,
        },
    },
    "required": ["job_id"],
    "additionalProperties": False,
}
JOB_OUTPUT_OUTPUT_SCHEMA = {
    "$schema": JSON_SCHEMA_DIALECT,
    "type": "object",
    "properties": {
        **copy.deepcopy(_JOB_SUMMARY_PROPERTIES),
        "output": {"type": "string", "maxLength": MAX_JOB_OUTPUT_CHARS},
    },
    "required": [*_JOB_SUMMARY_REQUIRED, "output"],
    "additionalProperties": False,
}
CANCEL_JOB_INPUT_SCHEMA = {
    "$schema": JSON_SCHEMA_DIALECT,
    "type": "object",
    "properties": {
        "job_id": {"type": "string", "pattern": "^terminal-job-[0-9a-f]{32}$"}
    },
    "required": ["job_id"],
    "additionalProperties": False,
}
CANCEL_JOB_OUTPUT_SCHEMA = {
    "$schema": JSON_SCHEMA_DIALECT,
    "type": "object",
    "properties": {
        "job_id": {"type": "string", "pattern": "^terminal-job-[0-9a-f]{32}$"},
        "request_state": {
            "type": "string",
            "enum": ["requested", "already_requested", "already_inactive"],
        },
        "state": {"type": "string", "enum": _JOB_STATES},
        "cancellation_requested": {"type": "boolean"},
        "cancellation_acknowledged": {"type": "boolean"},
    },
    "required": [
        "job_id",
        "request_state",
        "state",
        "cancellation_requested",
        "cancellation_acknowledged",
    ],
    "additionalProperties": False,
}

_TERMINAL_JOB_CALL: ContextVar[RuntimeToolCall | None] = ContextVar(
    "terminal_job_call", default=None
)
_TERMINAL_JOB_OWNER: ContextVar[str | None] = ContextVar(
    "terminal_job_owner", default=None
)


class TerminalToolEngine(Protocol):
    """Existing terminal-engine operations used by the dormant adapter."""

    def status(self) -> dict[str, Any]: ...

    def effective_mode(self, surface: str = "mc") -> str: ...

    def gate(
        self, command: str, surface: str = "mc", use_llm: bool = False
    ) -> dict[str, Any]: ...

    def run(self, command: str, **kwargs: Any) -> dict[str, Any]: ...

    def redact(self, text: str) -> str: ...


def _command_digest(command: str) -> str:
    return hashlib.sha256(command.encode("utf-8")).hexdigest()


def _command_target(arguments: Mapping[str, Any]) -> str:
    return f"terminal:inspect:sha256:{_command_digest(arguments['command'])}"


def _command_evidence(output: Any) -> tuple[str, ...]:
    return (f"terminal:command:sha256:{output['command_sha256']}",)


def _require_allowed_command(command: str) -> str:
    if not isinstance(command, str) or command not in _ALLOWED_COMMAND_SET:
        raise ToolExecutionError("tool.terminal_command_denied")
    return command


def _require_mutable_command(command: str) -> str:
    if (
        not isinstance(command, str)
        or len(command) > MAX_ACTION_COMMAND_LENGTH
        or re.fullmatch(_ACTION_COMMAND_PATTERN, command) is None
    ):
        raise ToolExecutionError("tool.terminal_action_command_denied")
    return command


def _directory_digest(directory: Path) -> str:
    return hashlib.sha256(str(directory.resolve()).encode("utf-8")).hexdigest()


def _action_target(arguments: Mapping[str, Any], directory: Path) -> str:
    command = _require_mutable_command(arguments["command"])
    return (
        f"terminal:action:cwd-sha256:{_directory_digest(directory)}:"
        f"command-sha256:{_command_digest(command)}"
    )


def _action_arguments_for_persistence(
    arguments: Mapping[str, Any],
) -> Mapping[str, Any]:
    command = _require_mutable_command(arguments["command"])
    return {
        "command": "[REDACTED]",
        "command_sha256": _command_digest(command),
        "command_chars": len(command),
        "timeout": int(arguments.get("timeout", 60)),
    }


def _action_effect_summary(arguments: Mapping[str, Any], output: Any) -> str:
    command = _require_mutable_command(arguments["command"])
    state = output.get("state") if isinstance(output, Mapping) else "unknown"
    exit_code = output.get("exit_code") if isinstance(output, Mapping) else None
    return (
        f"Approved foreground command {_command_digest(command)} finished with "
        f"state {state} and exit code {exit_code}"
    )


def _action_reconciliation(arguments: Mapping[str, Any]) -> ToolActionReconciliation:
    command = _require_mutable_command(arguments["command"])
    return ToolActionReconciliation(
        outcome="unknown",
        summary="A generic foreground command has no universal read-only effect proof",
        evidence_refs=(f"terminal:command:sha256:{_command_digest(command)}",),
    )


def _wait_duration(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ToolExecutionError("tool.terminal_job_duration_denied")
    if value < 1 or value > MAX_WAIT_SECONDS:
        raise ToolExecutionError("tool.terminal_job_duration_denied")
    return value


def _wait_command(duration_s: int) -> str:
    return f"wait {_wait_duration(duration_s)}"


def terminal_job_target(
    duration_s: int, working_directory: str | os.PathLike[str]
) -> str:
    command = _wait_command(duration_s)
    directory = Path(working_directory).resolve()
    return (
        f"terminal:job-start:cwd-sha256:{_directory_digest(directory)}:"
        f"command-sha256:{_command_digest(command)}"
    )


def _require_terminal_job_id(value: Any) -> str:
    if not isinstance(value, str) or re.fullmatch(_TERMINAL_JOB_ID_PATTERN, value) is None:
        raise ToolExecutionError("tool.terminal_job_id_invalid")
    return value


def terminal_job_cancel_target(job_id: str) -> str:
    return f"terminal:job:{_require_terminal_job_id(job_id)}:cancel"


def _current_terminal_job_call(expected_ref: str) -> RuntimeToolCall:
    call = _TERMINAL_JOB_CALL.get()
    if call is None or call.tool_ref != expected_ref:
        raise ToolExecutionError("tool.terminal_job_context_missing")
    return call


def _current_terminal_job_owner() -> str:
    owner_id = _TERMINAL_JOB_OWNER.get()
    if not isinstance(owner_id, str) or not owner_id.strip():
        raise ToolExecutionError("tool.terminal_job_owner_missing")
    return owner_id


def _start_job_output(job: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "job_id": job["job_id"],
        "state": job["state"],
        "duration_s": int(job["duration_s"]),
        "command_sha256": job["command_sha256"],
    }


def _start_job_arguments_for_persistence(
    arguments: Mapping[str, Any],
) -> Mapping[str, Any]:
    duration_s = _wait_duration(arguments["duration_s"])
    command = _wait_command(duration_s)
    return {
        "operation": "wait",
        "command_sha256": _command_digest(command),
        "duration_s": duration_s,
    }


def _start_job_effect_summary(
    _arguments: Mapping[str, Any], output: Any
) -> str:
    return (
        f"Managed terminal job {output['job_id']} accepted with state "
        f"{output['state']}"
    )


def _start_job_evidence(output: Any) -> tuple[str, ...]:
    return (f"terminal:job:{output['job_id']}",)


def _cancel_job_output(job: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "job_id": job["job_id"],
        "request_state": job["request_state"],
        "state": job["state"],
        "cancellation_requested": bool(job["cancellation_requested"]),
        "cancellation_acknowledged": bool(job["cancellation_acknowledged"]),
    }


def _cancel_job_arguments_for_persistence(
    arguments: Mapping[str, Any],
) -> Mapping[str, Any]:
    return {"job_id": _require_terminal_job_id(arguments["job_id"])}


def _cancel_job_effect_summary(
    _arguments: Mapping[str, Any], output: Any
) -> str:
    return (
        f"Managed terminal job {output['job_id']} cancellation request finished with "
        f"request state {output['request_state']}"
    )


def _cancel_job_evidence(output: Any) -> tuple[str, ...]:
    return (f"terminal:job:{output['job_id']}:cancel-request",)


class _TerminalJobAdapter:
    def __init__(
        self,
        repository: TerminalJobRepository,
        launcher: TerminalJobLauncher,
        working_directory: Path,
        *,
        handshake_timeout_s: float,
        poll_interval_s: float,
    ) -> None:
        self._repository = repository
        self._launcher = launcher
        self._working_directory = working_directory
        self._handshake_timeout_s = handshake_timeout_s
        self._poll_interval_s = poll_interval_s

    def start_job(self, duration_s: int) -> dict[str, Any]:
        call = _current_terminal_job_call(START_JOB_REF)
        duration_s = _wait_duration(duration_s)
        command = _wait_command(duration_s)
        target = terminal_job_target(duration_s, self._working_directory)
        job_id = terminal_job_id(call)
        worker_token = new_worker_token()
        try:
            self._repository.create_intent(
                call,
                target=target,
                command_sha256=_command_digest(command),
                working_directory_sha256=_directory_digest(self._working_directory),
                duration_s=duration_s,
            )
            self._repository.mark_launching(job_id, worker_token)
        except Exception:
            return {"error": "managed job intent was not safely prepared"}

        try:
            self._launcher(job_id, worker_token)
        except Exception:
            try:
                self._repository.mark_not_started(job_id, worker_token)
            except Exception:
                pass
            return {"error": "managed worker did not start"}

        row = self._repository.wait_for_worker(
            job_id,
            worker_token,
            timeout_s=self._handshake_timeout_s,
            poll_interval_s=self._poll_interval_s,
        )
        if row is None:
            raise TerminalJobLaunchUnknown(
                "managed worker launch returned without trustworthy handshake"
            )
        return _start_job_output(self._repository.get_job(job_id))

    def list_jobs(self, limit: int = 20) -> dict[str, Any]:
        return self._repository.list_jobs(limit=limit)

    def job_output(
        self, job_id: str, tail: int = MAX_JOB_OUTPUT_CHARS
    ) -> dict[str, Any]:
        return self._repository.get_job(job_id, tail=tail)

    def cancel_job(self, job_id: str) -> dict[str, Any]:
        call = _current_terminal_job_call(CANCEL_JOB_REF)
        row = self._repository.request_cancellation(
            call,
            job_id=_require_terminal_job_id(job_id),
            owner_id=_current_terminal_job_owner(),
        )
        return _cancel_job_output(row)

    def reconcile_start(
        self, _arguments: Mapping[str, Any]
    ) -> ToolActionReconciliation:
        call = _current_terminal_job_call(START_JOB_REF)
        job_id = terminal_job_id(call)
        outcome, evidence = self._repository.start_evidence(job_id)
        evidence_refs = (f"terminal:job:{job_id}",)
        if outcome == "applied" and evidence is not None:
            return ToolActionReconciliation(
                outcome="applied",
                summary="The authenticated managed worker claimed this job",
                evidence_refs=evidence_refs,
                output=_start_job_output(evidence),
            )
        if outcome == "not_applied":
            return ToolActionReconciliation(
                outcome="not_applied",
                summary="No authenticated managed worker claimed this job",
                evidence_refs=evidence_refs,
            )
        return ToolActionReconciliation(
            outcome="unknown",
            summary="The managed launch has no trustworthy worker proof yet",
            evidence_refs=evidence_refs,
        )

    def reconcile_cancel(
        self, arguments: Mapping[str, Any]
    ) -> ToolActionReconciliation:
        call = _current_terminal_job_call(CANCEL_JOB_REF)
        job_id = _require_terminal_job_id(arguments["job_id"])
        try:
            outcome, evidence = self._repository.cancel_evidence(
                job_id, call.idempotency_key or ""
            )
        except Exception:
            return ToolActionReconciliation(
                outcome="unknown",
                summary="The managed cancellation request cannot yet be verified",
                evidence_refs=(f"terminal:job:{job_id}:cancel-request",),
            )
        evidence_refs = (f"terminal:job:{job_id}:cancel-request",)
        if outcome == "applied" and evidence is not None:
            return ToolActionReconciliation(
                outcome="applied",
                summary="The matching managed cancellation request is durable",
                evidence_refs=evidence_refs,
                output=_cancel_job_output(evidence),
            )
        return ToolActionReconciliation(
            outcome="not_applied",
            summary="No matching managed cancellation request was stored",
            evidence_refs=evidence_refs,
        )


def _bounded_redaction(engine: TerminalToolEngine, value: Any) -> tuple[str, bool]:
    text = str(value or "")
    try:
        redacted = engine.redact(text)
    except Exception:
        redacted = "[REDACTED]"
    redacted = str(redacted)
    truncated = len(redacted) > MAX_OUTPUT_CHARS
    return redacted[-MAX_OUTPUT_CHARS:], truncated


class _TerminalAdapter:
    def __init__(self, engine: TerminalToolEngine, working_directory: Path) -> None:
        self._engine = engine
        self._working_directory = working_directory

    def status(self) -> dict[str, Any]:
        raw = self._engine.status()
        if not isinstance(raw, Mapping):
            raise ToolExecutionError("tool.terminal_status_invalid")
        managers = raw.get("package_managers")
        modes = raw.get("modes")
        if not isinstance(managers, list) or not isinstance(modes, list):
            raise ToolExecutionError("tool.terminal_status_invalid")
        return {
            "enabled": raw.get("enabled"),
            "mode": raw.get("mode"),
            "os": raw.get("os"),
            "shell": raw.get("shell"),
            "package_managers": copy.deepcopy(managers),
            "tools_registered": raw.get("tools_registered"),
            "modes": copy.deepcopy(modes),
        }

    def run_command(self, command: str, timeout: int = MAX_TIMEOUT_S) -> dict[str, Any]:
        command = _require_allowed_command(command)
        gate = self._engine.gate(command, surface="mc", use_llm=False)
        if not isinstance(gate, Mapping):
            return {"error": "terminal safety gate did not return a decision"}
        if gate.get("decision") != "run" or gate.get("risk") != "low":
            return {"error": "terminal safety gate changed before execution"}

        raw = self._engine.run(
            command,
            cwd=str(self._working_directory),
            timeout=timeout,
            background=False,
            risk="low",
            mode=str(gate.get("mode") or "ask"),
            surface="mc",
        )
        if not isinstance(raw, Mapping):
            raw = {}

        exit_code = raw.get("exit_code")
        if isinstance(exit_code, bool) or not isinstance(exit_code, int):
            exit_code = None
        if raw.get("timed_out") is True:
            state = "timed_out"
            output = "Command timed out before returning a result."
        elif exit_code is not None:
            state = "completed"
            output = raw.get("output") or "(no output)"
        else:
            state = "failed_to_start"
            output = "The local shell could not start this inspection command."

        bounded_output, bounded = _bounded_redaction(self._engine, output)
        duration_ms = raw.get("duration_ms")
        if (
            isinstance(duration_ms, bool)
            or not isinstance(duration_ms, int)
            or duration_ms < 0
        ):
            duration_ms = None
        return {
            "state": state,
            "ok": state == "completed" and exit_code == 0,
            "exit_code": exit_code,
            "output": bounded_output,
            "truncated": bool(raw.get("truncated")) or bounded,
            "duration_ms": duration_ms,
            "command_sha256": _command_digest(command),
        }

    def run_action(self, command: str, timeout: int = 60) -> dict[str, Any]:
        command = _require_mutable_command(command)
        gate = self._engine.gate(command, surface="mc", use_llm=False)
        if not isinstance(gate, Mapping):
            return {"error": "terminal safety gate did not return a decision"}
        if gate.get("decision") not in {"run", "confirm"} or gate.get("risk") not in {
            "medium",
            "high",
        }:
            return {"error": "terminal safety gate changed before execution"}

        raw = self._engine.run(
            command,
            cwd=str(self._working_directory),
            timeout=timeout,
            background=False,
            risk=str(gate.get("risk")),
            mode=str(gate.get("mode") or "ask"),
            surface="mc",
        )
        if not isinstance(raw, Mapping):
            raw = {}

        exit_code = raw.get("exit_code")
        if isinstance(exit_code, bool) or not isinstance(exit_code, int):
            exit_code = None
        if raw.get("timed_out") is True:
            state = "timed_out"
            output = "Command timed out before returning a result."
        elif exit_code is not None:
            state = "completed"
            output = raw.get("output") or "(no output)"
        else:
            state = "failed_to_start"
            output = "The local shell could not start this approved command."

        bounded_output, bounded = _bounded_redaction(self._engine, output)
        duration_ms = raw.get("duration_ms")
        if (
            isinstance(duration_ms, bool)
            or not isinstance(duration_ms, int)
            or duration_ms < 0
        ):
            duration_ms = None
        return {
            "state": state,
            "ok": state == "completed" and exit_code == 0,
            "exit_code": exit_code,
            "output": bounded_output,
            "truncated": bool(raw.get("truncated")) or bounded,
            "duration_ms": duration_ms,
            "command_sha256": _command_digest(command),
        }


def _availability(spec, reason_code: str) -> ToolAvailability:
    return ToolAvailability(
        tool_ref=spec.ref,
        status=ToolAvailabilityStatus.AVAILABLE,
        reason_codes=(reason_code,),
    )


def _promote(entry: ToolCatalogEntry) -> ToolCatalogEntry:
    if entry.spec.name == "terminal_status":
        spec = replace(
            entry.spec,
            description="Read bounded local terminal safety and capability status.",
            input_schema=copy.deepcopy(STATUS_INPUT_SCHEMA),
            output_schema=copy.deepcopy(STATUS_OUTPUT_SCHEMA),
            side_effect_class=SideEffectClass.NONE,
            risk=RiskLevel.NONE,
            allowed_modes=("chat", "agent"),
            allowed_surfaces=(Surface.CHAT, Surface.AGENT),
            required_permissions=("terminal.read",),
            required_integrations=(),
            timeout_s=30,
            retry_policy="none",
            idempotency_policy="none",
            isolation="in_process",
            audit_policy="terminal_status_read",
            adapter="terminal_runtime_v2",
        )
        reason = "terminal.migration_run3a_status"
    elif entry.spec.name == "run_command":
        spec = replace(
            entry.spec,
            description="Run one allowlisted read-only foreground inspection command.",
            input_schema=copy.deepcopy(RUN_INPUT_SCHEMA),
            output_schema=copy.deepcopy(RUN_OUTPUT_SCHEMA),
            side_effect_class=SideEffectClass.NONE,
            risk=RiskLevel.LOW,
            allowed_modes=("agent",),
            allowed_surfaces=(Surface.AGENT,),
            required_permissions=("terminal.execute",),
            required_integrations=(),
            timeout_s=MAX_TIMEOUT_S,
            retry_policy="none",
            idempotency_policy="none",
            isolation="subprocess",
            audit_policy="terminal_inspection_read",
            adapter="terminal_runtime_v2",
        )
        reason = "terminal.migration_run3a_command"
    else:
        raise ToolExecutionError("tool.terminal_source_unexpected")
    return ToolCatalogEntry(
        source_key=entry.source_key,
        spec=spec,
        availability=_availability(spec, reason),
    )


def _promote_action(entry: ToolCatalogEntry) -> ToolCatalogEntry:
    if entry.spec.name != "run_command":
        raise ToolExecutionError("tool.terminal_action_source_unexpected")
    spec = replace(
        entry.spec,
        version=TERMINAL_ACTION_VERSION,
        description="Run one approved bounded local foreground mutation.",
        input_schema=copy.deepcopy(ACTION_INPUT_SCHEMA),
        output_schema=copy.deepcopy(RUN_OUTPUT_SCHEMA),
        side_effect_class=SideEffectClass.IRREVERSIBLE,
        risk=RiskLevel.HIGH,
        allowed_modes=("agent",),
        allowed_surfaces=(Surface.AGENT,),
        required_permissions=("terminal.execute",),
        required_integrations=(),
        timeout_s=MAX_ACTION_TIMEOUT_S,
        retry_policy="none",
        idempotency_policy="required",
        isolation="subprocess",
        audit_policy="terminal_foreground_action",
        adapter="terminal_runtime_v2",
    )
    return ToolCatalogEntry(
        source_key=f"{entry.source_key}:action-v2",
        spec=spec,
        availability=_availability(spec, "terminal.migration_run3b1_action"),
    )


def _with_denial(policy_input: PolicyInput, reason: str) -> PolicyInput:
    denials = (*policy_input.compatibility_denials, reason)
    return replace(policy_input, compatibility_denials=tuple(dict.fromkeys(denials)))


@dataclass(frozen=True)
class TerminalToolRuntime:
    catalog: CanonicalToolCatalog
    executor: CanonicalToolExecutor
    _engine: TerminalToolEngine

    def execute(
        self,
        call: RuntimeToolCall,
        policy_input: PolicyInput,
        *,
        worker_id: str,
        lease_token: str,
        lease_epoch: int,
        now: datetime | None = None,
    ) -> RuntimeToolResult:
        """Apply current terminal facts before the canonical execution boundary."""
        if call.tool_ref in {RUN_COMMAND_REF, RUN_COMMAND_ACTION_REF}:
            arguments = self.catalog.validate_arguments(
                call.tool_ref, call.validated_arguments
            )
            action = call.tool_ref == RUN_COMMAND_ACTION_REF
            command = (
                _require_mutable_command(arguments["command"])
                if action
                else _require_allowed_command(arguments["command"])
            )
            if action and not call.idempotency_key:
                raise ToolExecutionError("tool.idempotency_key_required")
            try:
                effective_mode = self._engine.effective_mode(surface="mc")
            except Exception:
                effective_mode = "unknown"
            policy_input = apply_legacy_policy_facts(
                policy_input, resolve_terminal_mode(effective_mode)
            )
            try:
                gate = self._engine.gate(command, surface="mc", use_llm=False)
            except Exception:
                gate = {}
            decision = gate.get("decision") if isinstance(gate, Mapping) else None
            risk = gate.get("risk") if isinstance(gate, Mapping) else None
            allowed_decisions = {"run", "confirm"} if action else {"run"}
            allowed_risks = {"medium", "high"} if action else {"low"}
            if decision not in allowed_decisions:
                safe_decision = decision if decision in {"confirm", "plan", "refuse"} else "unknown"
                policy_input = _with_denial(
                    policy_input, f"compatibility.terminal.gate_{safe_decision}"
                )
            if risk not in allowed_risks:
                policy_input = _with_denial(
                    policy_input,
                    (
                        "compatibility.terminal.risk_not_mutation"
                        if action
                        else "compatibility.terminal.risk_not_low"
                    ),
                )
        return self.executor.execute(
            call,
            policy_input,
            worker_id=worker_id,
            lease_token=lease_token,
            lease_epoch=lease_epoch,
            now=now,
        )


def build_terminal_tool_runtime(
    *,
    engine: TerminalToolEngine | None = None,
    working_directory: str | os.PathLike[str] | None = None,
    control: Any = None,
) -> TerminalToolRuntime:
    """Build an isolated three-contract runtime without registering a live caller."""
    from core import conductor_registry

    if engine is None:
        from core import terminal_engine

        engine = terminal_engine
    for name in ("status", "effective_mode", "gate", "run", "redact"):
        if not callable(getattr(engine, name, None)):
            raise ToolExecutionError("tool.terminal_engine_invalid")

    directory = Path(working_directory or os.getcwd()).resolve()
    if not directory.is_dir():
        raise ToolExecutionError("tool.terminal_working_directory_invalid")

    adapted = adapt_legacy_catalog(
        {
            "terminal_status": conductor_registry.TOOL_SPECS["terminal_status"],
            "run_command": conductor_registry.TOOL_SPECS["run_command"],
        },
        namespace=TERMINAL_NAMESPACE,
        version=TERMINAL_VERSION,
    )
    if adapted.issues or len(adapted.entries) != 2:
        raise ToolExecutionError("tool.terminal_catalog_invalid")
    promoted = tuple(_promote(entry) for entry in adapted.entries)
    run_source = next(
        entry for entry in adapted.entries if entry.spec.name == "run_command"
    )
    entries = (*promoted, _promote_action(run_source))
    catalog = CanonicalToolCatalog(entries)
    adapter = _TerminalAdapter(engine, directory)
    executor = CanonicalToolExecutor(
        catalog,
        (
            ToolExecutionBinding(
                tool_ref=RUN_COMMAND_REF,
                invoke=adapter.run_command,
                target_from_arguments=_command_target,
                read_failure_owner_message=(
                    "TOBI did not run that inspection command because a terminal safety "
                    "check or the local shell blocked it."
                ),
                evidence_refs=_command_evidence,
            ),
            ToolExecutionBinding(
                tool_ref=RUN_COMMAND_ACTION_REF,
                invoke=adapter.run_action,
                target_from_arguments=lambda arguments: _action_target(
                    arguments, directory
                ),
                effect_summary=_action_effect_summary,
                evidence_refs=_command_evidence,
                action_arguments_for_persistence=_action_arguments_for_persistence,
                action_reconciliation=_action_reconciliation,
                action_not_applied_owner_message=(
                    "TOBI did not run that approved terminal command because the final "
                    "safety check refused it."
                ),
                action_not_applied_summary=(
                    "The final terminal safety check refused the command before invocation"
                ),
                reported_error_is_not_applied=True,
            ),
            ToolExecutionBinding(
                tool_ref=TERMINAL_STATUS_REF,
                invoke=adapter.status,
                target_from_arguments=lambda _arguments: "terminal:status",
                read_failure_owner_message="TOBI could not read the local terminal status.",
                evidence_refs=lambda _output: ("terminal:status",),
            ),
        ),
        control=control,
    )
    return TerminalToolRuntime(catalog=catalog, executor=executor, _engine=engine)


def _promote_job_entry(entry: ToolCatalogEntry, kind: str) -> ToolCatalogEntry:
    common = {
        "version": TERMINAL_VERSION,
        "allowed_modes": ("agent",),
        "allowed_surfaces": (Surface.AGENT,),
        "required_integrations": (),
        "retry_policy": "none",
        "adapter": "terminal_job_runtime_v2",
    }
    spec: RuntimeToolSpec
    if kind == "start":
        spec = replace(
            entry.spec,
            **common,
            name="start_job",
            description="Start one approved bounded managed wait job.",
            input_schema=copy.deepcopy(START_JOB_INPUT_SCHEMA),
            output_schema=copy.deepcopy(START_JOB_OUTPUT_SCHEMA),
            side_effect_class=SideEffectClass.REVERSIBLE,
            risk=RiskLevel.HIGH,
            required_permissions=("terminal.execute",),
            timeout_s=10,
            idempotency_policy="required",
            isolation="subprocess",
            audit_policy="terminal_managed_job_start",
        )
        reason = "terminal.migration_run3b2a_start"
    elif kind == "list":
        spec = replace(
            entry.spec,
            **common,
            description="List bounded canonical managed terminal job summaries.",
            input_schema=copy.deepcopy(LIST_JOBS_INPUT_SCHEMA),
            output_schema=copy.deepcopy(LIST_JOBS_OUTPUT_SCHEMA),
            side_effect_class=SideEffectClass.NONE,
            risk=RiskLevel.NONE,
            required_permissions=("terminal.read",),
            timeout_s=30,
            idempotency_policy="none",
            isolation="in_process",
            audit_policy="terminal_managed_job_list",
        )
        reason = "terminal.migration_run3b2a_list"
    elif kind == "output":
        spec = replace(
            entry.spec,
            **common,
            description="Read bounded redacted output for one canonical managed terminal job.",
            input_schema=copy.deepcopy(JOB_OUTPUT_INPUT_SCHEMA),
            output_schema=copy.deepcopy(JOB_OUTPUT_OUTPUT_SCHEMA),
            side_effect_class=SideEffectClass.NONE,
            risk=RiskLevel.NONE,
            required_permissions=("terminal.read",),
            timeout_s=30,
            idempotency_policy="none",
            isolation="in_process",
            audit_policy="terminal_managed_job_output",
        )
        reason = "terminal.migration_run3b2a_output"
    elif kind == "cancel":
        spec = replace(
            entry.spec,
            **common,
            name="cancel_job",
            description="Request approved cancellation of one managed terminal job.",
            input_schema=copy.deepcopy(CANCEL_JOB_INPUT_SCHEMA),
            output_schema=copy.deepcopy(CANCEL_JOB_OUTPUT_SCHEMA),
            side_effect_class=SideEffectClass.IRREVERSIBLE,
            risk=RiskLevel.HIGH,
            required_permissions=("terminal.execute",),
            timeout_s=10,
            idempotency_policy="required",
            isolation="in_process",
            audit_policy="terminal_managed_job_cancel",
        )
        reason = "terminal.migration_run3b2b_cancel"
    else:
        raise ToolExecutionError("tool.terminal_job_source_unexpected")
    return ToolCatalogEntry(
        source_key=f"{entry.source_key}:managed-{kind}",
        spec=spec,
        availability=_availability(spec, reason),
    )


@dataclass(frozen=True)
class TerminalJobToolRuntime:
    catalog: CanonicalToolCatalog
    executor: CanonicalToolExecutor
    _engine: Any
    _jobs: TerminalJobRepository

    def execute(
        self,
        call: RuntimeToolCall,
        policy_input: PolicyInput,
        *,
        worker_id: str,
        lease_token: str,
        lease_epoch: int,
        now: datetime | None = None,
    ) -> RuntimeToolResult:
        if call.tool_ref == START_JOB_REF:
            arguments = self.catalog.validate_arguments(
                call.tool_ref, call.validated_arguments
            )
            _wait_duration(arguments["duration_s"])
            if not call.idempotency_key:
                raise ToolExecutionError("tool.idempotency_key_required")
            try:
                effective_mode = self._engine.effective_mode(surface="mc")
            except Exception:
                effective_mode = "unknown"
            policy_input = apply_legacy_policy_facts(
                policy_input, resolve_terminal_mode(effective_mode)
            )
            try:
                status = self._engine.status()
            except Exception:
                status = {}
            if not isinstance(status, Mapping) or status.get("enabled") is not True:
                policy_input = _with_denial(
                    policy_input, "compatibility.terminal.disabled_or_unknown"
                )
        elif call.tool_ref == CANCEL_JOB_REF:
            arguments = self.catalog.validate_arguments(
                call.tool_ref, call.validated_arguments
            )
            job_id = _require_terminal_job_id(arguments["job_id"])
            if not call.idempotency_key:
                raise ToolExecutionError("tool.idempotency_key_required")
            try:
                self._jobs.require_owner(job_id, policy_input.owner_id)
            except TerminalJobError:
                raise ToolExecutionError("tool.terminal_job_unavailable") from None
        call_token = _TERMINAL_JOB_CALL.set(call)
        owner_token = _TERMINAL_JOB_OWNER.set(policy_input.owner_id)
        try:
            return self.executor.execute(
                call,
                policy_input,
                worker_id=worker_id,
                lease_token=lease_token,
                lease_epoch=lease_epoch,
                now=now,
            )
        finally:
            _TERMINAL_JOB_OWNER.reset(owner_token)
            _TERMINAL_JOB_CALL.reset(call_token)

    def reconcile_action(
        self,
        call: RuntimeToolCall,
        *,
        actor: str,
        now: datetime | None = None,
    ) -> RuntimeToolResult:
        token = _TERMINAL_JOB_CALL.set(call)
        try:
            return self.executor.reconcile_action(call, actor=actor, now=now)
        finally:
            _TERMINAL_JOB_CALL.reset(token)


def build_terminal_job_runtime(
    *,
    engine: Any = None,
    job_repository: TerminalJobRepository | None = None,
    launcher: TerminalJobLauncher | None = None,
    working_directory: str | os.PathLike[str] | None = None,
    handshake_timeout_s: float = 5.0,
    poll_interval_s: float = 0.05,
    control: Any = None,
) -> TerminalJobToolRuntime:
    """Build isolated managed-job bindings without registering a live caller."""
    from core import conductor_registry

    if engine is None:
        from core import terminal_engine

        engine = terminal_engine
    for name in ("effective_mode", "status"):
        if not callable(getattr(engine, name, None)):
            raise ToolExecutionError("tool.terminal_engine_invalid")
    if handshake_timeout_s <= 0 or poll_interval_s <= 0:
        raise ToolExecutionError("tool.terminal_job_timing_invalid")

    directory = Path(working_directory or os.getcwd()).resolve()
    if not directory.is_dir():
        raise ToolExecutionError("tool.terminal_working_directory_invalid")
    jobs = job_repository or TerminalJobRepository()
    if not isinstance(jobs, TerminalJobRepository):
        raise ToolExecutionError("tool.terminal_job_repository_invalid")

    adapted = adapt_legacy_catalog(
        {
            "run_command": conductor_registry.TOOL_SPECS["run_command"],
            "list_jobs": conductor_registry.TOOL_SPECS["list_jobs"],
            "job_output": conductor_registry.TOOL_SPECS["job_output"],
            "kill_job": conductor_registry.TOOL_SPECS["kill_job"],
        },
        namespace=TERMINAL_NAMESPACE,
        version=TERMINAL_VERSION,
    )
    if adapted.issues or len(adapted.entries) != 4:
        raise ToolExecutionError("tool.terminal_job_catalog_invalid")
    sources = {entry.spec.name: entry for entry in adapted.entries}
    entries = (
        _promote_job_entry(sources["run_command"], "start"),
        _promote_job_entry(sources["list_jobs"], "list"),
        _promote_job_entry(sources["job_output"], "output"),
        _promote_job_entry(sources["kill_job"], "cancel"),
    )
    catalog = CanonicalToolCatalog(entries)

    if launcher is None:
        def managed_launcher(job_id: str, worker_token: str) -> None:
            launch_detached_worker(
                job_id, worker_token, working_directory=directory
            )

        launcher = managed_launcher
    adapter = _TerminalJobAdapter(
        jobs,
        launcher,
        directory,
        handshake_timeout_s=handshake_timeout_s,
        poll_interval_s=poll_interval_s,
    )
    executor = CanonicalToolExecutor(
        catalog,
        (
            ToolExecutionBinding(
                tool_ref=START_JOB_REF,
                invoke=adapter.start_job,
                target_from_arguments=lambda arguments: terminal_job_target(
                    arguments["duration_s"], directory
                ),
                effect_summary=_start_job_effect_summary,
                external_ref=lambda output: f"terminal:job:{output['job_id']}",
                evidence_refs=_start_job_evidence,
                action_arguments_for_persistence=_start_job_arguments_for_persistence,
                action_reconciliation=adapter.reconcile_start,
                action_not_applied_owner_message=(
                    "TOBI did not start that managed terminal job. It is safe to retry."
                ),
                action_not_applied_summary=(
                    "The managed worker was proven not to have started"
                ),
                reported_error_is_not_applied=True,
            ),
            ToolExecutionBinding(
                tool_ref=LIST_JOBS_REF,
                invoke=adapter.list_jobs,
                target_from_arguments=lambda _arguments: "terminal:jobs",
                read_failure_owner_message="TOBI could not list managed terminal jobs.",
                evidence_refs=lambda _output: ("terminal:jobs",),
            ),
            ToolExecutionBinding(
                tool_ref=JOB_OUTPUT_REF,
                invoke=adapter.job_output,
                target_from_arguments=lambda arguments: (
                    f"terminal:job:{arguments['job_id']}"
                ),
                read_failure_owner_message="TOBI could not read that managed job output.",
                evidence_refs=lambda output: (f"terminal:job:{output['job_id']}",),
            ),
            ToolExecutionBinding(
                tool_ref=CANCEL_JOB_REF,
                invoke=adapter.cancel_job,
                target_from_arguments=lambda arguments: terminal_job_cancel_target(
                    arguments["job_id"]
                ),
                effect_summary=_cancel_job_effect_summary,
                external_ref=lambda output: (
                    f"terminal:job:{output['job_id']}:cancel-request"
                ),
                evidence_refs=_cancel_job_evidence,
                action_arguments_for_persistence=_cancel_job_arguments_for_persistence,
                action_reconciliation=adapter.reconcile_cancel,
                action_not_applied_owner_message=(
                    "TOBI did not store that managed job cancellation request. "
                    "It is safe to retry."
                ),
                action_not_applied_summary=(
                    "No matching managed job cancellation request was stored"
                ),
            ),
        ),
        control=control,
    )
    return TerminalJobToolRuntime(
        catalog=catalog, executor=executor, _engine=engine, _jobs=jobs
    )

"""Dormant canonical adapter for bounded foreground terminal tools."""
from __future__ import annotations

import copy
import hashlib
import os
import re
from collections.abc import Mapping
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


TERMINAL_NAMESPACE = "tobi.terminal"
TERMINAL_VERSION = "1"
TERMINAL_ACTION_VERSION = "2"
RUN_COMMAND_REF = f"{TERMINAL_NAMESPACE}.run_command@{TERMINAL_VERSION}"
RUN_COMMAND_ACTION_REF = (
    f"{TERMINAL_NAMESPACE}.run_command@{TERMINAL_ACTION_VERSION}"
)
TERMINAL_STATUS_REF = f"{TERMINAL_NAMESPACE}.terminal_status@{TERMINAL_VERSION}"

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

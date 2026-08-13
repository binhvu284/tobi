"""Compatibility handling for persisted Conductor recovery checkpoints."""

from __future__ import annotations

import json
from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CheckpointRecoveryOutcome:
    """Changes Conductor applies after handling one persisted recovery command."""

    messages: tuple[dict[str, Any], ...] = ()
    tools_used: tuple[str, ...] = ()
    completed_actions: tuple[str, ...] = ()
    turn_response: dict[str, Any] | None = None


def apply_recovery_checkpoint(
    checkpoint: Mapping[str, Any] | None,
    *,
    chat_id: int,
    surface: str,
    intent: str,
    mode: str,
    review_mode: str,
    denied_tools: Collection[str],
    allowed_tools: set[str] | None,
    turn_id: str | None,
    risk_by_tool: Mapping[str, str],
    tool_specs: Mapping[str, Any],
    terminal_tools: Collection[str],
    validate_call: Callable[..., Any],
    phase_for: Callable[[str], str],
    terminal_engine_loader: Callable[[], Any],
    terminal_command_for: Callable[[str, dict[str, Any]], str | None],
    propose_actions: Callable[..., dict[str, Any]],
    execute_terminal: Callable[..., dict[str, Any]],
    execute_action: Callable[..., dict[str, Any]],
    action_summary: Callable[[str, dict[str, Any]], str],
    failure_report: Callable[[list[str], str, str], str],
    on_event: Callable[[dict[str, Any]], None] | None = None,
) -> CheckpointRecoveryOutcome:
    """Apply the legacy recovery branch without owning persistence or tool policy."""

    if not checkpoint:
        return CheckpointRecoveryOutcome()

    command = checkpoint.get("command")
    failed = checkpoint.get("failed_step") or {}
    tool = checkpoint.get("tool") or failed.get("tool")
    args = failed.get("args") or {}
    risk = failed.get("risk") or risk_by_tool.get(tool, "read")

    if command == "retry_step" and tool:
        validation_error = validate_call(
            {"tool": tool, "args": args},
            tool_specs.get(tool),
            mode,
            allowed_tools,
        )
        if tool in denied_tools or validation_error:
            reason = (
                "tool is denied in this mode"
                if tool in denied_tools
                else validation_error.message
            )
            return CheckpointRecoveryOutcome(turn_response={
                "reply": f"I couldn't retry that checkpoint, sir \u2014 {reason}.",
                "tools_used": [],
                "intent": intent,
                "stopped_on_error": True,
                "failed_step": failed,
                "streamed": False,
            })

        if on_event:
            on_event({"type": "thinking", "phase": phase_for(tool), "tool": tool})

        if tool in terminal_tools:
            terminal_engine = terminal_engine_loader()
            command_text = terminal_command_for(tool, args)
            gate = (
                terminal_engine.gate(command_text, surface=surface)
                if command_text
                else {"decision": "run", "risk": risk}
            )
            risk = gate.get("risk", risk)
            if gate.get("decision") == "refuse":
                result = {
                    "error": gate.get("reason")
                    or "terminal safety gate refused the command"
                }
            elif gate.get("decision") == "plan":
                result = terminal_engine.plan(command_text, surface)
            elif gate.get("decision") == "confirm":
                return CheckpointRecoveryOutcome(turn_response=propose_actions(
                    [(tool, args, risk)],
                    chat_id,
                    surface,
                    [],
                    intent,
                ))
            else:
                result = execute_terminal(
                    chat_id,
                    surface,
                    tool,
                    args,
                    risk,
                    on_event,
                )
        else:
            if risk == "high" and review_mode != "always":
                return CheckpointRecoveryOutcome(turn_response=propose_actions(
                    [(tool, args, risk)],
                    chat_id,
                    surface,
                    [],
                    intent,
                ))
            result = execute_action(
                chat_id,
                surface,
                tool,
                args,
                risk,
                mode=mode,
                allowed_tools=allowed_tools,
                turn_id=turn_id,
                step_index=0,
            )

        messages = ({
            "role": "user",
            "content": (
                f"CHECKPOINT_RETRY_RESULT {tool}: "
                f"{json.dumps(result, default=str)[:3000]}"
            ),
        },)
        tools_used = (tool,)
        if isinstance(result, dict) and result.get("error"):
            failed_now = {
                "tool": tool,
                "args": args,
                "risk": risk,
                "error": result["error"],
            }
            return CheckpointRecoveryOutcome(
                messages=messages,
                tools_used=tools_used,
                turn_response={
                    "reply": failure_report(
                        [],
                        action_summary(tool, args),
                        result["error"],
                    ),
                    "tools_used": list(tools_used),
                    "intent": intent,
                    "stopped_on_error": True,
                    "failed_step": failed_now,
                    "streamed": False,
                },
            )
        return CheckpointRecoveryOutcome(
            messages=messages,
            tools_used=tools_used,
            completed_actions=(action_summary(tool, args),),
        )

    if command == "skip_step" and tool:
        return CheckpointRecoveryOutcome(messages=({
            "role": "user",
            "content": (
                f"CHECKPOINT_SKIPPED {tool}: the owner explicitly skipped this failed step. "
                "Continue only with remaining work; do not call it again."
            ),
        },))
    if command == "revise" and checkpoint.get("revision"):
        return CheckpointRecoveryOutcome(messages=({
            "role": "user",
            "content": "PLAN_REVISION: " + str(checkpoint["revision"])[:1000],
        },))
    if command == "resume":
        return CheckpointRecoveryOutcome(messages=({
            "role": "user",
            "content": "RESUME_CHECKPOINT: continue after the last persisted completed step.",
        },))
    return CheckpointRecoveryOutcome()

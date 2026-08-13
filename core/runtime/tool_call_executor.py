"""Compatibility execution for one parsed Conductor tool call."""

from __future__ import annotations

import json
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolCallExecutionOutcome:
    """Changes Conductor applies after dispatching one parsed tool call."""

    messages: tuple[dict[str, Any], ...] = ()
    tools_used: tuple[str, ...] = ()
    completed_actions: tuple[str, ...] = ()
    proposed_actions: tuple[tuple[Any, ...], ...] = ()
    turn_response: dict[str, Any] | None = None


def _tool_result(tool: str, result: Any) -> tuple[dict[str, Any], ...]:
    return ({
        "role": "user",
        "content": f"TOOL_RESULT {tool}: {json.dumps(result, default=str)[:3000]}",
    },)


def execute_tool_call(
    call: Mapping[str, Any],
    *,
    chat_id: int,
    surface: str,
    intent: str,
    mode: str,
    review_mode: str,
    denied_tools: Collection[str],
    allowed_tools: set[str] | None,
    turn_id: str | None,
    step_index: int,
    prior_tools_used: Sequence[str],
    completed_actions: Sequence[str],
    risk_by_tool: Mapping[str, str],
    tool_specs: Mapping[str, Any],
    read_tools: Collection[str],
    optional_tools: Collection[str],
    terminal_tools: Collection[str],
    workflow_read_tools: Collection[str],
    validate_call: Callable[..., Any],
    phase_for: Callable[[str], str],
    execute_tool: Callable[..., dict[str, Any]],
    terminal_engine_loader: Callable[[], Any],
    terminal_command_for: Callable[[str, dict[str, Any]], str | None],
    make_tool_call: Callable[[str, dict[str, Any]], Any],
    receipt_key: Callable[[str, int, Any], str],
    load_receipt: Callable[[str], dict[str, Any] | None],
    store_receipt: Callable[[str, str, str, dict[str, Any], dict[str, Any]], None],
    execute_terminal: Callable[..., dict[str, Any]],
    execute_action: Callable[..., dict[str, Any]],
    log_action: Callable[..., Any],
    action_summary: Callable[[str, dict[str, Any]], str],
    picker_intro: Callable[[dict[str, Any]], str],
    failure_report: Callable[[list[str], str, str], str],
    on_event: Callable[[dict[str, Any]], None] | None = None,
) -> ToolCallExecutionOutcome:
    """Validate and dispatch one call while legacy helpers retain authority."""

    tool = call["tool"]
    args = call.get("args") or {}
    if not isinstance(args, dict):
        args = {}
    risk = risk_by_tool.get(tool, "read")

    if tool in denied_tools:
        result = {
            "denied": True,
            "reason": (
                f"{tool} is not available in this mode \u2014 shell/terminal actions require "
                "Agent mode. Tell the owner to switch modes; do not retry."
            ),
        }
        return ToolCallExecutionOutcome(messages=_tool_result(tool, result))

    is_read = tool in read_tools or tool in optional_tools
    if not is_read and allowed_tools is not None and tool not in allowed_tools:
        available = sorted(
            candidate
            for candidate in (allowed_tools or set())
            if candidate in read_tools or candidate in optional_tools
        )
        result = {
            "denied": True,
            "error_code": "tool.route_denied",
            "reason": (
                f"'{tool}' isn't an available tool this turn. Use one of these instead: "
                f"{', '.join(available) or '(none)'}. Do NOT tell the owner to change "
                "permissions or re-authorize \u2014 pick a real tool and continue."
            ),
        }
        return ToolCallExecutionOutcome(messages=_tool_result(tool, result))

    validation_error = validate_call(call, tool_specs.get(tool), mode, allowed_tools)
    if validation_error:
        result = {
            "error": validation_error.message,
            "error_code": validation_error.code,
            "stage": validation_error.stage,
            "retryable": validation_error.retryable,
        }
        return ToolCallExecutionOutcome(messages=_tool_result(tool, result))

    if on_event:
        try:
            on_event({"type": "thinking", "phase": phase_for(tool), "tool": tool})
        except Exception:
            pass

    if tool == "outline_plan":
        result = execute_tool(
            call,
            mode=mode,
            allowed_tools=allowed_tools,
            turn_id=turn_id,
            step_index=step_index,
        )
        if on_event and isinstance(result, dict) and result.get("ok"):
            try:
                on_event({
                    "type": "plan",
                    "steps": result["steps"],
                    "title": result.get("title", ""),
                })
            except Exception:
                pass
        return ToolCallExecutionOutcome(
            messages=_tool_result(tool, result),
            tools_used=(tool,),
        )

    if tool in terminal_tools:
        terminal_engine = terminal_engine_loader()
        command = terminal_command_for(tool, args)
        if not command:
            result = execute_tool(
                call,
                mode=mode,
                allowed_tools=allowed_tools,
                turn_id=turn_id,
                step_index=step_index,
            )
            completed = ()
        else:
            gate = terminal_engine.gate(command, surface=surface)
            decision, terminal_risk = gate["decision"], gate["risk"]
            if decision == "refuse":
                result = {
                    "refused": True,
                    "risk": terminal_risk,
                    "reason": gate["reason"],
                    "command": command,
                }
                completed = ()
            elif decision == "plan":
                result = terminal_engine.plan(command, surface)
                completed = ()
            elif decision == "confirm":
                return ToolCallExecutionOutcome(
                    proposed_actions=((tool, args, terminal_risk),),
                )
            else:
                terminal_receipt = None
                if turn_id:
                    terminal_call = make_tool_call(tool, args)
                    terminal_receipt = receipt_key(turn_id, step_index, terminal_call)
                replay = load_receipt(terminal_receipt) if terminal_receipt else None
                if replay is not None:
                    result = dict(replay)
                    result["receipt_key"] = terminal_receipt
                    result["replayed"] = True
                else:
                    result = execute_terminal(
                        chat_id,
                        surface,
                        tool,
                        args,
                        terminal_risk,
                        on_event,
                    )
                    if terminal_receipt and not result.get("error"):
                        store_receipt(
                            terminal_receipt,
                            turn_id,
                            tool,
                            args,
                            result,
                        )
                        result = dict(result)
                        result["receipt_key"] = terminal_receipt
                        result["replayed"] = False
                completed = (
                    (action_summary(tool, args),)
                    if not (isinstance(result, dict) and result.get("error"))
                    else ()
                )
        return ToolCallExecutionOutcome(
            messages=_tool_result(tool, result),
            tools_used=(tool,),
            completed_actions=completed,
        )

    if surface == "telegram" and risk in ("medium", "high"):
        result = {
            "blocked": (
                f"That's a {risk}-risk change, sir \u2014 please do it from Mission Control "
                "(Telegram stays read-only and safe)."
            )
        }
        completed = ()
    elif risk == "high" and review_mode != "always":
        return ToolCallExecutionOutcome(proposed_actions=((tool, args),))
    elif risk == "read":
        result = execute_tool(
            call,
            mode=mode,
            allowed_tools=allowed_tools,
            turn_id=turn_id,
            step_index=step_index,
        )
        if tool in workflow_read_tools and not (
            isinstance(result, dict) and result.get("__picker__")
        ):
            succeeded = (
                isinstance(result, dict)
                and result.get("available")
                and not result.get("error")
            )
            try:
                log_action(
                    chat_id,
                    surface,
                    tool,
                    args,
                    "read",
                    "executed" if succeeded else "failed",
                    action_summary(tool, args),
                    result,
                )
            except Exception:
                pass
        if isinstance(result, dict) and result.get("__picker__"):
            picker = result["__picker__"]
            return ToolCallExecutionOutcome(turn_response={
                "reply": picker_intro(picker),
                "tools_used": list(prior_tools_used) + [tool],
                "intent": intent,
                "pending_picker": picker,
                "streamed": False,
            })
    else:
        if review_mode == "ask":
            return ToolCallExecutionOutcome(
                proposed_actions=((tool, args, risk),),
            )
        try:
            result = execute_action(
                chat_id,
                surface,
                tool,
                args,
                risk,
                mode=mode,
                allowed_tools=allowed_tools,
                turn_id=turn_id,
                step_index=step_index,
            )
        except TypeError as exc:
            if "unexpected keyword argument" not in str(exc):
                raise
            result = execute_action(chat_id, surface, tool, args, risk)
        if isinstance(result, dict) and result.get("error"):
            failed_step = {
                "tool": tool,
                "args": args,
                "risk": risk,
                "error": result["error"],
            }
            return ToolCallExecutionOutcome(turn_response={
                "reply": failure_report(
                    list(completed_actions),
                    action_summary(tool, args),
                    result["error"],
                ),
                "tools_used": list(prior_tools_used) + [tool],
                "intent": intent,
                "stopped_on_error": True,
                "failed_step": failed_step,
                "streamed": False,
            })
        completed = (action_summary(tool, args),)

    return ToolCallExecutionOutcome(
        messages=_tool_result(tool, result),
        tools_used=(tool,),
        completed_actions=completed if risk != "read" else (),
    )

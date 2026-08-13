"""Compatibility turn coordinator for the legacy Conductor public API.

The facade composes the accepted T08 routing, context, recovery, one-call,
tool-loop, and response services through injected bindings. It deliberately
does not import ``core.conductor`` or create new policy, execution, persistence,
or routing authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional

from core.runtime.response_composer import FinalResponseContext, compose_final_response


@dataclass(frozen=True)
class ConductorTurnRequest:
    """One immutable compatibility request matching ``conductor.answer`` inputs."""

    message: str
    chat_id: Optional[int] = None
    surface: str = "mc"
    model: Optional[str] = None
    history: Optional[list[dict]] = None
    attachments_text: Optional[str] = None
    directives: Optional[str] = None
    extra_tools: Optional[list[str]] = None
    on_event: Optional[Callable[[dict], None]] = None
    on_delta: Optional[Callable[[str], None]] = None
    denied_tools: Optional[set] = None
    review_mode: Optional[str] = None
    mode: str = "agent"
    route: Optional[str] = None
    allowed_tools: Optional[set] = None
    context_manifest: Any = None
    turn_id: Optional[str] = None
    max_tool_steps: Optional[int] = None
    step_tokens: Optional[int] = None
    final_tokens: Optional[int] = None
    usage_context: Optional[dict] = None
    recovery_checkpoint: Optional[dict] = None


@dataclass(frozen=True)
class ConductorFacadeBindings:
    """Current compatibility owners injected by ``core.conductor`` per turn."""

    default_chat_id: Callable[..., Any]
    pending_all: Callable[..., Any]
    is_affirm: Callable[..., Any]
    is_negate: Callable[..., Any]
    confirm_action: Callable[..., Any]
    confirm_reply_batch: Callable[..., Any]
    profile_loader: Callable[..., Any]
    tier_loader: Callable[..., Any]
    resolve_context_sources: Callable[..., Any]
    resolve_intent: Callable[..., Any]
    prepare_prompt_context: Callable[..., Any]
    prompt_builder: Callable[..., Any]
    recall_detector: Callable[..., Any]
    get_llm: Callable[..., Any]
    prepare_model_messages: Callable[..., Any]
    history_loader: Callable[..., Any]
    apply_recovery_checkpoint: Callable[..., Any]
    risk_by_tool: Mapping[str, Any]
    tool_specs: Mapping[str, Any]
    read_tools: Mapping[str, Any]
    optional_tools: Mapping[str, Any]
    terminal_tools: Any
    workflow_read_tools: Any
    validate_call: Callable[..., Any]
    phase_for: Callable[..., Any]
    terminal_engine_loader: Callable[..., Any]
    terminal_command_for: Callable[..., Any]
    propose_actions: Callable[..., Any]
    execute_terminal: Callable[..., Any]
    execute_action: Callable[..., Any]
    execute_tool: Callable[..., Any]
    log_action: Callable[..., Any]
    action_summary: Callable[..., Any]
    picker_intro: Callable[..., Any]
    failure_report: Callable[..., Any]
    make_tool_call: Callable[..., Any]
    receipt_key: Callable[..., Any]
    load_receipt: Callable[..., Any]
    store_receipt: Callable[..., Any]
    execute_tool_call: Callable[..., Any]
    run_tool_loop: Callable[..., Any]
    parse_tool_calls: Callable[..., Any]
    generate_step: Callable[..., Any]
    continue_answer: Callable[..., Any]
    get_escalation_llm: Callable[..., Any]
    get_usage_context: Callable[..., Any]
    set_usage_context: Callable[..., Any]
    restore_usage_context: Callable[..., Any]
    default_max_tool_steps: int
    step_token_budget: int
    final_token_budget: int
    max_step_retries: int
    mixed_prose_min: int
    model_down_text: str
    model_struggling_text: str


def run_conductor_turn(
    request: ConductorTurnRequest,
    bindings: ConductorFacadeBindings,
) -> dict:
    """Execute one legacy-compatible Conductor turn through accepted Runtime services."""
    message = (request.message or "").strip()
    if not message:
        return {"reply": "", "tools_used": [], "error": "empty"}

    chat_id = request.chat_id if request.chat_id is not None else bindings.default_chat_id()
    denied_tools = set(request.denied_tools or ())
    allowed_tools = set(request.allowed_tools) if request.allowed_tools is not None else None
    mode = request.mode if request.mode in ("chat", "agent") else "chat"
    review_mode = (request.review_mode or "").strip().lower()

    if request.usage_context:
        try:
            bindings.set_usage_context(
                request.usage_context.get("surface", mode),
                request.usage_context.get("feature", ""),
                **{
                    key: value for key, value in request.usage_context.items()
                    if key not in {"surface", "feature"}
                },
            )
        except Exception:
            pass

    pending_list = bindings.pending_all(chat_id)
    if pending_list:
        if bindings.is_affirm(message):
            results = [
                bindings.confirm_action(item["id"], "approve", request.surface, chat_id)
                for item in pending_list
            ]
            return {
                "reply": bindings.confirm_reply_batch(pending_list, results, "approve"),
                "tools_used": [item["tool"] for item in pending_list],
                "intent": "CONFIRM",
                "confirmed": results,
            }
        if bindings.is_negate(message):
            for item in pending_list:
                bindings.confirm_action(item["id"], "reject", request.surface, chat_id)
            return {
                "reply": bindings.confirm_reply_batch(pending_list, None, "reject"),
                "tools_used": [],
                "intent": "CANCEL",
            }

    context_sources = bindings.resolve_context_sources(
        request.context_manifest,
        profile_loader=bindings.profile_loader,
        tier_loader=bindings.tier_loader,
    )
    intent_decision = bindings.resolve_intent(message, mode, request.route)
    intent = intent_decision.intent
    tools_enabled = intent_decision.tools_enabled
    prompt_context = bindings.prepare_prompt_context(
        message,
        request.attachments_text,
        context_sources,
        tools_enabled=tools_enabled,
        surface=request.surface,
        directives=request.directives,
        extra_tools=request.extra_tools,
        denied_tools=denied_tools,
        allowed_tools=allowed_tools,
        prompt_builder=bindings.prompt_builder,
        recall_detector=bindings.recall_detector,
    )
    message = prompt_context.message
    system = prompt_context.system

    try:
        client = (
            bindings.get_llm("simple", model=request.model)
            if request.model
            else bindings.get_llm("simple")
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "reply": bindings.model_down_text,
            "tools_used": [],
            "intent": intent,
            "error": str(exc),
        }

    messages = bindings.prepare_model_messages(
        message,
        request.history,
        chat_id,
        history_loader=bindings.history_loader,
    )
    used_tools: list[str] = []
    completed_actions: list[str] = []
    on_reset = (
        (lambda: request.on_event({"type": "reset"}))
        if request.on_event
        else None
    )

    recovery = bindings.apply_recovery_checkpoint(
        request.recovery_checkpoint,
        chat_id=chat_id,
        surface=request.surface,
        intent=intent,
        mode=mode,
        review_mode=review_mode,
        denied_tools=denied_tools,
        allowed_tools=allowed_tools,
        turn_id=request.turn_id,
        risk_by_tool=bindings.risk_by_tool,
        tool_specs=bindings.tool_specs,
        terminal_tools=bindings.terminal_tools,
        validate_call=bindings.validate_call,
        phase_for=bindings.phase_for,
        terminal_engine_loader=bindings.terminal_engine_loader,
        terminal_command_for=bindings.terminal_command_for,
        propose_actions=bindings.propose_actions,
        execute_terminal=bindings.execute_terminal,
        execute_action=bindings.execute_action,
        action_summary=bindings.action_summary,
        failure_report=bindings.failure_report,
        on_event=request.on_event,
    )
    if recovery.turn_response is not None:
        return recovery.turn_response
    messages.extend(recovery.messages)
    used_tools.extend(recovery.tools_used)
    completed_actions.extend(recovery.completed_actions)

    def compose(text: str) -> dict:
        return compose_final_response(
            text,
            FinalResponseContext(
                client=client,
                requested_model=request.model,
                usage_context=request.usage_context,
                mode=mode,
                intent=intent,
                messages=tuple(messages),
                system=system,
                tools_used=tuple(used_tools),
                final_tokens=request.final_tokens or bindings.final_token_budget,
                on_event=request.on_event,
                on_delta=request.on_delta,
                on_reset=on_reset,
            ),
            mixed_prose_min=bindings.mixed_prose_min,
            model_struggling_text=bindings.model_struggling_text,
            generate_step_legacy=bindings.generate_step,
            get_escalation_llm=bindings.get_escalation_llm,
            get_usage_context=bindings.get_usage_context,
            set_usage_context=bindings.set_usage_context,
            restore_usage_context=bindings.restore_usage_context,
        )

    if not tools_enabled:
        final_tokens = request.final_tokens or bindings.final_token_budget
        text, _is_answer, finish_reason = bindings.generate_step(
            client,
            messages,
            system,
            final_tokens,
            request.on_delta,
        )
        if finish_reason == "length":
            text += bindings.continue_answer(
                client,
                messages,
                text,
                system,
                request.on_delta,
            )
        return compose(text)

    def execute_loop_call(
        call: dict,
        *,
        step_index: int,
        prior_tools_used: list[str],
        completed_actions: list[str],
    ) -> Any:
        return bindings.execute_tool_call(
            call,
            chat_id=chat_id,
            surface=request.surface,
            intent=intent,
            mode=mode,
            review_mode=review_mode,
            denied_tools=denied_tools,
            allowed_tools=allowed_tools,
            turn_id=request.turn_id,
            step_index=step_index,
            prior_tools_used=prior_tools_used,
            completed_actions=completed_actions,
            risk_by_tool=bindings.risk_by_tool,
            tool_specs=bindings.tool_specs,
            read_tools=bindings.read_tools,
            optional_tools=bindings.optional_tools,
            terminal_tools=bindings.terminal_tools,
            workflow_read_tools=bindings.workflow_read_tools,
            validate_call=bindings.validate_call,
            phase_for=bindings.phase_for,
            execute_tool=bindings.execute_tool,
            terminal_engine_loader=bindings.terminal_engine_loader,
            terminal_command_for=bindings.terminal_command_for,
            make_tool_call=bindings.make_tool_call,
            receipt_key=bindings.receipt_key,
            load_receipt=bindings.load_receipt,
            store_receipt=bindings.store_receipt,
            execute_terminal=bindings.execute_terminal,
            execute_action=bindings.execute_action,
            log_action=bindings.log_action,
            action_summary=bindings.action_summary,
            picker_intro=bindings.picker_intro,
            failure_report=bindings.failure_report,
            on_event=request.on_event,
        )

    loop = bindings.run_tool_loop(
        client=client,
        messages=messages,
        system=system,
        chat_id=chat_id,
        surface=request.surface,
        intent=intent,
        mode=mode,
        used_tools=used_tools,
        completed_actions=completed_actions,
        max_tool_steps=request.max_tool_steps,
        default_max_tool_steps=bindings.default_max_tool_steps,
        step_tokens=request.step_tokens,
        step_token_budget=bindings.step_token_budget,
        final_tokens=request.final_tokens,
        final_token_budget=bindings.final_token_budget,
        max_step_retries=bindings.max_step_retries,
        generate_step=bindings.generate_step,
        continue_answer=bindings.continue_answer,
        parse_tool_calls=bindings.parse_tool_calls,
        execute_tool_call=execute_loop_call,
        propose_actions=bindings.propose_actions,
        on_delta=request.on_delta,
        on_reset=on_reset,
    )
    messages[:] = list(loop.messages)
    used_tools[:] = list(loop.tools_used)
    completed_actions[:] = list(loop.completed_actions)
    if loop.turn_response is not None:
        return loop.turn_response
    if loop.model_issue:
        return {
            "reply": bindings.model_struggling_text,
            "tools_used": used_tools,
            "intent": intent,
            "model_issue": True,
            "streamed": False,
        }
    return compose(loop.final_text or "")

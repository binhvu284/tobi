"""
TOBI Conductor — one shared conversational engine over Mission Control (queue #7).

P1 (this file, v1): the Conductor *reads & answers about* every MC feature by talking
to the owner — grounded strictly in live data via a read-tool catalog, with a butler
"sir" voice and language mirroring. Shared by both surfaces (MC chat + Telegram) so the
two front doors run one brain.

Design (locked by the spec's 30 Q&A):
  - **Hybrid routing:** a cheap regex classifier pre-routes; smalltalk/coding answer
    directly (fast, no tools), anything about MC state enters the tool-loop.
  - **Provider-agnostic tool-loop:** the model emits a one-line JSON `{"tool","args"}`
    when it needs live data; we execute the tool, feed the result back, and repeat until
    it gives a final answer. Works over the plain `complete()` string interface, so it
    runs on OpenRouter *and* Claude (no native-tool-use lock-in).
  - **Strict grounding:** every number/status must come from a tool result. The system
    prompt forbids invention; missing data → "I don't have that yet, sir" + offer to fetch.

Read tools are thin wrappers over existing DB ops / dashboard helpers (low risk). Act
tools, confirmation gating, the TOBI Actions audit and external chains are P2/P3.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from core.runtime.context_assembler import (
    prepare_model_messages as _prepare_model_messages,
    prepare_prompt_context as _prepare_prompt_context,
    resolve_context_sources as _resolve_context_sources,
)
from core.runtime.checkpoint_recovery import (
    apply_recovery_checkpoint as _apply_recovery_checkpoint,
)
from core.runtime.intent_router import (
    needs_episodic_recall as _detect_past_reference,
    resolve_intent as _resolve_intent,
)

logger = logging.getLogger("tobi.conductor")

# Shared tool helpers/constants live in core/conductor_tools/common.py (Phase 2 refactor)
# so the extracted tool modules and this orchestrator share one definition. Imported back
# into this namespace to preserve every existing reference (inline tools + orchestration).
from core.conductor_tools.common import (  # noqa: E402
    _AGENT_ALIASES, _EMOJI_BY_CATEGORY, _TASK_AGENTS, _TASK_PRIORITY,
    _TASK_STATUS_LEGACY, _conn, _load_owner_timezone, _notion_title, _pm_log,
    _pm_recalc, _resolve_pm_project, _resolve_when, _resource_inventory,
)

# Tool registry + the actions audit/confirm path now live in core/conductor_registry.py
# (Phase 4b). Imported back so the orchestration loop below is unchanged.
from core.conductor_registry import (
    ALL_TOOLS, ACT_TOOLS, OPTIONAL_TOOLS, READ_TOOLS, RISK, TERMINAL_TOOLS, TOOL_SPECS,
    _WORKFLOW_READ_TOOLS, _action_summary, _exec_tool, _execute_and_log,
    _execute_terminal_and_log, _log_action, _pending_all, _terminal_command_for,
    # Re-exported for callers that reach them through this module: api/routers/
    # {conductor,chat,office}.py, core/telegram_bot.py and the mode/office test suites.
    confirm_action, list_actions, propose_action,
)

# Tool functions stay re-exported from this module: core/chat_modes.py and
# core/news/telemetry.py import them as `from core.conductor import tool_*`.
# The 62 tool_* implementations were extracted to core/conductor_tools/* (Phase 2). They are
# imported back here so the tool-registry dicts (READ_TOOLS/OPTIONAL_TOOLS/ACT_TOOLS) and the
# few orchestration references (e.g. _system_prompt → tool_get_current_datetime) resolve them.
from core.conductor_tools.read_tools import (  # noqa: E402
    tool_get_evolution, tool_explain_architecture, tool_office_status, tool_list_projects,
    tool_list_tasks, tool_project_overview, tool_check_health, tool_recall,
    tool_recall_conversations, tool_storage_status, tool_llm_spend,
    tool_analyze_performance, tool_web_search, tool_outline_plan,
    tool_get_current_datetime, tool_ask_owner_details, tool_list_project_resources,
    tool_read_resource, tool_search_project_resources, tool_awakening_status,
)
from core.conductor_tools.external_read_tools import (  # noqa: E402
    tool_read_notion, tool_list_github_repos, tool_read_github, tool_read_drive,
    tool_summarize_repo,
)
from core.conductor_tools.terminal_tools import (  # noqa: E402
    tool_terminal_status, tool_list_jobs, tool_job_output, tool_list_installed_tools,
    tool_run_command, tool_install_package, tool_configure_tool, tool_connect_tool,
    tool_kill_job, tool_set_terminal_mode,
)
from core.conductor_tools.action_tools import (  # noqa: E402
    tool_remember, tool_save_note, tool_create_project, tool_create_task,
    tool_create_task_from_conversation, tool_update_task, tool_create_resource,
    tool_set_project_description, tool_pick_project_icon, tool_complete_task,
    tool_rename_project, tool_create_goal, tool_edit_goal, tool_set_category_lock,
    tool_assign_task, tool_update_project_progress, tool_delete_goal, tool_delete_task,
    tool_delete_project, tool_run_mission, tool_office_create_artifact,
    tool_office_update_artifact, tool_office_delete_artifact, tool_office_create_mission,
    tool_office_run_mission, tool_office_control_mission, tool_office_convert_to_tasks,
)

from core import tool_registry as _tool_registry


# Persona/prompt building and tool-call parsing moved to core/conductor_prompts.py
# and core/conductor_parsing.py (Phase 4b). Imported back for the loop below.
from core.conductor_prompts import (  # noqa: F401 - re-exported: tests and other
    # modules reach these through core.conductor (e.g. conductor._BUTLER, _read_doc).
    _BUTLER, _TIME_SENSITIVE_RE, _act_doc, _build_tier_context, _read_doc, _system_prompt
)
from core.conductor_parsing import (  # noqa: F401 - re-exported: tests and other
    # modules reach these through core.conductor (e.g. conductor._BUTLER, _read_doc).
    _AFFIRM, _FENCE_RE, _NEGATE, _TOOL_PHASE, _balanced_objects, _confirm_reply,
    _confirm_reply_batch, _default_chat_id, _history, _is_affirm, _is_negate, _norm,
    _parse_tool_call, _parse_tool_calls, _phase_for, _propose_actions, _propose_reply,
    _safe_complete, strip_tool_calls
)
from core.runtime.response_composer import (
    TOOL_SIGNATURE_RE as _TOOL_SIG_RE,
    continue_answer as _continue_model_answer,
    generate_step as _generate_model_step,
    looks_like_tool_start as _looks_like_tool_start,
    split_reasoning as _strip_reasoning,
    stream_chunks as _stream_chunks,
)
from core.runtime.tool_call_executor import execute_tool_call as _execute_tool_call
from core.runtime.tool_loop_orchestrator import run_tool_loop as _run_tool_loop

MAX_TOOL_STEPS = 8  # enough for a chain: read → create project → tasks → assign → answer
_LLM_DOWN = "I can't reach my language model right now, sir — do check the LLM API key in Integrations."


def _failure_report(done: list[str], failed_summary: str, error: str) -> str:
    """Stop-on-failure report for a partly-completed multi-step chain (P3)."""
    parts = ["I hit a snag mid-way, sir, so I stopped to keep things clean."]
    if done:
        parts.append("Completed so far: " + "; ".join(done) + ".")
    parts.append(f"Failed at: {failed_summary} — {error}.")
    parts.append("Shall I retry that step, or adjust the plan?")
    return " ".join(parts)


def _load_terminal_engine():
    from core import terminal_engine

    return terminal_engine


# ════════════════════════════════════════════════════════════════════════════
# Read-tool catalog  (each returns a compact, JSON-serializable dict of LIVE data)
# ════════════════════════════════════════════════════════════════════════════


















# ── External read tools (P3) — Notion / GitHub / Drive, via the Genesis-vault creds ──










from datetime import datetime as _dt, timedelta as _td, timezone as _tz
















# name → (callable, one-line description for the model)






def _picker_intro(picker: dict) -> str:
    topic = (picker.get("topic") or "a few details").strip().rstrip(".")
    return f"I need a bit of context first, sir — {topic[:1].lower() + topic[1:]}. Mind filling these in?"












# ── Terminal read tools (#11) ────────────────────────────────────────────────────














# ════════════════════════════════════════════════════════════════════════════
# Engine
# ════════════════════════════════════════════════════════════════════════════




# ── Reliability core (#8 v2 P1): never truncate, never leak reasoning ────────────
STEP_TOKENS = 2048    # generous so a tool-call JSON (or short answer) never truncates
FINAL_TOKENS = 4096   # generous final answer; complete continuation if it still caps
MAX_STEP_RETRIES = 2  # re-issue a garbled/truncated tool-call up to this many times

# Prose left over once a tool call is removed only counts as an answer at this length. A
# stray word ("Okay") beside a call is noise; a real question or finding is longer.
_MIXED_PROSE_MIN = 20

_MODEL_STRUGGLING = (
    "I'm having trouble completing that with the current model, sir — it keeps returning "
    "incomplete or malformed output. Do try a stronger model from the picker (top-right) and "
    "I'll pick this straight back up."
)

def _gen_step(client, msgs: list, system: str, max_tokens: int,
              on_delta: Optional[Callable[[str], None]],
              on_reset: Optional[Callable[[], None]] = None) -> tuple[str, bool, Optional[str]]:
    """Compatibility tuple wrapper around the typed Runtime service."""
    return _generate_model_step(
        client, msgs, system, max_tokens, on_delta, on_reset
    ).as_legacy_tuple()


def _continue_answer(client, msgs: list, partial: str, system: str,
                     on_delta: Optional[Callable[[str], None]], rounds: int = 2) -> str:
    """Compatibility wrapper using the historical final-answer token cap."""
    return _continue_model_answer(
        client, msgs, partial, system, on_delta,
        max_tokens=FINAL_TOKENS, rounds=rounds,
    )


def answer(message: str, chat_id: Optional[int] = None, surface: str = "mc",
           model: Optional[str] = None, history: Optional[list[dict]] = None,
           attachments_text: Optional[str] = None, directives: Optional[str] = None,
           extra_tools: Optional[list[str]] = None,
           on_event: Optional[Callable[[dict], None]] = None,
           on_delta: Optional[Callable[[str], None]] = None,
           denied_tools: Optional[set] = None, review_mode: Optional[str] = None,
           mode: str = "agent", route: Optional[str] = None,
           allowed_tools: Optional[set] = None, context_manifest: Any = None,
           turn_id: Optional[str] = None, max_tool_steps: Optional[int] = None,
           step_tokens: Optional[int] = None, final_tokens: Optional[int] = None,
           usage_context: Optional[dict] = None,
           recovery_checkpoint: Optional[dict] = None) -> dict:
    """Core turn: confirm-pending? → classify → (optional) tool-loop with tiered act gating →
    grounded butler reply (+ pending_action when a high-risk act needs confirmation). No
    persistence (the chat/stream wrappers persist + learn). `surface` = 'mc' | 'telegram'.

    `model` ('provider:model') overrides the routed model — the Premium Chat (#8) picker
    threads the session's chosen model here. `history`, when given, is used verbatim as the
    conversation context (the session store owns it) instead of the Conductor's rolling
    `conversations` table.

    `denied_tools` is the mode capability boundary (#16 [D11][D23]): any tool in this set is
    NOT advertised AND is rejected server-side if the model calls it anyway — so the selected
    mode changes the real backend capability, not just prompting (Chat denies the terminal
    surface). Review policy is server-authoritative: ``ask`` proposes every mutation,
    ``session`` trusts low/medium mutations but proposes high-risk work, and ``always`` executes
    all otherwise-allowed mutations autonomously. Recovery checkpoints come from persisted run
    state rather than browser-supplied tool arguments."""
    message = (message or "").strip()
    if not message:
        return {"reply": "", "tools_used": [], "error": "empty"}
    if chat_id is None:
        chat_id = _default_chat_id()
    denied_tools = set(denied_tools or ())
    allowed_tools = set(allowed_tools) if allowed_tools is not None else None
    mode = mode if mode in ("chat", "agent") else "chat"
    review_mode = (review_mode or "").strip().lower()
    if usage_context:
        try:
            from core import model_router as _mr
            _mr.set_usage_context(
                usage_context.get("surface", mode),
                usage_context.get("feature", ""),
                **{
                    key: value for key, value in usage_context.items()
                    if key not in {"surface", "feature"}
                },
            )
        except Exception:
            pass

    # Pending high-risk proposals + a typed yes/no resolves them (the whole batch) first.
    pending_list = _pending_all(chat_id)
    if pending_list:
        if _is_affirm(message):
            results = [confirm_action(p["id"], "approve", surface, chat_id) for p in pending_list]
            return {"reply": _confirm_reply_batch(pending_list, results, "approve"),
                    "tools_used": [p["tool"] for p in pending_list], "intent": "CONFIRM", "confirmed": results}
        if _is_negate(message):
            for p in pending_list:
                confirm_action(p["id"], "reject", surface, chat_id)
            return {"reply": _confirm_reply_batch(pending_list, None, "reject"), "tools_used": [], "intent": "CANCEL"}
        # otherwise the owner moved on — leave the proposals pending and answer normally.

    from core import brain
    from core.model_router import get_llm

    context_sources = _resolve_context_sources(
        context_manifest,
        profile_loader=brain.profile_summary,
        tier_loader=_build_tier_context,
    )
    intent_decision = _resolve_intent(message, mode, route)
    intent = intent_decision.intent
    # Attachments (P2): the owner's files arrive as extracted text — fold them into the
    # turn as context so the tool-loop and the grounded reply can use them.
    tools_enabled = intent_decision.tools_enabled
    prompt_context = _prepare_prompt_context(
        message,
        attachments_text,
        context_sources,
        tools_enabled=tools_enabled,
        surface=surface,
        directives=directives,
        extra_tools=extra_tools,
        denied_tools=denied_tools,
        allowed_tools=allowed_tools,
        prompt_builder=_system_prompt,
        recall_detector=_detect_past_reference,
    )
    message = prompt_context.message
    system = prompt_context.system

    try:
        # Keep the legacy call shape when no model override is given, so callers/tests that
        # wrap get_llm with the old (task_type-only) signature keep working.
        client = get_llm("simple", model=model) if model else get_llm("simple")
    except Exception as e:
        return {"reply": _LLM_DOWN, "tools_used": [], "intent": intent, "error": str(e)}

    def _with_model_meta(payload: dict, *, actual_override: Optional[str] = None,
                         reason_override: Optional[str] = None) -> dict:
        requested = (
            getattr(client, "requested_model", None)
            or (model or "")
            or (usage_context or {}).get("requested_model")
            or None
        )
        actual = actual_override or getattr(client, "actual_model_id", None)
        if not actual and getattr(client, "provider", None) and getattr(client, "model", None):
            actual = f"{client.provider}:{client.model}"
        payload.update({
            "requested_model": requested,
            "actual_model": actual,
            "fallback_reason": reason_override or getattr(client, "fallback_reason", None),
            "model_attempts": int(getattr(client, "attempt_count", 1) or 1),
        })
        return payload

    msgs = _prepare_model_messages(message, history, chat_id, history_loader=_history)
    used: list[str] = []
    done_acts: list[str] = []  # successfully executed acts in this chain (for stop-on-failure)
    # When a chatty model leaks a prose preamble before a tool call, retract it from the UI.
    on_reset = (lambda: on_event({"type": "reset"})) if on_event else None

    # Recover persisted work before model planning while existing helpers retain authority for
    # validation, safety, execution, approvals, receipts, and owner-visible responses.
    recovery = _apply_recovery_checkpoint(
        recovery_checkpoint,
        chat_id=chat_id,
        surface=surface,
        intent=intent,
        mode=mode,
        review_mode=review_mode,
        denied_tools=denied_tools,
        allowed_tools=allowed_tools,
        turn_id=turn_id,
        risk_by_tool=RISK,
        tool_specs=TOOL_SPECS,
        terminal_tools=TERMINAL_TOOLS,
        validate_call=_tool_registry.validate_call,
        phase_for=_phase_for,
        terminal_engine_loader=_load_terminal_engine,
        terminal_command_for=_terminal_command_for,
        propose_actions=_propose_actions,
        execute_terminal=_execute_terminal_and_log,
        execute_action=_execute_and_log,
        action_summary=_action_summary,
        failure_report=_failure_report,
        on_event=on_event,
    )
    if recovery.turn_response is not None:
        return recovery.turn_response
    msgs.extend(recovery.messages)
    used.extend(recovery.tools_used)
    done_acts.extend(recovery.completed_actions)

    def _final(text: str) -> dict:
        """Finish a turn: strip reasoning, continue if it was truncated, flag a model issue.

        Guard: NEVER surface a raw tool-call JSON to the owner. A weaker model sometimes emits
        `{"tool": …}` where a prose answer was required (it keeps "calling" a tool — e.g. loops
        on recall_conversations — and still emits JSON on the forced-final step). Dumping that
        verbatim is the `{"tool":"…"}` leak owners see; instead we treat it as a model issue so
        the UI shows a graceful notice, not machine JSON."""
        clean, reasoning = _strip_reasoning(text)
        # Trip only on a genuine tool call: a parseable {"tool":…} object, or a leading `{"tool"`
        # signature (a truncated/garbled one). This is precise — a legitimate fenced-JSON answer
        # the owner asked for does NOT lead with `{"tool"` and won't parse as a call.
        if not clean or _TOOL_SIG_RE.match(clean.lstrip()) or _parse_tool_call(clean):
            # A reply can be BOTH a tool call and something worth saying. Asked to "list all
            # project, update their progress", the model emitted the call and, glued to it,
            # "I need each project's current status ... to update progress accurately" — the
            # one question the request left open. The tools have already run by this point, so
            # the prose IS the answer; discarding it cost the owner a fair question and told
            # him his model was struggling, which was never true.
            leftover = strip_tool_calls(clean)
            if len(leftover) >= _MIXED_PROSE_MIN:
                return _with_model_meta({
                    "reply": leftover, "reasoning": reasoning, "tools_used": used,
                    "intent": intent, "streamed": False,
                })
            # Nothing but a tool call — the model genuinely never answered. Escalate once,
            # visibly, only after the invalid response has been buffered/retracted.
            try:
                from core.model_router import get_escalation_llm
                stronger, stronger_id = get_escalation_llm(model)
                if stronger is not None:
                    if on_reset:
                        on_reset()
                    if on_event:
                        on_event({"type": "model_escalated", "from_model": model,
                                  "to_model": stronger_id, "reason": "malformed_output"})
                    retry_msgs = list(msgs) + [{"role": "user", "content":
                        "The previous model produced malformed internal output. Give the owner a complete "
                        "plain-language answer now. Do not emit a tool call or JSON."}]
                    from core import model_router as _model_router
                    previous_usage = _model_router.get_usage_context()
                    _model_router.set_usage_context(
                        previous_usage.get("surface", mode),
                        previous_usage.get("feature", ""),
                        **{
                            **{
                                key: value for key, value in previous_usage.items()
                                if key not in {"surface", "feature"}
                            },
                            "requested_model": (
                                getattr(client, "requested_model", None)
                                or model or previous_usage.get("requested_model", "")
                            ),
                            "attempt": int(getattr(client, "attempt_count", 1) or 1) + 1,
                            "fallback_reason": "malformed_output",
                        },
                    )
                    try:
                        retry, retry_is_answer, _ = _gen_step(
                            stronger, retry_msgs, system, final_tokens or FINAL_TOKENS,
                            on_delta, on_reset)
                    finally:
                        _model_router.restore_usage_context(previous_usage)
                    retry_clean, retry_reasoning = _strip_reasoning(retry)
                    if retry_is_answer and retry_clean and not _parse_tool_call(retry_clean):
                        return _with_model_meta({
                            "reply": retry_clean, "reasoning": retry_reasoning,
                            "tools_used": used, "intent": intent, "streamed": bool(on_delta),
                            "model_escalated": stronger_id,
                        }, actual_override=stronger_id, reason_override="malformed_output")
            except Exception as exc:
                logger.warning("conductor model escalation failed: %s", exc)
            return _with_model_meta({
                "reply": _MODEL_STRUGGLING, "tools_used": used, "intent": intent,
                "model_issue": True, "streamed": False,
            })
        return _with_model_meta({
            "reply": clean, "reasoning": reasoning, "tools_used": used,
            "intent": intent, "streamed": bool(on_delta),
        })

    if not tools_enabled:
        _final_tokens = final_tokens or FINAL_TOKENS
        text, _isa, fr = _gen_step(client, msgs, system, _final_tokens, on_delta)
        if fr == "length":
            text += _continue_answer(client, msgs, text, system, on_delta)
        return _final(text)

    def _execute_loop_call(call: dict, *, step_index: int,
                           prior_tools_used: list[str],
                           completed_actions: list[str]):
        return _execute_tool_call(
            call,
            chat_id=chat_id,
            surface=surface,
            intent=intent,
            mode=mode,
            review_mode=review_mode,
            denied_tools=denied_tools,
            allowed_tools=allowed_tools,
            turn_id=turn_id,
            step_index=step_index,
            prior_tools_used=prior_tools_used,
            completed_actions=completed_actions,
            risk_by_tool=RISK,
            tool_specs=TOOL_SPECS,
            read_tools=READ_TOOLS,
            optional_tools=OPTIONAL_TOOLS,
            terminal_tools=TERMINAL_TOOLS,
            workflow_read_tools=_WORKFLOW_READ_TOOLS,
            validate_call=_tool_registry.validate_call,
            phase_for=_phase_for,
            execute_tool=_exec_tool,
            terminal_engine_loader=_load_terminal_engine,
            terminal_command_for=_terminal_command_for,
            make_tool_call=_tool_registry.ToolCall,
            receipt_key=_tool_registry.receipt_key,
            load_receipt=_tool_registry.load_receipt,
            store_receipt=_tool_registry.store_receipt,
            execute_terminal=_execute_terminal_and_log,
            execute_action=_execute_and_log,
            log_action=_log_action,
            action_summary=_action_summary,
            picker_intro=_picker_intro,
            failure_report=_failure_report,
            on_event=on_event,
        )

    loop = _run_tool_loop(
        client=client,
        messages=msgs,
        system=system,
        chat_id=chat_id,
        surface=surface,
        intent=intent,
        mode=mode,
        used_tools=used,
        completed_actions=done_acts,
        max_tool_steps=max_tool_steps,
        default_max_tool_steps=MAX_TOOL_STEPS,
        step_tokens=step_tokens,
        step_token_budget=STEP_TOKENS,
        final_tokens=final_tokens,
        final_token_budget=FINAL_TOKENS,
        max_step_retries=MAX_STEP_RETRIES,
        generate_step=_gen_step,
        continue_answer=_continue_answer,
        parse_tool_calls=_parse_tool_calls,
        execute_tool_call=_execute_loop_call,
        propose_actions=_propose_actions,
        on_delta=on_delta,
        on_reset=on_reset,
    )
    msgs[:] = list(loop.messages)
    used[:] = list(loop.tools_used)
    done_acts[:] = list(loop.completed_actions)
    if loop.turn_response is not None:
        return loop.turn_response
    if loop.model_issue:
        return {"reply": _MODEL_STRUGGLING, "tools_used": used, "intent": intent,
                "model_issue": True, "streamed": False}
    return _final(loop.final_text or "")


def _persist_and_learn(chat_id: int, message: str, reply: str) -> None:
    try:
        from core.database import save_conversation_message
        save_conversation_message(chat_id, "user", message)
        save_conversation_message(chat_id, "assistant", reply)
    except Exception as e:
        logger.warning("conductor persist failed: %s", e)
    try:
        from core import brain
        brain.sweep_once()
    except Exception as e:
        logger.warning("post-chat sweep failed: %s", e)


def conductor_chat(message: str, chat_id: Optional[int] = None, surface: str = "mc") -> dict:
    """Non-streaming turn used by the MC chat (and Telegram). Returns {reply, tools_used}."""
    message = (message or "").strip()
    if not message:
        return {"reply": "", "error": "empty"}
    if chat_id is None:
        chat_id = _default_chat_id()
    res = answer(message, chat_id, surface)
    _persist_and_learn(chat_id, message, res.get("reply", ""))
    return res


def conductor_chat_stream(message: str, chat_id: Optional[int] = None, surface: str = "mc"):
    """Streaming turn: computes the grounded answer (running tools as needed), then reveals it
    in chunks. The tool-loop isn't token-streamable across providers, so we stream the final
    answer; the chat UI's thinking orb covers the 'working' phase."""
    message = (message or "").strip()
    if not message:
        return
    if chat_id is None:
        chat_id = _default_chat_id()
    res = answer(message, chat_id, surface)
    reply = res.get("reply", "") or _LLM_DOWN
    for chunk in _stream_chunks(reply):
        yield chunk
    _persist_and_learn(chat_id, message, reply)


def conductor_status() -> dict:
    """Introspection for the API/tests: which tools the Conductor exposes."""
    terminal: dict = {}
    try:
        from core import terminal_engine as te
        terminal = te.status()
    except Exception as e:  # noqa: BLE001
        terminal = {"error": str(e)[:120]}
    return {
        "phase": "P3 + terminal (#11: read + act + external + chains + full-machine shell)",
        "read_tools": [{"name": n, "description": d} for n, (_, d) in READ_TOOLS.items()],
        "act_tools": [{"name": n, "risk": r, "description": d} for n, (_, r, d) in ACT_TOOLS.items()],
        "optional_tools": [{"name": n, "description": d} for n, (_, d) in OPTIONAL_TOOLS.items()],
        "terminal_tools": sorted(TERMINAL_TOOLS),
        "terminal": terminal,
        "surfaces": {"mc": "full power", "telegram": "read + low-risk only (terminal capped at Ask)"},
        "confirmation": "high-risk actions (delete, run_mission) + gated terminal commands require owner "
                        "confirmation (button or typed yes); the terminal approval mode (plan/ask/accept/auto) "
                        "and hard denylist govern shell execution",
    }

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
import re
from datetime import datetime, timezone
from typing import Any, Callable, Optional

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
    _safe_complete
)

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


# ════════════════════════════════════════════════════════════════════════════
# Read-tool catalog  (each returns a compact, JSON-serializable dict of LIVE data)
# ════════════════════════════════════════════════════════════════════════════


















# ── External read tools (P3) — Notion / GitHub / Drive, via the Genesis-vault creds ──










# ── Episodic recall: cross-session memory ────────────────────────────────────

import re as _re
from datetime import datetime as _dt, timedelta as _td, timezone as _tz

_PAST_REF_RE = _re.compile(
    r'(yesterday|last\s+\w+|\d+\s*days?\s*ago|earlier|before|'
    r'what\s+did\s+we|do\s+you\s+remember|recall|when\s+did\s+we|'
    r'when\s+were\s+we|what\s+were\s+we\s+discuss\w*|what\s+have\s+we\s+been|'
    r'previous\s+(session|chat|conversation)|other\s+(session|chat|conversation)|'
    r'what\s+about\s+our|talked\s+about|discussed)',
    _re.IGNORECASE,
)


def _detect_past_reference(message: str) -> bool:
    """True when the owner is likely asking about past conversations."""
    return bool(_PAST_REF_RE.search(message or ""))
















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

_MODEL_STRUGGLING = (
    "I'm having trouble completing that with the current model, sir — it keeps returning "
    "incomplete or malformed output. Do try a stronger model from the picker (top-right) and "
    "I'll pick this straight back up."
)

_THINK_RE = re.compile(r"<think(?:ing)?>.*?</think(?:ing)?>", re.S | re.I)
_REASON_LEAD_RE = re.compile(r"^\s*(?:reasoning|thought|thinking|analysis)\s*:\s*", re.I)
# A tool-call JSON object emerging anywhere in a streamed reply (even after a prose preamble
# from a chatty model) — used to reclassify "answer"→"tool" mid-stream and retract the leak.
# Matches as soon as `{"tool"` appears (before the value), so the JSON body never streams.
_TOOL_SIG_RE = re.compile(r'\{\s*"tool"')


def _looks_like_tool_start(stripped: str) -> bool:
    """Cheap classifier for a (streamed) prefix: is this the start of a tool-call JSON?"""
    if not stripped:
        return False
    if stripped[0] == "{":
        return True
    return bool(re.match(r"```(?:json)?\s*\{", stripped))


def _strip_reasoning(text: str) -> tuple[str, str]:
    """Split a reply into (clean_answer, reasoning). Removes <think>…</think> blocks, OpenAI
    'harmony' channels and a leading 'Reasoning:' preamble so the answer body never shows the
    model's private thinking — that goes to the collapsible panel instead (decision #5/#6)."""
    if not text:
        return "", ""
    reasoning = "\n".join(_THINK_RE.findall(text)).strip()
    clean = _THINK_RE.sub("", text)
    if "<|channel|>" in clean or "<|start|>" in clean:
        finals = re.findall(r"final\s*<\|message\|>(.*?)(?:<\|end\|>|<\|return\|>|$)", clean, re.S)
        if finals:
            reasoning = (reasoning + "\n" + clean).strip()
            clean = "\n".join(f.strip() for f in finals)
    low = clean.lower()
    if "<think" in low and "</think" not in low:  # unclosed → it's all reasoning, no answer yet
        idx = low.find("<think")
        reasoning = (reasoning + "\n" + clean[idx:]).strip()
        clean = clean[:idx]
    clean = _REASON_LEAD_RE.sub("", clean).strip()
    return clean, reasoning


def _gen_step(client, msgs: list, system: str, max_tokens: int,
              on_delta: Optional[Callable[[str], None]],
              on_reset: Optional[Callable[[], None]] = None) -> tuple[str, bool, Optional[str]]:
    """Run one model turn. Returns (text, is_answer, finish_reason).

    When `on_delta` is set and the client can stream, a *final answer* streams live via
    on_delta while a *tool-call* is buffered silently (classified from its prefix), so only
    real answers reach the chat as tokens — tool deliberation never shows.

    A chatty model sometimes writes a prose preamble *before* the tool-call JSON ("Of course,
    sir…\\n{\"tool\":…}"). The prefix then looks like an answer, so we start streaming it; once
    the `{\"tool\":` signature appears we reclassify to a tool call, fire `on_reset` (the UI
    drops the leaked preamble) and buffer the rest silently — so the JSON never lingers in chat
    and the tool actually runs."""
    streamer = getattr(client, "complete_stream", None)
    if not on_delta or streamer is None:
        try:
            text = client.complete(list(msgs), system=system, max_tokens=max_tokens) or ""
        except Exception as e:  # noqa: BLE001
            logger.warning("conductor step failed: %s", e)
            return "", False, "error"
        # A parseable tool call (even behind a prose preamble) is a tool call, not an answer.
        is_answer = _parse_tool_call(text) is None and not _looks_like_tool_start(text.lstrip())
        if is_answer and on_delta:
            for ch in _stream_chunks(text):
                on_delta(ch)
        return text, is_answer, getattr(client, "last_finish_reason", None)

    buf = ""; decided: Optional[str] = None; emitted = 0; reset = False

    def _to_tool():
        """Reclassify a mid-stream answer as a tool call: retract whatever leaked, buffer on."""
        nonlocal decided, reset
        decided = "tool"; reset = True
        if emitted and on_reset:
            try: on_reset()
            except Exception: pass

    try:
        for delta in streamer(list(msgs), system=system, max_tokens=max_tokens):
            buf += delta
            if decided is None:
                s = buf.lstrip()
                if len(s) >= 8 or "\n" in buf:
                    decided = "tool" if _looks_like_tool_start(s) else "answer"
                    if decided == "answer" and _TOOL_SIG_RE.search(buf):
                        _to_tool()
                    elif decided == "answer":
                        on_delta(buf[emitted:]); emitted = len(buf)
            elif decided == "answer":
                if _TOOL_SIG_RE.search(buf):           # a tool call surfaced after prose → retract
                    _to_tool()
                else:
                    on_delta(buf[emitted:]); emitted = len(buf)
    except Exception as e:  # noqa: BLE001
        logger.warning("conductor stream failed: %s", e)
        try:
            buf = client.complete(list(msgs), system=system, max_tokens=max_tokens) or buf
        except Exception:
            pass
    if decided is None:  # very short output
        decided = "tool" if (_looks_like_tool_start(buf.lstrip()) or _parse_tool_call(buf)) else "answer"
        if decided == "answer" and emitted == 0 and buf:
            on_delta(buf)
    elif decided == "answer" and not reset and _parse_tool_call(buf):
        # streamed fully as an answer but it actually parses as a tool call → retract + run it
        _to_tool()
    return buf, (decided == "answer"), getattr(client, "last_finish_reason", None)


def _continue_answer(client, msgs: list, partial: str, system: str,
                     on_delta: Optional[Callable[[str], None]], rounds: int = 2) -> str:
    """If a streamed/compiled answer stopped on the token cap, ask the model to continue from
    where it left off (streaming the continuation too). Returns the appended text."""
    extra = ""
    cur = partial
    for _ in range(rounds):
        if getattr(client, "last_finish_reason", None) != "length":
            break
        cont = list(msgs) + [
            {"role": "assistant", "content": cur},
            {"role": "user", "content": "Continue from exactly where you stopped. Do not repeat anything."},
        ]
        piece, _isa, _fr = _gen_step(client, cont, system, FINAL_TOKENS, on_delta)
        if not piece:
            break
        extra += piece
        cur = piece
    return extra


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
            _mr.set_usage_context(usage_context.get("surface", mode), usage_context.get("feature", ""))
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
    from core.task_classifier import classify

    if context_manifest is not None:
        profile = context_manifest.source_content("owner_memory")
        tier_context = context_manifest.source_content("evolution")
        try:
            from core.context_manager import prompt_context
            manifest_text = prompt_context(context_manifest)
        except Exception:
            manifest_text = ""
    else:
        try:
            profile = brain.profile_summary()
        except Exception:
            profile = ""
        tier_context = _build_tier_context()
        manifest_text = ""
    try:
        intent = classify(message)
    except Exception:
        intent = "QUESTION"
    # Attachments (P2): the owner's files arrive as extracted text — fold them into the
    # turn as context so the tool-loop and the grounded reply can use them.
    if attachments_text:
        message = f"{message}\n\n[Attached content the owner shared]\n{attachments_text}"
    tools_enabled = route != "direct" if route else intent not in ("SMALLTALK", "CODING")
    if mode == "agent" and intent == "CODING":
        tools_enabled = True
    system = _system_prompt(profile, tools_enabled, surface, directives, extra_tools,
                            user_message=message, denied_tools=denied_tools,
                            allowed_tools=allowed_tools, tier_context=tier_context,
                            context_text=manifest_text)

    # Smart trigger: when the owner references past conversations, nudge the LLM
    # to use the recall_conversations tool before answering.
    if tools_enabled and _detect_past_reference(message):
        system += (
            "\n\n⚠ EPISODIC RECALL: The owner is asking about past conversations. "
            "Use the recall_conversations tool to retrieve relevant messages BEFORE responding. "
            "Extract the time reference (e.g., 'yesterday', 'last week') and topic from their "
            "message and pass them as the 'when' and 'query' args. "
            "If the owner asks broadly ('what did we discuss yesterday?'), summarize the returned "
            "messages. If they ask specifically ('when did we discuss X?'), report exact messages "
            "with timestamps and which session they came from."
        )

    try:
        # Keep the legacy call shape when no model override is given, so callers/tests that
        # wrap get_llm with the old (task_type-only) signature keep working.
        client = get_llm("simple", model=model) if model else get_llm("simple")
    except Exception as e:
        return {"reply": _LLM_DOWN, "tools_used": [], "intent": intent, "error": str(e)}

    prior = history if history is not None else _history(chat_id, limit=6)
    msgs = list(prior) + [{"role": "user", "content": message}]
    used: list[str] = []
    done_acts: list[str] = []  # successfully executed acts in this chain (for stop-on-failure)
    step_fails = 0             # truncated/garbled steps → model self-diagnosis
    # When a chatty model leaks a prose preamble before a tool call, retract it from the UI.
    on_reset = (lambda: on_event({"type": "reset"})) if on_event else None

    # Recover the persisted failed checkpoint before model planning. Retry replays the exact
    # validated call; Skip creates an explicit result that prevents the model calling it again.
    if recovery_checkpoint:
        command = recovery_checkpoint.get("command")
        failed = recovery_checkpoint.get("failed_step") or {}
        tool = recovery_checkpoint.get("tool") or failed.get("tool")
        args = failed.get("args") or {}
        risk = failed.get("risk") or RISK.get(tool, "read")
        if command == "retry_step" and tool:
            validation_error = _tool_registry.validate_call(
                {"tool": tool, "args": args}, TOOL_SPECS.get(tool), mode, allowed_tools)
            if tool in denied_tools or validation_error:
                reason = "tool is denied in this mode" if tool in denied_tools else validation_error.message
                return {"reply": f"I couldn't retry that checkpoint, sir — {reason}.",
                        "tools_used": [], "intent": intent, "stopped_on_error": True,
                        "failed_step": failed, "streamed": False}
            if on_event:
                on_event({"type": "thinking", "phase": _phase_for(tool), "tool": tool})
            if tool in TERMINAL_TOOLS:
                from core import terminal_engine as te
                cmd = _terminal_command_for(tool, args)
                gate = te.gate(cmd, surface=surface) if cmd else {"decision": "run", "risk": risk}
                risk = gate.get("risk", risk)
                if gate.get("decision") == "refuse":
                    result = {"error": gate.get("reason") or "terminal safety gate refused the command"}
                elif gate.get("decision") == "plan":
                    result = te.plan(cmd, surface)
                elif gate.get("decision") == "confirm":
                    return _propose_actions([(tool, args, risk)], chat_id, surface, used, intent)
                else:
                    result = _execute_terminal_and_log(chat_id, surface, tool, args, risk, on_event)
            else:
                if risk == "high" and review_mode != "always":
                    return _propose_actions([(tool, args, risk)], chat_id, surface, used, intent)
                result = _execute_and_log(chat_id, surface, tool, args, risk, mode=mode,
                                          allowed_tools=allowed_tools, turn_id=turn_id, step_index=0)
            used.append(tool)
            msgs.append({"role": "user", "content":
                         f"CHECKPOINT_RETRY_RESULT {tool}: {json.dumps(result, default=str)[:3000]}"})
            if isinstance(result, dict) and result.get("error"):
                failed_now = {"tool": tool, "args": args, "risk": risk, "error": result["error"]}
                return {"reply": _failure_report([], _action_summary(tool, args), result["error"]),
                        "tools_used": used, "intent": intent, "stopped_on_error": True,
                        "failed_step": failed_now, "streamed": False}
            done_acts.append(_action_summary(tool, args))
        elif command == "skip_step" and tool:
            msgs.append({"role": "user", "content":
                         f"CHECKPOINT_SKIPPED {tool}: the owner explicitly skipped this failed step. "
                         "Continue only with remaining work; do not call it again."})
        elif command == "revise" and recovery_checkpoint.get("revision"):
            msgs.append({"role": "user", "content":
                         "PLAN_REVISION: " + str(recovery_checkpoint["revision"])[:1000]})
        elif command == "resume":
            msgs.append({"role": "user", "content":
                         "RESUME_CHECKPOINT: continue after the last persisted completed step."})

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
            # One explicit, visible escalation for malformed output. This runs only after the
            # invalid response has been buffered/retracted, never after a valid partial answer.
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
                    retry, retry_is_answer, _ = _gen_step(
                        stronger, retry_msgs, system, final_tokens or FINAL_TOKENS, on_delta, on_reset)
                    retry_clean, retry_reasoning = _strip_reasoning(retry)
                    if retry_is_answer and retry_clean and not _parse_tool_call(retry_clean):
                        return {"reply": retry_clean, "reasoning": retry_reasoning,
                                "tools_used": used, "intent": intent, "streamed": bool(on_delta),
                                "model_escalated": stronger_id}
            except Exception as exc:
                logger.warning("conductor model escalation failed: %s", exc)
            return {"reply": _MODEL_STRUGGLING, "tools_used": used, "intent": intent,
                    "model_issue": True, "streamed": False}
        return {"reply": clean, "reasoning": reasoning, "tools_used": used,
                "intent": intent, "streamed": bool(on_delta)}

    if not tools_enabled:
        _final_tokens = final_tokens or FINAL_TOKENS
        text, _isa, fr = _gen_step(client, msgs, system, _final_tokens, on_delta)
        if fr == "length":
            text += _continue_answer(client, msgs, text, system, on_delta)
        return _final(text)

    tool_step_index = 0
    for _ in range(max_tool_steps or MAX_TOOL_STEPS):
        text, is_answer, fr = _gen_step(client, msgs, system, step_tokens or STEP_TOKENS, on_delta, on_reset)
        if not text:
            step_fails += 1
            if step_fails > MAX_STEP_RETRIES:
                return {"reply": _MODEL_STRUGGLING, "tools_used": used, "intent": intent, "model_issue": True, "streamed": False}
            continue
        if is_answer:
            if fr == "length":
                text += _continue_answer(client, msgs, text, system, on_delta)
            return _final(text)

        calls = _parse_tool_calls(text)
        if not calls:
            # It looked like a tool call but the JSON was truncated/garbled → retry, stricter.
            step_fails += 1
            if step_fails > MAX_STEP_RETRIES:
                return {"reply": _MODEL_STRUGGLING, "tools_used": used, "intent": intent, "model_issue": True, "streamed": False}
            msgs.append({"role": "assistant", "content": text[:600]})
            msgs.append({"role": "user", "content": "That tool call was incomplete or invalid. Reply with ONLY "
                         "a single-line JSON object exactly like {\"tool\": \"<name>\", \"args\": {}} — no prose, "
                         "no markdown, no commentary."})
            continue

        # Execute EVERY call in this message (a model may batch 'create 2 projects' into one reply).
        # High-risk calls are COLLECTED and proposed together at the end (one confirmation card).
        msgs.append({"role": "assistant", "content": text})
        highs: list[tuple] = []
        for call in calls:
            tool_step_index += 1
            tool = call["tool"]
            args = call.get("args") or {}
            if not isinstance(args, dict):
                args = {}
            risk = RISK.get(tool, "read")

            # ── Mode capability boundary (#16 [D11][D23]): a tool the mode forbids is rejected
            # server-side even if the model calls it anyway (Chat can't run terminal tools). Feed
            # a denial back so the model adjusts and tells the owner to switch to Agent mode. ──
            if tool in denied_tools:
                msgs.append({"role": "user", "content": f"TOOL_RESULT {tool}: " + json.dumps(
                    {"denied": True, "reason": f"{tool} is not available in this mode — shell/terminal "
                     "actions require Agent mode. Tell the owner to switch modes; do not retry."})})
                continue
            # Read tools bypass the route-scope gate entirely — they're safe, non-mutating,
            # and blocking them was the root cause of "list_projects is blocked" / tool.route_denied.
            # Only ACT tools (mutations) are gated by the route's allowed_tools set.
            is_read = tool in READ_TOOLS or tool in OPTIONAL_TOOLS
            if not is_read and allowed_tools is not None and tool not in allowed_tools:
                available = sorted(t for t in (allowed_tools or set())
                                   if t in READ_TOOLS or t in OPTIONAL_TOOLS)
                msgs.append({"role": "user", "content": f"TOOL_RESULT {tool}: " + json.dumps(
                    {"denied": True, "error_code": "tool.route_denied",
                     "reason": f"'{tool}' isn't an available tool this turn. Use one of these "
                               f"instead: {', '.join(available) or '(none)'}. Do NOT tell the owner "
                               f"to change permissions or re-authorize — pick a real tool and continue."})})
                continue
            validation_error = _tool_registry.validate_call(
                call, TOOL_SPECS.get(tool), mode, allowed_tools
            )
            if validation_error:
                msgs.append({"role": "user", "content": f"TOOL_RESULT {tool}: " + json.dumps({
                    "error": validation_error.message, "error_code": validation_error.code,
                    "stage": validation_error.stage, "retryable": validation_error.retryable,
                })})
                continue

            if on_event:
                try:
                    on_event({"type": "thinking", "phase": _phase_for(tool), "tool": tool})
                except Exception:
                    pass

            # ── outline_plan (#16 D9): surface the declared plan as a structured event ──
            if tool == "outline_plan":
                result = _exec_tool(call, mode=mode, allowed_tools=allowed_tools,
                                    turn_id=turn_id, step_index=tool_step_index)
                if on_event and isinstance(result, dict) and result.get("ok"):
                    try:
                        on_event({"type": "plan", "steps": result["steps"], "title": result.get("title", "")})
                    except Exception:
                        pass
                used.append(tool)
                msgs.append({"role": "user", "content": f"TOOL_RESULT {tool}: {json.dumps(result, default=str)[:3000]}"})
                continue

            # ── Terminal tools (#11): the two-axis engine (mode × command risk) decides ──
            if tool in TERMINAL_TOOLS:
                from core import terminal_engine as te
                cmd = _terminal_command_for(tool, args)
                if not cmd:
                    result = _exec_tool(call, mode=mode, allowed_tools=allowed_tools,
                                        turn_id=turn_id, step_index=tool_step_index)
                else:
                    g = te.gate(cmd, surface=surface)
                    decision, trisk = g["decision"], g["risk"]
                    if decision == "refuse":
                        result = {"refused": True, "risk": trisk, "reason": g["reason"], "command": cmd}
                    elif decision == "plan":
                        result = te.plan(cmd, surface)
                    elif decision == "confirm":
                        highs.append((tool, args, trisk))  # propose with the command's real risk
                        continue
                    else:  # run
                        terminal_receipt = None
                        if turn_id:
                            terminal_call = _tool_registry.ToolCall(tool, args)
                            terminal_receipt = _tool_registry.receipt_key(
                                turn_id, tool_step_index, terminal_call)
                        replay = _tool_registry.load_receipt(terminal_receipt) if terminal_receipt else None
                        if replay is not None:
                            result = dict(replay)
                            result["receipt_key"] = terminal_receipt
                            result["replayed"] = True
                        else:
                            result = _execute_terminal_and_log(chat_id, surface, tool, args, trisk, on_event)
                            if terminal_receipt and not result.get("error"):
                                _tool_registry.store_receipt(
                                    terminal_receipt, turn_id, tool, args, result)
                                result = dict(result)
                                result["receipt_key"] = terminal_receipt
                                result["replayed"] = False
                        if not (isinstance(result, dict) and result.get("error")):
                            done_acts.append(_action_summary(tool, args))
                used.append(tool)
                msgs.append({"role": "user", "content": f"TOOL_RESULT {tool}: {json.dumps(result, default=str)[:3000]}"})
                continue

            if surface == "telegram" and risk in ("medium", "high"):
                result = {"blocked": f"That's a {risk}-risk change, sir — please do it from Mission Control "
                                     "(Telegram stays read-only and safe)."}
            elif risk == "high" and review_mode != "always":
                # Ask/session retain the destructive-action checkpoint. Autonomous mode is an
                # explicit owner choice enforced here rather than silently approved by the UI.
                highs.append((tool, args))
                continue
            elif risk == "read":
                result = _exec_tool(call, mode=mode, allowed_tools=allowed_tools,
                                    turn_id=turn_id, step_index=tool_step_index)
                # #17: audit workflow read-tools (summarize_repo) to Actions. A receipt only
                # counts as 'executed' when the read genuinely succeeded (available, no error).
                if tool in _WORKFLOW_READ_TOOLS and not (isinstance(result, dict) and result.get("__picker__")):
                    _ok = isinstance(result, dict) and result.get("available") and not result.get("error")
                    try:
                        _log_action(chat_id, surface, tool, args, "read",
                                    "executed" if _ok else "failed", _action_summary(tool, args), result)
                    except Exception:
                        pass
                # Picker sentinel: halt the turn and surface an interactive wizard to the
                # owner (the answers arrive as his next message — session-scoped context).
                if isinstance(result, dict) and result.get("__picker__"):
                    picker = result["__picker__"]
                    return {"reply": _picker_intro(picker), "tools_used": used + [tool],
                            "intent": intent, "pending_picker": picker, "streamed": False}
            else:  # low / medium (and high under autonomous mode) → act + report
                if review_mode == "ask":
                    highs.append((tool, args, risk))
                    continue
                try:
                    result = _execute_and_log(chat_id, surface, tool, args, risk, mode=mode,
                                              allowed_tools=allowed_tools, turn_id=turn_id,
                                              step_index=tool_step_index)
                except TypeError as exc:
                    # Compatibility for existing callers/tests that monkeypatch the historical
                    # five-argument helper. Do not mask TypeErrors raised by the real helper.
                    if "unexpected keyword argument" not in str(exc):
                        raise
                    result = _execute_and_log(chat_id, surface, tool, args, risk)
                # Stop-on-failure: a failed state change halts the chain and reports cleanly.
                if isinstance(result, dict) and result.get("error"):
                    failed_step = {"tool": tool, "args": args, "risk": risk, "error": result["error"]}
                    return {"reply": _failure_report(done_acts, _action_summary(tool, args), result["error"]),
                            "tools_used": used + [tool], "intent": intent, "stopped_on_error": True,
                            "failed_step": failed_step, "streamed": False}
                done_acts.append(_action_summary(tool, args))

            used.append(tool)
            msgs.append({"role": "user", "content": f"TOOL_RESULT {tool}: {json.dumps(result, default=str)[:3000]}"})

        if highs:  # one or more high-risk actions → propose them (batched) and wait for the owner
            return _propose_actions(highs, chat_id, surface, used, intent)

    # Step budget exhausted → force a complete, grounded final answer from the gathered results.
    msgs.append({"role": "user", "content": "Now give your final answer to the owner using only the tool "
                 "results above. Do not call any more tools. Answer fully and do not stop mid-sentence."})
    _final_tokens = final_tokens or FINAL_TOKENS
    text, is_ans, fr = _gen_step(client, msgs, system, _final_tokens, on_delta, on_reset)
    # A weak model may STILL emit a tool-call JSON here instead of answering. One blunt prose-only
    # retry (on_reset retracts any live leak) so the owner gets a real answer — never raw JSON.
    if not is_ans:
        msgs.append({"role": "assistant", "content": text[:600]})
        msgs.append({"role": "user", "content": "Answer in plain prose for the owner now. Do NOT output "
                     "JSON and do NOT call any tool — just summarise what the tool results above show."})
        text, is_ans, fr = _gen_step(client, msgs, system, _final_tokens, on_delta, on_reset)
    if fr == "length":
        text += _continue_answer(client, msgs, text, system, on_delta)
    return _final(text)


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


def _stream_chunks(text: str):
    """Split a finished answer into small pieces so the chat reveals it like a stream."""
    buf = ""
    for piece in re.findall(r"\S+\s*", text):
        buf += piece
        if len(buf) >= 18:
            yield buf
            buf = ""
    if buf:
        yield buf


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

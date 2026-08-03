"""Premium Chat (#8) + Agent-runs API — /api/chat/* .

Extracted from api/dashboard.py (refactor Slice — pre-#21 decomposition). Byte-
identical: 8 chat request models + 19 routes (chat config, session CRUD, the
streaming turn handler, message feedback, agent runs/commands/trace, artifacts,
compact); only @app.* -> @router.*. The heavy runtime deps (conductor, model_router,
chat_store, attachments, agent_runs) are imported inline inside the handlers and
move unchanged with them. Module-level free-var set verified by isolated-pyflakes
analysis. See docs/REFACTORING_PLAN.md.
"""
from __future__ import annotations

import asyncio  # noqa: F401 - used by streaming/background handlers
import json  # noqa: F401 - used by some handlers
import logging
from typing import Optional  # noqa: F401 - used in models/signatures

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from core import brain

router = APIRouter(tags=["chat"])
logger = logging.getLogger(__name__)
_SHADOW_IO_TIMEOUT_S = 0.10
_ACTIVE_IO_TIMEOUT_S = 0.40


# ── Premium Chat (#8 P1): multi-model sessions + vault-backed LLM config ─────────
class ChatSessionCreate(BaseModel):
    title: str | None = None
    model: str | None = None


class ChatSessionPatch(BaseModel):
    title: str | None = None
    model: str | None = None


class ChatSendReq(BaseModel):
    message: str
    model: str | None = None
    attachments: list[dict] = Field(default_factory=list)   # {name,mime,kind,text?,data_url?}
    web_research: bool = False
    thinking: bool = False
    connectors: list[str] = Field(default_factory=list)     # enabled connector ids for this turn
    # ── Chat Mode contract (#16) — old clients simply omit these (→ chat mode) ──
    mode: str | None = None                                  # 'chat' | 'agent' (+ legacy labels)
    deep_research: bool = False                              # one-message Deep Research toggle
    review_mode: str | None = None                           # 'ask' | 'session' | 'always'
    client_turn_id: str | None = None                        # runtime trace/idempotency correlation
    resume_run_id: int | None = None                         # continue an existing paused Agent run


class ChatAppendReq(BaseModel):
    role: str = "assistant"
    content: str


class ChatForkReq(BaseModel):
    before_message_id: int


class ChatFeedbackReq(BaseModel):
    value: int | None = None    # 1 👍 | -1 👎 | null clear


class AgentRunCommandReq(BaseModel):
    command: str
    revision: str = ""


def _chat_directives(web_research: bool, thinking: bool, connectors: list[str]) -> str | None:
    """Legacy directive builder — superseded by core.chat_modes.build_directives (#16),
    kept for rollback parity (its chat-mode output is line-identical)."""
    lines = []
    if web_research:
        lines.append("- Web research: use the web_search tool for anything current/factual and cite the sources you use in a ```tobi:reference``` block.")
    if connectors:
        lines.append(f"- Connectors: {', '.join(connectors)} — prefer their tools (e.g. read_notion / read_github) when relevant.")
    if thinking:
        lines.append("- Briefly show your reasoning before the final answer.")
    return "\n".join(lines) or None


class ChatConfigReq(BaseModel):
    mode_v2: Optional[bool] = None
    premium_readers: Optional[bool] = None   # #14 rollback flag (YouTube/reader layer)
    chat_runtime_v2: Optional[str] = None    # off | shadow | on


@router.get("/api/chat/config")
def chat_config_get():
    """Chat feature flags — the frontend picks the v2 Chat/Agent UI vs the legacy five-mode
    UI (#16), plus the #14 premium-reader rollback flag, both from owner_settings."""
    from core import chat_modes, premium_readers, chat_runtime
    return {"mode_v2": chat_modes.mode_v2_enabled(),
            "premium_readers": premium_readers.premium_readers_enabled(),
            "chat_runtime_v2": chat_runtime.runtime_mode()}


@router.post("/api/chat/config")
def chat_config_set(body: ChatConfigReq):
    from core import chat_modes, premium_readers, chat_runtime
    if body.mode_v2 is not None:
        chat_modes.set_mode_v2(body.mode_v2)
    if body.premium_readers is not None:
        premium_readers.set_premium_readers(body.premium_readers)
    if body.chat_runtime_v2 is not None:
        chat_runtime.set_runtime_mode(body.chat_runtime_v2)
    return {"mode_v2": chat_modes.mode_v2_enabled(),
            "premium_readers": premium_readers.premium_readers_enabled(),
            "chat_runtime_v2": chat_runtime.runtime_mode()}


@router.get("/api/chat/sessions")
def chat_sessions_list():
    from core import chat_store
    return {"sessions": chat_store.list_sessions()}


@router.post("/api/chat/sessions")
def chat_session_create(body: ChatSessionCreate):
    from core import chat_store
    return chat_store.create_session(title=body.title, model=body.model)


@router.get("/api/chat/sessions/{sid}")
def chat_session_get(sid: int):
    from core import chat_store
    sess = chat_store.get_session(sid)
    if not sess:
        raise HTTPException(status_code=404, detail="session not found")
    return {"session": sess, "messages": chat_store.get_messages(sid)}


@router.patch("/api/chat/sessions/{sid}")
def chat_session_patch(sid: int, body: ChatSessionPatch):
    from core import chat_store
    sess = chat_store.update_session(sid, title=body.title, model=body.model)
    if not sess:
        raise HTTPException(status_code=404, detail="session not found")
    return sess


@router.delete("/api/chat/sessions/{sid}")
def chat_session_delete(sid: int):
    from core import chat_store
    chat_store.delete_session(sid)
    return {"ok": True}


@router.post("/api/chat/sessions/{sid}/append")
def chat_session_append(sid: int, body: ChatAppendReq):
    """Persist a message the client produced out-of-band (e.g. a confirmed high-risk
    action result) into the session so it survives a reload."""
    from core import chat_store
    if not chat_store.get_session(sid):
        raise HTTPException(status_code=404, detail="session not found")
    mid = chat_store.add_message(sid, body.role, body.content)
    return {"ok": True, "id": mid}


@router.post("/api/chat/sessions/{sid}/stream")
async def chat_session_stream(sid: int, payload: ChatSendReq, request: Request):
    """Premium chat turn over SSE with **typed events**: `thinking` (phase + tool chips),
    `delta` (smoothed answer chunks), `action` (a high-risk act awaiting confirmation),
    `usage` (tokens + latency), then `done`. Conductor-powered, per-session model + history.
    P2: folds in **attachments** (text → context, images → native vision), an opt-in
    **web_search** tool and **connector** emphasis, all gated by the chat's `+` menu."""
    from core import chat_store, conductor, model_router, attachments as attach
    from core import premium_readers, youtube_reader, chat_modes, chat_runtime, context_manager
    from core.chat_runtime_contracts import TurnError, TurnRequest
    from core.runtime import config as runtime_config
    from core.runtime.gateway import TurnGateway, submit_gateway_accept, submit_gateway_mirror
    from core.task_classifier import classify
    import time as _time

    sess = chat_store.get_session(sid)
    if not sess:
        raise HTTPException(status_code=404, detail="session not found")
    message = (payload.message or "").strip()
    model = (payload.model or sess.get("model") or "").strip() or None
    images, att_text = attach.split(payload.attachments)
    img_urls = attach.image_data_urls(images)
    # ── Mode contract (#16): normalize the raw mode + toggles into a resolved context.
    # Flag off → the new fields are ignored (mode forced to chat) and no mode event is
    # emitted, so behavior is identical to the pre-#16 route [D29].
    mode_v2 = chat_modes.mode_v2_enabled()
    if mode_v2:
        ctx = chat_modes.normalize(payload.mode, payload.web_research, payload.deep_research,
                                   payload.connectors, payload.review_mode)
    else:
        ctx = chat_modes.normalize(None, payload.web_research, False, payload.connectors)
    directives = chat_modes.build_directives(ctx, thinking=payload.thinking)
    extra_tools = chat_modes.extra_tools_for(ctx)
    # Mode capability boundary (#16 [D11][D23]) + Human Review policy — enforced server-side by
    # the Conductor, so the selected mode is a real backend capability, not just prompting.
    denied_tools = chat_modes.denied_tools_for(ctx) if mode_v2 else set()
    review_mode = ctx.get("review_mode") if mode_v2 else None
    runtime_state = chat_runtime.runtime_mode()
    runtime_request = TurnRequest(
        session_id=sid, message=message, mode=ctx["mode"], model=model,
        client_turn_id=(payload.client_turn_id or None), resume_run_id=payload.resume_run_id,
        capabilities=ctx.get("capabilities") or {},
    )
    try:
        runtime_intent = classify(message)
    except Exception:
        runtime_intent = "QUESTION"
    route_decision = chat_runtime.route_turn(runtime_request, runtime_intent)
    runtime_active = runtime_state == "on"
    direct_chat_ready = bool(
        runtime_active
        and runtime_request.mode == "chat"
        and route_decision.route == "direct"
        and not route_decision.requires_clarification
        and not payload.attachments
    )
    expected_gateway_mode = runtime_config.surface_gateway_mode(
        runtime_request.mode, activation_ready=direct_chat_ready
    )
    runtime_allowed = None
    if runtime_active and route_decision.allowed_tools:
        runtime_allowed = set(route_decision.allowed_tools) | set(extra_tools or [])
    # "direct" route no longer starves the tool catalog — leaving runtime_allowed=None
    # means all tools are available, so the LLM can call a read tool even when the
    # classifier didn't predict one.  This was the root cause of "list projects is blocked."

    async def gen():
        loop = asyncio.get_event_loop()

        async def poll_background_result(future, timeout: float):
            deadline = loop.time() + timeout
            while not future.done():
                remaining = deadline - loop.time()
                if remaining <= 0:
                    return False, None
                await asyncio.sleep(min(0.01, remaining))
            return True, future.result()

        if not message and not img_urls and not att_text:
            yield "event: done\ndata: {}\n\n"
            return
        runtime_gateway = TurnGateway()
        gateway_acceptance = None
        accept_future = submit_gateway_accept(
            lambda: runtime_gateway.accept_turn(
                runtime_request,
                attachments=payload.attachments,
                activation_ready=direct_chat_ready,
            )
        )
        if accept_future is not None:
            try:
                completed, result = await poll_background_result(
                    accept_future,
                    _ACTIVE_IO_TIMEOUT_S
                    if expected_gateway_mode == "on"
                    else _SHADOW_IO_TIMEOUT_S,
                )
                if completed:
                    gateway_acceptance = result
                else:
                    logger.warning("Runtime V2 gateway acceptance timed out")
            except Exception as exc:
                logger.warning(
                    "Runtime V2 gateway acceptance failed: %s",
                    type(exc).__name__,
                )
        else:
            logger.warning("Runtime V2 gateway acceptance queue is full")

        if expected_gateway_mode == "on" and gateway_acceptance is None:
            yield "event: error\ndata: " + json.dumps({
                "detail": "TOBI could not safely start this reply. Please retry the request."
            }) + "\n\n"
            yield "event: done\ndata: {}\n\n"
            return

        canonical_execution = None
        canonical_active = bool(
            gateway_acceptance is not None
            and gateway_acceptance.mode == "on"
            and gateway_acceptance.run_id
        )
        if canonical_active:
            prepare_future = submit_gateway_accept(
                lambda: runtime_gateway.prepare_direct_chat(gateway_acceptance)
            )
            try:
                if prepare_future is None:
                    raise RuntimeError("gateway execution queue is full")
                completed, canonical_execution = await poll_background_result(
                    prepare_future, _ACTIVE_IO_TIMEOUT_S
                )
                if not completed:
                    raise TimeoutError("gateway execution preparation timed out")
            except Exception as exc:
                logger.warning(
                    "Runtime V2 direct Chat preparation failed: %s", type(exc).__name__
                )
                yield "event: error\ndata: " + json.dumps({
                    "detail": "TOBI could not safely prepare this reply. Please retry the request."
                }) + "\n\n"
                yield "event: done\ndata: {}\n\n"
                return
            if canonical_execution.disposition in {"in_progress", "recovery"}:
                detail = (
                    "This reply is already running. Please wait a moment and retry."
                    if canonical_execution.disposition == "in_progress"
                    else "This reply needs recovery. Please send the request again."
                )
                yield f"event: error\ndata: {json.dumps({'detail': detail})}\n\n"
                yield "event: done\ndata: {}\n\n"
                return

        recorder = (chat_runtime.TurnRecorder.start(runtime_request, route_decision)
                    if runtime_state in ("shadow", "on") else None)
        shadow_active = bool(
            gateway_acceptance is not None
            and gateway_acceptance.mode == "shadow"
            and gateway_acceptance.run_id
        )
        runtime_tracking = recorder is not None or shadow_active or canonical_active
        shadow_source_sequence = 0

        def _shadow_done(future):
            try:
                future.result()
            except Exception as exc:
                logger.warning(
                    "Runtime V2 shadow observation failed; legacy turn continues: %s",
                    type(exc).__name__,
                )

        def shadow_observe(event_type: str, stage: str, data: Optional[dict] = None) -> None:
            nonlocal shadow_source_sequence
            if not shadow_active:
                return
            shadow_source_sequence += 1
            future = submit_gateway_mirror(
                runtime_gateway,
                gateway_acceptance,
                source_sequence=shadow_source_sequence,
                event_type=event_type,
                stage=stage,
                payload=data or {},
            )
            if future is None:
                logger.warning("Runtime V2 shadow observation queue is full; event dropped")
            else:
                future.add_done_callback(_shadow_done)

        def runtime_frame(event_type: str, stage: str, data: Optional[dict] = None) -> str:
            shadow_observe(event_type, stage, data)
            if recorder is None:
                return ""
            envelope = recorder.event(event_type, stage, data or {})
            return f"event: {event_type}\ndata: {json.dumps(envelope)}\n\n"

        def runtime_event(event_type: str, stage: str, data: Optional[dict] = None) -> None:
            shadow_observe(event_type, stage, data)
            if recorder is not None:
                recorder.event(event_type, stage, data or {})

        def runtime_complete(status: str, error=None) -> None:
            if recorder is not None:
                recorder.complete(status, error)

        async def link_shadow_run(legacy_run_id: int) -> None:
            if not shadow_active:
                return
            future = submit_gateway_accept(
                lambda: runtime_gateway.link_legacy_run(gateway_acceptance, legacy_run_id)
            )
            if future is None:
                logger.warning("Runtime V2 legacy-link queue is full; legacy turn continues")
                return
            try:
                completed, _result = await poll_background_result(
                    future, _SHADOW_IO_TIMEOUT_S
                )
                if completed:
                    return
                else:
                    logger.warning("Runtime V2 legacy-link timed out; legacy turn continues")
            except Exception as exc:
                logger.warning(
                    "Runtime V2 legacy-link failed; legacy turn continues: %s",
                    type(exc).__name__,
                )

        if runtime_tracking:
            yield runtime_frame("turn_started", "gateway", {
                "route": route_decision.route, "intent": route_decision.intent,
                "confidence": route_decision.confidence, "runtime_mode": runtime_state,
            })
        # Echo the normalized mode as the FIRST frame so the UI can chip it before
        # anything streams (#16). Old clients silently ignore unknown SSE events.
        if mode_v2:
            yield f"event: mode\ndata: {json.dumps({'mode': ctx['mode'], 'legacy_mode': ctx['legacy_mode'], 'capabilities': ctx['capabilities']})}\n\n"
        if canonical_active and canonical_execution.disposition == "replay":
            replayed = await loop.run_in_executor(
                None,
                lambda: chat_store.get_runtime_response(sid, canonical_execution.run_id),
            )
            if replayed is None:
                runtime_complete("failed")
                yield "event: error\ndata: " + json.dumps({
                    "detail": "TOBI found the completed run but not its reply. Please send a new message."
                }) + "\n\n"
                yield "event: done\ndata: {}\n\n"
                return
            for chunk in conductor._stream_chunks(replayed["content"]):
                yield f"event: delta\ndata: {json.dumps({'text': chunk})}\n\n"
            yield f"event: usage\ndata: {json.dumps({
                'prompt_tokens': 0,
                'completion_tokens': int(replayed.get('tokens') or 0),
                'model': replayed.get('model') or 'not_used',
                'requested_model': replayed.get('model'),
                'actual_model': replayed.get('model'),
                'fallback_reason': None,
                'attempts': 0,
                'latency_ms': 0,
                'replayed': True,
            })}\n\n"
            runtime_complete("succeeded")
            yield runtime_frame(
                "turn_completed", "gateway", {"status": "done", "replayed": True}
            )
            yield "event: done\ndata: {}\n\n"
            return
        cid = chat_store.chat_id_for_session(sid)
        from core.database import save_conversation_message as _bridge_msg
        history = await loop.run_in_executor(None, lambda: chat_store.recent_history(sid, limit=8))
        stored_user = message + (f"  📎×{len(payload.attachments)}" if payload.attachments else "")
        await loop.run_in_executor(None, lambda: chat_store.add_message(sid, "user", stored_user, model=model))
        await loop.run_in_executor(None, lambda: _bridge_msg(cid, "user", message))
        await loop.run_in_executor(None, lambda: chat_store.auto_title(sid, message or "Attachment"))
        t0 = _time.time()

        # A clear request to mutate state from Chat mode does not need an LLM round-trip.
        # The clarification gate gives one deterministic, recoverable instruction instead.
        if runtime_active and route_decision.requires_clarification:
            reply = "Switch this conversation to **Agent** mode and send the request again, sir — it requires execution tools."
            for chunk in conductor._stream_chunks(reply):
                yield f"event: delta\ndata: {json.dumps({'text': chunk})}\n\n"
            await loop.run_in_executor(None, lambda: chat_store.add_message(
                sid, "assistant", reply, model=model,
                meta=json.dumps({"mode": ctx["mode"], "turn_id": recorder.turn_id if recorder else None})))
            await loop.run_in_executor(None, lambda: _bridge_msg(cid, "assistant", reply))
            if runtime_tracking:
                yield runtime_frame("recovery_required", "clarification", {
                    "code": "turn.agent_mode_required", "actions": ["switch_to_agent"],
                    "message": route_decision.reason,
                })
                runtime_complete("waiting_user", TurnError(
                    "turn.agent_mode_required", "clarification", route_decision.reason, False))
                yield runtime_frame("turn_completed", "gateway", {"status": "waiting_user"})
            yield "event: done\ndata: {}\n\n"
            return

        # ── Premium readers (#14): read YouTube transcripts referenced in the message
        # BEFORE answering, so both the vision and tool-loop paths get the context. A
        # pasted link is treated as consent to fetch [spec]. Honest notice if unavailable.
        reader = premium_readers.ReaderResult()
        if youtube_reader.find_youtube_urls(message):
            yield f"event: thinking\ndata: {json.dumps({'phase': 'Reading the YouTube transcript…', 'tools': ['youtube']})}\n\n"
            try:
                # Bounded so a slow/hanging transcript fetch can't stall the whole turn (#14
                # follow-up). On timeout the fetch is abandoned (its result discarded) and we
                # continue honestly without the transcript. It runs on a DEDICATED bounded pool
                # so repeated hangs can never exhaust the app-wide default executor.
                reader = await asyncio.wait_for(
                    loop.run_in_executor(premium_readers.reader_executor(),
                                         lambda: premium_readers.read_message(message)),
                    timeout=premium_readers.READER_TIMEOUT_S)
            except asyncio.TimeoutError:
                reader = premium_readers.timeout_result(message)
            yield f"event: notice\ndata: {json.dumps(premium_readers.notice_payload(reader))}\n\n"

        # Turn metadata (#16) — persisted onto the assistant message so mode/chips/steps
        # survive a reload. Empty (→ NULL column) when the flag is off.
        turn_meta: dict = ({"mode": ctx["mode"], "legacy_mode": ctx["legacy_mode"],
                            "capabilities": ctx["capabilities"]} if mode_v2 else {})
        if recorder:
            turn_meta["turn_id"] = recorder.turn_id

        # ── Auto project context (#16 [D19][D20]): detect a referenced PM project and
        # inject a read-only summary as evidence; visible to the owner as chips. Skipped
        # for Deep Research turns (web-focused) and when the flag is off. ──
        pctx = {"projects": [], "resources": [], "context_text": ""}
        if mode_v2 and message and not ctx["capabilities"]["deep_research"]:
            pctx = await loop.run_in_executor(None, lambda: chat_modes.detect_project_context(message))
            if pctx["projects"]:
                yield f"event: context\ndata: {json.dumps({'projects': pctx['projects'], 'resources': pctx['resources'], 'auto': True})}\n\n"
                turn_meta["context"] = {"projects": pctx["projects"], "resources": pctx["resources"]}

        manifest = None
        if runtime_state in ("shadow", "on"):
            base_attachment_context = premium_readers.compose_context(att_text, reader)
            manifest = await loop.run_in_executor(None, lambda: context_manager.build_manifest(
                message, ctx["mode"], history, pctx, base_attachment_context))
            if recorder:
                recorder.set_context(manifest.to_dict())
            if runtime_tracking:
                yield runtime_frame("context_ready", "context", {
                    "total_tokens": manifest.total_tokens,
                    "token_budget": manifest.token_budget,
                    "sources": [{"source": i.source, "label": i.label, "trust": i.trust,
                                 "tokens": i.token_cost} for i in manifest.items],
                })
            # #20 review P1: surface per-memory feedback chips (each carries memory_id,
            # scope, quality) so the owner can rate every recalled memory useful/
            # irrelevant/wrong. They live in the brain_recall item metadata; emit them
            # on the stream and persist onto the turn so they survive a reload.
            _recall = next((i for i in manifest.items if i.source == "brain_recall"), None)
            _mem_chips = list((_recall.metadata or {}).get("chips") or []) if _recall else []
            if _mem_chips:
                yield f"event: memory_chips\ndata: {json.dumps({'chips': _mem_chips})}\n\n"
                turn_meta["memory_chips"] = _mem_chips

        # ── Deep Research (#16 [D14][D15]): one-message cited-report workflow. Beats the
        # vision path (an explicit command wins over an implicit affordance — images are
        # skipped with an honest notice); YouTube/attachment context rides in as evidence. ──
        if mode_v2 and ctx["capabilities"]["deep_research"]:
            from core import deep_research
            if runtime_tracking:
                yield runtime_frame("step_started", "deep_research", {"label": "Deep Research"})
            if img_urls:
                yield f"event: notice\ndata: {json.dumps({'kind': 'dr_images_skipped'})}\n\n"
            dr_q: asyncio.Queue = asyncio.Queue()

            def _emit_step(step, phase):
                try:
                    loop.call_soon_threadsafe(dr_q.put_nowait, {"step": step, "phase": phase})
                except Exception:
                    pass

            dr_ctx = premium_readers.compose_context(att_text, reader)
            fut = loop.run_in_executor(None, lambda: deep_research.run(
                message, context_text=dr_ctx, on_step=_emit_step, model=model))
            try:
                while not fut.done() or not dr_q.empty():
                    try:
                        ev = await asyncio.wait_for(dr_q.get(), timeout=0.12)
                    except asyncio.TimeoutError:
                        continue
                    yield f"event: thinking\ndata: {json.dumps({'phase': ev.get('phase', ''), 'tools': ['deep_research']})}\n\n"
                dr = await fut
            except Exception as e:
                if runtime_tracking:
                    err = TurnError("research.failed", "deep_research", "Deep Research failed", True, str(e)[:200])
                    yield runtime_frame("step_failed", "deep_research", err.to_dict())
                    runtime_complete("failed", err)
                yield f"event: error\ndata: {json.dumps({'detail': str(e)[:200]})}\n\n"
                yield "event: done\ndata: {}\n\n"
                return
            report = dr.get("report_md") or "I couldn't produce the report, sir."
            for chunk in conductor._stream_chunks(report):
                yield f"event: delta\ndata: {json.dumps({'text': chunk})}\n\n"
            title = f"Research: {message[:80]}"
            aid = await loop.run_in_executor(None, lambda: chat_store.add_artifact(
                sid, "research_report", title, report,
                meta_json=json.dumps({"queries": dr.get("queries") or [],
                                      "source_count": len(dr.get("sources") or []),
                                      "caveats": dr.get("caveats") or []})))
            yield f"event: artifact\ndata: {json.dumps({'id': aid, 'kind': 'research_report', 'title': title})}\n\n"
            turn_meta["artifact_ids"] = [aid]
            ctok = model_router.estimate_tokens(report)
            await loop.run_in_executor(None, lambda: chat_store.add_message(
                sid, "assistant", report, model=model, tokens=ctok, thinking="Deep Research",
                meta=json.dumps(turn_meta) if turn_meta else None))
            await loop.run_in_executor(None, lambda: _bridge_msg(cid, "assistant", report))
            usage = {"prompt_tokens": model_router.estimate_tokens(message + dr_ctx),
                     "completion_tokens": ctok,
                     "model": dr.get("actual_model") or dr.get("requested_model") or model or "not_used",
                     "requested_model": dr.get("requested_model") or model,
                     "actual_model": dr.get("actual_model"),
                     "fallback_reason": dr.get("fallback_reason"),
                     "attempts": dr.get("model_attempts") or 0,
                     "latency_ms": round((_time.time() - t0) * 1000)}
            yield f"event: usage\ndata: {json.dumps(usage)}\n\n"
            if runtime_tracking:
                yield runtime_frame("step_completed", "deep_research", {"artifact_id": aid})
                runtime_complete("done")
                yield runtime_frame("turn_completed", "gateway", {"status": "done"})
            yield "event: done\ndata: {}\n\n"
            return

        # ── Vision path: read image attachments with a vision-capable model. If the chat's
        # selected model can't see images, AUTO-BORROW an available vision model (#14) so the
        # owner never has to switch models just to read a screenshot — image reading no longer
        # depends on the chosen model. Only refuses when no vision model is connected at all. ──
        vmodel = model or model_router.load_llm_config().get("default_model") or ""
        vision_model = vmodel if (vmodel and model_router.supports_vision(vmodel)) else None
        borrowed = False
        if img_urls and not vision_model:
            alt = model_router.first_vision_model()
            if alt:
                vision_model, borrowed = alt, True
        if img_urls and vision_model:
            if runtime_tracking:
                yield runtime_frame("step_started", "vision", {"model": vision_model})
            yield f"event: thinking\ndata: {json.dumps({'phase': 'Looking at the image…', 'tools': ['vision']})}\n\n"
            try:
                from core import brain as _brain
                profile = await loop.run_in_executor(None, _brain.profile_summary)
            except Exception:
                profile = ""
            system = conductor._system_prompt(profile, False, "mc", directives)
            v_ctx = premium_readers.compose_context(att_text, reader)
            if pctx["context_text"]:
                v_ctx = (v_ctx + "\n\n" if v_ctx else "") + pctx["context_text"]
            vtext = message + (("\n\n" + v_ctx) if v_ctx else "")
            try:
                reply = await loop.run_in_executor(
                    None, lambda: model_router.run_with_usage_context(
                        "chat", "vision", model_router.vision_complete,
                        vision_model, system, vtext, img_urls, history=history,
                        usage_metadata={
                            "requested_model": vmodel,
                            "turn_id": (recorder.turn_id if recorder else ""),
                            "agent_id": "tobi-vision", "purpose": "owner_turn",
                            "source": "chat_vision", "is_background": False,
                            "fallback_reason": "vision_capability" if borrowed else "",
                        },
                    ))
            except Exception as e:
                reply = f"I couldn't read that image, sir — {str(e)[:160]}"
            reply = reply or "I couldn't make out the image, sir."
            if borrowed:  # be transparent about which model actually read the image
                short = vision_model.split(":", 1)[-1]
                reply = f"*(Your model can't see images, so I read it with **{short}**.)*\n\n{reply}"
            for chunk in conductor._stream_chunks(reply):
                yield f"event: delta\ndata: {json.dumps({'text': chunk})}\n\n"
            ctok = model_router.estimate_tokens(reply)
            await loop.run_in_executor(None, lambda: chat_store.add_message(
                sid, "assistant", reply, model=vision_model, tokens=ctok, thinking="Looked at image",
                meta=json.dumps(turn_meta) if turn_meta else None))
            await loop.run_in_executor(None, lambda: _bridge_msg(cid, "assistant", reply))
            usage = {
                "prompt_tokens": model_router.estimate_tokens(vtext),
                "completion_tokens": ctok,
                "model": vision_model,
                "requested_model": vmodel or None,
                "actual_model": vision_model,
                "fallback_reason": "vision_capability" if borrowed else None,
                "attempts": 1,
                "latency_ms": round((_time.time() - t0) * 1000),
            }
            yield f"event: usage\ndata: {json.dumps(usage)}\n\n"
            if runtime_tracking:
                yield runtime_frame("step_completed", "vision", {"model": vision_model})
                runtime_complete("done")
                yield runtime_frame("turn_completed", "gateway", {"status": "done"})
            yield "event: done\ndata: {}\n\n"
            return

        # Fold reader context (YouTube transcript / notices) + an honest image note (only when
        # images are attached AND no vision model is connected anywhere) + auto project
        # context (#16) into the turn context.
        image_note = premium_readers.image_unavailable_note(len(img_urls)) if img_urls else None
        atext = premium_readers.compose_context(att_text, reader, image_note)
        if pctx["context_text"] and not runtime_active:
            atext = (atext + "\n\n" if atext else "") + pctx["context_text"]

        # ── Agent run persistence (#16 [D8]): one durable run per Agent turn, steps recorded
        # incrementally from the event stream so an interrupted SSE leaves last-known state. ──
        run_id = None
        recovery_checkpoint = None
        turn_allowed = set(runtime_allowed) if runtime_allowed is not None else None
        if mode_v2 and ctx["mode"] == "agent":
            from core import agent_runs
            if payload.resume_run_id is not None:
                existing_run = await loop.run_in_executor(None, lambda: agent_runs.get_run(payload.resume_run_id))
                if not existing_run or int(existing_run.get("session_id") or 0) != sid:
                    err = TurnError("run.not_found", "recovery", "The Agent run could not be resumed", False)
                    if runtime_tracking:
                        yield runtime_frame("step_failed", "recovery", err.to_dict())
                        runtime_complete("failed", err)
                    yield f"event: error\ndata: {json.dumps({'detail': err.message})}\n\n"
                    yield "event: done\ndata: {}\n\n"
                    return
                run_id = int(payload.resume_run_id)
                await loop.run_in_executor(None, lambda: agent_runs.set_status(run_id, "running"))
                recovery_checkpoint = await loop.run_in_executor(
                    None, lambda: agent_runs.consume_recovery(run_id))
                recovery_tool = (recovery_checkpoint or {}).get("tool")
                if recovery_tool and turn_allowed is not None:
                    turn_allowed.add(recovery_tool)
            else:
                run_id = await loop.run_in_executor(
                    None, lambda: agent_runs.create_run(sid, title=(message or "Agent task")[:120]))
            turn_meta["run_id"] = run_id
            if recorder:
                recorder.bind_run(run_id)
            await link_shadow_run(run_id)

        # ── Standard tool-loop turn — live tool-step + token events via a thread→async queue ──
        yield f"event: thinking\ndata: {json.dumps({'phase': 'Thinking…'})}\n\n"
        q: asyncio.Queue = asyncio.Queue()

        def _emit(ev):
            try:
                loop.call_soon_threadsafe(q.put_nowait, ev)
            except Exception:
                pass

        requested_model = model or sess.get("model") or ""
        usage_run_id = (
            canonical_execution.run_id
            if canonical_active and canonical_execution is not None
            else str(run_id or "")
        )
        _prev = model_router.set_usage_context(
            ctx["mode"], "chat_runtime_v2",
            requested_model=requested_model,
            turn_id=(recorder.turn_id if recorder else ""),
            run_id=usage_run_id,
            agent_id="tobi-agent" if ctx["mode"] == "agent" else "tobi-chat",
            purpose="owner_turn",
            source="chat_runtime",
            is_background=False,
        )
        fut = loop.run_in_executor(chat_runtime.chat_executor(), lambda: conductor.answer(
            message or "(see attached)", cid, "mc", model=model, history=history,
            attachments_text=atext or None,
            directives=directives, extra_tools=extra_tools,
            denied_tools=denied_tools, review_mode=review_mode,
            mode=ctx["mode"], route=(route_decision.route if runtime_active else None),
            allowed_tools=turn_allowed,
            context_manifest=(manifest if runtime_active else None),
            turn_id=(recorder.turn_id if recorder else None),
            max_tool_steps=(route_decision.max_tool_steps if runtime_active else None),
            step_tokens=(route_decision.step_tokens if runtime_active else None),
            final_tokens=(route_decision.final_tokens if runtime_active else None),
            usage_context={
                "surface": ctx["mode"], "feature": "chat_runtime_v2",
                "requested_model": requested_model,
                "turn_id": (recorder.turn_id if recorder else ""),
                "run_id": usage_run_id,
                "agent_id": "tobi-agent" if ctx["mode"] == "agent" else "tobi-chat",
                "purpose": "owner_turn", "source": "chat_runtime",
                "is_background": False,
            },
            recovery_checkpoint=recovery_checkpoint,
            on_event=_emit, on_delta=lambda t: _emit({"type": "delta", "text": t})))
        seen_tools: list[str] = []
        seen_phases: list[str] = []
        checkpoint_steps: list[str] = []
        term_lines: list[str] = []
        first_delta_recorded = False
        _persisted = False  # guards against double-persist (normal path vs bg task)

        async def _bg_persist():
            """Detached persistence — if the client disconnects mid-stream, wait for
            the LLM to finish and save the reply so it appears when they reopen."""
            nonlocal _persisted
            try:
                bg_res = await fut
                if _persisted:
                    return
                _persisted = True
                bg_reply = bg_res.get("reply", "") or ""
                if not bg_reply.strip():
                    return
                bg_reasoning = bg_res.get("reasoning") or None
                bg_tools = bg_res.get("tools_used") or []
                bg_thinking = bg_reasoning or (("Consulted: " + ", ".join(bg_tools)) if bg_tools else None)
                bg_ctok = model_router.estimate_tokens(bg_reply)
                bg_model = bg_res.get("actual_model") or bg_res.get("requested_model") or model
                bg_meta = json.dumps(turn_meta) if turn_meta else None
                if canonical_active and canonical_execution.disposition == "execute":
                    bg_mid = await loop.run_in_executor(
                        None,
                        lambda: chat_store.add_runtime_response(
                            sid,
                            canonical_execution.run_id,
                            bg_reply,
                            model=bg_model,
                            tokens=bg_ctok,
                            thinking=bg_thinking,
                            meta=bg_meta,
                        ),
                    )
                    bg_ptok = model_router.estimate_tokens(
                        message
                        + (atext or "")
                        + " ".join(item.get("content", "") for item in history)
                    )
                    if bg_res.get("model_issue") or bg_res.get("stopped_on_error"):
                        await loop.run_in_executor(
                            None,
                            lambda: runtime_gateway.fail_direct_chat(canonical_execution),
                        )
                    else:
                        await loop.run_in_executor(
                            None,
                            lambda: runtime_gateway.complete_direct_chat(
                                canonical_execution,
                                message_id=bg_mid,
                                model=bg_model,
                                prompt_tokens=bg_ptok,
                                completion_tokens=bg_ctok,
                                latency_ms=round((_time.time() - t0) * 1000),
                            ),
                        )
                else:
                    await loop.run_in_executor(
                        None,
                        lambda: chat_store.add_message(
                            sid,
                            "assistant",
                            bg_reply,
                            model=bg_model,
                            tokens=bg_ctok,
                            thinking=bg_thinking,
                            meta=bg_meta,
                        ),
                    )
                await loop.run_in_executor(None, lambda: _bridge_msg(cid, "assistant", bg_reply))
                shadow_observe("turn_completed", "gateway", {
                    "status": "done", "run_id": run_id, "detached": True,
                })
            except Exception as exc:
                logger.warning(
                    "Detached Chat response persistence failed: %s", type(exc).__name__
                )
                if canonical_active and canonical_execution.disposition == "execute":
                    try:
                        await loop.run_in_executor(
                            None,
                            lambda: runtime_gateway.fail_direct_chat(canonical_execution),
                        )
                    except Exception:
                        pass

        def _record_step(step_type, title, **kw):
            if run_id is None:
                return None
            from core import agent_runs
            return loop.run_in_executor(None, lambda: agent_runs.add_step(run_id, step_type, title, **kw))

        try:
            while not fut.done() or not q.empty():
                # Client disconnect check — spawn bg persistence and stop yielding
                if await request.is_disconnected():
                    shadow_observe("client_disconnected", "gateway", {"run_id": run_id})
                    if not fut.done() and not _persisted:
                        asyncio.ensure_future(_bg_persist())
                    return
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=0.12)
                except asyncio.TimeoutError:
                    continue
                if ev.get("type") == "delta":
                    if runtime_tracking and not first_delta_recorded:
                        runtime_event("delta", "response", {"chars": len(ev.get("text", ""))})
                        first_delta_recorded = True
                    yield f"event: delta\ndata: {json.dumps({'text': ev.get('text', '')})}\n\n"
                elif ev.get("type") == "terminal":
                    # live stdout from a run_command execution (#11) → xterm-style console
                    term_lines.append(ev.get("line", ""))
                    yield f"event: terminal\ndata: {json.dumps({'line': ev.get('line', '')})}\n\n"
                elif ev.get("type") == "reset":
                    yield "event: reset\ndata: {}\n\n"
                elif ev.get("type") == "model_escalated":
                    notice = {"kind": "model_escalated", "from_model": ev.get("from_model"),
                              "to_model": ev.get("to_model"), "reason": ev.get("reason")}
                    yield f"event: notice\ndata: {json.dumps(notice)}\n\n"
                    if runtime_tracking:
                        yield runtime_frame("model_escalated", "model", notice)
                elif ev.get("type") == "plan":
                    # agent-mode declared plan (#16 D9) → structured timeline event
                    plan_steps = [str(s).strip() for s in (ev.get("steps") or []) if str(s).strip()]
                    yield f"event: plan\ndata: {json.dumps({'steps': plan_steps, 'title': ev.get('title', '')})}\n\n"
                    checkpoint_steps.append(
                        f"Planned {len(plan_steps)} step{'s' if len(plan_steps) != 1 else ''}")
                    checkpoint_steps.extend(
                        f"{index}. {step}" for index, step in enumerate(plan_steps[:12], 1))
                    if runtime_tracking:
                        yield runtime_frame("plan_ready", "planning", {
                            "steps": plan_steps, "title": ev.get("title", "")})
                    step = _record_step("plan", ev.get("title") or "Plan",
                                        payload={"steps": plan_steps})
                    if step is not None:
                        await step
                elif ev.get("type") == "thinking":
                    tool_name = ev.get("tool")
                    phase = str(ev.get("phase") or "").strip()
                    if tool_name:
                        if tool_name not in seen_tools:
                            seen_tools.append(tool_name)
                        if tool_name != "outline_plan":   # the plan event records itself
                            step = _record_step("tool", phase, tool=tool_name)
                            if step is not None:
                                await step
                    if phase:
                        seen_phases.append(phase)
                        checkpoint_steps.append(phase)
                        if runtime_tracking:
                            yield runtime_frame("step_started", "execution", {
                                "label": phase, "tool": tool_name})
                    yield f"event: thinking\ndata: {json.dumps({'phase': ev.get('phase', ''), 'tools': seen_tools})}\n\n"
            res = await fut
        except Exception as e:
            err = TurnError("turn.internal", "execution", "The turn failed unexpectedly", True, str(e)[:200])
            if run_id is not None:
                from core import agent_runs
                await loop.run_in_executor(None, lambda: agent_runs.complete_run(run_id, "failed", error=str(e)[:300]))
            if canonical_active and canonical_execution.disposition == "execute":
                try:
                    await loop.run_in_executor(
                        None,
                        lambda: runtime_gateway.fail_direct_chat(canonical_execution),
                    )
                except Exception as gateway_exc:
                    logger.warning(
                        "Runtime V2 direct Chat failure recording failed: %s",
                        type(gateway_exc).__name__,
                    )
            if runtime_tracking:
                yield runtime_frame("step_failed", "execution", err.to_dict())
                runtime_complete("failed", err)
            detail = (
                "TOBI could not finish this reply. Please retry the request."
                if canonical_active
                else str(e)[:200]
            )
            yield f"event: error\ndata: {json.dumps({'detail': detail})}\n\n"
            yield "event: done\ndata: {}\n\n"
            return
        finally:
            model_router.restore_usage_context(_prev)
        reply = res.get("reply", "") or ""
        reasoning = res.get("reasoning") or None
        tools = list(dict.fromkeys([*seen_tools, *(res.get("tools_used") or [])]))
        # The streamed answer already reached the client via on_delta; only special replies
        # (proposals, failures, model-issue notices) still need to be sent here.
        if not res.get("streamed"):
            if runtime_tracking and reply and not first_delta_recorded:
                runtime_event("delta", "response", {"chars": min(len(reply), 32)})
                first_delta_recorded = True
            for chunk in conductor._stream_chunks(reply):
                yield f"event: delta\ndata: {json.dumps({'text': chunk})}\n\n"
        if res.get("model_issue"):
            yield f"event: notice\ndata: {json.dumps({'kind': 'model_issue'})}\n\n"
            if runtime_tracking:
                yield runtime_frame("recovery_required", "model", {
                    "run_id": run_id, "code": "model.malformed_output",
                    "actions": ["retry_step", "revise", "cancel"],
                })
        # A chain stopped on a failed step → the run is paused awaiting the owner's call
        # (Retry / Skip / Revise quick actions in the UI) [D10].
        if res.get("stopped_on_error"):
            yield f"event: notice\ndata: {json.dumps({'kind': 'run_paused', 'run_id': run_id})}\n\n"
            if runtime_tracking:
                yield runtime_frame("recovery_required", "execution", {
                    "run_id": run_id, "actions": ["resume", "retry_step", "skip_step", "revise", "cancel"],
                    "code": "tool.execution",
                })
            if run_id is not None and res.get("failed_step"):
                failed_step = res["failed_step"]
                await loop.run_in_executor(None, lambda: agent_runs.add_step(
                    run_id, "tool", f"Failed: {failed_step.get('tool') or 'tool'}",
                    tool=failed_step.get("tool"), risk=failed_step.get("risk"),
                    payload=failed_step, summary=str(failed_step.get("error") or "")[:1000],
                    status="failed"))
        thinking_meta = reasoning or (("Consulted: " + ", ".join(tools)) if tools else None)
        if mode_v2 and (checkpoint_steps or tools):
            turn_meta["steps"] = checkpoint_steps
            turn_meta["tools"] = tools
        # Task-result artifact (#16 [D21]) — only when the agent run actually ACTED
        # (≥1 act/terminal tool), so read-only turns don't spam artifacts.
        if run_id is not None and not res.get("stopped_on_error") and not res.get("pending_action"):
            acted = [t for t in tools if t in conductor.ACT_TOOLS]
            if acted:
                a_title = (message or "Agent task")[:80]
                a_content = (f"## Task result\n\n{reply}\n\n"
                             f"**Actions:** {', '.join(acted)}\n"
                             f"**Steps:** {len(seen_phases)} · **Tools:** {', '.join(tools)}")
                aid = await loop.run_in_executor(None, lambda: chat_store.add_artifact(
                    sid, "task_result", a_title, a_content, run_id=run_id,
                    meta_json=json.dumps({"tools": tools, "acted": acted})))
                yield f"event: artifact\ndata: {json.dumps({'id': aid, 'kind': 'task_result', 'title': a_title})}\n\n"
                turn_meta.setdefault("artifact_ids", []).append(aid)
        ctok = model_router.estimate_tokens(reply)
        ptok = model_router.estimate_tokens(message + (atext or "") + " ".join(m.get("content", "") for m in history))
        turn_meta["elapsedMs"] = round((_time.time() - t0) * 1000)
        _persisted = True  # normal path handles persistence; bg task (if any) will skip
        actual_model = res.get("actual_model")
        requested_model = res.get("requested_model") or requested_model or None
        fallback_reason = res.get("fallback_reason")
        if actual_model and requested_model and actual_model != requested_model and not res.get("model_escalated"):
            yield f"event: notice\ndata: {json.dumps({'kind': 'model_fallback', 'from_model': requested_model, 'to_model': actual_model, 'reason': fallback_reason})}\n\n"
        response_model = actual_model or requested_model
        response_meta = json.dumps(turn_meta) if turn_meta else None
        try:
            if canonical_active and canonical_execution.disposition == "execute":
                mid = await loop.run_in_executor(
                    None,
                    lambda: chat_store.add_runtime_response(
                        sid,
                        canonical_execution.run_id,
                        reply,
                        model=response_model,
                        tokens=ctok,
                        thinking=thinking_meta,
                        meta=response_meta,
                    ),
                )
            else:
                mid = await loop.run_in_executor(
                    None,
                    lambda: chat_store.add_message(
                        sid,
                        "assistant",
                        reply,
                        model=response_model,
                        tokens=ctok,
                        thinking=thinking_meta,
                        meta=response_meta,
                    ),
                )
        except Exception as exc:
            logger.warning("Chat response persistence failed: %s", type(exc).__name__)
            if canonical_active and canonical_execution.disposition == "execute":
                try:
                    await loop.run_in_executor(
                        None,
                        lambda: runtime_gateway.fail_direct_chat(canonical_execution),
                    )
                except Exception:
                    pass
            runtime_complete("failed")
            yield "event: error\ndata: " + json.dumps({
                "detail": "TOBI produced a reply but could not save it. Please retry the request."
            }) + "\n\n"
            yield "event: done\ndata: {}\n\n"
            return
        await loop.run_in_executor(None, lambda: _bridge_msg(cid, "assistant", reply))
        pending = res.get("pending_action")
        if run_id is not None and pending:
            action_ids = [i.get("id") for i in (pending.get("items") or [pending]) if i.get("id")]
            await loop.run_in_executor(None, lambda: agent_runs.link_actions(run_id, action_ids))
        if recovery_checkpoint and recovery_checkpoint.get("recovery_step_id") and not pending:
            recovery_status = "failed" if res.get("stopped_on_error") else "done"
            await loop.run_in_executor(None, lambda: agent_runs.finish_recovery(
                int(recovery_checkpoint["recovery_step_id"]), recovery_status,
                "checkpoint failed again" if recovery_status == "failed" else "checkpoint applied"))
        # Close out the agent run with an honest status [D8][D10].
        if run_id is not None:
            from core import agent_runs
            if term_lines:
                tail = "\n".join(term_lines[-30:])
                await loop.run_in_executor(None, lambda: agent_runs.add_step(
                    run_id, "terminal", "Terminal output", payload={"tail": tail[-3000:]}))
            run_status = ("waiting_user" if res.get("stopped_on_error")
                          else "waiting_approval" if pending
                          else "failed" if res.get("model_issue") else "done")
            await loop.run_in_executor(None, lambda: agent_runs.complete_run(
                run_id, run_status, message_id=mid))
        if pending:
            yield f"event: action\ndata: {json.dumps(pending)}\n\n"
        picker = res.get("pending_picker")
        if picker:
            yield f"event: picker\ndata: {json.dumps(picker)}\n\n"
        usage = {
            "prompt_tokens": ptok,
            "completion_tokens": ctok,
            "model": actual_model or requested_model or "not_used",
            "requested_model": requested_model,
            "actual_model": actual_model,
            "fallback_reason": fallback_reason,
            "attempts": res.get("model_attempts") or 0,
            "latency_ms": round((_time.time() - t0) * 1000),
        }
        yield f"event: usage\ndata: {json.dumps(usage)}\n\n"
        final_status = ("waiting_user" if res.get("stopped_on_error")
                        else "waiting_approval" if pending
                        else "failed" if res.get("model_issue") else "done")
        if canonical_active and canonical_execution.disposition == "execute":
            try:
                if final_status == "done":
                    await loop.run_in_executor(
                        None,
                        lambda: runtime_gateway.complete_direct_chat(
                            canonical_execution,
                            message_id=mid,
                            model=response_model,
                            prompt_tokens=ptok,
                            completion_tokens=ctok,
                            latency_ms=usage["latency_ms"],
                        ),
                    )
                else:
                    await loop.run_in_executor(
                        None,
                        lambda: runtime_gateway.fail_direct_chat(canonical_execution),
                    )
            except Exception as gateway_exc:
                logger.warning(
                    "Runtime V2 direct Chat completion failed: %s",
                    type(gateway_exc).__name__,
                )
                yield f"event: notice\ndata: {json.dumps({'kind': 'runtime_recovery'})}\n\n"
        if runtime_tracking:
            yield runtime_frame("step_completed", "response", {
                "tools": tools, "model": usage["model"],
                "requested_model": requested_model, "actual_model": actual_model,
                "latency_ms": usage["latency_ms"]})
            runtime_complete(final_status)
            yield runtime_frame("turn_completed", "gateway", {"status": final_status, "run_id": run_id})
        # Trigger brain auto-learning sweep (non-blocking — runs in background thread)
        loop.run_in_executor(None, lambda: model_router.run_with_usage_context(
            "brain", "memory_sweep", brain.sweep_once,
            usage_metadata={
                "purpose": "background", "source": "brain",
                "is_background": True, "agent_id": "tobi-memory",
            },
        ))
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "Connection": "keep-alive",
                                      "X-Accel-Buffering": "no"})


@router.post("/api/chat/sessions/{sid}/fork")
def chat_session_fork(sid: int, body: ChatForkReq):
    """Edit→branch: clone the session up to a message into a NEW session (original preserved)."""
    from core import chat_store
    new = chat_store.fork_session(sid, body.before_message_id)
    if not new:
        raise HTTPException(status_code=404, detail="session not found")
    return new


@router.post("/api/chat/messages/{mid}/feedback")
def chat_message_feedback(mid: int, body: ChatFeedbackReq):
    from core import chat_store
    chat_store.set_feedback(mid, body.value)
    return {"ok": True, "id": mid, "feedback": body.value}


@router.get("/api/chat/sessions/{sid}/activity")
def chat_session_activity(sid: int, limit: int = 50):
    """The system action log for this session — TOBI Actions (#7) scoped to the session's chat_id."""
    from core import chat_store, conductor
    cid = chat_store.chat_id_for_session(sid)
    return conductor.list_actions(limit=max(1, min(limit, 200)), chat_id=cid)


# ── Agent runs + artifacts (#16) ─────────────────────────────────────────────────
@router.get("/api/chat/sessions/{sid}/runs")
def chat_session_runs(sid: int, limit: int = 20):
    from core import agent_runs
    return {"runs": agent_runs.list_runs(sid, limit=max(1, min(limit, 100)))}


@router.get("/api/chat/runs/{run_id}")
def chat_run_detail(run_id: int):
    from core import agent_runs
    run = agent_runs.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="run not found")
    return run


@router.post("/api/chat/runs/{run_id}/commands")
def chat_run_command(run_id: int, body: AgentRunCommandReq):
    from core import agent_runs
    try:
        result = agent_runs.command_run(run_id, body.command, body.revision)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not result:
        raise HTTPException(status_code=404, detail="run not found")
    return result


@router.get("/api/chat/turns/{turn_id}/trace")
def chat_turn_trace(turn_id: str):
    from core import chat_runtime
    trace = chat_runtime.get_trace(turn_id)
    if not trace:
        raise HTTPException(status_code=404, detail="turn not found")
    return trace


@router.get("/api/chat/sessions/{sid}/artifacts")
def chat_session_artifacts(sid: int, limit: int = 50):
    from core import chat_store
    return {"artifacts": chat_store.list_artifacts(sid, limit=max(1, min(limit, 200)))}


@router.get("/api/chat/artifacts/{artifact_id}")
def chat_artifact_detail(artifact_id: int):
    from core import chat_store
    art = chat_store.get_artifact(artifact_id)
    if not art:
        raise HTTPException(status_code=404, detail="artifact not found")
    return art


class ChatCompactReq(BaseModel):
    model: str | None = None
    keep: int = 6


@router.post("/api/chat/sessions/{sid}/compact")
def chat_session_compact(sid: int, body: ChatCompactReq):
    """Compact (P3): summarize the older turns (keep the most recent `keep` verbatim),
    store the summary, and return the trimmed message list — the context bar drops."""
    from core import chat_store, model_router
    sess = chat_store.get_session(sid)
    if not sess:
        raise HTTPException(status_code=404, detail="session not found")
    keep = max(2, min(int(body.keep or 6), 20))
    transcript = chat_store.older_messages_text(sid, keep=keep)
    if not transcript:
        return {"compacted": False, "messages": chat_store.get_messages(sid),
                "detail": "Nothing old enough to compact yet."}
    model = (body.model or sess.get("model") or "").strip() or None
    prompt = ("Summarize this earlier part of a conversation between the Owner and TOBI into tight bullet "
              "points that preserve names, numbers, decisions, and open threads, so the assistant can keep "
              "context. Be concise.\n\n" + transcript)
    try:
        summary = model_router.run_with_usage_context(
            "chat", "compaction",
            lambda: (
                model_router.get_llm("simple", model=model)
                if model else model_router.get_llm("simple")
            ).complete([{"role": "user", "content": prompt}], max_tokens=500) or "",
            usage_metadata={
                "requested_model": model or "", "purpose": "owner_turn",
                "source": "chat_compaction", "agent_id": "tobi-chat",
            },
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Could not summarize: {str(e)[:160]}")
    msgs = chat_store.compact_session(sid, summary, keep=keep)
    if msgs is None:
        return {"compacted": False, "messages": chat_store.get_messages(sid)}
    return {"compacted": True, "messages": msgs, "summary": summary}

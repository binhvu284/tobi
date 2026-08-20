"""Telegram Bot - Tobi Agent"""
from core.env_utils import safe_load_dotenv
safe_load_dotenv()

import os
import re
import time
import json
import asyncio
import logging
import subprocess
from datetime import datetime
from typing import Optional

try:
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import (
        Application, CommandHandler, CallbackQueryHandler,
        ContextTypes, MessageHandler, filters,
    )
except ImportError:
    raise ImportError("pip install python-telegram-bot")

import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


from core.database import (
    get_project, approve_project, reject_project,
    get_all_projects, get_active_projects, get_dashboard,
    get_pending_human_tasks_all, complete_task, get_revenue_summary,
    get_all_lessons, add_lesson,
    load_conversation_history, save_conversation_message,
    get_connection,
)
from core.task_classifier import classify
import json as _json

# Decomposed into core/telegram/* (Phase 4b). Imported back so build_app() and the
# chat/callback handlers below resolve every name exactly as before.
from core.telegram.common import (  # noqa: F401
    ALLOWED_IDS, BOT_TOKEN, CHAT_ID, MAX_HISTORY, PROJECT_DIR, detect_lang,
    get_dashboard_url, is_authorized, logger, md,
)
from core.telegram.pm_helpers import (  # noqa: F401
    pm_list_active, pm_summary_for_prompt
)
from core.telegram.formatting import (  # noqa: F401
    format_daily_report
)
from core.telegram.coding import (  # noqa: F401
    handle_coding_background, handle_research_background
)
from core.telegram.commands import (  # noqa: F401
    cmd_brain, cmd_code, cmd_dashboard, cmd_done, cmd_integrations, cmd_learn, cmd_lessons,
    cmd_note, cmd_pm, cmd_projects, cmd_remember, cmd_report, cmd_research, cmd_revenue,
    cmd_start, cmd_status, cmd_todos, cmd_web
)
from core.telegram.formatting import send_project_proposal_msg  # noqa: F401


# ── PM project helpers (direct DB, no HTTP) ──────────────────────────────────














logging.basicConfig(level=logging.INFO)



_history: dict[int, list] = {}
_chat_locks: dict[int, asyncio.Lock] = {}

_prompt_cache: dict = {"text": "", "expires": 0.0}


# ─────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────







def build_system_prompt() -> str:
    try:
        d = get_dashboard()
        rev = d.get('revenue', {})
        todos = d.get('human_todos_count', 0)
    except Exception:
        rev, todos = {}, 0
    pm_ctx = pm_summary_for_prompt()
    return (
        f"You are Tobi, Thomas's personal AI agent. Sharp, direct, results-focused.\n"
        f"Revenue this month: ${rev.get('this_month', 0):.0f} | Pending todos: {todos}\n"
        f"\nMy Projects:\n{pm_ctx}\n"
        f"\nYou can manage projects via /pm commands or naturally in chat.\n"
        f"Reply in same language as user (Vietnamese if Vietnamese chars detected).\n"
        f"Be concise. Lead with the answer. Suggest /pm commands when relevant."
    )


def build_system_prompt_cached() -> str:
    """Cached version — refreshes every 5 minutes."""
    now = time.monotonic()
    if now < _prompt_cache["expires"]:
        return _prompt_cache["text"]
    _prompt_cache["text"] = build_system_prompt()
    _prompt_cache["expires"] = now + 300
    return _prompt_cache["text"]


def _get_lock(chat_id: int) -> asyncio.Lock:
    if chat_id not in _chat_locks:
        _chat_locks[chat_id] = asyncio.Lock()
    return _chat_locks[chat_id]


def _init_history(chat_id: int) -> None:
    if chat_id not in _history:
        _history[chat_id] = load_conversation_history(chat_id, limit=MAX_HISTORY)


def _trim_history(chat_id: int) -> None:
    if len(_history[chat_id]) > MAX_HISTORY:
        _history[chat_id] = _history[chat_id][-MAX_HISTORY:]


# ─────────────────────────────────────────
# Coding Agent Tools
# ─────────────────────────────────────────






# ─────────────────────────────────────────
# Background task handlers
# ─────────────────────────────────────────





# ─────────────────────────────────────────
# Formatters
# ─────────────────────────────────────────







# ─────────────────────────────────────────
# Command Handlers
# ─────────────────────────────────────────



































# ─────────────────────────────────────────
# Research + Chat Handlers
# ─────────────────────────────────────────





async def _handle_chat_legacy(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    chat_id = update.effective_chat.id
    user_msg = update.message.text

    task_type = classify(user_msg)
    await ctx.bot.send_chat_action(chat_id=chat_id, action="typing")

    # SMALLTALK — fast path, no DB query, lightweight model
    if task_type == "SMALLTALK":
        from core.model_router import get_llm
        client = get_llm("simple")
        system = "You are Tobi, Thomas's AI agent. Be brief and friendly. Max 2 sentences."
        async with _get_lock(chat_id):
            _init_history(chat_id)
            _history[chat_id].append({"role": "user", "content": user_msg})
            _trim_history(chat_id)
            try:
                reply = await asyncio.to_thread(client.complete, _history[chat_id], system, 150)
                _history[chat_id].append({"role": "assistant", "content": reply})
                _trim_history(chat_id)
            except Exception as e:
                reply = "👋"
        save_conversation_message(chat_id, "user", user_msg)
        save_conversation_message(chat_id, "assistant", reply)
        try:
            await update.message.reply_text(reply, parse_mode="Markdown")
        except Exception:
            await update.message.reply_text(reply)
        return

    # CODING — acknowledge immediately, run in background
    if task_type == "CODING":
        await update.message.reply_text("💻 Đang viết code... sẽ báo khi xong.")
        save_conversation_message(chat_id, "user", user_msg)
        asyncio.create_task(handle_coding_background(update, user_msg, chat_id))
        return

    # PROJECT_MGMT — natural language project actions via LLM with PM context
    if task_type == "PROJECT_MGMT":
        from core.model_router import get_llm
        client = get_llm("writing")
        projects = pm_list_active()
        pm_ctx = "\n".join(
            f"#{p['id']} {p['name']} [{p['status']}] {p['progress_pct']}% ({p['task_done']}/{p['task_count']} tasks)"
            for p in projects
        ) or "none"
        system = (
            "You are Tobi, Thomas's AI agent. You manage his projects.\n"
            f"Current projects:\n{pm_ctx}\n\n"
            "When the user asks to create a project, add a task, update progress, or check project status:\n"
            "1. Do the action if you have enough info (call the appropriate /pm command in your reply)\n"
            "2. If you need clarification, ask a single focused question\n"
            "Always reply with a VERY clear confirmation of what you did or plan to do.\n"
            "Format: tell the user exactly what action was taken and the /pm command equivalent.\n"
            "Reply in same language as user."
        )
        async with _get_lock(chat_id):
            _init_history(chat_id)
            _history[chat_id].append({"role": "user", "content": user_msg})
            _trim_history(chat_id)
            try:
                reply = await asyncio.to_thread(client.complete, _history[chat_id], system, 400)
                _history[chat_id].append({"role": "assistant", "content": reply})
                _trim_history(chat_id)
            except Exception as e:
                reply = f"⚠️ {str(e)[:80]}"
        save_conversation_message(chat_id, "user", user_msg)
        save_conversation_message(chat_id, "assistant", reply)
        try:
            await update.message.reply_text(reply, parse_mode="Markdown")
        except Exception:
            await update.message.reply_text(reply)
        return

    # RESEARCH — acknowledge, run in background
    if task_type == "RESEARCH":
        await update.message.reply_text(
            "🔬 Đang research... sẽ báo khi xong (5-10 phút).",
            parse_mode="Markdown",
        )
        save_conversation_message(chat_id, "user", user_msg)
        asyncio.create_task(handle_research_background(update, user_msg, chat_id))
        return

    # STATUS / QUESTION — Conductor (queue #7): grounded, butler-voiced answers about
    # live Mission Control state. Telegram is read-only/safe, so only the read intents go
    # here; EXECUTION (run missions) still falls through to the legacy path for now.
    if task_type in ("STATUS", "QUESTION"):
        reply = None
        try:
            from core import conductor
            res = await asyncio.to_thread(conductor.conductor_chat, user_msg, chat_id, "telegram")
            reply = (res or {}).get("reply")
        except Exception:
            logger.exception("Conductor error in handle_chat")
            reply = None
        if reply:
            async with _get_lock(chat_id):
                _init_history(chat_id)
                _history[chat_id].append({"role": "user", "content": user_msg})
                _history[chat_id].append({"role": "assistant", "content": reply})
                _trim_history(chat_id)
            try:
                await update.message.reply_text(reply, parse_mode="Markdown")
            except Exception:
                await update.message.reply_text(reply)
            return
        # else fall through to the legacy path below

    # STATUS / QUESTION / EXECUTION — normal LLM path with context
    from core.model_router import get_llm
    client = get_llm("writing")
    system = build_system_prompt_cached()
    # Memory-first: consult the Brain for what's relevant to this message (v2).
    try:
        from core import brain
        ctx_block = await asyncio.to_thread(brain.owner_context, user_msg)
        if ctx_block:
            system += f"\n\n{ctx_block}"
    except Exception:
        pass

    async with _get_lock(chat_id):
        _init_history(chat_id)
        _history[chat_id].append({"role": "user", "content": user_msg})
        _trim_history(chat_id)
        try:
            reply = await asyncio.to_thread(client.complete, _history[chat_id], system, 500)
            _history[chat_id].append({"role": "assistant", "content": reply})
            _trim_history(chat_id)
        except Exception as e:
            logger.exception("LLM error in handle_chat")
            reply = f"⚠️ {str(e)[:50]} — thử lại sau"

    save_conversation_message(chat_id, "user", user_msg)
    save_conversation_message(chat_id, "assistant", reply)
    try:
        await update.message.reply_text(reply, parse_mode="Markdown")
    except Exception:
        await update.message.reply_text(reply)


# ─────────────────────────────────────────
# Callback Query (Inline Buttons)
# ─────────────────────────────────────────

async def handle_chat(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    from core.runtime.surface_adapter import track_async_surface
    update_id = getattr(update, "update_id", None)
    chat_id = getattr(getattr(update, "effective_chat", None), "id", "unknown")
    return await track_async_surface(
        surface="telegram",
        operation="message.handle",
        request_id=f"telegram:{update_id}" if update_id is not None else None,
        session_id=f"telegram:{chat_id}",
        actor="telegram-adapter",
        callback=lambda: _handle_chat_legacy(update, ctx),
    )


async def handle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action, project_id_str = query.data.split(":", 1)
    project_id = int(project_id_str)

    if action == "approve":
        approve_project(project_id)
        await query.edit_message_text(
            f"✅ *Project #{project_id} APPROVED!*\nAgent bắt đầu thực hiện. /todos để xem việc cần làm.",
            parse_mode="Markdown",
        )
    elif action == "reject":
        reject_project(project_id, "Rejected by investor via Telegram")
        await query.edit_message_text(
            f"❌ *Project #{project_id} REJECTED.*\nAgent sẽ nghiên cứu phương án khác.",
            parse_mode="Markdown",
        )
    elif action == "edit":
        await query.edit_message_text(
            f"✏️ *Chỉnh sửa Project #{project_id}:*\nReply với hướng dẫn cụ thể.\n"
            f"VD: 'Focus vào thị trường VN' hoặc 'Budget giảm xuống $10'",
            parse_mode="Markdown",
        )


# ─────────────────────────────────────────
# Proactive Senders
# ─────────────────────────────────────────



async def send_project_proposal(app: Application, project_id: int, business_plan: dict):
    await send_project_proposal_msg(app.bot, project_id, business_plan)


async def send_daily_report(app: Application):
    await app.bot.send_message(chat_id=CHAT_ID, text=format_daily_report(get_dashboard()), parse_mode="Markdown")


async def send_human_alert(app: Application, project_name: str, tasks: list):
    task_lines = "\n".join(f"   • {t['title']}" for t in tasks[:5])
    await app.bot.send_message(
        chat_id=CHAT_ID, parse_mode="Markdown",
        text=f"🔔 *HUMAN ACTION REQUIRED*\nProject: *{project_name}*\n\n{task_lines}\n\n/todos để xem chi tiết.",
    )


async def send_revenue_alert(app: Application, project_name: str, amount: float, source: str):
    await app.bot.send_message(
        chat_id=CHAT_ID, parse_mode="Markdown",
        text=f"💰 *REVENUE RECEIVED!*\nProject: *{project_name}*\nAmount: *${amount:.2f}*\nSource: {source}",
    )


async def send_message(app: Application, text: str):
    await app.bot.send_message(chat_id=CHAT_ID, text=text, parse_mode="Markdown")


# ─────────────────────────────────────────
# Terminal interface (used by main.py)
# ─────────────────────────────────────────

_REPL_CHAT_ID = -424242  # dedicated conversation id for the interactive TOBI terminal


async def run_terminal_session():
    """Interactive TOBI terminal (queue #11 D4). Routes chat through the Conductor so the full
    tool-loop — including the real full-machine shell (run_command) — is available, with the
    two-axis approval mode surfaced. Commands prefixed with `!` run directly through the engine.

    Commands: /quit · /status · /mode <plan|ask|accept|auto> · /jobs · /kill <id> · !<command>"""
    from core import conductor, terminal_engine as te

    def _banner() -> str:
        return (f"🤖 TOBI Terminal | mode: {te.get_mode()} | {te.status().get('shell')} on "
                f"{te.status().get('os')}\n"
                "  /quit · /status · /mode <plan|ask|accept|auto> · /jobs · /kill <id> · !<command>\n")

    print(_banner())

    async def _run_direct(cmd: str):
        g = te.gate(cmd, surface="mc")
        if g["decision"] == "refuse":
            print(f"⛔ {g['reason']}\n"); return
        if g["decision"] == "plan":
            print(f"📋 Plan ({g['risk']}): would run `{cmd}` — switch off Plan mode to execute.\n"); return
        if g["decision"] == "confirm":
            ans = (await asyncio.to_thread(input, f"⚠️  {g['risk']}-risk command. Run it? (yes/no) ")).strip().lower()
            if ans not in ("y", "yes", "có", "co"):
                print("Cancelled.\n"); return
        res = await asyncio.to_thread(te.run, cmd, risk=g["risk"], surface="mc")
        if res.get("error"):
            print(f"❌ {res['error']}\n")
        else:
            print(f"[exit {res.get('exit_code')}] {res.get('output', '')}\n")

    while True:
        try:
            user_input = await asyncio.to_thread(input, "You: ")
        except (EOFError, KeyboardInterrupt):
            print("\n👋 Bye!")
            break

        user_input = user_input.strip()
        if not user_input:
            continue
        if user_input in ("/quit", "/exit", "quit", "exit"):
            print("👋 Bye!")
            break
        if user_input == "/status":
            st = te.status()
            print(f"🖥  mode={st['mode']} enabled={st['enabled']} shell={st['shell']} cwd={st['cwd']}")
            print(f"    package managers: {', '.join(st['package_managers']) or 'none'} | tools: {st['tools_registered']}")
            print(format_daily_report(get_dashboard()))
            continue
        if user_input.startswith("/mode"):
            parts = user_input.split()
            if len(parts) < 2:
                print(f"Current mode: {te.get_mode()} (plan|ask|accept|auto)\n"); continue
            try:
                print(f"✅ mode → {te.set_mode(parts[1])}\n")
            except ValueError as e:
                print(f"❌ {e}\n")
            continue
        if user_input == "/jobs":
            jobs = te.list_jobs()["jobs"]
            print("\n".join(f"  #{j['id']} [{j['status']}] {j['command']}" for j in jobs) or "  (no jobs)")
            print()
            continue
        if user_input.startswith("/kill"):
            parts = user_input.split()
            if len(parts) >= 2 and parts[1].isdigit():
                print(f"  {te.kill_job(int(parts[1]))}\n")
            else:
                print("  usage: /kill <job_id>\n")
            continue
        if user_input.startswith("!"):
            await _run_direct(user_input[1:].strip())
            continue

        print("Tobi: ", end="", flush=True)
        res = await asyncio.to_thread(conductor.answer, user_input, _REPL_CHAT_ID, "mc")
        print(res.get("reply", "") + "\n")
        pending = res.get("pending_action")
        if pending:
            ans = (await asyncio.to_thread(input, "Confirm? (yes/no) ")).strip().lower()
            decision = "approve" if ans in ("y", "yes", "có", "co", "ok") else "reject"
            r = await asyncio.to_thread(conductor.confirm_action, pending["id"], decision, "mc", _REPL_CHAT_ID)
            print(f"  → {r.get('status')}: {r.get('summary', '')}\n")


# ─────────────────────────────────────────
# Build App
# ─────────────────────────────────────────

def build_app() -> Application:
    if not BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN not set in .env")
    if not CHAT_ID:
        raise ValueError("TELEGRAM_CHAT_ID not set in .env")

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .concurrent_updates(True)
        .build()
    )

    app.add_handler(CommandHandler("start",        cmd_start))
    app.add_handler(CommandHandler("status",       cmd_status))
    app.add_handler(CommandHandler("report",       cmd_report))
    app.add_handler(CommandHandler("projects",     cmd_projects))
    app.add_handler(CommandHandler("todos",        cmd_todos))
    app.add_handler(CommandHandler("revenue",      cmd_revenue))
    app.add_handler(CommandHandler("lessons",      cmd_lessons))
    app.add_handler(CommandHandler("done",         cmd_done))
    app.add_handler(CommandHandler("research",     cmd_research))
    app.add_handler(CommandHandler("code",         cmd_code))
    app.add_handler(CommandHandler("note",         cmd_note))
    app.add_handler(CommandHandler("learn",        cmd_learn))
    app.add_handler(CommandHandler("remember",     cmd_remember))
    app.add_handler(CommandHandler("brain",        cmd_brain))
    app.add_handler(CommandHandler("web",          cmd_web))
    app.add_handler(CommandHandler("dashboard",    cmd_dashboard))
    app.add_handler(CommandHandler("pm",           cmd_pm))
    app.add_handler(CommandHandler("integrations", cmd_integrations))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_chat))

    return app


if __name__ == "__main__":
    print("🤖 Starting Tobi Telegram Bot...")
    app = build_app()
    print(f"✅ Bot ready | Chat ID: {CHAT_ID}")
    app.run_polling(drop_pending_updates=True)

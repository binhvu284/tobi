"""Telegram Bot - Tobi Agent"""
from dotenv import load_dotenv
load_dotenv()

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
)
from core.task_classifier import classify

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID     = os.getenv("TELEGRAM_CHAT_ID")
ALLOWED_IDS = [int(x) for x in os.getenv("TELEGRAM_ALLOWED_USERS", CHAT_ID or "0").split(",") if x]

PROJECT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

_history: dict[int, list] = {}
_chat_locks: dict[int, asyncio.Lock] = {}
MAX_HISTORY = 12

_prompt_cache: dict = {"text": "", "expires": 0.0}


# ─────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────

def is_authorized(update: Update) -> bool:
    return update.effective_user.id in ALLOWED_IDS


def detect_lang(text: str) -> str:
    viet = set('àáâãèéêìíòóôõùúýăđơưạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹ')
    return 'vi' if any(c in viet for c in text.lower()) else 'en'


def md(text: str) -> str:
    """Escape Markdown v1 special chars in dynamic content."""
    return str(text).replace('_', r'\_').replace('*', r'\*').replace('`', r'\`').replace('[', r'\[')


def build_system_prompt() -> str:
    try:
        d = get_dashboard()
        rev = d.get('revenue', {})
        projects = d.get('active_projects', [])
        todos = d.get('human_todos_count', 0)
        proj_summary = ', '.join([
            f"{p['name']}({p['progress_pct']}%)" for p in projects
        ]) or 'none'
    except Exception:
        proj_summary, rev, todos = 'none', {}, 0
    return (
        f"You are Tobi, Thomas's AI agent. Sharp, direct, results-focused.\n"
        f"Active projects: {proj_summary}\n"
        f"Revenue this month: ${rev.get('this_month', 0):.0f}\n"
        f"Pending todos: {todos}\n"
        f"Reply in same language as user (Vietnamese if Vietnamese chars detected).\n"
        f"Be concise. Lead with the answer. Suggest /commands when relevant."
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

_CODING_TOOLS = [
    {
        "name": "write_file",
        "description": "Write or overwrite a file in the project directory",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path (relative to project root or absolute)"},
                "content": {"type": "string", "description": "Full file content to write"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "read_file",
        "description": "Read a file's content",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "run_bash",
        "description": "Run a bash command in the project directory. Do not run destructive commands.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to execute"},
            },
            "required": ["command"],
        },
    },
    {
        "name": "list_files",
        "description": "List files in a directory",
        "input_schema": {
            "type": "object",
            "properties": {
                "directory": {"type": "string", "description": "Directory to list (default: project root)"},
            },
        },
    },
]

_BLOCKED_CMDS = ["rm -rf /", "sudo rm", "> /dev/", "dd if=", ":(){ :|:& };:"]


async def _execute_tool(name: str, inputs: dict) -> str:
    if name == "write_file":
        raw = inputs.get("path", "")
        path = os.path.join(PROJECT_DIR, raw) if not os.path.isabs(raw) else raw
        path = os.path.normpath(path)
        if not path.startswith(PROJECT_DIR):
            return f"ERROR: path outside project directory ({PROJECT_DIR})"
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(inputs.get("content", ""))
        return f"Written {len(inputs.get('content',''))} chars to {path}"

    if name == "read_file":
        raw = inputs.get("path", "")
        path = os.path.join(PROJECT_DIR, raw) if not os.path.isabs(raw) else raw
        try:
            with open(path, encoding="utf-8") as f:
                return f.read()[:6000]
        except Exception as e:
            return f"ERROR: {e}"

    if name == "run_bash":
        cmd = inputs.get("command", "")
        if any(b in cmd for b in _BLOCKED_CMDS):
            return "ERROR: command blocked for safety"
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                cmd, shell=True, capture_output=True, text=True,
                timeout=30, cwd=PROJECT_DIR,
            )
            out = (result.stdout + result.stderr).strip()
            return out[:3000] if out else "(no output)"
        except subprocess.TimeoutExpired:
            return "ERROR: command timed out (30s)"
        except Exception as e:
            return f"ERROR: {e}"

    if name == "list_files":
        d = inputs.get("directory", ".")
        base = os.path.join(PROJECT_DIR, d) if not os.path.isabs(d) else d
        try:
            files = []
            for root, dirs, fnames in os.walk(base):
                dirs[:] = [x for x in dirs if x not in ("__pycache__", "node_modules", "venv", ".git", ".tobi")]
                for fn in fnames:
                    files.append(os.path.relpath(os.path.join(root, fn), base))
            return "\n".join(files[:150])
        except Exception as e:
            return f"ERROR: {e}"

    return f"ERROR: unknown tool {name}"


async def _run_coding_agent(user_msg: str, context_msg: str = "") -> str:
    """Run Claude with tool_use loop. Returns final text reply."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        from core.model_router import get_llm
        client = get_llm("coding")
        return await asyncio.to_thread(
            client.complete,
            [{"role": "user", "content": user_msg}],
            "You are an expert programmer. Write clean, working code with brief explanation.",
            1500,
        )

    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    system = (
        f"You are Tobi's coding agent. Project dir: {PROJECT_DIR}\n"
        "Write clean, working code. Use tools to create files and test commands.\n"
        "When done, give a brief summary of what you built."
    )
    full_msg = (context_msg + "\n\n" + user_msg).strip() if context_msg else user_msg
    messages = [{"role": "user", "content": full_msg}]

    max_iterations = 15
    final_text = ""

    for _ in range(max_iterations):
        response = await asyncio.to_thread(
            client.messages.create,
            model="claude-sonnet-4-20250514",
            max_tokens=4000,
            system=system,
            tools=_CODING_TOOLS,
            messages=messages,
        )

        text_parts = [b.text for b in response.content if hasattr(b, "text")]
        if text_parts:
            final_text = "\n".join(text_parts)

        if response.stop_reason != "tool_use":
            break

        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                result = await _execute_tool(block.name, block.input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result,
                })

        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})

    return final_text or "Done (no summary produced)."


# ─────────────────────────────────────────
# Background task handlers
# ─────────────────────────────────────────

async def handle_coding_background(update: Update, user_msg: str, chat_id: int):
    try:
        result = await _run_coding_agent(user_msg)
        # Split long responses
        if len(result) > 3800:
            for chunk in [result[i:i+3800] for i in range(0, len(result), 3800)]:
                await update.get_bot().send_message(chat_id=chat_id, text=chunk, parse_mode="Markdown")
        else:
            await update.get_bot().send_message(chat_id=chat_id, text=f"✅ Done:\n{result}", parse_mode="Markdown")
    except Exception as e:
        logger.exception("Coding background error")
        await update.get_bot().send_message(chat_id=chat_id, text=f"⚠️ Coding error: {str(e)[:200]}")


async def handle_research_background(update: Update, user_msg: str, chat_id: int):
    try:
        from core.research_engine import run_research_cycle
        project_ids = run_research_cycle()
        bot = update.get_bot()
        if not project_ids:
            await bot.send_message(
                chat_id=chat_id,
                text="🔬 Research xong — không tìm thấy cơ hội nổi bật.",
                parse_mode="Markdown",
            )
            return
        for pid in project_ids:
            p = get_project(pid)
            if p:
                await send_project_proposal_msg(bot, pid, p.get("business_plan", {}))
    except Exception as e:
        logger.exception("Research background error")
        await update.get_bot().send_message(
            chat_id=chat_id,
            text=f"⚠️ Research error: {str(e)[:200]}",
        )


# ─────────────────────────────────────────
# Formatters
# ─────────────────────────────────────────

def format_business_plan(project_id: int, plan: dict) -> str:
    p = plan or {}
    projections = p.get("revenue_projections", {})
    human_list = "\n".join(f"   • {t}" for t in p.get("human_tasks", [])[:5]) or "   • Tạo tài khoản nền tảng"
    risk_list  = "\n".join(f"   ⚠️ {r}" for r in p.get("risks", [])[:3]) or "   ⚠️ Cạnh tranh cao"
    return (
        f"📊 *BUSINESS PLAN PROPOSAL #{project_id}*\n{'─'*32}\n\n"
        f"📝 *Tổng quan:*\n{md(p.get('executive_summary','—'))}\n\n"
        f"💰 *Revenue model:* {md(p.get('revenue_model','—'))}\n\n"
        f"📈 *Dự báo doanh thu:*\n"
        f"   Tháng 1: {projections.get('month_1','$0')}\n"
        f"   Tháng 3: {projections.get('month_3','$0')}\n"
        f"   Tháng 6: {projections.get('month_6','$0')}\n\n"
        f"💵 *Budget:* ${p.get('monthly_budget',0)}/tháng  🤖 *Agent:* {p.get('agent_workload_pct',90)}%\n\n"
        f"📋 *Bạn cần làm:*\n{human_list}\n\n"
        f"⚠️ *Rủi ro:*\n{risk_list}\n\n{'─'*32}\n"
        f"Approve project này?"
    )


def format_daily_report(dashboard: dict) -> str:
    rev = dashboard.get("revenue", {})
    projects = dashboard.get("active_projects", [])
    todos = dashboard.get("human_todos_count", 0)
    proj_lines = "".join(
        f"\n   📁 *{md(p['name'])}* ({md(p['type'])})\n"
        f"      Progress: {p['progress_pct']}% | Revenue: ${p['revenue_total']:.2f}\n"
        for p in projects
    )
    alert = f"\n\n🔔 *{todos} việc đang chờ bạn!* Gõ /todos để xem." if todos > 0 else ""
    return (
        f"📅 *DAILY REPORT* — {datetime.now().strftime('%d/%m/%Y %H:%M')}\n{'─'*32}\n\n"
        f"💰 *Revenue tháng này:* ${rev.get('this_month',0):.2f}\n"
        f"💰 *Revenue all-time:*  ${rev.get('total_all_time',0):.2f}\n\n"
        f"🚀 *Active Projects:* {len(projects)}{proj_lines}{alert}"
    )


def format_human_todos(todos: list) -> str:
    if not todos:
        return "✅ Không có việc gì cần bạn làm!"
    lines = ["📋 *VIỆC BẠN CẦN LÀM*\n" + "─"*32]
    for i, t in enumerate(todos, 1):
        lines.append(
            f"\n*{i}. [{t['project_name']}]*\n"
            f"   {t['title']}\n"
            f"   _{t.get('description','')}_ \n"
            f"   ID: `{t['id']}`"
        )
    lines.append("\n\nGõ `/done <task_id>` sau khi hoàn thành.")
    return "\n".join(lines)


# ─────────────────────────────────────────
# Command Handlers
# ─────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    await update.message.reply_text(
        "🤖 *Tobi online.*\n\n"
        "Chat tự nhiên hoặc dùng lệnh:\n"
        "/research — tìm cơ hội MMO mới\n"
        "/status — tổng quan portfolio\n"
        "/projects — danh sách dự án\n"
        "/todos — việc cần làm\n"
        "/revenue — theo dõi doanh thu\n"
        "/code — viết code\n"
        "/web — search & tóm tắt\n"
        "/note — lưu ghi chú\n"
        "/learn — bài học đã rút\n"
        "/dashboard — mở web dashboard\n"
        "/integrations — kết nối apps",
        parse_mode="Markdown",
    )


async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    await update.message.reply_text(format_daily_report(get_dashboard()), parse_mode="Markdown")


async def cmd_report(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    await update.message.reply_text(format_daily_report(get_dashboard()), parse_mode="Markdown")


async def cmd_projects(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    projects = get_all_projects()
    if not projects:
        await update.message.reply_text("Chưa có project nào.")
        return
    STATUS_EMOJI = {"pending":"⏳","approved":"✅","active":"🚀","paused":"⏸️","completed":"🏆","failed":"❌"}
    lines = ["📁 *DANH SÁCH PROJECTS*\n" + "─"*32]
    for p in projects:
        rev = p.get("revenue_total", 0) or 0
        lines.append(
            f"\n{STATUS_EMOJI.get(p['status'],'❓')} *#{p['id']} {p['name']}*\n"
            f"   Type: {p['type']} | Progress: {p['progress_pct']}% | Revenue: ${rev:.2f}\n"
            f"   Status: {p['status']}"
        )
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_todos(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    await update.message.reply_text(format_human_todos(get_pending_human_tasks_all()), parse_mode="Markdown")


async def cmd_revenue(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    rev = get_revenue_summary()
    lines = [
        f"💰 *REVENUE REPORT* — {datetime.now().strftime('%d/%m/%Y')}\n{'─'*32}\n",
        f"*Tháng này:* ${rev['this_month']:.2f}",
        f"*Tổng all-time:* ${rev['total_all_time']:.2f}\n",
        "\n*Theo project:*",
    ]
    for p in rev["by_project"]:
        lines.append(f"   📁 {p['name']}: ${p['revenue']:.2f}")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_lessons(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    lessons = get_all_lessons()
    if not lessons:
        await update.message.reply_text("Chưa có bài học nào được ghi lại.")
        return
    TYPE_EMOJI = {"success":"✅","failure":"❌","insight":"💡","warning":"⚠️"}
    lines = ["📚 *BÀI HỌC ĐÃ RÚT RA*\n" + "─"*32]
    for l in lessons[:10]:
        emoji = TYPE_EMOJI.get(l["lesson_type"], "📌")
        lines.append(
            f"\n{emoji} *{l.get('title', l['lesson_type'].upper())}*\n"
            f"   {l['content'][:200]}\n"
            f"   Impact: {'⭐' * min(l['impact_score'], 10)}"
        )
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_done(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    if not ctx.args or not ctx.args[0].isdigit():
        await update.message.reply_text("Dùng: /done <task_id>")
        return
    complete_task(int(ctx.args[0]), output="Completed by human")
    await update.message.reply_text(f"✅ Task #{ctx.args[0]} đã hoàn thành!")


async def cmd_code(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    desc = " ".join(ctx.args) if ctx.args else ""
    if not desc:
        await update.message.reply_text("Dùng: /code [mô tả code cần viết]")
        return
    await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    await update.message.reply_text("💻 Đang viết code... sẽ báo khi xong.")
    chat_id = update.effective_chat.id
    asyncio.create_task(handle_coding_background(update, desc, chat_id))


async def cmd_note(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    note_text = " ".join(ctx.args) if ctx.args else ""
    if not note_text:
        await update.message.reply_text("Dùng: /note [nội dung ghi chú]")
        return
    add_lesson(content=note_text, title=note_text[:50], lesson_type="insight", impact_score=5)
    import subprocess as _sp
    _sp.run(["hermes", "memory", "add", f"note: {note_text[:100]}"],
            capture_output=True, timeout=5, check=False)
    await update.message.reply_text(f"📝 Đã lưu: _{note_text[:100]}_", parse_mode="Markdown")


async def cmd_learn(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    lessons = get_all_lessons()[:5]
    if not lessons:
        await update.message.reply_text("Chưa có bài học nào.")
        return
    TYPE_EMOJI = {"success":"✅","failure":"❌","insight":"💡","warning":"⚠️"}
    lines = ["📚 *5 bài học gần đây:*"]
    for l in lessons:
        emoji = TYPE_EMOJI.get(l["lesson_type"], "📌")
        lines.append(f"\n{emoji} *{l.get('title','')[:50]}*\n   {l['content'][:150]}")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_web(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    query = " ".join(ctx.args) if ctx.args else ""
    if not query:
        await update.message.reply_text("Dùng: /web [URL hoặc từ khóa]")
        return
    await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    from core.model_router import llm_complete
    content = ""
    if query.startswith("http://") or query.startswith("https://"):
        try:
            import requests as req
            r = req.get(query, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
            content = r.text[:3000]
        except Exception as e:
            content = f"Cannot fetch: {e}"
    else:
        from core.research_engine import tavily_search
        results = tavily_search(query, max_results=3)
        content = "\n\n".join([
            f"{r.get('title','')}\n{r.get('content','')[:300]}" for r in results
        ])
    if not content:
        await update.message.reply_text("Không tìm thấy kết quả.")
        return
    lang_hint = "in Vietnamese" if detect_lang(query) == "vi" else "in English"
    summary = await asyncio.to_thread(
        llm_complete,
        f"Summarize this in 3-5 bullet points {lang_hint}:\n\n{content[:2000]}",
        "simple", None, 400,
    )
    await update.message.reply_text(f"🌐 *{query[:50]}*\n\n{summary}", parse_mode="Markdown")


async def cmd_dashboard(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    port = os.getenv("DASHBOARD_PORT", "8080")
    await update.message.reply_text(
        f"📊 *Tobi Dashboard*\n\n`http://localhost:{port}`\n\n"
        f"_(VPS: thay localhost bằng IP server)_",
        parse_mode="Markdown",
    )


async def cmd_integrations(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    try:
        from core.integrations import check_all
        status = check_all()
        lines = ["🔌 *Integrations:*\n"]
        for name, available in status.items():
            lines.append(f"{'✅' if available else '⚪'} {name}")
        lines.append("\n_⚪ = chưa cấu hình API key_")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"⚠️ {str(e)[:100]}")


# ─────────────────────────────────────────
# Research + Chat Handlers
# ─────────────────────────────────────────

async def run_research_and_notify(bot):
    from core.research_engine import run_research_cycle
    project_ids = run_research_cycle()
    if not project_ids:
        await bot.send_message(
            chat_id=CHAT_ID,
            text="🔬 Research xong — không tìm thấy cơ hội nổi bật.",
            parse_mode="Markdown",
        )
        return
    for pid in project_ids:
        p = get_project(pid)
        if p:
            await send_project_proposal_msg(bot, pid, p.get("business_plan", {}))


async def cmd_research(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    await update.message.reply_text(
        "🔬 *Research cycle bắt đầu...*\nTobi đang tìm cơ hội. Sẽ gửi proposals sau 5-10 phút.",
        parse_mode="Markdown",
    )
    asyncio.create_task(run_research_and_notify(update.get_bot()))


async def handle_chat(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
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

    # RESEARCH — acknowledge, run in background
    if task_type == "RESEARCH":
        await update.message.reply_text(
            "🔬 Đang research... sẽ báo khi xong (5-10 phút).",
            parse_mode="Markdown",
        )
        save_conversation_message(chat_id, "user", user_msg)
        asyncio.create_task(handle_research_background(update, user_msg, chat_id))
        return

    # STATUS / QUESTION / EXECUTION — normal LLM path with context
    from core.model_router import get_llm
    client = get_llm("writing")
    system = build_system_prompt_cached()

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

async def send_project_proposal_msg(bot, project_id: int, business_plan: dict):
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ APPROVE", callback_data=f"approve:{project_id}"),
        InlineKeyboardButton("❌ REJECT",  callback_data=f"reject:{project_id}"),
    ],[
        InlineKeyboardButton("✏️ REQUEST CHANGES", callback_data=f"edit:{project_id}"),
    ]])
    await bot.send_message(
        chat_id=CHAT_ID, text=format_business_plan(project_id, business_plan),
        parse_mode="Markdown", reply_markup=keyboard,
    )


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

async def run_terminal_session():
    """Interactive terminal chat with Tobi. Ctrl+C or /quit to exit."""
    from core.model_router import get_llm
    print("🤖 Tobi Terminal | /quit to exit | /status | /code <task>\n")
    history: list[dict] = []

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
            print(format_daily_report(get_dashboard()))
            continue

        task_type = classify(user_input)
        history.append({"role": "user", "content": user_input})
        if len(history) > MAX_HISTORY:
            history = history[-MAX_HISTORY:]

        print("Tobi: ", end="", flush=True)

        if task_type == "CODING":
            print("💻 Running coding agent...")
            reply = await _run_coding_agent(user_input)
        elif task_type == "SMALLTALK":
            client = get_llm("simple")
            reply = await asyncio.to_thread(client.complete, history, "You are Tobi. Be brief.", 150)
        else:
            client = get_llm("writing")
            reply = await asyncio.to_thread(client.complete, history, build_system_prompt_cached(), 800)

        print(reply + "\n")
        history.append({"role": "assistant", "content": reply})
        if len(history) > MAX_HISTORY:
            history = history[-MAX_HISTORY:]


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
    app.add_handler(CommandHandler("web",          cmd_web))
    app.add_handler(CommandHandler("dashboard",    cmd_dashboard))
    app.add_handler(CommandHandler("integrations", cmd_integrations))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_chat))

    return app


if __name__ == "__main__":
    print("🤖 Starting Tobi Telegram Bot...")
    app = build_app()
    print(f"✅ Bot ready | Chat ID: {CHAT_ID}")
    app.run_polling(drop_pending_updates=True)

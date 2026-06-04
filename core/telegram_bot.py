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


def get_dashboard_url() -> str:
    port = os.getenv("DASHBOARD_PORT", "8080")
    custom = os.getenv("DASHBOARD_URL")
    if custom:
        return custom
    codespace = os.getenv("CODESPACE_NAME")
    domain = os.getenv("GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN", "app.github.dev")
    if codespace:
        return f"https://{codespace}-{port}.{domain}"
    return f"http://localhost:{port}"
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


# ── PM project helpers (direct DB, no HTTP) ──────────────────────────────────

def pm_list_active() -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM pm_projects WHERE status != 'archived' ORDER BY updated_at DESC"
    ).fetchall()
    result = []
    for r in rows:
        p = dict(r)
        p["task_count"] = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE pm_project_id=? AND deleted_at IS NULL", (p["id"],)
        ).fetchone()[0]
        p["task_done"] = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE pm_project_id=? AND deleted_at IS NULL AND status_v1='done'",
            (p["id"],),
        ).fetchone()[0]
        result.append(p)
    conn.close()
    return result


def pm_find_project(name_or_id: str) -> dict | None:
    conn = get_connection()
    # Try numeric ID first
    if name_or_id.isdigit():
        row = conn.execute("SELECT * FROM pm_projects WHERE id=?", (int(name_or_id),)).fetchone()
    else:
        row = conn.execute(
            "SELECT * FROM pm_projects WHERE LOWER(name) LIKE ? ORDER BY updated_at DESC LIMIT 1",
            (f"%{name_or_id.lower()}%",),
        ).fetchone()
    conn.close()
    return dict(row) if row else None


def pm_create(name: str, status: str = "active", created_by: str = "tobi") -> dict:
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO pm_projects (name, status, size, emoji_icon, accent_color, created_by) VALUES (?,?,?,?,?,?)",
        (name, status, "medium", "🚀", "#58a6ff", created_by),
    )
    pid = cur.lastrowid
    conn.execute(
        "INSERT INTO pm_activity (project_id, actor, action_type, summary) VALUES (?,?,?,?)",
        (pid, created_by, "project.created", f"Project '{name}' created via Telegram"),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM pm_projects WHERE id=?", (pid,)).fetchone()
    conn.close()
    return dict(row)


def pm_add_task(project_id: int, title: str, priority: str = "P2", agent: str = "tobi",
                created_by: str = "tobi") -> dict:
    conn = get_connection()
    next_sort = conn.execute("SELECT COALESCE(MAX(sort_order), 0)+1 FROM tasks").fetchone()[0]
    cur = conn.execute(
        """INSERT INTO tasks (title, objective, status, status_v1, priority, priority_label,
           owner_label, agent_key, pm_project_id, created_at, updated_at, sort_order)
           VALUES (?,?,?,?,5,?,?,?,?,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,?)""",
        (title, title, "pending", "planned", priority, "owner", agent, project_id, next_sort),
    )
    tid = cur.lastrowid
    conn.execute(
        "INSERT INTO pm_activity (project_id, actor, action_type, summary) VALUES (?,?,?,?)",
        (project_id, created_by, "task.created", f"Task '{title}' added via Telegram"),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()
    conn.close()
    return dict(row)


def pm_list_tasks(project_id: int, status: str | None = None) -> list[dict]:
    conn = get_connection()
    sql = "SELECT * FROM tasks WHERE pm_project_id=? AND deleted_at IS NULL"
    params: list = [project_id]
    if status:
        sql += " AND status_v1=?"; params.append(status)
    sql += " ORDER BY sort_order ASC, created_at ASC"
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def pm_update_goal(goal_id: int, current_value: float, actor: str = "tobi") -> bool:
    conn = get_connection()
    row = conn.execute("SELECT project_id FROM pm_goals WHERE id=?", (goal_id,)).fetchone()
    if not row:
        conn.close()
        return False
    conn.execute(
        "UPDATE pm_goals SET current_value=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (current_value, goal_id),
    )
    # Recalculate progress
    pid = row["project_id"]
    goals = conn.execute("SELECT target_value, current_value FROM pm_goals WHERE project_id=?", (pid,)).fetchall()
    pcts = [min(100.0, (g["current_value"] / g["target_value"] * 100)) for g in goals if g["target_value"] > 0]
    pct = round(sum(pcts) / len(pcts), 1) if pcts else 0.0
    conn.execute("UPDATE pm_projects SET progress_pct=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (pct, pid))
    conn.execute(
        "INSERT INTO pm_activity (project_id, actor, action_type, summary) VALUES (?,?,?,?)",
        (pid, actor, "goal.updated", f"Goal #{goal_id} updated to {current_value} via Telegram"),
    )
    conn.commit()
    conn.close()
    return True


def pm_summary_for_prompt() -> str:
    """Brief PM context for the LLM system prompt."""
    try:
        projects = pm_list_active()
        if not projects:
            return "No active PM projects."
        lines = []
        for p in projects[:5]:
            lines.append(
                f"• #{p['id']} {p['name']} [{p['status']}] {p['progress_pct']}% "
                f"({p['task_done']}/{p['task_count']} tasks)"
            )
        return "\n".join(lines)
    except Exception:
        return ""

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
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("⚡ Open Mission Control", url=get_dashboard_url()),
    ]])
    await update.message.reply_text(
        "🤖 *Tobi online.*\n\n"
        "*Project Management:*\n"
        "/pm — danh sách projects\n"
        "/pm new <name> — tạo project mới\n"
        "/pm task <id> <title> — thêm task\n"
        "/pm tasks <id> — xem tasks của project\n"
        "/pm done <task\\_id> — hoàn thành task\n"
        "/pm goal <id> <value> — cập nhật goal\n\n"
        "*General:*\n"
        "/status — tổng quan · /todos — việc cần làm\n"
        "/research — tìm cơ hội · /code — viết code\n"
        "/web — search · /note — ghi chú\n"
        "/dashboard — mở Mission Control",
        parse_mode="Markdown",
        reply_markup=keyboard,
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
    url = get_dashboard_url()
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("⚡ Open Mission Control", url=url),
    ]])
    await update.message.reply_text(
        f"📊 *Mission Control*\n\n{url}",
        parse_mode="Markdown",
        reply_markup=keyboard,
    )


async def cmd_pm(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    /pm               — list PM projects
    /pm new <name>    — create a new active project
    /pm task <id> <title> — add a task to project <id>
    /pm done <task_id>    — complete a task
    /pm tasks <id>        — list open tasks for project <id>
    /pm goal <goal_id> <value> — update goal current value
    """
    if not is_authorized(update): return
    args = ctx.args or []
    sub = args[0].lower() if args else ""

    # ── /pm  (no subcommand) — list projects ──────────────────────────────────
    if not sub:
        projects = pm_list_active()
        if not projects:
            await update.message.reply_text("📁 No active PM projects.\nUse `/pm new <name>` to create one.", parse_mode="Markdown")
            return
        STATUS_EMOJI = {"idea": "💡", "active": "🚀", "done": "✅", "archived": "📦"}
        lines = ["📁 *MY PROJECTS*\n" + "─" * 28]
        for p in projects:
            e = STATUS_EMOJI.get(p["status"], "📁")
            lines.append(
                f"\n{e} *#{p['id']} {md(p['name'])}* [{p['status']}]\n"
                f"   {p['progress_pct']}% · {p['task_done']}/{p['task_count']} tasks"
                + (f" · 📅 {p['deadline']}" if p.get('deadline') else "")
            )
        lines.append(f"\n_/pm task <id> <title> to add a task_")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
        return

    # ── /pm new <name> ────────────────────────────────────────────────────────
    if sub == "new":
        name = " ".join(args[1:]).strip()
        if not name:
            await update.message.reply_text("Usage: `/pm new Project Name`", parse_mode="Markdown")
            return
        p = pm_create(name, status="active", created_by="tobi")
        await update.message.reply_text(
            f"✅ *Project created!*\n\n#{p['id']} {md(p['name'])}\nStatus: {p['status']}\n\n"
            f"Add tasks: `/pm task {p['id']} Task title`",
            parse_mode="Markdown",
        )
        return

    # ── /pm task <project_id_or_name> <title> ─────────────────────────────────
    if sub == "task":
        if len(args) < 3:
            await update.message.reply_text("Usage: `/pm task <project_id> <task title>`", parse_mode="Markdown")
            return
        proj = pm_find_project(args[1])
        if not proj:
            await update.message.reply_text(f"❌ Project '{args[1]}' not found. Use /pm to list projects.")
            return
        title = " ".join(args[2:]).strip()
        t = pm_add_task(proj["id"], title, created_by="tobi")
        await update.message.reply_text(
            f"✅ *Task added to {md(proj['name'])}*\n\n`{md(title)}`\nTask #{t['id']}",
            parse_mode="Markdown",
        )
        return

    # ── /pm done <task_id> ────────────────────────────────────────────────────
    if sub == "done":
        if not args[1:] or not args[1].isdigit():
            await update.message.reply_text("Usage: `/pm done <task_id>`", parse_mode="Markdown")
            return
        tid = int(args[1])
        conn = get_connection()
        row = conn.execute("SELECT title, pm_project_id FROM tasks WHERE id=? AND deleted_at IS NULL", (tid,)).fetchone()
        if not row:
            conn.close(); await update.message.reply_text("❌ Task not found."); return
        conn.execute(
            "UPDATE tasks SET status='done', status_v1='done', completed_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (tid,),
        )
        if row["pm_project_id"]:
            # recalc progress
            total = conn.execute("SELECT COUNT(*) FROM tasks WHERE pm_project_id=? AND deleted_at IS NULL", (row["pm_project_id"],)).fetchone()[0]
            done = conn.execute("SELECT COUNT(*) FROM tasks WHERE pm_project_id=? AND deleted_at IS NULL AND status_v1='done'", (row["pm_project_id"],)).fetchone()[0]
            pct = round(done / total * 100, 1) if total > 0 else 0
            conn.execute("UPDATE pm_projects SET progress_pct=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (pct, row["pm_project_id"]))
            conn.execute(
                "INSERT INTO pm_activity (project_id, actor, action_type, summary) VALUES (?,?,?,?)",
                (row["pm_project_id"], "tobi", "task.done", f"Task #{tid} '{row['title']}' completed via Telegram"),
            )
        conn.commit(); conn.close()
        await update.message.reply_text(f"✅ *Task #{tid} done!*\n`{md(row['title'])}`", parse_mode="Markdown")
        return

    # ── /pm tasks <project_id> ────────────────────────────────────────────────
    if sub == "tasks":
        if not args[1:]:
            await update.message.reply_text("Usage: `/pm tasks <project_id>`", parse_mode="Markdown")
            return
        proj = pm_find_project(args[1])
        if not proj:
            await update.message.reply_text("❌ Project not found."); return
        tasks = pm_list_tasks(proj["id"])
        if not tasks:
            await update.message.reply_text(f"📋 *{md(proj['name'])}* has no tasks yet.\n`/pm task {proj['id']} Task title`", parse_mode="Markdown")
            return
        STATUS_EMOJI = {"planned": "⬜", "in_progress": "🔄", "done": "✅", "blocked": "🚫", "paused": "⏸️"}
        lines = [f"📋 *{md(proj['name'])}* — Tasks\n" + "─" * 24]
        for t in tasks[:15]:
            e = STATUS_EMOJI.get(t["status_v1"], "⬜")
            lines.append(f"{e} `#{t['id']}` {md(t['title'][:60])} [{t.get('priority_label','P2')}]")
        if len(tasks) > 15:
            lines.append(f"\n_…and {len(tasks)-15} more. Open Mission Control for full view._")
        lines.append(f"\n`/pm done <task_id>` to complete a task")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
        return

    # ── /pm goal <goal_id> <value> ────────────────────────────────────────────
    if sub == "goal":
        if len(args) < 3 or not args[1].isdigit():
            await update.message.reply_text("Usage: `/pm goal <goal_id> <current_value>`", parse_mode="Markdown")
            return
        try:
            val = float(args[2])
        except ValueError:
            await update.message.reply_text("❌ Value must be a number."); return
        if pm_update_goal(int(args[1]), val, actor="tobi"):
            await update.message.reply_text(f"✅ Goal #{args[1]} updated to *{val}*", parse_mode="Markdown")
        else:
            await update.message.reply_text("❌ Goal not found.")
        return

    # ── Unknown subcommand ────────────────────────────────────────────────────
    await update.message.reply_text(
        "📁 *PM Commands*\n"
        "/pm — list projects\n"
        "/pm new <name> — create project\n"
        "/pm task <id> <title> — add task\n"
        "/pm tasks <id> — list tasks\n"
        "/pm done <task_id> — complete task\n"
        "/pm goal <id> <value> — update goal progress",
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

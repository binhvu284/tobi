"""
TELEGRAM APPROVAL BOT - MMO Agent System
==========================================
Xử lý toàn bộ tương tác giữa bạn (investor) và hệ thống:
  • Nhận business plan proposals → inline buttons Approve/Reject/Edit
  • Gửi daily/weekly reports về revenue và tiến độ
  • Alert khi có human tasks cần làm
  • Nhận lệnh từ bạn để điều hướng hệ thống

Cài đặt:
  1. Tạo bot qua @BotFather → lấy TELEGRAM_BOT_TOKEN
  2. Lấy TELEGRAM_CHAT_ID qua @userinfobot
  3. Chạy: python telegram_bot.py

Env vars cần có:
  TELEGRAM_BOT_TOKEN=xxx
  TELEGRAM_CHAT_ID=xxx
"""

import os
import json
import asyncio
import logging
from datetime import datetime
from typing import Optional

try:
    from telegram import (
        Update,
        InlineKeyboardButton,
        InlineKeyboardMarkup,
    )
    from telegram.ext import (
        Application,
        CommandHandler,
        CallbackQueryHandler,
        ContextTypes,
        MessageHandler,
        filters,
    )
except ImportError:
    raise ImportError("Chạy: pip install python-telegram-bot")

# Import hệ thống
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.database import (
    get_project, approve_project, reject_project,
    get_all_projects, get_active_projects, get_dashboard,
    get_pending_human_tasks_all, complete_task, get_revenue_summary,
    get_all_lessons,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID     = os.getenv("TELEGRAM_CHAT_ID")
ALLOWED_IDS = [int(x) for x in os.getenv("TELEGRAM_ALLOWED_USERS", CHAT_ID or "0").split(",") if x]


# ─────────────────────────────────────────
# Auth Guard
# ─────────────────────────────────────────

def is_authorized(update: Update) -> bool:
    uid = update.effective_user.id
    return uid in ALLOWED_IDS


# ─────────────────────────────────────────
# Message Formatters
# ─────────────────────────────────────────

def format_business_plan(project_id: int, plan: dict) -> str:
    """Format business plan đẹp để gửi Telegram."""
    p = plan if plan else {}
    exec_summary   = p.get("executive_summary", "—")
    revenue_model  = p.get("revenue_model", "—")
    projections    = p.get("revenue_projections", {})
    m1  = projections.get("month_1",  "$0")
    m3  = projections.get("month_3",  "$0")
    m6  = projections.get("month_6",  "$0")
    budget         = p.get("monthly_budget", 0)
    agent_pct      = p.get("agent_workload_pct", 90)
    human_tasks    = p.get("human_tasks", [])
    risks          = p.get("risks", [])

    human_list = "\n".join(f"   • {t}" for t in human_tasks[:5]) or "   • Tạo tài khoản nền tảng"
    risk_list  = "\n".join(f"   ⚠️ {r}" for r in risks[:3]) or "   ⚠️ Cạnh tranh cao"

    return (
        f"📊 *BUSINESS PLAN PROPOSAL #{project_id}*\n"
        f"{'─' * 32}\n\n"
        f"📝 *Tổng quan:*\n{exec_summary}\n\n"
        f"💰 *Revenue model:* {revenue_model}\n\n"
        f"📈 *Dự báo doanh thu:*\n"
        f"   Tháng 1: {m1}\n"
        f"   Tháng 3: {m3}\n"
        f"   Tháng 6: {m6}\n\n"
        f"💵 *Budget cần:* ${budget}/tháng\n"
        f"🤖 *Agent tự làm:* {agent_pct}%\n\n"
        f"📋 *Bạn cần làm (once):*\n{human_list}\n\n"
        f"⚠️ *Rủi ro:*\n{risk_list}\n\n"
        f"{'─' * 32}\n"
        f"Bạn có muốn approve project này không?"
    )


def format_daily_report(dashboard: dict) -> str:
    rev = dashboard.get("revenue", {})
    projects = dashboard.get("active_projects", [])
    todos = dashboard.get("human_todos_count", 0)

    proj_lines = ""
    for p in projects:
        proj_lines += f"\n   📁 *{p['name']}* ({p['type']})\n"
        proj_lines += f"      Progress: {p['progress_pct']}% | Revenue: ${p['revenue_total']:.2f}\n"

    alert = f"\n\n🔔 *{todos} việc đang chờ bạn!* Gõ /todos để xem." if todos > 0 else ""

    return (
        f"📅 *DAILY REPORT* — {datetime.now().strftime('%d/%m/%Y %H:%M')}\n"
        f"{'─' * 32}\n\n"
        f"💰 *Revenue tháng này:* ${rev.get('this_month', 0):.2f}\n"
        f"💰 *Revenue all-time:* ${rev.get('total_all_time', 0):.2f}\n\n"
        f"🚀 *Active Projects:* {len(projects)}{proj_lines}"
        f"{alert}"
    )


def format_human_todos(todos: list[dict]) -> str:
    if not todos:
        return "✅ Không có việc gì cần bạn làm!"

    lines = ["📋 *VIỆC BẠN CẦN LÀM*\n" + "─" * 32]
    for i, task in enumerate(todos, 1):
        lines.append(
            f"\n*{i}. [{task['project_name']}]*\n"
            f"   {task['title']}\n"
            f"   _{task.get('description', '')}_ \n"
            f"   ID: `{task['id']}`"
        )
    lines.append(
        "\n\nGõ `/done <task_id>` sau khi hoàn thành."
    )
    return "\n".join(lines)


# ─────────────────────────────────────────
# Command Handlers
# ─────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    await update.message.reply_text(
        "🤖 *MMO Agent System* — Đang hoạt động!\n\n"
        "Các lệnh có sẵn:\n"
        "/status — Xem tổng quan hệ thống\n"
        "/projects — Danh sách projects\n"
        "/report — Daily report\n"
        "/todos — Việc bạn cần làm\n"
        "/revenue — Chi tiết doanh thu\n"
        "/lessons — Bài học đã rút ra\n"
        "/research — Tobi tự research tìm cơ hội mới\n"
        "/pause <id> — Tạm dừng project\n"
        "/done <task_id> — Đánh dấu task hoàn thành",
        parse_mode="Markdown",
    )


async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    dash = get_dashboard()
    await update.message.reply_text(
        format_daily_report(dash),
        parse_mode="Markdown",
    )


async def cmd_report(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    dash = get_dashboard()
    await update.message.reply_text(
        format_daily_report(dash),
        parse_mode="Markdown",
    )


async def cmd_projects(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    projects = get_all_projects()
    if not projects:
        await update.message.reply_text("Chưa có project nào.")
        return

    STATUS_EMOJI = {
        "pending":   "⏳",
        "approved":  "✅",
        "active":    "🚀",
        "paused":    "⏸️",
        "completed": "🏆",
        "failed":    "❌",
    }

    lines = ["📁 *DANH SÁCH PROJECTS*\n" + "─" * 32]
    for p in projects:
        emoji = STATUS_EMOJI.get(p["status"], "❓")
        rev = p.get("revenue_total", 0) or 0
        lines.append(
            f"\n{emoji} *#{p['id']} {p['name']}*\n"
            f"   Type: {p['type']} | Niche: {p['niche']}\n"
            f"   Progress: {p['progress_pct']}% | Revenue: ${rev:.2f}\n"
            f"   Status: {p['status']}"
        )

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_todos(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    todos = get_pending_human_tasks_all()
    await update.message.reply_text(
        format_human_todos(todos),
        parse_mode="Markdown",
    )


async def cmd_revenue(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    rev = get_revenue_summary()
    lines = [
        f"💰 *REVENUE REPORT* — {datetime.now().strftime('%d/%m/%Y')}\n"
        f"{'─' * 32}\n",
        f"*Tháng này:* ${rev['this_month']:.2f}",
        f"*Tổng all-time:* ${rev['total_all_time']:.2f}\n",
        "\n*Theo project:*",
    ]
    for proj in rev["by_project"]:
        lines.append(f"   📁 {proj['name']}: ${proj['revenue']:.2f}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_lessons(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    lessons = get_all_lessons()
    if not lessons:
        await update.message.reply_text("Chưa có bài học nào được ghi lại.")
        return

    TYPE_EMOJI = {"success": "✅", "failure": "❌", "insight": "💡", "warning": "⚠️"}
    lines = ["📚 *BÀI HỌC ĐÃ RÚT RA*\n" + "─" * 32]
    for l in lessons[:10]:
        emoji = TYPE_EMOJI.get(l["lesson_type"], "📌")
        lines.append(
            f"\n{emoji} *{l.get('title', l['lesson_type'].upper())}*\n"
            f"   {l['content'][:200]}...\n"
            f"   Impact: {'⭐' * l['impact_score']}"
        )

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_done(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Mark human task as done: /done <task_id>"""
    if not is_authorized(update):
        return
    args = ctx.args
    if not args or not args[0].isdigit():
        await update.message.reply_text("Dùng: /done <task_id>")
        return
    task_id = int(args[0])
    complete_task(task_id, output="Completed by human")
    await update.message.reply_text(f"✅ Task #{task_id} đã được đánh dấu hoàn thành!")


# ─────────────────────────────────────────
# Callback Query Handler (Inline Buttons)
# ─────────────────────────────────────────

async def run_research_and_notify(bot):
    from core.research_engine import run_research_cycle
    from core.database import get_project
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
    if not is_authorized(update):
        return
    await update.message.reply_text(
        "🔬 *Research cycle bắt đầu...*\n"
        "Tobi đang tìm kiếm cơ hội. Sẽ gửi proposals sau 5-10 phút.",
        parse_mode="Markdown",
    )
    asyncio.create_task(run_research_and_notify(update.get_bot()))


async def handle_chat(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    user_msg = update.message.text
    await update.message.reply_text("💭 _Tobi đang suy nghĩ..._", parse_mode="Markdown")
    from core.model_router import llm_complete
    system = (
        "Bạn là Tobi, AI agent quản lý digital business portfolio cho Thomas. "
        "Trả lời ngắn gọn, thực tế, bằng tiếng Việt. "
        "Nếu được hỏi về projects, dùng lệnh /projects. "
        "Nếu muốn research, gợi ý /research."
    )
    reply = llm_complete(user_msg, task_type="simple", system=system, max_tokens=500)
    await update.message.reply_text(reply, parse_mode="Markdown")


async def handle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data  # format: "approve:123" | "reject:123" | "edit:123"
    action, project_id_str = data.split(":", 1)
    project_id = int(project_id_str)

    if action == "approve":
        approve_project(project_id)
        await query.edit_message_text(
            f"✅ *Project #{project_id} đã được APPROVE!*\n\n"
            f"Agent sẽ bắt đầu thực hiện ngay. Kiểm tra /todos để xem việc cần bạn làm.",
            parse_mode="Markdown",
        )

    elif action == "reject":
        reject_project(project_id, "Rejected by investor via Telegram")
        await query.edit_message_text(
            f"❌ *Project #{project_id} đã bị REJECT.*\n\n"
            f"Agent sẽ nghiên cứu phương án khác.",
            parse_mode="Markdown",
        )

    elif action == "edit":
        await query.edit_message_text(
            f"✏️ *Để chỉnh sửa Project #{project_id}:*\n\n"
            f"Reply message này với hướng dẫn cụ thể.\n"
            f"Ví dụ: 'Tập trung vào thị trường Việt Nam' hoặc 'Budget giảm xuống $10'",
            parse_mode="Markdown",
        )


# ─────────────────────────────────────────
# Proactive Notification Functions
# (Gọi từ ngoài để gửi messages chủ động)
# ─────────────────────────────────────────

async def send_project_proposal_msg(bot, project_id: int, business_plan: dict):
    """Gửi business plan proposal dùng raw bot object (không cần Application)."""
    text = format_business_plan(project_id, business_plan)
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ APPROVE", callback_data=f"approve:{project_id}"),
            InlineKeyboardButton("❌ REJECT",  callback_data=f"reject:{project_id}"),
        ],
        [
            InlineKeyboardButton("✏️ REQUEST CHANGES", callback_data=f"edit:{project_id}"),
        ],
    ])
    await bot.send_message(
        chat_id=CHAT_ID,
        text=text,
        parse_mode="Markdown",
        reply_markup=keyboard,
    )


async def send_project_proposal(app: Application, project_id: int, business_plan: dict):
    """Gửi business plan proposal đến Telegram kèm inline buttons."""
    text = format_business_plan(project_id, business_plan)

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ APPROVE", callback_data=f"approve:{project_id}"),
            InlineKeyboardButton("❌ REJECT",  callback_data=f"reject:{project_id}"),
        ],
        [
            InlineKeyboardButton("✏️ REQUEST CHANGES", callback_data=f"edit:{project_id}"),
        ],
    ])

    await app.bot.send_message(
        chat_id=CHAT_ID,
        text=text,
        parse_mode="Markdown",
        reply_markup=keyboard,
    )


async def send_daily_report(app: Application):
    """Gửi daily report tự động."""
    dash = get_dashboard()
    text = format_daily_report(dash)
    await app.bot.send_message(chat_id=CHAT_ID, text=text, parse_mode="Markdown")


async def send_human_alert(app: Application, project_name: str, tasks: list[dict]):
    """Alert khi có human tasks mới."""
    task_lines = "\n".join(f"   • {t['title']}" for t in tasks[:5])
    text = (
        f"🔔 *HUMAN ACTION REQUIRED*\n"
        f"Project: *{project_name}*\n\n"
        f"Các việc cần bạn làm:\n{task_lines}\n\n"
        f"Gõ /todos để xem chi tiết."
    )
    await app.bot.send_message(chat_id=CHAT_ID, text=text, parse_mode="Markdown")


async def send_revenue_alert(app: Application, project_name: str, amount: float, source: str):
    """Alert khi có revenue mới."""
    text = (
        f"💰 *REVENUE RECEIVED!*\n\n"
        f"Project: *{project_name}*\n"
        f"Amount: *${amount:.2f}*\n"
        f"Source: {source}\n"
        f"Time: {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    )
    await app.bot.send_message(chat_id=CHAT_ID, text=text, parse_mode="Markdown")


async def send_message(app: Application, text: str):
    """Generic message sender."""
    await app.bot.send_message(chat_id=CHAT_ID, text=text, parse_mode="Markdown")


# ─────────────────────────────────────────
# Build App
# ─────────────────────────────────────────

def build_app() -> Application:
    if not BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN chưa được set trong .env")
    if not CHAT_ID:
        raise ValueError("TELEGRAM_CHAT_ID chưa được set trong .env")

    app = Application.builder().token(BOT_TOKEN).build()

    # Register handlers
    app.add_handler(CommandHandler("start",    cmd_start))
    app.add_handler(CommandHandler("status",   cmd_status))
    app.add_handler(CommandHandler("report",   cmd_report))
    app.add_handler(CommandHandler("projects", cmd_projects))
    app.add_handler(CommandHandler("todos",    cmd_todos))
    app.add_handler(CommandHandler("revenue",  cmd_revenue))
    app.add_handler(CommandHandler("lessons",  cmd_lessons))
    app.add_handler(CommandHandler("done",     cmd_done))
    app.add_handler(CommandHandler("research", cmd_research))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_chat))

    return app


# ─────────────────────────────────────────
# Main (Standalone mode)
# ─────────────────────────────────────────

if __name__ == "__main__":
    print("🤖 Starting MMO Agent Telegram Bot...")
    app = build_app()
    print(f"✅ Bot running | Chat ID: {CHAT_ID}")
    app.run_polling(drop_pending_updates=True)

"""Report/message formatters for Telegram replies.

Extracted verbatim from core/telegram_bot.py (Phase 4b — pre-#21 decomposition).
See docs/REFACTORING_PLAN.md.
"""
from core.env_utils import safe_load_dotenv
safe_load_dotenv()

import os  # noqa: F401
import re  # noqa: F401
import time  # noqa: F401
import json  # noqa: F401
import asyncio  # noqa: F401
import logging  # noqa: F401
import subprocess  # noqa: F401
from datetime import datetime  # noqa: F401
from typing import Optional  # noqa: F401

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup  # noqa: F401
from telegram.ext import ContextTypes  # noqa: F401

from core.database import (  # noqa: F401
    get_project, approve_project, reject_project,
    get_all_projects, get_active_projects, get_dashboard,
    get_pending_human_tasks_all, complete_task, get_revenue_summary,
    get_all_lessons, add_lesson,
    load_conversation_history, save_conversation_message,
    get_connection,
)
from core.task_classifier import classify  # noqa: F401
import json as _json  # noqa: F401

from core.telegram.common import (  # noqa: F401
    ALLOWED_IDS, BOT_TOKEN, CHAT_ID, MAX_HISTORY, PROJECT_DIR, detect_lang,
    get_dashboard_url, is_authorized, logger, md,
)

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

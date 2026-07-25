"""Shared Telegram config, logger and small helpers.

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


logger = logging.getLogger(__name__)


BOT_TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN")


CHAT_ID     = os.getenv("TELEGRAM_CHAT_ID")


ALLOWED_IDS = [int(x) for x in os.getenv("TELEGRAM_ALLOWED_USERS", CHAT_ID or "0").split(",") if x]


PROJECT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


MAX_HISTORY = 12


def is_authorized(update: Update) -> bool:
    return update.effective_user.id in ALLOWED_IDS


def detect_lang(text: str) -> str:
    viet = set('àáâãèéêìíòóôõùúýăđơưạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹ')
    return 'vi' if any(c in viet for c in text.lower()) else 'en'


def md(text: str) -> str:
    """Escape Markdown v1 special chars in dynamic content."""
    return str(text).replace('_', r'\_').replace('*', r'\*').replace('`', r'\`').replace('[', r'\[')



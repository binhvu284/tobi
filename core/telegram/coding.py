"""Coding-agent tool catalog, executor and background handlers.

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
from core.telegram.formatting import send_project_proposal_msg  # noqa: F401

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
        # Routed through the real terminal engine (#11 D5): full-machine scope, the two-axis
        # safety model and the hard denylist replace the old PROJECT_DIR lock + _BLOCKED_CMDS.
        # This autonomous coding loop only auto-runs commands the engine gates to 'run'
        # (Telegram is capped at Ask); medium/high are refused with a nudge to Mission Control.
        cmd = inputs.get("command", "")
        from core import terminal_engine as te
        g = te.gate(cmd, surface="telegram", use_llm=False)
        if g["decision"] == "refuse":
            return f"BLOCKED (safety): {g['reason']}"
        if g["decision"] != "run":
            return (f"NOT RUN — this is a {g['risk']}-risk command ({g['reason']}). "
                    "Ask the owner to run it from Mission Control terminal mode (Accept/Auto), "
                    "or confirm it there.")
        res = await asyncio.to_thread(te.run, cmd, risk=g["risk"], surface="telegram")
        if res.get("error"):
            return f"ERROR: {res['error']}"
        tail = res.get("output") or "(no output)"
        return f"[exit {res.get('exit_code')}] {tail}"[:3000]

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

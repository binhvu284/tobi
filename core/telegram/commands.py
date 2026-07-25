"""Telegram /command handlers.

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
from core.telegram.pm_helpers import (  # noqa: F401
    pm_add_task, pm_create, pm_find_project, pm_list_active, pm_list_tasks,
    pm_summary_for_prompt, pm_update_goal
)
from core.telegram.formatting import (  # noqa: F401
    format_business_plan, format_daily_report, format_human_todos
)
from core.telegram.formatting import send_project_proposal_msg  # noqa: F401
from core.telegram.coding import (  # noqa: F401
    _CODING_TOOLS, handle_coding_background, handle_research_background
)

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
        "*Brain (trí nhớ):*\n"
        "/remember <điều cần nhớ> — lưu vào Brain\n"
        "/brain — tổng quan · /brain <từ khóa> — tìm\n\n"
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


async def cmd_remember(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """/remember <fact> — explicitly save a durable fact about the owner into the Brain."""
    if not is_authorized(update): return
    content = " ".join(ctx.args).strip() if ctx.args else ""
    if not content:
        await update.message.reply_text(
            "Dùng: `/remember <điều cần nhớ>`\nVD: `/remember Tôi thích họp buổi sáng`",
            parse_mode="Markdown",
        )
        return
    try:
        from core import brain
        res = await asyncio.to_thread(brain.remember, content)
        if res.get("ok"):
            await update.message.reply_text(
                f"🧠 Đã nhớ vào *{res.get('category','identity')}*:\n_{md(content[:200])}_",
                parse_mode="Markdown",
            )
        else:
            await update.message.reply_text("⚠️ Không lưu được (nội dung trống).")
    except Exception as e:
        await update.message.reply_text(f"⚠️ {str(e)[:120]}")


async def cmd_brain(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """/brain [query] — what Tobi knows about you. With a query → semantic recall."""
    if not is_authorized(update): return
    query = " ".join(ctx.args).strip() if ctx.args else ""
    try:
        from core import brain
        if query:
            items = await asyncio.to_thread(brain.semantic_search, query, 8)
            if not items:
                await update.message.reply_text("🧠 Chưa nhớ gì liên quan tới điều đó.")
                return
            lines = [f"🧠 *Tobi nhớ về:* _{md(query[:60])}_\n" + "─" * 24]
            for m in items:
                conf = int(round((m.get("confidence") or 0) * 100))
                lines.append(f"• [{m.get('category','?')}] {md(m['content'][:160])}  _({conf}%)_")
            await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
        else:
            st = await asyncio.to_thread(brain.stats)
            by_cat = st.get("by_category", {})
            cat_lines = "\n".join(f"   • {c}: {n}" for c, n in sorted(by_cat.items(), key=lambda x: -x[1]))
            await update.message.reply_text(
                f"🧠 *Brain* — {st.get('total',0)} điều đã nhớ\n{'─'*24}\n{cat_lines or '   (trống)'}\n\n"
                f"⏳ Pending: {st.get('pending',0)} · ⚠️ Conflicts: {st.get('conflicts',0)} · 🕰 Stale: {st.get('stale',0)}\n\n"
                f"_/brain <từ khóa> để tìm · /remember <điều cần nhớ> để lưu_",
                parse_mode="Markdown",
            )
    except Exception as e:
        await update.message.reply_text(f"⚠️ {str(e)[:120]}")


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


async def cmd_research(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    await update.message.reply_text(
        "🔬 *Research cycle bắt đầu...*\nTobi đang tìm cơ hội. Sẽ gửi proposals sau 5-10 phút.",
        parse_mode="Markdown",
    )
    asyncio.create_task(run_research_and_notify(update.get_bot()))


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

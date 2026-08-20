"""Scheduled background jobs and the Telegram notification plumbing they share.

Extracted verbatim from main.py (Phase 4b — pre-#21 decomposition). main.py keeps the
process/CLI entry points and imports these back, so schedule registration and every
call site behave exactly as before.

The lazily-built Telegram application (`_tg_app`) lives here with get_telegram_app()/
notify() because every job notifies through it; keeping the global in one module means
there is still exactly ONE application instance process-wide.
"""
import asyncio
import logging
from datetime import datetime

import schedule

from core.database import add_lesson, get_all_lessons, get_dashboard
from core.model_router import llm_complete
from core.research_engine import run_research_cycle
from core.project_executor import execute_all_projects
from core.ceo_loop import run_ceo_review, format_ceo_telegram_summary
from core.telegram_bot import build_app, send_daily_report, send_message, send_project_proposal
from core.runtime.surface_adapter import track_sync_surface

logger = logging.getLogger(__name__)
_tg_app = None
_tg_app_lock = asyncio.Lock()


async def get_telegram_app():
    """Return one fully initialized Telegram application.

    Build into a local variable so a timeout during initialization cannot poison
    the process-wide singleton with a partially initialized application.
    """
    global _tg_app
    if _tg_app is not None:
        return _tg_app

    async with _tg_app_lock:
        if _tg_app is not None:
            return _tg_app

        candidate = build_app()
        try:
            await candidate.initialize()
        except Exception:
            # Application.shutdown() is a no-op until Application.initialize()
            # finishes, but Bot.initialize() may already have opened HTTP clients.
            try:
                await candidate.bot.shutdown()
            except Exception:
                logger.debug("Telegram partial initialization cleanup failed", exc_info=True)
            raise

        _tg_app = candidate
    return _tg_app


async def start_telegram_polling():
    """Start polling and update processing in python-telegram-bot's required order."""
    app = await get_telegram_app()
    if app.updater is None:
        raise RuntimeError("Telegram application has no polling updater.")

    try:
        if not app.updater.running:
            await app.updater.start_polling(drop_pending_updates=True)
        if not app.running:
            await app.start()
    except Exception:
        await shutdown_telegram_app()
        raise
    return app


async def shutdown_telegram_app():
    """Idempotently stop polling, processing, and Telegram HTTP resources."""
    global _tg_app
    async with _tg_app_lock:
        app = _tg_app
        _tg_app = None
        if app is None:
            return

        if app.updater is not None and app.updater.running:
            await app.updater.stop()
        if app.running:
            await app.stop()
        await app.shutdown()


async def notify(message: str):
    try:
        app = await get_telegram_app()
        await send_message(app, message)
    except Exception as e:
        logger.error(f"Telegram notify error: {e}")


async def job_daily_report():
    logger.info("📅 Running daily report...")
    try:
        await send_daily_report(await get_telegram_app())
    except Exception as e:
        logger.error(f"Daily report error: {e}")


async def job_execution_cycle():
    logger.info("⚙️  Running execution cycle...")
    try:
        results = execute_all_projects(tasks_per_project=3)
        if not results:
            return
        total = sum(r.get("tasks_executed", 0) for r in results)
        needs_human = [r for r in results if r.get("human_todos_count", 0) > 0 and not r.get("error")]
        if total > 0:
            await notify(f"⚙️ *Execution complete*\n{total} tasks done across {len(results)} projects")
        if needs_human:
            app = await get_telegram_app()
            from core.telegram_bot import send_human_alert
            for r in needs_human:
                await send_human_alert(app, r["project_name"], r.get("human_todos", []))
        logger.info(f"✅ Execution: {total} tasks done")
    except Exception as e:
        logger.error(f"Execution error: {e}")
        await notify(f"⚠️ Execution error: {str(e)[:200]}")


async def job_task_reminders():
    """Project v2 (#12): push a Telegram alert for tasks whose reminder_at is due."""
    try:
        from core.pm_reminders import fire_due_reminders
        due = fire_due_reminders()
        if not due:
            return
        lines = [f"   • {d['title']} ({d['project_name']})" for d in due[:10]]
        msg = "🔔 *Task reminder*\n" + "\n".join(lines)
        if len(due) > 10:
            msg += f"\n…and {len(due) - 10} more"
        await notify(msg)
        logger.info(f"🔔 Fired {len(due)} task reminder(s)")
    except Exception as e:
        logger.error(f"Task reminders error: {e}")


async def job_research_cycle():
    logger.info("🔬 Running weekly research...")
    await notify("🔬 *Weekly Research Started*\nĐang tìm kiếm cơ hội mới...")
    try:
        project_ids = run_research_cycle()
        if not project_ids:
            await notify("🔬 Research xong — không tìm thấy cơ hội nổi bật tuần này.")
            return
        app = await get_telegram_app()
        from core.database import get_project
        for pid in project_ids:
            p = get_project(pid)
            if p:
                await send_project_proposal(app, pid, p.get("business_plan", {}))
                await asyncio.sleep(2)
        logger.info(f"✅ Research: {len(project_ids)} proposals sent")
    except Exception as e:
        logger.error(f"Research error: {e}")
        await notify(f"⚠️ Research error: {str(e)[:200]}")


async def job_ceo_review():
    logger.info("🎯 Running monthly CEO review...")
    await notify("🎯 *Monthly CEO Review Starting...*")
    try:
        analysis = run_ceo_review()
        if analysis.get("status") == "no_projects":
            await notify("🎯 CEO Review: Chưa có project nào để review.")
            return
        await notify(format_ceo_telegram_summary(analysis))
        logger.info("✅ CEO review done")
    except Exception as e:
        logger.error(f"CEO review error: {e}")
        await notify(f"⚠️ CEO review error: {str(e)[:200]}")


async def job_weekly_reflection():
    logger.info("🪞 Running weekly self-reflection...")
    try:
        lessons = get_all_lessons()[:10]
        lessons_text = "\n".join([
            f"- [{l['lesson_type']}] {l.get('title','')}: {l['content'][:150]}"
            for l in lessons
        ]) if lessons else "No lessons yet."
        dash = get_dashboard()
        active = len(dash.get("active_projects", []))
        prompt = (
            f"Weekly self-reflection for Tobi AI Agent.\n"
            f"Active projects: {active}\n"
            f"Recent lessons:\n{lessons_text}\n\n"
            f"Write a brief weekly reflection in Vietnamese (3-5 bullet points):\n"
            f"1. Gì đã làm tốt?\n2. Cần cải thiện gì?\n3. Insight cho tuần tới?\n"
            f"Giữ dưới 200 từ, thực tế và actionable."
        )
        reflection = llm_complete(prompt, task_type="simple", max_tokens=400)
        await notify(f"🪞 *Weekly Reflection* — {datetime.now().strftime('%d/%m/%Y')}\n\n{reflection}")
        add_lesson(
            content=reflection,
            title=f"Weekly Reflection {datetime.now().strftime('%Y-%m-%d')}",
            lesson_type="insight",
            impact_score=6,
        )
        logger.info("✅ Weekly reflection done")
    except Exception as e:
        logger.error(f"Weekly reflection error: {e}")


def job_brain_sweep():
    """Periodic Brain auto-learning: extract durable owner facts from new chat messages
    (dashboard + Telegram — both persist to the shared `conversations` table)."""
    try:
        from core.brain import sweep_once, mirror_to_hermes
        res = sweep_once()
        if res.get("processed"):
            logger.info(f"🧠 Brain sweep: {res}")
        # Mirror freshly-learned memories into Hermes (one-way, best-effort).
        mres = mirror_to_hermes()
        if mres.get("mirrored"):
            logger.info(f"🪞 Brain→Hermes mirror: {mres}")
    except Exception as e:
        logger.error(f"Brain sweep error: {e}")


def job_brain_decay():
    """Daily freshness automation: decay confidence of unconfirmed memories so stale
    knowledge fades and surfaces for re-check (never silently deleted)."""
    try:
        from core.brain import decay_confidences
        res = decay_confidences()
        if res.get("decayed"):
            logger.info(f"🧠 Brain decay: {res}")
    except Exception as e:
        logger.error(f"Brain decay error: {e}")


def job_brain_import_expire():
    """Purge encrypted payloads of stale uncommitted Brain V2 import jobs past the
    24h temp-data limit (#20 review P1: the promised cleanup must be automatic,
    not just an on-demand function)."""
    try:
        from core.brain_import import expire_jobs
        n = expire_jobs()
        if n:
            logger.info(f"🧠 Brain import expiry: purged {n} stale job(s)")
    except Exception as e:
        logger.error(f"Brain import expiry error: {e}")


def job_news_v2_refresh():
    """News V2 (#23, N03): hourly due-schedule check. Fail-closed no-op until the
    owner turns on news.v2_enabled or news.v2_shadow (rollout stage 1)."""
    try:
        from core.news.refresh import job_scheduled
        outcome = job_scheduled()
        if outcome:
            logger.info(f"📰 News V2 refresh: {outcome}")
    except Exception as e:
        logger.error(f"News V2 refresh error: {e}")


def job_news_v2_retention():
    """News V2 (#23): nightly retention — favorites/notes exempt. Same flag gate."""
    try:
        from core.news.refresh import retention_scheduled
        outcome = retention_scheduled()
        if outcome and any(outcome.values()):
            logger.info(f"📰 News V2 retention: {outcome}")
    except Exception as e:
        logger.error(f"News V2 retention error: {e}")


def job_storage_scan_db():
    """Hourly-ish DB storage snapshot (cheap) — Storage & Usage (#10) [S21]."""
    try:
        from core.storage_scan import run_scan
        run_scan("db")
    except Exception as e:
        logger.error(f"Storage DB scan error: {e}")


def job_storage_scan_fs():
    """Daily filesystem storage snapshot (expensive walk) — Storage & Usage (#10) [S21]."""
    try:
        from core.storage_scan import run_scan
        res = run_scan("fs")
        logger.info(f"💾 Storage fs scan: {res}")
    except Exception as e:
        logger.error(f"Storage fs scan error: {e}")


def job_graph_sync():
    """Periodic Graph View refresh: register internal nodes (memory/task/project), mirror
    connected integrations, rebuild semantic + tag edges, recompute degree."""
    try:
        from core.graph_engine import rebuild
        from core.integrations import check_all
        sources = [s for s, ok in check_all().items() if ok and s in ("notion", "github", "google")]
        res = rebuild(sources=sources)
        logger.info(f"🕸️ Graph sync: {res}")
    except Exception as e:
        logger.error(f"Graph sync error: {e}")


def job_explore_news():
    try:
        from core import explore
        logger.info(f"📰 Explore news: {explore.refresh('news')}")
    except Exception as e:
        logger.error(f"Explore news error: {e}")


def job_explore_tools():
    try:
        from core import explore
        logger.info(f"🛠️ Explore tools: {explore.refresh('tools')}")
    except Exception as e:
        logger.error(f"Explore tools error: {e}")


def job_explore_social():
    try:
        from core import explore
        logger.info(f"💬 Explore social: {explore.refresh('social')}")
    except Exception as e:
        logger.error(f"Explore social error: {e}")


def job_explore_models():
    try:
        from core import explore
        logger.info(f"🏆 Explore models: {explore.refresh_models()}")
    except Exception as e:
        logger.error(f"Explore models error: {e}")


def run_async(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(coro)
        else:
            loop.run_until_complete(coro)
    except RuntimeError:
        asyncio.run(coro)


def tracked_schedule(operation, callback):
    return lambda: track_sync_surface(
        surface="scheduler", operation=operation, session_id="scheduler",
        actor="scheduler-adapter", callback=callback,
    )


def setup_schedules():
    schedule.every().day.at("08:00").do(tracked_schedule("daily.report", lambda: run_async(job_daily_report())))
    schedule.every(6).hours.do(tracked_schedule("execution.cycle", lambda: run_async(job_execution_cycle())))
    schedule.every(2).minutes.do(tracked_schedule("task.reminders", lambda: run_async(job_task_reminders())))
    schedule.every().sunday.at("20:00").do(tracked_schedule("research.cycle", lambda: run_async(job_research_cycle())))
    schedule.every().sunday.at("20:00").do(tracked_schedule("weekly.reflection", lambda: run_async(job_weekly_reflection())))
    schedule.every(30).minutes.do(tracked_schedule("brain.sweep", job_brain_sweep))
    schedule.every().day.at("04:00").do(tracked_schedule("brain.decay", job_brain_decay))
    schedule.every().hour.do(tracked_schedule("brain.import_expire", job_brain_import_expire))
    schedule.every(45).minutes.do(tracked_schedule("graph.sync", job_graph_sync))
    schedule.every().hour.do(tracked_schedule("storage.scan_db", job_storage_scan_db))
    schedule.every().day.at("04:30").do(tracked_schedule("storage.scan_fs", job_storage_scan_fs))
    # News V2 (#23): flag-gated no-ops until news.v2_enabled/v2_shadow turn on
    schedule.every().hour.do(tracked_schedule("news_v2.refresh", job_news_v2_refresh))
    schedule.every().day.at("04:15").do(tracked_schedule("news_v2.retention", job_news_v2_retention))
    # Explore → News (#9): per-pillar tuned cadence [E24]
    schedule.every().hour.do(tracked_schedule("explore.news", job_explore_news))
    schedule.every(3).hours.do(tracked_schedule("explore.tools", job_explore_tools))
    schedule.every(6).hours.do(tracked_schedule("explore.social", job_explore_social))
    schedule.every().day.at("03:30").do(tracked_schedule("explore.models", job_explore_models))
    schedule.every().day.at("09:00").do(
        tracked_schedule("ceo.review", lambda: run_async(job_ceo_review()) if datetime.now().day == 1 else None)
    )
    logger.info("📅 Schedules: daily 08:00 report | every 6h execution | task reminders 2m | sunday 20:00 research+reflection | brain sweep 30m + decay 04:00 | storage scan db 1h + fs 04:30 | explore news 1h / tools 3h / social 6h / models 03:30 | monthly CEO review")

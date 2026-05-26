from dotenv import load_dotenv
load_dotenv()

"""
MAIN ORCHESTRATOR - MMO Agent System
======================================
Entry point chính của toàn bộ hệ thống.
Điều phối tất cả modules theo lịch trình.

SCHEDULES:
  Every 6h   → execute_all_projects()   (agent tasks)
  Daily 8 AM → send_daily_report()      (Telegram)
  Sunday 8PM → run_research_cycle()     (niche discovery)
  Monthly 1st → run_ceo_review()        (strategic review)

Usage:
  python main.py              # Start all (daemon mode)
  python main.py research     # Manual: run research now
  python main.py execute      # Manual: run execution now
  python main.py ceo          # Manual: run CEO review now
  python main.py status       # Print system status
  python main.py test         # Test all connections
"""

import os
import sys
import asyncio
import logging
from datetime import datetime

try:
    import schedule
    import time
except ImportError:
    print("Install: pip install schedule")
    sys.exit(1)

# System modules
from core.database import init_database, get_dashboard
from core.model_router import llm_complete
from core.research_engine import run_research_cycle
from core.project_executor import execute_all_projects
from core.ceo_loop import run_ceo_review, format_ceo_telegram_summary
from core.telegram_bot import build_app, send_daily_report, send_message, send_project_proposal

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("/workspaces/tobi/logs/system.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# Global Telegram app
_tg_app = None


# ─────────────────────────────────────────
# Telegram App Management
# ─────────────────────────────────────────

async def get_telegram_app():
    global _tg_app
    if _tg_app is None:
        _tg_app = build_app()
        await _tg_app.initialize()
        await _tg_app.start()
    return _tg_app


async def notify(message: str):
    """Quick send to Telegram."""
    try:
        app = await get_telegram_app()
        await send_message(app, message)
    except Exception as e:
        logger.error(f"Telegram notify error: {e}")


# ─────────────────────────────────────────
# Scheduled Jobs
# ─────────────────────────────────────────

async def job_daily_report():
    """Gửi daily report qua Telegram mỗi sáng 8 AM."""
    logger.info("📅 Running daily report job...")
    try:
        app = await get_telegram_app()
        await send_daily_report(app)
        logger.info("✅ Daily report sent")
    except Exception as e:
        logger.error(f"Daily report error: {e}")


async def job_execution_cycle():
    """Execute active project tasks mỗi 6 giờ."""
    logger.info("⚙️  Running execution cycle...")
    try:
        results = execute_all_projects(tasks_per_project=3)

        if not results:
            return

        # Build summary
        total_tasks = sum(r.get("tasks_executed", 0) for r in results)
        needs_human = [
            r for r in results
            if r.get("human_todos_count", 0) > 0 and not r.get("error")
        ]

        if total_tasks > 0:
            summary = f"⚙️ *Execution complete*\n{total_tasks} tasks done across {len(results)} projects"
            await notify(summary)

        # Alert cho projects cần human
        if needs_human:
            app = await get_telegram_app()
            for r in needs_human:
                from core.telegram_bot import send_human_alert
                await send_human_alert(
                    app,
                    r["project_name"],
                    r.get("human_todos", []),
                )

        logger.info(f"✅ Execution cycle: {total_tasks} tasks done")

    except Exception as e:
        logger.error(f"Execution cycle error: {e}")
        await notify(f"⚠️ Execution error: {str(e)[:200]}")


async def job_research_cycle():
    """Weekly research: tìm niches mới và propose."""
    logger.info("🔬 Running weekly research cycle...")
    await notify("🔬 *Weekly Research Started*\nĐang tìm kiếm cơ hội mới...")

    try:
        project_ids = run_research_cycle()

        if not project_ids:
            await notify("🔬 Research complete — không tìm thấy cơ hội nổi bật tuần này.")
            return

        # Send proposals to Telegram
        app = await get_telegram_app()
        from core.database import get_project

        for pid in project_ids:
            project = get_project(pid)
            if project:
                await send_project_proposal(app, pid, project.get("business_plan", {}))
                await asyncio.sleep(2)

        logger.info(f"✅ Research cycle: {len(project_ids)} proposals sent")

    except Exception as e:
        logger.error(f"Research cycle error: {e}")
        await notify(f"⚠️ Research error: {str(e)[:200]}")


async def job_ceo_review():
    """Monthly CEO review và strategy update."""
    logger.info("🎯 Running monthly CEO review...")
    await notify("🎯 *Monthly CEO Review Starting...*")

    try:
        analysis = run_ceo_review()

        if analysis.get("status") == "no_projects":
            await notify("🎯 CEO Review: Chưa có project nào để review.")
            return

        # Send Telegram summary
        summary = format_ceo_telegram_summary(analysis)
        await notify(summary)

        logger.info("✅ CEO review complete")

    except Exception as e:
        logger.error(f"CEO review error: {e}")
        await notify(f"⚠️ CEO review error: {str(e)[:200]}")


# ─────────────────────────────────────────
# Scheduler Wrappers (sync → async bridge)
# ─────────────────────────────────────────

def run_async(coro):
    """Chạy coroutine từ sync scheduler."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(coro)
        else:
            loop.run_until_complete(coro)
    except RuntimeError:
        asyncio.run(coro)


def scheduled_daily_report():
    run_async(job_daily_report())


def scheduled_execution():
    run_async(job_execution_cycle())


def scheduled_research():
    run_async(job_research_cycle())


def scheduled_ceo_review():
    run_async(job_ceo_review())


# ─────────────────────────────────────────
# Setup Schedules
# ─────────────────────────────────────────

def setup_schedules():
    # Daily 8 AM report
    schedule.every().day.at("08:00").do(scheduled_daily_report)

    # Every 6 hours execution
    schedule.every(6).hours.do(scheduled_execution)

    # Weekly research - Sunday 8 PM
    schedule.every().sunday.at("20:00").do(scheduled_research)

    # Monthly CEO review - 1st of month at 9 AM
    schedule.every().day.at("09:00").do(
        lambda: scheduled_ceo_review() if datetime.now().day == 1 else None
    )

    logger.info("📅 Schedules configured:")
    logger.info("  • Daily 08:00    → Daily report")
    logger.info("  • Every 6 hours  → Execution cycle")
    logger.info("  • Sunday 20:00   → Research cycle")
    logger.info("  • Monthly 1st    → CEO review")


# ─────────────────────────────────────────
# System Status
# ─────────────────────────────────────────

def print_status():
    """Print current system status."""
    dash = get_dashboard()
    projects = dash.get("projects", {})
    revenue = dash.get("revenue", {})

    print("\n" + "="*50)
    print("🤖 MMO AGENT SYSTEM STATUS")
    print("="*50)
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"\nProjects:")
    for status, count in projects.items():
        print(f"  {status}: {count}")
    print(f"\nRevenue:")
    print(f"  This month: ${revenue.get('this_month', 0):.2f}")
    print(f"  All-time:   ${revenue.get('total_all_time', 0):.2f}")
    print(f"\nHuman TODOs: {dash.get('human_todos_count', 0)}")
    print(f"\nConfig:")
    print(f"  Model: {os.getenv('PRIMARY_MODEL', 'claude (default)')}")
    print(f"  Telegram: {'✅' if os.getenv('TELEGRAM_BOT_TOKEN') else '❌ missing'}")
    print(f"  Tavily: {'✅' if os.getenv('TAVILY_API_KEY') else '⚠️ missing (search limited)'}")
    print("="*50 + "\n")


# ─────────────────────────────────────────
# Connection Tests
# ─────────────────────────────────────────

async def test_connections():
    """Test tất cả connections trước khi run."""
    print("\n🧪 Testing connections...\n")
    all_ok = True

    # Test LLM
    print("1. Testing LLM (Claude API)...")
    try:
        result = llm_complete("Reply with exactly: OK", task_type="simple", max_tokens=10)
        print(f"   ✅ LLM OK: {result.strip()[:30]}")
    except Exception as e:
        print(f"   ❌ LLM FAILED: {e}")
        all_ok = False

    # Test Telegram
    print("2. Testing Telegram bot...")
    try:
        app = await get_telegram_app()
        me = await app.bot.get_me()
        print(f"   ✅ Telegram OK: @{me.username}")
    except Exception as e:
        print(f"   ❌ Telegram FAILED: {e}")
        all_ok = False

    # Test Database
    print("3. Testing database...")
    try:
        dash = get_dashboard()
        print(f"   ✅ Database OK: {sum(dash.get('projects', {}).values())} projects")
    except Exception as e:
        print(f"   ❌ Database FAILED: {e}")
        all_ok = False

    # Test Tavily (optional)
    print("4. Testing Tavily search...")
    if os.getenv("TAVILY_API_KEY"):
        try:
            from core.research_engine import tavily_search
            results = tavily_search("test", max_results=1)
            print(f"   ✅ Tavily OK: got {len(results)} results")
        except Exception as e:
            print(f"   ⚠️  Tavily WARNING: {e}")
    else:
        print("   ⚠️  Tavily: No API key (will use limited search)")

    print(f"\n{'✅ All systems GO!' if all_ok else '❌ Some checks failed - check config'}\n")
    return all_ok


# ─────────────────────────────────────────
# Main Entry Points
# ─────────────────────────────────────────

async def startup_notification():
    """Gửi startup notification."""
    await notify(
        "🚀 *MMO Agent System Started*\n"
        f"Time: {datetime.now().strftime('%d/%m/%Y %H:%M')}\n"
        f"Model: {os.getenv('PRIMARY_MODEL', 'claude')}\n\n"
        "System is now running 24/7.\n"
        "Type /status để xem tổng quan."
    )


async def run_daemon():
    """Main daemon mode - chạy liên tục."""
    # Init
    init_database()
    print_status()

    # Test connections
    ok = await test_connections()
    if not ok:
        print("⚠️  Some connections failed. Continuing anyway...")

    # Setup schedules
    setup_schedules()

    # Startup notification
    await startup_notification()

    # Run initial execution cycle
    logger.info("Running initial execution cycle...")
    await job_execution_cycle()

    # Start Telegram bot (non-blocking polling)
    app = await get_telegram_app()

    logger.info("🤖 System running. Ctrl+C to stop.\n")

    # Main loop
    while True:
        schedule.run_pending()
        await asyncio.sleep(60)  # Check every minute


async def run_telegram_bot():
    """Run Telegram bot only (for separate process)."""
    init_database()
    app = build_app()
    print("🤖 Starting Telegram bot...")
    app.run_polling(drop_pending_updates=True)


# ─────────────────────────────────────────
# CLI
# ─────────────────────────────────────────

async def main_async():
    command = sys.argv[1] if len(sys.argv) > 1 else "start"

    if command == "start":
        await run_daemon()

    elif command == "research":
        init_database()
        print("🔬 Running manual research cycle...")
        project_ids = run_research_cycle()
        if project_ids:
            app = await get_telegram_app()
            from core.database import get_project
            for pid in project_ids:
                p = get_project(pid)
                if p:
                    await send_project_proposal(app, pid, p.get("business_plan", {}))
        print(f"Done: {project_ids}")

    elif command == "execute":
        init_database()
        print("⚙️  Running manual execution cycle...")
        results = execute_all_projects(tasks_per_project=5)
        print(f"Done: {len(results)} projects processed")

    elif command == "ceo":
        init_database()
        print("🎯 Running manual CEO review...")
        analysis = run_ceo_review()
        print("Done. Check Telegram for summary.")
        await notify(format_ceo_telegram_summary(analysis))

    elif command == "status":
        init_database()
        print_status()

    elif command == "test":
        init_database()
        await test_connections()

    elif command == "bot":
        print("Starting Telegram bot only...")
        await run_telegram_bot()

    else:
        print(f"Unknown command: {command}")
        print("Usage: python main.py [start|research|execute|ceo|status|test|bot]")


if __name__ == "__main__":
    # run_polling() manages its own event loop — must run outside asyncio.run()
    if len(sys.argv) > 1 and sys.argv[1] == "bot":
        init_database()
        app = build_app()
        print("🤖 Starting Telegram bot...")
        app.run_polling(drop_pending_updates=True)
    else:
        asyncio.run(main_async())

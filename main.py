from core.env_utils import safe_load_dotenv
safe_load_dotenv()

"""
TOBI — Main Orchestrator
=========================
python main.py start      → full system (bot + API + dashboard + scheduler)
python main.py bot        → Telegram bot only
python main.py api        → API + Dashboard only
python main.py research   → manual research cycle
python main.py execute    → manual execution cycle
python main.py ceo        → manual CEO review
python main.py status     → print system status
python main.py test       → test all connections
python main.py terminal   → interactive terminal chat with Tobi

Schedules (Vietnam GMT+7):
  Every 6h      → execute_all_projects()
  Daily 08:00   → send_daily_report()
  Sunday 20:00  → run_research_cycle() + weekly_self_reflection()
  Monthly 1st   → run_ceo_review()
"""

import os
import sys
import signal
import shutil
import asyncio
import logging
import threading
from datetime import datetime
from pathlib import Path

try:
    import schedule
    import time
except ImportError:
    print("pip install schedule")
    sys.exit(1)

from core.database import init_database, get_dashboard, get_all_lessons, add_lesson
from core.model_router import llm_complete
from core.research_engine import run_research_cycle
from core.project_executor import execute_all_projects
from core.ceo_loop import run_ceo_review, format_ceo_telegram_summary
from core.telegram_bot import build_app, send_daily_report, send_message, send_project_proposal, run_terminal_session

_PID_FILE = Path(__file__).parent / ".tobi" / "tobi.pid"


def ensure_single_instance():
    """Kill any existing Tobi process before starting, then claim the PID file."""
    if _PID_FILE.exists():
        try:
            old_pid = int(_PID_FILE.read_text().strip())
            os.kill(old_pid, 0)  # raises if process doesn't exist
            print(f"[single-instance] Stopping existing Tobi (PID {old_pid})...")
            os.kill(old_pid, signal.SIGTERM)
            for _ in range(20):          # wait up to 10 s for clean exit
                time.sleep(0.5)
                try:
                    os.kill(old_pid, 0)
                except ProcessLookupError:
                    break
            else:
                os.kill(old_pid, signal.SIGKILL)
            time.sleep(1)               # let OS release ports
        except (ProcessLookupError, ValueError):
            pass                        # stale PID file — ignore
    _PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    _PID_FILE.write_text(str(os.getpid()))

    def _cleanup():
        try:
            if _PID_FILE.exists() and _PID_FILE.read_text().strip() == str(os.getpid()):
                _PID_FILE.unlink()
        except Exception:
            pass

    import atexit
    atexit.register(_cleanup)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("/workspaces/tobi/logs/system.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

_tg_app = None


# ─────────────────────────────────────────
# Startup: sync SOUL + skills
# ─────────────────────────────────────────

def sync_soul_and_skills():
    soul_src = "/workspaces/tobi/SOUL.md"
    soul_dst = os.path.expanduser("~/.hermes/SOUL.md")
    if os.path.exists(soul_src):
        try:
            shutil.copy2(soul_src, soul_dst)
            logger.info(f"✅ SOUL.md synced → {soul_dst}")
        except Exception as e:
            logger.warning(f"SOUL.md sync failed: {e}")

    skills_src = "/workspaces/tobi/hermes_skills"
    skills_dst = os.path.expanduser("~/.hermes/skills/tobi")
    if os.path.exists(skills_src):
        try:
            os.makedirs(skills_dst, exist_ok=True)
            for f in os.listdir(skills_src):
                if f.endswith(".md"):
                    shutil.copy2(os.path.join(skills_src, f), os.path.join(skills_dst, f))
            logger.info(f"✅ Skills synced → {skills_dst}")
        except Exception as e:
            logger.warning(f"Skills sync failed: {e}")


# ─────────────────────────────────────────
# Background servers (API + Dashboard)
# ─────────────────────────────────────────

def start_api_server():
    try:
        import uvicorn
        from api.server import app as api_app
        port = int(os.getenv("API_PORT", 8000))
        logger.info(f"🌐 API server starting on :{port}")
        uvicorn.run(api_app, host="0.0.0.0", port=port, log_level="warning")
    except ImportError:
        logger.warning("FastAPI/uvicorn not installed — API server skipped. pip install fastapi uvicorn")
    except Exception as e:
        logger.error(f"API server error: {e}")


def start_dashboard_server():
    try:
        import uvicorn
        from api.dashboard import app as dash_app
        port = int(os.getenv("DASHBOARD_PORT", 8080))
        logger.info(f"📊 Dashboard starting on :{port}")
        uvicorn.run(dash_app, host="0.0.0.0", port=port, log_level="warning")
    except ImportError:
        logger.warning("FastAPI/uvicorn not installed — Dashboard skipped.")
    except Exception as e:
        logger.error(f"Dashboard error: {e}")


def _ensure_port_public():
    """Flip the dashboard port to public in GitHub Codespaces after it binds."""
    codespace = os.getenv("CODESPACE_NAME")
    if not codespace:
        return
    port = os.getenv("DASHBOARD_PORT", "8080")
    for _ in range(30):
        time.sleep(2)
        try:
            import urllib.request
            urllib.request.urlopen(f"http://localhost:{port}/api/status", timeout=2)
            ret = os.system(f"gh codespace ports visibility {port}:public -c {codespace} >/dev/null 2>&1")
            if ret == 0:
                logger.info(f"🌐 Port {port} set to public (Codespace)")
            return
        except Exception:
            continue


def launch_background_servers():
    threading.Thread(target=start_api_server,    daemon=True, name="api").start()
    threading.Thread(target=start_dashboard_server, daemon=True, name="dashboard").start()
    threading.Thread(target=_ensure_port_public, daemon=True, name="port-public").start()
    time.sleep(1)  # brief pause for servers to bind


# ─────────────────────────────────────────
# Telegram
# ─────────────────────────────────────────

async def get_telegram_app():
    global _tg_app
    if _tg_app is None:
        _tg_app = build_app()
        await _tg_app.initialize()
        await _tg_app.start()
    return _tg_app


async def notify(message: str):
    try:
        app = await get_telegram_app()
        await send_message(app, message)
    except Exception as e:
        logger.error(f"Telegram notify error: {e}")


# ─────────────────────────────────────────
# Scheduled Jobs
# ─────────────────────────────────────────

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


# ─────────────────────────────────────────
# Scheduler bridge
# ─────────────────────────────────────────

def run_async(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(coro)
        else:
            loop.run_until_complete(coro)
    except RuntimeError:
        asyncio.run(coro)


def setup_schedules():
    schedule.every().day.at("08:00").do(lambda: run_async(job_daily_report()))
    schedule.every(6).hours.do(lambda: run_async(job_execution_cycle()))
    schedule.every().sunday.at("20:00").do(lambda: run_async(job_research_cycle()))
    schedule.every().sunday.at("20:00").do(lambda: run_async(job_weekly_reflection()))
    schedule.every().day.at("09:00").do(
        lambda: run_async(job_ceo_review()) if datetime.now().day == 1 else None
    )
    logger.info("📅 Schedules: daily 08:00 report | every 6h execution | sunday 20:00 research+reflection | monthly CEO review")


# ─────────────────────────────────────────
# Status
# ─────────────────────────────────────────

def get_dashboard_url() -> str:
    """Return the public-accessible Mission Control URL."""
    port = os.getenv("DASHBOARD_PORT", "8080")
    custom = os.getenv("DASHBOARD_URL")
    if custom:
        return custom
    codespace = os.getenv("CODESPACE_NAME")
    domain = os.getenv("GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN", "app.github.dev")
    if codespace:
        return f"https://{codespace}-{port}.{domain}"
    return f"http://localhost:{port}"


def print_status():
    dash = get_dashboard()
    projects = dash.get("projects", {})
    revenue = dash.get("revenue", {})
    mc_url = get_dashboard_url()
    print("\n" + "="*50)
    print("🤖 TOBI STATUS")
    print("="*50)
    print(f"Time:   {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"\nProjects: {projects}")
    print(f"Revenue this month: ${revenue.get('this_month', 0):.2f}")
    print(f"Revenue all-time:   ${revenue.get('total_all_time', 0):.2f}")
    print(f"Human TODOs: {dash.get('human_todos_count', 0)}")
    print(f"\nConfig:")
    print(f"  Model:     {os.getenv('PRIMARY_MODEL', 'openrouter')}")
    print(f"  Telegram:  {'✅' if os.getenv('TELEGRAM_BOT_TOKEN') else '❌'}")
    print(f"  Tavily:    {'✅' if os.getenv('TAVILY_API_KEY') else '⚠️ missing'}")
    print(f"  API:       http://localhost:{os.getenv('API_PORT','8000')}")
    print(f"  Mission Control: {mc_url}")
    print("="*50 + "\n")


# ─────────────────────────────────────────
# Connection test
# ─────────────────────────────────────────

async def test_connections():
    print("\n🧪 Testing connections...\n")
    all_ok = True

    print("1. LLM...")
    try:
        r = llm_complete("Reply: OK", task_type="simple", max_tokens=10)
        print(f"   ✅ LLM: {r.strip()[:30]}")
    except Exception as e:
        print(f"   ❌ LLM: {e}")
        all_ok = False

    print("2. Telegram...")
    try:
        app = await get_telegram_app()
        me = await app.bot.get_me()
        print(f"   ✅ Telegram: @{me.username}")
    except Exception as e:
        print(f"   ❌ Telegram: {e}")
        all_ok = False

    print("3. Database...")
    try:
        dash = get_dashboard()
        print(f"   ✅ Database: {sum(dash.get('projects',{}).values())} projects")
    except Exception as e:
        print(f"   ❌ Database: {e}")
        all_ok = False

    print("4. Tavily...")
    if os.getenv("TAVILY_API_KEY"):
        try:
            from core.research_engine import tavily_search
            r = tavily_search("test", max_results=1)
            print(f"   ✅ Tavily: {len(r)} result(s)")
        except Exception as e:
            print(f"   ⚠️  Tavily: {e}")
    else:
        print("   ⚠️  Tavily: no key")

    print("5. Integrations...")
    try:
        from core.integrations import check_all
        status = check_all()
        ok = sum(1 for v in status.values() if v)
        print(f"   ✅ Integrations: {ok}/{len(status)} available")
    except Exception as e:
        print(f"   ⚠️  Integrations: {e}")

    print(f"\n{'✅ All systems GO!' if all_ok else '❌ Some checks failed'}\n")
    return all_ok


# ─────────────────────────────────────────
# Main modes
# ─────────────────────────────────────────

async def run_daemon():
    ensure_single_instance()
    init_database()
    sync_soul_and_skills()
    print_status()

    ok = await test_connections()
    if not ok:
        print("⚠️  Some checks failed. Continuing anyway...")

    launch_background_servers()
    setup_schedules()

    mc_url = get_dashboard_url()
    await notify(
        f"🚀 *Tobi Started*\n"
        f"Time: {datetime.now().strftime('%d/%m/%Y %H:%M')}\n"
        f"Model: {os.getenv('PRIMARY_MODEL','openrouter')}\n"
        f"Mission Control: {mc_url}\n\n"
        f"System running 24/7\\. /status để xem tổng quan\\."
    )

    logger.info("Running initial execution cycle...")
    await job_execution_cycle()

    app = await get_telegram_app()
    await app.updater.start_polling(drop_pending_updates=True)
    logger.info("🤖 Tobi running + polling Telegram. Ctrl+C to stop.\n")

    try:
        while True:
            schedule.run_pending()
            await asyncio.sleep(60)
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()


async def main_async():
    command = sys.argv[1] if len(sys.argv) > 1 else "start"

    if command == "start":
        await run_daemon()

    elif command == "research":
        init_database()
        print("🔬 Running manual research...")
        ids = run_research_cycle()
        if ids:
            app = await get_telegram_app()
            from core.database import get_project
            for pid in ids:
                p = get_project(pid)
                if p:
                    await send_project_proposal(app, pid, p.get("business_plan", {}))
        print(f"Done: {ids}")

    elif command == "execute":
        init_database()
        print("⚙️  Running manual execution...")
        results = execute_all_projects(tasks_per_project=5)
        print(f"Done: {len(results)} projects")

    elif command == "ceo":
        init_database()
        print("🎯 Running CEO review...")
        analysis = run_ceo_review()
        await notify(format_ceo_telegram_summary(analysis))
        print("Done.")

    elif command == "status":
        init_database()
        print_status()

    elif command == "test":
        init_database()
        await test_connections()

    elif command == "api":
        init_database()
        print(f"🌐 Starting API on :{os.getenv('API_PORT','8000')} and Dashboard on :{os.getenv('DASHBOARD_PORT','8080')}")
        launch_background_servers()
        print("Press Ctrl+C to stop.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nStopped.")

    elif command == "terminal":
        init_database()
        await run_terminal_session()

    else:
        print(f"Unknown command: {command}")
        print("Usage: python main.py [start|bot|api|research|execute|ceo|status|test|terminal]")


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "start"

    if command == "bot":
        # run_polling manages its own event loop — must be outside asyncio.run()
        init_database()
        sync_soul_and_skills()
        app = build_app()
        print("🤖 Starting Tobi Telegram bot...")
        app.run_polling(drop_pending_updates=True)
    else:
        asyncio.run(main_async())

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
python main.py dev ...    → controlled coding workflows through Mission Control

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

# Windows consoles often default to a non-UTF-8 codepage (e.g. cp1258 on a
# Vietnamese locale), which raises UnicodeEncodeError on the emoji used in
# log/print statements throughout the codebase. Force UTF-8 console I/O.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

from core.database import init_database, get_dashboard, get_all_lessons, add_lesson
from core.model_router import llm_complete
from core.research_engine import run_research_cycle
from core.project_executor import execute_all_projects
from core.ceo_loop import run_ceo_review, format_ceo_telegram_summary
from core.telegram_bot import build_app, send_daily_report, send_message, send_project_proposal, run_terminal_session

PROJECT_DIR = Path(__file__).resolve().parent
_PID_FILE = PROJECT_DIR / ".tobi" / "tobi.pid"


def _run_dev_cli(args: list[str]) -> int:
    """Operate Developer through its API so CLI and MC share policy and state."""
    import getpass
    import json as _json
    import uuid as _uuid
    import requests as _requests

    base = os.getenv("TOBI_MC_URL", f"http://127.0.0.1:{os.getenv('DASHBOARD_PORT', '8080')}").rstrip("/")
    session = os.getenv("TOBI_VAULT_SESSION", "")
    if not session:
        print("Set TOBI_VAULT_SESSION to the current in-memory vault session before using `tobi dev`.")
        return 2
    headers = {"X-Vault-Session": session, "Content-Type": "application/json"}

    def call(method: str, path: str, payload=None):
        response = _requests.request(method, f"{base}{path}", headers=headers, json=payload, timeout=30)
        if response.status_code >= 400:
            try:
                detail = response.json().get("detail", response.text)
            except Exception:
                detail = response.text
            raise RuntimeError(f"Developer API HTTP {response.status_code}: {detail}")
        return response.json() if response.content else {}

    action = args[0] if args else "status"
    try:
        if action == "start":
            if len(args) < 2:
                raise RuntimeError("Usage: tobi dev start <queue-id>")
            data = call("POST", "/api/developer/workflows", {
                "queue_id": int(args[1]), "idempotency_key": str(_uuid.uuid4()), "start": True,
            })
        elif action == "status":
            data = call("GET", f"/api/developer/workflows/{int(args[1])}") if len(args) > 1 else call("GET", "/api/developer/overview")
        elif action == "logs":
            if len(args) < 2:
                raise RuntimeError("Usage: tobi dev logs <workflow-id>")
            data = call("GET", f"/api/developer/events?workflow_id={int(args[1])}&after=0")
        elif action in {"pause", "resume", "cancel", "retry"}:
            if len(args) < 2:
                raise RuntimeError(f"Usage: tobi dev {action} <workflow-id>")
            data = call("POST", f"/api/developer/workflows/{int(args[1])}/commands", {
                "command": action, "idempotency_key": str(_uuid.uuid4()),
            })
        elif action == "approve":
            if len(args) < 3:
                raise RuntimeError("Usage: tobi dev approve <workflow-id> <special_paths|merge_deploy>")
            workflow_id, purpose = int(args[1]), args[2]
            challenge = call("POST", "/api/developer/reauth", {
                "master": getpass.getpass("Vault master password: "),
                "purpose": purpose,
                "workflow_id": workflow_id,
            })
            data = call("POST", f"/api/developer/workflows/{workflow_id}/approve", {
                "purpose": purpose, "challenge": challenge["challenge"],
            })
        elif action == "queue":
            data = call("GET", "/api/developer/queue")
        elif action == "goal-create":
            title = " ".join(args[1:]).strip() or input("Goal title: ").strip()
            objective = input("Objective: ").strip()
            criteria = [item.strip() for item in input("Acceptance criteria (separate with ;;): ").split(";;") if item.strip()]
            models = [item.strip() for item in input("Preferred model IDs (optional, comma-separated): ").split(",") if item.strip()]
            data = call("POST", "/api/developer/goals", {
                "title": title, "objective": objective, "acceptance_criteria": criteria,
                "preferred_models": models, "autonomy": "sandbox",
            })
        elif action == "goal-list":
            data = call("GET", "/api/developer/goals")
        elif action == "goal-status":
            if len(args) < 2:
                raise RuntimeError("Usage: tobi dev goal-status <goal-id>")
            data = call("GET", f"/api/developer/goals/{int(args[1])}")
        elif action in {"goal-pause", "goal-resume", "goal-cancel"}:
            if len(args) < 2:
                raise RuntimeError(f"Usage: tobi dev {action} <goal-id>")
            data = call("POST", f"/api/developer/goals/{int(args[1])}/commands", {
                "command": action.removeprefix("goal-"), "idempotency_key": str(_uuid.uuid4()),
            })
        else:
            raise RuntimeError("Usage: tobi dev [start|status|logs|pause|resume|cancel|retry|approve|queue|goal-create|goal-list|goal-status|goal-pause|goal-resume|goal-cancel]")
        print(_json.dumps(data, indent=2, ensure_ascii=False, default=str))
        return 0
    except (ValueError, RuntimeError, _requests.RequestException) as exc:
        print(str(exc))
        return 1


def _pid_alive(pid: int) -> bool:
    """Cross-platform 'is this PID running?' check.

    On Windows `os.kill(pid, 0)` is NOT a no-op existence probe — signal 0 maps
    to CTRL_C_EVENT — so we shell out to `tasklist` instead.
    """
    if pid <= 0:
        return False
    if os.name == "nt":
        import subprocess
        try:
            out = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                capture_output=True, text=True, timeout=10,
            ).stdout
            return str(pid) in out
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _terminate_pid(pid: int, force: bool = False) -> None:
    """Cross-platform process termination."""
    if os.name == "nt":
        import subprocess
        args = ["taskkill", "/PID", str(pid)] + (["/F"] if force else [])
        subprocess.run(args, capture_output=True, text=True)
        return
    os.kill(pid, signal.SIGKILL if force else signal.SIGTERM)


def ensure_single_instance():
    """Kill any existing Tobi process before starting, then claim the PID file."""
    if _PID_FILE.exists():
        try:
            old_pid = int(_PID_FILE.read_text().strip())
            if _pid_alive(old_pid):
                print(f"[single-instance] Stopping existing Tobi (PID {old_pid})...")
                _terminate_pid(old_pid, force=False)
                for _ in range(20):          # wait up to 10 s for clean exit
                    time.sleep(0.5)
                    if not _pid_alive(old_pid):
                        break
                else:
                    _terminate_pid(old_pid, force=True)
                time.sleep(1)               # let OS release ports
        except ValueError:
            pass                        # stale/garbage PID file — ignore
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


_LOG_DIR = PROJECT_DIR / "logs"
_LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(str(_LOG_DIR / "system.log"), encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# ── Silence noisy HTTP polling logs (Telegram getUpdates, httpx, etc.) ──
for _name in ("httpx", "httpcore", "openai", "urllib3"):
    logging.getLogger(_name).setLevel(logging.WARNING)

_tg_app = None


# ─────────────────────────────────────────
# Startup: sync SOUL + skills
# ─────────────────────────────────────────

def sync_soul_and_skills():
    # HERMES_DIR lets us keep Hermes-synced files off the C: home dir.
    hermes_dir = os.path.expanduser(os.getenv("HERMES_DIR", "~/.hermes"))

    soul_src = str(PROJECT_DIR / "SOUL.md")
    soul_dst = os.path.join(hermes_dir, "SOUL.md")
    if os.path.exists(soul_src):
        try:
            os.makedirs(os.path.dirname(soul_dst), exist_ok=True)
            shutil.copy2(soul_src, soul_dst)
            logger.info(f"✅ SOUL.md synced → {soul_dst}")
        except Exception as e:
            logger.warning(f"SOUL.md sync failed: {e}")

    skills_src = str(PROJECT_DIR / "hermes_skills")
    skills_dst = os.path.join(hermes_dir, "skills", "tobi")
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

def _autounlock_vault():
    """Re-inject previously-connected integration secrets into os.environ at boot,
    using the vault's cached key (no master-password prompt). No-op if the vault
    isn't set up or auto-unlock was never enabled. Never raises."""
    try:
        from core import vault
        from core.database import get_connection
        if not vault.CRYPTO_AVAILABLE:
            return
        conn = get_connection()
        try:
            if vault.is_setup(conn) and vault.try_autounlock(conn):
                n = vault.inject_env(conn)
                logger.info(f"🔐 Vault auto-unlocked; {n} integration secret(s) live.")
        finally:
            conn.close()
    except Exception as e:
        logger.warning(f"Vault auto-unlock skipped: {e}")


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
    """Flip the dashboard port to public in GitHub Codespaces, retrying until
    `gh ports` actually confirms it.

    Codespaces forward ports as private by default and reset them to private on
    every restart, so the MC link 404s for anyone outside the Codespace until we
    re-flip. The previous version polled only 60s (too short on a cold boot),
    swallowed all errors, and never retried — so a single failed/raced flip left
    the port private with no trace. Now: wait up to 5 min for the dashboard to
    bind, then retry the flip up to 10x until the port listing reports `public`
    (the first call can race the port-forward registration), logging each step.
    """
    codespace = os.getenv("CODESPACE_NAME")
    if not codespace:
        return
    port = os.getenv("DASHBOARD_PORT", "8080")
    import urllib.request, subprocess, re

    # Wait up to 5 min (150 x 2s) for the dashboard to answer.
    for _ in range(150):
        try:
            urllib.request.urlopen(f"http://localhost:{port}/api/status", timeout=2)
            break
        except Exception:
            time.sleep(2)
    else:
        logger.warning(f"⚠️  Dashboard never answered on :{port} — skipped public flip")
        return

    # Flip to public, retrying until `gh ports` confirms it. The window is
    # generous (~2 min) because the port-FORWARD itself can lag: on a
    # restart-in-place (kill the old instance, relaunch) Codespaces tears down
    # the existing 8080 forward and re-registers it up to a minute later — until
    # it reappears in `gh ports` there is no port for `visibility` to act on, so
    # early attempts are silent no-ops. A fresh boot succeeds on attempt 1 and
    # exits immediately, so the long ceiling only costs time in the lag case.
    logger.info(f"🌐 Publishing port {port} to public (Codespace)…")
    attempts = 40
    for attempt in range(1, attempts + 1):
        subprocess.run(
            ["gh", "codespace", "ports", "visibility", f"{port}:public", "-c", codespace],
            capture_output=True, text=True,
        )
        try:
            listing = subprocess.run(
                ["gh", "codespace", "ports", "-c", codespace],
                capture_output=True, text=True, timeout=15,
            ).stdout
        except Exception:
            listing = ""
        if re.search(rf"{port}\s+public", listing):
            logger.info(f"🌐 Port {port} is PUBLIC (attempt {attempt}) — MC link is reachable")
            return
        # Stay quiet during the normal forward-registration lag — a healthy boot
        # succeeds on attempt 1, so this only loops when something's actually
        # wrong. Escalate to WARNING every 10th try instead of spamming 40 lines.
        if attempt % 10 == 0:
            logger.warning(f"⚠️  Port {port} still not public after {attempt}/{attempts} attempts — forward not registering")
        else:
            logger.debug(f"Port {port} not public yet (attempt {attempt}/{attempts}); retrying in 3s")
        time.sleep(3)
    logger.error(f"❌ Could not make port {port} public after {attempts} attempts — MC link will 404 externally")


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


# ── Explore → News (#9): per-pillar tuned cadence [E24] ───────────────────────
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
    schedule.every(2).minutes.do(lambda: run_async(job_task_reminders()))
    schedule.every().sunday.at("20:00").do(lambda: run_async(job_research_cycle()))
    schedule.every().sunday.at("20:00").do(lambda: run_async(job_weekly_reflection()))
    schedule.every(30).minutes.do(job_brain_sweep)
    schedule.every().day.at("04:00").do(job_brain_decay)
    schedule.every(45).minutes.do(job_graph_sync)
    schedule.every().hour.do(job_storage_scan_db)
    schedule.every().day.at("04:30").do(job_storage_scan_fs)
    # Explore → News (#9): per-pillar tuned cadence [E24]
    schedule.every().hour.do(job_explore_news)
    schedule.every(3).hours.do(job_explore_tools)
    schedule.every(6).hours.do(job_explore_social)
    schedule.every().day.at("03:30").do(job_explore_models)
    schedule.every().day.at("09:00").do(
        lambda: run_async(job_ceo_review()) if datetime.now().day == 1 else None
    )
    logger.info("📅 Schedules: daily 08:00 report | every 6h execution | task reminders 2m | sunday 20:00 research+reflection | brain sweep 30m + decay 04:00 | storage scan db 1h + fs 04:30 | explore news 1h / tools 3h / social 6h / models 03:30 | monthly CEO review")


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
    _autounlock_vault()
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

    import time as _time, math as _math
    _boot = _time.time()
    _pulse = 0
    # Smoke wisps — each heartbeat prints a different fragment so when many
    # lines accumulate in the console they form a flowing smoke wave pattern.
    _SMOKE_CHARS = ['·', '⋅', '∘', '○', '◌', '◯', '○', '∘', '⋅', '·']
    _SMOPE_WISP = '˜'
    try:
        while True:
            schedule.run_pending()
            _pulse += 1
            if _pulse % 5 == 0:  # every ~5 min
                _mins = int((_time.time() - _boot) / 60)
                _h = _mins // 60
                _m = _mins % 60
                _uptime = f"{_h}h{_m:02d}m" if _h else f"{_m}m"
                # Smoke intensity breathes in a sine wave (0–6 wisps)
                _wave = round(_math.sin((_pulse / 5) * 0.6) * 3 + 3)
                _char = _SMOKE_CHARS[(_pulse // 5) % len(_SMOKE_CHARS)]
                _wisps = _SMOPE_WISP * max(0, _wave)
                logger.info(f"🚬 still smoking, everything okay! · uptime {_uptime}  {_wisps}{_char}")
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

    elif command == "hermes":
        # `tobi hermes <args>` — thin passthrough to the Hermes runtime + MC logging (#11 D2/D20).
        import shutil as _shutil
        init_database()
        hargs = sys.argv[2:]
        try:
            from core import conductor as _c
            _c._log_action(_c._default_chat_id(), "cli", "tobi_cli",
                           {"argv": hargs}, "read", "executed", f"tobi hermes {' '.join(hargs)}"[:120], None)
        except Exception:
            pass
        exe = _shutil.which("hermes")
        if not exe:
            print("hermes isn't on PATH — this command wraps the Hermes runtime (see HERMES_* guides).")
            print("For the interactive TOBI terminal, run:  tobi terminal")
        else:
            import subprocess as _sp
            raise SystemExit(_sp.call([exe, *hargs]))

    elif command == "dev":
        raise SystemExit(_run_dev_cli(sys.argv[2:]))

    else:
        print(f"Unknown command: {command}")
        print("Usage: python main.py [start|bot|api|research|execute|ceo|status|test|terminal|hermes|dev]")


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

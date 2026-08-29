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
from core.research_engine import run_research_cycle
from core.project_executor import execute_all_projects
from core.ceo_loop import run_ceo_review, format_ceo_telegram_summary
from core.telegram_bot import build_app, send_daily_report, send_message, send_project_proposal, run_terminal_session

# Scheduled jobs + the Telegram notifier moved to core/scheduled_jobs.py (Phase 4b).
# Imported back so schedule registration and every call site here are unchanged.
from core.scheduled_jobs import (
    get_telegram_app, job_execution_cycle, notify, setup_schedules,
    shutdown_telegram_app, start_telegram_polling,
)
from core.proc import no_window

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
                creationflags=no_window(),
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
        subprocess.run(args, capture_output=True, text=True, creationflags=no_window())
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
        conn = get_connection()
        try:
            if vault.CRYPTO_AVAILABLE and vault.is_setup(conn) and vault.try_autounlock(conn):
                n = vault.inject_env(conn)
                logger.info(f"🔐 Vault auto-unlocked; {n} integration secret(s) live.")
            # safe_load_dotenv() may already have made GitHub available even when a
            # DPAPI-wrapped vault key cannot be unwrapped by this process.
            from core import awakening
            proof = awakening.refresh_connector_evidence_on_startup(conn)
            logger.info(f"🔐 Awakening GitHub proof at startup: {proof.get('github')}.")
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
            creationflags=no_window(),
        )
        try:
            listing = subprocess.run(
                ["gh", "codespace", "ports", "-c", codespace],
                capture_output=True, text=True, timeout=15,
                creationflags=no_window(),
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





# ─────────────────────────────────────────
# Scheduled Jobs
# ─────────────────────────────────────────





























# ── Explore → News (#9): per-pillar tuned cadence [E24] ───────────────────────








# ─────────────────────────────────────────
# Scheduler bridge
# ─────────────────────────────────────────





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

    # A one-shot "Reply: OK" used to print a green LLM line here. On 2026-08-01 it printed it
    # all day while every Chat request failed, because the defect only existed on the second
    # message of a conversation. The same check the Health page runs is used instead: a real
    # short conversation that uses a tool. See core/chat_self_check.py.
    print("1. Chat...")
    try:
        from core.chat_self_check import run_self_check
        check = run_self_check()
        icon = "✅" if check["ok"] else "❌"
        label = {"working": "Chat works", "broken": "Chat is BROKEN",
                 "model_unavailable": "Model unreachable"}.get(check["state"], check["state"])
        tools = ", ".join(check["tools_used"]) or "no tool ran"
        print(f"   {icon} {label} ({tools}, {check['model_turns']} turns, {check['latency_ms']}ms)")
        if not check["ok"]:
            print(f"      {check['detail']}")
            all_ok = False
    except Exception as e:
        print(f"   ❌ Chat: {e}")
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

    telegram_app = None
    telegram_retry_at = 0.0
    telegram_retry_seconds = 300
    try:
        telegram_app = await start_telegram_polling()
        logger.info("🤖 Tobi running + polling Telegram. Ctrl+C to stop.\n")
    except Exception as exc:
        telegram_retry_at = asyncio.get_running_loop().time() + telegram_retry_seconds
        logger.warning(
            "Telegram polling unavailable; API and Mission Control remain online. "
            "Retrying in %s minutes: %s",
            telegram_retry_seconds // 60,
            exc,
        )

    import time as _time, math as _math
    _boot = _time.time()
    _pulse = 0
    try:
        while True:
            schedule.run_pending()
            if telegram_app is None and asyncio.get_running_loop().time() >= telegram_retry_at:
                try:
                    telegram_app = await start_telegram_polling()
                    logger.info("✅ Telegram polling recovered.")
                except Exception as exc:
                    telegram_retry_at = (
                        asyncio.get_running_loop().time() + telegram_retry_seconds
                    )
                    logger.warning(
                        "Telegram polling retry failed; Mission Control remains online. "
                        "Retrying in %s minutes: %s",
                        telegram_retry_seconds // 60,
                        exc,
                    )
            _pulse += 1
            if _pulse % 5 == 0:  # every ~5 min
                _mins = int((_time.time() - _boot) / 60)
                _h = _mins // 60
                _m = _mins % 60
                _uptime = f"{_h}h{_m:02d}m" if _h else f"{_m}m"
                # ── Smoke: a connected vertical smoke trail ──
                # Each heartbeat prints a vertical bar (╎) at a smoothly
                # drifting horizontal position. Consecutive lines overlap
                # so the bars connect top-to-bottom, forming one continuous
                # smoke column that sways left ↔ right.
                _step = _pulse // 5
                _offset = int(6 + 3 * _math.sin(_step * 0.45))
                _trail = ' ' * _offset + '\u254e\u254e'  # ╎╎ (vertical smoke)
                logger.info(f"\U0001f6ac still smoking, everything okay! \u00b7 uptime {_uptime}  {_trail}")
            await asyncio.sleep(60)
    finally:
        await shutdown_telegram_app()


async def _main_async(command: str):
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


async def main_async():
    from core.runtime.surface_adapter import track_async_surface
    command = sys.argv[1] if len(sys.argv) > 1 else "start"
    await track_async_surface(
        surface="cli",
        operation=f"command.{command}",
        session_id="cli",
        actor="cli-adapter",
        callback=lambda: _main_async(command),
    )


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "start"

    if command == "bot":
        # run_polling manages its own event loop — must be outside asyncio.run()
        from core.runtime.surface_adapter import track_sync_surface
        def run_bot():
            init_database()
            sync_soul_and_skills()
            app = build_app()
            print("🤖 Starting Tobi Telegram bot...")
            app.run_polling(drop_pending_updates=True)
        track_sync_surface(
            surface="cli", operation="command.bot", session_id="cli",
            actor="cli-adapter", callback=run_bot,
        )
    else:
        asyncio.run(main_async())

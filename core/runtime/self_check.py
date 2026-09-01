"""One-click proof that Mission Control Infrastructure V2 (#21) actually works here.

The owner had a running server that reported `healthy` while every model call failed, and a
second server quietly serving an empty database. Both looked fine because nothing checked the
things that were broken. This module is the answer to that: press one button and get two kinds
of evidence back, because neither kind is enough on its own.

**Behaviour** — the registered #21 and #34 acceptance suites, each run in its own throwaway
database as a separate process. They are the project's gate, so the health page and the gate
can never disagree about whether the runtime works; nothing is re-implemented here, only named
in plain words and executed.

**Wiring** — read-only checks that only mean something on a *running* server: which database
file this process actually opened, whether the canonical tables and migrations are all present,
whether the process can reach the internet at all, what the rollout switches are set to. An
offline suite can never fail on these, and every incident so far has been one of them.

Nothing here writes to the owner's data. The suites set their own temporary `DB_PATH` before
importing anything, and this module hands them one as well; the wiring checks only read.
"""
from __future__ import annotations

import os
import re
import socket
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional
from core.proc import no_window

ROOT = Path(__file__).resolve().parents[2]

# Output from a child process is redacted before it can reach the page. A failing check quotes
# the suite's own lines, and a suite is free to print whatever it was handed.
_REDACT = (
    (re.compile(r"bot\d+:[A-Za-z0-9_\-]+"), "bot***"),
    (re.compile(r"sk-[A-Za-z0-9_\-]{8,}"), "sk-***"),
    (re.compile(r"(?i)\b(bearer)\s+\S+"), r"\1 ***"),
    (re.compile(r"(?i)(token|key|secret|password|authorization)[=:]\s*\S+"), r"\1=***"),
)

# A suite that has not printed anything for this long is not going to. The slowest real suite
# (terminal jobs, which starts detached workers and waits on them) finishes in ~15s.
SUITE_TIMEOUT_S = 180


@dataclass(frozen=True)
class SuiteSpec:
    """One acceptance suite, named the way the owner thinks about it rather than by filename."""

    id: str
    label: str      # what it proves, in plain words
    package: str    # the #21 package it belongs to, for grouping
    path: str       # relative to the repository root
    proves: str     # one sentence: what a green row actually means


# Ordered the way the system is built up, which is also the order the board lists the packages
# in — history first, then durable runs, then everything standing on them.
SUITES: tuple[SuiteSpec, ...] = (
    SuiteSpec("contracts", "The shared shapes hold", "T01",
              "tests/test_mc_runtime_contracts.py",
              "Runs, tools, loops, errors and evaluations all have one agreed shape, and a "
              "wrong one is refused instead of stored."),
    SuiteSpec("event_store", "Everything is written down, in order", "T02",
              "tests/test_mc_runtime_event_store.py",
              "History is append-only and strictly ordered, secrets are masked before they are "
              "stored, and current state can be rebuilt from the events alone."),
    SuiteSpec("repository", "Runs survive a crash", "T03",
              "tests/test_mc_runtime_repository.py",
              "A run is saved with versioned state, exclusive leases, restart checkpoints and "
              "immutable receipts, so a crash resumes instead of restarting."),
    SuiteSpec("gateway_live_chat", "Chat and Agent reach the new engine", "T04",
              "tests/test_mc_runtime_gateway_live_chat.py",
              "A real Chat turn is accepted, mirrored and compared by the runtime gateway "
              "without changing what the owner sees."),
    SuiteSpec("policy", "One place decides what is allowed", "T05",
              "tests/test_mc_runtime_policy.py",
              "Permissions, approvals, credentials and budgets are decided in one place and "
              "fail closed when anything is missing."),
    SuiteSpec("tool_catalog", "One list of tools, arguments checked", "T06",
              "tests/test_mc_runtime_tool_catalog.py",
              "Every tool is described once and its arguments are validated before it runs."),
    SuiteSpec("project_tools", "Project actions leave a receipt", "T07",
              "tests/test_mc_runtime_project_tools.py",
              "A project change records a receipt, and repeating the request cannot apply it "
              "twice."),
    SuiteSpec("file_tools", "File actions stay inside their fence", "T07",
              "tests/test_mc_runtime_file_tools.py",
              "File reads and writes are bounded to allowed paths and receipted, so a retry "
              "cannot double-apply and a path cannot escape."),
    SuiteSpec("terminal_jobs", "Terminal work is leased and cancellable", "T07",
              "tests/test_mc_runtime_terminal_jobs.py",
              "A long command is owned by exactly one worker, survives an app restart, and "
              "stops when it is cancelled."),
    SuiteSpec("conductor_facade", "The Conductor is a thin wrapper", "T08",
              "tests/test_mc_runtime_conductor_facade.py",
              "The old Conductor entry point still accepts every argument it used to, while "
              "the work happens in the new services behind it."),
    SuiteSpec("owner_intelligence", "Memory changes answers, safely", "T09",
              "tests/test_mc_runtime_owner_intelligence.py",
              "Relevant memory reaches an answer, and stale or private memory does not."),
    SuiteSpec("coding_adapter", "The coding agent is a worker, not a boss", "T10",
              "tests/test_mc_runtime_coding_adapter.py",
              "Coding sessions record bounded history and cannot change the authoritative "
              "record themselves."),
    SuiteSpec("evals", "Every request has a trace, releases are gated", "T11",
              "tests/test_mc_runtime_evals.py",
              "One trace joins context, model, tools, approvals, cost and outcome, and a "
              "release is blocked when the quality evidence is missing."),
    SuiteSpec("system_model", "The system can describe itself", "T11A",
              "tests/test_mc_runtime_system_model.py",
              "Subsystems, capabilities, risks and limits are typed records with sources, and "
              "an unsupported claim is refused."),
    SuiteSpec("security", "Attacks are blocked on purpose", "T12",
              "tests/test_mc_runtime_security.py",
              "Injection, secret leakage, over-reach, budget exhaustion and path escape are "
              "each attempted and each blocked."),
    SuiteSpec("runs_view", "The Runs page shows bounded history", "T13",
              "tests/test_mc_runtime_runs_view.py",
              "The Runs list and detail expose labels, states and references only — never a "
              "prompt, a body, a secret or raw tool output."),
    SuiteSpec("runs_ui", "The Runs page explains itself", "T13",
              "tests/test_mc_runtime_runs_ui.py",
              "The page says why it is empty and reconnects where it left off, instead of "
              "showing a blank list."),
    SuiteSpec("rollout", "Turning it on is staged and reversible", "T14",
              "tests/test_mc_runtime_rollout.py",
              "A stage cannot be skipped, needs seven consecutive matching comparisons, and "
              "one switch returns new work to the old behaviour."),
    SuiteSpec("surface_adapters", "Every surface enters the same history", "T15",
              "tests/test_mc_runtime_surface_adapters.py",
              "Projects, Office, CLI, Telegram and the schedulers record bounded runs, and a "
              "recording failure never interrupts the real work."),
    SuiteSpec("model_unreachable", "A model we cannot reach is reported honestly", "fix",
              "tests/test_model_unreachable_message.py",
              "A provider that was never contacted is reported as unreachable rather than as "
              "a model that answered badly."),
    SuiteSpec("schema_ledger", "The schema records what it has applied", "T02",
              "tests/test_runtime_schema_ledger.py",
              "The migration ledger actually records each applied version, so the runtime "
              "schema is not silently re-applied on every database call."),
    SuiteSpec("self_check", "This test itself still covers everything", "UI",
              "tests/test_infrastructure_self_check.py",
              "The button runs exactly the suites the release gate runs, every wiring check "
              "answers, and nothing raw from a suite can reach this page."),
    SuiteSpec("no_windows", "Background work never steals the screen", "UI",
              "tests/test_no_console_windows.py",
              "No process the server starts can pop a console window onto the desktop, "
              "whatever started the server."),
    SuiteSpec("ui_loading", "Every button shows it is working", "UI",
              "tests/test_ui_loading_states.py",
              "No control in the app can be pressed twice or appear frozen while it works."),
    SuiteSpec("agent_tier_baseline", "Agent Tier starts from frozen evidence", "#35 T00",
              "tests/test_agent_tier_baseline.py",
              "Seven abilities, five workflow families, thirty cases, five sealed holdouts, and "
              "the unchanged-code result are hash-locked before Agent behavior changes."),
    SuiteSpec("agent_tier_registry", "Agent progress comes from current proof", "#35 T01",
              "tests/test_agent_tier_registry.py",
              "Tier II uses seven evidence-backed abilities, rejects raw or stale proof, and "
              "shows the owner what is missing and what to do next."),
    SuiteSpec("agent_tier_workflows", "Agent completes bounded local work", "#35 T02",
              "tests/test_agent_tier_workflows.py",
              "Qualified Project, local diagnosis, and coding maintenance requests use canonical "
              "Runtime, preserve retries, require grounded evidence, and retain a scoped rollback."),
    SuiteSpec("tobival_workflows", "Supported work follows one workflow", "#34 T02",
              "tests/test_tobival_workflows.py",
              "Known Mission Control requests select one frozen workflow and cannot escape its "
              "tool boundary, while unsupported work remains explicit."),
    SuiteSpec("tobival_api", "Evaluation proof stays bounded and private", "#34 T06",
              "tests/test_tobival_api.py",
              "The owner view reports canonical metrics and blockers without exposing prompts, "
              "responses, fixtures, secrets, or raw tool output."),
    SuiteSpec("tobival_final", "TOBIval clears its frozen final exam", "#34 T07",
              "tests/test_tobival_acceptance.py",
              "All 72 frozen cases and 14 holdouts meet the quality and model-independence targets, "
              "with real provider evidence and bounded recovery."),
    SuiteSpec("tobival_dependency", "Model dependence comes from recorded proof", "#34 T08",
              "tests/test_tobival_model_dependency.py",
              "Canonical decision ownership is recomputed from Runtime events, raw model quality "
              "stays visible, and a provider outage cannot be reported as quality proof."),
    SuiteSpec("chat_runtime", "Normal Chat uses the supported workflow boundary", "#34 T08",
              "tests/test_chat_runtime.py",
              "The production Chat router selects supported deterministic reads without changing "
              "the established mode, recovery, or compatibility behavior."),
)

_PASS_LINE = re.compile(r"^PASS\s", re.MULTILINE)
_FAIL_LINE = re.compile(r"^FAIL\b.*$", re.MULTILINE)


def redact(text: str) -> str:
    for pattern, replacement in _REDACT:
        text = pattern.sub(replacement, text)
    return text


def suite_ids() -> list[str]:
    return [spec.id for spec in SUITES]


def _summarise(output: str, returncode: int) -> tuple[int, int, str]:
    """Turn a suite's console output into (passed, failed, one owner-readable line).

    Every suite prints `PASS <name>` / `FAIL <name>` per check and a summary line at the end,
    but the summary lines are all worded differently. Counting the per-check lines is the one
    thing that works for all of them, and it is also what the owner wants to see: how many
    individual proofs ran, not how the suite chose to phrase its ending.
    """
    passed = len(_PASS_LINE.findall(output))
    failures = [line.strip() for line in _FAIL_LINE.findall(output)]
    if returncode == 0 and not failures:
        return passed, 0, f"{passed} checks passed" if passed else "passed"
    if failures:
        head = redact(failures[0])[:220]
        more = f" (+{len(failures) - 1} more)" if len(failures) > 1 else ""
        return passed, len(failures), f"{head}{more}"
    # A non-zero exit with no FAIL line: a crash, an import error, a timeout. The last
    # non-empty line of output is the closest thing to a cause the suite gave us.
    tail = [line.strip() for line in output.splitlines() if line.strip()]
    return passed, 1, redact(tail[-1])[:220] if tail else f"exited with code {returncode}"


def _run_once(spec: SuiteSpec, workdir: Path, python: str) -> tuple[bool, int, int, str]:
    env = os.environ.copy()
    # Belt and braces. Every suite already points DB_PATH at its own temporary directory before
    # importing anything, but a suite that forgets must still never see the owner's database.
    env["DB_PATH"] = str(workdir / "agent.db")
    env["TOBI_SELF_CHECK"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        completed = subprocess.run(
            [python, spec.path],
            cwd=str(ROOT), env=env, capture_output=True, text=True,
            # cp1258 consoles decode child output with the console codepage: one emoji in a
            # suite's banner kills the reader thread and returns stdout as None. Pin UTF-8 and
            # treat both streams as possibly-None. This exact trap has cost a full run before.
            encoding="utf-8", errors="replace", timeout=SUITE_TIMEOUT_S,
            creationflags=no_window(),
        )
    except FileNotFoundError:
        return False, 0, 1, f"could not start {python}"
    except subprocess.TimeoutExpired:
        return False, 0, 1, f"still running after {SUITE_TIMEOUT_S}s — stopped"
    output = (completed.stdout or "") + (completed.stderr or "")
    passed, failed, detail = _summarise(output, completed.returncode)
    return completed.returncode == 0 and failed == 0, passed, failed, detail


def run_suite(spec: SuiteSpec, *, python: Optional[str] = None) -> dict[str, Any]:
    """Run one suite in a throwaway database and report it the way the owner reads it.

    A failure is run a second time before it is believed. Three of these suites start real
    worker processes and wait on real timeouts, so under load they can lose a race that has
    nothing to do with the code — and a health light that goes red for reasons the owner cannot
    act on is worse than no light at all. A real failure fails twice; a flake is reported as
    passing, and says that it needed the retry.
    """
    python = python or sys.executable
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix=f"tobi_selfcheck_{spec.id}_") as tmp:
        ok, passed, failed, detail = _run_once(spec, Path(tmp), python)
        retried = False
        if not ok:
            retried = True
            ok, passed, failed, detail = _run_once(spec, Path(tmp), python)
            if ok:
                detail = f"{detail} · passed on a second run, so the first was a timing flake"
    return {
        "id": spec.id, "label": spec.label, "package": spec.package, "proves": spec.proves,
        "ok": ok, "checks": passed, "failed": failed, "detail": detail, "retried": retried,
        "duration_ms": int((time.perf_counter() - started) * 1000),
    }


# ── Wiring: only a running server can answer these ───────────────────────────────

def _check(id: str, label: str, fn: Callable[[], tuple[bool, str]], hint: str = "") -> dict:
    started = time.perf_counter()
    try:
        ok, detail = fn()
    except Exception as exc:  # noqa: BLE001 - a diagnostic never fails by raising
        ok, detail = False, redact(f"{type(exc).__name__}: {exc}")[:220]
    return {"id": id, "label": label, "ok": bool(ok), "detail": str(detail)[:300],
            "hint": hint if not ok else "", "duration_ms": int((time.perf_counter() - started) * 1000)}


def _database() -> tuple[bool, str]:
    from core import database
    path = Path(database.DB_PATH)
    if not path.is_file():
        return False, f"{path} does not exist"
    size_mb = path.stat().st_size / (1024 * 1024)
    conn = database.get_connection()

    def count(table: str) -> int:
        try:
            return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        except Exception:  # noqa: BLE001 - a table this build does not have is not a failure
            return 0

    try:
        projects, sessions, runs = count("pm_projects"), count("chat_sessions"), count("mc_runs")
    finally:
        conn.close()
    # A brand-new database sitting at the expected path is the failure that wasted a whole test
    # session: the server reported `healthy` while serving a file it had just created itself,
    # because a relative DB_PATH resolved somewhere nobody looked.
    if size_mb < 1 and projects == 0 and sessions == 0:
        return False, (f"{path} looks brand new ({size_mb:.1f} MB, no projects, no chats) — "
                       "this is probably not the database you meant to open")
    return True, (f"{path.name} · {size_mb:.0f} MB · {projects} projects · {sessions} chats · "
                  f"{runs} canonical runs · in {path.parent}")


def _schema() -> tuple[bool, str]:
    from core import database
    from core.schema.runtime import RUNTIME_SCHEMA_VERSIONS, _RUNTIME_TABLES
    conn = database.get_connection()
    try:
        present = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        applied = {row[0] for row in conn.execute(
            "SELECT version FROM schema_migrations").fetchall()}
    finally:
        conn.close()
    missing_tables = sorted(_RUNTIME_TABLES - present)
    missing_versions = sorted(set(RUNTIME_SCHEMA_VERSIONS) - applied)
    if missing_tables or missing_versions:
        return False, (f"missing {len(missing_tables)} table(s) {missing_tables[:3]} and "
                       f"{len(missing_versions)} migration(s)")
    return True, (f"all {len(_RUNTIME_TABLES)} canonical tables and "
                  f"{len(RUNTIME_SCHEMA_VERSIONS)} migrations present")


def _redaction_armed() -> tuple[bool, str]:
    from core.runtime.event_store import redact_payload
    probe = {"api_key": "sk-live-should-never-be-stored", "note": "authorization=Bearer abc123"}
    stored = str(redact_payload(probe))
    leaked = [needle for needle in ("sk-live-should", "abc123") if needle in stored]
    if leaked:
        return False, "a secret survived redaction before storage"
    return True, "keys and tokens are masked before anything is written down"


def _runs_view() -> tuple[bool, str]:
    from core.runtime.runs_view import RuntimeRunsView, RunsViewValidationError
    view = RuntimeRunsView()
    page = view.list_runs(limit=1)
    items = page.get("items") or []
    banned = {"prompt", "message", "body", "output", "response"}
    leak = sorted(banned & set(items[0])) if items else []
    if leak:
        return False, f"the Runs list exposes {leak}"
    try:
        view.list_runs(limit=1, surface="not-a-surface")
        return False, "an unknown surface filter was accepted instead of refused"
    except RunsViewValidationError:
        pass
    return True, (f"answers with bounded summaries ({len(items)} shown) and refuses an "
                  "unknown filter")


def _engine_mode() -> tuple[bool, str]:
    from core import chat_runtime
    from core.runtime import config as runtime_config
    mode = chat_runtime.runtime_mode()
    if mode not in ("off", "shadow", "on"):
        return False, f"unrecognised runtime mode {mode!r}"
    flags = runtime_config.rollout_state()
    on = sum(1 for value in flags.values() if value)
    return True, (f"engine is {mode} · gateway {runtime_config.gateway_mode()} · "
                  f"{on} of {len(flags)} rollout flags on")


def _rollout() -> tuple[bool, str]:
    from core.runtime.rollout import RolloutController
    status = RolloutController().status()
    decisions = status.get("decisions") or {}
    allowed = [name for name, value in decisions.items() if value.get("allowed")]
    direct = decisions.get("direct_chat") or {}
    blockers = ", ".join(direct.get("blockers") or []) or "none"
    # Nothing being activated is the intended state, not a fault. The check is that the
    # controller can still answer and still names what is holding each stage.
    return True, (f"stage {status.get('stage')} · rollback "
                  f"{'on' if status.get('rollback') else 'off'} · "
                  f"{len(allowed)} of {len(decisions)} stages allowed · "
                  f"direct chat blocked by: {blockers}")


def _surfaces() -> tuple[bool, str]:
    from core.runtime.surface_adapter import COMPATIBILITY_SURFACES
    expected = {"projects", "office", "cli", "telegram", "scheduler"}
    missing = sorted(expected - set(COMPATIBILITY_SURFACES))
    if missing:
        return False, f"no adapter for {missing}"
    return True, f"adapters wired for {', '.join(COMPATIBILITY_SURFACES)}"


def _routes() -> tuple[bool, str]:
    from api.dashboard import app
    paths = {getattr(route, "path", "") for route in app.routes}
    required = {"/api/runtime/runs", "/api/runtime/rollout", "/api/runtime/loops"}
    missing = sorted(required - paths)
    if missing:
        return False, f"this server does not serve {missing}"
    return True, f"{len(paths)} routes mounted, including every runtime route"


def _dashboard_build() -> tuple[bool, str]:
    dist = ROOT / "dashboard" / "dist"
    src = ROOT / "dashboard" / "src"
    index = dist / "index.html"
    if not index.is_file():
        return False, "dashboard/dist is missing — the page you are reading is stale"
    newest_src = max((p.stat().st_mtime for p in src.rglob("*") if p.is_file()), default=0)
    built = max((p.stat().st_mtime for p in dist.rglob("*") if p.is_file()), default=0)
    if newest_src > built:
        age = int((newest_src - built) / 60)
        return False, f"the build is {age} min older than the source — rebuild the dashboard"
    return True, f"built {time.strftime('%d %b %H:%M', time.localtime(built))}, newer than the source"


def _internet() -> tuple[bool, str]:
    """Can *this process* open a connection out? Not whether the machine can.

    A Mission Control started inside an agent's sandbox inherits its network rules. It answers
    every local request perfectly while every model call fails, which is exactly what happened
    on 2026-08-20 and read as "the current model is struggling" for two test sessions.
    """
    for host, port in (("api.openai.com", 443), ("api.telegram.org", 443)):
        try:
            socket.create_connection((host, port), timeout=4).close()
            return True, f"this server process reached {host} — outbound network works"
        except OSError as exc:
            last = f"{host}: {type(exc).__name__}"
    return False, (f"this server process cannot open a connection out ({last}). "
                   "Model calls and every integration will fail.")


def _vault() -> tuple[bool, str]:
    from core import database, vault
    conn = database.get_connection()
    try:
        status = vault.status(conn)
    finally:
        conn.close()
    if not status.get("setup"):
        return True, "no vault set up — connectors use .env only"
    if status.get("unlocked"):
        return True, f"unlocked · {status.get('secret_count', 0)} keys loaded"
    return False, (f"locked · {status.get('secret_count', 0)} saved keys are not loaded, so "
                   "those connectors will read as unavailable")


def _fallback_model() -> tuple[bool, str]:
    """A recovery path that ships empty does not exist. CLAUDE.md's rule, checked."""
    from core import model_router
    config = model_router.load_llm_config()
    default = (config.get("default_model") or "").strip()
    if not default:
        return False, "no default model is selected"
    client, name = model_router.get_escalation_llm(default)
    if client is None:
        return False, f"{default} has no working fallback — a model failure has nowhere to go"
    return True, f"{default}, falling back to {name}"


WIRING: tuple[tuple[str, str, Callable[[], tuple[bool, str]], str], ...] = (
    ("database", "Serving the right database", _database,
     "Stop the server and restart it from the project folder so it loads .env."),
    ("schema", "Canonical history tables are present", _schema,
     "Restart Mission Control — the runtime schema is applied on startup."),
    ("internet", "This server can reach the internet", _internet,
     "Start Mission Control from your own PowerShell window, not inside an agent's terminal."),
    ("redaction", "Secrets are masked before storage", _redaction_armed,
     "Stop using this build and report it — nothing should be written unredacted."),
    ("runs_view", "The Runs page can read history", _runs_view, ""),
    ("engine", "The runtime engine is wired in", _engine_mode, ""),
    ("rollout", "Rollout controls answer", _rollout, ""),
    ("surfaces", "Every surface has an adapter", _surfaces, ""),
    ("routes", "This server serves the runtime API", _routes,
     "Restart Mission Control; the runtime router did not mount."),
    ("dashboard", "The page you are reading is current", _dashboard_build,
     "Rebuild the dashboard, then hard-refresh the browser."),
    ("vault", "Saved keys are loaded", _vault,
     "Open Integrations, unlock the vault once, and switch auto-connect back on."),
    ("fallback", "A failing model has somewhere to go", _fallback_model,
     "Choose a fallback model on the Models page."),
)


def wiring_checks() -> list[dict[str, Any]]:
    """Every read-only check, in display order. Safe to call on the live database."""
    return [_check(id, label, fn, hint) for id, label, fn, hint in WIRING]


def summarise(wiring: list[dict], suites: list[dict]) -> dict[str, Any]:
    rows = list(wiring) + list(suites)
    return {
        "ok": sum(1 for row in rows if row.get("ok")),
        "total": len(rows),
        "checks": sum(int(row.get("checks") or 0) for row in suites),
        "failed_ids": [row["id"] for row in rows if not row.get("ok")],
        "flaky_ids": [row["id"] for row in suites if row.get("retried") and row.get("ok")],
    }

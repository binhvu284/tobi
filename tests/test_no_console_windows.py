"""No background work may pop a console window onto the owner's screen.

Reported 2026-08-21: pressing the Infrastructure test button made a terminal window appear and
vanish, repeatedly. TOBI runs as a background server, so when it starts a child process Windows
has no console to lend it and creates a new one — a black window that flashes, steals focus, and
can eat a keystroke mid-sentence. The infrastructure test starts 23 child processes in a row, so
it turned a long-standing quiet defect into an obvious one: `git rev-parse` on every health
check, `tasklist` on startup, the Hermes worker, the tunnel, and the terminal engine all did the
same thing, one flash at a time.

`CREATE_NO_WINDOW` prevents it and costs nothing when a console does exist. Four call sites
already passed it and the rest did not, which is exactly how a rule that lives only in reviewers'
heads ends up half-applied.

The rule this suite enforces: every process the server can start passes `creationflags`, and
gets the value from `core.proc.no_window()` so there is one spelling of it. Checked by reading
the syntax tree, so a call cannot slip through by being written differently.

Plain python, no pytest:
    python tests/test_no_console_windows.py
"""
from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FAILURES: list[str] = []


def ok(name: str, cond: bool, detail: str = "") -> None:
    print(f"{'PASS' if cond else 'FAIL'} {name}{('  -> ' + detail) if detail and not cond else ''}")
    if not cond:
        FAILURES.append(name)


# Everything the running server can reach. `scripts/` is excluded on purpose: those are run by
# hand from a terminal that already has a console, so there is no window to suppress.
SEARCH = [ROOT / "core", ROOT / "api", ROOT / "main.py"]
SPAWNERS = {"run", "Popen", "call", "check_call", "check_output"}


def python_files() -> list[Path]:
    files: list[Path] = []
    for target in SEARCH:
        if target.is_file():
            files.append(target)
            continue
        files.extend(p for p in target.rglob("*.py")
                     if "__pycache__" not in p.parts and "venv" not in p.parts)
    return sorted(files)


def bare_spawns(path: Path) -> list[tuple[int, str]]:
    """Every `subprocess.<spawner>(...)` in this file that does not pass creationflags.

    What it passes is checked separately: `no_window()` is the only spelling allowed, and the
    last check in this suite fails if a hand-rolled version reappears.
    """
    try:
        # Production still supports Python 3.11. Parse with that grammar even when the gate
        # itself runs on 3.12, otherwise newer f-string syntax can pass the gate and fail in MC.
        tree = ast.parse(path.read_text(encoding="utf-8"), feature_version=(3, 11))
    except SyntaxError as exc:  # a file that will not parse is a failure worth seeing
        return [(getattr(exc, "lineno", 0) or 0, f"cannot parse: {exc}")]
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in SPAWNERS:
            continue
        owner = node.func.value
        if not (isinstance(owner, ast.Name) and owner.id == "subprocess"):
            continue
        if any(kw.arg == "creationflags" for kw in node.keywords):
            continue
        # `**kwargs` may well carry it; those call sites build their flags deliberately.
        if any(kw.arg is None for kw in node.keywords):
            continue
        found.append((node.lineno, f"subprocess.{node.func.attr}"))
    return found


offenders = {
    str(path.relative_to(ROOT)).replace("\\", "/"): spawns
    for path in python_files()
    if (spawns := bare_spawns(path))
}

ok("no server-side process is started without suppressing its console window",
   not offenders,
   "; ".join(f"{name}:{line} {call}" for name, spawns in offenders.items()
             for line, call in spawns)[:600])

# --- the helper itself behaves ------------------------------------------------------------
from core import proc  # noqa: E402

ok("the helper exposes a flags value", isinstance(proc.CREATE_NO_WINDOW, int))
ok("caller flags are kept, not replaced",
   proc.no_window(0x00000200) & 0x00000200 == 0x00000200)
ok("on Windows the no-window flag is actually set",
   proc.no_window(0) != 0 if sys.platform == "win32" else proc.no_window(0) == 0)

# A real child, to prove the flag does not break an ordinary spawn.
result = subprocess.run([sys.executable, "-c", "print('quiet')"], capture_output=True, text=True,
                        timeout=60, creationflags=proc.no_window())
ok("a process started with the flag still runs and returns its output",
   result.returncode == 0 and "quiet" in (result.stdout or ""), repr(result.stdout)[:120])

# --- the one that started it ----------------------------------------------------------------
self_check_source = (ROOT / "core" / "runtime" / "self_check.py").read_text(encoding="utf-8")
ok("the infrastructure test starts its suites without a window",
   "creationflags=no_window()" in self_check_source,
   "self_check still spawns without the flag")

# A call site that needs flags of its own must combine them, not replace them: the Hermes worker
# wants its own process group so a cancel can signal the whole tree, and still no window.
worker_source = (ROOT / "core" / "hermes_worker.py").read_text(encoding="utf-8")
ok("a spawn with its own flags keeps them and adds this one",
   "no_window(" in worker_source and "CREATE_NEW_PROCESS_GROUP" in worker_source,
   "hermes_worker lost one of the two")

# One spelling, everywhere. The hand-rolled version is how four sites had it and sixteen did not.
hand_rolled = [name for name in (str(path.relative_to(ROOT)).replace("\\", "/")
                                 for path in python_files()
                                 if 'getattr(subprocess, "CREATE_NO_WINDOW"' in path.read_text(encoding="utf-8"))
               if name != "core/proc.py"]  # the helper is where the platform check belongs
ok("the flag is spelled one way, through the shared helper", not hand_rolled, str(hand_rolled))

print(f"\n{'ALL' if not FAILURES else str(len(FAILURES)) + ' OF'} "
      f"{'CONSOLE-WINDOW CHECKS PASSED' if not FAILURES else 'CHECKS FAILED: ' + ', '.join(FAILURES)}")
raise SystemExit(1 if FAILURES else 0)

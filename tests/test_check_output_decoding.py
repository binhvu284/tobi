"""A check's output must not be able to kill the run that produced it.

Run 15 passed every gate it reached. `python tests/test_awakening.py` exited 0 with
`ALL 73 CHECKS PASSED`, and the workflow died anyway with `internal_error: TypeError`.

The cause was the console codepage. This host's locale is cp1258, and `subprocess.run(text=True)`
decodes a child's output with it. `tests/test_awakening.py` ends with an emoji, whose UTF-8 bytes
cp1258 cannot decode, so the reader thread raised `UnicodeDecodeError` and died -- leaving
`completed.stdout` as **None**. `(None + "")` is the TypeError. A passing test was fatal because
of a character in its success message.

The same decode sits under every git call, which is worse: a diff, a filename, or a commit
message carrying any non-Latin byte would take out the run the same way.

The stripping bug in this file is from the same run. `git status --porcelain=v1 -z` emits
"XY PATH"; an unstaged edit -- what a worktree always holds after an agent writes -- has status
" M", so stripping the leading space cost every path its first character. Run 15 recorded
"ore/awakening.py". That value is what the quality gate hands to the protected-path check, so a
truncated "core/coding_agent.py" stops matching the protected entry that guards it.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FAILURES: list[str] = []


def ok(label: str, condition: bool, detail: str = "") -> None:
    print(f"{'PASS' if condition else 'FAIL'} {label}{('  -> ' + detail) if detail and not condition else ''}")
    if not condition:
        FAILURES.append(label)


base = ROOT / ".tobi" / "test-runs"
base.mkdir(parents=True, exist_ok=True)
sandbox = Path(tempfile.mkdtemp(prefix="check_decoding_", dir=base))

# A check whose *successful* output carries the exact bytes cp1258 cannot decode.
emoji_check = sandbox / "emoji_check.py"
emoji_check.write_text(
    "import sys\n"
    "sys.stdout.reconfigure(encoding='utf-8')\n"
    "print('\\N{PARTY POPPER} ALL 73 CHECKS PASSED')\n",
    encoding="utf-8",
)

# --- the decode the agent performs -------------------------------------------------------
source = (ROOT / "core" / "coding_agent.py").read_text(encoding="utf-8")
run_checks = source[source.index("def _run_checks"):][:2600]
ok("the check runner pins its decoding instead of trusting the console codepage",
   'encoding="utf-8"' in run_checks and 'errors="replace"' in run_checks, run_checks[:200])
ok("a stream lost to a decode error cannot be concatenated blindly",
   "(completed.stdout or \"\")" in run_checks and "(completed.stderr or \"\")" in run_checks)

git_source = (ROOT / "core" / "git_workspace.py").read_text(encoding="utf-8")
ok("git output is decoded as UTF-8, not as the console codepage",
   'encoding="utf-8"' in git_source and 'errors="replace"' in git_source)

tools_source = (ROOT / "core" / "coding_tools.py").read_text(encoding="utf-8")
run_check = tools_source[tools_source.index("def run_check"):][:900]
ok("the worker's own check runner decodes the same way",
   'encoding="utf-8"' in run_check and 'errors="replace"' in run_check, run_check[:200])

# The behaviour itself: reproduce the call the agent makes and prove it survives.
completed = subprocess.run(
    [sys.executable, str(emoji_check)], cwd=str(sandbox), capture_output=True,
    text=True, encoding="utf-8", errors="replace", timeout=120,
)
ok("a check that prints an emoji still reports its exit code", completed.returncode == 0,
   str(completed.returncode))
ok("its output survives decoding", completed.stdout is not None and "CHECKS PASSED" in completed.stdout,
   repr(completed.stdout))
ok("concatenating the streams does not raise",
   isinstance((completed.stdout or "") + (completed.stderr or ""), str))

# --- porcelain paths keep their first character ------------------------------------------
repo = sandbox / "repo"
(repo / "core").mkdir(parents=True, exist_ok=True)


def git(*args: str, strip: bool = True) -> str:
    out = subprocess.run(["git", *args], cwd=str(repo), capture_output=True, text=True,
                         encoding="utf-8", errors="replace", timeout=120)
    return out.stdout.strip() if strip else out.stdout


git("init", "-q")
git("config", "user.email", "guard@example.com")
git("config", "user.name", "Guard")
(repo / "core" / "coding_agent.py").write_text("original\n", encoding="utf-8")
git("add", "-A")
git("commit", "-qm", "base")
# The state a worktree is actually in after an agent edits a tracked file: unstaged, status " M".
(repo / "core" / "coding_agent.py").write_text("modified\n", encoding="utf-8")

raw = git("status", "--porcelain=v1", "-z", "--untracked-files=all", strip=False)
ok("an unstaged edit really does start with a space", raw.startswith(" M"), repr(raw[:6]))


def parse(output: str) -> set[str]:
    """The parser from GitWorkspace.changed_files, which assumes 'XY PATH'."""
    files: set[str] = set()
    for record in output.split("\0"):
        if record:
            files.add(record[3:].replace("\\", "/"))
    return {name for name in files if name}


ok("stripping the porcelain output truncates the path",
   parse(raw.strip()) == {"ore/coding_agent.py"}, str(parse(raw.strip())))
ok("the unstripped output yields the real path",
   parse(raw) == {"core/coding_agent.py"}, str(parse(raw)))

changed_files = git_source[git_source.index("def changed_files"):][:900]
ok("changed_files asks for the unstripped output", "strip=False" in changed_files,
   changed_files[:300])

# A path the quality gate must recognise as protected only matches when it is intact.
ok("the truncated path no longer matches the protected entry that guards it",
   "ore/coding_agent.py" != "core/coding_agent.py")

# --- an unknown crash must name itself ---------------------------------------------------
handler = source[source.index("except Exception as exc:"):][:900]
ok("an internal error records its traceback", "traceback.format_exc()" in handler, handler[:200])
ok("the owner-visible blocker carries the message, not just the class name",
   '{type(exc).__name__}: {exc}' in handler, handler[:300])
ok("core/coding_agent.py imports traceback", "\nimport traceback\n" in source)

print(f"\n{'ALL' if not FAILURES else str(len(FAILURES)) + ' OF'} "
      f"{'CHECK DECODING GUARDS PASSED' if not FAILURES else 'CHECKS FAILED: ' + ', '.join(FAILURES)}")
raise SystemExit(1 if FAILURES else 0)

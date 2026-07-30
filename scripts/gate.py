"""The gate: the check an agent cannot talk its way past.

An agent decides for itself when it is finished, and it will decide "finished" long before
the work is correct. Sixteen Developer runs reported 100% complete while failing. This script
is the outside opinion. Claude Code runs it on every Stop; exit code 2 refuses the stop and
hands the failure back to the agent, so "done" has to be earned rather than declared.

It reads .claude/CURRENT_WORK.md and does what the Gate line there tells it:

    Gate: no      nothing is armed -- pass, say nothing
    Gate: red     the checks MUST fail. Proves a new test actually tests something.
    Gate: green   the checks MUST pass. The ordinary finish line.

`red` is the half everyone skips. A test written after the code just agrees with the code;
running it against the unchanged codebase and watching it fail is the only proof it has teeth.

Run it by hand any time:  python scripts/gate.py
"""
from __future__ import annotations

import re
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CURRENT_WORK = ROOT / ".claude" / "CURRENT_WORK.md"
PER_COMMAND_TIMEOUT = 900

BLOCK = 2  # Claude Code: refuse the stop, feed stderr back to the agent.
PASS = 0

_MODE_RE = re.compile(r"^\s*\**Gate:?\**\s*:?\s*\**\s*(no|red|green)\b", re.IGNORECASE | re.MULTILINE)
_FENCE_RE = re.compile(r"^```gate\s*$(.*?)^```\s*$", re.DOTALL | re.MULTILINE)


def read_plan() -> tuple[str, list[str]]:
    """Return (mode, commands). Anything unparseable means 'not armed', never 'blocked'."""
    if not CURRENT_WORK.is_file():
        return "no", []
    text = CURRENT_WORK.read_text(encoding="utf-8", errors="replace")
    mode_match = _MODE_RE.search(text)
    mode = mode_match.group(1).lower() if mode_match else "no"
    fence = _FENCE_RE.search(text)
    commands = []
    if fence:
        for raw in fence.group(1).splitlines():
            line = raw.strip()
            if line and not line.startswith("#"):
                commands.append(line)
    return mode, commands


def run(command: str) -> tuple[bool, str]:
    try:
        argv = shlex.split(command)
    except ValueError as exc:
        return False, f"cannot parse command: {exc}"
    try:
        # Windows consoles here are cp1258; a single emoji in child output kills the reader
        # thread and leaves stdout as None. Pin UTF-8 and tolerate None -- this exact bug
        # cost a full Developer run to diagnose.
        completed = subprocess.run(
            argv, cwd=str(ROOT), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=PER_COMMAND_TIMEOUT,
        )
    except FileNotFoundError:
        return False, f"executable not found: {argv[0]}"
    except subprocess.TimeoutExpired:
        return False, f"timed out after {PER_COMMAND_TIMEOUT}s"
    output = ((completed.stdout or "") + (completed.stderr or "")).strip()
    return completed.returncode == 0, output[-1500:]


def main() -> int:
    mode, commands = read_plan()
    if mode == "no" or not commands:
        return PASS

    results = [(command, *run(command)) for command in commands]
    passed = [item for item in results if item[1]]
    failed = [item for item in results if not item[1]]

    def report(header: str) -> None:
        print(header, file=sys.stderr)
        for command, ok, output in results:
            print(f"  [{'PASS' if ok else 'FAIL'}] {command}", file=sys.stderr)
            if not ok and output:
                for line in output.splitlines()[-12:]:
                    print(f"         {line}", file=sys.stderr)

    if mode == "green":
        if failed:
            report(f"GATE FAILED ({len(failed)} of {len(results)} checks are red).")
            print("\nThe work is not finished. Fix the failure above and continue.\n"
                  "Do not weaken, skip, or delete a check to get past this.", file=sys.stderr)
            return BLOCK
        report(f"GATE GREEN ({len(passed)} of {len(results)} checks pass).")
        return PASS

    # mode == "red": a check that passes before the work exists proves nothing.
    if not failed:
        report("GATE RED EXPECTED A FAILURE, GOT NONE.")
        print("\nEvery check passes against code that does not implement the change yet,\n"
              "so none of them can tell whether the change works. Make the check assert the\n"
              "behaviour the item actually promises, then run this again.", file=sys.stderr)
        return BLOCK
    report(f"GATE RED CONFIRMED ({len(failed)} of {len(results)} checks fail as intended).")
    print("\nThe check has teeth. Set `Gate: green` in .claude/CURRENT_WORK.md "
          "and implement.", file=sys.stderr)
    return PASS


if __name__ == "__main__":
    raise SystemExit(main())

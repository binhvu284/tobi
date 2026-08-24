"""The one-click infrastructure test has to keep telling the truth.

The Health page now has a button that proves Mission Control Infrastructure V2 works on this
machine. A button like that fails in three quiet ways, and none of them look like a failure:

1. **It stops covering things.** A suite is renamed or added, the health page never hears about
   it, and the row simply is not there. A missing row reads exactly like a passing one.
2. **It disagrees with the gate.** Two lists of "the checks that matter" always drift, and then
   green on the page means something different from green at release.
3. **It leaks.** Suite output is a child process's stdout. Whatever a suite was handed can end
   up on a page the owner might screenshot.

So this suite checks the checker: every registered suite exists, the health button and the
release gate run exactly the same set, the wiring checks all answer without raising, and
anything quoted from a child process is redacted first.

Isolated temp DB, plain python, no pytest:
    python tests/test_infrastructure_self_check.py
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TMP = tempfile.mkdtemp(prefix="tobi_selfcheck_meta_")
os.environ["DB_PATH"] = os.path.join(TMP, "agent.db")

from core.database import init_database  # noqa: E402

init_database()

from core.runtime import self_check  # noqa: E402

FAILURES: list[str] = []


def ok(name: str, cond: bool, detail: str = "") -> None:
    print(f"{'PASS' if cond else 'FAIL'} {name}{('  -> ' + detail) if detail and not cond else ''}")
    if not cond:
        FAILURES.append(name)


# --- 1. every registered suite is real ---------------------------------------------------
missing = [spec.path for spec in self_check.SUITES if not (ROOT / spec.path).is_file()]
ok("every suite the health page promises actually exists", not missing, str(missing))
ok("no suite is registered twice",
   len({spec.id for spec in self_check.SUITES}) == len(self_check.SUITES))
ok("every suite says in plain words what a green result means",
   all(len(spec.proves) > 40 and len(spec.label) > 8 for spec in self_check.SUITES))

# --- 2. the button and the release gate run the same set ---------------------------------
# Two lists of "what matters" drift apart, and then a green page and a green gate stop meaning
# the same thing. They are compared here so they cannot.
# The gate's own parser is used rather than a second reading of the file, so "what the gate
# runs" can never be a different answer here than it is at release time.
sys.path.insert(0, str(ROOT / "scripts"))
import gate as gate_script  # noqa: E402

_mode, gate_commands = gate_script.read_plan()
gate_paths = {m.replace("\\", "/")
              for command in gate_commands
              for m in re.findall(r"(tests/[A-Za-z0-9_]+\.py)", command)}
suite_paths = {spec.path for spec in self_check.SUITES}
ok("the health button runs every suite the release gate runs",
   not (gate_paths - suite_paths), f"gate-only: {sorted(gate_paths - suite_paths)}")
ok("the health button runs nothing the release gate does not",
   not (suite_paths - gate_paths), f"button-only: {sorted(suite_paths - gate_paths)}")
ok("the whole #21 package range is covered",
   {"T01", "T02", "T03", "T04", "T05", "T06", "T07", "T08", "T09", "T10", "T11", "T11A",
    "T12", "T13", "T14", "T15"}.issubset({spec.package for spec in self_check.SUITES}),
   str(sorted({spec.package for spec in self_check.SUITES})))

# --- 3. the wiring checks answer, and never raise ----------------------------------------
rows = self_check.wiring_checks()
ok("every wiring check returns a row", len(rows) == len(self_check.WIRING))
ok("each row carries what the page needs",
   all({"id", "label", "ok", "detail"} <= set(row) for row in rows))
ok("a failing wiring check tells the owner what to do about it",
   all(row.get("hint") or row.get("ok") or row["id"] in {"runs_view", "engine", "rollout", "surfaces"}
       for row in rows),
   str([row["id"] for row in rows if not row.get("ok") and not row.get("hint")]))
ok("the wiring checks name the incidents that actually happened",
   {"database", "internet", "vault", "dashboard"} <= {row["id"] for row in rows},
   str(sorted(row["id"] for row in rows)))

# --- 4. nothing raw reaches the page -----------------------------------------------------
dirty = ("FAIL leaked: authorization=Bearer sk-live-abc123def456 "
         "token=9f8e7d6c bot777777:AAHfake_telegram_token password: hunter2")
clean = self_check.redact(dirty)
for needle in ("sk-live-abc123def456", "9f8e7d6c", "AAHfake_telegram_token", "hunter2"):
    ok(f"{needle[:14]}… never survives redaction", needle not in clean, clean)

# --- 5. the summary counts real checks, not summary lines --------------------------------
sample = "PASS one\nPASS two\nFAIL three: it broke\nPASS: 2 SUMMARY LINE\n"
passed, failed, detail = self_check._summarise(sample, 1)
ok("individual PASS lines are counted", passed == 2, str(passed))
ok("a suite's own summary line is not counted as a check", passed == 2)
ok("failures are counted and quoted", failed == 1 and "it broke" in detail, detail)
passed, failed, detail = self_check._summarise("PASS one\nPASS two\n", 0)
ok("a clean run reports its total", passed == 2 and failed == 0 and "2 checks" in detail, detail)
_, failed, detail = self_check._summarise("", 3)
ok("a suite that crashed without a FAIL line still fails", failed == 1, detail)

# --- 6. the page is actually wired to it -------------------------------------------------
health_page = (ROOT / "dashboard" / "src" / "pages" / "Health.tsx").read_text(encoding="utf-8")
component = (ROOT / "dashboard" / "src" / "components" / "InfrastructureCheck.tsx").read_text(encoding="utf-8")
client = (ROOT / "dashboard" / "src" / "api.abilities.ts").read_text(encoding="utf-8")
router = (ROOT / "api" / "routers" / "health.py").read_text(encoding="utf-8")

ok("Health has an Infrastructure tab", "'infrastructure', 'Infrastructure'" in health_page)
ok("the tab renders the check", "<InfrastructureCheck />" in health_page)
ok("the check calls the streaming endpoint", "runInfrastructureCheckStream" in component)
ok("the client points at the endpoint the server serves",
   "/api/health/infrastructure/stream" in client
   and '"/api/health/infrastructure/stream"' in router)
ok("the button cannot be pressed twice while it runs", "ActionButton" in component)
ok("a failed row shows the next thing to do", "row.hint" in component)

print(f"\n{'ALL' if not FAILURES else str(len(FAILURES)) + ' OF'} "
      f"{'INFRASTRUCTURE SELF-CHECK CHECKS PASSED' if not FAILURES else 'CHECKS FAILED: ' + ', '.join(FAILURES)}")
raise SystemExit(1 if FAILURES else 0)

"""Guard the single source of the coding-workflow vocabulary.

The vocabulary used to live in seven places -- two Python sets, two SQL string literals,
two hand-written TypeScript sets, and an inline set in the overview endpoint. Adding
`locally_complete` to some and not others produced two defects in two days: the API kept
serving a finished run as the active workflow, and the Process tab rendered it as still
running with its push gate stuck on "In progress". Neither copy was wrong in isolation.

These checks fail while any copy can drift again.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import coding_completion, coding_loop  # noqa: E402
from core.coding_states import (  # noqa: E402
    ACTIVE_STATES, CLEANUP_ELIGIBLE_STATES, FAULT_STATES, STAGES, STATE_KIND, SUCCESS_STATES,
    TERMINAL_STATES, permitted_stages, state_in_clause,
)

FAILURES: list[str] = []


def ok(label: str, condition: bool, detail: str = "") -> None:
    print(f"{'PASS' if condition else 'FAIL'} {label}{('  -> ' + detail) if detail and not condition else ''}")
    if not condition:
        FAILURES.append(label)


# --- the generated mirror is current -------------------------------------------------
result = subprocess.run(
    [sys.executable, str(ROOT / "scripts" / "generate_developer_states.py"), "--check"],
    capture_output=True, text=True, cwd=str(ROOT),
)
ok("generated developer.states.ts matches core/coding_states.py",
   result.returncode == 0, (result.stdout + result.stderr).strip())

generated = (ROOT / "dashboard" / "src" / "developer.states.ts").read_text(encoding="utf-8")
ok("generated file warns against hand editing", "do not edit by hand" in generated)

# --- every state is classified -------------------------------------------------------
ok("every state has a kind", all(STATE_KIND.values()))
ok("active and terminal never overlap", not (ACTIVE_STATES & TERMINAL_STATES))
ok("locally_complete is terminal", "locally_complete" in TERMINAL_STATES)
ok("locally_complete is a success, not a fault", "locally_complete" in SUCCESS_STATES)

# --- no module keeps a private copy --------------------------------------------------
ok("coding_completion reuses the shared ACTIVE_STATES", coding_completion.ACTIVE_STATES is ACTIVE_STATES)
ok("coding_loop reuses the shared ACTIVE_STATES", coding_loop.ACTIVE_STATES is ACTIVE_STATES)

# Queries that used to inline the session-state names as SQL text. A literal list cannot be
# updated by editing the vocabulary, which is exactly how six of them fell behind. Anchored on
# a `state` column so it does not catch `development_tasks.status`, a separate vocabulary.
for name in ("core/coding_agent.py", "core/development_store.py", "api/developer.py"):
    source = (ROOT / name).read_text(encoding="utf-8")
    inlined = re.search(r"\bstate\s+IN\s*\(\s*'", source)
    ok(f"{name} has no inlined session-state list", inlined is None,
       inlined.group(0) if inlined else "")

ok("a locally-complete run's worktree becomes reclaimable",
   "locally_complete" in CLEANUP_ELIGIBLE_STATES)
ok("a faulted run is never auto-reclaimed", not (CLEANUP_ELIGIBLE_STATES & FAULT_STATES))

overview_src = (ROOT / "api" / "developer.py").read_text(encoding="utf-8")
ok("overview derives active_workflow from TERMINAL_STATES",
   'item["state"] not in TERMINAL_STATES' in overview_src)

# --- stage vocabulary ----------------------------------------------------------------
ok("every stage declares whether it needs a capability",
   all("capability" in stage for stage in STAGES))
ok("the four remote gates require a capability",
   [s["id"] for s in STAGES if s["capability"]] ==
   ["push", "pull_request", "merge_deploy", "health"])

sandbox = permitted_stages({"github": False, "merge": False, "deploy": False})
ok("a github-disabled policy permits exactly the seven local gates",
   list(sandbox) == ["prepare", "index", "code", "validate", "review", "commit", "scan"],
   str(sandbox))
ok("enabling github reopens push and pull_request",
   set(permitted_stages({"github": True})) - set(sandbox) == {"push", "pull_request"})
ok("permitted_stages tolerates a missing capability map", permitted_stages(None) == sandbox)

# --- the SQL helper binds rather than interpolates ------------------------------------
clause, params = state_in_clause("state", ACTIVE_STATES)
ok("state_in_clause emits one placeholder per state",
   clause.count("?") == len(ACTIVE_STATES) == len(params), clause)
ok("state_in_clause interpolates no state names",
   not any(state in clause for state in ACTIVE_STATES), clause)

print(f"\n{'ALL' if not FAILURES else str(len(FAILURES)) + ' OF'} "
      f"{'DEVELOPER STATE SYNC CHECKS PASSED' if not FAILURES else 'CHECKS FAILED: ' + ', '.join(FAILURES)}")
raise SystemExit(1 if FAILURES else 0)

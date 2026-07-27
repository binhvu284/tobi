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
    ACTIVE_STATES, CLEANUP_ELIGIBLE_STATES, CORRECTABLE_BY_RECODE, FAULT_STATES, STAGES,
    STATE_KIND, SUCCESS_STATES,
    TERMINAL_STATES, permitted_stages, state_in_clause, workflow_progress,
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

# The overview endpoint once carried its own copy of the terminal set, went stale, and served
# a finished run as the active workflow. It now asks the store, which derives the set. The
# guard follows the logic rather than the file it used to live in.
store_src = (ROOT / "core" / "development_store.py").read_text(encoding="utf-8")
active_query = store_src[store_src.index("def active_session_id"):][:700]
ok("the active-workflow lookup excludes terminal states from the shared set",
   "state_in_clause(\"state\", TERMINAL_STATES)" in active_query and "NOT {clause}" in active_query,
   active_query[:200])
overview_src = (ROOT / "api" / "developer.py").read_text(encoding="utf-8")
ok("overview asks the store instead of scanning every workflow",
   "agent.store.active_session_id()" in overview_src and "agent.list_workflows(50)" not in overview_src)

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

# --- progress is measured against what the policy permits, and gated on delivery ---------
LOCAL = {"github": False, "merge": False, "deploy": False}
all_local_gates = {gate: "completed" for gate in sandbox}

ok("every permitted gate green plus a reachable result is 100%",
   workflow_progress(all_local_gates, LOCAL, delivered=True) == 100)
ok("every permitted gate green with nothing reachable stops at 99",
   workflow_progress(all_local_gates, LOCAL, delivered=False) == 99,
   str(workflow_progress(all_local_gates, LOCAL, delivered=False)))
ok("a run stopped early reports its share of the permitted gates",
   workflow_progress({"prepare": "completed", "index": "completed"}, LOCAL, delivered=False) == 29,
   str(workflow_progress({"prepare": "completed", "index": "completed"}, LOCAL, delivered=False)))
ok("progress never counts a gate the policy forbids",
   workflow_progress({**all_local_gates, "push": "completed"}, LOCAL, delivered=False) ==
   workflow_progress(all_local_gates, LOCAL, delivered=False))
ok("enabling github lowers the same run's progress, because more is now expected",
   workflow_progress(all_local_gates, {"github": True}, delivered=False) <
   workflow_progress(all_local_gates, LOCAL, delivered=False))
ok("a run with no gates yet is 0%", workflow_progress({}, LOCAL, delivered=False) == 0)

# --- retrying a failure must be able to change the outcome -----------------------------
# Three separate dead-end loops shipped in this workflow: an over-long launch command, a
# poisoned resume session, and a gate that re-judged an unchanged worktree. All three looked
# identical to the owner -- press Retry, get the same failure, forever. A verdict on the
# produced code can only be cleared by producing different code, so retrying one of these has
# to hand the run back to the code stage rather than re-running the gate alone.
for code in ("quality_gate_failed", "secret_found"):
    ok(f"retrying {code} re-opens the code stage", code in CORRECTABLE_BY_RECODE)
ok("a stale-snapshot error is not treated as a code problem",
   not (CORRECTABLE_BY_RECODE & {"policy_changed", "plan_changed"}))

agent_source = (ROOT / "core" / "coding_agent.py").read_text(encoding="utf-8")
ok("the retry path reads the shared set instead of an inline literal",
   "in CORRECTABLE_BY_RECODE" in agent_source
   and '{"validation_failed", "review_failed", "review_unavailable"}' not in agent_source)
reset_clause = agent_source[agent_source.index("in CORRECTABLE_BY_RECODE"):][:400]
ok("the reset returns the run to the code stage", "'code'" in reset_clause, reset_clause[:160])

# --- the SQL helper binds rather than interpolates ------------------------------------
clause, params = state_in_clause("state", ACTIVE_STATES)
ok("state_in_clause emits one placeholder per state",
   clause.count("?") == len(ACTIVE_STATES) == len(params), clause)
ok("state_in_clause interpolates no state names",
   not any(state in clause for state in ACTIVE_STATES), clause)

print(f"\n{'ALL' if not FAILURES else str(len(FAILURES)) + ' OF'} "
      f"{'DEVELOPER STATE SYNC CHECKS PASSED' if not FAILURES else 'CHECKS FAILED: ' + ', '.join(FAILURES)}")
raise SystemExit(1 if FAILURES else 0)

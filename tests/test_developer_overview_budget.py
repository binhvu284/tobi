"""Keep the polled Developer overview small enough to answer inside its own timeout.

`GET /api/developer/overview` is polled every five seconds. It used to build every session in
full to pick the active one -- roughly 500 queries across 50 sqlite connections -- and return
them all. Checkpoints were 98% of that: each carries a `recent_events` dump, and the largest
in the live database was 1.13 MB. The response reached 5.2 MB and grew with every run, until
the page began failing its own 15-second load timeout and the owner had to keep refreshing.

Nothing here caps a payload for its own sake. The budget exists because the response is on a
timer: it has to arrive before the next poll starts, on a laptop, forever.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.coding_agent import CodingAgent  # noqa: E402
from core.development_store import DevelopmentStore, utc_now  # noqa: E402

FAILURES: list[str] = []


def ok(label: str, condition: bool, detail: str = "") -> None:
    print(f"{'PASS' if condition else 'FAIL'} {label}{('  -> ' + detail) if detail and not condition else ''}")
    if not condition:
        FAILURES.append(label)


base = ROOT / ".tobi" / "test-runs"
base.mkdir(parents=True, exist_ok=True)
root = Path(tempfile.mkdtemp(prefix="overview_budget_", dir=base))
store = DevelopmentStore(root / "budget.db")

task = store.upsert_task({
    "queue_id": 4242, "title": "Overview budget", "plan_path": "docs/x.md",
    "plan_hash": "b" * 64, "acceptance_criteria": ["stays small"], "dependencies": [],
    "status": "planned", "risk": "low",
})
session = store.create_session(int(task["id"]), "policy-hash", "overview-budget-key")
session_id = int(session["id"])

# A realistic worst case: the handoff blob that actually shipped was 1.13 MB, and twenty of
# them were returned per workflow.
fat_handoff = {
    "status": "paused", "stage": "code", "next_action": "Correct the unmet criteria.",
    "recent_events": [{"event_type": "worker_heartbeat", "payload": {"noise": "x" * 400}}
                      for _ in range(500)],
}
for _ in range(20):
    store.save_checkpoint(
        session_id=session_id, worker_session_id=None,
        head_sha="c" * 40, status="paused", handoff=fat_handoff,
    )
stored = len(json.dumps(fat_handoff)) * 20
ok("fixture reproduces the real shape", stored > 3_000_000, f"{stored:,} chars stored")


class Policy:
    version = 1
    hash = "policy-hash"
    data = {"capabilities": {"github": False, "merge": False, "deploy": False}}

    def limit(self, name: str, default: int) -> int:
        return default


agent = CodingAgent.__new__(CodingAgent)
agent.store = store
agent.policy = Policy()

workflow = agent.get_workflow(session_id)
payload = len(json.dumps(workflow, default=str))
ok("a workflow carries one checkpoint, not twenty", len(workflow["checkpoints"]) == 1,
   str(len(workflow["checkpoints"])))
ok("the newest checkpoint is the one kept",
   int(workflow["checkpoints"][0]["sequence"]) == 20, str(workflow["checkpoints"][0]["sequence"]))
ok("the event log is not shipped to the browser",
   "recent_events" not in json.dumps(workflow["checkpoints"]))
ok("what Mission Control renders survives the trim",
   json.loads(workflow["checkpoints"][0]["handoff_json"]).get("next_action")
   == "Correct the unmet criteria.")
ok("a workflow built from a 3 MB history stays under 64 KB", payload < 64_000, f"{payload:,} chars")

# The full history is still reachable -- trimmed for the poll, not discarded.
ok("every checkpoint remains available for recovery",
   len(store.list_checkpoints(session_id, 50)) == 20,
   str(len(store.list_checkpoints(session_id, 50))))

# The active-workflow lookup must not walk every session.
ok("the active session is found by a single lookup", store.active_session_id() == session_id,
   str(store.active_session_id()))
store.update_session(session_id, state="canceled", completed_at=utc_now())
ok("a terminal run is not reported as active", store.active_session_id() is None,
   str(store.active_session_id()))

overview_src = (ROOT / "api" / "developer.py").read_text(encoding="utf-8")
ok("overview no longer returns every workflow", '"workflows": workflows' not in overview_src)

print(f"\n{'ALL' if not FAILURES else str(len(FAILURES)) + ' OF'} "
      f"{'OVERVIEW BUDGET CHECKS PASSED' if not FAILURES else 'CHECKS FAILED: ' + ', '.join(FAILURES)}")
raise SystemExit(1 if FAILURES else 0)

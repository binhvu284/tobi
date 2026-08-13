"""Queue tab backend checks (#18 UI continuation): owner queue preferences
(Next slot + priority order), auto-queue promotion honoring them, completed
restore/remove, and the plan Markdown endpoint helper. No network, no workers —
workflow starts are stubbed."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TEST_ROOT = ROOT / ".tobi" / "test-runs"
TEST_ROOT.mkdir(parents=True, exist_ok=True)
TMP = Path(tempfile.mkdtemp(prefix="developer_queue_", dir=TEST_ROOT))
os.environ["DB_PATH"] = str(TMP / "agent.db")

from core.coding_agent import CodingAgent  # noqa: E402
from core.coding_policy import CodingPolicy  # noqa: E402
from core.development_store import DevelopmentStore  # noqa: E402
from core import owner_flags  # noqa: E402

PASS = 0


def ok(name: str, condition: bool, detail: str = "") -> None:
    global PASS
    if not condition:
        raise AssertionError(f"{name}: {detail}")
    PASS += 1
    print(f"PASS {name}")


store = DevelopmentStore(TMP / "agent.db")
agent = CodingAgent(policy=CodingPolicy.load(), store=store)

# ── queue_state: baseline shape + normalization ──────────────────────────────
state = agent.queue_state()
ok("queue_state has items", len(state["items"]) >= 20, str(len(state["items"])))
ok("queue_state defaults: empty order + no next", state["order"] == [] and state["next_queue_id"] is None)
ok("queue_state reports auto_queue flag", isinstance(state["auto_queue"], bool))
item_32 = next(item for item in state["items"] if int(item["queue_id"]) == 32)
ok("current six-column Queue names are plain text",
   item_32["title"] == "Health checks run together", item_32["title"])

planned = [int(t["queue_id"]) for t in state["items"] if t["status"] == "planned"]
completed = [int(t["queue_id"]) for t in state["items"] if t["status"] == "completed"]
ok("fixture sanity: planned + completed items exist", len(planned) >= 3 and len(completed) >= 1,
   f"planned={planned} completed={completed}")

# ── set_queue_order: persist, dedupe, next excluded from list ────────────────
a, b, c = planned[0], planned[1], planned[2]
state = agent.set_queue_order([b, c, b], a)          # duplicate b collapses
ok("set_queue_order persists next", state["next_queue_id"] == a)
ok("set_queue_order dedupes + keeps order", state["order"] == [b, c], str(state["order"]))
state = agent.set_queue_order([a, b, c], a)          # next also in list -> dropped from list
ok("next item is excluded from the priority list", state["order"] == [b, c], str(state["order"]))

try:
    agent.set_queue_order([999_999], None)
    raise AssertionError("unknown id accepted")
except KeyError:
    ok("set_queue_order rejects non-planned ids", True)
try:
    agent.set_queue_order([], completed[0])
    raise AssertionError("completed id accepted as next")
except KeyError:
    ok("set_queue_order rejects a completed item as next", True)

# reload from flags: state survives a fresh read
ok("prefs persist in owner_flags",
   json.loads(owner_flags.get_str("developer.queue_order")) == [b, c]
   and owner_flags.get_str("developer.queue_next") == str(a))

# ── restore / remove guards ──────────────────────────────────────────────────
done = completed[0]
state = agent.restore_task(done)
ok("restore: completed -> planned", any(
    t["queue_id"] == done and t["status"] == "planned" for t in state["items"]))
state = agent.restore_task(done)                     # already planned -> idempotent
ok("restore of an already-queued item is a no-op, not an error",
   sum(1 for t in state["items"] if t["queue_id"] == done and t["status"] == "planned") == 1)
try:
    agent.remove_task(done)                          # planned -> remove still refused
    raise AssertionError("remove of planned item accepted")
except ValueError:
    ok("remove still guards an item that is in the queue", True)

# Starting a run moves a task to 'approved', and nothing moves it back unless that run
# merges and deploys. restore/remove used to accept 'completed' only, so a run that finished
# locally, was canceled, or failed left its item reachable from neither the queue nor the
# completed list -- a History row with no action on it.
store.set_task_status(done, "approved")
state = agent.restore_task(done)
ok("an item stranded at approved can be pushed back to the queue", any(
    t["queue_id"] == done and t["status"] == "planned" for t in state["items"]))
ok("requeue clears a stale owner state", (store.get_task(queue_id=done) or {})["owner_state"] == "Ready")
store.set_task_status(done, "approved")
state = agent.remove_task(done)
ok("an item stranded at approved can also be removed",
   all(t["queue_id"] != done for t in state["items"]))
store.set_task_status(done, "planned")
store.set_task_status(done, "completed")             # put it back
state = agent.remove_task(done)
ok("remove: completed -> hidden from queue", all(t["queue_id"] != done for t in state["items"]))
agent.sync()
ok("re-sync does not resurrect a removed item",
   all(t["queue_id"] != done for t in agent.queue_state()["items"]))
row = store.get_task(queue_id=done)
ok("removed item is status=deleted (row kept)", row is not None and row["status"] == "deleted")
store.set_task_status(done, "completed")             # restore fixture state

# ── plan markdown ────────────────────────────────────────────────────────────
plan = agent.plan_markdown(a)
ok("plan_markdown returns the plan text", len(plan["markdown"]) > 100 and plan["plan_path"].endswith(".md"))
ok("plan_markdown carries id + title", plan["queue_id"] == a and bool(plan["title"]))
try:
    agent.plan_markdown(999_999)
    raise AssertionError("unknown plan accepted")
except KeyError:
    ok("plan_markdown 404s unknown items", True)

# ── auto-queue promotion honors Next -> priority list, and shifts pointers ────
def eligible(qid: int) -> bool:
    task = store.get_task(queue_id=qid)
    deps = json.loads(task["dependencies_json"] or "[]")
    return all((store.get_task(queue_id=int(d)) or {}).get("status") == "completed" for d in deps)

elig = [qid for qid in planned if eligible(qid)]
ok("fixture sanity: >=2 eligible planned items", len(elig) >= 2, str(elig))
x, y = elig[0], elig[1]
agent.set_queue_order([y], x)                        # next=x, priority list = [y]
owner_flags.set_bool("developer.auto_queue", True)

started: list[int] = []
agent.list_workflows = lambda limit=200: []                       # no active run
agent.create_workflow = lambda qid, **kw: (started.append(int(qid)) or {"id": 1, "queue_id": qid})
agent.preflight = lambda qid, **kw: {"ready": True, "readiness_id": int(qid), "blockers": []}
agent.start_background = lambda wid: {"id": wid, "started": True}
agent._event = lambda *args, **kw: None

result = agent.start_next_queued()
ok("auto mode starts the Next item first", result is not None and started == [x],
   f"started={started}")
ok("priority #1 moved into Next; list shifts",
   owner_flags.get_str("developer.queue_next") == str(y)
   and json.loads(owner_flags.get_str("developer.queue_order")) == [],
   f"next={owner_flags.get_str('developer.queue_next')!r}")

result = agent.start_next_queued()                    # promotes y (the new next)
ok("second promotion consumes the shifted Next", started == [x, y], f"started={started}")
ok("Next slot is empty once the list runs out", owner_flags.get_str("developer.queue_next") == "")

owner_flags.set_bool("developer.auto_queue", False)
ok("auto off: start_next_queued is a no-op", agent.start_next_queued() is None)

print(f"\n{PASS} checks passed")

"""Queue #18 controlled coding-agent acceptance checks (no network calls)."""
from __future__ import annotations

import json
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path


ROOT = Path(os.environ.get("TOBI_VALIDATION_ROOT") or Path(__file__).resolve().parents[1]).resolve()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TEST_ROOT = ROOT / ".tobi" / "test-runs"
TEST_ROOT.mkdir(parents=True, exist_ok=True)
TMP = Path(tempfile.mkdtemp(prefix="coding_agent_", dir=TEST_ROOT))
os.environ["DB_PATH"] = str(TMP / "agent.db")
os.environ["TOBI_HERMES_CODING_COMMAND"] = "definitely-missing-hermes"
os.environ["TOBI_CODING_WORKERS"] = "hermes"

from core.coding_agent import CodingAgent  # noqa: E402
from core.coding_policy import CodingPolicy, PolicyDenied, find_probable_secrets  # noqa: E402
from core.coding_queue import parse_queue  # noqa: E402
from core.development_store import DevelopmentStore, utc_now  # noqa: E402
from core.hermes_worker import HermesWorker  # noqa: E402


PASS = 0


def ok(name: str, condition: bool, detail: str = "") -> None:
    global PASS
    if not condition:
        raise AssertionError(f"{name}: {detail}")
    PASS += 1
    print(f"PASS {name}")


def git(*args: str, cwd: Path | None = None) -> str:
    result = subprocess.run(["git", *args], cwd=str(cwd or TMP), capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise AssertionError(result.stderr or result.stdout)
    return result.stdout.strip()


def make_repo() -> tuple[Path, Path]:
    origin = TMP / "origin.git"
    repo = TMP / "repo"
    git("init", "--bare", str(origin))
    repo.mkdir()
    git("init", "-b", "main", cwd=repo)
    git("config", "user.email", "test@tobi.local", cwd=repo)
    git("config", "user.name", "TOBI Test", cwd=repo)
    (repo / "README.md").write_text("# Test repo\n", encoding="utf-8")
    git("add", "README.md", cwd=repo)
    git("commit", "-m", "initial", cwd=repo)
    git("remote", "add", "origin", str(origin), cwd=repo)
    git("push", "-u", "origin", "main", cwd=repo)
    return repo, origin


repo, origin = make_repo()
policy_data = json.loads((ROOT / "config" / "coding_policy.v1.json").read_text(encoding="utf-8"))
policy_data["repository"]["allowed_remote_suffix"] = "origin.git"
policy_data["repository"]["allowed_repository"] = ""
policy_data["workers"]["allow_external_cli"] = True
policy_data["commands"]["mandatory_checks"] = [[sys.executable, "-c", "print('ok')"]]
policy_data["commands"]["allowed_executables"].append(Path(sys.executable).stem.lower())
policy = CodingPolicy(policy_data, repo_root=repo)
store = DevelopmentStore(TMP / "agent.db")
conn = store.connect()
migration = conn.execute("SELECT version FROM developer_schema_migrations").fetchone()
conn.close()
ok("developer schema migration is recorded", migration[0] == 1)
conn = store.connect()
versions = [row[0] for row in conn.execute("SELECT version FROM developer_schema_migrations ORDER BY version")]
conn.close()
ok(
    "production schema migrations are recorded",
    versions == list(range(1, max(versions, default=0) + 1)),
    str(versions),
)
conn = store.connect()
session_columns = {row[1] for row in conn.execute("PRAGMA table_info(coding_sessions)")}
conn.close()
ok("validation and review correction counters are separate", "validation_cycles" in session_columns)

# Policy boundaries.
ok("policy hash is stable", policy.hash == CodingPolicy(policy_data, repo_root=repo).hash)
ok("ordinary source is L2", policy.path_decision("core/example.py").level == 2)
ok("policy file is protected", policy.path_decision("config/coding_policy.v2.json").protected)
ok("developer state is forbidden", policy.path_decision(".tobi/developer/index/a.json").forbidden)
try:
    policy.assert_write_paths(["config/coding_policy.v2.json"])
    raise AssertionError("protected path was allowed")
except PolicyDenied:
    ok("protected write requires special approval", True)
policy.assert_write_paths(["config/coding_policy.v2.json"], special_approval=True)
ok("special approval permits protected path", True)
try:
    policy.assert_command(["git", "push", "--force", "origin", "main"], allow_network=True)
    raise AssertionError("force push was allowed")
except PolicyDenied:
    ok("force push is always denied", True)
ok("secret detector catches GitHub token", bool(find_probable_secrets("token=ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ123456")))

# Markdown queue mirror and dependency truth.
items = parse_queue()
item18 = next(item for item in items if item["queue_id"] == 18)
ok("queue parser finds all items", len(items) >= 21, str(len(items)))
ok("item 18 depends on accepted Awakening", item18["dependencies"] == [17], str(item18["dependencies"]))
ok("item 18 targets Agent 3.0.0", item18["target_version"] == "3.0.0", str(item18["target_version"]))

# Store: additive schema, idempotency, one worker, events, one-use re-auth.
agent = CodingAgent(policy=policy, store=store)
test_task = store.upsert_task({
    "queue_id": 180,
    "title": "Acceptance workflow",
    "plan_path": "README.md",
    "plan_hash": hashlib.sha256((repo / "README.md").read_bytes()).hexdigest(),
    "acceptance_criteria": ["workflow keeps durable state"],
    "dependencies": [],
    "status": "planned",
    "risk": "medium",
    "target_version": "3.18.0",
})
readiness_payload = {
    "ready": True,
    "selected_agent": "deepseek-harness",
    "reviewer": "reviewer-default",
    "fallback_agents": [],
    "validation_commands": policy.mandatory_checks(),
    "plan_hash": test_task["plan_hash"],
}
readiness = store.save_readiness(
    int(test_task["id"]), "ready", readiness_payload, policy.hash
)
workflow = agent.create_workflow(180, idempotency_key="acceptance-item180", readiness_id=int(readiness["id"]))
same = agent.create_workflow(180, idempotency_key="acceptance-item180", readiness_id=int(readiness["id"]))
ok("workflow creation is idempotent", workflow["id"] == same["id"])
ok("workflow has full stage DAG", len(workflow["stages"]) == 11, str(len(workflow["stages"])))

for index in range(5):
    store.append_event(workflow["id"], "test_event", {"index": index})
events = store.list_events(workflow["id"])
ok("events are strictly ordered", [event["sequence"] for event in events] == list(range(1, len(events) + 1)))
agent._event(workflow["id"], "redaction_probe", {"token": "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ123456", "output": "password=supersecretvalue123"})
redacted = store.list_events(workflow["id"])[-1]["payload"]
ok("event keys are redacted", redacted["token"] == "[REDACTED]")
ok("nested event text is redacted", "supersecretvalue123" not in redacted["output"])
artifact = agent._artifact(workflow["id"], "probe", {"token": "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ123456"})
ok("evidence artifact is retained", Path(artifact["path"]).is_file() and artifact["size_bytes"] > 0)
ok("evidence artifact content is redacted", "ABCDEFGHIJKLMNOPQRSTUVWXYZ" not in Path(artifact["path"]).read_text(encoding="utf-8"))

challenge, _ = store.create_challenge("special_paths", policy.hash, session_id=workflow["id"], ttl_seconds=60)
store.consume_challenge(challenge, "special_paths", policy.hash, session_id=workflow["id"])
try:
    store.consume_challenge(challenge, "special_paths", policy.hash, session_id=workflow["id"])
    raise AssertionError("challenge replay was allowed")
except PermissionError:
    ok("re-auth challenge cannot replay", True)

try:
    other_task = store.upsert_task({
        "queue_id": 181, "title": "Parallel guard", "plan_path": "README.md",
        "plan_hash": test_task["plan_hash"], "acceptance_criteria": ["one active run"],
        "dependencies": [], "status": "planned", "risk": "low",
    })
    store.create_session(other_task["id"], policy.hash, "parallel-worker")
    raise AssertionError("parallel active worker was allowed")
except RuntimeError:
    ok("one-active-worker invariant is enforced", True)

# Real local Git worktree plus Hermes-unavailable checkpoint recovery.
result = agent.run_to_gate(workflow["id"])
ok("workflow pauses when Hermes is unavailable", result["state"] == "paused", result["state"])
ok("worker failure is typed", result["error_code"] == "worker_unavailable", str(result["error_code"]))
ok("isolated worktree is retained", bool(result["worktree"]) and Path(result["worktree"]).is_dir())
ok("deployment checkout remains on main", git("branch", "--show-current", cwd=repo) == "main")
ok("worktree branch uses target version", str(result["branch"]).startswith("v3.18.0/"), str(result["branch"]))

other_task = store.get_task(queue_id=181)
try:
    store.create_session(other_task["id"], policy.hash, "active-after-pause")
    raise AssertionError("paused workflow released the foreground-run slot")
except RuntimeError:
    ok("paused workflow preserves one-foreground-run invariant", True)

try:
    agent.releases.reserve("3.18.0", 181, risk="medium")
    raise AssertionError("reserved version was reused")
except RuntimeError:
    ok("reserved semantic version cannot move to another queue item", True)

timeout_policy_data = json.loads(json.dumps(policy_data))
timeout_policy_data["limits"]["worker_timeout_seconds"] = 1
timeout_policy = CodingPolicy(timeout_policy_data, repo_root=repo)
os.environ["TOBI_HERMES_CODING_COMMAND"] = "ping 127.0.0.1 -n 8"
os.environ["TOBI_HERMES_SANDBOX_ARGV"] = '["{command}"]'
try:
    HermesWorker(timeout_policy).run(999, "timeout", repo, {"test": True})
    raise AssertionError("silent worker escaped its deadline")
except TimeoutError:
    ok("silent worker is terminated at its deadline", True)
finally:
    os.environ["TOBI_HERMES_CODING_COMMAND"] = "definitely-missing-hermes"
    os.environ.pop("TOBI_HERMES_SANDBOX_ARGV", None)

# Concurrent event writers preserve unique monotonic sequence numbers.
threads = [threading.Thread(target=store.append_event, args=(workflow["id"], "concurrent", {"n": n})) for n in range(10)]
for thread in threads:
    thread.start()
for thread in threads:
    thread.join()
events = store.list_events(workflow["id"])
sequences = [event["sequence"] for event in events]
ok("concurrent events stay unique", len(sequences) == len(set(sequences)))
ok("concurrent events stay monotonic", sequences == sorted(sequences))

# API auth is denied without a vault session, then works through an override.
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from api import developer  # noqa: E402

developer.agent = agent
developer.start_loop = lambda: True
app = FastAPI()
app.include_router(developer.router)
client = TestClient(app)
ok("Developer API denies anonymous owner", client.get("/api/developer/overview").status_code == 401)
app.dependency_overrides[developer.require_owner] = lambda: "test-owner"
response = client.get("/api/developer/overview")
ok("authenticated overview works", response.status_code == 200, response.text[:200])
ok("overview returns policy fingerprint", response.json()["policy"]["hash"] == policy.hash)

# A terminal run must not be served as the active workflow. The overview endpoint used to
# carry its own copy of the terminal-state set; when `locally_complete` was added the copy
# was missed, so a finished run stayed "active" and the Developer page kept rendering it.
store.update_session(int(workflow["id"]), state="locally_complete", completed_at=utc_now())
terminal_overview = client.get("/api/developer/overview").json()
ok("a locally-complete run is not the active workflow", terminal_overview["active_workflow"] is None,
   str((terminal_overview.get("active_workflow") or {}).get("state")))
store.update_session(int(workflow["id"]), state=workflow["state"], completed_at=None)

# Delivery is keyed on the commit gate, never on head_sha. `prepare` seeds head_sha with the
# branch point, so every run carries one from the moment its worktree exists -- three runs
# canceled during coding held a head_sha identical to their base_sha. Reading it as "work
# exists" reported them 100% delivered.
live = agent.get_workflow(int(workflow["id"]))
stage_map = {item["node_id"]: item["status"] for item in live["stages"]}
ok("an uncommitted run is not deliverable even though head_sha is set",
   agent._delivery(live, {**stage_map, "commit": "pending"})["reachable"] is False,
   f"head_sha={live.get('head_sha')}")
delivered = agent._delivery(live, {**stage_map, "commit": "completed"})
ok("a committed run is deliverable as a local branch",
   delivered["reachable"] and delivered["kind"] == "local_branch", str(delivered))
ok("get_workflow exposes a delivery block", isinstance(live.get("delivery"), dict))
ok("progress never claims 100 without a reachable result",
   agent._delivery(live, stage_map)["reachable"] or int(live["progress"]) < 100,
   f"progress={live['progress']}")
event_response = client.get(f"/api/developer/events?workflow_id={workflow['id']}&after=0")
ok("event trace endpoint works", event_response.status_code == 200 and len(event_response.json()["events"]) >= 10)
goal_response = client.post("/api/developer/goals", json={
    "title": "API contract goal",
    "objective": "Verify the authenticated durable goal API without starting a coding worker.",
    "acceptance_criteria": ["goal is persisted and owner commands are idempotent"],
    "autonomy": "sandbox",
})
ok("authenticated owner can create a durable goal", goal_response.status_code == 200, goal_response.text[:200])
goal_id = int(goal_response.json()["id"])
goals_response = client.get("/api/developer/goals")
ok("goal list exposes the persisted goal", goals_response.status_code == 200 and any(
    int(item["id"]) == goal_id for item in goals_response.json()["goals"]
))
command_body = {"command": "evaluate", "idempotency_key": "coding-agent-goal-evaluate-contract"}
evaluate_response = client.post(f"/api/developer/goals/{goal_id}/commands", json=command_body)
replay_response = client.post(f"/api/developer/goals/{goal_id}/commands", json=command_body)
ok("goal evidence evaluation is accepted", evaluate_response.status_code == 200 and evaluate_response.json()["status"] == "active")
ok("goal command replay is idempotent", replay_response.status_code == 200 and replay_response.json() == evaluate_response.json())
ok("goal API creates no synthetic Queue mirror", store.get_task(queue_id=900_000_000 + goal_id) is None)
delete_response = client.post(f"/api/developer/goals/{goal_id}/commands", json={
    "command": "delete", "idempotency_key": "coding-agent-goal-delete-contract",
})
ok("goal delete is a recoverable soft delete", delete_response.status_code == 200 and delete_response.json()["status"] == "deleted")
visible_goal_ids = {int(item["id"]) for item in client.get("/api/developer/goals").json()["goals"]}
ok("soft-deleted goal is hidden from owner goal list", goal_id not in visible_goal_ids)
deepseek_models = client.get("/api/developer/workers/deepseek-harness/models")
ok("DeepSeek Harness offers DeepSeek models only", (
    deepseek_models.status_code == 200
    and deepseek_models.json()["source"] == "deepseek"
    and isinstance(deepseek_models.json()["models"], list)
    and all(item["provider"] == "deepseek" for item in deepseek_models.json()["models"])
), deepseek_models.text[:200])
from api import dashboard  # noqa: E402
ok("dashboard registers Developer router", any(getattr(route, "path", "") == "/api/developer/overview" for route in dashboard.app.routes))

print(f"ALL {PASS} CODING AGENT CHECKS PASSED")

# The test runner owns this isolated directory and may clean it after all handles close.
shutil.rmtree(TMP, ignore_errors=True)

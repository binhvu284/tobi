"""Queue #18 controlled coding-agent acceptance checks (no network calls)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TEST_ROOT = ROOT / ".tobi" / "test-runs"
TEST_ROOT.mkdir(parents=True, exist_ok=True)
TMP = Path(tempfile.mkdtemp(prefix="coding_agent_", dir=TEST_ROOT))
os.environ["DB_PATH"] = str(TMP / "agent.db")
os.environ["TOBI_HERMES_CODING_COMMAND"] = "definitely-missing-hermes"

from core.coding_agent import CodingAgent  # noqa: E402
from core.coding_policy import CodingPolicy, PolicyDenied, find_probable_secrets  # noqa: E402
from core.coding_queue import parse_queue  # noqa: E402
from core.development_store import DevelopmentStore  # noqa: E402
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
policy_data["commands"]["mandatory_checks"] = [[sys.executable, "-c", "print('ok')"]]
policy_data["commands"]["allowed_executables"].append(Path(sys.executable).stem.lower())
policy = CodingPolicy(policy_data, repo_root=repo)
store = DevelopmentStore(TMP / "agent.db")
conn = store.connect()
migration = conn.execute("SELECT version FROM developer_schema_migrations").fetchone()
conn.close()
ok("developer schema migration is recorded", migration[0] == 1)

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
workflow = agent.create_workflow(18, idempotency_key="acceptance-item18")
same = agent.create_workflow(18, idempotency_key="acceptance-item18")
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
    task20 = store.get_task(queue_id=20)
    store.create_session(task20["id"], policy.hash, "parallel-worker")
    raise AssertionError("parallel active worker was allowed")
except RuntimeError:
    ok("one-active-worker invariant is enforced", True)

# Real local Git worktree plus Hermes-unavailable checkpoint recovery.
result = agent.run_to_gate(workflow["id"])
ok("workflow pauses when Hermes is unavailable", result["state"] == "paused", result["state"])
ok("Hermes failure is typed", result["error_code"] == "hermes_unavailable", str(result["error_code"]))
ok("isolated worktree is retained", bool(result["worktree"]) and Path(result["worktree"]).is_dir())
ok("deployment checkout remains on main", git("branch", "--show-current", cwd=repo) == "main")
ok("worktree branch uses target version", str(result["branch"]).startswith("v3.0.0/"), str(result["branch"]))

task20 = store.get_task(queue_id=20)
other = store.create_session(task20["id"], policy.hash, "active-after-pause")
try:
    agent.command(workflow["id"], "resume")
    raise AssertionError("paused workflow resumed beside another active workflow")
except RuntimeError:
    ok("resume preserves one-active-worker invariant", True)
store.update_session(other["id"], state="canceled", completed_at="2026-01-01T00:00:00+00:00")

try:
    agent.releases.reserve("3.0.0", 20, risk="medium")
    raise AssertionError("reserved version was reused")
except RuntimeError:
    ok("reserved semantic version cannot move to another queue item", True)

timeout_policy_data = json.loads(json.dumps(policy_data))
timeout_policy_data["limits"]["worker_timeout_seconds"] = 1
timeout_policy = CodingPolicy(timeout_policy_data, repo_root=repo)
os.environ["TOBI_HERMES_CODING_COMMAND"] = "ping 127.0.0.1 -n 8"
try:
    HermesWorker(timeout_policy).run(999, "timeout", repo, {"test": True})
    raise AssertionError("silent worker escaped its deadline")
except TimeoutError:
    ok("silent worker is terminated at its deadline", True)
finally:
    os.environ["TOBI_HERMES_CODING_COMMAND"] = "definitely-missing-hermes"

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
app = FastAPI()
app.include_router(developer.router)
client = TestClient(app)
ok("Developer API denies anonymous owner", client.get("/api/developer/overview").status_code == 401)
app.dependency_overrides[developer.require_owner] = lambda: "test-owner"
response = client.get("/api/developer/overview")
ok("authenticated overview works", response.status_code == 200, response.text[:200])
ok("overview returns policy fingerprint", response.json()["policy"]["hash"] == policy.hash)
event_response = client.get(f"/api/developer/events?workflow_id={workflow['id']}&after=0")
ok("event trace endpoint works", event_response.status_code == 200 and len(event_response.json()["events"]) >= 10)
from api import dashboard  # noqa: E402
ok("dashboard registers Developer router", any(getattr(route, "path", "") == "/api/developer/overview" for route in dashboard.app.routes))

print(f"ALL {PASS} CODING AGENT CHECKS PASSED")

# The test runner owns this isolated directory and may clean it after all handles close.
shutil.rmtree(TMP, ignore_errors=True)

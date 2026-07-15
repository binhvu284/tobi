"""Production invariants for queue #18 continuous coding goals (no external network)."""
from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TEST_ROOT = ROOT / ".tobi" / "test-runs"
TEST_ROOT.mkdir(parents=True, exist_ok=True)
TMP = Path(tempfile.mkdtemp(prefix="coding_prod_", dir=TEST_ROOT))
os.environ["DB_PATH"] = str(TMP / "production.db")
os.environ["TOBI_CODING_WORKERS"] = "llm"

from core.coding_agent import CodingAgent  # noqa: E402
from core.coding_loop import CodingLoopService  # noqa: E402
from core.coding_policy import CodingPolicy, PolicyDenied  # noqa: E402
from core.coding_tools import CodingToolBroker  # noqa: E402
from core.deployment_manager import DeploymentManager, DeploymentError  # noqa: E402
from core.development_store import DevelopmentStore, utc_now  # noqa: E402
from core.git_workspace import GitWorkspaceManager  # noqa: E402


PASS = 0


def ok(name: str, condition: bool, detail: str = "") -> None:
    global PASS
    if not condition:
        raise AssertionError(f"{name}: {detail}")
    PASS += 1
    print(f"PASS {name}")


def run_git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=str(repo), capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise AssertionError(result.stderr or result.stdout)
    return result.stdout.strip()


def make_repo(name: str) -> tuple[Path, Path, str]:
    origin = TMP / f"{name}.git"
    repo = TMP / name
    subprocess.run(["git", "init", "--bare", str(origin)], capture_output=True, check=True)
    repo.mkdir()
    run_git(repo, "init", "-b", "main")
    run_git(repo, "config", "user.email", "production@tobi.local")
    run_git(repo, "config", "user.name", "TOBI Production Test")
    (repo / "README.md").write_text("# production\n", encoding="utf-8")
    run_git(repo, "add", "README.md")
    run_git(repo, "commit", "-m", "initial")
    run_git(repo, "remote", "add", "origin", str(origin))
    run_git(repo, "push", "-u", "origin", "main")
    return repo, origin, run_git(repo, "rev-parse", "HEAD")


def policy_for(repo: Path, origin: Path) -> CodingPolicy:
    data = json.loads((ROOT / "config" / "coding_policy.v1.json").read_text(encoding="utf-8"))
    data["repository"]["allowed_repository"] = ""
    data["repository"]["allowed_remote_suffix"] = origin.name
    data["commands"]["mandatory_checks"] = [[sys.executable, "-c", "print('validated')"]]
    executable = Path(sys.executable).stem.lower()
    if executable not in data["commands"]["allowed_executables"]:
        data["commands"]["allowed_executables"].append(executable)
    return CodingPolicy(data, repo_root=repo)


repo, origin, base = make_repo("coding")
policy = policy_for(repo, origin)
store = DevelopmentStore(TMP / "production.db")
manager = GitWorkspaceManager(policy)

# Policy authority and repository identity are exact.
ok("queue authority is protected", policy.path_decision("docs/feature-idea-queue/QUEUE.md").protected)
production_data = json.loads((ROOT / "config" / "coding_policy.v1.json").read_text(encoding="utf-8"))
production_policy = CodingPolicy(production_data, repo_root=repo)
try:
    production_policy.assert_remote("https://lookalike.invalid/binhvu284/tobi.git")
    raise AssertionError("lookalike remote was accepted")
except PolicyDenied:
    ok("lookalike remote is denied", True)

# Typed tools cannot escape, cannot modify protected authority, and scans include new files.
prepared = manager.prepare(77, "3.0.77", "broker safety", fetch=False)
worktree = Path(prepared["worktree"])
broker = CodingToolBroker(policy, worktree)
broker.replace_text("README.md", "# production", "# production safe")
ok("brokered replacement writes inside worktree", "safe" in (worktree / "README.md").read_text(encoding="utf-8"))
try:
    broker.read_file("../../outside.txt")
    raise AssertionError("tool path escaped")
except PolicyDenied:
    ok("broker blocks path escape", True)
try:
    broker.write_file("docs/feature-idea-queue/QUEUE.md", "tampered")
    raise AssertionError("queue authority was writable")
except PolicyDenied:
    ok("broker blocks queue self-modification", True)
(worktree / "new_secret.txt").write_text("token=ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ123456\n", encoding="utf-8")
ok("untracked secrets block pre-commit scan", bool(manager.scan_secrets(worktree)))
(worktree / "new_secret.txt").unlink()


class FakeWorker:
    def run(self, workflow_id, stage_id, worktree, brief, **kwargs):
        target = Path(worktree) / "goal_result.txt"
        target.write_text("goal standard met\n", encoding="utf-8")
        callback = kwargs.get("on_event")
        if callback:
            callback("complete", {"summary": "goal result written"})
        return {"ok": True, "exit_code": 0, "events": [{"type": "complete"}],
                "output": "complete", "worker": "fake"}

    def cancel(self, workflow_id):
        return True


class FakeReviewer:
    def review(self, **kwargs):
        return {"qualified": True, "score": 1.0, "unmet": [], "risks": [], "summary": "accepted"}


# A persisted sandbox goal executes to a deterministic local qualification gate.
agent = CodingAgent(policy=policy, store=store)
agent.worker = FakeWorker()
agent.reviewer = FakeReviewer()
goal = agent.create_goal(
    title="Production loop goal",
    objective="Create a durable proof file and satisfy every configured validation command.",
    acceptance_criteria=["goal_result.txt exists", "all configured checks pass"],
    autonomy="sandbox",
    max_iterations=3,
)
loop = CodingLoopService(agent)
result = loop.tick()
ok("continuous goal reaches local qualification", bool(result and result["status"] == "qualified_local"), str(result))
qualified_workflow = agent.get_workflow(int(result["current_session_id"]))
ok("qualified goal stops before GitHub", qualified_workflow["error_code"] == "autonomy_boundary")
ok("goal iteration evidence is persisted", int(result["iteration_count"]) == 1)

# Goal and command claims are database-backed and idempotent.
second = agent.create_goal(
    title="Lease test goal", objective="Remain queued while database lease ownership is verified.",
    acceptance_criteria=["only one owner claims the goal"], autonomy="sandbox",
)
claimed = store.claim_goal("owner-a", 120)
ok("first loop owner claims queued goal", bool(claimed and claimed["id"] == second["id"]))
ok("second loop owner cannot steal live lease", store.claim_goal("owner-b", 120) is None)
command = store.begin_command("production-command-key", "goal", int(second["id"]), "pause")
store.finish_command("production-command-key", {"status": "paused"})
replayed = store.begin_command("production-command-key", "goal", int(second["id"]), "pause")
ok("command response is idempotently replayable", not replayed["_claimed"] and replayed["status"] == "completed")

# Deployment applies the exact merged SHA and health reports that same revision.
deploy_repo, deploy_origin, prior = make_repo("deploy")
(deploy_repo / "release.txt").write_text("new\n", encoding="utf-8")
run_git(deploy_repo, "add", "release.txt")
run_git(deploy_repo, "commit", "-m", "new release")
new_sha = run_git(deploy_repo, "rev-parse", "HEAD")
run_git(deploy_repo, "push", "origin", "main")
run_git(deploy_repo, "switch", "--detach", prior)


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        revision = run_git(deploy_repo, "rev-parse", "HEAD")
        body = json.dumps({"status": "ok", "revision": revision}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


server = HTTPServer(("127.0.0.1", 0), HealthHandler)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
deploy_data = json.loads((ROOT / "config" / "coding_policy.v1.json").read_text(encoding="utf-8"))
deploy_data["repository"]["allowed_repository"] = ""
deploy_data["repository"]["allowed_remote_suffix"] = deploy_origin.name
deploy_data["capabilities"]["deploy"] = True
deploy_data["deployment"] = {
    "target_name": "local-test", "checkout_path": str(deploy_repo),
    "preflight": [], "build": [], "restart": [],
    "health_url": f"http://127.0.0.1:{server.server_port}/health",
    "require_health_revision": True, "rollback": [],
}
deploy_policy = CodingPolicy(deploy_data, repo_root=deploy_repo)
deploy_store = DevelopmentStore(TMP / "deploy.db")
conn = deploy_store.connect()
release_id = conn.execute(
    "INSERT INTO releases(version,source,status,created_at) VALUES ('9.0.0','test','merged',?)", (utc_now(),)
).lastrowid
conn.commit()
conn.close()
deployment = DeploymentManager(deploy_policy, deploy_store).deploy(int(release_id), prior, new_sha)
ok("deployment reaches exact requested SHA", deployment["status"] == "healthy" and run_git(deploy_repo, "rev-parse", "HEAD") == new_sha)

# A failing build returns the checkout to the exact previous healthy SHA.
(deploy_repo / "release.txt").write_text("broken\n", encoding="utf-8")
run_git(deploy_repo, "add", "release.txt")
run_git(deploy_repo, "commit", "-m", "broken release")
broken_sha = run_git(deploy_repo, "rev-parse", "HEAD")
run_git(deploy_repo, "push", "origin", "main")
run_git(deploy_repo, "switch", "--detach", new_sha)
deploy_data["deployment"]["build"] = [[sys.executable, "-c", "raise SystemExit(1)"]]
deploy_data["commands"]["allowed_executables"].append(Path(sys.executable).stem.lower())
rollback_policy = CodingPolicy(deploy_data, repo_root=deploy_repo)
conn = deploy_store.connect()
rollback_release = conn.execute(
    "INSERT INTO releases(version,source,status,created_at) VALUES ('9.0.1','test','merged',?)", (utc_now(),)
).lastrowid
conn.commit()
conn.close()
rolled_back = DeploymentManager(rollback_policy, deploy_store).deploy(int(rollback_release), new_sha, broken_sha)
ok("failed deployment rolls back exact prior SHA", rolled_back["status"] == "rolled_back" and run_git(deploy_repo, "rev-parse", "HEAD") == new_sha)
server.shutdown()
server.server_close()

print(f"ALL {PASS} PRODUCTION CODING CHECKS PASSED")


def remove_readonly(function, path, _exc):
    os.chmod(path, stat.S_IWRITE)
    function(path)


shutil.rmtree(TMP, onerror=remove_readonly)

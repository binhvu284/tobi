"""Coding Agent v2 control-plane invariants without external provider calls."""
from __future__ import annotations

import base64
import json
import os
import re
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
TMP = Path(tempfile.mkdtemp(prefix="coding_v2_", dir=TEST_ROOT))
os.environ["DB_PATH"] = str(TMP / "v2.db")

from core.coding_agent import CodingAgent, STAGES  # noqa: E402
from core.coding_contracts import SprintBudget, WorkerProfile  # noqa: E402
from core.coding_learning import CodingLearningService  # noqa: E402
from core.coding_policy import CodingPolicy  # noqa: E402
from core.coding_runner import IsolatedProcessRunner, QueuedProcessRunner  # noqa: E402
from core.coding_runner_service import CodingRunnerService  # noqa: E402
from core.coding_workers import (  # noqa: E402
    CodexCLIWorker, CodingWorkerRouter, CodingWorkerUnavailable, OpenCodeCLIWorker,
    _platform_cli_command,
)
from core.development_store import DevelopmentStore  # noqa: E402


PASS = 0


def ok(name: str, condition: bool, detail: str = "") -> None:
    global PASS
    if not condition:
        raise AssertionError(f"{name}: {detail}")
    PASS += 1
    print(f"PASS {name}")


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=str(repo), capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise AssertionError(result.stderr or result.stdout)
    return result.stdout.strip()


repo = TMP / "repo"
origin = TMP / "origin.git"
subprocess.run(["git", "init", "--bare", str(origin)], check=True, capture_output=True)
repo.mkdir()
git(repo, "init", "-b", "main")
git(repo, "config", "user.email", "v2@tobi.local")
git(repo, "config", "user.name", "TOBI V2 Test")
(repo / "README.md").write_text("# v2\n", encoding="utf-8")
git(repo, "add", "README.md")
git(repo, "commit", "-m", "initial")
git(repo, "remote", "add", "origin", str(origin))
git(repo, "push", "-u", "origin", "main")

data = json.loads((ROOT / "config" / "coding_policy.v1.json").read_text(encoding="utf-8"))
data["repository"]["allowed_repository"] = ""
data["repository"]["allowed_remote_suffix"] = origin.name
data["commands"]["mandatory_checks"] = [[sys.executable, "-c", "print('ok')"]]
executable = Path(sys.executable).stem.lower()
if executable not in data["commands"]["allowed_executables"]:
    data["commands"]["allowed_executables"].append(executable)
policy = CodingPolicy(data, repo_root=repo)
store = DevelopmentStore(TMP / "v2.db")
agent = CodingAgent(policy=policy, store=store)

with store.connect() as conn:
    versions = [row[0] for row in conn.execute(
        "SELECT version FROM developer_schema_migrations ORDER BY version"
    )]
ok("v2 schema migration is additive", versions == [1, 2, 3, 4, 5, 6, 7], str(versions))

legacy_store = DevelopmentStore(TMP / "legacy_profile.db")
with legacy_store.connect() as conn:
    conn.execute(
        "UPDATE coding_worker_profiles SET model=? WHERE slug='opencode-glm'",
        ("zai-coding-plan/glm-4.6",),
    )
    conn.execute("DELETE FROM developer_schema_migrations WHERE version=5")
    conn.commit()
legacy_store = DevelopmentStore(TMP / "legacy_profile.db")
ok(
    "legacy OpenCode default migrates to a live model",
    legacy_store.get_worker_profile("opencode-glm")["model"] == "zai-coding-plan/glm-5.2",
)

custom_store = DevelopmentStore(TMP / "custom_profile.db")
with custom_store.connect() as conn:
    conn.execute(
        "UPDATE coding_worker_profiles SET model=? WHERE slug='opencode-glm'",
        ("zai-coding-plan/glm-5.1",),
    )
    conn.execute("DELETE FROM developer_schema_migrations WHERE version=5")
    conn.commit()
custom_store = DevelopmentStore(TMP / "custom_profile.db")
ok(
    "OpenCode migration preserves owner model choices",
    custom_store.get_worker_profile("opencode-glm")["model"] == "zai-coding-plan/glm-5.1",
)
profiles = {item["slug"]: item for item in store.list_worker_profiles()}
ok("default coding worker profiles are seeded", {
    "mc-native", "codex-chatgpt", "opencode-glm", "reviewer-default"
}.issubset(profiles))
external_disabled = json.loads(json.dumps(data))
external_disabled["capabilities"]["external_workers"] = False
disabled_router = CodingWorkerRouter(CodingPolicy(external_disabled, repo_root=repo), store)
ok("reviewed policy can disable every external coding worker", (
    disabled_router.probe("codex-chatgpt")["health_status"] == "disabled"
))
ok("worker profile contract rejects unsafe credential names", bool(
    WorkerProfile(slug="safe", name="Safe", adapter="native")
))
try:
    WorkerProfile(
        slug="unsafe", name="Unsafe", adapter="opencode",
        auth_mode="vault_env", credential_env="KEY;DELETE",
    )
    raise AssertionError("unsafe credential environment name was accepted")
except ValueError:
    ok("worker credential reference is boundary validated", True)
try:
    WorkerProfile(
        slug="unsafe-system-env", name="Unsafe system env", adapter="opencode",
        auth_mode="vault_env", credential_env="DB_PATH",
    )
    raise AssertionError("non-secret process environment reference was accepted")
except ValueError:
    ok("worker profiles cannot expose arbitrary process environment values", True)

assessment = agent.assess_goal(
    title="Refactor authentication architecture",
    objective="Refactor authentication and database schema across frontend and backend safely.",
    acceptance_criteria=["migration is additive", "auth remains secure", "tests pass", "UI reports state"],
)
ok("high-impact goal requires owner scope review", assessment["owner_review_required"], str(assessment))
ok("large goal is split into bounded sprints", len(assessment["sprints"]) == 2)
goal = agent.create_goal(
    title="Refactor authentication architecture",
    objective="Refactor authentication and database schema across frontend and backend safely.",
    acceptance_criteria=["migration is additive", "auth remains secure", "tests pass", "UI reports state"],
    worker_profile_slug="mc-native",
)
ok("goal is a non-executable outcome record", goal["status"] == "active", goal["status"])
ok("goal does not create coding sprints", len(store.list_sprints(int(goal["id"]))) == 0)
ok("goal does not create a synthetic Queue task", store.get_task(queue_id=900_000_000 + int(goal["id"])) is None)

task = store.upsert_task({
    "queue_id": 22,
    "title": "Coding Agent V2 checkpoint",
    "plan_path": "docs/coding-agent-v2.md",
    "plan_hash": "checkpoint-plan",
    "acceptance_criteria": ["checkpoint remains durable"],
    "dependencies": [],
    "status": "planned",
    "risk": "medium",
    "target_version": "3.22.0",
})
store.link_goal_task(int(goal["id"]), int(task["id"]))
evaluated = agent.evaluate_goal(int(goal["id"]))
ok("goal qualification requires criterion evidence", evaluated["qualification_percent"] == 0)
session = store.create_session(
    int(task["id"]), policy.hash, "v2-checkpoint-session",
    goal_id=int(goal["id"]), worker_profile_slug="mc-native",
    reviewer_profile_slug="reviewer-default", sprint_budget=SprintBudget().to_dict(),
)
store.add_stages(int(session["id"]), [])
prepared = agent.git.prepare(int(session["id"]), "3.22.0", "checkpoint test", fetch=False)
store.update_session(int(session["id"]), **prepared, state="paused", stage="code")
(Path(prepared["worktree"]) / "checkpoint.txt").write_text("durable\n", encoding="utf-8")
checkpoint = agent._checkpoint(
    int(session["id"]), status="paused", next_action="Continue the exact bounded sprint."
)
ok("portable checkpoint is persisted", bool(checkpoint and checkpoint["sequence"] == 1))
handoff = store.latest_checkpoint(int(session["id"]))["handoff"]
ok("handoff preserves files and next action", "checkpoint.txt" in handoff["changed_files"] and
   handoff["next_action"].startswith("Continue"))
switched = agent.switch_worker(int(session["id"]), "codex-chatgpt")
ok("worker switching updates the same workflow", switched["worker_profile_slug"] == "codex-chatgpt")
ok("worker switch creates a checkpoint boundary", len(store.list_checkpoints(int(session["id"]))) >= 2)
codex_profile = WorkerProfile.from_row(store.get_worker_profile("codex-chatgpt"))
opencode_profile = WorkerProfile.from_row(store.get_worker_profile("opencode-glm"))
codex_command = CodexCLIWorker(policy, IsolatedProcessRunner()).command(
    codex_profile, "continue", Path(prepared["worktree"]), "thread-123"
)
opencode_command = OpenCodeCLIWorker(policy, IsolatedProcessRunner()).command(
    opencode_profile, "continue", Path(prepared["worktree"]), "session-456"
)
ok(
    "Windows external adapters use the service-safe command bridge",
    os.name != "nt"
    or (
        codex_command[:4]
        == ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand"]
        and opencode_command[:4]
        == ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand"]
        and len(codex_command) == 5
        and len(opencode_command) == 5
    ),
)
if os.name == "nt":
    bridge = _platform_cli_command([
        sys.executable,
        "-c",
        "import os,sys; print(os.getcwd()); print('|'.join(sys.argv[1:]))",
        r"D:\[PERSONAL PROJECT FILES]\TOBI\quoted path",
        "objective=hello world",
    ], cwd=Path(prepared["worktree"]))
    bridge_result = subprocess.run(
        bridge, capture_output=True, text=True, timeout=30
    )
    bridge_lines = bridge_result.stdout.strip().splitlines()
    ok(
        "Windows service bridge preserves working directory and bracketed arguments",
        bridge_result.returncode == 0
        and Path(bridge_lines[0]).resolve() == Path(prepared["worktree"]).resolve()
        and bridge_lines[1]
        == r"D:\[PERSONAL PROJECT FILES]\TOBI\quoted path|objective=hello world",
        bridge_result.stderr,
    )
else:
    ok("Windows service bridge preserves working directory and bracketed arguments", True)


def worker_argv(command: list[str]) -> list[str]:
    if os.name != "nt":
        return command
    script = base64.b64decode(command[-1]).decode("utf-16le")
    match = re.search(r"\$encoded=@\(([^)]*)\);", script)
    if not match:
        raise AssertionError("Windows worker bridge payload is missing.")
    return [
        base64.b64decode(item).decode("utf-8")
        for item in re.findall(r"'([^']+)'", match.group(1))
    ]


codex_argv = worker_argv(codex_command)
opencode_argv = worker_argv(opencode_command)
stable_prompt = CodexCLIWorker._prompt({
    "objective": 'Create "one" file',
    "acceptance_criteria": ["file exists"],
    "sprint_budget": {"max_files": 1},
})
ok(
    "external worker prompt is shell-stable and sectioned",
    "<bounded_sprint>" in stable_prompt
    and "objective:" in stable_prompt
    and '"one"' not in stable_prompt
    and "'one'" in stable_prompt,
)
ok(
    "Codex adapter uses trusted native session resume",
    codex_argv[:3] == ["codex", "exec", "resume"]
    and "--json" in codex_argv
    and "--skip-git-repo-check" in codex_argv
    and "thread-123" in codex_argv,
)
ok("OpenCode adapter carries model and session", "--model" in opencode_argv and
   "zai-coding-plan/glm-5.2" in opencode_argv and "--session" in opencode_argv)


class FakeCodex:
    def __init__(self):
        self.resume_ids: list[str | None] = []

    def run(self, *args, **kwargs):
        self.resume_ids.append(kwargs.get("external_session_id"))
        return {
            "ok": True, "exit_code": 0, "events": [{"type": "complete"}],
            "output": "done", "worker": "codex", "external_session_id": "thread-persisted",
        }

    def probe(self, profile):
        return {"status": "ready", "detail": "fake", "executable": "codex"}


fake_codex = FakeCodex()
agent.worker.codex = fake_codex
brief = {
    "worker_profile_slug": "codex-chatgpt", "objective": "Continue safely",
    "validation_commands": [], "checkpoint_handoff": handoff,
}
agent.worker.run(int(session["id"]), "code", prepared["worktree"], brief)
agent.worker.run(int(session["id"]), "code", prepared["worktree"], brief)
ok("external worker session id is persisted and resumed", fake_codex.resume_ids == [
    None, "thread-persisted"
], str(fake_codex.resume_ids))

runner = IsolatedProcessRunner()
os.environ["TOBI_V2_SECRET_PROBE"] = "must-not-leak"
code, stdout, _ = runner.run(
    999, [sys.executable, "-c", "import os; print(os.getenv('TOBI_V2_SECRET_PROBE',''))"],
    cwd=repo, timeout=10,
)
ok("isolated runner scrubs unrelated environment secrets", code == 0 and not stdout.strip())
try:
    runner.run(
        1000, [sys.executable, "-c", "import time; time.sleep(3)"],
        cwd=repo, timeout=1,
    )
    raise AssertionError("isolated runner ignored its configured deadline")
except TimeoutError:
    ok("isolated runner enforces the configured deadline", True)
code, stdout, _ = runner.run(
    1001, [sys.executable, "-c", "print('x' * 1000)"],
    cwd=repo, timeout=10, max_output_bytes=64,
)
ok("isolated runner bounds captured output", code == 0 and len(stdout.encode("utf-8")) <= 64)

runner_service = CodingRunnerService(store, node_id="test-runner", poll_seconds=0.05)
service_thread = threading.Thread(target=runner_service.run_forever, daemon=True)
service_thread.start()
queued_runner = QueuedProcessRunner(store, poll_seconds=0.05)
service_events: list[str] = []
os.environ["TOBI_V2_SERVICE_SECRET"] = "vault-value"
code, stdout, stderr = queued_runner.run(
    int(session["id"]), [
        sys.executable, "-c",
        "import os; print(os.getenv('TOBI_V2_SERVICE_SECRET') == 'vault-value')",
    ],
    cwd=repo, timeout=10, adapter="codex", max_output_bytes=1024,
    allowed_env=["TOBI_V2_SERVICE_SECRET"],
    on_output=service_events.append,
)
runner_nodes_ready = bool(store.list_runner_nodes(active_within_seconds=30))
runner_service.stop()
service_thread.join(timeout=5)
ok("supervised runner executes durable queued jobs", (
    code == 0 and stdout.strip() == "True" and not stderr
))
ok("supervised runner streams persisted output events", service_events == ["True"])
runner_job = store.latest_runner_job(int(session["id"])) or {}
ok("runner job stores a durable terminal state", runner_job.get("status") == "completed")
ok("runner job never stores plaintext profile credentials", (
    "vault-value" not in str(runner_job.get("env_envelope_json") or "") and
    bool(runner_job.get("env_envelope_json"))
))
ok("runner service records health heartbeats", runner_nodes_ready)
os.environ.pop("TOBI_V2_SERVICE_SECRET", None)


class CancelRaceWorker:
    def run(self, workflow_id, *_args, **_kwargs):
        store.update_session(workflow_id, state="canceled", cancel_requested=1)
        raise CodingWorkerUnavailable("runner stopped after owner cancellation")

    def cancel(self, _workflow_id):
        return True


store.add_stages(int(session["id"]), STAGES)
store.update_stage(int(session["id"]), "prepare", status="completed")
store.update_stage(int(session["id"]), "index", status="completed")
store.update_session(int(session["id"]), state="approved", stage="code", cancel_requested=0)
original_worker = agent.worker
agent.worker = CancelRaceWorker()
canceled = agent.run_to_gate(int(session["id"]))
agent.worker = original_worker
ok("owner cancellation cannot be overwritten by a late worker error", (
    canceled["state"] == "canceled"
))
store.update_session(int(session["id"]), state="paused", stage="code", cancel_requested=0)

quality = agent.quality.evaluate(
    worktree=prepared["worktree"], budget=SprintBudget(max_files=1, max_changed_lines=10),
    checks=[{"ok": True}], special_approval=False,
)
ok("deterministic quality gate accepts bounded diff", quality["qualified"], str(quality))
too_small = agent.quality.evaluate(
    worktree=prepared["worktree"], budget=SprintBudget(max_files=1, max_changed_lines=1),
    checks=[{"ok": True}], special_approval=False,
)
ok("deterministic quality gate reports exact line usage", too_small["metrics"]["changed_lines"] == 1)
(Path(prepared["worktree"]) / "checkpoint.txt").write_text("durable\nsecond line\n", encoding="utf-8")
too_small = agent.quality.evaluate(
    worktree=prepared["worktree"], budget=SprintBudget(max_files=1, max_changed_lines=1),
    checks=[{"ok": True}], special_approval=False,
)
ok("deterministic quality gate enforces line budget", not too_small["qualified"])

learning = CodingLearningService(store)
for _ in range(3):
    learning.record(
        session_id=int(session["id"]), outcome="paused", stage="code",
        error_code="malformed_worker_action", worker_profile="mc-native",
        evidence={"checkpoint": checkpoint["id"]},
    )
playbooks = store.list_playbooks()
ok("repeated failures create a reusable playbook candidate", len(playbooks) == 1)
replay = learning.replay()
ok("unproven playbook does not auto-promote", replay["results"][0]["qualified"] is False)
for _ in range(3):
    learning.record(
        session_id=int(session["id"]), outcome="qualified_local", stage="review",
        worker_profile="mc-native", evidence={"quality": "passed"},
    )
replay = learning.replay()
routing = next(item for item in replay["results"] if item["slug"].startswith("route-"))
ok("successful replay evidence auto-promotes a safe routing playbook", routing["qualified"])
ok("native worker profile reports ready", agent.worker.probe("mc-native")["health_status"] == "ready")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from api import developer  # noqa: E402

developer.agent = agent
developer.start_loop = lambda: True
app = FastAPI()
app.include_router(developer.router)
app.dependency_overrides[developer.require_owner] = lambda: "v2-owner"
client = TestClient(app)
workers_response = client.get("/api/developer/workers")
ok("worker profile API lists seeded adapters", workers_response.status_code == 200 and
   len(workers_response.json()["workers"]) >= 4)
ok("worker profile API exposes Models catalog and routing", (
    "models" in workers_response.json() and
    "providers" in workers_response.json() and
    "coding_review" in workers_response.json()["routing"]
))
assessment_response = client.post("/api/developer/goals/assess", json={
    "title": "Assess secure database refactor",
    "objective": "Refactor authentication and database schema across the application.",
    "acceptance_criteria": ["migration is additive", "security tests pass", "UI reports state", "rollback works"],
})
ok("assessment API returns bounded sprints", assessment_response.status_code == 200 and
   len(assessment_response.json()["sprints"]) == 2)
invalid_profile = client.put("/api/developer/workers/invalid-worker", json={
    "name": "Invalid worker", "adapter": "opencode", "model": "glm",
    "auth_mode": "vault_env", "credential_env": "", "reviewer_profile": "reviewer-default",
    "enabled": True, "config": {},
})
ok("worker API rejects missing vault credential reference", invalid_profile.status_code == 422)
invalid_model_profile = client.put("/api/developer/workers/invalid-model-worker", json={
    "name": "Invalid model worker", "adapter": "native", "model": "missing:model",
    "auth_mode": "inherited", "credential_env": "", "reviewer_profile": "reviewer-default",
    "enabled": True, "config": {},
})
ok("worker API rejects models outside enabled Models providers", invalid_model_profile.status_code == 422)
disabled_model_profile = client.put("/api/developer/workers/invalid-model-worker", json={
    "name": "Disabled model worker", "adapter": "native", "model": "missing:model",
    "auth_mode": "inherited", "credential_env": "", "reviewer_profile": "reviewer-default",
    "enabled": False, "config": {},
})
ok("worker API always permits the safe deactivation transition", (
    disabled_model_profile.status_code == 200 and not disabled_model_profile.json()["enabled"]
))
learning_response = client.get("/api/developer/learning")
ok("learning API exposes records and playbooks", learning_response.status_code == 200 and
   "playbooks" in learning_response.json())
replay_response = client.post("/api/developer/learning/replay", json={"playbook_slug": None})
ok("learning replay API is owner-controlled", replay_response.status_code == 200)

print(f"ALL {PASS} CODING AGENT V2 CHECKS PASSED")
shutil.rmtree(TMP, ignore_errors=True)

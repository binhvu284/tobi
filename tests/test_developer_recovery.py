"""Focused recovery tests for stale workflows and durable goal commands."""
from __future__ import annotations

import json
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TEST_ROOT = ROOT / ".tobi" / "test-runs"
TEST_ROOT.mkdir(parents=True, exist_ok=True)
TMP = Path(tempfile.mkdtemp(prefix="developer_recovery_", dir=TEST_ROOT))
os.environ["DB_PATH"] = str(TMP / "recovery.db")

from core.coding_agent import CodingAgent, STAGES  # noqa: E402
from core.coding_loop import CodingLoopService  # noqa: E402
from core.coding_policy import CodingPolicy  # noqa: E402
from core.development_store import DevelopmentStore  # noqa: E402


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=str(repo),
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode:
        raise AssertionError(result.stderr or result.stdout)
    return result.stdout.strip()


def check(name: str, condition: bool, detail: str = "") -> None:
    if not condition:
        raise AssertionError(f"{name}: {detail}")
    print(f"PASS {name}")


try:
    repo = TMP / "repo"
    origin = TMP / "origin.git"
    subprocess.run(["git", "init", "--bare", str(origin)], check=True, capture_output=True)
    repo.mkdir()
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.email", "recovery@tobi.local")
    git(repo, "config", "user.name", "TOBI Recovery Test")
    (repo / "README.md").write_text("# recovery\n", encoding="utf-8")
    git(repo, "add", "README.md")
    git(repo, "commit", "-m", "initial")
    git(repo, "remote", "add", "origin", str(origin))
    git(repo, "push", "-u", "origin", "main")

    data = json.loads((ROOT / "config" / "coding_policy.v1.json").read_text(encoding="utf-8"))
    data["repository"]["allowed_repository"] = ""
    data["repository"]["allowed_remote_suffix"] = origin.name
    # Pinned: recovery is about resuming a run, not about delivery. Preflight blocks an
    # enabled github capability with no Coding App, which would fail this for another reason.
    data["capabilities"] = {**data["capabilities"],
                            "github": False, "merge": False, "deploy": False}
    policy = CodingPolicy(data, repo_root=repo)
    store = DevelopmentStore(TMP / "recovery.db")
    agent = CodingAgent(policy=policy, store=store)
    agent.start_background = lambda workflow_id: agent.get_workflow(workflow_id)  # type: ignore[method-assign]

    class ReadyWorker:
        def probe(self, slug, active=False):
            return {"slug": slug, "name": slug, "adapter": "native", "model": "test",
                    "health_status": "ready", "health_detail": "ready"}

    class OneSprintAssessment:
        def to_dict(self):
            return {"route": "direct", "risk": "medium", "score": 90, "sprints": [{"sequence": 1}]}

    class OneSprintAssessor:
        def assess(self, **kwargs):
            return OneSprintAssessment()

    agent.worker = ReadyWorker()
    agent.completion.worker = agent.worker
    agent.completion.assessor = OneSprintAssessor()
    (repo / "docs").mkdir()
    plan_path = repo / "docs" / "theme.md"
    plan_path.write_text("# Theme recovery\n\n- Must remain durable.\n", encoding="utf-8")
    plan_hash = hashlib.sha256(plan_path.read_bytes()).hexdigest()

    task = store.upsert_task({
        "queue_id": 13,
        "title": "Theme v2 recovery",
        "plan_path": "docs/theme.md",
        "plan_hash": plan_hash,
        "acceptance_criteria": ["replacement workflow is durable"],
        "dependencies": [],
        "status": "approved",
        "risk": "medium",
        "target_version": "3.13.0",
    })
    stale = store.create_session(
        int(task["id"]),
        "stale-policy",
        "stale-queue-workflow",
        plan_hash_snapshot=plan_hash,
        criteria_snapshot=["replacement workflow is durable"],
    )
    stale_id = int(stale["id"])
    store.add_stages(stale_id, STAGES)
    store.update_session(
        stale_id,
        state="paused",
        stage="prepare",
        progress=5,
        blocker="Policy changed.",
        error_code="policy_changed",
    )

    replacement = agent.command(stale_id, "retry")
    replacement_id = int(replacement["id"])
    check("stale retry preserves the same workflow", replacement_id == stale_id)
    check("same run uses the active policy", replacement["policy_hash"] == policy.hash)
    check("same run snapshots the current plan", replacement["plan_hash_snapshot"] == plan_hash)
    check("same-run restart is persisted", any(
        event["event_type"] == "workflow_restarted"
        and event["payload"]["same_run"] is True
        for event in store.list_events(stale_id)
    ))

    store.update_session(replacement_id, state="canceled", completed_at="test")
    goal = agent.create_goal(
        title="Recover continuous loop",
        objective="Verify a stale goal workflow restarts without losing its durable sprint.",
        acceptance_criteria=["the goal points to a new workflow"],
    )
    goal_id = int(goal["id"])
    check("Goal recovery never creates a synthetic task", store.get_task(queue_id=900_000_000 + goal_id) is None)
    evaluated = CodingLoopService(agent).command(goal_id, "evaluate")
    check("Goal command re-evaluates evidence without running", evaluated["status"] == "active")

    command = store.begin_command("failed-command-key", "workflow", stale_id, "retry")
    check("new command is claimed", command["_claimed"])
    store.fail_command("failed-command-key", {"type": "RuntimeError", "message": "expected failure"})
    failed = store.begin_command("failed-command-key", "workflow", stale_id, "retry")
    check("failed command is terminal, not stuck running", (
        not failed["_claimed"] and failed["status"] == "failed"
    ))

    stale_command = store.begin_command("abandoned-command-key", "workflow", stale_id, "retry")
    check("abandoned command starts running", stale_command["status"] == "running")
    with store.connect() as conn:
        conn.execute(
            "UPDATE development_commands SET created_at=? WHERE idempotency_key=?",
            ("2000-01-01T00:00:00+00:00", "abandoned-command-key"),
        )
        conn.commit()
    check("startup reconciliation terminalizes abandoned commands", store.fail_stale_commands() == 1)
    reconciled_command = store.begin_command(
        "abandoned-command-key", "workflow", stale_id, "retry"
    )
    check("reconciled command reports a durable failure", (
        not reconciled_command["_claimed"] and reconciled_command["status"] == "failed"
    ))
finally:
    shutil.rmtree(TMP, ignore_errors=True)

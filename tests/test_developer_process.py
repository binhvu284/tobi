"""Focused Process UI backend contracts: archive visibility and safe auto-queue selection."""
from __future__ import annotations

import tempfile
import threading
import subprocess
import json
from pathlib import Path
from types import SimpleNamespace

from core import owner_flags
from core import coding_review as coding_review_module
from core.coding_agent import CodingAgent
from core.coding_review import CodingReviewer
from core.development_store import DevelopmentStore
from core.git_workspace import GitWorkspaceManager


PASS = 0


def ok(name: str, condition: bool) -> None:
    global PASS
    if not condition:
        raise AssertionError(name)
    PASS += 1
    print(f"PASS {name}")


test_root = Path(__file__).resolve().parents[1] / ".tobi" / "test-runs"
test_root.mkdir(parents=True, exist_ok=True)
root = Path(tempfile.mkdtemp(prefix="developer_process_", dir=test_root))
store = DevelopmentStore(root / "process.db")
task = store.upsert_task({
    "queue_id": 901,
    "title": "Process contract",
    "plan_path": "docs/feature-idea-queue/process.md",
    "plan_hash": "a" * 64,
    "acceptance_criteria": ["Process must preserve durable state"],
    "dependencies": [],
    "status": "planned",
    "risk": "medium",
})
session = store.create_session(int(task["id"]), "policy-hash", "process-command-test")
store.update_session(int(session["id"]), state="canceled", completed_at="2026-07-18T00:00:00+00:00")

agent = CodingAgent.__new__(CodingAgent)
agent.store = store
# get_workflow reports progress against the gates the policy permits, so even this partial
# agent needs a capability map. An empty one means the sandbox set: the seven local gates.
agent.policy = SimpleNamespace(data={"capabilities": {}})
agent._event = CodingAgent._event.__get__(agent, CodingAgent)
archived = CodingAgent.command(agent, int(session["id"]), "remove")
ok("remove archives a terminal Process workflow", bool(archived["archived_at"]))
ok("archived workflow remains directly recoverable", store.get_session(int(session["id"])) is not None)
ok("archived workflow leaves the visible Process history", not store.list_sessions())

merged_task = store.upsert_task({
    "queue_id": 904,
    "title": "Merged Process contract",
    "plan_path": "docs/feature-idea-queue/merged-process.md",
    "plan_hash": "b" * 64,
    "acceptance_criteria": ["Merged Process can be archived"],
    "dependencies": [],
    "status": "completed",
    "risk": "low",
})
merged_session = store.create_session(
    int(merged_task["id"]), "policy-hash", "merged-process-command-test"
)
store.update_session(
    int(merged_session["id"]),
    state="merged",
    stage="merge_deploy",
    completed_at="2026-07-28T00:00:00+00:00",
)
archived_merged = CodingAgent.command(agent, int(merged_session["id"]), "remove")
ok("remove archives a merged Process workflow", bool(archived_merged["archived_at"]))

auto = CodingAgent.__new__(CodingAgent)
auto._auto_queue_lock = threading.Lock()
auto.list_workflows = lambda limit=200: []
auto.sync = lambda: [
    {"queue_id": 903, "status": "planned", "dependencies_json": "[902]"},
    {"queue_id": 902, "status": "planned", "dependencies_json": "[]"},
]
auto.store = type("Store", (), {"get_task": lambda self, queue_id: {"status": "planned"}})()
started: list[int] = []
auto.preflight = lambda queue_id, **kwargs: {"ready": True, "readiness_id": queue_id, "blockers": []}
auto.create_workflow = lambda queue_id, **kwargs: {"id": queue_id, "queue_id": queue_id}
auto._event = lambda workflow_id, event_type, payload: None
auto.start_background = lambda workflow_id: started.append(workflow_id) or {"id": workflow_id}
original_get_bool = owner_flags.get_bool
owner_flags.get_bool = lambda key, default=False: True
try:
    result = CodingAgent.start_next_queued(auto)
finally:
    owner_flags.get_bool = original_get_bool
ok("auto queue skips a task with incomplete dependencies", result == {"id": 902})
ok("auto queue starts exactly one eligible task", started == [902])

auto.list_workflows = lambda limit=200: [{"state": "failed"}]
owner_flags.get_bool = lambda key, default=False: True
try:
    blocked = CodingAgent.start_next_queued(auto)
finally:
    owner_flags.get_bool = original_get_bool
ok("auto queue never skips over a failed Process workflow", blocked is None)


class GitPolicy:
    repo_root = root
    worktree_root = root

    @staticmethod
    def repo_path(name):
        return root

    @staticmethod
    def assert_command(argv, allow_network=False):
        return None


repo = root / "restore-worktree"
repo.mkdir()
subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
subprocess.run(["git", "config", "user.email", "process@test.local"], cwd=repo, check=True)
subprocess.run(["git", "config", "user.name", "Process Test"], cwd=repo, check=True)
(repo / "tracked.txt").write_text("original\n", encoding="utf-8")
subprocess.run(["git", "add", "tracked.txt"], cwd=repo, check=True)
subprocess.run(["git", "commit", "-m", "initial"], cwd=repo, check=True, capture_output=True)
(repo / "tracked.txt").write_text("changed\n", encoding="utf-8")
(repo / "untracked.txt").write_text("temporary\n", encoding="utf-8")
GitWorkspaceManager(GitPolicy()).restore_paths(repo, ["tracked.txt", "untracked.txt"])
ok("rejected tracked paths restore their committed content", (repo / "tracked.txt").read_text(encoding="utf-8") == "original\n")
ok("rejected untracked paths are removed from the isolated worktree", not (repo / "untracked.txt").exists())

marker = repo / "fallback_recovery_test.txt"
marker.write_text("FALLBACK_TEST=passed\n", encoding="utf-8")
manager = GitWorkspaceManager(GitPolicy())
patch = manager.diff_patch(repo)
ok("new files use a valid unified diff hunk", all(part in patch for part in (
    "diff --git a/fallback_recovery_test.txt b/fallback_recovery_test.txt",
    "--- /dev/null",
    "+++ b/fallback_recovery_test.txt",
    "@@ -0,0 +1 @@",
    "+FALLBACK_TEST=passed",
)))
file_evidence = manager.changed_file_evidence(repo, ["fallback_recovery_test.txt"])
ok("review evidence includes resulting file content", bool(
    file_evidence
    and file_evidence[0]["exists"]
    and file_evidence[0]["text_preview"].strip() == "FALLBACK_TEST=passed"
    and len(file_evidence[0]["sha256"]) == 64
))

captured_review: dict = {}


class FakeReviewClient:
    def complete(self, messages, **_kwargs):
        captured_review.update(json.loads(messages[0]["content"]))
        return json.dumps({
            "qualified": True,
            "score": 1.0,
            "unmet": [],
            "risks": [],
            "summary": "Criterion is evidenced.",
        })


from core import model_router  # noqa: E402
original_review_problem = coding_review_module.reviewer_model_problem
original_get_llm = model_router.get_llm
coding_review_module.reviewer_model_problem = lambda _model=None: ""
model_router.get_llm = lambda *_args, **_kwargs: FakeReviewClient()
try:
    review = CodingReviewer().review(
        objective="Create a fallback marker.",
        acceptance_criteria=["The file contains FALLBACK_TEST=passed"],
        checks=[{"argv": ["test"], "ok": True, "exit_code": 0}],
        patch=patch,
        changed_files=["fallback_recovery_test.txt"],
        quality_report={"qualified": True},
        file_evidence=file_evidence,
    )
finally:
    coding_review_module.reviewer_model_problem = original_review_problem
    model_router.get_llm = original_get_llm
ok("independent reviewer receives post-change file evidence", bool(
    review["qualified"]
    and captured_review["changed_file_evidence"][0]["text_preview"].strip()
        == "FALLBACK_TEST=passed"
))

print(f"{PASS} Developer Process checks passed")

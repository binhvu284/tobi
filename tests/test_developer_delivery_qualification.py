"""Final #22 delivery, evidence, and acceptance-control regressions."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from core.coding_agent import CodingAgent
from core.coding_states import STAGES, workflow_progress
from core.development_store import DevelopmentStore
from core.git_workspace import GitWorkspaceManager
from core.github_coding import GitHubCodingService


def test_zero_github_status_contexts_are_not_pending() -> None:
    service = GitHubCodingService.__new__(GitHubCodingService)
    service.repository = "owner/repository"

    def request(_method: str, path: str, **_kwargs):
        if path.endswith("/pulls/7"):
            return {
                "number": 7,
                "html_url": "https://example.test/pr/7",
                "state": "open",
                "draft": False,
                "mergeable": True,
                "mergeable_state": "clean",
                "head": {"sha": "head"},
                "base": {"sha": "base"},
                "merged": False,
            }
        if path.endswith("/check-runs"):
            return {"check_runs": []}
        if path.endswith("/status"):
            return {"state": "pending", "statuses": []}
        raise AssertionError(path)

    service._request = request
    readiness = service.merge_readiness(7)

    assert readiness["ready"] is True
    assert readiness["pending_checks"] == []
    assert readiness["failed_checks"] == []


def test_completed_external_gate_never_overflows_progress() -> None:
    capabilities = {"github": True, "merge": False, "deploy": False}
    statuses = {
        "prepare": "completed",
        "index": "completed",
        "code": "completed",
        "validate": "completed",
        "review": "completed",
        "commit": "completed",
        "scan": "completed",
        "push": "completed",
        "pull_request": "completed",
        "merge_deploy": "completed",
    }

    assert workflow_progress(statuses, capabilities, delivered=True) == 100
    assert workflow_progress(statuses, capabilities, delivered=False) <= 99


def test_stage_attempt_and_acceptance_fault_reconciliation(tmp_path: Path) -> None:
    store = DevelopmentStore(tmp_path / "developer.db")
    task = store.upsert_task({
        "queue_id": 2201,
        "title": "Qualification fixture",
        "plan_path": "docs/qualification.md",
        "plan_hash": "a" * 64,
        "acceptance_criteria": ["evidence remains durable"],
        "dependencies": [],
        "status": "planned",
        "risk": "low",
    })
    session = store.create_session(int(task["id"]), "policy", "qualification-session")
    session_id = int(session["id"])
    store.add_stages(session_id, STAGES)
    store.update_stage(session_id, "prepare", status="completed")
    store.start_stage_attempt(session_id, "prepare", 1, "deepseek-harness")

    assert store.reconcile_stage_attempts(session_id) == 1
    with store.connect() as conn:
        attempt = conn.execute(
            "SELECT * FROM coding_stage_attempts WHERE session_id=? AND stage_id='prepare'",
            (session_id,),
        ).fetchone()
    assert attempt["status"] == "completed"
    assert attempt["completed_at"]

    first = store.arm_acceptance_fault(session_id, "worker_failure")
    consumed = store.consume_acceptance_fault(session_id, "worker_failure")
    assert consumed and consumed["id"] == first["id"]
    assert store.consume_acceptance_fault(session_id, "worker_failure") is None


def test_committed_diff_uses_base_to_head_range(tmp_path: Path) -> None:
    manager = GitWorkspaceManager.__new__(GitWorkspaceManager)
    manager._assert_worktree = lambda _worktree: tmp_path
    calls: list[tuple[str, ...]] = []

    def git(*args: str, **_kwargs) -> str:
        calls.append(args)
        if args[:2] == ("diff", "--name-status"):
            return "M\ttests/test_task_classifier.py"
        if args[:2] == ("diff", "--stat"):
            return " tests/test_task_classifier.py | 4 ++++"
        if args[:2] == ("rev-parse", "head"):
            return "head"
        if args[:2] == ("rev-parse", "base"):
            return "base"
        raise AssertionError(args)

    manager.git = git
    summary = manager.diff_summary(tmp_path, base_ref="base", head_ref="head")

    assert summary["files"] == [{"status": "M", "path": "tests/test_task_classifier.py"}]
    assert ("diff", "--name-status", "base..head") in calls


def test_merged_finalization_is_idempotent(tmp_path: Path) -> None:
    store = DevelopmentStore(tmp_path / "developer.db")
    queue_item = {
        "queue_id": 2202,
        "title": "Merged fixture",
        "plan_path": "docs/merged.md",
        "plan_hash": "b" * 64,
        "acceptance_criteria": ["merge is terminal success"],
        "dependencies": [],
        "status": "approved",
        "risk": "low",
    }
    task = store.upsert_task(queue_item)
    session = store.create_session(int(task["id"]), "policy", "merged-session")
    session_id = int(session["id"])
    store.update_session(session_id, state="paused", stage="merge_deploy")

    events: list[str] = []
    scorecards: list[int] = []
    auto_starts: list[bool] = []
    agent = CodingAgent.__new__(CodingAgent)
    agent.store = store
    agent._sync_progress = lambda _session_id: None
    agent._event = lambda _session_id, event_type, _payload, **_kwargs: events.append(event_type)
    agent._checkpoint = lambda *_args, **_kwargs: None
    agent._record_learning = lambda *_args, **_kwargs: None
    agent.completion = SimpleNamespace(
        evaluate_goal=lambda _goal_id: None,
        build_scorecard=lambda value: scorecards.append(value),
    )
    agent.start_next_queued = lambda: auto_starts.append(True)
    agent.get_workflow = lambda value: store.get_session(value)

    first = CodingAgent._finalize_merged(agent, session_id, "merge-sha")
    second = CodingAgent._finalize_merged(agent, session_id, "merge-sha")

    assert first["state"] == second["state"] == "merged"
    completed_task = store.get_task(task_id=int(task["id"]))
    assert completed_task["owner_state"] == "Done"
    assert completed_task["status_override"] == 1
    store.upsert_task({**queue_item, "status": "planned"})
    assert store.get_task(task_id=int(task["id"]))["status"] == "completed"
    assert events == ["workflow_merged"]
    assert scorecards == [session_id]
    assert auto_starts == [True]

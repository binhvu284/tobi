"""Coding Agent V2 completion contracts that are not covered by legacy suites."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from core import coding_completion, coding_queue, coding_queue_authoring
from core.coding_agent import CodingAgent
from core.coding_completion import CodingCompletionService
from core.coding_policy import CodingPolicy
from core.development_store import DevelopmentStore


class _Assessment:
    def to_dict(self) -> dict:
        return {"route": "direct", "risk": "low", "score": 90, "sprints": [{"sequence": 1}]}


class _Assessor:
    def assess(self, **_kwargs) -> _Assessment:
        return _Assessment()


class _Worker:
    def probe(self, slug: str, active: bool = False) -> dict:
        return {
            "slug": slug,
            "name": slug,
            "adapter": (
                "model_review" if slug == "reviewer-default"
                else "deepseek" if slug == "deepseek-harness"
                else "codex" if slug == "codex-chatgpt"
                else "native"
            ),
            "model": "test-model",
            "health_status": "ready",
            "health_detail": "available",
            "active_probe": active,
        }


def _policy(
    root: Path,
    qualified_adapters: list[str] | None = None,
) -> CodingPolicy:
    source = Path(__file__).resolve().parents[1] / "config" / "coding_policy.v1.json"
    data = json.loads(source.read_text(encoding="utf-8"))
    data["repository"]["allowed_repository"] = ""
    data["repository"]["allowed_remote_suffix"] = ""
    data["commands"]["mandatory_checks"] = [["python", "-m", "compileall", "-q", "core"]]
    # Pinned: these contracts are not about delivery, so they must not start failing when the
    # owner enables a capability. Preflight blocks an enabled github with no Coding App.
    data["capabilities"] = {**data["capabilities"],
                            "github": False, "merge": False, "deploy": False}
    data["workers"]["qualified_implementer_adapters"] = (
        qualified_adapters or ["native", "deepseek", "codex", "opencode"]
    )
    return CodingPolicy(data, repo_root=root)


def _task(store: DevelopmentStore, root: Path, *, queue_id: int = 41) -> dict:
    plan = root / "WORK_PLAN.md"
    plan.write_text(
        "# Work\n\n## Acceptance Criteria\n- Must preserve the same run identity.\n",
        encoding="utf-8",
    )
    return store.upsert_task({
        "queue_id": queue_id,
        "title": "Durable work",
        "plan_path": plan.name,
        "plan_hash": hashlib.sha256(plan.read_bytes()).hexdigest(),
        "acceptance_criteria": ["preserve the same run identity"],
        "dependencies": [],
        "status": "planned",
        "risk": "low",
    })


def test_preflight_blocks_disabled_agent_before_run_creation(tmp_path: Path, monkeypatch) -> None:
    store = DevelopmentStore(tmp_path / "developer.db")
    task = _task(store, tmp_path)
    with store.connect() as conn:
        conn.execute("UPDATE coding_worker_profiles SET enabled=0 WHERE slug='deepseek-harness'")
        conn.commit()
    monkeypatch.setattr(coding_completion, "REPO_ROOT", tmp_path)
    service = CodingCompletionService(
        store=store, policy=_policy(tmp_path), worker=_Worker(), assessor=_Assessor()
    )

    report = service.preflight(int(task["queue_id"]), active_probe=False)

    assert not report["ready"]
    assert "agent_disabled" in {item["code"] for item in report["blockers"]}
    assert store.list_sessions(10) == []
    assert store.get_readiness(int(report["readiness_id"]))["status"] == "blocked"


def test_preflight_locks_future_agent_and_offers_codex(tmp_path: Path, monkeypatch) -> None:
    store = DevelopmentStore(tmp_path / "developer.db")
    task = _task(store, tmp_path)
    # The task's agent is DeepSeek Harness, which this policy does not qualify.
    monkeypatch.setattr(coding_completion, "REPO_ROOT", tmp_path)
    service = CodingCompletionService(
        store=store,
        policy=_policy(tmp_path, ["codex"]),
        worker=_Worker(),
        assessor=_Assessor(),
    )

    report = service.preflight(int(task["queue_id"]), active_probe=False)

    assert not report["ready"]
    assert "agent_future_locked" in {item["code"] for item in report["blockers"]}
    assert [item["slug"] for item in report["alternatives"]] == ["codex-chatgpt"]
    assert store.list_sessions(10) == []


@pytest.mark.parametrize(
    ("queue_status", "expected_code"),
    [
        ("Blocked by #22 owner acceptance", "queue_blocked"),
        ("In progress (qualification pending)", "queue_in_progress"),
    ],
)
def test_preflight_enforces_owner_queue_lifecycle(
    tmp_path: Path, monkeypatch, queue_status: str, expected_code: str
) -> None:
    store = DevelopmentStore(tmp_path / "developer.db")
    task = _task(store, tmp_path)
    with store.connect() as conn:
        conn.execute(
            "UPDATE development_tasks SET queue_status=? WHERE id=?",
            (queue_status, int(task["id"])),
        )
        conn.commit()
    monkeypatch.setattr(coding_completion, "REPO_ROOT", tmp_path)
    service = CodingCompletionService(
        store=store, policy=_policy(tmp_path), worker=_Worker(), assessor=_Assessor()
    )

    report = service.preflight(int(task["queue_id"]), active_probe=False)

    assert not report["ready"]
    assert expected_code in {item["code"] for item in report["blockers"]}
    assert store.list_sessions(10) == []


def test_queue_projection_disables_blocked_in_progress_and_dependencies() -> None:
    agent = CodingAgent.__new__(CodingAgent)
    agent.store = type("Store", (), {"get_task": lambda _self, queue_id: None})()
    items = [
        {
            "queue_id": 22, "status": "planned", "queue_status": "In progress",
            "status_override": 0, "dependencies_json": "[]",
        },
        {
            "queue_id": 21, "status": "planned", "queue_status": "Blocked by #22",
            "status_override": 0, "dependencies_json": "[22]",
        },
        {
            "queue_id": 27, "status": "planned", "queue_status": "Ready",
            "status_override": 0, "dependencies_json": "[]",
        },
    ]

    projected = {
        item["queue_id"]: item
        for item in CodingAgent._queue_items_with_execution(agent, items)
    }

    assert projected[22]["execution_state"] == "in_progress"
    assert projected[22]["can_start"] is False
    assert projected[21]["execution_state"] == "blocked"
    assert projected[21]["can_start"] is False
    assert "Queue item #22 must be completed first." in projected[21]["start_blockers"]
    assert projected[27]["execution_state"] == "ready"
    assert projected[27]["can_start"] is True


def test_goal_qualification_requires_criterion_level_evidence(tmp_path: Path, monkeypatch) -> None:
    store = DevelopmentStore(tmp_path / "developer.db")
    task = _task(store, tmp_path)
    goal = store.create_goal(
        title="Durable recovery",
        objective="Recover coding work without repeating completed side effects.",
        acceptance_criteria=["preserve the same run identity"],
        status="active",
    )
    store.link_goal_task(int(goal["id"]), int(task["id"]))
    monkeypatch.setattr(coding_completion, "REPO_ROOT", tmp_path)
    service = CodingCompletionService(
        store=store, policy=_policy(tmp_path), worker=_Worker(), assessor=_Assessor()
    )

    unresolved = service.evaluate_goal(int(goal["id"]))
    assert unresolved["qualification_percent"] == 0
    store.add_evidence(
        task_id=int(task["id"]), goal_id=int(goal["id"]), criterion_index=0,
        kind="check", status="passed", source="pytest", payload={"test": "same_run"},
    )
    qualified = service.evaluate_goal(int(goal["id"]))
    assert qualified["qualification_percent"] == 100
    assert qualified["status"] == "qualified"


def test_queue_authoring_targets_feature_table_and_detects_conflict(tmp_path: Path, monkeypatch) -> None:
    queue_dir = tmp_path / "docs" / "feature-idea-queue"
    queue_dir.mkdir(parents=True)
    queue_path = queue_dir / "QUEUE.md"
    (queue_dir / "ONE_PLAN.md").write_text(
        "# One\n\n- Must remain readable.\n", encoding="utf-8"
    )
    queue_path.write_text(
        "# Queue\n\n"
        "| Calibration | Value | Note |\n"
        "|---|---|---|\n"
        "| Old | 1 day | Legacy |\n\n"
        "| # | Feature | Status | Solo time (full -> left) | Spec | Notes |\n"
        "|---|---------|--------|--------|------|-------|\n"
        "| 1 | **One** | Queued | 1 day -> same | [ONE_PLAN.md](ONE_PLAN.md) | Existing. |\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(coding_queue, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(coding_queue, "QUEUE_PATH", queue_path)
    monkeypatch.setattr(coding_queue_authoring, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(coding_queue_authoring, "QUEUE_PATH", queue_path)
    original_hash = coding_queue_authoring.queue_hash()

    created = coding_queue_authoring.create_queue_item(
        title="Second item",
        objective="Create a bounded canonical Queue item safely.",
        acceptance_criteria=["the feature Queue table contains the new row"],
        expected_queue_hash=original_hash,
    )

    lines = queue_path.read_text(encoding="utf-8").splitlines()
    feature_header = lines.index("| # | Feature | Status | Solo time (full -> left) | Spec | Notes |")
    assert created["queue_id"] == 2
    assert lines[feature_header + 2].startswith("| 2 | **Second item** |")
    assert lines[3] == "|---|---|---|"
    with pytest.raises(RuntimeError, match="changed outside"):
        coding_queue_authoring.create_queue_item(
            title="Stale write",
            objective="This stale write must be rejected before changing files.",
            acceptance_criteria=["no file is created"],
            expected_queue_hash=original_hash,
        )

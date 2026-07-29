"""Focused regressions for Developer stability and evidence-backed learning."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from core import coding_completion
from core.coding_agent import CodingAgent
from core.coding_completion import CodingCompletionService
from core.coding_learning import CodingLearningService
from core.coding_policy import CodingPolicy
from core.coding_states import STAGES
from core.development_store import DevelopmentStore, utc_now


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
            "adapter": "model_review" if slug == "reviewer-default" else "native",
            "model": "test-model",
            "health_status": "ready",
            "health_detail": "available",
            "active_probe": active,
        }


class _OpenPullRequest:
    repository = "owner/repository"

    @staticmethod
    def get_pr(_number: int) -> dict:
        return {
            "number": 7,
            "url": "https://example.test/pull/7",
            "head_sha": "a" * 40,
            "base_sha": "b" * 40,
            "draft": False,
            "merged": False,
            "state": "open",
            "mergeable_state": "clean",
            "merged_at": None,
            "merge_commit_sha": None,
        }

    @staticmethod
    def merge_readiness(_number: int) -> dict:
        return {
            "ready": True,
            "pending_checks": [],
            "failed_checks": [],
            "pull_request": {"mergeable_state": "clean"},
        }


def _policy(root: Path) -> CodingPolicy:
    source = Path(__file__).resolve().parents[1] / "config" / "coding_policy.v1.json"
    data = json.loads(source.read_text(encoding="utf-8"))
    data["repository"]["allowed_repository"] = ""
    data["repository"]["allowed_remote_suffix"] = ""
    data["commands"]["mandatory_checks"] = [["python", "tests/test_coding_agent.py"]]
    data["capabilities"] = {
        **data["capabilities"],
        "github": False,
        "merge": False,
        "deploy": False,
    }
    return CodingPolicy(data, repo_root=root)


def _task(store: DevelopmentStore, root: Path, queue_id: int) -> dict:
    plan = root / f"PLAN_{queue_id}.md"
    plan.write_text(
        "# Stability\n\n## Acceptance Criteria\n- Must retain deterministic evidence.\n",
        encoding="utf-8",
    )
    return store.upsert_task({
        "queue_id": queue_id,
        "title": "Stability hardening",
        "plan_path": plan.name,
        "plan_hash": hashlib.sha256(plan.read_bytes()).hexdigest(),
        "acceptance_criteria": ["retain deterministic evidence"],
        "dependencies": [],
        "status": "planned",
        "queue_status": "Draft",
        "risk": "low",
    })


def _session(store: DevelopmentStore, task: dict, suffix: str = "one") -> dict:
    session = store.create_session(
        int(task["id"]),
        "policy",
        f"stability-{suffix}",
        plan_hash_snapshot=task["plan_hash"],
        criteria_snapshot=["retain deterministic evidence"],
        worker_profile_slug="mc-native",
        reviewer_profile_slug="reviewer-default",
    )
    store.add_stages(int(session["id"]), STAGES)
    return session


def test_preflight_blocks_an_unhealthy_control_plane_validator(
    tmp_path: Path, monkeypatch
) -> None:
    store = DevelopmentStore(tmp_path / "developer.db")
    task = _task(store, tmp_path, 701)
    monkeypatch.setattr(coding_completion, "REPO_ROOT", tmp_path)
    service = CodingCompletionService(
        store=store,
        policy=_policy(tmp_path),
        worker=_Worker(),
        assessor=_Assessor(),
        validation_probe=lambda _commands: {
            "ok": False,
            "checked": [{"harness": "tests/test_coding_agent.py", "ok": False}],
            "cached": False,
            "message": "Baseline validator failed before worker assignment.",
        },
    )

    report = service.preflight(int(task["queue_id"]), active_probe=False)

    assert not report["ready"]
    assert "validation_infrastructure_failed" in {
        item["code"] for item in report["blockers"]
    }
    assert report["validation_health"]["ok"] is False
    assert store.list_sessions(10) == []


def test_learning_deduplicates_one_attempt_and_applies_resolved_playbook(
    tmp_path: Path,
) -> None:
    store = DevelopmentStore(tmp_path / "developer.db")
    task = _task(store, tmp_path, 702)
    session = _session(store, task)
    learning = CodingLearningService(store)

    first = learning.record(
        session_id=int(session["id"]),
        outcome="paused",
        stage="validate",
        error_code="validation_failed",
        worker_profile="mc-native",
        evidence={"attempt": 1, "blocker": "same failed check"},
    )
    duplicate = learning.record(
        session_id=int(session["id"]),
        outcome="paused",
        stage="validate",
        error_code="validation_failed",
        worker_profile="mc-native",
        evidence={"attempt": 1, "blocker": "same failed check"},
    )
    assert int(duplicate["id"]) == int(first["id"])
    assert duplicate["deduplicated"] is True

    for attempt in (2, 3):
        learning.record(
            session_id=int(session["id"]),
            outcome="paused",
            stage="validate",
            error_code="validation_failed",
            worker_profile="mc-native",
            evidence={"attempt": attempt, "blocker": "same failed check"},
        )
    learning.record(
        session_id=int(session["id"]),
        outcome="merged",
        stage="merge_deploy",
        worker_profile="mc-native",
        evidence={"attempt": 1, "sha": "c" * 40},
    )

    replay = learning.replay()
    repair = next(item for item in replay["results"] if item["slug"].startswith("repair-"))
    assert repair["qualified"] is True
    store.update_session(
        int(session["id"]),
        state="merged",
        stage="merge_deploy",
        completed_at=utc_now(),
    )
    future_session = _session(store, task, "future")
    applied = learning.applicable(
        worker_profile="mc-native",
        session_id=int(future_session["id"]),
    )
    assert applied
    assert "fingerprint" in " ".join(applied[0]["instructions"]).lower()


def test_same_failure_is_blocked_before_a_third_worker_cycle(tmp_path: Path) -> None:
    store = DevelopmentStore(tmp_path / "developer.db")
    task = _task(store, tmp_path, 703)
    session = _session(store, task)
    agent = CodingAgent(policy=_policy(tmp_path), store=store)
    session_id = int(session["id"])

    store.update_stage(session_id, "validate", status="running", attempts=1)
    first = agent._pause(
        session_id,
        "validate",
        "Validation failed. Review the failed check evidence.",
        "validation_failed",
    )
    assert first["state"] == "paused"

    store.update_stage(session_id, "validate", status="running", attempts=2)
    store.update_session(
        session_id,
        state="validating",
        stage="validate",
        blocker=None,
        error_code=None,
    )
    second = agent._pause(
        session_id,
        "validate",
        "Validation failed. Review the failed check evidence.",
        "validation_failed",
    )
    assert second["state"] == "blocked"
    assert second["error_code"] == "repeated_failure"


def test_delivery_sync_emits_only_when_remote_state_changes(tmp_path: Path) -> None:
    store = DevelopmentStore(tmp_path / "developer.db")
    task = _task(store, tmp_path, 704)
    session = _session(store, task)
    session_id = int(session["id"])
    agent = CodingAgent(policy=_policy(tmp_path), store=store)
    agent.github = _OpenPullRequest()

    for stage in ("prepare", "index", "code", "validate", "review", "commit", "scan", "push", "pull_request"):
        store.update_stage(session_id, stage, status="completed", completed_at=utc_now())
    store.update_session(
        session_id,
        state="awaiting_owner_merge",
        stage="merge_deploy",
        branch="v3.704.0/stability",
        head_sha="a" * 40,
        base_sha="b" * 40,
    )
    agent._save_pr(
        int(task["id"]),
        {
            "number": 7,
            "url": "https://example.test/pull/7",
            "head_sha": "a" * 40,
            "base_sha": "b" * 40,
            "draft": False,
        },
    )

    agent.sync_delivery(session_id)
    agent.sync_delivery(session_id)

    synchronized = [
        item for item in store.list_events(session_id, limit=100)
        if item["event_type"] == "delivery_synchronized"
    ]
    assert len(synchronized) == 1


def test_completed_runtime_status_survives_stale_queue_markdown(tmp_path: Path) -> None:
    store = DevelopmentStore(tmp_path / "developer.db")
    task = _task(store, tmp_path, 705)
    with store.connect() as conn:
        conn.execute(
            """UPDATE development_tasks
               SET status='completed',owner_state='Done',queue_status='Done',status_override=1
               WHERE id=?""",
            (int(task["id"]),),
        )
        conn.commit()

    stale = store.upsert_task({
        "queue_id": 705,
        "title": "Stability hardening",
        "plan_path": task["plan_path"],
        "plan_hash": task["plan_hash"],
        "acceptance_criteria": ["retain deterministic evidence"],
        "dependencies": [],
        "status": "planned",
        "queue_status": "Draft",
        "risk": "low",
    })

    assert stale["status"] == "completed"
    assert stale["queue_status"] == "Done"

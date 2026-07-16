"""Durable coding workflow orchestrator owned by Mission Control."""
from __future__ import annotations

import json
import hashlib
import os
import socket
import subprocess
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from core.coding_assessment import CodingTaskAssessor
from core.coding_contracts import SprintBudget, WorkerProfile, build_handoff
from core.coding_learning import CodingLearningService
from core.coding_policy import CodingPolicy, PolicyDenied
from core.coding_quality import CodingQualityGate
from core.coding_review import CodingReviewError, CodingReviewer
from core.coding_queue import sync_queue
from core.deployment_manager import DeploymentManager
from core.development_store import DevelopmentStore, utc_now
from core.git_workspace import GitCommandError, GitWorkspaceManager
from core.github_coding import GitHubCodingError, GitHubCodingService
from core.coding_workers import CodingWorkerBlocked, CodingWorkerRouter, CodingWorkerUnavailable
from core.release_manager import ReleaseManager
from core.repo_index import RepositoryIndex


STAGES = [
    {"id": "prepare", "title": "Create isolated worktree", "depends": []},
    {"id": "index", "title": "Build scoped repository context", "depends": ["prepare"]},
    {"id": "code", "title": "Run selected coding worker", "depends": ["index"]},
    {"id": "validate", "title": "Run mandatory checks", "depends": ["code"]},
    {"id": "review", "title": "Review scope, policy, and evidence", "depends": ["validate"]},
    {"id": "commit", "title": "Create logical checkpoint", "depends": ["review"]},
    {"id": "scan", "title": "Perform final secret scan", "depends": ["commit"]},
    {"id": "push", "title": "Push feature branch", "depends": ["scan"]},
    {"id": "pull_request", "title": "Create draft pull request", "depends": ["push"]},
    {"id": "merge_deploy", "title": "Owner merge and deploy gate", "depends": ["pull_request"]},
    {"id": "health", "title": "Verify release health", "depends": ["merge_deploy"]},
]


def _safe(value: Any) -> Any:
    """Redact all persisted/evented text, including nested worker output."""
    from core.terminal_engine import redact
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, list):
        return [_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_safe(item) for item in value]
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            if any(word in str(key).lower() for word in ("secret", "token", "password", "private_key")):
                cleaned[str(key)] = "[REDACTED]"
            else:
                cleaned[str(key)] = _safe(item)
        return cleaned
    return value


class CodingAgent:
    def __init__(
        self,
        *,
        policy: CodingPolicy | None = None,
        store: DevelopmentStore | None = None,
    ) -> None:
        self.policy = policy or CodingPolicy.load()
        self.store = store or DevelopmentStore()
        self.queue = sync_queue(self.store)
        self.index = RepositoryIndex(self.policy, self.store)
        self.git = GitWorkspaceManager(self.policy)
        self.worker = CodingWorkerRouter(self.policy, self.store)
        self.reviewer = CodingReviewer()
        self.assessor = CodingTaskAssessor(self.policy, self.index)
        self.quality = CodingQualityGate(self.policy, self.git)
        self.learning = CodingLearningService(self.store)
        self.github = GitHubCodingService(self.policy)
        self.releases = ReleaseManager(self.store)
        self.deployments = DeploymentManager(self.policy, self.store)
        self._threads: dict[int, threading.Thread] = {}
        self._thread_lock = threading.Lock()
        self.runtime_owner = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"

    def sync(self) -> list[dict[str, Any]]:
        self.queue = sync_queue(self.store)
        return self.queue

    def create_workflow(self, queue_id: int, *, idempotency_key: str | None = None) -> dict[str, Any]:
        self.sync()
        task = self.store.get_task(queue_id=queue_id)
        if not task:
            raise KeyError(f"Queue item #{queue_id} was not found.")
        dependencies = json.loads(task["dependencies_json"] or "[]")
        for dependency in dependencies:
            dep = self.store.get_task(queue_id=int(dependency))
            if not dep or dep["status"] != "completed":
                raise RuntimeError(f"Queue item #{dependency} must be completed first.")
        target_version = task.get("target_version") or self._next_version(queue_id)
        conn = self.store.connect()
        try:
            conn.execute("UPDATE development_tasks SET status='approved',target_version=?,updated_at=? WHERE id=?",
                         (target_version, utc_now(), task["id"]))
            conn.commit()
        finally:
            conn.close()
        session = self.store.create_session(
            int(task["id"]), self.policy.hash, idempotency_key or str(uuid.uuid4()),
            plan_hash_snapshot=task["plan_hash"],
            criteria_snapshot=json.loads(task.get("acceptance_criteria_json") or "[]"),
            sprint_budget=self.assessor._budget(str(task.get("risk") or "medium")).to_dict(),
        )
        self.store.add_stages(int(session["id"]), STAGES)
        self.releases.reserve(target_version, queue_id, risk=task.get("risk") or "medium")
        self.store.append_event(int(session["id"]), "workflow_approved", {
            "queue_id": queue_id, "plan_path": task["plan_path"], "plan_hash": task["plan_hash"],
            "policy_hash": self.policy.hash, "target_version": target_version,
        }, actor="owner")
        return self.get_workflow(int(session["id"]))

    def create_goal(
        self,
        *,
        title: str,
        objective: str,
        acceptance_criteria: list[str],
        validation_commands: list[list[str]] | None = None,
        autonomy: str = "sandbox",
        preferred_models: list[str] | None = None,
        max_iterations: int | None = None,
        worker_profile_slug: str = "mc-native",
        reviewer_profile_slug: str = "reviewer-default",
    ) -> dict[str, Any]:
        commands = validation_commands or []
        for command in commands:
            self.policy.assert_command(command)
        worker_profile = self.store.get_worker_profile(worker_profile_slug)
        if not worker_profile or not bool(worker_profile["enabled"]):
            raise ValueError(f"Worker profile is unavailable: {worker_profile_slug}")
        reviewer_profile = self.store.get_worker_profile(reviewer_profile_slug)
        if not reviewer_profile or reviewer_profile["adapter"] != "model_review":
            raise ValueError(f"Reviewer profile is unavailable: {reviewer_profile_slug}")
        assessment = self.assessor.assess(
            title=title,
            objective=objective,
            acceptance_criteria=acceptance_criteria,
            validation_commands=commands,
        )
        assessment_row = self.store.create_assessment(assessment.to_dict())
        initial_status = "awaiting_scope_approval" if assessment.owner_review_required else "queued"
        configured_max = int(self.policy.data.get("loop", {}).get("max_goal_iterations", 12))
        goal = self.store.create_goal(
            title=title,
            objective=objective,
            acceptance_criteria=acceptance_criteria,
            validation_commands=commands,
            autonomy=autonomy,
            preferred_models=preferred_models or [],
            max_iterations=max_iterations or configured_max,
            worker_profile_slug=worker_profile_slug,
            reviewer_profile_slug=reviewer_profile_slug,
            assessment_id=int(assessment_row["id"]),
            assessment=assessment.to_dict(),
            budget=assessment.sprints[0].budget.to_dict(),
            status=initial_status,
        )
        goal_id = int(goal["id"])
        self.store.attach_assessment(int(assessment_row["id"]), goal_id)
        self.store.create_sprints(goal_id, [sprint.to_dict() for sprint in assessment.sprints])
        payload = {
            "title": goal["title"], "objective": goal["objective"],
            "acceptance": json.loads(goal["acceptance_criteria_json"]),
            "validation": json.loads(goal["validation_commands_json"]),
        }
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        self.store.upsert_task({
            "queue_id": 900_000_000 + goal_id,
            "title": goal["title"],
            "plan_path": f"developer-goal:{goal_id}",
            "plan_hash": digest,
            "acceptance_criteria": payload["acceptance"],
            "dependencies": [],
            "status": "planned",
            "risk": "high",
            "target_version": f"3.0.{goal_id}",
            "queue_status": "Goal loop",
            "queue_effort": "continuous",
        })
        return self.store.get_goal(goal_id) or goal

    def create_goal_workflow(self, goal_id: int) -> dict[str, Any]:
        goal = self.store.get_goal(goal_id)
        if not goal:
            raise KeyError(goal_id)
        task = self.store.get_task(queue_id=900_000_000 + goal_id)
        if not task:
            raise RuntimeError("Goal task mirror is missing.")
        sprint = self.store.next_sprint(goal_id)
        if not sprint:
            raise RuntimeError("Development goal has no pending sprint.")
        criteria = json.loads(sprint["acceptance_criteria_json"] or "[]")
        commands = json.loads(goal["validation_commands_json"] or "[]")
        iteration = int(goal["iteration_count"] or 0) + 1
        session = self.store.create_session(
            int(task["id"]), self.policy.hash, f"goal-{goal_id}-iteration-{iteration}",
            goal_id=goal_id,
            plan_hash_snapshot=task["plan_hash"],
            criteria_snapshot=criteria,
            validation_commands=commands,
            worker_profile_slug=str(goal.get("worker_profile_slug") or "mc-native"),
            reviewer_profile_slug=str(goal.get("reviewer_profile_slug") or "reviewer-default"),
            assessment_id=int(goal["assessment_id"]) if goal.get("assessment_id") else None,
            current_sprint_id=int(sprint["id"]),
            sprint_budget=json.loads(sprint["budget_json"] or "{}"),
        )
        self.store.add_stages(int(session["id"]), STAGES)
        self.store.update_sprint(int(sprint["id"]), status="active", session_id=int(session["id"]))
        if goal["autonomy"] != "sandbox":
            self.releases.reserve(task["target_version"], int(task["queue_id"]), risk="high")
        self.store.update_goal(goal_id, iteration_count=iteration, current_session_id=session["id"], status="running")
        self.store.add_goal_iteration(goal_id, int(session["id"]), iteration)
        self._event(int(session["id"]), "goal_iteration_started", {
            "goal_id": goal_id, "iteration": iteration, "objective": goal["objective"],
            "plan_hash": task["plan_hash"], "sprint": int(sprint["sequence"]),
        })
        return self.get_workflow(int(session["id"]))

    @staticmethod
    def _next_version(queue_id: int) -> str:
        return "3.0.0" if queue_id == 18 else f"3.{queue_id}.0"

    def get_workflow(self, session_id: int) -> dict[str, Any]:
        session = self.store.get_session(session_id)
        if not session:
            raise KeyError(session_id)
        session["stages"] = self.store.list_stages(session_id)
        session["checkpoints"] = self.store.list_checkpoints(session_id, 20)
        session["worker_session"] = self.store.latest_worker_session(session_id)
        session["sprint"] = self.store.get_sprint(int(session["current_sprint_id"])) if session.get("current_sprint_id") else None
        session["assessment"] = self.store.get_assessment(int(session["assessment_id"])) if session.get("assessment_id") else None
        conn = self.store.connect()
        try:
            pr = conn.execute("SELECT * FROM coding_pull_requests WHERE task_id=?", (session["task_id"],)).fetchone()
            session["pull_request"] = dict(pr) if pr else None
        finally:
            conn.close()
        return session

    def list_workflows(self, limit: int = 50) -> list[dict[str, Any]]:
        return [self.get_workflow(int(workflow["id"])) for workflow in self.store.list_sessions(limit)]

    def assess_goal(
        self,
        *,
        title: str,
        objective: str,
        acceptance_criteria: list[str],
        validation_commands: list[list[str]] | None = None,
    ) -> dict[str, Any]:
        for command in validation_commands or []:
            self.policy.assert_command(command)
        return self.assessor.assess(
            title=title,
            objective=objective,
            acceptance_criteria=acceptance_criteria,
            validation_commands=validation_commands or [],
        ).to_dict()

    def worker_profiles(self, *, probe: bool = False) -> list[dict[str, Any]]:
        profiles: list[dict[str, Any]] = []
        for row in self.store.list_worker_profiles():
            profile = WorkerProfile.from_row(row)
            item = {**profile.public_dict(), **{
                "health_status": row.get("health_status") or "unknown",
                "health_detail": row.get("health_detail"),
                "last_probed_at": row.get("last_probed_at"),
            }}
            if probe:
                item = self.worker.probe(profile.slug)
            profiles.append(item)
        return profiles

    def switch_worker(self, session_id: int, profile_slug: str) -> dict[str, Any]:
        session = self.get_workflow(session_id)
        if session["state"] not in {"paused", "blocked", "failed", "approved"}:
            raise RuntimeError("A worker can only be switched at a paused checkpoint.")
        row = self.store.get_worker_profile(profile_slug)
        if not row or not bool(row["enabled"]) or row["adapter"] == "model_review":
            raise ValueError("Selected coding worker profile is unavailable.")
        self._checkpoint(
            session_id,
            status="worker_switch",
            next_action=f"Resume the bounded sprint with worker profile {profile_slug}.",
        )
        self.store.close_worker_sessions(session_id)
        self.store.update_session(
            session_id,
            worker_profile_slug=profile_slug,
            active_worker_session_id=None,
            blocker=None,
            error_code=None,
            cancel_requested=0,
        )
        if session.get("goal_id"):
            self.store.update_goal(int(session["goal_id"]), worker_profile_slug=profile_slug)
        conn = self.store.connect()
        try:
            conn.execute(
                """UPDATE coding_stages SET status='pending',started_at=NULL,completed_at=NULL
                   WHERE session_id=? AND node_id IN ('code','validate','review','commit','scan','push','pull_request')""",
                (session_id,),
            )
            conn.commit()
        finally:
            conn.close()
        self._event(session_id, "worker_switched", {
            "from": session.get("worker_profile_slug"), "to": profile_slug,
        }, actor="owner")
        return self.get_workflow(session_id)

    def learning_state(self) -> dict[str, Any]:
        return {
            "records": self.store.list_learning_records(limit=200),
            "playbooks": self.store.list_playbooks(),
        }

    def start_background(self, session_id: int) -> dict[str, Any]:
        with self._thread_lock:
            current = self._threads.get(session_id)
            if current and current.is_alive():
                return self.get_workflow(session_id)
            thread = threading.Thread(target=self.run_to_gate, args=(session_id,), daemon=True,
                                      name=f"tobi-coding-{session_id}")
            self._threads[session_id] = thread
            thread.start()
        return self.get_workflow(session_id)

    def _event(self, session_id: int, event_type: str, payload: dict[str, Any], actor: str = "tobi") -> None:
        self.store.append_event(session_id, event_type, _safe(payload), actor=actor)

    def _artifact(self, session_id: int, evidence_type: str, value: Any) -> dict[str, Any]:
        root = self.policy.repo_path("artifact_root") / str(session_id)
        root.mkdir(parents=True, exist_ok=True)
        existing = len(list(root.glob(f"{evidence_type}-*.json")))
        path = root / f"{evidence_type}-{existing + 1:03d}.json"
        path.write_text(json.dumps(_safe(value), ensure_ascii=True, indent=2, default=str), encoding="utf-8")
        retain = datetime.now(timezone.utc) + timedelta(days=self.policy.limit("retention_days", 7))
        artifact = self.store.add_artifact(session_id, evidence_type, path, retain.isoformat())
        self._event(session_id, "artifact_retained", {"artifact_id": artifact["id"],
                                                       "evidence_type": evidence_type,
                                                       "size_bytes": artifact["size_bytes"]})
        return artifact

    def _checkpoint(
        self,
        session_id: int,
        *,
        status: str,
        next_action: str,
    ) -> dict[str, Any] | None:
        session = self.store.get_session(session_id)
        if not session or not session.get("worktree") or not Path(session["worktree"]).is_dir():
            return None
        try:
            changed = self.git.changed_files(session["worktree"])
            head_sha = self.git.head(session["worktree"])
        except (GitCommandError, PolicyDenied, OSError):
            changed = []
            head_sha = session.get("head_sha")
        validate = next(
            (stage for stage in self.store.list_stages(session_id) if stage["node_id"] == "validate"), {}
        )
        try:
            checks = json.loads(validate.get("checks_json") or "[]")
        except json.JSONDecodeError:
            checks = []
        worker_session = self.store.latest_worker_session(session_id)
        sprint = self.store.get_sprint(int(session["current_sprint_id"])) if session.get("current_sprint_id") else None
        handoff = build_handoff(
            workflow_id=session_id,
            stage=str(session.get("stage") or "approved"),
            worker_profile=str(session.get("worker_profile_slug") or "mc-native"),
            worktree=str(session["worktree"]),
            head_sha=head_sha,
            changed_files=changed,
            recent_events=self.store.list_events(session_id, limit=50),
            checks=checks,
            sprint=sprint,
            status=status,
            next_action=next_action,
        )
        checkpoint = self.store.save_checkpoint(
            session_id=session_id,
            worker_session_id=int(worker_session["id"]) if worker_session else None,
            head_sha=head_sha,
            status=status,
            handoff=handoff,
        )
        self._event(session_id, "checkpoint_created", {
            "checkpoint_id": checkpoint["id"], "sequence": checkpoint["sequence"],
            "status": status, "head_sha": head_sha, "next_action": next_action,
        })
        return checkpoint

    def _record_learning(
        self,
        session_id: int,
        *,
        outcome: str,
        stage: str,
        error_code: str = "",
        evidence: dict[str, Any] | None = None,
    ) -> None:
        session = self.store.get_session(session_id) or {}
        self.learning.record(
            session_id=session_id,
            outcome=outcome,
            stage=stage,
            error_code=error_code,
            worker_profile=str(session.get("worker_profile_slug") or ""),
            evidence=_safe(evidence or {}),
        )

    def _stage_start(self, session_id: int, node_id: str, state: str, progress: int) -> None:
        stage = next((s for s in self.store.list_stages(session_id) if s["node_id"] == node_id), None)
        attempts = int(stage["attempts"] if stage else 0) + 1
        self.store.update_stage(session_id, node_id, status="running", attempts=attempts, started_at=utc_now())
        self.store.update_session(session_id, state=state, stage=node_id, progress=progress,
                                  blocker=None, error_code=None)
        self._event(session_id, "stage_started", {"stage": node_id, "attempt": attempts})

    def _stage_complete(self, session_id: int, node_id: str, result: dict[str, Any] | None = None) -> None:
        safe_result = _safe(result or {})
        self.store.update_stage(session_id, node_id, status="completed", result_json=safe_result, completed_at=utc_now())
        self._event(session_id, "stage_completed", {"stage": node_id, "result": safe_result})

    def _pause(self, session_id: int, stage: str, blocker: str, code: str) -> dict[str, Any]:
        blocker = str(_safe(blocker))
        current = next((item for item in self.store.list_stages(session_id) if item["node_id"] == stage), None)
        if current and current["status"] != "completed":
            self.store.update_stage(session_id, stage, status="paused", result_json={"error_code": code})
        self.store.update_session(session_id, state="paused", stage=stage, blocker=blocker, error_code=code)
        self._event(session_id, "workflow_paused", {"stage": stage, "error_code": code, "action": blocker})
        self._checkpoint(session_id, status="paused", next_action=blocker)
        self._record_learning(
            session_id, outcome="paused", stage=stage, error_code=code,
            evidence={"blocker": blocker},
        )
        return self.get_workflow(session_id)

    def _block(self, session_id: int, stage: str, blocker: str, code: str) -> dict[str, Any]:
        blocker = str(_safe(blocker))
        self.store.update_stage(session_id, stage, status="failed", result_json={"error_code": code})
        self.store.update_session(session_id, state="blocked", stage=stage, blocker=blocker, error_code=code)
        self._event(session_id, "workflow_blocked", {"stage": stage, "error_code": code, "action": blocker})
        self._checkpoint(session_id, status="blocked", next_action=blocker)
        self._record_learning(
            session_id, outcome="blocked", stage=stage, error_code=code,
            evidence={"blocker": blocker},
        )
        return self.get_workflow(session_id)

    def run_to_gate(self, session_id: int) -> dict[str, Any]:
        lease_seconds = max(
            3600,
            self.policy.limit("worker_timeout_seconds", 1800) +
            self.policy.limit("command_timeout_seconds", 900) * max(1, len(self.policy.mandatory_checks())) + 600,
        )
        if not self.store.claim_session(session_id, self.runtime_owner, lease_seconds):
            raise RuntimeError("Coding workflow is already owned by another live runtime.")
        try:
            return self._run_to_gate(session_id)
        finally:
            self.store.release_session(session_id, self.runtime_owner)

    def _run_to_gate(self, session_id: int) -> dict[str, Any]:
        session = self.get_workflow(session_id)
        if session["policy_hash"] != self.policy.hash:
            return self._pause(session_id, session["stage"], "The active coding policy changed; review and restart from a new workflow.",
                               "policy_changed")
        if session.get("plan_hash_snapshot") and session.get("plan_hash") != session.get("plan_hash_snapshot"):
            return self._pause(session_id, session["stage"],
                               "The approved plan changed after this workflow started. Review the new plan and start a new workflow.",
                               "plan_changed")
        try:
            statuses = {item["node_id"]: item["status"] for item in session["stages"]}
            if statuses.get("merge_deploy") == "completed" and statuses.get("health") != "completed":
                return self._deploy_merged_release(session_id)

            if statuses.get("prepare") != "completed":
                self._stage_start(session_id, "prepare", "preparing", 5)
                prepared = self.git.prepare(session_id, session.get("target_version") or "3.0.0", session["title"])
                self.store.update_session(session_id, **prepared)
                self._stage_complete(session_id, "prepare", prepared)

            session = self.get_workflow(session_id)
            statuses = {item["node_id"]: item["status"] for item in session["stages"]}
            if statuses.get("index") != "completed":
                self._stage_start(session_id, "index", "preparing", 12)
                snapshot = self.index.build(Path(session["worktree"]))
                self._stage_complete(session_id, "index", snapshot)

            session = self.get_workflow(session_id)
            statuses = {item["node_id"]: item["status"] for item in session["stages"]}
            if statuses.get("code") != "completed":
                self._stage_start(session_id, "code", "coding", 20)
                task = self.store.get_task(task_id=int(session["task_id"])) or {}
                criteria = json.loads(session.get("criteria_snapshot_json") or task.get("acceptance_criteria_json") or "[]")
                validation_commands = json.loads(session.get("validation_commands_json") or "[]")
                goal = self.store.get_goal(int(session["goal_id"])) if session.get("goal_id") else None
                context = self.index.search(
                    f"{session['title']} {' '.join(criteria[:8])}", limit=30, root=Path(session["worktree"]),
                )
                validation_stage = next((item for item in session["stages"] if item["node_id"] == "validate"), {})
                sprint = self.store.get_sprint(int(session["current_sprint_id"])) if session.get("current_sprint_id") else None
                sprint_budget = SprintBudget.from_value(
                    sprint.get("budget_json") if sprint else session.get("sprint_budget_json")
                )
                brief = {
                    "workflow_id": session_id, "stage_id": "code", "worktree": session["worktree"],
                    "title": sprint["title"] if sprint else session["title"],
                    "objective": sprint["objective"] if sprint else goal["objective"] if goal else session["title"],
                    "plan_path": session["plan_path"], "plan_hash": session["plan_hash"],
                    "acceptance_criteria": criteria, "relevant_files": context,
                    "previous_checks": json.loads(validation_stage.get("checks_json") or "[]"),
                    "allowed_commands": self.policy.mandatory_checks(),
                    "validation_commands": validation_commands,
                    "preferred_models": json.loads(goal["preferred_models_json"] or "[]") if goal else [],
                    "worker_profile_slug": str(session.get("worker_profile_slug") or "mc-native"),
                    "reviewer_profile_slug": str(session.get("reviewer_profile_slug") or "reviewer-default"),
                    "sprint_budget": sprint_budget.to_dict(),
                    "special_approval": self.store.has_approval(session_id, "special_paths", self.policy.hash),
                    "policy": {"version": self.policy.version, "hash": self.policy.hash,
                               "protected_paths": self.policy.data.get("protected_paths", []),
                               "forbidden_paths": self.policy.data.get("forbidden_paths", [])},
                }

                def worker_event(kind: str, payload: dict[str, Any]) -> None:
                    self._event(
                        session_id, f"worker_{kind}", payload,
                        actor=str(session.get("worker_profile_slug") or "worker"),
                    )

                try:
                    result = self.worker.run(
                        session_id, "code", session["worktree"], brief, on_event=worker_event,
                        cancel_check=lambda: bool((self.store.get_session(session_id) or {}).get("cancel_requested")),
                    )
                except CodingWorkerUnavailable as exc:
                    current = self.store.get_session(session_id) or {}
                    if current.get("state") == "canceled":
                        return self.get_workflow(session_id)
                    if current.get("cancel_requested"):
                        if current.get("state") == "paused":
                            return self.get_workflow(session_id)
                        return self._pause(
                            session_id, "code", "Paused by owner. Resume when ready.", "owner_paused"
                        )
                    return self._pause(session_id, "code", str(exc), "worker_unavailable")
                except CodingWorkerBlocked as exc:
                    current = self.store.get_session(session_id) or {}
                    if current.get("state") == "canceled":
                        return self.get_workflow(session_id)
                    if current.get("cancel_requested"):
                        if current.get("state") == "paused":
                            return self.get_workflow(session_id)
                        return self._pause(
                            session_id, "code", "Paused by owner. Resume when ready.", "owner_paused"
                        )
                    return self._pause(session_id, "code", str(exc), "worker_blocked")
                except TimeoutError as exc:
                    current = self.store.get_session(session_id) or {}
                    if current.get("state") == "canceled":
                        return self.get_workflow(session_id)
                    if current.get("cancel_requested"):
                        if current.get("state") == "paused":
                            return self.get_workflow(session_id)
                        return self._pause(
                            session_id, "code", "Paused by owner. Resume when ready.", "owner_paused"
                        )
                    return self._pause(session_id, "code", str(exc), "worker_timeout")
                except RuntimeError as exc:
                    current = self.store.get_session(session_id) or {}
                    if current.get("state") == "canceled":
                        return self.get_workflow(session_id)
                    if current.get("cancel_requested"):
                        return self._pause(session_id, "code", "Paused by owner. Resume when ready.", "owner_paused")
                    return self._pause(session_id, "code", str(exc), "worker_failed")
                changed = self.git.changed_files(session["worktree"])
                self._artifact(session_id, "worker", {"events": result["events"], "output": result["output"]})
                self._stage_complete(session_id, "code", {"changed_files": changed, "event_count": len(result["events"])})
                self._checkpoint(
                    session_id, status="worker_completed",
                    next_action="Run deterministic validation and quality gates.",
                )
                if not changed:
                    return self._pause(session_id, "code", "Coding worker completed without changing files; revise the sprint or retry.",
                                       "no_changes")
                special = self.store.has_approval(session_id, "special_paths", self.policy.hash)
                self.policy.assert_write_paths(changed, special_approval=special)

            session = self.get_workflow(session_id)
            statuses = {item["node_id"]: item["status"] for item in session["stages"]}
            if statuses.get("validate") != "completed":
                checks = self._run_checks(session_id, Path(session["worktree"]))
                if any(not check["ok"] for check in checks):
                    cycles = int(session.get("review_cycles") or 0) + 1
                    self.store.update_session(session_id, review_cycles=cycles)
                    if cycles > self.policy.limit("max_review_cycles", 2):
                        return self._block(session_id, "validate",
                                           "Validation failed after the maximum correction cycles. Owner action is required.",
                                           "review_cycles_exhausted")
                    return self._pause(session_id, "validate",
                                       "Validation failed. Review the failed check evidence, then retry the workflow.",
                                       "validation_failed")

            session = self.get_workflow(session_id)
            statuses = {item["node_id"]: item["status"] for item in session["stages"]}
            if statuses.get("review") != "completed":
                self._stage_start(session_id, "review", "reviewing", 66)
                diff = self.git.diff_summary(session["worktree"])
                secret_findings = self.git.scan_secrets(session["worktree"])
                if secret_findings:
                    return self._pause(session_id, "review", "Remove probable secrets before acceptance review.",
                                       "secret_found")
                validate_stage = next((item for item in session["stages"] if item["node_id"] == "validate"), {})
                checks = json.loads(validate_stage.get("checks_json") or "[]")
                budget = SprintBudget.from_value(session.get("sprint_budget_json"))
                special = self.store.has_approval(session_id, "special_paths", self.policy.hash)
                quality = self.quality.evaluate(
                    worktree=session["worktree"],
                    budget=budget,
                    checks=checks,
                    special_approval=special,
                )
                self._artifact(session_id, "quality", quality)
                self._event(session_id, "quality_gate_completed", quality)
                if not quality["qualified"]:
                    return self._pause(
                        session_id, "review",
                        "Deterministic quality gates failed: " + " ".join(quality["failures"]),
                        "quality_gate_failed",
                    )
                criteria = json.loads(session.get("criteria_snapshot_json") or "[]")
                goal = self.store.get_goal(int(session["goal_id"])) if session.get("goal_id") else None
                reviewer_profile = self.store.get_worker_profile(
                    str(session.get("reviewer_profile_slug") or "reviewer-default")
                ) or {}
                try:
                    review = self.reviewer.review(
                        objective=goal["objective"] if goal else session["title"],
                        acceptance_criteria=criteria,
                        checks=checks,
                        patch=self.git.diff_patch(session["worktree"]),
                        changed_files=diff["files"],
                        model=str(reviewer_profile.get("model") or "") or None,
                        quality_report=quality,
                    )
                except CodingReviewError as exc:
                    return self._pause(session_id, "review", str(exc), "review_unavailable")
                self._artifact(session_id, "review", {**diff, **review})
                if not review["qualified"]:
                    cycles = int(session.get("review_cycles") or 0) + 1
                    self.store.update_session(session_id, review_cycles=cycles)
                    self.store.update_stage(session_id, "review", status="failed", result_json=review,
                                            completed_at=utc_now())
                    if cycles >= self.policy.limit("max_review_cycles", 2):
                        return self._block(session_id, "review", "Acceptance review failed after the correction limit.",
                                           "review_cycles_exhausted")
                    return self._pause(session_id, "review", "Acceptance review found unmet criteria. Retry for a correction pass.",
                                       "review_failed")
                self._stage_complete(session_id, "review", {**diff, **review})
            if statuses.get("commit") != "completed":
                self._stage_start(session_id, "commit", "reviewing", 72)
                special = self.store.has_approval(session_id, "special_paths", self.policy.hash)
                head = self.git.commit(session["worktree"], f"feat: implement queue item #{session['queue_id']}",
                                       special_approval=special)
                self.store.update_session(session_id, head_sha=head)
                self._stage_complete(session_id, "commit", {"head_sha": head})
                self._checkpoint(
                    session_id, status="logical_checkpoint",
                    next_action="Continue to the next bounded sprint or final acceptance.",
                )
                if self._advance_sprint(session_id, head):
                    return self._run_to_gate(session_id)

            session = self.get_workflow(session_id)
            statuses = {item["node_id"]: item["status"] for item in session["stages"]}
            if statuses.get("scan") != "completed":
                self._stage_start(session_id, "scan", "validating", 78)
                findings = self.git.scan_secrets(session["worktree"], base_ref=session["base_sha"])
                if findings:
                    return self._pause(session_id, "scan", "Remove probable secrets and request a clean rescan.", "secret_found")
                self._stage_complete(session_id, "scan", {"findings": 0})

            session = self.get_workflow(session_id)
            statuses = {item["node_id"]: item["status"] for item in session["stages"]}
            if statuses.get("push") != "completed":
                goal = self.store.get_goal(int(session["goal_id"])) if session.get("goal_id") else None
                if goal and goal["autonomy"] == "sandbox":
                    return self._pause(session_id, "push",
                                       "Goal met the local acceptance standard. Sandbox autonomy stops before GitHub mutation.",
                                       "autonomy_boundary")
                if not self.policy.feature_enabled("github"):
                    return self._pause(session_id, "push",
                                       "Local branch is validated. Enable the GitHub capability in reviewed policy to push and create a draft PR.",
                                       "github_disabled")
                self._stage_start(session_id, "push", "pushed", 84)
                self.git.push(session["worktree"], session["branch"])
                self._stage_complete(session_id, "push", {"branch": session["branch"]})
            if statuses.get("pull_request") != "completed":
                self._stage_start(session_id, "pull_request", "pushed", 88)
                pr = self.github.create_draft_pr(
                    session["branch"], f"#{session['queue_id']} {session['title']}", self._pull_request_body(session_id),
                )
                self._save_pr(int(session["task_id"]), pr)
                self._stage_complete(session_id, "pull_request", pr)

            session = self.get_workflow(session_id)
            pr = session.get("pull_request") or {}
            self.store.update_session(session_id, state="awaiting_merge_deploy_approval",
                                      stage="merge_deploy", progress=90,
                                      blocker="Owner re-authentication is required to merge and deploy.")
            self._event(session_id, "approval_required", {"purpose": "merge_deploy", "pull_request": pr})
            self._record_learning(
                session_id, outcome="draft_pr", stage="pull_request",
                evidence={"pull_request": pr, "head_sha": session.get("head_sha")},
            )
            return self.get_workflow(session_id)
        except CodingWorkerUnavailable as exc:
            return self._pause(session_id, "code", str(exc), "worker_unavailable")
        except PolicyDenied as exc:
            code = "special_approval_required" if "protected" in str(exc).lower() else "policy_denied"
            return self._pause(session_id, self.get_workflow(session_id)["stage"], str(exc), code)
        except (GitCommandError, GitHubCodingError, subprocess.SubprocessError, OSError) as exc:
            return self._pause(session_id, self.get_workflow(session_id)["stage"], str(exc)[:1000], "external_step_failed")
        except Exception as exc:
            return self._pause(session_id, self.get_workflow(session_id)["stage"],
                               f"Workflow stopped safely: {type(exc).__name__}", "internal_error")

    def _advance_sprint(self, session_id: int, checkpoint_sha: str) -> bool:
        session = self.store.get_session(session_id) or {}
        goal_id = session.get("goal_id")
        sprint_id = session.get("current_sprint_id")
        if not goal_id or not sprint_id:
            return False
        sprint = self.store.get_sprint(int(sprint_id))
        if sprint and sprint["status"] != "completed":
            self.store.update_sprint(
                int(sprint_id),
                status="completed",
                checkpoint_sha=checkpoint_sha,
                completed_at=utc_now(),
            )
            self._event(session_id, "sprint_completed", {
                "sprint_id": sprint_id,
                "sequence": sprint["sequence"],
                "checkpoint_sha": checkpoint_sha,
            })
        next_sprint = self.store.next_sprint(int(goal_id))
        if not next_sprint:
            return False
        criteria = json.loads(next_sprint["acceptance_criteria_json"] or "[]")
        budget = json.loads(next_sprint["budget_json"] or "{}")
        self.store.update_sprint(int(next_sprint["id"]), status="active", session_id=session_id)
        conn = self.store.connect()
        try:
            conn.execute(
                """UPDATE coding_stages
                   SET status='pending',checks_json='[]',result_json=NULL,started_at=NULL,completed_at=NULL
                   WHERE session_id=? AND node_id IN ('code','validate','review','commit')""",
                (session_id,),
            )
            conn.commit()
        finally:
            conn.close()
        self.store.update_session(
            session_id,
            current_sprint_id=int(next_sprint["id"]),
            criteria_snapshot_json=json.dumps(criteria, ensure_ascii=True, separators=(",", ":")),
            sprint_budget_json=json.dumps(budget, ensure_ascii=True, separators=(",", ":")),
            review_cycles=0,
            state="approved",
            stage="code",
            progress=20,
            blocker=None,
            error_code=None,
        )
        self._event(session_id, "sprint_started", {
            "sprint_id": next_sprint["id"],
            "sequence": next_sprint["sequence"],
            "title": next_sprint["title"],
            "budget": budget,
        })
        return True

    def _run_checks(self, session_id: int, worktree: Path) -> list[dict[str, Any]]:
        self._stage_start(session_id, "validate", "validating", 50)
        results: list[dict[str, Any]] = []
        timeout = self.policy.limit("command_timeout_seconds", 900)
        session = self.get_workflow(session_id)
        commands = list(self.policy.mandatory_checks())
        commands.extend(json.loads(session.get("validation_commands_json") or "[]"))
        unique: list[list[str]] = []
        seen: set[tuple[str, ...]] = set()
        for command in commands:
            argv = [str(part) for part in command]
            key = tuple(argv)
            if key not in seen:
                seen.add(key)
                unique.append(argv)
        for argv in unique:
            self.policy.assert_command(argv)
            completed = subprocess.run(argv, cwd=str(worktree), capture_output=True, text=True, timeout=timeout)
            result = _safe({"argv": argv, "ok": completed.returncode == 0, "exit_code": completed.returncode,
                            "output": (completed.stdout + completed.stderr)[-20_000:]})
            results.append(result)
            self._event(session_id, "check_completed", result)
            if not result["ok"]:
                break
        self.store.update_stage(session_id, "validate", status="completed" if all(r["ok"] for r in results) else "failed",
                                checks_json=results, result_json={"ok": all(r["ok"] for r in results)}, completed_at=utc_now())
        self._artifact(session_id, "checks", results)
        self._event(session_id, "stage_completed" if all(r["ok"] for r in results) else "stage_failed",
                    {"stage": "validate", "ok": all(r["ok"] for r in results)})
        return results

    def command(self, session_id: int, command: str, *, background: bool = True) -> dict[str, Any]:
        session = self.get_workflow(session_id)
        if command == "pause":
            self.store.update_session(session_id, cancel_requested=1)
            self.worker.cancel(session_id)
            return self._pause(session_id, session["stage"], "Paused by owner. Resume when ready.", "owner_paused")
        if command == "cancel":
            self.store.update_session(session_id, cancel_requested=1)
            self.worker.cancel(session_id)
            self.store.update_session(session_id, state="canceled", stage=session["stage"],
                                      blocker="Recoverable worktree retained for policy retention period.",
                                      completed_at=utc_now())
            self._event(session_id, "workflow_canceled", {"worktree_retained": bool(session.get("worktree"))}, actor="owner")
            return self.get_workflow(session_id)
        if command in {"resume", "retry"}:
            if session["state"] not in {"paused", "blocked", "failed", "approved"}:
                raise RuntimeError(f"Workflow cannot {command} from state {session['state']}.")
            conn = self.store.connect()
            try:
                active = conn.execute(
                    """SELECT id FROM coding_sessions
                       WHERE id<>? AND state IN ('approved','preparing','coding','validating','reviewing','pushed','merging','deploying')
                       LIMIT 1""",
                    (session_id,),
                ).fetchone()
                if active:
                    raise RuntimeError(f"Coding workflow {active['id']} is already active.")
                if session.get("error_code") in {"validation_failed", "review_failed", "review_unavailable"}:
                    conn.execute(
                        """UPDATE coding_stages SET status='pending',started_at=NULL,completed_at=NULL
                           WHERE session_id=? AND node_id IN ('code','validate','review','commit','scan','push','pull_request')""",
                        (session_id,),
                    )
                    conn.commit()
            finally:
                conn.close()
            self.store.update_session(session_id, state="approved" if not session.get("worktree") else "paused",
                                      blocker=None, error_code=None, cancel_requested=0)
            self._event(session_id, f"workflow_{command}d", {"stage": session["stage"]}, actor="owner")
            return self.start_background(session_id) if background else self.run_to_gate(session_id)
        raise ValueError(f"Unknown workflow command: {command}")

    def reconcile(self) -> list[dict[str, Any]]:
        """Fail closed after backend restart and repair durable checkpoints where evidence is conclusive."""
        reconciled: list[dict[str, Any]] = []
        active_states = {"approved", "preparing", "coding", "validating", "reviewing", "pushed", "merging", "deploying"}
        for item in self.store.list_sessions(200):
            if item["state"] not in active_states:
                continue
            lease_owner = str(item.get("lease_owner") or "")
            lease_expires = str(item.get("lease_expires_at") or "")
            if lease_owner and lease_owner != self.runtime_owner:
                parts = lease_owner.split(":")
                if len(parts) >= 2 and parts[0] == socket.gethostname():
                    try:
                        os.kill(int(parts[1]), 0)
                        continue
                    except (OSError, ValueError):
                        self.store.update_session(int(item["id"]), lease_owner=None, lease_expires_at=None)
                elif lease_expires > utc_now():
                    continue
            session = self.get_workflow(int(item["id"]))
            stages = {stage["node_id"]: stage for stage in session["stages"]}
            worktree = session.get("worktree")
            if worktree and Path(worktree).is_dir():
                try:
                    head = self.git.head(worktree)
                    self.store.update_session(int(session["id"]), head_sha=head)
                    commit_stage = stages.get("commit") or {}
                    if commit_stage.get("status") == "running" and head != session.get("base_sha") and self.git.is_clean(worktree):
                        self._stage_complete(int(session["id"]), "commit", {"head_sha": head, "reconciled": True})
                except (GitCommandError, PolicyDenied):
                    pass
            pr_stage = stages.get("pull_request") or {}
            if self.policy.feature_enabled("github") and session.get("branch") and pr_stage.get("status") == "running":
                try:
                    existing_pr = self.github.find_open_pr(str(session["branch"]))
                    if existing_pr:
                        self._save_pr(int(session["task_id"]), existing_pr)
                        self._stage_complete(int(session["id"]), "pull_request", {**existing_pr, "reconciled": True})
                except (GitHubCodingError, PolicyDenied):
                    pass
            current = self.get_workflow(int(session["id"]))
            stage = str(current.get("stage") or "approved")
            if stage in {"merge_deploy", "health"}:
                updated = self._pause(int(session["id"]), stage,
                                      "Backend restarted during an external mutation stage. Owner reconciliation is required.",
                                      "external_reconciliation_required")
            else:
                updated = self._pause(int(session["id"]), stage,
                                      "Backend restarted. Durable checkpoints were preserved and the workflow can resume safely.",
                                      "backend_restarted")
            reconciled.append(updated)
        return reconciled

    def approve(self, session_id: int, purpose: str, challenge: str) -> dict[str, Any]:
        session = self.get_workflow(session_id)
        if purpose not in {"special_paths", "merge_deploy"}:
            raise ValueError("Unsupported approval purpose.")
        if purpose == "merge_deploy" and session["state"] != "awaiting_merge_deploy_approval":
            raise RuntimeError("Workflow is not waiting for merge and deployment approval.")
        if purpose == "special_paths" and session.get("error_code") != "special_approval_required":
            raise RuntimeError("Workflow is not waiting for protected-path approval.")
        self.store.consume_challenge(challenge, purpose, self.policy.hash, session_id=session_id)
        self._event(session_id, "approval_granted", {"purpose": purpose, "policy_hash": self.policy.hash}, actor="owner")
        if purpose == "special_paths":
            return self.command(session_id, "resume")
        return self._merge_and_deploy(session_id)

    def _merge_and_deploy(self, session_id: int) -> dict[str, Any]:
        session = self.get_workflow(session_id)
        conn = self.store.connect()
        try:
            pr = conn.execute("SELECT * FROM coding_pull_requests WHERE task_id=?", (session["task_id"],)).fetchone()
        finally:
            conn.close()
        if not pr or not pr["number"]:
            raise RuntimeError("Workflow has no pull request to merge.")
        try:
            self._stage_start(session_id, "merge_deploy", "merging", 92)
            remote = self.github.get_pr(int(pr["number"]))
            if remote.get("merged") and remote.get("merge_commit_sha"):
                merged = {"merged": True, "sha": remote["merge_commit_sha"], "reconciled": True}
            else:
                if remote.get("draft"):
                    self.github.mark_ready(int(pr["number"]))
                readiness = self.github.merge_readiness(int(pr["number"]))
                if not readiness["ready"]:
                    detail = readiness["failed_checks"] or readiness["pending_checks"] or [
                        readiness["pull_request"].get("mergeable_state") or "GitHub is still calculating mergeability"
                    ]
                    raise GitHubCodingError(f"Pull request is not merge-ready: {', '.join(str(v) for v in detail)}")
                merged = self.github.squash_merge(int(pr["number"]), str(pr["head_sha"]), session["title"])
            self.releases.set_status(session["target_version"], "merged", commit_sha=merged["sha"])
            self._stage_complete(session_id, "merge_deploy", merged)
        except (GitHubCodingError, PolicyDenied) as exc:
            return self._pause(session_id, "merge_deploy", str(exc), "merge_not_ready")
        return self._deploy_merged_release(session_id)

    def _deploy_merged_release(self, session_id: int) -> dict[str, Any]:
        session = self.get_workflow(session_id)
        conn = self.store.connect()
        try:
            release = conn.execute("SELECT * FROM releases WHERE version=?", (session["target_version"],)).fetchone()
            latest = conn.execute(
                "SELECT * FROM deployments WHERE release_id=? ORDER BY id DESC LIMIT 1",
                (release["id"] if release else -1,),
            ).fetchone()
            known_good = conn.execute(
                "SELECT * FROM deployments WHERE status='healthy' ORDER BY id DESC LIMIT 1"
            ).fetchone()
        finally:
            conn.close()
        if not release or not release["commit_sha"]:
            return self._block(session_id, "health", "Merged release metadata is missing.", "release_metadata_missing")
        if release["status"] in {"failed", "rolled_back"}:
            return self._block(session_id, "health",
                               "This version is immutable after a failed or rolled-back deployment. Start a new versioned workflow.",
                               "version_not_reusable")
        if not self.policy.feature_enabled("deploy"):
            return self._pause(session_id, "health", "Merge completed; deployment is disabled by reviewed policy.",
                               "deploy_disabled")
        self.store.update_session(session_id, state="deploying", stage="health", progress=96)
        self.releases.set_status(session["target_version"], "deploying", commit_sha=release["commit_sha"])
        if latest and latest["status"] == "healthy" and latest["new_sha"] == release["commit_sha"]:
            deployment = {"id": latest["id"], "status": "healthy", "reconciled": True}
        else:
            deployment = self.deployments.deploy(
                int(release["id"]), str(known_good["new_sha"] if known_good else ""), release["commit_sha"],
            )
        if deployment["status"] != "healthy":
            status = "rolled_back" if deployment["status"] == "rolled_back" else "failed"
            self.releases.set_status(session["target_version"], status, commit_sha=release["commit_sha"])
            return self._pause(session_id, "health", f"Deployment ended in {deployment['status']}.", deployment["status"])
        try:
            tag = self.github.create_annotated_tag(
                session["target_version"], release["commit_sha"],
                f"TOBI release v{session['target_version']} for queue item #{session['queue_id']}",
            )
        except (GitHubCodingError, PolicyDenied) as exc:
            return self._pause(session_id, "health", str(exc), "tag_failed")
        self._stage_complete(session_id, "health", {"deployment": deployment, "tag": tag})
        self.releases.set_status(session["target_version"], "released", commit_sha=release["commit_sha"],
                                 tag=tag["tag"])
        self.store.update_session(session_id, state="completed", stage="completed", progress=100,
                                  blocker=None, completed_at=utc_now())
        self._mark_task_completed(int(session["task_id"]))
        self._event(session_id, "workflow_completed", {"version": session["target_version"],
                                                        "sha": release["commit_sha"], "tag": tag["tag"]})
        self._record_learning(
            session_id, outcome="completed", stage="health",
            evidence={"version": session["target_version"], "sha": release["commit_sha"]},
        )
        return self.get_workflow(session_id)

    def _mark_task_completed(self, task_id: int) -> None:
        conn = self.store.connect()
        try:
            conn.execute("UPDATE development_tasks SET status='completed',updated_at=? WHERE id=?", (utc_now(), task_id))
            conn.commit()
        finally:
            conn.close()

    def _save_pr(self, task_id: int, pr: dict[str, Any]) -> None:
        conn = self.store.connect()
        try:
            conn.execute(
                """INSERT INTO coding_pull_requests(task_id,repository,number,url,head_sha,base_sha,draft,updated_at)
                   VALUES (?,?,?,?,?,?,?,?)
                   ON CONFLICT(task_id) DO UPDATE SET number=excluded.number,url=excluded.url,
                   head_sha=excluded.head_sha,base_sha=excluded.base_sha,draft=excluded.draft,updated_at=excluded.updated_at""",
                (task_id, self.github.repository, pr.get("number"), pr.get("url"), pr.get("head_sha"),
                 pr.get("base_sha"), int(bool(pr.get("draft", True))), utc_now()),
            )
            conn.commit()
        finally:
            conn.close()

    def _pull_request_body(self, session_id: int) -> str:
        session = self.get_workflow(session_id)
        checks = next((stage for stage in session["stages"] if stage["node_id"] == "validate"), {})
        return (
            f"Implements queue item #{session['queue_id']}.\n\n"
            f"Plan: `{session['plan_path']}`\n\n"
            f"Policy: `{session['policy_hash'][:12]}`\n\n"
            f"Validation: `{checks.get('status', 'unknown')}`\n\n"
            "Generated by TOBI's controlled coding workflow. Owner merge and deployment approval remains required."
        )

    def changes(self, session_id: int) -> dict[str, Any]:
        session = self.get_workflow(session_id)
        if not session.get("worktree"):
            return {"files": [], "stat": "", "head_sha": session.get("head_sha")}
        return self.git.diff_summary(session["worktree"])

    def storage(self) -> dict[str, Any]:
        usage = self.git.storage()
        def tree_size(path: Path) -> int:
            return sum(item.stat().st_size for item in path.rglob("*") if item.is_file()) if path.exists() else 0
        artifact_root = self.policy.repo_path("artifact_root")
        index_root = self.policy.repo_path("index_root")
        usage["artifact_bytes"] = tree_size(artifact_root)
        usage["artifact_count"] = sum(1 for item in artifact_root.rglob("*.json")) if artifact_root.exists() else 0
        usage["index_bytes"] = tree_size(index_root)
        usage["total_developer_bytes"] = usage["worktree_bytes"] + usage["artifact_bytes"] + usage["index_bytes"]
        usage["warning_bytes"] = self.policy.limit("storage_warning_bytes", 10_737_418_240)
        usage["blocked_new_workflows"] = usage["total_developer_bytes"] >= usage["warning_bytes"]
        usage["retention_days"] = self.policy.limit("retention_days", 7)
        cutoff = (datetime.now(timezone.utc) - timedelta(days=usage["retention_days"])).isoformat()
        conn = self.store.connect()
        try:
            usage["cleanup_eligible_artifacts"] = int(conn.execute(
                """SELECT COUNT(*) FROM coding_artifacts a JOIN coding_sessions s ON s.id=a.session_id
                   WHERE a.retain_until<=? AND a.cleanup_eligible=0 AND s.state IN ('completed','canceled')""",
                (datetime.now(timezone.utc).isoformat(),),
            ).fetchone()[0])
            usage["cleanup_eligible_worktrees"] = int(conn.execute(
                """SELECT COUNT(*) FROM coding_sessions WHERE state IN ('completed','canceled') AND completed_at<=?
                   AND worktree IS NOT NULL""", (cutoff,)
            ).fetchone()[0])
        finally:
            conn.close()
        return usage

    def cleanup(self, challenge: str) -> dict[str, Any]:
        self.store.consume_challenge(challenge, "developer_cleanup", self.policy.hash)
        state = self.storage()
        cutoff = (datetime.now(timezone.utc) - timedelta(days=state["retention_days"])).isoformat()
        now = datetime.now(timezone.utc).isoformat()
        conn = self.store.connect()
        try:
            artifacts = conn.execute(
                """SELECT a.* FROM coding_artifacts a JOIN coding_sessions s ON s.id=a.session_id
                   WHERE a.retain_until<=? AND a.cleanup_eligible=0 AND s.state IN ('completed','canceled')""",
                (now,),
            ).fetchall()
            sessions = conn.execute(
                """SELECT * FROM coding_sessions WHERE state IN ('completed','canceled') AND completed_at<=?
                   AND worktree IS NOT NULL""", (cutoff,)
            ).fetchall()
        finally:
            conn.close()
        artifact_root = self.policy.repo_path("artifact_root").resolve()
        removed_artifacts = 0
        for row in artifacts:
            path = Path(row["path"]).resolve()
            if path.is_relative_to(artifact_root) and path.is_file():
                path.unlink()
                removed_artifacts += 1
            conn = self.store.connect()
            try:
                conn.execute("UPDATE coding_artifacts SET cleanup_eligible=1 WHERE id=?", (row["id"],))
                conn.commit()
            finally:
                conn.close()
        removed_worktrees = 0
        for row in sessions:
            try:
                self.git.cancel_cleanup(row["worktree"])
                removed_worktrees += 1
                self.store.update_session(int(row["id"]), worktree=None)
                self._event(int(row["id"]), "retained_workspace_cleaned", {}, actor="owner")
            except (PolicyDenied, GitCommandError):
                continue
        return {"removed_artifacts": removed_artifacts, "removed_worktrees": removed_worktrees,
                "remaining": self.storage()}

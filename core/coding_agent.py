"""Durable coding workflow orchestrator owned by Mission Control."""
from __future__ import annotations

import json
import hashlib
import os
import socket
import subprocess
import threading
import traceback
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from core.coding_assessment import CodingTaskAssessor
from core.coding_contracts import SprintBudget, WorkerProfile, build_handoff
from core.coding_completion import CodingCompletionService
from core.coding_states import (  # noqa: F401  (STAGES is re-exported for tests and callers)
    ACTIVE_STATES, CORRECTABLE_BY_RECODE, STAGES, TERMINAL_STATES, workflow_progress,
)
from core.coding_learning import CodingLearningService, failure_detail_signature
from core.coding_policy import CodingPolicy, PolicyDenied
from core.coding_quality import CodingQualityGate
from core.coding_review import CodingReviewError, CodingReviewer
from core.coding_queue import sync_queue, REPO_ROOT, task_execution_state
from core.deployment_manager import DeploymentManager
from core.development_store import DevelopmentStore, utc_now
from core.git_workspace import GitCommandError, GitWorkspaceManager
from core.github_coding import GitHubCodingError, GitHubCodingService
from core.coding_workers import CodingWorkerBlocked, CodingWorkerRouter, CodingWorkerUnavailable
from core.coding_tools import resolve_runtime_command
from core.release_manager import ReleaseManager
from core.repo_index import RepositoryIndex
from core.runtime.coding_adapter import CodingRuntimeAdapter
from core.proc import no_window


STALE_SNAPSHOT_ERRORS = {"policy_changed", "plan_changed"}
CANONICAL_VALIDATION_HARNESSES = frozenset({"tests/test_coding_agent.py"})
REPEAT_GUARDED_ERRORS = frozenset({
    "validation_failed",
    "quality_gate_failed",
    "review_failed",
    "review_unavailable",
})
INFRASTRUCTURE_FAILURE_MARKERS = (
    "no module named",
    "modulenotfounderror",
    "command not found",
    "is not recognized as an internal or external command",
    "cannot find the file",
    "filenotfounderror",
    "missing dependency",
    "node_modules is absent",
    "executable was not found",
)


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
        runtime_adapter: CodingRuntimeAdapter | None = None,
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
        self.runtime_coding = runtime_adapter or CodingRuntimeAdapter()
        self._validation_probe_lock = threading.Lock()
        self._validation_probe_cache: dict[str, dict[str, Any]] = {}
        self.completion = CodingCompletionService(
            store=self.store, policy=self.policy, worker=self.worker, assessor=self.assessor,
            validation_probe=self._preflight_validation_health,
            learning=self.learning,
        )
        self._threads: dict[int, threading.Thread] = {}
        self._thread_lock = threading.Lock()
        self._auto_queue_lock = threading.Lock()
        self.runtime_owner = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"

    def _preflight_validation_health(
        self, commands: list[list[str]]
    ) -> dict[str, Any]:
        """Prove trusted control-plane validators before spending a worker turn."""
        probes: list[tuple[list[str], str]] = []
        for command in commands:
            argv = [str(part) for part in command]
            if len(argv) < 2:
                continue
            relative = str(argv[1]).replace("\\", "/").lstrip("./")
            if relative not in CANONICAL_VALIDATION_HARNESSES:
                continue
            canonical = (self.git.repo_root / relative).resolve()
            if canonical.is_file() and canonical.is_relative_to(self.git.repo_root.resolve()):
                probes.append((argv, relative))
        if not probes:
            return {"ok": True, "checked": [], "cached": False}

        try:
            head = self.git.default_branch_sha()
        except (GitCommandError, PolicyDenied):
            head = "working-tree"
        key_source = json.dumps(
            {
                "head": head,
                "policy": self.policy.hash,
                "commands": [argv for argv, _relative in probes],
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        key = hashlib.sha256(key_source.encode("utf-8")).hexdigest()
        with self._validation_probe_lock:
            cached = self._validation_probe_cache.get(key)
            if cached:
                return {**cached, "cached": True}

        checked: list[dict[str, Any]] = []
        timeout = min(300, self.policy.limit("command_timeout_seconds", 900))
        for argv, relative in probes:
            invocation = list(argv)
            invocation[1] = str((self.git.repo_root / relative).resolve())
            environment = os.environ.copy()
            environment["TOBI_VALIDATION_ROOT"] = str(self.git.repo_root)
            try:
                completed = subprocess.run(
                    resolve_runtime_command(invocation),
                    cwd=str(self.git.repo_root),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=timeout,
                    env=environment,
                    creationflags=no_window(),
                )
                output = ((completed.stdout or "") + (completed.stderr or ""))[-4000:]
                result = {
                    "argv": argv,
                    "harness": relative,
                    "ok": completed.returncode == 0,
                    "exit_code": completed.returncode,
                    "output": str(_safe(output)),
                }
            except (OSError, subprocess.SubprocessError) as exc:
                result = {
                    "argv": argv,
                    "harness": relative,
                    "ok": False,
                    "exit_code": None,
                    "output": str(_safe(f"{type(exc).__name__}: {exc}")),
                }
            checked.append(result)
            if not result["ok"]:
                break

        healthy = all(item["ok"] for item in checked)
        payload = {
            "ok": healthy,
            "checked": checked,
            "cached": False,
            "message": (
                "Mission Control validation is healthy."
                if healthy
                else "Mission Control's own validator is failing. Repair the development "
                     "environment before assigning a coding agent."
            ),
        }
        with self._validation_probe_lock:
            self._validation_probe_cache[key] = payload
        return payload

    def sync(self) -> list[dict[str, Any]]:
        self.queue = sync_queue(self.store)
        return self.queue

    def work_state(self) -> dict[str, Any]:
        self.sync()
        return self.completion.work_state()

    def preflight(
        self,
        queue_id: int,
        *,
        selected_agent: str | None = None,
        reviewer: str | None = None,
        fallback_agents: list[str] | None = None,
        validation_commands: list[list[str]] | None = None,
        protected_paths_approved: bool = False,
        active_probe: bool = True,
        exclude_session_id: int | None = None,
    ) -> dict[str, Any]:
        self.sync()
        task = self.store.get_task(queue_id=queue_id)
        if not task:
            raise KeyError(f"Queue item #{queue_id} was not found.")
        if any(value is not None for value in (
            selected_agent, reviewer, fallback_agents, validation_commands,
        )):
            self.store.configure_task(
                queue_id,
                worker_profile_slug=str(selected_agent or task.get("worker_profile_slug") or "mc-native"),
                reviewer_profile_slug=str(reviewer or task.get("reviewer_profile_slug") or "reviewer-default"),
                fallback_profiles=(
                    fallback_agents if fallback_agents is not None
                    else json.loads(task.get("fallback_profiles_json") or "[]")
                ),
                validation_commands=(
                    validation_commands if validation_commands is not None
                    else json.loads(task.get("validation_commands_json") or "[]")
                ),
                owner_state="Ready",
            )
        return self.completion.preflight(
            queue_id,
            selected_agent=selected_agent,
            reviewer=reviewer,
            fallback_agents=fallback_agents,
            validation_commands=validation_commands,
            protected_paths_approved=protected_paths_approved,
            active_probe=active_probe,
            exclude_session_id=exclude_session_id,
        )

    def evaluate_goal(self, goal_id: int) -> dict[str, Any]:
        return self.completion.evaluate_goal(goal_id)

    def link_goal(self, goal_id: int, queue_id: int) -> dict[str, Any]:
        goal = self.store.get_goal(goal_id)
        task = self.store.get_task(queue_id=queue_id)
        if not goal:
            raise KeyError(goal_id)
        if not task or bool(task.get("legacy_hidden")):
            raise KeyError(queue_id)
        return self.store.link_goal_task(goal_id, int(task["id"]))

    def run_history(self, **filters: Any) -> list[dict[str, Any]]:
        return self.completion.history(**filters)

    def run_scorecard(self, session_id: int) -> dict[str, Any]:
        return self.completion.build_scorecard(session_id)

    def create_workflow(
        self,
        queue_id: int,
        *,
        idempotency_key: str | None = None,
        readiness_id: int | None = None,
    ) -> dict[str, Any]:
        self.sync()
        task = self.store.get_task(queue_id=queue_id)
        if not task:
            raise KeyError(f"Queue item #{queue_id} was not found.")
        readiness = self.store.get_readiness(readiness_id) if readiness_id else None
        if readiness:
            payload = readiness.get("payload") or {}
            if int(readiness["task_id"]) != int(task["id"]):
                raise RuntimeError("Readiness snapshot belongs to another Queue item.")
            if readiness["status"] != "ready" or not payload.get("ready"):
                raise RuntimeError("Readiness blockers must be resolved before Start.")
            if readiness["policy_hash"] != self.policy.hash or payload.get("plan_hash") != task.get("plan_hash"):
                raise RuntimeError("Readiness snapshot is stale. Run preflight again.")
        else:
            payload = self.completion.preflight(queue_id)
            readiness_id = int(payload["readiness_id"])
            if not payload["ready"]:
                detail = "; ".join(item["message"] for item in payload["blockers"][:4])
                raise RuntimeError(f"Queue item is not ready: {detail}")
        target_version = task.get("target_version") or self._next_version(queue_id)
        self.store.approve_task_for_workflow(int(task["id"]), target_version)
        session = self.store.create_session(
            int(task["id"]), self.policy.hash, idempotency_key or str(uuid.uuid4()),
            plan_hash_snapshot=task["plan_hash"],
            criteria_snapshot=json.loads(task.get("acceptance_criteria_json") or "[]"),
            validation_commands=payload.get("validation_commands") or self.policy.mandatory_checks(),
            worker_profile_slug=str(payload.get("selected_agent") or task.get("worker_profile_slug") or "mc-native"),
            reviewer_profile_slug=str(payload.get("reviewer") or task.get("reviewer_profile_slug") or "reviewer-default"),
            sprint_budget=self.assessor._budget(str(task.get("risk") or "medium")).to_dict(),
            readiness_snapshot_id=readiness_id,
        )
        self.store.add_stages(int(session["id"]), STAGES)
        self.releases.reserve(target_version, queue_id, risk=task.get("risk") or "medium")
        self._event(int(session["id"]), "workflow_approved", {
            "queue_id": queue_id, "plan_path": task["plan_path"], "plan_hash": task["plan_hash"],
            "policy_hash": self.policy.hash, "target_version": target_version,
            "readiness_id": readiness_id,
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
        goal = self.store.create_goal(
            title=title,
            objective=objective,
            acceptance_criteria=acceptance_criteria,
            validation_commands=[],
            autonomy="sandbox",
            preferred_models=[],
            max_iterations=1,
            worker_profile_slug="",
            reviewer_profile_slug="",
            assessment=None,
            budget=None,
            status="active",
        )
        return self.completion.evaluate_goal(int(goal["id"]))

    def create_goal_workflow(self, goal_id: int) -> dict[str, Any]:
        if not self.store.get_goal(goal_id):
            raise KeyError(goal_id)
        raise RuntimeError(
            "Goals describe outcomes and never execute. Link the Goal to a Ready Queue item, then start that item."
        )

    def restart_stale_workflow(self, session_id: int, *, background: bool = True) -> dict[str, Any]:
        session = self.get_workflow(session_id)
        error_code = str(session.get("error_code") or "")
        if error_code not in STALE_SNAPSHOT_ERRORS:
            raise RuntimeError("Only a workflow with a stale policy or plan snapshot can be restarted.")
        if session["state"] not in {"paused", "blocked", "failed"}:
            raise RuntimeError(f"Workflow cannot restart from state {session['state']}.")

        task = self.store.get_task(task_id=int(session["task_id"]))
        if not task:
            raise RuntimeError("The development task for this workflow no longer exists.")
        prior_readiness = session.get("readiness") or {}
        prior_payload = prior_readiness.get("payload") or {}
        readiness = self.preflight(
            int(task["queue_id"]),
            selected_agent=str(session.get("worker_profile_slug") or "mc-native"),
            reviewer=str(session.get("reviewer_profile_slug") or "reviewer-default"),
            fallback_agents=json.loads(task.get("fallback_profiles_json") or "[]"),
            validation_commands=json.loads(task.get("validation_commands_json") or "[]"),
            protected_paths_approved=bool(prior_payload.get("protected_paths")),
            exclude_session_id=session_id,
        )
        if not readiness["ready"]:
            detail = "; ".join(item["message"] for item in readiness["blockers"][:4])
            raise RuntimeError(f"Updated workflow is not ready: {detail}")

        criteria = json.loads(task.get("acceptance_criteria_json") or "[]")
        self.store.reset_stages_for_replan(
            session_id, has_worktree=bool(session.get("worktree"))
        )
        self.store.update_session(
            session_id,
            state="paused" if session.get("worktree") else "approved",
            stage="code" if session.get("worktree") else "approved",
            policy_hash=self.policy.hash,
            plan_hash_snapshot=task["plan_hash"],
            criteria_snapshot_json=json.dumps(criteria, separators=(",", ":")),
            validation_commands_json=json.dumps(readiness["validation_commands"], separators=(",", ":")),
            readiness_snapshot_id=int(readiness["readiness_id"]),
            blocker=None,
            error_code=None,
            cancel_requested=0,
            completed_at=None,
        )
        self._sync_progress(session_id)
        self._event(session_id, "workflow_restarted", {
            "same_run": True,
            "reason": error_code,
            "policy_hash": self.policy.hash,
            "plan_hash": task["plan_hash"],
            "worktree_preserved": bool(session.get("worktree")),
        }, actor="owner")
        return self.start_background(session_id) if background else self.run_to_gate(session_id)

    @staticmethod
    def _next_version(queue_id: int) -> str:
        return "3.0.0" if queue_id == 18 else f"3.{queue_id}.0"

    def _latest_checkpoint_summary(self, session_id: int) -> list[dict[str, Any]]:
        """The newest checkpoint only, with its handoff reduced to the readable fields.

        Twenty checkpoints per workflow were being returned in full, and a handoff carries a
        `recent_events` dump -- the largest one in this database is 1.13 MB. That made the
        overview response 5.2 MB, growing with every run, until the page could not finish
        loading inside its own timeout. Mission Control renders one checkpoint and reads four
        fields off it: sequence, status, head_sha, and the handoff's next_action.

        Still a list, because that is the shape callers expect. The complete history stays at
        GET /workflows/{id}/checkpoints for anyone who needs it.
        """
        latest = self.store.latest_checkpoint(session_id)
        if not latest:
            return []
        handoff = latest.get("handoff")
        if not isinstance(handoff, dict):
            try:
                handoff = json.loads(latest.get("handoff_json") or "{}")
            except (TypeError, ValueError):
                handoff = {}
        summary = {key: handoff.get(key) for key in ("status", "stage", "next_action")
                   if handoff.get(key) is not None}
        return [{
            "id": latest.get("id"), "session_id": session_id,
            "worker_session_id": latest.get("worker_session_id"),
            "sequence": latest.get("sequence"), "status": latest.get("status"),
            "head_sha": latest.get("head_sha"), "created_at": latest.get("created_at"),
            "handoff_json": json.dumps(summary, ensure_ascii=True, separators=(",", ":")),
        }]

    def get_workflow(self, session_id: int) -> dict[str, Any]:
        session = self.store.get_session(session_id)
        if not session:
            raise KeyError(session_id)
        timing = self.store.stage_attempt_timing(session_id)
        session["active_seconds"] = timing["active_seconds"]
        session["active_timer_started_at"] = (
            timing["timer_started_at"] if session["state"] in ACTIVE_STATES else None
        )
        session["stages"] = self.store.list_stages(session_id)
        session["checkpoints"] = self._latest_checkpoint_summary(session_id)
        session["worker_session"] = self.store.latest_worker_session(session_id)
        session["sprint"] = self.store.get_sprint(int(session["current_sprint_id"])) if session.get("current_sprint_id") else None
        session["assessment"] = self.store.get_assessment(int(session["assessment_id"])) if session.get("assessment_id") else None
        session["readiness"] = (
            self.store.get_readiness(int(session["readiness_snapshot_id"]))
            if session.get("readiness_snapshot_id") else None
        )
        session["evidence"] = self.store.list_evidence(session_id=session_id)
        session["scorecard"] = self.store.get_scorecard(session_id)
        conn = self.store.connect()
        try:
            pr = conn.execute("SELECT * FROM coding_pull_requests WHERE task_id=?", (session["task_id"],)).fetchone()
            session["pull_request"] = dict(pr) if pr else None
        finally:
            conn.close()
        statuses = {item["node_id"]: item["status"] for item in session["stages"]}
        session["delivery"] = self._delivery(session, statuses)
        # Derived here as well as stored by _sync_progress. The stored column is only written
        # on a state transition, so a run that finished under the old hardcoded scheme would
        # otherwise keep reporting the gate number it stopped at.
        session["progress"] = workflow_progress(
            statuses, self.policy.data.get("capabilities", {}),
            delivered=bool(session["delivery"]["reachable"]),
        )
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
                "qualification": self.policy.implementer_qualification(profile.adapter),
            }}
            if probe:
                item = {
                    **self.worker.probe(profile.slug),
                    "qualification": self.policy.implementer_qualification(profile.adapter),
                }
            profiles.append(item)
        return profiles

    def switch_worker(self, session_id: int, profile_slug: str) -> dict[str, Any]:
        session = self.get_workflow(session_id)
        if session["state"] not in {"paused", "blocked", "failed", "approved"}:
            raise RuntimeError("A worker can only be switched at a paused checkpoint.")
        row = self.store.get_worker_profile(profile_slug)
        if not row or not bool(row["enabled"]) or row["adapter"] == "model_review":
            raise ValueError("Selected coding worker profile is unavailable.")
        if row["adapter"] not in self.policy.qualified_implementer_adapters():
            raise ValueError(
                "Selected coding worker is reserved for future development. Use Codex."
            )
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
        self.store.reset_stages_for_worker_switch(session_id)
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

    def process_settings(self) -> dict[str, Any]:
        from core import owner_flags
        return {"auto_queue": owner_flags.get_bool("developer.auto_queue", False)}

    def set_auto_queue(self, enabled: bool) -> dict[str, Any]:
        from core import owner_flags
        owner_flags.set_bool("developer.auto_queue", enabled)
        next_workflow = self.start_next_queued() if enabled else None
        return {"auto_queue": enabled, "next_workflow": next_workflow}

    def acceptance_status(self, session_id: int | None = None) -> dict[str, Any]:
        scenarios = [
            {
                "id": "worker_failure",
                "label": "Fail selected agent once",
                "description": "Pause one Code attempt and preserve its checkpoint for retry or switch.",
            },
            {
                "id": "worker_hang",
                "label": "Hang worker",
                "description": "Emit the no-output warning and enter structured recovery.",
            },
            {
                "id": "restart_checkpoint",
                "label": "Restart checkpoint",
                "description": "Pause at a durable checkpoint so backend restart recovery can be verified.",
            },
            {
                "id": "main_drift",
                "label": "Safe main drift",
                "description": "Exercise base reconciliation before the workflow pushes.",
            },
        ]
        return {
            "enabled": os.getenv("TOBI_CODING_ACCEPTANCE_MODE", "").strip() == "1",
            "workflow_id": session_id,
            "scenarios": scenarios,
            "faults": self.store.list_acceptance_faults(session_id) if session_id else [],
        }

    def arm_acceptance_fault(self, session_id: int, scenario: str) -> dict[str, Any]:
        allowed = {"worker_failure", "worker_hang", "restart_checkpoint", "main_drift"}
        if scenario not in allowed:
            raise ValueError("Unsupported acceptance scenario.")
        workflow = self.get_workflow(session_id)
        if workflow["state"] in TERMINAL_STATES:
            raise RuntimeError("Acceptance faults can only target an unfinished workflow.")
        fault = self.store.arm_acceptance_fault(session_id, scenario)
        self._event(
            session_id,
            "acceptance_fault_armed",
            {"scenario": scenario, "fault_id": fault["id"]},
            actor="owner",
        )
        return self.acceptance_status(session_id)

    # ── owner queue preferences (Queue tab: Next slot + priority order) ──────
    # Stored as owner_settings strings so no schema change is needed. The QUEUE.md
    # sync stays canonical for item content/status; these only order planned items.
    def _queue_prefs(self) -> tuple[list[int], int | None]:
        from core import owner_flags
        try:
            order = [int(x) for x in json.loads(owner_flags.get_str("developer.queue_order", "[]") or "[]")]
        except (ValueError, TypeError):
            order = []
        raw_next = (owner_flags.get_str("developer.queue_next", "") or "").strip()
        next_id = int(raw_next) if raw_next.isdigit() else None
        return order, next_id

    def _save_queue_prefs(self, order: list[int], next_id: int | None) -> None:
        from core import owner_flags
        owner_flags.set_str("developer.queue_order", json.dumps(list(order)))
        owner_flags.set_str("developer.queue_next", str(next_id) if next_id else "")

    def _queue_items_with_execution(
        self, tasks: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        by_id = {int(task["queue_id"]): task for task in tasks}
        projected: list[dict[str, Any]] = []
        for source in tasks:
            task = dict(source)
            execution_state = task_execution_state(task)
            blockers: list[str] = []
            if execution_state == "blocked":
                blockers.append(str(task.get("queue_status") or "Owner action is required."))
            elif execution_state == "in_progress":
                blockers.append("This item is already in progress.")
            elif execution_state == "done":
                blockers.append("This item is already completed.")
            elif str(task.get("status") or "") != "planned":
                blockers.append(
                    f"This item is {str(task.get('status') or 'not ready').replace('_', ' ')}."
                )

            try:
                dependencies = [
                    int(value) for value in json.loads(task.get("dependencies_json") or "[]")
                ]
            except (TypeError, ValueError, json.JSONDecodeError):
                dependencies = []
                blockers.append("The dependency list is invalid.")
            for dependency_id in dependencies:
                dependency = by_id.get(dependency_id) or self.store.get_task(
                    queue_id=dependency_id
                )
                if not dependency or str(dependency.get("status") or "") != "completed":
                    blockers.append(f"Queue item #{dependency_id} must be completed first.")

            task["execution_state"] = execution_state
            task["start_blockers"] = blockers
            task["can_start"] = execution_state == "ready" and not blockers
            projected.append(task)
        return projected

    def queue_state(self) -> dict[str, Any]:
        """Queue items plus the owner's Next slot + priority order, normalized so
        stale ids (started/completed/removed items) silently drop out."""
        from core import owner_flags
        # sync() returns every QUEUE.md row's upsert result — including rows the
        # owner removed (status=deleted, preserved by the upsert). Hide those.
        items = self._queue_items_with_execution([
            task for task in self.sync() if task.get("status") != "deleted"
        ])
        planned = {int(t["queue_id"]) for t in items if t.get("status") == "planned"}
        startable = {int(t["queue_id"]) for t in items if t.get("can_start")}
        order, next_id = self._queue_prefs()
        if next_id not in startable:
            next_id = None
        order = [qid for qid in order if qid in planned and qid != next_id]
        from core.coding_queue_authoring import queue_hash
        return {"items": items, "order": order, "next_queue_id": next_id,
                "auto_queue": owner_flags.get_bool("developer.auto_queue", False),
                "queue_hash": queue_hash()}

    def set_queue_order(self, order: list[int], next_queue_id: int | None) -> dict[str, Any]:
        items = self._queue_items_with_execution(self.sync())
        planned = {int(t["queue_id"]) for t in items if t.get("status") == "planned"}
        startable = {int(t["queue_id"]) for t in items if t.get("can_start")}
        if next_queue_id is not None and int(next_queue_id) not in startable:
            raise KeyError(f"Queue item #{next_queue_id} is not ready to start.")
        cleaned: list[int] = []
        for qid in order:
            qid = int(qid)
            if qid not in planned:
                raise KeyError(f"Queue item #{qid} is not a planned item.")
            if qid != next_queue_id and qid not in cleaned:
                cleaned.append(qid)
        self._save_queue_prefs(cleaned, int(next_queue_id) if next_queue_id else None)
        return self.queue_state()

    def restore_task(self, queue_id: int) -> dict[str, Any]:
        """Any item that is off the queue → planned ('push back to queue').

        This used to accept `completed` only, which left a dead zone. Starting a run moves a
        task to `approved`, and nothing moves it back unless the run merges and deploys. A
        run that finished locally, was canceled, or failed therefore left its item invisible:
        gone from the Queue, absent from the Completed list, and refused by this method --
        reachable only as a History row with no action on it.

        The live-run guard replaces the status check. Requeueing a task while its workflow is
        still executing would let the owner start a second run against the same item.
        """
        task = self.store.get_task(queue_id=int(queue_id))
        if not task:
            raise KeyError(f"Queue item #{queue_id} was not found.")
        if task["status"] == "planned":
            return self.queue_state()
        if task["status"] == "deleted":
            raise ValueError(f"Queue item #{queue_id} was deleted. Restore it from QUEUE.md.")
        live = self.store.active_session_for_task(int(task["id"]))
        if live:
            raise ValueError(
                f"Queue item #{queue_id} has workflow {live} running. Stop it before requeueing."
            )
        self.store.set_task_status(int(queue_id), "planned", override_source=True)
        # Clear the owner state too. A canceled item kept owner_state='Canceled', so even once
        # it was back in the queue the Work list would still label it as stopped.
        self._set_task_owner_state(int(task["id"]), "Ready")
        return self.queue_state()

    def remove_task(self, queue_id: int) -> dict[str, Any]:
        """Completed → deleted (hidden from the queue; the QUEUE.md row is untouched
        and a re-sync never resurrects it because upsert preserves status)."""
        task = self.store.get_task(queue_id=int(queue_id))
        if not task:
            raise KeyError(f"Queue item #{queue_id} was not found.")
        # Mirrors restore_task: any item that is off the queue can be removed, gated on there
        # being no live run rather than on the status being exactly 'completed'. Requiring
        # 'completed' meant an item stranded at 'approved' could be neither requeued nor
        # deleted -- it simply stayed in the list forever. An item still in the queue is
        # deliberately still refused; removing it is the queue owner's edit, not this action.
        if task["status"] == "deleted":
            return self.queue_state()
        if task["status"] == "planned":
            raise ValueError(f"Queue item #{queue_id} is still in the queue. Requeue is for items that left it.")
        live = self.store.active_session_for_task(int(task["id"]))
        if live:
            raise ValueError(
                f"Queue item #{queue_id} has workflow {live} running. Stop it before removing."
            )
        self.store.set_task_status(int(queue_id), "deleted", override_source=True)
        return self.queue_state()

    def plan_markdown(self, queue_id: int) -> dict[str, Any]:
        """The raw Markdown of the item's plan file for the Plan Detail modal.
        Path is re-validated (inside the repo, .md only) before reading."""
        task = self.store.get_task(queue_id=int(queue_id))
        if not task:
            raise KeyError(f"Queue item #{queue_id} was not found.")
        plan_path = (REPO_ROOT / task["plan_path"]).resolve()
        if not plan_path.is_relative_to(REPO_ROOT) or plan_path.suffix.lower() != ".md":
            raise ValueError(f"Queue item #{queue_id} has an unsafe plan path.")
        if not plan_path.is_file():
            raise KeyError(f"Plan file for #{queue_id} was not found: {task['plan_path']}")
        markdown = plan_path.read_text(encoding="utf-8", errors="replace")[:400_000]
        return {"queue_id": int(queue_id), "plan_path": task["plan_path"],
                "title": task["title"], "markdown": markdown}

    def start_next_queued(self) -> dict[str, Any] | None:
        """Start one eligible planned queue item; never skip an active or blocked run."""
        from core import owner_flags
        if not owner_flags.get_bool("developer.auto_queue", False):
            return None
        with self._auto_queue_lock:
            active_states = {
                "approved", "preparing", "coding", "validating", "reviewing", "pushed",
                "merging", "deploying", "paused", "blocked", "awaiting_merge_deploy_approval",
                "failed",
            }
            if any(item["state"] in active_states for item in self.list_workflows(200)):
                return None
            # Owner ordering (Queue tab): the Next slot wins, then the priority
            # list, then remaining items in QUEUE.md file order.
            tasks = self._queue_items_with_execution(self.sync())
            order, next_id = self._queue_prefs()
            file_pos = {int(t["queue_id"]): i for i, t in enumerate(tasks)}

            def _rank(task: dict[str, Any]) -> tuple[int, int]:
                qid = int(task["queue_id"])
                if qid == next_id:
                    return (0, 0)
                if qid in order:
                    return (1, order.index(qid))
                return (2, file_pos[qid])

            for task in sorted(tasks, key=_rank):
                if not task.get("can_start"):
                    continue
                dependencies = json.loads(task.get("dependencies_json") or "[]")
                if any(
                    not (dependency := self.store.get_task(queue_id=int(queue_id)))
                    or dependency.get("status") != "completed"
                    for queue_id in dependencies
                ):
                    continue
                readiness = self.preflight(int(task["queue_id"]), active_probe=False)
                if not readiness["ready"]:
                    codes = {str(item.get("code") or "") for item in readiness.get("blockers") or []}
                    system_blockers = {
                        "run_active", "plan_changed", "agent_disabled", "agent_unhealthy",
                        "reviewer_unavailable", "reviewer_unhealthy", "check_denied",
                        "github_app_unconfigured", "reviewer_model_unconfigured",
                        "reviewer_probe_failed",
                    }
                    if codes & system_blockers:
                        owner_flags.set_bool("developer.auto_queue", False)
                        return None
                    # Scope, dependency, protected-path, or item-specific blockers do not
                    # prevent an independent Ready item later in the owner-prioritized queue.
                    continue
                workflow = self.create_workflow(
                    int(task["queue_id"]), readiness_id=int(readiness["readiness_id"])
                )
                self._event(int(workflow["id"]), "auto_queue_started", {
                    "queue_id": task["queue_id"], "reason": "previous_workflow_completed",
                })
                started = self.start_background(int(workflow["id"]))
                # Shift the owner's pointers: promoted Next → priority #1 becomes
                # the new Next; a started list item just leaves the list. Only
                # still-planned ids survive the shift (stale ids drop out).
                qid = int(task["queue_id"])
                planned_left = [x for x in order
                                if x != qid and file_pos.get(x) is not None
                                and tasks[file_pos[x]].get("status") == "planned"]
                if qid == next_id:
                    self._save_queue_prefs(planned_left[1:] if planned_left else [],
                                           planned_left[0] if planned_left else None)
                else:
                    self._save_queue_prefs(planned_left,
                                           next_id if qid != next_id else None)
                return started
        return None

    def _event(self, session_id: int, event_type: str, payload: dict[str, Any], actor: str = "tobi") -> None:
        stored_event = self.store.append_event(session_id, event_type, _safe(payload), actor=actor)
        current = self.store.get_session(session_id)
        if current and current.get("stage"):
            self.store.heartbeat_stage_attempt(
                session_id,
                str(current["stage"]),
                output=event_type.startswith("worker_") and event_type != "worker_heartbeat",
            )
        if current:
            try:
                mirror = self.runtime_coding.mirror(current, stored_event)
                if not mirror.ok:
                    self.store.append_event(
                        session_id,
                        "runtime_mirror_recovery_required",
                        {
                            "reason": mirror.reason,
                            "action": mirror.recovery_action,
                            "source_sequence": stored_event["sequence"],
                        },
                        actor="mission-control",
                    )
            except Exception:
                # Canonical history is additive; #22's accepted record always wins.
                pass

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
        payload = dict(evidence or {})
        stage_row = next(
            (
                item for item in self.store.list_stages(session_id)
                if item["node_id"] == stage
            ),
            None,
        )
        if stage_row:
            payload.setdefault("attempt", int(stage_row.get("attempts") or 0))
        self.learning.record(
            session_id=session_id,
            outcome=outcome,
            stage=stage,
            error_code=error_code,
            worker_profile=str(session.get("worker_profile_slug") or ""),
            evidence=_safe(payload),
        )

    def _delivery(self, session: dict[str, Any], stage_statuses: dict[str, str]) -> dict[str, Any]:
        """Whether this run produced something the owner can open, and how to reach it.

        Keyed on the commit gate, not on `head_sha`: `prepare` seeds `head_sha` with the
        branch point, so every run has one from the moment its worktree exists. Three runs
        canceled during coding still carried a `head_sha` identical to their `base_sha`.
        Only a completed commit gate means this run's work is in the object store.

        Reads no git and no network. `get_workflow` calls this once per workflow in the
        overview listing, so anything expensive here would be paid fifty times over; the
        diff is fetched lazily by the Delivery panel from /workflows/{id}/changes.
        """
        # `pull_request` is attached by get_workflow, not by store.get_session, so it only
        # describes the result. Reachability comes from the stage table, which both have.
        pull_request = session.get("pull_request") or {}
        branch, head_sha = session.get("branch"), session.get("head_sha")
        committed = (
            stage_statuses.get("commit") == "completed"
            or session.get("state") in {"completed", "merged"}
        )
        if pull_request.get("url") and committed:
            state = str(pull_request.get("merge_state") or "")
            # GitHub exposes a provisional merge_commit_sha for open pull requests. It is
            # the test merge ref, not evidence that the pull request was actually merged.
            if pull_request.get("merged_at") or state == "merged":
                state = "merged"
            allowed = ["open_pull_request"]
            if session.get("state") == "awaiting_owner_merge":
                allowed.append("sync_delivery")
            return {
                "reachable": True,
                "kind": "pull_request",
                "branch": branch,
                "head_sha": head_sha,
                "url": pull_request.get("url"),
                "state": state or ("draft" if pull_request.get("draft") else "open"),
                "draft": bool(pull_request.get("draft")),
                "merged": state == "merged",
                "merge_commit_sha": pull_request.get("merge_commit_sha"),
                "ci_state": pull_request.get("ci_state"),
                "conflict_state": pull_request.get("conflict_state"),
                "updated_at": pull_request.get("updated_at"),
                "allowed_actions": allowed,
            }
        # A committed local branch is reachable: the worktree shares the repository's object
        # store, so the commit survives whether or not the worktree directory does.
        if committed:
            return {
                "reachable": True, "kind": "local_branch", "branch": branch,
                "head_sha": head_sha, "url": None, "state": "committed",
                "allowed_actions": [],
            }
        return {
            "reachable": False, "kind": "none", "branch": branch, "head_sha": None,
            "url": None, "state": "none", "allowed_actions": [],
        }

    def _sync_progress(self, session_id: int) -> None:
        """Recompute stored progress from the gates the policy permits.

        Stored rather than derived on read because the History tab reads raw session rows
        while the Process tab reads get_workflow(); deriving in only one of them is how the
        two ended up disagreeing about the same field.
        """
        session = self.store.get_session(session_id) or {}
        statuses = {item["node_id"]: item["status"] for item in self.store.list_stages(session_id)}
        progress = workflow_progress(
            statuses, self.policy.data.get("capabilities", {}),
            delivered=bool(self._delivery(session, statuses)["reachable"]),
        )
        self.store.update_session(session_id, progress=progress)

    def _stage_start(self, session_id: int, node_id: str, state: str) -> None:
        stage = next((s for s in self.store.list_stages(session_id) if s["node_id"] == node_id), None)
        attempts = int(stage["attempts"] if stage else 0) + 1
        self.store.update_stage(session_id, node_id, status="running", attempts=attempts, started_at=utc_now())
        self.store.update_session(session_id, state=state, stage=node_id, blocker=None, error_code=None)
        self._sync_progress(session_id)
        session = self.store.get_session(session_id) or {}
        self.store.start_stage_attempt(
            session_id, node_id, attempts, str(session.get("worker_profile_slug") or "") or None
        )
        self._set_task_owner_state(int(session.get("task_id") or 0), "Running")
        self._event(session_id, "stage_started", {"stage": node_id, "attempt": attempts})

    def _stage_complete(self, session_id: int, node_id: str, result: dict[str, Any] | None = None) -> None:
        safe_result = _safe(result or {})
        self.store.update_stage(session_id, node_id, status="completed", result_json=safe_result, completed_at=utc_now())
        self.store.finish_stage_attempt(session_id, node_id, status="completed", result=safe_result)
        self._sync_progress(session_id)
        session = self.store.get_session(session_id)
        if session:
            self.completion.record_stage_evidence(session, node_id, safe_result)
        self._event(session_id, "stage_completed", {"stage": node_id, "result": safe_result})

    def _pause(
        self,
        session_id: int,
        stage: str,
        blocker: str,
        code: str,
        *,
        evidence: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        blocker = str(_safe(blocker))
        learning_evidence = dict(evidence or {})
        fingerprint = str(
            learning_evidence.get("failure_fingerprint")
            or failure_detail_signature(stage, code, blocker)
        )
        learning_evidence["failure_fingerprint"] = fingerprint
        learning_evidence.setdefault("blocker", blocker)
        if (
            code in REPEAT_GUARDED_ERRORS
            and self.learning.failure_count(session_id, fingerprint) >= 1
        ):
            return self._block(
                session_id,
                stage,
                "The same failure returned after one correction attempt. TOBI stopped "
                "before spending another worker cycle. Revise the item, switch agent, or "
                "repair the development environment.",
                "repeated_failure",
                evidence={
                    **learning_evidence,
                    "original_error_code": code,
                    "repeat_guard": True,
                },
            )
        current = next((item for item in self.store.list_stages(session_id) if item["node_id"] == stage), None)
        if current and current["status"] != "completed":
            self.store.update_stage(session_id, stage, status="paused", result_json={"error_code": code})
            self.store.finish_stage_attempt(
                session_id, stage, status="paused", error_code=code, result={"blocker": blocker}
            )
        self.store.update_session(session_id, state="paused", stage=stage, blocker=blocker, error_code=code)
        session = self.store.get_session(session_id) or {}
        self._set_task_owner_state(int(session.get("task_id") or 0), "Paused")
        self._event(session_id, "workflow_paused", {"stage": stage, "error_code": code, "action": blocker})
        self._checkpoint(session_id, status="paused", next_action=blocker)
        self._record_learning(
            session_id, outcome="paused", stage=stage, error_code=code,
            evidence=learning_evidence,
        )
        return self.get_workflow(session_id)

    def _local_complete(self, session_id: int, reason: str, code: str) -> dict[str, Any]:
        """Terminal success at the GitHub boundary — every stage the policy allows has passed.

        Distinct from `_pause` because nothing failed and nothing is waiting on the owner:
        the reviewed policy simply does not permit remote mutation, so this workflow is
        finished rather than interrupted. Treating it as a pause made a clean local run
        indistinguishable from a fault in the stored data, since both wrote `state=paused`
        with an `error_code` and neither produced a scorecard.

        It is genuinely terminal. Granting the missing capability edits the policy, which
        changes `policy_hash`, and `_run_to_gate` refuses to resume any workflow whose
        stored hash no longer matches — so continuing this same run was never reachable
        from here. The owner picks the work back up with a fresh workflow.

        A scorecard is written, which previously only existed for merged-and-deployed runs.
        The queue item is returned to `Ready` rather than `Done`: the branch is committed
        locally but nothing has shipped, so the item must stay visible and actionable.
        """
        reason = str(_safe(reason))
        self.store.update_session(session_id, state="locally_complete", stage="push",
                                  blocker=reason, error_code=code, completed_at=utc_now())
        self._sync_progress(session_id)
        session = self.store.get_session(session_id) or {}
        self._set_task_owner_state(int(session.get("task_id") or 0), "Ready")
        self._event(session_id, "workflow_locally_complete",
                    {"stage": "push", "error_code": code, "action": reason})
        self._checkpoint(session_id, status="locally_complete", next_action=reason)
        self._record_learning(
            session_id, outcome="locally_complete", stage="push", error_code=code,
            evidence={"reason": reason, "head_sha": session.get("head_sha"),
                      "branch": session.get("branch")},
        )
        self.completion.build_scorecard(session_id)
        return self.get_workflow(session_id)

    def _block(
        self,
        session_id: int,
        stage: str,
        blocker: str,
        code: str,
        *,
        evidence: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        blocker = str(_safe(blocker))
        self.store.update_stage(session_id, stage, status="failed", result_json={"error_code": code})
        self.store.finish_stage_attempt(
            session_id, stage, status="failed", error_code=code, result={"blocker": blocker}
        )
        self.store.update_session(session_id, state="blocked", stage=stage, blocker=blocker, error_code=code)
        session = self.store.get_session(session_id) or {}
        self._set_task_owner_state(int(session.get("task_id") or 0), "Needs Action")
        self._event(session_id, "workflow_blocked", {"stage": stage, "error_code": code, "action": blocker})
        self._checkpoint(session_id, status="blocked", next_action=blocker)
        self._record_learning(
            session_id, outcome="blocked", stage=stage, error_code=code,
            evidence={**(evidence or {}), "blocker": blocker},
        )
        self.completion.build_scorecard(session_id)
        return self.get_workflow(session_id)

    def _set_task_owner_state(self, task_id: int, owner_state: str) -> None:
        if task_id <= 0:
            return
        self.store.set_task_owner_state(task_id, owner_state)

    def _run_worker_with_heartbeat(
        self, session_id: int, brief: dict[str, Any], worker_event
    ) -> dict[str, Any]:
        stop = threading.Event()
        started_at = utc_now()
        heartbeat_seconds = max(1, self.policy.limit("heartbeat_seconds", 5))
        warning_seconds = max(heartbeat_seconds, self.policy.limit("no_output_warning_seconds", 90))

        def pulse() -> None:
            warned = False
            while not stop.wait(heartbeat_seconds):
                current = self.store.get_session(session_id) or {}
                if current.get("state") not in ACTIVE_STATES:
                    return
                self._event(session_id, "worker_heartbeat", {"stage": "code"})
                last_output = str(current.get("last_output_at") or "")
                stage = next(
                    (item for item in self.store.list_stages(session_id) if item["node_id"] == "code"), {}
                )
                stage_started = str(stage.get("started_at") or started_at)
                reference = last_output if last_output > stage_started else stage_started
                try:
                    silent_for = (datetime.now(timezone.utc) - datetime.fromisoformat(reference)).total_seconds()
                except ValueError:
                    silent_for = 0
                if silent_for >= warning_seconds and not warned:
                    warned = True
                    self._event(session_id, "worker_no_output_warning", {
                        "stage": "code", "silent_seconds": round(silent_for),
                        "message": "Agent is alive but has not produced output within the health window.",
                    })

        monitor = threading.Thread(target=pulse, name=f"coding-heartbeat-{session_id}", daemon=True)
        monitor.start()
        try:
            return self.worker.run(
                session_id, "code", str(brief["worktree"]), brief, on_event=worker_event,
                cancel_check=lambda: bool((self.store.get_session(session_id) or {}).get("cancel_requested")),
            )
        finally:
            stop.set()
            monitor.join(timeout=heartbeat_seconds + 1)

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
                self._stage_start(session_id, "prepare", "preparing")
                prepared = self.git.prepare(session_id, session.get("target_version") or "3.0.0", session["title"])
                self.store.update_session(session_id, **prepared)
                self._stage_complete(session_id, "prepare", prepared)

            session = self.get_workflow(session_id)
            statuses = {item["node_id"]: item["status"] for item in session["stages"]}
            if statuses.get("index") != "completed":
                self._stage_start(session_id, "index", "preparing")
                snapshot = self.index.build(Path(session["worktree"]))
                self._stage_complete(session_id, "index", snapshot)

            session = self.get_workflow(session_id)
            statuses = {item["node_id"]: item["status"] for item in session["stages"]}
            if statuses.get("code") != "completed":
                self._stage_start(session_id, "code", "coding")
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
                    "learned_playbooks": self.learning.applicable(
                        worker_profile=str(session.get("worker_profile_slug") or "mc-native"),
                        session_id=session_id,
                    ),
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

                if self.store.consume_acceptance_fault(session_id, "worker_failure"):
                    self._event(
                        session_id,
                        "acceptance_fault_triggered",
                        {"scenario": "worker_failure", "stage": "code"},
                    )
                    return self._pause(
                        session_id,
                        "code",
                        "Acceptance fault: selected agent failed once. Retry or switch agents.",
                        "acceptance_worker_failure",
                    )
                if self.store.consume_acceptance_fault(session_id, "worker_hang"):
                    self._event(
                        session_id,
                        "worker_no_output_warning",
                        {
                            "stage": "code",
                            "scenario": "acceptance_worker_hang",
                            "message": "Acceptance fault: the worker stopped producing output.",
                        },
                    )
                    return self._pause(
                        session_id,
                        "code",
                        "Worker unresponsive. Retry the same checkpoint or switch agents.",
                        "worker_unresponsive",
                    )
                if self.store.consume_acceptance_fault(session_id, "restart_checkpoint"):
                    self._event(
                        session_id,
                        "acceptance_fault_triggered",
                        {"scenario": "restart_checkpoint", "stage": "code"},
                    )
                    return self._pause(
                        session_id,
                        "code",
                        "Acceptance checkpoint is ready. Restart the backend, then resume this run.",
                        "acceptance_restart_ready",
                    )
                try:
                    result = self._run_worker_with_heartbeat(session_id, brief, worker_event)
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
                failed_check = next(
                    (check for check in checks if not check["ok"]),
                    None,
                )
                if failed_check:
                    failure_evidence = {
                        "argv": failed_check.get("argv"),
                        "output": failed_check.get("output"),
                        "failure_kind": failed_check.get("failure_kind") or "task",
                        "failure_fingerprint": failed_check.get("failure_fingerprint"),
                    }
                    if failed_check.get("failure_kind") == "infrastructure":
                        return self._block(
                            session_id,
                            "validate",
                            "Mission Control could not run a healthy validation environment. "
                            "Repair the missing runtime or dependency, then resume from this checkpoint.",
                            "validation_infrastructure_failed",
                            evidence=failure_evidence,
                        )
                    cycles = int(session.get("validation_cycles") or 0) + 1
                    self.store.update_session(session_id, validation_cycles=cycles)
                    if cycles > self.policy.limit("max_review_cycles", 2):
                        return self._block(
                            session_id,
                            "validate",
                            "Validation failed after the maximum correction cycles. Owner action is required.",
                            "review_cycles_exhausted",
                            evidence=failure_evidence,
                        )
                    return self._pause(
                        session_id,
                        "validate",
                        "Validation failed. Review the failed check evidence, then retry the workflow.",
                        "validation_failed",
                        evidence=failure_evidence,
                    )

            session = self.get_workflow(session_id)
            statuses = {item["node_id"]: item["status"] for item in session["stages"]}
            if statuses.get("review") != "completed":
                self._stage_start(session_id, "review", "reviewing")
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
                        file_evidence=self.git.changed_file_evidence(
                            session["worktree"], diff["files"]
                        ),
                    )
                except CodingReviewError as exc:
                    return self._pause(session_id, "review", str(exc), "review_unavailable")
                self._artifact(session_id, "review", {**diff, **review})
                if not review["qualified"]:
                    cycles = int(session.get("review_cycles") or 0) + 1
                    self.store.update_session(session_id, review_cycles=cycles)
                    self.store.update_stage(session_id, "review", status="failed", result_json=review,
                                            completed_at=utc_now())
                    reason = review["unmet"][0] if review.get("unmet") else review.get("summary")
                    blocker = "Acceptance review needs more evidence."
                    if reason:
                        blocker += f" {str(reason)[:700]}"
                    if cycles >= self.policy.limit("max_review_cycles", 2):
                        return self._block(
                            session_id, "review", blocker, "review_cycles_exhausted"
                        )
                    return self._pause(session_id, "review", blocker,
                                       "review_failed")
                self._stage_complete(session_id, "review", {**diff, **review})
            if statuses.get("commit") != "completed":
                self._stage_start(session_id, "commit", "reviewing")
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
                self._stage_start(session_id, "scan", "validating")
                findings = self.git.scan_secrets(session["worktree"], base_ref=session["base_sha"])
                if findings:
                    return self._pause(session_id, "scan", "Remove probable secrets and request a clean rescan.", "secret_found")
                self._stage_complete(session_id, "scan", {"findings": 0})

            session = self.get_workflow(session_id)
            statuses = {item["node_id"]: item["status"] for item in session["stages"]}
            if statuses.get("push") != "completed":
                goal = self.store.get_goal(int(session["goal_id"])) if session.get("goal_id") else None
                if goal and goal["autonomy"] == "sandbox":
                    return self._local_complete(session_id,
                                                "Goal met the local acceptance standard. Sandbox autonomy stops before GitHub mutation.",
                                                "autonomy_boundary")
                if not self.policy.feature_enabled("github"):
                    return self._local_complete(session_id,
                                                "Local branch is validated. Enable the GitHub capability in reviewed policy to push and create a draft PR.",
                                                "github_disabled")
                acceptance_drift = self.store.consume_acceptance_fault(session_id, "main_drift")
                current_base = self.git.default_branch_sha()
                if acceptance_drift or current_base != session.get("base_sha"):
                    if acceptance_drift:
                        self._event(
                            session_id,
                            "acceptance_fault_triggered",
                            {"scenario": "main_drift", "stage": "push"},
                        )
                    return self._pause(
                        session_id,
                        "push",
                        "The main branch changed after this run started. Reconcile the base before pushing.",
                        "main_drift",
                    )
                self._stage_start(session_id, "push", "pushed")
                self.git.push(session["worktree"], session["branch"])
                self._stage_complete(session_id, "push", {"branch": session["branch"]})
            if statuses.get("pull_request") != "completed":
                self._stage_start(session_id, "pull_request", "pushed")
                pr = self.github.create_draft_pr(
                    session["branch"], f"#{session['queue_id']} {session['title']}", self._pull_request_body(session_id),
                )
                self._save_pr(int(session["task_id"]), pr)
                self._stage_complete(session_id, "pull_request", pr)

            session = self.get_workflow(session_id)
            pr = session.get("pull_request") or {}
            merge_enabled = self.policy.feature_enabled("merge")
            deploy_enabled = self.policy.feature_enabled("deploy")
            if merge_enabled:
                action = "merge and deploy" if deploy_enabled else "merge"
                self.store.update_session(
                    session_id,
                    state="awaiting_merge_deploy_approval",
                    stage="merge_deploy",
                    blocker=f"Owner re-authentication is required to {action}.",
                )
                self._event(
                    session_id,
                    "approval_required",
                    {"purpose": "merge_deploy", "pull_request": pr, "action": action},
                )
            else:
                self.store.update_session(
                    session_id,
                    state="awaiting_owner_merge",
                    stage="merge_deploy",
                    blocker="Draft pull request is ready. Merge it on GitHub, then synchronize delivery.",
                )
                self._event(
                    session_id,
                    "delivery_waiting",
                    {"purpose": "owner_merge", "pull_request": pr},
                )
            self._sync_progress(session_id)
            self._record_learning(
                session_id, outcome="draft_pr", stage="pull_request",
                evidence={"pull_request": pr, "head_sha": session.get("head_sha")},
            )
            self.completion.build_scorecard(session_id)
            return self.get_workflow(session_id)
        except CodingWorkerUnavailable as exc:
            return self._pause(session_id, "code", str(exc), "worker_unavailable")
        except PolicyDenied as exc:
            code = "special_approval_required" if "protected" in str(exc).lower() else "policy_denied"
            return self._pause(session_id, self.get_workflow(session_id)["stage"], str(exc), code)
        except (GitCommandError, GitHubCodingError, subprocess.SubprocessError, OSError) as exc:
            return self._pause(session_id, self.get_workflow(session_id)["stage"], str(exc)[:1000], "external_step_failed")
        except Exception as exc:
            # The name of the exception class is not a diagnosis. Run 15 reported only
            # "TypeError" and finding it cost a full agent run; the traceback names the line
            # in one read. Kept as an event and an artifact so it survives in the trace.
            trace = traceback.format_exc()
            self._event(session_id, "internal_error", _safe({
                "error": f"{type(exc).__name__}: {exc}"[:2000], "traceback": trace[-8000:],
            }))
            self._artifact(session_id, "internal_error", {"traceback": trace[-20_000:]})
            return self._pause(session_id, self.get_workflow(session_id)["stage"],
                               f"Workflow stopped safely: {type(exc).__name__}: {exc}"[:500],
                               "internal_error")

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
        self.store.reset_stages_for_next_sprint(session_id)
        self.store.update_session(
            session_id,
            current_sprint_id=int(next_sprint["id"]),
            criteria_snapshot_json=json.dumps(criteria, ensure_ascii=True, separators=(",", ":")),
            sprint_budget_json=json.dumps(budget, ensure_ascii=True, separators=(",", ":")),
            validation_cycles=0,
            review_cycles=0,
            state="approved",
            stage="code",
            blocker=None,
            error_code=None,
        )
        self._sync_progress(session_id)
        self._event(session_id, "sprint_started", {
            "sprint_id": next_sprint["id"],
            "sequence": next_sprint["sequence"],
            "title": next_sprint["title"],
            "budget": budget,
        })
        return True

    @staticmethod
    def _check_unavailable(argv: list[str], worktree: Path) -> str:
        """Reason to skip a check whose prerequisites cannot exist in a worktree, else ''.

        A git worktree does not carry ignored directories, so `dashboard/node_modules` is
        absent from every run even though it exists in the main checkout. Running the node
        build there fails for want of a local `tsc`/`vite` no matter what the change was —
        and for a backend-only item it is wasted effort regardless. Skipping is recorded as
        an explicit `check_skipped` event so the gap is visible in the trace rather than
        silently counted as a pass.
        """
        if not argv:
            return ""
        tool = Path(argv[0]).name.lower().removesuffix(".cmd").removesuffix(".exe")
        if tool in {"npm", "npx", "pnpm", "yarn"}:
            if not (worktree / "dashboard" / "node_modules").is_dir():
                return ("skipped: dashboard/node_modules is absent from this worktree "
                        "(git worktrees do not carry ignored directories)")
        return ""

    def _validation_invocation(
        self,
        argv: list[str],
        worktree: Path,
        changed_files: set[str],
    ) -> tuple[list[str], dict[str, str] | None, str | None]:
        """Run stable platform checks from the control plane against worktree source.

        A retained worktree intentionally keeps its original branch snapshot. The validation
        contract, however, belongs to the live control plane. When the platform adds a schema
        migration, an old copy of the harness can reject the newer worktree code forever. Use
        the current trusted harness unless the sprint is explicitly changing that harness.
        """
        invocation = list(argv)
        if len(invocation) < 2:
            return invocation, None, None
        relative = str(invocation[1]).replace("\\", "/").lstrip("./")
        if relative not in CANONICAL_VALIDATION_HARNESSES or relative in changed_files:
            return invocation, None, None
        canonical = (self.git.repo_root / relative).resolve()
        if not canonical.is_file() or not canonical.is_relative_to(self.git.repo_root.resolve()):
            return invocation, None, None
        invocation[1] = str(canonical)
        environment = os.environ.copy()
        environment["TOBI_VALIDATION_ROOT"] = str(worktree)
        return invocation, environment, relative

    def _run_checks(self, session_id: int, worktree: Path) -> list[dict[str, Any]]:
        self._stage_start(session_id, "validate", "validating")
        results: list[dict[str, Any]] = []
        timeout = self.policy.limit("command_timeout_seconds", 900)
        session = self.get_workflow(session_id)
        changed_files = set(self.git.changed_files(worktree))
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
            skip = self._check_unavailable(argv, worktree)
            if skip:
                result = _safe({"argv": argv, "ok": True, "exit_code": 0, "skipped": True,
                                "output": skip})
                results.append(result)
                self._event(session_id, "check_skipped", result)
                continue
            invocation, check_env, harness = self._validation_invocation(
                argv, worktree, changed_files
            )
            if harness:
                self._event(session_id, "validation_harness_selected", {
                    "harness": harness,
                    "message": "Using the current Mission Control validator against this retained worktree.",
                })
            try:
                completed = subprocess.run(
                    resolve_runtime_command(invocation), cwd=str(worktree), capture_output=True,
                    text=True, encoding="utf-8", errors="replace", timeout=timeout,
                    env=check_env,
                    creationflags=no_window(),
                )
            except (OSError, subprocess.SubprocessError) as exc:
                # The command could not be launched at all (missing binary, bad shim).
                # Record it as a failed check naming the argv — raising here pauses the
                # workflow with a bare error and no check_completed row, so the owner
                # cannot tell which check died.
                result = _safe({"argv": argv, "ok": False, "exit_code": None,
                                "output": f"{type(exc).__name__}: {exc}",
                                "failure_kind": "infrastructure"})
                result["failure_fingerprint"] = failure_detail_signature(
                    "validate", "validation_infrastructure_failed", result["output"]
                )
                results.append(result)
                self._event(session_id, "check_completed", result)
                break
            # A reader thread that died mid-decode leaves the stream as None rather than "".
            # Concatenating that is the TypeError that killed run 15 after every check passed.
            result = _safe({"argv": argv, "ok": completed.returncode == 0, "exit_code": completed.returncode,
                            "output": ((completed.stdout or "") + (completed.stderr or ""))[-20_000:]})
            if not result["ok"]:
                lowered = str(result["output"]).lower()
                task_changes_python_runtime = any(
                    Path(path).suffix.lower() in {".py", ".toml", ".lock"}
                    or Path(path).name.lower().startswith("requirements")
                    for path in changed_files
                )
                failure_kind = (
                    "infrastructure"
                    if (
                        any(marker in lowered for marker in INFRASTRUCTURE_FAILURE_MARKERS)
                        and not task_changes_python_runtime
                    )
                    else "task"
                )
                error_code = (
                    "validation_infrastructure_failed"
                    if failure_kind == "infrastructure" else "validation_failed"
                )
                result["failure_kind"] = failure_kind
                result["failure_fingerprint"] = failure_detail_signature(
                    "validate", error_code, f"{argv}\n{result['output']}"
                )
            results.append(result)
            self._event(session_id, "check_completed", result)
            if not result["ok"]:
                break
        checks_ok = all(r["ok"] for r in results)
        result_payload = {"ok": checks_ok, "checks": results}
        self.store.update_stage(
            session_id,
            "validate",
            status="completed" if checks_ok else "failed",
            checks_json=results,
            result_json=result_payload,
            completed_at=utc_now(),
        )
        self.store.finish_stage_attempt(
            session_id,
            "validate",
            status="completed" if checks_ok else "failed",
            error_code=None if checks_ok else "validation_failed",
            result=result_payload,
        )
        current = self.store.get_session(session_id)
        if current:
            self.completion.record_stage_evidence(current, "validate", result_payload)
        self._artifact(session_id, "checks", results)
        self._event(
            session_id,
            "stage_completed" if checks_ok else "stage_failed",
            {"stage": "validate", "ok": checks_ok},
        )
        return results

    def command(self, session_id: int, command: str, *, background: bool = True) -> dict[str, Any]:
        session = self.get_workflow(session_id)
        if command == "sync_delivery":
            return self.sync_delivery(session_id)
        if command == "reconcile_base":
            if session.get("error_code") != "main_drift":
                raise RuntimeError("Base reconciliation is only available after main-branch drift.")
            if not session.get("worktree"):
                raise RuntimeError("Workflow has no retained worktree to reconcile.")
            result = self.git.reconcile_base(session["worktree"])
            self.store.reset_stages_for_base_reconciliation(session_id)
            self.store.update_session(
                session_id,
                base_sha=result["base_sha"],
                head_sha=result["head_sha"],
                state="paused",
                stage="push",
                blocker=None,
                error_code=None,
                completed_at=None,
            )
            self._event(session_id, "base_reconciled", result, actor="owner")
            self._checkpoint(
                session_id,
                status="base_reconciled",
                next_action="Continue push and delivery from the reconciled base.",
            )
            return self.command(session_id, "resume", background=background)
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
            self.store.finish_stage_attempt(
                session_id, str(session["stage"]), status="canceled", error_code="owner_canceled"
            )
            self._set_task_owner_state(int(session["task_id"]), "Canceled")
            self._event(session_id, "workflow_canceled", {"worktree_retained": bool(session.get("worktree"))}, actor="owner")
            self.completion.build_scorecard(session_id)
            return self.get_workflow(session_id)
        if command == "remove":
            if session["state"] not in TERMINAL_STATES:
                raise RuntimeError("Only a finished workflow can be removed from Process.")
            self.store.update_session(session_id, archived_at=utc_now())
            self._event(session_id, "workflow_archived", {"state": session["state"]}, actor="owner")
            return self.get_workflow(session_id)
        if command in {"resume", "retry"}:
            if session.get("error_code") in STALE_SNAPSHOT_ERRORS:
                return self.restart_stale_workflow(session_id, background=background)
            if session.get("error_code") in {
                "repeated_failure",
                "validation_infrastructure_failed",
            }:
                raise RuntimeError(
                    "Retry is disabled because the same work cannot repair this failure. "
                    "Repair the development environment, revise the item, or switch agents."
                )
            if session["state"] not in {"paused", "blocked", "failed", "approved"}:
                raise RuntimeError(f"Workflow cannot {command} from state {session['state']}.")
            self.store.prepare_session_retry(
                session_id,
                reset_recode=session.get("error_code") in CORRECTABLE_BY_RECODE,
            )
            self.store.update_session(session_id, state="approved" if not session.get("worktree") else "paused",
                                      blocker=None, error_code=None, cancel_requested=0)
            self._set_task_owner_state(int(session["task_id"]), "Running")
            self._event(session_id, f"workflow_{command}d", {"stage": session["stage"]}, actor="owner")
            return self.start_background(session_id) if background else self.run_to_gate(session_id)
        raise ValueError(f"Unknown workflow command: {command}")

    def reject_approval(self, session_id: int, purpose: str) -> dict[str, Any]:
        """Reject an approval and resume from code with the rejection in the durable handoff."""
        session = self.get_workflow(session_id)
        if purpose == "special_paths":
            if session.get("error_code") != "special_approval_required":
                raise RuntimeError("Workflow is not waiting for protected-path approval.")
            changed = self.git.changed_files(session["worktree"]) if session.get("worktree") else []
            protected = [path for path in changed if self.policy.path_decision(path).protected]
            restored = self.git.restore_paths(session["worktree"], protected) if protected else []
            instruction = "Protected-path access was rejected. Preserve the approved scope using non-protected files."
        elif purpose == "merge_deploy":
            if session["state"] != "awaiting_merge_deploy_approval":
                raise RuntimeError("Workflow is not waiting for merge and deployment approval.")
            restored = []
            instruction = "Merge and deployment were rejected. Revise the implementation and provide new evidence."
        else:
            raise ValueError("Unsupported approval purpose.")
        self.store.reset_stages_after_approval_rejection(session_id)
        self.store.update_session(
            session_id, state="paused", stage="code", blocker=None,
            error_code=None, completed_at=None, cancel_requested=0,
        )
        self._sync_progress(session_id)
        self._event(session_id, "approval_rejected", {
            "purpose": purpose, "instruction": instruction, "restored_paths": restored,
        }, actor="owner")
        self._checkpoint(session_id, status="owner_revision", next_action=instruction)
        return self.command(session_id, "resume")

    def sync_delivery(self, session_id: int) -> dict[str, Any]:
        """Synchronize the durable run with the pull request without repeating effects."""
        session = self.get_workflow(session_id)
        pr = session.get("pull_request") or {}
        if not pr.get("number"):
            raise RuntimeError("Workflow has no pull request to synchronize.")
        previous_sync = str(pr.get("last_sync_status") or "")
        remote = self.github.get_pr(int(pr["number"]))
        pending: list[str] = []
        failed: list[str] = []
        if remote.get("merged"):
            ci_state = "passed"
            conflict_state = "none"
            merge_state = "merged"
        elif remote.get("state") == "closed":
            ci_state = pr.get("ci_state") or "unknown"
            conflict_state = pr.get("conflict_state") or "unknown"
            merge_state = "closed"
        else:
            readiness = self.github.merge_readiness(int(pr["number"]))
            pending = [str(item) for item in readiness.get("pending_checks") or []]
            failed = [str(item) for item in readiness.get("failed_checks") or []]
            ci_state = "failed" if failed else "pending" if pending else "passed"
            mergeable_state = str(remote.get("mergeable_state") or "")
            conflict_state = "conflicted" if mergeable_state == "dirty" else "clear"
            if remote.get("draft"):
                merge_state = "draft"
            elif conflict_state == "conflicted":
                merge_state = "conflicted"
            elif readiness.get("ready"):
                merge_state = "ready"
            else:
                merge_state = "open"
        event_payload = {
            "draft": bool(remote.get("draft")),
            "ci_state": ci_state,
            "conflict_state": conflict_state,
            "merge_state": merge_state,
            "merged_at": remote.get("merged_at"),
            "merge_commit_sha": remote.get("merge_commit_sha"),
            "pending_checks": sorted(pending),
            "failed_checks": sorted(failed),
        }
        sync_fingerprint = hashlib.sha256(
            json.dumps(
                event_payload,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            ).encode("utf-8")
        ).hexdigest()[:20]
        synchronized = {
            **remote,
            "ci_state": ci_state,
            "conflict_state": conflict_state,
            "merge_state": merge_state,
            "last_sync_status": f"ok:{sync_fingerprint}",
        }
        self._save_pr(int(session["task_id"]), synchronized)
        if previous_sync != synchronized["last_sync_status"]:
            self._event(session_id, "delivery_synchronized", event_payload)
        if remote.get("merged") and remote.get("merge_commit_sha"):
            sha = str(remote["merge_commit_sha"])
            refreshed = self.get_workflow(session_id)
            statuses = {stage["node_id"]: stage["status"] for stage in refreshed["stages"]}
            if statuses.get("merge_deploy") != "completed":
                self._stage_start(session_id, "merge_deploy", "merging")
                self._stage_complete(
                    session_id,
                    "merge_deploy",
                    {
                        "merged": True,
                        "sha": sha,
                        "merged_at": remote.get("merged_at"),
                        "reconciled": True,
                    },
                )
            self.releases.set_status(refreshed["target_version"], "merged", commit_sha=sha)
            return self._deploy_merged_release(session_id)
        if remote.get("state") == "closed":
            return self._pause(
                session_id,
                "merge_deploy",
                "The pull request was closed without merging. Revise the item or cancel this run.",
                "pull_request_closed",
            )
        if self.policy.feature_enabled("merge"):
            action = "merge and deploy" if self.policy.feature_enabled("deploy") else "merge"
            self.store.update_session(
                session_id,
                state="awaiting_merge_deploy_approval",
                stage="merge_deploy",
                blocker=f"Owner re-authentication is required to {action}.",
                error_code=None,
            )
        else:
            self.store.update_session(
                session_id,
                state="awaiting_owner_merge",
                stage="merge_deploy",
                blocker="Draft pull request is ready. Merge it on GitHub, then synchronize delivery.",
                error_code=None,
            )
        self._sync_progress(session_id)
        self.completion.build_scorecard(session_id)
        return self.get_workflow(session_id)

    def reconcile(self) -> list[dict[str, Any]]:
        """Fail closed after backend restart and repair durable checkpoints where evidence is conclusive."""
        self.store.fail_stale_commands()
        reconciled: list[dict[str, Any]] = []
        sessions = self.store.list_sessions(200)
        for item in sessions:
            self.store.reconcile_stage_attempts(int(item["id"]))
            if item["state"] in TERMINAL_STATES:
                continue
            workflow = self.get_workflow(int(item["id"]))
            if not (workflow.get("pull_request") or {}).get("number"):
                continue
            try:
                synchronized = self.sync_delivery(int(item["id"]))
            except (GitHubCodingError, PolicyDenied, RuntimeError):
                continue
            if synchronized["state"] in {"merged", "completed", "awaiting_owner_merge"}:
                reconciled.append(synchronized)
        sessions = self.store.list_sessions(200)
        active_states = {"approved", "preparing", "coding", "validating", "reviewing", "pushed", "merging", "deploying"}
        for item in sessions:
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
        if not self.policy.feature_enabled("merge"):
            raise PolicyDenied("Merge is disabled by reviewed policy.")
        conn = self.store.connect()
        try:
            pr = conn.execute("SELECT * FROM coding_pull_requests WHERE task_id=?", (session["task_id"],)).fetchone()
        finally:
            conn.close()
        if not pr or not pr["number"]:
            raise RuntimeError("Workflow has no pull request to merge.")
        try:
            self._stage_start(session_id, "merge_deploy", "merging")
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
            self._save_pr(
                int(session["task_id"]),
                {
                    **dict(pr),
                    "draft": False,
                    "merge_state": "merged",
                    "merged_at": utc_now(),
                    "merge_commit_sha": merged["sha"],
                    "last_sync_status": "ok",
                },
            )
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
            return self._finalize_merged(session_id, str(release["commit_sha"]))
        self.store.update_session(session_id, state="deploying", stage="health")
        self._sync_progress(session_id)
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
        self.store.update_session(session_id, state="completed", stage="completed",
                                  blocker=None, completed_at=utc_now())
        self._sync_progress(session_id)
        self._mark_task_completed(int(session["task_id"]))
        self._event(session_id, "workflow_completed", {"version": session["target_version"],
                                                        "sha": release["commit_sha"], "tag": tag["tag"]})
        self._record_learning(
            session_id, outcome="completed", stage="health",
            evidence={"version": session["target_version"], "sha": release["commit_sha"]},
        )
        for link in self.store.list_goal_task_links(task_id=int(session["task_id"])):
            self.completion.evaluate_goal(int(link["goal_id"]))
        self.completion.build_scorecard(session_id)
        self.start_next_queued()
        return self.get_workflow(session_id)

    def _finalize_merged(self, session_id: int, commit_sha: str) -> dict[str, Any]:
        current = self.store.get_session(session_id) or {}
        if current.get("state") == "merged":
            return self.get_workflow(session_id)
        message = "Merged, deployment skipped by reviewed policy."
        self.store.update_session(
            session_id,
            state="merged",
            stage="merge_deploy",
            blocker=message,
            error_code=None,
            completed_at=utc_now(),
        )
        self._sync_progress(session_id)
        session = self.store.get_session(session_id) or {}
        self._mark_task_completed(int(session["task_id"]))
        self._event(
            session_id,
            "workflow_merged",
            {"version": session.get("target_version"), "sha": commit_sha, "deployment": "skipped"},
        )
        self._checkpoint(session_id, status="merged", next_action=message)
        self._record_learning(
            session_id,
            outcome="merged",
            stage="merge_deploy",
            evidence={"version": session.get("target_version"), "sha": commit_sha},
        )
        for link in self.store.list_goal_task_links(task_id=int(session["task_id"])):
            self.completion.evaluate_goal(int(link["goal_id"]))
        self.completion.build_scorecard(session_id)
        self.start_next_queued()
        return self.get_workflow(session_id)

    def _mark_task_completed(self, task_id: int) -> None:
        self.store.complete_task(task_id, queue_status="Done")

    def _save_pr(self, task_id: int, pr: dict[str, Any]) -> None:
        merge_state = str(pr.get("merge_state") or "")
        merged = bool(pr.get("merged") or pr.get("merged_at") or merge_state == "merged")
        # Do not retain GitHub's provisional merge-test SHA for an open pull request.
        merge_commit_sha = pr.get("merge_commit_sha") if merged else None
        conn = self.store.connect()
        try:
            conn.execute(
                """INSERT INTO coding_pull_requests(
                       task_id,repository,number,url,head_sha,base_sha,draft,
                       ci_state,conflict_state,merge_state,merged_at,merge_commit_sha,
                       last_sync_status,updated_at
                   )
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(task_id) DO UPDATE SET number=excluded.number,url=excluded.url,
                   head_sha=excluded.head_sha,base_sha=excluded.base_sha,draft=excluded.draft,
                   ci_state=COALESCE(excluded.ci_state,coding_pull_requests.ci_state),
                   conflict_state=COALESCE(excluded.conflict_state,coding_pull_requests.conflict_state),
                   merge_state=COALESCE(excluded.merge_state,coding_pull_requests.merge_state),
                   merged_at=excluded.merged_at,
                   merge_commit_sha=excluded.merge_commit_sha,
                   last_sync_status=COALESCE(excluded.last_sync_status,coding_pull_requests.last_sync_status),
                   updated_at=excluded.updated_at""",
                (
                    task_id,
                    self.github.repository,
                    pr.get("number"),
                    pr.get("url"),
                    pr.get("head_sha"),
                    pr.get("base_sha"),
                    int(bool(pr.get("draft", True))),
                    pr.get("ci_state"),
                    pr.get("conflict_state"),
                    merge_state or None,
                    pr.get("merged_at"),
                    merge_commit_sha,
                    pr.get("last_sync_status"),
                    utc_now(),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def _pull_request_body(self, session_id: int) -> str:
        session = self.get_workflow(session_id)
        checks = next((stage for stage in session["stages"] if stage["node_id"] == "validate"), {})
        delivery_note = (
            "Owner merge and deployment approval remains required."
            if self.policy.feature_enabled("merge") and self.policy.feature_enabled("deploy")
            else "Owner merge approval remains required; deployment is disabled by reviewed policy."
            if self.policy.feature_enabled("merge")
            else "Merge remains owner-controlled on GitHub; deployment follows reviewed policy."
        )
        return (
            f"Implements queue item #{session['queue_id']}.\n\n"
            f"Plan: `{session['plan_path']}`\n\n"
            f"Policy: `{session['policy_hash'][:12]}`\n\n"
            f"Validation: `{checks.get('status', 'unknown')}`\n\n"
            f"Generated by TOBI's controlled coding workflow. {delivery_note}"
        )

    def changes(self, session_id: int) -> dict[str, Any]:
        session = self.get_workflow(session_id)
        if not session.get("worktree"):
            return {"files": [], "stat": "", "head_sha": session.get("head_sha")}
        statuses = {stage["node_id"]: stage["status"] for stage in session["stages"]}
        if (
            statuses.get("commit") == "completed"
            and session.get("base_sha")
            and session.get("head_sha")
        ):
            return self.git.diff_summary(
                session["worktree"],
                base_ref=str(session["base_sha"]),
                head_ref=str(session["head_sha"]),
            )
        return self.git.diff_summary(session["worktree"])

    def storage(self, *, refresh: bool = False) -> dict[str, Any]:
        usage = self.git.storage(refresh=refresh)
        tree_size = self.git._tree_bytes  # scandir-based; see GitWorkspace._tree_bytes
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
        counts = self.store.storage_cleanup_counts(
            now=datetime.now(timezone.utc).isoformat(), cutoff=cutoff
        )
        usage["cleanup_eligible_artifacts"] = counts["artifacts"]
        usage["cleanup_eligible_worktrees"] = counts["worktrees"]
        return usage

    def cleanup(self, challenge: str) -> dict[str, Any]:
        self.store.consume_challenge(challenge, "developer_cleanup", self.policy.hash)
        state = self.storage()
        cutoff = (datetime.now(timezone.utc) - timedelta(days=state["retention_days"])).isoformat()
        now = datetime.now(timezone.utc).isoformat()
        candidates = self.store.cleanup_candidates(now=now, cutoff=cutoff)
        artifacts = candidates["artifacts"]
        sessions = candidates["sessions"]
        artifact_root = self.policy.repo_path("artifact_root").resolve()
        removed_artifacts = 0
        for row in artifacts:
            path = Path(row["path"]).resolve()
            if path.is_relative_to(artifact_root) and path.is_file():
                path.unlink()
                removed_artifacts += 1
            self.store.mark_artifact_cleaned(int(row["id"]))
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
                # Fresh, not cached: the owner just deleted worktrees and is asking whether the
                # space came back. A stale reading here would report the pre-cleanup total.
                "remaining": self.storage(refresh=True)}

"""Durable single-owner development goal loop for always-on VPS operation."""
from __future__ import annotations

import logging
import os
import socket
import threading
import uuid
from typing import Any

from core.coding_agent import CodingAgent
from core.development_store import utc_now


LOGGER = logging.getLogger(__name__)


RETRYABLE_ERRORS = {
    "validation_failed", "review_failed", "review_unavailable", "worker_timeout",
    "worker_failed", "no_changes", "internal_error", "external_step_failed", "backend_restarted",
}
CONFIG_ERRORS = {
    "worker_unavailable", "github_disabled", "deploy_disabled", "special_approval_required",
    "external_reconciliation_required", "policy_changed", "plan_changed", "autonomy_boundary",
}
ACTIVE_STATES = {"approved", "preparing", "coding", "validating", "reviewing", "pushed", "merging", "deploying"}


class CodingLoopService:
    def __init__(self, agent: CodingAgent | None = None) -> None:
        self.agent = agent or CodingAgent()
        self.policy = self.agent.policy
        self.store = self.agent.store
        self.owner = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"
        self.poll_seconds = max(2, int(self.policy.data.get("loop", {}).get("poll_seconds", 10)))
        self.lease_seconds = max(30, int(self.policy.data.get("loop", {}).get("lease_seconds", 120)))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._current_goal: int | None = None

    def enabled(self) -> bool:
        return bool(self.policy.data.get("loop", {}).get("enabled", False))

    def start(self) -> bool:
        if not self.enabled():
            return False
        if self._thread and self._thread.is_alive():
            return True
        self.agent.reconcile()
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="tobi-development-loop")
        self._thread.start()
        return True

    def stop(self, timeout: float = 10.0) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
            if self._thread.is_alive():
                LOGGER.warning("Development loop is still finishing goal %s; retaining its lease", self._current_goal)
                return
        if self._current_goal is not None:
            self.store.release_goal_lease(self._current_goal, self.owner)
        self._current_goal = None

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception:
                # A durable goal records actionable errors in tick(); the daemon itself must survive.
                LOGGER.exception("Continuous development loop tick failed before durable goal handling completed")
            self._stop.wait(self.poll_seconds)

    def tick(self) -> dict[str, Any] | None:
        goal = self.store.claim_goal(self.owner, self.lease_seconds)
        if not goal:
            self._current_goal = None
            return None
        goal_id = int(goal["id"])
        self._current_goal = goal_id
        heartbeat_stop = threading.Event()
        heartbeat = threading.Thread(
            target=self._maintain_goal_lease,
            args=(goal_id, heartbeat_stop),
            daemon=True,
            name=f"tobi-development-goal-{goal_id}-lease",
        )
        heartbeat.start()
        try:
            return self._advance(goal)
        except Exception as exc:
            updated = self.store.update_goal(
                goal_id, status="blocked", last_error=f"{type(exc).__name__}: {str(exc)[:1000]}",
            )
            return updated
        finally:
            heartbeat_stop.set()
            heartbeat.join(timeout=2.0)
            self.store.renew_goal_lease(goal_id, self.owner, self.lease_seconds)

    def _maintain_goal_lease(self, goal_id: int, stop: threading.Event) -> None:
        interval = max(5.0, self.lease_seconds / 3)
        while not stop.wait(interval):
            if not self.store.renew_goal_lease(goal_id, self.owner, self.lease_seconds):
                return

    def _advance(self, goal: dict[str, Any]) -> dict[str, Any]:
        goal_id = int(goal["id"])
        max_iterations = int(goal["max_iterations"])
        session_id = goal.get("current_session_id")
        if not session_id:
            workflow = self.agent.create_goal_workflow(goal_id)
            session_id = int(workflow["id"])
            result = self.agent.run_to_gate(session_id)
            return self._record_result(self.store.get_goal(goal_id) or goal, result)

        workflow = self.agent.get_workflow(int(session_id))
        if workflow["state"] in ACTIVE_STATES:
            return self.store.get_goal(goal_id) or goal
        if workflow["state"] == "completed":
            return self._complete(goal, workflow, "completed")
        if workflow["state"] == "awaiting_merge_deploy_approval":
            return self.store.update_goal(goal_id, status="awaiting_approval", last_error=None)
        if workflow["state"] == "canceled":
            return self.store.update_goal(goal_id, status="canceled", completed_at=utc_now())

        error_code = str(workflow.get("error_code") or "")
        if error_code in RETRYABLE_ERRORS and int(goal["iteration_count"]) < max_iterations:
            previous = int(goal["iteration_count"])
            self.store.finish_goal_iteration(goal_id, previous, "retrying", {
                "session_id": session_id, "error_code": error_code, "stage": workflow.get("stage"),
            })
            iteration = previous + 1
            self.store.update_goal(goal_id, iteration_count=iteration, status="retrying", last_error=error_code)
            self.store.add_goal_iteration(goal_id, int(session_id), iteration)
            result = self.agent.command(int(session_id), "retry", background=False)
            return self._record_result(self.store.get_goal(goal_id) or goal, result)
        if error_code in CONFIG_ERRORS:
            if error_code in {"github_disabled", "autonomy_boundary"} and goal["autonomy"] == "sandbox":
                return self._complete(goal, workflow, "qualified_local")
            return self.store.update_goal(goal_id, status="awaiting_config", last_error=error_code)
        if int(goal["iteration_count"]) >= max_iterations:
            return self.store.update_goal(goal_id, status="blocked", last_error="max_iterations_exhausted")
        return self.store.update_goal(goal_id, status="blocked", last_error=error_code or workflow["state"])

    def _record_result(self, goal: dict[str, Any], workflow: dict[str, Any]) -> dict[str, Any]:
        goal_id = int(goal["id"])
        iteration = int(goal["iteration_count"])
        self.store.finish_goal_iteration(goal_id, iteration, workflow["state"], {
            "session_id": workflow["id"], "state": workflow["state"],
            "stage": workflow.get("stage"), "error_code": workflow.get("error_code"),
        })
        if workflow["state"] == "completed":
            return self._complete(goal, workflow, "completed")
        if workflow["state"] == "awaiting_merge_deploy_approval":
            return self.store.update_goal(goal_id, status="awaiting_approval", last_error=None)
        error_code = str(workflow.get("error_code") or "")
        if error_code in {"github_disabled", "autonomy_boundary"} and goal["autonomy"] == "sandbox":
            return self._complete(goal, workflow, "qualified_local")
        if error_code in CONFIG_ERRORS:
            return self.store.update_goal(goal_id, status="awaiting_config", last_error=error_code)
        if error_code in RETRYABLE_ERRORS:
            return self.store.update_goal(goal_id, status="retrying", last_error=error_code)
        return self.store.update_goal(goal_id, status="blocked", last_error=error_code or workflow["state"])

    def _complete(self, goal: dict[str, Any], workflow: dict[str, Any], state: str) -> dict[str, Any]:
        goal_id = int(goal["id"])
        self.store.finish_goal_iteration(goal_id, int(goal["iteration_count"]), state, {
            "session_id": workflow["id"], "state": workflow["state"], "completed_at": utc_now(),
        })
        return self.store.update_goal(goal_id, status=state, last_error=None, completed_at=utc_now())

    def command(self, goal_id: int, command: str) -> dict[str, Any]:
        goal = self.store.get_goal(goal_id)
        if not goal:
            raise KeyError(goal_id)
        if command == "pause":
            if goal.get("current_session_id"):
                self.agent.command(int(goal["current_session_id"]), "pause")
            return self.store.update_goal(goal_id, status="paused", lease_owner=None, lease_expires_at=None)
        if command == "cancel":
            if goal.get("current_session_id"):
                self.agent.command(int(goal["current_session_id"]), "cancel")
            return self.store.update_goal(goal_id, status="canceled", completed_at=utc_now(),
                                          lease_owner=None, lease_expires_at=None)
        if command == "resume":
            if goal["status"] not in {"paused", "blocked", "awaiting_config"}:
                raise RuntimeError(f"Goal cannot resume from {goal['status']}.")
            return self.store.update_goal(goal_id, status="retrying", last_error=None,
                                          lease_owner=None, lease_expires_at=None)
        raise ValueError("Goal command must be pause, resume, or cancel.")


_loop: CodingLoopService | None = None
_loop_lock = threading.Lock()


def get_coding_loop() -> CodingLoopService:
    global _loop
    with _loop_lock:
        if _loop is None:
            _loop = CodingLoopService()
        return _loop

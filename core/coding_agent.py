"""Durable coding workflow orchestrator owned by Mission Control."""
from __future__ import annotations

import json
import subprocess
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from core.coding_policy import CodingPolicy, PolicyDenied
from core.coding_queue import sync_queue
from core.deployment_manager import DeploymentManager
from core.development_store import DevelopmentStore, utc_now
from core.git_workspace import GitCommandError, GitWorkspaceManager
from core.github_coding import GitHubCodingError, GitHubCodingService
from core.hermes_worker import HermesUnavailable, HermesWorker
from core.release_manager import ReleaseManager
from core.repo_index import RepositoryIndex


STAGES = [
    {"id": "prepare", "title": "Create isolated worktree", "depends": []},
    {"id": "index", "title": "Build scoped repository context", "depends": ["prepare"]},
    {"id": "code", "title": "Run managed Hermes worker", "depends": ["index"]},
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
        self.worker = HermesWorker(self.policy)
        self.github = GitHubCodingService(self.policy)
        self.releases = ReleaseManager(self.store)
        self.deployments = DeploymentManager(self.policy, self.store)
        self._threads: dict[int, threading.Thread] = {}
        self._thread_lock = threading.Lock()

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
        )
        self.store.add_stages(int(session["id"]), STAGES)
        self.releases.reserve(target_version, queue_id, risk=task.get("risk") or "medium")
        self.store.append_event(int(session["id"]), "workflow_approved", {
            "queue_id": queue_id, "plan_path": task["plan_path"], "plan_hash": task["plan_hash"],
            "policy_hash": self.policy.hash, "target_version": target_version,
        }, actor="owner")
        return self.get_workflow(int(session["id"]))

    @staticmethod
    def _next_version(queue_id: int) -> str:
        return "3.0.0" if queue_id == 18 else f"3.{queue_id}.0"

    def get_workflow(self, session_id: int) -> dict[str, Any]:
        session = self.store.get_session(session_id)
        if not session:
            raise KeyError(session_id)
        session["stages"] = self.store.list_stages(session_id)
        conn = self.store.connect()
        try:
            pr = conn.execute("SELECT * FROM coding_pull_requests WHERE task_id=?", (session["task_id"],)).fetchone()
            session["pull_request"] = dict(pr) if pr else None
        finally:
            conn.close()
        return session

    def list_workflows(self, limit: int = 50) -> list[dict[str, Any]]:
        return [self.get_workflow(int(workflow["id"])) for workflow in self.store.list_sessions(limit)]

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
        return self.get_workflow(session_id)

    def _block(self, session_id: int, stage: str, blocker: str, code: str) -> dict[str, Any]:
        blocker = str(_safe(blocker))
        self.store.update_stage(session_id, stage, status="failed", result_json={"error_code": code})
        self.store.update_session(session_id, state="blocked", stage=stage, blocker=blocker, error_code=code)
        self._event(session_id, "workflow_blocked", {"stage": stage, "error_code": code, "action": blocker})
        return self.get_workflow(session_id)

    def run_to_gate(self, session_id: int) -> dict[str, Any]:
        session = self.get_workflow(session_id)
        if session["policy_hash"] != self.policy.hash:
            return self._pause(session_id, session["stage"], "The active coding policy changed; review and restart from a new workflow.",
                               "policy_changed")
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
                snapshot = self.index.build()
                self._stage_complete(session_id, "index", snapshot)

            session = self.get_workflow(session_id)
            statuses = {item["node_id"]: item["status"] for item in session["stages"]}
            if statuses.get("code") != "completed":
                self._stage_start(session_id, "code", "coding", 20)
                task = self.store.get_task(task_id=int(session["task_id"])) or {}
                criteria = json.loads(task.get("acceptance_criteria_json") or "[]")
                context = self.index.search(f"{session['title']} {' '.join(criteria[:8])}", limit=30)
                validation_stage = next((item for item in session["stages"] if item["node_id"] == "validate"), {})
                brief = {
                    "workflow_id": session_id, "stage_id": "code", "worktree": session["worktree"],
                    "plan_path": session["plan_path"], "plan_hash": session["plan_hash"],
                    "acceptance_criteria": criteria, "relevant_files": context,
                    "previous_checks": json.loads(validation_stage.get("checks_json") or "[]"),
                    "allowed_commands": self.policy.mandatory_checks(),
                    "policy": {"version": self.policy.version, "hash": self.policy.hash,
                               "protected_paths": self.policy.data.get("protected_paths", []),
                               "forbidden_paths": self.policy.data.get("forbidden_paths", [])},
                }

                def worker_event(kind: str, payload: dict[str, Any]) -> None:
                    self._event(session_id, f"worker_{kind}", payload, actor="hermes")

                try:
                    result = self.worker.run(session_id, "code", session["worktree"], brief, on_event=worker_event)
                except HermesUnavailable as exc:
                    return self._pause(session_id, "code", str(exc), "hermes_unavailable")
                except TimeoutError as exc:
                    return self._pause(session_id, "code", str(exc), "worker_timeout")
                except RuntimeError as exc:
                    return self._pause(session_id, "code", str(exc), "worker_failed")
                changed = self.git.changed_files(session["worktree"])
                self._artifact(session_id, "worker", {"events": result["events"], "output": result["output"]})
                self._stage_complete(session_id, "code", {"changed_files": changed, "event_count": len(result["events"])})
                if not changed:
                    return self._pause(session_id, "code", "Hermes completed without changing files; revise the stage brief or retry.",
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
                self._artifact(session_id, "review", diff)
                self._stage_complete(session_id, "review", {"qualified": True, **diff})
            if statuses.get("commit") != "completed":
                self._stage_start(session_id, "commit", "reviewing", 72)
                special = self.store.has_approval(session_id, "special_paths", self.policy.hash)
                head = self.git.commit(session["worktree"], f"feat: implement queue item #{session['queue_id']}",
                                       special_approval=special)
                self.store.update_session(session_id, head_sha=head)
                self._stage_complete(session_id, "commit", {"head_sha": head})

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
            return self.get_workflow(session_id)
        except HermesUnavailable as exc:
            return self._pause(session_id, "code", str(exc), "hermes_unavailable")
        except PolicyDenied as exc:
            code = "special_approval_required" if "protected" in str(exc).lower() else "policy_denied"
            return self._pause(session_id, self.get_workflow(session_id)["stage"], str(exc), code)
        except (GitCommandError, GitHubCodingError, subprocess.SubprocessError, OSError) as exc:
            return self._pause(session_id, self.get_workflow(session_id)["stage"], str(exc)[:1000], "external_step_failed")
        except Exception as exc:
            return self._pause(session_id, self.get_workflow(session_id)["stage"],
                               f"Workflow stopped safely: {type(exc).__name__}", "internal_error")

    def _run_checks(self, session_id: int, worktree: Path) -> list[dict[str, Any]]:
        self._stage_start(session_id, "validate", "validating", 50)
        results: list[dict[str, Any]] = []
        timeout = self.policy.limit("command_timeout_seconds", 900)
        for argv in self.policy.mandatory_checks():
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

    def command(self, session_id: int, command: str) -> dict[str, Any]:
        session = self.get_workflow(session_id)
        if command == "pause":
            self.worker.cancel(session_id)
            return self._pause(session_id, session["stage"], "Paused by owner. Resume when ready.", "owner_paused")
        if command == "cancel":
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
                if session.get("error_code") == "validation_failed":
                    conn.execute(
                        """UPDATE coding_stages SET status='pending',started_at=NULL,completed_at=NULL
                           WHERE session_id=? AND node_id IN ('code','validate','review','commit','scan','push','pull_request')""",
                        (session_id,),
                    )
                    conn.commit()
            finally:
                conn.close()
            self.store.update_session(session_id, state="approved" if not session.get("worktree") else "paused",
                                      blocker=None, error_code=None)
            self._event(session_id, f"workflow_{command}d", {"stage": session["stage"]}, actor="owner")
            return self.start_background(session_id)
        raise ValueError(f"Unknown workflow command: {command}")

    def approve(self, session_id: int, purpose: str, challenge: str) -> dict[str, Any]:
        session = self.get_workflow(session_id)
        self.store.consume_challenge(challenge, purpose, self.policy.hash, session_id=session_id)
        self._event(session_id, "approval_granted", {"purpose": purpose, "policy_hash": self.policy.hash}, actor="owner")
        if purpose == "special_paths":
            return self.command(session_id, "resume")
        if purpose != "merge_deploy":
            raise ValueError("Unsupported approval purpose.")
        if session["state"] != "awaiting_merge_deploy_approval":
            raise RuntimeError("Workflow is not waiting for merge and deployment approval.")
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
        if latest and latest["status"] == "healthy" and latest["new_sha"] == release["commit_sha"]:
            deployment = {"id": latest["id"], "status": "healthy", "reconciled": True}
        else:
            deployment = self.deployments.deploy(int(release["id"]), session["base_sha"], release["commit_sha"])
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
                """SELECT COUNT(*) FROM coding_sessions WHERE state='completed' AND completed_at<=?
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
                """SELECT * FROM coding_sessions WHERE state='completed' AND completed_at<=?
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

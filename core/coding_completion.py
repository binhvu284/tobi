"""Canonical readiness, evidence, and history services for Coding Agent V2."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from core.coding_contracts import ReadinessIssue, ReadinessReport, WorkerProfile
from core.coding_queue import REPO_ROOT
from core.coding_states import ACTIVE_STATES
from core.development_store import DevelopmentStore, utc_now


PASSING_EVIDENCE = {"passed", "success", "ok", "approved", "completed"}
_PATH_RE = re.compile(r"(?<![A-Za-z0-9_.-])([A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+)")


def _json(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default
    return value


def _seconds(start: str | None, end: str | None) -> float | None:
    if not start or not end:
        return None
    try:
        return max(0.0, (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds())
    except (TypeError, ValueError):
        return None


class CodingCompletionService:
    """Keep completion policy outside the HTTP layer and the stage executor."""

    def __init__(self, *, store: DevelopmentStore, policy, worker, assessor) -> None:
        self.store = store
        self.policy = policy
        self.worker = worker
        self.assessor = assessor

    def work_state(self) -> dict[str, Any]:
        tasks = self.store.list_tasks()
        goals = self.store.list_goals(500)
        links = self.store.list_goal_task_links()
        readiness: dict[int, dict[str, Any]] = {}
        conn = self.store.connect()
        try:
            rows = conn.execute(
                """SELECT r.* FROM coding_readiness_snapshots r
                   JOIN (SELECT task_id,MAX(id) id FROM coding_readiness_snapshots GROUP BY task_id) latest
                     ON latest.id=r.id"""
            ).fetchall()
            for row in rows:
                item = dict(row)
                item["payload"] = _json(item.pop("payload_json"), {})
                readiness[int(item["task_id"])] = item
        finally:
            conn.close()
        for task in tasks:
            task["goals"] = [link for link in links if int(link["task_id"]) == int(task["id"])]
            task["readiness"] = readiness.get(int(task["id"]))
        for goal in goals:
            goal["items"] = [link for link in links if int(link["goal_id"]) == int(goal["id"])]
            goal["evidence"] = _json(goal.get("evidence_json"), [])
            goal["gaps"] = _json(goal.get("gaps_json"), [])
        return {"items": tasks, "goals": goals, "links": links}

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
    ) -> dict[str, Any]:
        task = self.store.get_task(queue_id=queue_id)
        if not task or bool(task.get("legacy_hidden")):
            raise KeyError(f"Queue item #{queue_id} was not found.")
        selected = str(selected_agent or task.get("worker_profile_slug") or "mc-native")
        review_slug = str(reviewer or task.get("reviewer_profile_slug") or "reviewer-default")
        fallbacks = list(fallback_agents if fallback_agents is not None else _json(
            task.get("fallback_profiles_json"), []
        ))
        commands = [list(command) for command in (
            validation_commands if validation_commands is not None else _json(
                task.get("validation_commands_json"), []
            )
        )]
        if not commands:
            commands = self.policy.mandatory_checks()

        blockers: list[ReadinessIssue] = []
        warnings: list[ReadinessIssue] = []
        alternatives: list[dict[str, Any]] = []
        plan_text = ""
        plan_path = REPO_ROOT / str(task.get("plan_path") or "")
        if not plan_path.is_file() or not plan_path.resolve().is_relative_to(REPO_ROOT.resolve()):
            blockers.append(ReadinessIssue("plan_missing", "The Queue item plan file is missing or unsafe.", "plan"))
        else:
            plan_bytes = plan_path.read_bytes()
            plan_text = plan_bytes.decode("utf-8", errors="replace")
            current_hash = hashlib.sha256(plan_bytes).hexdigest()
            if current_hash != str(task.get("plan_hash") or ""):
                blockers.append(ReadinessIssue(
                    "plan_changed", "The plan changed after Queue synchronization. Refresh before Start.", "plan"
                ))

        if str(task.get("status") or "") == "completed":
            blockers.append(ReadinessIssue("item_done", "This Queue item is already completed.", "status", False))
        criteria = [str(item) for item in _json(task.get("acceptance_criteria_json"), []) if str(item).strip()]
        if not criteria:
            blockers.append(ReadinessIssue(
                "criteria_missing", "Add measurable acceptance criteria to the plan before Start.", "criteria"
            ))
        for dependency in _json(task.get("dependencies_json"), []):
            dep = self.store.get_task(queue_id=int(dependency))
            if not dep or dep.get("status") != "completed":
                blockers.append(ReadinessIssue(
                    "dependency_incomplete", f"Queue item #{dependency} must be completed first.", "dependencies"
                ))

        conn = self.store.connect()
        try:
            active = conn.execute(
                f"SELECT id FROM coding_sessions WHERE state IN ({','.join('?' for _ in ACTIVE_STATES)}) LIMIT 1",
                tuple(sorted(ACTIVE_STATES)),
            ).fetchone()
        finally:
            conn.close()
        if active:
            blockers.append(ReadinessIssue(
                "run_active", f"Coding run #{active['id']} is already active.", "runtime"
            ))

        profiles = self.store.list_worker_profiles(enabled_only=False)
        for row in profiles:
            if not bool(row.get("enabled")) or row.get("adapter") == "model_review" or row.get("slug") == selected:
                continue
            probe = self.worker.probe(str(row["slug"]), active=False)
            if probe.get("health_status") == "ready":
                alternatives.append({
                    "slug": probe["slug"], "name": probe["name"], "adapter": probe["adapter"],
                    "model": probe.get("model"), "detail": probe.get("health_detail"),
                })

        selected_row = self.store.get_worker_profile(selected)
        if not selected_row or not bool(selected_row.get("enabled")) or selected_row.get("adapter") == "model_review":
            blockers.append(ReadinessIssue(
                "agent_disabled", f"Selected agent {selected} is disabled or not an implementer.", "selected_agent"
            ))
        else:
            selected_health = self.worker.probe(selected, active=active_probe)
            if selected_health.get("health_status") != "ready":
                blockers.append(ReadinessIssue(
                    "agent_unhealthy", str(selected_health.get("health_detail") or "Selected agent is unavailable."),
                    "selected_agent",
                ))

        reviewer_row = self.store.get_worker_profile(review_slug)
        if (
            not reviewer_row or not bool(reviewer_row.get("enabled"))
            or reviewer_row.get("adapter") != "model_review"
        ):
            blockers.append(ReadinessIssue(
                "reviewer_unavailable", f"Independent reviewer {review_slug} is unavailable.", "reviewer"
            ))
        else:
            reviewer_health = self.worker.probe(review_slug, active=False)
            if reviewer_health.get("health_status") != "ready":
                blockers.append(ReadinessIssue(
                    "reviewer_unhealthy", str(reviewer_health.get("health_detail") or "Reviewer is unavailable."),
                    "reviewer",
                ))

        valid_fallbacks: list[str] = []
        for slug in fallbacks:
            if slug == selected or slug in valid_fallbacks:
                continue
            row = self.store.get_worker_profile(slug)
            if not row or not bool(row.get("enabled")) or row.get("adapter") == "model_review":
                warnings.append(ReadinessIssue(
                    "fallback_unavailable", f"Fallback agent {slug} is disabled or unavailable.", "fallback_agents"
                ))
                continue
            health = self.worker.probe(slug, active=False)
            if health.get("health_status") == "ready":
                valid_fallbacks.append(slug)
            else:
                warnings.append(ReadinessIssue(
                    "fallback_unhealthy", f"Fallback {slug}: {health.get('health_detail')}", "fallback_agents"
                ))

        for command in commands:
            try:
                self.policy.assert_command(command)
            except Exception as exc:
                blockers.append(ReadinessIssue("check_denied", str(exc), "validation_commands"))

        assessment = self.assessor.assess(
            title=str(task.get("title") or ""),
            objective=plan_text[:20_000] or str(task.get("title") or ""),
            acceptance_criteria=criteria,
            validation_commands=commands,
        ).to_dict()
        if len(assessment.get("sprints") or []) > 1:
            blockers.append(ReadinessIssue(
                "scope_too_large",
                "This item exceeds one continuous agent session. Split it into smaller Queue items before Start.",
                "scope",
            ))

        protected: list[str] = []
        for relative in sorted(set(_PATH_RE.findall(plan_text[:40_000]))):
            try:
                decision = self.policy.path_decision(relative)
            except Exception:
                continue
            if decision.forbidden:
                blockers.append(ReadinessIssue(
                    "forbidden_path", f"The plan references forbidden path {decision.path}.", "scope", False
                ))
            elif decision.protected:
                protected.append(decision.path)
        if protected and not protected_paths_approved:
            blockers.append(ReadinessIssue(
                "protected_scope_approval", "Owner approval is required for protected development paths.", "scope"
            ))
        elif protected:
            warnings.append(ReadinessIssue(
                "protected_scope", "Protected paths were acknowledged; runtime write approval is still enforced.", "scope"
            ))

        report = ReadinessReport(
            queue_id=queue_id,
            ready=not blockers,
            selected_agent=selected,
            reviewer=review_slug,
            fallback_agents=valid_fallbacks,
            validation_commands=commands,
            blockers=blockers,
            warnings=warnings,
            alternatives=alternatives,
            protected_paths=protected,
            policy_hash=self.policy.hash,
            plan_hash=str(task.get("plan_hash") or ""),
            assessment=assessment,
        )
        snapshot = self.store.save_readiness(
            int(task["id"]), "ready" if report.ready else "blocked", report.to_dict(), self.policy.hash
        )
        return {**report.to_dict(), "readiness_id": int(snapshot["id"]), "created_at": snapshot["created_at"]}

    def evaluate_goal(self, goal_id: int) -> dict[str, Any]:
        goal = self.store.get_goal(goal_id)
        if not goal:
            raise KeyError(goal_id)
        criteria = [str(item) for item in _json(goal.get("acceptance_criteria_json"), [])]
        links = self.store.list_goal_task_links(goal_id=goal_id)
        evidence = self.store.list_evidence(goal_id=goal_id)
        matrix: list[dict[str, Any]] = []
        gaps: list[str] = []
        passed = 0
        for index, criterion in enumerate(criteria):
            matching = [
                item for item in evidence
                if item.get("criterion_index") == index and str(item.get("status") or "").lower() in PASSING_EVIDENCE
            ]
            linked_done = [item for item in links if item.get("status") == "completed"]
            if matching:
                state = "passed"
                passed += 1
            elif linked_done:
                state = "needs_evidence"
                gaps.append(f"Criterion {index + 1} needs criterion-level evidence.")
            else:
                state = "unresolved"
                gaps.append(f"Criterion {index + 1} has no completed linked Queue item.")
            matrix.append({
                "index": index, "criterion": criterion, "status": state,
                "evidence": matching, "linked_items": linked_done,
            })
        qualification = round((passed / len(criteria)) * 100) if criteria else 0
        updated = self.store.update_goal(
            goal_id,
            status="qualified" if qualification == 100 else "active",
            qualification_percent=qualification,
            evidence_json=json.dumps(matrix, separators=(",", ":")),
            gaps_json=json.dumps(gaps, separators=(",", ":")),
            last_evaluated_at=utc_now(),
            completed_at=utc_now() if qualification == 100 else None,
        )
        updated["evidence"] = matrix
        updated["gaps"] = gaps
        updated["items"] = links
        return updated

    def record_stage_evidence(
        self, session: dict[str, Any], stage: str, result: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        status = "passed" if stage not in {"blocked", "failed"} else "failed"
        return self.store.add_evidence(
            session_id=int(session["id"]), task_id=int(session["task_id"]),
            goal_id=int(session["goal_id"]) if session.get("goal_id") else None,
            kind="stage", status=status, source=stage, payload=result or {},
        )

    def build_scorecard(self, session_id: int) -> dict[str, Any]:
        session = self.store.get_session(session_id)
        if not session:
            raise KeyError(session_id)
        conn = self.store.connect()
        try:
            stages = [dict(row) for row in conn.execute(
                "SELECT * FROM coding_stages WHERE session_id=? ORDER BY position", (session_id,)
            )]
            attempts = [dict(row) for row in conn.execute(
                "SELECT * FROM coding_stage_attempts WHERE session_id=? ORDER BY id", (session_id,)
            )]
            workers = [dict(row) for row in conn.execute(
                "SELECT * FROM coding_worker_sessions WHERE session_id=? ORDER BY id", (session_id,)
            )]
        finally:
            conn.close()
        events = self.store.list_events(session_id, limit=2000)
        evidence = self.store.list_evidence(session_id=session_id)
        checks = []
        for stage in stages:
            checks.extend(_json(stage.get("checks_json"), []))
        payload = {
            "session_id": session_id,
            "queue_id": session.get("queue_id"),
            "state": session.get("state"),
            "stage": session.get("stage"),
            "duration_seconds": _seconds(session.get("created_at"), session.get("completed_at") or utc_now()),
            "agent": session.get("worker_profile_slug"),
            "reviewer": session.get("reviewer_profile_slug"),
            "attempts": len(attempts),
            "retries": max(0, len(attempts) - len({item["stage_id"] for item in attempts})),
            "tool_failures": sum(1 for event in events if "failed" in str(event["event_type"])),
            "checks": checks,
            "review": next((stage for stage in stages if stage["node_id"] == "review"), None),
            "evidence": evidence,
            "worker_sessions": workers,
            "error_code": session.get("error_code"),
            "outcome": "delivered" if session.get("state") == "completed" else session.get("state"),
            "generated_at": utc_now(),
        }
        self.store.save_scorecard(session_id, payload)
        return payload

    def history(
        self, *, limit: int = 100, status: str | None = None, agent: str | None = None,
        queue_id: int | None = None, goal_id: int | None = None,
    ) -> list[dict[str, Any]]:
        sessions = self.store.list_sessions(max(1, min(limit, 200)))
        result = []
        for item in sessions:
            if status and item.get("state") != status:
                continue
            if agent and item.get("worker_profile_slug") != agent:
                continue
            if queue_id is not None and int(item.get("queue_id") or 0) != queue_id:
                continue
            if goal_id is not None and int(item.get("goal_id") or 0) != goal_id:
                continue
            item["scorecard"] = self.store.get_scorecard(int(item["id"]))
            result.append(item)
        return result

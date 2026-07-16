"""Deterministic capability and scope assessment for development goals."""
from __future__ import annotations

import re
from typing import Any

from core.coding_contracts import SprintBudget, SprintContract, TaskAssessment


HIGH_RISK_TERMS = {
    "authentication", "authorization", "vault", "secret", "migration", "deploy",
    "deployment", "database", "schema", "billing", "payment", "permission",
    "coding agent", "coding_agent", "coding loop", "coding_loop", "policy",
}
CROSS_CUTTING_TERMS = {
    "architecture", "refactor", "all pages", "whole system", "end to end",
    "frontend and backend", "continuous", "infrastructure", "framework",
}


class CodingTaskAssessor:
    def __init__(self, policy, index) -> None:
        self.policy = policy
        self.index = index

    def assess(
        self,
        *,
        title: str,
        objective: str,
        acceptance_criteria: list[str],
        validation_commands: list[list[str]] | None = None,
    ) -> TaskAssessment:
        text = " ".join([title, objective, *acceptance_criteria]).lower()
        try:
            relevant = self.index.search(text, limit=20, root=self.policy.repo_root)
        except (OSError, RuntimeError):
            relevant = []
        relevant_files = [str(item.get("path") or "") for item in relevant if item.get("path")]
        high_hits = sorted(term for term in HIGH_RISK_TERMS if term in text)
        cross_hits = sorted(term for term in CROSS_CUTTING_TERMS if term in text)
        explicit_paths = sorted(set(re.findall(
            r"(?:^|[\s`'\"])([A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+)", " " + objective
        )))
        protected = [
            path for path in explicit_paths
            if self.policy.path_decision(path).protected or self.policy.path_decision(path).forbidden
        ]
        criteria_count = len(acceptance_criteria)
        score = min(100, 10 + criteria_count * 6 + len(relevant_files) * 2 +
                    len(high_hits) * 12 + len(cross_hits) * 10 + len(protected) * 20)
        risk = "high" if high_hits or protected or score >= 70 else "medium" if score >= 38 else "low"
        owner_review = bool(protected or risk == "high")
        route = "owner_review" if owner_review else "decompose" if criteria_count > 3 or cross_hits else "direct"
        budget = self._budget(risk)
        sprints = self._sprints(title, objective, acceptance_criteria, budget, risk)
        reasons: list[str] = []
        if high_hits:
            reasons.append("Sensitive surfaces: " + ", ".join(high_hits[:8]))
        if cross_hits:
            reasons.append("Cross-cutting scope: " + ", ".join(cross_hits[:6]))
        if protected:
            reasons.append("Protected paths require owner re-authentication.")
        if len(sprints) > 1:
            reasons.append(f"Goal was split into {len(sprints)} bounded sprints.")
        if validation_commands:
            reasons.append(f"{len(validation_commands)} owner-supplied validation command(s) will be enforced.")
        if not reasons:
            reasons.append("Scope fits the default bounded coding sprint.")
        return TaskAssessment(
            route=route,
            risk=risk,
            score=score,
            reasons=reasons,
            relevant_files=relevant_files,
            sprints=sprints,
            owner_review_required=owner_review,
        )

    @staticmethod
    def _budget(risk: str) -> SprintBudget:
        if risk == "high":
            return SprintBudget(max_files=8, max_changed_lines=750, max_subsystems=2,
                                max_minutes=90, max_worker_steps=60)
        if risk == "medium":
            return SprintBudget(max_files=5, max_changed_lines=450, max_subsystems=1,
                                max_minutes=60, max_worker_steps=50)
        return SprintBudget()

    @staticmethod
    def _sprints(
        title: str,
        objective: str,
        criteria: list[str],
        budget: SprintBudget,
        risk: str,
    ) -> list[SprintContract]:
        groups = [criteria[index:index + 3] for index in range(0, len(criteria), 3)] or [[]]
        return [
            SprintContract(
                sequence=index,
                title=title if len(groups) == 1 else f"{title} - sprint {index}",
                objective=objective if len(groups) == 1 else
                          f"{objective}\n\nThis sprint is limited to criteria {index} of {len(groups)}.",
                acceptance_criteria=group,
                budget=budget,
                risk=risk,
            )
            for index, group in enumerate(groups, start=1)
        ]

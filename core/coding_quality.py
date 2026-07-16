"""Deterministic acceptance gates that do not depend on model intelligence."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

from core.coding_contracts import SprintBudget


class CodingQualityGate:
    def __init__(self, policy, git) -> None:
        self.policy = policy
        self.git = git

    def evaluate(
        self,
        *,
        worktree: Path | str,
        budget: SprintBudget,
        checks: Sequence[dict[str, Any]],
        special_approval: bool,
    ) -> dict[str, Any]:
        metrics = self.git.diff_metrics(worktree)
        changed_files = list(metrics["files"])
        decisions = self.policy.assert_write_paths(changed_files, special_approval=special_approval)
        subsystems = sorted({path.split("/", 1)[0] for path in changed_files})
        failures: list[str] = []
        if len(changed_files) > budget.max_files:
            failures.append(f"Changed files {len(changed_files)} exceed sprint budget {budget.max_files}.")
        if int(metrics["changed_lines"]) > budget.max_changed_lines:
            failures.append(
                f"Changed lines {metrics['changed_lines']} exceed sprint budget {budget.max_changed_lines}."
            )
        if len(subsystems) > budget.max_subsystems:
            failures.append(
                f"Subsystem count {len(subsystems)} exceeds sprint budget {budget.max_subsystems}."
            )
        if not checks or any(not bool(item.get("ok")) for item in checks):
            failures.append("Mandatory validation evidence is incomplete or failed.")
        if self.git.scan_secrets(worktree):
            failures.append("Probable secret material was detected.")
        report = {
            "qualified": not failures,
            "failures": failures,
            "metrics": metrics,
            "subsystems": subsystems,
            "path_decisions": [decision.__dict__ for decision in decisions],
            "budget": budget.to_dict(),
        }
        return report

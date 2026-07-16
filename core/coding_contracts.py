"""Typed contracts shared by the Coding Agent v2 control plane."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any


ADAPTERS = {"native", "codex", "opencode", "hermes", "model_review"}
AUTH_MODES = {"inherited", "native_login", "vault_env"}
SECRET_ENV_SUFFIXES = ("_KEY", "_TOKEN", "_SECRET", "_PASSWORD", "_CREDENTIAL")


@dataclass(frozen=True)
class SprintBudget:
    max_files: int = 3
    max_changed_lines: int = 250
    max_subsystems: int = 1
    max_minutes: int = 30
    max_worker_steps: int = 40

    def __post_init__(self) -> None:
        for name, value in asdict(self).items():
            if int(value) < 1:
                raise ValueError(f"{name} must be positive.")

    @classmethod
    def from_value(cls, value: Any) -> "SprintBudget":
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            try:
                value = json.loads(value or "{}")
            except json.JSONDecodeError:
                value = {}
        data = dict(value or {})
        return cls(**{name: int(data.get(name, default))
                      for name, default in asdict(cls()).items()})

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


@dataclass(frozen=True)
class WorkerProfile:
    slug: str
    name: str
    adapter: str
    model: str = ""
    auth_mode: str = "inherited"
    credential_env: str = ""
    reviewer_profile: str = "reviewer-default"
    enabled: bool = True
    config: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        slug = self.slug.strip().lower()
        if not slug or any(char not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for char in slug):
            raise ValueError("Worker profile slug contains unsupported characters.")
        if self.adapter not in ADAPTERS:
            raise ValueError(f"Unsupported coding adapter: {self.adapter}")
        if self.auth_mode not in AUTH_MODES:
            raise ValueError(f"Unsupported worker auth mode: {self.auth_mode}")
        if self.credential_env and not self.credential_env.replace("_", "").isalnum():
            raise ValueError("Credential environment variable name is invalid.")
        if self.auth_mode == "vault_env":
            if not self.credential_env:
                raise ValueError("Vault-backed workers require a credential environment name.")
            if not self.credential_env.upper().endswith(SECRET_ENV_SUFFIXES):
                raise ValueError("Vault-backed workers may reference secret environment names only.")

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "WorkerProfile":
        config = row.get("config_json") or {}
        if isinstance(config, str):
            try:
                config = json.loads(config)
            except json.JSONDecodeError:
                config = {}
        return cls(
            slug=str(row["slug"]),
            name=str(row["name"]),
            adapter=str(row["adapter"]),
            model=str(row.get("model") or ""),
            auth_mode=str(row.get("auth_mode") or "inherited"),
            credential_env=str(row.get("credential_env") or ""),
            reviewer_profile=str(row.get("reviewer_profile") or "reviewer-default"),
            enabled=bool(row.get("enabled", 1)),
            config=dict(config or {}),
        )

    def public_dict(self) -> dict[str, Any]:
        return {
            "slug": self.slug,
            "name": self.name,
            "adapter": self.adapter,
            "model": self.model,
            "auth_mode": self.auth_mode,
            "credential_env": self.credential_env,
            "reviewer_profile": self.reviewer_profile,
            "enabled": self.enabled,
            "config": self.config,
        }


@dataclass(frozen=True)
class SprintContract:
    sequence: int
    title: str
    objective: str
    acceptance_criteria: list[str]
    budget: SprintBudget
    risk: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "title": self.title,
            "objective": self.objective,
            "acceptance_criteria": list(self.acceptance_criteria),
            "budget": self.budget.to_dict(),
            "risk": self.risk,
        }


@dataclass(frozen=True)
class TaskAssessment:
    route: str
    risk: str
    score: int
    reasons: list[str]
    relevant_files: list[str]
    sprints: list[SprintContract]
    owner_review_required: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "route": self.route,
            "risk": self.risk,
            "score": self.score,
            "reasons": list(self.reasons),
            "relevant_files": list(self.relevant_files),
            "sprints": [sprint.to_dict() for sprint in self.sprints],
            "owner_review_required": self.owner_review_required,
        }


def build_handoff(
    *,
    workflow_id: int,
    stage: str,
    worker_profile: str,
    worktree: str,
    head_sha: str | None,
    changed_files: list[str],
    recent_events: list[dict[str, Any]],
    checks: list[dict[str, Any]],
    sprint: dict[str, Any] | None,
    status: str,
    next_action: str,
) -> dict[str, Any]:
    """Build a portable handoff without storing hidden model reasoning."""
    return {
        "version": 1,
        "workflow_id": workflow_id,
        "stage": stage,
        "worker_profile": worker_profile,
        "worktree": worktree,
        "head_sha": head_sha,
        "changed_files": changed_files,
        "recent_events": recent_events[-30:],
        "checks": checks[-20:],
        "sprint": sprint,
        "status": status,
        "next_action": next_action,
    }

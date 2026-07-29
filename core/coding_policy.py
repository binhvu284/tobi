"""Versioned safety policy for TOBI's controlled coding agent."""
from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
from urllib.parse import urlparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY_PATH = REPO_ROOT / "config" / "coding_policy.v1.json"


class PolicyDenied(RuntimeError):
    """Raised when an operation violates the active coding policy."""


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _posix_relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise PolicyDenied(f"Path is outside the approved repository: {path}") from exc


@dataclass(frozen=True)
class PathDecision:
    path: str
    level: int
    protected: bool
    forbidden: bool
    reason: str


class CodingPolicy:
    def __init__(
        self,
        data: dict[str, Any],
        *,
        repo_root: Path | str = REPO_ROOT,
        source_path: Path | str | None = None,
    ) -> None:
        self.data = data
        self.repo_root = Path(repo_root).resolve()
        self.source_path = Path(source_path).resolve() if source_path else None
        self.hash = hashlib.sha256(_canonical_json(data)).hexdigest()

    @classmethod
    def load(
        cls,
        path: Path | str | None = None,
        *,
        repo_root: Path | str = REPO_ROOT,
    ) -> "CodingPolicy":
        policy_path = Path(path or os.getenv("TOBI_CODING_POLICY", str(DEFAULT_POLICY_PATH)))
        data = json.loads(policy_path.read_text(encoding="utf-8"))
        if int(data.get("version", 0)) < 1:
            raise PolicyDenied("Coding policy must have a positive version.")
        return cls(data, repo_root=repo_root, source_path=policy_path)

    @property
    def version(self) -> int:
        return int(self.data["version"])

    def feature_enabled(self, name: str) -> bool:
        return bool(self.data.get("capabilities", {}).get(name, False))

    def qualified_implementer_adapters(self) -> set[str]:
        configured = self.data.get("workers", {}).get(
            "qualified_implementer_adapters", ["native", "codex", "opencode"]
        )
        return {str(value) for value in configured}

    def implementer_qualification(self, adapter: str) -> dict[str, Any]:
        if adapter == "model_review":
            return {
                "status": "reviewer",
                "configuration_locked": False,
                "detail": "Independent review remains required for qualified coding runs.",
            }
        if adapter in self.qualified_implementer_adapters():
            return {
                "status": "qualified",
                "configuration_locked": False,
                "detail": "Qualified for the current Coding Agent V2 rollout.",
            }
        return {
            "status": "future",
            "configuration_locked": True,
            "detail": (
                "Reserved for future development. Codex is the only implementation "
                "agent qualified for the current rollout."
            ),
        }

    def limit(self, name: str, default: int) -> int:
        return int(self.data.get("limits", {}).get(name, default))

    def repo_path(self, key: str) -> Path:
        configured = str(self.data["repository"][key])
        path = Path(os.path.expandvars(configured))
        return path.resolve() if path.is_absolute() else (self.repo_root / path).resolve()

    def path_decision(self, path: Path | str) -> PathDecision:
        full = Path(path)
        if not full.is_absolute():
            full = self.repo_root / full
        relative = _posix_relative(full, self.repo_root)
        forbidden = any(fnmatch.fnmatch(relative, p) for p in self.data.get("forbidden_paths", []))
        protected = any(fnmatch.fnmatch(relative, p) for p in self.data.get("protected_paths", []))
        if forbidden:
            return PathDecision(relative, 99, protected, True, "forbidden path")
        if protected:
            return PathDecision(relative, 7, True, False, "protected self-development path")
        return PathDecision(relative, 2, False, False, "approved worktree path")

    def assert_write_paths(self, paths: Iterable[Path | str], *, special_approval: bool = False) -> list[PathDecision]:
        decisions = [self.path_decision(path) for path in paths]
        denied = [d for d in decisions if d.forbidden or (d.protected and not special_approval)]
        if denied:
            details = ", ".join(f"{d.path} ({d.reason})" for d in denied)
            raise PolicyDenied(f"Write denied by coding policy: {details}")
        return decisions

    def is_indexable(self, path: Path | str) -> bool:
        full = Path(path)
        if not full.is_absolute():
            full = self.repo_root / full
        try:
            relative = _posix_relative(full, self.repo_root)
        except PolicyDenied:
            return False
        return not any(fnmatch.fnmatch(relative, p) for p in self.data.get("index_exclusions", []))

    def assert_command(self, argv: Sequence[str], *, allow_network: bool = False) -> None:
        if not argv or not str(argv[0]).strip():
            raise PolicyDenied("An empty command is not allowed.")
        executable = Path(str(argv[0])).name.lower()
        if executable.endswith(".exe"):
            executable = executable[:-4]
        allowed = {str(v).lower() for v in self.data.get("commands", {}).get("allowed_executables", [])}
        if executable not in allowed:
            raise PolicyDenied(f"Executable is not allowlisted: {executable}")
        rendered = " ".join(str(v) for v in argv).lower()
        for forbidden in self.data.get("commands", {}).get("forbidden_arguments", []):
            if str(forbidden).lower() in rendered:
                raise PolicyDenied(f"Command contains a forbidden operation: {forbidden}")
        if not allow_network and executable in {"curl", "wget"}:
            raise PolicyDenied("Network commands require an explicit policy capability.")

    def mandatory_checks(self) -> list[list[str]]:
        checks = self.data.get("commands", {}).get("mandatory_checks", [])
        return [[str(part) for part in check] for check in checks if isinstance(check, list) and check]

    def assert_remote(self, remote_url: str) -> None:
        repository = str(self.data.get("repository", {}).get("allowed_repository", "")).strip().lower()
        if repository:
            normalized = remote_url.strip()
            actual = ""
            if normalized.startswith("git@github.com:"):
                actual = normalized.split(":", 1)[1]
            else:
                parsed = urlparse(normalized)
                if parsed.hostname and parsed.hostname.lower() == "github.com":
                    actual = parsed.path.lstrip("/")
            actual = actual.rstrip("/").removesuffix(".git").lower()
            if actual != repository:
                raise PolicyDenied("Git remote does not match the exact repository allowed by coding policy.")
            return
        suffix = str(self.data.get("repository", {}).get("allowed_remote_suffix", "")).strip().lower()
        normalized = remote_url.strip().rstrip("/").lower()
        if not suffix or not normalized.endswith(suffix.rstrip("/")):
            raise PolicyDenied("Git remote does not match the repository allowed by coding policy.")

    def deployment(self) -> dict[str, Any]:
        return dict(self.data.get("deployment", {}))


_SECRET_PATTERNS = [
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"(?i)\b(?:api[_-]?key|secret|token|password)\s*[:=]\s*['\"]?[A-Za-z0-9_./+=-]{16,}"),
]


def find_probable_secrets(text: str) -> list[str]:
    findings: list[str] = []
    for pattern in _SECRET_PATTERNS:
        for match in pattern.finditer(text):
            digest = hashlib.sha256(match.group(0).encode("utf-8", errors="ignore")).hexdigest()[:12]
            findings.append(f"{pattern.pattern[:32]}:{digest}")
    return findings

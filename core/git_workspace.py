"""Policy-constrained Git worktree and branch operations."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Sequence

from core.coding_policy import CodingPolicy, PolicyDenied, find_probable_secrets


class GitCommandError(RuntimeError):
    pass


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return cleaned[:48] or "change"


class GitWorkspaceManager:
    def __init__(self, policy: CodingPolicy) -> None:
        self.policy = policy
        self.repo_root = policy.repo_root
        self.worktree_root = policy.repo_path("worktree_root")

    def _run(
        self,
        argv: Sequence[str],
        *,
        cwd: Path | None = None,
        timeout: int = 120,
        allow_network: bool = False,
    ) -> str:
        self.policy.assert_command(argv, allow_network=allow_network)
        result = subprocess.run(
            list(argv), cwd=str(cwd or self.repo_root), capture_output=True, text=True,
            timeout=timeout, env=os.environ.copy(),
        )
        if result.returncode != 0:
            message = (result.stderr or result.stdout or "Git command failed.").strip()
            raise GitCommandError(message[:2000])
        return result.stdout.strip()

    def git(self, *args: str, cwd: Path | None = None, timeout: int = 120, allow_network: bool = False) -> str:
        return self._run(["git", *args], cwd=cwd, timeout=timeout, allow_network=allow_network)

    def verify_repository(self) -> dict[str, str]:
        top = Path(self.git("rev-parse", "--show-toplevel")).resolve()
        if top != self.repo_root:
            raise PolicyDenied("Configured repository root does not match Git top-level directory.")
        remote = self.git("remote", "get-url", "origin")
        self.policy.assert_remote(remote)
        return {"root": str(top), "remote": remote}

    def prepare(self, workflow_id: int, target_version: str, title: str, *, fetch: bool = True) -> dict[str, Any]:
        self.verify_repository()
        if fetch:
            self.git("fetch", "origin", self.policy.data["repository"].get("default_branch", "main"),
                     allow_network=True, timeout=180)
        default_branch = str(self.policy.data["repository"].get("default_branch", "main"))
        base_ref = f"origin/{default_branch}"
        base_sha = self.git("rev-parse", base_ref)
        branch = f"v{target_version}/{_slug(title)}"
        worktree = (self.worktree_root / f"{workflow_id}-{_slug(title)}").resolve()
        if not worktree.is_relative_to(self.worktree_root.resolve()):
            raise PolicyDenied("Resolved worktree escaped the approved worktree root.")
        if worktree.exists():
            raise GitCommandError(f"Worktree already exists: {worktree}")
        worktree.parent.mkdir(parents=True, exist_ok=True)
        existing = self.git("branch", "--list", branch)
        if existing:
            branch = f"{branch}-{workflow_id}"
        self.git("worktree", "add", "-b", branch, str(worktree), base_ref, timeout=180)
        head_sha = self.git("rev-parse", "HEAD", cwd=worktree)
        return {"branch": branch, "worktree": str(worktree), "base_sha": base_sha, "head_sha": head_sha}

    def changed_files(self, worktree: Path | str) -> list[str]:
        root = Path(worktree).resolve()
        output = self.git("status", "--porcelain=v1", cwd=root)
        files: list[str] = []
        for line in output.splitlines():
            name = line[3:].strip()
            if " -> " in name:
                name = name.split(" -> ", 1)[1]
            if name:
                files.append(name.replace("\\", "/"))
        return files

    def diff_summary(self, worktree: Path | str) -> dict[str, Any]:
        root = Path(worktree).resolve()
        return {
            "files": self.changed_files(root),
            "stat": self.git("diff", "--stat", cwd=root),
            "head_sha": self.git("rev-parse", "HEAD", cwd=root),
        }

    def scan_secrets(self, worktree: Path | str, *, base_ref: str | None = None) -> list[str]:
        root = Path(worktree).resolve()
        if base_ref:
            diff = self.git("diff", "--no-ext-diff", "--binary", f"{base_ref}..HEAD", cwd=root)
            staged = ""
        else:
            diff = self.git("diff", "--no-ext-diff", "--binary", cwd=root)
            staged = self.git("diff", "--cached", "--no-ext-diff", "--binary", cwd=root)
        return sorted(set(find_probable_secrets(f"{diff}\n{staged}")))

    def commit(self, worktree: Path | str, message: str, *, special_approval: bool = False) -> str:
        root = Path(worktree).resolve()
        changed = self.changed_files(root)
        if not changed:
            raise GitCommandError("No changed files are available for a checkpoint commit.")
        self.policy.assert_write_paths(changed, special_approval=special_approval)
        findings = self.scan_secrets(root)
        if findings:
            raise PolicyDenied(f"Probable secrets block commit: {len(findings)} finding(s).")
        self.git("add", "--", *changed, cwd=root)
        self.git("commit", "-m", message, cwd=root)
        return self.git("rev-parse", "HEAD", cwd=root)

    def push(self, worktree: Path | str, branch: str) -> str:
        if not self.policy.feature_enabled("github"):
            raise PolicyDenied("GitHub capability is disabled by policy.")
        return self.git("push", "--set-upstream", "origin", branch, cwd=Path(worktree),
                        allow_network=True, timeout=180)

    def cancel_cleanup(self, worktree: Path | str, *, force: bool = False) -> None:
        root = Path(worktree).resolve()
        if not root.is_relative_to(self.worktree_root.resolve()):
            raise PolicyDenied("Cleanup target escaped the developer worktree root.")
        if root.exists() and self.changed_files(root) and not force:
            raise PolicyDenied("A modified worktree requires explicit cleanup approval.")
        if root.exists():
            self.git("worktree", "remove", str(root), *( ["--force"] if force else [] ))

    def storage(self) -> dict[str, Any]:
        def size(path: Path) -> int:
            if not path.exists():
                return 0
            return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())
        return {"worktree_root": str(self.worktree_root), "worktree_bytes": size(self.worktree_root),
                "worktree_count": len([p for p in self.worktree_root.glob("*") if p.is_dir()]) if self.worktree_root.exists() else 0,
                "git_available": bool(shutil.which("git"))}

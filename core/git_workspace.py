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

    def _assert_worktree(self, worktree: Path | str) -> Path:
        root = Path(worktree).resolve()
        if not root.is_relative_to(self.worktree_root.resolve()):
            raise PolicyDenied("Coding workspace escaped the approved worktree root.")
        return root

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
        root = self._assert_worktree(worktree)
        output = self.git("status", "--porcelain=v1", "-z", "--untracked-files=all", cwd=root)
        records = output.split("\0")
        files: set[str] = set()
        index = 0
        while index < len(records):
            record = records[index]
            index += 1
            if not record:
                continue
            status = record[:2]
            name = record[3:] if len(record) >= 4 else ""
            if name:
                files.add(name.replace("\\", "/"))
            if ("R" in status or "C" in status) and index < len(records):
                source = records[index]
                index += 1
                if source:
                    files.add(source.replace("\\", "/"))
        return sorted(files)

    def diff_summary(self, worktree: Path | str) -> dict[str, Any]:
        root = self._assert_worktree(worktree)
        return {
            "files": self.changed_files(root),
            "stat": self.git("diff", "--stat", cwd=root),
            "head_sha": self.git("rev-parse", "HEAD", cwd=root),
        }

    def diff_metrics(self, worktree: Path | str) -> dict[str, Any]:
        root = self._assert_worktree(worktree)
        files = self.changed_files(root)
        output = self.git("diff", "--numstat", cwd=root)
        added = 0
        deleted = 0
        for line in output.splitlines():
            parts = line.split("\t", 2)
            if len(parts) < 2:
                continue
            try:
                added += int(parts[0]) if parts[0] != "-" else 0
                deleted += int(parts[1]) if parts[1] != "-" else 0
            except ValueError:
                continue
        tracked = {line.split("\t", 2)[-1] for line in output.splitlines() if "\t" in line}
        for relative in (path for path in files if path not in tracked):
            target = (root / relative).resolve()
            if target.is_relative_to(root) and target.is_file():
                try:
                    added += len(target.read_text(encoding="utf-8", errors="replace").splitlines())
                except OSError:
                    pass
        return {
            "files": files,
            "file_count": len(files),
            "added_lines": added,
            "deleted_lines": deleted,
            "changed_lines": added + deleted,
            "head_sha": self.git("rev-parse", "HEAD", cwd=root),
        }

    def diff_patch(self, worktree: Path | str, *, max_bytes: int = 100_000) -> str:
        root = self._assert_worktree(worktree)
        patch = self.git("diff", "--no-ext-diff", "--binary", cwd=root)
        untracked = self.git("ls-files", "--others", "--exclude-standard", "-z", cwd=root)
        additions: list[str] = []
        remaining = max_bytes - len(patch.encode("utf-8", errors="replace"))
        for relative in (item for item in untracked.split("\0") if item):
            if remaining <= 0:
                break
            path = (root / relative).resolve()
            if not path.is_relative_to(root) or not path.is_file():
                continue
            data = path.read_bytes()[:remaining]
            block = f"\n--- /dev/null\n+++ b/{relative}\n" + data.decode("utf-8", errors="replace")
            additions.append(block)
            remaining -= len(block.encode("utf-8", errors="replace"))
        patch += "".join(additions)
        encoded = patch.encode("utf-8", errors="replace")
        if len(encoded) > max_bytes:
            return encoded[:max_bytes].decode("utf-8", errors="replace") + "\n[PATCH TRUNCATED]"
        return patch

    def scan_secrets(self, worktree: Path | str, *, base_ref: str | None = None) -> list[str]:
        root = self._assert_worktree(worktree)
        if base_ref:
            diff = self.git("diff", "--no-ext-diff", "--binary", f"{base_ref}..HEAD", cwd=root)
            staged = ""
        else:
            diff = self.git("diff", "--no-ext-diff", "--binary", cwd=root)
            staged = self.git("diff", "--cached", "--no-ext-diff", "--binary", cwd=root)
        findings = set(find_probable_secrets(f"{diff}\n{staged}"))
        untracked = self.git("ls-files", "--others", "--exclude-standard", "-z", cwd=root)
        max_file = int(self.policy.data.get("workers", {}).get("max_file_bytes", 250_000))
        for relative in (item for item in untracked.split("\0") if item):
            path = (root / relative).resolve()
            if not path.is_relative_to(root) or not path.is_file():
                continue
            try:
                data = path.read_bytes()
            except OSError:
                continue
            if len(data) > max_file:
                findings.add(f"untracked_file_too_large:{relative}")
                continue
            findings.update(find_probable_secrets(data.decode("utf-8", errors="ignore")))
        return sorted(findings)

    def commit(self, worktree: Path | str, message: str, *, special_approval: bool = False) -> str:
        root = self._assert_worktree(worktree)
        changed = self.changed_files(root)
        if not changed:
            raise GitCommandError("No changed files are available for a checkpoint commit.")
        self.policy.assert_write_paths(changed, special_approval=special_approval)
        findings = self.scan_secrets(root)
        if findings:
            raise PolicyDenied(f"Probable secrets block commit: {len(findings)} finding(s).")
        self.git("add", "-A", cwd=root)
        self.git("commit", "-m", message, cwd=root)
        return self.git("rev-parse", "HEAD", cwd=root)

    def push(self, worktree: Path | str, branch: str) -> str:
        if not self.policy.feature_enabled("github"):
            raise PolicyDenied("GitHub capability is disabled by policy.")
        root = self._assert_worktree(worktree)
        return self.git("push", "--set-upstream", "origin", branch, cwd=root,
                        allow_network=True, timeout=180)

    def head(self, worktree: Path | str) -> str:
        return self.git("rev-parse", "HEAD", cwd=self._assert_worktree(worktree))

    def is_clean(self, worktree: Path | str) -> bool:
        return not self.changed_files(worktree)

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

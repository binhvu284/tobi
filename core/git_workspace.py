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
        strip: bool = True,
    ) -> str:
        self.policy.assert_command(argv, allow_network=allow_network)
        # Decode git's bytes as UTF-8 rather than the console codepage. On this host the
        # locale is cp1258, which cannot decode a diff, a filename, or a commit message that
        # carries any non-Latin byte: the reader thread dies and the stream comes back None.
        result = subprocess.run(
            list(argv), cwd=str(cwd or self.repo_root), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout, env=os.environ.copy(),
        )
        if result.returncode != 0:
            message = (result.stderr or result.stdout or "Git command failed.").strip()
            if len(message) > 2000:
                message = f"[earlier command output omitted]\n{message[-1967:]}"
            raise GitCommandError(message)
        return (result.stdout or "").strip() if strip else (result.stdout or "")

    def git(self, *args: str, cwd: Path | None = None, timeout: int = 120,
            allow_network: bool = False, strip: bool = True) -> str:
        return self._run(["git", *args], cwd=cwd, timeout=timeout,
                         allow_network=allow_network, strip=strip)

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

    def _configure_sparse_checkout(self, worktree: Path) -> None:
        """Keep generated dependencies out of disposable coding worktrees."""
        patterns = (
            "/*",
            "!/venv/",
            "!/.venv/",
            "!/**/node_modules/",
            "!/**/__pycache__/",
            "!/**/*.pyc",
            "!/**/*.pyo",
        )
        self.git("sparse-checkout", "set", "--no-cone", *patterns, cwd=worktree, timeout=60)
        self.git("read-tree", "-mu", "HEAD", cwd=worktree, timeout=180)

    def _rollback_failed_prepare(self, worktree: Path, branch: str, base_sha: str) -> list[str]:
        """Remove only disposable state created by a failed worktree checkout."""
        warnings: list[str] = []
        try:
            self.git("worktree", "remove", str(worktree), timeout=60)
        except GitCommandError:
            try:
                if worktree.exists():
                    shutil.rmtree(worktree)
                self.git("worktree", "prune", timeout=60)
            except (GitCommandError, OSError) as exc:
                warnings.append(f"worktree cleanup: {exc}")

        try:
            existing = self.git("branch", "--list", branch)
            if existing and self.git("rev-parse", branch) == base_sha:
                self.git("branch", "-d", branch)
        except GitCommandError as exc:
            warnings.append(f"branch cleanup: {exc}")
        return warnings

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
        try:
            self.git(
                "worktree", "add", "--quiet", "--no-checkout", "-b", branch,
                str(worktree), base_ref, timeout=180,
            )
            self._configure_sparse_checkout(worktree)
        except (GitCommandError, PolicyDenied) as exc:
            warnings = self._rollback_failed_prepare(worktree, branch, base_sha)
            cleanup = f" Cleanup warning: {'; '.join(warnings)}" if warnings else ""
            raise GitCommandError(f"Unable to create isolated coding worktree. {exc}{cleanup}") from exc
        head_sha = self.git("rev-parse", "HEAD", cwd=worktree)
        return {"branch": branch, "worktree": str(worktree), "base_sha": base_sha, "head_sha": head_sha}

    def changed_files(self, worktree: Path | str) -> list[str]:
        root = self._assert_worktree(worktree)
        # `strip=False` matters: a porcelain record is "XY PATH", and an unstaged edit -- the
        # normal state after an agent writes -- has status " M", so stripping ate the leading
        # space of the first record and every path lost its first character. Run 15 reported
        # "ore/awakening.py". That path is then what the quality gate checks against the
        # protected-path list, so a truncated "core/coding_agent.py" would no longer match it.
        output = self.git("status", "--porcelain=v1", "-z", "--untracked-files=all",
                          cwd=root, strip=False)
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

    def restore_paths(self, worktree: Path | str, paths: Sequence[str]) -> list[str]:
        """Restore selected worktree paths after the owner rejects a protected-path action."""
        root = self._assert_worktree(worktree)
        restored: list[str] = []
        for relative in paths:
            normalized = str(relative).replace("\\", "/").lstrip("/")
            target = (root / normalized).resolve()
            if not target.is_relative_to(root):
                raise PolicyDenied("Restore target escaped the approved worktree root.")
            tracked = True
            try:
                self.git("ls-files", "--error-unmatch", "--", normalized, cwd=root)
            except GitCommandError:
                tracked = False
            if tracked:
                self.git("restore", "--staged", "--worktree", "--", normalized, cwd=root)
            else:
                if target.is_file() or target.is_symlink():
                    target.unlink()
                elif target.is_dir():
                    shutil.rmtree(target)
            restored.append(normalized)
        return restored

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

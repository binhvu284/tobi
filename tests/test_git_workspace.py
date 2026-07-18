"""Regression tests for durable Developer worktree preparation."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.coding_policy import CodingPolicy  # noqa: E402
from core.git_workspace import GitCommandError, GitWorkspaceManager  # noqa: E402


def run_git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise AssertionError(result.stderr or result.stdout)
    return result.stdout.strip()


class GitWorkspacePrepareTests(unittest.TestCase):
    def setUp(self) -> None:
        test_root = ROOT / ".tobi" / "test-runs"
        test_root.mkdir(parents=True, exist_ok=True)
        self.root = Path(tempfile.mkdtemp(prefix="git_workspace_", dir=test_root))
        self.origin = self.root / "origin.git"
        self.repo = self.root / "repo"
        subprocess.run(["git", "init", "--bare", str(self.origin)], check=True, capture_output=True)
        self.repo.mkdir()
        run_git(self.repo, "init", "-b", "main")
        run_git(self.repo, "config", "user.email", "workspace@test.local")
        run_git(self.repo, "config", "user.name", "Workspace Test")
        (self.repo / "README.md").write_text("# workspace\n", encoding="utf-8")
        run_git(self.repo, "add", "README.md")
        run_git(self.repo, "commit", "-m", "initial")
        run_git(self.repo, "remote", "add", "origin", str(self.origin))
        run_git(self.repo, "push", "-u", "origin", "main")

        data = json.loads((ROOT / "config" / "coding_policy.v1.json").read_text(encoding="utf-8"))
        data["repository"]["allowed_repository"] = ""
        data["repository"]["allowed_remote_suffix"] = self.origin.name
        data["repository"]["worktree_root"] = ".worktrees"
        self.manager = GitWorkspaceManager(CodingPolicy(data, repo_root=self.repo))

    def tearDown(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    def test_generated_dependencies_are_omitted_from_sparse_checkout(self) -> None:
        generated = self.repo / "venv" / "lib" / "package" / "__pycache__"
        generated.mkdir(parents=True)
        (generated / "module.pyc").write_bytes(b"compiled")
        run_git(self.repo, "add", "-f", "venv")
        run_git(self.repo, "commit", "-m", "track generated dependency")
        run_git(self.repo, "push", "origin", "main")

        prepared = self.manager.prepare(20, "3.20.0", "hygiene checkout", fetch=False)

        worktree = Path(prepared["worktree"])
        self.assertTrue((worktree / "README.md").is_file())
        self.assertFalse((worktree / "venv").exists())

    def test_clean_repository_prepares_an_isolated_worktree(self) -> None:
        prepared = self.manager.prepare(19, "3.19.0", "clean checkout", fetch=False)

        worktree = Path(prepared["worktree"])
        self.assertTrue((worktree / "README.md").is_file())
        self.assertEqual(prepared["base_sha"], prepared["head_sha"])
        self.assertEqual(prepared["branch"], "v3.19.0/clean-checkout")

    def test_failed_prepare_cleanup_removes_disposable_branch_and_directory(self) -> None:
        base_sha = run_git(self.repo, "rev-parse", "origin/main")
        branch = "v3.20.0/failed-prepare"
        worktree = self.repo / ".worktrees" / "21-failed-prepare"
        run_git(self.repo, "branch", branch, base_sha)
        worktree.mkdir(parents=True)
        (worktree / "partial-checkout.txt").write_text("partial\n", encoding="utf-8")

        warnings = self.manager._rollback_failed_prepare(worktree, branch, base_sha)

        self.assertEqual(warnings, [])
        self.assertFalse(worktree.exists())
        self.assertFalse(run_git(self.repo, "branch", "--list", branch))

    def test_command_failures_preserve_the_diagnostic_tail(self) -> None:
        command = "import sys;sys.stderr.write('x'*2500 + '\\nTAIL_MARKER\\n');raise SystemExit(1)"
        with self.assertRaises(GitCommandError) as captured:
            self.manager._run([sys.executable, "-c", command])

        self.assertIn("TAIL_MARKER", str(captured.exception))
        self.assertIn("earlier command output omitted", str(captured.exception))


if __name__ == "__main__":
    unittest.main()

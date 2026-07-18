"""Trusted coding-tool diagnostics and runtime command tests."""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.coding_tools import CodingToolBroker, resolve_runtime_command  # noqa: E402


class FakePolicy:
    data = {"workers": {"max_file_bytes": 250_000, "max_tool_output_bytes": 100_000}}

    def __init__(self, root: Path) -> None:
        self.root = root

    def repo_path(self, key: str) -> Path:
        if key != "worktree_root":
            raise KeyError(key)
        return self.root

    def mandatory_checks(self):
        return []

    def assert_command(self, argv):
        return None

    def assert_write_paths(self, paths, *, special_approval=False):
        return []

    def is_indexable(self, path):
        return True

    def limit(self, name: str, default: int) -> int:
        return default


class CodingToolDiagnosticTests(unittest.TestCase):
    def setUp(self) -> None:
        base = ROOT / ".tobi" / "test-runs"
        base.mkdir(parents=True, exist_ok=True)
        self.root = Path(tempfile.mkdtemp(prefix="coding_diagnostic_", dir=base))
        self.worktree = self.root / "worktree"
        (self.worktree / "core").mkdir(parents=True)
        (self.worktree / "core" / "sample.py").write_text(
            "def healthy():\n    return True\n", encoding="utf-8"
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    def test_python_checks_use_mission_control_interpreter(self) -> None:
        self.assertEqual(resolve_runtime_command(["python", "-V"])[0], sys.executable)
        self.assertEqual(resolve_runtime_command(["npm", "run", "build"])[0], "npm")

    def test_broker_executes_python_check_with_mission_control_interpreter(self) -> None:
        policy = FakePolicy(self.root)
        policy.mandatory_checks = lambda: [["python", "-c", "print('ok')"]]
        broker = CodingToolBroker(policy, self.worktree)
        completed = subprocess.CompletedProcess([], 0, stdout="ok\n", stderr="")

        with patch("core.coding_tools.subprocess.run", return_value=completed) as run:
            result = broker.run_check(0)

        self.assertTrue(result["ok"])
        self.assertEqual(run.call_args.args[0][0], sys.executable)

    def test_performance_tool_returns_bounded_read_only_report(self) -> None:
        observed = []
        broker = CodingToolBroker(
            FakePolicy(self.root), self.worktree,
            on_event=lambda kind, payload: observed.append((kind, payload)),
        )

        result = broker.execute({"action": "inspect_performance", "ignored": "not executed"})

        self.assertIn("grade", result["overall"])
        self.assertIn("score", result["overall"])
        self.assertFalse(result["snapshot_saved"])
        self.assertLessEqual(len(result["findings"]), 20)
        self.assertIn("tool_performance", [kind for kind, _ in observed])


if __name__ == "__main__":
    unittest.main()

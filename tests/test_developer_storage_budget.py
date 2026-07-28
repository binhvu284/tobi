"""Developer storage must not re-walk the disk on every poll.

`GET /api/developer/storage` is one of eight calls the Developer page makes on load and again
on every five-second poll. It was the only one that touched the filesystem, and it walked every
worktree with `Path.rglob` plus a separate `stat` per entry.

Each worktree is a full checkout and `dashboard/dist` is tracked, so fourteen of them came to
410 MB. The call took **9.7 seconds to return 421 bytes** -- on its own most of the page's
fifteen-second budget, which is why "Developer data unavailable" kept coming back and the owner
kept pressing Retry.

Two fixes, both asserted here: walk with `os.scandir` so the OS's directory entry is reused
instead of re-stat'd, and cache the result briefly because disk usage does not change between
polls. Cleanup asks for a fresh reading, since that is the one moment the owner is specifically
asking whether the space came back.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.git_workspace import GitWorkspaceManager  # noqa: E402

FAILURES: list[str] = []


def ok(label: str, condition: bool, detail: str = "") -> None:
    print(f"{'PASS' if condition else 'FAIL'} {label}{('  -> ' + detail) if detail and not condition else ''}")
    if not condition:
        FAILURES.append(label)


base = ROOT / ".tobi" / "test-runs"
base.mkdir(parents=True, exist_ok=True)
sandbox = Path(tempfile.mkdtemp(prefix="storage_budget_", dir=base))

# A shape like the real thing: several "worktrees", each with nested directories.
expected = 0
for tree in range(4):
    for depth in ("", "core", "dashboard/dist/assets", "tests/fixtures"):
        directory = sandbox / f"wt-{tree}" / depth
        directory.mkdir(parents=True, exist_ok=True)
        for index in range(5):
            payload = b"x" * (100 + index)
            (directory / f"f{index}.bin").write_bytes(payload)
            expected += len(payload)

naive = sum(item.stat().st_size for item in sandbox.rglob("*") if item.is_file())
ok("the fixture is what the test thinks it is", naive == expected, f"{naive} vs {expected}")

# --- the walk is correct, not merely fast -------------------------------------------------
ok("scandir walk matches the rglob total it replaces",
   GitWorkspaceManager._tree_bytes(sandbox) == expected,
   f"{GitWorkspaceManager._tree_bytes(sandbox)} vs {expected}")
ok("a missing directory is zero, not an error",
   GitWorkspaceManager._tree_bytes(sandbox / "does-not-exist") == 0)

empty = sandbox / "empty"
empty.mkdir()
ok("an empty directory is zero", GitWorkspaceManager._tree_bytes(empty) == 0)

# Nested-but-empty directories must not be counted as files.
(sandbox / "empty" / "a" / "b").mkdir(parents=True)
ok("directories are not counted as files", GitWorkspaceManager._tree_bytes(empty) == 0)


# --- the result is cached between polls ---------------------------------------------------
class _Policy:
    hash = "test"
    data: dict = {}

    def repo_path(self, name: str) -> Path:
        return sandbox

    def limit(self, name: str, default: int) -> int:
        return default


workspace = GitWorkspaceManager.__new__(GitWorkspaceManager)
workspace.policy = _Policy()
workspace.worktree_root = sandbox
GitWorkspaceManager._storage_cache = None

first = workspace.storage()
ok("the first call reports the real total", first["worktree_bytes"] == expected,
   str(first["worktree_bytes"]))
ok("worktrees are counted as directories", first["worktree_count"] == 5,
   str(first["worktree_count"]))  # 4 wt-* plus "empty"

# Change the tree underneath, then prove the cached call does not pay to notice.
(sandbox / "wt-0" / "late.bin").write_bytes(b"y" * 10_000)

cached = workspace.storage()
ok("a polled call is served from cache", cached["worktree_bytes"] == expected,
   f"{cached['worktree_bytes']} -- a cache miss would have seen the new file")

started = time.perf_counter()
for _ in range(50):
    workspace.storage()
per_call_ms = (time.perf_counter() - started) * 1000 / 50
ok("fifty polled calls stay far under the page's budget", per_call_ms < 5.0,
   f"{per_call_ms:.3f} ms per call")

fresh = workspace.storage(refresh=True)
ok("refresh=True re-walks and sees the change",
   fresh["worktree_bytes"] == expected + 10_000, str(fresh["worktree_bytes"]))
ok("the refreshed value replaces the cache",
   workspace.storage()["worktree_bytes"] == expected + 10_000)

ok("the caller cannot mutate the cache through the returned dict",
   (workspace.storage().__setitem__("worktree_bytes", 1),
    workspace.storage()["worktree_bytes"])[1] == expected + 10_000)

# --- the ttl is a real window, not a one-shot ---------------------------------------------
ok("the cache has a bounded lifetime", 0 < GitWorkspaceManager._STORAGE_TTL_SECONDS <= 600,
   str(GitWorkspaceManager._STORAGE_TTL_SECONDS))
GitWorkspaceManager._storage_cache = (time.monotonic() - GitWorkspaceManager._STORAGE_TTL_SECONDS - 1,
                               {"worktree_bytes": -1})
ok("an expired entry is re-walked rather than served",
   workspace.storage()["worktree_bytes"] == expected + 10_000)

# --- no caller still pays the old cost ----------------------------------------------------
git_source = (ROOT / "core" / "git_workspace.py").read_text(encoding="utf-8")
storage_fn = git_source[git_source.index("def storage("):][:1600]
ok("storage no longer walks with rglob", "rglob" not in storage_fn, storage_fn[:200])
ok("the walk uses scandir", "os.scandir" in git_source)

agent_source = (ROOT / "core" / "coding_agent.py").read_text(encoding="utf-8")
agent_storage = agent_source[agent_source.index("def storage(self"):][:1400]
ok("the agent reuses the same walker for artifacts and index",
   "_tree_bytes" in agent_storage and "rglob(\"*\")" not in agent_storage, agent_storage[:250])
ok("cleanup reports a fresh total, not a cached one",
   "self.storage(refresh=True)" in agent_source)

print(f"\n{'ALL' if not FAILURES else str(len(FAILURES)) + ' OF'} "
      f"{'STORAGE BUDGET CHECKS PASSED' if not FAILURES else 'CHECKS FAILED: ' + ', '.join(FAILURES)}")
raise SystemExit(1 if FAILURES else 0)

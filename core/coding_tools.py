"""Typed, policy-enforced tools exposed to model-based coding workers."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Sequence

from core.coding_policy import CodingPolicy, PolicyDenied


class CodingToolError(RuntimeError):
    pass


def resolve_runtime_command(argv: Sequence[str]) -> list[str]:
    """Run configured Python checks with the interpreter hosting Mission Control."""
    resolved = [str(part) for part in argv]
    if not resolved:
        return resolved
    executable = Path(resolved[0]).name.lower()
    if executable in {"python", "python.exe", "python3", "python3.exe"}:
        resolved[0] = sys.executable
    return resolved


class CodingToolBroker:
    """The only file and command authority available to an in-process LLM worker."""

    def __init__(
        self,
        policy: CodingPolicy,
        worktree: Path | str,
        *,
        validation_commands: Sequence[Sequence[str]] = (),
        special_approval: bool = False,
        on_event: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> None:
        self.policy = policy
        self.worktree = Path(worktree).resolve()
        approved_root = policy.repo_path("worktree_root").resolve()
        if not self.worktree.is_relative_to(approved_root) or not self.worktree.is_dir():
            raise PolicyDenied("Coding tool workspace is outside the approved worktree root.")
        self.special_approval = special_approval
        self.on_event = on_event
        checks = [list(command) for command in policy.mandatory_checks()]
        checks.extend([list(command) for command in validation_commands])
        self.validation_commands = []
        seen: set[tuple[str, ...]] = set()
        for command in checks:
            key = tuple(command)
            if key not in seen:
                seen.add(key)
                self.validation_commands.append(command)
        for command in self.validation_commands:
            self.policy.assert_command(command)
        workers = policy.data.get("workers", {})
        self.max_file_bytes = int(workers.get("max_file_bytes", 250_000))
        self.max_output_bytes = int(workers.get("max_tool_output_bytes", 100_000))

    def _emit(self, kind: str, payload: dict[str, Any]) -> None:
        if self.on_event:
            self.on_event(kind, payload)

    def _resolve(self, relative: str, *, write: bool = False) -> tuple[Path, str]:
        normalized = str(relative or "").replace("\\", "/").lstrip("/")
        if not normalized or normalized in {".", ".."}:
            raise CodingToolError("A repository-relative file path is required.")
        target = (self.worktree / normalized).resolve()
        if not target.is_relative_to(self.worktree):
            raise PolicyDenied("Tool path escaped the approved worktree.")
        rel = target.relative_to(self.worktree).as_posix()
        if write:
            self.policy.assert_write_paths([rel], special_approval=self.special_approval)
        elif not self.policy.is_indexable(rel):
            raise PolicyDenied("Tool read is excluded by coding policy.")
        return target, rel

    def read_file(self, path: str) -> dict[str, Any]:
        target, rel = self._resolve(path)
        if not target.is_file():
            raise CodingToolError(f"File does not exist: {rel}")
        data = target.read_bytes()
        if len(data) > self.max_file_bytes:
            raise CodingToolError(f"File exceeds the {self.max_file_bytes}-byte read limit: {rel}")
        self._emit("tool_read", {"path": rel, "bytes": len(data)})
        return {"path": rel, "content": data.decode("utf-8", errors="replace"), "bytes": len(data)}

    def list_files(self, prefix: str = "", limit: int = 200) -> dict[str, Any]:
        base = self.worktree
        if prefix:
            base, _ = self._resolve(prefix)
        if not base.exists() or not base.is_dir():
            raise CodingToolError("List prefix is not a directory.")
        files: list[str] = []
        for item in base.rglob("*"):
            if len(files) >= max(1, min(limit, 500)):
                break
            if not item.is_file():
                continue
            rel = item.resolve().relative_to(self.worktree).as_posix()
            if self.policy.is_indexable(rel):
                files.append(rel)
        files.sort()
        self._emit("tool_list", {"prefix": prefix, "count": len(files)})
        return {"files": files, "truncated": len(files) >= max(1, min(limit, 500))}

    def search(self, query: str, prefix: str = "", limit: int = 50) -> dict[str, Any]:
        needle = str(query or "").strip()
        if len(needle) < 2:
            raise CodingToolError("Search query must contain at least two characters.")
        listed = self.list_files(prefix, limit=500)["files"]
        matches: list[dict[str, Any]] = []
        for rel in listed:
            target, _ = self._resolve(rel)
            if target.stat().st_size > self.max_file_bytes:
                continue
            text = target.read_text(encoding="utf-8", errors="ignore")
            for number, line in enumerate(text.splitlines(), 1):
                if needle.lower() in line.lower():
                    matches.append({"path": rel, "line": number, "text": line[:500]})
                    if len(matches) >= max(1, min(limit, 200)):
                        self._emit("tool_search", {"query": needle, "count": len(matches)})
                        return {"matches": matches, "truncated": True}
        self._emit("tool_search", {"query": needle, "count": len(matches)})
        return {"matches": matches, "truncated": False}

    def write_file(self, path: str, content: str) -> dict[str, Any]:
        target, rel = self._resolve(path, write=True)
        data = str(content).encode("utf-8")
        if len(data) > self.max_file_bytes:
            raise CodingToolError(f"Write exceeds the {self.max_file_bytes}-byte file limit: {rel}")
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=str(target.parent))
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        self._emit("tool_write", {"path": rel, "bytes": len(data)})
        return {"path": rel, "bytes": len(data)}

    def replace_text(self, path: str, old: str, new: str, count: int = 1) -> dict[str, Any]:
        current = self.read_file(path)
        source = current["content"]
        occurrences = source.count(old)
        if not old or occurrences == 0:
            raise CodingToolError("Replacement source text was not found.")
        if count == 1 and occurrences != 1:
            raise CodingToolError(f"Replacement source is ambiguous ({occurrences} matches).")
        updated = source.replace(old, new, count if count > 0 else occurrences)
        result = self.write_file(path, updated)
        result["replacements"] = min(occurrences, count) if count > 0 else occurrences
        return result

    def run_check(self, index: int) -> dict[str, Any]:
        if index < 0 or index >= len(self.validation_commands):
            raise CodingToolError("Validation command index is out of range.")
        argv = self.validation_commands[index]
        self.policy.assert_command(argv)
        runtime_argv = resolve_runtime_command(argv)
        completed = subprocess.run(
            runtime_argv,
            cwd=str(self.worktree),
            capture_output=True,
            text=True,
            timeout=self.policy.limit("command_timeout_seconds", 900),
        )
        output = (completed.stdout + completed.stderr).encode("utf-8", errors="replace")[-self.max_output_bytes:]
        result = {
            "index": index,
            "argv": argv,
            "ok": completed.returncode == 0,
            "exit_code": completed.returncode,
            "output": output.decode("utf-8", errors="replace"),
        }
        self._emit("tool_check", {key: value for key, value in result.items() if key != "output"})
        return result

    def inspect_performance(self) -> dict[str, Any]:
        """Run the trusted quick analyzer against this worktree without persisting a snapshot."""
        trusted_root = Path(__file__).resolve().parents[1]
        script = """
import importlib.util
import json
import pathlib
import sys

trusted_root = pathlib.Path(sys.argv[1]).resolve()
worktree = pathlib.Path(sys.argv[2]).resolve()
sys.path.insert(0, str(trusted_root))
source = trusted_root / "core" / "performance_doctor.py"
spec = importlib.util.spec_from_file_location("_tobi_trusted_performance_doctor", source)
if spec is None or spec.loader is None:
    raise RuntimeError("Performance Doctor could not be loaded.")
doctor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(doctor)
doctor._ROOT = worktree
doctor._GRAPH = worktree / "graphify-out" / "graph.json"
doctor._AST = worktree / "graphify-out" / ".graphify_ast.json"
doctor._save_snapshot = lambda result, depth: None
doctor.trend = lambda limit=30: []
print(json.dumps(doctor.analyze("quick"), ensure_ascii=True, default=str))
"""
        completed = subprocess.run(
            [sys.executable, "-I", "-c", script, str(trusted_root), str(self.worktree)],
            cwd=str(trusted_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=min(self.policy.limit("command_timeout_seconds", 900), 120),
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "Analyzer failed.")[-2000:]
            raise CodingToolError(f"Performance Doctor failed: {detail.strip()}")
        try:
            report = json.loads(completed.stdout.strip())
        except (TypeError, json.JSONDecodeError) as exc:
            raise CodingToolError("Performance Doctor returned malformed output.") from exc
        result = {
            "overall": report.get("overall") or {},
            "counts": report.get("counts") or {},
            "subsystems": list(report.get("subsystems") or [])[:20],
            "findings": list(report.get("findings") or [])[:20],
            "freshness": report.get("freshness") or {},
            "diagnosis": str(report.get("diagnosis") or "")[:4000],
            "generated_ms": report.get("generated_ms"),
            "snapshot_saved": False,
        }
        self._emit("tool_performance", {
            "overall": result["overall"],
            "counts": result["counts"],
            "snapshot_saved": False,
        })
        return result

    def execute(self, action: dict[str, Any]) -> dict[str, Any]:
        name = str(action.get("action", "")).strip()
        if name == "read_file":
            return self.read_file(str(action.get("path", "")))
        if name == "list_files":
            return self.list_files(str(action.get("prefix", "")), int(action.get("limit", 200)))
        if name == "search":
            return self.search(str(action.get("query", "")), str(action.get("prefix", "")), int(action.get("limit", 50)))
        if name == "write_file":
            return self.write_file(str(action.get("path", "")), str(action.get("content", "")))
        if name == "replace_text":
            return self.replace_text(
                str(action.get("path", "")), str(action.get("old", "")), str(action.get("new", "")),
                int(action.get("count", 1)),
            )
        if name == "run_check":
            return self.run_check(int(action.get("index", -1)))
        if name == "inspect_performance":
            return self.inspect_performance()
        raise CodingToolError(f"Unsupported coding tool action: {name or 'missing'}")

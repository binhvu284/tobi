"""Graphify plus lexical repository snapshots for scoped coding context."""
from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.coding_policy import CodingPolicy
from core.development_store import DevelopmentStore
from core.proc import no_window


class RepositoryIndex:
    def __init__(self, policy: CodingPolicy, store: DevelopmentStore) -> None:
        self.policy = policy
        self.store = store
        self.root = policy.repo_root
        self.index_root = policy.repo_path("index_root")

    def _git(self, *args: str, root: Path | None = None) -> str:
        target = (root or self.root).resolve()
        result = subprocess.run(
            ["git", "-C", str(target), *args], capture_output=True, text=True, timeout=30,
            creationflags=no_window(),
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "Git index command failed.")
        return result.stdout.strip()

    def current_sha(self, root: Path | None = None) -> str:
        return self._git("rev-parse", "HEAD", root=root)

    def build(self, root: Path | str | None = None) -> dict[str, Any]:
        source_root = Path(root).resolve() if root else self.root
        sha = self.current_sha(source_root)
        files: list[dict[str, Any]] = []
        for relative in self._git("ls-files", root=source_root).splitlines():
            path = source_root / relative
            if not path.is_file() or not self.policy.is_indexable(relative):
                continue
            stat = path.stat()
            files.append({"path": relative.replace("\\", "/"), "size": stat.st_size})

        graph_path = source_root / "graphify-out" / "graph.json"
        graph = {"available": False, "built_at_commit": None, "nodes": []}
        if graph_path.is_file() and self.policy.is_indexable(graph_path):
            try:
                raw = json.loads(graph_path.read_text(encoding="utf-8"))
                graph = {
                    "available": True,
                    "built_at_commit": raw.get("built_at_commit"),
                    "stale": raw.get("built_at_commit") != sha,
                    "nodes": [
                        {"id": node.get("id"), "label": node.get("label"), "source_file": node.get("source_file")}
                        for node in raw.get("nodes", []) if node.get("source_file")
                    ],
                }
            except (OSError, json.JSONDecodeError):
                graph["error"] = "Graphify snapshot could not be parsed."

        self.index_root.mkdir(parents=True, exist_ok=True)
        manifest = {
            "main_sha": sha,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "files": files,
            "graphify": graph,
            "exclusions": self.policy.data.get("index_exclusions", []),
        }
        output = self.index_root / f"{sha[:12]}.json"
        output.write_text(json.dumps(manifest, ensure_ascii=True, separators=(",", ":")), encoding="utf-8")
        conn = self.store.connect()
        try:
            conn.execute(
                "INSERT INTO repo_snapshots(main_sha,graphify_version,index_path,exclusions_json,generated_at) VALUES (?,?,?,?,?)",
                (sha, str(graph.get("built_at_commit") or ""), str(output),
                 json.dumps(manifest["exclusions"]), manifest["generated_at"]),
            )
            conn.commit()
        finally:
            conn.close()
        return {"main_sha": sha, "index_path": str(output), "file_count": len(files),
                "graphify_available": graph.get("available", False), "graphify_stale": graph.get("stale", True)}

    def search(self, query: str, *, limit: int = 30, max_bytes: int = 500_000,
               root: Path | str | None = None) -> list[dict[str, Any]]:
        source_root = Path(root).resolve() if root else self.root
        terms = [term.lower() for term in query.split() if len(term) >= 3][:12]
        if not terms:
            return []
        results: list[dict[str, Any]] = []
        consumed = 0
        graph_scores: dict[str, int] = {}
        graph_path = source_root / "graphify-out" / "graph.json"
        if graph_path.is_file():
            try:
                raw = json.loads(graph_path.read_text(encoding="utf-8"))
                for node in raw.get("nodes", []):
                    source = str(node.get("source_file") or "")
                    haystack = f"{node.get('label', '')} {source}".lower()
                    score = sum(6 for term in terms if term in haystack)
                    if source and score:
                        graph_scores[source] = graph_scores.get(source, 0) + score
            except (OSError, json.JSONDecodeError):
                pass
        for relative in self._git("ls-files", root=source_root).splitlines():
            path = source_root / relative
            if not path.is_file() or not self.policy.is_indexable(relative):
                continue
            if path.stat().st_size > 250_000:
                continue
            lowered_path = relative.lower()
            path_score = sum(4 for term in terms if term in lowered_path) + graph_scores.get(relative, 0)
            text = ""
            if path_score == 0 and consumed < max_bytes:
                try:
                    text = path.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                consumed += len(text.encode("utf-8", errors="ignore"))
            lowered = text.lower()
            body_score = sum(min(lowered.count(term), 10) for term in terms)
            score = path_score + body_score
            if score:
                results.append({
                    "path": relative.replace("\\", "/"), "score": score,
                    "sha256": hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest() if text else None,
                })
        return sorted(results, key=lambda item: (-item["score"], item["path"]))[:max(1, min(limit, 100))]

"""Mirror Markdown feature plans into structured developer task state."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from core.development_store import DevelopmentStore


REPO_ROOT = Path(__file__).resolve().parents[1]
QUEUE_PATH = REPO_ROOT / "docs" / "feature-idea-queue" / "QUEUE.md"
_LINK_RE = re.compile(r"\[[^]]+\]\(([^)]+)\)")
_DEP_RE = re.compile(r"(?:after|depends?\s+on|prerequisite(?:\s+item)?)\s+#(\d+)", re.IGNORECASE)


def _plain(text: str) -> str:
    return re.sub(r"[*_`]", "", text).strip()


def parse_queue(path: Path | str = QUEUE_PATH) -> list[dict[str, Any]]:
    queue_path = Path(path)
    base = queue_path.parent
    items: list[dict[str, Any]] = []
    for raw in queue_path.read_text(encoding="utf-8").splitlines():
        if not re.match(r"^\|\s*\d+\s*\|", raw):
            continue
        parts = [part.strip() for part in raw.strip().strip("|").split("|")]
        if len(parts) < 5:
            continue
        queue_id = int(parts[0])
        title, queue_status, effort, spec_cell = parts[1:5]
        notes = " | ".join(parts[5:]).strip() if len(parts) > 5 else ""
        match = _LINK_RE.search(spec_cell)
        plan_name = match.group(1) if match else ""
        plan_path = (base / plan_name).resolve() if plan_name else queue_path.resolve()
        if not plan_path.is_relative_to(REPO_ROOT) or plan_path.suffix.lower() != ".md":
            raise ValueError(f"Queue item #{queue_id} references an unsafe plan path.")
        plan_bytes = plan_path.read_bytes() if plan_path.is_file() else raw.encode("utf-8")
        plan_text = plan_bytes.decode("utf-8", errors="replace")
        criteria = [
            line.strip()[2:].strip()
            for line in plan_text.splitlines()
            if line.strip().startswith("- ") and any(word in line.lower() for word in ("must", "accept", "pass", "cannot", "never"))
        ][:40]
        dependencies = sorted({int(value) for value in _DEP_RE.findall(f"{queue_status} {notes}")})
        lowered = queue_status.lower()
        status = "completed" if "done" in lowered else "planned"
        risk = "critical" if "critical" in notes.lower() or "high conflict" in notes.lower() else "medium"
        target_match = re.search(r"`v?(\d+\.\d+\.\d+)`", f"{notes}\n{plan_text[:2000]}")
        items.append({
            "queue_id": queue_id,
            "title": _plain(title),
            "plan_path": plan_path.relative_to(REPO_ROOT).as_posix() if plan_path.is_relative_to(REPO_ROOT) else str(plan_path),
            "plan_hash": hashlib.sha256(plan_bytes).hexdigest(),
            "acceptance_criteria": criteria,
            "dependencies": dependencies,
            "status": status,
            "risk": risk,
            "target_version": target_match.group(1) if target_match else None,
            "queue_status": _plain(queue_status),
            "queue_effort": effort,
        })
    return items


def sync_queue(store: DevelopmentStore, path: Path | str = QUEUE_PATH) -> list[dict[str, Any]]:
    return [store.upsert_task(item) for item in parse_queue(path)]

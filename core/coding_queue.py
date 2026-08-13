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
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_BULLET_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(.+?)\s*$")


def _plain(text: str) -> str:
    without_links = re.sub(r"\[([^]]+)\]\([^)]+\)", r"\1", text)
    return re.sub(r"[*_`]", "", without_links).strip()


def queue_execution_state(queue_status: str | None) -> str:
    """Map owner-facing Queue text to the runtime eligibility vocabulary."""
    value = _plain(str(queue_status or "")).lower()
    if "blocked" in value:
        return "blocked"
    if "in progress" in value or re.search(r"\bactive\b", value):
        return "in_progress"
    if re.search(r"\b(?:done|delivered|completed|merged)\b", value):
        return "done"
    # Empty status is retained for legacy/test-created tasks. Draft, Ready, and
    # Queued all still pass through strict preflight before a run can exist.
    return "ready"


def task_execution_state(task: dict[str, Any]) -> str:
    status = str(task.get("status") or "")
    if status == "completed":
        return "done"
    if status in {"approved", "running"}:
        return "in_progress"
    if status in {"blocked", "failed", "paused"}:
        return "blocked"
    if bool(task.get("status_override")) and status == "planned":
        return "ready"
    return queue_execution_state(task.get("queue_status"))


def _criteria_from_plan(plan_text: str) -> list[str]:
    """Read criteria from their section without treating every plan bullet as a gate."""
    lines = plan_text.splitlines()
    section: list[str] = []
    section_level: int | None = None
    for line in lines:
        heading = _HEADING_RE.match(line.strip())
        if heading:
            level = len(heading.group(1))
            title = _plain(heading.group(2)).lower()
            if section_level is not None and level <= section_level:
                break
            if section_level is None and (
                title.startswith("acceptance criteria")
                or title in {"acceptance", "definition of done"}
            ):
                section_level = level
            continue
        if section_level is not None:
            section.append(line)

    scoped = [
        match.group(1).strip()
        for line in section
        if (match := _BULLET_RE.match(line))
    ]
    if scoped:
        return scoped[:40]

    # Legacy plans without an explicit section keep the previous conservative behavior.
    return [
        line.strip()[2:].strip()
        for line in lines
        if line.strip().startswith("- ")
        and any(word in line.lower() for word in ("must", "accept", "pass", "cannot", "never"))
    ][:40]


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
        if len(parts) >= 6:
            # Current Queue schema: # | ID | Name/link | Description | Status | Notes.
            # The previous parser still treated these as the legacy five-column fields,
            # which made the Name cell the status and classified every item as planned.
            title = parts[2]
            spec_cell = parts[2]
            effort = parts[3]
            queue_status = parts[4]
            notes = " | ".join(parts[5:]).strip()
        else:
            # Legacy schema retained for old fixtures and archived queue snapshots.
            title, queue_status, effort, spec_cell = parts[1:5]
            notes = ""
        match = _LINK_RE.search(spec_cell)
        plan_name = match.group(1) if match else ""
        plan_path = (base / plan_name).resolve() if plan_name else queue_path.resolve()
        if not plan_path.is_relative_to(REPO_ROOT) or plan_path.suffix.lower() != ".md":
            raise ValueError(f"Queue item #{queue_id} references an unsafe plan path.")
        plan_bytes = plan_path.read_bytes() if plan_path.is_file() else raw.encode("utf-8")
        plan_text = plan_bytes.decode("utf-8", errors="replace")
        criteria = _criteria_from_plan(plan_text)
        dependencies = sorted({int(value) for value in _DEP_RE.findall(f"{queue_status} {notes}")})
        status = "completed" if queue_execution_state(queue_status) == "done" else "planned"
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
    synchronized: list[dict[str, Any]] = []
    for item in parse_queue(path):
        row = store.upsert_task(item)
        row["source_queue_status"] = item.get("queue_status")
        row["status_authority"] = (
            "developer_runtime" if bool(row.get("status_override")) else "queue_markdown"
        )
        synchronized.append(row)
    return synchronized

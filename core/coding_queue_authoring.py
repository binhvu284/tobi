"""Locked, conflict-detecting authoring for Queue Markdown and plan files."""
from __future__ import annotations

import hashlib
import os
import re
import tempfile
import threading
from pathlib import Path
from typing import Any

from core.coding_queue import QUEUE_PATH, REPO_ROOT, parse_queue


_LOCK = threading.Lock()


def queue_hash() -> str:
    return hashlib.sha256(QUEUE_PATH.read_bytes()).hexdigest()


def _slug(value: str) -> str:
    result = re.sub(r"[^A-Za-z0-9]+", "_", value.strip()).strip("_").upper()
    return result[:80] or "DEVELOPMENT_ITEM"


def _clean_cell(value: str) -> str:
    return re.sub(r"\s+", " ", value).replace("|", "-").strip()


def _table_cells(line: str) -> list[str]:
    value = line.strip()
    if not value.startswith("|") or not value.endswith("|"):
        return []
    return [cell.strip() for cell in value.strip("|").split("|")]


def _queue_table(lines: list[str]) -> tuple[int, list[str]]:
    for index, line in enumerate(lines[:-1]):
        columns = _table_cells(line)
        normalized = [column.lower() for column in columns]
        if not columns or normalized[0] != "#" or "status" not in normalized:
            continue
        current = {"id", "name", "description", "notes"}.issubset(normalized)
        legacy = {"feature", "spec", "notes"}.issubset(normalized)
        separator = _table_cells(lines[index + 1])
        valid_separator = (
            len(separator) == len(columns)
            and all(re.fullmatch(r":?-{3,}:?", cell) for cell in separator)
        )
        if (current or legacy) and valid_separator:
            return index, normalized
    raise RuntimeError("QUEUE.md table header could not be located.")


def _queue_row(
    columns: list[str],
    *,
    queue_id: int,
    title: str,
    objective: str,
    effort: str,
    plan_name: str,
    notes: str,
) -> str:
    values = {
        "#": str(queue_id),
        "id": f"`DEV-QUEUE-{queue_id:03d}`",
        "name": f"[**{title}**]({plan_name})",
        "description": _clean_cell(objective),
        "status": "Draft",
        "notes": notes,
        "feature": f"**{title}**",
        "solo time (full -> left)": _clean_cell(effort),
        "spec": f"[{plan_name}]({plan_name})",
    }
    unknown = [column for column in columns if column not in values]
    if unknown:
        raise RuntimeError(f"QUEUE.md has unsupported columns: {', '.join(unknown)}")
    return "| " + " | ".join(values[column] for column in columns) + " |"


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def create_queue_item(
    *,
    title: str,
    objective: str,
    acceptance_criteria: list[str],
    dependencies: list[int] | None = None,
    effort: str = "1-2 focus days -> same",
    risk: str = "medium",
    goal_ids: list[int] | None = None,
    expected_queue_hash: str,
    plan_markdown: str | None = None,
    source_note: str = "Created in Developer Work.",
) -> dict[str, Any]:
    title = _clean_cell(title)
    objective = objective.strip()
    criteria = [item.strip() for item in acceptance_criteria if item.strip()]
    if len(title) < 3 or len(objective) < 10 or not criteria:
        raise ValueError("Title, objective, and at least one acceptance criterion are required.")
    dependencies = sorted({int(item) for item in dependencies or [] if int(item) > 0})
    goal_ids = sorted({int(item) for item in goal_ids or [] if int(item) > 0})
    with _LOCK:
        current_hash = queue_hash()
        if not expected_queue_hash or current_hash != expected_queue_hash:
            raise RuntimeError("QUEUE.md changed outside this form. Refresh and review before saving.")
        existing = parse_queue(QUEUE_PATH)
        queue_id = max((int(item["queue_id"]) for item in existing), default=0) + 1
        plan_name = f"{_slug(title)}_PLAN.md"
        plan_path = QUEUE_PATH.parent / plan_name
        suffix = 2
        while plan_path.exists():
            plan_name = f"{_slug(title)}_{suffix}_PLAN.md"
            plan_path = QUEUE_PATH.parent / plan_name
            suffix += 1
        plan = plan_markdown.strip() if plan_markdown else "\n".join([
            f"# {title}",
            "",
            "## Objective",
            objective,
            "",
            "## Acceptance Criteria",
            *[f"- Must {item.removeprefix('Must ').removeprefix('must ')}" for item in criteria],
            "",
            "## Dependencies",
            *( [f"- Queue item #{item}" for item in dependencies] or ["- None"] ),
            "",
            "## Goal Links",
            *( [f"- Development Goal #{item}" for item in goal_ids] or ["- None"] ),
            "",
            "## Delivery Notes",
            "- Start only after strict Developer preflight passes.",
            "- Completion requires deterministic checks, criterion evidence, and independent review.",
            "",
        ])
        queue_text = QUEUE_PATH.read_text(encoding="utf-8")
        lines = queue_text.splitlines()
        header, columns = _queue_table(lines)
        separator = header + 1
        dependency_note = f" Depends on {' and '.join(f'#{item}' for item in dependencies)}." if dependencies else ""
        risk_note = " Critical scope." if risk.lower() in {"high", "critical"} else ""
        row = _queue_row(
            columns,
            queue_id=queue_id,
            title=title,
            objective=objective,
            effort=effort,
            plan_name=plan_name,
            notes=f"{_clean_cell(source_note)}{dependency_note}{risk_note}",
        )
        lines.insert(separator + 1, row)
        _atomic_write(plan_path, plan.rstrip() + "\n")
        try:
            _atomic_write(QUEUE_PATH, "\n".join(lines) + "\n")
        except Exception:
            plan_path.unlink(missing_ok=True)
            raise
        created = next(item for item in parse_queue(QUEUE_PATH) if int(item["queue_id"]) == queue_id)
        return {
            **created,
            "queue_hash": queue_hash(),
            "goal_ids": goal_ids,
            "plan_path": plan_path.relative_to(REPO_ROOT).as_posix(),
        }

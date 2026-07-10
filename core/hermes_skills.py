"""
HERMES SKILLS (read-only) — TOBI Premium Ability (#14).

A read-only parser for the repo's Hermes skill markdown files
(``hermes_skills/*.md``). It surfaces skill metadata for the Ability dashboard —
name, description, status, risk, version, last-modified — **without** executing,
editing, or mirroring anything to a database. Execution stays behind Conductor
human review (a future, approval-gated step); v1 marks every skill
``approval_required`` and ``can_execute=False``.

Never touches machine-level ``~/.hermes`` folders. A missing folder or a broken
file degrades gracefully (empty list / minimal metadata with a parse warning).
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

# Repo skill files live at <repo>/hermes_skills; this module is <repo>/core/hermes_skills.py.
SKILLS_DIR = Path(__file__).resolve().parent.parent / "hermes_skills"

_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.*\S)\s*$")
_VERSION = re.compile(r"(?:^|\n)\s*(?:version|v)\s*[:=]\s*v?(\d+)", re.I)


def _clean_heading(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lstrip("#").strip())


def _base(f: Path) -> dict:
    return {
        "id": f.stem,
        "name": f.stem.replace("_", " ").title(),
        "source": "hermes_repo_file",
        "file_path": f"hermes_skills/{f.name}",
        "status": "available",
        "risk_tier": "approval_required",   # execution is future + human-review gated
        "can_execute": False,
        "version": 1,
        "description": "",
        "last_modified": None,
    }


def _parse_one(path: Path) -> dict:
    item = _base(path)
    raw = path.read_text(encoding="utf-8", errors="replace")
    lines = raw.splitlines()

    # name = first markdown heading, cleaned
    for ln in lines:
        m = _HEADING.match(ln)
        if m:
            item["name"] = _clean_heading(m.group(1)) or item["name"]
            break

    # description = first useful prose paragraph (skip headings, code fences, tables, lists)
    for ln in lines:
        s = ln.strip()
        if not s or s.startswith(("#", "```", "|", "-", "*", ">", "{")):
            continue
        item["description"] = re.sub(r"\s+", " ", s)[:280]
        break

    # version = explicit marker if present, else 1
    mv = _VERSION.search(raw)
    if mv:
        try:
            item["version"] = int(mv.group(1))
        except ValueError:
            pass

    try:
        item["last_modified"] = datetime.fromtimestamp(
            path.stat().st_mtime, tz=timezone.utc).isoformat()
    except Exception:
        pass
    return item


def list_skills() -> list[dict]:
    """All repo Hermes skills, sorted by id. Missing folder → []. Never raises."""
    try:
        if not SKILLS_DIR.is_dir():
            return []
        files = sorted(SKILLS_DIR.glob("*.md"))
    except Exception:
        return []
    out: list[dict] = []
    for f in files:
        try:
            out.append(_parse_one(f))
        except Exception:
            item = _base(f)
            item["description"] = "(could not parse this skill file)"
            item["parse_warning"] = True
            out.append(item)
    return out


def skills_report() -> dict:
    items = list_skills()
    return {"items": items, "count": len(items)}

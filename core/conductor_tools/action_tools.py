"""Conductor action tools — create/update/delete project·task·goal·resource, memory,
Office V3, and missions (the write path).

Extracted from core/conductor.py (Phase 2 — pre-#21 decomposition). Verbatim move;
behavior identical. Includes the _resolve_or_create_project helper (calls
tool_create_project — kept here to avoid a common->tool cycle) and the _TASK_STATUS_V1
lookup (used only by tool_update_task). Shared helpers from core.conductor_tools.common;
core.* imported inline. Registered into ACT_TOOLS back in conductor.py.
"""
from __future__ import annotations

from typing import Any, Optional  # noqa: F401 - used in signatures

from core.conductor_tools.common import (_AGENT_ALIASES, _EMOJI_BY_CATEGORY, _TASK_AGENTS,
                                         _TASK_PRIORITY, _TASK_STATUS_LEGACY, _conn, _pm_log,
                                         _pm_recalc)
def tool_remember(fact: str = "", category: Optional[str] = None, **_: Any) -> dict:
    from core import brain
    fact = (fact or "").strip()
    if not fact:
        return {"error": "fact is required"}
    try:
        res = brain.remember(fact, category)
    except Exception as e:
        return {"error": str(e)[:200]}
    return {"ok": True, "saved": fact[:80], "detail": res}


def tool_create_project(name: str = "", description: str = "", category: str = "", **_: Any) -> dict:
    """Create a project on the PM board the owner sees (pm_projects), status 'active'."""
    name = (name or "").strip()
    if not name:
        return {"error": "name is required"}
    conn = _conn()
    try:
        cur = conn.execute(
            "INSERT INTO pm_projects (name, description, status, size, category, emoji_icon, accent_color, created_by) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (name, (description or None), "active", "medium", (category or "General"), "📁", "#58a6ff", "tobi"),
        )
        pid = cur.lastrowid
        _pm_log(conn, pid, "project.created", f"Project '{name}' created via TOBI")
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "project_id": pid, "name": name, "status": "active"}


def tool_create_task(project_id: int = 0, title: str = "", description: str = "", **_: Any) -> dict:
    """Create a task inside a PM project (tasks.pm_project_id) so it appears on the board + task list."""
    title = (title or "").strip()
    if not title:
        return {"error": "title is required"}
    try:
        project_id = int(project_id)
    except Exception:
        project_id = 0
    if not project_id:
        return {"error": "project_id is required — call list_projects first to find it"}
    conn = _conn()
    try:
        if not conn.execute("SELECT 1 FROM pm_projects WHERE id=?", (project_id,)).fetchone():
            return {"error": f"no project with id {project_id} — call list_projects to find a real id"}
        next_sort = conn.execute("SELECT COALESCE(MAX(sort_order), 0)+1 FROM tasks").fetchone()[0]
        cur = conn.execute(
            "INSERT INTO tasks (title, objective, description, status, status_v1, priority, priority_label, "
            "owner_label, agent_key, pm_project_id, created_at, updated_at, sort_order) "
            "VALUES (?,?,?,?,?,5,?,?,?,?,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,?)",
            (title, title, (description or None), "pending", "planned", "P2", "owner", "tobi", project_id, next_sort),
        )
        tid = cur.lastrowid
        _pm_log(conn, project_id, "task.created", f"Task '{title}' added via TOBI")
        _pm_recalc(conn, project_id)
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "task_id": tid, "title": title, "project_id": project_id}


def tool_create_resource(project_id: int = 0, url: str = "", name: str = "", text: str = "", **_: Any) -> dict:
    """Add a resource to a project's Resources drive — either a web link (url) or a text note (text)."""
    try:
        project_id = int(project_id)
    except Exception:
        project_id = 0
    if not project_id:
        return {"error": "project_id is required — call list_projects first"}
    url = (url or "").strip()
    text = (text or "").strip()
    if not url and not text:
        return {"error": "either url or text is required"}
    from core import pm_resources as pmres
    conn = _conn()
    try:
        if not conn.execute("SELECT 1 FROM pm_projects WHERE id=?", (project_id,)).fetchone():
            return {"error": f"no project with id {project_id}"}
        if url:
            meta = pmres.build_link(url, name or None)
            cur = conn.execute(
                "INSERT INTO pm_resources (project_id, kind, name, ext, source, rtype, url, text_content, created_by) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (project_id, "link", meta["name"], meta.get("ext"), meta["source"], meta["rtype"],
                 meta["url"], meta.get("text_content"), "tobi"),
            )
        else:
            fname = (name or "note").strip() or "note"
            if "." not in fname:
                fname += ".md"
            meta = pmres.save_file(project_id, fname, text.encode("utf-8"))
            cur = conn.execute(
                "INSERT INTO pm_resources (project_id, kind, name, ext, source, rtype, "
                "size_bytes, disk_path, mime, text_content, created_by) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (project_id, "file", meta["name"], meta["ext"], "device", meta["rtype"],
                 meta["size_bytes"], meta["disk_path"], meta["mime"], meta["text_content"], "tobi"),
            )
            conn.execute("UPDATE pm_projects SET resources_bytes=? WHERE id=?",
                         (pmres.project_bytes(project_id), project_id))
        rid = cur.lastrowid
        _pm_log(conn, project_id, "resource.added", f"Resource '{meta['name']}' added via TOBI")
        conn.commit()
    finally:
        conn.close()
    try:  # index for per-project RAG (best-effort, separate connection)
        pmres.index_resource(rid, project_id, meta.get("text_content"))
    except Exception:
        pass
    return {"ok": True, "resource_id": rid, "project_id": project_id, "name": meta["name"]}


def tool_set_project_description(project_id: int = 0, description: str = "", **_: Any) -> dict:
    """Set (overwrite) a project's plain-text Overview description."""
    try:
        project_id = int(project_id)
    except Exception:
        return {"error": "project_id must be an integer"}
    description = (description or "").strip()
    conn = _conn()
    try:
        if not conn.execute("SELECT 1 FROM pm_projects WHERE id=?", (project_id,)).fetchone():
            return {"error": f"no project with id {project_id}"}
        conn.execute("UPDATE pm_projects SET description=? WHERE id=?", (description or None, project_id))
        _pm_log(conn, project_id, "project.description", "Description updated via TOBI")
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "project_id": project_id, "description": description}


def tool_pick_project_icon(project_id: int = 0, emoji: str = "", icon: str = "", **_: Any) -> dict:
    """Set a project's icon. Pass emoji (e.g. '🚀') or icon (a lucide key). Omit both to auto-pick."""
    try:
        project_id = int(project_id)
    except Exception:
        return {"error": "project_id must be an integer"}
    conn = _conn()
    try:
        row = conn.execute("SELECT id, name, category FROM pm_projects WHERE id=?", (project_id,)).fetchone()
        if not row:
            return {"error": f"no project with id {project_id}"}
        if (emoji or "").strip():
            icon_type, icon_value = "emoji", emoji.strip()
        elif (icon or "").strip():
            icon_type, icon_value = "icon", icon.strip()
        else:
            cat = (row["category"] or "").lower()
            pick = _EMOJI_BY_CATEGORY.get(cat)
            if not pick:
                import hashlib
                pool = list(_EMOJI_BY_CATEGORY.values())
                pick = pool[hashlib.md5((row["name"] or "").encode()).digest()[0] % len(pool)]
            icon_type, icon_value = "emoji", pick
        conn.execute("UPDATE pm_projects SET icon_type=?, icon_value=? WHERE id=?",
                     (icon_type, icon_value, project_id))
        _pm_log(conn, project_id, "project.icon", f"Icon set to {icon_value} via TOBI")
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "project_id": project_id, "icon_type": icon_type, "icon_value": icon_value}


def tool_complete_task(task_id: int = 0, note: str = "", **_: Any) -> dict:
    try:
        task_id = int(task_id)
    except Exception:
        return {"error": "task_id must be an integer"}
    conn = _conn()
    try:
        row = conn.execute("SELECT pm_project_id FROM tasks WHERE id=? AND deleted_at IS NULL", (task_id,)).fetchone()
        if not row:
            return {"error": f"no task with id {task_id}"}
        conn.execute(
            "UPDATE tasks SET status='done', status_v1='done', completed_at=CURRENT_TIMESTAMP, "
            "updated_at=CURRENT_TIMESTAMP, output=COALESCE(?, output) WHERE id=?",
            (note or None, task_id),
        )
        if row["pm_project_id"]:
            _pm_log(conn, row["pm_project_id"], "task.completed", f"Task #{task_id} completed via TOBI")
            _pm_recalc(conn, row["pm_project_id"])
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "task_id": task_id, "status": "done"}


def tool_update_project_progress(project_id: int = 0, progress_pct: int = 0, notes: str = "", **_: Any) -> dict:
    try:
        project_id = int(project_id)
        progress_pct = max(0, min(100, int(progress_pct)))
    except Exception:
        return {"error": "project_id and progress_pct must be integers"}
    conn = _conn()
    try:
        if not conn.execute("SELECT 1 FROM pm_projects WHERE id=?", (project_id,)).fetchone():
            return {"error": f"no project with id {project_id}"}
        conn.execute("UPDATE pm_projects SET progress_pct=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                     (float(progress_pct), project_id))
        _pm_log(conn, project_id, "progress.updated", f"Progress set to {progress_pct}% via TOBI" + (f" — {notes}" if notes else ""))
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "project_id": project_id, "progress_pct": progress_pct}


def tool_delete_task(task_id: int = 0, **_: Any) -> dict:
    try:
        task_id = int(task_id)
    except Exception:
        return {"error": "task_id must be an integer"}
    conn = _conn()
    try:
        row = conn.execute("SELECT pm_project_id FROM tasks WHERE id=?", (task_id,)).fetchone()
        if not row:
            return {"error": f"no task with id {task_id}"}
        try:
            conn.execute("UPDATE tasks SET deleted_at=CURRENT_TIMESTAMP WHERE id=?", (task_id,))
        except Exception:
            conn.execute("UPDATE tasks SET status='skipped' WHERE id=?", (task_id,))
        if row["pm_project_id"]:
            _pm_recalc(conn, row["pm_project_id"])
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "task_id": task_id, "deleted": True}


def tool_delete_project(project_id: int = 0, **_: Any) -> dict:
    """Delete a PM project (and remove its tasks from the board). High-risk → owner confirms first."""
    try:
        project_id = int(project_id)
    except Exception:
        return {"error": "project_id must be an integer"}
    conn = _conn()
    try:
        row = conn.execute("SELECT name FROM pm_projects WHERE id=?", (project_id,)).fetchone()
        if not row:
            return {"error": f"no project with id {project_id}"}
        name = row["name"]
        # soft-remove the project's tasks so none dangle on the board, then drop the project row
        try:
            conn.execute("UPDATE tasks SET deleted_at=CURRENT_TIMESTAMP WHERE pm_project_id=? AND deleted_at IS NULL", (project_id,))
        except Exception:
            pass
        conn.execute("DELETE FROM pm_projects WHERE id=?", (project_id,))
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "project_id": project_id, "name": name, "deleted": True}


def tool_assign_task(task_id: int = 0, agent: str = "", **_: Any) -> dict:
    try:
        task_id = int(task_id)
    except Exception:
        return {"error": "task_id must be an integer"}
    agent = (agent or "").strip().lower()
    if not agent:
        return {"error": "agent is required (tobi, research, coder, or ceo)"}
    key = agent if agent in _TASK_AGENTS else _AGENT_ALIASES.get(agent, "tobi")
    conn = _conn()
    try:
        if not conn.execute("SELECT 1 FROM tasks WHERE id=? AND deleted_at IS NULL", (task_id,)).fetchone():
            return {"error": f"no task with id {task_id}"}
        conn.execute("UPDATE tasks SET agent_key=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (key, task_id))
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "task_id": task_id, "assigned_to": key}


def tool_run_mission(objective: str = "", **_: Any) -> dict:
    obj = (objective or "").strip()
    if not obj:
        return {"error": "objective is required"}
    conn = _conn()
    try:
        cur = conn.execute(
            "INSERT INTO missions (title, goal, status, priority) VALUES (?, ?, 'planned', 'Normal')",
            (obj[:80], obj),
        )
        mid = cur.lastrowid
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "mission_id": mid, "status": "queued", "objective": obj[:120]}


def tool_rename_project(project_id: int = 0, new_name: str = "", **_: Any) -> dict:
    """Rename a PM project. Args: project_id (int), new_name (string)."""
    try:
        project_id = int(project_id)
    except Exception:
        return {"error": "project_id must be an integer"}
    new_name = (new_name or "").strip()
    if not new_name:
        return {"error": "new_name is required"}
    conn = _conn()
    try:
        row = conn.execute("SELECT name FROM pm_projects WHERE id=?", (project_id,)).fetchone()
        if not row:
            return {"error": f"no project with id {project_id}"}
        old_name = row["name"]
        conn.execute("UPDATE pm_projects SET name=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (new_name, project_id))
        _pm_log(conn, project_id, "project.renamed", f"Renamed from '{old_name}' to '{new_name}'")
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "project_id": project_id, "old_name": old_name, "new_name": new_name}


def tool_create_goal(project_id: int = 0, title: str = "", description: str = "",
                     due_date: str = "", priority: str = "medium", **_: Any) -> dict:
    """Create a goal inside a PM project. Args: project_id (int), title (string), description (optional), due_date (YYYY-MM-DD, optional), priority (low|medium|high)."""
    title = (title or "").strip()
    if not title:
        return {"error": "title is required"}
    try:
        project_id = int(project_id)
    except Exception:
        return {"error": "project_id must be an integer"}
    conn = _conn()
    try:
        if not conn.execute("SELECT 1 FROM pm_projects WHERE id=?", (project_id,)).fetchone():
            return {"error": f"no project with id {project_id}"}
        cur = conn.execute(
            "INSERT INTO pm_goals (project_id, title, description, due_date, priority, target_value, current_value, owner) VALUES (?,?,?,?,?,100,0,'tobi')",
            (project_id, title, description or None, due_date or None, priority or "medium"),
        )
        gid = cur.lastrowid
        _pm_log(conn, project_id, "goal.created", f"Goal '{title}' created via TOBI")
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "goal_id": gid, "project_id": project_id, "title": title}


def tool_edit_goal(goal_id: int = 0, title: str = "", description: str = "",
                   due_date: str = "", priority: str = "", current_value: float = -1, **_: Any) -> dict:
    """Edit a goal. Args: goal_id (int), and any of: title, description, due_date, priority (low|medium|high), current_value (0-100)."""
    try:
        goal_id = int(goal_id)
    except Exception:
        return {"error": "goal_id must be an integer"}
    conn = _conn()
    try:
        row = conn.execute("SELECT project_id FROM pm_goals WHERE id=?", (goal_id,)).fetchone()
        if not row:
            return {"error": f"no goal with id {goal_id}"}
        project_id = row["project_id"]
        fields, vals = [], []
        if title:
            fields.append("title=?"); vals.append(title.strip())
        if description:
            fields.append("description=?"); vals.append(description)
        if due_date:
            fields.append("due_date=?"); vals.append(due_date)
        if priority:
            fields.append("priority=?"); vals.append(priority)
        if current_value >= 0:
            fields.append("current_value=?"); vals.append(float(current_value))
        if fields:
            fields.append("updated_at=CURRENT_TIMESTAMP")
            vals.append(goal_id)
            conn.execute(f"UPDATE pm_goals SET {', '.join(fields)} WHERE id=?", vals)
            _pm_log(conn, project_id, "goal.edited", f"Goal #{goal_id} updated via TOBI")
            conn.commit()
    finally:
        conn.close()
    return {"ok": True, "goal_id": goal_id}


def tool_delete_goal(goal_id: int = 0, **_: Any) -> dict:
    """Delete a goal (and its sub-goals). Args: goal_id (int)."""
    try:
        goal_id = int(goal_id)
    except Exception:
        return {"error": "goal_id must be an integer"}
    conn = _conn()
    try:
        row = conn.execute("SELECT project_id, title FROM pm_goals WHERE id=?", (goal_id,)).fetchone()
        if not row:
            return {"error": f"no goal with id {goal_id}"}
        project_id = row["project_id"]
        title = row["title"]
        conn.execute("DELETE FROM pm_goals WHERE parent_goal_id=?", (goal_id,))
        conn.execute("DELETE FROM pm_goals WHERE id=?", (goal_id,))
        _pm_log(conn, project_id, "goal.deleted", f"Goal '{title}' deleted via TOBI")
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "goal_id": goal_id, "deleted": True}


def tool_set_category_lock(category_id: str = "", is_locked: bool = False, **_: Any) -> dict:
    """Lock or unlock a Brain memory category. Args: category_id (string slug e.g. 'psychology'), is_locked (bool)."""
    category_id = (category_id or "").strip()
    if not category_id:
        return {"error": "category_id is required"}
    conn = _conn()
    try:
        if not conn.execute("SELECT 1 FROM brain_categories WHERE id=?", (category_id,)).fetchone():
            return {"error": f"no category '{category_id}'"}
        conn.execute("UPDATE brain_categories SET is_locked=? WHERE id=?", (1 if is_locked else 0, category_id))
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "category_id": category_id, "is_locked": is_locked}


_TASK_STATUS_V1 = {
    "planned": "planned", "todo": "planned", "pending": "planned", "backlog": "planned",
    "in_progress": "in_progress", "doing": "in_progress", "active": "in_progress", "started": "in_progress",
    "paused": "paused", "blocked": "blocked", "needs_owner_input": "needs_owner_input",
    "done": "done", "completed": "done", "complete": "done",
    "cancelled": "cancelled", "canceled": "cancelled",
}


def tool_update_task(task_id: int = 0, title: str = "", description: str = "",
                     status: str = "", priority: str = "", agent: str = "", **_: Any) -> dict:
    """Edit a task's fields (#17). Args: task_id (int), and any of: title, description,
    status (planned|in_progress|paused|blocked|done|cancelled), priority (P0-P3 or
    low|medium|high|urgent), agent (tobi|research|coder|ceo)."""
    try:
        task_id = int(task_id)
    except Exception:
        return {"error": "task_id must be an integer"}
    sets: list[str] = []
    vals: list[Any] = []
    changed: dict[str, Any] = {}
    if (title or "").strip():
        sets += ["title=?", "objective=?"]; vals += [title.strip(), title.strip()]; changed["title"] = title.strip()
    if (description or "").strip():
        sets.append("description=?"); vals.append(description.strip()); changed["description"] = True
    if (status or "").strip():
        sv = _TASK_STATUS_V1.get(status.strip().lower())
        if not sv:
            return {"error": f"unknown status '{status}' — use planned|in_progress|paused|blocked|done|cancelled"}
        sets += ["status_v1=?", "status=?"]; vals += [sv, _TASK_STATUS_LEGACY[sv]]
        sets.append("completed_at=" + ("CURRENT_TIMESTAMP" if sv == "done" else "NULL"))
        changed["status"] = sv
    if (priority or "").strip():
        pl = _TASK_PRIORITY.get(priority.strip().lower())
        if not pl:
            return {"error": f"unknown priority '{priority}' — use P0-P3 or low|medium|high|urgent"}
        sets.append("priority_label=?"); vals.append(pl); changed["priority"] = pl
    if (agent or "").strip():
        key = agent.strip().lower()
        key = key if key in _TASK_AGENTS else _AGENT_ALIASES.get(key, "tobi")
        sets.append("agent_key=?"); vals.append(key); changed["agent"] = key
    if not sets:
        return {"error": "nothing to update — pass at least one of title/description/status/priority/agent"}
    conn = _conn()
    try:
        row = conn.execute("SELECT pm_project_id FROM tasks WHERE id=? AND deleted_at IS NULL", (task_id,)).fetchone()
        if not row:
            return {"error": f"no task with id {task_id}"}
        sets.append("updated_at=CURRENT_TIMESTAMP")
        conn.execute(f"UPDATE tasks SET {', '.join(sets)} WHERE id=?", (*vals, task_id))
        if row["pm_project_id"]:
            _pm_recalc(conn, row["pm_project_id"])
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "task_id": task_id, "updated": changed}


def tool_save_note(text: str = "", project_id: int = 0, category: str = "", **_: Any) -> dict:
    """Save a note (#17 workflow). To a project's Resources drive if project_id is given,
    otherwise to the Brain as a memory. Args: text (string), project_id (optional int),
    category (optional Brain category)."""
    text = (text or "").strip()
    if not text:
        return {"error": "text is required"}
    try:
        pid = int(project_id) if project_id else 0
    except Exception:
        pid = 0
    if pid:
        res = tool_create_resource(project_id=pid, text=text, name=(text[:40] or "Note"))
        if isinstance(res, dict) and res.get("error"):
            return res
        return {"ok": True, "saved_to": "project_resource", "project_id": pid, "detail": res}
    res = tool_remember(fact=text, category=(category or None))
    if isinstance(res, dict) and res.get("error"):
        return res
    return {"ok": True, "saved_to": "brain", "detail": res}


def _resolve_or_create_project(project_id: Any = 0, name: str = "", default_name: str = "Inbox") -> int:
    """Find a project by id or name, else create one — for capturing conversation tasks."""
    try:
        if project_id:
            pid = int(project_id)
            conn = _conn()
            try:
                if conn.execute("SELECT 1 FROM pm_projects WHERE id=?", (pid,)).fetchone():
                    return pid
            finally:
                conn.close()
        target = (name or default_name).strip() or default_name
        conn = _conn()
        try:
            row = conn.execute("SELECT id FROM pm_projects WHERE lower(name)=lower(?) LIMIT 1", (target,)).fetchone()
        finally:
            conn.close()
        if row:
            return int(row[0])
        r = tool_create_project(name=target, description="Tasks TOBI captured from conversations.", category="General")
        return int(r.get("project_id")) if isinstance(r, dict) and r.get("ok") else 0
    except Exception:
        return 0


def tool_create_task_from_conversation(tasks: Optional[list] = None, project_id: int = 0,
                                       project: str = "", **_: Any) -> dict:
    """Turn the current conversation into MC task(s) (#17 workflow). Distill it YOURSELF
    into short task titles and pass them. Args: tasks (list of strings, or list of
    {title, description}); project_id (optional) or project (optional name) — omit both to
    use/create an 'Inbox' project."""
    items = tasks or []
    if isinstance(items, str):
        items = [items]
    norm: list[tuple[str, str]] = []
    for t in items:
        if isinstance(t, dict) and (t.get("title") or "").strip():
            norm.append((str(t["title"]).strip(), str(t.get("description") or "").strip()))
        elif isinstance(t, str) and t.strip():
            norm.append((t.strip(), ""))
    if not norm:
        return {"error": "pass at least one task title distilled from the conversation"}
    pid = _resolve_or_create_project(project_id, project, "Inbox")
    if not pid:
        return {"error": "couldn't resolve or create a project for the tasks"}
    created = []
    for title, desc in norm[:12]:
        r = tool_create_task(project_id=pid, title=title, description=desc)
        if isinstance(r, dict) and r.get("ok"):
            created.append({"task_id": r.get("task_id"), "title": title})
    if not created:
        return {"error": "no tasks were created"}
    return {"ok": True, "project_id": pid, "count": len(created), "created": created}


def tool_office_create_artifact(title: str = "", kind: str = "report", content: str = "",
                                source_type: str = "manual", source_id: Any = None,
                                office_payload_id: int = 0, content_chars: int = 0, **_: Any) -> dict:
    from core import office_artifacts
    staged = office_artifacts.resolve_action_payload("office_create_artifact", {
        "title": title, "kind": kind, "content": content, "source_type": source_type,
        "source_id": source_id, "office_payload_id": office_payload_id,
    })
    return office_artifacts.create_artifact(
        staged.get("title", title), staged.get("kind", kind), staged.get("content", content),
        source_type=staged.get("source_type", source_type),
        source_id=staged.get("source_id", source_id), created_by="tobi")


def tool_office_update_artifact(artifact_id: int = 0, title: str = "", kind: str = "",
                                content: str = "", office_payload_id: int = 0,
                                content_chars: int = 0, **_: Any) -> dict:
    from core import office_artifacts
    staged = office_artifacts.resolve_action_payload("office_update_artifact", {
        "artifact_id": artifact_id, "title": title, "kind": kind, "content": content,
        "office_payload_id": office_payload_id,
    })
    return office_artifacts.update_artifact(
        staged.get("artifact_id", artifact_id), title=staged.get("title", title),
        kind=staged.get("kind", kind), content=staged.get("content", content))


def tool_office_delete_artifact(artifact_id: int = 0, **_: Any) -> dict:
    from core import office_artifacts
    return office_artifacts.delete_artifact(artifact_id)


def tool_office_create_mission(title: str = "", goal: str = "", priority: str = "Normal", **_: Any) -> dict:
    from core import office_artifacts
    return office_artifacts.create_mission(title, goal, priority)


def tool_office_run_mission(mission_id: int = 0, mock: bool = False, **_: Any) -> dict:
    from core import office_artifacts
    return office_artifacts.start_mission(mission_id, mock)


def tool_office_control_mission(mission_id: int = 0, action: str = "", **_: Any) -> dict:
    from core import office_artifacts
    return office_artifacts.control_mission(mission_id, action)


def tool_office_convert_to_tasks(tasks: Optional[list] = None, project_id: int = 0,
                                 project: str = "", source_type: str = "artifact",
                                 source_id: Any = None, **_: Any) -> dict:
    result = tool_create_task_from_conversation(tasks=tasks, project_id=project_id, project=project)
    if isinstance(result, dict) and result.get("ok"):
        try:
            from core import office_artifacts
            office_artifacts.record_activity(
                "tasks.created", "tobi", f"Created {result.get('count', 0)} task(s) from Office",
                payload={"count": result.get("count"), "project_id": result.get("project_id")},
                source_type=source_type, source_id=source_id)
        except Exception:
            pass
    return result

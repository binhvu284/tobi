"""Tasks API — /api/tasks/* and /done/* (Mission Control task ledger).

Extracted from api/dashboard.py (refactor Slice — pre-#21 decomposition). Byte-
identical: task constants + 9 request models + 3 validators + 12 routes, only
@app.* -> @router.*. Shared task/activity helpers come from api.deps. The pm
router imports TASK_STATUS_V1/ALLOWED_*/TaskPatchRequest/api_task_patch from here
(one-directional — tasks never imports pm). See docs/REFACTORING_PLAN.md.
"""
from __future__ import annotations

import json  # noqa: F401 - used by some handlers
from datetime import datetime, timezone  # noqa: F401 - used by some handlers
from typing import Any  # noqa: F401 - used in models/type hints

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from api.deps import (_append_activity, _fetch_checklist, _fetch_task_row, _get_conn,
                      _json_loads, _legacy_status_from_v1, _serialize_task)

router = APIRouter(tags=["tasks"])


TASK_STATUS_V1 = {
    "planned",
    "in_progress",
    "paused",
    "blocked",
    "needs_owner_input",
    "done",
    "cancelled",
}

HIGH_RISK_TRANSITIONS = {
    "done",
    "cancelled",
}

ALLOWED_AGENTS = {"tobi", "research", "coder", "ceo", "owner"}
ALLOWED_PRIORITIES = {"P0", "P1", "P2", "P3"}


class OwnerInputItem(BaseModel):
    item_key: str
    label: str
    input_type: str = Field(default="text")
    required: bool = True
    placeholder: str | None = None
    value_text: str | None = None
    file_path: str | None = None
    status: str | None = None


class TaskCreateRequest(BaseModel):
    title: str
    objective: str | None = None
    success_criteria: str | None = None
    description: str | None = None
    status: str = "planned"
    priority: str = "P2"
    owner: str = "owner"
    agent: str = "tobi"
    project_id: int | None = None
    project_name: str | None = None
    due_at: str | None = None
    checklist: list[OwnerInputItem] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)


class TaskPatchRequest(BaseModel):
    status: str | None = None
    priority: str | None = None
    agent: str | None = None
    due_at: str | None = None
    before_task_id: int | None = None
    owner: str | None = None
    title: str | None = None
    objective: str | None = None
    success_criteria: str | None = None
    description: str | None = None       # v2 task detail (plain text)
    start_at: str | None = None          # v2 optional start date
    reminder_at: str | None = None       # v2 optional reminder
    time_estimate: str | None = None     # v2 effort estimate
    require_confirmation: bool = False
    confirmed: bool = False


class TaskReorderRequest(BaseModel):
    task_id: int
    target_status: str | None = None
    before_task_id: int | None = None
    confirmed: bool = False


class TaskAuditEntry(BaseModel):
    id: int
    task_id: int
    activity_type: str
    author: str
    message: str
    payload: dict[str, Any]
    created_at: str


class TaskNoteRequest(BaseModel):
    note: str
    author: str = "owner"


class OwnerInputSubmissionRequest(BaseModel):
    items: list[OwnerInputItem] = Field(default_factory=list)
    author: str = "owner"


class TaskInputEvaluationRequest(BaseModel):
    author: str = "tobi"


class TaskCommandRequest(BaseModel):
    command: str
    author: str = "owner"


@router.post("/done/{task_id}")
async def mark_done(task_id: int):
    conn = _get_conn()
    try:
        row = _fetch_task_row(conn, task_id)
        if not row:
            raise HTTPException(status_code=404, detail="Task not found")
        conn.execute(
            """
            UPDATE tasks
            SET status='done', status_v1='done', completed_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP
            WHERE id=?
            """,
            (task_id,),
        )
        _append_activity(conn, task_id, "status_change", "owner", "Marked done via Mission Control", {
            "to": "done",
            "compat_endpoint": True,
        })
        conn.commit()
        return {"status": "done", "task_id": task_id}
    finally:
        conn.close()


def _validate_status(value: str) -> str:
    if value not in TASK_STATUS_V1:
        raise HTTPException(status_code=400, detail=f"Invalid status '{value}'")
    return value


def _validate_priority(value: str) -> str:
    if value not in ALLOWED_PRIORITIES:
        raise HTTPException(status_code=400, detail=f"Invalid priority '{value}'")
    return value


def _validate_agent(value: str) -> str:
    if value not in ALLOWED_AGENTS:
        raise HTTPException(status_code=400, detail=f"Invalid agent '{value}'")
    return value


@router.get("/api/tasks")
async def api_tasks(
    status: list[str] = Query(default=[]),
    priority: list[str] = Query(default=[]),
    owner: list[str] = Query(default=[]),
    agent: list[str] = Query(default=[]),
    project_id: int | None = None,
    overdue: bool | None = None,
    q: str | None = None,
):
    conn = _get_conn()
    try:
        query = """
            SELECT t.*, COALESCE(p.name, pmp.name) AS project_name
            FROM tasks t
            LEFT JOIN projects p ON p.id = t.project_id
            LEFT JOIN pm_projects pmp ON pmp.id = t.pm_project_id
            WHERE t.deleted_at IS NULL
        """
        params: list[Any] = []

        if status:
            placeholders = ",".join(["?"] * len(status))
            query += f" AND t.status_v1 IN ({placeholders})"
            params.extend(status)
        if priority:
            placeholders = ",".join(["?"] * len(priority))
            query += f" AND t.priority_label IN ({placeholders})"
            params.extend(priority)
        if owner:
            placeholders = ",".join(["?"] * len(owner))
            query += f" AND t.owner_label IN ({placeholders})"
            params.extend(owner)
        if agent:
            placeholders = ",".join(["?"] * len(agent))
            query += f" AND t.agent_key IN ({placeholders})"
            params.extend(agent)
        if project_id is not None:
            query += " AND t.project_id=?"
            params.append(project_id)
        if q:
            query += " AND (t.title LIKE ? OR t.objective LIKE ? OR t.description LIKE ?)"
            like_q = f"%{q.strip()}%"
            params.extend([like_q, like_q, like_q])

        query += """
            ORDER BY CASE t.status_v1
                WHEN 'planned' THEN 1
                WHEN 'in_progress' THEN 2
                WHEN 'paused' THEN 3
                WHEN 'blocked' THEN 4
                WHEN 'needs_owner_input' THEN 5
                WHEN 'done' THEN 6
                WHEN 'cancelled' THEN 7
                ELSE 99
            END,
            t.sort_order ASC,
            t.created_at DESC
        """
        rows = conn.execute(query, params).fetchall()
        tasks = [_serialize_task(conn, row, include_activity=False) for row in rows]

        if overdue is not None:
            tasks = [t for t in tasks if t["is_overdue"] == overdue]

        return {"items": tasks, "total": len(tasks), "timestamp": datetime.now().isoformat()}
    finally:
        conn.close()


@router.get("/api/tasks/metrics")
async def api_task_metrics():
    conn = _get_conn()
    try:
        rows = conn.execute(
            """
            SELECT id, status_v1, priority_label, due_at, created_at, completed_at
            FROM tasks
            WHERE deleted_at IS NULL
            """
        ).fetchall()
        now = datetime.now(timezone.utc)
        open_count = 0
        overdue_count = 0
        needs_owner_input_count = 0
        blocked_count = 0
        p0_p1_count = 0
        cycle_hours: list[float] = []

        for row in rows:
            status = row["status_v1"] or "planned"
            if status not in {"done", "cancelled"}:
                open_count += 1
            if status == "needs_owner_input":
                needs_owner_input_count += 1
            if status == "blocked":
                blocked_count += 1
            if row["priority_label"] in {"P0", "P1"}:
                p0_p1_count += 1

            due_at = row["due_at"]
            if due_at and status not in {"done", "cancelled"}:
                try:
                    if datetime.fromisoformat(due_at.replace("Z", "+00:00")) < now:
                        overdue_count += 1
                except Exception:
                    pass

            if row["completed_at"] and row["created_at"]:
                try:
                    created = datetime.fromisoformat(str(row["created_at"]).replace("Z", "+00:00"))
                    completed = datetime.fromisoformat(str(row["completed_at"]).replace("Z", "+00:00"))
                    cycle_hours.append((completed - created).total_seconds() / 3600)
                except Exception:
                    pass

        cycle_avg = round(sum(cycle_hours) / len(cycle_hours), 2) if cycle_hours else None
        return {
            "open_tasks": open_count,
            "overdue": overdue_count,
            "needs_owner_input": needs_owner_input_count,
            "blocked": blocked_count,
            "p0_p1": p0_p1_count,
            "cycle_time_hours": cycle_avg,
            "timestamp": datetime.now().isoformat(),
        }
    finally:
        conn.close()


@router.get("/api/tasks/{task_id}")
async def api_task_detail(task_id: int):
    conn = _get_conn()
    try:
        row = _fetch_task_row(conn, task_id)
        if not row:
            raise HTTPException(status_code=404, detail="Task not found")
        return _serialize_task(conn, row, include_activity=True)
    finally:
        conn.close()


@router.post("/api/tasks")
async def api_task_create(payload: TaskCreateRequest):
    status = _validate_status(payload.status)
    priority = _validate_priority(payload.priority)
    agent = _validate_agent(payload.agent)
    conn = _get_conn()
    try:
        next_sort = conn.execute("SELECT COALESCE(MAX(sort_order), 0) + 1 FROM tasks").fetchone()[0]
        cur = conn.execute(
            """
            INSERT INTO tasks (
                project_id, title, description, task_type, status, priority,
                status_v1, priority_label, owner_label, agent_key,
                objective, success_criteria, due_at, risk_flags_json,
                created_at, updated_at, sort_order
            ) VALUES (?, ?, ?, 'agent', ?, 5, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, ?)
            """,
            (
                payload.project_id,
                payload.title.strip(),
                payload.description,
                _legacy_status_from_v1(status),
                status,
                priority,
                payload.owner.strip() or "owner",
                agent,
                payload.objective or payload.description or payload.title,
                payload.success_criteria,
                payload.due_at,
                json.dumps(payload.risk_flags, ensure_ascii=False),
                next_sort,
            ),
        )
        task_id = cur.lastrowid

        for item in payload.checklist:
            conn.execute(
                """
                INSERT INTO task_owner_inputs (task_id, item_key, label, input_type, required, placeholder, value_text, file_path, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    item.item_key,
                    item.label,
                    item.input_type,
                    1 if item.required else 0,
                    item.placeholder,
                    item.value_text,
                    item.file_path,
                    item.status or ("submitted" if item.value_text or item.file_path else "pending"),
                ),
            )

        _append_activity(conn, task_id, "created", payload.owner, "Task created", {
            "status": status,
            "priority": priority,
            "agent": agent,
        })

        conn.commit()
        row = _fetch_task_row(conn, task_id)
        return _serialize_task(conn, row, include_activity=True)
    finally:
        conn.close()


@router.patch("/api/tasks/{task_id}")
async def api_task_patch(task_id: int, payload: TaskPatchRequest):
    conn = _get_conn()
    try:
        row = _fetch_task_row(conn, task_id)
        if not row:
            raise HTTPException(status_code=404, detail="Task not found")

        updates: list[str] = []
        values: list[Any] = []
        changes: dict[str, Any] = {}

        high_risk_reasons: list[str] = []

        target_status = row["status_v1"]

        if payload.status is not None:
            status = _validate_status(payload.status)
            if status in HIGH_RISK_TRANSITIONS and row["status_v1"] != status and not payload.confirmed:
                raise HTTPException(status_code=409, detail={
                    "code": "confirmation_required",
                    "message": f"Transition to {status} requires confirmation",
                })
            if status in HIGH_RISK_TRANSITIONS and row["status_v1"] != status:
                high_risk_reasons.append(f"status:{status}")
            updates.extend(["status_v1=?", "status=?"])
            values.extend([status, _legacy_status_from_v1(status)])
            if status == "in_progress" and row["status_v1"] != "in_progress":
                updates.append("started_at=COALESCE(started_at, CURRENT_TIMESTAMP)")
            if status == "done" and row["status_v1"] != "done":
                updates.append("completed_at=CURRENT_TIMESTAMP")
            if status in {"planned", "in_progress", "paused", "blocked", "needs_owner_input"} and row["status_v1"] != status:
                updates.append("completed_at=NULL")
            changes["status"] = status
            target_status = status

        if payload.before_task_id is not None:
            before_row = _fetch_task_row(conn, payload.before_task_id)
            if not before_row:
                raise HTTPException(status_code=404, detail="Target position task not found")
            if before_row["id"] == row["id"]:
                raise HTTPException(status_code=400, detail="Cannot reorder task before itself")
            before_sort = float(before_row["sort_order"] or 0)
            prev = conn.execute(
                """
                SELECT sort_order FROM tasks
                WHERE status_v1=? AND deleted_at IS NULL AND id NOT IN (?, ?)
                  AND sort_order < ?
                ORDER BY sort_order DESC
                LIMIT 1
                """,
                (target_status, row["id"], before_row["id"], before_sort),
            ).fetchone()
            prev_sort = float(prev["sort_order"]) if prev else before_sort - 2.0
            new_sort = (prev_sort + before_sort) / 2.0
            updates.append("sort_order=?")
            values.append(new_sort)
            changes["sort_order"] = new_sort
            changes["before_task_id"] = payload.before_task_id
        elif payload.status is not None:
            max_row = conn.execute(
                "SELECT COALESCE(MAX(sort_order), 0) AS max_sort FROM tasks WHERE status_v1=? AND deleted_at IS NULL AND id!=?",
                (target_status, task_id),
            ).fetchone()
            new_sort = float(max_row["max_sort"] or 0) + 1.0
            updates.append("sort_order=?")
            values.append(new_sort)
            changes["sort_order"] = new_sort

        if payload.priority is not None:
            priority = _validate_priority(payload.priority)
            if priority == "P0" and row["priority_label"] != "P0" and not payload.confirmed:
                raise HTTPException(status_code=409, detail={
                    "code": "confirmation_required",
                    "message": "Escalating priority to P0 requires confirmation",
                })
            if priority == "P0" and row["priority_label"] != "P0":
                high_risk_reasons.append("priority:P0")
            updates.append("priority_label=?")
            values.append(priority)
            changes["priority"] = priority

        if payload.agent is not None:
            agent = _validate_agent(payload.agent)
            if row["agent_key"] != agent and not payload.confirmed:
                raise HTTPException(status_code=409, detail={
                    "code": "confirmation_required",
                    "message": "Reassigning task agent requires confirmation",
                })
            if row["agent_key"] != agent:
                high_risk_reasons.append("agent:reassign")
            updates.append("agent_key=?")
            values.append(agent)
            changes["agent"] = agent

        if payload.due_at is not None:
            updates.append("due_at=?")
            values.append(payload.due_at)
            changes["due_at"] = payload.due_at

        if payload.owner is not None:
            updates.append("owner_label=?")
            values.append(payload.owner)
            changes["owner"] = payload.owner

        if payload.title is not None:
            updates.append("title=?")
            values.append(payload.title)
            changes["title"] = payload.title

        if payload.objective is not None:
            updates.append("objective=?")
            values.append(payload.objective)
            changes["objective"] = payload.objective

        if payload.success_criteria is not None:
            updates.append("success_criteria=?")
            values.append(payload.success_criteria)
            changes["success_criteria"] = payload.success_criteria

        if payload.description is not None:
            updates.append("description=?")
            values.append(payload.description)
            changes["description"] = payload.description

        if payload.start_at is not None:
            updates.append("start_at=?")
            values.append(payload.start_at or None)
            changes["start_at"] = payload.start_at

        if payload.reminder_at is not None:
            updates.append("reminder_at=?")
            values.append(payload.reminder_at or None)
            changes["reminder_at"] = payload.reminder_at

        if payload.time_estimate is not None:
            updates.append("time_estimate=?")
            values.append(payload.time_estimate or None)
            changes["time_estimate"] = payload.time_estimate

        if not updates:
            raise HTTPException(status_code=400, detail="No updates provided")

        updates.append("updated_at=CURRENT_TIMESTAMP")
        sql = f"UPDATE tasks SET {', '.join(updates)} WHERE id=?"
        values.append(task_id)
        conn.execute(sql, values)
        _append_activity(conn, task_id, "updated", "owner", "Task updated", changes)
        if payload.confirmed and high_risk_reasons:
            _append_activity(
                conn,
                task_id,
                "high_risk_confirmation",
                "owner",
                "High-risk transition confirmed",
                {
                    "reasons": high_risk_reasons,
                    "changes": changes,
                },
            )
        conn.commit()

        updated = _fetch_task_row(conn, task_id)
        return _serialize_task(conn, updated, include_activity=True)
    finally:
        conn.close()


@router.post("/api/tasks/{task_id}/notes")
async def api_task_add_note(task_id: int, payload: TaskNoteRequest):
    conn = _get_conn()
    try:
        row = _fetch_task_row(conn, task_id)
        if not row:
            raise HTTPException(status_code=404, detail="Task not found")
        _append_activity(conn, task_id, "note", payload.author, payload.note)
        conn.execute(
            "UPDATE tasks SET notes=COALESCE(notes,'') || ? || ?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            ("\n" if row["notes"] else "", payload.note, task_id),
        )
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


@router.post("/api/tasks/{task_id}/owner-input")
async def api_task_owner_input(task_id: int, payload: OwnerInputSubmissionRequest):
    conn = _get_conn()
    try:
        row = _fetch_task_row(conn, task_id)
        if not row:
            raise HTTPException(status_code=404, detail="Task not found")

        for item in payload.items:
            conn.execute(
                """
                INSERT INTO task_owner_inputs (task_id, item_key, label, input_type, required, placeholder, value_text, file_path, status, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(task_id, item_key) DO UPDATE SET
                    label=excluded.label,
                    input_type=excluded.input_type,
                    required=excluded.required,
                    placeholder=excluded.placeholder,
                    value_text=excluded.value_text,
                    file_path=excluded.file_path,
                    status=excluded.status,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (
                    task_id,
                    item.item_key,
                    item.label,
                    item.input_type,
                    1 if item.required else 0,
                    item.placeholder,
                    item.value_text,
                    item.file_path,
                    item.status or ("submitted" if item.value_text or item.file_path else "pending"),
                ),
            )

        conn.execute(
            """
            UPDATE tasks
            SET status_v1='needs_owner_input', status='pending', updated_at=CURRENT_TIMESTAMP
            WHERE id=?
            """,
            (task_id,),
        )
        _append_activity(conn, task_id, "owner_input", payload.author, "Owner input submitted", {
            "items": len(payload.items),
        })
        conn.commit()
        return {"ok": True, "items": len(payload.items)}
    finally:
        conn.close()


@router.post("/api/tasks/{task_id}/evaluate-input")
async def api_task_evaluate_input(task_id: int, payload: TaskInputEvaluationRequest):
    conn = _get_conn()
    try:
        row = _fetch_task_row(conn, task_id)
        if not row:
            raise HTTPException(status_code=404, detail="Task not found")
        checklist = _fetch_checklist(conn, task_id)
        missing = []
        for item in checklist:
            if item["required"] and not item.get("value_text") and not item.get("file_path"):
                missing.append(item["item_key"])

        passed = len(missing) == 0
        if passed:
            conn.execute(
                "UPDATE tasks SET status_v1='in_progress', status='in_progress', started_at=COALESCE(started_at, CURRENT_TIMESTAMP), updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (task_id,),
            )
            message = "Owner input accepted. Task resumed."
        else:
            conn.execute(
                "UPDATE tasks SET status_v1='needs_owner_input', status='pending', updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (task_id,),
            )
            message = "Input insufficient. Missing required checklist items."

        _append_activity(conn, task_id, "input_evaluation", payload.author, message, {
            "passed": passed,
            "missing": missing,
        })
        conn.commit()
        return {"passed": passed, "missing": missing, "message": message}
    finally:
        conn.close()


@router.post("/api/tasks/{task_id}/command")
async def api_task_command(task_id: int, payload: TaskCommandRequest):
    conn = _get_conn()
    try:
        row = _fetch_task_row(conn, task_id)
        if not row:
            raise HTTPException(status_code=404, detail="Task not found")

        _append_activity(conn, task_id, "command", payload.author, payload.command, {
            "status": "accepted",
            "agent": row["agent_key"] or "tobi",
        })
        conn.execute(
            "UPDATE tasks SET status_v1='in_progress', status='in_progress', started_at=COALESCE(started_at, CURRENT_TIMESTAMP), updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (task_id,),
        )
        conn.commit()
        return {
            "ok": True,
            "task_id": task_id,
            "ack": f"Command queued for {row['agent_key'] or 'tobi'}",
        }
    finally:
        conn.close()


@router.delete("/api/tasks/{task_id}")
async def api_task_delete(task_id: int):
    conn = _get_conn()
    try:
        row = _fetch_task_row(conn, task_id)
        if not row:
            raise HTTPException(status_code=404, detail="Task not found")
        conn.execute(
            """
            UPDATE tasks
            SET status_v1='cancelled', status='skipped', deleted_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP
            WHERE id=?
            """,
            (task_id,),
        )
        _append_activity(conn, task_id, "deleted", "owner", "Task deleted from active board")
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


@router.get("/api/tasks/audit/high-risk")
async def api_task_high_risk_audit(limit: int = Query(default=50, ge=1, le=200)):
    conn = _get_conn()
    try:
        rows = conn.execute(
            """
            SELECT a.id, a.task_id, a.activity_type, a.author, a.message, a.payload, a.created_at,
                   t.title AS task_title
            FROM task_activity a
            JOIN tasks t ON t.id = a.task_id
            WHERE a.activity_type='high_risk_confirmation'
               OR (a.activity_type='updated' AND (
                    instr(a.payload, '"status": "done"') > 0
                 OR instr(a.payload, '"status": "cancelled"') > 0
                 OR instr(a.payload, '"priority": "P0"') > 0
                 OR instr(a.payload, '"agent"') > 0
               ))
            ORDER BY a.created_at DESC, a.id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

        items = []
        for row in rows:
            items.append({
                "id": row["id"],
                "task_id": row["task_id"],
                "task_title": row["task_title"],
                "activity_type": row["activity_type"],
                "author": row["author"],
                "message": row["message"],
                "payload": _json_loads(row["payload"], {}),
                "created_at": row["created_at"],
            })
        return {"items": items, "count": len(items), "timestamp": datetime.now().isoformat()}
    finally:
        conn.close()

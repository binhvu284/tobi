"""News V2 operational telemetry (#23, N12) — plan §9: "Repeated source failures
create one deduplicated Inbox action."

After a partial/failed refresh, a source whose checkpoint failed in each of the
last ``FAIL_STREAK`` terminal jobs for its tab raises ONE owner-visible task in
the Inbox project. Deduplicated on the open task title — a source that keeps
failing never floods the Inbox with duplicates; once the owner closes the task a
continued streak may raise it again. Errors quoted in the task body come from
adapter checkpoints, which are already secret-redacted at the source (N02).

Best-effort by design: telemetry must never break or delay a refresh — every
entry point swallows its own failures.
"""
from __future__ import annotations

import json
import sqlite3

FAIL_STREAK = 3
_TERMINAL = ("completed", "partial", "failed")
_OPEN_STATUSES_EXCLUDED = ("done", "skipped", "canceled", "cancelled", "archived")


def failing_sources(conn: sqlite3.Connection, tab: str) -> list[str]:
    """Sources whose checkpoint state was ``failed`` in EVERY one of the last
    ``FAIL_STREAK`` terminal jobs for ``tab``. Fewer runs than the streak → no
    alert yet (a brand-new source gets the benefit of the doubt)."""
    rows = conn.execute(
        "SELECT checkpoints_json FROM news_refresh_jobs"
        " WHERE tab=? AND state IN (?,?,?) ORDER BY id DESC LIMIT ?",
        (tab, *_TERMINAL, FAIL_STREAK)).fetchall()
    if len(rows) < FAIL_STREAK:
        return []
    streak: set[str] | None = None
    for row in rows:
        checkpoints = json.loads(row[0] or "{}")
        failed = {source for source, cp in checkpoints.items() if cp.get("state") == "failed"}
        streak = failed if streak is None else streak & failed
    return sorted(streak or ())


def _latest_error(conn: sqlite3.Connection, tab: str, source: str) -> str:
    row = conn.execute(
        "SELECT checkpoints_json FROM news_refresh_jobs WHERE tab=? AND state IN (?,?,?)"
        " ORDER BY id DESC LIMIT 1", (tab, *_TERMINAL)).fetchone()
    if not row:
        return "unknown error"
    cp = json.loads(row[0] or "{}").get(source, {})
    return str(cp.get("error") or "unknown error")


def _title(source: str, tab: str) -> str:
    return f"[News] Source '{source}' failed {FAIL_STREAK} refreshes in a row ({tab})"


def _create_inbox_task(conn: sqlite3.Connection, title: str, description: str) -> bool:
    try:
        # Preferred: the Conductor capture path — resolves/creates the Inbox
        # project and keeps PM logs/rollups consistent. Imported lazily so the
        # news module never depends on the chat runtime at import time.
        from core.conductor import tool_create_task_from_conversation
        result = tool_create_task_from_conversation(tasks=[{"title": title, "description": description}])
        if isinstance(result, dict) and not result.get("error"):
            return True
    except Exception:
        pass
    try:
        # Fallback: minimal insert on the base tasks schema (still owner-visible).
        conn.execute("INSERT INTO tasks (title, description, status, task_type)"
                     " VALUES (?,?,?,?)", (title, description, "pending", "human"))
        conn.commit()
        return True
    except sqlite3.Error:
        return False


def alert_failing_sources(conn: sqlite3.Connection, tab: str) -> dict:
    """Raise one deduplicated Inbox action per persistently failing source.
    Returns {"alerted": [...], "deduplicated": [...]} for tests/observability."""
    alerted: list[str] = []
    deduplicated: list[str] = []
    for source in failing_sources(conn, tab):
        title = _title(source, tab)
        try:
            placeholders = ",".join("?" for _ in _OPEN_STATUSES_EXCLUDED)
            open_row = conn.execute(
                f"SELECT 1 FROM tasks WHERE title=? AND status NOT IN ({placeholders}) LIMIT 1",
                (title, *_OPEN_STATUSES_EXCLUDED)).fetchone()
        except sqlite3.Error:
            open_row = None
        if open_row:
            deduplicated.append(source)
            continue
        description = (
            f"The '{source}' source failed its last {FAIL_STREAK} {tab} refreshes."
            f" Latest error: {_latest_error(conn, tab, source)}."
            " Check credentials/rate limits, then retry the failed sources from the News"
            " refresh controls. This alert deduplicates — one open task per failing source.")
        if _create_inbox_task(conn, title, description):
            alerted.append(source)
    return {"alerted": alerted, "deduplicated": deduplicated}

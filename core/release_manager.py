"""Immutable semantic release records for controlled development."""
from __future__ import annotations

import re
from typing import Any

from core.development_store import DevelopmentStore, utc_now


DEFAULT_DEVELOPER_VERSION = "3.0"


def current_developer_version(conn: Any, fallback: str = DEFAULT_DEVELOPER_VERSION) -> str:
    """Return the active Developer target, then the newest viable release."""
    queries = (
        """SELECT t.target_version AS version
           FROM coding_sessions s
           JOIN development_tasks t ON t.id=s.task_id
           WHERE s.state NOT IN ('completed','canceled','failed','rolled_back')
             AND t.target_version IS NOT NULL AND t.target_version != ''
           ORDER BY s.id DESC LIMIT 1""",
        """SELECT version FROM releases
           WHERE status NOT IN ('failed','rolled_back')
           ORDER BY id DESC LIMIT 1""",
    )
    for query in queries:
        try:
            row = conn.execute(query).fetchone()
        except Exception:
            continue
        if row:
            try:
                value = row["version"]
            except (TypeError, IndexError):
                value = row[0]
            if value:
                return str(value)
    return fallback


class ReleaseManager:
    def __init__(self, store: DevelopmentStore) -> None:
        self.store = store

    def reserve(self, version: str, queue_item: int, *, risk: str, tier: str = "agent", source: str = "tobi") -> dict[str, Any]:
        if not re.fullmatch(r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)", version):
            raise ValueError(f"Invalid semantic version: {version}")
        conn = self.store.connect()
        try:
            existing = conn.execute("SELECT * FROM releases WHERE version=?", (version,)).fetchone()
            if existing:
                if int(existing["queue_item"] or 0) != int(queue_item):
                    raise RuntimeError(f"Version {version} is already reserved for another queue item.")
                if existing["status"] in {"failed", "rolled_back"}:
                    raise RuntimeError(f"Version {version} is immutable after {existing['status']} status.")
                return dict(existing)
            cur = conn.execute(
                """INSERT INTO releases(version,tier,source,queue_item,risk,status,created_at)
                   VALUES (?,?,?,?,?,'reserved',?)""",
                (version, tier, source, queue_item, risk, utc_now()),
            )
            conn.commit()
            return dict(conn.execute("SELECT * FROM releases WHERE id=?", (cur.lastrowid,)).fetchone())
        finally:
            conn.close()

    def set_status(self, version: str, status: str, *, commit_sha: str | None = None,
                   tag: str | None = None, notes: str | None = None) -> dict[str, Any]:
        allowed = {"reserved", "merged", "deploying", "released", "failed", "rolled_back"}
        if status not in allowed:
            raise ValueError(f"Invalid release status: {status}")
        conn = self.store.connect()
        try:
            current = conn.execute("SELECT * FROM releases WHERE version=?", (version,)).fetchone()
            if not current:
                raise KeyError(version)
            transitions = {
                "reserved": {"reserved", "merged", "failed"},
                "merged": {"merged", "deploying", "failed", "rolled_back"},
                "deploying": {"deploying", "released", "failed", "rolled_back"},
                "released": {"released"},
                "failed": {"failed"},
                "rolled_back": {"rolled_back"},
            }
            if status not in transitions.get(str(current["status"]), set()):
                raise RuntimeError(f"Release cannot transition from {current['status']} to {status}.")
            released_at = utc_now() if status == "released" else None
            conn.execute(
                """UPDATE releases SET status=?,commit_sha=COALESCE(?,commit_sha),tag=COALESCE(?,tag),
                   notes=COALESCE(?,notes),released_at=COALESCE(?,released_at) WHERE version=?""",
                (status, commit_sha, tag, notes, released_at, version),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM releases WHERE version=?", (version,)).fetchone()
            return dict(row)
        finally:
            conn.close()

    def list(self, limit: int = 100) -> list[dict[str, Any]]:
        conn = self.store.connect()
        try:
            return [dict(row) for row in conn.execute("SELECT * FROM releases ORDER BY id DESC LIMIT ?", (limit,))]
        finally:
            conn.close()

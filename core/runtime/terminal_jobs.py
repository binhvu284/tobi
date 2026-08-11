"""Durable managed background jobs for the dormant canonical terminal runtime."""
from __future__ import annotations

import hashlib
import os
import secrets
import sqlite3
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core import database
from core.runtime.contracts import RuntimeToolCall
from core.runtime.event_store import redact_payload
from core.schema.runtime import _ensure_runtime_schema


MAX_JOB_OUTPUT_CHARS = 6_000
MAX_WAIT_SECONDS = 300
HEARTBEAT_STALE_SECONDS = 3.0
HANDSHAKE_STALE_SECONDS = 5.0
CANCELLATION_POLL_SECONDS = 0.2
WORKER_TOKEN_ENV = "TOBI_TERMINAL_JOB_TOKEN"


class TerminalJobError(RuntimeError):
    """A managed job could not safely complete the requested state change."""


class TerminalJobConflictError(TerminalJobError):
    """A deterministic job identity was reused for different immutable content."""


class TerminalJobNotFoundError(TerminalJobError):
    """The requested canonical terminal job does not exist."""


class TerminalJobLaunchUnknown(TerminalJobError):
    """Process creation returned but no trustworthy worker handshake arrived."""


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _now(now: datetime | None = None) -> datetime:
    value = now or datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _iso(now: datetime | None = None) -> str:
    return _now(now).isoformat().replace("+00:00", "Z")


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
            timezone.utc
        )
    except (TypeError, ValueError):
        return None


def _bounded_output(value: Any) -> tuple[str, bool, str]:
    text = str(value or "")
    redacted = str(redact_payload({"output": text})["output"])
    truncated = len(redacted) > MAX_JOB_OUTPUT_CHARS
    bounded = redacted[-MAX_JOB_OUTPUT_CHARS:]
    return bounded, truncated, _sha256(bounded)


def worker_identity_sha256(worker_token: str) -> str:
    if not isinstance(worker_token, str) or len(worker_token) < 32:
        raise TerminalJobError("worker token is invalid")
    return _sha256(f"terminal-worker:{worker_token}")


def terminal_job_id(call: RuntimeToolCall) -> str:
    if not isinstance(call, RuntimeToolCall) or not call.idempotency_key:
        raise TerminalJobError("a side-effecting runtime call is required")
    identity = (
        f"{call.idempotency_key}:{call.run_id}:{call.step_id}:"
        f"{call.call_id}:{call.tool_ref}"
    )
    return f"terminal-job-{_sha256(identity)[:32]}"


class TerminalJobRepository:
    """Persist one canonical job identity and authenticated worker lifecycle."""

    def _connect(self) -> sqlite3.Connection:
        conn = database.get_connection()
        _ensure_runtime_schema(conn)
        return conn

    def create_intent(
        self,
        call: RuntimeToolCall,
        *,
        target: str,
        command_sha256: str,
        working_directory_sha256: str,
        duration_s: int,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if not call.idempotency_key:
            raise TerminalJobError("start action requires idempotency")
        if duration_s < 1 or duration_s > MAX_WAIT_SECONDS:
            raise TerminalJobError("wait duration is outside the managed bound")
        job_id = terminal_job_id(call)
        created_at = _iso(now)
        empty_output_hash = _sha256("")
        identity = {
            "job_id": job_id,
            "start_idempotency_key": call.idempotency_key,
            "run_id": call.run_id,
            "step_id": call.step_id,
            "call_id": call.call_id,
            "tool_ref": call.tool_ref,
            "target": target,
            "operation": "wait",
            "command_sha256": command_sha256,
            "working_directory_sha256": working_directory_sha256,
            "duration_s": duration_s,
        }
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM mc_terminal_jobs WHERE job_id=?", (job_id,)
            ).fetchone()
            if row is None:
                conn.execute(
                    """INSERT INTO mc_terminal_jobs (
                        job_id,start_idempotency_key,run_id,step_id,call_id,tool_ref,
                        target,operation,command_sha256,working_directory_sha256,
                        duration_s,status,output_sha256,created_at,updated_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,'intent',?,?,?)""",
                    (
                        job_id,
                        call.idempotency_key,
                        call.run_id,
                        call.step_id,
                        call.call_id,
                        call.tool_ref,
                        target,
                        "wait",
                        command_sha256,
                        working_directory_sha256,
                        duration_s,
                        empty_output_hash,
                        created_at,
                        created_at,
                    ),
                )
            else:
                mismatches = [
                    name for name, value in identity.items() if row[name] != value
                ]
                if mismatches:
                    raise TerminalJobConflictError(
                        "managed job identity changed: " + ", ".join(mismatches)
                    )
            stored = conn.execute(
                "SELECT * FROM mc_terminal_jobs WHERE job_id=?", (job_id,)
            ).fetchone()
            conn.commit()
            return dict(stored)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def mark_launching(
        self,
        job_id: str,
        worker_token: str,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        timestamp = _iso(now)
        identity_hash = worker_identity_sha256(worker_token)
        empty_output_hash = _sha256("")
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            changed = conn.execute(
                """UPDATE mc_terminal_jobs
                   SET status='launching',launch_count=launch_count+1,
                       worker_identity_sha256=?,output='',output_sha256=?,
                       output_truncated=0,exit_code=NULL,error_code=NULL,
                       updated_at=?,launch_started_at=?,worker_started_at=NULL,
                       heartbeat_at=NULL,completed_at=NULL,version=version+1
                   WHERE job_id=? AND status IN ('intent','not_started')""",
                (identity_hash, empty_output_hash, timestamp, timestamp, job_id),
            )
            if changed.rowcount != 1:
                raise TerminalJobError("managed job is not safe to launch")
            row = conn.execute(
                "SELECT * FROM mc_terminal_jobs WHERE job_id=?", (job_id,)
            ).fetchone()
            conn.commit()
            return dict(row)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def mark_not_started(
        self,
        job_id: str,
        worker_token: str,
        *,
        now: datetime | None = None,
    ) -> None:
        timestamp = _iso(now)
        output, truncated, output_hash = _bounded_output(
            "Managed worker did not start."
        )
        conn = self._connect()
        try:
            changed = conn.execute(
                """UPDATE mc_terminal_jobs
                   SET status='not_started',output=?,output_sha256=?,output_truncated=?,
                       error_code='worker_not_started',updated_at=?,completed_at=?,
                       version=version+1
                   WHERE job_id=? AND status='launching'
                     AND worker_identity_sha256=? AND worker_started_at IS NULL""",
                (
                    output,
                    output_hash,
                    int(truncated),
                    timestamp,
                    timestamp,
                    job_id,
                    worker_identity_sha256(worker_token),
                ),
            )
            if changed.rowcount != 1:
                raise TerminalJobError("managed launch outcome is no longer pre-start")
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def claim_worker(
        self,
        job_id: str,
        worker_token: str,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        timestamp = _iso(now)
        output, truncated, output_hash = _bounded_output("Wait job started.")
        identity_hash = worker_identity_sha256(worker_token)
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            changed = conn.execute(
                """UPDATE mc_terminal_jobs
                   SET status='running',output=?,output_sha256=?,output_truncated=?,
                       updated_at=?,worker_started_at=?,heartbeat_at=?,version=version+1
                   WHERE job_id=? AND status='launching'
                     AND worker_identity_sha256=?""",
                (
                    output,
                    output_hash,
                    int(truncated),
                    timestamp,
                    timestamp,
                    timestamp,
                    job_id,
                    identity_hash,
                ),
            )
            row = conn.execute(
                "SELECT * FROM mc_terminal_jobs WHERE job_id=?", (job_id,)
            ).fetchone()
            if changed.rowcount != 1:
                if (
                    row is None
                    or row["worker_identity_sha256"] != identity_hash
                    or row["status"] not in {"running", "succeeded", "failed"}
                ):
                    raise TerminalJobError("worker could not claim this managed job")
            conn.commit()
            return dict(row)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def heartbeat(
        self,
        job_id: str,
        worker_token: str,
        *,
        now: datetime | None = None,
    ) -> None:
        timestamp = _iso(now)
        conn = self._connect()
        try:
            changed = conn.execute(
                """UPDATE mc_terminal_jobs
                   SET heartbeat_at=?,updated_at=?,version=version+1
                   WHERE job_id=? AND status='running'
                     AND worker_identity_sha256=?""",
                (
                    timestamp,
                    timestamp,
                    job_id,
                    worker_identity_sha256(worker_token),
                ),
            )
            if changed.rowcount != 1:
                raise TerminalJobError("worker heartbeat lost job ownership")
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def finish_job(
        self,
        job_id: str,
        worker_token: str,
        *,
        status: str,
        exit_code: int | None,
        output: Any,
        error_code: str | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if status not in {"succeeded", "failed"}:
            raise TerminalJobError("managed job final status is invalid")
        timestamp = _iso(now)
        bounded, truncated, output_hash = _bounded_output(output)
        conn = self._connect()
        try:
            changed = conn.execute(
                """UPDATE mc_terminal_jobs
                   SET status=?,output=?,output_sha256=?,output_truncated=?,exit_code=?,
                       error_code=?,updated_at=?,heartbeat_at=?,completed_at=?,
                       version=version+1
                   WHERE job_id=? AND status='running'
                     AND cancel_requested_at IS NULL
                     AND worker_identity_sha256=?""",
                (
                    status,
                    bounded,
                    output_hash,
                    int(truncated),
                    exit_code,
                    error_code,
                    timestamp,
                    timestamp,
                    timestamp,
                    job_id,
                    worker_identity_sha256(worker_token),
                ),
            )
            if changed.rowcount != 1:
                raise TerminalJobError("worker could not finalize this managed job")
            row = conn.execute(
                "SELECT * FROM mc_terminal_jobs WHERE job_id=?", (job_id,)
            ).fetchone()
            conn.commit()
            return dict(row)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def require_owner(self, job_id: str, owner_id: str) -> None:
        if not isinstance(owner_id, str) or not owner_id.strip():
            raise TerminalJobError("managed job owner is invalid")
        conn = self._connect()
        try:
            row = conn.execute(
                """SELECT r.owner_id
                   FROM mc_terminal_jobs AS j
                   JOIN mc_runs AS r ON r.run_id=j.run_id
                   WHERE j.job_id=?""",
                (job_id,),
            ).fetchone()
            if row is None or row["owner_id"] != owner_id:
                raise TerminalJobError("managed job is unavailable to this owner")
        finally:
            conn.close()

    def request_cancellation(
        self,
        call: RuntimeToolCall,
        *,
        job_id: str,
        owner_id: str,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if not isinstance(call, RuntimeToolCall) or not call.idempotency_key:
            raise TerminalJobError("cancel action requires idempotency")
        if not isinstance(owner_id, str) or not owner_id.strip():
            raise TerminalJobError("managed job owner is invalid")
        timestamp = _iso(now)
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                """SELECT j.*,r.owner_id AS originating_owner_id
                   FROM mc_terminal_jobs AS j
                   JOIN mc_runs AS r ON r.run_id=j.run_id
                   WHERE j.job_id=?""",
                (job_id,),
            ).fetchone()
            if row is None or row["originating_owner_id"] != owner_id:
                raise TerminalJobError("managed job is unavailable to this owner")

            request_state: str
            if row["cancel_idempotency_key"] is not None:
                request_state = (
                    "requested"
                    if row["cancel_idempotency_key"] == call.idempotency_key
                    else "already_requested"
                )
            elif row["status"] in {"succeeded", "failed", "not_started"}:
                request_state = "already_inactive"
            elif row["status"] not in {"launching", "running"}:
                raise TerminalJobError("managed job is not ready for cancellation")
            else:
                changed = conn.execute(
                    """UPDATE mc_terminal_jobs
                       SET cancel_idempotency_key=?,cancel_requested_at=?,
                           cancel_requested_by=?,updated_at=?,version=version+1
                       WHERE job_id=? AND status IN ('launching','running')
                         AND cancel_idempotency_key IS NULL
                         AND cancel_requested_at IS NULL
                         AND cancel_requested_by IS NULL""",
                    (
                        call.idempotency_key,
                        timestamp,
                        owner_id,
                        timestamp,
                        job_id,
                    ),
                )
                if changed.rowcount != 1:
                    raise TerminalJobError("managed cancellation request conflicted")
                request_state = "requested"

            stored = conn.execute(
                "SELECT * FROM mc_terminal_jobs WHERE job_id=?", (job_id,)
            ).fetchone()
            conn.commit()
            value = self._public(stored, include_output=False, now=now)
            value["request_state"] = request_state
            return value
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def cancellation_requested(self, job_id: str, worker_token: str) -> bool:
        identity_hash = worker_identity_sha256(worker_token)
        conn = self._connect()
        try:
            row = conn.execute(
                """SELECT status,worker_identity_sha256,cancel_requested_at
                   FROM mc_terminal_jobs WHERE job_id=?""",
                (job_id,),
            ).fetchone()
            if (
                row is None
                or row["status"] != "running"
                or row["worker_identity_sha256"] != identity_hash
            ):
                raise TerminalJobError("worker lost managed job ownership")
            return row["cancel_requested_at"] is not None
        finally:
            conn.close()

    def finish_cancelled(
        self,
        job_id: str,
        worker_token: str,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        timestamp = _iso(now)
        bounded, truncated, output_hash = _bounded_output(
            "Managed wait job cancelled."
        )
        conn = self._connect()
        try:
            changed = conn.execute(
                """UPDATE mc_terminal_jobs
                   SET status='failed',output=?,output_sha256=?,output_truncated=?,
                       exit_code=NULL,error_code='managed_job_cancelled',
                       updated_at=?,heartbeat_at=?,completed_at=?,
                       cancel_acknowledged_at=?,version=version+1
                   WHERE job_id=? AND status='running'
                     AND worker_identity_sha256=?
                     AND cancel_idempotency_key IS NOT NULL
                     AND cancel_requested_at IS NOT NULL
                     AND cancel_requested_by IS NOT NULL
                     AND cancel_acknowledged_at IS NULL""",
                (
                    bounded,
                    output_hash,
                    int(truncated),
                    timestamp,
                    timestamp,
                    timestamp,
                    timestamp,
                    job_id,
                    worker_identity_sha256(worker_token),
                ),
            )
            if changed.rowcount != 1:
                raise TerminalJobError(
                    "worker could not acknowledge managed job cancellation"
                )
            row = conn.execute(
                "SELECT * FROM mc_terminal_jobs WHERE job_id=?", (job_id,)
            ).fetchone()
            conn.commit()
            return dict(row)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _stored_row(self, job_id: str) -> sqlite3.Row:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM mc_terminal_jobs WHERE job_id=?", (job_id,)
            ).fetchone()
            if row is None:
                raise TerminalJobNotFoundError(f"unknown managed job {job_id}")
            return row
        finally:
            conn.close()

    def _observed_state(
        self, row: Mapping[str, Any], *, now: datetime | None = None
    ) -> str:
        status = str(row["status"])
        if status == "failed" and row["error_code"] == "managed_job_cancelled":
            return "cancelled"
        observed_at = _now(now)
        if status == "launching":
            launch_at = _parse_iso(row["launch_started_at"])
            if launch_at is None or (
                observed_at - launch_at
            ).total_seconds() > HANDSHAKE_STALE_SECONDS:
                return "unknown"
        elif status == "running":
            heartbeat_at = _parse_iso(row["heartbeat_at"])
            if heartbeat_at is None or (
                observed_at - heartbeat_at
            ).total_seconds() > HEARTBEAT_STALE_SECONDS:
                return "unknown"
        return status

    def _public(
        self,
        row: Mapping[str, Any],
        *,
        include_output: bool,
        tail: int = MAX_JOB_OUTPUT_CHARS,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        output = str(row["output"] or "")
        value = {
            "job_id": row["job_id"],
            "state": self._observed_state(row, now=now),
            "duration_s": int(row["duration_s"]),
            "command_sha256": row["command_sha256"],
            "created_at": row["created_at"],
            "started_at": row["worker_started_at"],
            "completed_at": row["completed_at"],
            "exit_code": row["exit_code"],
            "output_chars": len(output),
            "truncated": bool(row["output_truncated"]),
            "cancellation_requested": row["cancel_requested_at"] is not None,
            "cancellation_acknowledged": row["cancel_acknowledged_at"] is not None,
            "cancel_requested_at": row["cancel_requested_at"],
            "cancel_acknowledged_at": row["cancel_acknowledged_at"],
        }
        if include_output:
            value["output"] = output[-max(1, min(int(tail), MAX_JOB_OUTPUT_CHARS)) :]
        return value

    def get_job(
        self,
        job_id: str,
        *,
        tail: int = MAX_JOB_OUTPUT_CHARS,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        return self._public(
            self._stored_row(job_id), include_output=True, tail=tail, now=now
        )

    def list_jobs(
        self, *, limit: int = 20, now: datetime | None = None
    ) -> dict[str, Any]:
        bounded_limit = max(1, min(int(limit), 100))
        conn = self._connect()
        try:
            rows = conn.execute(
                """SELECT * FROM mc_terminal_jobs
                   ORDER BY created_at DESC, job_id DESC LIMIT ?""",
                (bounded_limit,),
            ).fetchall()
        finally:
            conn.close()
        jobs = [
            self._public(row, include_output=False, now=now) for row in rows
        ]
        return {"count": len(jobs), "jobs": jobs}

    def wait_for_worker(
        self,
        job_id: str,
        worker_token: str,
        *,
        timeout_s: float,
        poll_interval_s: float,
    ) -> dict[str, Any] | None:
        expected_identity = worker_identity_sha256(worker_token)
        deadline = time.monotonic() + max(0.0, timeout_s)
        while True:
            row = self._stored_row(job_id)
            if row["worker_identity_sha256"] != expected_identity:
                raise TerminalJobError("managed worker identity changed during launch")
            if row["worker_started_at"] and row["status"] in {
                "running",
                "succeeded",
                "failed",
            }:
                return dict(row)
            if time.monotonic() >= deadline:
                return None
            time.sleep(max(0.001, poll_interval_s))

    def start_evidence(
        self, job_id: str, *, now: datetime | None = None
    ) -> tuple[str, dict[str, Any] | None]:
        try:
            row = self._stored_row(job_id)
        except TerminalJobNotFoundError:
            return "not_applied", None
        public = self._public(row, include_output=False, now=now)
        if row["status"] in {"intent", "not_started"} and not row[
            "worker_started_at"
        ]:
            return "not_applied", public
        if row["worker_started_at"] and row["worker_identity_sha256"]:
            return "applied", public
        return "unknown", public

    def cancel_evidence(
        self,
        job_id: str,
        cancel_idempotency_key: str,
        *,
        now: datetime | None = None,
    ) -> tuple[str, dict[str, Any] | None]:
        try:
            row = self._stored_row(job_id)
        except TerminalJobNotFoundError:
            return "not_applied", None
        public = self._public(row, include_output=False, now=now)
        if row["cancel_idempotency_key"] == cancel_idempotency_key:
            public["request_state"] = "requested"
            return "applied", public
        return "not_applied", public


def _worker_environment(worker_token: str) -> dict[str, str]:
    allowed = {
        "APPDATA",
        "COMSPEC",
        "HOME",
        "LANG",
        "LC_ALL",
        "LOCALAPPDATA",
        "PATH",
        "PATHEXT",
        "SYSTEMROOT",
        "TEMP",
        "TMP",
        "USERPROFILE",
        "WINDIR",
    }
    env = {key: value for key, value in os.environ.items() if key in allowed}
    env.update(
        {
            "DB_PATH": str(Path(database.DB_PATH).resolve()),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONIOENCODING": "utf-8",
            WORKER_TOKEN_ENV: worker_token,
        }
    )
    return env


def launch_detached_worker(
    job_id: str,
    worker_token: str,
    *,
    working_directory: Path,
) -> None:
    command = [
        sys.executable,
        "-m",
        "core.runtime.terminal_job_worker",
        job_id,
    ]
    kwargs: dict[str, Any] = {
        "cwd": str(working_directory),
        "env": _worker_environment(worker_token),
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
    }
    if os.name == "nt":
        kwargs["creationflags"] = (
            getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            | getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
    else:
        kwargs["start_new_session"] = True
    process = subprocess.Popen(command, **kwargs)
    threading.Thread(
        target=process.wait,
        daemon=True,
        name=f"tobi-terminal-job-reaper-{job_id[-8:]}",
    ).start()


def new_worker_token() -> str:
    return secrets.token_urlsafe(32)


TerminalJobLauncher = Callable[[str, str], None]

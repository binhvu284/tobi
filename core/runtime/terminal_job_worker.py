"""Detached worker entry point for one fixed managed wait operation."""
from __future__ import annotations

import os
import sys
import time

from core.runtime.terminal_jobs import (
    WORKER_TOKEN_ENV,
    TerminalJobRepository,
)


HEARTBEAT_INTERVAL_SECONDS = 0.5
WAIT_POLL_SECONDS = 0.05


def run_wait_job(job_id: str, worker_token: str) -> int:
    jobs = TerminalJobRepository()
    claimed = False
    try:
        row = jobs.claim_worker(job_id, worker_token)
        claimed = True
        duration_s = int(row["duration_s"])
        deadline = time.monotonic() + duration_s
        next_heartbeat = time.monotonic() + HEARTBEAT_INTERVAL_SECONDS
        while time.monotonic() < deadline:
            now = time.monotonic()
            if now >= next_heartbeat:
                jobs.heartbeat(job_id, worker_token)
                next_heartbeat = now + HEARTBEAT_INTERVAL_SECONDS
            time.sleep(min(WAIT_POLL_SECONDS, max(0.0, deadline - now)))
        jobs.finish_job(
            job_id,
            worker_token,
            status="succeeded",
            exit_code=0,
            output="Wait job started.\nWait job completed.",
        )
        return 0
    except Exception:
        if claimed:
            try:
                jobs.finish_job(
                    job_id,
                    worker_token,
                    status="failed",
                    exit_code=1,
                    error_code="managed_worker_failed",
                    output="Managed wait job failed.",
                )
            except Exception:
                pass
        return 1


def main(argv: list[str] | None = None) -> int:
    values = list(sys.argv[1:] if argv is None else argv)
    worker_token = os.environ.pop(WORKER_TOKEN_ENV, "")
    if len(values) != 1 or not worker_token:
        return 2
    job_id = values[0]
    if not job_id.startswith("terminal-job-"):
        return 2
    return run_wait_job(job_id, worker_token)


if __name__ == "__main__":
    raise SystemExit(main())

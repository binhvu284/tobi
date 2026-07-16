"""Standalone supervised service for durable external coding-worker jobs."""
from __future__ import annotations

import argparse
import json
import os
import signal
import shutil
import socket
import threading
import uuid
from typing import Any

from core.env_utils import safe_load_dotenv
from core.coding_runner import IsolatedProcessRunner, RunnerSecretEnvelope
from core.development_store import DevelopmentStore

safe_load_dotenv()


class CodingRunnerService:
    def __init__(
        self,
        store: DevelopmentStore | None = None,
        *,
        node_id: str | None = None,
        poll_seconds: float = 1.0,
    ) -> None:
        self.store = store or DevelopmentStore()
        self.node_id = node_id or (
            f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        )
        self.poll_seconds = max(0.1, poll_seconds)
        self.runner = IsolatedProcessRunner()
        self.secrets = RunnerSecretEnvelope(
            self.store.db_path.parent / "developer" / "runner-envelope.key"
        )
        self.stop_event = threading.Event()

    @staticmethod
    def metadata(**extra: Any) -> dict[str, Any]:
        return {
            "pid": os.getpid(),
            "version": 1,
            "adapters": {
                name: bool(shutil.which(name)) for name in ("codex", "opencode")
            },
            **extra,
        }

    def heartbeat(self) -> None:
        self.store.heartbeat_runner_node(
            self.node_id,
            metadata=self.metadata(),
        )

    def tick(self) -> bool:
        self.heartbeat()
        self.store.reconcile_runner_jobs()
        job = self.store.claim_runner_job(self.node_id)
        if not job:
            return False
        self.run_job(job)
        return True

    def run_job(self, job: dict[str, Any]) -> None:
        job_id = int(job["id"])
        workflow_id = int(job["workflow_id"])
        result: dict[str, Any] = {}

        def execute() -> None:
            try:
                result["value"] = self.runner.run(
                    job_id,
                    json.loads(job["argv_json"]),
                    cwd=job["cwd"],
                    timeout=int(job["timeout_seconds"]),
                    allowed_env=json.loads(job["allowed_env_json"] or "[]"),
                    adapter=str(job["adapter"]),
                    max_output_bytes=int(job["max_output_bytes"]),
                    env_overrides=self.secrets.open(job.get("env_envelope_json") or ""),
                    on_output=lambda line: self.store.add_runner_event(job_id, line),
                )
            except BaseException as exc:
                result["error"] = exc

        thread = threading.Thread(target=execute, name=f"coding-runner-{job_id}", daemon=True)
        thread.start()
        while thread.is_alive():
            current = self.store.get_runner_job(job_id) or {}
            if current.get("cancel_requested"):
                self.runner.cancel(job_id)
            self.store.heartbeat_runner_job(job_id, self.node_id)
            self.heartbeat()
            thread.join(timeout=0.5)

        current = self.store.get_runner_job(job_id) or {}
        if current.get("cancel_requested"):
            self.store.finish_runner_job(
                job_id,
                status="canceled",
                error_code="owner_canceled",
                stderr="External coding worker was canceled by the owner.",
            )
            return
        error = result.get("error")
        if error:
            self.store.finish_runner_job(
                job_id,
                status="failed",
                error_code="worker_timeout" if isinstance(error, TimeoutError) else type(error).__name__,
                stderr=str(error)[:20_000],
            )
            return
        exit_code, stdout, stderr = result["value"]
        self.store.finish_runner_job(
            job_id,
            status="completed",
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
        )
        self.store.heartbeat_runner_node(
            self.node_id,
            metadata=self.metadata(last_workflow_id=workflow_id),
        )

    def run_forever(self) -> None:
        self.heartbeat()
        while not self.stop_event.is_set():
            handled = self.tick()
            if not handled:
                self.stop_event.wait(self.poll_seconds)
        self.store.heartbeat_runner_node(
            self.node_id,
            status="stopped",
            metadata=self.metadata(),
        )

    def stop(self, *_args: Any) -> None:
        self.stop_event.set()


def main() -> None:
    parser = argparse.ArgumentParser(description="TOBI supervised coding runner")
    parser.add_argument("--poll-seconds", type=float, default=1.0)
    parser.add_argument("--node-id", default=None)
    args = parser.parse_args()
    service = CodingRunnerService(node_id=args.node_id, poll_seconds=args.poll_seconds)
    signal.signal(signal.SIGINT, service.stop)
    signal.signal(signal.SIGTERM, service.stop)
    service.run_forever()


if __name__ == "__main__":
    main()

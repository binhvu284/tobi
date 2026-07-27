"""Subprocess boundary for external coding-agent adapters."""
from __future__ import annotations

import base64
import json
import os
import subprocess
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any, Callable, Sequence

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class RunnerError(RuntimeError):
    pass


class RunnerSecretEnvelope:
    """Encrypt the one profile-specific environment handoff stored with a runner job."""

    AAD = b"tobi-coding-runner-env:v1"

    def __init__(self, key_path: Path | str) -> None:
        configured = os.getenv("TOBI_CODING_RUNNER_KEY_PATH", "").strip()
        self.key_path = Path(configured or key_path).expanduser().resolve()

    def _key(self) -> bytes:
        self.key_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            descriptor = os.open(
                self.key_path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
        except FileExistsError:
            descriptor = None
        if descriptor is not None:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(os.urandom(32))
            try:
                os.chmod(self.key_path, 0o600)
            except OSError:
                pass
        key = self.key_path.read_bytes()
        if len(key) != 32:
            raise RunnerError("Coding runner envelope key is invalid.")
        return key

    def seal(self, values: dict[str, str]) -> str:
        if not values:
            return ""
        nonce = os.urandom(12)
        plaintext = json.dumps(values, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
        ciphertext = AESGCM(self._key()).encrypt(nonce, plaintext, self.AAD)
        return json.dumps({
            "version": 1,
            "nonce": base64.b64encode(nonce).decode("ascii"),
            "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
        }, separators=(",", ":"))

    def open(self, envelope: str) -> dict[str, str]:
        if not envelope:
            return {}
        try:
            payload = json.loads(envelope)
            nonce = base64.b64decode(payload["nonce"], validate=True)
            ciphertext = base64.b64decode(payload["ciphertext"], validate=True)
            values = json.loads(
                AESGCM(self._key()).decrypt(nonce, ciphertext, self.AAD).decode("utf-8")
            )
        except Exception as exc:
            raise RunnerError("Coding runner credential envelope could not be decrypted.") from exc
        if not isinstance(values, dict) or any(
            not isinstance(key, str) or not isinstance(value, str)
            for key, value in values.items()
        ):
            raise RunnerError("Coding runner credential envelope is invalid.")
        return values


class IsolatedProcessRunner:
    """Run array-form commands with a scrubbed environment and hard deadline."""

    BASE_ENV = {
        "PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "COMSPEC", "TEMP", "TMP",
        "HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "CODEX_HOME",
        "OPENCODE_CONFIG", "OPENCODE_CONFIG_DIR", "LANG", "LC_ALL",
    }

    def __init__(self) -> None:
        self._processes: dict[int, subprocess.Popen[str]] = {}
        self._lock = threading.Lock()

    def run(
        self,
        workflow_id: int,
        argv: Sequence[str],
        *,
        cwd: Path | str,
        timeout: int,
        allowed_env: Sequence[str] = (),
        on_output: Callable[[str], None] | None = None,
        adapter: str = "external",
        max_output_bytes: int = 2_097_152,
        env_overrides: dict[str, str] | None = None,
        stdin_text: str | None = None,
    ) -> tuple[int, str, str]:
        if not argv or not str(argv[0]).strip():
            raise RunnerError("External worker command is empty.")
        if max_output_bytes < 1:
            raise RunnerError("External worker output limit must be positive.")
        environment = {
            key: value for key, value in os.environ.items()
            if key.upper() in self.BASE_ENV or key in allowed_env
        }
        allowed_names = {str(item) for item in allowed_env}
        for key, value in (env_overrides or {}).items():
            if key in allowed_names:
                environment[key] = value
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        process = subprocess.Popen(
            [str(item) for item in argv],
            cwd=str(Path(cwd).resolve()),
            env=environment,
            # Only claim stdin when there is something to send. Left inherited otherwise, so
            # adapters that read the terminal keep behaving as they did.
            stdin=subprocess.PIPE if stdin_text is not None else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=flags,
        )
        with self._lock:
            self._processes[workflow_id] = process
        stdout_lines: deque[str] = deque()
        stderr_lines: deque[str] = deque()

        def drain(stream, lines: deque[str], callback: Callable[[str], None] | None) -> None:
            size = 0
            try:
                for line in iter(stream.readline, ""):
                    encoded_size = len(line.encode("utf-8", errors="replace"))
                    if encoded_size > max_output_bytes:
                        line = line.encode("utf-8", errors="replace")[-max_output_bytes:].decode(
                            "utf-8", errors="replace"
                        )
                        encoded_size = len(line.encode("utf-8", errors="replace"))
                    lines.append(line)
                    size += encoded_size
                    while lines and size > max_output_bytes:
                        size -= len(lines.popleft().encode("utf-8", errors="replace"))
                    if callback:
                        try:
                            callback(line.rstrip("\r\n"))
                        except Exception:
                            pass
            finally:
                stream.close()

        stdout_thread = threading.Thread(
            target=drain, args=(process.stdout, stdout_lines, on_output), daemon=True
        )
        stderr_thread = threading.Thread(
            target=drain, args=(process.stderr, stderr_lines, None), daemon=True
        )
        stdout_thread.start()
        stderr_thread.start()
        if stdin_text is not None and process.stdin is not None:
            # Written after the drain threads are running: a large prompt can exceed the pipe
            # buffer, and the child may block writing output until we read it, so writing
            # first would deadlock. A child that exits before reading gives a broken pipe,
            # which is its own failure to report -- not this write's.
            try:
                process.stdin.write(stdin_text)
            except (BrokenPipeError, OSError):
                pass
            finally:
                try:
                    process.stdin.close()
                except (BrokenPipeError, OSError):
                    pass
        deadline = time.monotonic() + max(1, timeout)
        try:
            while process.poll() is None:
                if time.monotonic() >= deadline:
                    process.kill()
                    process.wait(timeout=10)
                    raise TimeoutError(
                        f"External coding worker exceeded its {timeout}s deadline."
                    )
                time.sleep(0.1)
        finally:
            stdout_thread.join(timeout=5)
            stderr_thread.join(timeout=5)
            with self._lock:
                self._processes.pop(workflow_id, None)
        return process.returncode, "".join(stdout_lines), "".join(stderr_lines)

    def cancel(self, workflow_id: int) -> bool:
        with self._lock:
            process = self._processes.get(workflow_id)
        if not process or process.poll() is not None:
            return False
        process.kill()
        return True


class QueuedProcessRunner:
    """Submit external worker processes to a separately supervised runner service."""

    def __init__(self, store, *, poll_seconds: float = 0.25) -> None:
        self.store = store
        self.poll_seconds = max(0.05, poll_seconds)
        self.secrets = RunnerSecretEnvelope(
            store.db_path.parent / "developer" / "runner-envelope.key"
        )
        self._jobs: dict[int, int] = {}
        self._lock = threading.Lock()

    def run(
        self,
        workflow_id: int,
        argv: Sequence[str],
        *,
        cwd: Path | str,
        timeout: int,
        allowed_env: Sequence[str] = (),
        on_output: Callable[[str], None] | None = None,
        adapter: str = "external",
        max_output_bytes: int = 2_097_152,
        stdin_text: str | None = None,
    ) -> tuple[int, str, str]:
        if not argv or not str(argv[0]).strip():
            raise RunnerError("External worker command is empty.")
        if stdin_text is not None:
            # Jobs are handed to a separate service process through the database, which has
            # nowhere to carry stdin. Refusing is the only safe answer: dropping it silently
            # would launch the CLI with a `-` placeholder and no prompt behind it, and the
            # agent would run against an empty brief.
            raise RunnerError(
                "Service runner mode cannot deliver a stdin prompt. Run with "
                "TOBI_CODING_RUNNER_MODE=local, or extend the runner job schema to carry it."
            )
        job = self.store.submit_runner_job(
            workflow_id=workflow_id,
            adapter=adapter,
            argv=[str(item) for item in argv],
            cwd=str(Path(cwd).resolve()),
            allowed_env=list(allowed_env),
            timeout_seconds=max(1, timeout),
            max_output_bytes=max(1, max_output_bytes),
            env_envelope=self.secrets.seal({
                key: os.environ[key] for key in allowed_env if key and key in os.environ
            }),
        )
        job_id = int(job["id"])
        with self._lock:
            self._jobs[workflow_id] = job_id
        startup_timeout = max(
            2, int(os.getenv("TOBI_CODING_RUNNER_STARTUP_TIMEOUT_SECONDS", "15"))
        )
        submitted_at = time.monotonic()
        deadline = submitted_at + startup_timeout + max(1, timeout) + 30
        event_sequence = 0

        def emit_events() -> None:
            nonlocal event_sequence
            events = self.store.list_runner_events(
                job_id, after_sequence=event_sequence, limit=500
            )
            for event in events:
                event_sequence = max(event_sequence, int(event["sequence"]))
                if on_output:
                    on_output(str(event["line"]))

        try:
            while time.monotonic() < deadline:
                current = self.store.get_runner_job(job_id)
                if not current:
                    raise RunnerError("Coding runner job disappeared before completion.")
                emit_events()
                status = str(current["status"])
                if status == "completed":
                    stdout = str(current.get("stdout") or "")
                    if on_output and not event_sequence:
                        for line in stdout.splitlines():
                            on_output(line)
                    return int(current.get("exit_code") or 0), stdout, str(current.get("stderr") or "")
                if status == "failed":
                    message = str(current.get("stderr") or current.get("error_code") or "Runner failed.")
                    if current.get("error_code") == "worker_timeout":
                        raise TimeoutError(message)
                    raise RunnerError(message)
                if status == "canceled":
                    raise RunnerError("External coding worker was canceled.")
                if status == "queued" and time.monotonic() - submitted_at > startup_timeout:
                    self.store.request_runner_cancel(workflow_id)
                    raise RunnerError(
                        "Coding runner service did not claim the job. Start the supervised "
                        "runner service or use local runner mode."
                    )
                time.sleep(self.poll_seconds)
            self.store.request_runner_cancel(workflow_id)
            raise TimeoutError(f"External coding worker exceeded its {timeout}s deadline.")
        finally:
            with self._lock:
                self._jobs.pop(workflow_id, None)

    def cancel(self, workflow_id: int) -> bool:
        return bool(self.store.request_runner_cancel(workflow_id))

    def health(self) -> dict[str, Any]:
        nodes = self.store.list_runner_nodes(active_within_seconds=30)
        parsed_nodes: list[dict[str, Any]] = []
        for node in nodes:
            item = dict(node)
            try:
                item["metadata"] = json.loads(item.get("metadata_json") or "{}")
            except json.JSONDecodeError:
                item["metadata"] = {}
            parsed_nodes.append(item)
        return {
            "status": "ready" if nodes else "unavailable",
            "detail": (
                f"{len(nodes)} supervised coding runner node(s) are active."
                if nodes else "No supervised coding runner heartbeat was seen in the last 30 seconds."
            ),
            "nodes": parsed_nodes,
        }

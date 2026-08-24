"""Managed, credential-free Hermes subprocess adapter."""
from __future__ import annotations

import json
import os
import queue
import shlex
import shutil
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable

from core.coding_policy import CodingPolicy, PolicyDenied
from core.proc import no_window


class HermesUnavailable(RuntimeError):
    pass


class HermesWorker:
    def __init__(self, policy: CodingPolicy) -> None:
        self.policy = policy
        self._active: dict[int, subprocess.Popen[str]] = {}
        self._lock = threading.Lock()

    def command(self) -> list[str]:
        configured = os.getenv("TOBI_HERMES_CODING_COMMAND", "hermes")
        argv = shlex.split(configured, posix=os.name != "nt")
        if not argv or not shutil.which(argv[0]):
            raise HermesUnavailable(
                "Hermes coding worker is unavailable. Install Hermes or set TOBI_HERMES_CODING_COMMAND."
            )
        return argv

    def _environment(self, workflow_id: int, stage_id: str) -> dict[str, str]:
        allow = {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "LANG", "LC_ALL"}
        env = {key: value for key, value in os.environ.items() if key.upper() in allow}
        home = self.policy.repo_path("artifact_root") / "worker-home" / str(workflow_id)
        home.mkdir(parents=True, exist_ok=True)
        env.update({"HOME": str(home), "USERPROFILE": str(home)})
        env.update({"TOBI_WORKFLOW_ID": str(workflow_id), "TOBI_STAGE_ID": stage_id,
                    "TOBI_MANAGED_WORKER": "1", "PYTHONUNBUFFERED": "1"})
        return env

    def run(
        self,
        workflow_id: int,
        stage_id: str,
        worktree: Path | str,
        brief: dict[str, Any],
        *,
        on_event: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        argv = self.command()
        cwd = Path(worktree).resolve()
        sandbox_raw = os.getenv("TOBI_HERMES_SANDBOX_ARGV", "")
        if not sandbox_raw:
            raise HermesUnavailable("External Hermes requires TOBI_HERMES_SANDBOX_ARGV; unisolated CLI workers are denied.")
        try:
            template = json.loads(sandbox_raw)
        except json.JSONDecodeError as exc:
            raise HermesUnavailable("TOBI_HERMES_SANDBOX_ARGV must be a JSON argument array.") from exc
        if not isinstance(template, list) or not template:
            raise HermesUnavailable("TOBI_HERMES_SANDBOX_ARGV must contain a sandbox executable.")
        wrapped: list[str] = []
        for part in template:
            if part == "{command}":
                wrapped.extend(argv)
            else:
                wrapped.append(str(part).replace("{worktree}", str(cwd)))
        if "{command}" not in template or not shutil.which(wrapped[0]):
            raise HermesUnavailable("Hermes sandbox wrapper is invalid or unavailable.")
        argv = wrapped
        timeout = self.policy.limit("worker_timeout_seconds", 1800)
        output_limit = self.policy.limit("worker_output_bytes", 2_097_152)
        # Its own process group so a cancel can signal the whole tree, and no console window:
        # this runs from a background server, where a new console is a window on the owner's screen.
        creationflags = no_window(
            subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0)
        proc = subprocess.Popen(
            argv, cwd=str(cwd), env=self._environment(workflow_id, stage_id),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
            creationflags=creationflags, start_new_session=os.name != "nt",
        )
        with self._lock:
            if workflow_id in self._active:
                proc.kill()
                raise RuntimeError("This workflow already has an active Hermes worker.")
            self._active[workflow_id] = proc
        assert proc.stdin is not None and proc.stdout is not None
        proc.stdin.write(json.dumps(brief, ensure_ascii=True) + "\n")
        proc.stdin.close()
        started = time.monotonic()
        captured: list[str] = []
        total = 0
        events: list[dict[str, Any]] = []
        lines: queue.Queue[str | None] = queue.Queue()

        def read_output() -> None:
            assert proc.stdout is not None
            try:
                for output_line in iter(proc.stdout.readline, ""):
                    lines.put(output_line)
            finally:
                lines.put(None)

        reader = threading.Thread(target=read_output, daemon=True, name=f"hermes-output-{workflow_id}")
        reader.start()
        try:
            while True:
                if time.monotonic() - started > timeout:
                    self.cancel(workflow_id)
                    raise TimeoutError(f"Hermes worker exceeded {timeout} seconds.")
                try:
                    line = lines.get(timeout=0.25)
                except queue.Empty:
                    if proc.poll() is not None and not reader.is_alive():
                        break
                    continue
                if line is None:
                    break
                encoded = line.encode("utf-8", errors="replace")
                total += len(encoded)
                if total > output_limit:
                    self.cancel(workflow_id)
                    raise RuntimeError("Hermes worker output exceeded the configured limit.")
                text = line.rstrip("\r\n")
                captured.append(text)
                try:
                    event = json.loads(text)
                except json.JSONDecodeError:
                    event = {"type": "log", "message": text[:2000]}
                if not isinstance(event, dict):
                    event = {"type": "log", "message": str(event)[:2000]}
                events.append(event)
                if on_event:
                    on_event(str(event.get("type", "log")), event)
            code = proc.wait(timeout=10)
            if code != 0:
                raise RuntimeError(f"Hermes worker exited with code {code}.")
            return {"ok": True, "exit_code": code, "events": events, "output": "\n".join(captured)[-100_000:]}
        finally:
            with self._lock:
                self._active.pop(workflow_id, None)

    def cancel(self, workflow_id: int) -> bool:
        with self._lock:
            proc = self._active.get(workflow_id)
        if not proc or proc.poll() is not None:
            return False
        try:
            if os.name == "nt":
                proc.send_signal(signal.CTRL_BREAK_EVENT)
                time.sleep(0.5)
            else:
                os.killpg(proc.pid, signal.SIGTERM)
                time.sleep(0.5)
        except Exception:
            pass
        if proc.poll() is None:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                               capture_output=True, timeout=10, creationflags=no_window())
            else:
                os.killpg(proc.pid, signal.SIGKILL)
        return True

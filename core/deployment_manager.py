"""Declared deployment pipeline with health verification and rollback evidence."""
from __future__ import annotations

import json
import subprocess
import urllib.request
from pathlib import Path
from typing import Any, Sequence

from core.coding_policy import CodingPolicy, PolicyDenied
from core.development_store import DevelopmentStore, utc_now


class DeploymentError(RuntimeError):
    pass


class DeploymentManager:
    def __init__(self, policy: CodingPolicy, store: DevelopmentStore) -> None:
        self.policy = policy
        self.store = store

    def configured(self) -> bool:
        cfg = self.policy.deployment()
        return bool(cfg.get("target_name") and cfg.get("checkout_path") and cfg.get("health_url"))

    def _run(self, argv: Sequence[str], cwd: Path) -> dict[str, Any]:
        from core.terminal_engine import redact
        self.policy.assert_command(argv, allow_network=True)
        result = subprocess.run(
            list(argv), cwd=str(cwd), capture_output=True, text=True,
            timeout=self.policy.limit("command_timeout_seconds", 900),
        )
        stdout = redact(result.stdout[-20_000:])
        stderr = redact(result.stderr[-20_000:])
        return {
            "argv": [redact(str(part)) for part in argv],
            "ok": result.returncode == 0,
            "exit_code": result.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "output": (stdout + stderr)[-20_000:],
        }

    @staticmethod
    def _health(url: str, expected_sha: str | None = None, *, require_revision: bool = False) -> dict[str, Any]:
        try:
            with urllib.request.urlopen(url, timeout=15) as response:
                body = response.read(100_000)
                payload: Any = None
                try:
                    payload = json.loads(body.decode("utf-8", errors="replace"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    payload = None
                revision = None
                if isinstance(payload, dict):
                    for key in ("revision", "commit_sha", "commit", "sha"):
                        if payload.get(key):
                            revision = str(payload[key])
                            break
                revision_ok = not expected_sha or bool(revision and (
                    revision == expected_sha or expected_sha.startswith(revision) or revision.startswith(expected_sha)
                ))
                ok = 200 <= response.status < 400 and (revision_ok if require_revision else True)
                return {"ok": ok, "status": response.status, "revision": revision,
                        "expected_revision": expected_sha if require_revision else None}
        except Exception as exc:
            return {"ok": False, "error": type(exc).__name__}

    def deploy(self, release_id: int, prior_sha: str, new_sha: str) -> dict[str, Any]:
        if not self.policy.feature_enabled("deploy"):
            raise PolicyDenied("Deployment capability is disabled by policy.")
        if not self.configured():
            raise DeploymentError("Deployment target is not fully declared in coding policy.")
        cfg = self.policy.deployment()
        checkout = Path(str(cfg["checkout_path"])).resolve()
        if not checkout.is_dir():
            raise DeploymentError("Declared deployment checkout does not exist.")
        default_branch = str(self.policy.data.get("repository", {}).get("default_branch", "main"))

        def require(result: dict[str, Any], message: str) -> dict[str, Any]:
            if not result["ok"]:
                raise DeploymentError(message)
            return result

        top = require(self._run(["git", "rev-parse", "--show-toplevel"], checkout),
                      "Deployment checkout is not a Git repository.")
        if Path(top["stdout"].strip()).resolve() != checkout:
            raise DeploymentError("Deployment checkout must be the configured repository root.")
        remote = require(self._run(["git", "remote", "get-url", "origin"], checkout),
                         "Deployment checkout has no origin remote.")
        self.policy.assert_remote(remote["stdout"].strip())
        dirty = require(self._run(["git", "status", "--porcelain"], checkout),
                        "Deployment checkout status could not be read.")
        if dirty["stdout"].strip():
            raise DeploymentError("Deployment checkout has uncommitted changes.")
        current = require(self._run(["git", "rev-parse", "HEAD"], checkout),
                          "Deployment checkout revision could not be read.")["stdout"].strip()
        if prior_sha and current != prior_sha:
            raise DeploymentError("Deployment checkout does not match the recorded known-good revision.")
        prior_sha = current
        created = utc_now()
        conn = self.store.connect()
        try:
            cur = conn.execute(
                """INSERT INTO deployments(release_id,target,prior_sha,new_sha,status,created_at)
                   VALUES (?,?,?,?,?,?)""",
                (release_id, str(cfg["target_name"]), prior_sha, new_sha, "deploying", created),
            )
            deployment_id = int(cur.lastrowid)
            conn.commit()
        finally:
            conn.close()
        stages: list[dict[str, Any]] = []
        applied = False
        require_revision = bool(cfg.get("require_health_revision", True))
        try:
            for name in ("preflight",):
                for argv in cfg.get(name, []):
                    result = self._run(argv, checkout)
                    result["stage"] = name
                    stages.append(result)
                    if not result["ok"]:
                        raise DeploymentError(f"Deployment {name} stage failed.")
            git_steps = [
                ["git", "fetch", "origin", default_branch],
                ["git", "merge-base", "--is-ancestor", new_sha, f"origin/{default_branch}"],
                ["git", "switch", default_branch],
                ["git", "merge", "--ff-only", new_sha],
            ]
            for argv in git_steps:
                result = self._run(argv, checkout)
                result["stage"] = "apply_revision"
                stages.append(result)
                require(result, f"Failed to apply exact deployment revision during: {' '.join(argv[1:3])}")
            applied_head = require(self._run(["git", "rev-parse", "HEAD"], checkout),
                                   "Applied deployment revision could not be verified.")
            applied_head["stage"] = "verify_revision"
            stages.append(applied_head)
            if applied_head["stdout"].strip() != new_sha:
                raise DeploymentError("Deployment checkout did not reach the exact merged revision.")
            applied = True
            for name in ("build", "restart"):
                for argv in cfg.get(name, []):
                    result = self._run(argv, checkout)
                    result["stage"] = name
                    stages.append(result)
                    if not result["ok"]:
                        raise DeploymentError(f"Deployment {name} stage failed.")
            health = self._health(str(cfg["health_url"]), new_sha, require_revision=require_revision)
            if not health["ok"]:
                raise DeploymentError("Deployment health check failed.")
            self._finish(deployment_id, "healthy", stages, health, None)
            return {"id": deployment_id, "status": "healthy", "stages": stages, "health": health}
        except Exception as exc:
            rollback: list[dict[str, Any]] = []
            if applied:
                switch = self._run(["git", "switch", "--detach", prior_sha], checkout)
                switch["stage"] = "rollback_revision"
                rollback.append(switch)
                if switch["ok"]:
                    for argv in cfg.get("rollback", []):
                        result = self._run(argv, checkout)
                        result["stage"] = "rollback"
                        rollback.append(result)
                        if not result["ok"]:
                            break
            rollback_health = self._health(
                str(cfg["health_url"]), prior_sha, require_revision=require_revision,
            ) if applied else {"ok": False, "error": "revision_not_applied"}
            status = "rolled_back" if applied and rollback and all(r["ok"] for r in rollback) and rollback_health["ok"] else "rollback_failed"
            self._finish(deployment_id, status, stages, {"ok": False, "error": str(exc)[:500]},
                         {"commands": rollback, "health": rollback_health})
            return {"id": deployment_id, "status": status, "stages": stages,
                    "health": {"ok": False, "error": str(exc)[:500]}, "rollback": rollback}

    def _finish(self, deployment_id: int, status: str, stages: list[dict[str, Any]],
                health: dict[str, Any], rollback: dict[str, Any] | None) -> None:
        conn = self.store.connect()
        try:
            conn.execute(
                """UPDATE deployments SET status=?,stages_json=?,health_json=?,rollback_json=?,completed_at=? WHERE id=?""",
                (status, json.dumps(stages), json.dumps(health), json.dumps(rollback) if rollback else None,
                 utc_now(), deployment_id),
            )
            conn.commit()
        finally:
            conn.close()

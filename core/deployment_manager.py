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
        return {"argv": [redact(str(part)) for part in argv], "ok": result.returncode == 0, "exit_code": result.returncode,
                "output": redact((result.stdout + result.stderr)[-20_000:])}

    @staticmethod
    def _health(url: str) -> dict[str, Any]:
        try:
            with urllib.request.urlopen(url, timeout=15) as response:
                return {"ok": 200 <= response.status < 400, "status": response.status}
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
        try:
            for name in ("preflight", "build", "restart"):
                for argv in cfg.get(name, []):
                    result = self._run(argv, checkout)
                    result["stage"] = name
                    stages.append(result)
                    if not result["ok"]:
                        raise DeploymentError(f"Deployment {name} stage failed.")
            health = self._health(str(cfg["health_url"]))
            if not health["ok"]:
                raise DeploymentError("Deployment health check failed.")
            self._finish(deployment_id, "healthy", stages, health, None)
            return {"id": deployment_id, "status": "healthy", "stages": stages, "health": health}
        except Exception as exc:
            rollback: list[dict[str, Any]] = []
            for argv in cfg.get("rollback", []):
                result = self._run(argv, checkout)
                result["stage"] = "rollback"
                rollback.append(result)
            rollback_health = self._health(str(cfg["health_url"]))
            status = "rolled_back" if rollback and all(r["ok"] for r in rollback) and rollback_health["ok"] else "rollback_failed"
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

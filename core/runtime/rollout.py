"""Durable shadow comparison, staged activation, and one-switch rollback."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from core import owner_flags
from core.database import get_connection
from core.runtime.evals import EvalRepository
from core.schema.runtime import _ensure_runtime_schema


ROLLOUT_STAGES = ("direct_chat", "read_chat", "actions", "agent")
_ROLLOUT_EVAL_SCOPES = {
    stage: (f"rollout:{stage}",) for stage in ROLLOUT_STAGES
}
REQUIRED_CONSECUTIVE_PASSES = 7
_TOKEN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.:@/-]{0,159}$")
_DIGEST = re.compile(r"^[a-f0-9]{64}$")
_OUTCOMES = frozenset({"succeeded", "failed", "waiting_owner", "cancelled"})


class RolloutConflictError(ValueError):
    """An immutable comparison identity was reused for different evidence."""


class RolloutNotReadyError(ValueError):
    """A stage or resume command does not have sufficient passing evidence."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _hash(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _require_token(value: str, field: str) -> str:
    if not isinstance(value, str) or not _TOKEN.fullmatch(value.strip()):
        raise ValueError(f"{field} is invalid")
    return value.strip()


@dataclass(frozen=True)
class RolloutObservation:
    route: str
    manifest_digest: str
    policy: str
    outcome: str
    latency_ms: int
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_token(self.route, "route")
        if not isinstance(self.manifest_digest, str) or not _DIGEST.fullmatch(self.manifest_digest):
            raise ValueError("manifest_digest must be a lowercase SHA-256 digest")
        _require_token(self.policy, "policy")
        if self.outcome not in _OUTCOMES:
            raise ValueError("outcome is invalid")
        if isinstance(self.latency_ms, bool) or not isinstance(self.latency_ms, int) or not 0 <= self.latency_ms <= 3_600_000:
            raise ValueError("latency_ms must be between 0 and 3600000")
        if not isinstance(self.evidence_refs, tuple) or not 1 <= len(self.evidence_refs) <= 50:
            raise ValueError("evidence_refs must contain between 1 and 50 references")
        for ref in self.evidence_refs:
            _require_token(ref, "evidence_ref")

    def to_dict(self) -> dict[str, Any]:
        return {
            "route": self.route,
            "manifest_digest": self.manifest_digest,
            "policy": self.policy,
            "outcome": self.outcome,
            "latency_ms": self.latency_ms,
            "evidence_refs": list(self.evidence_refs),
        }


@dataclass(frozen=True)
class RolloutDecision:
    stage: str
    allowed: bool
    consecutive_passes: int
    required_passes: int
    blockers: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "allowed": self.allowed,
            "consecutive_passes": self.consecutive_passes,
            "required_passes": self.required_passes,
            "blockers": list(self.blockers),
        }


def _row(row: Any) -> dict[str, Any]:
    result = dict(row)
    result["passed"] = bool(result["passed"])
    result["reasons"] = json.loads(result.pop("reasons_json"))
    result["evidence_refs"] = json.loads(result.pop("evidence_refs_json"))
    result.pop("input_hash", None)
    return result


class RolloutController:
    def compare(
        self,
        comparison_id: str,
        stage: str,
        legacy: RolloutObservation,
        runtime: RolloutObservation,
        *,
        actor: str = "local-eval",
    ) -> dict[str, Any]:
        comparison_id = _require_token(comparison_id, "comparison_id")
        actor = _require_token(actor, "actor")
        if stage not in ROLLOUT_STAGES:
            raise ValueError("unknown rollout stage")
        if not isinstance(legacy, RolloutObservation) or not isinstance(runtime, RolloutObservation):
            raise ValueError("legacy and runtime observations are required")
        reasons: list[str] = []
        for field in ("route", "manifest_digest", "policy", "outcome"):
            if getattr(legacy, field) != getattr(runtime, field):
                reasons.append(f"{field}_mismatch")
        latency_limit = int(legacy.latency_ms * 1.25) + 250
        if runtime.latency_ms > latency_limit:
            reasons.append("latency_regression")
        evidence_refs = sorted(set(legacy.evidence_refs + runtime.evidence_refs))[:50]
        identity = {
            "comparison_id": comparison_id,
            "stage": stage,
            "legacy": legacy.to_dict(),
            "runtime": runtime.to_dict(),
            "actor": actor,
        }
        input_hash = _hash(identity)
        conn = get_connection()
        try:
            _ensure_runtime_schema(conn)
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT * FROM mc_rollout_comparisons WHERE comparison_id=?", (comparison_id,)
            ).fetchone()
            if existing is not None:
                if existing["input_hash"] != input_hash:
                    raise RolloutConflictError("comparison id already has different evidence")
                conn.commit()
                return _row(existing)
            sequence = conn.execute(
                "SELECT COALESCE(MAX(sequence),0)+1 FROM mc_rollout_comparisons WHERE stage=?",
                (stage,),
            ).fetchone()[0]
            conn.execute(
                """INSERT INTO mc_rollout_comparisons (
                    comparison_id,stage,sequence,legacy_route,runtime_route,
                    legacy_manifest_hash,runtime_manifest_hash,legacy_policy,runtime_policy,
                    legacy_outcome,runtime_outcome,legacy_latency_ms,runtime_latency_ms,
                    passed,reasons_json,evidence_refs_json,input_hash,actor,created_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    comparison_id, stage, sequence, legacy.route, runtime.route,
                    legacy.manifest_digest, runtime.manifest_digest, legacy.policy, runtime.policy,
                    legacy.outcome, runtime.outcome, legacy.latency_ms, runtime.latency_ms,
                    int(not reasons), _json(reasons), _json(evidence_refs), input_hash, actor, _now(),
                ),
            )
            row = conn.execute(
                "SELECT * FROM mc_rollout_comparisons WHERE comparison_id=?", (comparison_id,)
            ).fetchone()
            conn.commit()
            return _row(row)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def decision(self, stage: str, *, now: str | None = None) -> RolloutDecision:
        if stage not in ROLLOUT_STAGES:
            raise ValueError("unknown rollout stage")
        conn = get_connection()
        try:
            _ensure_runtime_schema(conn)
            rows = conn.execute(
                "SELECT passed FROM mc_rollout_comparisons WHERE stage=? ORDER BY sequence DESC LIMIT ?",
                (stage, REQUIRED_CONSECUTIVE_PASSES),
            ).fetchall()
        finally:
            conn.close()
        consecutive = 0
        for row in rows:
            if not bool(row["passed"]):
                break
            consecutive += 1
        blockers: list[str] = []
        if consecutive < REQUIRED_CONSECUTIVE_PASSES:
            blockers.append(f"comparison-streak:{consecutive}/{REQUIRED_CONSECUTIVE_PASSES}")
        release = EvalRepository().gate(
            "release", capability_refs=_ROLLOUT_EVAL_SCOPES[stage], now=now,
        )
        if not release.allowed:
            blockers.extend(f"release-eval:{blocker}" for blocker in release.blockers)
        if stage == "agent":
            autonomy = EvalRepository().gate(
                "autonomy", capability_refs=_ROLLOUT_EVAL_SCOPES[stage], now=now,
            )
            if not autonomy.allowed:
                blockers.extend(f"autonomy-eval:{blocker}" for blocker in autonomy.blockers)
        return RolloutDecision(
            stage=stage,
            allowed=not blockers,
            consecutive_passes=consecutive,
            required_passes=REQUIRED_CONSECUTIVE_PASSES,
            blockers=tuple(blockers),
        )

    @staticmethod
    def _stored_stage() -> str:
        stage = owner_flags.get_str(owner_flags.RUNTIME_V2_ROLLOUT_STAGE, "shadow")
        return stage if stage in ROLLOUT_STAGES else "shadow"

    @staticmethod
    def _write_controls(values: dict[str, str]) -> None:
        conn = get_connection()
        try:
            owner_flags.ensure_schema(conn)
            conn.execute("BEGIN IMMEDIATE")
            for key, value in values.items():
                conn.execute(
                    """INSERT INTO owner_settings (key,value,updated_at)
                       VALUES (?,?,CURRENT_TIMESTAMP)
                       ON CONFLICT(key) DO UPDATE SET
                         value=excluded.value,updated_at=CURRENT_TIMESTAMP""",
                    (key, value),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def activate(self, stage: str, *, actor: str = "owner") -> dict[str, Any]:
        _require_token(actor, "actor")
        if stage not in ROLLOUT_STAGES:
            raise ValueError("unknown rollout stage")
        current = self._stored_stage()
        current_index = ROLLOUT_STAGES.index(current) if current in ROLLOUT_STAGES else -1
        target_index = ROLLOUT_STAGES.index(stage)
        if target_index != current_index + 1:
            raise ValueError("rollout stages must advance exactly one step")
        decision = self.decision(stage)
        if not decision.allowed:
            raise RolloutNotReadyError("rollout stage is blocked: " + ", ".join(decision.blockers))
        values = {
            owner_flags.RUNTIME_V2_ROLLOUT_STAGE: stage,
            owner_flags.RUNTIME_V2_ROLLBACK: "0",
            owner_flags.RUNTIME_V2_EVENTS: "1",
            owner_flags.RUNTIME_V2_EXECUTION: "1",
            owner_flags.RUNTIME_V2_UI: "1",
        }
        if target_index >= 0:
            values[owner_flags.RUNTIME_V2_CHAT_EXECUTION] = "1"
        if target_index >= 1:
            values[owner_flags.RUNTIME_V2_CONTEXT] = "1"
        if target_index >= 2:
            values[owner_flags.RUNTIME_V2_TOOLS] = "1"
            values[owner_flags.RUNTIME_V2_POLICY] = "1"
        if target_index >= 3:
            values[owner_flags.RUNTIME_V2_AGENT_EXECUTION] = "1"
        self._write_controls(values)
        return self.status()

    def rollback(self, *, actor: str = "owner") -> dict[str, Any]:
        _require_token(actor, "actor")
        self._write_controls({owner_flags.RUNTIME_V2_ROLLBACK: "1"})
        return self.status()

    def resume(self, *, actor: str = "owner") -> dict[str, Any]:
        _require_token(actor, "actor")
        stage = self._stored_stage()
        if stage == "shadow":
            raise RolloutNotReadyError("no activated rollout stage can resume")
        decision = self.decision(stage)
        if not decision.allowed:
            raise RolloutNotReadyError("rollout resume is blocked: " + ", ".join(decision.blockers))
        self._write_controls({owner_flags.RUNTIME_V2_ROLLBACK: "0"})
        return self.status()

    def status(self) -> dict[str, Any]:
        return {
            "stage": self._stored_stage(),
            "rollback": owner_flags.get_bool(owner_flags.RUNTIME_V2_ROLLBACK, False),
            "decisions": {stage: self.decision(stage).to_dict() for stage in ROLLOUT_STAGES},
        }

"""Canonical durable run repository for Mission Control Runtime V2."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from core.database import get_connection
from core.runtime.contracts import (
    ExecutionPlan,
    LoopPolicy,
    LoopRecipe,
    RunRequest,
    contract_to_dict,
)
from core.runtime.event_store import _append_run_event, redact_payload
from core.runtime.state import (
    RunStateError,
    RunStatus,
    TERMINAL_STATUSES,
    as_run_status,
    require_transition,
)
from core.schema.runtime import _ensure_runtime_schema


class RunConflictError(ValueError):
    """A stable request or recipe identity was reused for different content."""


class VersionConflictError(ValueError):
    """A writer used an out-of-date run version."""


class RunNotFoundError(KeyError):
    """The requested canonical run does not exist."""


class PlanValidationError(ValueError):
    """An execution plan has invalid identities or dependencies."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), default=str)


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _load_json(value: Any, fallback: Any) -> Any:
    try:
        return json.loads(value) if value else fallback
    except (TypeError, json.JSONDecodeError):
        return fallback


def _validate_plan_graph(plan: ExecutionPlan) -> None:
    step_ids = [step.step_id for step in plan.steps]
    if len(step_ids) != len(set(step_ids)):
        raise PlanValidationError("plan step IDs must be unique")
    known = set(step_ids)
    dependencies = {step.step_id: set(step.depends_on) for step in plan.steps}
    for step_id, required in dependencies.items():
        missing = required - known
        if missing:
            raise PlanValidationError(
                f"step {step_id!r} depends on missing steps: {sorted(missing)!r}"
            )
        if step_id in required:
            raise PlanValidationError(f"step {step_id!r} cannot depend on itself")

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(step_id: str) -> None:
        if step_id in visiting:
            raise PlanValidationError("plan dependencies contain a cycle")
        if step_id in visited:
            return
        visiting.add(step_id)
        for dependency in dependencies[step_id]:
            visit(dependency)
        visiting.remove(step_id)
        visited.add(step_id)

    for step_id in step_ids:
        visit(step_id)


class RuntimeRepository:
    """Persist canonical runs without activating any live runtime surface."""

    @staticmethod
    def _run_from_conn(conn: sqlite3.Connection, run_id: str) -> dict[str, Any] | None:
        row = conn.execute("SELECT * FROM mc_runs WHERE run_id=?", (run_id,)).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["request"] = _load_json(result.pop("request_json"), {})
        result["budget"] = _load_json(result.pop("budget_json"), {})
        loop = conn.execute("SELECT * FROM mc_loop_runs WHERE run_id=?", (run_id,)).fetchone()
        if loop is not None:
            loop_result = dict(loop)
            loop_result["policy"] = _load_json(loop_result.pop("policy_json"), {})
            loop_result["owner_override"] = _load_json(
                loop_result.pop("owner_override_json"), {}
            )
            loop_result["enabled"] = bool(loop_result["enabled"])
            result["loop"] = loop_result
        else:
            result["loop"] = None
        return result

    def save_loop_recipe(self, recipe: LoopRecipe, *, created_at: str | None = None) -> dict[str, Any]:
        if not isinstance(recipe, LoopRecipe):
            raise ValueError("recipe must be a validated LoopRecipe")
        contract = contract_to_dict(recipe)
        stored_contract = redact_payload(contract)
        contract_json = _canonical_json(stored_contract)
        contract_hash = _hash(contract)
        created_at = created_at or _now()
        conn = get_connection()
        try:
            _ensure_runtime_schema(conn)
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT * FROM mc_loop_recipes WHERE recipe_id=? AND version=?",
                (recipe.recipe_id, recipe.version),
            ).fetchone()
            if existing is not None:
                if existing["contract_hash"] != contract_hash:
                    raise RunConflictError(
                        f"loop recipe {recipe.recipe_id!r}@{recipe.version} already differs"
                    )
                conn.commit()
                result = dict(existing)
                result["contract"] = _load_json(result.pop("contract_json"), {})
                return result
            conn.execute(
                """INSERT INTO mc_loop_recipes
                   (recipe_id,version,name,loop_type,contract_json,contract_hash,created_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (
                    recipe.recipe_id,
                    recipe.version,
                    stored_contract["name"],
                    recipe.loop_type.value,
                    contract_json,
                    contract_hash,
                    created_at,
                ),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM mc_loop_recipes WHERE recipe_id=? AND version=?",
                (recipe.recipe_id, recipe.version),
            ).fetchone()
            result = dict(row)
            result["contract"] = _load_json(result.pop("contract_json"), {})
            return result
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def create_run(
        self,
        request: RunRequest,
        *,
        loop_policy: LoopPolicy,
        run_id: str | None = None,
        actor: str = "owner",
        event_id: str | None = None,
        timestamp: str | None = None,
    ) -> dict[str, Any]:
        if not isinstance(request, RunRequest):
            raise ValueError("request must be a validated RunRequest")
        if not isinstance(loop_policy, LoopPolicy):
            raise ValueError("loop_policy must be a validated LoopPolicy")
        request_contract = contract_to_dict(request)
        request_hash = _hash(request_contract)
        stored_request = redact_payload(request_contract)
        request_json = _canonical_json(stored_request)
        policy_contract = contract_to_dict(loop_policy)
        stored_policy = redact_payload(policy_contract)
        policy_json = _canonical_json(stored_policy)
        policy_hash = _hash(policy_contract)
        timestamp = timestamp or _now()
        conn = get_connection()
        try:
            _ensure_runtime_schema(conn)
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT * FROM mc_runs WHERE request_id=?", (request.request_id,)
            ).fetchone()
            if existing is not None:
                loop = conn.execute(
                    "SELECT policy_hash FROM mc_loop_runs WHERE run_id=?",
                    (existing["run_id"],),
                ).fetchone()
                same_identity = existing["request_hash"] == request_hash
                same_policy = loop is not None and loop["policy_hash"] == policy_hash
                same_run = run_id is None or run_id == existing["run_id"]
                if not (same_identity and same_policy and same_run):
                    raise RunConflictError(
                        f"request_id {request.request_id!r} already has different content"
                    )
                conn.commit()
                return self._run_from_conn(conn, existing["run_id"]) or {}

            recipe_row = conn.execute(
                "SELECT 1 FROM mc_loop_recipes WHERE recipe_id=? AND version=?",
                (loop_policy.recipe_id, loop_policy.recipe_version),
            ).fetchone()
            if recipe_row is None:
                raise RunConflictError(
                    "the loop policy references a recipe version that is not persisted"
                )
            run_id = run_id or str(uuid.uuid4())
            objective = stored_request["message"].strip() or "Owner request"
            conn.execute(
                """INSERT INTO mc_runs (
                    run_id,request_id,request_hash,request_json,owner_id,session_id,
                    surface,mode,objective,status,version,budget_profile,budget_json,
                    contract_version,created_at,updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,'accepted',1,?,?,?,?,?)""",
                (
                    run_id,
                    request.request_id,
                    request_hash,
                    request_json,
                    stored_request["owner_id"],
                    stored_request["session_id"],
                    stored_request["surface"],
                    stored_request["mode"],
                    objective,
                    stored_request["budget_profile"],
                    _canonical_json({}),
                    request.contract_version,
                    timestamp,
                    timestamp,
                ),
            )
            conn.execute(
                """INSERT INTO mc_loop_runs (
                    run_id,recipe_id,recipe_version,policy_id,policy_version,
                    policy_decision_id,loop_type,policy_json,policy_hash,
                    owner_override_json,enabled,iteration,status,created_at,updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,0,'accepted',?,?)""",
                (
                    run_id,
                    loop_policy.recipe_id,
                    loop_policy.recipe_version,
                    loop_policy.policy_id,
                    loop_policy.version,
                    loop_policy.policy_decision_id,
                    loop_policy.loop_type.value,
                    policy_json,
                    policy_hash,
                    _canonical_json(stored_policy["owner_override"]),
                    int(loop_policy.enabled),
                    timestamp,
                    timestamp,
                ),
            )
            _append_run_event(
                conn,
                run_id=run_id,
                event_type="run.accepted",
                stage="accept",
                actor=actor,
                payload={
                    "objective": objective,
                    "status": RunStatus.ACCEPTED.value,
                    "surface": request.surface.value,
                    "mode": request.mode,
                    "loop_policy_id": loop_policy.policy_id,
                },
                event_id=event_id or f"{run_id}:accepted",
                timestamp=timestamp,
                contract_version=request.contract_version,
            )
            conn.commit()
            return self._run_from_conn(conn, run_id) or {}
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        conn = get_connection()
        try:
            _ensure_runtime_schema(conn)
            return self._run_from_conn(conn, run_id)
        finally:
            conn.close()

    def list_steps(self, run_id: str) -> list[dict[str, Any]]:
        conn = get_connection()
        try:
            _ensure_runtime_schema(conn)
            rows = conn.execute(
                "SELECT * FROM mc_run_steps WHERE run_id=? ORDER BY position", (run_id,)
            ).fetchall()
            result = []
            for row in rows:
                step = dict(row)
                step["arguments"] = _load_json(step.pop("arguments_json"), {})
                step["depends_on"] = _load_json(step.pop("depends_on_json"), [])
                step["required_capabilities"] = _load_json(
                    step.pop("required_capabilities_json"), []
                )
                step["output_contract"] = _load_json(
                    step.pop("output_contract_json"), {}
                )
                result.append(step)
            return result
        finally:
            conn.close()

    def save_plan(
        self,
        plan: ExecutionPlan,
        *,
        expected_version: int,
        actor: str,
        event_id: str | None = None,
        timestamp: str | None = None,
    ) -> dict[str, Any]:
        if not isinstance(plan, ExecutionPlan):
            raise ValueError("plan must be a validated ExecutionPlan")
        _validate_plan_graph(plan)
        plan_contract = contract_to_dict(plan)
        stored_plan = redact_payload(plan_contract)
        plan_hash = _hash(plan_contract)
        timestamp = timestamp or _now()
        conn = get_connection()
        try:
            _ensure_runtime_schema(conn)
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM mc_runs WHERE run_id=?", (plan.run_id,)).fetchone()
            if row is None:
                raise RunNotFoundError(plan.run_id)
            if row["plan_hash"] == plan_hash:
                conn.commit()
                return self._run_from_conn(conn, plan.run_id) or {}
            if row["plan_hash"] is not None:
                raise RunConflictError("this run already has a different persisted plan")
            if row["version"] != expected_version:
                raise VersionConflictError(
                    f"run version is {row['version']}, not {expected_version}"
                )
            require_transition(row["status"], RunStatus.PLANNED)
            for position, step in enumerate(plan.steps):
                stored_step = stored_plan["steps"][position]
                conn.execute(
                    """INSERT INTO mc_run_steps (
                        run_id,step_id,plan_version,position,kind,tool_name,
                        arguments_json,depends_on_json,risk,timeout_s,retry_policy,
                        idempotency_key,required_capabilities_json,output_contract_json,
                        status,attempts,created_at,updated_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,'pending',0,?,?)""",
                    (
                        plan.run_id,
                        step.step_id,
                        plan.version,
                        position,
                        stored_step["kind"],
                        stored_step["tool_name"],
                        _canonical_json(stored_step["arguments"]),
                        _canonical_json(stored_step["depends_on"]),
                        step.risk.value,
                        step.timeout_s,
                        stored_step["retry_policy"],
                        stored_step["idempotency_key"],
                        _canonical_json([item.value for item in step.required_capabilities]),
                        _canonical_json(stored_step["output_contract"]),
                        timestamp,
                        timestamp,
                    ),
                )
            updated = conn.execute(
                """UPDATE mc_runs
                   SET objective=?,status='planned',version=version+1,plan_id=?,
                       plan_version=?,plan_hash=?,budget_json=?,updated_at=?
                   WHERE run_id=? AND version=? AND status=?""",
                (
                    stored_plan["objective"],
                    plan.plan_id,
                    plan.version,
                    plan_hash,
                    _canonical_json(stored_plan["budget"]),
                    timestamp,
                    plan.run_id,
                    expected_version,
                    row["status"],
                ),
            )
            if updated.rowcount != 1:
                raise VersionConflictError("run changed while the plan was being persisted")
            _append_run_event(
                conn,
                run_id=plan.run_id,
                event_type="run.planned",
                stage="plan",
                actor=actor,
                payload={
                    "objective": plan.objective,
                    "status": RunStatus.PLANNED.value,
                    "current_step": plan.steps[0].step_id if plan.steps else None,
                    "plan_id": plan.plan_id,
                    "plan_version": plan.version,
                    "step_count": len(plan.steps),
                },
                event_id=event_id or f"{plan.run_id}:planned:{plan.version}",
                timestamp=timestamp,
            )
            conn.execute(
                "UPDATE mc_loop_runs SET status='planned',updated_at=? WHERE run_id=?",
                (timestamp, plan.run_id),
            )
            conn.commit()
            return self._run_from_conn(conn, plan.run_id) or {}
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def transition_run(
        self,
        run_id: str,
        target_status: RunStatus | str,
        *,
        expected_version: int,
        actor: str,
        event_id: str | None = None,
        timestamp: str | None = None,
    ) -> dict[str, Any]:
        target = as_run_status(target_status)
        if not isinstance(expected_version, int) or expected_version <= 0:
            raise ValueError("expected_version must be a positive integer")
        timestamp = timestamp or _now()
        conn = get_connection()
        try:
            _ensure_runtime_schema(conn)
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM mc_runs WHERE run_id=?", (run_id,)).fetchone()
            if row is None:
                raise RunNotFoundError(run_id)
            if row["version"] != expected_version:
                raise VersionConflictError(
                    f"run version is {row['version']}, not {expected_version}"
                )
            require_transition(row["status"], target)
            if target == RunStatus.RUNNING:
                loop = conn.execute(
                    "SELECT enabled FROM mc_loop_runs WHERE run_id=?", (run_id,)
                ).fetchone()
                if loop is None or not bool(loop["enabled"]):
                    raise RunStateError("a disabled loop policy cannot enter running")
            new_version = expected_version + 1
            completed_at = timestamp if target in TERMINAL_STATUSES else None
            updated = conn.execute(
                """UPDATE mc_runs
                   SET status=?,version=?,updated_at=?,completed_at=?
                   WHERE run_id=? AND version=? AND status=?""",
                (
                    target.value,
                    new_version,
                    timestamp,
                    completed_at,
                    run_id,
                    expected_version,
                    row["status"],
                ),
            )
            if updated.rowcount != 1:
                raise VersionConflictError("run changed during transition")
            conn.execute(
                "UPDATE mc_loop_runs SET status=?,updated_at=? WHERE run_id=?",
                (target.value, timestamp, run_id),
            )
            _append_run_event(
                conn,
                run_id=run_id,
                event_type=f"run.{target.value}",
                stage=target.value,
                actor=actor,
                payload={
                    "status": target.value,
                    "owner_attention": target
                    in {RunStatus.WAITING_APPROVAL, RunStatus.WAITING_OWNER},
                },
                event_id=event_id or f"{run_id}:{target.value}:{new_version}",
                timestamp=timestamp,
            )
            conn.commit()
            return self._run_from_conn(conn, run_id) or {}
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

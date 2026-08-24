"""Local-first TOBIval persistence and fail-closed activation gates."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from core.database import get_connection
from core.runtime.contracts import EvalCase, EvalFinding, EvalRun, EvalStatus, contract_to_dict
from core.schema.runtime import _ensure_runtime_schema


class EvalConflictError(ValueError):
    """An immutable evaluation identity was reused for different content."""


@dataclass(frozen=True)
class EvalGateDecision:
    scope: str
    allowed: bool
    required_cases: tuple[str, ...]
    passed_cases: tuple[str, ...]
    blockers: tuple[str, ...]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _hash(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _run_refs(run: EvalRun) -> tuple[str, ...]:
    refs = set(run.tool_call_refs)
    refs.update(run.policy_decision_refs)
    refs.update(run.receipt_refs)
    refs.update(run.artifact_refs)
    refs.update(run.finding_refs)
    if run.context_manifest_ref:
        refs.add(run.context_manifest_ref)
    return tuple(sorted(refs))


def _case_dict(row: Any) -> dict[str, Any]:
    result = dict(row)
    result["required_evidence"] = json.loads(result.pop("required_evidence_json"))
    result["release_gate"] = bool(result["release_gate"])
    result["autonomy_gate"] = bool(result["autonomy_gate"])
    return result


def _run_dict(row: Any) -> dict[str, Any]:
    result = dict(row)
    result["evidence_refs"] = json.loads(result.pop("evidence_refs_json"))
    return result


def _finding_dict(row: Any) -> dict[str, Any]:
    result = dict(row)
    result["evidence_refs"] = json.loads(result.pop("evidence_refs_json"))
    return result


def default_eval_cases() -> tuple[EvalCase, ...]:
    definitions = (
        ("final-answer", "final_answer", "final_answer", False),
        ("tool-trajectory", "tool_trajectory", "tool_call", False),
        ("policy", "policy", "policy_decision", True),
        ("recovery", "recovery", "recovery", True),
        ("brain-context", "brain_context", "context_manifest", False),
        ("hallucination", "hallucination", "ground_truth", True),
        ("connector-freshness", "connector_freshness", "freshness", False),
        ("coding-workflow", "coding_workflow", "coding_evidence", True),
    )
    return tuple(EvalCase(
        eval_case_id=f"tobival.{slug}",
        version="1",
        category=category,
        objective=f"Verify {category.replace('_', ' ')} behavior",
        input_fixture={"fixture_ref": f"golden:{slug}:1"},
        expected_behavior="Required evidence meets the deterministic threshold",
        required_evidence=(evidence,),
        scorer="evidence_ratio",
        threshold=1.0,
        release_gate=True,
        autonomy_gate=autonomy,
    ) for slug, category, evidence, autonomy in definitions)


class EvalRepository:
    def save_case(self, case: EvalCase) -> dict[str, Any]:
        if not isinstance(case, EvalCase):
            raise ValueError("case must be a validated EvalCase")
        contract = contract_to_dict(case)
        contract_hash = _hash(contract)
        conn = get_connection()
        try:
            _ensure_runtime_schema(conn)
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT * FROM mc_eval_cases WHERE eval_case_id=? AND version=?",
                (case.eval_case_id, case.version),
            ).fetchone()
            if existing is not None:
                if existing["contract_hash"] != contract_hash:
                    raise EvalConflictError("evaluation case version already has different content")
                conn.commit()
                return _case_dict(existing)
            conn.execute(
                """INSERT INTO mc_eval_cases (
                    eval_case_id,version,category,objective,expected_behavior,
                    required_evidence_json,scorer,threshold,release_gate,autonomy_gate,
                    fixture_hash,contract_hash,created_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    case.eval_case_id, case.version, case.category, case.objective,
                    case.expected_behavior, _json(list(case.required_evidence)), case.scorer,
                    case.threshold, int(case.release_gate), int(case.autonomy_gate),
                    _hash(case.input_fixture), contract_hash, _now(),
                ),
            )
            row = conn.execute(
                "SELECT * FROM mc_eval_cases WHERE eval_case_id=? AND version=?",
                (case.eval_case_id, case.version),
            ).fetchone()
            conn.commit()
            return _case_dict(row)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def ensure_default_cases(self) -> list[dict[str, Any]]:
        return [self.save_case(case) for case in default_eval_cases()]

    def list_cases(self) -> list[dict[str, Any]]:
        conn = get_connection()
        try:
            _ensure_runtime_schema(conn)
            rows = conn.execute(
                "SELECT * FROM mc_eval_cases ORDER BY category,eval_case_id,version"
            ).fetchall()
            return [_case_dict(row) for row in rows]
        finally:
            conn.close()

    def list_runs(
        self,
        *,
        eval_case_id: str | None = None,
        eval_case_version: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        parameters: list[str] = []
        if eval_case_id is not None:
            clauses.append("eval_case_id=?")
            parameters.append(eval_case_id)
        if eval_case_version is not None:
            clauses.append("eval_case_version=?")
            parameters.append(eval_case_version)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        conn = get_connection()
        try:
            _ensure_runtime_schema(conn)
            rows = conn.execute(
                "SELECT * FROM mc_eval_runs" + where
                + " ORDER BY COALESCE(completed_at,started_at,created_at) DESC,rowid DESC",
                tuple(parameters),
            ).fetchall()
            return [_run_dict(row) for row in rows]
        finally:
            conn.close()

    def list_findings(self, *, eval_run_id: str | None = None) -> list[dict[str, Any]]:
        where = " WHERE eval_run_id=?" if eval_run_id is not None else ""
        parameters = (eval_run_id,) if eval_run_id is not None else ()
        conn = get_connection()
        try:
            _ensure_runtime_schema(conn)
            rows = conn.execute(
                "SELECT * FROM mc_eval_findings" + where + " ORDER BY created_at,finding_id",
                parameters,
            ).fetchall()
            return [_finding_dict(row) for row in rows]
        finally:
            conn.close()

    def record_run(self, run: EvalRun) -> dict[str, Any]:
        if not isinstance(run, EvalRun):
            raise ValueError("run must be a validated EvalRun")
        contract = contract_to_dict(run)
        contract_hash = _hash(contract)
        refs = _run_refs(run)
        conn = get_connection()
        try:
            _ensure_runtime_schema(conn)
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT * FROM mc_eval_runs WHERE eval_run_id=?", (run.eval_run_id,)
            ).fetchone()
            if existing is not None:
                if existing["contract_hash"] != contract_hash:
                    raise EvalConflictError("evaluation run id already has different content")
                conn.commit()
                return _run_dict(existing)
            case = conn.execute(
                "SELECT 1 FROM mc_eval_cases WHERE eval_case_id=? AND version=?",
                (run.eval_case_id, run.eval_case_version),
            ).fetchone()
            if case is None:
                raise KeyError(f"unknown evaluation case {run.eval_case_id}@{run.eval_case_version}")
            conn.execute(
                """INSERT INTO mc_eval_runs (
                    eval_run_id,eval_case_id,eval_case_version,status,threshold,score,
                    run_id,trace_id,evidence_refs_json,contract_hash,started_at,completed_at,created_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    run.eval_run_id, run.eval_case_id, run.eval_case_version, run.status.value,
                    run.threshold, run.score, run.run_id, run.trace_id, _json(list(refs)),
                    contract_hash, run.started_at, run.completed_at, _now(),
                ),
            )
            row = conn.execute(
                "SELECT * FROM mc_eval_runs WHERE eval_run_id=?", (run.eval_run_id,)
            ).fetchone()
            conn.commit()
            return _run_dict(row)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def record_finding(self, finding: EvalFinding) -> dict[str, Any]:
        if not isinstance(finding, EvalFinding):
            raise ValueError("finding must be a validated EvalFinding")
        contract = contract_to_dict(finding)
        contract_hash = _hash(contract)
        conn = get_connection()
        try:
            _ensure_runtime_schema(conn)
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT * FROM mc_eval_findings WHERE finding_id=?", (finding.finding_id,)
            ).fetchone()
            if existing is not None:
                if existing["contract_hash"] != contract_hash:
                    raise EvalConflictError("evaluation finding id already has different content")
                conn.commit()
                return _finding_dict(existing)
            conn.execute(
                """INSERT INTO mc_eval_findings (
                    finding_id,eval_run_id,category,severity,summary,remediation_owner,
                    status,defect_ref,evidence_refs_json,contract_hash,created_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    finding.finding_id, finding.eval_run_id, finding.category,
                    finding.severity.value, finding.summary[:240], finding.remediation_owner,
                    finding.status, finding.defect_ref, _json(list(finding.evidence_refs)),
                    contract_hash, _now(),
                ),
            )
            row = conn.execute(
                "SELECT * FROM mc_eval_findings WHERE finding_id=?", (finding.finding_id,)
            ).fetchone()
            conn.commit()
            return _finding_dict(row)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def gate(self, scope: str) -> EvalGateDecision:
        if scope not in {"release", "autonomy"}:
            raise ValueError("scope must be release or autonomy")
        column = "release_gate" if scope == "release" else "autonomy_gate"
        conn = get_connection()
        try:
            _ensure_runtime_schema(conn)
            cases = conn.execute(
                f"SELECT * FROM mc_eval_cases WHERE {column}=1 ORDER BY eval_case_id,version"
            ).fetchall()
            blockers: list[str] = []
            passed: list[str] = []
            required: list[str] = []
            for case in cases:
                ref = f"{case['eval_case_id']}@{case['version']}"
                required.append(ref)
                latest = conn.execute(
                    """SELECT * FROM mc_eval_runs
                       WHERE eval_case_id=? AND eval_case_version=?
                       ORDER BY COALESCE(completed_at,started_at,created_at) DESC,rowid DESC LIMIT 1""",
                    (case["eval_case_id"], case["version"]),
                ).fetchone()
                if latest is None:
                    blockers.append(f"missing:{ref}")
                    continue
                refs = set(json.loads(latest["evidence_refs_json"]))
                required_evidence = json.loads(case["required_evidence_json"])
                missing = [
                    name for name in required_evidence
                    if not any(value == name or value.startswith(f"{name}:") for value in refs)
                ]
                unsafe = conn.execute(
                    """SELECT 1 FROM mc_eval_findings
                       WHERE eval_run_id=? AND severity IN ('high','critical')
                         AND status NOT IN ('resolved','accepted') LIMIT 1""",
                    (latest["eval_run_id"],),
                ).fetchone()
                if (
                    latest["status"] != EvalStatus.PASSED.value
                    or latest["score"] is None
                    or float(latest["score"]) < float(case["threshold"])
                    or missing
                    or unsafe is not None
                ):
                    blockers.append(f"failed:{ref}")
                else:
                    passed.append(ref)
            if not cases:
                blockers.append("no-required-cases")
            return EvalGateDecision(
                scope=scope,
                allowed=not blockers,
                required_cases=tuple(required),
                passed_cases=tuple(passed),
                blockers=tuple(blockers),
            )
        finally:
            conn.close()

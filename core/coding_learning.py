"""Evidence-backed coding outcomes, replay evaluation, and safe playbooks."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from core.development_store import utc_now


SAFE_PLAYBOOK_KINDS = {"prompt", "routing", "repair"}
FAILURE_OUTCOMES = {"paused", "blocked", "failed"}
SUCCESS_OUTCOMES = {"completed", "merged", "locally_complete", "qualified_local"}


def failure_signature(stage: str, error_code: str, worker_profile: str) -> str:
    source = f"{stage}|{error_code}|{worker_profile}".lower()
    return hashlib.sha256(source.encode("utf-8")).hexdigest()[:20]


def failure_detail_signature(stage: str, error_code: str, detail: str) -> str:
    """Stable fingerprint for one concrete failure, without run-specific noise."""
    normalized = str(detail or "").lower().replace("\\", "/")
    normalized = re.sub(r"[a-z]:/[^ \n\r\t:]+/worktrees/[^ \n\r\t:]+", "<worktree>", normalized)
    normalized = re.sub(r"\b[0-9a-f]{8,64}\b", "<sha>", normalized)
    normalized = re.sub(r"\b\d{1,2}:\d{2}:\d{2}\b", "<time>", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    source = f"{stage}|{error_code}|{normalized[:6000]}"
    return hashlib.sha256(source.encode("utf-8")).hexdigest()[:24]


def _evidence(value: dict[str, Any]) -> dict[str, Any]:
    try:
        parsed = json.loads(value.get("evidence_json") or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _repair_instructions(error_code: str) -> list[str]:
    if error_code == "validation_infrastructure_failed":
        return [
            "Verify the current Mission Control validator before assigning a coding worker.",
            "Treat missing runtimes, dependencies, or a broken baseline as infrastructure work.",
            "Do not spend a model correction cycle until the control-plane check is healthy.",
        ]
    if error_code in {"validation_failed", "review_cycles_exhausted"}:
        return [
            "Compare the failed check fingerprint with prior attempts before retrying.",
            "If the fingerprint already occurred, preserve the checkpoint and revise the route.",
            "Run the narrow failing check before repeating the full validation suite.",
        ]
    if error_code == "quality_gate_failed":
        return [
            "Use content-authoritative Git diff evidence before counting changed subsystems.",
            "Remove unrelated changes before rerunning review.",
            "Preserve the accepted task change and rerun only the failed quality gate.",
        ]
    return [
        "Preserve the current worktree, action receipts, and latest valid checkpoint.",
        "Compare the concrete failure fingerprint before retrying.",
        "Retry once only; switch route or request owner action if the same fingerprint returns.",
    ]


class CodingLearningService:
    def __init__(self, store) -> None:
        self.store = store

    def record(
        self,
        *,
        session_id: int,
        outcome: str,
        stage: str,
        error_code: str = "",
        worker_profile: str = "",
        evidence: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        signature = failure_signature(stage, error_code or outcome, worker_profile)
        payload = dict(evidence or {})
        if outcome in FAILURE_OUTCOMES:
            payload.setdefault(
                "failure_fingerprint",
                failure_detail_signature(
                    stage,
                    error_code or outcome,
                    str(payload.get("blocker") or payload.get("output") or error_code or outcome),
                ),
            )
        attempt = payload.get("attempt")
        if attempt is not None:
            for existing in self.store.list_learning_records(signature=signature, limit=100):
                existing_evidence = _evidence(existing)
                if (
                    int(existing["session_id"]) == int(session_id)
                    and existing["outcome"] == outcome
                    and existing_evidence.get("attempt") == attempt
                    and existing_evidence.get("failure_fingerprint")
                    == payload.get("failure_fingerprint")
                ):
                    return {**existing, "deduplicated": True}
        record = self.store.add_learning_record(
            session_id=session_id,
            outcome=outcome,
            stage=stage,
            error_code=error_code,
            worker_profile=worker_profile,
            signature=signature,
            evidence=payload,
        )
        self._propose_reusable_playbook(
            signature, outcome, stage, error_code, worker_profile
        )
        if outcome in SUCCESS_OUTCOMES:
            self._link_resolved_failures(record)
        return record

    def failure_count(self, session_id: int, fingerprint: str) -> int:
        count = 0
        for record in self.store.list_learning_records(limit=1000):
            if (
                int(record["session_id"]) == int(session_id)
                and record["outcome"] in FAILURE_OUTCOMES
                and _evidence(record).get("failure_fingerprint") == fingerprint
            ):
                count += 1
        return count

    def applicable(
        self,
        *,
        worker_profile: str,
        session_id: int | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        selected: list[dict[str, Any]] = []
        for playbook in self.store.list_playbooks(status="active"):
            try:
                content = json.loads(playbook.get("content_json") or "{}")
            except (TypeError, json.JSONDecodeError):
                continue
            match = content.get("match") or {}
            expected_worker = str(match.get("worker_profile") or "")
            if expected_worker and expected_worker != worker_profile:
                continue
            selected.append({
                "slug": playbook["slug"],
                "title": playbook["title"],
                "kind": playbook["kind"],
                "match": match,
                "instructions": [str(item) for item in content.get("instructions") or []][:5],
            })
            if len(selected) >= max(1, limit):
                break
        return selected

    def _link_resolved_failures(self, success: dict[str, Any]) -> None:
        session_id = int(success["session_id"])
        records = self.store.list_learning_records(limit=1000)
        failures = [
            item for item in records
            if int(item["session_id"]) == session_id and item["outcome"] in FAILURE_OUTCOMES
        ]
        resolved_ids = {
            int(payload["resolves_record_id"])
            for item in records
            if item["outcome"] == "resolved"
            and (payload := _evidence(item)).get("resolves_record_id") is not None
        }
        for failure in failures:
            failure_id = int(failure["id"])
            if failure_id in resolved_ids:
                continue
            evidence = _evidence(failure)
            self.store.add_learning_record(
                session_id=session_id,
                outcome="resolved",
                stage=str(failure["stage"]),
                error_code=str(failure["error_code"]),
                worker_profile=str(failure["worker_profile"]),
                signature=str(failure["signature"]),
                evidence={
                    "resolves_record_id": failure_id,
                    "failure_fingerprint": evidence.get("failure_fingerprint"),
                    "resolution_record_id": int(success["id"]),
                    "resolution_outcome": success["outcome"],
                },
            )
            matching = self.store.list_learning_records(
                signature=str(failure["signature"]), limit=1000
            )
            resolved_count = sum(item["outcome"] == "resolved" for item in matching)
            self.store.upsert_playbook(
                slug=f"repair-{failure['signature']}",
                title=f"Recovery for {failure['error_code'] or failure['stage']}",
                kind="repair",
                content={
                    "match": {
                        "signature": failure["signature"],
                        "stage": failure["stage"],
                        "error_code": failure["error_code"],
                        "worker_profile": failure["worker_profile"],
                    },
                    "action": "avoid_repeated_failure",
                    "instructions": _repair_instructions(str(failure["error_code"])),
                },
                status="candidate",
                evidence_count=resolved_count,
            )

    def _propose_reusable_playbook(
        self, signature: str, outcome: str, stage: str, error_code: str, worker_profile: str
    ) -> None:
        records = self.store.list_learning_records(signature=signature, limit=100)
        if len(records) < 3:
            return
        successful = outcome in SUCCESS_OUTCOMES
        title = (
            f"Prefer {worker_profile or 'qualified worker'} for {stage}"
            if successful else f"Recovery for {error_code or stage}"
        )
        content = {
            "match": {
                "signature": signature,
                "stage": stage,
                "error_code": error_code,
                "worker_profile": worker_profile,
            },
            "action": "prefer_worker" if successful else "checkpoint_then_repair",
            "instructions": [
                (
                    "Prefer the recorded worker profile for a matching bounded sprint."
                    if successful else "Preserve the current worktree and action receipts."
                ),
                (
                    "Keep the same deterministic gates and reviewer requirements."
                    if successful else "Build a fresh handoff from the latest valid checkpoint."
                ),
                (
                    "Fall back only at a validated checkpoint."
                    if successful else "Retry once, then switch worker only at the checkpoint boundary."
                ),
            ],
        }
        if not successful:
            content["instructions"] = _repair_instructions(error_code)
        self.store.upsert_playbook(
            slug=f"{'route' if successful else 'repair'}-{signature}",
            title=title,
            kind="routing" if successful else "repair",
            content=content,
            status="candidate",
            evidence_count=len(records),
        )

    def replay(self, playbook_slug: str | None = None) -> dict[str, Any]:
        playbooks = self.store.list_playbooks(status=None)
        if playbook_slug:
            playbooks = [item for item in playbooks if item["slug"] == playbook_slug]
        results: list[dict[str, Any]] = []
        for playbook in playbooks:
            content = json.loads(playbook.get("content_json") or "{}")
            match = content.get("match") or {}
            signature = str(match.get("signature") or "")
            records = self.store.list_learning_records(
                signature=signature or None, limit=100
            )
            if playbook["kind"] == "repair":
                failures = [item for item in records if item["outcome"] in FAILURE_OUTCOMES]
                resolved = [item for item in records if item["outcome"] == "resolved"]
                eligible = failures
                passing = resolved
            else:
                eligible = [item for item in records if item["outcome"] in SUCCESS_OUTCOMES]
                passing = list(eligible)
            pass_rate = len(passing) / len(eligible) if eligible else 0.0
            qualified = (
                playbook["kind"] in SAFE_PLAYBOOK_KINDS and
                len(eligible) >= 3 and len(passing) >= 2 and pass_rate >= 0.9
            )
            status = "active" if qualified else "candidate"
            self.store.update_playbook_replay(
                playbook["slug"],
                status=status,
                replay={"cases": len(eligible), "passed": len(passing), "pass_rate": pass_rate,
                        "evaluated_at": utc_now()},
            )
            results.append({
                "slug": playbook["slug"], "qualified": qualified,
                "cases": len(eligible), "passed": len(passing), "pass_rate": pass_rate,
            })
        return {"results": results}

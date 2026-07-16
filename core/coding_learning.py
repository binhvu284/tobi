"""Evidence-backed coding outcomes, replay evaluation, and safe playbooks."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from core.development_store import utc_now


SAFE_PLAYBOOK_KINDS = {"prompt", "routing", "repair"}


def failure_signature(stage: str, error_code: str, worker_profile: str) -> str:
    source = f"{stage}|{error_code}|{worker_profile}".lower()
    return hashlib.sha256(source.encode("utf-8")).hexdigest()[:20]


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
        record = self.store.add_learning_record(
            session_id=session_id,
            outcome=outcome,
            stage=stage,
            error_code=error_code,
            worker_profile=worker_profile,
            signature=signature,
            evidence=evidence or {},
        )
        self._propose_reusable_playbook(
            signature, outcome, stage, error_code, worker_profile
        )
        return record

    def _propose_reusable_playbook(
        self, signature: str, outcome: str, stage: str, error_code: str, worker_profile: str
    ) -> None:
        records = self.store.list_learning_records(signature=signature, limit=100)
        if len(records) < 3:
            return
        successful = outcome in {"completed", "qualified_local"}
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
            eligible = [
                item for item in records
                if item["outcome"] in {"completed", "qualified_local"} or
                   (item["signature"] == playbook.get("slug", "").removeprefix("repair-"))
            ]
            passing = [item for item in eligible if item["outcome"] in {"completed", "qualified_local"}]
            pass_rate = len(passing) / len(eligible) if eligible else 0.0
            qualified = (
                playbook["kind"] in SAFE_PLAYBOOK_KINDS and
                len(eligible) >= 3 and pass_rate >= 0.9
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

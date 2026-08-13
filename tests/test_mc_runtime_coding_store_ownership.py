"""T10 Run 2: accepted #22 table writes have one store owner."""
from __future__ import annotations

import inspect
import os
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import coding_agent  # noqa: E402
from core.development_store import DevelopmentStore  # noqa: E402


FAILURES: list[str] = []


def ok(name: str, condition: bool, detail: str = "") -> None:
    print(f"{'PASS' if condition else 'FAIL'} {name}")
    if not condition:
        if detail:
            print(f"  {detail}")
        FAILURES.append(name)


agent_source = inspect.getsource(coding_agent)
for table in ("development_tasks", "coding_stages", "coding_artifacts"):
    direct_sql = re.search(
        rf"(?is)\b(select|insert|update|delete)\b.{{0,240}}\b{table}\b",
        agent_source,
    )
    ok(f"coding agent has no direct {table} SQL", direct_sql is None,
       direct_sql.group(0)[:280] if direct_sql else "")

required_methods = (
    "approve_task_for_workflow",
    "set_task_owner_state",
    "complete_task",
    "active_session_for_task",
    "reset_stages_for_replan",
    "reset_stages_for_worker_switch",
    "reset_stages_for_next_sprint",
    "reset_stages_for_base_reconciliation",
    "reset_stages_for_recode",
    "reset_stages_after_approval_rejection",
    "storage_cleanup_counts",
    "cleanup_candidates",
    "mark_artifact_cleaned",
)
for method in required_methods:
    ok(f"store owns {method}", callable(getattr(DevelopmentStore, method, None)))

if all(callable(getattr(DevelopmentStore, method, None)) for method in required_methods):
    with tempfile.TemporaryDirectory(prefix="tobi_t10_store_") as tmp:
        store = DevelopmentStore(Path(tmp) / "agent.db")
        task = store.upsert_task({
            "queue_id": 21001,
            "title": "Ownership test",
            "plan_path": "docs/test.md",
            "plan_hash": "abc123",
            "status": "planned",
        })
        approved = store.approve_task_for_workflow(int(task["id"]), "3.21.0")
        ok("approval update remains exact", (
            approved["status"] == "approved"
            and approved["owner_state"] == "Running"
            and approved["target_version"] == "3.21.0"
        ), repr(approved))
        session = store.create_session(int(task["id"]), "policy", "t10-store")
        store.add_stages(int(session["id"]), [
            {"id": "code", "title": "Code", "depends": []},
            {"id": "validate", "title": "Validate", "depends": ["code"]},
            {"id": "review", "title": "Review", "depends": ["validate"]},
            {"id": "commit", "title": "Commit", "depends": ["review"]},
        ])
        for node in ("code", "validate", "review", "commit"):
            store.update_stage(int(session["id"]), node, status="completed", result_json={"ok": True})
        store.reset_stages_for_recode(int(session["id"]))
        statuses = {row["node_id"]: row for row in store.list_stages(int(session["id"]))}
        ok("recode reset preserves exact pending result behavior", all(
            statuses[node]["status"] == "pending" and statuses[node]["result_json"] is not None
            for node in statuses
        ), repr(statuses))
        ok("active-session guard remains store owned", (
            store.active_session_for_task(int(task["id"])) == int(session["id"])
        ))
        artifact_path = Path(tmp) / "artifact.json"
        artifact_path.write_text('{"ok":true}', encoding="utf-8")
        artifact = store.add_artifact(
            int(session["id"]), "test", artifact_path, "2020-01-01T00:00:00+00:00"
        )
        store.update_session(
            int(session["id"]),
            state="completed",
            completed_at="2020-01-01T00:00:00+00:00",
            worktree=str(Path(tmp) / "worktree"),
        )
        counts = store.storage_cleanup_counts(
            now="2026-08-14T00:00:00+00:00",
            cutoff="2026-08-01T00:00:00+00:00",
        )
        ok("cleanup counts remain exact", counts == {"artifacts": 1, "worktrees": 1}, repr(counts))
        candidates = store.cleanup_candidates(
            now="2026-08-14T00:00:00+00:00",
            cutoff="2026-08-01T00:00:00+00:00",
        )
        ok("cleanup candidates retain artifact and session identity", (
            [row["id"] for row in candidates["artifacts"]] == [artifact["id"]]
            and [row["id"] for row in candidates["sessions"]] == [session["id"]]
        ), repr(candidates))
        store.mark_artifact_cleaned(int(artifact["id"]))
        counts = store.storage_cleanup_counts(
            now="2026-08-14T00:00:00+00:00",
            cutoff="2026-08-01T00:00:00+00:00",
        )
        ok("cleaned artifact leaves the eligible count", counts["artifacts"] == 0, repr(counts))
        completed = store.complete_task(int(task["id"]), queue_status="Done")
        ok("completion update remains exact", (
            completed["status"] == "completed"
            and completed["owner_state"] == "Done"
            and completed["status_override"] == 1
        ), repr(completed))

print(f"\n{len(FAILURES)} failures")
raise SystemExit(1 if FAILURES else 0)

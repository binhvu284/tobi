"""T10 Run 1: MC-authoritative, versioned worker capability boundary."""
from __future__ import annotations

import inspect
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import hermes_skills, hermes_sync  # noqa: E402
from core.runtime import worker_capabilities  # noqa: E402
from core.runtime.contracts import ErrorCategory, ErrorStage, RecoveryAction  # noqa: E402


FAILURES: list[str] = []


def ok(name: str, condition: bool, detail: str = "") -> None:
    print(f"{'PASS' if condition else 'FAIL'} {name}")
    if not condition:
        if detail:
            print(f"  {detail}")
        FAILURES.append(name)


profiles = [
    {
        "slug": "codex-chatgpt",
        "name": "Codex",
        "adapter": "codex",
        "enabled": 1,
        "health_status": "ready",
        "health_detail": "Native login ready.",
        "canonical_owner": "worker",
    },
    {
        "slug": "hermes-legacy",
        "name": "Hermes",
        "adapter": "hermes",
        "enabled": 0,
        "health_status": "disabled",
        "health_detail": "Hermes is disabled by reviewed policy.",
        "canonical_owner": "hermes",
    },
]
skills = [{
    "id": "skill_controlled_coding",
    "version": 1,
    "status": "available",
    "can_execute": False,
    "file_path": "hermes_skills/skill_controlled_coding.md",
}]

snapshot = worker_capabilities.build_snapshot(
    profiles,
    skills,
    observed_at="2026-08-14T00:00:00+00:00",
    coding_source_version="2",
    hermes_source_version="1",
)
same = worker_capabilities.build_snapshot(
    list(reversed(profiles)),
    list(reversed(skills)),
    observed_at="2026-08-14T00:00:00+00:00",
    coding_source_version="2",
    hermes_source_version="1",
)

ok("snapshot is immutable", worker_capabilities.WorkerCapabilitySnapshot.__dataclass_params__.frozen)
ok("worker record is immutable", worker_capabilities.WorkerCapabilityRecord.__dataclass_params__.frozen)
ok("assignment is immutable", worker_capabilities.WorkerAssignment.__dataclass_params__.frozen)
ok("Mission Control is the only authority", snapshot.authority == "mission_control")
ok("input worker authority cannot override MC", all(
    worker.authority == "mission_control" for worker in snapshot.workers
))
ok("identical metadata has a deterministic version", snapshot.version == same.version)
ok("snapshot ordering is deterministic", snapshot.workers == same.workers)

codex = next(worker for worker in snapshot.workers if worker.worker_id == "codex-chatgpt")
ok("ready coding worker has bounded coding capability", "bounded_coding" in codex.capabilities)
ok("accepted checkpoint capability is visible", "checkpoint_resume" in codex.capabilities)
ok("accepted evidence capability is visible", "evidence_report" in codex.capabilities)
ok("worker never owns canonical state", codex.canonical_writes == ())

hermes = next(worker for worker in snapshot.workers if worker.worker_id == "hermes-legacy")
ok("disabled Hermes is unavailable", hermes.available is False)
ok("read-only Hermes skill cannot grant execution", "bounded_coding" not in hermes.capabilities)
ok("skill remains metadata evidence", hermes.evidence_refs == (
    "hermes_skills/skill_controlled_coding.md@1",
))

assignment = worker_capabilities.select_worker(
    snapshot,
    "hermes-legacy",
    run_id="run:t10",
)
ok("unavailable worker keeps canonical run id", assignment.run_id == "run:t10")
ok("unavailable worker yields structured recovery", (
    assignment.status == "blocked" and assignment.error is not None
))
ok("recovery error uses availability taxonomy", (
    assignment.error.category is ErrorCategory.AVAILABILITY
    and assignment.error.stage is ErrorStage.PLAN
))
ok("recovery offers retry setup or fallback", set(assignment.error.recovery_actions) == {
    RecoveryAction.RETRY_STEP, RecoveryAction.PROVIDE_INPUT, RecoveryAction.REVISE,
})
ok("raw worker detail is not exposed", "Native login" not in assignment.error.owner_message)
ok("ready worker assignment does not execute", (
    worker_capabilities.select_worker(snapshot, "codex-chatgpt", run_id="run:t10").status == "ready"
))

try:
    worker_capabilities.build_snapshot(
        profiles, skills, observed_at="2026-08-14T00:00:00+00:00",
        coding_source_version="999", hermes_source_version="1",
    )
except ValueError:
    unknown_version_rejected = True
else:
    unknown_version_rejected = False
ok("unknown source version is rejected", unknown_version_rejected)

try:
    worker_capabilities.build_snapshot(
        [profiles[0], {**profiles[0], "adapter": "hermes"}], skills,
        observed_at="2026-08-14T00:00:00+00:00",
        coding_source_version="2", hermes_source_version="1",
    )
except ValueError:
    duplicate_rejected = True
else:
    duplicate_rejected = False
ok("contradictory duplicate worker authority is rejected", duplicate_rejected)

sync_source = hermes_sync.capability_source()
skills_source = hermes_skills.capability_source(skills)
ok("Hermes sync declares one-way MC authority", (
    sync_source["authority"] == "mission_control"
    and sync_source["direction"] == "mc_to_hermes"
    and sync_source["can_own_runtime"] is False
))
ok("Hermes skills source remains read only", (
    skills_source["can_execute"] is False
    and skills_source["can_own_runtime"] is False
))

source = inspect.getsource(worker_capabilities)
ok("adapter has no worker execution dependency", "hermes_worker" not in source and ".run(" not in source)
ok("adapter has no queue persistence dependency", (
    "development_store" not in source and "coding_queue" not in source and "get_connection" not in source
))

print(f"\n{len(FAILURES)} failures")
raise SystemExit(1 if FAILURES else 0)

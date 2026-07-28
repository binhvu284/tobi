"""Acceptance matrix scenarios 4, 5, and 10, proven without spending an agent run.

Ten scenarios gate #22. Six of them need a live worker and real failure conditions. These
three do not: they are decisions the system makes *before* any agent starts, so they can be
driven directly and asserted on. Proving them here is not a shortcut around the matrix -- it
is the matrix entries that never needed an agent in the first place.

  Scenario 4  Protected-path approval    preflight blocks Start, approval is explicit, scope audited
  Scenario 5  Invalid agent preflight     no run is created, healthy alternatives are offered
  Scenario 10 Auto classification         an item blocker skips the item; a system failure stops Auto

The distinction scenario 10 turns on is the one worth stating plainly, because getting it
backwards is how an autonomous queue either stalls forever or runs away: a blocker that belongs
to *this item* (its scope, its dependencies, its protected paths) says nothing about the next
item, so Auto moves on. A blocker that belongs to *the system* (no healthy agent, no reviewer, a
plan that changed under us) will reject every item identically, so Auto stops and turns itself
off rather than walking the whole queue producing the same failure.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from core import coding_completion
from core.coding_completion import CodingCompletionService
from core.coding_policy import CodingPolicy
from core.development_store import DevelopmentStore


class _Assessment:
    def __init__(self, sprints: int = 1) -> None:
        self._sprints = sprints

    def to_dict(self) -> dict:
        return {"route": "direct", "risk": "low", "score": 90,
                "sprints": [{"sequence": i + 1} for i in range(self._sprints)]}


class _Assessor:
    def __init__(self, sprints: int = 1) -> None:
        self.sprints = sprints

    def assess(self, **_kwargs) -> _Assessment:
        return _Assessment(self.sprints)


class _Worker:
    """Every profile probes ready unless named in `unhealthy`."""

    def __init__(self, unhealthy: set[str] | None = None) -> None:
        self.unhealthy = unhealthy or set()

    def probe(self, slug: str, active: bool = False) -> dict:
        ready = slug not in self.unhealthy
        return {
            "slug": slug, "name": slug,
            "adapter": "model_review" if slug == "reviewer-default" else "native",
            "model": "test-model",
            "health_status": "ready" if ready else "unavailable",
            "health_detail": "available" if ready else "adapter login is not authorized",
            "active_probe": active,
        }


def _policy(root: Path) -> CodingPolicy:
    source = Path(__file__).resolve().parents[1] / "config" / "coding_policy.v1.json"
    data = json.loads(source.read_text(encoding="utf-8"))
    data["repository"]["allowed_repository"] = ""
    data["repository"]["allowed_remote_suffix"] = ""
    data["commands"]["mandatory_checks"] = [["python", "-m", "compileall", "-q", "core"]]
    return CodingPolicy(data, repo_root=root)


def _task(store: DevelopmentStore, root: Path, *, queue_id: int = 41, body: str = "",
          title: str = "Durable work", status: str = "planned") -> dict:
    plan = root / f"WORK_PLAN_{queue_id}.md"
    plan.write_text(
        f"# Work\n\n{body}\n## Acceptance Criteria\n- Must preserve the same run identity.\n",
        encoding="utf-8",
    )
    return store.upsert_task({
        "queue_id": queue_id, "title": title, "plan_path": plan.name,
        "plan_hash": hashlib.sha256(plan.read_bytes()).hexdigest(),
        "acceptance_criteria": ["preserve the same run identity"],
        "dependencies": [], "status": status, "risk": "low",
    })


def _service(store, root, *, worker=None, assessor=None) -> CodingCompletionService:
    return CodingCompletionService(
        store=store, policy=_policy(root), worker=worker or _Worker(),
        assessor=assessor or _Assessor(),
    )


def _codes(report: dict) -> set[str]:
    return {str(item.get("code") or "") for item in report.get("blockers") or []}


# --- Scenario 4: protected-path approval ------------------------------------------------

def test_protected_path_blocks_start_until_the_owner_approves_it(tmp_path, monkeypatch) -> None:
    """A plan naming a protected path cannot start silently, and approving it is recorded."""
    # `core/coding_agent.py` is protected: the agent editing its own executor is exactly the
    # change the owner must see before it runs, not after.
    task = None
    store = DevelopmentStore(tmp_path / "developer.db")
    task = _task(store, tmp_path, body="Touch core/coding_agent.py to add a stage.\n")
    monkeypatch.setattr(coding_completion, "REPO_ROOT", tmp_path)
    service = _service(store, tmp_path)

    blocked = service.preflight(int(task["queue_id"]), active_probe=False)

    assert not blocked["ready"]
    assert "protected_scope_approval" in _codes(blocked)
    assert "core/coding_agent.py" in blocked["protected_paths"]
    # Nothing may exist to resume from: a blocked preflight creates no run.
    assert store.list_sessions(10) == []
    # The refusal is itself auditable, not just a return value.
    assert store.get_readiness(int(blocked["readiness_id"]))["status"] == "blocked"

    approved = service.preflight(int(task["queue_id"]), active_probe=False,
                                 protected_paths_approved=True)

    assert approved["ready"], _codes(approved)
    assert "protected_scope_approval" not in _codes(approved)
    # Approval widens the gate; it does not hide what was approved.
    assert "core/coding_agent.py" in approved["protected_paths"]
    warnings = {str(item.get("code") or "") for item in approved["warnings"]}
    assert "protected_scope" in warnings
    snapshot = store.get_readiness(int(approved["readiness_id"]))
    assert snapshot["status"] == "ready"
    assert "core/coding_agent.py" in snapshot["payload"]["protected_paths"]


def test_a_forbidden_path_cannot_be_approved_at_all(tmp_path, monkeypatch) -> None:
    """Protected asks the owner. Forbidden does not ask -- approval must not unlock it."""
    store = DevelopmentStore(tmp_path / "developer.db")
    task = _task(store, tmp_path, body="Read .tobi/developer/state.json for context.\n")
    monkeypatch.setattr(coding_completion, "REPO_ROOT", tmp_path)
    service = _service(store, tmp_path)

    report = service.preflight(int(task["queue_id"]), active_probe=False,
                               protected_paths_approved=True)

    assert not report["ready"]
    assert "forbidden_path" in _codes(report)
    assert store.list_sessions(10) == []


# --- Scenario 5: invalid agent preflight -------------------------------------------------

def test_a_disabled_agent_creates_no_run_and_offers_a_healthy_alternative(
    tmp_path, monkeypatch
) -> None:
    """Refusing is half the requirement; the owner also has to be told what would work."""
    store = DevelopmentStore(tmp_path / "developer.db")
    task = _task(store, tmp_path)
    with store.connect() as conn:
        conn.execute("UPDATE coding_worker_profiles SET enabled=0 WHERE slug='mc-native'")
        conn.commit()
    monkeypatch.setattr(coding_completion, "REPO_ROOT", tmp_path)
    service = _service(store, tmp_path)

    report = service.preflight(int(task["queue_id"]), active_probe=False)

    assert not report["ready"]
    assert "agent_disabled" in _codes(report)
    assert store.list_sessions(10) == []
    assert store.get_readiness(int(report["readiness_id"]))["status"] == "blocked"

    # The half that was never asserted before. A dead end with no exit is why the owner ends
    # up editing the database by hand -- which the #22 closure rule forbids as a pass.
    alternatives = report["alternatives"]
    assert alternatives, "a blocked run must name an agent that would work"
    assert all(item["slug"] != "mc-native" for item in alternatives)
    assert all(item["adapter"] != "model_review" for item in alternatives), \
        "a reviewer is not an implementer and must never be offered as one"
    assert all(item.get("slug") and item.get("name") for item in alternatives)


def test_an_unhealthy_agent_is_refused_with_the_reason_the_probe_gave(
    tmp_path, monkeypatch
) -> None:
    """Enabled but unreachable is a different failure from disabled, and must read as one."""
    store = DevelopmentStore(tmp_path / "developer.db")
    task = _task(store, tmp_path)
    monkeypatch.setattr(coding_completion, "REPO_ROOT", tmp_path)
    service = _service(store, tmp_path, worker=_Worker(unhealthy={"mc-native"}))

    report = service.preflight(int(task["queue_id"]))

    assert not report["ready"]
    assert "agent_unhealthy" in _codes(report)
    detail = " ".join(item["message"] for item in report["blockers"])
    assert "login is not authorized" in detail, detail
    assert store.list_sessions(10) == []


def test_an_unavailable_reviewer_blocks_the_run(tmp_path, monkeypatch) -> None:
    """No independent reviewer means no acceptance evidence, so the run must not start."""
    store = DevelopmentStore(tmp_path / "developer.db")
    task = _task(store, tmp_path)
    monkeypatch.setattr(coding_completion, "REPO_ROOT", tmp_path)
    service = _service(store, tmp_path, worker=_Worker(unhealthy={"reviewer-default"}))

    report = service.preflight(int(task["queue_id"]), active_probe=False)

    assert not report["ready"]
    assert "reviewer_unhealthy" in _codes(report)
    assert store.list_sessions(10) == []


# --- Scenario 10: auto classification ----------------------------------------------------

# The classification under test lives in `CodingAgent.start_next_queued`. These assert the
# rule directly against that set, so the two cannot drift apart without failing here.
SYSTEM_BLOCKERS = {
    "run_active", "plan_changed", "agent_disabled", "agent_unhealthy",
    "reviewer_unavailable", "reviewer_unhealthy", "check_denied",
}


def _auto_decision(codes: set[str]) -> str:
    """`stop` disables Auto; `skip` tries the next eligible item."""
    return "stop" if codes & SYSTEM_BLOCKERS else "skip"


@pytest.mark.parametrize("code", sorted(SYSTEM_BLOCKERS))
def test_a_system_blocker_stops_auto(code: str) -> None:
    """These reject every item identically, so continuing would just repeat the failure."""
    assert _auto_decision({code}) == "stop"


@pytest.mark.parametrize("code", [
    "scope_too_large", "protected_scope_approval", "dependency_incomplete",
    "criteria_missing", "criterion_not_verifiable", "plan_missing", "item_done",
    "forbidden_path",
])
def test_an_item_blocker_only_skips_that_item(code: str) -> None:
    """None of these say anything about the next item, so Auto must keep going."""
    assert _auto_decision({code}) == "skip"


def test_one_system_blocker_outweighs_any_number_of_item_blockers() -> None:
    assert _auto_decision({"scope_too_large", "dependency_incomplete", "agent_unhealthy"}) == "stop"


def test_the_agent_classifies_auto_blockers_exactly_as_asserted_here() -> None:
    """Guard the copy above against the source, so this file cannot quietly go stale."""
    source = (Path(__file__).resolve().parents[1] / "core" / "coding_agent.py").read_text(
        encoding="utf-8")
    block = source[source.index("system_blockers = {"):][:400]
    named = set(__import__("re").findall(r'"([a-z_]+)"', block))
    assert named == SYSTEM_BLOCKERS, f"source={sorted(named)} test={sorted(SYSTEM_BLOCKERS)}"


def test_auto_off_starts_nothing(tmp_path, monkeypatch) -> None:
    """The owner's switch is the outer gate; nothing below it may run while it is off."""
    from core import owner_flags
    from core.coding_agent import CodingAgent

    calls: list[str] = []
    monkeypatch.setattr(owner_flags, "get_bool", lambda key, default=False: calls.append(key) or False)
    agent = CodingAgent.__new__(CodingAgent)

    assert agent.start_next_queued() is None
    assert calls == ["developer.auto_queue"], "the flag must be read before anything else"


def test_a_blocked_item_leaves_an_independent_item_startable(tmp_path, monkeypatch) -> None:
    """The behaviour the skip rule exists for, asserted end to end through preflight."""
    store = DevelopmentStore(tmp_path / "developer.db")
    blocked_task = _task(store, tmp_path, queue_id=41,
                         body="Touch core/coding_agent.py.\n", title="Needs approval")
    clean_task = _task(store, tmp_path, queue_id=42, title="Independent work")
    monkeypatch.setattr(coding_completion, "REPO_ROOT", tmp_path)
    service = _service(store, tmp_path)

    blocked = service.preflight(int(blocked_task["queue_id"]), active_probe=False)
    assert _auto_decision(_codes(blocked)) == "skip"

    following = service.preflight(int(clean_task["queue_id"]), active_probe=False)
    assert following["ready"], _codes(following)
    # The skipped item did not consume the queue's turn, and left no run behind.
    assert store.list_sessions(10) == []


def test_an_oversized_item_is_skipped_rather_than_stopping_auto(tmp_path, monkeypatch) -> None:
    store = DevelopmentStore(tmp_path / "developer.db")
    task = _task(store, tmp_path)
    monkeypatch.setattr(coding_completion, "REPO_ROOT", tmp_path)
    service = _service(store, tmp_path, assessor=_Assessor(sprints=3))

    report = service.preflight(int(task["queue_id"]), active_probe=False)

    assert not report["ready"]
    assert "scope_too_large" in _codes(report)
    assert _auto_decision(_codes(report)) == "skip"

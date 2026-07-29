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


def _policy(root: Path, **capabilities: bool) -> CodingPolicy:
    """The shipped policy with its delivery capabilities pinned.

    These scenarios are about protected paths, agent health, and queue classification -- none
    of which is a statement about delivery. Inheriting whatever `capabilities` the owner
    happens to have enabled made them fail the moment `github` was turned on, which is a test
    reporting the owner's configuration rather than the behaviour it claims to cover.
    """
    source = Path(__file__).resolve().parents[1] / "config" / "coding_policy.v1.json"
    data = json.loads(source.read_text(encoding="utf-8"))
    data["repository"]["allowed_repository"] = ""
    data["repository"]["allowed_remote_suffix"] = ""
    data["commands"]["mandatory_checks"] = [["python", "-m", "compileall", "-q", "core"]]
    data["workers"]["qualified_implementer_adapters"] = ["native", "codex", "opencode"]
    data["capabilities"] = {**data["capabilities"],
                            "github": False, "merge": False, "deploy": False, **capabilities}
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


@pytest.fixture(autouse=True)
def _reviewer_model_is_configured(monkeypatch):
    """Assume a working Models configuration unless a test is specifically about it.

    Preflight asks whether acceptance review can be given a model. That question depends on
    the machine's own Models page, so without this every scenario here would start reporting
    the developer's local configuration instead of the behaviour it claims to cover -- the
    same trap the capability pinning in `_policy` exists to avoid. The two tests that *are*
    about reviewer models re-patch this themselves.
    """
    monkeypatch.setattr(coding_completion, "reviewer_model_problem", lambda model=None: "")
    monkeypatch.setattr(
        coding_completion, "reviewer_model_auth_problem", lambda model=None: ""
    )


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


def test_enabling_github_without_the_coding_app_blocks_before_anything_is_pushed(
    tmp_path, monkeypatch
) -> None:
    """The capability must prove its prerequisite at Start, not halfway through delivery.

    `push` and `pull_request` are gated by one flag but backed by two different credentials:
    push rides the repository's own git auth, the draft PR needs a GitHub App. Turning the
    flag on with no App configured is the worst ordering available -- the branch lands on the
    real repository and *then* the PR raises, leaving a dead-ended run that has already
    mutated GitHub. Stopping cleanly at `locally_complete` is strictly better than that.
    """
    store = DevelopmentStore(tmp_path / "developer.db")
    task = _task(store, tmp_path)
    monkeypatch.setattr(coding_completion, "REPO_ROOT", tmp_path)
    for name in ("GITHUB_APP_ID", "GITHUB_APP_INSTALLATION_ID", "GITHUB_APP_PRIVATE_KEY"):
        monkeypatch.delenv(name, raising=False)
    policy = _policy(tmp_path)
    policy.data["capabilities"]["github"] = True
    service = CodingCompletionService(
        store=store, policy=policy, worker=_Worker(), assessor=_Assessor()
    )

    report = service.preflight(int(task["queue_id"]), active_probe=False)

    assert not report["ready"]
    assert "github_app_unconfigured" in _codes(report)
    assert store.list_sessions(10) == []
    # It rejects every item identically, so Auto stops rather than walking the whole queue.
    assert _auto_decision(_codes(report)) == "stop"

    # With the App present the capability stops being the thing standing in the way.
    for name, value in (("GITHUB_APP_ID", "1"), ("GITHUB_APP_INSTALLATION_ID", "2"),
                        ("GITHUB_APP_PRIVATE_KEY", "-----BEGIN PRIVATE KEY-----\nx\n")):
        monkeypatch.setenv(name, value)
    cleared = service.preflight(int(task["queue_id"]), active_probe=False)
    assert "github_app_unconfigured" not in _codes(cleared), _codes(cleared)


def test_the_reviewed_policy_grants_delivery_but_not_merge_or_deploy(tmp_path) -> None:
    """github went true on 2026-07-28 once the Coding App was configured and verified.

    merge and deploy stay false deliberately. `github` lets a run push its branch and open a
    *draft* PR -- work the owner can see and close. `merge` would let it change `main` and
    `deploy` would let it ship, neither of which has been proven by a single run yet. The
    three are separate flags precisely so delivery can be earned one step at a time.
    """
    source = Path(__file__).resolve().parents[1] / "config" / "coding_policy.v1.json"
    capabilities = json.loads(source.read_text(encoding="utf-8"))["capabilities"]
    assert capabilities["github"] is True
    assert capabilities["merge"] is False, "merging main is not an agent decision yet"
    assert capabilities["deploy"] is False, "deploying is not an agent decision yet"


def test_a_reviewer_with_no_model_blocks_before_an_implementer_is_spent(
    tmp_path, monkeypatch
) -> None:
    """The probe says "enabled and reachable", which a reviewer with no model passes.

    Review is the last gate before delivery, so this gap does not surface until an implementer
    has produced the entire change. Run 16 spent two full Codex sprints -- writing the suite,
    then re-running every validation on retry -- before pausing on ModelRoutingNotConfigured,
    and Retry could never clear it because nothing about the code was wrong.
    """
    store = DevelopmentStore(tmp_path / "developer.db")
    task = _task(store, tmp_path)
    monkeypatch.setattr(coding_completion, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(coding_completion, "reviewer_model_problem",
                        lambda model=None: "No model is configured for acceptance review.")
    service = _service(store, tmp_path)

    report = service.preflight(int(task["queue_id"]), active_probe=False)

    assert not report["ready"]
    assert "reviewer_model_unconfigured" in _codes(report)
    assert store.list_sessions(10) == [], "no implementer time may be spent on an unreviewable run"
    assert _auto_decision(_codes(report)) == "stop"

    monkeypatch.setattr(coding_completion, "reviewer_model_problem", lambda model=None: "")
    cleared = service.preflight(int(task["queue_id"]), active_probe=False)
    assert cleared["ready"], _codes(cleared)


def test_the_preflight_check_and_the_reviewer_resolve_the_model_the_same_way(tmp_path) -> None:
    """One resolution order, so a run cannot be admitted and then fail on the same question."""
    source = (Path(__file__).resolve().parents[1] / "core" / "coding_review.py").read_text(
        encoding="utf-8")
    review_body = source[source.index("    def review("):]
    assert "reviewer_model_problem(model)" in review_body, \
        "review() must ask the same helper preflight asks"
    assert "config.get(\"default_model\")" not in review_body, \
        "review() must not keep a second copy of the resolution order"

    from core.coding_review import reviewer_model_problem
    # The order itself: an explicit model wins over configuration, and is validated.
    assert "not available" in reviewer_model_problem("definitely-not-a-real-model-id")


def test_reviewer_authentication_is_proved_before_the_run_starts(
    tmp_path, monkeypatch
) -> None:
    """A configured reviewer that cannot authenticate must not spend an implementer."""
    store = DevelopmentStore(tmp_path / "developer.db")
    task = _task(store, tmp_path)
    monkeypatch.setattr(coding_completion, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        coding_completion,
        "reviewer_model_auth_problem",
        lambda model=None: "The acceptance reviewer could not authenticate during preflight.",
    )
    service = _service(store, tmp_path)

    report = service.preflight(int(task["queue_id"]), active_probe=True)

    assert not report["ready"]
    assert "reviewer_probe_failed" in _codes(report)
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
    "github_app_unconfigured", "reviewer_model_unconfigured",
    "reviewer_probe_failed",
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

"""A run must perform the checks its acceptance criteria name.

Sessions 9 through 14 each carried a criterion naming a test file -- `tests/test_awakening.py`,
`tests/test_task_classifier.py` -- while the run's validation commands were the policy default
(`compileall`, `tests/test_coding_agent.py`, `npm run build`). None of those runs ever executed
the named test, so the evidence the criterion asked for could not exist. Run 14's reviewer read
the diff, agreed the code was correct, and still refused to qualify it: "no evidence is provided
that the test suite tests/test_awakening.py remains green". The item was unpassable from the
moment it was authored, and finding that out cost six agent runs.

These checks fail while a criterion can name a check the run will not perform.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import coding_completion  # noqa: E402
from core.coding_completion import CodingCompletionService  # noqa: E402
from core.coding_criteria import (  # noqa: E402
    command_for, covered_by, derive_checks, is_test_path, referenced_checks,
)
from core.coding_policy import CodingPolicy  # noqa: E402
from core.development_store import DevelopmentStore  # noqa: E402

FAILURES: list[str] = []


def ok(label: str, condition: bool, detail: str = "") -> None:
    print(f"{'PASS' if condition else 'FAIL'} {label}{('  -> ' + detail) if detail and not condition else ''}")
    if not condition:
        FAILURES.append(label)


# --- the criteria that actually shipped -------------------------------------------------
# Verbatim from coding_sessions.criteria_snapshot_json for sessions 14 and 10.
SESSION_14 = [
    "Must treat a read connector as verified only when a successful connection test proves it,"
    " not when a token is merely present",
    "Must report external read access as partial when credentials exist without successful test"
    " evidence, and as setup needed when no connector is configured",
    "Must leave tests/test_awakening.py fully green with its configured-but-unverified"
    " expectation unchanged",
]
SESSION_10 = [
    "Must add tests/test_task_classifier.py with at least one ASCII-only case for each of the"
    " seven classify outcomes",
    "Must include a case proving the 60-character smalltalk limit and a case proving a coding"
    " word outranks a project word",
    "Must leave the new suite green under `python tests/test_task_classifier.py` while every"
    " existing file stays byte-identical",
]
DEFAULT_COMMANDS = [
    ["python", "-m", "compileall", "-q", "core", "api"],
    ["python", "tests/test_coding_agent.py"],
    ["npm", "run", "build", "--prefix", "dashboard"],
]

ok("the criterion that blocked run 14 names a check",
   referenced_checks(SESSION_14) == ["tests/test_awakening.py"], str(referenced_checks(SESSION_14)))
ok("run 10's two mentions of one test collapse to a single check",
   referenced_checks(SESSION_10) == ["tests/test_task_classifier.py"], str(referenced_checks(SESSION_10)))
ok("prose without a path names no check", referenced_checks(SESSION_14[:2]) == [])

# A criterion may legitimately name a module it changes. Running a module is not evidence, and
# turning every mentioned .py file into a command would make preflight refuse ordinary work.
ok("an implementation module is not mistaken for a check",
   referenced_checks(["Must keep core/coding_agent.py behavior-preserving"]) == [])
ok("a test outside tests/ is still a check", is_test_path("core/test_helpers.py"))
ok("the pytest suffix convention is recognized", is_test_path("suite/awakening_test.py"))

# --- reconciliation ---------------------------------------------------------------------
result = derive_checks(SESSION_14, DEFAULT_COMMANDS, repo_root=ROOT)
ok("the named check becomes a command the run will actually perform",
   result["add"] == [["python", "tests/test_awakening.py"]], str(result["add"]))
ok("nothing is reported unverifiable when the check can simply be run",
   result["unverifiable"] == [], str(result["unverifiable"]))

already = derive_checks(
    ["Must leave tests/test_coding_agent.py green"], DEFAULT_COMMANDS, repo_root=ROOT,
)
ok("a check the run already performs is not added twice", already["add"] == [], str(already["add"]))
ok("covered_by sees through the command's own path form",
   covered_by(["python", "-m", "pytest", "tests/test_awakening.py"], "tests/test_awakening.py"))
ok("command_for emits the policy-allowed shape",
   command_for("tests/x.py") == ["python", "tests/x.py"])

# An item whose deliverable *is* the test names a file that does not exist yet. That is not an
# authoring error -- run 10 was exactly this shape -- so the check is still scheduled and the
# owner is warned, rather than the item being refused.
pending = derive_checks(SESSION_10, DEFAULT_COMMANDS, repo_root=ROOT)
ok("a test the run must create is still scheduled",
   pending["add"] == [["python", "tests/test_task_classifier.py"]], str(pending["add"]))
ok("creating the named test is a warning, not a refusal",
   pending["pending"] == ["tests/test_task_classifier.py"] and pending["unverifiable"] == [],
   f"pending={pending['pending']} unverifiable={pending['unverifiable']}")

escaped = derive_checks(
    ["Must leave ../../elsewhere/tests/test_outside.py green"], DEFAULT_COMMANDS, repo_root=ROOT,
)
ok("a check outside the repository is unverifiable, not scheduled",
   escaped["add"] == [] and len(escaped["unverifiable"]) == 1,
   f"add={escaped['add']} unverifiable={escaped['unverifiable']}")


def _deny(argv):
    raise RuntimeError(f"executable {argv[0]} is not permitted")


denied = derive_checks(SESSION_14, DEFAULT_COMMANDS, repo_root=ROOT, assert_command=_deny)
ok("a check the policy forbids is unverifiable, not scheduled",
   denied["add"] == [] and [item[0] for item in denied["unverifiable"]] == ["tests/test_awakening.py"],
   f"add={denied['add']} unverifiable={denied['unverifiable']}")


# --- the wiring, end to end through preflight -------------------------------------------
# The helper being right proves nothing on its own: the defect was that nothing called it.
class _Assessment:
    def to_dict(self) -> dict:
        return {"route": "direct", "risk": "low", "score": 90, "sprints": [{"sequence": 1}]}


class _Assessor:
    def assess(self, **_kwargs) -> _Assessment:
        return _Assessment()


class _Worker:
    def probe(self, slug: str, active: bool = False) -> dict:
        return {"slug": slug, "name": slug,
                "adapter": "model_review" if slug == "reviewer-default" else "native",
                "model": "test-model", "health_status": "ready", "health_detail": "available"}


base = ROOT / ".tobi" / "test-runs"
base.mkdir(parents=True, exist_ok=True)
sandbox = Path(tempfile.mkdtemp(prefix="criteria_evidence_", dir=base))


def _preflight(criteria: list[str], *, create: str | None = None,
               configured: list[list[str]] | None = None) -> dict:
    """Run the real preflight against a throwaway repo root and return its report."""
    root = Path(tempfile.mkdtemp(dir=sandbox))
    if create:
        target = root / create
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("print('green')\n", encoding="utf-8")
    plan = root / "WORK_PLAN.md"
    plan.write_text("# Work\n\n## Acceptance Criteria\n" +
                    "".join(f"- {line}\n" for line in criteria), encoding="utf-8")

    data = json.loads((ROOT / "config" / "coding_policy.v1.json").read_text(encoding="utf-8"))
    data["repository"]["allowed_repository"] = ""
    data["repository"]["allowed_remote_suffix"] = ""
    data["commands"]["mandatory_checks"] = [["python", "-m", "compileall", "-q", "core"]]

    store = DevelopmentStore(root / "developer.db")
    task = store.upsert_task({
        "queue_id": 41, "title": "Evidence", "plan_path": plan.name,
        "plan_hash": hashlib.sha256(plan.read_bytes()).hexdigest(),
        "acceptance_criteria": criteria, "dependencies": [], "status": "planned", "risk": "low",
    })
    previous = coding_completion.REPO_ROOT
    coding_completion.REPO_ROOT = root
    try:
        service = CodingCompletionService(
            store=store, policy=CodingPolicy(data, repo_root=root),
            worker=_Worker(), assessor=_Assessor(),
        )
        return service.preflight(
            int(task["queue_id"]), active_probe=False, validation_commands=configured,
        )
    finally:
        coding_completion.REPO_ROOT = previous


report = _preflight(SESSION_14, create="tests/test_awakening.py")
ok("preflight schedules the check the criteria name",
   ["python", "tests/test_awakening.py"] in [list(c) for c in report["validation_commands"]],
   str(report["validation_commands"]))
ok("the run stays ready once its evidence can be produced", report["ready"],
   str([item["code"] for item in report["blockers"]]))

# The readiness snapshot is what create_workflow copies into the session, so the derived check
# has to survive the round trip -- otherwise the run still would not perform it.
persisted = json.dumps(report["validation_commands"])
ok("the scheduled check reaches the snapshot the run is built from",
   "tests/test_awakening.py" in persisted, persisted)

blocked = _preflight(["Must leave ../../elsewhere/tests/test_outside.py green"])
ok("preflight refuses an item whose evidence no permitted check can produce",
   not blocked["ready"] and "criterion_not_verifiable" in {i["code"] for i in blocked["blockers"]},
   str([item["code"] for item in blocked["blockers"]]))

warned = _preflight(SESSION_10)
ok("an item that must create its own test is allowed to start",
   warned["ready"] and "criterion_check_pending" in {i["code"] for i in warned["warnings"]},
   f"ready={warned['ready']} warnings={[i['code'] for i in warned['warnings']]}")

owner_set = _preflight(
    SESSION_14, create="tests/test_awakening.py",
    configured=[["python", "tests/test_awakening.py"]],
)
scheduled = [list(c) for c in owner_set["validation_commands"]]
ok("an owner-supplied check is not duplicated by derivation",
   scheduled.count(["python", "tests/test_awakening.py"]) == 1, str(scheduled))

shutil.rmtree(sandbox, ignore_errors=True)

print(f"\n{'ALL' if not FAILURES else str(len(FAILURES)) + ' OF'} "
      f"{'CRITERIA EVIDENCE CHECKS PASSED' if not FAILURES else 'CHECKS FAILED: ' + ', '.join(FAILURES)}")
raise SystemExit(1 if FAILURES else 0)

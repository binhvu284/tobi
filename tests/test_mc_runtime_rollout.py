"""Acceptance checks for #21 T14 staged activation and rollback."""
from __future__ import annotations

import hashlib
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TMP = tempfile.mkdtemp(prefix="tobi_t14_")
os.environ["DB_PATH"] = os.path.join(TMP, "agent.db")

from core import owner_flags  # noqa: E402
from core.database import get_connection, init_database  # noqa: E402
from core.runtime import config  # noqa: E402
from core.runtime.contracts import EvalRun, EvalStatus  # noqa: E402
from core.runtime.evals import EvalRepository  # noqa: E402
from core.runtime.rollout import (  # noqa: E402
    ROLLOUT_STAGES,
    RolloutConflictError,
    RolloutController,
    RolloutObservation,
)
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from api.routers.runtime import router as runtime_router  # noqa: E402


PASS = 0


def ok(name: str, condition: bool, detail="") -> None:
    global PASS
    if not condition:
        print(f"FAIL {name}: {detail}")
        raise SystemExit(1)
    PASS += 1
    print(f"PASS {name}")


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def observation(*, latency: int = 100) -> RolloutObservation:
    return RolloutObservation(
        route="direct",
        manifest_digest=digest("manifest-v1"),
        policy="allow",
        outcome="succeeded",
        latency_ms=latency,
        evidence_refs=("test:t14",),
    )


def raises(error_type: type[Exception], callback) -> bool:
    try:
        callback()
    except error_type:
        return True
    return False


def query(sql: str, parameters: tuple = ()):
    conn = get_connection()
    try:
        return conn.execute(sql, parameters).fetchall()
    finally:
        conn.close()


def mutate_comparison_history() -> None:
    conn = get_connection()
    try:
        conn.execute("UPDATE mc_rollout_comparisons SET passed=0")
        conn.commit()
    finally:
        conn.close()


init_database()
controller = RolloutController()
ok("T14 migration adds immutable comparison history", bool(query(
    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='mc_rollout_comparisons'"
)))
ok("all rollout controls default safe", controller.status()["stage"] == "shadow" and not controller.status()["rollback"] and config.gateway_mode() == "off")

evals = EvalRepository()
for case in evals.ensure_default_cases():
    required = tuple(case["required_evidence"])
    evals.record_run(EvalRun(
        eval_run_id=f"t14-{case['eval_case_id']}",
        eval_case_id=case["eval_case_id"],
        eval_case_version=case["version"],
        status=EvalStatus.PASSED,
        threshold=float(case["threshold"]),
        score=1.0,
        artifact_refs=required,
        started_at="2026-08-20T03:00:00Z",
        completed_at="2026-08-20T03:01:00Z",
    ))

ok("a stage is blocked before seven consecutive matches", not controller.decision("direct_chat").allowed)
for index in range(6):
    controller.compare(f"direct-{index}", "direct_chat", observation(), observation(latency=110))
ok("six matches are still blocked", not controller.decision("direct_chat").allowed)
controller.compare("direct-6", "direct_chat", observation(), observation(latency=110))
ok("seven matches open the first stage", controller.decision("direct_chat").allowed)
controller.activate("direct_chat")
ok("direct Chat activation sets only its required runtime flags", config.gateway_mode() == "on" and owner_flags.get_bool(owner_flags.RUNTIME_V2_CHAT_EXECUTION) and not owner_flags.get_bool(owner_flags.RUNTIME_V2_AGENT_EXECUTION))

controller.compare("read-fail", "read_chat", observation(), observation(latency=1000))
for index in range(7):
    controller.compare(f"read-{index}", "read_chat", observation(), observation(latency=105))
ok("a failure falls outside the new seven-pass streak", controller.decision("read_chat").allowed and controller.decision("read_chat").consecutive_passes == 7)
controller.activate("read_chat")
ok("read stage enables shared context after direct Chat", owner_flags.get_bool(owner_flags.RUNTIME_V2_CONTEXT))

for stage in ("actions", "agent"):
    for index in range(7):
        controller.compare(f"{stage}-{index}", stage, observation(), observation(latency=115))
    ok(f"{stage} has seven consecutive local passes", controller.decision(stage).allowed)
    controller.activate(stage)

ok("stages cannot be skipped or moved backward", raises(ValueError, lambda: controller.activate("read_chat")))
ok("actions and Agent flags activate only after prior stages", owner_flags.get_bool(owner_flags.RUNTIME_V2_TOOLS) and owner_flags.get_bool(owner_flags.RUNTIME_V2_POLICY) and owner_flags.get_bool(owner_flags.RUNTIME_V2_AGENT_EXECUTION))

controller.rollback(actor="owner")
ok("one rollback switch returns new work to shadow while preserving stage", config.gateway_mode() == "shadow" and controller.status()["stage"] == "agent")
ok("comparison history survives rollback", len(query("SELECT comparison_id FROM mc_rollout_comparisons")) == 29)
controller.resume(actor="owner")
ok("resume rechecks evidence and restores staged execution", config.gateway_mode() == "on" and not controller.status()["rollback"])

same = controller.compare("agent-6", "agent", observation(), observation(latency=115))
ok("exact comparison replay is idempotent", same["comparison_id"] == "agent-6")
ok("changed comparison identity fails closed", raises(RolloutConflictError, lambda: controller.compare("agent-6", "agent", observation(), observation(latency=116))))
ok("comparison rows contain references and hashes but no raw bodies", all(
    forbidden not in str(query("PRAGMA table_info(mc_rollout_comparisons)"))
    for forbidden in ("prompt", "response", "secret", "raw_error", "tool_output")
))
ok("comparison history is database-immutable", raises(sqlite3.IntegrityError, mutate_comparison_history))
ok("the four rollout stages remain ordered", ROLLOUT_STAGES == ("direct_chat", "read_chat", "actions", "agent"))

source = (ROOT / "api" / "routers" / "runtime.py").read_text(encoding="utf-8")
ok("runtime API exposes rollout status and owner commands", all(path in source for path in (
    "/api/runtime/rollout", "/activate", "/rollback", "/resume",
)))
ok("rollout mutations require the owner vault session", "_vault_guard(x_vault_session)" in source)
test_app = FastAPI()
test_app.include_router(runtime_router)
client = TestClient(test_app)
ok("unauthenticated rollback is rejected by the live route", client.post(
    "/api/runtime/rollout/rollback"
).status_code == 401)

print(f"PASS: {PASS} T14 staged rollout checks")

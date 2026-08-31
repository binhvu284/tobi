"""Red-first checks for #35/T01 Agent registry and Evolution truth."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TMP = tempfile.mkdtemp(prefix="tobi_agent_tier_registry_")
os.environ["DB_PATH"] = os.path.join(TMP, "agent.db")

from core.database import get_connection, init_database  # noqa: E402

init_database()

from api.routers import evolution  # noqa: E402
from core import agent_tier  # noqa: E402
from tobival.agent_tier_baseline import (  # noqa: E402
    baseline_acceptance_path,
    baseline_artifact_path,
    load_baseline_acceptance,
)


PASS = 0
NOW = datetime(2026, 8, 30, 8, 37, 30, tzinfo=timezone.utc)
RELEASE = "3.0"


def ok(name: str, condition: bool, detail: str = "") -> None:
    global PASS
    if not condition:
        raise AssertionError(f"{name}: {detail}")
    PASS += 1
    print(f"PASS {name}")


def raises(name: str, call) -> None:
    try:
        call()
    except agent_tier.AgentTierEvidenceError:
        ok(name, True)
    else:
        ok(name, False, "expected AgentTierEvidenceError")


acceptance = load_baseline_acceptance()
artifact_path = baseline_artifact_path("fc4d6d798aa2af3fe0c59a1467bd1297a73884ff")
ok("owner acceptance is stored separately from the immutable baseline", (
    acceptance is not None
    and acceptance["accepted"] is True
    and acceptance["artifact_sha256"] == hashlib.sha256(artifact_path.read_bytes()).hexdigest()
    and baseline_acceptance_path(acceptance["production_commit"]).name == "owner-acceptance.json"
))

with tempfile.TemporaryDirectory(prefix="agent_tier_acceptance_tamper_") as tamper_tmp:
    tampered_artifact = Path(tamper_tmp) / "unchanged-baseline.json"
    tampered_acceptance = Path(tamper_tmp) / "owner-acceptance.json"
    tampered_artifact.write_bytes(artifact_path.read_bytes() + b"\n")
    tampered_acceptance.write_bytes(
        baseline_acceptance_path(acceptance["production_commit"]).read_bytes()
    )
    ok("changed baseline bytes invalidate owner acceptance", (
        load_baseline_acceptance(tampered_artifact, tampered_acceptance) is None
    ))

ok("registry owns exactly the seven frozen Agent abilities", (
    set(agent_tier.ABILITY_IDS) == {
        "grounded_task_intake", "bounded_workflow_planning", "local_work_execution",
        "browser_external_action", "durable_recovery", "verified_delivery",
        "proactive_delivery",
    }
    and len(agent_tier.ABILITY_IDS) == 7
))
ok("registry owns exactly the five frozen workflow families", (
    len(agent_tier.FAMILY_IDS) == 5
    and set(agent_tier.FAMILY_IDS) == {
        "project_execution", "local_diagnosis", "coding_maintenance", "browser_work",
        "github_monitoring_action",
    }
))

conn = get_connection()
empty = agent_tier.summary(conn, current_release=RELEASE, now=NOW)
ok("code and tool presence alone cannot activate Agent abilities", (
    empty["active_count"] == 0 and empty["progress_pct"] == 0 and empty["complete"] is False
))
empty_rows = agent_tier.evaluate(conn, current_release=RELEASE, now=NOW)
ok("empty evidence explains missing proof and the next owner action", all(
    row["status"] != "active"
    and row["missing"]
    and row["freshness"]["state"] == "missing"
    and row["next_action"]
    for row in empty_rows
))

raises("unknown ability evidence is rejected", lambda: agent_tier.record_evidence(
    conn, ability_id="invented", family_id="project_execution", evidence_type="typed_request",
    evidence_ref="run:unknown", source_release=RELEASE, observed_at=NOW,
))
raises("raw or secret-like evidence references are rejected", lambda: agent_tier.record_evidence(
    conn, ability_id="grounded_task_intake", family_id="project_execution",
    evidence_type="typed_request", evidence_ref="raw_prompt:owner secret",
    source_release=RELEASE, observed_at=NOW,
))

contract = agent_tier.contract("grounded_task_intake")
first_family = contract["required_families"][0]
first_type = contract["required_evidence"][0]
receipt = agent_tier.record_evidence(
    conn, ability_id=contract["id"], family_id=first_family, evidence_type=first_type,
    evidence_ref="run:intake-one", source_release=RELEASE, observed_at=NOW,
)
same_receipt = agent_tier.record_evidence(
    conn, ability_id=contract["id"], family_id=first_family, evidence_type=first_type,
    evidence_ref="run:intake-one", source_release=RELEASE, observed_at=NOW,
)
ok("replaying the same proof is idempotent", (
    receipt["evidence_id"] == same_receipt["evidence_id"]
    and conn.execute("SELECT COUNT(*) FROM agent_tier_evidence").fetchone()[0] == 1
))
partial = next(row for row in agent_tier.evaluate(
    conn, current_release=RELEASE, now=NOW
) if row["id"] == contract["id"])
ok("one receipt cannot overclaim a complete ability", (
    partial["status"] == "partial" and partial["missing"]
))

for family_id in contract["required_families"]:
    for evidence_type in contract["required_evidence"]:
        agent_tier.record_evidence(
            conn, ability_id=contract["id"], family_id=family_id,
            evidence_type=evidence_type,
            evidence_ref=f"trace:{family_id}:{evidence_type}", source_release=RELEASE,
            observed_at=NOW,
        )
active = next(row for row in agent_tier.evaluate(
    conn, current_release=RELEASE, now=NOW
) if row["id"] == contract["id"])
ok("all required current-release proof activates one ability", (
    active["status"] == "active" and active["missing"] == []
    and active["freshness"]["state"] == "current"
))
old_release = next(row for row in agent_tier.evaluate(
    conn, current_release="3.1", now=NOW
) if row["id"] == contract["id"])
ok("a new release makes old release-bound proof stale", (
    old_release["status"] != "active" and old_release["freshness"]["state"] == "stale"
))

external = agent_tier.contract("browser_external_action")
for family_id in external["required_families"]:
    for evidence_type in external["required_evidence"]:
        agent_tier.record_evidence(
            conn, ability_id=external["id"], family_id=family_id,
            evidence_type=evidence_type,
            evidence_ref=f"artifact:stale:{family_id}:{evidence_type}", source_release=RELEASE,
            observed_at=NOW - timedelta(days=2),
        )
stale = next(row for row in agent_tier.evaluate(
    conn, current_release=RELEASE, now=NOW
) if row["id"] == external["id"])
ok("24-hour external proof expires instead of remaining active", (
    stale["status"] != "active" and stale["freshness"]["state"] == "stale"
))

legacy_statuses = {
    ability["id"]: True
    for tier in evolution._TIER_DEFINITIONS
    for abilities in tier["pillars"].values()
    for ability in abilities
}
tiers, _unlocked = evolution._build_evo_response(legacy_statuses, {}, conn)
tier2 = next(tier for tier in tiers if tier["id"] == 2)
tier2_rows = [ability for rows in tier2["pillars"].values() for ability in rows]
ok("Evolution Tier II ignores the legacy static detector", (
    len(tier2_rows) == 7
    and {row["id"] for row in tier2_rows} == set(agent_tier.ABILITY_IDS)
    and tier2["active_count"] == 1
))

original_get_conn = evolution._get_conn
evolution._get_conn = lambda: get_connection()
try:
    report = asyncio.run(evolution.get_evolution())
finally:
    evolution._get_conn = original_get_conn
agent_report = next(tier for tier in report["tiers"] if tier["id"] == 2)
ok("the Evolution API projects registry evidence and freshness", all(
    "evidence" in row and "missing" in row and "freshness" in row and "next_action" in row
    for rows in agent_report["pillars"].values() for row in rows
))

client_source = (ROOT / "dashboard/src/api.abilities.ts").read_text(encoding="utf-8")
page_source = (ROOT / "dashboard/src/pages/Evolution.tsx").read_text(encoding="utf-8")
ok("the dashboard contract carries Agent evidence truth", all(
    marker in client_source for marker in ("freshness", "next_action", "last_verified_at")
))
ok("Evolution shows freshness, missing proof, and the next action", all(
    marker in page_source for marker in ("Freshness", "What's missing", "Next action")
))

conn.close()
print(f"PASS: {PASS} Agent Tier T01 registry checks")

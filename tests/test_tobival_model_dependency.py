"""Acceptance checks for #34/T08 canonical model-dependency proof."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TMP = tempfile.mkdtemp(prefix="tobival_t08_")
os.environ["DB_PATH"] = os.path.join(TMP, "agent.db")

from core.chat_runtime import TurnRequest, route_turn  # noqa: E402
from tobival.acceptance import run_final_acceptance  # noqa: E402
from tobival.metrics import calculate_unguarded_decision_share  # noqa: E402


PASS = 0


def ok(name: str, condition: bool, detail: object = "") -> None:
    global PASS
    if not condition:
        print(f"FAIL {name}: {detail}")
        raise SystemExit(1)
    PASS += 1
    print(f"PASS {name}")


class BrokenModelClient:
    on_subscription = True

    def __init__(self) -> None:
        self.last_usage = {"prompt_tokens": 7, "completion_tokens": 2}

    def complete(self, *_args, **_kwargs) -> str:
        return "{}"


report = run_final_acceptance(client_factory=lambda _model_id: BrokenModelClient())

ok("final acceptance is backed by canonical Runtime execution", (
    report["schema_version"] == "tobival.final-acceptance.v2"
    and report["evidence_scope"] == "canonical_runtime"
    and all(row["run_id"] and row["trace_ref"] for row in report["results"])
))

provenance = report["decision_provenance"]
ok("all five frozen decision stages come from recorded provenance", (
    len(provenance) == report["case_count"]
    and all(
        set(row["stages"]) == {
            "route", "workflow_tools", "entity_arguments",
            "result_verification", "owner_response",
        }
        and set(row["no_model_pass"]) == set(row["stages"])
        and len(row["evidence_refs"]) == 5
        for row in provenance
    )
    and calculate_unguarded_decision_share(provenance)
        == report["metrics"]["unguarded_decision_share"]
    and report["metrics"]["ldr_source"] == "canonical_decision_provenance"
))

quality = report["model_quality"]
ok("raw model quality stays visible beside deterministic recovery", (
    quality == {
        "attempts": 156,
        "raw_passes": 0,
        "raw_failures": 156,
        "raw_pass_rate": 0.0,
        "model_responses": 156,
        "response_rate": 100.0,
        "provider_failures": 0,
        "recoveries": 156,
        "recovery_rate": 100.0,
    }
    and report["lanes"]["strong"]["completion_rate"] == 100.0
    and report["lanes"]["weak"]["completion_rate"] == 100.0
))


class UnreachableModelClient(BrokenModelClient):
    def complete(self, *_args, **_kwargs) -> str:
        raise ConnectionError("provider unavailable")


unreachable = run_final_acceptance(
    client_factory=lambda _model_id: UnreachableModelClient(),
)
ok("provider transport failure cannot masquerade as model-quality proof", (
    unreachable["release_ready"] is False
    and "model-quality-proof-missing" in unreachable["blockers"]
    and unreachable["model_quality"]["model_responses"] == 0
    and unreachable["model_quality"]["provider_failures"] == 156
))

decision = route_turn(
    TurnRequest(session_id="t08", message="Show my projects.", mode="chat"),
    "PROJECT_MGMT",
)
ok("production Chat uses the frozen deterministic workflow boundary", (
    decision.route == "read"
    and decision.allowed_tools == ("list_projects",)
    and "workflow=project.list@v1" in decision.reason
))

print(f"PASS: {PASS} TOBIval T08 model-dependency checks")

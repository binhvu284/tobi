"""Focused Office V3 backend checks. Plain Python, isolated SQLite database."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_TMP = tempfile.mkdtemp(prefix="tobi_office_v3_")
os.environ["DB_PATH"] = os.path.join(_TMP, "agent.db")

from core import conductor, database, office_artifacts as office  # noqa: E402


PASS = 0


def ok(label: str, condition, detail=""):
    global PASS
    if not condition:
        raise AssertionError(f"{label}: {detail}")
    PASS += 1
    print(f"PASS {label}")


database.init_database()
office.ensure_schema()

ok("Office V3 defaults enabled", office.v3_enabled() is True)
ok("Office V3 rollback flag disables", office.set_v3_enabled(False) is False and office.v3_enabled() is False)
ok("Office V3 rollback flag restores", office.set_v3_enabled(True) is True and office.v3_enabled() is True)

created = office.create_artifact("Launch report", "report", "Sensitive owner strategy", source_type="mission", source_id=1)
ok("artifact creates locally", created.get("ok") and created["artifact"]["sensitivity"] == "sensitive", created)
aid = created["artifact"]["id"]
listed = office.list_artifacts()
ok("artifact list returns preview only", listed and "content" not in listed[0] and listed[0]["preview"], listed)
ok("artifact detail returns content", office.get_artifact(aid)["content"] == "Sensitive owner strategy")
activity = office.list_activity()
ok("activity summary does not leak artifact content", all("Sensitive owner strategy" not in json.dumps(row) for row in activity))

updated = office.update_artifact(aid, title="Launch plan", kind="plan", content="Revised sensitive plan")
ok("artifact update stores latest only", updated.get("ok") and updated["artifact"]["title"] == "Launch plan", updated)

office_tools = {
    "office_create_artifact", "office_update_artifact", "office_delete_artifact",
    "office_create_mission", "office_run_mission", "office_control_mission",
    "office_convert_to_tasks",
}
ok("all Office mutation tools are registered", office_tools <= set(conductor.ACT_TOOLS))
ok("all Office mutation tools require confirmation", all(conductor.ACT_TOOLS[name][1] == "high" for name in office_tools))

proposal = conductor.propose_action("office_create_artifact", {
    "title": "Confirmed brief", "kind": "summary", "content": "Owner approved content",
    "source_type": "tobi",
}, surface="office")
ok("Office mutation creates global proposed action", proposal.get("status") == "proposed", proposal)
conn = database.get_connection()
logged_args = conn.execute("SELECT args_json FROM tobi_actions WHERE id=?", (proposal["id"],)).fetchone()[0]
conn.close()
ok("global Actions log excludes sensitive artifact content",
   "Owner approved content" not in logged_args and "office_payload_id" in logged_args, logged_args)
confirmed = conductor.confirm_action(proposal["id"], "approve", surface="office")
ok("confirmed Office action executes", confirmed.get("ok") and confirmed.get("status") == "executed", confirmed)
ok("confirmed artifact is persisted", any(row["title"] == "Confirmed brief" for row in office.list_artifacts()))

mission_proposal = conductor.propose_action("office_create_mission", {
    "title": "Prepare launch report", "goal": "Return a concise plan", "priority": "High",
}, surface="office")
mission_confirmed = conductor.confirm_action(mission_proposal["id"], "approve", surface="office")
ok("confirmed mission creation works", mission_confirmed.get("result", {}).get("mission_id"), mission_confirmed)
ok("mission mutation appears in Office activity", any(row["event_type"] == "mission.created" for row in office.list_activity()))

deleted_proposal = conductor.propose_action("office_delete_artifact", {"artifact_id": aid}, surface="office")
ok("artifact deletion waits for confirmation", office.get_artifact(aid) is not None)
conductor.confirm_action(deleted_proposal["id"], "reject", surface="office")
ok("rejected deletion changes nothing", office.get_artifact(aid) is not None)

manifest = office.context_manifest(artifact_id=aid)
ok("selected artifact is explicit TOBI context", manifest["labels"] and "Revised sensitive plan" in manifest["text"])

print(f"ALL {PASS} OFFICE V3 CHECKS PASSED")

"""Acceptance checks for #21 T11A System Model and Atlas data foundation."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TMP = tempfile.mkdtemp(prefix="tobi_t11a_")
os.environ["DB_PATH"] = os.path.join(TMP, "agent.db")

from core.database import get_connection, init_database  # noqa: E402
from core.runtime.contracts import SystemEdge, SystemEntity, SystemEntityType  # noqa: E402
from core.runtime.event_store import EventConflictError  # noqa: E402
from core.runtime.projections import rebuild_system_projection  # noqa: E402
from core.runtime.system_model import SystemModelRepository, SystemModelValidationError  # noqa: E402


PASS = 0


def ok(name: str, condition: bool, detail: str = "") -> None:
    global PASS
    if not condition:
        print(f"FAIL {name}: {detail}")
        raise SystemExit(1)
    PASS += 1
    print(f"PASS {name}")


def raises(error_type: type[Exception], callback) -> bool:
    try:
        callback()
    except error_type:
        return True
    return False


def entity(kind: SystemEntityType, number: int) -> SystemEntity:
    return SystemEntity(
        entity_id=f"entity-{number}",
        entity_type=kind,
        canonical_key=f"{kind.value}:fixture-{number}",
        name=f"Fixture {kind.value}",
        status="known",
        version="1",
        owner_domain="mission-control",
        source_ref=f"source:test:{number}",
        observed_at=f"2026-08-20T00:{number:02d}:00Z",
        metadata={"evidence_ref": f"evidence:test:{number}", "api_key": "sk-never-store"},
    )


init_database()
model = SystemModelRepository()
stored = []
for number, kind in enumerate(SystemEntityType, start=1):
    stored.append(model.upsert_entity(entity(kind, number)))

ok("every required System entity type is representable", {item["entity_type"] for item in stored} == {kind.value for kind in SystemEntityType})
ok("entity metadata is redacted before storage", "sk-never-store" not in json.dumps(stored, sort_keys=True))
ok("read model filters by typed entity kind", len(model.list_entities(entity_type=SystemEntityType.CAPABILITY)) == 1)

by_type = {item["entity_type"]: item for item in stored}
capability = by_type["capability"]
limitation = by_type["limitation"]
risk = by_type["risk"]
model.upsert_edge(SystemEdge(
    edge_id="edge-capability-limitation",
    from_entity_id=capability["entity_id"],
    edge_type="limited_by",
    to_entity_id=limitation["entity_id"],
    version="1",
    evidence_refs=("evidence:test:limitation",),
))
model.upsert_edge(SystemEdge(
    edge_id="edge-capability-risk",
    from_entity_id=capability["entity_id"],
    edge_type="exposed_to",
    to_entity_id=risk["entity_id"],
    version="1",
    evidence_refs=("evidence:test:risk",),
))
view = model.get_entity(capability["entity_id"], include_edges=True)
ok("capability links to evidence-backed limitations and risks", view is not None and {edge["edge_type"] for edge in view["edges"]} == {"limited_by", "exposed_to"})
ok("dangling relationship fails closed", raises(SystemModelValidationError, lambda: model.upsert_edge(SystemEdge(edge_id="dangling", from_entity_id="missing", edge_type="depends_on", to_entity_id=capability["entity_id"], version="1", evidence_refs=("evidence:test",)))))
ok("relationship without evidence fails closed", raises(SystemModelValidationError, lambda: model.upsert_edge(SystemEdge(edge_id="no-evidence", from_entity_id=capability["entity_id"], edge_type="depends_on", to_entity_id=risk["entity_id"], version="1"))))

same = model.upsert_entity(entity(SystemEntityType.CAPABILITY, 3))
ok("exact entity version replay is idempotent", same["entity_id"] == capability["entity_id"])
changed = SystemEntity(**{**entity(SystemEntityType.CAPABILITY, 3).__dict__, "name": "Changed capability"})
ok("changed content cannot reuse entity version", raises(EventConflictError, lambda: model.upsert_entity(changed)))

before = model.snapshot()
conn = get_connection()
conn.execute("DELETE FROM mc_system_edges")
conn.execute("DELETE FROM mc_system_entities")
conn.commit()
conn.close()
rebuilt = rebuild_system_projection()
after = model.snapshot()
ok("current System rows rebuild from append-only history", before == after and rebuilt["state"]["last_sequence"] > 0)
ok("System projection is deterministic", rebuilt["state_hash"] == rebuild_system_projection()["state_hash"])

source = (ROOT / "core" / "runtime" / "system_model.py").read_text(encoding="utf-8")
ok("System Model has no execution authority", "tool_execution" not in source and "transition_run" not in source and "CodingWorker" not in source)

print(f"PASS: {PASS} T11A System Model checks")

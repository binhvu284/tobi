"""Acceptance checks for #21 T15 compatibility surface adapters."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TMP = tempfile.mkdtemp(prefix="tobi_t15_")
os.environ["DB_PATH"] = os.path.join(TMP, "agent.db")

from core import owner_flags  # noqa: E402
from core.database import get_connection, init_database  # noqa: E402
from core.runtime.event_store import list_run_events  # noqa: E402
from core.runtime.surface_adapter import (  # noqa: E402
    COMPATIBILITY_SURFACES,
    SurfaceRuntimeAdapter,
)
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from api.runtime_surface import RuntimeSurfaceMiddleware  # noqa: E402


PASS = 0


def ok(name: str, condition: bool, detail="") -> None:
    global PASS
    if not condition:
        print(f"FAIL {name}: {detail}")
        raise SystemExit(1)
    PASS += 1
    print(f"PASS {name}")


def query(sql: str, parameters: tuple = ()):
    conn = get_connection()
    try:
        return conn.execute(sql, parameters).fetchall()
    finally:
        conn.close()


init_database()
adapter = SurfaceRuntimeAdapter()
ok("the five remaining surfaces are explicit", COMPATIBILITY_SURFACES == (
    "projects", "office", "cli", "telegram", "scheduler",
))

off = adapter.accept(
    surface="projects", operation="get.project", request_id="off-project",
    session_id="api", actor="api",
)
ok("adapters default off without creating canonical work", off.mode == "off" and off.run_id is None and not query("SELECT 1 FROM mc_runs"))

owner_flags.set_bool(owner_flags.RUNTIME_V2_EVENTS, True)
accepted = {}
for surface in COMPATIBILITY_SURFACES:
    item = adapter.accept(
        surface=surface,
        operation=f"observe.{surface}",
        request_id=f"t15-{surface}",
        session_id=f"session-{surface}",
        actor=f"{surface}-adapter",
    )
    adapter.observe(item, outcome="succeeded", evidence_refs=(f"legacy:{surface}:ok",))
    accepted[surface] = item

ok("every remaining surface creates one canonical shadow run", len(query(
    "SELECT run_id FROM mc_runs"
)) == 5 and all(item.mode == "shadow" and item.run_id for item in accepted.values()))
ok("all compatibility policies remain non-executing", all(row[0] == 0 for row in query(
    "SELECT enabled FROM mc_loop_runs"
)))
ok("each adapter records an ordered bounded outcome reference", all(
    [event.event_type for event in list_run_events(item.run_id or "")][-1]
    == "shadow.surface_completed" for item in accepted.values()
))
project_event_count = len(list_run_events(accepted["projects"].run_id or ""))
adapter.safe_observe(
    accepted["projects"], outcome="failed", evidence_refs=("legacy:projects:failed",),
)
ok("the first terminal surface outcome remains authoritative", len(
    list_run_events(accepted["projects"].run_id or "")
) == project_event_count)
ok("exact adapter delivery reuses one canonical run", adapter.accept(
    surface="projects", operation="observe.projects", request_id="t15-projects",
    session_id="session-projects", actor="projects-adapter",
).run_id == accepted["projects"].run_id)
ok("unsafe adapter input fails without entering history", adapter.safe_accept(
    surface="projects", operation="raw request body", request_id="unsafe",
    session_id="api", actor="api",
) is None and len(query("SELECT run_id FROM mc_runs")) == 5)
ok("adapter history contains no caller body fields", all(
    forbidden not in str(query("SELECT request_json FROM mc_runs"))
    for forbidden in ("prompt", "response", "secret", "raw_error", "tool_output")
))

web_app = FastAPI()
web_app.add_middleware(RuntimeSurfaceMiddleware)


@web_app.post("/api/pm/projects/{project_id}")
def project_write(project_id: int):
    return {"project_id": project_id}


@web_app.get("/api/office/stats")
def office_poll():
    return {"ok": True}


@web_app.post("/api/pmtime")
def similarly_named_route():
    return {"ok": True}


client = TestClient(web_app)
before_http = len(query("SELECT run_id FROM mc_runs"))
response = client.post(
    "/api/pm/projects/42",
    headers={"Idempotency-Key": "t15-http-project"},
    json={"secret": "never-store-this"},
)
after_http = len(query("SELECT run_id FROM mc_runs"))
client.get("/api/office/stats")
ok("live HTTP middleware tracks a Project write", response.status_code == 200 and after_http == before_http + 1)
ok("HTTP adapter ignores request bodies and routine polling reads", "never-store-this" not in str(
    query("SELECT request_json FROM mc_runs")
) and len(query("SELECT run_id FROM mc_runs")) == after_http)
client.post("/api/pmtime")
ok("HTTP adapter matches complete route prefixes only", len(
    query("SELECT run_id FROM mc_runs")
) == after_http)

api_source = (ROOT / "api" / "dashboard.py").read_text(encoding="utf-8")
middleware_source = (ROOT / "api" / "runtime_surface.py").read_text(encoding="utf-8")
main_source = (ROOT / "main.py").read_text(encoding="utf-8")
telegram_source = (ROOT / "core" / "telegram_bot.py").read_text(encoding="utf-8")
scheduler_source = (ROOT / "core" / "scheduled_jobs.py").read_text(encoding="utf-8")
ok("Projects and Office are wired at the shared HTTP boundary", "RuntimeSurfaceMiddleware" in api_source and all(prefix in middleware_source for prefix in ("/api/pm", "/api/office")))
ok("CLI entry commands use the compatibility adapter", "track_async_surface" in main_source and 'surface="cli"' in main_source)
ok("Telegram messages use the compatibility adapter", "track_async_surface" in telegram_source and 'surface="telegram"' in telegram_source)
ok("every registered scheduler callback is tracked", scheduler_source.count(".do(") == 18 and scheduler_source.count("tracked_schedule(") == 19)
ok("legacy retirement remains a separate owner decision", (ROOT / "docs" / "feature-idea-queue" / "MC_V2_LEGACY_EXIT_REVIEW.md").exists())

print(f"PASS: {PASS} T15 surface adapter checks")

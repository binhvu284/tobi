"""Plain-Python API contract checks for the MC chat runtime v2."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_TMP = tempfile.mkdtemp(prefix="tobi_runtime_route_")
os.environ["DB_PATH"] = os.path.join(_TMP, "agent.db")

from fastapi.testclient import TestClient  # noqa: E402
from api.dashboard import app  # noqa: E402
from core import agent_runs, chat_runtime, chat_store, conductor, database  # noqa: E402


def check(label: str, condition: bool, detail=""):
    if not condition:
        raise AssertionError(f"{label}: {detail}")
    print(f"PASS {label}")


client = TestClient(app)
database.init_database()

cfg = client.get("/api/chat/config").json()
check("config exposes runtime mode", cfg.get("chat_runtime_v2") in ("off", "shadow", "on"), cfg)
for mode in ("shadow", "off", "on"):
    out = client.post("/api/chat/config", json={"chat_runtime_v2": mode}).json()
    check(f"runtime flag {mode}", out.get("chat_runtime_v2") == mode, out)

session = chat_store.create_session("runtime route")
old_answer = conductor.answer
conductor.answer = lambda *a, **k: {"reply": "Hello, sir.", "tools_used": [], "streamed": False}
try:
    response = client.post(
        f"/api/chat/sessions/{session['id']}/stream",
        json={"message": "hello", "mode": "chat", "client_turn_id": "route-test-turn"},
    )
finally:
    conductor.answer = old_answer
check("stream route 200", response.status_code == 200, response.text[:500])
check("typed turn_started event", "event: turn_started" in response.text)
check("typed context_ready event", "event: context_ready" in response.text)
check("typed turn_completed event", "event: turn_completed" in response.text)
check("legacy delta preserved", "event: delta" in response.text)
check("legacy done preserved", "event: done" in response.text)

trace_response = client.get("/api/chat/turns/route-test-turn/trace")
trace = trace_response.json()
check("trace endpoint 200", trace_response.status_code == 200, trace)
check("trace has ordered events", [e["seq"] for e in trace["events"]] == sorted(e["seq"] for e in trace["events"]))
check("trace omits prompt body", "message" not in (trace.get("request") or {}), trace.get("request"))

run_id = agent_runs.create_run(session["id"], "recover me")
agent_runs.add_step(run_id, "tool", "failed read", tool="list_projects", risk="read",
                    payload={"tool": "list_projects", "args": {}, "risk": "read", "error": "temporary"},
                    status="failed")
agent_runs.set_status(run_id, "waiting_user", "failed")
command = client.post(f"/api/chat/runs/{run_id}/commands", json={"command": "retry_step"})
payload = command.json()
check("run command 200", command.status_code == 200, payload)
check("run command keeps id", payload.get("run_id") == run_id, payload)
check("run command returns continuation", payload.get("requires_turn") is True and bool(payload.get("recovery_prompt")), payload)

print("ALL CHAT RUNTIME ROUTE CHECKS PASSED")

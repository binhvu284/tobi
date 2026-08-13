"""T09 Run 2: owner memory has bounded influence and turn-linked evidence.

Plain Python, no pytest and no network:
    python tests/test_mc_runtime_owner_intelligence_routing.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import brain_feedback, context_manager, owner_flags  # noqa: E402
from core import chat_runtime  # noqa: E402
from core.chat_runtime_contracts import TurnRequest  # noqa: E402
from core.runtime import owner_intelligence  # noqa: E402


FAILURES: list[str] = []


def ok(name: str, condition: bool, detail: str = "") -> None:
    print(f"{'PASS' if condition else 'FAIL'} {name}")
    if not condition:
        if detail:
            print(f"  {detail}")
        FAILURES.append(name)


def memory(mid: int, **overrides):
    value = {
        "memory_id": mid,
        "text": f"Memory {mid}",
        "behavior_implication": "Use local project evidence and answer concisely.",
        "type": "workflow_standard",
        "authority": "soft",
        "scope": "global",
        "hedged": False,
        "precedence": 6,
        "score": 0.8,
        "signals": {"recency": 0.9},
        "chip": {"memory_id": mid, "text": f"Memory {mid}"},
        "status": "active",
        "sensitive": False,
        "redacted": False,
        "trust": "trusted",
        "explicitness": "explicit",
        "updated_at": "2026-08-14T00:00:00+00:00",
        "provenance_refs": ("conversation:42",),
        "tags": (
            "route:read",
            "tool:list_projects",
            "response:concise",
            "planning:bounded",
        ),
        "suggested_usage": "route,tool,response,planning",
    }
    value.update(overrides)
    return value


def request(message: str, mode: str = "chat", **capabilities) -> TurnRequest:
    return TurnRequest(session_id=1, message=message, mode=mode, capabilities=capabilities)


eligible = owner_intelligence.adapt_retrieval([memory(1)], mode="chat")
ok("eligible memory exposes only the read route hint", eligible.route_hint == "read")
ok("safe local read tool survives", eligible.tool_hints == ("list_projects",))
ok("response style hint is structured", eligible.response_style_hints == ("concise",))
ok("planning hint is structured", eligible.planning_hints == ("bounded",))
ok("prompt says the current request wins", "current request overrides memory" in eligible.prompt_block)

fallback = chat_runtime.route_turn(request("Can you help me with this?"), "QUESTION", eligible)
ok("eligible memory changes only ordinary fallback to read", fallback.route == "read", repr(fallback))
ok("memory fallback exposes only safe local reads", fallback.allowed_tools == ("list_projects",), repr(fallback))

unsafe = owner_intelligence.adapt_retrieval([
    memory(2, tags=(
        "route:read", "tool:run_command", "tool:web_search", "tool:read_github",
        "route:action", "response:impersonate", "planning:unbounded",
    )),
], mode="chat")
ok("unsafe tools are discarded", unsafe.tool_hints == (), repr(unsafe.tool_hints))
ok("unsupported influence hints are discarded", (
    unsafe.response_style_hints == () and unsafe.planning_hints == ()
))
ok("route hint alone cannot change fallback", (
    chat_runtime.route_turn(request("Can you help?"), "QUESTION", unsafe).route == "direct"
))

ok("smalltalk current request wins", (
    chat_runtime.route_turn(request("hello"), "SMALLTALK", eligible).route == "direct"
))
ok("coding current request wins", (
    chat_runtime.route_turn(request("debug this code"), "CODING", eligible).route == "direct"
))
ok("explicit action current request wins", (
    chat_runtime.route_turn(request("create a task in TOBI"), "PROJECT_MGMT", eligible).route == "clarify"
))
current = chat_runtime.route_turn(request("what is the current time?"), "QUESTION", eligible)
ok("explicit current-information route wins", (
    current.route == "read" and current.allowed_tools == ("get_current_datetime",)
), repr(current))

blocked = owner_intelligence.adapt_retrieval([
    memory(3, sensitive=True),
    memory(4, certainty="stale"),
    memory(5, explicitness="inferred", hedged=True),
    memory(6, trust="untrusted"),
], mode="chat")
ok("sensitive stale inferred and imported memories cannot hint", (
    blocked.route_hint is None and blocked.tool_hints == ()
))

calls: list[dict] = []
old_mode = owner_flags.brain_v2_mode
old_profile = context_manager._stable_profile_v2
old_retrieve = owner_intelligence.retrieve_owner_intelligence
old_record = brain_feedback.record_influence
try:
    owner_flags.brain_v2_mode = lambda: "on"
    context_manager._stable_profile_v2 = lambda: ""
    owner_intelligence.retrieve_owner_intelligence = lambda *_a, **_k: (_ for _ in ()).throw(
        AssertionError("pre-routed intelligence must be reused")
    )
    brain_feedback.record_influence = lambda ids, surface, **kwargs: calls.append({
        "ids": ids, "surface": surface, **kwargs,
    }) or len(ids)
    context_manager.invalidate()
    manifest = context_manager.build_manifest(
        "Can you help me with this?",
        "chat",
        [],
        owner_intelligence_context=eligible,
        turn_ref="turn:run-2",
    )
finally:
    owner_flags.brain_v2_mode = old_mode
    context_manager._stable_profile_v2 = old_profile
    owner_intelligence.retrieve_owner_intelligence = old_retrieve
    brain_feedback.record_influence = old_record
    context_manager.invalidate()

recall = next((item for item in manifest.items if item.source == "brain_recall"), None)
runtime_items = list((recall.metadata or {}).get("runtime_items") or []) if recall else []
ok("Context Manager reuses pre-routed intelligence", recall is not None)
ok("influence evidence carries the real turn id", (
    calls and calls[0].get("turn_ref") == "turn:run-2"
), repr(calls))
ok("runtime trace context remains metadata only", (
    runtime_items and all("content" not in item for item in runtime_items)
), repr(runtime_items))

print(f"\n{len(FAILURES)} failures")
raise SystemExit(1 if FAILURES else 0)

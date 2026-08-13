"""T08 Run 4: Conductor delegates one turn through a typed Runtime facade.

Plain Python, no pytest and no network:
    python tests/test_mc_runtime_conductor_facade.py
"""
from __future__ import annotations

import inspect
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.runtime import conductor_facade as facade  # noqa: E402


FAILURES: list[str] = []


def ok(name: str, condition: bool, detail: str = "") -> None:
    print(f"{'PASS' if condition else 'FAIL'} {name}")
    if not condition:
        if detail:
            print(f"  {detail}")
        FAILURES.append(name)


ok("turn request is immutable", facade.ConductorTurnRequest.__dataclass_params__.frozen)
ok("facade bindings are immutable", facade.ConductorFacadeBindings.__dataclass_params__.frozen)

from core import conductor  # noqa: E402

expected_parameters = [
    "message", "chat_id", "surface", "model", "history", "attachments_text", "directives",
    "extra_tools", "on_event", "on_delta", "denied_tools", "review_mode", "mode", "route",
    "allowed_tools", "context_manifest", "turn_id", "max_tool_steps", "step_tokens",
    "final_tokens", "usage_context", "recovery_checkpoint",
]
ok(
    "public answer signature is unchanged",
    list(inspect.signature(conductor.answer).parameters) == expected_parameters,
)
answer_source = inspect.getsource(conductor.answer)
ok("answer delegates through the Runtime facade", "_run_conductor_turn" in answer_source)
ok("answer no longer owns final composition", "def _final" not in answer_source)
ok("answer no longer owns the tool loop", "_run_tool_loop(" not in answer_source)
conductor_source = inspect.getsource(conductor)
ok("legacy answer implementation was removed", "_legacy_answer_reference" not in conductor_source)
ok("Conductor module no longer owns final composition", "def _final" not in conductor_source)
ok("Conductor module no longer calls the tool loop", "_run_tool_loop(" not in conductor_source)

facade_source = inspect.getsource(facade)
ok("Runtime facade does not reverse-import Conductor", "from core import conductor" not in facade_source)

print(f"\n{len(expected_parameters)} answer parameters; {len(FAILURES)} failures")
raise SystemExit(1 if FAILURES else 0)

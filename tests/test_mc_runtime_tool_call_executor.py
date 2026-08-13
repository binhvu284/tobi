"""Behavior checks for Conductor one-call execution extraction."""

from __future__ import annotations

import copy
import inspect
import json
import os
import sys
import tempfile
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import SimpleNamespace

os.environ["DB_PATH"] = os.path.join(
    tempfile.mkdtemp(prefix="tobi_tool_call_executor_"),
    "agent.db",
)

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.runtime import tool_call_executor


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


class _Harness:
    def __init__(self) -> None:
        self.events: list[tuple] = []
        self.validation_error = None
        self.tool_result: dict = {"ok": True, "value": 1}
        self.action_result: dict = {"ok": True, "changed": True}
        self.terminal_result: dict = {"ok": True, "exit_code": 0}
        self.terminal_command: str | None = "echo hi"
        self.terminal_decision = "run"
        self.terminal_risk = "medium"
        self.loaded_receipt: dict | None = None
        self.raise_event = False
        self.raise_log = False

    def validate(self, call, spec, mode, allowed_tools):
        self.events.append(("validate", call, spec, mode, allowed_tools))
        return self.validation_error

    def phase(self, tool):
        self.events.append(("phase", tool))
        return "acting"

    def on_event(self, event):
        self.events.append(("event", event))
        if self.raise_event:
            raise RuntimeError("event sink unavailable")

    def execute_tool(self, call, **kwargs):
        self.events.append(("execute_tool", call, kwargs))
        return self.tool_result

    def terminal_command_for(self, tool, args):
        self.events.append(("terminal_command", tool, args))
        return self.terminal_command

    def terminal_engine_loader(self):
        self.events.append(("terminal_engine",))
        return SimpleNamespace(gate=self.terminal_gate, plan=self.terminal_plan)

    def terminal_gate(self, command, surface="mc"):
        self.events.append(("terminal_gate", command, surface))
        result = {"decision": self.terminal_decision, "risk": self.terminal_risk}
        if self.terminal_decision == "refuse":
            result["reason"] = "terminal denied"
        return result

    def terminal_plan(self, command, surface):
        self.events.append(("terminal_plan", command, surface))
        return {"planned": command, "surface": surface}

    def make_tool_call(self, tool, args):
        self.events.append(("make_tool_call", tool, args))
        return (tool, args)

    def receipt_key(self, turn_id, step_index, call):
        self.events.append(("receipt_key", turn_id, step_index, call))
        return f"receipt:{turn_id}:{step_index}"

    def load_receipt(self, key):
        self.events.append(("load_receipt", key))
        return self.loaded_receipt

    def store_receipt(self, key, turn_id, tool, args, result):
        self.events.append(("store_receipt", key, turn_id, tool, args, result))

    def execute_terminal(self, chat_id, surface, tool, args, risk, on_event):
        self.events.append(("execute_terminal", chat_id, surface, tool, args, risk, on_event))
        return self.terminal_result

    def execute_action(self, chat_id, surface, tool, args, risk, **kwargs):
        self.events.append(("execute_action", chat_id, surface, tool, args, risk, kwargs))
        return self.action_result

    def log_action(self, chat_id, surface, tool, args, risk, status, summary, result):
        self.events.append(("log_action", chat_id, surface, tool, args, risk, status, summary, result))
        if self.raise_log:
            raise RuntimeError("audit unavailable")

    def summary(self, tool, args):
        self.events.append(("summary", tool, args))
        return f"summary:{tool}"

    def picker_intro(self, picker):
        self.events.append(("picker_intro", picker))
        return "picker intro"

    def failure(self, done, summary, error):
        self.events.append(("failure", done, summary, error))
        return f"failure:{','.join(done)}:{summary}:{error}"

    def execute(self, call, **overrides):
        values = {
            "chat_id": 71,
            "surface": "mc",
            "intent": "QUESTION",
            "mode": "agent",
            "review_mode": "session",
            "denied_tools": set(),
            "allowed_tools": {"read_data", "workflow_read", "create_project", "run_command"},
            "turn_id": "turn-1",
            "step_index": 3,
            "prior_tools_used": ("already_used",),
            "completed_actions": ("already_done",),
            "risk_by_tool": {
                "outline_plan": "read",
                "read_data": "read",
                "workflow_read": "read",
                "optional_read": "read",
                "run_command": "medium",
                "terminal_status": "read",
                "create_project": "low",
                "delete_project": "high",
            },
            "tool_specs": {
                "outline_plan": "plan-spec",
                "read_data": "read-spec",
                "workflow_read": "workflow-spec",
                "optional_read": "optional-spec",
                "run_command": "terminal-spec",
                "terminal_status": "terminal-status-spec",
                "create_project": "create-spec",
                "delete_project": "delete-spec",
            },
            "read_tools": {"outline_plan", "read_data", "workflow_read", "terminal_status"},
            "optional_tools": {"optional_read"},
            "terminal_tools": {"run_command", "terminal_status"},
            "workflow_read_tools": {"workflow_read"},
            "validate_call": self.validate,
            "phase_for": self.phase,
            "execute_tool": self.execute_tool,
            "terminal_engine_loader": self.terminal_engine_loader,
            "terminal_command_for": self.terminal_command_for,
            "make_tool_call": self.make_tool_call,
            "receipt_key": self.receipt_key,
            "load_receipt": self.load_receipt,
            "store_receipt": self.store_receipt,
            "execute_terminal": self.execute_terminal,
            "execute_action": self.execute_action,
            "log_action": self.log_action,
            "action_summary": self.summary,
            "picker_intro": self.picker_intro,
            "failure_report": self.failure,
            "on_event": self.on_event,
        }
        values.update(overrides)
        return tool_call_executor.execute_tool_call(call, **values)


def _tool_result(tool: str, payload: dict) -> tuple[dict, ...]:
    return ({
        "role": "user",
        "content": f"TOOL_RESULT {tool}: {json.dumps(payload, default=str)[:3000]}",
    },)


def _check_contract_and_denials() -> int:
    checks = 0
    _check("core.conductor" not in sys.modules, "executor import must not load Conductor")
    checks += 1

    empty = tool_call_executor.ToolCallExecutionOutcome()
    _check(
        empty.messages == ()
        and empty.tools_used == ()
        and empty.completed_actions == ()
        and empty.proposed_actions == ()
        and empty.turn_response is None,
        "empty outcome changed",
    )
    checks += 1
    try:
        empty.messages = ({"role": "user", "content": "changed"},)
    except FrozenInstanceError:
        pass
    else:
        raise AssertionError("ToolCallExecutionOutcome must be frozen")
    checks += 1

    denied = _Harness()
    call = {"tool": "run_command", "args": {"command": "echo hi"}}
    original = copy.deepcopy(call)
    outcome = denied.execute(call, denied_tools={"run_command"})
    payload = {
        "denied": True,
        "reason": (
            "run_command is not available in this mode \u2014 shell/terminal actions require "
            "Agent mode. Tell the owner to switch modes; do not retry."
        ),
    }
    _check(outcome.messages == _tool_result("run_command", payload), "mode denial changed")
    _check(outcome.tools_used == () and denied.events == [], "mode denial invoked dependencies")
    _check(call == original, "executor mutated the parsed call")
    checks += 3

    route = _Harness()
    outcome = route.execute(
        {"tool": "delete_project", "args": {"project_id": 7}},
        allowed_tools={"read_data", "optional_read"},
    )
    payload = {
        "denied": True,
        "error_code": "tool.route_denied",
        "reason": (
            "'delete_project' isn't an available tool this turn. Use one of these instead: "
            "optional_read, read_data. Do NOT tell the owner to change permissions or "
            "re-authorize \u2014 pick a real tool and continue."
        ),
    }
    _check(outcome.messages == _tool_result("delete_project", payload), "route denial changed")
    _check(route.events == [], "route denial reached schema validation")
    checks += 2

    invalid = _Harness()
    invalid.validation_error = SimpleNamespace(
        message="bad args", code="tool.invalid_args", stage="tool_validation", retryable=False
    )
    outcome = invalid.execute({"tool": "create_project", "args": ["wrong"]})
    payload = {
        "error": "bad args",
        "error_code": "tool.invalid_args",
        "stage": "tool_validation",
        "retryable": False,
    }
    _check(outcome.messages == _tool_result("create_project", payload), "validation error changed")
    _check(
        invalid.events == [(
            "validate",
            {"tool": "create_project", "args": ["wrong"]},
            "create-spec",
            "agent",
            {"read_data", "workflow_read", "create_project", "run_command"},
        )],
        "validation input or ordering changed",
    )
    checks += 2
    return checks


def _check_plan_and_read_paths() -> int:
    checks = 0
    plan = _Harness()
    plan.tool_result = {"ok": True, "steps": ["one", "two"], "title": "Tiny"}
    outcome = plan.execute({"tool": "outline_plan", "args": {"steps": ["one", "two"]}})
    _check(outcome.messages == _tool_result("outline_plan", plan.tool_result), "plan result changed")
    _check(outcome.tools_used == ("outline_plan",), "plan tool tracking changed")
    _check(
        [event[0] for event in plan.events]
        == ["validate", "phase", "event", "execute_tool", "event"],
        f"plan event ordering changed: {plan.events}",
    )
    _check(plan.events[-1][1] == {
        "type": "plan", "steps": ["one", "two"], "title": "Tiny"
    }, "plan event payload changed")
    checks += 4

    event_failure = _Harness()
    event_failure.raise_event = True
    outcome = event_failure.execute({"tool": "read_data", "args": {}})
    _check(outcome.tools_used == ("read_data",), "event callback failure stopped execution")
    _check(any(event[0] == "execute_tool" for event in event_failure.events),
           "read did not execute after event callback failure")
    checks += 2

    workflow = _Harness()
    workflow.tool_result = {"available": True, "items": [1]}
    outcome = workflow.execute({"tool": "workflow_read", "args": {}})
    log = next(event for event in workflow.events if event[0] == "log_action")
    _check(log[5:8] == ("read", "executed", "summary:workflow_read"),
           "successful workflow read audit changed")
    _check(outcome.tools_used == ("workflow_read",), "workflow read tracking changed")
    checks += 2

    failed_audit = _Harness()
    failed_audit.tool_result = {"error": "offline"}
    failed_audit.raise_log = True
    outcome = failed_audit.execute({"tool": "workflow_read", "args": {}})
    _check(outcome.tools_used == ("workflow_read",), "audit failure stopped workflow read")
    _check(next(e for e in failed_audit.events if e[0] == "log_action")[6] == "failed",
           "failed workflow read audit status changed")
    checks += 2

    picker = _Harness()
    picker.tool_result = {"__picker__": {"topic": "Project", "fields": ["name"]}}
    outcome = picker.execute({"tool": "read_data", "args": {}})
    _check(outcome.turn_response == {
        "reply": "picker intro",
        "tools_used": ["already_used", "read_data"],
        "intent": "QUESTION",
        "pending_picker": picker.tool_result["__picker__"],
        "streamed": False,
    }, "picker terminal response changed")
    _check(outcome.tools_used == () and outcome.messages == (), "picker leaked partial outcome")
    checks += 2
    return checks


def _check_terminal_paths() -> int:
    checks = 0
    no_command = _Harness()
    no_command.terminal_command = None
    no_command.tool_result = {"mode": "ask"}
    outcome = no_command.execute({"tool": "terminal_status", "args": {}})
    _check(outcome.messages == _tool_result("terminal_status", no_command.tool_result),
           "commandless terminal result changed")
    _check(any(e[0] == "terminal_engine" for e in no_command.events),
           "commandless terminal call no longer loads the current Terminal owner")
    checks += 2

    refused = _Harness()
    refused.terminal_decision = "refuse"
    refused.terminal_risk = "blocked"
    outcome = refused.execute({"tool": "run_command", "args": {"command": "bad"}})
    payload = {"refused": True, "risk": "blocked", "reason": "terminal denied", "command": "echo hi"}
    _check(outcome.messages == _tool_result("run_command", payload), "terminal refusal changed")
    _check(outcome.tools_used == ("run_command",), "refused terminal tool tracking changed")
    checks += 2

    planned = _Harness()
    planned.terminal_decision = "plan"
    outcome = planned.execute({"tool": "run_command", "args": {"command": "echo hi"}})
    _check(outcome.messages == _tool_result(
        "run_command", {"planned": "echo hi", "surface": "mc"}
    ), "terminal plan changed")
    _check(not any(e[0] == "execute_terminal" for e in planned.events), "terminal plan executed")
    checks += 2

    confirmed = _Harness()
    confirmed.terminal_decision = "confirm"
    confirmed.terminal_risk = "high"
    outcome = confirmed.execute({"tool": "run_command", "args": {"command": "echo hi"}})
    _check(outcome.proposed_actions == (("run_command", {"command": "echo hi"}, "high"),),
           "terminal confirmation tuple changed")
    _check(outcome.messages == () and outcome.tools_used == (), "confirmation executed or emitted result")
    checks += 2

    replay = _Harness()
    replay.loaded_receipt = {"ok": True, "cached": True}
    outcome = replay.execute({"tool": "run_command", "args": {"command": "echo hi"}})
    replayed = {
        "ok": True,
        "cached": True,
        "receipt_key": "receipt:turn-1:3",
        "replayed": True,
    }
    _check(outcome.messages == _tool_result("run_command", replayed), "terminal replay changed")
    _check(outcome.completed_actions == ("summary:run_command",), "replay summary changed")
    _check(not any(e[0] in {"execute_terminal", "store_receipt"} for e in replay.events),
           "terminal replay executed or stored again")
    checks += 3

    run = _Harness()
    outcome = run.execute({"tool": "run_command", "args": {"command": "echo hi"}})
    result = {
        "ok": True,
        "exit_code": 0,
        "receipt_key": "receipt:turn-1:3",
        "replayed": False,
    }
    _check(outcome.messages == _tool_result("run_command", result), "terminal execution result changed")
    _check(outcome.tools_used == ("run_command",), "terminal execution tracking changed")
    _check(outcome.completed_actions == ("summary:run_command",), "terminal summary changed")
    _check(
        [e[0] for e in run.events][-6:]
        == ["make_tool_call", "receipt_key", "load_receipt", "execute_terminal",
            "store_receipt", "summary",],
        f"terminal receipt ordering changed: {run.events}",
    )
    checks += 4

    failed = _Harness()
    failed.terminal_result = {"error": "command failed"}
    outcome = failed.execute({"tool": "run_command", "args": {"command": "echo hi"}})
    _check(outcome.completed_actions == (), "failed terminal recorded completion")
    _check(not any(e[0] == "store_receipt" for e in failed.events), "failed terminal stored receipt")
    checks += 2
    return checks


def _check_mutation_paths() -> int:
    checks = 0
    telegram = _Harness()
    outcome = telegram.execute(
        {"tool": "delete_project", "args": {"project_id": 7}},
        surface="telegram",
        allowed_tools={"delete_project"},
    )
    payload = {
        "blocked": (
            "That's a high-risk change, sir \u2014 please do it from Mission Control "
            "(Telegram stays read-only and safe)."
        )
    }
    _check(outcome.messages == _tool_result("delete_project", payload), "Telegram block changed")
    _check(outcome.tools_used == ("delete_project",), "Telegram block tracking changed")
    checks += 2

    high = _Harness()
    outcome = high.execute(
        {"tool": "delete_project", "args": {"project_id": 7}},
        allowed_tools={"delete_project"},
    )
    _check(outcome.proposed_actions == (("delete_project", {"project_id": 7}),),
           "session high-risk proposal tuple changed")
    checks += 1

    ask = _Harness()
    outcome = ask.execute(
        {"tool": "create_project", "args": {"name": "A"}},
        review_mode="ask",
    )
    _check(outcome.proposed_actions == (("create_project", {"name": "A"}, "low"),),
           "ask-mode proposal tuple changed")
    _check(not any(e[0] == "execute_action" for e in ask.events), "ask-mode proposal executed")
    checks += 2

    success = _Harness()
    outcome = success.execute(
        {"tool": "create_project", "args": {"name": "A"}},
        review_mode="always",
    )
    execute = next(event for event in success.events if event[0] == "execute_action")
    _check(execute[1:6] == (71, "mc", "create_project", {"name": "A"}, "low"),
           "action identity changed")
    _check(execute[6] == {
        "mode": "agent",
        "allowed_tools": {"read_data", "workflow_read", "create_project", "run_command"},
        "turn_id": "turn-1",
        "step_index": 3,
    }, "action execution metadata changed")
    _check(outcome.messages == _tool_result("create_project", success.action_result),
           "action result changed")
    _check(outcome.tools_used == ("create_project",), "action tracking changed")
    _check(outcome.completed_actions == ("summary:create_project",), "action summary changed")
    checks += 5

    legacy = _Harness()

    def legacy_execute(chat_id, surface, tool, args, risk):
        legacy.events.append(("legacy_execute", chat_id, surface, tool, args, risk))
        return {"ok": True, "legacy": True}

    outcome = legacy.execute(
        {"tool": "create_project", "args": {"name": "A"}},
        review_mode="always",
        execute_action=legacy_execute,
    )
    _check(any(e[0] == "legacy_execute" for e in legacy.events), "legacy helper fallback removed")
    _check(outcome.tools_used == ("create_project",), "legacy fallback result changed")
    checks += 2

    broken = _Harness()
    broken.action_result = {"error": "temporary"}
    outcome = broken.execute(
        {"tool": "create_project", "args": {"name": "A"}},
        review_mode="always",
    )
    _check(outcome.turn_response == {
        "reply": "failure:already_done:summary:create_project:temporary",
        "tools_used": ["already_used", "create_project"],
        "intent": "QUESTION",
        "stopped_on_error": True,
        "failed_step": {
            "tool": "create_project",
            "args": {"name": "A"},
            "risk": "low",
            "error": "temporary",
        },
        "streamed": False,
    }, "stop-on-failure response changed")
    _check(outcome.messages == () and outcome.tools_used == (), "failure leaked partial outcome")
    checks += 2
    return checks


def _check_conductor_boundary() -> int:
    from core import conductor

    checks = 0
    signature = inspect.signature(conductor.answer)
    _check("recovery_checkpoint" in signature.parameters, "Conductor answer signature changed")
    checks += 1

    answer_source = inspect.getsource(conductor.answer)
    for marker in (
        "for _ in range(max_tool_steps or MAX_TOOL_STEPS)",
        "for call in calls",
        "tool_step_index += 1",
        "highs.extend(execution.proposed_actions)",
        "if highs:",
        "_propose_actions(highs, chat_id, surface, used, intent)",
        "Now give your final answer to the owner using only the tool",
    ):
        _check(marker in answer_source, f"Run 3B2 ownership moved early: {marker}")
        checks += 1
    _check("_execute_tool_call(" in answer_source, "Conductor does not delegate one-call execution")
    checks += 1

    service_source = inspect.getsource(tool_call_executor)
    for forbidden in ("core.conductor", "for call in calls", "_propose_actions", "MAX_TOOL_STEPS"):
        _check(forbidden not in service_source, f"executor took unapproved ownership: {forbidden}")
        checks += 1

    importers = []
    for path in (ROOT / "core").rglob("*.py"):
        if path == ROOT / "core" / "runtime" / "tool_call_executor.py":
            continue
        text = path.read_text(encoding="utf-8")
        if "core.runtime.tool_call_executor" in text:
            importers.append(path.relative_to(ROOT).as_posix())
    _check(importers == ["core/conductor.py"], f"unexpected live executor imports: {importers}")
    checks += 1
    return checks


total = 0
total += _check_contract_and_denials()
total += _check_plan_and_read_paths()
total += _check_terminal_paths()
total += _check_mutation_paths()
total += _check_conductor_boundary()
print(f"\n{total}/{total} T08 Run 3B1 tool-call executor checks pass")

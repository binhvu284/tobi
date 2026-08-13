"""Behavior checks for Conductor checkpoint-recovery extraction."""

from __future__ import annotations

import copy
import inspect
import os
import sys
import tempfile
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import SimpleNamespace

os.environ["DB_PATH"] = os.path.join(
    tempfile.mkdtemp(prefix="tobi_checkpoint_recovery_"),
    "agent.db",
)

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.runtime import checkpoint_recovery


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


class _Harness:
    def __init__(self) -> None:
        self.events: list[tuple] = []
        self.validation_error = None
        self.action_result: dict = {"ok": True, "value": 1}
        self.terminal_result: dict = {"ok": True, "terminal": True}
        self.terminal_decision = "run"
        self.terminal_risk = "medium"
        self.terminal_plan: dict = {"planned": True}
        self.terminal_command: str | None = "echo hi"
        self.proposal: dict = {"reply": "approval", "pending_action": {"tool": "x"}}

    def validate(self, call, spec, mode, allowed_tools):
        self.events.append(("validate", call, spec, mode, allowed_tools))
        return self.validation_error

    def phase(self, tool):
        self.events.append(("phase", tool))
        return "acting"

    def on_event(self, event):
        self.events.append(("event", event))

    def terminal_command_for(self, tool, args):
        self.events.append(("terminal_command", tool, args))
        return self.terminal_command

    def terminal_engine_loader(self):
        self.events.append(("terminal_engine",))
        return SimpleNamespace(gate=self.terminal_gate, plan=self.plan_terminal)

    def terminal_gate(self, command, surface="mc"):
        self.events.append(("terminal_gate", command, surface))
        result = {"decision": self.terminal_decision, "risk": self.terminal_risk}
        if self.terminal_decision == "refuse":
            result["reason"] = "terminal denied"
        return result

    def plan_terminal(self, command, surface):
        self.events.append(("terminal_plan", command, surface))
        return self.terminal_plan

    def propose(self, actions, chat_id, surface, used, intent):
        self.events.append(("propose", actions, chat_id, surface, used, intent))
        return self.proposal

    def execute_terminal(self, chat_id, surface, tool, args, risk, on_event):
        self.events.append(("execute_terminal", chat_id, surface, tool, args, risk, on_event))
        return self.terminal_result

    def execute_action(self, chat_id, surface, tool, args, risk, **kwargs):
        self.events.append(("execute_action", chat_id, surface, tool, args, risk, kwargs))
        return self.action_result

    def summary(self, tool, args):
        self.events.append(("summary", tool, args))
        return f"summary:{tool}"

    def failure(self, done, summary, error):
        self.events.append(("failure", done, summary, error))
        return f"failure:{summary}:{error}"

    def apply(self, checkpoint, **overrides):
        values = {
            "chat_id": 71,
            "surface": "mc",
            "intent": "QUESTION",
            "mode": "agent",
            "review_mode": "always",
            "denied_tools": set(),
            "allowed_tools": {"create_project", "delete_project", "run_command"},
            "turn_id": "turn-1",
            "risk_by_tool": {
                "create_project": "low",
                "delete_project": "high",
                "run_command": "medium",
            },
            "tool_specs": {
                "create_project": "create-spec",
                "delete_project": "delete-spec",
                "run_command": "terminal-spec",
            },
            "terminal_tools": {"run_command"},
            "validate_call": self.validate,
            "phase_for": self.phase,
            "terminal_engine_loader": self.terminal_engine_loader,
            "terminal_command_for": self.terminal_command_for,
            "propose_actions": self.propose,
            "execute_terminal": self.execute_terminal,
            "execute_action": self.execute_action,
            "action_summary": self.summary,
            "failure_report": self.failure,
            "on_event": self.on_event,
        }
        values.update(overrides)
        return checkpoint_recovery.apply_recovery_checkpoint(checkpoint, **values)


def _check_contract_and_control_messages() -> int:
    checks = 0
    _check("core.conductor" not in sys.modules, "recovery import must not load Conductor")
    checks += 1

    empty = checkpoint_recovery.CheckpointRecoveryOutcome()
    _check(empty.messages == () and empty.turn_response is None, "empty outcome changed")
    checks += 1
    try:
        empty.messages = ({"role": "user", "content": "changed"},)
    except FrozenInstanceError:
        pass
    else:
        raise AssertionError("CheckpointRecoveryOutcome must be frozen")
    checks += 1

    harness = _Harness()
    none_outcome = harness.apply(None)
    _check(none_outcome == empty and harness.events == [], "empty checkpoint invoked dependencies")
    checks += 1

    failed = {"tool": "create_project", "args": {"name": "A"}, "risk": "low"}
    skipped = harness.apply({"command": "skip_step", "failed_step": failed})
    _check(skipped.messages == ({
        "role": "user",
        "content": (
            "CHECKPOINT_SKIPPED create_project: the owner explicitly skipped this failed step. "
            "Continue only with remaining work; do not call it again."
        ),
    },), "skip message changed")
    _check(skipped.tools_used == () and harness.events == [], "skip executed a dependency")
    checks += 2

    revision = "r" * 1200
    revised = harness.apply({"command": "revise", "revision": revision})
    _check(revised.messages == ({"role": "user", "content": "PLAN_REVISION: " + revision[:1000]},),
           "revision text or cap changed")
    resumed = harness.apply({"command": "resume"})
    _check(resumed.messages == ({
        "role": "user",
        "content": "RESUME_CHECKPOINT: continue after the last persisted completed step.",
    },), "resume message changed")
    checks += 2
    return checks


def _check_action_recovery() -> int:
    checks = 0
    harness = _Harness()
    failed = {"tool": "ignored", "args": {"name": "Exact"}, "risk": "low", "error": "old"}
    checkpoint = {"command": "retry_step", "tool": "create_project", "failed_step": failed}
    original = copy.deepcopy(checkpoint)
    outcome = harness.apply(checkpoint)

    validate = harness.events[0]
    execute = next(event for event in harness.events if event[0] == "execute_action")
    _check(validate == (
        "validate",
        {"tool": "create_project", "args": failed["args"]},
        "create-spec",
        "agent",
        {"create_project", "delete_project", "run_command"},
    ), "retry validation identity changed")
    _check(execute[1:6] == (71, "mc", "create_project", failed["args"], "low"),
           "retry execution identity changed")
    _check(execute[6] == {
        "mode": "agent",
        "allowed_tools": {"create_project", "delete_project", "run_command"},
        "turn_id": "turn-1",
        "step_index": 0,
    }, "retry execution metadata changed")
    _check(outcome.messages == ({
        "role": "user",
        "content": 'CHECKPOINT_RETRY_RESULT create_project: {"ok": true, "value": 1}',
    },), "retry result message changed")
    _check(outcome.tools_used == ("create_project",), "successful retry tool tracking changed")
    _check(outcome.completed_actions == ("summary:create_project",), "completed summary changed")
    _check(outcome.turn_response is None and checkpoint == original, "retry mutated input or stopped")
    _check(
        [event[0] for event in harness.events] ==
        ["validate", "phase", "event", "execute_action", "summary"],
        f"retry callback order changed: {harness.events}",
    )
    checks += 8

    denied = _Harness()
    denied_outcome = denied.apply(checkpoint, denied_tools={"create_project"})
    _check([event[0] for event in denied.events] == ["validate"], "denied retry reached execution")
    _check(denied_outcome.turn_response == {
        "reply": "I couldn't retry that checkpoint, sir \u2014 tool is denied in this mode.",
        "tools_used": [],
        "intent": "QUESTION",
        "stopped_on_error": True,
        "failed_step": failed,
        "streamed": False,
    }, "denied retry response changed")
    checks += 2

    invalid = _Harness()
    invalid.validation_error = SimpleNamespace(message="bad args")
    invalid_outcome = invalid.apply(checkpoint)
    _check(invalid_outcome.turn_response["reply"].endswith("\u2014 bad args."),
           "validation response changed")
    _check([event[0] for event in invalid.events] == ["validate"], "invalid retry reached execution")
    checks += 2

    proposed = _Harness()
    high = {
        "command": "retry_step",
        "failed_step": {"tool": "delete_project", "args": {"project_id": 7}, "risk": "high"},
    }
    proposed_outcome = proposed.apply(high, review_mode="session")
    proposal_event = next(event for event in proposed.events if event[0] == "propose")
    _check(proposal_event[1] == [("delete_project", {"project_id": 7}, "high")],
           "high-risk retry proposal changed")
    _check(proposed_outcome.turn_response is proposed.proposal, "proposal response was rewritten")
    _check(not any(event[0] == "execute_action" for event in proposed.events),
           "proposed retry executed")
    checks += 3

    failed_run = _Harness()
    failed_run.action_result = {"error": "temporary"}
    failed_outcome = failed_run.apply(checkpoint)
    _check(failed_outcome.turn_response == {
        "reply": "failure:summary:create_project:temporary",
        "tools_used": ["create_project"],
        "intent": "QUESTION",
        "stopped_on_error": True,
        "failed_step": {
            "tool": "create_project",
            "args": {"name": "Exact"},
            "risk": "low",
            "error": "temporary",
        },
        "streamed": False,
    }, "failed retry response changed")
    _check(failed_outcome.messages[0]["content"].endswith('{"error": "temporary"}'),
           "failed retry result was not returned to the model transcript")
    checks += 2
    return checks


def _check_terminal_recovery() -> int:
    checks = 0
    checkpoint = {
        "command": "retry_step",
        "failed_step": {"tool": "run_command", "args": {"command": "echo hi"}, "risk": "medium"},
    }

    refused = _Harness()
    refused.terminal_decision = "refuse"
    refused.terminal_risk = "blocked"
    refused_outcome = refused.apply(checkpoint)
    _check(refused_outcome.turn_response["failed_step"]["risk"] == "blocked",
           "Terminal gate risk was not authoritative")
    _check("terminal denied" in refused_outcome.turn_response["reply"], "Terminal refusal text changed")
    _check(not any(event[0] == "execute_terminal" for event in refused.events),
           "refused Terminal retry executed")
    checks += 3

    planned = _Harness()
    planned.terminal_decision = "plan"
    planned_outcome = planned.apply(checkpoint)
    _check(planned_outcome.turn_response is None, "Terminal plan incorrectly stopped recovery")
    _check(planned_outcome.messages[0]["content"].endswith('{"planned": true}'),
           "Terminal plan result changed")
    _check(any(event[0] == "terminal_plan" for event in planned.events), "Terminal plan was skipped")
    checks += 3

    confirmed = _Harness()
    confirmed.terminal_decision = "confirm"
    confirmed.terminal_risk = "high"
    confirmed_outcome = confirmed.apply(checkpoint)
    proposal = next(event for event in confirmed.events if event[0] == "propose")
    _check(proposal[1] == [("run_command", {"command": "echo hi"}, "high")],
           "Terminal confirmation proposal changed")
    _check(confirmed_outcome.turn_response is confirmed.proposal, "Terminal proposal was rewritten")
    checks += 2

    executed = _Harness()
    executed_outcome = executed.apply(checkpoint)
    terminal_call = next(event for event in executed.events if event[0] == "execute_terminal")
    _check(terminal_call[1:6] == (71, "mc", "run_command", {"command": "echo hi"}, "medium"),
           "Terminal retry execution changed")
    _check(executed_outcome.completed_actions == ("summary:run_command",),
           "Terminal retry completion changed")
    checks += 2

    no_command = _Harness()
    no_command.terminal_command = None
    no_command.apply(checkpoint)
    _check(not any(event[0] == "terminal_gate" for event in no_command.events),
           "empty Terminal command entered the gate")
    _check(any(event[0] == "execute_terminal" for event in no_command.events),
           "empty Terminal command no longer uses its tool helper")
    checks += 2
    return checks


def _check_conductor_delegation() -> int:
    checks = 0
    from core import brain, conductor, model_router, task_classifier

    expected_parameters = [
        "message", "chat_id", "surface", "model", "history", "attachments_text", "directives",
        "extra_tools", "on_event", "on_delta", "denied_tools", "review_mode", "mode", "route",
        "allowed_tools", "context_manifest", "turn_id", "max_tool_steps", "step_tokens",
        "final_tokens", "usage_context", "recovery_checkpoint",
    ]
    _check(list(inspect.signature(conductor.answer).parameters) == expected_parameters,
           "Conductor public signature changed")
    _check(conductor._apply_recovery_checkpoint is checkpoint_recovery.apply_recovery_checkpoint,
           "Conductor does not re-export the shared recovery function")
    checks += 2

    answer_source = inspect.getsource(conductor.answer)
    from core.runtime import conductor_facade
    facade_source = inspect.getsource(conductor_facade)
    _check("recovery_checkpoint" in answer_source, "Conductor facade dropped recovery input")
    _check(facade_source.count("bindings.apply_recovery_checkpoint(") == 1,
           "Runtime facade recovery delegation count changed")
    for ordinary_loop_marker in (
        "_run_tool_loop(",
        "execute_tool_call=_execute_loop_call",
        "_execute_tool_call(",
    ):
        expected = {
            "_run_tool_loop(": "bindings.run_tool_loop(",
            "execute_tool_call=_execute_loop_call": "execute_tool_call=execute_loop_call",
            "_execute_tool_call(": "bindings.execute_tool_call(",
        }[ordinary_loop_marker]
        _check(expected in facade_source, f"ordinary loop ownership changed: {ordinary_loop_marker}")
        checks += 1
    checks += 2

    imports = []
    for path in (ROOT / "core").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "core.runtime.checkpoint_recovery" in text:
            imports.append(path.relative_to(ROOT).as_posix())
    _check(imports == ["core/conductor.py"], f"unexpected live recovery imports: {imports}")
    checks += 1

    class _FakeModel:
        provider = "test"
        model = "recovery"

        def __init__(self) -> None:
            self.messages = None

        def complete(self, messages, system=None, **_kwargs):
            self.messages = messages
            return "Recovered and continued, sir."

    model = _FakeModel()
    captured: list[dict] = []
    original = {
        "apply": conductor._apply_recovery_checkpoint,
        "pending": conductor._pending_all,
        "profile": brain.profile_summary,
        "tier": conductor._build_tier_context,
        "prompt": conductor._system_prompt,
        "classify": task_classifier.classify,
        "get_llm": model_router.get_llm,
    }
    try:
        conductor._pending_all = lambda _chat_id: []
        brain.profile_summary = lambda: ""
        conductor._build_tier_context = lambda: ""
        conductor._system_prompt = lambda *_args, **_kwargs: "SYSTEM"
        task_classifier.classify = lambda _message: "SMALLTALK"
        model_router.get_llm = lambda *_args, **_kwargs: model

        def delegated(checkpoint, **kwargs):
            captured.append({"checkpoint": checkpoint, **kwargs})
            return checkpoint_recovery.CheckpointRecoveryOutcome(
                messages=({"role": "user", "content": "RECOVERY"},),
                tools_used=("create_project",),
                completed_actions=("summary:create_project",),
            )

        conductor._apply_recovery_checkpoint = delegated
        checkpoint = {"command": "resume"}
        response = conductor.answer(
            "continue",
            chat_id=88,
            history=[],
            route="direct",
            recovery_checkpoint=checkpoint,
        )
        _check(len(captured) == 1 and captured[0]["checkpoint"] is checkpoint,
               "Conductor did not delegate the original checkpoint once")
        _check(model.messages == [
            {"role": "user", "content": "continue"},
            {"role": "user", "content": "RECOVERY"},
        ], "Conductor did not apply recovery messages in order")
        _check(response["tools_used"] == ["create_project"], "Conductor lost recovered tool tracking")
        _check(response["reply"] == "Recovered and continued, sir.", "Conductor reply changed")
        checks += 4
    finally:
        conductor._apply_recovery_checkpoint = original["apply"]
        conductor._pending_all = original["pending"]
        brain.profile_summary = original["profile"]
        conductor._build_tier_context = original["tier"]
        conductor._system_prompt = original["prompt"]
        task_classifier.classify = original["classify"]
        model_router.get_llm = original["get_llm"]
    return checks


if __name__ == "__main__":
    total = (
        _check_contract_and_control_messages()
        + _check_action_recovery()
        + _check_terminal_recovery()
        + _check_conductor_delegation()
    )
    print(f"OK: {total} checkpoint-recovery checks passed")

import inspect
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.runtime import tool_loop_orchestrator


def _check(condition, message):
    if not condition:
        raise AssertionError(message)


class _Execution:
    def __init__(self, *, messages=(), tools_used=(), completed_actions=(),
                 proposed_actions=(), turn_response=None):
        self.messages = tuple(messages)
        self.tools_used = tuple(tools_used)
        self.completed_actions = tuple(completed_actions)
        self.proposed_actions = tuple(proposed_actions)
        self.turn_response = turn_response


class _Harness:
    def __init__(self, steps, parsed=None, executions=None):
        self.steps = list(steps)
        self.parsed = dict(parsed or {})
        self.executions = list(executions or [])
        self.generated = []
        self.continued = []
        self.executed = []
        self.proposals = []
        self.reset_count = 0

    def generate(self, client, messages, system, max_tokens, on_delta=None, on_reset=None):
        self.generated.append({
            "messages": [dict(m) for m in messages],
            "system": system,
            "max_tokens": max_tokens,
        })
        if not self.steps:
            raise AssertionError("unexpected model generation")
        return self.steps.pop(0)

    def continue_answer(self, client, messages, partial, system, on_delta=None):
        self.continued.append((partial, max(len(messages), 0)))
        return " + continued"

    def parse(self, text):
        return list(self.parsed.get(text, ()))

    def execute(self, call, *, step_index, prior_tools_used, completed_actions):
        self.executed.append({
            "call": dict(call),
            "step_index": step_index,
            "prior_tools_used": list(prior_tools_used),
            "completed_actions": list(completed_actions),
        })
        if not self.executions:
            raise AssertionError("unexpected tool execution")
        return self.executions.pop(0)

    def propose(self, proposed, chat_id, surface, tools_used, intent):
        self.proposals.append((tuple(proposed), list(tools_used)))
        return {
            "reply": f"proposal:{len(proposed)}",
            "tools_used": list(tools_used),
            "intent": intent,
            "pending_action": True,
            "streamed": False,
        }

    def reset(self):
        self.reset_count += 1


def _run(harness, **overrides):
    values = {
        "client": object(),
        "messages": [{"role": "user", "content": "owner asks"}],
        "system": "system",
        "chat_id": 7,
        "surface": "mc",
        "intent": "QUESTION",
        "mode": "agent",
        "used_tools": (),
        "completed_actions": (),
        "max_tool_steps": None,
        "default_max_tool_steps": 3,
        "step_tokens": None,
        "step_token_budget": 11,
        "final_tokens": None,
        "final_token_budget": 17,
        "max_step_retries": 2,
        "generate_step": harness.generate,
        "continue_answer": harness.continue_answer,
        "parse_tool_calls": harness.parse,
        "execute_tool_call": harness.execute,
        "propose_actions": harness.propose,
        "on_delta": None,
        "on_reset": harness.reset,
    }
    values.update(overrides)
    return tool_loop_orchestrator.run_tool_loop(**values)


def _check_contract_and_copies():
    checks = 0
    outcome = tool_loop_orchestrator.ToolLoopOutcome(messages=[{"role": "x", "content": "y"}])
    try:
        outcome.final_text = "mutated"
        raise AssertionError("ToolLoopOutcome is not frozen")
    except Exception:
        pass
    _check(isinstance(outcome.messages, tuple), "outcome did not freeze messages")
    checks += 2

    original_messages = [{"role": "user", "content": "owner asks"}]
    original_used = ["already"]
    original_done = ["done"]
    harness = _Harness([("plain answer", True, None)])
    result = _run(
        harness,
        messages=original_messages,
        used_tools=original_used,
        completed_actions=original_done,
    )
    _check(result.final_text == "plain answer", "direct answer final text changed")
    _check(result.tools_used == ("already",), "used tools were not preserved")
    _check(result.completed_actions == ("done",), "completed actions were not preserved")
    _check(original_messages == [{"role": "user", "content": "owner asks"}],
           "caller messages were mutated")
    _check(original_used == ["already"], "caller used-tools list was mutated")
    _check(original_done == ["done"], "caller completed-actions list was mutated")
    checks += 6
    return checks


def _check_answer_and_retry_paths():
    checks = 0
    harness = _Harness([("partial", True, "length")])
    result = _run(harness)
    _check(result.final_text == "partial + continued", "length continuation changed")
    _check(harness.continued == [("partial", 1)], "continuation call changed")
    _check(harness.generated[0]["max_tokens"] == 11, "step token budget changed")
    checks += 3

    broken = _Harness([
        ("", False, None),
        ("not json", False, None),
        ("", False, None),
    ])
    issue = _run(broken)
    _check(issue.model_issue is True and issue.final_text is None, "retry issue boundary changed")
    _check(len(issue.messages) == 3, "invalid-output history changed")
    _check(issue.messages[1]["content"] == "not json", "invalid assistant echo changed")
    _check("single-line JSON object" in issue.messages[2]["content"],
           "invalid corrective prompt changed")
    checks += 4
    return checks


def _check_ordered_execution_and_terminal_stop():
    checks = 0
    calls = (
        {"tool": "first", "args": {"n": 1}},
        {"tool": "second", "args": {"n": 2}},
    )
    harness = _Harness(
        [("batch", False, None), ("done", True, None)],
        parsed={"batch": calls},
        executions=[
            _Execution(messages=({"role": "user", "content": "TOOL_RESULT first: {}"},),
                       tools_used=("first",), completed_actions=("first done",)),
            _Execution(messages=({"role": "user", "content": "TOOL_RESULT second: {}"},),
                       tools_used=("second",), completed_actions=("second done",)),
        ],
    )
    result = _run(harness)
    _check(result.final_text == "done", "ordered execution did not continue to final answer")
    _check([e["step_index"] for e in harness.executed] == [1, 2], "step identity changed")
    _check(harness.executed[1]["prior_tools_used"] == ["first"],
           "prior tools were not passed across a batch")
    _check(result.tools_used == ("first", "second"), "tools-used merge changed")
    _check(result.completed_actions == ("first done", "second done"),
           "completed-action merge changed")
    checks += 5

    stop = _Harness(
        [("batch", False, None)],
        parsed={"batch": calls},
        executions=[
            _Execution(turn_response={"reply": "terminal", "tools_used": ["first"],
                                      "intent": "QUESTION", "streamed": False}),
        ],
    )
    stopped = _run(stop)
    _check(stopped.turn_response == {"reply": "terminal", "tools_used": ["first"],
                                     "intent": "QUESTION", "streamed": False},
           "terminal turn response changed")
    _check(len(stop.executed) == 1, "terminal response did not stop later calls")
    checks += 2
    return checks


def _check_combined_proposal_and_budget_forcing():
    checks = 0
    calls = (
        {"tool": "read", "args": {}},
        {"tool": "act", "args": {"name": "A"}},
    )
    harness = _Harness(
        [("batch", False, None)],
        parsed={"batch": calls},
        executions=[
            _Execution(messages=({"role": "user", "content": "TOOL_RESULT read: {}"},),
                       tools_used=("read",)),
            _Execution(proposed_actions=(("act", {"name": "A"}, "high"),)),
        ],
    )
    result = _run(harness)
    _check(result.turn_response["reply"] == "proposal:1", "combined proposal response changed")
    _check(harness.proposals == [((("act", {"name": "A"}, "high"),), ["read"])],
           "proposal batching changed")
    checks += 2

    budget = _Harness(
        [("batch", False, None), ("still a call", False, None), ("final", True, "length")],
        parsed={
            "batch": ({"tool": "read", "args": {}},),
            "still a call": ({"tool": "read_again", "args": {}},),
        },
        executions=[
            _Execution(messages=({"role": "user", "content": "TOOL_RESULT read: {}"},),
                       tools_used=("read",)),
        ],
    )
    forced = _run(budget, max_tool_steps=1, final_tokens=19)
    _check(forced.final_text == "final + continued", "forced final continuation changed")
    _check("Now give your final answer" in budget.generated[1]["messages"][-1]["content"],
           "forced-final prompt changed")
    _check("Do NOT output" in budget.generated[2]["messages"][-1]["content"],
           "prose-only retry prompt changed")
    _check(budget.generated[1]["max_tokens"] == 19 and budget.generated[2]["max_tokens"] == 19,
           "final token budget changed")
    checks += 4
    return checks


def _check_conductor_boundary():
    from core import conductor

    checks = 0
    expected_parameters = [
        "message", "chat_id", "surface", "model", "history", "attachments_text", "directives",
        "extra_tools", "on_event", "on_delta", "denied_tools", "review_mode", "mode", "route",
        "allowed_tools", "context_manifest", "turn_id", "max_tool_steps", "step_tokens",
        "final_tokens", "usage_context", "recovery_checkpoint",
    ]
    _check(list(inspect.signature(conductor.answer).parameters) == expected_parameters,
           "Conductor public signature changed")
    checks += 1

    source = inspect.getsource(conductor.answer)
    _check("_run_tool_loop(" in source, "Conductor does not delegate tool-loop orchestration")
    for moved_marker in (
        "for _ in range(max_tool_steps or MAX_TOOL_STEPS)",
        "for call in calls:",
        "tool_step_index += 1",
        "highs.extend(execution.proposed_actions)",
        "if highs:",
        "Now give your final answer to the owner using only the tool",
    ):
        _check(moved_marker not in source, f"Conductor still owns Run 3B2 loop marker: {moved_marker}")
        checks += 1
    checks += 1

    service_source = inspect.getsource(tool_loop_orchestrator)
    for forbidden in (
        "core.conductor",
        "core.runtime.loop_controller",
        "core.runtime.tool_executor",
        "validate_call(",
        "confirm_action",
        "_final(",
        "get_llm(",
    ):
        _check(forbidden not in service_source, f"orchestrator took unapproved ownership: {forbidden}")
        checks += 1

    importers = []
    for path in (ROOT / "core").rglob("*.py"):
        if path == ROOT / "core" / "runtime" / "tool_loop_orchestrator.py":
            continue
        text = path.read_text(encoding="utf-8")
        if "core.runtime.tool_loop_orchestrator" in text:
            importers.append(path.relative_to(ROOT).as_posix())
    _check(importers == ["core/conductor.py"], f"unexpected live orchestrator imports: {importers}")
    checks += 1
    return checks


total = 0
total += _check_contract_and_copies()
total += _check_answer_and_retry_paths()
total += _check_ordered_execution_and_terminal_stop()
total += _check_combined_proposal_and_budget_forcing()
total += _check_conductor_boundary()
print(f"\n{total}/{total} T08 Run 3B2 tool-loop orchestrator checks pass")

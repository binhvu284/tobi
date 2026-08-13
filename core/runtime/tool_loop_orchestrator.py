"""Compatibility orchestration for Conductor's model/tool loop."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolLoopOutcome:
    """Immutable loop result for Conductor to compose into public replies."""

    final_text: str | None = None
    turn_response: dict[str, Any] | None = None
    messages: tuple[dict[str, Any], ...] = ()
    tools_used: tuple[str, ...] = ()
    completed_actions: tuple[str, ...] = ()
    model_issue: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "messages", tuple(dict(message) for message in self.messages))
        object.__setattr__(self, "tools_used", tuple(self.tools_used))
        object.__setattr__(self, "completed_actions", tuple(self.completed_actions))
        if self.turn_response is not None:
            object.__setattr__(self, "turn_response", dict(self.turn_response))


def _model_issue(
    *,
    messages: Sequence[Mapping[str, Any]],
    tools_used: Sequence[str],
    completed_actions: Sequence[str],
) -> ToolLoopOutcome:
    return ToolLoopOutcome(
        messages=tuple(dict(message) for message in messages),
        tools_used=tuple(tools_used),
        completed_actions=tuple(completed_actions),
        model_issue=True,
    )


def _final_outcome(
    text: str,
    *,
    messages: Sequence[Mapping[str, Any]],
    tools_used: Sequence[str],
    completed_actions: Sequence[str],
) -> ToolLoopOutcome:
    return ToolLoopOutcome(
        final_text=text,
        messages=tuple(dict(message) for message in messages),
        tools_used=tuple(tools_used),
        completed_actions=tuple(completed_actions),
    )


def run_tool_loop(
    *,
    client: Any,
    messages: Sequence[Mapping[str, Any]],
    system: str,
    chat_id: int,
    surface: str,
    intent: str,
    mode: str,
    used_tools: Sequence[str],
    completed_actions: Sequence[str],
    max_tool_steps: int | None,
    default_max_tool_steps: int,
    step_tokens: int | None,
    step_token_budget: int,
    final_tokens: int | None,
    final_token_budget: int,
    max_step_retries: int,
    generate_step: Callable[..., tuple[str, bool, str | None]],
    continue_answer: Callable[..., str],
    parse_tool_calls: Callable[[str], Sequence[Mapping[str, Any]]],
    execute_tool_call: Callable[..., Any],
    propose_actions: Callable[..., dict[str, Any]],
    on_delta: Callable[[str], None] | None = None,
    on_reset: Callable[[], None] | None = None,
) -> ToolLoopOutcome:
    """Run the legacy Conductor loop while injected helpers keep behavior ownership."""

    msgs = [dict(message) for message in messages]
    used = list(used_tools)
    done_acts = list(completed_actions)
    step_fails = 0
    tool_step_index = 0

    for _ in range(max_tool_steps or default_max_tool_steps):
        text, is_answer, finish_reason = generate_step(
            client,
            msgs,
            system,
            step_tokens or step_token_budget,
            on_delta,
            on_reset,
        )
        if not text:
            step_fails += 1
            if step_fails > max_step_retries:
                return _model_issue(messages=msgs, tools_used=used, completed_actions=done_acts)
            continue
        if is_answer:
            if finish_reason == "length":
                text += continue_answer(client, msgs, text, system, on_delta)
            return _final_outcome(
                text,
                messages=msgs,
                tools_used=used,
                completed_actions=done_acts,
            )

        calls = list(parse_tool_calls(text))
        if not calls:
            step_fails += 1
            if step_fails > max_step_retries:
                return _model_issue(messages=msgs, tools_used=used, completed_actions=done_acts)
            msgs.append({"role": "assistant", "content": text[:600]})
            msgs.append({"role": "user", "content": "That tool call was incomplete or invalid. Reply with ONLY "
                         "a single-line JSON object exactly like {\"tool\": \"<name>\", \"args\": {}} \u2014 no prose, "
                         "no markdown, no commentary."})
            continue

        msgs.append({"role": "assistant", "content": text})
        proposed_actions: list[tuple[Any, ...]] = []
        for call in calls:
            tool_step_index += 1
            execution = execute_tool_call(
                call,
                step_index=tool_step_index,
                prior_tools_used=used,
                completed_actions=done_acts,
            )
            if execution.turn_response is not None:
                return ToolLoopOutcome(
                    turn_response=execution.turn_response,
                    messages=msgs,
                    tools_used=used,
                    completed_actions=done_acts,
                )
            msgs.extend(execution.messages)
            used.extend(execution.tools_used)
            done_acts.extend(execution.completed_actions)
            proposed_actions.extend(execution.proposed_actions)

        if proposed_actions:
            return ToolLoopOutcome(
                turn_response=propose_actions(proposed_actions, chat_id, surface, used, intent),
                messages=msgs,
                tools_used=used,
                completed_actions=done_acts,
            )

    msgs.append({"role": "user", "content": "Now give your final answer to the owner using only the tool "
                 "results above. Do not call any more tools. Answer fully and do not stop mid-sentence."})
    final_budget = final_tokens or final_token_budget
    text, is_answer, finish_reason = generate_step(
        client,
        msgs,
        system,
        final_budget,
        on_delta,
        on_reset,
    )
    if not is_answer:
        msgs.append({"role": "assistant", "content": text[:600]})
        msgs.append({"role": "user", "content": "Answer in plain prose for the owner now. Do NOT output "
                     "JSON and do NOT call any tool \u2014 just summarise what the tool results above show."})
        text, is_answer, finish_reason = generate_step(
            client,
            msgs,
            system,
            final_budget,
            on_delta,
            on_reset,
        )
    if finish_reason == "length":
        text += continue_answer(client, msgs, text, system, on_delta)
    return _final_outcome(
        text,
        messages=msgs,
        tools_used=used,
        completed_actions=done_acts,
    )

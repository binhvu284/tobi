"""T08 Run 1: model-response behavior moves out of Conductor without changing it.

Plain Python, no pytest and no network:
    python tests/test_mc_runtime_response_composer.py
"""
from __future__ import annotations

import inspect
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.runtime import response_composer as rc  # noqa: E402


FAILURES: list[str] = []


def ok(name: str, condition: bool, detail: str = "") -> None:
    print(f"{'PASS' if condition else 'FAIL'} {name}")
    if not condition:
        if detail:
            print(f"  {detail}")
        FAILURES.append(name)


class CompleteFake:
    last_finish_reason = "stop"

    def __init__(self, replies: list[str]):
        self.replies = list(replies)
        self.calls: list[tuple[list[dict], str, int]] = []

    def complete(self, messages, system=None, max_tokens=0):
        self.calls.append((list(messages), system or "", max_tokens))
        return self.replies.pop(0)


class StreamFake(CompleteFake):
    def __init__(self, deltas: list[str], fallback: str = "fallback"):
        super().__init__([fallback])
        self.deltas = list(deltas)

    def complete_stream(self, messages, system=None, max_tokens=0):
        yield from self.deltas


ok("response service does not reverse-import Conductor", "core.conductor" not in sys.modules)
ok("typed model-step result is immutable", rc.ModelStepResult.__dataclass_params__.frozen)
ok("final response decision is immutable", rc.FinalResponseDecision.__dataclass_params__.frozen)
ok("final response context is immutable", rc.FinalResponseContext.__dataclass_params__.frozen)

ok("empty prefix is not a tool", not rc.looks_like_tool_start(""))
ok("leading object is a tool prefix", rc.looks_like_tool_start('{"tool"'))
ok("fenced object is a tool prefix", rc.looks_like_tool_start("```json\n{"))
ok("ordinary prose is not a tool prefix", not rc.looks_like_tool_start("Right away, sir."))

clean, reasoning = rc.split_reasoning("<think>private plan</think>Final answer")
ok("closed private reasoning is removed", clean == "Final answer" and "private plan" in reasoning)
clean, reasoning = rc.split_reasoning("Visible start <thinking>unfinished")
ok("unclosed private reasoning is removed", clean == "Visible start" and "unfinished" in reasoning)
harmony = (
    "<|start|>assistant<|channel|>analysis<|message|>private<|end|>"
    "<|start|>assistant<|channel|>final<|message|>Visible answer<|end|>"
)
clean, reasoning = rc.split_reasoning(harmony)
ok("harmony final channel is selected", clean == "Visible answer" and "private" in reasoning)

plain_final = rc.classify_final_response("Visible answer", mixed_prose_min=20)
ok("plain final response needs no escalation", not plain_final.requires_escalation)
mixed_final = rc.classify_final_response(
    '{"tool":"list_projects","args":{}} I need the current project status first.',
    mixed_prose_min=20,
)
ok("mixed tool prose keeps its useful text", mixed_final.mixed_reply == "I need the current project status first.")
malformed_final = rc.classify_final_response('{"tool"', mixed_prose_min=20)
ok("malformed internal output requests escalation", malformed_final.requires_escalation)

metadata_client = CompleteFake([])
metadata_client.requested_model = "openai:wanted"
metadata_client.provider = "openai"
metadata_client.model = "actual"
metadata_client.attempt_count = 2
metadata = rc.attach_model_metadata(
    {"reply": "done"},
    client=metadata_client,
    requested_model="openai:asked",
    usage_context=None,
)
ok(
    "model metadata preserves requested and actual identities",
    metadata["requested_model"] == "openai:wanted"
    and metadata["actual_model"] == "openai:actual"
    and metadata["model_attempts"] == 2,
)

sample = "One short sentence followed by a second sentence."
chunks = list(rc.stream_chunks(sample))
ok("chunking preserves every character", "".join(chunks) == sample, repr(chunks))
ok("chunking yields stable non-empty pieces", bool(chunks) and all(chunks))

emitted: list[str] = []
plain = rc.generate_step(
    CompleteFake(["Plain answer"]), [], "system", 123, emitted.append
)
ok("non-stream prose is a typed answer", isinstance(plain, rc.ModelStepResult) and plain.is_answer)
ok("non-stream prose uses compatibility chunks", "".join(emitted) == "Plain answer")

emitted.clear()
tool = rc.generate_step(
    CompleteFake(['{"tool":"list_projects","args":{}}']), [], "system", 123, emitted.append
)
ok("non-stream tool JSON is classified as a tool", not tool.is_answer)
ok("non-stream tool JSON is never emitted", emitted == [])

emitted.clear()
streamed = rc.generate_step(
    StreamFake(["Hello", ", sir."]), [], "system", 123, emitted.append
)
ok("clean streaming reply stays an answer", streamed.is_answer)
ok("clean streaming deltas preserve order", "".join(emitted) == "Hello, sir.")

emitted.clear()
resets: list[str] = []
mixed = rc.generate_step(
    StreamFake(["Of course, sir.\n", '{"tool":"list_projects","args":{}}']),
    [], "system", 123, emitted.append, lambda: resets.append("reset")
)
ok("prose-first tool output is reclassified", not mixed.is_answer)
ok("prose-first stream requests exactly one reset", resets == ["reset"], repr(resets))
ok("tool JSON never reaches streamed deltas", '"tool"' not in "".join(emitted))


class ContinueFake(CompleteFake):
    def __init__(self):
        super().__init__([" continued"])
        self.last_finish_reason = "length"

    def complete(self, messages, system=None, max_tokens=0):
        reply = super().complete(messages, system, max_tokens)
        self.last_finish_reason = "stop"
        return reply


continued_client = ContinueFake()
continued = rc.continue_answer(
    continued_client, [{"role": "user", "content": "question"}], "partial", "system",
    None, max_tokens=456, rounds=2
)
ok("token-capped answer continues once", continued == " continued")
ok("continuation uses the supplied token cap", continued_client.calls[0][2] == 456)
ok(
    "continuation includes the partial answer",
    continued_client.calls[0][0][-2] == {"role": "assistant", "content": "partial"},
)

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
ok("legacy tool-prefix helper is re-exported", conductor._looks_like_tool_start is rc.looks_like_tool_start)
ok("legacy reasoning helper is re-exported", conductor._strip_reasoning is rc.split_reasoning)
ok("legacy chunk helper is re-exported", conductor._stream_chunks is rc.stream_chunks)
legacy_step = conductor._gen_step(CompleteFake(["Legacy answer"]), [], "system", 123, None)
ok("legacy generation helper keeps its tuple shape", legacy_step == ("Legacy answer", True, "stop"))

print(f"\n{len(expected_parameters)} answer parameters; {len(FAILURES)} failures")
raise SystemExit(1 if FAILURES else 0)

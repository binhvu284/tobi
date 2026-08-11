"""Behavior checks for the Conductor compatibility context assembler."""

from __future__ import annotations

import inspect
import os
import sys
import tempfile
from dataclasses import FrozenInstanceError
from pathlib import Path

os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="tobi_context_assembler_"), "agent.db")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.chat_runtime_contracts import ContextItem, ContextManifest
from core.runtime import context_assembler


EXPECTED_RECALL_PROMPT = (
    "\n\n\u26a0 EPISODIC RECALL: The owner is asking about past conversations. "
    "Use the recall_conversations tool to retrieve relevant messages BEFORE responding. "
    "Extract the time reference (e.g., 'yesterday', 'last week') and topic from their "
    "message and pass them as the 'when' and 'query' args. "
    "If the owner asks broadly ('what did we discuss yesterday?'), summarize the returned "
    "messages. If they ask specifically ('when did we discuss X?'), report exact messages "
    "with timestamps and which session they came from."
)


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _item(source: str, content: str) -> ContextItem:
    return ContextItem(
        source=source,
        label=source,
        content=content,
        trust="trusted",
        relevance=1.0,
        token_cost=1,
    )


def _check_source_resolution() -> int:
    checks = 0
    _check("core.conductor" not in sys.modules, "assembler import must not load Conductor")
    checks += 1

    sources = context_assembler.ContextSources("owner", "tier", "manifest")
    prompt = context_assembler.PreparedPrompt("message", "system")
    for value, attribute in ((sources, "profile"), (prompt, "message")):
        try:
            setattr(value, attribute, "changed")
        except FrozenInstanceError:
            pass
        else:
            raise AssertionError(f"{type(value).__name__} must be immutable")
        checks += 1

    manifest = ContextManifest(mode="chat", token_budget=20)
    manifest.add(_item("owner_memory", "MANIFEST_OWNER"))
    manifest.add(_item("evolution", "MANIFEST_TIER"))
    manifest.add(_item("project", "PROJECT_CONTEXT"))
    calls: list[str] = []

    def forbidden_profile() -> str:
        raise AssertionError("manifest branch must not load legacy profile")

    def forbidden_tier() -> str:
        raise AssertionError("manifest branch must not load legacy tier context")

    def render(value: ContextManifest) -> str:
        calls.append("render")
        _check(value is manifest, "renderer received a different manifest")
        return "RENDERED_CONTEXT"

    resolved = context_assembler.resolve_context_sources(
        manifest,
        profile_loader=forbidden_profile,
        tier_loader=forbidden_tier,
        manifest_renderer=render,
    )
    _check(resolved == context_assembler.ContextSources("MANIFEST_OWNER", "MANIFEST_TIER", "RENDERED_CONTEXT"),
           "manifest sources changed")
    _check(calls == ["render"], "manifest renderer must run exactly once")
    checks += 2

    def failing_renderer(_manifest: ContextManifest) -> str:
        raise RuntimeError("renderer unavailable")

    rendered_fallback = context_assembler.resolve_context_sources(
        manifest,
        profile_loader=forbidden_profile,
        tier_loader=forbidden_tier,
        manifest_renderer=failing_renderer,
    )
    _check(rendered_fallback.manifest_text == "", "renderer failure must become empty context")
    _check(rendered_fallback.profile == "MANIFEST_OWNER", "renderer failure must keep owner memory")
    checks += 2

    calls.clear()

    def load_profile() -> str:
        calls.append("profile")
        return "LEGACY_OWNER"

    def load_tier() -> str:
        calls.append("tier")
        return "LEGACY_TIER"

    legacy = context_assembler.resolve_context_sources(
        None,
        profile_loader=load_profile,
        tier_loader=load_tier,
        manifest_renderer=lambda _manifest: (_ for _ in ()).throw(AssertionError("renderer called")),
    )
    _check(legacy == context_assembler.ContextSources("LEGACY_OWNER", "LEGACY_TIER", ""),
           "legacy sources changed")
    _check(calls == ["profile", "tier"], "legacy source order changed")
    checks += 2

    calls.clear()

    def failing_profile() -> str:
        calls.append("profile")
        raise RuntimeError("profile unavailable")

    failed_profile = context_assembler.resolve_context_sources(
        None,
        profile_loader=failing_profile,
        tier_loader=load_tier,
    )
    _check(failed_profile == context_assembler.ContextSources("", "LEGACY_TIER", ""),
           "legacy profile failure must become empty")
    _check(calls == ["profile", "tier"], "tier fallback must still run after profile failure")
    checks += 2
    return checks


def _check_prompt_and_messages() -> int:
    checks = 0
    calls: list[tuple] = []
    sources = context_assembler.ContextSources("OWNER", "TIER", "TURN")

    def build_prompt(profile, tools_enabled, surface, directives, extra_tools, **kwargs):
        calls.append(("prompt", profile, tools_enabled, surface, directives, extra_tools, kwargs))
        return "BASE_SYSTEM"

    def detect_recall(message: str) -> bool:
        calls.append(("recall", message))
        return True

    prepared = context_assembler.prepare_prompt_context(
        "original question",
        "we discussed this yesterday",
        sources,
        tools_enabled=True,
        surface="mc",
        directives="DIRECTIVE",
        extra_tools=["extra"],
        denied_tools={"denied"},
        allowed_tools={"allowed"},
        prompt_builder=build_prompt,
        recall_detector=detect_recall,
    )
    expanded = "original question\n\n[Attached content the owner shared]\nwe discussed this yesterday"
    _check(prepared.message == expanded, "attachment expansion changed")
    _check(prepared.system == "BASE_SYSTEM" + EXPECTED_RECALL_PROMPT, "recall prompt changed")
    prompt_call = calls[0]
    _check(prompt_call[:6] == ("prompt", "OWNER", True, "mc", "DIRECTIVE", ["extra"]),
           "prompt positional inputs changed")
    _check(prompt_call[6] == {
        "user_message": expanded,
        "denied_tools": {"denied"},
        "allowed_tools": {"allowed"},
        "tier_context": "TIER",
        "context_text": "TURN",
    }, "prompt keyword inputs changed")
    _check(calls[1] == ("recall", expanded), "recall must inspect the expanded message")
    checks += 5

    calls.clear()
    direct = context_assembler.prepare_prompt_context(
        "plain question",
        None,
        sources,
        tools_enabled=False,
        surface="telegram",
        directives=None,
        extra_tools=None,
        denied_tools=set(),
        allowed_tools=None,
        prompt_builder=build_prompt,
        recall_detector=lambda _message: (_ for _ in ()).throw(AssertionError("recall detector called")),
    )
    _check(direct.message == "plain question", "empty attachment must not alter message")
    _check(direct.system == "BASE_SYSTEM", "tools-disabled prompt gained recall text")
    _check(len(calls) == 1 and calls[0][0] == "prompt", "tools-disabled recall must short-circuit")
    checks += 3

    explicit_history = [{"role": "assistant", "content": "prior"}]
    original_history = list(explicit_history)
    explicit_messages = context_assembler.prepare_model_messages(
        "current",
        explicit_history,
        41,
        history_loader=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("history loader called")),
    )
    _check(explicit_messages == [*explicit_history, {"role": "user", "content": "current"}],
           "explicit history messages changed")
    _check(explicit_history == original_history, "input history was mutated")
    _check(explicit_messages is not explicit_history, "message assembly must copy the history list")
    checks += 3

    empty_messages = context_assembler.prepare_model_messages(
        "current",
        [],
        42,
        history_loader=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("empty history loaded")),
    )
    _check(empty_messages == [{"role": "user", "content": "current"}],
           "explicit empty history must bypass storage")
    checks += 1

    history_calls: list[tuple] = []

    def load_history(chat_id: int, limit: int = 0) -> list[dict]:
        history_calls.append((chat_id, limit))
        return [{"role": "user", "content": "stored"}]

    stored_messages = context_assembler.prepare_model_messages(
        "current",
        None,
        43,
        history_loader=load_history,
    )
    _check(history_calls == [(43, 6)], "fallback history must load exactly six turns")
    _check(stored_messages == [
        {"role": "user", "content": "stored"},
        {"role": "user", "content": "current"},
    ], "fallback history messages changed")
    checks += 2
    return checks


def _check_conductor_delegation() -> int:
    from core import brain, conductor, context_manager, model_router, task_classifier

    expected_parameters = [
        "message", "chat_id", "surface", "model", "history", "attachments_text", "directives",
        "extra_tools", "on_event", "on_delta", "denied_tools", "review_mode", "mode", "route",
        "allowed_tools", "context_manifest", "turn_id", "max_tool_steps", "step_tokens",
        "final_tokens", "usage_context", "recovery_checkpoint",
    ]
    _check(list(inspect.signature(conductor.answer).parameters) == expected_parameters,
           "Conductor public signature changed")
    checks = 1

    class FakeModel:
        last_finish_reason = "stop"

        def __init__(self, events: list[str]) -> None:
            self.events = events
            self.calls: list[tuple[list[dict], str]] = []

        def complete(self, messages, system=None, **_kwargs):
            self.events.append("complete")
            self.calls.append((messages, system or ""))
            return "Done, sir."

    original = {
        "get_llm": model_router.get_llm,
        "classify": task_classifier.classify,
        "profile": brain.profile_summary,
        "tier": conductor._build_tier_context,
        "prompt": conductor._system_prompt,
        "history": conductor._history,
        "recall": conductor._detect_past_reference,
        "pending": conductor._pending_all,
        "render": context_manager.prompt_context,
    }
    events: list[str] = []
    fake_model = FakeModel(events)
    prompt_inputs: list[tuple] = []
    try:
        conductor._pending_all = lambda _chat_id: []

        def profile() -> str:
            events.append("profile")
            return "LEGACY_OWNER"

        def tier() -> str:
            events.append("tier")
            return "LEGACY_TIER"

        def classify(message: str) -> str:
            events.append("classify")
            _check(message == "original question", "classification saw expanded attachments")
            return "QUESTION"

        def prompt_builder(profile_text, tools_enabled, surface, directives, extra_tools, **kwargs):
            events.append("prompt")
            prompt_inputs.append((profile_text, tools_enabled, surface, directives, extra_tools, kwargs))
            return "BASE_SYSTEM"

        def recall(message: str) -> bool:
            events.append("recall")
            return "yesterday" in message

        def get_llm(*_args, **_kwargs):
            events.append("model")
            return fake_model

        def history(chat_id: int, limit: int = 0) -> list[dict]:
            events.append("history")
            _check((chat_id, limit) == (77, 6), "Conductor history arguments changed")
            return [{"role": "assistant", "content": "stored reply"}]

        brain.profile_summary = profile
        conductor._build_tier_context = tier
        task_classifier.classify = classify
        conductor._system_prompt = prompt_builder
        conductor._detect_past_reference = recall
        model_router.get_llm = get_llm
        conductor._history = history

        response = conductor.answer(
            "original question",
            chat_id=77,
            model="test-model",
            history=None,
            attachments_text="we discussed this yesterday",
            directives="DIRECTIVE",
            extra_tools=["extra"],
            denied_tools={"denied"},
            allowed_tools={"allowed"},
            mode="chat",
        )
        _check(events == ["profile", "tier", "classify", "prompt", "recall", "model", "history", "complete"],
               f"Conductor context order changed: {events}")
        _check(response["intent"] == "QUESTION", "Conductor result intent changed")
        _check(prompt_inputs[0][0:5] == ("LEGACY_OWNER", True, "mc", "DIRECTIVE", ["extra"]),
               "Conductor prompt positional inputs changed")
        expanded = "original question\n\n[Attached content the owner shared]\nwe discussed this yesterday"
        _check(prompt_inputs[0][5]["user_message"] == expanded, "Conductor prompt missed attachment")
        _check(fake_model.calls[0] == ([
            {"role": "assistant", "content": "stored reply"},
            {"role": "user", "content": expanded},
        ], "BASE_SYSTEM" + EXPECTED_RECALL_PROMPT), "Conductor model context changed")
        checks += 5

        manifest = ContextManifest(mode="chat", token_budget=10)
        manifest.add(_item("owner_memory", "MANIFEST_OWNER"))
        manifest.add(_item("evolution", "MANIFEST_TIER"))
        events.clear()

        def render(value: ContextManifest) -> str:
            events.append("render")
            _check(value is manifest, "Conductor passed a different manifest")
            return "MANIFEST_CONTEXT"

        context_manager.prompt_context = render
        task_classifier.classify = lambda _message: events.append("classify") or "SMALLTALK"
        conductor._system_prompt = lambda *args, **kwargs: events.append("prompt") or "MANIFEST_SYSTEM"
        model_router.get_llm = lambda *_args, **_kwargs: events.append("model") or fake_model
        response = conductor.answer(
            "manifest question",
            chat_id=78,
            history=[],
            mode="chat",
            route="direct",
            context_manifest=manifest,
        )
        _check(events == ["render", "classify", "prompt", "model", "complete"],
               f"manifest context order changed: {events}")
        _check(response["intent"] == "SMALLTALK", "manifest result intent changed")
        _check(fake_model.calls[-1] == ([{"role": "user", "content": "manifest question"}], "MANIFEST_SYSTEM"),
               "manifest model context changed")
        checks += 3

        events.clear()
        brain.profile_summary = lambda: events.append("profile") or "OWNER"
        conductor._build_tier_context = lambda: events.append("tier") or "TIER"
        task_classifier.classify = lambda _message: events.append("classify") or "QUESTION"
        conductor._system_prompt = lambda *args, **kwargs: events.append("prompt") or "SYSTEM"
        conductor._detect_past_reference = lambda _message: events.append("recall") or False

        def fail_model(*_args, **_kwargs):
            events.append("model")
            raise RuntimeError("model unavailable")

        model_router.get_llm = fail_model
        conductor._history = lambda *_args, **_kwargs: events.append("history") or []
        failed = conductor.answer("question", chat_id=79, history=None, mode="chat")
        _check(events == ["profile", "tier", "classify", "prompt", "recall", "model"],
               "history loaded before failed model selection")
        _check(failed["intent"] == "QUESTION" and failed["error"] == "model unavailable",
               "model-down result changed")
        checks += 2
    finally:
        model_router.get_llm = original["get_llm"]
        task_classifier.classify = original["classify"]
        brain.profile_summary = original["profile"]
        conductor._build_tier_context = original["tier"]
        conductor._system_prompt = original["prompt"]
        conductor._history = original["history"]
        conductor._detect_past_reference = original["recall"]
        conductor._pending_all = original["pending"]
        context_manager.prompt_context = original["render"]
    return checks


if __name__ == "__main__":
    total = _check_source_resolution() + _check_prompt_and_messages() + _check_conductor_delegation()
    print(f"OK: {total} context-assembler checks passed")

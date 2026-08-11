"""Behavior checks for the Conductor compatibility intent router."""

from __future__ import annotations

import inspect
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.runtime import intent_router


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _check_pure_router_contract() -> int:
    checks = 0
    _check("core.conductor" not in sys.modules, "router import must not load Conductor")
    checks += 1

    decision = intent_router.ConductorIntentDecision("QUESTION", True)
    try:
        decision.intent = "SMALLTALK"
    except FrozenInstanceError:
        pass
    else:
        raise AssertionError("ConductorIntentDecision must be immutable")
    checks += 1

    seen: list[str] = []

    def classify(message: str) -> str:
        seen.append(message)
        return "SMALLTALK"

    decision = intent_router.resolve_intent("hello", "chat", None, classify)
    _check(seen == ["hello"], "router must classify the original message exactly once")
    _check(decision == intent_router.ConductorIntentDecision("SMALLTALK", False), "smalltalk must stay direct")
    checks += 2

    cases = [
        ("CODING", "chat", None, False),
        ("CODING", "agent", None, True),
        ("QUESTION", "chat", None, True),
        ("QUESTION", "chat", "direct", False),
        ("CODING", "agent", "direct", True),
        ("SMALLTALK", "chat", "tools", True),
        ("SMALLTALK", "chat", "", False),
    ]
    for classified_intent, mode, route, expected_tools in cases:
        decision = intent_router.resolve_intent(
            "message",
            mode,
            route,
            lambda _message, value=classified_intent: value,
        )
        _check(decision.intent == classified_intent, f"intent changed for {classified_intent}/{mode}/{route}")
        _check(decision.tools_enabled is expected_tools, f"wrong tool decision for {classified_intent}/{mode}/{route}")
        checks += 2

    def failing_classifier(_message: str) -> str:
        raise RuntimeError("classifier unavailable")

    fallback = intent_router.resolve_intent("message", "chat", None, failing_classifier)
    _check(fallback == intent_router.ConductorIntentDecision("QUESTION", True), "classifier failure must fail open to QUESTION tools")
    checks += 1

    from core import task_classifier

    original_classifier = task_classifier.classify
    try:
        task_classifier.classify = lambda _message: "SMALLTALK"
        patched = intent_router.resolve_intent("message", "chat", None)
    finally:
        task_classifier.classify = original_classifier
    _check(patched == intent_router.ConductorIntentDecision("SMALLTALK", False), "default classifier lookup must remain patchable")
    checks += 1

    for message in (
        "What did we discuss yesterday?",
        "Please recall our previous session.",
        "What were we discussing last week?",
        "We talked about this before.",
    ):
        _check(intent_router.needs_episodic_recall(message), f"missed past reference: {message}")
        checks += 1
    _check(not intent_router.needs_episodic_recall("Summarize this document."), "ordinary messages must not trigger recall")
    _check(not intent_router.needs_episodic_recall("What did we discuss yesterday?", False), "recall must not enable tools")
    checks += 2
    return checks


def _check_conductor_delegation() -> int:
    from core import brain, conductor, model_router, task_classifier

    expected_parameters = [
        "message",
        "chat_id",
        "surface",
        "model",
        "history",
        "attachments_text",
        "directives",
        "extra_tools",
        "on_event",
        "on_delta",
        "denied_tools",
        "review_mode",
        "mode",
        "route",
        "allowed_tools",
        "context_manifest",
        "turn_id",
        "max_tool_steps",
        "step_tokens",
        "final_tokens",
        "usage_context",
        "recovery_checkpoint",
    ]
    _check(list(inspect.signature(conductor.answer).parameters) == expected_parameters, "Conductor public signature changed")
    _check(conductor._detect_past_reference is intent_router.needs_episodic_recall, "Conductor must re-export the shared detector")
    checks = 2

    class FakeModel:
        last_finish_reason = "stop"

        def __init__(self) -> None:
            self.system_prompts: list[str] = []
            self.message_batches: list[list[dict]] = []

        def complete(self, messages, system=None, **_kwargs):
            self.system_prompts.append(system or "")
            self.message_batches.append(messages)
            return "Done, sir."

    fake_model = FakeModel()
    classified_messages: list[str] = []
    original_get_llm = model_router.get_llm
    original_classify = task_classifier.classify
    original_build_context = conductor._build_tier_context
    original_profile_summary = brain.profile_summary
    original_pending_all = conductor._pending_all
    try:
        model_router.get_llm = lambda *_args, **_kwargs: fake_model

        def classify(message: str) -> str:
            classified_messages.append(message)
            return "QUESTION"

        task_classifier.classify = classify
        conductor._build_tier_context = lambda *_args, **_kwargs: ""
        brain.profile_summary = lambda: ""
        conductor._pending_all = lambda _chat_id: []

        response = conductor.answer(
            "original question",
            model="test-model",
            history=[],
            attachments_text="we discussed this yesterday",
        )
        _check(classified_messages == ["original question"], "Conductor must classify before attachment expansion")
        _check(response["intent"] == "QUESTION", "Conductor must expose the routed intent")
        _check("EPISODIC RECALL" in fake_model.system_prompts[-1], "attachment-expanded message must trigger recall")
        _check(
            "we discussed this yesterday" in fake_model.message_batches[-1][-1]["content"],
            "attachment text must reach the model prompt",
        )
        checks += 4

        task_classifier.classify = lambda _message: "SMALLTALK"
        conductor.answer(
            "original question",
            model="test-model",
            history=[],
            attachments_text="we discussed this yesterday",
            route="direct",
        )
        _check("EPISODIC RECALL" not in fake_model.system_prompts[-1], "direct routing must not enable recall tools")
        checks += 1
    finally:
        model_router.get_llm = original_get_llm
        task_classifier.classify = original_classify
        conductor._build_tier_context = original_build_context
        brain.profile_summary = original_profile_summary
        conductor._pending_all = original_pending_all
    return checks


if __name__ == "__main__":
    total = _check_pure_router_contract() + _check_conductor_delegation()
    print(f"OK: {total} intent-router checks passed")

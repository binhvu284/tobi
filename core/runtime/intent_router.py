"""Pure compatibility intent routing for the legacy Conductor."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Optional

from core import task_classifier

Classifier = Callable[[str], str]

_PAST_REFERENCE_RE = re.compile(
    r"(yesterday|last\s+\w+|\d+\s*days?\s*ago|earlier|before|"
    r"what\s+did\s+we|do\s+you\s+remember|recall|when\s+did\s+we|"
    r"when\s+were\s+we|what\s+were\s+we\s+discuss\w*|what\s+have\s+we\s+been|"
    r"previous\s+(session|chat|conversation)|other\s+(session|chat|conversation)|"
    r"what\s+about\s+our|talked\s+about|discussed)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ConductorIntentDecision:
    """The classified intent and whether Conductor may enter its tool loop."""

    intent: str
    tools_enabled: bool


def resolve_intent(
    message: str,
    mode: str,
    route_override: Optional[str],
    classifier: Optional[Classifier] = None,
) -> ConductorIntentDecision:
    """Preserve Conductor's current classifier fallback and tool-routing rules."""

    classify = classifier if classifier is not None else task_classifier.classify
    try:
        intent = classify(message)
    except Exception:
        intent = "QUESTION"

    tools_enabled = route_override != "direct" if route_override else intent not in ("SMALLTALK", "CODING")
    if mode == "agent" and intent == "CODING":
        tools_enabled = True
    return ConductorIntentDecision(intent=intent, tools_enabled=tools_enabled)


def needs_episodic_recall(message: str, tools_enabled: bool = True) -> bool:
    """Return whether an eligible turn refers to earlier conversations."""

    return bool(tools_enabled and _PAST_REFERENCE_RE.search(message or ""))

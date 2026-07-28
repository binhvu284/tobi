"""Regression tests for the chat task classifier."""
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.task_classifier import classify  # noqa: E402


PASS = 0


def ok(name: str, condition: bool, detail: str = "") -> None:
    global PASS
    if not condition:
        raise AssertionError(f"{name}: {detail}")
    PASS += 1
    print(f"PASS {name}")


def expect(name: str, text: str, expected: str) -> None:
    ok(
        f"{name} input is ASCII",
        text.isascii(),
        f"non-ASCII input: {text!r}",
    )
    actual = classify(text)
    ok(name, actual == expected, f"expected {expected}, got {actual}")


def test_all_classifier_outcomes() -> None:
    cases = [
        ("smalltalk", "hello", "SMALLTALK"),
        ("coding", "please implement the webhook handler", "CODING"),
        ("project management", "create project launch tracker", "PROJECT_MGMT"),
        ("research", "research competitor pricing", "RESEARCH"),
        ("status", "show revenue status", "STATUS"),
        ("execution", "execute the pending task", "EXECUTION"),
        ("question", "what should I focus on next", "QUESTION"),
    ]

    for name, text, expected in cases:
        expect(name, text, expected)


def test_smalltalk_requires_less_than_sixty_characters() -> None:
    under_limit = "hi " + ("a" * 56)
    at_limit = "hi " + ("a" * 57)

    ok("under limit length", len(under_limit) == 59, str(len(under_limit)))
    ok("at limit length", len(at_limit) == 60, str(len(at_limit)))
    expect("smalltalk under 60 characters", under_limit, "SMALLTALK")
    expect("smalltalk at 60 characters", at_limit, "QUESTION")


def test_coding_word_outranks_project_word() -> None:
    expect(
        "coding outranks project",
        "implement create project flow",
        "CODING",
    )


if __name__ == "__main__":
    test_all_classifier_outcomes()
    test_smalltalk_requires_less_than_sixty_characters()
    test_coding_word_outranks_project_word()
    print(f"PASS total={PASS}")

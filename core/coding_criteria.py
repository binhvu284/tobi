"""Derive the checks a run must perform from what its acceptance criteria demand.

Acceptance criteria are authored from the plan; validation commands come from the policy's
mandatory list. Nothing reconciled the two, so a criterion could name a test the run would
never execute -- and the reviewer, correctly, refused to qualify the work for lack of
evidence that could not exist. Six consecutive runs (sessions 9-14) named a test file no
configured command ran; run 14 was blocked on exactly that gap while the code itself was
judged correct.

Criteria naming a check are the only class of criterion whose evidence is mechanical. This
module finds them and turns each into a command, so the checks artifact the reviewer reads
actually contains the result the criterion asks about. What no permitted command can run is
reported instead, so preflight can refuse the item before an agent run is spent on it.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence


# A criterion cites a check by naming its path: "leave tests/test_awakening.py fully green",
# "green under `python tests/test_task_classifier.py`". The lookbehind keeps the match from
# starting midway through a longer path.
_PY_PATH_RE = re.compile(r"(?<![A-Za-z0-9_./\\-])((?:[A-Za-z0-9_.-]+[/\\])*[A-Za-z0-9_.-]+\.py)")

INTERPRETER = "python"


def _normalize(raw: str) -> str:
    # Only a leading "./" is noise. `lstrip("./")` would eat the leading dots of "../../etc",
    # which is exactly the path shape the escape check downstream exists to catch.
    path = raw.replace("\\", "/")
    while path.startswith("./"):
        path = path[2:]
    return path


def is_test_path(relative: str) -> bool:
    """A path whose result a criterion can be judged against by running it."""
    path = _normalize(relative)
    name = path.rsplit("/", 1)[-1]
    return path.startswith("tests/") or name.startswith("test_") or name.endswith("_test.py")


def referenced_checks(criteria: Iterable[Any]) -> list[str]:
    """Every runnable test path named by the criteria, in the order they are mentioned."""
    found: list[str] = []
    for criterion in criteria:
        for match in _PY_PATH_RE.findall(str(criterion)):
            path = _normalize(match)
            if is_test_path(path) and path not in found:
                found.append(path)
    return found


def command_for(relative: str) -> list[str]:
    """The command that produces this check's evidence, in the shape the policy allows."""
    return [INTERPRETER, _normalize(relative)]


def covered_by(command: Sequence[Any], relative: str) -> bool:
    """True when `command` already runs `relative`, whatever form it invokes it in."""
    target = _normalize(relative)
    return any(_normalize(str(token)).endswith(target) for token in command)


def derive_checks(
    criteria: Iterable[Any],
    commands: Iterable[Sequence[Any]],
    *,
    repo_root: Path,
    assert_command: Callable[[Sequence[str]], Any] | None = None,
) -> dict[str, list[Any]]:
    """Reconcile the criteria against the commands the run will actually perform.

    Returns the commands to add so every named check is run (`add`), the checks that no
    permitted command can produce (`unverifiable`, a preflight blocker), and the checks that
    the run is expected to create before validation reaches them (`pending`, a warning --
    an item whose deliverable *is* the test legitimately names a file that does not exist
    yet, and the check failing until it does is the feedback the run needs).
    """
    root = Path(repo_root).resolve()
    existing = [list(command) for command in commands]
    add: list[list[str]] = []
    unverifiable: list[tuple[str, str]] = []
    pending: list[str] = []

    for relative in referenced_checks(criteria):
        if any(covered_by(command, relative) for command in existing + add):
            continue
        try:
            target = (root / relative).resolve()
            inside = target.is_relative_to(root)
        except (OSError, ValueError):
            target, inside = None, False
        if not inside:
            unverifiable.append((relative, "the path resolves outside the repository"))
            continue
        command = command_for(relative)
        if assert_command is not None:
            try:
                assert_command(command)
            except Exception as exc:  # policy refusal is the whole point of asking
                unverifiable.append((relative, str(exc)))
                continue
        add.append(command)
        if target is not None and not target.is_file():
            pending.append(relative)

    return {"add": add, "unverifiable": unverifiable, "pending": pending}

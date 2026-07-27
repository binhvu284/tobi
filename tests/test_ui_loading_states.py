"""Guard the loading affordance on every asynchronous control in Mission Control.

CLAUDE.md requires any control that triggers async work to show a loading state for the
duration and to re-enable on both success and failure. That rule kept being lost, because it
was per-site discipline: a button written without pending tracking looks the same in review
as one written with it, and nothing failed when it was missing. The visible symptom was a
screen that appeared frozen -- an owner action would refetch the whole page while every
section kept rendering correct-but-stale content with no motion anywhere.

These checks fail while any control in the app can trigger async work with no pending state.
They are deliberately shallow -- a parser would be better -- but they catch the regression
that actually happens: someone adds a plain <button onClick={...async...}> and ships it.
"""
from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "dashboard" / "src"
# Every component in the app, not a hand-maintained list. A list has to be remembered when a
# file is added, which is the same failure mode as remembering the loading state itself.
SURFACE = sorted(SRC.rglob("*.tsx"))

FAILURES: list[str] = []


def ok(label: str, condition: bool, detail: str = "") -> None:
    print(f"{'PASS' if condition else 'FAIL'} {label}{('  -> ' + detail) if detail and not condition else ''}")
    if not condition:
        FAILURES.append(label)


# --- the shared primitives exist and behave ------------------------------------------
async_ui = (SRC / "components" / "async-ui.tsx").read_text(encoding="utf-8")
for name in ("ActionButton", "BusyOverlay", "ActivityBar", "SectionSkeleton"):
    ok(f"async-ui exports {name}", f"export function {name}" in async_ui)

# The whole point of the primitive: a throwing action must still release the control.
action_body = async_ui[async_ui.index("export function ActionButton"):async_ui.index("export function BusyOverlay")]
ok("ActionButton clears pending in a finally, so a failed action re-enables it",
   "finally {" in action_body and "setPending(false)" in action_body.split("finally {")[1].split("}")[0])
ok("ActionButton refuses re-entry while pending",
   re.search(r"if \(pending \|\| busy \|\| disabled\) return", action_body) is not None)
ok("ActionButton is unmount-safe", "mounted.current" in action_body)
ok("ActionButton marks itself busy for assistive tech", "aria-busy" in action_body)
ok("reduced motion is respected",
   "prefers-reduced-motion" in (SRC / "index.css").read_text(encoding="utf-8"))

# --- the page never sits silent during page-scoped work -------------------------------
page = (SRC / "pages" / "Developer.tsx").read_text(encoding="utf-8")
ok("Developer renders an ActivityBar", "<ActivityBar" in page)
ok("the ActivityBar is driven by the action-busy flag", re.search(r"<ActivityBar pending=\{busy", page) is not None)
ok("tabs with no data yet render a skeleton, not an empty state",
   page.count("<SectionSkeleton") >= 2, str(page.count("<SectionSkeleton")))

# --- no async control ships without a pending affordance ------------------------------
def button_tags(source: str) -> list[str]:
    """Every <button ...> opening tag, whole.

    A naive `<button[^>]*>` is wrong here and produced five false positives on the first
    run: JSX handlers contain `=>`, so the scan ended at the arrow and never reached the
    `disabled` that followed it. Brace depth is tracked so the tag ends at its real `>`.
    """
    tags: list[str] = []
    for match in re.finditer(r"<button\b", source):
        depth, index = 0, match.end()
        while index < len(source):
            char = source[index]
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
            elif char == ">" and depth == 0:
                break
            index += 1
        tags.append(source[match.start():index])
    return tags


# High precision on purpose. A handler that awaits, or voids a promise, is unambiguously
# async work; a handler that merely opens a modal is not, and demanding a spinner there
# would train people to silence the check. Missing `disabled` on such a button means no
# pending state at all, which is exactly the regression this exists to stop.
ASYNC_HANDLER = re.compile(r"onClick=\{\s*(?:async\b|\(\)\s*=>\s*void\s)|await\s")
offenders: list[str] = []
scanned = buttons = 0
for path in SURFACE:
    tags = button_tags(path.read_text(encoding="utf-8"))
    scanned += 1
    buttons += len(tags)
    for tag in tags:
        if ASYNC_HANDLER.search(tag) and "disabled" not in tag:
            offenders.append(f"{path.relative_to(SRC)}: {' '.join(tag.split())[:100]}")

ok(f"every async button in the app carries a pending state "
   f"({buttons} buttons across {scanned} components)",
   not offenders, f"{len(offenders)} unguarded — use ActionButton from components/async-ui:\n    "
   + "\n    ".join(offenders[:8]))

# The files that had zero pending affordance at all, pinned so they cannot regress to it.
for name, path in (("DevelopmentGoals.tsx", SRC / "components" / "developer" / "DevelopmentGoals.tsx"),
                   ("SystemView.tsx", SRC / "pages" / "developer" / "SystemView.tsx")):
    source = path.read_text(encoding="utf-8")
    ok(f"{name} uses the shared pending primitive", "ActionButton" in source)

# The goal menu used to close before awaiting, so its actions ran with nothing on screen.
goals = (SRC / "components" / "developer" / "DevelopmentGoals.tsx").read_text(encoding="utf-8")
run_body = goals[goals.index("const run = async"):goals.index("const run = async") + 700]
ok("the goal menu closes after its command resolves, not before",
   run_body.index("await onCommand") < run_body.index("setOpen(false)"))

print(f"\n{'ALL' if not FAILURES else str(len(FAILURES)) + ' OF'} "
      f"{'UI LOADING-STATE CHECKS PASSED' if not FAILURES else 'CHECKS FAILED: ' + ', '.join(FAILURES)}")
raise SystemExit(1 if FAILURES else 0)

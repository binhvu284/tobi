"""A page that cannot load its data must say so.

`pages/Storage.tsx` shipped this, and 64 more like it across 23 files:

    getStorageOverview().then(setOv).catch(() => {})

If the request fails, nothing happens. The page renders exactly as it would with no data, so
the owner cannot tell an empty result from a broken one. On 2026-08-01 he lost an afternoon to
precisely that ambiguity in two other places -- Health reported "LLM OK" while every Chat
request failed, and Chat blamed a model that was never asked. Both are fixed. This is the same
lie told by omission, in the UI.

The rule is already written in CLAUDE.md: error messages must be true and actionable. It kept
being lost because it was per-site discipline -- a swallowed catch looks identical to a handled
one in review, and nothing breaks when it is missing. `tests/test_ui_loading_states.py` solved
that same problem for pending states by scanning every component instead of trusting memory.
This is its sibling.

These checks fail while any component can drop a data-fetch failure on the floor.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "dashboard" / "src"
# Every component, not a hand-maintained list — a list has to be remembered when a file is
# added, which is the same failure mode as remembering the error state itself.
SURFACE = sorted(list(SRC.rglob("*.tsx")) + list(SRC.rglob("*.ts")))

FAILURES: list[str] = []


def ok(label: str, condition: bool, detail: str = "") -> None:
    print(f"{'PASS' if condition else 'FAIL'} {label}{('  -> ' + detail) if detail and not condition else ''}")
    if not condition:
        FAILURES.append(label)


# An empty handler: `.catch(() => {})`, `.catch(() => { /* note */ })`, or a bare `catch {}`.
_EMPTY_ARROW = re.compile(r"\.catch\(\s*\(\s*[\w$]*\s*\)\s*=>\s*\{\s*(?:/\*.*?\*/|//[^\n]*)?\s*\}\s*\)", re.S)
_EMPTY_BLOCK = re.compile(r"\bcatch\s*(?:\([^)]*\))?\s*\{\s*(?:/\*.*?\*/|//[^\n]*)?\s*\}", re.S)
# Silence is sometimes right, and banning it outright would push noise into the places it is
# right. `components/news/TableRefresh.tsx` swallows a failed poll because the *next* poll is
# the retry; telling the owner about a transient blip he cannot act on is worse than saying
# nothing. What was missing was never the handling — it was the decision being visible.
#
# So the rule is not "never be silent". It is "say why", in the handler, where the next reader
# sees it. An unexplained empty catch fails; `/* silent: the next poll retries */` passes.
#
# Most sites are neither: background work whose failure the owner should hear about once, but
# which must not blank the page. `softFail()` in lib/report.ts is that answer, and it is a real
# handler rather than a comment — it logs every time and notifies once per subject per minute.
_DELIBERATE = re.compile(r"(?:/\*|//)\s*silent:\s*\S", re.I)
# Guards around browser storage and parsing are legitimately silent: there is nothing to tell
# the owner when a cached preference fails to read, and the page still works.
_LOCAL_ONLY = re.compile(
    r"(sessionStorage|localStorage|JSON\.parse|matchMedia|navigator\.|document\.|window\.|"
    r"URL\.|structuredClone|\.play\(|AudioContext|ResizeObserver|IntersectionObserver|"
    r"clipboard|scrollIntoView|requestAnimationFrame|cancelAnimationFrame|\.close\(\)|"
    r"AbortError|abort\(\))")
# A data fetch: one of the api.*.ts helpers, or an explicit request.
_FETCH = re.compile(r"\b(get|list|load|fetch|post|put|patch|delete|run|start|stop|save|create|"
                    r"update|remove|send|refresh|sync|probe|test)[A-Z]\w*\s*\(|\bfetch\s*\(|\bawait\s+api")


def swallowed(path: Path) -> list[str]:
    """Silent handlers in `path` whose guarded work looks like a data fetch."""
    source = path.read_text(encoding="utf-8", errors="replace")
    found: list[str] = []
    for pattern in (_EMPTY_ARROW, _EMPTY_BLOCK):
        for match in pattern.finditer(source):
            if _DELIBERATE.search(match.group(0)):
                continue                      # silence with a stated reason is a decision
            context = source[max(0, match.start() - 260): match.end() + 60]
            if _LOCAL_ONLY.search(context):
                continue
            if not _FETCH.search(context):
                continue
            line = source[:match.start()].count("\n") + 1
            found.append(f"{path.relative_to(SRC).as_posix()}:{line}")
    return found


# --- the primitive exists and does its job ------------------------------------------------
async_ui_path = SRC / "components" / "async-ui.tsx"
async_ui = async_ui_path.read_text(encoding="utf-8", errors="replace")

ok("async-ui exports LoadFailure", "export function LoadFailure" in async_ui)

if "export function LoadFailure" in async_ui:
    rest = async_ui[async_ui.index("export function LoadFailure"):]
    body = rest.split("\nexport function ")[0]
    ok("LoadFailure shows the real reason, not a generic phrase",
       re.search(r"\{\s*(reason|message|detail)\s*\}", body) is not None, body[:200])
    ok("LoadFailure offers a retry the owner can press",
       "onRetry" in body and "ActionButton" in body, body[:200])
    ok("LoadFailure says what failed to load, in the owner's terms",
       "what" in body, body[:200])
    ok("LoadFailure announces itself to assistive tech",
       'role="alert"' in body or "aria-live" in body, body[:200])

# --- no component drops a data-fetch failure on the floor ---------------------------------
offenders: dict[str, list[str]] = {}
for path in SURFACE:
    hits = swallowed(path)
    if hits:
        offenders[path.relative_to(SRC).as_posix()] = hits

total = sum(len(v) for v in offenders.values())
detail = ""
if offenders:
    worst = sorted(offenders.items(), key=lambda kv: -len(kv[1]))[:8]
    detail = f"{total} in {len(offenders)} files: " + ", ".join(
        f"{name}({len(hits)})" for name, hits in worst)
ok("no component swallows a data-fetch failure silently", total == 0, detail)

# --- the sibling rule is not weakened -----------------------------------------------------
ok("the pending-state primitives are still exported",
   all(f"export function {n}" in async_ui
       for n in ("ActionButton", "BusyOverlay", "ActivityBar", "SectionSkeleton")))

# --- the background-failure reporter behaves --------------------------------------------
report = (SRC / "lib" / "report.ts")
ok("lib/report.ts exists for background failures", report.is_file())
if report.is_file():
    text = report.read_text(encoding="utf-8", errors="replace")
    ok("softFail is exported", "export function softFail" in text)
    ok("a flapping poll is reported once, not on every tick", "QUIET_MS" in text and "lastToldAt" in text)
    ok("every failure is still logged even while quiet", "console.warn" in text)
    ok("an abort the app caused itself is not reported as a failure", "AbortError" in text)

if offenders and "--list" in sys.argv:
    print("\nevery site:")
    for name, hits in sorted(offenders.items()):
        for hit in hits:
            print(f"  {hit}")

print(f"\n{'ALL' if not FAILURES else str(len(FAILURES)) + ' OF'} "
      f"{'SILENT-FAILURE CHECKS PASSED' if not FAILURES else 'CHECKS FAILED: ' + ', '.join(FAILURES)}")
raise SystemExit(1 if FAILURES else 0)

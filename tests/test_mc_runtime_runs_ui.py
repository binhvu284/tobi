"""Focused source checks for the T13 shared Runs Center frontend."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


checks = {
    "typed runtime API uses bounded snapshot endpoints": lambda: (
        "/api/runtime/runs?" in read("dashboard/src/api.runtime.ts")
        and "/snapshot?after=" in read("dashboard/src/api.runtime.ts")
    ),
    "one shared store backs both frontend consumers": lambda: (
        "useRuntimeStore" in read("dashboard/src/pages/Runs.tsx")
        and "useRuntimeStore" in read("dashboard/src/components/developer/DeveloperRuntimeLoop.tsx")
    ),
    "store reconnects from the latest event sequence": lambda: (
        "current?.last_sequence ?? 0" in read("dashboard/src/stores/runtime.ts")
        and "item.sequence === event.sequence" in read("dashboard/src/stores/runtime.ts")
    ),
    "Runs route is registered and lazy loaded": lambda: (
        "import('./pages/Runs')" in read("dashboard/src/App.tsx")
        and 'path="/runs"' in read("dashboard/src/App.tsx")
    ),
    "Runs is available in navigation and workspace tabs": lambda: (
        "to: '/runs'" in read("dashboard/src/components/AppShell.tsx")
        and "route: '/runs'" in read("dashboard/src/context/WorkspaceTabsContext.tsx")
    ),
    "Runs has all four bounded evidence views": lambda: all(
        label in read("dashboard/src/pages/Runs.tsx")
        for label in ("Timeline", "Trace", "Evals", "Context")
    ),
    "Developer loop selection uses the shared preference API": lambda: (
        "saveLoopSelection" in read("dashboard/src/components/developer/DeveloperRuntimeLoop.tsx")
        and "/api/runtime/preferences/developer-loop" in read("dashboard/src/api.runtime.ts")
    ),
    "frontend projection does not model raw request or secret fields": lambda: all(
        forbidden not in (
            read("dashboard/src/api.runtime.ts")
            + read("dashboard/src/stores/runtime.ts")
            + read("dashboard/src/pages/Runs.tsx")
        )
        for forbidden in ("request_json", "objective_text", "secret_value", "raw_error")
    ),
}


failed = []
for name, check in checks.items():
    if check():
        print(f"PASS {name}")
    else:
        print(f"FAIL {name}")
        failed.append(name)

if failed:
    raise SystemExit(f"FAIL: {len(failed)} of {len(checks)} T13 UI checks")
print(f"PASS: {len(checks)} T13 Runs UI checks")

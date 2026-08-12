"""`/api/health` must not freeze the app while it checks itself.

Measured warm on 2026-08-12: `/api/health` answered in 4,076 ms while every other endpoint the
pages poll answered in 8-30 ms. The cause is one line:

    r = requests.get(f"http://localhost:{API_PORT}/health", timeout=2)   api/routers/health.py

`requests` is synchronous, and it sits inside an `async def`. An async handler that blocks does
not merely make itself slow -- it holds the event loop, so every other request in flight waits
behind it. Opening the Health page paused the whole app, and when the API server was not
listening it paused it for four seconds.

`timeout=2` did not cap it either: that is two seconds to connect *and* two to read, so an
unreachable port costs the sum.

These checks fail while the endpoint can block the loop, and while its response shape drifts.
No network is required: the port used is deliberately closed.
"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.environ.setdefault("DB_PATH", os.path.join(tempfile.mkdtemp(prefix="tobi_hbudget_"), "agent.db"))

# A port nothing is listening on, so the self-probe takes its worst path every time.
os.environ["API_PORT"] = "59_999".replace("_", "")

from core.database import init_database  # noqa: E402

init_database()

from api.routers import health as health_module  # noqa: E402

BUDGET_MS = 500

FAILURES: list[str] = []


def ok(label: str, condition: bool, detail: str = "") -> None:
    print(f"{'PASS' if condition else 'FAIL'} {label}{('  -> ' + detail) if detail and not condition else ''}")
    if not condition:
        FAILURES.append(label)


asyncio.run(health_module.api_health())          # warm: imports, first DB touch
start = time.perf_counter()
report = asyncio.run(health_module.api_health())
elapsed_ms = (time.perf_counter() - start) * 1000

ok(f"/api/health answers within {BUDGET_MS}ms with the API port closed",
   elapsed_ms < BUDGET_MS, f"took {elapsed_ms:.0f}ms")

# The endpoint may get faster; it may not get quieter. Every key the Health page reads has to
# survive, or the page breaks in exchange for speed.
for key in ("overall", "score", "up", "configured", "activity", "data", "recent_errors"):
    ok(f"response still carries `{key}`", key in report, str(sorted(report))[:160])

ok("the api_server probe still reports a verdict",
   isinstance(report.get("up", {}).get("api_server"), dict), str(report.get("up", {}))[:160])
ok("an unreachable API server is reported as down, not as healthy",
   report["up"]["api_server"].get("ok") is False, str(report["up"]["api_server"])[:160])

# The loop must stay free while the probe runs. If the handler blocks, a task scheduled
# alongside it cannot make progress until the whole handler returns.
async def _loop_stays_free() -> float:
    ticks = 0

    async def heartbeat() -> None:
        nonlocal ticks
        while True:
            ticks += 1
            await asyncio.sleep(0.01)

    beat = asyncio.create_task(heartbeat())
    await asyncio.sleep(0)
    await health_module.api_health()
    beat.cancel()
    return ticks

ok("the event loop keeps running while the health probe waits",
   asyncio.run(_loop_stays_free()) > 1, "the loop was blocked for the whole call")

print(f"\n{'ALL' if not FAILURES else str(len(FAILURES)) + ' OF'} "
      f"{'HEALTH BUDGET CHECKS PASSED' if not FAILURES else 'CHECKS FAILED: ' + ', '.join(FAILURES)}")
raise SystemExit(1 if FAILURES else 0)

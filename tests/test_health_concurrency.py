"""The Health button must cost its slowest check, not the sum of all of them.

Measured on 2026-08-13, one real run of `/api/health/deep`:

    chat self-check   18,453 ms
    tavily             1,557 ms
    telegram           1,549 ms
    five integrations      0 ms (not configured)
    wall clock        20-50 s

Nothing in that list depends on anything else -- Telegram has no idea what the chat check is
doing -- and they still ran strictly one after another, showing nothing until the last one
returned.

This is a regression introduced by `be5e198`. Before it, the first row was a one-second
`llm_complete("Reply with exactly: OK")` ping, and running the checks in sequence cost almost
nothing. Replacing that ping with a real two-turn conversation was right -- it is what made the
check honest, and it caught the `input_text` defect the ping could not see -- but it turned a
four-second button into a fifty-second one, and the button was not re-measured afterwards.

Wall-clock timing cannot prove the fix: a live model call swings by tens of seconds run to run.
So concurrency is proven by construction instead. Every check is stubbed to sleep a fixed
250 ms; run together they finish in about 250 ms, run in sequence they cannot beat their sum.

No network. No model calls.
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
os.environ.setdefault("DB_PATH", os.path.join(tempfile.mkdtemp(prefix="tobi_hconc_"), "agent.db"))

from core.database import init_database  # noqa: E402

init_database()

from api.routers import health as health_module  # noqa: E402

STUB_MS = 250
CHECK_COUNT = 8          # chat self-check + telegram + tavily + five integrations
BUDGET_MS = 500          # concurrent: ~250ms. sequential: 8 x 250 = 2,000ms.

FAILURES: list[str] = []


def ok(label: str, condition: bool, detail: str = "") -> None:
    print(f"{'PASS' if condition else 'FAIL'} {label}{('  -> ' + detail) if detail and not condition else ''}")
    if not condition:
        FAILURES.append(label)


class _Stub:
    """Every outbound check, replaced by a fixed sleep so the shape of the run is measurable."""

    def __init__(self, *, fail: str = "") -> None:
        self.fail = fail
        self.started: list[float] = []

    def sleep(self, label: str = "") -> None:
        self.started.append(time.perf_counter())
        time.sleep(STUB_MS / 1000)
        if self.fail and self.fail == label:
            raise RuntimeError(f"{label} is down")


stub = _Stub()
_real_requests_get = None


def _install_stubs(fail: str = "") -> _Stub:
    """Replace every network and model call the deep check makes."""
    global stub
    stub = _Stub(fail=fail)

    import requests

    def fake_get(url, *a, **k):
        stub.sleep("telegram" if "telegram" in str(url) else "http")

        class R:
            status_code = 200
            headers = {"content-type": "application/json"}
            ok = True

            @staticmethod
            def json():
                return {"ok": True, "result": {"username": "stub"}}
        return R()

    def fake_post(url, *a, **k):
        stub.sleep("tavily")

        class R:
            status_code = 200
            ok = True

            @staticmethod
            def json():
                return {"results": []}
        return R()

    requests.get = fake_get
    requests.post = fake_post
    os.environ["TELEGRAM_BOT_TOKEN"] = "bot0:stub"
    os.environ["TAVILY_API_KEY"] = "stub"

    from core import chat_self_check

    def fake_self_check(**_kwargs):
        stub.sleep("llm")
        return {"state": "working", "ok": True, "detail": "stubbed",
                "tools_used": ["list_projects"], "model_turns": 2, "latency_ms": STUB_MS}

    chat_self_check.run_self_check = fake_self_check

    class _Inst:
        def is_available(self) -> bool:
            return True

        def test(self) -> dict:
            stub.sleep("integration")
            return {"ok": True, "detail": "stubbed"}

    from core import integrations
    integrations._integrations = {f"svc{i}": _Inst for i in range(5)}
    return stub


_install_stubs()

# --- 1. the checks run together --------------------------------------------------------
start = time.perf_counter()
report = asyncio.run(health_module.api_health_deep())
elapsed_ms = (time.perf_counter() - start) * 1000

ok(f"{CHECK_COUNT} checks of {STUB_MS}ms finish within {BUDGET_MS}ms",
   elapsed_ms < BUDGET_MS,
   f"took {elapsed_ms:.0f}ms — sequential would be about {CHECK_COUNT * STUB_MS}ms")

# Overlap is the property; the budget above could in principle be met by a faster machine
# running them one at a time, so assert the starts actually interleave.
if len(stub.started) >= 2:
    spread_ms = (max(stub.started) - min(stub.started)) * 1000
    ok("the checks start together rather than one after another",
       spread_ms < STUB_MS, f"first and last started {spread_ms:.0f}ms apart")

# --- 2. the answer is unchanged ---------------------------------------------------------
for key in ("timestamp", "llm", "integrations", "summary"):
    ok(f"response still carries `{key}`", key in report, str(sorted(report))[:160])
for key in ("ok", "detail", "latency_ms"):
    ok(f"each check still reports `{key}`", key in report["llm"], str(sorted(report["llm"]))[:160])
ok("the summary still counts every check",
   report["summary"]["total"] == len(report["integrations"]) + 1,
   str(report["summary"]))

# --- 3. a check's own duration survives the overlap --------------------------------------
# Once they run together, wall clock says nothing about which one is slow. Each has to keep
# reporting its own time or the page loses the only number that identifies the culprit.
durations = [c["latency_ms"] for c in report["integrations"].values()] + [report["llm"]["latency_ms"]]
ok("each check reports its own duration, not the wall clock",
   all(0 < d < STUB_MS * 3 for d in durations), str(durations))

# --- 4. one broken check must not take the others down ------------------------------------
_install_stubs(fail="tavily")
broken = asyncio.run(health_module.api_health_deep())
ok("a failing check is reported as failed", broken["integrations"]["tavily"]["ok"] is False,
   str(broken["integrations"].get("tavily"))[:160])
ok("the other checks still return their results",
   broken["llm"]["ok"] is True and broken["integrations"]["telegram"]["ok"] is True,
   str(broken["integrations"])[:200])

# --- 5. the loop stays free throughout ----------------------------------------------------
async def _longest_block_ms(coro_factory) -> float:
    """Longest gap between heartbeat ticks while the handler runs.

    Counting ticks is the wrong measure: a handler that finishes in 5ms yields almost none,
    which reads as "blocked" when it is simply fast. The gap is the property — a blocked loop
    cannot tick at all for the duration of the block.
    """
    gaps: list[float] = []
    last = time.perf_counter()

    async def heartbeat() -> None:
        nonlocal last
        while True:
            now = time.perf_counter()
            gaps.append(now - last)
            last = now
            await asyncio.sleep(0.005)

    beat = asyncio.create_task(heartbeat())
    await asyncio.sleep(0.02)          # let the heartbeat settle before the work starts
    gaps.clear()
    last = time.perf_counter()
    await coro_factory()
    beat.cancel()
    return (max(gaps) if gaps else 0.0) * 1000


# The stubs sleep 250ms per check, so a blocking implementation shows a gap of at least that.
MAX_BLOCK_MS = 120

_install_stubs()
deep_block = asyncio.run(_longest_block_ms(health_module.api_health_deep))
ok("the event loop keeps running during the deep check",
   deep_block < MAX_BLOCK_MS, f"loop frozen for {deep_block:.0f}ms in one stretch")

from api.routers import genesis as genesis_module  # noqa: E402


class _Request:
    """Minimum the handler touches: it only reads the base URL to build a redirect."""
    url = type("U", (), {"scheme": "http", "netloc": "127.0.0.1:8090"})()
    base_url = "http://127.0.0.1:8090/"
    headers: dict = {}


_install_stubs()
# Force the branch that actually calls out: an unconnected account skips it entirely, which
# would prove nothing.
class _Google:
    USERINFO_URL = "https://example.invalid/userinfo"

    def is_connected(self) -> bool:
        return True

    def is_available(self) -> bool:
        return True

    def _get_valid_access_token(self) -> str:
        return "stub-token"


from core import integrations as _integrations_module  # noqa: E402
_integrations_module.GoogleIntegration = _Google
genesis_module._google_redirect_uri = lambda _r: "http://127.0.0.1:8090/callback"

google_block = asyncio.run(_longest_block_ms(lambda: genesis_module.google_oauth_status(_Request())))
ok("the event loop keeps running during the Google status check",
   google_block < MAX_BLOCK_MS, f"loop frozen for {google_block:.0f}ms in one stretch")

print(f"\n{'ALL' if not FAILURES else str(len(FAILURES)) + ' OF'} "
      f"{'HEALTH CONCURRENCY CHECKS PASSED' if not FAILURES else 'CHECKS FAILED: ' + ', '.join(FAILURES)}")
raise SystemExit(1 if FAILURES else 0)

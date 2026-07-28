"""A failing connection test must say what failed.

Saving a GitHub App is gated on its test passing -- `connect_integration` puts the candidate
values in the environment, runs the test, and rolls back without persisting anything if the
test says no. That is the right shape: a bad key should not reach the vault. It only works if
the owner can see *why* it said no.

Every connector test caught bare `Exception` and returned "check your connection". That one
sentence covered a 404 from an installation id that points at nothing, a 401 from a revoked
key, a `PolicyDenied` raised before any packet left the process, and an invalid PEM. The owner
is sent to check their wifi while the real cause sits in the discarded exception -- which is
exactly what happened here: three App credentials could not be saved, Update appeared to do
nothing, and the only clue offered was a network error on a working connection.

Same defect class as `internal_error: TypeError` in the coding agent: the handler knew what
went wrong and threw it away.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import integrations_registry as registry  # noqa: E402

FAILURES: list[str] = []


def ok(label: str, condition: bool, detail: str = "") -> None:
    print(f"{'PASS' if condition else 'FAIL'} {label}{('  -> ' + detail) if detail and not condition else ''}")
    if not condition:
        FAILURES.append(label)


# --- the reason helper --------------------------------------------------------------------
class _Boom(RuntimeError):
    pass


if not hasattr(registry, "_reason"):
    ok("integrations_registry exposes a reason helper", False, "registry._reason is missing")
    print("\n1 OF CHECKS FAILED: integrations_registry exposes a reason helper")
    raise SystemExit(1)

message = registry._reason(_Boom("GitHub App private key is invalid."), "Could not reach GitHub.")
ok("the exception's own message survives", "private key is invalid" in message, message)
ok("the exception type is named", "_Boom" in message, message)
ok("the friendly fallback is kept as context", "Could not reach GitHub" in message, message)
ok("an empty exception falls back rather than emitting a bare dash",
   registry._reason(_Boom(""), "Could not reach GitHub.") == "Could not reach GitHub.",
   registry._reason(_Boom(""), "Could not reach GitHub."))
ok("the message is bounded", len(registry._reason(_Boom("x" * 5000), "Nope.")) <= 400)

# --- no connector test is still blind ------------------------------------------------------
source = (ROOT / "core" / "integrations_registry.py").read_text(encoding="utf-8")
ok("no test still reports a bare connection error",
   "check your connection." not in source,
   [line.strip() for line in source.splitlines() if "check your connection." in line][:3])
bound = source.count("except Exception as exc:")
used = source.count("_reason(exc,")
ok("every handler that reports a reason binds the exception", bound >= used and used >= 8,
   f"bound={bound} used={used}")

# --- the real path, driven end to end ------------------------------------------------------
saved = {name: os.environ.get(name) for name in
         ("GITHUB_APP_ID", "GITHUB_APP_INSTALLATION_ID", "GITHUB_APP_PRIVATE_KEY")}
try:
    os.environ["GITHUB_APP_ID"] = "1"
    os.environ["GITHUB_APP_INSTALLATION_ID"] = "0"
    os.environ["GITHUB_APP_PRIVATE_KEY"] = "definitely not a PEM"
    passed, detail = registry._test_github()
    ok("an unusable App key fails the test", passed is False, str(passed))
    ok("and the owner is told it is the key, not the network",
       "private key" in detail.lower() and "check your connection" not in detail.lower(), detail)

    # Partly-filled App config used to fall through to the token test and report plain success,
    # which reads as "configured" while Developer push/PR is still dead.
    del os.environ["GITHUB_APP_PRIVATE_KEY"]
    source_fn = source[source.index("def _test_github"):][:1400]
    ok("a partly-configured App is called out rather than reported as success",
       "Coding App not tested" in source_fn and "still missing" in source_fn, source_fn[:200])
finally:
    for name, value in saved.items():
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value

print(f"\n{'ALL' if not FAILURES else str(len(FAILURES)) + ' OF'} "
      f"{'INTEGRATION REASON CHECKS PASSED' if not FAILURES else 'CHECKS FAILED: ' + ', '.join(FAILURES)}")
raise SystemExit(1 if FAILURES else 0)

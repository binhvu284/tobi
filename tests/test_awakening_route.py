"""Route-level regression checks for Awakening connector verification."""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_TMP = tempfile.mkdtemp(prefix="tobi_awakening_route_")
os.environ["DB_PATH"] = os.path.join(_TMP, "agent.db")
os.environ["GOOGLE_CLIENT_ID"] = ""
os.environ["GOOGLE_CLIENT_SECRET"] = ""

from core.database import get_connection, init_database  # noqa: E402

init_database()

from api import dashboard  # noqa: E402
from api.routers import genesis  # noqa: E402
from core import awakening, integrations, vault  # noqa: E402


PASS = 0


def ok(name: str, condition: bool, detail: str = "") -> None:
    global PASS
    if not condition:
        raise AssertionError(f"{name}: {detail}")
    PASS += 1
    print(f"PASS {name}")


# Keep the test hermetic: exercise route behavior without setting up real vault crypto.
#
# The guard is patched on api.routers.genesis because that is the module whose globals
# the handlers below actually resolve. The handlers are still called as dashboard.* —
# they are re-exported there — but since the Phase 1 split they are DEFINED in genesis
# and bind _vault_guard from api.deps at import time, so rebinding the (now unused) name
# in dashboard's namespace would silently leave the real guard in place.
# The vault.* and dashboard.registry.* patches below need no such change: those mutate
# attributes on a shared module object, which every importer sees.
original_guard = genesis._vault_guard
original_key = vault._key
original_encrypt = vault._encrypt
original_inject = vault.inject_env
genesis._vault_guard = lambda _session: None
vault._key = b"test-key"
vault._encrypt = lambda key, name, value: (b"cipher", b"nonce")
vault.inject_env = lambda conn: 0

try:
    body = dashboard.IntegrationConnectReq(fields={
        "GOOGLE_CLIENT_ID": "client-id",
        "GOOGLE_CLIENT_SECRET": "client-secret",
    })
    connected = asyncio.run(dashboard.connect_integration("google", body, "test-session"))
    ok("credential-stage connect succeeds", connected.get("ok") is True)
    ok("credential-stage connect is explicitly unverified", connected.get("verified") is False)

    conn = get_connection()
    rows = conn.execute(
        "SELECT test_status,last_tested_at FROM vault_secrets "
        "WHERE integration_id='google' ORDER BY name"
    ).fetchall()
    state = awakening.status_map(conn)["external_read_access"]
    conn.close()
    ok("credential-stage rows remain untested", len(rows) == 2 and all(r[0] == "untested" for r in rows))
    ok("credential-stage rows carry no verified timestamp", all(r[1] is None for r in rows))
    ok("Awakening reports Google credentials without OAuth as partial", state == "partial", state)

    tested = asyncio.run(dashboard.test_integration_endpoint("google", "test-session"))
    ok("Google setup test can guide the OAuth step", tested.get("ok") is True)
    ok("Google setup test still does not claim read access", tested.get("verified") is False)
    conn = get_connection()
    rows = conn.execute(
        "SELECT test_status,last_tested_at FROM vault_secrets "
        "WHERE integration_id='google' ORDER BY name"
    ).fetchall()
    conn.close()
    ok("Test endpoint preserves untested state until OAuth", all(r[0] == "untested" and r[1] is None for r in rows))

    # The OAuth callback is the point where Google may become verified. Stub only the remote
    # exchange/test while exercising the real callback persistence path.
    original_google = integrations.GoogleIntegration
    original_registry_test = dashboard.registry.test_integration
    original_registry_confirm = dashboard.registry.test_confirms_read_access

    class FakeGoogle:
        def __init__(self):
            self.redirect_uri = ""

        def is_available(self):
            return True

        def exchange_code(self, code):
            return {"access_token": "stub"}

    integrations.GoogleIntegration = FakeGoogle
    dashboard.registry.test_integration = lambda integration_id: (True, "Google read verified.")
    dashboard.registry.test_confirms_read_access = lambda integration_id: True
    try:
        request = SimpleNamespace(headers={"host": "localhost:8080"}, url=SimpleNamespace(scheme="http"))
        response = asyncio.run(dashboard.google_oauth_callback(request, code="stub-code"))
    finally:
        integrations.GoogleIntegration = original_google
        dashboard.registry.test_integration = original_registry_test
        dashboard.registry.test_confirms_read_access = original_registry_confirm
    ok("successful OAuth callback completes normally", response.status_code == 200)
    conn = get_connection()
    rows = conn.execute(
        "SELECT test_status,last_tested_at FROM vault_secrets "
        "WHERE integration_id='google' ORDER BY name"
    ).fetchall()
    conn.close()
    ok("successful OAuth callback records fresh verified evidence",
       len(rows) == 2 and all(r[0] == "ok" and r[1] is not None for r in rows))
finally:
    genesis._vault_guard = original_guard
    vault._key = original_key
    vault._encrypt = original_encrypt
    vault.inject_env = original_inject

print(f"ALL {PASS} AWAKENING ROUTE CHECKS PASSED")

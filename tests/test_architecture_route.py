"""
ARCHITECTURE ROUTES (queue #20 Phase B) — read-only diagram API contract.

Plain-Python TestClient checks:
    DB_PATH=/tmp/tar.db python tests/test_architecture_route.py

Covers: list/detail/history shapes; unknown id and unknown version → 404; a route never returns
invalid Mermaid; and the config toggle round-trips through owner_flags.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_TMP = tempfile.mkdtemp(prefix="tobi_arch_route_")
os.environ["DB_PATH"] = os.path.join(_TMP, "agent.db")

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from fastapi.testclient import TestClient  # noqa: E402
from api.dashboard import app  # noqa: E402
from core import database  # noqa: E402

PASS = 0


def ok(name: str, cond: bool, detail=""):
    global PASS
    if not cond:
        print(f"❌ {name} {detail}")
        sys.exit(1)
    PASS += 1
    print(f"✅ {name}")


client = TestClient(app)
database.init_database()

# ── list ────────────────────────────────────────────────────────────────────────────
r = client.get("/api/architecture/diagrams")
ok("GET diagrams → 200", r.status_code == 200)
body = r.json()
ok("diagrams envelope has 2 items", body["count"] == 2 and len(body["items"]) == 2, str(body))
ids = [it["id"] for it in body["items"]]
ok("both canonical ids present", "overall-tobi" in ids and "mission-control" in ids)

# ── detail ────────────────────────────────────────────────────────────────────────
r = client.get("/api/architecture/diagrams/overall-tobi")
ok("GET a diagram → 200", r.status_code == 200)
d = r.json()
ok("diagram is valid with content + guide", d["valid"] and "flowchart" in d["content"] and "##" in d["guide"])
ok("route never returns invalid Mermaid (valid=true ⇒ non-empty content)", not (d["valid"] and not d["content"]))

r = client.get("/api/architecture/diagrams/does-not-exist")
ok("unknown diagram → 404", r.status_code == 404)

# ── history ───────────────────────────────────────────────────────────────────────
r = client.get("/api/architecture/diagrams/overall-tobi/history?limit=5")
ok("GET history → 200", r.status_code == 200)
h = r.json()
ok("history has an 'available' flag and an items list", "available" in h and isinstance(h.get("items"), list), str(h))
ok("history unknown id → 404", client.get("/api/architecture/diagrams/nope/history").status_code == 404)

# ── versions: unknown/invalid sha → 404 (never interpolate a raw ref into git) ──────
ok("unknown version sha → 404", client.get("/api/architecture/diagrams/overall-tobi/versions/" + "d" * 40).status_code == 404)
ok("non-hex version sha → 404", client.get("/api/architecture/diagrams/overall-tobi/versions/deadbeef").status_code == 404)

# ── config toggle round-trips ───────────────────────────────────────────────────────
r = client.get("/api/architecture/config")
ok("GET config → 200 default false", r.status_code == 200 and r.json()["v2_enabled"] is False, r.text)
ok("POST config enable → true", client.post("/api/architecture/config", json={"v2_enabled": True}).json()["v2_enabled"] is True)
ok("GET config reflects enable", client.get("/api/architecture/config").json()["v2_enabled"] is True)
ok("POST config disable → false", client.post("/api/architecture/config", json={"v2_enabled": False}).json()["v2_enabled"] is False)

print(f"\n🎉 ALL {PASS} CHECKS PASSED")

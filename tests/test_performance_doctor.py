"""
PERFORMANCE DOCTOR (#19) — system-doctor analysis.

Isolated temp DB (DB_PATH env), plain python, no pytest:
    DB_PATH=/tmp/tperf.db python tests/test_performance_doctor.py

Runs the real analyzer over this repo's graphify graph (no LLM in Quick mode, no network),
and covers: scorecard shape, feature-area subsystem mapping + grading, oversized-file and
coupling findings ranked by severity, staleness detection (graph built_at_commit vs HEAD),
snapshot persistence + trend + latest(), Deep-mode LLM synthesis (stubbed), and graceful
degradation when the graph is missing.
"""
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix="tobi_tperf_")
os.environ["DB_PATH"] = os.path.join(_TMP, "agent.db")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.database import init_database  # noqa: E402

init_database()

from core import performance_doctor as pd  # noqa: E402
from core import model_router as mr  # noqa: E402

PASS = 0


def ok(name: str, cond: bool, detail: str = ""):
    global PASS
    if not cond:
        print(f"❌ {name} {detail}")
        sys.exit(1)
    PASS += 1
    print(f"✅ {name}")


# ── Quick analysis over the real repo/graph ────────────────────────────────────────
res = pd.analyze("quick")
ok("returns overall score+grade", isinstance(res["overall"]["score"], float) and res["overall"]["grade"], str(res["overall"]))
ok("score within 0..100", 0 <= res["overall"]["score"] <= 100)
ok("subsystems graded", len(res["subsystems"]) >= 4 and all("grade" in s for s in res["subsystems"]))
ok("subsystems sorted weakest-first", res["subsystems"] == sorted(res["subsystems"], key=lambda s: s["score"]))
names = {s["name"] for s in res["subsystems"]}
ok("feature-area subsystems present", {"Conductor & Chat", "API"} <= names, str(names))
ok("indexed many files", res["counts"]["files"] >= 50, str(res["counts"]))
ok("has findings", len(res["findings"]) >= 1)
ok("findings ranked by severity", [f["severity"] for f in res["findings"]] ==
   sorted([f["severity"] for f in res["findings"]], key=lambda s: {"high": 0, "med": 1, "low": 2}[s]))
ok("finding is file/function-level", all({"title", "subsystem", "severity", "effort", "target"} <= set(f) for f in res["findings"]))

# a big file in this repo (api/dashboard.py / core/conductor.py) → an oversized 'size' finding
size_findings = [f for f in res["findings"] if f["kind"] == "size"]
ok("oversized-file finding exists", any("dashboard.py" in f["target"] or "conductor.py" in f["target"] for f in size_findings), str([f["target"] for f in size_findings][:5]))

# ── staleness: the committed graph is older than HEAD ──────────────────────────────
ok("freshness computed", "stale" in res["freshness"])
if res["freshness"].get("stale"):
    ok("stale → refresh finding present", any(f["kind"] == "freshness" for f in res["findings"]))
else:
    ok("stale flag boolean", isinstance(res["freshness"]["stale"], bool))

ok("quick diagnosis prose", "optimization" in res["diagnosis"].lower() and not res.get("deep_synthesized"))
ok("snapshot persisted", isinstance(res["id"], int) and res["id"] > 0)
ok("trend has the run", len(res["trend"]) >= 1 and res["trend"][-1]["score"] == res["overall"]["score"])

# ── latest() rehydrates the stored snapshot ────────────────────────────────────────
lt = pd.latest()
ok("latest() returns stored run", lt and lt["id"] == res["id"] and lt["overall"]["grade"] == res["overall"]["grade"])
ok("latest() carries subsystems+findings", len(lt["subsystems"]) == len(res["subsystems"]) and len(lt["findings"]) == len(res["findings"]))


# ── Deep mode: one stubbed LLM synthesis replaces the diagnosis ────────────────────
class _Fake:
    last_finish_reason = None
    def complete(self, messages, system=None, max_tokens=2000):
        return "Sir, the system is broadly healthy; Conductor & Chat is the first refactor target."


mr.get_llm = lambda *a, **k: _Fake()
deep = pd.analyze("deep")
ok("deep synthesizes a diagnosis", deep.get("deep_synthesized") and "refactor target" in deep["diagnosis"])
ok("deep still persists + trends", isinstance(deep["id"], int) and len(deep["trend"]) >= 2)


# ── graceful degradation when the graph is missing ─────────────────────────────────
_orig = pd._GRAPH
pd._GRAPH = pd._ROOT / "graphify-out" / "__no_such_graph__.json"
try:
    degraded = pd.analyze("quick")
    ok("degrades without graph", degraded["overall"]["grade"] and degraded["counts"]["files"] >= 1)
    ok("missing graph → stale", degraded["freshness"]["stale"] is True)
finally:
    pd._GRAPH = _orig

print(f"\n🎉 ALL {PASS} CHECKS PASSED")

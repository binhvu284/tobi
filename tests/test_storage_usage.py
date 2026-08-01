"""
Storage & Usage (#10) test suite — storage_scan + usage_meter + Conductor tools.

Runs against an isolated temp DB (DB_PATH env) — plain python, no pytest:
    DB_PATH=/tmp/t10.db python3 tests/test_storage_usage.py
"""
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# isolated DB before any core import
_TMP = tempfile.mkdtemp(prefix="tobi_t10_")
os.environ["DB_PATH"] = os.path.join(_TMP, "agent.db")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.database import init_database, get_connection  # noqa: E402
from core import storage_scan as ss                       # noqa: E402
from core import usage, usage_meter as um                 # noqa: E402

PASS = 0


def ok(name: str, cond: bool, detail: str = ""):
    global PASS
    if not cond:
        print(f"❌ {name} {detail}")
        sys.exit(1)
    PASS += 1
    print(f"✅ {name}")


init_database()

# ── storage_scan ──────────────────────────────────────────────────────────────
ok("table→feature map", ss.feature_for_table("brain_memories") == "Brain"
   and ss.feature_for_table("graph_edges") == "Graph"
   and ss.feature_for_table("pm_projects") == "Projects"
   and ss.feature_for_table("pm_files") == "Documents"
   and ss.feature_for_table("chat_messages") == "Chat"
   and ss.feature_for_table("agent_runs") == "Agent"
   and ss.feature_for_table("developer_schema_migrations") == "Developer"
   and ss.feature_for_table("coding_sessions") == "Developer"
   and ss.feature_for_table("development_goals") == "Developer"
   and ss.feature_for_table("news_items") == "News"
   and ss.feature_for_table("office_artifacts") == "Office"
   and ss.feature_for_table("skill_metrics") == "Abilities"
   and ss.feature_for_table("vault_secrets") == "Vault"
   and ss.feature_for_table("mcp_tools") == "MCP"
   and ss.feature_for_table("tasks") == "Tasks"
   and ss.feature_for_table("llm_usage") == "System"
   and ss.feature_for_table("mc_run_events") == "System"
   and ss.feature_for_table("weird_table") == "Other")

data_root = Path(os.environ["DB_PATH"]).parent
(data_root / "developer" / "artifacts").mkdir(parents=True)
(data_root / "news_media").mkdir()
(data_root / "review-build").mkdir()
target_features = {Path(t["path"]).name: t["feature"] for t in ss._fs_targets()}
ok("data dir→module map", target_features.get("developer") == "Developer"
   and target_features.get("review-build") == "Developer"
   and target_features.get("news_media") == "News"
   and all(t["label"] != "Agent data dir" for t in ss._fs_targets()))

db = ss.scan_db()
ok("scan_db per-table", db["db_size_bytes"] > 0 and len(db["tables"]) > 20
   and all("feature" in t and "rows" in t for t in db["tables"]))

res = ss.run_scan("all")
ok("run_scan writes snapshots", res["db"]["tables"] > 20 and "fs" in res)
conn = get_connection()
n_snap = conn.execute("SELECT COUNT(*) FROM storage_snapshots").fetchone()[0]
conn.close()
ok("snapshot rows persisted", n_snap > 5, f"got {n_snap}")

ov = ss.overview()
ok("overview KPIs", ov["total_bytes"] > 0 and ov["db"]["size_bytes"] > 0
   and ov["biggest"] is not None and isinstance(ov["trend"], list) and ov["trend"])
ok("System bucket separated", ov["system_bytes"] >= 0
   and all(f["feature"] != "System" for f in [ov["biggest"]] if f))

deps1 = ss.scan_deps()
deps2 = ss.scan_deps()
ok("deps cache (2nd hit cached)", deps2.get("cached") is True or not deps1["items"])

det = ss.category_detail("brain")
ok("drill-down case-insensitive", det["feature"] == "Brain"
   and any(t["table"].startswith("brain_") for t in det["tables"]))
ok("vault privacy note", "size and item count only" in (ss.category_detail("Vault").get("note") or ""))

code = ss.category_detail("Codebase", top_n=50)
names = {i["name"].split("/")[-1] for i in code["fs_items"]}
ok("drill-down honors skip set", not names & {"venv", "node_modules", ".git", ".tobi", "dist"},
   f"leaked: {names & {'venv', 'node_modules', '.git', '.tobi', 'dist'}}")

# ── usage_meter: prices ───────────────────────────────────────────────────────
rows = um._load_yaml_prices()
ok("price yaml parses", len(rows) >= 15 and any(m == "claude-opus" for m, _, _ in rows))
sync = um.sync_prices()
ok("prices mirrored to DB", sync["active"] >= 15)
ok("estimator uses table", usage.estimate_cost("claude-opus-4-8", 1_000_000, 0) == 15.0
   and usage.estimate_cost("nvidia/nemotron-3:free", 1e6, 1e6) == 0.0)

# SQLite legacy rows use a space between date and time. Freeze the clock to the
# first day so this cannot regress into a lexicographic ISO-string comparison.
boundary_conn = get_connection()
boundary_conn.execute(
    "INSERT INTO llm_usage (agent_id, provider, model, prompt_tokens, completion_tokens, "
    "total_tokens, cost, created_at) VALUES ('boundary','boundary-provider','legacy',3,4,7,0,?)",
    ("2026-08-01 00:30:00",),
)
boundary_conn.commit()
real_datetime = um.datetime


class FirstDayDatetime(real_datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 8, 1, 12, 0, tzinfo=timezone.utc)


try:
    um.datetime = FirstDayDatetime
    boundary_usage = um._month_usage(boundary_conn, "boundary-provider")
finally:
    um.datetime = real_datetime
    boundary_conn.execute("DELETE FROM llm_usage WHERE provider='boundary-provider'")
    boundary_conn.commit()
    boundary_conn.close()
ok("first-day legacy timestamp counted", boundary_usage["tokens"] == 7)

# ── usage_meter: overview / calls ─────────────────────────────────────────────
usage.log("anthropic", "claude-opus-4-8", 1000, 500, 800, surface="chat",
          feature="chat.reply", requested_model="anthropic:claude-opus-4-8",
          actual_model="anthropic:claude-opus-4-8", turn_id="turn-1",
          purpose="owner_turn", source="chat_runtime")
usage.log("anthropic", "claude-haiku-4-5", 400, 100, 200, surface="agent", feature="classifier")
usage.log("openrouter", "nvidia/nemotron-3:free", 900, 300, 1500, surface="research",
          requested_model="codex:gpt-5.6-sol",
          actual_model="openrouter:nvidia/nemotron-3:free", attempt=2,
          fallback_reason="codex:RateLimitError")
usage.log_failure("codex", "gpt-5.6-sol", 50, error_code="RateLimitError",
                  requested_model="codex:gpt-5.6-sol",
                  actual_model="codex:gpt-5.6-sol", attempt=1)
# legacy office-style row (no ts/surface → folds in via created_at with surface='office')
conn = get_connection()
conn.execute("INSERT INTO llm_usage (agent_id, provider, model, prompt_tokens, completion_tokens, "
             "total_tokens, cost) VALUES ('friday','openrouter','x-model',10,10,20,0)")
conn.commit(); conn.close()

uo = um.overview("month")
ok("overview totals", uo["requests"] == 4 and uo["total_tokens"] == 3220)
ok("attempt and fallback truth", uo["attempts"] == 5 and uo["failed_attempts"] == 1
   and uo["fallback_calls"] == 1 and uo["calls_per_turn"] == 1)
ok("all four dims", len(uo["by_provider"]) == 2 and len(uo["by_model"]) == 4
   and {b["surface"] for b in uo["by_surface"]} == {"chat", "agent", "research", "office"}
   and uo["by_agent"] and uo["by_agent"][0]["agent"] == "friday")
ok("cost from price table", abs(uo["total_cost"] - round(0.0525 + 0.00072, 4)) < 1e-9,
   f"got {uo['total_cost']}")
ok("day series stacked by surface", len(uo["by_day"]) == 30
   and any("chat" in d for d in uo["by_day"]))
ok("range validation", um.overview("day")["requests"] == 4 and um.overview("all")["requests"] == 4)

calls = um.calls(q="opus")
ok("call log search", calls["total"] == 1 and calls["calls"][0]["model"] == "claude-opus-4-8")
ok("call log surface filter", um.calls(surface="office")["total"] == 1)
ok("failed attempt filter", um.calls(status="failed")["total"] == 1
   and um.calls(status="failed")["calls"][0]["error_code"] == "RateLimitError")
ok("call log pagination", um.calls(limit=2)["total"] == 5 and len(um.calls(limit=2)["calls"]) == 2)

# ── plans & budget ────────────────────────────────────────────────────────────
plans = um.set_plans([{"provider": "anthropic", "plan_name": "Claude Max",
                       "limit_type": "usd", "limit_value": 100},
                      {"provider": "openrouter", "plan_name": "Credits",
                       "limit_type": "tokens", "limit_value": 1_000_000}])
ok("plans usage-vs-limit", len(plans) == 2
   and plans[0]["used"] > 0 and 0 < plans[0]["pct"] < 100
   and plans[1]["used"] == 1220)  # openrouter tokens incl. legacy row

ok("budget off by default", um.get_budget()["level"] == "off")
b = um.set_budget(100, 80)
ok("budget ok level", b["level"] == "ok" and b["monthly_cap_usd"] == 100)
ok("budget warn level", um.set_budget(0.06, 80)["level"] == "warn")
ok("budget over level", um.set_budget(0.01, 80)["level"] == "over")

sc = um.spend_compact("month")
ok("spend_compact", sc["total_cost_usd"] > 0 and sc["top_models"]
   and sc["budget"]["level"] == "over")

# ── Conductor tools (#7 wiring) ───────────────────────────────────────────────
from core import conductor  # noqa: E402
ok("tools registered", "storage_status" in conductor.READ_TOOLS
   and "llm_spend" in conductor.READ_TOOLS)
st = conductor.tool_storage_status()
ok("storage_status tool", st.get("total_bytes", 0) > 0 and st.get("biggest"))
st2 = conductor.tool_storage_status(feature="Brain")
ok("storage_status drill", st2.get("feature") == "Brain")
sp = conductor.tool_llm_spend(range="month")
ok("llm_spend tool", sp.get("total_cost_usd", 0) > 0 and sp.get("budget"))
sp2 = conductor.tool_llm_spend(range="nonsense")
ok("llm_spend bad range falls back", sp2.get("range") == "month")

print(f"\n🎉 {PASS}/{PASS} Storage & Usage tests pass")

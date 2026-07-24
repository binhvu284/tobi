"""News V2 N05 (#23): versioned rank snapshots — models, GitHub growth, feed.

Isolated temp DB, injected clocks, no network. Proves the N05 acceptance gate —
deterministic, attributed, stable pagination — plus Top-10 eligibility (fresh
evidence, >=2 score families), within-source normalization, honest snapshot-only
GitHub growth ("collecting" until history exists, never stars-as-growth), the
55/25/10/10 feed formula with immediate dislike hiding, diversity invariants
(<=3 consecutive per source, <=40% per topic), bounded context with direct-action
precedence, snapshot pruning, and the refresh-engine rebuild hook.
"""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TMP = Path(tempfile.mkdtemp(prefix="tobi_news_rank_"))
os.environ["DB_PATH"] = str(TMP / "agent.db")

from core.database import init_database, get_connection  # noqa: E402

init_database()

from core.news import contracts as CT  # noqa: E402
from core.news import interactions as IX  # noqa: E402
from core.news import normalizer as N  # noqa: E402
from core.news import ranking as RK  # noqa: E402
from core.news import refresh, repository  # noqa: E402
from core.news.sources import base  # noqa: E402

PASS = 0


def ok(name: str, cond: bool, detail: str = "") -> None:
    global PASS
    if not cond:
        print(f"FAIL {name} {detail}")
        sys.exit(1)
    PASS += 1
    print(f"PASS {name}")


NOW = datetime.now(timezone.utc)
conn = get_connection()


def metric(model: str, source: str, name: str, value: float, days_old: int = 0) -> CT.ModelMetric:
    return CT.ModelMetric(model_id=model, category="general", source=source, metric=name,
                          value=value, confidence=0.9,
                          observed_at=(NOW - timedelta(days=days_old)).isoformat(),
                          formula_version="raw")


# ── 1. Model Strength: eligibility, normalization, attribution, determinism ──────────
N.ingest_model_evidence(conn, [
    metric("alpha/one", "bench", "intelligence", 80.0),
    metric("alpha/one", "arena", "elo", 1300.0),
    metric("beta/two", "bench", "intelligence", 60.0),
    metric("beta/two", "arena", "elo", 1400.0),
    metric("beta/two", "openrouter", "price_in", 0.001),
    metric("beta/two", "openrouter", "price_out", 0.002),
    metric("beta/two", "openrouter", "context", 200000.0),
    metric("gamma/three", "openrouter", "context", 100000.0),      # 1 family → ineligible
    metric("stale/old", "bench2", "intelligence", 95.0, days_old=40),  # stale → ineligible
], [])
conn.commit()
snap = RK.build_model_snapshot(conn, now=NOW)
entries = repository.read_snapshot_page(conn, kind="models:top", limit=40)["entries"]
ok("model snapshot written and readable", snap is not None and len(entries) == 2)
ok("one-family and stale models are excluded from Top-10",
   {e["model_id"] for e in entries} == {"alpha/one", "beta/two"})
ok("within-source normalization ranks the strong-intelligence model first",
   entries[0]["model_id"] == "alpha/one" and entries[0]["score"] > entries[1]["score"],
   str([(e["model_id"], e["score"]) for e in entries]))
ok("every entry is attributed (components + sources + formula version)",
   all(e["components"] and e["sources"] and e["formula_version"] == "model-v1" for e in entries))
ok("lower-is-better metrics are inverted (cost component in [0,1])",
   0.0 <= entries[1]["components"].get("cost", 0.0) <= 1.0
   and "cost" in entries[1]["components"])
snap2 = RK.build_model_snapshot(conn, now=NOW)
entries2 = repository.read_snapshot_page(conn, kind="models:top", limit=40)["entries"]
ok("model ranking is deterministic (identical rebuild)", entries == entries2 and snap2 != snap)

# ── 2. GitHub growth: history only, never stars-as-growth ────────────────────────────
today = NOW.date().isoformat()
d8 = (NOW - timedelta(days=8)).date().isoformat()
d35 = (NOW - timedelta(days=35)).date().isoformat()
N.ingest_github_snapshots(conn, [
    CT.GitHubSnapshot(repo="r/hot", snapshot_date=d35, stars=500),
    CT.GitHubSnapshot(repo="r/hot", snapshot_date=d8, stars=900),
    CT.GitHubSnapshot(repo="r/hot", snapshot_date=today, stars=1000),
    CT.GitHubSnapshot(repo="r/new", snapshot_date=today, stars=5000),
])
conn.commit()
week = RK.github_trending_entries(conn, "week", now=NOW)
ok("week growth = newest vs nearest snapshot AT/BEFORE the boundary",
   week[0] == {"repo": "r/hot", "stars": 1000, "growth": 100, "baseline_date": d8, "status": "ok"},
   str(week[0]))
ok("no baseline in window → collecting, and NO growth field",
   week[1]["repo"] == "r/new" and week[1]["status"] == "collecting" and "growth" not in week[1])
month = RK.github_trending_entries(conn, "month", now=NOW)
ok("month uses the older baseline honestly", month[0]["growth"] == 500
   and month[0]["baseline_date"] == d35)
alltime = RK.github_trending_entries(conn, "all", now=NOW)
ok("all-time ranks by total stars", [e["repo"] for e in alltime] == ["r/new", "r/hot"])
d3 = (NOW - timedelta(days=3)).date().isoformat()
N.ingest_github_snapshots(conn, [
    CT.GitHubSnapshot(repo="r/young", snapshot_date=d3, stars=100),
    CT.GitHubSnapshot(repo="r/young", snapshot_date=today, stars=180),
])
conn.commit()
young = [e for e in RK.github_trending_entries(conn, "week", now=NOW) if e["repo"] == "r/young"][0]
ok("window not spanned but 2 days exist → measured growth since the earliest date",
   young == {"repo": "r/young", "stars": 180, "growth": 80, "baseline_date": d3, "status": "ok"},
   str(young))
still_new = [e for e in RK.github_trending_entries(conn, "week", now=NOW) if e["repo"] == "r/new"][0]
ok("a single snapshot day still reports collecting — never stars-as-growth",
   still_new["status"] == "collecting" and "growth" not in still_new)
try:
    RK.github_trending_entries(conn, "fortnight")
    ok("unknown window refused", False)
except ValueError:
    ok("unknown window refused", True)

# ── GitHub REAL trending: github.com/trending numbers PREEMPT the snapshot fallback ──
N.ingest_github_trending(conn, [
    CT.GitHubTrending(repo="hot/repo", window="week", rank=1, period_stars=1234,
                      total_stars=4200, observed_at=NOW.isoformat(), description="d1", language="Python"),
    CT.GitHubTrending(repo="cool/repo", window="week", rank=2, period_stars=800,
                      total_stars=9000, observed_at=NOW.isoformat(), description="d2", language="Rust"),
    CT.GitHubTrending(repo="hot/repo", window="month", rank=1, period_stars=5000,
                      total_stars=4200, observed_at=NOW.isoformat()),
])
conn.commit()
rweek = RK.github_trending_entries(conn, "week", now=NOW)
ok("real trending preempts snapshots: growth is GitHub's own period number, page order kept",
   [(e["repo"], e["growth"]) for e in rweek] == [("hot/repo", 1234), ("cool/repo", 800)],
   str(rweek))
ok("real trending never emits 'collecting' (data is real from the first refresh)",
   all(e["status"] == "ok" for e in rweek))
# all-time is its OWN real board (GitHub Search top-starred), not a reorder of trending
N.ingest_github_trending(conn, [
    CT.GitHubTrending(repo="torvalds/linux", window="all", rank=1, period_stars=0,
                      total_stars=900000, observed_at=NOW.isoformat(), description="kernel", language="C"),
    CT.GitHubTrending(repo="sindre/awesome", window="all", rank=2, period_stars=0,
                      total_stars=488000, observed_at=NOW.isoformat())])
conn.commit()
rall = RK.github_trending_entries(conn, "all", now=NOW)
ok("all-time is the real Search-API board (verifiable), GitHub's rank order, no growth",
   [e["repo"] for e in rall] == ["torvalds/linux", "sindre/awesome"] and "growth" not in rall[0],
   str(rall))
N.ingest_github_trending(conn, [
    CT.GitHubTrending(repo="hot/repo", window="week", rank=1, period_stars=1234,
                      total_stars=4200, observed_at=NOW.isoformat())])
gone = [e["repo"] for e in RK.github_trending_entries(conn, "week", now=NOW)]
ok("a repo that fell off GitHub's board is cleared on the next refresh",
   gone == ["hot/repo"], str(gone))

# ── capability gate: price/context alone never ranks a model ─────────────────────────
N.ingest_model_evidence(conn, [
    CT.ModelMetric(model_id="cheapo-big", category="general", source="catalog",
                   metric="price_in", value=0.1, confidence=0.9,
                   observed_at=NOW.isoformat(), formula_version="raw"),
    CT.ModelMetric(model_id="cheapo-big", category="general", source="catalog",
                   metric="context", value=2_000_000, confidence=0.9,
                   observed_at=NOW.isoformat(), formula_version="raw"),
], [])
conn.commit()
RK.build_model_snapshot(conn, now=NOW)
top_ids = {e["model_id"] for e in repository.read_snapshot_page(conn, kind="models:top", limit=40)["entries"]}
ok("2 families of cost+context alone are NOT Top-10 eligible (capability gate)",
   "cheapo-big" not in top_ids and top_ids)
trend_snaps = RK.build_trending_snapshots(conn, now=NOW)
ok("trending snapshots persist per window + tools",
   set(trend_snaps) == {"github:week", "github:month", "github:all", "tools"})

# ── 3. Feed: formula, hiding, diversity, context, latest ─────────────────────────────
T2H = (NOW - timedelta(hours=2)).isoformat()


def art(source: str, ext: str, title: str, trust: CT.TrustClass, engagement: int = 0,
        published: str = T2H) -> CT.SourceRecord:
    return CT.SourceRecord(source=source, external_id=ext, url=f"https://{source}.io/{ext}",
                           title=title, item_type=CT.ItemType.ARTICLE, trust=trust,
                           observed_at=NOW.isoformat(), engagement=engagement,
                           published_at=published)


N.ingest(conn, [
    art("openai_blog", "a1", "Alpha breakthrough result", CT.TrustClass.OFFICIAL, 500),
    art("reddit", "a2", "Bravo community story", CT.TrustClass.COMMUNITY, 500),
    art("hn", "d1", "Delta disliked story", CT.TrustClass.VERIFIED_API, 300),
    art("wire", "s1", "Solar panels milestone", CT.TrustClass.AGGREGATOR),
    art("wire", "s2", "Harbor logistics update", CT.TrustClass.AGGREGATOR),
    art("wire", "s3", "Voyager probe telemetry", CT.TrustClass.AGGREGATOR),
    art("wire", "s4", "Glacier survey findings", CT.TrustClass.AGGREGATOR),
    art("wire", "s5", "Orchard robotics pilot", CT.TrustClass.AGGREGATOR),
    art("tw1", "t1", "Quantum entanglement claim", CT.TrustClass.AGGREGATOR),
    art("tw2", "t2", "Quantum sensor array", CT.TrustClass.AGGREGATOR),
    art("tw3", "t3", "Quantum error correction", CT.TrustClass.AGGREGATOR),
    art("tw4", "t4", "Quantum networking test", CT.TrustClass.AGGREGATOR),
    art("wire2", "old1", "Ancient update chronicle", CT.TrustClass.AGGREGATOR, 0,
        (NOW - timedelta(hours=72)).isoformat()),
    art("flashwire", "fresh1", "Breaking fresh flash", CT.TrustClass.AGGREGATOR, 0,
        (NOW - timedelta(minutes=10)).isoformat()),
])
conn.commit()
iid = {ext: conn.execute("SELECT id FROM news_items WHERE url_hash=?",
                         (CT.url_hash(f"https://{src}.io/{ext}"),)).fetchone()[0]
       for src, ext in [("openai_blog", "a1"), ("reddit", "a2"), ("hn", "d1"),
                        ("wire", "s1"), ("wire", "s2"), ("tw1", "t1"),
                        ("wire2", "old1"), ("flashwire", "fresh1")]}

IX.dislike(conn, iid["d1"], "dx", now=NOW)               # hidden immediately (undo still open)
IX.like(conn, iid["s1"], "lx", now=NOW)
repository.set_settings(conn, CT.NewsSettings(context_classes={"owner_interests": True}))
conn.commit()

BUILD_AT = NOW + timedelta(seconds=5)
out = RK.rebuild_for_tab(conn, "feed", now=BUILD_AT)
conn.commit()
ok("feed rebuild produces for_you + latest snapshots", set(out) == {"for_you", "latest"})
for_you = repository.read_snapshot_page(conn, kind="feed:for_you", limit=40)["entries"]
ids_shown = [e["item_id"] for e in for_you]
ok("a disliked item is hidden IMMEDIATELY (undo window still open)", iid["d1"] not in ids_shown)
ok("official trust dominates the top slot", for_you[0]["item_id"] == iid["a1"])
ok("a liked source outranks equal-trust strangers",
   ids_shown.index(iid["s2"]) < ids_shown.index(iid["t1"]))

runs_ok = all(
    not all(e["source"] == for_you[i + k]["source"] for k in range(1, RK.MAX_CONSECUTIVE_SOURCE + 1))
    for i, e in enumerate(for_you[:-RK.MAX_CONSECUTIVE_SOURCE]))
ok("never more than 3 consecutive items from one source", runs_ok,
   str([e["source"] for e in for_you]))
prefix_ok = True
counts: dict = {}
for k, e in enumerate(for_you, start=1):
    counts[e["topic"]] = counts.get(e["topic"], 0) + 1
    if counts[e["topic"]] > max(1, int(RK.MAX_TOPIC_SHARE * k)):
        prefix_ok = False
        break
ok("every prefix honors the 40% topic cap", prefix_ok, str([e["topic"] for e in for_you]))
ok("entries carry components, context points, and <=2 reasons",
   all("components" in e and "context_points" in e and len(e["reasons"]) <= 2 for e in for_you))

ctx_scores = {iid["t1"]: {"owner_interests": 40.0}, iid["s1"]: {"owner_interests": 40.0}}
RK.build_feed_snapshots(conn, now=BUILD_AT, context_scores=ctx_scores)
conn.commit()
boosted = repository.read_snapshot_page(conn, kind="feed:for_you", limit=40)["entries"]
by_id = {e["item_id"]: e for e in boosted}
ok("context boosts an untouched item by at most +5", by_id[iid["t1"]]["context_points"] == 5.0)
ok("direct News action takes precedence — context contributes zero",
   by_id[iid["s1"]]["context_points"] == 0.0)

latest = repository.read_snapshot_page(conn, kind="feed:latest", limit=40)["entries"]
ok("latest is pure recency", latest[0]["item_id"] == iid["fresh1"]
   and latest[-1]["item_id"] == iid["old1"])

again = RK.build_feed_snapshots(conn, now=BUILD_AT, context_scores=ctx_scores)
conn.commit()
rebuilt = repository.read_snapshot_page(conn, kind="feed:for_you", limit=40)["entries"]
ok("feed ranking is deterministic (identical rebuild, new snapshot id)",
   rebuilt == boosted and again["for_you"] != out["for_you"])
page = repository.read_snapshot_page(conn, kind="feed:for_you", limit=15)
ok("snapshot pagination stays stable and bounded", page["snapshot_id"] == again["for_you"]
   and len(page["entries"]) == 13 and page["next_cursor"] is None)

# ── 4. retention keeps a bounded per-kind snapshot history ───────────────────────────
for _ in range(25):
    repository.write_rank_snapshot(conn, "prune:kind", [{"x": 1}], "v1")
conn.commit()
result = repository.run_retention(conn, now=NOW)
conn.commit()
kept = conn.execute("SELECT COUNT(*) FROM news_rank_snapshots WHERE kind='prune:kind'").fetchone()[0]
ok("retention prunes snapshots beyond the per-kind cap", kept == repository.SNAPSHOT_KEEP
   and result["snapshots"] >= 5, f"kept={kept} {result}")

conn.close()


# ── 5. the refresh engine rebuilds ranks after a successful job ──────────────────────
class Quiet(base.Adapter):
    name = "quiet"

    def _collect(self) -> base.Payload:
        return base.Payload()


refresh._TAB_SOURCES = {"home": (Quiet,), "trending": (Quiet,), "feed": (Quiet,)}
conn = get_connection()
before = conn.execute("SELECT COUNT(*) FROM news_rank_snapshots WHERE kind='models:top'").fetchone()[0]
conn.close()
job = refresh.request_refresh("home")
refresh.run_job(job["job_id"])
conn = get_connection()
after = conn.execute("SELECT COUNT(*) FROM news_rank_snapshots WHERE kind='models:top'").fetchone()[0]
conn.close()
ok("a completed refresh precomputes its tab's rank snapshot", after == before + 1,
   f"{before}->{after}")

print(f"\nALL {PASS} CHECKS PASSED")

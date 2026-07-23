"""News V2 feed-quality redesign (#23): deep-dive recaps — selection, generation, curation.

Isolated temp DB, stubbed LLM seam (no routing, no network). Proves the owner's
product rule — a few (TOP_STORIES) deep-dive stories per refresh: deterministic
top-story selection, grounded + bounded recap writes with per-item isolation and
budget gating, the untrusted-material prompt fence, curated ``feed:for_you``
(recapped-only, newest batch first, honest fallback when no recaps exist), and
the refresh-hook integration end to end.
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

TMP = Path(tempfile.mkdtemp(prefix="tobi_news_recap_"))
os.environ["DB_PATH"] = str(TMP / "agent.db")

from core.database import init_database, get_connection  # noqa: E402

init_database()

from core.news import contracts as CT  # noqa: E402
from core.news import ranking as RK  # noqa: E402
from core.news import recap, refresh, repository  # noqa: E402
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

# ── 1. migration: recap columns exist and re-running schema is idempotent ────────────
repository.ensure_schema(conn)
repository.ensure_schema(conn)
cols = {row[1] for row in conn.execute("PRAGMA table_info(news_items)")}
ok("migration 2 adds recap columns idempotently", {"recap", "recap_at"} <= cols)


def seed(item_id_hint: str, source: str, trust: str, engagement: int,
         hours_ago: float = 1.0, excerpt: str = "solid material " * 20) -> int:
    stamp = (NOW - timedelta(hours=hours_ago)).isoformat()
    cur = conn.execute(
        "INSERT INTO news_items (url_hash, canonical_url, item_type, title, excerpt,"
        " published_at, first_seen_at, expires_at) VALUES (?,?,?,?,?,?,?,?)",
        (f"h-{item_id_hint}", f"https://ex.io/{item_id_hint}", "article",
         f"Story {item_id_hint} about agents", excerpt, stamp, stamp,
         (NOW + timedelta(days=60)).isoformat()))
    conn.execute(
        "INSERT INTO news_item_sources (item_id, source, external_id, trust, engagement, observed_at)"
        " VALUES (?,?,?,?,?,?)", (cur.lastrowid, source, f"x-{item_id_hint}", trust, engagement, stamp))
    return int(cur.lastrowid)


# ── 2. selection: deterministic top stories ──────────────────────────────────────────
ids = {
    "hot_official": seed("a", "openai", "official", 900),
    "hot_agg": seed("b", "hackernews", "aggregator", 800),
    "warm": seed("c", "theverge", "aggregator", 300),
    "mild": seed("d", "arstechnica", "aggregator", 120),
    "cool": seed("e", "venturebeat", "aggregator", 50),
    "cold_thin": seed("f", "reddit", "community", 5, excerpt="thin"),
    "old_story": seed("g", "hackernews", "aggregator", 999, hours_ago=80),
}
conn.commit()
picked = recap.pick_top_stories(conn)
ok("top-story selection is bounded to TOP_STORIES", len(picked) == recap.TOP_STORIES)
ok("selection favors trust + engagement and drops the thin/cold tail",
   ids["hot_official"] in picked and ids["hot_agg"] in picked and ids["cold_thin"] not in picked)
ok("stories outside the 48h window are never picked", ids["old_story"] not in picked)
ok("selection is deterministic", picked == recap.pick_top_stories(conn))

# ── 3. generation: grounded, bounded, isolated, budget-gated ─────────────────────────
prompts: list[str] = []


def fake_llm(user: str):
    prompts.append(user)
    if "Story c" in user:
        return None                                    # one model failure → skip that item only
    return "Para one about what happened.\n\nPara two with the concrete details. " + "x" * 2000


_real_llm = recap._llm_complete
recap._llm_complete = fake_llm
result = recap.generate_recaps(conn, picked)
ok("recaps written with per-item isolation on LLM failure",
   result == {"written": recap.TOP_STORIES - 1, "skipped": 1}, str(result))
stored = conn.execute("SELECT recap, recap_at FROM news_items WHERE id=?", (ids["hot_official"],)).fetchone()
ok("stored recap is bounded and timestamped",
   stored[0] and len(stored[0]) <= recap.RECAP_MAX_CHARS and stored[1])
ok("prompt fences material as untrusted (injection rule)",
   all("UNTRUSTED" in p for p in prompts))
ok("already-recapped items never re-pick", ids["hot_official"] not in recap.pick_top_stories(conn))
replay = recap.generate_recaps(conn, [ids["hot_official"]])
ok("replaying a recapped item is a no-op skip", replay == {"written": 0, "skipped": 1})

_real_budget = recap._budget_ok
recap._budget_ok = lambda: False
blocked = recap.generate_recaps(conn, [ids["cold_thin"]])
ok("over-budget skips everything honestly", blocked == {"written": 0, "skipped": 1})
recap._budget_ok = _real_budget

# ── 4. curation: for_you is the recapped stream; latest stays the firehose ───────────
RK.build_feed_snapshots(conn)
conn.commit()
for_you = repository.read_snapshot_page(conn, kind="feed:for_you", limit=40)["entries"]
latest = repository.read_snapshot_page(conn, kind="feed:latest", limit=40)["entries"]
recapped_ids = {r[0] for r in conn.execute("SELECT id FROM news_items WHERE recap IS NOT NULL")}
ok("for_you serves ONLY recapped deep-dive stories",
   for_you and {e["item_id"] for e in for_you} == recapped_ids)
ok("latest keeps the full firehose", len(latest) == len(ids))

conn.execute("UPDATE news_items SET recap=NULL, recap_at=NULL")
conn.commit()
RK.build_feed_snapshots(conn)
conn.commit()
fallback = repository.read_snapshot_page(conn, kind="feed:for_you", limit=40)["entries"]
ok("no recaps yet → for_you falls back to the ranked list (never artificially empty)",
   len(fallback) == len(ids))

# ── 5. refresh-hook integration ──────────────────────────────────────────────────────
class FreshSource(base.Adapter):
    name = "freshsrc"
    max_attempts = 1
    retry_wait_s = 0.0

    def _collect(self) -> base.Payload:
        return base.Payload(records=[CT.SourceRecord(
            source="freshsrc", external_id=f"fs-{n}", url=f"https://fresh.io/{n}",
            title=f"Fresh launch {n} of an agent runtime", item_type=CT.ItemType.ARTICLE,
            trust=CT.TrustClass.AGGREGATOR, observed_at=NOW.isoformat(),
            published_at=NOW.isoformat(), excerpt="rich reporting body " * 15,
            engagement=600 + n) for n in range(3)])


_orig_sources = dict(refresh._TAB_SOURCES)
refresh._TAB_SOURCES[CT.Tab.FEED.value] = (FreshSource,)
job = refresh.request_refresh("feed")
final = refresh.run_job(job["job_id"])
recap_count = conn.execute("SELECT COUNT(*) FROM news_items WHERE recap IS NOT NULL").fetchone()[0]
curated = repository.read_snapshot_page(conn, kind="feed:for_you", limit=40)["entries"]
ok("feed refresh recaps top stories before rebuilding the snapshot",
   final["state"] == "completed" and recap_count == recap.TOP_STORIES
   and len(curated) == recap.TOP_STORIES, f"state={final['state']} recaps={recap_count}")
refresh._TAB_SOURCES.clear()
refresh._TAB_SOURCES.update(_orig_sources)
recap._llm_complete = _real_llm

conn.close()
print(f"\nALL {PASS} CHECKS PASSED")

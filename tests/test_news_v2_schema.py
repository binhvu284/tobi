"""News V2 N01 (#23): contracts + additive schema + repository.

Isolated temp DB, plain python. Proves the N01 acceptance gate — migrations are
idempotent and Explore V1 rows are NEVER rewritten — plus contract validation,
canonical dedupe, idempotent event/interaction primitives, snapshot-pinned cursor
pagination, retention protections, settings round-trip, and the fail-closed flag.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TMP = Path(tempfile.mkdtemp(prefix="tobi_news_v2_"))
os.environ["DB_PATH"] = str(TMP / "agent.db")

from core.database import init_database, get_connection  # noqa: E402

init_database()

from core import owner_flags  # noqa: E402
from core.news import contracts as CT  # noqa: E402
from core.news import repository as R  # noqa: E402

PASS = 0


def ok(name: str, cond: bool, detail: str = "") -> None:
    global PASS
    if not cond:
        print(f"FAIL {name} {detail}")
        sys.exit(1)
    PASS += 1
    print(f"PASS {name}")


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


NOW = now_utc().isoformat()

# ── 1. schema: idempotent ledger migrations, all 12 tables ───────────────────────────
init_database()                                     # second boot — must be a no-op
R.ensure_schema()                                   # direct re-run — must be a no-op
conn = get_connection()
tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'news_%'")}
expected = {"news_items", "news_item_sources", "news_interactions", "news_interaction_events",
            "news_interest_profiles", "news_rank_snapshots", "news_refresh_jobs",
            "news_github_snapshots", "news_model_metrics", "news_model_releases",
            "news_media_cache", "news_settings", "news_schema_migrations"}
ok("all 12 N01 tables + ledger exist", expected <= tables, str(sorted(expected - tables)))
ledger = conn.execute("SELECT version, COUNT(*) FROM news_schema_migrations GROUP BY version").fetchall()
ok("ledger recorded every migration exactly once",
   [tuple(r) for r in ledger] == [(v, 1) for v, _ in __import__("core.news.repository", fromlist=["_MIGRATIONS"])._MIGRATIONS],
   str(ledger))
conn.close()

# ── 2. V1 copy: idempotent, V1 rows byte-identical, compat ids retained ──────────────
conn = get_connection()
conn.execute("INSERT INTO explore_items (pillar, source_name, ext_id, title, url, summary, raw_json,"
             " engagement, published_at, first_seen_at) VALUES"
             " ('models','hn','a1','GPT-6 announced','https://Example.com/gpt6/?utm_source=x','sum',"
             " '{\"k\":1}', 40, ?, ?)", (NOW, NOW))
conn.execute("INSERT INTO explore_items (pillar, source_name, ext_id, title, url, summary,"
             " engagement, first_seen_at) VALUES"
             " ('social','reddit','b2','Same story','https://example.com/gpt6?fbclid=zz', 'dupe', 7, ?)", (NOW,))
conn.execute("INSERT INTO explore_items (pillar, source_name, ext_id, title, url, first_seen_at)"
             " VALUES ('tools','gh','c3','', 'https://example.com/untitled', ?)", (NOW,))   # no title → skipped
conn.execute("INSERT INTO explore_models (model_id, provider, intelligence, elo, composite, updated_at)"
             " VALUES ('gpt-6','openai', 71.5, 1401.0, 88.2, ?)", (NOW,))
conn.commit()
v1_before = [tuple(r) for r in conn.execute("SELECT * FROM explore_items ORDER BY id")]
m1_before = [tuple(r) for r in conn.execute("SELECT * FROM explore_models ORDER BY model_id")]

first = R.copy_v1(conn)
second = R.copy_v1(conn)
conn.commit()
ok("copy_v1 copies titled items once (dedupe by canonical URL)", first["items"] == 1, str(first))
ok("copy_v1 keeps BOTH source evidence rows for the deduped story", first["evidence"] == 2, str(first))
ok("copy_v1 copies each non-null model metric", first["metrics"] == 3, str(first))
ok("copy_v1 re-run is a pure no-op", second == {"items": 0, "evidence": 0, "metrics": 0}, str(second))

v1_after = [tuple(r) for r in conn.execute("SELECT * FROM explore_items ORDER BY id")]
m1_after = [tuple(r) for r in conn.execute("SELECT * FROM explore_models ORDER BY model_id")]
ok("explore_items rows are byte-identical after copy", v1_before == v1_after)
ok("explore_models rows are byte-identical after copy", m1_before == m1_after)

item = conn.execute("SELECT id, item_type, compat_v1_id, expires_at FROM news_items").fetchone()
ok("canonical item retains its V1 id as compat reference", item is not None and item[2] == 1, str(tuple(item or ())))
ok("copied item starts with a 90-day expiry (not protected)", item[3] is not None)
metrics = conn.execute("SELECT COUNT(*) FROM news_model_metrics WHERE source='explore_v1' AND formula_version='v1'").fetchone()[0]
ok("V1 metrics are attributed to source explore_v1", metrics == 3, str(metrics))
ITEM_ID = int(item[0])
conn.close()

# ── 3. contracts: validation rejects malformed data at the boundary ──────────────────
def raises(fn) -> bool:
    try:
        fn()
        return False
    except ValueError:
        return True

ok("SourceRecord requires a title", raises(lambda: CT.SourceRecord(
    source="hn", external_id="x", url="https://a.io", title="  ", item_type=CT.ItemType.ARTICLE,
    trust=CT.TrustClass.VERIFIED_API, observed_at=NOW)))
ok("SourceRecord rejects negative engagement", raises(lambda: CT.SourceRecord(
    source="hn", external_id="x", url="https://a.io", title="t", item_type=CT.ItemType.ARTICLE,
    trust=CT.TrustClass.VERIFIED_API, observed_at=NOW, engagement=-1)))
ok("SourceRecord bounds the excerpt", raises(lambda: CT.SourceRecord(
    source="hn", external_id="x", url="https://a.io", title="t", item_type=CT.ItemType.ARTICLE,
    trust=CT.TrustClass.VERIFIED_API, observed_at=NOW, excerpt="x" * (CT.EXCERPT_MAX + 1))))
ok("dislike event REQUIRES an undo deadline", raises(lambda: CT.InteractionEvent(
    item_id=1, action=CT.EventAction.DISLIKE, idempotency_key="k", created_at=NOW)))
ok("non-dislike event must NOT carry undo_until", raises(lambda: CT.InteractionEvent(
    item_id=1, action=CT.EventAction.LIKE, idempotency_key="k", created_at=NOW, undo_until=NOW)))
ok("dwell event requires bounded payload.ms", raises(lambda: CT.InteractionEvent(
    item_id=1, action=CT.EventAction.DWELL, idempotency_key="k", created_at=NOW)))
ok("RefreshJob refuses the favorites tab", raises(lambda: CT.RefreshJob(
    tab=CT.Tab.FAVORITES, state=CT.JobState.PENDING)))
ok("ModelRelease requires source_url evidence", raises(lambda: CT.ModelRelease(
    title="r", source_url=" ", observed_at=NOW)))
ok("NewsSettings refuses a favorites schedule", raises(lambda: CT.NewsSettings(
    schedules={"favorites": "daily"})))
ok("NewsSettings refuses unknown context classes", raises(lambda: CT.NewsSettings(
    context_classes={"raw_transcripts": True})))

# ── 4. canonical URLs + cursors ──────────────────────────────────────────────────────
h1 = CT.url_hash("https://Example.com/gpt6/?utm_source=x")
h2 = CT.url_hash("https://example.com/gpt6?fbclid=zz")
ok("tracking params/case/trailing slash normalize to one hash", h1 == h2)
ok("different paths stay distinct", CT.url_hash("https://example.com/other") != h1)
tok = CT.encode_cursor(7, 40)
ok("cursor round-trips", CT.decode_cursor(tok) == (7, 40))
ok("forged cursor raises", raises(lambda: CT.decode_cursor("nope!!")))
ok("limit clamps into [15,40]", (CT.clamp_limit(5), CT.clamp_limit(100), CT.clamp_limit("abc"),
                                 CT.clamp_limit(20)) == (15, 40, 15, 20))

# ── 5. event + interaction primitives ────────────────────────────────────────────────
conn = get_connection()
ev = CT.InteractionEvent(item_id=ITEM_ID, action=CT.EventAction.FAVORITE, idempotency_key="fav-1", created_at=NOW)
ok("record_event writes a new action", R.record_event(conn, ev) is True)
ok("replayed idempotency key is a no-op", R.record_event(conn, ev) is False)
ok("favorite protects the item (expiry cleared)", conn.execute(
    "SELECT expires_at FROM news_items WHERE id=?", (ITEM_ID,)).fetchone()[0] is None)
like = CT.InteractionEvent(item_id=ITEM_ID, action=CT.EventAction.LIKE, idempotency_key="like-1", created_at=NOW)
R.record_event(conn, like)
ok("a later touch never un-protects a favorite", conn.execute(
    "SELECT expires_at FROM news_items WHERE id=?", (ITEM_ID,)).fetchone()[0] is None)

state = R.upsert_interaction(conn, ITEM_ID, reaction=CT.Reaction.LIKE, expected_version=0)
ok("interaction upsert creates version 1", state["version"] == 1 and state["reaction"] == "like")
state = R.upsert_interaction(conn, ITEM_ID, favorite=True, expected_version=1)
ok("upsert bumps version and keeps prior fields", state["version"] == 2 and state["reaction"] == "like"
   and state["favorite"] == 1)
ok("stale optimistic version raises", raises(lambda: R.upsert_interaction(
    conn, ITEM_ID, note="n", expected_version=1)))
conn.commit()
conn.close()

# ── 6. rank snapshots: stable, pinned pagination ─────────────────────────────────────
conn = get_connection()
entries = [{"item_id": i, "score": 100 - i} for i in range(50)]
snap_a = R.write_rank_snapshot(conn, "feed:for_you", entries, "feed-v1")
page1 = R.read_snapshot_page(conn, kind="feed:for_you", limit=20)
ok("page 1 serves 20 entries from the newest snapshot", page1["snapshot_id"] == snap_a
   and len(page1["entries"]) == 20 and page1["entries"][0]["item_id"] == 0)
snap_b = R.write_rank_snapshot(conn, "feed:for_you", [{"item_id": 999}], "feed-v1")
page2 = R.read_snapshot_page(conn, cursor=page1["next_cursor"], limit=20)
ok("cursor stays PINNED to its snapshot after a newer one lands", page2["snapshot_id"] == snap_a
   and page2["entries"][0]["item_id"] == 20, str(page2["snapshot_id"]))
page3 = R.read_snapshot_page(conn, cursor=page2["next_cursor"], limit=20)
ok("final page closes the cursor chain", len(page3["entries"]) == 10 and page3["next_cursor"] is None)
fresh = R.read_snapshot_page(conn, kind="feed:for_you", limit=15)
ok("cursorless read serves the NEWEST snapshot", fresh["snapshot_id"] == snap_b)
conn.commit()
conn.close()

# ── 7. retention: expiry enforced, favorites/notes/live-undo protected ───────────────
conn = get_connection()
past = (now_utc() - timedelta(days=1)).isoformat()
old = (now_utc() - timedelta(days=CT.EVENT_AGGREGATE_DAYS + 10)).isoformat()
conn.execute("INSERT INTO news_items (url_hash, canonical_url, item_type, title, first_seen_at, expires_at)"
             " VALUES ('h-exp','https://x.io/e','article','expired untouched', ?, ?)", (old, past))
expired_id = conn.execute("SELECT id FROM news_items WHERE url_hash='h-exp'").fetchone()[0]
conn.execute("INSERT INTO news_item_sources (item_id, source, external_id, trust, observed_at)"
             " VALUES (?,?,?,?,?)", (expired_id, "hn", "e-1", "aggregator", old))
# settled ancient event → prunable; ancient dislike with a (theoretical) live undo → kept
R.record_event(conn, CT.InteractionEvent(item_id=ITEM_ID, action=CT.EventAction.OPEN,
                                         idempotency_key="old-open", created_at=old))
future_undo = (now_utc() + timedelta(seconds=CT.UNDO_SECONDS)).isoformat()
conn.execute("INSERT INTO news_interaction_events (item_id, action, idempotency_key, created_at, undo_until)"
             " VALUES (?,?,?,?,?)", (ITEM_ID, "dislike", "old-dis", old, future_undo))
conn.execute("INSERT INTO news_media_cache (url_hash, local_key, mime, bytes, expires_at)"
             " VALUES ('m1','k1','image/png', 10, ?)", (past,))
conn.commit()
result = R.run_retention(conn)
conn.commit()
ok("retention removes the expired untouched item (+ its evidence)", result["items"] == 1 and conn.execute(
    "SELECT COUNT(*) FROM news_item_sources WHERE item_id=?", (expired_id,)).fetchone()[0] == 0, str(result))
ok("favorited item survives retention", conn.execute(
    "SELECT COUNT(*) FROM news_items WHERE id=?", (ITEM_ID,)).fetchone()[0] == 1)
ok("ancient settled events are aggregated away", conn.execute(
    "SELECT COUNT(*) FROM news_interaction_events WHERE idempotency_key='old-open'").fetchone()[0] == 0)
ok("an event inside a live Undo window is never dropped", conn.execute(
    "SELECT COUNT(*) FROM news_interaction_events WHERE idempotency_key='old-dis'").fetchone()[0] == 1)
ok("expired media-cache rows are cleared", result["media"] == 1, str(result))
conn.close()

# ── 8. settings + flag ───────────────────────────────────────────────────────────────
conn = get_connection()
defaults = R.get_settings(conn)
ok("default settings: daily schedules, context classes off", defaults.schedules[CT.Tab.FEED.value] == "daily"
   and not any(defaults.context_classes.values()))
saved = R.set_settings(conn, CT.NewsSettings(schedules={"home": "weekly", "trending": "monthly", "feed": "daily"},
                                             enabled_sources=("hn", "github"),
                                             context_classes={"owner_interests": True}))
conn.commit()
loaded = R.get_settings(conn)
ok("settings round-trip", loaded.schedules["home"] == "weekly" and loaded.enabled_sources == ("hn", "github")
   and loaded.context_classes["owner_interests"] is True)
conn.execute("UPDATE news_settings SET value_json='{broken' WHERE key='settings'")
conn.commit()
ok("corrupted settings degrade to defaults, never raise", R.get_settings(conn).schedules == CT.NewsSettings().schedules)
conn.close()

ok("news.v2_enabled is registered and fails closed", "news.v2_enabled" in owner_flags.KEYS
   and owner_flags.get_bool(owner_flags.NEWS_V2_ENABLED, False) is False)

print(f"\nALL {PASS} CHECKS PASSED")

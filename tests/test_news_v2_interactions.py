"""News V2 N04 (#23): interactions, exact Undo, profiles, reasons, context caps.

Isolated temp DB, injected clocks (no sleeps). Proves the N04 acceptance gate —
REPLAY-SAFE actions and EXACT 10-second Undo behavior — plus favorite/note retention
protection, meaningful-dwell thresholds, committed-dislike profile semantics,
versioned profile provenance, the bounded immediate modifier, direct-action
precedence over context, and deterministic "Why shown" reasons.
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

TMP = Path(tempfile.mkdtemp(prefix="tobi_news_int_"))
os.environ["DB_PATH"] = str(TMP / "agent.db")

from core.database import init_database, get_connection  # noqa: E402

init_database()

from core.news import contracts as CT  # noqa: E402
from core.news import interactions as IX  # noqa: E402
from core.news import normalizer as N  # noqa: E402
from core.news import personalization as P  # noqa: E402

PASS = 0


def ok(name: str, cond: bool, detail: str = "") -> None:
    global PASS
    if not cond:
        print(f"FAIL {name} {detail}")
        sys.exit(1)
    PASS += 1
    print(f"PASS {name}")


T0 = datetime.now(timezone.utc)


def rec(source: str, ext: str, url: str, title: str, engagement: int = 0,
        published: str | None = None) -> CT.SourceRecord:
    return CT.SourceRecord(source=source, external_id=ext, url=url, title=title,
                           item_type=CT.ItemType.ARTICLE, trust=CT.TrustClass.AGGREGATOR,
                           observed_at=T0.isoformat(), engagement=engagement,
                           published_at=published)


conn = get_connection()
N.ingest(conn, [
    rec("hn", "a", "https://x.io/a", "Rust compiler internals deep dive", 500),
    rec("hn", "b", "https://x.io/b", "Async runtime scheduling tricks", 50),
    rec("reddit", "c", "https://x.io/c", "Random gossip thread", 20),
    rec("openai_blog", "d", "https://x.io/d", "GPT-6 model release notes", 2000,
        (T0 - timedelta(hours=1)).isoformat()),
    rec("hn", "e", "https://x.io/e", "Boundary case story", 5),
    rec("hn", "f", "https://x.io/f", "Neutral protection story", 5),
    rec("openai_blog", "g", "https://x.io/g", "Quiet unrelated words entirely", 2000),
])
conn.commit()
ids = {ext: conn.execute("SELECT id FROM news_items WHERE url_hash=?",
                         (CT.url_hash(f"https://x.io/{ext}"),)).fetchone()[0]
       for ext in "abcdefg"}
A, B, C, D, E, F, G = (ids[k] for k in "abcdefg")


def events(item_id: int) -> int:
    return conn.execute("SELECT COUNT(*) FROM news_interaction_events WHERE item_id=?",
                        (item_id,)).fetchone()[0]


def expiry(item_id: int):
    return conn.execute("SELECT expires_at FROM news_items WHERE id=?", (item_id,)).fetchone()[0]


# ── A. like is replay-safe ───────────────────────────────────────────────────────────
state = IX.like(conn, A, "k1", now=T0)
ok("like sets the reaction", state["reaction"] == "like" and state["version"] == 1)
replay = IX.like(conn, A, "k1", now=T0)
ok("replayed like is a pure no-op", replay["version"] == 1 and events(A) == 1)
try:
    IX.like(conn, 999_999, "k-x", now=T0)
    ok("unknown item refused", False)
except ValueError:
    ok("unknown item refused", True)

# ── B. dislike: hidden immediately, EXACTLY 10 seconds to undo ───────────────────────
state = IX.dislike(conn, B, "d1", now=T0)
ok("dislike hides immediately with the exact deadline", state["reaction"] == "dislike"
   and state["undo_until"] == (T0 + timedelta(seconds=10)).isoformat())
state = IX.undo_dislike(conn, B, "u1", now=T0 + timedelta(seconds=9))
ok("undo inside the window restores the item", state["reaction"] == "none")
reversed_row = conn.execute("SELECT reversed_by FROM news_interaction_events"
                            " WHERE idempotency_key='d1'").fetchone()
ok("the reversal is linked onto the dislike event", reversed_row[0] is not None)
ok("a reversed dislike never commits", IX.committed_dislike(conn, B, T0 + timedelta(days=1)) is False)
replay = IX.undo_dislike(conn, B, "u1", now=T0 + timedelta(seconds=9))
ok("replayed undo is a pure no-op", replay["reaction"] == "none"
   and conn.execute("SELECT COUNT(*) FROM news_interaction_events WHERE action='undo'"
                    " AND item_id=?", (B,)).fetchone()[0] == 1)

IX.dislike(conn, C, "d2", now=T0)
try:
    IX.undo_dislike(conn, C, "u2", now=T0 + timedelta(seconds=11))
    ok("undo after the deadline refused", False)
except ValueError:
    ok("undo after the deadline refused", True)
ok("an un-reversed dislike commits after its window",
   IX.committed_dislike(conn, C, T0 + timedelta(seconds=11)) is True
   and IX.committed_dislike(conn, C, T0 + timedelta(seconds=5)) is False)

IX.dislike(conn, E, "d3", now=T0)
state = IX.undo_dislike(conn, E, "u3", now=T0 + timedelta(seconds=10))
ok("undo at exactly the 10-second boundary still counts", state["reaction"] == "none")

# ── C. favorites and notes drive retention protection ────────────────────────────────
IX.set_favorite(conn, D, True, "f1", now=T0)
ok("favorite protects indefinitely", expiry(D) is None)
IX.set_note(conn, D, "worth keeping", "n1", now=T0)
IX.set_favorite(conn, D, False, "f2", now=T0)
ok("a noted item stays protected after unfavorite", expiry(D) is None)
IX.set_favorite(conn, D, True, "f3", now=T0)

IX.set_favorite(conn, F, True, "f4", now=T0)
IX.set_favorite(conn, F, False, "f5", now=T0)
ok("unfavorite with no note restores the retention clock", expiry(F) is not None)
IX.set_note(conn, F, "temp", "n2", now=T0)
ok("a note re-protects", expiry(F) is None)
IX.set_note(conn, F, "", "n3", now=T0)
ok("clearing the note un-protects an unfavorited item", expiry(F) is not None)

# ── D. passive signals: open + meaningful dwell ──────────────────────────────────────
IX.record_open(conn, A, "o1", now=T0)
IX.record_open(conn, A, "o1", now=T0)
state = IX.record_open(conn, A, "o2", now=T0)
ok("opens aggregate once per idempotency key", state["opens"] == 2)
state = IX.record_dwell(conn, A, 3000, "w1", now=T0)
ok("sub-threshold dwell is ignored entirely", state["recorded"] is False and state["dwell_ms"] == 0
   and conn.execute("SELECT COUNT(*) FROM news_interaction_events WHERE action='dwell'").fetchone()[0] == 0)
state = IX.record_dwell(conn, A, 8000, "w2", now=T0)
replay = IX.record_dwell(conn, A, 8000, "w2", now=T0)
ok("meaningful dwell aggregates once", state["recorded"] is True and replay["dwell_ms"] == 8000)

# ── E. profile: committed-dislike semantics, versions, provenance ────────────────────
conn.commit()
T1 = T0 + timedelta(seconds=60)
profile = P.recompute_profile(conn, now=T1)
ok("positive signals build source affinity (like+open+dwell on hn)",
   profile["sources"].get("hn") == 5.0, str(profile["sources"]))
ok("committed dislike drives its source negative", profile["sources"].get("reddit") == -5.0)
ok("favorite + note weigh strongest", profile["sources"].get("openai_blog") == 9.0)
ok("undone dislikes leave no trace", profile["provenance"]["items_considered"] == 3,
   str(profile["provenance"]))
ok("title topics carry the item's weight", profile["topics"].get("rust") == 5.0)
profile2 = P.recompute_profile(conn, now=T1 + timedelta(seconds=1))
ok("recompute versions monotonically; latest is active",
   profile2["version"] == 2 and P.active_profile(conn)["version"] == 2)

# ── F. immediate bounded modifier ────────────────────────────────────────────────────
T2 = T1 + timedelta(seconds=120)
IX.like(conn, B, "k2", now=T2)
conn.commit()
deltas = P.immediate_adjustments(conn, now=T2)
ok("fresh actions surface immediately, clamped to ±2", deltas == {"hn": 2.0}, str(deltas))

# ── G. context: owner toggles, ±5 cap, direct-action precedence ──────────────────────
settings_off = CT.NewsSettings()
ok("disabled context classes contribute nothing",
   P.context_delta({"owner_interests": 4.0}, settings_off, False) == 0.0)
settings_on = CT.NewsSettings(context_classes={"owner_interests": True, "project_topics": True})
ok("enabled context counts and clamps to +5",
   P.context_delta({"owner_interests": 4.0, "project_topics": 3.0}, settings_on, False) == 5.0)
ok("negative context clamps to -5",
   P.context_delta({"owner_interests": -8.0}, settings_on, False) == -5.0)
ok("unknown context classes are ignored",
   P.context_delta({"raw_transcripts": 99.0}, settings_on, False) == 0.0)
ok("a direct News action takes precedence — context contributes zero",
   P.context_delta({"owner_interests": 4.0}, settings_on, True) == 0.0)

# ── H. deterministic "Why shown" reasons ─────────────────────────────────────────────
prof = P.active_profile(conn)
reasons = P.reasons_for(conn, G, prof)      # no topic overlap → pure affinity + popularity
ok("top-2 reasons come from affinity then popularity",
   [r["reason"] for r in reasons] == ["You often engage with openai_blog posts", "Popular on openai_blog"],
   str(reasons))
ok("reasons are deterministic across calls", P.reasons_for(conn, G, prof) == reasons
   and P.reasons_for(conn, D, prof) == P.reasons_for(conn, D, prof))
ok("every reason carries its strength", all(r["strength"] > 0 for r in reasons)
   and len(P.reasons_for(conn, D, prof)) == 2)
try:
    P.reasons_for(conn, 999_999, prof)
    ok("reasons for an unknown item refused", False)
except ValueError:
    ok("reasons for an unknown item refused", True)

conn.commit()
conn.close()
print(f"\nALL {PASS} CHECKS PASSED")

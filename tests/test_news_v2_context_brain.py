"""News V2 N11 (#23): approved cross-module context, Save to Brain, and the Chat read.

Isolated temp DB, no network, no LLM. Proves the N11 acceptance gate — *no automatic
write, no raw-transcript retrieval* — plus:

- context classes are OFF by default and read nothing until the owner enables them;
- an enabled class only ever contributes what the owner himself wrote (an approved
  Brain memory, an active project, a stored chat SUMMARY), never a raw transcript;
- the nudge is capped, loses to any direct News action, and is visible on the card;
- Save to Brain writes once per item, carries ``news:<item_id>`` provenance through
  the accepted Brain facade, and reports Brain's refusal instead of faking success;
- the Chat read model answers from stored rows only, never inventing a figure, and
  falls back to V1 Explore rather than claiming there is no news.
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

TMP = Path(tempfile.mkdtemp(prefix="tobi_news_n11_"))
os.environ["DB_PATH"] = str(TMP / "agent.db")

from core.database import init_database, get_connection  # noqa: E402

init_database()

from core import brain  # noqa: E402
from core.news import brain_adapter as BA  # noqa: E402
from core.news import contracts as CT  # noqa: E402
from core.news import context as CX  # noqa: E402
from core.news import interactions as IX  # noqa: E402
from core.news import normalizer as N  # noqa: E402
from core.news import personalization as P  # noqa: E402
from core.news import ranking as RK  # noqa: E402
from core.news import reader as RD  # noqa: E402
from core.news import repository as R  # noqa: E402

PASS = 0


def ok(name: str, cond: bool, detail: str = "") -> None:
    global PASS
    if not cond:
        print(f"FAIL {name} {detail}")
        sys.exit(1)
    PASS += 1
    print(f"PASS {name}")


def raises(fn) -> bool:
    try:
        fn()
    except Exception:
        return True
    return False


T0 = datetime.now(timezone.utc)


def rec(source: str, ext: str, url: str, title: str, engagement: int = 0,
        excerpt: str | None = None) -> CT.SourceRecord:
    return CT.SourceRecord(source=source, external_id=ext, url=url, title=title,
                           item_type=CT.ItemType.ARTICLE, trust=CT.TrustClass.AGGREGATOR,
                           observed_at=T0.isoformat(), engagement=engagement,
                           published_at=T0.isoformat(), excerpt=excerpt or "")


conn = get_connection()
N.ingest(conn, [
    rec("hn", "a", "https://x.io/a", "Kubernetes operator patterns explained", 400,
        "How operators reconcile desired state."),
    rec("hn", "b", "https://x.io/b", "Watercolour brush techniques for beginners", 400),
    rec("rss", "c", "https://x.io/c", "Telegram bot delivery at scale", 400),
])
conn.commit()
IDS = {r[1]: r[0] for r in conn.execute("SELECT id, title FROM news_items")}
KUBE = next(v for k, v in IDS.items() if k.startswith("Kubernetes"))
PAINT = next(v for k, v in IDS.items() if k.startswith("Watercolour"))
TELE = next(v for k, v in IDS.items() if k.startswith("Telegram"))


# ── 1. context is OFF by default and reads nothing ───────────────────────────────────
settings = R.get_settings(conn)
ok("every context class ships off", all(not settings.context_classes.get(c, False)
                                        for c in CT.CONTEXT_CLASSES),
   str(settings.context_classes))
ok("a disabled class is not read at all", CX.available_topics(conn, settings) == {})
ok("context scores are empty while every class is off",
   CX.collect_context_scores(conn, [KUBE, PAINT, TELE], settings) == {})


# ── 2. an enabled class contributes only the owner's own words ───────────────────────
conn.execute("INSERT INTO pm_projects (name, description, status) VALUES (?,?,?)",
             ("Kubernetes migration", "Move the cluster onto operator patterns", "active"))
conn.execute("INSERT INTO pm_projects (name, description, status) VALUES (?,?,?)",
             ("Watercolour hobby", "Painting on weekends", "idea"))   # NOT active
conn.commit()

on_projects = CT.NewsSettings(schedules=dict(settings.schedules),
                              enabled_sources=settings.enabled_sources,
                              context_classes={"project_topics": True})
topics = CX.available_topics(conn, on_projects)
ok("only the enabled class is loaded", set(topics) == {"project_topics"}, str(list(topics)))
ok("an ACTIVE project supplies topics", "kubernetes" in topics["project_topics"])
ok("a non-active project supplies nothing", "watercolour" not in topics["project_topics"])

scores = CX.collect_context_scores(conn, [KUBE, PAINT, TELE], on_projects)
ok("context lands on the matching item only", set(scores) == {KUBE}, str(scores))
ok("its class is named in the score", set(scores[KUBE]) == {"project_topics"})

prov = CX.explain(conn, KUBE, on_projects)
ok("provenance names the owner's own phrase",
   prov and prov[0]["context_class"] == "project_topics"
   and "Kubernetes migration" in prov[0]["because"], str(prov))
ok("an unmatched item has no provenance", CX.explain(conn, PAINT, on_projects) == [])


# ── 3. chat context reads SUMMARIES, never the transcript ────────────────────────────
conn.execute("INSERT INTO chat_sessions (title) VALUES ('s')")
sid = conn.execute("SELECT id FROM chat_sessions ORDER BY id DESC LIMIT 1").fetchone()[0]
conn.execute("INSERT INTO chat_messages (session_id, role, content) VALUES (?,?,?)",
             (sid, "user", "secret transcript about watercolour brushes"))
conn.execute("INSERT INTO chat_session_summaries (session_id, summary, through_message_id, updated_at)"
             " VALUES (?,?,?,?)", (sid, "Owner is working on Telegram delivery", 1, T0.isoformat()))
conn.commit()

on_chat = CT.NewsSettings(schedules=dict(settings.schedules),
                          enabled_sources=settings.enabled_sources,
                          context_classes={"chat_topics": True})
chat_topics = CX.available_topics(conn, on_chat)["chat_topics"]
ok("the stored chat SUMMARY supplies topics", "telegram" in chat_topics)
ok("the raw transcript is never read", "watercolour" not in chat_topics
   and "brushes" not in chat_topics, str(sorted(chat_topics)))
ok("chat context lands on the matching story",
   set(CX.collect_context_scores(conn, [KUBE, PAINT, TELE], on_chat)) == {TELE})


# ── 4. approved Brain memories only ──────────────────────────────────────────────────
brain.add_memory("I care about kubernetes operators", "preferences", source="remember",
                 status="active")
brain.add_memory("watercolour painting is my hobby", "preferences", source="remember",
                 status="pending")                       # NOT approved
on_brain = CT.NewsSettings(schedules=dict(settings.schedules),
                           enabled_sources=settings.enabled_sources,
                           context_classes={"owner_interests": True})
interests = CX.available_topics(conn, on_brain)["owner_interests"]
ok("an approved memory supplies topics", "kubernetes" in interests)
ok("a pending memory is never read", "watercolour" not in interests, str(sorted(interests)))


# ── 5. the nudge stays bounded and loses to a direct action ──────────────────────────
ok("context is capped at ±5 points",
   P.context_delta({"project_topics": 99.0}, on_projects, False) == P.CONTEXT_CAP)
ok("a direct News action overrides context entirely",
   P.context_delta({"project_topics": 99.0}, on_projects, True) == 0.0)
ok("a class the owner left off contributes nothing",
   P.context_delta({"chat_topics": 5.0}, on_projects, False) == 0.0)

R.set_settings(conn, on_projects)
conn.commit()
RK.build_feed_snapshots(conn, T0)
conn.commit()
page = R.read_snapshot_page(conn, kind="feed:for_you", limit=20)
by_id = {e["item_id"]: e for e in page["entries"]}
ok("the nudged item records its context points", by_id[KUBE]["context_points"] > 0,
   str(by_id[KUBE]))
ok("an unmatched item records none", by_id[PAINT]["context_points"] == 0)
ok("the card says WHICH part of TOBI nudged it",
   any(r.get("context_class") == "project_topics" for r in by_id[KUBE]["reasons"]),
   str(by_id[KUBE]["reasons"]))
ok("the reason quotes the owner's own phrase",
   any("Kubernetes migration" in (r.get("reason") or "") for r in by_id[KUBE]["reasons"]))

IX.like(conn, PAINT, "ctx-direct")
conn.commit()
RK.build_feed_snapshots(conn, T0)
conn.commit()
direct = {e["item_id"]: e for e in R.read_snapshot_page(
    conn, kind="feed:for_you", limit=20)["entries"]}
ok("a liked item takes no context at all", direct[PAINT]["context_points"] == 0)

R.set_settings(conn, settings)          # back to the shipped default: all classes off
conn.commit()
RK.build_feed_snapshots(conn, T0)
conn.commit()
off = {e["item_id"]: e for e in R.read_snapshot_page(
    conn, kind="feed:for_you", limit=20)["entries"]}
ok("turning every class back off removes the nudge", off[KUBE]["context_points"] == 0)


# ── 6. Save to Brain: explicit, once, with provenance ────────────────────────────────
ok("nothing is in Brain before the owner presses the button",
   BA.existing_save(conn, KUBE) is None
   and conn.execute("SELECT COUNT(*) FROM news_brain_saves").fetchone()[0] == 0)

text, evidence = BA.build_memory_text(conn, KUBE)
ok("the saved text is built from stored evidence only",
   "Kubernetes operator patterns explained" in text and "https://x.io/a" in text
   and evidence["source"] == "hn", text)
ok("an unknown item is refused, not invented",
   raises(lambda: BA.build_memory_text(conn, 99999)))

saved = BA.save_to_brain(conn, KUBE)
conn.commit()
ok("the save succeeds and reports Brain's own action",
   saved["ok"] and saved["action"] in ("active", "merged") and not saved["already_saved"],
   str(saved))
ok("provenance is news:<item_id>", saved["provenance"] == f"news:{KUBE}")
row = conn.execute("SELECT source, content FROM brain_memories WHERE id=?",
                   (saved["memory_id"],)).fetchone()
ok("the Brain row carries the News provenance", row and row[0] == f"news:{KUBE}", str(row))
ok("the Brain page can find it by source",
   any(m["id"] == saved["memory_id"] for m in brain.list_memories(source=f"news:{KUBE}")))

again = BA.save_to_brain(conn, KUBE)
conn.commit()
ok("a second press does not remember it twice",
   again["already_saved"] and again["memory_id"] == saved["memory_id"], str(again))
ok("exactly one save row exists",
   conn.execute("SELECT COUNT(*) FROM news_brain_saves").fetchone()[0] == 1)
ok("saving is never automatic — the other items are untouched",
   BA.existing_save(conn, PAINT) is None and BA.existing_save(conn, TELE) is None)
ok("the page badge query finds exactly the saved item",
   BA.saved_item_ids(conn, [KUBE, PAINT, TELE]) == {KUBE})


# a Brain refusal is reported, not reshaped into a success
_real_remember = brain.remember
try:
    brain.remember = lambda *a, **k: {"ok": False, "action": "blocked",
                                      "v2": {"error": "unlock the vault to store it"}}
    refused = BA.save_to_brain(conn, TELE)
    conn.commit()
    ok("a Brain refusal is reported truthfully",
       not refused["ok"] and "vault" in refused["error"], str(refused))
    ok("a refused save records nothing", BA.existing_save(conn, TELE) is None)
finally:
    brain.remember = _real_remember


# ── 7. the Chat read model — grounded, never invented ────────────────────────────────
over = RD.read(section="overview", conn=conn)
ok("overview counts what is really stored",
   over["collected"]["items"] == 3 and over["collected"]["saved_to_brain"] == 1, str(over["collected"]))

feed = RD.read(section="feed", conn=conn)
ok("the feed read returns stored items with their source",
   feed["items"] and all(i.get("source") and i.get("url") for i in feed["items"]))

models = RD.read(section="models", conn=conn)
ok("no model ranking is invented when none was collected",
   models["models"] == [] and "collected" in models["note"].lower(), str(models))

trend = RD.read(section="trending", window="week", conn=conn)
ok("no GitHub growth is invented before a snapshot exists",
   trend["repos"] == [] and trend["note"], str(trend))

found = RD.read(query="kubernetes", conn=conn)
ok("search resolves to the search section", found["section"] == "search")
ok("search finds the real story", any(m["item_id"] == KUBE for m in found["matches"]))
missing = RD.read(query="zzz-nothing-here", conn=conn)
ok("a miss says so instead of guessing",
   missing["matches"] == [] and "matches" in missing["note"], str(missing))

one = RD.read(section="item", item_id=KUBE, conn=conn)
ok("one story reads back with its sources and the owner's own state",
   one["item_id"] == KUBE and one["sources"] and one["saved_to_brain"] is True, str(one)[:200])
ok("an unknown item id is an honest error",
   "error" in RD.read(section="item", item_id=99999, conn=conn))
ok("section=item without an id says what is missing",
   "item_id" in RD.read(section="item", conn=conn)["error"])

IX.set_note(conn, PAINT, "worth revisiting", "n11-note")
IX.set_favorite(conn, TELE, True, "n11-fav")
conn.commit()
favs = RD.read(section="favorites", conn=conn)
notes = RD.read(section="notes", conn=conn)
ok("favorites read back", any(f["item_id"] == TELE for f in favs["favorites"]), str(favs))
ok("private notes read back", any(n["note"] == "worth revisiting" for n in notes["notes"]))

ok("an unknown section is refused", "error" in RD.read(section="nonsense", conn=conn))
ok("limit is clamped to the bounded page size",
   len(RD.read(section="feed", limit=9999, conn=conn)["items"]) <= RD.MAX_ITEMS)

# text is treated as evidence, and bounded on the way out
long_title = "x" * 5000
N.ingest(conn, [rec("hn", "long", "https://x.io/long", long_title, 1)])
conn.commit()
long_id = conn.execute("SELECT id FROM news_items WHERE url_hash=("
                       "SELECT url_hash FROM news_items ORDER BY id DESC LIMIT 1)").fetchone()[0]
ok("source text is length-capped before it reaches the model",
   len(RD.read(section="item", item_id=long_id, conn=conn)["title"]) <= 300)

# the registered Chat tool answers through the same read model
from core.conductor_registry import READ_TOOLS  # noqa: E402
ok("read_news is registered as a Chat read tool", "read_news" in READ_TOOLS)
tool_fn, tool_help = READ_TOOLS["read_news"]
ok("its help tells the model to quote the stored source",
   "source" in tool_help and "News" in tool_help)
ok("the tool returns the same grounded shape",
   tool_fn(section="item", item_id=KUBE)["item_id"] == KUBE)
ok("the tool never raises on a bad section",
   "error" in tool_fn(section="nonsense"))

conn.close()
print(f"\nALL {PASS} CHECKS PASSED")

"""News V2 N06 (#23): the /api/explore/v2 surface — contracts, cursors, guards.

Isolated temp DB, in-process TestClient, stubbed adapters (no network). Proves the
N06 acceptance gate — API contracts and cursor behavior — plus the fail-closed flag
gate (503), Idempotency-Key enforcement (400) with replay short-circuit, optimistic
version conflicts (409), limit clamping, refresh lifecycle + SSE, media key safety,
and legacy /api/explore/* rollback parity.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TMP = Path(tempfile.mkdtemp(prefix="tobi_news_api_"))
os.environ["DB_PATH"] = str(TMP / "agent.db")

from core.database import init_database, get_connection  # noqa: E402

init_database()

from fastapi.testclient import TestClient  # noqa: E402

from api.dashboard import app  # noqa: E402
from core import owner_flags  # noqa: E402
from core.news import contracts as CT  # noqa: E402
from core.news import normalizer as N  # noqa: E402
from core.news import ranking as RK  # noqa: E402
from core.news import refresh  # noqa: E402
from core.news.sources import base  # noqa: E402

PASS = 0


def ok(name: str, cond: bool, detail: str = "") -> None:
    global PASS
    if not cond:
        print(f"FAIL {name} {detail}")
        sys.exit(1)
    PASS += 1
    print(f"PASS {name}")


client = TestClient(app)
V2 = "/api/explore/v2"
NOW = datetime.now(timezone.utc)

# ── 1. fail-closed gate (config stays reachable so the UI can pick V1 vs V2) ─────────
ok("V2 surface is 503 until the owner opts in", client.get(f"{V2}/home").status_code == 503)
cfg = client.get(f"{V2}/config")
ok("config is ungated and reports both flags off", cfg.status_code == 200
   and cfg.json() == {"enabled": False, "shadow": False})
owner_flags.set_bool(owner_flags.NEWS_V2_SHADOW, True)
ok("shadow flag opens the surface", client.get(f"{V2}/home").status_code == 200)
ok("config reflects the flag flip", client.get(f"{V2}/config").json()["shadow"] is True)

# ── 2. seed evidence + snapshots ─────────────────────────────────────────────────────
conn = get_connection()


def metric(model, source, name, value):
    return CT.ModelMetric(model_id=model, category="general", source=source, metric=name,
                          value=value, confidence=0.9, observed_at=NOW.isoformat(),
                          formula_version="raw")


N.ingest_model_evidence(conn,
                        [metric("alpha/one", "bench", "intelligence", 80.0),
                         metric("alpha/one", "arena", "elo", 1300.0),
                         metric("beta/two", "bench", "intelligence", 60.0),
                         metric("beta/two", "arena", "elo", 1400.0)]
                        + [metric(f"pager/m{i:02d}", "bench", "speed", float(i)) for i in range(16)],
                        [CT.ModelRelease(title="Alpha One launch", source_url="https://alpha.ai/one",
                                         observed_at=NOW.isoformat(), model_id="alpha/one",
                                         released_at=NOW.isoformat())])
N.ingest(conn, [
    CT.SourceRecord(source="hn", external_id="h1", url="https://x.io/h1", title="Feed story one",
                    item_type=CT.ItemType.ARTICLE, trust=CT.TrustClass.VERIFIED_API,
                    observed_at=NOW.isoformat(), engagement=300,
                    published_at=(NOW - timedelta(hours=1)).isoformat()),
    CT.SourceRecord(source="wire", external_id="w1", url="https://x.io/w1", title="Feed story two",
                    item_type=CT.ItemType.ARTICLE, trust=CT.TrustClass.AGGREGATOR,
                    observed_at=NOW.isoformat(), engagement=10,
                    published_at=(NOW - timedelta(hours=2)).isoformat()),
    CT.SourceRecord(source="hn", external_id="t1", url="https://x.io/t1", title="Show HN neat tool",
                    item_type=CT.ItemType.TOOL, trust=CT.TrustClass.VERIFIED_API,
                    observed_at=NOW.isoformat(), engagement=90),
])
N.ingest_github_snapshots(conn, [
    CT.GitHubSnapshot(repo="o/r", snapshot_date=(NOW - timedelta(days=8)).date().isoformat(), stars=100),
    CT.GitHubSnapshot(repo="o/r", snapshot_date=NOW.date().isoformat(), stars=150),
])
# Tool Discovery shows only SPOTLIGHTED picks now — give the tool a content-creator recap.
conn.execute("UPDATE news_items SET recap='A neat tool.\n**Highlights**\n- fast', recap_at=?"
             " WHERE url_hash=?", (NOW.isoformat(), CT.url_hash("https://x.io/t1")))
for tab in ("home", "trending", "feed"):
    RK.rebuild_for_tab(conn, tab, now=NOW)
conn.commit()
A = conn.execute("SELECT id FROM news_items WHERE url_hash=?", (CT.url_hash("https://x.io/h1"),)).fetchone()[0]
B = conn.execute("SELECT id FROM news_items WHERE url_hash=?", (CT.url_hash("https://x.io/w1"),)).fetchone()[0]
conn.close()

# ── 3. reads: home / models / trending / feed ────────────────────────────────────────
home = client.get(f"{V2}/home").json()
ok("home serves the LLM Top list + releases + freshness from snapshots",
   home["top"] and len(home["top"]) <= 20 and home["releases"][0]["title"] == "Alpha One launch"
   and "models:top" in home["freshness"])
ok("home top entries are attributed", all(
    e["sources"] and e["formula_version"] for e in home["top"]))

models = client.get(f"{V2}/models", params={"limit": 15}).json()
ok("model explorer pages with a keyset cursor", len(models["models"]) == 15
   and models["next_cursor"])
page2 = client.get(f"{V2}/models", params={"limit": 15, "cursor": models["next_cursor"]}).json()
ids1 = {m["model_id"] for m in models["models"]}
ids2 = {m["model_id"] for m in page2["models"]}
ok("cursor pages never overlap and terminate", not (ids1 & ids2) and page2["next_cursor"] is None
   and len(ids1 | ids2) == 18)
ok("explorer search filters by model id", {m["model_id"] for m in client.get(
    f"{V2}/models", params={"q": "alpha"}).json()["models"]} == {"alpha/one"})
ok("explorer metrics carry attribution", all(
    m["metrics"][0]["source"] and m["metrics"][0]["observed_at"]
    for m in client.get(f"{V2}/models", params={"q": "alpha"}).json()["models"]))
ok("bad explorer cursor is a 422", client.get(f"{V2}/models", params={"cursor": "zzz!"}).status_code == 422)

boards = client.get(f"{V2}/models/leaderboards").json()["categories"]
ok("leaderboards are data-driven per category, sourced, and Top-5 bounded",
   boards and all(b["sources"] and len(b["entries"]) <= 5 for b in boards)
   and {b["category"] for b in boards} == {r[0] for r in get_connection().execute(
       "SELECT DISTINCT category FROM news_model_metrics")})
ok("leaderboard entries are ranked deterministically",
   all(b["entries"] == sorted(b["entries"], key=lambda e: (-e["score"], e["model_id"]))
       for b in boards))

trending = client.get(f"{V2}/trending", params={"section": "github", "window": "week"}).json()
ok("trending github serves the snapshot with growth", trending["entries"][0]["growth"] == 50)
ok("bad trending window is a 422", client.get(
    f"{V2}/trending", params={"section": "github", "window": "fortnight"}).status_code == 422)
# owner: "add filter menu — all topic, AI, …". Every row carries a derived topic facet.
ok("trending github rows carry a topic facet + the topic list",
   trending["entries"][0]["topic"] == "Other" and "AI/ML" in trending.get("topics", []))
ai_only = client.get(f"{V2}/trending",
                     params={"section": "github", "window": "week", "topic": "AI/ML"}).json()
kept = client.get(f"{V2}/trending",
                  params={"section": "github", "window": "week", "topic": "Other"}).json()
ok("topic filter narrows the board (AI/ML → none here) and All topics is a no-op",
   ai_only["entries"] == [] and len(kept["entries"]) == len(trending["entries"])
   and len(trending["entries"]) > 0)
tools = client.get(f"{V2}/trending", params={"section": "tools"}).json()
ok("tools section enriches canonical items", tools["entries"]
   and tools["entries"][0]["interaction"]["version"] == 0)
sources = client.get(f"{V2}/trending", params={"section": "sources"}).json()
ok("sources section projects the canonical store", {s["source"] for s in sources["sources"]}
   >= {"hn", "wire"})

feed = client.get(f"{V2}/feed", params={"mode": "for_you", "limit": 100}).json()
ok("for_you serves enriched snapshot entries", feed["snapshot_id"]
   and all("interaction" in e and "url" in e and len(e["reasons"]) <= 2 for e in feed["entries"]))
ok("feed source filter applies within the page", all(
    e["source"] == "wire" for e in client.get(
        f"{V2}/feed", params={"mode": "for_you", "source": "wire"}).json()["entries"]))
ok("bad feed mode is a 422", client.get(f"{V2}/feed", params={"mode": "surprise"}).status_code == 422)

# ── 4. mutations: idempotency + optimistic version ───────────────────────────────────
ok("mutation without Idempotency-Key is a 400", client.patch(
    f"{V2}/items/{A}/interaction", json={"action": "like", "version": 0}).status_code == 400)
ok("stale version is a 409", client.patch(
    f"{V2}/items/{A}/interaction", json={"action": "like", "version": 5},
    headers={"Idempotency-Key": "k0"}).status_code == 409)
r = client.patch(f"{V2}/items/{A}/interaction", json={"action": "like", "version": 0},
                 headers={"Idempotency-Key": "k1"}).json()
ok("like lands with a bumped version", r["reaction"] == "like" and r["version"] == 1)
r = client.patch(f"{V2}/items/{A}/interaction", json={"action": "like", "version": 0},
                 headers={"Idempotency-Key": "k1"}).json()
ok("replayed key short-circuits before the version check", r["replayed"] is True and r["version"] == 1)
r = client.patch(f"{V2}/items/{A}/interaction", json={"action": "dislike", "version": 1},
                 headers={"Idempotency-Key": "k2"}).json()
ok("dislike returns its exact undo deadline", r["reaction"] == "dislike" and r.get("undo_until"))
r = client.patch(f"{V2}/items/{A}/interaction", json={"action": "undo", "version": 2},
                 headers={"Idempotency-Key": "k3"}).json()
ok("undo inside the window restores via the API", r["reaction"] == "none" and r["version"] == 3)
r = client.put(f"{V2}/items/{A}/note", json={"note": "worth a read", "version": 3},
               headers={"Idempotency-Key": "k4"}).json()
ok("note upserts with version enforcement", r["note"] == "worth a read" and r["version"] == 4)
ok("note with a stale version is a 409", client.put(
    f"{V2}/items/{A}/note", json={"note": "x", "version": 1},
    headers={"Idempotency-Key": "k4b"}).status_code == 409)
r = client.post(f"{V2}/items/{A}/events", json={"type": "open"},
                headers={"Idempotency-Key": "k5"}).json()
replay = client.post(f"{V2}/items/{A}/events", json={"type": "open"},
                     headers={"Idempotency-Key": "k5"}).json()
ok("open events aggregate once per key", r["opens"] == 1 and replay["opens"] == 1)
r = client.post(f"{V2}/items/{A}/events", json={"type": "dwell", "ms": 8000},
                headers={"Idempotency-Key": "k6"}).json()
ok("meaningful dwell records through the API", r["recorded"] is True and r["dwell_ms"] == 8000)
r = client.post(f"{V2}/items/{A}/events", json={"type": "dwell", "ms": 1000},
                headers={"Idempotency-Key": "k7"}).json()
ok("sub-threshold dwell reports recorded=false", r["recorded"] is False)
ok("unknown item is a 404", client.patch(
    f"{V2}/items/999999/interaction", json={"action": "like", "version": 0},
    headers={"Idempotency-Key": "k8"}).status_code == 404)
ok("favorites mode lists favorited items", client.patch(
    f"{V2}/items/{A}/interaction", json={"action": "favorite", "version": 4},
    headers={"Idempotency-Key": "k9"}).status_code == 200 and [
    e["item_id"] for e in client.get(f"{V2}/feed", params={"mode": "favorites"}).json()["entries"]] == [A])
# N11 Save to Brain — explicit, once per item, provenance-stamped, 404 on unknown.
r = client.post(f"{V2}/items/{A}/save-to-brain")
ok("save-to-brain stores the item on the owner's explicit press",
   r.status_code == 200 and r.json()["ok"] and r.json()["provenance"] == f"news:{A}"
   and r.json()["already_saved"] is False, f"{r.status_code} {r.text[:200]}")
again = client.post(f"{V2}/items/{A}/save-to-brain").json()
ok("a second press returns the first save instead of remembering it twice",
   again["already_saved"] is True and again["memory_id"] == r.json()["memory_id"])
ok("the saved state is readable for the card badge",
   client.get(f"{V2}/items/{A}/brain-save").json()["saved"]["provenance"] == f"news:{A}")
ok("saving an unknown item is a 404, not a silent success",
   client.post(f"{V2}/items/999999/save-to-brain").status_code == 404)
ok("an item nobody pressed save on is NOT in Brain",
   client.get(f"{V2}/items/{B}/brain-save").json()["saved"] is None)
ok("the feed carries the Brain-save badge", {
    e["item_id"]: e["saved_to_brain"] for e in
    client.get(f"{V2}/feed", params={"mode": "latest"}).json()["entries"]}.get(A) is True)

# ── 5. settings ──────────────────────────────────────────────────────────────────────
settings = client.get(f"{V2}/settings").json()
ok("settings expose schedules + options + known sources", settings["schedules"]["feed"] == "daily"
   and "weekly" in settings["schedule_options"] and settings["known_sources"])
r = client.patch(f"{V2}/settings", json={"schedules": {"home": "weekly", "trending": "daily",
                                                       "feed": "daily"}}).json()
ok("schedule updates persist", r["schedules"]["home"] == "weekly"
   and client.get(f"{V2}/settings").json()["schedules"]["home"] == "weekly")
ok("a favorites schedule is refused", client.patch(
    f"{V2}/settings", json={"schedules": {"favorites": "daily"}}).status_code == 422)
ok("an unknown context class is refused", client.patch(
    f"{V2}/settings", json={"context_classes": {"raw_transcripts": True}}).status_code == 422)

# ── 6. refresh lifecycle + SSE ───────────────────────────────────────────────────────
class Quiet(base.Adapter):
    name = "quiet"

    def _collect(self) -> base.Payload:
        return base.Payload()


refresh._TAB_SOURCES = {"home": (Quiet,), "trending": (Quiet,), "feed": (Quiet,)}
job = client.post(f"{V2}/refresh", json={"tab": "feed"}).json()
ok("refresh starts (or joins) and returns a job id", job["job_id"] > 0)
state = None
for _ in range(50):
    state = client.get(f"{V2}/refresh/{job['job_id']}").json()
    if state["state"] in ("completed", "partial", "failed"):
        break
    time.sleep(0.1)
ok("the background job reaches a terminal state", state is not None and state["state"] == "completed",
   str(state and state["state"]))
ok("refreshing favorites is refused", client.post(f"{V2}/refresh", json={"tab": "favorites"}).status_code == 422)
ok("canceling a terminal job is a 409", client.post(
    f"{V2}/refresh/{job['job_id']}/commands", json={"command": "cancel"}).status_code == 409)
ok("unknown job is a 404", client.get(f"{V2}/refresh/999999").status_code == 404)
stream = client.get(f"{V2}/refresh/{job['job_id']}/stream")
ok("SSE stream emits ordered job events and closes on terminal state",
   stream.status_code == 200 and "event: job" in stream.text and '"sequence": 1' in stream.text)

# ── 7. media safety ──────────────────────────────────────────────────────────────────
ok("unknown media key is a 404", client.get(f"{V2}/media/nope.png").status_code == 404)
ok("malformed media key is a 422", client.get(f"{V2}/media/bad%20key%21").status_code == 422)

# ── 8. legacy rollback parity ────────────────────────────────────────────────────────
legacy = [r.path for r in app.routes if getattr(r, "path", "").startswith("/api/explore")
          and not r.path.startswith("/api/explore/v2")]
ok("legacy /api/explore/* routes remain registered for rollback", len(legacy) >= 3, str(len(legacy)))

owner_flags.set_bool(owner_flags.NEWS_V2_SHADOW, False)
ok("closing the flag re-seals the surface", client.get(f"{V2}/home").status_code == 503)

print(f"\nALL {PASS} CHECKS PASSED")

"""News V2 N03 (#23): durable refresh jobs — leases, checkpoints, restart recovery.

Isolated temp DB, stubbed adapters (no network). Proves the N03 acceptance gate —
restart-safe with NO overlap and NO duplicated work — plus join-not-duplicate,
partial success with evidence retained, retry-only-failed, cancel (idle and mid-run),
owner schedules, and the fail-closed shadow/enabled scheduler gate.
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

TMP = Path(tempfile.mkdtemp(prefix="tobi_news_ref_"))
os.environ["DB_PATH"] = str(TMP / "agent.db")

from core.database import init_database, get_connection  # noqa: E402

init_database()

from core import owner_flags  # noqa: E402
from core.news import contracts as CT  # noqa: E402
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


def make_ok(adapter_name: str):
    class _Ok(base.Adapter):
        name = adapter_name
        calls = 0

        def _collect(self) -> base.Payload:
            type(self).calls += 1
            n = type(self).calls
            return base.Payload(records=[CT.SourceRecord(
                source=adapter_name, external_id=f"{adapter_name}-{n}",
                url=f"https://{adapter_name}.io/{n}", title=f"{adapter_name} item {n}",
                item_type=CT.ItemType.ARTICLE, trust=CT.TrustClass.AGGREGATOR,
                observed_at=NOW.isoformat(), engagement=n)])
    return _Ok


class Flaky(base.Adapter):
    name = "flaky"
    max_attempts = 1
    retry_wait_s = 0.0
    calls = 0
    fail = True

    def _collect(self) -> base.Payload:
        type(self).calls += 1
        if type(self).fail:
            raise RuntimeError("api down token=sekret123")
        return base.Payload(records=[CT.SourceRecord(
            source="flaky", external_id="f-1", url="https://flaky.io/1", title="flaky item",
            item_type=CT.ItemType.ARTICLE, trust=CT.TrustClass.AGGREGATOR,
            observed_at=NOW.isoformat())])


OkFeed = make_ok("ok_feed")
OkHome = make_ok("ok_home")
OkTrendA = make_ok("ok_trend_a")
OkTrendB = make_ok("ok_trend_b")
refresh._TAB_SOURCES = {"feed": (OkFeed, Flaky), "home": (OkHome,), "trending": (OkTrendA, OkTrendB)}

# ── A. start / join (one lease per tab — never a duplicate job) ──────────────────────
req = refresh.request_refresh("feed")
JOB1 = req["job_id"]
ok("request creates a pending job with per-source checkpoints", not req["joined"]
   and refresh.get_job(JOB1)["checkpoints"] == {"ok_feed": {"state": "pending", "fetched": 0},
                                                "flaky": {"state": "pending", "fetched": 0}})
again = refresh.request_refresh("feed")
conn = get_connection()
feed_jobs = conn.execute("SELECT COUNT(*) FROM news_refresh_jobs WHERE tab='feed'").fetchone()[0]
conn.close()
ok("a second request JOINS the active job", again == {"job_id": JOB1, "joined": True, "resumed": False}
   and feed_jobs == 1)
try:
    refresh.request_refresh("favorites")
    ok("favorites refresh refused", False)
except ValueError:
    ok("favorites refresh refused", True)

# ── B. partial success: failed source degrades, evidence retained ────────────────────
job = refresh.run_job(JOB1)
ok("one failed source → PARTIAL, not a failed tab", job["state"] == "partial"
   and job["checkpoints"]["ok_feed"]["state"] == "ok"
   and job["checkpoints"]["flaky"]["state"] == "failed", job["state"])
ok("checkpoint errors are redacted", "sekret123" not in json.dumps(job["checkpoints"]))
ok("job error names the failed source; lease released; attempts counted",
   job["error"] == "failed sources: flaky" and job["lease_owner"] is None and job["attempts"] == 1)
conn = get_connection()
evidence = conn.execute("SELECT COUNT(*) FROM news_item_sources WHERE source='ok_feed'").fetchone()[0]
conn.close()
ok("the successful source's evidence is in the store", evidence == 1 and job["metrics"]["items_new"] == 1)

# ── C. retry re-runs ONLY the failed source ──────────────────────────────────────────
Flaky.fail = False
reopened = refresh.retry_failed(JOB1)
ok("retry keeps the proven checkpoint and reopens the failed one",
   reopened["state"] == "pending" and reopened["checkpoints"]["ok_feed"]["state"] == "ok"
   and reopened["checkpoints"]["flaky"]["state"] == "pending")
calls_before = OkFeed.calls
job = refresh.run_job(JOB1)
ok("resume never re-fetches proven work (no duplication)", job["state"] == "completed"
   and OkFeed.calls == calls_before and Flaky.calls == 2)
try:
    refresh.retry_failed(JOB1)
    ok("retry of a completed job refused", False)
except ValueError:
    ok("retry of a completed job refused", True)

# ── D. lease exclusivity: a valid foreign lease blocks execution ─────────────────────
JOB2 = refresh.request_refresh("home")["job_id"]
future = (NOW + timedelta(seconds=600)).isoformat()
conn = get_connection()
conn.execute("UPDATE news_refresh_jobs SET state='running', lease_owner='other-process',"
             " lease_until=? WHERE id=?", (future, JOB2))
conn.commit(); conn.close()
res = refresh.run_job(JOB2, owner="me")
ok("a live foreign lease is respected — no overlap, no work", res["state"] == "running"
   and res["lease_owner"] == "other-process" and OkHome.calls == 0)

# ── E. restart recovery: expired lease resumes from checkpoints ──────────────────────
past = (NOW - timedelta(seconds=60)).isoformat()
conn = get_connection()
conn.execute("UPDATE news_refresh_jobs SET lease_until=? WHERE id=?", (past, JOB2))
conn.commit(); conn.close()
ok("reconcile frees crashed-owner jobs back to pending", refresh.reconcile() == {"resumed": 1}
   and refresh.get_job(JOB2)["state"] == "pending" and refresh.get_job(JOB2)["lease_owner"] is None)
ok("the resumed job then completes", refresh.run_job(JOB2)["state"] == "completed" and OkHome.calls == 1)

JOB3 = refresh.request_refresh("trending")["job_id"]
conn = get_connection()
cps = {"ok_trend_a": {"state": "ok", "fetched": 1}, "ok_trend_b": {"state": "pending", "fetched": 0}}
conn.execute("UPDATE news_refresh_jobs SET state='running', lease_owner='crashed', lease_until=?,"
             " checkpoints_json=? WHERE id=?", (past, json.dumps(cps), JOB3))
conn.commit(); conn.close()
resumed = refresh.request_refresh("trending")
ok("a crashed running job is RESUMED by the next request, not duplicated",
   resumed == {"job_id": JOB3, "joined": False, "resumed": True})
job = refresh.run_job(JOB3)
ok("resume skips the source that finished before the crash", job["state"] == "completed"
   and OkTrendA.calls == 0 and OkTrendB.calls == 1, str((OkTrendA.calls, OkTrendB.calls)))

# ── F. cancel: idle and mid-run ──────────────────────────────────────────────────────
JOB4 = refresh.request_refresh("feed")["job_id"]        # feed's previous job is terminal
canceled = refresh.cancel_job(JOB4)
feed_calls = OkFeed.calls
ok("pending job cancels; runner then refuses it", canceled["state"] == "canceled"
   and refresh.run_job(JOB4)["state"] == "canceled" and OkFeed.calls == feed_calls)
try:
    refresh.cancel_job(JOB4)
    ok("double cancel refused", False)
except ValueError:
    ok("double cancel refused", True)


class CancelsItself(base.Adapter):
    name = "cancels_itself"
    job_id = 0

    def _collect(self) -> base.Payload:
        refresh.cancel_job(type(self).job_id)
        return base.Payload()


OkAfter = make_ok("ok_after")
refresh._TAB_SOURCES["trending"] = (CancelsItself, OkAfter)
JOB5 = refresh.request_refresh("trending")["job_id"]
CancelsItself.job_id = JOB5
job = refresh.run_job(JOB5)
ok("mid-run cancel stops before the next source", job["state"] == "canceled" and OkAfter.calls == 0)

# ── G. owner schedules (daily/weekly/monthly; manual never due) ──────────────────────
ok("freshly refreshed tabs are not due", refresh.due_tabs() == [], str(refresh.due_tabs()))
stale = (NOW - timedelta(days=2)).isoformat()
conn = get_connection()
conn.execute("UPDATE news_refresh_jobs SET updated_at=? WHERE tab='home' AND state='completed'", (stale,))
conn.commit(); conn.close()
ok("a tab past its daily interval comes due", refresh.due_tabs() == ["home"])
conn = get_connection()
repository.set_settings(conn, CT.NewsSettings(schedules={"home": "manual", "trending": "daily", "feed": "daily"}))
conn.commit(); conn.close()
ok("manual schedule never comes due", refresh.due_tabs() == [])
conn = get_connection()
repository.set_settings(conn, CT.NewsSettings(schedules={"home": "daily", "trending": "daily", "feed": "daily"}))
conn.commit(); conn.close()
outcome = refresh.run_due()
ok("run_due refreshes exactly the due tabs", outcome == {"home": "completed"} and refresh.due_tabs() == [])

# ── H. scheduler entries are fail-closed behind the flags ────────────────────────────
ok("flags off → scheduled refresh is a no-op", refresh.job_scheduled() is None
   and refresh.retention_scheduled() is None)
owner_flags.set_bool(owner_flags.NEWS_V2_SHADOW, True)
ok("shadow on → scheduled refresh runs (nothing due right now)", refresh.job_scheduled() == {})
ok("shadow on → retention runs", isinstance(refresh.retention_scheduled(), dict))
owner_flags.set_bool(owner_flags.NEWS_V2_SHADOW, False)

print(f"\nALL {PASS} CHECKS PASSED")

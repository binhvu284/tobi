"""News V2 durable refresh engine (#23, N03) — jobs, leases, checkpoints, schedules.

One active lease per tab: later requests JOIN the running job instead of duplicating
work (plan §9). Every source commits its own checkpoint, so a crashed process resumes
exactly where it stopped — sources already ``ok`` are never re-fetched (restart-safe,
no duplication: the N03 acceptance gate). A failed source degrades the job to
``partial``; ``retry_failed`` re-runs only the failed sources. Scheduled runs are
fail-closed: they no-op unless ``news.v2_enabled`` or ``news.v2_shadow`` is on.
"""
from __future__ import annotations

import json
import os
import socket
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone

from core.news.contracts import REFRESHABLE_TABS, Schedule, Tab
from core.news.sources.github_trending import GitHubTrendingAdapter
from core.news.sources.hackernews import HackerNewsAdapter
from core.news.sources.openrouter import OpenRouterAdapter
from core.news.sources.rss import RSSAdapter

LEASE_TTL_S = 300
_INTERVALS = {Schedule.DAILY.value: timedelta(days=1),
              Schedule.WEEKLY.value: timedelta(days=7),
              Schedule.MONTHLY.value: timedelta(days=30)}

# Tab → adapter classes. HN serves feed articles AND trending tool candidates; the
# normalizer's canonical ingest dedupes overlap. Tests patch this registry.
_TAB_SOURCES: dict = {
    Tab.HOME.value: (OpenRouterAdapter,),
    Tab.TRENDING.value: (GitHubTrendingAdapter, HackerNewsAdapter),
    Tab.FEED.value: (HackerNewsAdapter, RSSAdapter),
}


def _adapters_for(tab: str, conn: sqlite3.Connection | None = None) -> list:
    """Adapters for a tab, honoring the owner's enabled-sources setting: an empty
    ``enabled_sources`` means all sources on (the default); otherwise only listed
    sources run. Disabled sources never enter a job's checkpoints."""
    adapters = [cls() for cls in _TAB_SOURCES.get(tab, ())]
    try:
        from core.news import repository
        own = conn is None
        conn = conn or _conn()
        try:
            enabled = repository.get_settings(conn).enabled_sources
        finally:
            if own:
                conn.close()
        if enabled:
            adapters = [a for a in adapters if a.name in enabled]
    except Exception:
        pass                                             # settings unavailable → default all-on
    return adapters


def _conn() -> sqlite3.Connection:
    from core.database import get_connection
    return get_connection()


def _now(now: datetime | None = None) -> datetime:
    return now or datetime.now(timezone.utc)


def _owner_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:6]}"


def _row(conn: sqlite3.Connection, job_id: int) -> dict:
    r = conn.execute("SELECT id, tab, state, lease_owner, lease_until, attempts, error,"
                     " checkpoints_json, metrics_json, created_at, updated_at"
                     " FROM news_refresh_jobs WHERE id=?", (job_id,)).fetchone()
    if not r:
        raise ValueError(f"unknown refresh job {job_id}")
    return {"id": r[0], "tab": r[1], "state": r[2], "lease_owner": r[3], "lease_until": r[4],
            "attempts": r[5], "error": r[6],
            "checkpoints": json.loads(r[7] or "{}"), "metrics": json.loads(r[8] or "{}"),
            "created_at": r[9], "updated_at": r[10]}


def _save_checkpoints(conn: sqlite3.Connection, job_id: int, checkpoints: dict,
                      lease_until: str | None = None) -> None:
    if lease_until is not None:
        conn.execute("UPDATE news_refresh_jobs SET checkpoints_json=?, lease_until=?, updated_at=?"
                     " WHERE id=?", (json.dumps(checkpoints), lease_until, _now().isoformat(), job_id))
    else:
        conn.execute("UPDATE news_refresh_jobs SET checkpoints_json=?, updated_at=? WHERE id=?",
                     (json.dumps(checkpoints), _now().isoformat(), job_id))


# ── start / join ─────────────────────────────────────────────────────────────────────
def request_refresh(tab: str, now: datetime | None = None) -> dict:
    """Start a durable refresh for ``tab`` — or JOIN the one already active (one lease
    per tab). A running job whose lease expired (crashed owner) is reset to pending
    with its checkpoints intact, so the next runner resumes instead of duplicating."""
    tab_v = Tab(tab).value
    if Tab(tab_v) not in REFRESHABLE_TABS:
        raise ValueError("favorites never refreshes")
    now_iso = _now(now).isoformat()
    conn = _conn()
    try:
        from core.news import repository
        repository._ensure_once(conn)
        active = conn.execute(
            "SELECT id, state, lease_until FROM news_refresh_jobs"
            " WHERE tab=? AND state IN ('pending','running') ORDER BY id DESC LIMIT 1",
            (tab_v,)).fetchone()
        if active:
            job_id, state, lease_until = int(active[0]), active[1], active[2]
            if state == "running" and (not lease_until or lease_until < now_iso):
                conn.execute("UPDATE news_refresh_jobs SET state='pending', lease_owner=NULL,"
                             " lease_until=NULL, updated_at=? WHERE id=?", (now_iso, job_id))
                conn.commit()
                return {"job_id": job_id, "joined": False, "resumed": True}
            return {"job_id": job_id, "joined": True, "resumed": False}
        checkpoints = {a.name: {"state": "pending", "fetched": 0} for a in _adapters_for(tab_v, conn)}
        cur = conn.execute(
            "INSERT INTO news_refresh_jobs (tab, state, attempts, checkpoints_json, created_at, updated_at)"
            " VALUES (?,?,0,?,?,?)", (tab_v, "pending", json.dumps(checkpoints), now_iso, now_iso))
        conn.commit()
        return {"job_id": int(cur.lastrowid), "joined": False, "resumed": False}
    finally:
        conn.close()


# ── execution ────────────────────────────────────────────────────────────────────────
def run_job(job_id: int, owner: str | None = None, now: datetime | None = None) -> dict:
    """Execute one job under an atomic lease claim. Sources checkpoint (and commit)
    one by one; ``ok`` sources are skipped on resume. Never raises for job-state
    races — it simply returns the current row (someone else owns the lease)."""
    owner = owner or _owner_id()
    conn = _conn()
    try:
        from core.news import normalizer, repository
        repository._ensure_once(conn)
        start = _now(now)
        claimed = conn.execute(
            "UPDATE news_refresh_jobs SET state='running', lease_owner=?, lease_until=?, updated_at=?"
            " WHERE id=? AND state IN ('pending','running')"
            " AND (lease_owner IS NULL OR lease_owner=? OR lease_until < ?)",
            (owner, (start + timedelta(seconds=LEASE_TTL_S)).isoformat(), start.isoformat(),
             job_id, owner, start.isoformat()))
        conn.commit()
        if claimed.rowcount == 0:
            return _row(conn, job_id)                    # terminal, canceled, or leased elsewhere

        job = _row(conn, job_id)
        checkpoints = job["checkpoints"]
        adapters = {a.name: a for a in _adapters_for(job["tab"], conn)}
        totals = dict(job["metrics"]) or {"items_new": 0, "evidence_new": 0, "evidence_updated": 0,
                                          "metrics": 0, "releases": 0, "snapshots": 0}
        for source, cp in checkpoints.items():
            if cp.get("state") == "ok":
                continue                                 # resume: proven work is never redone
            state_now = conn.execute("SELECT state FROM news_refresh_jobs WHERE id=?",
                                     (job_id,)).fetchone()
            if state_now and state_now[0] == "canceled":
                break                                    # owner canceled mid-run — stop cleanly
            adapter = adapters.get(source)
            if adapter is None:
                checkpoints[source] = {"state": "failed", "fetched": 0, "error": "adapter unavailable"}
            else:
                result = adapter.run()
                if result.ok:
                    counts = normalizer.ingest(conn, result.records)
                    ev = normalizer.ingest_model_evidence(conn, result.metrics, result.releases)
                    snaps = normalizer.ingest_github_snapshots(conn, result.github_snapshots)
                    for key, val in counts.items():
                        totals[key] = totals.get(key, 0) + val
                    totals["metrics"] += ev["metrics"]; totals["releases"] += ev["releases"]
                    totals["snapshots"] += snaps
                    checkpoints[source] = {"state": "ok",
                                           "fetched": len(result.records) + len(result.metrics)
                                           + len(result.releases), "attempts": result.attempts}
                else:
                    checkpoints[source] = {"state": "failed", "fetched": 0, "error": result.error,
                                           "rate_limited": result.rate_limited}
            _save_checkpoints(conn, job_id, checkpoints,
                              (_now() + timedelta(seconds=LEASE_TTL_S)).isoformat())
            conn.commit()                                # durable per-source resume point

        end_state_row = conn.execute("SELECT state FROM news_refresh_jobs WHERE id=?", (job_id,)).fetchone()
        if end_state_row and end_state_row[0] == "canceled":
            final = "canceled"
        else:
            states = {cp.get("state") for cp in checkpoints.values()} or {"ok"}
            final = ("completed" if states == {"ok"}
                     else "partial" if "ok" in states else "failed")
        failed = sorted(s for s, cp in checkpoints.items() if cp.get("state") == "failed")
        totals["duration_ms"] = int((_now() - start).total_seconds() * 1000)
        conn.execute(
            "UPDATE news_refresh_jobs SET state=?, attempts=attempts+1, error=?, metrics_json=?,"
            " lease_owner=NULL, lease_until=NULL, updated_at=? WHERE id=?",
            (final, (f"failed sources: {', '.join(failed)}" if failed else None),
             json.dumps(totals), _now().isoformat(), job_id))
        conn.commit()
        if final in ("completed", "partial"):
            if job["tab"] == Tab.FEED.value:
                try:  # feed-quality: recap the top stories BEFORE ranking reads them
                    from core.news import recap
                    recap.run_for_refresh(conn, now)
                except Exception:
                    pass                               # recaps degrade, never fail a refresh
            try:  # N05: precompute the tab's rank snapshots from the fresh evidence.
                from core.news import ranking
                ranking.rebuild_for_tab(conn, job["tab"], now)
                conn.commit()
            except Exception:
                pass                                   # ranking failure never fails the refresh
        if final in ("partial", "failed"):
            try:  # N12: repeated source failures raise ONE deduplicated Inbox action.
                from core.news import telemetry
                telemetry.alert_failing_sources(conn, job["tab"])
            except Exception:
                pass                                   # telemetry never breaks a refresh
        return _row(conn, job_id)
    finally:
        conn.close()


def get_job(job_id: int) -> dict:
    conn = _conn()
    try:
        return _row(conn, job_id)
    finally:
        conn.close()


def cancel_job(job_id: int) -> dict:
    """Cancel a pending/running job (a runner observes it between sources). Terminal
    jobs raise ``ValueError``."""
    conn = _conn()
    try:
        cur = conn.execute("UPDATE news_refresh_jobs SET state='canceled', lease_owner=NULL,"
                           " lease_until=NULL, updated_at=? WHERE id=? AND state IN ('pending','running')",
                           (_now().isoformat(), job_id))
        conn.commit()
        if cur.rowcount == 0:
            raise ValueError(f"job {job_id} is not cancelable")
        return _row(conn, job_id)
    finally:
        conn.close()


def retry_failed(job_id: int) -> dict:
    """Reopen a partial/failed job, resetting ONLY its failed checkpoints — succeeded
    sources stay ``ok`` and will be skipped (plan §7 refresh commands)."""
    conn = _conn()
    try:
        job = _row(conn, job_id)
        if job["state"] not in ("partial", "failed"):
            raise ValueError(f"job {job_id} has no failed sources to retry")
        checkpoints = {source: ({"state": "pending", "fetched": 0} if cp.get("state") == "failed" else cp)
                       for source, cp in job["checkpoints"].items()}
        conn.execute("UPDATE news_refresh_jobs SET state='pending', error=NULL, checkpoints_json=?,"
                     " updated_at=? WHERE id=?",
                     (json.dumps(checkpoints), _now().isoformat(), job_id))
        conn.commit()
        return _row(conn, job_id)
    finally:
        conn.close()


def reconcile(now: datetime | None = None) -> dict:
    """Restart recovery: running jobs whose lease expired (crashed process) go back to
    ``pending`` with checkpoints intact, ready to resume. Valid leases are respected."""
    now_iso = _now(now).isoformat()
    conn = _conn()
    try:
        from core.news import repository
        repository._ensure_once(conn)
        cur = conn.execute("UPDATE news_refresh_jobs SET state='pending', lease_owner=NULL,"
                           " lease_until=NULL, updated_at=? WHERE state='running'"
                           " AND (lease_until IS NULL OR lease_until < ?)", (now_iso, now_iso))
        conn.commit()
        return {"resumed": cur.rowcount}
    finally:
        conn.close()


# ── owner schedules (plan §1: per-tab Daily/Weekly/Monthly; Favorites has none) ──────
def due_tabs(now: datetime | None = None) -> list[str]:
    """Tabs whose schedule interval has elapsed since their last successful
    (completed/partial) run. ``manual`` never comes due."""
    now_dt = _now(now)
    conn = _conn()
    try:
        from core.news import repository
        settings = repository.get_settings(conn)
        due: list[str] = []
        for tab in (t.value for t in REFRESHABLE_TABS):
            interval = _INTERVALS.get(settings.schedules.get(tab, Schedule.MANUAL.value))
            if interval is None:
                continue
            last = conn.execute("SELECT MAX(updated_at) FROM news_refresh_jobs"
                                " WHERE tab=? AND state IN ('completed','partial')", (tab,)).fetchone()[0]
            if not last or last < (now_dt - interval).isoformat():
                due.append(tab)
        return due
    finally:
        conn.close()


def run_due(now: datetime | None = None) -> dict:
    """Refresh every due tab sequentially. Returns {tab: final state}."""
    outcomes: dict = {}
    for tab in due_tabs(now):
        job = request_refresh(tab, now=now)
        outcomes[tab] = run_job(job["job_id"], now=now)["state"]
    return outcomes


def _shadow_or_enabled() -> bool:
    from core import owner_flags
    return owner_flags.get_bool(owner_flags.NEWS_V2_ENABLED, False) or \
        owner_flags.get_bool(owner_flags.NEWS_V2_SHADOW, False)


def job_scheduled() -> dict | None:
    """main.py hourly entry — fail-closed: a no-op until the owner turns on
    ``news.v2_enabled`` or ``news.v2_shadow`` (rollout stage 1, plan §12)."""
    if not _shadow_or_enabled():
        return None
    reconcile()
    return run_due()


def retention_scheduled() -> dict | None:
    """main.py nightly entry — same fail-closed gate as job_scheduled."""
    if not _shadow_or_enabled():
        return None
    from core.news import repository
    return repository.run_retention()

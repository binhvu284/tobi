"""News V2 ranking (#23, N05) — versioned model/trending/feed formulas + diversity.

Everything here is DETERMINISTIC and evidence-backed: model scores carry their
per-family components, sources, and formula version; GitHub growth is computed ONLY
from persisted star snapshots (a repo without enough history says "collecting" —
current stars are never presented as growth); feed scores combine the locked §6
weights with the N04 profile and enforce the diversity constraints (≤3 consecutive
per source, ≤40% per topic). Results persist as immutable rank snapshots, so
pagination cursors stay stable while newer snapshots land. No LLM anywhere.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

from core.news.contracts import Tab
from core.news.personalization import (
    _tokens, active_profile, context_delta, immediate_adjustments, recompute_profile,
)
from core.news.repository import _ensure_once, write_rank_snapshot

MODEL_FORMULA_VERSION = "model-v1"
TRENDING_FORMULA_VERSION = "trending-v1"
FEED_FORMULA_VERSION = "feed-v1"

# Locked §6 weights.
MODEL_WEIGHTS = {"intelligence": 0.55, "coding": 0.15, "agentic": 0.10, "arena": 0.10,
                 "speed": 0.04, "cost": 0.03, "context": 0.03}
FEED_WEIGHTS = {"trust": 0.55, "affinity": 0.25, "novelty": 0.10, "engagement": 0.10}
MAX_CONSECUTIVE_SOURCE = 3
MAX_TOPIC_SHARE = 0.40
FRESH_EVIDENCE_DAYS = 30
MIN_SCORE_FAMILIES = 2
TOP_N_MODELS = 10
# N12 performance gates (plan §9): snapshots stay bounded so page reads meet the
# <300 ms cached target no matter how large the canonical store grows. The feed
# ranks the freshest FEED_CANDIDATE_CAP items; older items remain in the ledger
# (searchable, favoritable) but are not re-ranked every rebuild.
FEED_CANDIDATE_CAP = 500
TOOLS_CAP = 200

_METRIC_FAMILY = {
    "intelligence": "intelligence", "reasoning": "intelligence", "composite": "intelligence",
    "coding": "coding", "webdev": "coding", "agentic": "agentic", "elo": "arena", "arena": "arena",
    "speed": "speed", "latency": "speed",
    "price_in": "cost", "price_out": "cost", "price_blended": "cost", "context": "context",
}
_LOWER_IS_BETTER = {"price_in", "price_out", "price_blended", "latency"}
# Top-10 eligibility requires at least one CAPABILITY family: price/context/speed
# alone must never rank a model as "strong" (the day-1 auto-beta lesson).
_CAPABILITY_FAMILIES = {"intelligence", "coding", "agentic", "arena"}

TRUST_BASE = {"official": 1.0, "verified_api": 0.9, "aggregator": 0.7, "community": 0.5}


def _now(now: datetime | None) -> datetime:
    return now or datetime.now(timezone.utc)


# ── 1. Model Strength Top 10 (plan §6) ───────────────────────────────────────────────
def build_model_snapshot(conn: sqlite3.Connection, now: datetime | None = None) -> int | None:
    """Rank general-purpose models with FRESH evidence and >= 2 independent score
    families. Values are min-max normalized within (source, metric) before
    aggregation; every entry persists its components, sources, and formula version.
    Ineligible models are excluded here but stay available to the Explorer reads."""
    _ensure_once(conn)
    now_dt = _now(now)
    cutoff = (now_dt - timedelta(days=FRESH_EVIDENCE_DAYS)).isoformat()
    rows = conn.execute(
        "SELECT model_id, source, metric, value FROM news_model_metrics"
        " WHERE category='general' AND observed_at >= ? ORDER BY model_id, source, metric",
        (cutoff,)).fetchall()
    if not rows:
        return None

    # normalize within each (source, metric) group, direction-aware
    groups: dict[tuple, list[tuple[str, float]]] = {}
    for model_id, source, metric, value in rows:
        groups.setdefault((source, metric), []).append((model_id, float(value)))
    per_model: dict[str, dict] = {}
    for (source, metric), members in groups.items():
        family = _METRIC_FAMILY.get(metric)
        if family is None:
            continue
        values = [v for _m, v in members]
        lo, hi = min(values), max(values)
        for model_id, value in members:
            norm = 0.5 if hi == lo else (value - lo) / (hi - lo)
            if metric in _LOWER_IS_BETTER:
                norm = 1.0 - norm
            slot = per_model.setdefault(model_id, {"families": {}, "sources": set()})
            slot["families"].setdefault(family, []).append(norm)
            slot["sources"].add(source)

    entries = []
    for model_id in sorted(per_model):
        families = per_model[model_id]["families"]
        if len(families) < MIN_SCORE_FAMILIES:
            continue                                   # incomplete evidence → not Top-10 eligible
        if not (_CAPABILITY_FAMILIES & set(families)):
            continue                                   # cheap+big-context ≠ strong (no capability proof)
        components = {fam: round(sum(vals) / len(vals), 4) for fam, vals in sorted(families.items())}
        present = sum(MODEL_WEIGHTS[f] for f in components)
        score = round(sum(MODEL_WEIGHTS[f] * v for f, v in components.items()) / present * 100, 2)
        entries.append({
            "model_id": model_id, "score": score, "components": components,
            "families": len(components), "sources": sorted(per_model[model_id]["sources"]),
            "formula_version": MODEL_FORMULA_VERSION,
        })
    if not entries:
        return None
    entries.sort(key=lambda e: (-e["score"], e["model_id"]))
    return write_rank_snapshot(conn, "models:top", entries[:TOP_N_MODELS * 3], MODEL_FORMULA_VERSION)


# ── 2. GitHub growth from persisted history (plan §6) ────────────────────────────────
def github_trending_entries(conn: sqlite3.Connection, window: str,
                            now: datetime | None = None) -> list[dict]:
    """``week``/``month``: newest snapshot minus the nearest snapshot AT OR BEFORE the
    boundary. When the window isn't spanned yet but an EARLIER day exists, fall back
    to the earliest persisted snapshot — real measured growth over a shorter span,
    honestly labeled via ``baseline_date`` (the UI renders "since <date>"). Only a
    single snapshot day → ``collecting`` with NO growth field: current stars are
    never presented as growth. ``all``: total stars."""
    if window not in ("week", "month", "all"):
        raise ValueError(f"unknown window {window!r}")
    _ensure_once(conn)
    now_dt = _now(now)
    boundary = (now_dt - timedelta(days=7 if window == "week" else 30)).date().isoformat()
    repos = [r[0] for r in conn.execute("SELECT DISTINCT repo FROM news_github_snapshots ORDER BY repo")]
    ranked, collecting = [], []
    for repo in repos:
        latest = conn.execute("SELECT snapshot_date, stars FROM news_github_snapshots"
                              " WHERE repo=? ORDER BY snapshot_date DESC LIMIT 1", (repo,)).fetchone()
        if not latest:
            continue
        if window == "all":
            ranked.append({"repo": repo, "stars": int(latest[1]), "status": "ok"})
            continue
        base = conn.execute("SELECT snapshot_date, stars FROM news_github_snapshots"
                            " WHERE repo=? AND snapshot_date <= ? ORDER BY snapshot_date DESC LIMIT 1",
                            (repo, boundary)).fetchone()
        if base is None:                                # window not spanned → earliest real reading
            earliest = conn.execute("SELECT snapshot_date, stars FROM news_github_snapshots"
                                    " WHERE repo=? ORDER BY snapshot_date ASC LIMIT 1", (repo,)).fetchone()
            if earliest and earliest[0] < latest[0]:
                base = earliest                          # measured, shorter span — labeled below
        if base is None:
            collecting.append({"repo": repo, "stars": int(latest[1]), "status": "collecting"})
        else:
            ranked.append({"repo": repo, "stars": int(latest[1]),
                           "growth": int(latest[1]) - int(base[1]),
                           "baseline_date": base[0], "status": "ok"})
    key = (lambda e: (-e["stars"], e["repo"])) if window == "all" else (lambda e: (-e["growth"], e["repo"]))
    ranked.sort(key=key)
    collecting.sort(key=lambda e: (-e["stars"], e["repo"]))
    return ranked + collecting


def build_trending_snapshots(conn: sqlite3.Connection, now: datetime | None = None) -> dict:
    """GitHub week/month/all + tool discovery, each an immutable snapshot."""
    _ensure_once(conn)
    out = {}
    for window in ("week", "month", "all"):
        out[f"github:{window}"] = write_rank_snapshot(
            conn, f"trending:github:{window}", github_trending_entries(conn, window, now),
            TRENDING_FORMULA_VERSION)
    tools = conn.execute(
        "SELECT n.id, n.title, s.source, s.trust, MAX(s.engagement) FROM news_items n"
        " JOIN news_item_sources s ON s.item_id=n.id WHERE n.item_type='tool'"
        " GROUP BY n.id ORDER BY n.id").fetchall()
    tool_entries = [{"item_id": r[0], "title": r[1], "source": r[2], "trust": r[3],
                     "engagement": int(r[4] or 0)} for r in tools]
    tool_entries.sort(key=lambda e: (-TRUST_BASE.get(e["trust"], 0.5), -e["engagement"], e["item_id"]))
    out["tools"] = write_rank_snapshot(conn, "trending:tools", tool_entries[:TOOLS_CAP],
                                       TRENDING_FORMULA_VERSION)
    return out


# ── 3. Personalized feed (plan §6): 55/25/10/10 + diversity constraints ──────────────
def _novelty(published: str | None, first_seen: str, now_dt: datetime) -> float:
    stamp = published or first_seen
    try:
        age_h = (now_dt - datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))).total_seconds() / 3600
    except (TypeError, ValueError):
        return 0.05
    if age_h < 0:
        return 0.05                                    # future-dated claims earn nothing
    for bound, value in ((6, 1.0), (24, 0.7), (48, 0.5), (168, 0.2)):
        if age_h <= bound:
            return value
    return 0.05


def _affinity(profile: dict | None, deltas: dict, source: str, item_type: str, title: str) -> float:
    """Profile-driven affinity squashed into [0,1] (0.5 = neutral)."""
    raw = 0.0
    if profile:
        raw += float(profile["sources"].get(source, 0.0))
        raw += 0.5 * float(profile["types"].get(item_type, 0.0))
        hits = [float(profile["topics"].get(t, 0.0)) for t in _tokens(title)]
        hits = [h for h in hits if h]
        if hits:
            raw += sum(hits) / len(hits)
    raw += float(deltas.get(source, 0.0))
    return 0.5 + max(-10.0, min(10.0, raw)) / 20.0


def _apply_diversity(entries: list[dict]) -> list[dict]:
    """Greedy re-order enforcing ≤MAX_CONSECUTIVE_SOURCE per source and
    ≤MAX_TOPIC_SHARE per topic; blocked items defer, never drop. Deterministic."""
    remaining = list(entries)
    ordered: list[dict] = []
    topic_counts: dict[str, int] = {}
    while remaining:
        placed = False
        for index, cand in enumerate(remaining):
            run = 0
            for prev in reversed(ordered):
                if prev["source"] != cand["source"]:
                    break
                run += 1
            if run >= MAX_CONSECUTIVE_SOURCE:
                continue
            k = len(ordered) + 1
            quota = max(1, int(MAX_TOPIC_SHARE * k))
            if topic_counts.get(cand["topic"], 0) + 1 > quota:
                continue
            ordered.append(cand)
            topic_counts[cand["topic"]] = topic_counts.get(cand["topic"], 0) + 1
            remaining.pop(index)
            placed = True
            break
        if not placed:                                 # every candidate blocked → relax in order
            cand = remaining.pop(0)
            ordered.append(cand)
            topic_counts[cand["topic"]] = topic_counts.get(cand["topic"], 0) + 1
    return ordered


def build_feed_snapshots(conn: sqlite3.Connection, now: datetime | None = None,
                         context_scores: dict | None = None) -> dict:
    """``feed:for_you`` (scored + diversity + top-2 reasons) and ``feed:latest``
    (pure recency). Disliked items are hidden IMMEDIATELY from both — even while
    their undo window is still open. ``context_scores`` ({item_id: {class: pts}})
    is capped at ±CONTEXT_CAP and ignored on items with a direct signal."""
    from core.news import personalization, repository
    _ensure_once(conn)
    now_dt = _now(now)
    settings = repository.get_settings(conn)
    profile = active_profile(conn)
    deltas = immediate_adjustments(conn, now_dt)
    # Bounded candidate window (N12): rank the freshest FEED_CANDIDATE_CAP items so
    # rebuild cost and snapshot size stay flat as the canonical store grows.
    rows = conn.execute(
        "SELECT n.id, n.title, n.item_type, n.published_at, n.first_seen_at,"
        " COALESCE(i.reaction,'none'), COALESCE(i.favorite,0), i.note,"
        " COALESCE(n.published_at, n.first_seen_at) AS stamp, n.recap_at"
        " FROM news_items n LEFT JOIN news_interactions i ON i.item_id=n.id"
        " WHERE n.item_type IN ('article','social')"
        " ORDER BY stamp DESC, n.id DESC LIMIT ?", (FEED_CANDIDATE_CAP,)).fetchall()
    stamps: dict[int, str] = {}
    recap_at: dict[int, str] = {}
    candidates = []
    for item_id, title, item_type, published, first_seen, reaction, favorite, note, stamp, recapped in rows:
        stamps[item_id] = stamp or ""
        if recapped:
            recap_at[item_id] = recapped
        if reaction == "dislike":
            continue                                   # hidden immediately (plan §1)
        evidence = conn.execute("SELECT source, trust, engagement FROM news_item_sources"
                                " WHERE item_id=? ORDER BY engagement DESC, source", (item_id,)).fetchall()
        if not evidence:
            continue
        source, trust, engagement = evidence[0][0], evidence[0][1], int(evidence[0][2] or 0)
        components = {
            "trust": TRUST_BASE.get(trust, 0.5),
            "affinity": round(_affinity(profile, deltas, source, item_type, title), 4),
            "novelty": _novelty(published, first_seen, now_dt),
            "engagement": min(1.0, engagement / 1000.0),
        }
        score = 100.0 * sum(FEED_WEIGHTS[k] * v for k, v in components.items())
        has_direct = reaction != "none" or bool(favorite) or bool((note or "").strip())
        ctx = context_delta((context_scores or {}).get(item_id, {}), settings, has_direct)
        tokens = _tokens(title)
        candidates.append({
            "item_id": item_id, "title": title, "source": source,
            "topic": tokens[0] if tokens else source,
            "score": round(score + ctx, 2), "components": components,
            "context_points": round(ctx, 2),
            "reasons": personalization.reasons_for(conn, item_id, profile),
        })
    candidates.sort(key=lambda e: (-e["score"], e["item_id"]))
    # Feed-quality rule (owner direction): For You is the CURATED deep-dive stream —
    # only recapped stories, newest recap batch first, personalization score within a
    # batch. Until the first recap exists (LLM off / first run) it falls back to the
    # full ranked list so the page is never artificially empty. Latest always stays
    # the raw everything-by-recency firehose.
    curated = [e for e in candidates if e["item_id"] in recap_at]
    if curated:
        curated.sort(key=lambda e: (recap_at[e["item_id"]], e["score"], -e["item_id"]), reverse=True)
        for_you = curated
    else:
        for_you = _apply_diversity(candidates)
    latest = sorted(candidates, key=lambda e: (e["item_id"],))
    latest = sorted(latest, key=lambda e: stamps.get(e["item_id"], ""), reverse=True)
    return {
        "for_you": write_rank_snapshot(conn, "feed:for_you", for_you, FEED_FORMULA_VERSION),
        "latest": write_rank_snapshot(conn, "feed:latest", latest, FEED_FORMULA_VERSION),
    }


def category_leaderboards(conn: sqlite3.Connection, top_n: int = 5) -> list[dict]:
    """Per-category Top-N leaderboards for the Model Explorer overview. DATA-DRIVEN:
    every distinct ``category`` in the evidence table becomes its own board — a new
    benchmark source emitting e.g. ``coding``/``image``/``video`` categories creates
    new boards with zero code change (owner requirement). Scoring reuses the N05
    idea: min-max normalize within each (source, metric) so scales never mix, invert
    lower-is-better metrics, average per model ×100. Deterministic; never invented."""
    _ensure_once(conn)
    rows = conn.execute("SELECT category, source, metric, model_id, value, observed_at"
                        " FROM news_model_metrics").fetchall()
    by_category: dict[str, dict] = {}
    for category, source, metric, model_id, value, observed in rows:
        by_category.setdefault(category, {}).setdefault((source, metric), []).append(
            (model_id, float(value), observed))
    boards = []
    for category in sorted(by_category):
        per_model: dict[str, dict] = {}
        sources: set[str] = set()
        for (source, metric), values in by_category[category].items():
            sources.add(source)
            nums = [v for _, v, _ in values]
            lo, hi = min(nums), max(nums)
            for model_id, value, observed in values:
                norm = 0.5 if hi == lo else (value - lo) / (hi - lo)
                if metric in _LOWER_IS_BETTER:
                    norm = 1.0 - norm
                slot = per_model.setdefault(model_id, {"scores": [], "latest": observed})
                slot["scores"].append(norm)
                slot["latest"] = max(slot["latest"], observed)
        entries = [{"model_id": model_id, "score": round(100 * sum(d["scores"]) / len(d["scores"]), 1),
                    "metrics": len(d["scores"]), "observed_at": d["latest"]}
                   for model_id, d in per_model.items()]
        entries.sort(key=lambda e: (-e["score"], e["model_id"]))
        boards.append({"category": category, "sources": sorted(sources), "entries": entries[:top_n]})
    return boards


# ── 4. per-tab rebuild (called by the N03 refresh engine after ingest) ───────────────
def rebuild_for_tab(conn: sqlite3.Connection, tab: str, now: datetime | None = None) -> dict:
    """Precompute the snapshots one tab's pages read. For the feed this refreshes the
    interest profile first when interactions are newer than the active profile."""
    tab_v = Tab(tab).value
    out: dict = {}
    if tab_v == Tab.HOME.value:
        snap = build_model_snapshot(conn, now)
        if snap is not None:
            out["models:top"] = snap
    elif tab_v == Tab.TRENDING.value:
        out.update(build_trending_snapshots(conn, now))
    elif tab_v == Tab.FEED.value:
        profile = active_profile(conn)
        since = profile["computed_at"] if profile else ""
        stale = conn.execute("SELECT 1 FROM news_interaction_events WHERE created_at > ? LIMIT 1",
                             (since,)).fetchone()
        if stale or profile is None:
            recompute_profile(conn, now)
        out.update(build_feed_snapshots(conn, now))
    return out

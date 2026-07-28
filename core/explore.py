"""
Explore → News (#9) — TOBI-conducted AI news/models/tools/social page.

A standalone ingestion + ranking engine (not the full Office mission engine):
  fetch → dedupe → summarize → score → store, logged to ``llm_usage`` and
  respecting a low monthly token budget (D21 guard pattern).

Four pillars:
  - ``models``  — frontier-model leaderboard with a blended composite strength
                  score (intelligence + Elo + popularity); new models surface
                  the day they ship via the OpenRouter live list.
  - ``tools``   — trending AI tools (HN + Product Hunt + GitHub + newsletters/X).
  - ``social``  — ranked "for you" feed (Reddit + Tavily + X opt-in).
  - ``news``    — shared AI-headlines backbone (NewsData.io + GDELT + RSS + GNews).

All keys are read from ``os.environ`` (injected by the Genesis vault #4 on
unlock) — never committed, never logged. Fetchers degrade to ``[]`` when a key
is absent or the network fails, so the page always renders.
"""
from __future__ import annotations

import json
import os
import re
import time
import sqlite3
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Callable, Optional

from core.env_utils import safe_load_dotenv
safe_load_dotenv()

_PILLARS = ("models", "tools", "social", "news")
_SURFACE = "explore"  # llm_usage tag


# ════════════════════════════════════════════════════════════════════════════
# Schema
# ════════════════════════════════════════════════════════════════════════════
def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS explore_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pillar TEXT NOT NULL,
            name TEXT NOT NULL,
            kind TEXT NOT NULL,
            enabled INTEGER DEFAULT 1,
            weight REAL DEFAULT 1.0,
            config_json TEXT,
            status TEXT,
            last_scan_at TEXT,
            UNIQUE(pillar, name)
        );
        CREATE TABLE IF NOT EXISTS explore_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pillar TEXT NOT NULL,
            source_name TEXT NOT NULL,
            ext_id TEXT NOT NULL,
            title TEXT,
            url TEXT,
            summary TEXT,
            tobi_take TEXT,
            raw_json TEXT,
            score REAL DEFAULT 0,
            engagement INTEGER DEFAULT 0,
            published_at TEXT,
            first_seen_at TEXT,
            freshness TEXT,
            ts TEXT,
            UNIQUE(pillar, ext_id)
        );
        CREATE INDEX IF NOT EXISTS idx_explore_items_pillar ON explore_items(pillar, score DESC);
        CREATE TABLE IF NOT EXISTS explore_models (
            model_id TEXT PRIMARY KEY,
            provider TEXT, owner TEXT,
            intelligence REAL, elo REAL, popularity REAL,
            price_in REAL, price_out REAL, speed REAL, latency REAL,
            context INTEGER, released_at TEXT,
            composite REAL, updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS explore_config (
            key TEXT PRIMARY KEY, value_json TEXT
        );
        """
    )
    _seed_defaults(conn)
    _seed_sources(conn)   # boot-only: seed the source catalog once


# Schema is created at boot by ``init_database``; to stay safe when the module
# is imported directly (tests, ad-hoc), we run ``ensure_schema`` at most once per
# process. Repeatedly seeding defaults/sources on every read would acquire a
# write lock on the hot path and conflict with the live server ("database is
# locked").
_SCHEMA_READY = False


def _ensure_once() -> None:
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    from core.database import get_connection
    conn = get_connection()
    try:
        # Read-only existence check first — after boot the tables already exist
        # (created by init_database), so we never acquire a write lock on the hot
        # path. Only create+seed if genuinely missing.
        exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='explore_config'"
        ).fetchone()
        if not exists:
            ensure_schema(conn)
            conn.commit()
        _SCHEMA_READY = True
    finally:
        conn.close()


# ── algorithm knobs (explore_config) ────────────────────────────────────────
_DEFAULT_CONFIG: dict = {
    # model composite weights (sum to 1)
    "model_weights": {"intelligence": 0.5, "elo": 0.3, "popularity": 0.2},
    # social/tools ranking
    "source_weights": {  # per-source boost; missing → 1.0
        "hackernews": 1.0, "producthunt": 0.9, "github": 1.1,
        "reddit": 1.0, "tavily": 0.8, "x": 0.7,
        "newsdata": 1.0, "gdelt": 0.9, "rss": 0.9, "gnews": 0.9,
    },
    "recency_vs_engagement": 0.5,   # 0 = pure engagement, 1 = pure recency
    "keyword_include": [],           # boost these topics
    "keyword_exclude": [],           # mute these topics
    "interest_prompt": "",           # NL "is this interesting to me" (seeds from Brain)
    "muted_categories": [],          # tools tab category mute
    # X opt-in (pay-per-use) — off until explicitly enabled with a cap
    "x_enabled": False,
    "x_cap_usd": 0.0,
    # reddit seed subs
    "reddit_subs": ["LocalLLaMA", "singularity", "MachineLearning", "OpenAI", "ArtificialIntelligence"],
    # budget guard (D21) — monthly USD cap for this engine's LLM calls
    "monthly_budget_usd": 5.0,
}


def _seed_defaults(conn: sqlite3.Connection) -> None:
    for k, v in _DEFAULT_CONFIG.items():
        conn.execute(
            "INSERT OR IGNORE INTO explore_config (key, value_json) VALUES (?, ?)",
            (k, json.dumps(v)),
        )


def load_config() -> dict:
    _ensure_once()
    from core.database import get_connection
    conn = get_connection()
    try:
        cfg = {k: v for k, v in _DEFAULT_CONFIG.items()}
        for key, val in conn.execute("SELECT key, value_json FROM explore_config").fetchall():
            try:
                cfg[key] = json.loads(val)
            except Exception:
                pass
        return cfg
    finally:
        conn.close()


def save_config(updates: dict) -> dict:
    _ensure_once()
    from core.database import get_connection
    conn = get_connection()
    try:
        for k, v in (updates or {}).items():
            conn.execute(
                "INSERT INTO explore_config (key, value_json) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json",
                (k, json.dumps(v)),
            )
        conn.commit()
    finally:
        conn.close()
    return load_config()


# ════════════════════════════════════════════════════════════════════════════
# Source catalog
# ════════════════════════════════════════════════════════════════════════════
# Each source: pillar, name, kind, key_envs (any present → usable), fetch fn.
# Fetchers return a list of normalized raw dicts:
#   {ext_id, title, url, summary?, raw?, engagement?, published_at?, category?}
RawItem = dict
FetchFn = Callable[[], "list[RawItem]"]


def _http_get(url: str, headers: dict | None = None, params: dict | None = None, timeout: int = 12):
    import requests
    return requests.get(url, headers=headers or {}, params=params or {}, timeout=timeout)


def _http_post(url: str, headers: dict | None = None, json_body=None, timeout: int = 12):
    import requests
    return requests.post(url, headers=headers or {}, json=json_body, timeout=timeout)


def _iso(ts: str | int | float | None) -> str | None:
    if not ts:
        return None
    try:
        if isinstance(ts, (int, float)):
            return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
        return str(ts)
    except Exception:
        return None


# ── News backbone sources ───────────────────────────────────────────────────
def _f_newsdata() -> list[RawItem]:
    k = os.getenv("NEWSDATA_API_KEY")
    if not k:
        return []
    r = _http_get("https://newsdata.io/api/1/news",
                  params={"apikey": k, "q": "AI OR \"artificial intelligence\"", "language": "en", "size": 15})
    if r.status_code != 200:
        return []
    out = []
    for a in r.json().get("results", []):
        out.append({"ext_id": a.get("article_id") or a.get("link") or a.get("title"),
                    "title": a.get("title"), "url": a.get("link"),
                    "summary": (a.get("description") or "")[:500] or None,
                    "published_at": _iso(a.get("pubDate")),
                    "engagement": 0, "raw": a})
    return out


def _f_gnews() -> list[RawItem]:
    k = os.getenv("GNEWS_API_KEY")
    if not k:
        return []
    r = _http_get("https://gnews.io/api/v4/search",
                  params={"q": "AI", "lang": "en", "max": 15, "apikey": k})
    if r.status_code != 200:
        return []
    out = []
    for a in r.json().get("articles", []):
        out.append({"ext_id": a.get("url") or a.get("title"),
                    "title": a.get("title"), "url": a.get("url"),
                    "summary": (a.get("description") or "")[:500] or None,
                    "published_at": _iso(a.get("publishedAt")),
                    "engagement": 0, "raw": a})
    return out


def _f_gdelt() -> list[RawItem]:
    # GDELT DOC 2.0 — free, no key. ArtList format returns recent articles.
    r = _http_get("https://api.gdeltproject.org/api/v2/doc/doc",
                  params={"query": "artificial intelligence", "mode": "ArtList", "maxrecords": 15, "format": "json"})
    if r.status_code != 200:
        return []
    try:
        arts = r.json().get("articles", [])
    except Exception:
        return []
    out = []
    for a in arts:
        url = a.get("url")
        out.append({"ext_id": url or a.get("title"),
                    "title": a.get("title"), "url": url,
                    "summary": (a.get("socialimage") or "") and None,
                    "published_at": _iso(a.get("seendate")),
                    "engagement": 0, "raw": a})
    return out


def _f_rss() -> list[RawItem]:
    # A handful of high-signal AI RSS feeds (no key). xml parsing, best-effort.
    import xml.etree.ElementTree as ET
    feeds = [
        "https://techcrunch.com/category/artificial-intelligence/feed/",
        "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",
        "https://venturebeat.com/category/ai/feed/",
    ]
    out: list[RawItem] = []
    for url in feeds:
        try:
            r = _http_get(url, timeout=10)
            root = ET.fromstring(r.content)
            for item in root.iter("item"):
                title = (item.findtext("title") or "").strip()
                link = (item.findtext("link") or "").strip()
                pub = item.findtext("pubDate")
                if title and link:
                    out.append({"ext_id": link, "title": title, "url": link,
                                "summary": None, "published_at": _iso(pub),
                                "engagement": 0, "raw": {}})
        except Exception:
            continue
    return out


# ── Tools sources ───────────────────────────────────────────────────────────
def _f_hackernews() -> list[RawItem]:
    # Algolia search API — free, no key. AI-tagged Show HN + stories, last 48h.
    r = _http_get("https://hn.algolia.com/api/v1/search",
                  params={"query": "AI OR LLM OR GPT", "tags": "story", "numericFilters": "created_at_i>%d" % int(time.time() - 48 * 3600)})
    if r.status_code != 200:
        return []
    out = []
    for h in r.json().get("hits", [])[:25]:
        out.append({"ext_id": str(h.get("objectID")),
                    "title": h.get("title") or h.get("story_title") or "Untitled",
                    "url": h.get("url") or f"https://news.ycombinator.com/item?id={h.get('objectID')}",
                    "summary": (h.get("story_text") or h.get("comment_text") or "")[:400] or None,
                    "published_at": _iso(h.get("created_at_i")),
                    "engagement": int(h.get("points") or 0),
                    "category": "community", "raw": h})
    return out


def _f_producthunt() -> list[RawItem]:
    tok = os.getenv("PRODUCTHUNT_API_TOKEN")
    if not tok:
        return []
    q = """
    { posts(first: 15, topic: "artificial-intelligence", order: VOTES) {
      edges { node { id name tagline url website votesCount topics(first:3){edges{node{name}}} } } } }"""
    r = _http_post("https://api.producthunt.com/v2/api/graphql",
                   headers={"Authorization": f"Bearer {tok}"}, json_body={"query": q})
    if r.status_code != 200:
        return []
    out = []
    try:
        edges = r.json()["data"]["posts"]["edges"]
    except Exception:
        return []
    for e in edges:
        n = e.get("node", {})
        cats = [t["node"]["name"] for t in (n.get("topics", {}).get("edges", []))]
        out.append({"ext_id": n.get("id"), "title": n.get("name"), "url": n.get("url"),
                    "summary": n.get("tagline"), "engagement": int(n.get("votesCount") or 0),
                    "category": ",".join(cats) or "product", "raw": n})
    return out


def _f_github_trending() -> list[RawItem]:
    # GitHub trending has no official API — approximate via search: recently-created
    # repos with fast star growth (existing GITHUB_TOKEN raises rate limit).
    tok = os.getenv("GITHUB_TOKEN")
    headers = {"Accept": "application/vnd.github+json"}
    if tok:
        headers["Authorization"] = f"Bearer {tok}"
    created = (datetime.now(timezone.utc) - timedelta(days=14)).strftime("%Y-%m-%d")
    r = _http_get("https://api.github.com/search/repositories",
                  headers=headers,
                  params={"q": f"AI LLM created:>{created} stars:>50", "sort": "stars", "order": "desc", "per_page": 20})
    if r.status_code != 200:
        return []
    out = []
    for repo in r.json().get("items", []):
        out.append({"ext_id": str(repo.get("id")),
                    "title": repo.get("full_name"), "url": repo.get("html_url"),
                    "summary": (repo.get("description") or "")[:300] or None,
                    "engagement": int(repo.get("stargazers_count") or 0),
                    "category": "code", "raw": repo})
    return out


# ── Social sources ──────────────────────────────────────────────────────────
def _f_reddit(subs: list[str]) -> list[RawItem]:
    # Public JSON — no OAuth needed for read of public hot posts (.json endpoint).
    out: list[RawItem] = []
    headers = {"User-Agent": "tobi-explore/1.0"}
    for sub in subs[:6]:
        try:
            r = _http_get(f"https://www.reddit.com/r/{sub}/hot.json", headers=headers, params={"limit": 8})
            if r.status_code != 200:
                continue
            for child in r.json().get("data", {}).get("children", []):
                d = child.get("data", {})
                out.append({"ext_id": d.get("id"), "title": d.get("title"),
                            "url": f"https://reddit.com{d.get('permalink', '')}",
                            "summary": (d.get("selftext") or "")[:400] or None,
                            "published_at": _iso(d.get("created_utc")),
                            "engagement": int(d.get("score") or 0),
                            "category": sub, "raw": {"sub": sub, "score": d.get("score"), "comments": d.get("num_comments")}})
        except Exception:
            continue
    return out


def _f_tavily() -> list[RawItem]:
    k = os.getenv("TAVILY_API_KEY")
    if not k:
        return []
    r = _http_post("https://api.tavily.com/search",
                   json_body={"api_key": k, "query": "AI news trending today", "max_results": 12, "topic": "news"})
    if r.status_code != 200:
        return []
    out = []
    for a in r.json().get("results", []):
        out.append({"ext_id": a.get("url") or a.get("title"), "title": a.get("title"),
                    "url": a.get("url"), "summary": (a.get("content") or "")[:400] or None,
                    "engagement": 0, "category": "web", "raw": a})
    return out


def _f_x() -> list[RawItem]:
    # OFF until opt-in (pay-per-use). Cap is enforced per-refresh.
    cfg = load_config()
    if not cfg.get("x_enabled"):
        return []
    tok = os.getenv("X_BEARER_TOKEN")
    if not tok:
        return []
    r = _http_get("https://api.twitter.com/2/tweets/search/recent",
                  headers={"Authorization": f"Bearer {tok}"},
                  params={"query": "(AI OR LLM) -is:retweet lang:en", "max_results": 20,
                          "tweet.fields": "public_metrics,created_at"})
    if r.status_code != 200:
        return []
    out = []
    for t in r.json().get("data", []):
        m = t.get("public_metrics", {})
        eng = int(m.get("like_count", 0)) + int(m.get("retweet_count", 0))
        out.append({"ext_id": t.get("id"), "title": (t.get("text") or "")[:120],
                    "url": f"https://x.com/i/web/status/{t.get('id')}",
                    "summary": t.get("text"), "published_at": _iso(t.get("created_at")),
                    "engagement": eng, "category": "x", "raw": t})
    return out


# ── Model sources ───────────────────────────────────────────────────────────
def _f_openrouter_models() -> list[dict]:
    """The live new-model spine. Public list, no key required; key raises detail."""
    headers = {}
    k = os.getenv("OPENROUTER_API_KEY")
    if k:
        headers["Authorization"] = f"Bearer {k}"
    r = _http_get("https://openrouter.ai/api/v1/models", headers=headers)
    if r.status_code != 200:
        return []
    return r.json().get("data", [])


# ── source registry ─────────────────────────────────────────────────────────
def _source_defs() -> list[dict]:
    """Static descriptor per source — used to seed explore_sources + dispatch fetch."""
    return [
        {"pillar": "news", "name": "newsdata", "kind": "api", "key_envs": ["NEWSDATA_API_KEY"]},
        {"pillar": "news", "name": "gnews", "kind": "api", "key_envs": ["GNEWS_API_KEY"]},
        {"pillar": "news", "name": "gdelt", "kind": "api", "key_envs": []},
        {"pillar": "news", "name": "rss", "kind": "rss", "key_envs": []},
        {"pillar": "tools", "name": "hackernews", "kind": "api", "key_envs": []},
        {"pillar": "tools", "name": "producthunt", "kind": "api", "key_envs": ["PRODUCTHUNT_API_TOKEN"]},
        {"pillar": "tools", "name": "github", "kind": "api", "key_envs": ["GITHUB_TOKEN"]},
        {"pillar": "social", "name": "reddit", "kind": "api", "key_envs": []},
        {"pillar": "social", "name": "tavily", "kind": "api", "key_envs": ["TAVILY_API_KEY"]},
        {"pillar": "social", "name": "x", "kind": "api", "key_envs": ["X_BEARER_TOKEN"]},
    ]


def _seed_sources(conn: sqlite3.Connection) -> None:
    for s in _source_defs():
        conn.execute(
            "INSERT OR IGNORE INTO explore_sources (pillar, name, kind, weight) VALUES (?, ?, ?, 1.0)",
            (s["pillar"], s["name"], s["kind"]),
        )


def _source_status(name: str) -> str:
    """Usable right now? key-aware + opt-in-aware."""
    s = next((x for x in _source_defs() if x["name"] == name), None)
    if not s:
        return "unknown"
    if name == "x":
        if not load_config().get("x_enabled"):
            return "opt_in_required"
    if not s["key_envs"]:
        return "ready"
    return "ready" if any(os.getenv(k) for k in s["key_envs"]) else "needs_key"


def _sources_view() -> list[dict]:
    _ensure_once()
    from core.database import get_connection
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM explore_sources ORDER BY pillar, name").fetchall()
        cols = [c[0] for c in conn.execute("SELECT * FROM explore_sources LIMIT 1").description]
        out = []
        for r in rows:
            d = dict(zip(cols, r))
            d["enabled"] = bool(d["enabled"])
            d["status"] = _source_status(d["name"])
            out.append(d)
        return out
    finally:
        conn.close()


def set_source_enabled(name: str, enabled: bool) -> None:
    _ensure_once()
    from core.database import get_connection
    conn = get_connection()
    try:
        conn.execute("UPDATE explore_sources SET enabled=? WHERE name=?", (1 if enabled else 0, name))
        conn.commit()
    finally:
        conn.close()


def set_source_weight(name: str, weight: float) -> None:
    _ensure_once()
    from core.database import get_connection
    conn = get_connection()
    try:
        conn.execute("UPDATE explore_sources SET weight=? WHERE name=?", (float(weight), name))
        conn.commit()
    finally:
        conn.close()


# ════════════════════════════════════════════════════════════════════════════
# Fetch dispatch
# ════════════════════════════════════════════════════════════════════════════
def _fetch_source(name: str) -> list[RawItem]:
    try:
        if name == "newsdata":
            return _f_newsdata()
        if name == "gnews":
            return _f_gnews()
        if name == "gdelt":
            return _f_gdelt()
        if name == "rss":
            return _f_rss()
        if name == "hackernews":
            return _f_hackernews()
        if name == "producthunt":
            return _f_producthunt()
        if name == "github":
            return _f_github_trending()
        if name == "reddit":
            return _f_reddit(load_config().get("reddit_subs", []))
        if name == "tavily":
            return _f_tavily()
        if name == "x":
            return _f_x()
    except Exception:
        return []
    return []


# ════════════════════════════════════════════════════════════════════════════
# Budget guard (D21)
# ════════════════════════════════════════════════════════════════════════════
def _month_spend_usd() -> float:
    """Approximate USD spent by this engine in the current calendar month."""
    try:
        from core import usage
        from core.database import get_connection
        conn = get_connection()
        try:
            since = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
            row = conn.execute(
                "SELECT COALESCE(SUM(cost_est), 0) FROM llm_usage WHERE surface=? AND COALESCE(ts, created_at) >= ?",
                (_SURFACE, since),
            ).fetchone()
            return float(row[0]) if row else 0.0
        finally:
            conn.close()
    except Exception:
        return 0.0


def _budget_ok() -> tuple[bool, float, float]:
    cfg = load_config()
    cap = float(cfg.get("monthly_budget_usd", 5.0) or 0)
    spent = _month_spend_usd()
    return (spent < cap, spent, cap)


# ════════════════════════════════════════════════════════════════════════════
# Summarize + score
# ════════════════════════════════════════════════════════════════════════════
def _summarize_iter(items: list[RawItem], pillar: str):
    """Bulk-summarize items that have no summary yet (Haiku-equivalent). Mutates in
    place. **Generator** — yields ``{"done": i, "total": n, "title": ...}`` after
    each item so callers (the SSE scout stream) can report per-item progress.
    Honours the monthly budget — stops summarizing once over cap."""
    todo = [it for it in items if not it.get("summary")]
    total = len(todo)
    if total == 0:
        return
    ok, _spent, _cap = _budget_ok()
    if not ok:
        yield {"done": 0, "total": total, "title": "", "skipped": "budget"}
        return
    try:
        from core.model_router import restore_usage_context, set_usage_context, get_llm
    except Exception:
        return
    prev = set_usage_context(
        _SURFACE, f"{pillar}_summarize", purpose="explore",
        source="explore", agent_id="tobi-explore",
    )
    try:
        client = get_llm("simple")
    except Exception:
        restore_usage_context(prev)
        return
    sys = ("You are TOBI, an AI-news editor. Write ONE concise neutral sentence (<= 30 words) "
           "summarizing the item for a busy founder. No hype, no first person. English.")
    done = 0
    for it in todo:
        body = it.get("title", "")
        if it.get("raw"):
            body += "\n" + json.dumps(it["raw"], ensure_ascii=False)[:600]
        if body.strip():
            try:
                text = client.complete([{"role": "user", "content": body[:1500]}], system=sys, max_tokens=80)
                it["summary"] = (text or "").strip()[:400]
            except Exception:
                pass
        done += 1
        yield {"done": done, "total": total, "title": (it.get("title") or "")[:60]}
        ok, _s, _c = _budget_ok()
        if not ok:
            break
    restore_usage_context(prev)


def _summarize(items: list[RawItem], pillar: str) -> None:
    """Sync wrapper around the generator (for callers that don't care about progress)."""
    for _ in _summarize_iter(items, pillar):
        pass


def _keyword_factor(text: str, cfg: dict) -> float:
    t = (text or "").lower()
    inc = [k.lower() for k in cfg.get("keyword_include", []) if k]
    exc = [k.lower() for k in cfg.get("keyword_exclude", []) if k]
    f = 1.0
    for k in exc:
        if k and k in t:
            return 0.0  # mute
    for k in inc:
        if k and k in t:
            f *= 1.4
    return f


def _recency_factor(published_at: str | None, knob: float) -> float:
    """0..1 — newer items score higher; ``knob`` (recency_vs_engagement) weights it."""
    if not published_at:
        return 0.5
    try:
        # tolerate ISO or epoch-ish strings
        ts = published_at
        if ts.isdigit():
            dt = datetime.fromtimestamp(float(ts), tz=timezone.utc)
        else:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return 0.5
    age_h = max(0.0, (datetime.now(timezone.utc) - dt).total_seconds() / 3600)
    decay = 0.5 ** (age_h / 36.0)   # halve every 36h
    return decay


def _score(it: RawItem, source_weight: float, cfg: dict) -> float:
    eng = max(1, int(it.get("engagement") or 0))
    # log-scale engagement → 0..1
    import math
    eng_n = math.log10(eng + 1) / max(1.0, math.log10(10000))
    rec = _recency_factor(it.get("published_at"), 0.5)
    knob = float(cfg.get("recency_vs_engagement", 0.5))
    blend = (1 - knob) * eng_n + knob * rec
    kw = _keyword_factor(it.get("title", "") + " " + (it.get("summary") or ""), cfg)
    if cfg.get("interest_prompt") and kw > 0:
        # cheap keyword proxy for the NL prompt keywords (LLM judge is a later version)
        for word in re.findall(r"[a-zA-Z]{4,}", cfg["interest_prompt"].lower()):
            if word in (it.get("title", "") + it.get("summary", "")).lower():
                kw *= 1.15
                break
    return round(source_weight * blend * kw, 4)


def _freshness(published_at: str | None, engagement: int) -> str:
    rec = _recency_factor(published_at, 0.5)
    if engagement and engagement > 200 and rec > 0.6:
        return "Hot"
    if rec > 0.8:
        return "New"
    if rec < 0.25:
        return "Cooling"
    return ""


def _dedupe(items: list[RawItem]) -> list[RawItem]:
    seen, out = set(), []
    for it in items:
        key = (it.get("ext_id") or it.get("url") or it.get("title") or "").strip().lower()
        if not key:
            key = hashlib.sha1((it.get("title") or "").encode()).hexdigest()
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


# ════════════════════════════════════════════════════════════════════════════
# Refresh orchestrator (tools / social / news)
# ════════════════════════════════════════════════════════════════════════════
def refresh_iter(pillar: str):
    """fetch → dedupe → summarize → score → store. **Generator** yielding progress
    events for the SSE scout stream::

        {"phase": "start", "pillar", "total_sources"}
        {"phase": "fetch", "source", "status": "start"|"done", "items"?}
        {"phase": "summarize", "done", "total", "title"?}
        {"phase": "score"}
        {"phase": "done", "items", "sources", "ts"}

    Connection-safe: all network/LLM work happens with NO DB connection held,
    then every write runs in one short transaction at the end.
    """
    if pillar not in ("news", "tools", "social"):
        yield {"phase": "error", "error": "bad pillar"}
        return
    _ensure_once()
    cfg = load_config()                       # quick open/close (read)
    sources = _sources_view()                 # quick open/close (read)
    now = datetime.now(timezone.utc).isoformat()
    enabled = [s for s in sources if s["pillar"] == pillar and s["enabled"] and s["status"] in ("ready", "opt_in_required")]
    yield {"phase": "start", "pillar": pillar, "total_sources": len(enabled)}

    # 1) fetch (network) — no connection held
    raw: list[RawItem] = []
    scan_stats: dict = {}
    for s in enabled:
        yield {"phase": "fetch", "source": s["name"], "status": "start"}
        items = _fetch_source(s["name"])
        scan_stats[s["name"]] = len(items)
        yield {"phase": "fetch", "source": s["name"], "status": "done", "items": len(items)}
        for it in items:
            it["source_name"] = s["name"]
            it["_weight"] = float(s.get("weight") or 1.0) * float(cfg.get("source_weights", {}).get(s["name"], 1.0))
        raw.extend(items)
    raw = _dedupe(raw)

    # 2) summarize (LLM, slow) — no connection held; stream per-item progress
    if pillar in ("tools", "social"):
        yield {"phase": "summarize", "done": 0, "total": sum(1 for r in raw if not r.get("summary"))}
        for ev in _summarize_iter(raw, pillar):
            yield ev

    # 3) score in memory
    yield {"phase": "score"}
    scored = []
    for it in raw:
        ext_id = (it.get("ext_id") or it.get("url") or it.get("title") or
                  hashlib.sha1((it.get("title") or "").encode()).hexdigest())
        it["ext_id"] = ext_id
        sc = _score(it, it.get("_weight", 1.0), cfg)
        if sc <= 0:
            continue  # muted by keyword exclude
        it["_score"] = sc
        scored.append(it)

    # 4) ONE short write transaction — open, write everything, close
    from core.database import get_connection
    conn = get_connection()
    try:
        for s in enabled:
            conn.execute(
                "UPDATE explore_sources SET status=?, last_scan_at=? WHERE name=?",
                (_source_status(s["name"]), now, s["name"]),
            )
        for it in scored:
            conn.execute(
                "INSERT INTO explore_items (pillar, source_name, ext_id, title, url, summary, raw_json, "
                "score, engagement, published_at, first_seen_at, freshness, ts) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(pillar, ext_id) DO UPDATE SET title=excluded.title, url=excluded.url, "
                "summary=COALESCE(excluded.summary, explore_items.summary), raw_json=excluded.raw_json, "
                "score=excluded.score, engagement=excluded.engagement, published_at=excluded.published_at, "
                "freshness=excluded.freshness, ts=excluded.ts",
                (pillar, it.get("source_name"), it["ext_id"], it.get("title"), it.get("url"),
                 it.get("summary"), json.dumps(it.get("raw") or {}, ensure_ascii=False),
                 it["_score"], int(it.get("engagement") or 0), it.get("published_at"), now,
                 _freshness(it.get("published_at"), int(it.get("engagement") or 0)), now),
            )
        # prune: keep top 200 per pillar
        conn.execute(
            "DELETE FROM explore_items WHERE pillar=? AND id NOT IN "
            "(SELECT id FROM explore_items WHERE pillar=? ORDER BY score DESC LIMIT 200)",
            (pillar, pillar),
        )
        conn.commit()
    finally:
        conn.close()
    yield {"phase": "done", "items": len(scored), "sources": scan_stats, "ts": now}


def refresh(pillar: str) -> dict:
    """Sync wrapper around ``refresh_iter`` — drains the generator, returns the
    final ``done`` payload (used by the scheduler + the non-stream endpoint)."""
    result = {"ok": True, "pillar": pillar, "sources": {}, "items": 0, "ts": ""}
    for ev in refresh_iter(pillar):
        if ev.get("phase") == "done":
            result.update({"sources": ev.get("sources", {}), "items": ev.get("items", 0), "ts": ev.get("ts", "")})
        elif ev.get("phase") == "error":
            return {"ok": False, "error": ev.get("error")}
    return result


# ════════════════════════════════════════════════════════════════════════════
# Models pillar — leaderboard + composite
# ════════════════════════════════════════════════════════════════════════════
_FRONTIER_HINTS = ("gpt-5", "gpt-4o", "o3", "o4", "claude-opus", "claude-sonnet",
                   "gemini-2.5", "gemini-2", "grok-4", "grok-3", "deepseek",
                   "glm-4.6", "llama-3", "llama-4", "qwen3", "mistral-large", "nova")


def _is_frontier(model_id: str) -> bool:
    name = (model_id or "").lower()
    # strip provider prefix
    if "/" in name:
        name = name.split("/", 1)[1]
    return any(h in name for h in _FRONTIER_HINTS)


def _price_per_tok(pricing: dict, key: str) -> float:
    """OpenRouter pricing {prompt, completion} are per-token USD strings."""
    try:
        return float(pricing.get(key) or 0)
    except Exception:
        return 0.0


def refresh_models_iter():
    """Rebuild the frontier leaderboard from OpenRouter's live list. **Generator**
    yielding scout events (single virtual 'openrouter' source)."""
    _ensure_once()
    cfg = load_config()
    yield {"phase": "start", "pillar": "models", "total_sources": 1}
    yield {"phase": "fetch", "source": "openrouter", "status": "start"}
    data = _f_openrouter_models()           # network — no connection held
    if not data:
        yield {"phase": "fetch", "source": "openrouter", "status": "done", "items": 0}
        yield {"phase": "error", "error": "openrouter unreachable"}
        return
    yield {"phase": "fetch", "source": "openrouter", "status": "done", "items": len(data)}
    yield {"phase": "score"}
    now = datetime.now(timezone.utc).isoformat()
    from core.database import get_connection
    conn = get_connection()
    try:
        w = cfg.get("model_weights", {})
        wi = float(w.get("intelligence", 0.5)); we = float(w.get("elo", 0.3)); wp = float(w.get("popularity", 0.2))
        wsum = wi + we + wp or 1.0
        wi, we, wp = wi / wsum, we / wsum, wp / wsum
        # popularity proxy: cheaper models on OpenRouter rank higher in usage; approximate by
        # inverse price + context. Real popularity (rankings endpoint) fills in if key present.
        prices = []
        for m in data:
            p = m.get("pricing") or {}
            pin, pout = _price_per_tok(p, "prompt"), _price_per_tok(p, "completion")
            if pin or pout:
                prices.append((pin + pout))
        # normalize price → popularity (cheaper ≈ more popular on the free/cheap tier)
        max_p = max(prices) if prices else 1.0
        kept = 0
        for m in data:
            mid = m.get("id")
            if not mid or not _is_frontier(mid):
                continue
            p = m.get("pricing") or {}
            pin, pout = _price_per_tok(p, "prompt"), _price_per_tok(p, "completion")
            ctx = int(m.get("context_length") or 0) or None
            # intelligence proxy: bigger context + known-frontier name. AA fills real scores later.
            intel = min(100.0, (ctx or 0) / 4000.0) if ctx else 40.0
            elo = None  # LMArena fill-in (later)
            price_total = pin + pout
            pop = (1.0 - (price_total / max_p)) * 100 if max_p > 0 else 50.0
            pop = max(0.0, min(100.0, pop))
            composite = wi * intel + we * 50.0 + wp * pop  # elo unknown → neutral 50
            conn.execute(
                "INSERT INTO explore_models (model_id, provider, owner, intelligence, elo, popularity, "
                "price_in, price_out, speed, latency, context, released_at, composite, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(model_id) DO UPDATE SET provider=excluded.provider, owner=excluded.owner, "
                "intelligence=excluded.intelligence, popularity=excluded.popularity, price_in=excluded.price_in, "
                "price_out=excluded.price_out, context=excluded.context, composite=excluded.composite, updated_at=excluded.updated_at",
                (mid, m.get("id", "").split("/")[0] if "/" in m.get("id", "") else None,
                 m.get("name") or mid, intel, elo, pop, pin * 1e6, pout * 1e6, None, None,
                 ctx, m.get("created"), composite, now),
            )
            kept += 1
        # prune non-frontier leftovers older than 7 days
        conn.execute(
            "DELETE FROM explore_models WHERE updated_at < ? AND model_id NOT IN "
            "(SELECT model_id FROM explore_models ORDER BY composite DESC LIMIT 80)",
            ((datetime.now(timezone.utc) - timedelta(days=7)).isoformat(),),
        )
        conn.commit()
    finally:
        conn.close()
    yield {"phase": "done", "items": kept, "sources": {"openrouter": len(data)}, "ts": now}


def refresh_models() -> dict:
    """Sync wrapper around ``refresh_models_iter``."""
    result = {"ok": True, "models": 0, "ts": ""}
    for ev in refresh_models_iter():
        if ev.get("phase") == "done":
            result.update({"models": ev.get("items", 0), "ts": ev.get("ts", "")})
        elif ev.get("phase") == "error":
            return {"ok": False, "error": ev.get("error")}
    return result


# ════════════════════════════════════════════════════════════════════════════
# Reads (for the API)
# ════════════════════════════════════════════════════════════════════════════
def _items(pillar: str, limit: int = 40) -> list[dict]:
    _ensure_once()
    from core.database import get_connection
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT pillar, source_name, ext_id, title, url, summary, tobi_take, score, "
            "engagement, published_at, first_seen_at, freshness, ts FROM explore_items "
            "WHERE pillar=? ORDER BY score DESC LIMIT ?",
            (pillar, limit),
        ).fetchall()
        cols = [c[0] for c in conn.execute("SELECT * FROM explore_items LIMIT 1").description]
        return [dict(zip(cols, r)) for r in rows]
    finally:
        conn.close()


def news_payload(limit: int = 20) -> dict:
    return {"items": _items("news", limit), "sources": [s for s in _sources_view() if s["pillar"] == "news"]}


def tools_payload(limit: int = 40) -> dict:
    return {"items": _items("tools", limit), "sources": [s for s in _sources_view() if s["pillar"] == "tools"]}


def social_payload(limit: int = 40) -> dict:
    return {"items": _items("social", limit), "sources": [s for s in _sources_view() if s["pillar"] == "social"]}


def models_payload(limit: int = 60) -> dict:
    _ensure_once()
    from core.database import get_connection
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT model_id, provider, owner, intelligence, elo, popularity, price_in, price_out, "
            "speed, latency, context, released_at, composite, updated_at FROM explore_models "
            "ORDER BY composite DESC LIMIT ?",
            (limit,),
        ).fetchall()
        cols = [c[0] for c in conn.execute("SELECT * FROM explore_models LIMIT 1").description]
        return {"models": [dict(zip(cols, r)) for r in rows], "weights": load_config().get("model_weights", {})}
    finally:
        conn.close()


# ════════════════════════════════════════════════════════════════════════════
# Conductor digest ("summarize today's news")
# ════════════════════════════════════════════════════════════════════════════
def digest(days: int = 1) -> str:
    """Editorial digest of the last N days, Opus-equivalent. Surface via #7 Conductor."""
    ok, _s, _c = _budget_ok()
    if not ok:
        return "Explore digest paused — monthly summarization budget reached."
    # gather top items across news/tools/social
    feed = (_items("news", 8) + _items("tools", 6) + _items("social", 6))
    if not feed:
        return "No Explore items yet — run a refresh first."
    try:
        from core.model_router import restore_usage_context, set_usage_context, get_llm
    except Exception:
        return "Model router unavailable."
    prev = set_usage_context(
        _SURFACE, "digest", purpose="background", source="explore",
        agent_id="tobi-explore", is_background=True,
    )
    bullets = "\n".join(f"- [{it.get('source_name')}] {it.get('title')}" for it in feed[:20])
    sys = ("You are TOBI. Write a tight daily AI brief for your owner: 3-5 short themed bullets "
           "(Models / Tools / Social as they arise), each ≤ 25 words, neutral tone, with an optional "
           "closing one-line 'TOBI's take'. English. No preamble.")
    user = f"Top Explore items from the last {days} day(s):\n{bullets}"
    try:
        client = get_llm("default")
        out = client.complete([{"role": "user", "content": user}], system=sys, max_tokens=500)
        restore_usage_context(prev)
        return (out or "").strip()
    except Exception as e:
        restore_usage_context(prev)
        return f"Digest failed: {e}"


# ════════════════════════════════════════════════════════════════════════════
# Status (for the page header)
# ════════════════════════════════════════════════════════════════════════════
def status() -> dict:
    ok, spent, cap = _budget_ok()
    srcs = _sources_view()
    last = {}
    from core.database import get_connection
    conn = get_connection()
    try:
        for p in _PILLARS:
            row = conn.execute(
                "SELECT MAX(ts) FROM explore_items WHERE pillar=?", (p,)
            ).fetchone()
            last[p] = row[0] if row else None
        mrow = conn.execute("SELECT MAX(updated_at) FROM explore_models").fetchone()
        last["models"] = mrow[0] if mrow else None
    finally:
        conn.close()
    return {
        "last_scan": last,
        "budget": {"spent_usd": round(spent, 4), "cap_usd": cap, "ok": ok},
        "sources": srcs,
    }


if __name__ == "__main__":
    print("=== Explore engine ===")
    print(status())

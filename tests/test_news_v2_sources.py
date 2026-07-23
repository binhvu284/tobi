"""News V2 N02 (#23): bounded source adapters + canonical normalizer.

Isolated temp DB, stubbed HTTP (no live network). Proves the N02 acceptance gate —
one failed source yields PARTIAL success with every successful source's evidence
retained — plus record bounds, retry policy, honest rate-limit reporting, secret
redaction, per-adapter mapping honesty (nothing invented), and evidence-preserving
canonical ingest.
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

TMP = Path(tempfile.mkdtemp(prefix="tobi_news_src_"))
os.environ["DB_PATH"] = str(TMP / "agent.db")
os.environ.pop("GITHUB_TOKEN", None)

from core.database import init_database, get_connection  # noqa: E402

init_database()

from core.news import normalizer as N  # noqa: E402
from core.news import contracts as CT  # noqa: E402
from core.news.sources import base  # noqa: E402
from core.news.sources.github_trending import GitHubTrendingAdapter  # noqa: E402
from core.news.sources.hackernews import HackerNewsAdapter  # noqa: E402
from core.news.sources.openrouter import OpenRouterAdapter  # noqa: E402

PASS = 0


def ok(name: str, cond: bool, detail: str = "") -> None:
    global PASS
    if not cond:
        print(f"FAIL {name} {detail}")
        sys.exit(1)
    PASS += 1
    print(f"PASS {name}")


NOW = datetime.now(timezone.utc)
_real_http = base.http_get_json
CALLS: list = []


def use(stub) -> None:
    CALLS.clear()
    base.http_get_json = stub


# ── 1. Hacker News mapping ───────────────────────────────────────────────────────────
_HN_ITEMS = {
    1: {"type": "story", "title": "Show HN: My AI tool", "url": "https://tool.dev/x",
        "score": 55, "time": int(NOW.timestamp()), "by": "alice"},
    2: {"type": "story", "title": "Big &amp; important article", "url": "https://blog.io/post?utm_source=hn",
        "score": 10, "time": int(NOW.timestamp()), "by": "bob"},
    3: {"type": "story", "title": "Ask HN: thoughts?", "score": 3, "time": int(NOW.timestamp()),
        "text": "<p>Some <b>question</b></p>"},
    4: {"type": "job", "title": "Hiring"},
}


def hn_stub(url, headers=None, timeout=8.0):
    CALLS.append(url)
    if url.endswith("topstories.json"):
        return [1, 2, 3, 4]
    return _HN_ITEMS.get(int(url.rsplit("/", 1)[1].split(".")[0]))


use(hn_stub)
hn = HackerNewsAdapter().run()
ok("HN run succeeds on first attempt", hn.ok and hn.attempts == 1)
ok("HN maps stories and skips non-stories", len(hn.records) == 3)
by_id = {r.external_id: r for r in hn.records}
ok("Show HN posts become tool candidates", by_id["1"].item_type is CT.ItemType.TOOL)
ok("regular stories stay articles (entities unescaped)", by_id["2"].item_type is CT.ItemType.ARTICLE
   and by_id["2"].title == "Big & important article")
ok("URL-less posts link their HN discussion (never blank)", by_id["3"].url.endswith("item?id=3"))
ok("engagement is the real HN score", by_id["1"].engagement == 55)
ok("HTML in text posts is stripped into the excerpt", by_id["3"].excerpt == "Some question")

bounded = HackerNewsAdapter()
bounded.max_records = 2
use(hn_stub)
res = bounded.run()
ok("record bound also bounds detail fetches", len(res.records) == 2 and len(CALLS) == 3, str(len(CALLS)))

# ── 2. runner: retry, permanent failure, redaction, rate limits ──────────────────────
class Flaky(base.Adapter):
    name = "flaky"
    max_attempts = 2
    retry_wait_s = 0.0

    def __init__(self) -> None:
        self.calls = 0

    def _collect(self) -> base.Payload:
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("transient blip")
        return base.Payload()


flaky = Flaky()
res = flaky.run()
ok("transient failure retries within bounds", res.ok and res.attempts == 2)


class Doomed(base.Adapter):
    name = "doomed"
    max_attempts = 2
    retry_wait_s = 0.0

    def _collect(self) -> base.Payload:
        raise RuntimeError("boom Bearer abc.secret token=xyz123 at https://api.io/x?key=hush")


res = Doomed().run()
ok("permanent failure reports after capped attempts", not res.ok and res.attempts == 2)
ok("errors are redacted (no tokens, no query strings)", res.error is not None
   and "xyz123" not in res.error and "hush" not in res.error and "abc.secret" not in res.error,
   str(res.error))


class Limited(base.Adapter):
    name = "limited"

    def _collect(self) -> base.Payload:
        raise base.RateLimited("rate limited: HTTP 429")


res = Limited().run()
ok("rate limit is reported honestly, never retried or faked",
   not res.ok and res.rate_limited and res.attempts == 1 and not res.records)


class Broken(base.Adapter):
    name = "broken"

    def run(self) -> base.AdapterResult:  # a truly buggy adapter
        raise TypeError("subclass bug")


# ── 3. N02 acceptance: partial failure, successful evidence retained ─────────────────
use(hn_stub)
results = base.run_all([HackerNewsAdapter(), Doomed(), Broken()])
ok("run_all isolates every adapter", set(results) == {"hackernews", "doomed", "broken"})
ok("one failed + one crashed source still leave a successful one",
   results["hackernews"].ok and not results["doomed"].ok and not results["broken"].ok)
conn = get_connection()
counts = N.ingest(conn, results["hackernews"].records)
conn.commit()
ok("successful source's evidence is retained despite the failures",
   counts["items_new"] == 3 and counts["evidence_new"] == 3, str(counts))
conn.close()

# ── 4. OpenRouter mapping: attributed observations, nothing invented ─────────────────
_OR_CATALOG = {"data": [
    {"id": "openai/gpt-6", "name": "GPT-6", "created": int((NOW - timedelta(days=5)).timestamp()),
     "context_length": 200000, "pricing": {"prompt": "0.00001", "completion": "0.00003"}},
    {"id": "old/model", "name": "Oldie", "created": int((NOW - timedelta(days=700)).timestamp())},
    {"name": "no-id entry"},
]}
use(lambda url, headers=None, timeout=8.0: _OR_CATALOG)
orr = OpenRouterAdapter().run()
ok("OpenRouter emits one metric per PRESENT field only", len(orr.metrics) == 3,
   str([(m.model_id, m.metric) for m in orr.metrics]))
ok("metrics carry source attribution + observation time", all(
    m.source == "openrouter" and m.observed_at for m in orr.metrics))
ok("a model with no pricing/context gets NO metrics (never zeros)",
   not any(m.model_id == "old/model" for m in orr.metrics))
ok("only recent catalog arrivals become releases", len(orr.releases) == 1
   and orr.releases[0].model_id == "gpt-6")            # canonical cross-source id
ok("release evidence carries source_url + released_at",
   orr.releases[0].source_url == "https://openrouter.ai/openai/gpt-6" and orr.releases[0].released_at)

# ── 5. GitHub mapping: auth-aware bounds, snapshots, honest rate limits ──────────────
_GH_RESULT = {"items": [
    {"full_name": "org/ai-lib", "html_url": "https://github.com/org/ai-lib",
     "stargazers_count": 4200, "description": "An <b>AI</b> library", "created_at": "2025-01-01T00:00:00Z",
     "owner": {"login": "org"}},
    {"full_name": "solo/tool", "html_url": "https://github.com/solo/tool", "stargazers_count": 900},
]}
seen_headers: dict = {}


def gh_stub(url, headers=None, timeout=8.0):
    CALLS.append(url)
    seen_headers.update(headers or {})
    return _GH_RESULT


use(gh_stub)
gh = GitHubTrendingAdapter().run()
ok("unauthenticated GitHub stays a polite guest (per_page=20, no auth header)",
   "per_page=20" in CALLS[-1] and "Authorization" not in seen_headers)
ok("repos map to REPO records with star engagement", len(gh.records) == 2
   and gh.records[0].item_type is CT.ItemType.REPO and gh.records[0].engagement == 4200)
today = NOW.date().isoformat()
ok("every repo yields today's star snapshot (growth comes ONLY from history)",
   [(s.repo, s.snapshot_date, s.stars) for s in gh.github_snapshots]
   == [("org/ai-lib", today, 4200), ("solo/tool", today, 900)])

os.environ["GITHUB_TOKEN"] = "ghp_dummy"
seen_headers.clear()
use(gh_stub)
GitHubTrendingAdapter().run()
ok("a vault-exported token authenticates and raises the bound",
   seen_headers.get("Authorization") == "Bearer ghp_dummy" and "per_page=40" in CALLS[-1])
os.environ.pop("GITHUB_TOKEN", None)


def gh_limited(url, headers=None, timeout=8.0):
    raise base.RateLimited("rate limited: HTTP 403")


use(gh_limited)
res = GitHubTrendingAdapter().run()
ok("GitHub rate limit surfaces honestly with zero records", res.rate_limited and not res.records)

# ── 6. normalizer text + timestamps ──────────────────────────────────────────────────
ok("strip_html removes tags and unescapes entities", N.strip_html("<b>Hi</b> &amp; <i>bye</i>") == "Hi & bye")
long_text = "word " * 200
cut = N.bound_excerpt(long_text)
ok("excerpts cut at a word boundary within the cap", len(cut) <= CT.EXCERPT_MAX and cut.endswith("…")
   and not cut[:-1].endswith(" wor"))
ok("unix + ISO timestamps normalize to UTC ISO; garbage stays None",
   (N.to_utc_iso(int(NOW.timestamp())) or "").endswith("+00:00")
   and (N.to_utc_iso("2026-07-01T10:00:00Z") or "").startswith("2026-07-01")
   and N.to_utc_iso("garbage") is None and N.to_utc_iso(None) is None)

# ── 7. ingest: canonical dedupe, evidence per source, idempotent replays ─────────────
conn = get_connection()
mk = lambda source, ext, url, engagement: CT.SourceRecord(  # noqa: E731
    source=source, external_id=ext, url=url, title="Same story", item_type=CT.ItemType.ARTICLE,
    trust=CT.TrustClass.AGGREGATOR, observed_at=NOW.isoformat(), engagement=engagement,
    raw_hash=CT.payload_hash({"e": engagement}))
a = mk("rss", "r-1", "https://example.com/story?utm_source=rss", 5)
b = mk("reddit", "d-1", "https://Example.com/story/", 40)
first = N.ingest(conn, [a, b])
ok("two sources of one story → one canonical item, both evidence rows",
   first == {"items_new": 1, "evidence_new": 2, "evidence_updated": 0}, str(first))
replay = N.ingest(conn, [a, b])
ok("identical replay is a pure no-op", replay == {"items_new": 0, "evidence_new": 0, "evidence_updated": 0},
   str(replay))
bumped = N.ingest(conn, [mk("reddit", "d-1", "https://Example.com/story/", 90)])
row = conn.execute("SELECT engagement FROM news_item_sources WHERE source='reddit' AND external_id='d-1'").fetchone()
ok("re-sighting updates evidence engagement in place", bumped["evidence_updated"] == 1 and row[0] == 90)

ev = N.ingest_model_evidence(conn, orr.metrics, orr.releases)
again = N.ingest_model_evidence(conn, orr.metrics, orr.releases)
metric_rows = conn.execute("SELECT COUNT(*) FROM news_model_metrics WHERE source='openrouter'").fetchone()[0]
release_rows = conn.execute("SELECT COUNT(*) FROM news_model_releases").fetchone()[0]
ok("model evidence upserts without duplication", ev["metrics"] == 3 and metric_rows == 3 and release_rows == 1,
   f"{ev} rows={metric_rows}/{release_rows}")
ok("release replay never duplicates evidence", again["releases"] == 0)

N.ingest_github_snapshots(conn, gh.github_snapshots)
N.ingest_github_snapshots(conn, [CT.GitHubSnapshot(repo="org/ai-lib", snapshot_date=today, stars=4321)])
snaps = conn.execute("SELECT COUNT(*), MAX(stars) FROM news_github_snapshots WHERE repo='org/ai-lib'").fetchone()
ok("one snapshot per repo per day; same-day refetch keeps the latest reading",
   tuple(snaps) == (1, 4321), str(tuple(snaps)))
conn.commit()
conn.close()

base.http_get_json = _real_http

# ── RSS adapter (N12 owner QA): curated publication feeds, RSS2 + Atom ───────────────
from core.news.sources.rss import RSSAdapter, FEEDS  # noqa: E402

_RSS_XML = """<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>AI &lt;b&gt;chips&lt;/b&gt; surge</title><link>https://pub.io/a1</link>
<pubDate>Wed, 22 Jul 2026 08:00:00 GMT</pubDate>
<description>&lt;p&gt;Big move in &lt;i&gt;silicon&lt;/i&gt;&lt;/p&gt;</description></item>
<item><title>No link item</title><link></link></item>
</channel></rss>"""
_ATOM_XML = """<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
<entry><title>Atom AI story</title><link href="https://pub2.io/b1"/>
<updated>2026-07-22T09:30:00Z</updated><summary>Atom summary</summary></entry>
</feed>"""


def fake_text(url, headers=None, timeout=8.0):
    if FEEDS[0][1] == url:
        return _RSS_XML
    if FEEDS[1][1] == url:
        return _ATOM_XML
    raise RuntimeError("HTTP 500")


_real_text = base.http_get_text
base.http_get_text = fake_text
rss_result = RSSAdapter().run()
ok("rss adapter: partial feed failure still succeeds with parsed records",
   rss_result.ok and len(rss_result.records) == 2, str(rss_result.error))
by_source = {r.source: r for r in rss_result.records}
ok("rss records carry the PUBLICATION as source (newspaper rack, not pipeline name)",
   set(by_source) == {FEEDS[0][0], FEEDS[1][0]})
ok("rss strips HTML from titles and excerpts",
   by_source[FEEDS[0][0]].title == "AI chips surge" and "<" not in by_source[FEEDS[0][0]].excerpt)
ok("rss parses RFC-822 and Atom dates to UTC ISO",
   (by_source[FEEDS[0][0]].published_at or "").startswith("2026-07-22")
   and (by_source[FEEDS[1][0]].published_at or "").startswith("2026-07-22"))


def all_fail(url, headers=None, timeout=8.0):
    raise RuntimeError("HTTP 500 token=sekr3t")


base.http_get_text = all_fail
dead = RSSAdapter().run()
ok("rss adapter: every feed failing fails the adapter with a redacted error",
   not dead.ok and "sekr3t" not in (dead.error or ""))
base.http_get_text = _real_text

# ── Model Strength sources (owner: real, trustworthy, latest) ────────────────────────
from core.news.contracts import canonical_model_id  # noqa: E402
from core.news.sources.artificial_analysis import ArtificialAnalysisAdapter  # noqa: E402
from core.news.sources.lmarena import LMArenaAdapter  # noqa: E402

ok("canonical model ids merge cross-source namings",
   canonical_model_id("openai/gpt-5.4") == "gpt-5.4"
   and canonical_model_id("GPT-5.4") == "gpt-5.4"
   and canonical_model_id("Anthropic/claude-opus-4.8:free") == "claude-opus-4.8"
   and canonical_model_id("Claude Opus 4.8") == "claude-opus-4.8")

_aa_payload = {"data": [
    {"slug": "openai/gpt-5.4",
     "evaluations": {"artificial_analysis_intelligence_index": 71.2,
                     "artificial_analysis_coding_index": 66.0},
     "median_output_tokens_per_second": 150.5,
     "pricing": {"price_1m_blended_3_to_1": 4.2}},
    {"slug": "tiny/no-evals"},                          # nothing numeric → no metrics
]}


def fake_aa(url, headers=None, timeout=8.0):
    assert headers and headers.get("x-api-key") == "aa-test-key"
    return _aa_payload


_saved_key = os.environ.pop("ARTIFICIALANALYSIS_API_KEY", None)
no_key = ArtificialAnalysisAdapter().run()
ok("artificialanalysis without a key fails with an actionable error",
   not no_key.ok and "ARTIFICIALANALYSIS_API_KEY" in (no_key.error or ""))
os.environ["ARTIFICIALANALYSIS_API_KEY"] = "aa-test-key"
base.http_get_json = fake_aa
aa = ArtificialAnalysisAdapter().run()
by_metric = {(m.category, m.metric): m for m in aa.metrics}
ok("artificialanalysis emits intelligence/coding/speed/price for present fields only",
   aa.ok and len(aa.metrics) == 4
   and by_metric[("general", "intelligence")].value == 71.2
   and by_metric[("coding", "coding")].model_id == "gpt-5.4")
if _saved_key is None:
    os.environ.pop("ARTIFICIALANALYSIS_API_KEY", None)
else:
    os.environ["ARTIFICIALANALYSIS_API_KEY"] = _saved_key


def fake_arena(url, headers=None, timeout=8.0):
    if "config=text" in url:
        return {"rows": [
            {"row": {"model_name": "gpt-5.4", "rating": 1499.0, "category": "overall",
                     "leaderboard_publish_date": "2026-07-21"}},
            {"row": {"model_name": "gpt-5.4", "rating": 1490.0, "category": "overall",
                     "leaderboard_publish_date": "2026-07-14"}},   # stale date → ignored
            {"row": {"model_name": "claude-fable-5", "rating": 1504.0, "category": "overall",
                     "leaderboard_publish_date": "2026-07-21"}},
        ]}
    if "config=agent" in url:
        return {"rows": [
            {"row": {"model_name": "Claude Fable 5 (High)", "score": 0.127, "category": "overall",
                     "leaderboard_publish_date": "2026-07-21"}},
            {"row": {"model_name": "Claude Fable 5 (Low)", "score": 0.080, "category": "overall",
                     "leaderboard_publish_date": "2026-07-21"}},   # variant merges, best kept
        ]}
    return {"rows": []}                                 # webdev board down → others survive


base.http_get_json = fake_arena
arena = LMArenaAdapter().run()
elo = {m.model_id: m.value for m in arena.metrics if m.metric == "elo"}
agentic = {m.model_id: m.value for m in arena.metrics if m.metric == "agentic"}
ok("lmarena: newest publish date only, per-board metrics, one board down survives",
   arena.ok and elo == {"gpt-5.4": 1499.0, "claude-fable-5": 1504.0}
   and not any(m.metric == "webdev" for m in arena.metrics))
ok("lmarena: effort variants merge onto the base model keeping the best score",
   agentic == {"claude-fable-5": 0.127})
base.http_get_json = _real_http

print(f"\nALL {PASS} CHECKS PASSED")

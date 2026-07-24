"""GitHub trending adapter (#23) — REAL trending from github.com/trending.

Owner direction: "fetch real data from github, not calculated it self." GitHub's
REST/GraphQL API has no trending endpoint; github.com/trending is GitHub's own
authoritative trending list and reports the ACTUAL stars gained this week/month.
So this adapter scrapes that page (keyless, no token needed) for the weekly and
monthly boards and stores GitHub's real period number directly — the ranking no
longer derives growth from our own star snapshots over time.

Parsing is defensive: each repo block is isolated, missing fields are skipped
(never guessed), and a board that fails to parse never kills the other. Star
history snapshots are still emitted (cheap, useful for the model explorer) but
are no longer the source of the week/month growth figure.
"""
from __future__ import annotations

import html
import re
from datetime import datetime, timezone

from core.news import normalizer
from core.news.contracts import (
    GitHubSnapshot, GitHubTrending, ItemType, SourceRecord, TrustClass, payload_hash,
)
from core.news.sources import base

_TRENDING = "https://github.com/trending?since={since}&spoken_language_code="
_WINDOWS = (("week", "weekly"), ("month", "monthly"))
# "All time" is the REAL most-starred set from GitHub's Search API (owner can verify at
# github.com/search?q=stars:>50000&type=repositories&s=stars) — NOT a reorder of the
# trending list. Keyless; one request per refresh stays inside the unauth rate limit.
_ALLTIME = ("https://api.github.com/search/repositories"
            "?q=stars:%3E50000&sort=stars&order=desc&per_page=30")

_BLOCK = re.compile(r'<article class="Box-row">')
_NAME = re.compile(r'<h2[^>]*>\s*<a[^>]*href="/([^"/]+/[^"?#]+)"')
_DESC = re.compile(r'<p class="col-9[^"]*"[^>]*>(.*?)</p>', re.S)
_TOTAL = re.compile(r'href="/[^"]+/stargazers"[^>]*>.*?</svg>\s*([\d,]+)', re.S)
_PERIOD = re.compile(r'([\d,]+)\s+stars\s+(?:today|this week|this month)')
_LANG = re.compile(r'itemprop="programmingLanguage">([^<]+)<')
_TAG = re.compile(r"<[^>]+>")


def _int(raw: str | None) -> int:
    try:
        return max(0, int((raw or "0").replace(",", "").strip()))
    except (TypeError, ValueError):
        return 0


def _text(raw: str) -> str:
    return html.unescape(_TAG.sub("", raw)).strip()


class GitHubTrendingAdapter(base.Adapter):
    name = "github"
    trust = TrustClass.VERIFIED_API
    attribution = "GitHub Trending (github.com/trending)"
    timeout_s = 10.0
    max_records = 30
    # Three boards (week + month + all-time), deduped, yield ~80 distinct repos — emit a
    # ledger item for every one so no GitHub-table row is left without action buttons.
    max_out_records = 100

    def _collect(self) -> base.Payload:
        now_dt = datetime.now(timezone.utc)
        now = now_dt.isoformat()
        today = now_dt.date().isoformat()
        payload = base.Payload()
        seen_snapshot: set[str] = set()
        parsed_any = False
        for window, since in _WINDOWS:
            try:
                page = base.http_get_text(_TRENDING.format(since=since), timeout=self.timeout_s)
            except base.RateLimited:
                raise
            except Exception:
                continue                                   # one board down never kills the other
            blocks = _BLOCK.split(page)[1:]
            for rank, block in enumerate(blocks[: self.max_records], start=1):
                name_m = _NAME.search(block)
                if not name_m:
                    continue
                full_name = name_m.group(1).strip()
                if "/" not in full_name:
                    continue
                period_m = _PERIOD.search(block)
                if not period_m:
                    continue                               # no real period number → skip, never guess
                period_stars = _int(period_m.group(1))
                total_m = _TOTAL.search(block)
                total_stars = _int(total_m.group(1)) if total_m else period_stars
                desc_m = _DESC.search(block)
                description = _text(desc_m.group(1))[:280] if desc_m else ""
                lang_m = _LANG.search(block)
                language = lang_m.group(1).strip() if lang_m else None
                parsed_any = True
                payload.github_trending.append(GitHubTrending(
                    repo=full_name, window=window, rank=rank,
                    period_stars=period_stars, total_stars=total_stars,
                    observed_at=now, description=description or None, language=language))
                self._emit_repo(payload, seen_snapshot, full_name, total_stars, description, today, now)

        # all-time most-starred (verifiable Search API) — a board an owner can trust
        try:
            data = base.http_get_json(_ALLTIME, headers={"Accept": "application/vnd.github+json"},
                                      timeout=self.timeout_s) or {}
        except base.RateLimited:
            raise
        except Exception:
            data = {}
        for rank, repo in enumerate((data.get("items") or [])[: self.max_records], start=1):
            full_name = str(repo.get("full_name") or "").strip()
            if "/" not in full_name:
                continue
            stars = _int(str(repo.get("stargazers_count") or 0))
            description = _text(str(repo.get("description") or ""))[:280]
            payload.github_trending.append(GitHubTrending(
                repo=full_name, window="all", rank=rank, period_stars=0, total_stars=stars,
                observed_at=now, description=description or None,
                language=(repo.get("language") or None)))
            self._emit_repo(payload, seen_snapshot, full_name, stars, description, today, now)
            parsed_any = True

        if not parsed_any:
            raise RuntimeError("github.com/trending returned no parsable repositories")
        return payload

    @staticmethod
    def _emit_repo(payload: base.Payload, seen: set, full_name: str, stars: int,
                   description: str, today: str, now: str) -> None:
        """One canonical REPO record + one star snapshot per repo (deduped across boards),
        so every GitHub-table row has a news item id to like/favourite/note."""
        if full_name in seen:
            return
        seen.add(full_name)
        payload.records.append(SourceRecord(
            source="github", external_id=full_name, url=f"https://github.com/{full_name}",
            title=full_name, item_type=ItemType.REPO, trust=TrustClass.VERIFIED_API,
            observed_at=now, published_at=None,
            excerpt=normalizer.bound_excerpt(description), engagement=stars,
            author=full_name.split("/", 1)[0] or None,
            raw_hash=payload_hash({"repo": full_name, "stars": stars})))
        if stars > 0:
            payload.github_snapshots.append(GitHubSnapshot(
                repo=full_name, snapshot_date=today, stars=stars))

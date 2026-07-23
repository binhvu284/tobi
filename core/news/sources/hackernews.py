"""Hacker News adapter (#23, N02) — the OFFICIAL Firebase API, never scraping.

Top stories → feed articles; "Show HN" posts → tool discovery candidates (plan §5).
Engagement is the real HN score; text posts without an outbound URL link to their HN
discussion page so the canonical URL is always real.
"""
from __future__ import annotations

from datetime import datetime, timezone

from core.news import normalizer
from core.news.contracts import ItemType, SourceRecord, TrustClass, payload_hash
from core.news.sources import base

_API = "https://hacker-news.firebaseio.com/v0"


class HackerNewsAdapter(base.Adapter):
    name = "hackernews"
    trust = TrustClass.VERIFIED_API
    attribution = "Hacker News (official API)"
    timeout_s = 6.0
    max_records = 30

    def _collect(self) -> base.Payload:
        now = datetime.now(timezone.utc).isoformat()
        ids = base.http_get_json(f"{_API}/topstories.json", timeout=self.timeout_s) or []
        payload = base.Payload()
        for story_id in ids[: self.max_records]:
            item = base.http_get_json(f"{_API}/item/{story_id}.json", timeout=self.timeout_s)
            if not isinstance(item, dict) or item.get("type") != "story" or item.get("dead"):
                continue
            title = normalizer.strip_html(item.get("title") or "")
            if not title:
                continue
            url = (item.get("url") or "").strip() or f"https://news.ycombinator.com/item?id={story_id}"
            payload.records.append(SourceRecord(
                source=self.name,
                external_id=str(story_id),
                url=url,
                title=title,
                item_type=ItemType.TOOL if title.lower().startswith("show hn") else ItemType.ARTICLE,
                trust=self.trust,
                observed_at=now,
                published_at=normalizer.to_utc_iso(item.get("time")),
                excerpt=normalizer.bound_excerpt(item.get("text")),
                engagement=max(0, int(item.get("score") or 0)),
                author=item.get("by") or None,
                raw_hash=payload_hash(item),
            ))
        return payload

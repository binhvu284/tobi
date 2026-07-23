"""RSS/Atom news adapter (#23, N12 owner QA) — curated AI publication feeds.

One adapter ("rss") fans out over a curated feed list; each record carries the
PUBLICATION as its source (theverge, arstechnica, …) so Source Explore and the
feed's source filter read like a newspaper rack, not a pipeline name. Feeds are
isolated: one broken feed degrades the batch, only all-feeds-failing fails the
adapter (the checkpoint stays honest either way). Everything emitted is untrusted
evidence bound by the same contracts as every other adapter — script/data URLs
are rejected at validation, HTML is stripped, excerpts bounded.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from core.news import normalizer
from core.news.contracts import ItemType, SourceRecord, TrustClass, payload_hash
from core.news.sources import base

# (source name, feed URL) — curated, publication-grade AI coverage. Adding a feed
# here is the only change needed for a new publication to appear everywhere.
FEEDS: tuple = (
    ("arstechnica", "https://arstechnica.com/ai/feed/"),
    ("theverge", "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"),
    ("venturebeat", "https://venturebeat.com/category/ai/feed/"),
    ("mittechreview", "https://www.technologyreview.com/topic/artificial-intelligence/feed"),
)
_PER_FEED = 15
_ATOM = "{http://www.w3.org/2005/Atom}"


def _text(node, tag: str) -> str:
    child = node.find(tag)
    return (child.text or "").strip() if child is not None and child.text else ""


def _to_iso(raw: str) -> str | None:
    if not raw:
        return None
    try:                                              # RFC-822 (RSS 2.0 pubDate)
        return parsedate_to_datetime(raw).astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError):
        return normalizer.to_utc_iso(raw)             # ISO (Atom) or None


def _parse_feed(xml_text: str) -> list[dict]:
    """RSS 2.0 ``item`` and Atom ``entry`` → [{title, url, published, summary}]."""
    root = ET.fromstring(xml_text)
    items = []
    for item in root.iter("item"):                    # RSS 2.0
        items.append({"title": _text(item, "title"), "url": _text(item, "link"),
                      "published": _to_iso(_text(item, "pubDate")),
                      "summary": _text(item, "description")})
    for entry in root.iter(f"{_ATOM}entry"):          # Atom
        link = entry.find(f"{_ATOM}link")
        items.append({"title": _text(entry, f"{_ATOM}title"),
                      "url": (link.get("href") or "").strip() if link is not None else "",
                      "published": _to_iso(_text(entry, f"{_ATOM}updated")
                                           or _text(entry, f"{_ATOM}published")),
                      "summary": _text(entry, f"{_ATOM}summary")
                      or _text(entry, f"{_ATOM}content")})
    return items


class RSSAdapter(base.Adapter):
    name = "rss"
    trust = TrustClass.AGGREGATOR
    attribution = "Publisher RSS/Atom feeds"
    timeout_s = 8.0
    max_records = 60
    max_attempts = 1                                  # feeds retry poorly; the schedule retries

    def _collect(self) -> base.Payload:
        now = datetime.now(timezone.utc).isoformat()
        payload = base.Payload()
        failures: list[str] = []
        for source, feed_url in FEEDS:
            try:
                raw = base.http_get_text(feed_url, headers={"User-Agent": "TOBI-News/1.0"},
                                         timeout=self.timeout_s)
                parsed = _parse_feed(raw)
            except base.RateLimited:
                raise                                  # whole-adapter honesty: surface it
            except Exception as exc:
                failures.append(f"{source}: {base.redact(str(exc) or exc.__class__.__name__)}")
                continue                               # one broken feed never kills the rest
            for item in parsed[:_PER_FEED]:
                title, url = item["title"], item["url"]
                if not title or not url.startswith(("http://", "https://")):
                    continue
                payload.records.append(SourceRecord(
                    source=source,
                    external_id=url,
                    url=url,
                    title=normalizer.strip_html(title)[:300],
                    item_type=ItemType.ARTICLE,
                    trust=self.trust,
                    observed_at=now,
                    published_at=item["published"],
                    excerpt=normalizer.bound_excerpt(normalizer.strip_html(item["summary"])),
                    raw_hash=payload_hash({"url": url, "title": title}),
                ))
        if failures and not payload.records:
            raise RuntimeError("all feeds failed — " + "; ".join(failures)[:150])
        return payload

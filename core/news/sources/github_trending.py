"""GitHub AI-repository adapter (#23, N02) — authenticated REST search, rate-honest.

Emits repo items for Trending plus one ``GitHubSnapshot`` star reading per repo per
day. Week/month growth is computed LATER (N05) purely from persisted snapshots — this
adapter never claims growth, and a rate-limit response surfaces as ``rate_limited``
instead of degraded fake data (plan §5/§6).
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

from core.news import normalizer
from core.news.contracts import GitHubSnapshot, ItemType, SourceRecord, TrustClass, payload_hash
from core.news.sources import base

_API = ("https://api.github.com/search/repositories"
        "?q=topic:ai+stars:%3E200&sort=stars&order=desc&per_page={n}")
_UNAUTH_MAX = 20                 # be a polite guest without a token


class GitHubTrendingAdapter(base.Adapter):
    name = "github"
    trust = TrustClass.VERIFIED_API
    attribution = "GitHub REST API"
    timeout_s = 8.0
    max_records = 40

    def _headers(self) -> dict:
        headers = {"Accept": "application/vnd.github+json"}
        token = os.getenv("GITHUB_TOKEN", "").strip()   # vault-exported when connected
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def _collect(self) -> base.Payload:
        headers = self._headers()
        bound = self.max_records if "Authorization" in headers else min(self.max_records, _UNAUTH_MAX)
        now_dt = datetime.now(timezone.utc)
        now = now_dt.isoformat()
        today = now_dt.date().isoformat()
        data = base.http_get_json(_API.format(n=bound), headers=headers, timeout=self.timeout_s) or {}
        payload = base.Payload()
        for repo in (data.get("items") or [])[:bound]:
            full_name = str(repo.get("full_name") or "").strip()
            html_url = (repo.get("html_url") or "").strip()
            if not full_name or "/" not in full_name or not html_url:
                continue
            stars = max(0, int(repo.get("stargazers_count") or 0))
            payload.records.append(SourceRecord(
                source=self.name,
                external_id=full_name,
                url=html_url,
                title=full_name,
                item_type=ItemType.REPO,
                trust=self.trust,
                observed_at=now,
                published_at=normalizer.to_utc_iso(repo.get("created_at")),
                excerpt=normalizer.bound_excerpt(repo.get("description")),
                engagement=stars,
                author=(repo.get("owner") or {}).get("login") or None,
                raw_hash=payload_hash({"full_name": full_name, "stars": stars}),
            ))
            payload.github_snapshots.append(GitHubSnapshot(
                repo=full_name, snapshot_date=today, stars=stars))
        return payload

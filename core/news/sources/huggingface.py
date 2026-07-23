"""Hugging Face Hub adapter (#23, Model Strength backend — keyless resilience).

The public Hub API (``https://huggingface.co/api/models``) is keyless and live —
it needs no owner setup and never shows a key-required chip, which is exactly the
resilience the owner asked for after the keyed llm-stats source proved flaky.

It supplies RELEASE evidence for recently-published open-weight models that have
already drawn real traction (a ``likes`` floor keeps it signal, not the raw
create-firehose). Bounded to a recent window; every release carries its Hub URL
as required evidence. No metrics — the ranking authority stays Artificial
Analysis + LMArena; this only diversifies the Latest-Releases stream so it never
depends on a single catalog source.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core.news import normalizer
from core.news.contracts import ModelRelease, TrustClass, canonical_model_id
from core.news.sources import base

# createdAt-desc surfaces the newest uploads; a likes floor keeps only models the
# community has actually noticed (raw newest is upload noise, live-verified).
_API = ("https://huggingface.co/api/models"
        "?sort=createdAt&direction=-1&limit=100&full=false")
RELEASE_WINDOW_DAYS = 30
MIN_LIKES = 5
FORMULA_VERSION = "hf-hub-v1"


class HuggingFaceAdapter(base.Adapter):
    name = "huggingface"
    trust = TrustClass.AGGREGATOR
    attribution = "Hugging Face Hub"
    timeout_s = 10.0
    max_records = 100
    max_attempts = 2

    def _collect(self) -> base.Payload:
        now_dt = datetime.now(timezone.utc)
        now = now_dt.isoformat()
        cutoff = now_dt - timedelta(days=RELEASE_WINDOW_DAYS)
        data = base.http_get_json(_API, timeout=self.timeout_s) or []
        payload = base.Payload()
        for model in (data if isinstance(data, list) else [])[: self.max_records]:
            if not isinstance(model, dict):
                continue
            try:
                likes = int(model.get("likes") or 0)
            except (TypeError, ValueError):
                likes = 0
            if likes < MIN_LIKES:
                continue                              # community traction floor → signal, not firehose
            raw_id = str(model.get("id") or model.get("modelId") or "").strip()
            if not raw_id:
                continue
            created = normalizer.to_utc_iso(model.get("createdAt") or model.get("created_at"))
            if not created or datetime.fromisoformat(created) < cutoff:
                continue                              # only recent releases; never guess a date
            payload.releases.append(ModelRelease(
                model_id=canonical_model_id(raw_id),
                title=f"{raw_id} published on Hugging Face ({likes} likes)",
                source_url=f"https://huggingface.co/{raw_id}",
                released_at=created,
                observed_at=now))
        return payload

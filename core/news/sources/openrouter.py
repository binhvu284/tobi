"""OpenRouter model-catalog adapter (#23, N02) — the plan's primary model source (§5).

Emits raw catalog observations as attributed ``ModelMetric`` rows (context window,
prompt/completion price) and ``ModelRelease`` evidence for models that appeared in the
catalog recently. Only fields the catalog actually carries are emitted — a model with
no pricing gets no price metric; missing data is never invented.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core.news import normalizer
from core.news.contracts import ModelMetric, ModelRelease, TrustClass
from core.news.sources import base

_API = "https://openrouter.ai/api/v1/models"
RELEASE_WINDOW_DAYS = 30
FORMULA_VERSION = "raw"          # raw catalog observations; N05 formulas cite their own version


class OpenRouterAdapter(base.Adapter):
    name = "openrouter"
    trust = TrustClass.OFFICIAL
    attribution = "OpenRouter model catalog"
    timeout_s = 8.0
    max_records = 200            # catalog rows, not feed items

    def _collect(self) -> base.Payload:
        now_dt = datetime.now(timezone.utc)
        now = now_dt.isoformat()
        cutoff = now_dt - timedelta(days=RELEASE_WINDOW_DAYS)
        data = base.http_get_json(_API, timeout=self.timeout_s) or {}
        payload = base.Payload()
        for model in (data.get("data") or [])[: self.max_records]:
            model_id = str(model.get("id") or "").strip()
            if not model_id:
                continue
            pricing = model.get("pricing") or {}
            observations = (
                ("context", model.get("context_length")),
                ("price_in", pricing.get("prompt")),
                ("price_out", pricing.get("completion")),
            )
            for metric, value in observations:
                try:
                    value_f = float(value)
                except (TypeError, ValueError):
                    continue                      # absent/odd field → no metric, never 0
                payload.metrics.append(ModelMetric(
                    model_id=model_id, category="general", source=self.name,
                    metric=metric, value=value_f, confidence=0.9,
                    observed_at=now, formula_version=FORMULA_VERSION))
            created = normalizer.to_utc_iso(model.get("created"))
            if created and datetime.fromisoformat(created) >= cutoff:
                name = str(model.get("name") or model_id)
                payload.releases.append(ModelRelease(
                    model_id=model_id,
                    title=f"{name} available on OpenRouter",
                    source_url=f"https://openrouter.ai/{model_id}",
                    released_at=created,
                    observed_at=now))
        return payload

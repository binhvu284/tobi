"""Artificial Analysis adapter (#23, Model Strength backend fix — owner direction).

The industry's apples-to-apples benchmark aggregator: intelligence index, coding
index, output speed, and blended price per model, refreshed as evaluations publish.
Official free Data API (``/api/v2/data/llms/models``) with an ``x-api-key`` from the
owner's free Insights account — exported as ``ARTIFICIALANALYSIS_API_KEY``. Without
the key the adapter FAILS with a clear, actionable error (visible in the refresh
progress strip and, after repeated failures, as one Inbox action) — it never
degrades to invented numbers. Attribution: https://artificialanalysis.ai/ (required
by their free-API terms; carried on every metric row via ``source``/``attribution``).

Field names are parsed defensively — only numeric values actually present are
emitted; a missing evaluation is a missing metric, never a zero.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

from core.news.contracts import ModelMetric, TrustClass, canonical_model_id
from core.news.sources import base

_API = "https://artificialanalysis.ai/api/v2/data/llms/models"
FORMULA_VERSION = "aa-v2"

# (metric name, category, candidate response keys — first numeric wins)
_FIELDS = (
    ("intelligence", "general", ("artificial_analysis_intelligence_index", "intelligence_index",
                                 "quality_index")),
    ("coding", "coding", ("artificial_analysis_coding_index", "coding_index")),
    ("speed", "general", ("median_output_tokens_per_second", "output_tokens_per_second",
                          "median_tokens_per_second")),
    ("price_blended", "general", ("price_1m_blended_3_to_1", "blended_price_1m",
                                  "price_1m_blended")),
)


def _pick(container: dict, keys: tuple) -> float | None:
    for key in keys:
        try:
            value = container.get(key)
            if value is not None:
                return float(value)
        except (TypeError, ValueError):
            continue
    return None


class ArtificialAnalysisAdapter(base.Adapter):
    name = "artificialanalysis"
    trust = TrustClass.VERIFIED_API
    attribution = "Artificial Analysis (artificialanalysis.ai)"
    timeout_s = 10.0
    max_records = 150

    def configured(self) -> tuple[bool, str]:
        if not os.getenv("ARTIFICIALANALYSIS_API_KEY", "").strip():
            return False, ("needs ARTIFICIALANALYSIS_API_KEY — free key at"
                           " artificialanalysis.ai, connect it on the Integrations page")
        return True, ""

    def _collect(self) -> base.Payload:
        key = os.getenv("ARTIFICIALANALYSIS_API_KEY", "").strip()
        if not key:
            raise RuntimeError(
                "ARTIFICIALANALYSIS_API_KEY not configured — create a free key at"
                " artificialanalysis.ai (Insights account) and add it to .env")
        now = datetime.now(timezone.utc).isoformat()
        data = base.http_get_json(_API, headers={"x-api-key": key}, timeout=self.timeout_s) or {}
        payload = base.Payload()
        for model in (data.get("data") or [])[: self.max_records]:
            raw_id = str(model.get("slug") or model.get("id") or model.get("name") or "").strip()
            if not raw_id:
                continue
            model_id = canonical_model_id(raw_id)
            # evaluations may sit nested or flat depending on API revision — check both
            containers = [model]
            for nested in ("evaluations", "benchmarks", "median_metrics", "pricing"):
                if isinstance(model.get(nested), dict):
                    containers.append(model[nested])
            for metric, category, keys in _FIELDS:
                value = next((v for c in containers if (v := _pick(c, keys)) is not None), None)
                if value is None:
                    continue
                payload.metrics.append(ModelMetric(
                    model_id=model_id, category=category, source=self.name,
                    metric=metric, value=value, confidence=0.95,
                    observed_at=now, formula_version=FORMULA_VERSION))
        if not payload.metrics:
            raise RuntimeError("Artificial Analysis returned no parsable model evaluations")
        return payload

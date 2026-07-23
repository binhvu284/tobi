"""LLM Stats adapter (#23, Model Strength backend — owner-referenced source).

Official llm-stats.com Data API (``https://api.llm-stats.com/stats/v1``, Bearer
``ze_…`` key from the developer console — vaulted as ``LLMSTATS_API_KEY``).
``/models`` supplies per-category benchmark scores (every category in the
response becomes evidence — new categories flow straight into the data-driven
leaderboards); ``/updates`` supplies recently-added models as release evidence.
Parsed defensively across plausible field spellings; a missing field is missing
evidence, never a zero. Without a key the adapter fails with an actionable
error — the owner connects it on the Integrations page (Explore sources card).
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

from core.news import normalizer
from core.news.contracts import ModelMetric, ModelRelease, TrustClass, canonical_model_id
from core.news.sources import base

_BASE = "https://api.llm-stats.com/stats/v1"
FORMULA_VERSION = "llmstats-v1"


def _rows(data) -> list:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("data", "models", "results", "items", "updates"):
            if isinstance(data.get(key), list):
                return data[key]
    return []


def _score_map(model: dict) -> dict:
    for key in ("category_scores", "categories", "scores"):
        if isinstance(model.get(key), dict):
            return model[key]
    return {}


class LLMStatsAdapter(base.Adapter):
    name = "llmstats"
    trust = TrustClass.VERIFIED_API
    attribution = "LLM Stats (llm-stats.com)"
    timeout_s = 10.0
    max_records = 150

    def configured(self) -> tuple[bool, str]:
        if not os.getenv("LLMSTATS_API_KEY", "").strip():
            return False, ("needs LLMSTATS_API_KEY — key at llm-stats.com/developer,"
                           " connect it on the Integrations page")
        return True, ""

    def _headers(self) -> dict:
        key = os.getenv("LLMSTATS_API_KEY", "").strip()
        if not key:
            raise RuntimeError(
                "LLMSTATS_API_KEY not configured — create a key at llm-stats.com/developer"
                " and connect it on the Integrations page (Explore sources)")
        return {"Authorization": f"Bearer {key}"}

    def _collect(self) -> base.Payload:
        headers = self._headers()
        now = datetime.now(timezone.utc).isoformat()
        payload = base.Payload()
        data = base.http_get_json(f"{_BASE}/models", headers=headers, timeout=self.timeout_s)
        for model in _rows(data)[: self.max_records]:
            if not isinstance(model, dict):
                continue
            raw_id = str(model.get("slug") or model.get("id") or model.get("name") or "").strip()
            if not raw_id:
                continue
            model_id = canonical_model_id(raw_id)
            for category, value in _score_map(model).items():
                try:
                    value_f = float(value)
                except (TypeError, ValueError):
                    continue
                cat = str(category).strip().lower() or "general"
                payload.metrics.append(ModelMetric(
                    model_id=model_id, category=cat, source=self.name,
                    metric=cat, value=value_f, confidence=0.9,
                    observed_at=now, formula_version=FORMULA_VERSION))
        if not payload.metrics:
            raise RuntimeError("LLM Stats returned no parsable category scores")
        try:                                            # optional enrichment — never fails the adapter
            updates = base.http_get_json(f"{_BASE}/updates", headers=headers, timeout=self.timeout_s)
            for row in _rows(updates)[:30]:
                if not isinstance(row, dict):
                    continue
                name = str(row.get("name") or row.get("id") or row.get("slug") or "").strip()
                slug = str(row.get("slug") or row.get("id") or name).strip()
                stamp = normalizer.to_utc_iso(row.get("released_at") or row.get("release_date")
                                              or row.get("added_at") or row.get("created_at"))
                if not name or not slug:
                    continue
                payload.releases.append(ModelRelease(
                    model_id=canonical_model_id(slug),
                    title=f"{name} tracked on LLM Stats",
                    source_url=f"https://llm-stats.com/models/{slug}",
                    released_at=stamp, observed_at=now))
        except Exception:
            pass
        return payload

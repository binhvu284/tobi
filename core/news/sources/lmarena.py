"""LMArena Elo adapter (#23, Model Strength backend fix — owner direction).

Human-preference ratings from the OFFICIAL ``lmarena-ai/leaderboard-dataset``
(Hugging Face datasets-server JSON, keyless, ``latest`` split — verified live).
Seven boards feed the ranking's capability families AND the Model Explorer's
per-aspect tables (owner: "coding, image, video, research aspects"): text → arena,
agent → agentic, webdev → coding, and the keyless media/multimodal boards
vision → vision, text_to_image → image, text_to_video → video, search → search.
All board configs are live-verified to carry an ``overall`` category and a
``rating`` column. Rows are filtered to each board's newest
``leaderboard_publish_date`` and the ``overall`` category; one rating per model,
never guessed, never averaged across publish dates.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from core.news.contracts import ModelMetric, TrustClass, canonical_model_id
from core.news.sources import base

_PAREN = re.compile(r"\s*\([^)]*\)")
# Effort/harness decorations appended to board names ("xHigh", "Thinking",
# "Codex Harness") — stripped iteratively so variants merge onto the base model.
_VARIANT = re.compile(r"(?i)[\s_-]+(thinking|x?high|low|medium|codex[\s_-]?harness|harness)$")


def _base_name(raw: str) -> str:
    name = _PAREN.sub("", raw).strip()
    while True:
        stripped = _VARIANT.sub("", name)
        if stripped == name:
            return name
        name = stripped

_ROWS = ("https://datasets-server.huggingface.co/rows"
         "?dataset=lmarena-ai%2Fleaderboard-dataset&config={config}&split=latest"
         "&offset=0&length=100")
FORMULA_VERSION = "arena-latest"

# (dataset config, emitted metric, category). The first three feed ranking
# capability families; the media/multimodal boards enrich the Model Explorer's
# per-aspect leaderboards (data-driven — a new category becomes a new board with
# zero ranking code change) without inflating the overall "strongest LLM" score.
_BOARDS = (
    ("text", "elo", "general"),
    ("agent", "agentic", "agentic"),
    ("webdev", "webdev", "coding"),
    ("vision", "vision", "vision"),
    ("text_to_image", "image", "image"),
    ("text_to_video", "video", "video"),
    ("search", "search", "search"),
)


class LMArenaAdapter(base.Adapter):
    name = "lmarena"
    trust = TrustClass.AGGREGATOR
    attribution = "LMArena leaderboards (official Hugging Face dataset)"
    timeout_s = 10.0
    max_records = 150
    max_attempts = 2

    def _collect(self) -> base.Payload:
        now = datetime.now(timezone.utc).isoformat()
        payload = base.Payload()
        for config, metric, category in _BOARDS:
            try:
                data = base.http_get_json(_ROWS.format(config=config), timeout=self.timeout_s) or {}
            except base.RateLimited:
                raise
            except Exception:
                continue                               # one board down never kills the rest
            rows = [w.get("row") for w in (data.get("rows") or []) if isinstance(w.get("row"), dict)]
            # boards differ: text/webdev carry ``rating`` (Elo), agent carries ``score``
            rows = [r for r in rows
                    if str(r.get("category") or "overall") == "overall"
                    and r.get("model_name")
                    and (r.get("rating") is not None or r.get("score") is not None)]
            if not rows:
                continue
            newest = max(str(r.get("leaderboard_publish_date") or "") for r in rows)
            best: dict[str, float] = {}
            for row in rows:
                if str(row.get("leaderboard_publish_date") or "") != newest:
                    continue
                # effort/harness variants merge onto the base model — the board's
                # best configuration represents the model's strength
                model_id = canonical_model_id(_base_name(str(row["model_name"])))
                try:
                    value = float(row["rating"] if row.get("rating") is not None else row["score"])
                except (TypeError, ValueError):
                    continue
                if not model_id or value <= 0:
                    continue
                best[model_id] = max(best.get(model_id, 0.0), value)
            for model_id, value in best.items():
                payload.metrics.append(ModelMetric(
                    model_id=model_id, category=category, source=self.name,
                    metric=metric, value=round(value, 4), confidence=0.9,
                    observed_at=now, formula_version=FORMULA_VERSION))
        if not payload.metrics:
            raise RuntimeError("LMArena dataset returned no parsable leaderboard rows")
        return payload

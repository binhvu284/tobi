"""News V2 source adapters (#23, N02) — one timeout- and record-bounded adapter per
external source (plan §3/§5). ``base`` owns the runner contract (bounds, retries,
rate-limit honesty, error redaction, partial-failure isolation); each sibling module
is one concrete adapter. All fetched content is untrusted evidence, never instructions.
"""
from core.news.sources.base import Adapter, AdapterResult, RateLimited, run_all

__all__ = ["Adapter", "AdapterResult", "RateLimited", "run_all"]

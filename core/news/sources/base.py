"""Adapter runner contract (#23, N02).

Every adapter declares its bounds up front — timeout, max records, attempts, trust,
attribution — and ``run()`` enforces them: bounded output, capped retries, honest
rate-limit reporting, and REDACTED errors (no tokens, no query strings). One adapter
failing must never poison another: ``run_all`` isolates each run so a tab refresh
degrades to partial success with all successful evidence retained (plan §5, N02 gate).
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

from core.news.contracts import (
    GitHubSnapshot, GitHubTrending, ModelMetric, ModelRelease, SourceRecord, TrustClass,
)


class RateLimited(RuntimeError):
    """The source said stop — surface it honestly; never work around or fabricate."""


@dataclass(frozen=True)
class AdapterResult:
    source: str
    ok: bool
    records: tuple = ()             # SourceRecord
    metrics: tuple = ()             # ModelMetric
    releases: tuple = ()            # ModelRelease
    github_snapshots: tuple = ()    # GitHubSnapshot
    github_trending: tuple = ()     # GitHubTrending (real period stars)
    rate_limited: bool = False
    error: str | None = None
    attempts: int = 0
    attribution: str = ""


@dataclass
class Payload:
    """What an adapter's ``_collect`` returns; the runner bounds and freezes it."""
    records: list = field(default_factory=list)
    metrics: list = field(default_factory=list)
    releases: list = field(default_factory=list)
    github_snapshots: list = field(default_factory=list)
    github_trending: list = field(default_factory=list)


_SECRET = re.compile(r"(?i)(bearer\s+\S+|token[=:\s]\S+|ghp_\w+|sk-\w+|key[=:]\S+)")
_QUERY = re.compile(r"\?\S*")


def redact(message: str) -> str:
    """Errors may quote URLs/headers — strip anything secret-shaped and query strings."""
    msg = _SECRET.sub("[redacted]", str(message))
    return _QUERY.sub("?[redacted]", msg)[:200]


# Some upstream WAFs tarpit/deny the python-requests default UA (live-verified:
# api.zeroeval.com hangs on "python-requests/*" but answers a plain product token
# instantly) — every adapter call identifies honestly as TOBI instead.
_USER_AGENT = "tobi-news/1.0"


def http_get_json(url: str, headers: dict | None = None, timeout: float = 8.0):
    """Single HTTP seam every adapter calls (tests monkeypatch this). Raises
    ``RateLimited`` on 429 / rate-limit 403; ``RuntimeError`` on other failures."""
    import requests
    resp = requests.get(url, headers={"User-Agent": _USER_AGENT, **(headers or {})}, timeout=timeout)
    if resp.status_code == 429 or (
            resp.status_code == 403 and resp.headers.get("X-RateLimit-Remaining") == "0"):
        raise RateLimited(f"rate limited: HTTP {resp.status_code}")
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}")
    return resp.json()


def http_get_text(url: str, headers: dict | None = None, timeout: float = 8.0) -> str:
    """Text twin of ``http_get_json`` for XML/RSS bodies — same seam contract
    (tests monkeypatch this), same rate-limit honesty."""
    import requests
    resp = requests.get(url, headers={"User-Agent": _USER_AGENT, **(headers or {})}, timeout=timeout)
    if resp.status_code == 429 or (
            resp.status_code == 403 and resp.headers.get("X-RateLimit-Remaining") == "0"):
        raise RateLimited(f"rate limited: HTTP {resp.status_code}")
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}")
    return resp.text


class Adapter:
    """Subclasses set the class attributes and implement ``_collect() -> Payload``.
    They must fetch through ``base.http_get_json`` and validate everything they emit
    through the contracts (a record that fails validation fails the adapter — bad
    data never rides along silently)."""

    name: str = ""
    trust: TrustClass = TrustClass.AGGREGATOR
    attribution: str = ""
    timeout_s: float = 8.0
    max_records: int = 50
    # Cap on emitted SourceRecords. Defaults to max_records; sources whose records span
    # several boards (GitHub: week + month + all-time) raise it so EVERY listed row still
    # has a ledger item to like/favourite (else late-board rows are truncated → no item_id).
    max_out_records: int | None = None
    max_attempts: int = 2
    retry_wait_s: float = 0.5

    def configured(self) -> tuple[bool, str]:
        """Override to declare required configuration (API keys). Returning
        ``(False, reason)`` makes the refresh SKIP this source honestly — a
        missing key is a setup task for the owner, never a failure."""
        return True, ""

    def _collect(self) -> Payload:  # pragma: no cover — abstract
        raise NotImplementedError

    def run(self) -> AdapterResult:
        """Never raises. Bounded, retried, redacted."""
        last_error: str | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                payload = self._collect()
                for rec in payload.records:
                    if not isinstance(rec, SourceRecord):
                        raise RuntimeError(f"{self.name} emitted a non-contract record")
                for group, cls in ((payload.metrics, ModelMetric), (payload.releases, ModelRelease),
                                   (payload.github_snapshots, GitHubSnapshot),
                                   (payload.github_trending, GitHubTrending)):
                    for row in group:
                        if not isinstance(row, cls):
                            raise RuntimeError(f"{self.name} emitted a non-contract {cls.__name__}")
                return AdapterResult(
                    source=self.name, ok=True, attempts=attempt, attribution=self.attribution,
                    records=tuple(payload.records[: (self.max_out_records or self.max_records)]),
                    metrics=tuple(payload.metrics[: self.max_records * 4]),
                    releases=tuple(payload.releases[: self.max_records]),
                    github_snapshots=tuple(payload.github_snapshots[: self.max_records]),
                    github_trending=tuple(payload.github_trending[: self.max_records * 2]),
                )
            except RateLimited as exc:
                return AdapterResult(source=self.name, ok=False, rate_limited=True,
                                     error=redact(str(exc)), attempts=attempt,
                                     attribution=self.attribution)
            except Exception as exc:  # transient or permanent — retry within bounds
                last_error = redact(str(exc) or exc.__class__.__name__)
                if attempt < self.max_attempts:
                    time.sleep(self.retry_wait_s)
        return AdapterResult(source=self.name, ok=False, error=last_error,
                             attempts=self.max_attempts, attribution=self.attribution)


def run_all(adapters: list) -> dict:
    """{adapter name → AdapterResult}. Each adapter is isolated: even a crashing
    ``run`` (broken subclass) yields a failed result while the rest proceed —
    partial success, never a failed tab (plan §5)."""
    results: dict = {}
    for adapter in adapters:
        name = getattr(adapter, "name", adapter.__class__.__name__) or adapter.__class__.__name__
        try:
            results[name] = adapter.run()
        except Exception as exc:
            results[name] = AdapterResult(source=name, ok=False, error=redact(str(exc)), attempts=1)
    return results

"""News V2 typed contracts (#23, N01) — pure, no DB, fully validated.

Every record that crosses a News V2 boundary (adapter → normalizer → repository →
ranking → API) is one of these frozen dataclasses; no unvalidated dict crosses a
boundary (same philosophy as ``core/brain_contracts.py``). Validation raises
``ValueError`` at construction so bad data fails at the seam it entered, not three
modules later.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# ── locked product constants (plan §1/§6/§9) ─────────────────────────────────────────
UNDO_SECONDS = 10          # dislike shows exactly 10 seconds of Undo
RETENTION_DAYS = 90        # untouched items expire; favorites/notes never do
EVENT_AGGREGATE_DAYS = 180  # settled events older than this may be aggregated away
FEED_MIN, FEED_MAX = 15, 40  # adaptive feed batch, server-bounded
EXCERPT_MAX = 500          # deterministic bounded excerpts — no LLM on page requests


class Tab(str, Enum):
    HOME = "home"
    TRENDING = "trending"
    FEED = "feed"
    FAVORITES = "favorites"


# Tabs that own a refresh schedule. Favorites is durable owner data: no schedule, ever.
REFRESHABLE_TABS = (Tab.HOME, Tab.TRENDING, Tab.FEED)


class ItemType(str, Enum):
    ARTICLE = "article"
    SOCIAL = "social"
    REPO = "repo"
    TOOL = "tool"


class TrustClass(str, Enum):
    OFFICIAL = "official"          # provider blogs/RSS, official APIs
    VERIFIED_API = "verified_api"  # authenticated first-party APIs (GitHub REST, HN API)
    AGGREGATOR = "aggregator"      # RSS aggregators, GDELT, news APIs
    COMMUNITY = "community"        # Reddit, social


class Reaction(str, Enum):
    NONE = "none"
    LIKE = "like"
    DISLIKE = "dislike"


class EventAction(str, Enum):
    LIKE = "like"
    DISLIKE = "dislike"
    UNDO = "undo"
    FAVORITE = "favorite"
    UNFAVORITE = "unfavorite"
    NOTE = "note"
    OPEN = "open"
    DWELL = "dwell"


class JobState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PARTIAL = "partial"      # some sources failed; tab still refreshed (plan §5)
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


class Schedule(str, Enum):
    MANUAL = "manual"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


# Owner-toggleable cross-module context classes (plan §6) — nothing else may feed
# personalization: no raw transcripts, private files, tool output, unapproved memories.
CONTEXT_CLASSES = ("owner_interests", "project_topics", "chat_topics")


def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise ValueError(msg)


def _iso_or_none(value: str | None, name: str) -> None:
    if value is None:
        return
    try:
        datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be ISO-8601, got {value!r}")


_MODEL_ID_JUNK = re.compile(r"[^a-z0-9.+-]+")
_MODEL_ID_SUFFIX = re.compile(r":(free|extended|beta|nitro|floor|online)$")
# Reasoning-effort/harness variants of ONE model, not distinct models (owner rule:
# "just take gpt-5-6-sol, the value is the highest mode"). Benchmark sources list
# each mode separately (…-xhigh/-high/-medium/-low/-non-reasoning); they collapse
# into the base id so evidence merges instead of fragmenting the leaderboard.
_MODEL_ID_VARIANT = re.compile(
    r"-(?:codex-harness|harness|non-?reasoning|non-?thinking|thinking|xhigh|high|medium|low|minimal)$")


def canonical_model_id(raw: str) -> str:
    """Deterministic cross-source model identity: sources name the same model
    differently ("openai/gpt-5.4" / "GPT-5.4" / "gpt-5.4"), and rankings can only
    combine evidence when the id matches. Rule: last path segment, lowercase,
    routing-variant suffixes stripped, non [a-z0-9.+-] → '-', reasoning-effort
    variant suffixes collapsed into the base id. Imperfect matches simply stay
    separate rows — identities are never guessed beyond this rule."""
    slug = (raw or "").strip().lower().rsplit("/", 1)[-1]
    slug = _MODEL_ID_SUFFIX.sub("", slug)
    slug = _MODEL_ID_JUNK.sub("-", slug).strip("-.")
    while (m := _MODEL_ID_VARIANT.search(slug)):
        base = slug[: m.start()].rstrip("-.")
        if not any(ch.isdigit() for ch in base):
            break        # "mistral-medium" → a family name, not an effort variant
        slug = base
    return slug or (raw or "").strip().lower()


def _http_url(value: str, name: str) -> None:
    """N12 security gate (plan §11 "script URLs"): every URL that can become a link
    or fetch target must be plain http(s) — javascript:/data:/file: never enter the
    ledger, so the UI can render hrefs without per-render sanitization."""
    scheme = urlsplit((value or "").strip()).scheme.lower()
    if scheme not in ("http", "https"):
        raise ValueError(f"{name} must be an http(s) URL, got scheme {scheme!r}")


# ── canonical URL → dedupe hash (minimal seam; N02's normalizer builds on it) ────────
_TRACKING_PARAM = re.compile(r"^(utm_\w+|fbclid|gclid|ref|ref_src|s|si)$", re.IGNORECASE)


def canonical_url(url: str) -> str:
    """Deterministic canonical form: lowercase scheme/host, default ports and fragments
    stripped, tracking params removed, trailing slash normalized. Never raises on odd
    URLs — falls back to the stripped input so hashing stays total."""
    raw = (url or "").strip()
    if not raw:
        return ""
    try:
        parts = urlsplit(raw)
        scheme = (parts.scheme or "https").lower()
        host = (parts.hostname or "").lower()
        port = f":{parts.port}" if parts.port and parts.port not in (80, 443) else ""
        path = parts.path.rstrip("/") or "/"
        keep = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
                if not _TRACKING_PARAM.match(k)]
        query = urlencode(keep)
        return urlunsplit((scheme, host + port, path, query, ""))
    except ValueError:
        return raw


def url_hash(url: str) -> str:
    """sha256 of the canonical URL — the ``news_items.url_hash`` dedupe key."""
    return hashlib.sha256(canonical_url(url).encode("utf-8")).hexdigest()


def payload_hash(payload: object) -> str:
    """Stable hash of a raw source payload (dict/str) for change detection."""
    if isinstance(payload, (dict, list)):
        raw = json.dumps(payload, sort_keys=True, default=str)
    else:
        raw = str(payload or "")
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ── adapter output ───────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class SourceRecord:
    """One normalized record emitted by a source adapter (plan §3/§5). All content is
    untrusted evidence — never instructions."""
    source: str
    external_id: str
    url: str
    title: str
    item_type: ItemType
    trust: TrustClass
    observed_at: str
    published_at: str | None = None
    excerpt: str = ""
    engagement: int = 0
    author: str | None = None
    media_url: str | None = None
    raw_hash: str = ""

    def __post_init__(self) -> None:
        _require(bool(self.source.strip()), "source is required")
        _require(bool(self.external_id.strip()), "external_id is required")
        _require(bool(self.url.strip()), "url is required")
        _http_url(self.url, "url")
        if self.media_url is not None:
            _http_url(self.media_url, "media_url")
        _require(bool(self.title.strip()), "title is required")
        _require(isinstance(self.item_type, ItemType), "item_type must be ItemType")
        _require(isinstance(self.trust, TrustClass), "trust must be TrustClass")
        _require(self.engagement >= 0, "engagement must be >= 0")
        # a source with no summary may hand us None; that is missing data, not a
        # malformed record — it must not fail the whole ingest batch.
        _require(len(self.excerpt or "") <= EXCERPT_MAX, f"excerpt exceeds {EXCERPT_MAX} chars")
        _iso_or_none(self.observed_at, "observed_at")
        _iso_or_none(self.published_at, "published_at")


# ── interactions (plan §6) ───────────────────────────────────────────────────────────
@dataclass(frozen=True)
class InteractionEvent:
    """Append-only owner action. ``undo_until`` is required for dislike (the 10-second
    window) and forbidden otherwise; a reversal links back via ``reversed_by``."""
    item_id: int
    action: EventAction
    idempotency_key: str
    created_at: str
    undo_until: str | None = None
    payload: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require(self.item_id > 0, "item_id must be positive")
        _require(isinstance(self.action, EventAction), "action must be EventAction")
        _require(bool(self.idempotency_key.strip()), "idempotency_key is required")
        _iso_or_none(self.created_at, "created_at")
        _iso_or_none(self.undo_until, "undo_until")
        if self.action is EventAction.DISLIKE:
            _require(self.undo_until is not None, "dislike requires undo_until")
        else:
            _require(self.undo_until is None, f"{self.action.value} must not set undo_until")
        if self.action is EventAction.DWELL:
            ms = self.payload.get("ms")
            _require(isinstance(ms, int) and 0 < ms <= 30 * 60 * 1000,
                     "dwell payload.ms must be 1..1800000")


# ── refresh jobs (plan §3/§9; durable runtime lands in N03) ──────────────────────────
@dataclass(frozen=True)
class RefreshJob:
    tab: Tab
    state: JobState
    id: int | None = None
    lease_owner: str | None = None
    lease_until: str | None = None
    attempts: int = 0
    error: str | None = None
    checkpoints: dict = field(default_factory=dict)   # source → {state, cursor, fetched, error}
    metrics: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require(self.tab in REFRESHABLE_TABS, "favorites never refreshes")
        _require(isinstance(self.state, JobState), "state must be JobState")
        _require(self.attempts >= 0, "attempts must be >= 0")
        _iso_or_none(self.lease_until, "lease_until")


# ── GitHub star history (plan §5: growth ONLY from persisted snapshots) ──────────────
@dataclass(frozen=True)
class GitHubSnapshot:
    repo: str                 # owner/name
    snapshot_date: str        # YYYY-MM-DD (UTC)
    stars: int

    def __post_init__(self) -> None:
        _require(bool(self.repo.strip()) and "/" in self.repo, "repo must be owner/name")
        _require(bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", self.snapshot_date)),
                 "snapshot_date must be YYYY-MM-DD")
        _require(self.stars >= 0, "stars must be >= 0")


# ── GitHub REAL trending (owner: "fetch real data, not calculated itself") ───────────
# github.com/trending is GitHub's own authoritative trending list — it reports the
# actual stars gained this week/month, so we store that period number directly
# instead of deriving growth from our own star snapshots over time.
@dataclass(frozen=True)
class GitHubTrending:
    repo: str                 # owner/name
    window: str               # "week" | "month"
    rank: int                 # position on GitHub's trending page (1-based)
    period_stars: int         # REAL stars gained this window, per GitHub
    total_stars: int
    observed_at: str
    description: str | None = None
    language: str | None = None

    def __post_init__(self) -> None:
        _require(bool(self.repo.strip()) and "/" in self.repo, "repo must be owner/name")
        # week/month = real github.com/trending; all = real GitHub Search top-starred
        _require(self.window in ("week", "month", "all"), "window must be week|month|all")
        _require(self.rank >= 1, "rank must be >= 1")
        _require(self.period_stars >= 0 and self.total_stars >= 0, "star counts must be >= 0")
        _iso_or_none(self.observed_at, "observed_at")


# ── model evidence (plan §5/§6) ──────────────────────────────────────────────────────
@dataclass(frozen=True)
class ModelMetric:
    """One normalized metric observation. Never invented: every row carries its source,
    observation time, confidence, and the formula version that consumed it."""
    model_id: str
    category: str
    source: str
    metric: str
    value: float
    confidence: float
    observed_at: str
    formula_version: str

    def __post_init__(self) -> None:
        for name in ("model_id", "category", "source", "metric", "formula_version"):
            _require(bool(getattr(self, name).strip()), f"{name} is required")
        _require(0.0 <= self.confidence <= 1.0, "confidence must be within [0,1]")
        _iso_or_none(self.observed_at, "observed_at")


@dataclass(frozen=True)
class ModelRelease:
    """A release/update claim. Source URL + observed timestamp are REQUIRED evidence."""
    title: str
    source_url: str
    observed_at: str
    model_id: str | None = None
    released_at: str | None = None

    def __post_init__(self) -> None:
        _require(bool(self.title.strip()), "title is required")
        _require(bool(self.source_url.strip()), "source_url evidence is required")
        _http_url(self.source_url, "source_url")
        _iso_or_none(self.observed_at, "observed_at")
        _iso_or_none(self.released_at, "released_at")


# ── settings (plan §4/§6/§8) ─────────────────────────────────────────────────────────
@dataclass(frozen=True)
class NewsSettings:
    """Per-tab schedule + enabled sources + context-class toggles. Favorites carries no
    schedule by construction."""
    schedules: dict = field(default_factory=lambda: {
        Tab.HOME.value: Schedule.DAILY.value,
        Tab.TRENDING.value: Schedule.DAILY.value,
        Tab.FEED.value: Schedule.DAILY.value,
    })
    enabled_sources: tuple = ()
    context_classes: dict = field(default_factory=lambda: {c: False for c in CONTEXT_CLASSES})

    def __post_init__(self) -> None:
        allowed_tabs = {t.value for t in REFRESHABLE_TABS}
        _require(set(self.schedules) <= allowed_tabs,
                 f"schedules keys must be within {sorted(allowed_tabs)} (favorites has none)")
        allowed_scheds = {s.value for s in Schedule}
        for tab, sched in self.schedules.items():
            _require(sched in allowed_scheds, f"schedule for {tab} must be one of {sorted(allowed_scheds)}")
        _require(set(self.context_classes) <= set(CONTEXT_CLASSES),
                 f"context classes must be within {CONTEXT_CLASSES}")

    def to_json(self) -> str:
        return json.dumps({
            "schedules": dict(self.schedules),
            "enabled_sources": list(self.enabled_sources),
            "context_classes": dict(self.context_classes),
        }, sort_keys=True)

    @staticmethod
    def from_json(raw: str | None) -> "NewsSettings":
        if not raw:
            return NewsSettings()
        data = json.loads(raw)
        return NewsSettings(
            schedules=dict(data.get("schedules") or {}),
            enabled_sources=tuple(data.get("enabled_sources") or ()),
            context_classes=dict(data.get("context_classes") or {c: False for c in CONTEXT_CLASSES}),
        )


# ── opaque cursors (plan §7: stable snapshot pagination) ─────────────────────────────
def clamp_limit(limit: object) -> int:
    """Server-bounded adaptive batch: anything unparseable → FEED_MIN; otherwise clamped
    into [FEED_MIN, FEED_MAX]."""
    try:
        n = int(limit)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return FEED_MIN
    return max(FEED_MIN, min(FEED_MAX, n))


def encode_cursor(snapshot_id: int, position: int) -> str:
    _require(snapshot_id > 0 and position >= 0, "cursor parts must be non-negative (snapshot > 0)")
    raw = json.dumps({"s": snapshot_id, "p": position}, separators=(",", ":"))
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")


def decode_cursor(token: str) -> tuple[int, int]:
    """(snapshot_id, position). Raises ``ValueError`` on any malformed/forged token."""
    try:
        padded = token + "=" * (-len(token) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
        snapshot_id, position = int(data["s"]), int(data["p"])
    except (KeyError, TypeError, ValueError, binascii.Error, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid cursor: {token!r}") from exc
    _require(snapshot_id > 0 and position >= 0, "invalid cursor contents")
    return snapshot_id, position

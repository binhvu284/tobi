"""Shared owner_settings flag helper (queue #20, Step 0).

One place for every off/shadow/on, boolean, and string flag stored in the ``owner_settings``
key/value table — replacing six near-identical bespoke ``_ensure_settings/_get/_set`` copies
(chat_modes, premium_readers, terminal_engine, office_artifacts, chat_runtime, vault).

It also REPAIRS the table. The canonical schema (``core/database.py``) is wide —
``(key, value, updated_at)`` — but the bespoke helpers created it narrow ``(key, value)``.
``CREATE TABLE IF NOT EXISTS`` means whichever ran first on a fresh DB won, and a narrow
table makes ``PATCH /api/owner/settings`` (which writes ``updated_at``) fail with a 500.
``ensure_schema()`` additively adds the missing column so both shapes converge.

Contract: **reads never raise** (degrade to the default, like ``core/hermes_skills``);
**writes may raise** ``ValueError`` on an invalid enum value (preserving
``chat_runtime.set_runtime_mode``'s contract).
"""
from __future__ import annotations

from core.database import get_connection

# Byte-identical to core/database.py:1117-1120 so a fresh DB created here matches canonical.
_CANONICAL_DDL = ("CREATE TABLE IF NOT EXISTS owner_settings ("
                  "key TEXT PRIMARY KEY, value TEXT, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP)")

_TRUE = {"1", "true", "on", "yes"}
_FALSE = {"0", "false", "off", "no"}

# Known keys — documentation + a place to see every flag at a glance. `chat_runtime_v2` is
# legacy/un-namespaced and MUST NOT be renamed (the /api/chat/config contract depends on it);
# every new key uses a dotted namespace. `vault.active_slot.<NAME>` is dynamic and not listed.
KEYS = {
    "timezone": "owner timezone (seeded by database.py)",
    "chat_runtime_v2": "chat runtime v2 rollout — off|shadow|on (legacy key name)",
    "chat.mode_v2": "chat mode v2 rollout (bool)",
    "chat.premium_readers": "premium readers rollback (bool)",
    "terminal.mode": "terminal approval mode — plan|ask|accept|auto",
    "terminal.enabled": "terminal kill-switch (bool)",
    "office.v3_enabled": "Office V3 rollout (bool)",
    "brain.v2_enabled": "#20 Brain Memory V2 (bool, default off)",
    "brain.v2_shadow": "#20 Brain V2 shadow evaluation (bool, default off)",
    "architecture.v2_enabled": "#20 Architecture V2 viewer (bool, default off)",
    "developer.auto_queue": "continue with the next eligible Developer queue item after success (bool)",
    "developer.queue_order": "owner priority order for planned queue items (JSON int array)",
    "developer.queue_next": "queue item pinned in the Next slot (int as string, '' = none)",
    "news.v2_enabled": "#23 News Page V2 rollout (bool, default off — Explore V1 stays authoritative)",
    "news.v2_shadow": "#23 News V2 shadow collection — scheduled adapter refreshes build history while V1 UI stays live (bool, default off)",
}

# New #20 flags — fail closed (default off). Phase A does NOT read these; they are pre-
# registered here so Phase B (architecture) and the later Brain-V2 tasks can use them.
BRAIN_V2_ENABLED = "brain.v2_enabled"
BRAIN_V2_SHADOW = "brain.v2_shadow"
ARCHITECTURE_V2_ENABLED = "architecture.v2_enabled"

# #23 News Page V2 — fail closed (default off). `enabled` gates the V2 UI/API surface;
# `shadow` lets the scheduled N03 refresh jobs collect history (GitHub star snapshots
# need lead time) while Explore V1 remains the live page — mirrors brain.v2_shadow.
NEWS_V2_ENABLED = "news.v2_enabled"
NEWS_V2_SHADOW = "news.v2_shadow"


def ensure_schema(conn=None) -> None:
    """Create ``owner_settings`` (canonical wide shape) and additively add ``updated_at`` if a
    bespoke helper created it narrow. ``conn`` is optional so vault/office can pass their own
    connection (then the caller owns commit/close); otherwise a private connection is used."""
    own = conn is None
    conn = conn or get_connection()
    try:
        conn.execute(_CANONICAL_DDL)
        cols = {row[1] for row in conn.execute("PRAGMA table_info(owner_settings)")}
        if "updated_at" not in cols:
            # SQLite forbids a non-constant DEFAULT (CURRENT_TIMESTAMP) on ADD COLUMN, so add
            # it bare and stamp the value explicitly in every upsert below.
            conn.execute("ALTER TABLE owner_settings ADD COLUMN updated_at DATETIME")
        if own:
            conn.commit()
    finally:
        if own:
            conn.close()


def get_str(key: str, default: str = "") -> str:
    """Stored string value for ``key``, or ``default`` when unset/NULL. Never raises."""
    try:
        conn = get_connection()
        try:
            ensure_schema(conn)
            row = conn.execute("SELECT value FROM owner_settings WHERE key=?", (key,)).fetchone()
            return row[0] if row and row[0] is not None else default
        finally:
            conn.close()
    except Exception:
        return default


def set_str(key: str, value: str) -> str:
    """Upsert a string value (stamps ``updated_at``). Returns the stored value."""
    conn = get_connection()
    try:
        ensure_schema(conn)
        conn.execute(
            "INSERT INTO owner_settings (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=CURRENT_TIMESTAMP",
            (key, value),
        )
        conn.commit()
        return value
    finally:
        conn.close()


def get_bool(key: str, default: bool = False) -> bool:
    """Recognized truthy/falsey string → bool; unset or unrecognized → ``default``. Never raises."""
    raw = get_str(key, "").strip().lower()
    if raw in _TRUE:
        return True
    if raw in _FALSE:
        return False
    return default


def set_bool(key: str, enabled: bool) -> bool:
    """Store a bool as canonical ``"1"``/``"0"``. Returns the bool."""
    set_str(key, "1" if enabled else "0")
    return bool(enabled)


def get_enum(key: str, allowed: set, default: str) -> str:
    """Stored value if it is in ``allowed`` (case-insensitive), else ``default``. Never raises.
    Reproduces the fail-open reads (unknown/unset → default) the enum flags rely on."""
    val = get_str(key, default).strip().lower()
    return val if val in allowed else default


def set_enum(key: str, value: str, allowed: set) -> str:
    """Upsert an enum value. Raises ``ValueError`` when ``value`` is not in ``allowed``."""
    value = (value or "").strip().lower()
    if value not in allowed:
        raise ValueError(f"{key} must be one of {sorted(allowed)}")
    return set_str(key, value)


def all_flags() -> dict:
    """Every stored key→value (diagnostics). Never raises."""
    try:
        conn = get_connection()
        try:
            ensure_schema(conn)
            return {row[0]: row[1] for row in conn.execute("SELECT key, value FROM owner_settings")}
        finally:
            conn.close()
    except Exception:
        return {}


def brain_v2_mode() -> str:
    """Derived ``off|shadow|on`` from the two brain bools — the single place their precedence
    lives (``enabled`` wins over ``shadow``). Phase A does not call this; it is for Phase B / T01."""
    if get_bool(BRAIN_V2_ENABLED, False):
        return "on"
    if get_bool(BRAIN_V2_SHADOW, False):
        return "shadow"
    return "off"

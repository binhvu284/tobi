"""
PREMIUM READERS — TOBI Premium Ability (#14).

A thin policy layer between the chat stream request and the Conductor/model call.
It keeps the "what can TOBI read from this turn" logic in one place so the chat
route doesn't grow more tangled:

- **YouTube**: detect supported links in the message, fetch + compact transcripts,
  and build a labelled context block (or an honest unavailable notice).
- **Images**: a single honest fold-in note when images are attached but the chosen
  model can't see them (the route still owns the native-vision routing decision).

Everything degrades gracefully; nothing here raises. A module flag lets the whole
layer be switched off for rollback without touching the route.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from core import youtube_reader

# Rollback flag [spec §Rollback]: safe built-in default (on). It is configuration-driven —
# an owner_settings row (key `chat.premium_readers`) overrides it at runtime without a code
# change; when no row is stored, this constant is the default (#14 follow-up).
ENABLE_PREMIUM_READERS = True

# Bound on how long transcript reading may block a chat turn. A slow/hanging fetch is
# abandoned past this deadline and the turn continues honestly without the transcript
# (the route wraps read_message in asyncio.wait_for with this value) (#14 follow-up).
READER_TIMEOUT_S = 25.0

_FLAG_KEY = "chat.premium_readers"


# ── config-driven rollback flag (owner_settings, same pattern as chat_modes) ──────
def _conn():
    from core.database import get_connection
    return get_connection()


def _ensure_settings(conn) -> None:
    conn.execute("CREATE TABLE IF NOT EXISTS owner_settings (key TEXT PRIMARY KEY, value TEXT)")


def _get_setting(key: str, default: str) -> str:
    try:
        conn = _conn()
        try:
            _ensure_settings(conn)
            row = conn.execute("SELECT value FROM owner_settings WHERE key=?", (key,)).fetchone()
            return row[0] if row and row[0] is not None else default
        finally:
            conn.close()
    except Exception:
        return default


def _set_setting(key: str, value: str) -> None:
    conn = _conn()
    try:
        _ensure_settings(conn)
        conn.execute(
            "INSERT INTO owner_settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        conn.commit()
    finally:
        conn.close()


def premium_readers_enabled() -> bool:
    """The rollback flag [spec §Rollback], config-driven via owner_settings (key
    ``chat.premium_readers``). Defaults to the ENABLE_PREMIUM_READERS constant, so no
    stored setting = the safe built-in default and toggling needs no code/schema change."""
    default = "1" if ENABLE_PREMIUM_READERS else "0"
    return _get_setting(_FLAG_KEY, default).strip().lower() not in ("0", "false", "off", "no")


def set_premium_readers(enabled: bool) -> bool:
    _set_setting(_FLAG_KEY, "1" if enabled else "0")
    return premium_readers_enabled()


@dataclass
class ReaderResult:
    youtube_context: str = ""                 # combined labelled transcript block(s)
    notices: list[str] = field(default_factory=list)  # honest reader failure notes
    youtube: list[dict] = field(default_factory=list)  # per-link chip state (for UI/log)
    used: bool = False                        # any reader processing happened this turn

    @property
    def any_available(self) -> bool:
        return any(y.get("available") for y in self.youtube)


def read_message(message: str, *, summarize: bool = True) -> ReaderResult:
    """Detect + read supported media referenced in the user's message. YouTube only in v1."""
    result = ReaderResult()
    if not premium_readers_enabled() or not message:
        return result
    urls = youtube_reader.find_youtube_urls(message)
    if not urls:
        return result
    result.used = True
    blocks: list[str] = []
    for url in urls:
        res = youtube_reader.read_youtube(url, summarize=summarize)
        result.youtube.append({
            "url": url, "video_id": res.video_id, "title": res.title,
            "state": res.chip_state(), "available": res.available, "reason": res.reason,
        })
        if res.available:
            block = youtube_reader.context_block(res)
            if block:
                blocks.append(block)
        else:
            # Prefix so the model states the honest limitation for this specific link.
            note = res.note if res.reason == "no_dependency" else f"{res.note} ({url})"
            result.notices.append(note)
    result.youtube_context = "\n\n".join(blocks)
    return result


def timeout_result(message: str) -> ReaderResult:
    """An honest 'reading timed out' result — used when the bounded reader deadline is hit,
    so the model and the UI both report the timeout instead of silently dropping the link
    (the abandoned executor thread's eventual result is discarded) (#14 follow-up)."""
    result = ReaderResult(used=True)
    for url in youtube_reader.find_youtube_urls(message or ""):
        result.youtube.append({
            "url": url, "video_id": youtube_reader.youtube_id_in(url), "title": None,
            "state": "timed out", "available": False, "reason": "timeout",
        })
    result.notices.append("Reading the YouTube transcript took too long, so I answered "
                          "without it. Ask me to try again if you'd like.")
    return result


def image_unavailable_note(count: int) -> str:
    """Honest fold-in note when images are attached but NO vision-capable model is connected
    at all (the chat auto-borrows one when available, so this only fires as a last resort)."""
    return (f"[{count} image(s) attached, but no vision-capable model is connected — add a "
            "Claude, GPT-4o, or Gemini key in Integrations so I can read images, sir.]")


def compose_context(att_text: str | None, reader: ReaderResult,
                    image_note: str | None = None) -> str:
    """Combine existing attachment text + YouTube context + reader notices into the single
    context string the Conductor/vision path folds into the turn."""
    parts: list[str] = []
    if att_text:
        parts.append(att_text)
    if reader.youtube_context:
        parts.append(reader.youtube_context)
    if image_note:
        parts.append(image_note)
    if reader.notices:
        parts.append("[Reader notes — tell the owner honestly if a source couldn't be read]\n"
                     + "\n".join(f"- {n}" for n in reader.notices))
    return "\n\n".join(parts)


def notice_payload(reader: ReaderResult) -> dict:
    """The SSE `notice` payload for the chat UI's YouTube chip (compact, no transcript)."""
    return {
        "kind": "reader",
        "reader": "youtube",
        "items": [{"url": y["url"], "state": y["state"], "title": y.get("title")}
                  for y in reader.youtube],
    }

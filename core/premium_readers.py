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

# Rollback flag [spec §Rollback]: default on for local dev, flip to disable the layer.
ENABLE_PREMIUM_READERS = True


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
    if not ENABLE_PREMIUM_READERS or not message:
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


def image_unavailable_note(count: int) -> str:
    """Honest fold-in note when images are attached but the model isn't vision-capable."""
    return (f"[{count} image(s) attached, but the current model isn't vision-capable — "
            "switch to Claude / GPT-4o / Gemini to read them, sir.]")


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

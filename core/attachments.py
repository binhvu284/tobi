"""
ATTACHMENTS — Premium Chat (#8 P2).

Turns the chat's `+` menu uploads / pasted images into model-ready inputs:

- **Text-like** files (txt/md/code/json/csv/yaml…) and **PDFs** → extracted to plain
  **text**, folded into the turn as context for the normal Conductor tool-loop (works on
  every model).
- **Images** (paste + upload) → kept as data-URLs and sent **natively** to vision-capable
  models via ``model_router.vision_complete`` (graceful text note otherwise).

Each attachment from the client looks like:
  ``{"name", "mime", "kind": "text"|"image"|"pdf"|"file", "text"?: str, "data_url"?: str}``
"""
from __future__ import annotations

import base64
import logging
from typing import Optional

logger = logging.getLogger("tobi.attachments")

_MAX_PER_FILE = 12000   # chars of extracted text per attachment (keep prompts sane)
_MAX_TOTAL = 30000


def _decode_data_url(data_url: str) -> tuple[str, bytes]:
    """'data:<mime>;base64,<b64>' → (mime, raw bytes). Tolerates a bare base64 string."""
    mime = "application/octet-stream"
    b64 = data_url or ""
    if b64.startswith("data:"):
        head, _, payload = b64.partition(",")
        b64 = payload
        if ";" in head and head[5:]:
            mime = head[5:head.index(";")] or mime
    try:
        return mime, base64.b64decode(b64)
    except Exception:
        return mime, b""


def _pdf_text(raw: bytes) -> str:
    try:
        import io
        try:
            from pypdf import PdfReader  # type: ignore
        except Exception:
            from PyPDF2 import PdfReader  # type: ignore
        reader = PdfReader(io.BytesIO(raw))
        return "\n".join((p.extract_text() or "") for p in reader.pages)
    except Exception as e:
        logger.info("PDF extract unavailable/failed: %s", e)
        return "[PDF received, but text extraction needs `pip install pypdf` — describe what you need, sir.]"


def is_image(att: dict) -> bool:
    return att.get("kind") == "image" or str(att.get("mime", "")).startswith("image/")


def extract_text(att: dict) -> str:
    """Extract plain text from one non-image attachment (text/code/pdf/file)."""
    name = att.get("name") or "file"
    kind = att.get("kind")
    if att.get("text"):
        body = str(att["text"])[:_MAX_PER_FILE]
        return f"--- {name} ---\n{body}"
    data_url = att.get("data_url")
    if not data_url:
        return f"--- {name} (empty) ---"
    mime, raw = _decode_data_url(data_url)
    if kind == "pdf" or mime == "application/pdf" or name.lower().endswith(".pdf"):
        return f"--- {name} (PDF) ---\n{_pdf_text(raw)[:_MAX_PER_FILE]}"
    # best-effort decode as utf-8 text
    try:
        return f"--- {name} ---\n{raw.decode('utf-8', errors='replace')[:_MAX_PER_FILE]}"
    except Exception:
        return f"--- {name} (binary, {len(raw)} bytes — can't read as text) ---"


def split(attachments: Optional[list[dict]]) -> tuple[list[dict], str]:
    """Partition attachments → (image_attachments, combined_text). Text is capped overall."""
    if not attachments:
        return [], ""
    images, texts, total = [], [], 0
    for att in attachments:
        if not isinstance(att, dict):
            continue
        if is_image(att):
            images.append(att)
            continue
        t = extract_text(att)
        if t and total < _MAX_TOTAL:
            texts.append(t[:_MAX_TOTAL - total])
            total += len(t)
    return images, "\n\n".join(texts)


def image_data_urls(images: list[dict]) -> list[str]:
    return [a["data_url"] for a in images if a.get("data_url")][:4]

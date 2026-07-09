"""Project v2 (#12) — Resources drive backend.

Disk-backed project files + online-link ingestion, tracked by Storage #10. Files live
under ``<data_dir>/projects/{project_id}/resources/`` (data_dir = the folder holding
agent.db, i.e. ~/.mmo_agent). Text is extracted where cheap (txt/md/code/csv/json, PDF
via pypdf, YouTube transcript, readable web) into ``pm_resources.text_content`` for
per-project search / RAG. Every optional dependency degrades gracefully.
"""
from __future__ import annotations

import os
import re
import base64
import mimetypes
from pathlib import Path
from urllib.parse import urlparse, parse_qs

MAX_FILE_BYTES = 100 * 1024 * 1024          # ~100 MB/file [D39]
MAX_TEXT_CHARS = 200_000                     # cap extracted text we store per resource
MAX_ICON_BYTES = 512 * 1024                  # custom project icon cap

# extension → (rtype, coarse category) for the curated per-type icon set [D51]
_EXT_RTYPE = {
    "md": "doc", "markdown": "doc", "txt": "doc", "rtf": "doc",
    "doc": "doc", "docx": "doc", "odt": "doc", "pages": "doc",
    "pdf": "pdf",
    "xls": "sheet", "xlsx": "sheet", "csv": "sheet", "ods": "sheet", "numbers": "sheet",
    "ppt": "slides", "pptx": "slides", "key": "slides", "odp": "slides",
    "png": "image", "jpg": "image", "jpeg": "image", "gif": "image", "webp": "image",
    "svg": "image", "bmp": "image", "heic": "image", "ico": "image",
    "mp4": "video", "mov": "video", "webm": "video", "mkv": "video", "avi": "video",
    "mp3": "audio", "wav": "audio", "m4a": "audio", "ogg": "audio", "flac": "audio",
    "zip": "archive", "rar": "archive", "7z": "archive", "tar": "archive", "gz": "archive",
    "json": "code", "yaml": "code", "yml": "code", "toml": "code", "xml": "code",
    "py": "code", "js": "code", "ts": "code", "tsx": "code", "jsx": "code",
    "go": "code", "rs": "code", "java": "code", "c": "code", "cpp": "code", "sh": "code",
}
_TEXT_EXT = {"md", "markdown", "txt", "rtf", "csv", "json", "yaml", "yml", "toml", "xml",
             "py", "js", "ts", "tsx", "jsx", "go", "rs", "java", "c", "cpp", "h", "sh", "log"}


def data_dir() -> Path:
    return Path(os.path.expanduser(os.getenv("DB_PATH", "~/.mmo_agent/agent.db"))).parent


def resources_root(project_id: int) -> Path:
    return data_dir() / "projects" / str(int(project_id)) / "resources"


def _safe_name(name: str) -> str:
    base = os.path.basename(name or "file").replace("\\", "_").replace("/", "_")
    base = re.sub(r"[^A-Za-z0-9._ \-()+]", "_", base).strip() or "file"
    return base[:180]


def ext_of(name: str) -> str:
    m = re.search(r"\.([A-Za-z0-9]{1,8})$", name or "")
    return m.group(1).lower() if m else ""


def rtype_for_ext(ext: str) -> str:
    return _EXT_RTYPE.get((ext or "").lower(), "file")


# ── disk-backed files ────────────────────────────────────────────────────────
def save_file(project_id: int, filename: str, content: bytes) -> dict:
    """Persist an uploaded file to the project's resources dir. Returns row fields."""
    if len(content) > MAX_FILE_BYTES:
        raise ValueError(f"file too large (> {MAX_FILE_BYTES // (1024*1024)} MB)")
    root = resources_root(project_id)
    root.mkdir(parents=True, exist_ok=True)
    name = _safe_name(filename)
    dest = root / name
    stem, ext = os.path.splitext(name)
    n = 1
    while dest.exists():                      # never clobber an existing file
        dest = root / f"{stem} ({n}){ext}"
        n += 1
    dest.write_bytes(content)
    e = ext_of(dest.name)
    return {
        "name": dest.name, "ext": e, "rtype": rtype_for_ext(e),
        "size_bytes": len(content), "disk_path": dest.name,
        "mime": mimetypes.guess_type(dest.name)[0] or "application/octet-stream",
        "text_content": _extract_text(dest, e, content),
    }


def abs_path(project_id: int, disk_path: str) -> Path | None:
    """Resolve a stored resource's absolute path, guarding against traversal."""
    if not disk_path:
        return None
    root = resources_root(project_id).resolve()
    p = (root / disk_path).resolve()
    try:
        p.relative_to(root)
    except ValueError:
        return None                            # escaped the resources root — refuse
    return p if p.exists() else None


def delete_file(project_id: int, disk_path: str) -> None:
    p = abs_path(project_id, disk_path)
    if p:
        try:
            p.unlink()
        except Exception:
            pass


def project_bytes(project_id: int) -> int:
    root = resources_root(project_id)
    if not root.exists():
        return 0
    total = 0
    for f in root.rglob("*"):
        if f.is_file():
            try:
                total += f.stat().st_size
            except Exception:
                pass
    return total


# ── text extraction (best-effort) ─────────────────────────────────────────────
def _extract_text(path: Path, ext: str, content: bytes) -> str | None:
    ext = (ext or "").lower()
    try:
        if ext in _TEXT_EXT:
            return content.decode("utf-8", errors="replace")[:MAX_TEXT_CHARS]
        if ext == "pdf":
            try:
                from pypdf import PdfReader  # optional
                import io
                reader = PdfReader(io.BytesIO(content))
                txt = "\n".join((pg.extract_text() or "") for pg in reader.pages)
                return txt[:MAX_TEXT_CHARS] or None
            except Exception:
                return None
        if ext == "docx":
            try:
                import io, docx  # optional python-docx
                d = docx.Document(io.BytesIO(content))
                return "\n".join(p.text for p in d.paragraphs)[:MAX_TEXT_CHARS] or None
            except Exception:
                return None
    except Exception:
        return None
    return None


# ── online links ──────────────────────────────────────────────────────────────
_YT = re.compile(r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/)([A-Za-z0-9_\-]{11})")


def classify_url(url: str) -> tuple[str, str]:
    """(source, rtype) for an online link — drives icon + ingestion. [D42]"""
    u = (url or "").lower()
    host = urlparse(u).netloc
    if _YT.search(u):
        return "youtube", "youtube"
    if "docs.google.com/spreadsheets" in u:
        return "drive", "sheet"
    if "docs.google.com/presentation" in u:
        return "drive", "slides"
    if "docs.google.com/document" in u:
        return "drive", "doc"
    if "drive.google.com" in u:
        return "drive", "file"
    if "github.com" in host or "raw.githubusercontent.com" in host:
        return "github", "github"
    if u.endswith(".pdf"):
        return "pdf", "pdf"
    return "web", "web"


def youtube_id(url: str) -> str | None:
    m = _YT.search(url or "")
    return m.group(1) if m else None


def fetch_youtube_transcript(url: str) -> str | None:
    vid = youtube_id(url)
    if not vid:
        return None
    try:
        from youtube_transcript_api import YouTubeTranscriptApi  # optional
        parts = YouTubeTranscriptApi.get_transcript(vid)
        return " ".join(p.get("text", "") for p in parts)[:MAX_TEXT_CHARS] or None
    except Exception:
        return None


def fetch_readable(url: str) -> tuple[str | None, str | None]:
    """(title, text) from a web page — best effort, dependency-light HTML strip."""
    try:
        import requests
        r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0 TOBI"})
        if r.status_code != 200 or "html" not in r.headers.get("content-type", ""):
            return None, None
        html = r.text
        title = None
        mt = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
        if mt:
            title = re.sub(r"\s+", " ", mt.group(1)).strip()[:200]
        body = re.sub(r"(?is)<(script|style|noscript|head).*?</\1>", " ", html)
        body = re.sub(r"(?s)<[^>]+>", " ", body)
        body = re.sub(r"&[a-z]+;", " ", body)
        text = re.sub(r"\s+", " ", body).strip()
        return title, (text[:MAX_TEXT_CHARS] or None)
    except Exception:
        return None, None


def build_link(url: str, name: str | None = None) -> dict:
    """Prepare a link resource row from a URL, ingesting text where cheap. [D42–D44]"""
    url = (url or "").strip()
    source, rtype = classify_url(url)
    title = name
    text = None
    if source == "youtube":
        text = fetch_youtube_transcript(url)
        if not title:
            title = f"YouTube · {youtube_id(url) or 'video'}"
    elif source == "web":
        t, text = fetch_readable(url)
        if not title:
            title = t or urlparse(url).netloc or url
    if not title:
        title = (name or urlparse(url).path.rsplit("/", 1)[-1] or url)[:180] or url
    return {
        "kind": "link", "name": title, "ext": rtype_for_ext(ext_of(url)) and ext_of(url) or None,
        "source": source, "rtype": rtype, "url": url, "size_bytes": 0,
        "mime": None, "text_content": text,
    }


# ── icons ──────────────────────────────────────────────────────────────────────
def clean_icon_data_url(data_url: str) -> tuple[str, str]:
    """Validate a data: URL for a custom icon → (mime, base64). Raises on bad/oversize."""
    m = re.match(r"^data:(image/[A-Za-z0-9.+-]+);base64,(.+)$", data_url or "", re.S)
    if not m:
        raise ValueError("icon must be a base64 image data URL")
    mime, b64 = m.group(1), m.group(2)
    try:
        raw = base64.b64decode(b64, validate=True)
    except Exception:
        raise ValueError("invalid base64 image")
    if len(raw) > MAX_ICON_BYTES:
        raise ValueError(f"icon too large (> {MAX_ICON_BYTES // 1024} KB)")
    return mime, b64

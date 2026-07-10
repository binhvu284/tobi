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
import html
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
        if hasattr(YouTubeTranscriptApi, "get_transcript"):
            parts = YouTubeTranscriptApi.get_transcript(vid)          # classic (<1.0) static API
        else:
            parts = list(YouTubeTranscriptApi().fetch(vid))           # >=1.0 instance .fetch() API
        text = " ".join(p.get("text", "") if isinstance(p, dict) else getattr(p, "text", "")
                        for p in parts)
        return text[:MAX_TEXT_CHARS] or None
    except Exception:
        return None


def fetch_youtube_meta(url: str) -> dict:
    """Title + author from YouTube oEmbed (free, no API key). Best-effort."""
    vid = youtube_id(url)
    if not vid:
        return {}
    try:
        import requests
        r = requests.get(
            "https://www.youtube.com/oembed",
            params={"url": f"https://www.youtube.com/watch?v={vid}", "format": "json"},
            timeout=10, headers={"User-Agent": "Mozilla/5.0 TOBI"})
        if r.status_code == 200:
            d = r.json()
            return {"title": d.get("title"), "author": d.get("author_name")}
    except Exception:
        pass
    return {}


def fetch_gdrive_meta(url: str) -> str | None:
    """Best-effort title for public Google Docs / Sheets / Slides / Drive links."""
    try:
        import requests
        r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0 TOBI"}, allow_redirects=True)
        if r.status_code != 200:
            return None
        page = r.text
        # og:title meta tag is the most reliable for Google Docs
        m = re.search(r'<meta\s+property="og:title"\s+content="([^"]*)"', page, re.I)
        if m and m.group(1).strip():
            return html.unescape(m.group(1)).strip()[:200]
        # fall back to <title> — Google Docs titles often end with " - Google Docs/Sheets"
        m = re.search(r"<title[^>]*>(.*?)</title>", page, re.I | re.S)
        if m:
            raw = html.unescape(re.sub(r"\s+", " ", m.group(1))).strip()
            cleaned = re.sub(r"\s*[-–]\s*Google (Docs|Sheets|Slides|Drive|Presentations)\s*$", "", raw, flags=re.I)
            if cleaned:
                return cleaned[:200]
        return None
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
        yt_meta = fetch_youtube_meta(url)
        text = fetch_youtube_transcript(url)
        if not title:
            title = yt_meta.get("title") or f"YouTube · {youtube_id(url) or 'video'}"
    elif source == "drive":
        if not title:
            title = fetch_gdrive_meta(url)
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


# ── per-project content RAG (#12 v1.1) ────────────────────────────────────────
_CHUNK_SIZE = 900
_CHUNK_OVERLAP = 140


def chunk_text(text: str, size: int = _CHUNK_SIZE, overlap: int = _CHUNK_OVERLAP) -> list[str]:
    """Split `text` into overlapping chunks. Never raises."""
    text = (text or "").strip()
    if not text:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        piece = text[start:start + size]
        if piece.strip():
            chunks.append(piece)
        if start + size >= len(text):
            break
        start += size - overlap
    return chunks[:200]  # hard cap so one giant doc can't flood the table


def index_resource(resource_id: int, project_id: int, text: str | None) -> int:
    """(Re)build the RAG chunks for one resource. Returns the number of chunks stored.

    fastembed is optional — when unavailable chunks are still stored without
    embeddings, so keyword search keeps working.
    """
    from core.database import get_connection
    from core import embeddings as emb
    chunks = chunk_text(text or "")
    conn = get_connection()
    try:
        conn.execute("DELETE FROM pm_resource_chunks WHERE resource_id=?", (int(resource_id),))
        if not chunks:
            conn.commit()
            return 0
        rows = []
        for i, c in enumerate(chunks):
            blob = None
            try:
                blob = emb.to_blob(emb.embed_one(c))
            except Exception:
                blob = None
            rows.append((int(resource_id), int(project_id), i, c, blob,
                         emb.MODEL_NAME if blob else None))
        conn.executemany(
            "INSERT INTO pm_resource_chunks (resource_id, project_id, ordinal, chunk_text, embedding, embed_model) "
            "VALUES (?,?,?,?,?,?)", rows)
        conn.commit()
        return len(rows)
    finally:
        conn.close()


def drop_resource(resource_id: int) -> None:
    """Drop all RAG chunks for a resource (call on delete). Best-effort."""
    from core.database import get_connection
    try:
        conn = get_connection()
        conn.execute("DELETE FROM pm_resource_chunks WHERE resource_id=?", (int(resource_id),))
        conn.commit()
        conn.close()
    except Exception:
        pass


def search_resources(project_id: int, query: str, k: int = 6) -> list[dict]:
    """Semantic (fastembed) + keyword fallback search across a project's resources.

    Returns up to `k` hits: ``{resource_id, name, score, snippet}`` deduped by resource.
    """
    from core.database import get_connection
    from core import embeddings as emb
    q = (query or "").strip()
    if not q:
        return []
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT c.id, c.resource_id, c.chunk_text, r.name "
            "FROM pm_resource_chunks c JOIN pm_resources r ON r.id = c.resource_id "
            "WHERE c.project_id=?", (int(project_id),)).fetchall()
    finally:
        conn.close()
    if not rows:
        return []

    qvec = None
    try:
        qvec = emb.embed_one(q)
    except Exception:
        qvec = None

    scored: dict[int, dict] = {}
    if qvec is not None:
        cands = []
        for r in rows:
            v = emb.from_blob(r["embedding"]) if r["embedding"] else None
            if v is not None:
                cands.append((r["id"], v))
        if cands:
            for cid, score in emb.cosine_topk(qvec, cands, k=len(cands), min_score=0.12):
                row = next(x for x in rows if x["id"] == cid)
                rid = row["resource_id"]
                if rid not in scored or score > scored[rid]["score"]:
                    scored[rid] = {"resource_id": rid, "name": row["name"],
                                   "score": round(float(score), 3), "snippet": _snippet(row["chunk_text"], q)}

    # keyword fallback / supplement (also covers the no-embeddings case)
    ql = q.lower()
    tokens = [t for t in re.split(r"\s+", ql) if len(t) > 2]
    for r in rows:
        rid = r["resource_id"]
        hay = (r["chunk_text"] or "").lower()
        if any(t in hay for t in tokens):
            sc = 0.35 if qvec is None else 0.15
            if rid not in scored:
                scored[rid] = {"resource_id": rid, "name": r["name"],
                               "score": sc, "snippet": _snippet(r["chunk_text"], q)}

    return sorted(scored.values(), key=lambda x: x["score"], reverse=True)[:k]


def _snippet(text: str, query: str, width: int = 180) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    idx = text.lower().find((query or "").lower())
    if idx < 0:
        return text[:width] + ("…" if len(text) > width else "")
    start = max(0, idx - 40)
    return ("…" if start > 0 else "") + text[start:start + width] + ("…" if start + width < len(text) else "")

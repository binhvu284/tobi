"""News V2 media pipeline (#23, owner: "thumbnails / visual images for posts").

An article's image is fetched SERVER-SIDE, validated, and cached to disk so the
UI serves it from ``/media`` — the browser never calls a third-party image host
(privacy) and the strict CSP is satisfied. This is the ONLY component that pulls
remote image bytes, and it is SSRF-hardened:

- scheme must be http(s) (contract-validated);
- the host must resolve exclusively to PUBLIC unicast addresses — any private,
  loopback, link-local, reserved, or multicast address rejects the fetch, so an
  attacker-controlled ``media_url`` can never reach internal services;
- redirects are DISABLED (a 3xx to an internal host is simply skipped);
- the response must be a real ``image/*`` under a hard byte cap.

A failure is never fatal: the item just has no thumbnail (the card falls back to
its deterministic gradient). Nothing here is presented as content — it is the
publisher's own image, cached.
"""
from __future__ import annotations

import hashlib
import ipaddress
import os
import socket
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

MAX_BYTES = 5 * 1024 * 1024                 # 5 MB — a thumbnail, never a payload
CONNECT_TIMEOUT_S = 6.0
CACHE_TTL_DAYS = 14
_ALLOWED_MIME = {
    "image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp",
    "image/gif": ".gif", "image/avif": ".avif",
}


def media_dir() -> Path:
    """Same directory the API's ``/media`` route serves from (derived from DB_PATH)."""
    db = os.getenv("DB_PATH") or ""
    base = Path(db).parent if db else Path.cwd()
    d = base / "news_media"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _host_is_public(host: str) -> bool:
    """True only if EVERY resolved address is a public unicast IP. Fail closed."""
    if not host:
        return False
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    if not infos:
        return False
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            return False
        if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
                or ip.is_multicast or ip.is_unspecified):
            return False
    return True


def _download(url: str) -> tuple[bytes, str] | None:
    """SSRF-guarded GET. Returns (bytes, mime) or None. Never raises."""
    parts = urlsplit(url)
    if parts.scheme.lower() not in ("http", "https"):
        return None
    if not _host_is_public(parts.hostname or ""):
        return None
    try:
        import requests
        resp = requests.get(url, timeout=CONNECT_TIMEOUT_S, allow_redirects=False,
                            stream=True, headers={"User-Agent": "tobi-news/1.0"})
        try:
            if resp.status_code != 200:                 # 3xx redirects are refused, not followed
                return None
            mime = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            if mime not in _ALLOWED_MIME:
                return None
            declared = resp.headers.get("Content-Length")
            if declared and declared.isdigit() and int(declared) > MAX_BYTES:
                return None
            chunks, total = [], 0
            for chunk in resp.iter_content(64 * 1024):
                total += len(chunk)
                if total > MAX_BYTES:                    # cap defends against lying Content-Length
                    return None
                chunks.append(chunk)
            data = b"".join(chunks)
            return (data, mime) if data else None
        finally:
            resp.close()
    except Exception:
        return None


def cache_image(conn: sqlite3.Connection, url: str, now: datetime | None = None) -> str | None:
    """Fetch + cache ``url``; return the local media key the UI serves, or None.
    Idempotent: a url already cached (and unexpired) returns its key without refetch."""
    from core.news.repository import _ensure_once
    _ensure_once(conn)
    now_dt = now or datetime.now(timezone.utc)
    url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()
    row = conn.execute("SELECT local_key, expires_at FROM news_media_cache WHERE url_hash=?",
                       (url_hash,)).fetchone()
    if row and (media_dir() / row[0]).is_file() and str(row[1]) > now_dt.isoformat():
        return row[0]
    got = _download(url)
    if not got:
        return None
    data, mime = got
    local_key = f"{url_hash[:40]}{_ALLOWED_MIME[mime]}"
    try:
        (media_dir() / local_key).write_bytes(data)
    except OSError:
        return None
    conn.execute(
        "INSERT INTO news_media_cache (url_hash, local_key, mime, bytes, expires_at)"
        " VALUES (?,?,?,?,?)"
        " ON CONFLICT(url_hash) DO UPDATE SET local_key=excluded.local_key, mime=excluded.mime,"
        " bytes=excluded.bytes, expires_at=excluded.expires_at",
        (url_hash, local_key, mime, len(data),
         (now_dt + timedelta(days=CACHE_TTL_DAYS)).isoformat()))
    return local_key

"""
CHAT ATTACHMENTS — durable storage for what the owner sends into a chat turn.

Before this module, an attachment lived exactly as long as one request: the browser read the
file into a data URL, `core.attachments` decoded it for the vision model, and the bytes were
dropped. The only trace left on the message was the literal text ``  📎×1``. Reopening the
session showed the count and nothing else.

Design decisions worth keeping:

* **Bytes live on disk, metadata lives in SQLite.** A screenshot is 0.5-3 MB. Putting that in
  the row (or in the message ``meta`` JSON) grows ``agent.db`` and drags every unrelated read
  that touches the row. The DB stays small and query-shaped; the files sit beside it.
* **The store is content-addressed.** The filename is the SHA-256 of the bytes, so pasting the
  same screenshot into ten turns writes one file and ten rows. Deleting one message never
  removes a file another message still points at.
* **The data directory follows the database.** It is derived from ``DB_PATH`` at call time, so
  the D:-drive rule and any future relocation hold without a second setting.
"""
from __future__ import annotations

import base64
import hashlib
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# A single attachment this big is refused; the owner gets a clear reason, not a truncated file.
MAX_BYTES = 12 * 1024 * 1024
_EXT = {
    "image/png": ".png", "image/jpeg": ".jpg", "image/jpg": ".jpg", "image/gif": ".gif",
    "image/webp": ".webp", "image/bmp": ".bmp", "image/svg+xml": ".svg",
    "application/pdf": ".pdf", "text/plain": ".txt", "text/markdown": ".md",
}
_DATA_URL = re.compile(r"^data:([^;,]+)?(;base64)?,(.*)$", re.S)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def storage_root() -> Path:
    """`<the directory holding agent.db>/attachments`, created on demand."""
    from core.database import DB_PATH
    root = Path(DB_PATH).resolve().parent / "attachments"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _conn() -> sqlite3.Connection:
    from core.database import get_connection
    return get_connection()


def ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS chat_attachments ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " session_id INTEGER NOT NULL,"
        " message_id INTEGER,"
        " name TEXT NOT NULL,"
        " mime TEXT NOT NULL,"
        " kind TEXT NOT NULL,"
        " bytes INTEGER NOT NULL,"
        " sha256 TEXT NOT NULL,"
        " rel_path TEXT NOT NULL,"
        " created_at TEXT NOT NULL)"
    )
    # the two reads this table serves: one session's files, and one message's files
    conn.execute("CREATE INDEX IF NOT EXISTS idx_chat_att_session ON chat_attachments(session_id, id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_chat_att_message ON chat_attachments(message_id)")


def _decode(data_url: str) -> tuple[str, bytes]:
    """`(mime, raw)` from a data URL. Raises ValueError on anything malformed."""
    m = _DATA_URL.match((data_url or "").strip())
    if not m:
        raise ValueError("not a data URL")
    mime = (m.group(1) or "application/octet-stream").strip()
    payload = m.group(3)
    raw = base64.b64decode(payload, validate=False) if m.group(2) else payload.encode("utf-8")
    return mime, raw


def _safe_name(name: str) -> str:
    name = os.path.basename((name or "file").strip()) or "file"
    name = re.sub(r"[^A-Za-z0-9._ -]+", "_", name)
    return name[:120]


def save_many(session_id: int, message_id: Optional[int], attachments: list[dict]) -> list[dict]:
    """Persist one turn's attachments. Returns the stored rows; unreadable items are skipped
    rather than failing the turn - a chat answer must not be lost because a file was odd."""
    if not attachments:
        return []
    root = storage_root()
    out: list[dict] = []
    conn = _conn()
    try:
        ensure_table(conn)
        for att in attachments:
            try:
                data_url = att.get("data_url")
                if data_url:
                    mime, raw = _decode(data_url)
                else:
                    text = att.get("text")
                    if text is None:
                        continue                      # nothing durable was sent
                    mime, raw = att.get("mime") or "text/plain", str(text).encode("utf-8")
                if not raw or len(raw) > MAX_BYTES:
                    continue
                sha = hashlib.sha256(raw).hexdigest()
                ext = _EXT.get(mime.lower(), os.path.splitext(att.get("name") or "")[1] or ".bin")
                rel = f"{sha[:2]}/{sha}{ext}"
                path = root / rel
                if not path.exists():                 # content-addressed: identical bytes, one file
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(raw)
                cur = conn.execute(
                    "INSERT INTO chat_attachments"
                    " (session_id, message_id, name, mime, kind, bytes, sha256, rel_path, created_at)"
                    " VALUES (?,?,?,?,?,?,?,?,?)",
                    (session_id, message_id, _safe_name(att.get("name") or "file"), mime,
                     att.get("kind") or ("image" if mime.startswith("image/") else "file"),
                     len(raw), sha, rel, _now()),
                )
                out.append({
                    "id": cur.lastrowid, "session_id": session_id, "message_id": message_id,
                    "name": _safe_name(att.get("name") or "file"), "mime": mime,
                    "kind": att.get("kind") or ("image" if mime.startswith("image/") else "file"),
                    "bytes": len(raw),
                })
            except Exception:
                continue                              # one bad file never costs the turn
        conn.commit()
    finally:
        conn.close()
    return out


def _rows(where: str, params: tuple) -> list[dict]:
    conn = _conn()
    try:
        ensure_table(conn)
        cur = conn.execute(
            "SELECT id, session_id, message_id, name, mime, kind, bytes, created_at"
            f" FROM chat_attachments WHERE {where} ORDER BY id", params)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
    finally:
        conn.close()


def list_for_session(session_id: int) -> list[dict]:
    """Every file sent in one session, oldest first. Powers the session files panel."""
    return _rows("session_id=?", (session_id,))


def get(attachment_id: int) -> Optional[dict]:
    """Metadata plus the absolute path, or None. The path is checked before it is handed back,
    so a row whose file was removed reads as missing instead of serving a 500."""
    conn = _conn()
    try:
        ensure_table(conn)
        row = conn.execute(
            "SELECT id, session_id, message_id, name, mime, kind, bytes, rel_path, created_at"
            " FROM chat_attachments WHERE id=?", (attachment_id,)).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    path = storage_root() / row[7]
    if not path.is_file():
        return None
    return {"id": row[0], "session_id": row[1], "message_id": row[2], "name": row[3],
            "mime": row[4], "kind": row[5], "bytes": row[6], "path": str(path),
            "created_at": row[8]}


def delete_for_session(session_id: int) -> int:
    """Drop a session's rows, and any file no remaining row still references."""
    conn = _conn()
    try:
        ensure_table(conn)
        gone = [r[0] for r in conn.execute(
            "SELECT rel_path FROM chat_attachments WHERE session_id=?", (session_id,))]
        cur = conn.execute("DELETE FROM chat_attachments WHERE session_id=?", (session_id,))
        conn.commit()
        root = storage_root()
        for rel in set(gone):
            still = conn.execute(
                "SELECT 1 FROM chat_attachments WHERE rel_path=? LIMIT 1", (rel,)).fetchone()
            if not still:
                try:
                    (root / rel).unlink(missing_ok=True)
                except OSError:
                    pass
        return cur.rowcount or 0
    finally:
        conn.close()

"""
CHAT STORE — Premium Chat (#8 P1).

DB-backed chat **sessions** (auto-title, rename, delete, per-session model) and their
**messages** (with parent_id for P2 branching, model + token bookkeeping, and an optional
collapsed `thinking` trace). The UI reads sessions/messages from here; the Conductor keeps
its own short rolling context in `conversations`, so this is the durable, richer store.

Each session maps to a stable negative ``chat_id`` so the Conductor's per-conversation
state (pending high-risk actions, rolling history) is naturally isolated per session
without colliding with the dashboard chat (990001) or positive Telegram ids.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Optional

_SESSION_CHAT_BASE = -200000  # session_id N → chat_id (-200000 - N), a private negative space


def chat_id_for_session(session_id: int) -> int:
    return _SESSION_CHAT_BASE - int(session_id)


def _conn() -> sqlite3.Connection:
    from core.database import get_connection
    return get_connection()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS chat_sessions (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            title      TEXT,
            model      TEXT,                       -- 'provider:model' or NULL (use default)
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS chat_messages (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
            role       TEXT NOT NULL,              -- user | assistant
            content    TEXT NOT NULL,
            parent_id  INTEGER,                    -- branching (P2); NULL = linear
            model      TEXT,
            tokens     INTEGER,
            thinking   TEXT,                       -- collapsed reasoning / tool trace
            feedback   INTEGER,                    -- 1 = 👍, -1 = 👎, NULL = none (P2)
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat_messages(session_id, id);
        """
    )
    # migrate older installs that predate the feedback column
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(chat_messages)").fetchall()}
        if "feedback" not in cols:
            conn.execute("ALTER TABLE chat_messages ADD COLUMN feedback INTEGER")
    except Exception:
        pass


def _with_conn(fn):
    conn = _conn()
    try:
        ensure_schema(conn)
        return fn(conn)
    finally:
        conn.close()


# ── sessions ────────────────────────────────────────────────────────────────
def list_sessions() -> list[dict]:
    def q(conn):
        rows = conn.execute(
            "SELECT s.id, s.title, s.model, s.created_at, s.updated_at, "
            "(SELECT COUNT(*) FROM chat_messages m WHERE m.session_id=s.id) AS message_count "
            "FROM chat_sessions s ORDER BY s.updated_at DESC, s.id DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    return _with_conn(q)


def create_session(title: Optional[str] = None, model: Optional[str] = None) -> dict:
    def q(conn):
        cur = conn.execute(
            "INSERT INTO chat_sessions (title, model, created_at, updated_at) VALUES (?,?,?,?)",
            (title or "New chat", model, _now(), _now()),
        )
        sid = cur.lastrowid
        conn.commit()
        row = conn.execute("SELECT * FROM chat_sessions WHERE id=?", (sid,)).fetchone()
        return dict(row)
    return _with_conn(q)


def get_session(session_id: int) -> Optional[dict]:
    def q(conn):
        row = conn.execute("SELECT * FROM chat_sessions WHERE id=?", (session_id,)).fetchone()
        return dict(row) if row else None
    return _with_conn(q)


def update_session(session_id: int, *, title: Optional[str] = None,
                   model: Optional[str] = None) -> Optional[dict]:
    def q(conn):
        sets, vals = [], []
        if title is not None:
            sets.append("title=?"); vals.append(title.strip()[:120] or "New chat")
        if model is not None:
            # empty string clears the per-session model (falls back to the global default)
            sets.append("model=?"); vals.append(model or None)
        if sets:
            sets.append("updated_at=?"); vals.append(_now())
            vals.append(session_id)
            conn.execute(f"UPDATE chat_sessions SET {', '.join(sets)} WHERE id=?", vals)
            conn.commit()
        row = conn.execute("SELECT * FROM chat_sessions WHERE id=?", (session_id,)).fetchone()
        return dict(row) if row else None
    return _with_conn(q)


def delete_session(session_id: int) -> bool:
    def q(conn):
        conn.execute("DELETE FROM chat_messages WHERE session_id=?", (session_id,))
        conn.execute("DELETE FROM chat_sessions WHERE id=?", (session_id,))
        conn.commit()
        return True
    return _with_conn(q)


def touch_session(session_id: int) -> None:
    def q(conn):
        conn.execute("UPDATE chat_sessions SET updated_at=? WHERE id=?", (_now(), session_id))
        conn.commit()
    _with_conn(q)


# ── messages ────────────────────────────────────────────────────────────────
def get_messages(session_id: int, limit: int = 200) -> list[dict]:
    def q(conn):
        rows = conn.execute(
            "SELECT id, role, content, parent_id, model, tokens, thinking, feedback, created_at "
            "FROM chat_messages WHERE session_id=? ORDER BY id ASC LIMIT ?",
            (session_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]
    return _with_conn(q)


def set_feedback(message_id: int, value: Optional[int]) -> bool:
    """Thumbs up (1) / down (-1) / clear (None) on an assistant message."""
    def q(conn):
        conn.execute("UPDATE chat_messages SET feedback=? WHERE id=?", (value, message_id))
        conn.commit()
        return True
    return _with_conn(q)


def fork_session(session_id: int, before_message_id: int,
                 title: Optional[str] = None) -> Optional[dict]:
    """Branch: clone a session up to (but excluding) `before_message_id` into a NEW session,
    preserving the original. The caller then runs the edited turn in the fork. Returns the
    new session dict (with its messages already copied)."""
    def q(conn):
        src = conn.execute("SELECT * FROM chat_sessions WHERE id=?", (session_id,)).fetchone()
        if not src:
            return None
        new_title = title or (f"↳ {src['title']}" if src['title'] else "↳ branch")[:120]
        cur = conn.execute(
            "INSERT INTO chat_sessions (title, model, created_at, updated_at) VALUES (?,?,?,?)",
            (new_title, src["model"], _now(), _now()),
        )
        new_id = cur.lastrowid
        rows = conn.execute(
            "SELECT role, content, model, tokens, thinking FROM chat_messages "
            "WHERE session_id=? AND id < ? ORDER BY id ASC", (session_id, before_message_id),
        ).fetchall()
        for r in rows:
            conn.execute(
                "INSERT INTO chat_messages (session_id, role, content, model, tokens, thinking, created_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (new_id, r["role"], r["content"], r["model"], r["tokens"], r["thinking"], _now()),
            )
        conn.commit()
        return dict(conn.execute("SELECT * FROM chat_sessions WHERE id=?", (new_id,)).fetchone())
    return _with_conn(q)


def add_message(session_id: int, role: str, content: str, *, model: Optional[str] = None,
                tokens: Optional[int] = None, thinking: Optional[str] = None,
                parent_id: Optional[int] = None) -> int:
    def q(conn):
        cur = conn.execute(
            "INSERT INTO chat_messages (session_id, role, content, parent_id, model, tokens, thinking, created_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (session_id, role, content, parent_id, model, tokens, thinking, _now()),
        )
        conn.execute("UPDATE chat_sessions SET updated_at=? WHERE id=?", (_now(), session_id))
        conn.commit()
        return cur.lastrowid
    return _with_conn(q)


def recent_history(session_id: int, limit: int = 8) -> list[dict]:
    """The last few turns, oldest-first, as {role, content} — fed to the Conductor as
    conversation context. A compaction `summary` message is surfaced as a user-role
    context line so the model keeps the gist of the older, trimmed turns."""
    msgs = get_messages(session_id, limit=400)
    out = []
    for m in msgs:
        if not m["content"]:
            continue
        if m["role"] in ("user", "assistant"):
            out.append({"role": m["role"], "content": m["content"]})
        elif m["role"] == "summary":
            out.append({"role": "user", "content": f"[Summary of earlier conversation]\n{m['content']}"})
    return out[-limit:]


def compact_session(session_id: int, summary_text: str, keep: int = 6) -> Optional[list[dict]]:
    """Compaction: replace older turns with a single `summary` message while keeping the
    most recent `keep` turns verbatim. Returns the new message list, or None if there was
    nothing old enough to compact. The summary persists and feeds back as context."""
    def q(conn):
        rows = conn.execute(
            "SELECT id, role, content, model, tokens, thinking, feedback FROM chat_messages "
            "WHERE session_id=? ORDER BY id ASC", (session_id,)
        ).fetchall()
        msgs = [dict(r) for r in rows]
        if len(msgs) <= keep + 1:
            return None
        recent = msgs[-keep:]
        # rebuild the message list: one summary, then the recent turns (preserves order via ids)
        conn.execute("DELETE FROM chat_messages WHERE session_id=?", (session_id,))
        conn.execute(
            "INSERT INTO chat_messages (session_id, role, content, created_at) VALUES (?,?,?,?)",
            (session_id, "summary", (summary_text or "").strip()[:6000], _now()),
        )
        for m in recent:
            conn.execute(
                "INSERT INTO chat_messages (session_id, role, content, model, tokens, thinking, feedback, created_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (session_id, m["role"], m["content"], m["model"], m["tokens"], m["thinking"], m["feedback"], _now()),
            )
        conn.execute("UPDATE chat_sessions SET updated_at=? WHERE id=?", (_now(), session_id))
        conn.commit()
        new_rows = conn.execute(
            "SELECT id, role, content, parent_id, model, tokens, thinking, feedback, created_at "
            "FROM chat_messages WHERE session_id=? ORDER BY id ASC", (session_id,)
        ).fetchall()
        return [dict(r) for r in new_rows]
    return _with_conn(q)


def older_messages_text(session_id: int, keep: int = 6) -> str:
    """The transcript of the turns that *would* be compacted (everything but the last
    `keep`), as plain text to summarize. Empty when there's nothing old enough."""
    msgs = get_messages(session_id, limit=400)
    if len(msgs) <= keep + 1:
        return ""
    older = msgs[:-keep]
    lines = []
    for m in older:
        who = "TOBI" if m["role"] == "assistant" else ("Summary" if m["role"] == "summary" else "Owner")
        lines.append(f"{who}: {m['content']}")
    return "\n".join(lines)[:16000]


def auto_title(session_id: int, first_user_message: str) -> str:
    """Derive a short title from the opening message (cheap heuristic — no LLM call).
    At most 5 words. Only applies while the session is still the placeholder 'New chat'."""
    sess = get_session(session_id)
    if not sess or (sess.get("title") or "").strip() not in ("", "New chat"):
        return sess.get("title") if sess else "New chat"
    words = (first_user_message or "").split()
    title = " ".join(words[:5])
    if len(words) > 5:
        title += "…"
    title = title[:60].rstrip() or "New chat"
    update_session(session_id, title=title)
    return title

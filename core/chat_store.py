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
        CREATE TABLE IF NOT EXISTS chat_artifacts (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            run_id     INTEGER,                    -- producing agent run (NULL for e.g. research)
            kind       TEXT NOT NULL,              -- task_result | research_report | terminal_output | source_cards
            title      TEXT,
            content    TEXT,                       -- markdown / JSON body
            meta_json  TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_chat_artifacts_session ON chat_artifacts(session_id, id);
        CREATE TABLE IF NOT EXISTS chat_session_summaries (
            session_id         INTEGER PRIMARY KEY REFERENCES chat_sessions(id) ON DELETE CASCADE,
            summary            TEXT NOT NULL,
            through_message_id INTEGER NOT NULL DEFAULT 0,
            updated_at         TEXT NOT NULL
        );
        """
    )
    # migrate older installs that predate the feedback / meta columns (additive only)
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(chat_messages)").fetchall()}
        if "feedback" not in cols:
            conn.execute("ALTER TABLE chat_messages ADD COLUMN feedback INTEGER")
        if "meta" not in cols:
            # #16: JSON turn metadata {mode, capabilities, steps, tools, run_id, artifact_ids, context}
            conn.execute("ALTER TABLE chat_messages ADD COLUMN meta TEXT")
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
            "SELECT id, role, content, parent_id, model, tokens, thinking, feedback, meta, created_at "
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
            "SELECT role, content, model, tokens, thinking, meta FROM chat_messages "
            "WHERE session_id=? AND id < ? ORDER BY id ASC", (session_id, before_message_id),
        ).fetchall()
        for r in rows:
            conn.execute(
                "INSERT INTO chat_messages (session_id, role, content, model, tokens, thinking, meta, created_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (new_id, r["role"], r["content"], r["model"], r["tokens"], r["thinking"], r["meta"], _now()),
            )
        conn.commit()
        return dict(conn.execute("SELECT * FROM chat_sessions WHERE id=?", (new_id,)).fetchone())
    return _with_conn(q)


def add_message(session_id: int, role: str, content: str, *, model: Optional[str] = None,
                tokens: Optional[int] = None, thinking: Optional[str] = None,
                parent_id: Optional[int] = None, meta: Optional[str] = None) -> int:
    def q(conn):
        cur = conn.execute(
            "INSERT INTO chat_messages (session_id, role, content, parent_id, model, tokens, thinking, meta, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (session_id, role, content, parent_id, model, tokens, thinking, meta, _now()),
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
    def summary_q(conn):
        row = conn.execute("SELECT summary,through_message_id FROM chat_session_summaries WHERE session_id=?",
                           (session_id,)).fetchone()
        return dict(row) if row else None
    rolling = _with_conn(summary_q)
    out = []
    for m in msgs:
        if not m["content"]:
            continue
        if m["role"] in ("user", "assistant"):
            out.append({"role": m["role"], "content": m["content"]})
        elif m["role"] == "summary":
            out.append({"role": "user", "content": f"[Summary of earlier conversation]\n{m['content']}"})
    if rolling and rolling.get("summary"):
        recent = [m for m in msgs if int(m.get("id") or 0) > int(rolling.get("through_message_id") or 0)]
        recent_out = []
        for m in recent:
            if m.get("content") and m.get("role") in ("user", "assistant"):
                recent_out.append({"role": m["role"], "content": m["content"]})
        return ([{"role": "user", "content": f"[Summary of earlier conversation]\n{rolling['summary']}"}]
                + recent_out[-max(1, limit - 1):])
    return out[-limit:]


def compact_session(session_id: int, summary_text: str, keep: int = 6) -> Optional[list[dict]]:
    """Persist a rolling summary without deleting the original conversation messages."""
    def q(conn):
        rows = conn.execute(
            "SELECT id, role, content, model, tokens, thinking, feedback, meta FROM chat_messages "
            "WHERE session_id=? ORDER BY id ASC", (session_id,)
        ).fetchall()
        msgs = [dict(r) for r in rows]
        if len(msgs) <= keep + 1:
            return None
        through_id = int(msgs[-keep - 1]["id"])
        conn.execute(
            "INSERT INTO chat_session_summaries(session_id,summary,through_message_id,updated_at) VALUES (?,?,?,?) "
            "ON CONFLICT(session_id) DO UPDATE SET summary=excluded.summary, "
            "through_message_id=excluded.through_message_id,updated_at=excluded.updated_at",
            (session_id, (summary_text or "").strip()[:6000], through_id, _now()),
        )
        conn.execute("UPDATE chat_sessions SET updated_at=? WHERE id=?", (_now(), session_id))
        conn.commit()
        # Preserve the historical return contract (summary + kept turns) for API/UI callers,
        # while the database retains every original row.
        recent = msgs[-keep:]
        virtual_summary = {"id": 0, "role": "summary", "content": (summary_text or "").strip()[:6000],
                           "parent_id": None, "model": None, "tokens": None, "thinking": None,
                           "feedback": None, "meta": None, "created_at": _now()}
        return [virtual_summary] + recent
    return _with_conn(q)


def older_messages_text(session_id: int, keep: int = 6) -> str:
    """The transcript of the turns that *would* be compacted (everything but the last
    `keep`), as plain text to summarize. Empty when there's nothing old enough."""
    msgs = get_messages(session_id, limit=400)
    def summary_q(conn):
        row = conn.execute("SELECT summary,through_message_id FROM chat_session_summaries WHERE session_id=?",
                           (session_id,)).fetchone()
        return dict(row) if row else None
    rolling = _with_conn(summary_q)
    through = int((rolling or {}).get("through_message_id") or 0)
    unsummarized = [m for m in msgs if int(m.get("id") or 0) > through]
    if len(unsummarized) <= keep + 1:
        return ""
    older = unsummarized[:-keep]
    lines = ([f"Previous summary: {rolling['summary']}"] if rolling and rolling.get("summary") else [])
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


# ── Artifacts (#16) — durable outputs a turn produces beyond the reply text ─────
# V1 kinds: task_result (agent runs), research_report (Deep Research). The shape is
# deliberately Canvas-ready (kind/title/content/meta) without building an editor [D22].

def add_artifact(session_id: int, kind: str, title: str, content: str,
                 run_id: Optional[int] = None, meta_json: Optional[str] = None) -> int:
    def q(conn):
        cur = conn.execute(
            "INSERT INTO chat_artifacts (session_id, run_id, kind, title, content, meta_json, created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (session_id, run_id, kind, (title or "").strip()[:200], content, meta_json, _now()),
        )
        conn.commit()
        return cur.lastrowid
    return _with_conn(q)


def list_artifacts(session_id: int, limit: int = 50) -> list[dict]:
    def q(conn):
        rows = conn.execute(
            "SELECT id, session_id, run_id, kind, title, meta_json, created_at "
            "FROM chat_artifacts WHERE session_id=? ORDER BY id DESC LIMIT ?",
            (session_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]   # content omitted from lists (can be large)
    return _with_conn(q)


def get_artifact(artifact_id: int) -> Optional[dict]:
    def q(conn):
        row = conn.execute("SELECT * FROM chat_artifacts WHERE id=?", (artifact_id,)).fetchone()
        return dict(row) if row else None
    return _with_conn(q)


# ── Cross-session search ──────────────────────────────────────────────────────

def search_all_messages(query: str = "", date_from: str = "", date_to: str = "",
                        role: str = "", limit: int = 50) -> list[dict]:
    """Unified search across ALL premium chat sessions AND Telegram/Brain conversations.

    Args:
      query: keyword filter (case-insensitive LIKE).
      date_from / date_to: YYYY-MM-DD bounds (inclusive).
      role: filter by role ('user', 'assistant').
      limit: cap results.

    Returns list of dicts sorted newest-first:
      {source, session_id, session_title, role, content, created_at}
    """
    results: list[dict] = []

    def _q(conn):
        sql = (
            "SELECT m.content, m.role, m.created_at, m.session_id, s.title "
            "FROM chat_messages m "
            "LEFT JOIN chat_sessions s ON m.session_id = s.id "
            "WHERE 1=1"
        )
        params: list = []
        if query:
            sql += " AND m.content LIKE ?"
            params.append(f"%{query}%")
        if date_from:
            sql += " AND date(m.created_at) >= ?"
            params.append(date_from)
        if date_to:
            sql += " AND date(m.created_at) <= ?"
            params.append(date_to)
        if role:
            sql += " AND m.role = ?"
            params.append(role)
        sql += " ORDER BY m.created_at DESC LIMIT ?"
        params.append(limit)
        return conn.execute(sql, params).fetchall()

    for r in _with_conn(_q):
        results.append({
            "source": "session",
            "session_id": r["session_id"],
            "session_title": r["title"] or f"Session #{r['session_id']}",
            "role": r["role"],
            "content": (r["content"] or "")[:500],
            "created_at": r["created_at"] or "",
        })

    # Also search the conversations table (Telegram + Brain + mirrored sessions)
    try:
        from core.database import search_conversations
        results.extend(search_conversations(
            query=query, date_from=date_from, date_to=date_to,
            role=role, limit=limit,
        ))
    except Exception:
        pass

    # Sort all by created_at DESC, cap at limit
    results.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return results[:limit]

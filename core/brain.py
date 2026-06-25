"""Brain engine — long-term owner memory (auto-learn + import + psychology profile).

Source of truth = SQLite (see core/database._ensure_brain_schema). This module owns
all Brain DB operations plus the LLM/embedding logic: extraction, hybrid routing,
import parsing, semantic dedup, retrieval, narrative synthesis, and the chat that
is wired to the Brain (summary + top-k retrieval).

Everything degrades gracefully: no embeddings → keyword search; no LLM key →
extraction/chat return a clear message instead of crashing.
"""
from __future__ import annotations

import json
import re
import logging
from datetime import datetime, timezone
from typing import Optional

from core.database import (
    get_connection, load_conversation_history, save_conversation_message,
)
from core import embeddings as emb

logger = logging.getLogger(__name__)

# ── Tunables ────────────────────────────────────────────────────────────────
DASHBOARD_CHAT_ID = 990001          # dedicated chat_id for the MC chat surface
AUTO_CONF_THRESHOLD = 0.7           # >= → auto-save (if not sensitive/conflict)
MERGE_THRESHOLD = 0.88              # cosine >= → auto-merge into existing
CONFLICT_MIN = 0.62                 # cosine in [min, merge) + same category → conflict
DUP_THRESHOLD = 0.86               # clean-duplicates grouping
STALE_DAYS = 90
CATEGORY_IDS = ["identity", "preferences", "psychology", "relationships",
                "goals", "work", "habits", "health"]


# ── llm helper (guarded) ─────────────────────────────────────────────────────
def _llm(prompt: str, system: Optional[str] = None, max_tokens: int = 800,
         task_type: str = "simple") -> Optional[str]:
    try:
        from core.model_router import llm_complete
        return llm_complete(prompt, task_type=task_type, system=system, max_tokens=max_tokens)
    except Exception as e:
        logger.warning("Brain LLM call failed: %s", e)
        return None


def _parse_json(text: Optional[str]):
    """Best-effort JSON extraction from an LLM reply (array or object)."""
    if not text:
        return None
    # strip code fences
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r"(\[.*\]|\{.*\})", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            return None
    return None


# ── categories ───────────────────────────────────────────────────────────────
def list_categories() -> list[dict]:
    conn = get_connection()
    rows = conn.execute("SELECT * FROM brain_categories ORDER BY sort_order, label").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _sensitive_set() -> set[str]:
    conn = get_connection()
    rows = conn.execute("SELECT id FROM brain_categories WHERE sensitive=1").fetchall()
    conn.close()
    return {r["id"] for r in rows}


def add_category(cid: str, label: str, color: str = "#58a6ff", icon: str = "Brain",
                 sensitive: int = 0, status: str = "pending") -> None:
    conn = get_connection()
    order = (conn.execute("SELECT COALESCE(MAX(sort_order),0)+1 FROM brain_categories").fetchone()[0])
    conn.execute(
        """INSERT OR IGNORE INTO brain_categories (id, label, color, icon, sort_order, sensitive, status)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (cid, label, color, icon, order, sensitive, status),
    )
    conn.commit()
    conn.close()


# ── memory row helpers ───────────────────────────────────────────────────────
def _stale(last_confirmed: Optional[str], created: Optional[str]) -> bool:
    ref = last_confirmed or created
    if not ref:
        return False
    try:
        dt = datetime.fromisoformat(ref.replace("Z", "")).replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).days >= STALE_DAYS
    except Exception:
        return False


def _row_to_dict(r) -> dict:
    d = dict(r)
    d.pop("embedding", None)
    d["has_embedding"] = bool(r["embedding"]) if "embedding" in r.keys() else False
    d["stale"] = _stale(d.get("last_confirmed_at"), d.get("created_at"))
    return d


def _add_version(conn, memory_id: int, content: str, category: str, confidence: float,
                 change_kind: str, changed_by: str) -> None:
    conn.execute(
        """INSERT INTO brain_memory_versions (memory_id, content, category, confidence, change_kind, changed_by)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (memory_id, content, category, confidence, change_kind, changed_by),
    )


def add_memory(content: str, category: str = "identity", confidence: float = 0.6,
               source: str = "manual", status: str = "active",
               context: Optional[str] = None, changed_by: str = "owner") -> int:
    vec = emb.embed_one(content)
    blob = emb.to_blob(vec)
    conn = get_connection()
    cur = conn.execute(
        """INSERT INTO brain_memories (content, category, confidence, source, status, context, embedding, embed_model, last_confirmed_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
        (content, category, confidence, source, status, context, blob,
         emb.MODEL_NAME if blob else None),
    )
    mid = cur.lastrowid
    _add_version(conn, mid, content, category, confidence, "create", changed_by)
    conn.commit()
    conn.close()
    return mid


def update_memory(mid: int, content: Optional[str] = None, category: Optional[str] = None,
                  confidence: Optional[float] = None, changed_by: str = "owner") -> Optional[dict]:
    conn = get_connection()
    row = conn.execute("SELECT * FROM brain_memories WHERE id=?", (mid,)).fetchone()
    if not row:
        conn.close()
        return None
    new_content = content if content is not None else row["content"]
    new_cat = category if category is not None else row["category"]
    new_conf = confidence if confidence is not None else row["confidence"]
    blob = row["embedding"]
    model = row["embed_model"]
    if content is not None and content != row["content"]:
        vec = emb.embed_one(new_content)
        if vec is not None:
            blob = emb.to_blob(vec)
            model = emb.MODEL_NAME
    conn.execute(
        """UPDATE brain_memories SET content=?, category=?, confidence=?, embedding=?, embed_model=?,
               updated_at=CURRENT_TIMESTAMP WHERE id=?""",
        (new_content, new_cat, new_conf, blob, model, mid),
    )
    _add_version(conn, mid, new_content, new_cat, new_conf, "edit", changed_by)
    conn.commit()
    out = conn.execute("SELECT * FROM brain_memories WHERE id=?", (mid,)).fetchone()
    conn.close()
    return _row_to_dict(out)


def delete_memory(mid: int) -> None:
    conn = get_connection()
    conn.execute(
        "UPDATE brain_memories SET status='archived', deleted_at=CURRENT_TIMESTAMP WHERE id=?",
        (mid,),
    )
    conn.commit()
    conn.close()


def confirm_memory(mid: int) -> Optional[dict]:
    conn = get_connection()
    row = conn.execute("SELECT * FROM brain_memories WHERE id=?", (mid,)).fetchone()
    if not row:
        conn.close()
        return None
    conn.execute("UPDATE brain_memories SET last_confirmed_at=CURRENT_TIMESTAMP WHERE id=?", (mid,))
    _add_version(conn, mid, row["content"], row["category"], row["confidence"], "confirm", "owner")
    conn.commit()
    out = conn.execute("SELECT * FROM brain_memories WHERE id=?", (mid,)).fetchone()
    conn.close()
    return _row_to_dict(out)


def get_memory(mid: int) -> Optional[dict]:
    conn = get_connection()
    row = conn.execute("SELECT * FROM brain_memories WHERE id=?", (mid,)).fetchone()
    conn.close()
    return _row_to_dict(row) if row else None


def list_versions(mid: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM brain_memory_versions WHERE memory_id=? ORDER BY created_at DESC", (mid,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def list_memories(category: Optional[str] = None, source: Optional[str] = None,
                  status: str = "active", q: Optional[str] = None,
                  stale: Optional[bool] = None, limit: int = 500) -> list[dict]:
    conn = get_connection()
    where = ["deleted_at IS NULL"]
    params: list = []
    if status and status != "all":
        where.append("status = ?")
        params.append(status)
    if category and category != "all":
        where.append("category = ?")
        params.append(category)
    if source and source != "all":
        where.append("source = ?")
        params.append(source)
    if q:
        where.append("content LIKE ?")
        params.append(f"%{q}%")
    sql = f"SELECT * FROM brain_memories WHERE {' AND '.join(where)} ORDER BY confidence DESC, updated_at DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    out = [_row_to_dict(r) for r in rows]
    if stale is True:
        out = [m for m in out if m["stale"]]
    return out


# ── embeddings / semantic ────────────────────────────────────────────────────
def _active_embeddings(exclude_id: Optional[int] = None) -> list[tuple[int, object]]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, embedding FROM brain_memories WHERE status='active' AND deleted_at IS NULL AND embedding IS NOT NULL"
    ).fetchall()
    conn.close()
    out = []
    for r in rows:
        if exclude_id is not None and r["id"] == exclude_id:
            continue
        out.append((r["id"], emb.from_blob(r["embedding"])))
    return out


def _best_match(content: str, exclude_id: Optional[int] = None) -> tuple[Optional[int], float]:
    qv = emb.embed_one(content)
    if qv is None:
        return None, 0.0
    ranked = emb.cosine_topk(qv, _active_embeddings(exclude_id), k=1)
    if not ranked:
        return None, 0.0
    return ranked[0][0], ranked[0][1]


def semantic_search(query: str, k: int = 12) -> list[dict]:
    qv = emb.embed_one(query)
    if qv is None:
        return list_memories(q=query, limit=k)  # keyword fallback
    ranked = emb.cosine_topk(qv, _active_embeddings(), k=k, min_score=0.25)
    if not ranked:
        return []
    ids = [cid for cid, _ in ranked]
    score = {cid: s for cid, s in ranked}
    conn = get_connection()
    rows = conn.execute(
        f"SELECT * FROM brain_memories WHERE id IN ({','.join('?' for _ in ids)})", ids
    ).fetchall()
    conn.close()
    out = [_row_to_dict(r) for r in rows]
    for m in out:
        m["score"] = round(score.get(m["id"], 0.0), 3)
    out.sort(key=lambda m: m["score"], reverse=True)
    return out


# ── pending / conflicts ──────────────────────────────────────────────────────
def list_pending() -> list[dict]:
    return list_memories(status="pending", limit=500)


def accept_pending(mid: int) -> Optional[dict]:
    conn = get_connection()
    row = conn.execute("SELECT * FROM brain_memories WHERE id=?", (mid,)).fetchone()
    if not row:
        conn.close()
        return None
    conn.execute("UPDATE brain_memories SET status='active', last_confirmed_at=CURRENT_TIMESTAMP WHERE id=?", (mid,))
    _add_version(conn, mid, row["content"], row["category"], row["confidence"], "confirm", "owner")
    conn.commit()
    conn.close()
    return get_memory(mid)


def reject_pending(mid: int) -> None:
    delete_memory(mid)


def _add_conflict(conn, memory_id: int, content: str, category: str, confidence: float,
                  source: str, reason: str) -> None:
    conn.execute(
        """INSERT INTO brain_conflicts (memory_id, candidate_content, candidate_category,
               candidate_confidence, candidate_source, reason) VALUES (?, ?, ?, ?, ?, ?)""",
        (memory_id, content, category, confidence, source, reason),
    )


def list_conflicts() -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        """SELECT c.*, m.content AS existing_content, m.category AS existing_category,
                  m.confidence AS existing_confidence
           FROM brain_conflicts c LEFT JOIN brain_memories m ON m.id = c.memory_id
           WHERE c.status='open' ORDER BY c.created_at DESC"""
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def resolve_conflict(cid: int, decision: str) -> None:
    """decision: keep_existing | use_candidate | keep_both"""
    conn = get_connection()
    c = conn.execute("SELECT * FROM brain_conflicts WHERE id=?", (cid,)).fetchone()
    if not c:
        conn.close()
        return
    conn.close()
    if decision == "use_candidate" and c["memory_id"]:
        # supersede existing, add candidate as a fresh active memory
        _supersede(c["memory_id"])
        add_memory(c["candidate_content"], c["candidate_category"] or "identity",
                   c["candidate_confidence"] or 0.6, c["candidate_source"] or "auto", "active")
    elif decision == "keep_both":
        add_memory(c["candidate_content"], c["candidate_category"] or "identity",
                   c["candidate_confidence"] or 0.6, c["candidate_source"] or "auto", "active")
    # keep_existing → just close
    conn = get_connection()
    conn.execute("UPDATE brain_conflicts SET status='resolved' WHERE id=?", (cid,))
    conn.commit()
    conn.close()


def _supersede(mid: int) -> None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM brain_memories WHERE id=?", (mid,)).fetchone()
    if row:
        conn.execute("UPDATE brain_memories SET status='superseded' WHERE id=?", (mid,))
        _add_version(conn, mid, row["content"], row["category"], row["confidence"], "supersede", "owner")
        conn.commit()
    conn.close()


def _confirm_raise(conn, mid: int, by: float = 0.05) -> None:
    row = conn.execute("SELECT confidence, content, category FROM brain_memories WHERE id=?", (mid,)).fetchone()
    if not row:
        return
    new_conf = min(1.0, (row["confidence"] or 0.6) + by)
    conn.execute("UPDATE brain_memories SET confidence=?, last_confirmed_at=CURRENT_TIMESTAMP WHERE id=?", (new_conf, mid))
    _add_version(conn, mid, row["content"], row["category"], new_conf, "merge", "auto")


# ── hybrid routing (the heart of auto-learn / import) ────────────────────────
def route_candidate(content: str, category: str, confidence: float, source: str) -> dict:
    """Apply the hybrid rule. Returns {action, memory_id?}."""
    content = (content or "").strip()
    if not content:
        return {"action": "skipped"}
    category = category if category in CATEGORY_IDS else "identity"
    best_id, score = _best_match(content)

    if best_id is not None and score >= MERGE_THRESHOLD:
        conn = get_connection()
        _confirm_raise(conn, best_id)
        conn.commit()
        conn.close()
        return {"action": "merged", "memory_id": best_id, "score": round(score, 3)}

    sensitive = category in _sensitive_set()

    if best_id is not None and CONFLICT_MIN <= score < MERGE_THRESHOLD:
        # similar-but-not-identical in the brain → let the owner resolve
        conn = get_connection()
        _add_conflict(conn, best_id, content, category, confidence, source,
                      f"Similar to an existing memory ({round(score*100)}% match)")
        conn.commit()
        conn.close()
        return {"action": "conflict", "memory_id": best_id, "score": round(score, 3)}

    if sensitive or confidence < AUTO_CONF_THRESHOLD:
        mid = add_memory(content, category, confidence, source, status="pending", changed_by="auto")
        return {"action": "pending", "memory_id": mid}

    mid = add_memory(content, category, confidence, source, status="active", changed_by="auto")
    return {"action": "active", "memory_id": mid}


# ── shared extraction guidance ───────────────────────────────────────────────
_CATEGORY_GUIDE = (
    "Categories — choose the single best fit for each card:\n"
    "- identity: who the owner is — name, age, location, nationality, languages, "
    "background, life roles, family status. e.g. 'Owner is based in Ho Chi Minh City, Vietnam.'\n"
    "- preferences: tastes, likes/dislikes, favoured tools or brands, and how they like "
    "to work or be communicated with. e.g. 'Owner prefers concise, direct answers.'\n"
    "- psychology: personality traits, motivations, fears, values, cognitive biases, "
    "emotional triggers, decision-making style, mental models. e.g. 'Owner is driven by "
    "autonomy and resists micromanagement.'\n"
    "- relationships: specific people in the owner's life (family, friends, colleagues, "
    "mentors) and the nature of those bonds.\n"
    "- goals: aspirations and objectives the owner is working toward, short or long term. "
    "e.g. 'Owner aims to launch his SaaS product this year.'\n"
    "- work: job, company, projects, business, professional responsibilities and tech "
    "stack. e.g. 'Owner builds with Next.js, React, TypeScript, Supabase and Vercel.'\n"
    "- habits: routines, schedules, rituals, recurring behaviours. e.g. 'Owner works late "
    "at night.'\n"
    "- health: physical or mental health, fitness, diet, sleep, medical context.\n"
)
_CONFIDENCE_GUIDE = (
    "Confidence: facts stated explicitly in the source -> 0.85-0.95; clearly implied -> "
    "0.7-0.85; your own inference or interpretation -> 0.5-0.7. If you are unsure which "
    "category fits, pick the most likely one and LOWER the confidence — never default "
    "everything to 'identity'."
)
_RULES = (
    "Rules:\n"
    "1. One atomic fact per card — never combine multiple facts into one.\n"
    "2. Rewrite each as a clean, self-contained third-person statement about the owner "
    "(start with 'Owner ' where natural). No markdown, pipes, bullets or asterisks.\n"
    "3. For tables, turn each meaningful row into a sentence (e.g. '| Location | Hanoi |' "
    "-> 'Owner is located in Hanoi.'); ignore header and separator rows.\n"
    "4. IGNORE document scaffolding entirely: titles, version numbers, dates, 'Purpose:', "
    "'Instruction to Agent:', section headers, generic instructions and meta commentary.\n"
    "5. Drop trivial, vague or low-value lines — keep only facts genuinely worth "
    "remembering long-term.\n"
)

# keyword safety net so an unknown category becomes a best guess, never silently 'identity'
_CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "health": ["sleep", "diet", "exercise", "fitness", "gym", "health", "anxiety",
               "weight", "medical", "workout", "mental health", "burnout"],
    "relationships": ["wife", "husband", "girlfriend", "boyfriend", "friend", "mother",
                      "father", "family", "colleague", "partner", "mentor", "brother",
                      "sister", "married", "son", "daughter"],
    "goals": ["goal", "aim", "wants to", "plans to", "aspire", "dream", "objective",
              "target", "wishes to", "ambition", "hopes to"],
    "work": ["work", "job", "company", "project", "stack", "founder", "startup",
             "business", "developer", "engineer", "client", "product manager", "saas"],
    "habits": ["every day", "daily", "routine", "usually", "habit", "morning", "nights",
               "weekly", "tends to", "ritual"],
    "psychology": ["fear", "motivat", "value", "believe", "personality", "introvert",
                   "extrovert", "bias", "trigger", "emotion", "mindset", "perfection",
                   "decision-making", "cognitive"],
    "preferences": ["prefer", "likes", "love", "favorite", "favourite", "enjoy",
                    "dislike", "hates", "rather"],
}


def _guess_category(content: str) -> str:
    low = content.lower()
    for cat, kws in _CATEGORY_KEYWORDS.items():
        if any(k in low for k in kws):
            return cat
    return "identity"


def _coerce_items(data) -> list[dict]:
    """Validate + normalize LLM card output; rescue bad categories with a best guess."""
    out: list[dict] = []
    if not isinstance(data, list):
        return out
    for it in data:
        if not isinstance(it, dict):
            continue
        content = str(it.get("content") or "").strip()
        if len(content) < 6:
            continue
        cat = it.get("category")
        conf = float(it.get("confidence", 0.6) or 0.6)
        if cat not in CATEGORY_IDS:
            cat = _guess_category(content)
            conf = min(conf, 0.55)
        out.append({
            "content": content,
            "category": cat,
            "confidence": max(0.05, min(1.0, conf)),
        })
    return out


# ── extraction (LLM) ─────────────────────────────────────────────────────────
_EXTRACT_SYS = (
    "You extract durable, atomic facts about the OWNER (the human user) from a "
    "conversation, for a personal assistant's long-term memory. Ignore transient/task "
    "chatter. Return STRICT JSON: an array of "
    '{"content": str, "category": str, "confidence": number}. Empty array if nothing '
    "durable.\n" + _RULES + _CATEGORY_GUIDE + _CONFIDENCE_GUIDE
)


def extract_from_messages(messages: list[dict]) -> list[dict]:
    if not messages:
        return []
    convo = "\n".join(f"{m.get('role','user')}: {m.get('content','')}" for m in messages)[:6000]
    raw = _llm(f"Conversation:\n{convo}\n\nExtract durable facts about the owner as a JSON array.",
               system=_EXTRACT_SYS, max_tokens=700, task_type="simple")
    return _coerce_items(_parse_json(raw))


# ── sweep (periodic background extraction) ───────────────────────────────────
def _sweep_state() -> int:
    conn = get_connection()
    row = conn.execute("SELECT last_processed_convo_id FROM brain_sweep_state WHERE id=1").fetchone()
    conn.close()
    return row["last_processed_convo_id"] if row else 0


def _set_sweep_state(last_id: int) -> None:
    conn = get_connection()
    conn.execute("UPDATE brain_sweep_state SET last_processed_convo_id=? WHERE id=1", (last_id,))
    conn.commit()
    conn.close()


def sweep_once(limit: int = 60) -> dict:
    """Process new conversation messages → extract → route. Idempotent via high-water mark."""
    last = _sweep_state()
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, role, content FROM conversations WHERE id > ? ORDER BY id ASC LIMIT ?",
        (last, limit),
    ).fetchall()
    conn.close()
    if not rows:
        return {"processed": 0, "active": 0, "pending": 0, "conflict": 0, "merged": 0}
    msgs = [{"role": r["role"], "content": r["content"]} for r in rows]
    max_id = rows[-1]["id"]
    candidates = extract_from_messages(msgs)
    tally = {"processed": len(rows), "active": 0, "pending": 0, "conflict": 0, "merged": 0, "skipped": 0}
    for c in candidates:
        res = route_candidate(c["content"], c["category"], c["confidence"], "auto")
        tally[res["action"]] = tally.get(res["action"], 0) + 1
    _set_sweep_state(max_id)
    return tally


# ── import ───────────────────────────────────────────────────────────────────
_IMPORT_SYS = (
    "You convert a personal-context document into atomic long-term memory cards about the "
    "OWNER for a personal assistant. Return STRICT JSON: an array of "
    '{"content": str, "category": str, "confidence": number}. Return [] if a chunk holds '
    "nothing durable.\n" + _RULES + _CATEGORY_GUIDE + _CONFIDENCE_GUIDE +
    "\nUse the SECTION heading provided with each chunk as a strong hint for categorization."
)

_META_RE = re.compile(
    r"^\s*(version\b|v\d+(\.\d+)*\b|purpose|instruction to agent|last updated|updated|"
    r"author|date|note|table of contents|overview|changelog)\s*[:\-—]?", re.I)


def _chunk_markdown(text: str, max_chars: int = 3500) -> list[tuple[str, str]]:
    """Split a doc into (section_heading, body) pieces so nothing is truncated."""
    chunks: list[tuple[str, str]] = []
    heading = ""
    buf: list[str] = []

    def flush() -> None:
        body = "\n".join(buf).strip()
        if body:
            chunks.append((heading, body))

    for ln in text.splitlines():
        m = re.match(r"^\s{0,3}#{1,6}\s+(.*)$", ln)
        if m:
            flush()
            buf = []
            heading = m.group(1).strip().strip("#").strip()
            continue
        buf.append(ln)
        if sum(len(x) + 1 for x in buf) >= max_chars:
            flush()
            buf = []
    flush()
    # no headings at all → size-based chunks so big plain docs still get fully processed
    if not chunks and text.strip():
        chunks = [("", text[i:i + max_chars]) for i in range(0, len(text), max_chars)]
    return chunks


def _naive_split(text: str) -> list[dict]:
    """No-LLM fallback: clean line/table split that skips scaffolding and table chrome."""
    out: list[dict] = []
    for line in text.splitlines():
        s = line.strip().lstrip(">").strip()    # drop blockquote markers first
        if not s or s.startswith("#") or _META_RE.match(s):
            continue
        if set(s) <= set("|-: "):           # table separator row
            continue
        if s.startswith("|"):               # table row → "Key: Value"
            cells = [c.strip(" *`") for c in s.strip("|").split("|")]
            cells = [c for c in cells if c]
            if not cells or cells[0].lower() in ("attribute", "value", "field", "key", "property"):
                continue
            s = f"{cells[0]}: {cells[1]}" if len(cells) >= 2 else cells[-1]
        s = s.strip("-*#> \t").strip()
        if len(s) >= 8:
            out.append({"content": s, "category": _guess_category(s), "confidence": 0.5})
    return out[:80]


def _dedup_candidates(items: list[dict]) -> list[dict]:
    """Collapse near-identical cards within one import; keep the highest-confidence copy."""
    kept: list[dict] = []
    vecs: list[object] = []
    use_emb = emb.is_available()
    for it in items:
        norm = re.sub(r"\s+", " ", it["content"].lower()).strip()
        v = emb.embed_one(it["content"]) if use_emb else None
        dup = -1
        for i, k in enumerate(kept):
            if re.sub(r"\s+", " ", k["content"].lower()).strip() == norm:
                dup = i
                break
            if v is not None and vecs[i] is not None and emb.cosine(v, vecs[i]) >= DUP_THRESHOLD:
                dup = i
                break
        if dup >= 0:
            if it["confidence"] > kept[dup]["confidence"]:
                kept[dup] = it
                vecs[dup] = v if v is not None else vecs[dup]
        else:
            kept.append(it)
            vecs.append(v)
    return kept


def parse_import(filename: str, text: str) -> list[dict]:
    """Parse .md/.json into atomic candidate cards: chunked, deduped, with merge hints."""
    text = text or ""
    items: list[dict] = []
    used_llm = False
    for heading, chunk in _chunk_markdown(text):
        prompt = (
            (f"SECTION: {heading}\n\n" if heading else "")
            + f"File: {filename}\n\nContent:\n{chunk}\n\nReturn the JSON array of memory cards."
        )
        raw = _llm(prompt, system=_IMPORT_SYS, max_tokens=1500, task_type="simple")
        if raw is not None:
            used_llm = True
        items.extend(_coerce_items(_parse_json(raw)))

    # Fallback: no LLM available → clean naive split (skips tables/meta/headers)
    if not used_llm and not items and text.strip():
        items = _naive_split(text)

    items = _dedup_candidates(items)

    # annotate overlap with existing memories as a merge SUGGESTION (never auto-applied)
    for it in items:
        bid, score = _best_match(it["content"])
        if bid is not None and score >= MERGE_THRESHOLD:
            it["merge_into"] = bid
            it["merge_score"] = round(score, 3)
    return items


def commit_import(filename: str, source_type: str, items: list[dict]) -> dict:
    saved, merged = 0, 0
    for it in items:
        content = (it.get("content") or "").strip()
        if not content:
            continue
        category = it.get("category") if it.get("category") in CATEGORY_IDS else "identity"
        confidence = float(it.get("confidence", 0.6) or 0.6)
        if it.get("merge_into"):
            conn = get_connection()
            _confirm_raise(conn, int(it["merge_into"]))
            conn.commit()
            conn.close()
            merged += 1
        else:
            add_memory(content, category, confidence, "import", status="active", changed_by="import")
            saved += 1
    conn = get_connection()
    conn.execute("INSERT INTO brain_imports (filename, source_type, card_count) VALUES (?, ?, ?)",
                 (filename, source_type, saved + merged))
    conn.commit()
    conn.close()
    return {"saved": saved, "merged": merged}


# ── duplicates (semantic) ────────────────────────────────────────────────────
def find_duplicates() -> list[dict]:
    cands = _active_embeddings()
    groups: list[list[int]] = []
    used: set[int] = set()
    for i, (idA, va) in enumerate(cands):
        if idA in used or va is None:
            continue
        group = [idA]
        for idB, vb in cands[i + 1:]:
            if idB in used or vb is None:
                continue
            if emb.cosine(va, vb) >= DUP_THRESHOLD:
                group.append(idB)
                used.add(idB)
        if len(group) > 1:
            used.update(group)
            groups.append(group)
    out = []
    if not groups:
        return out
    conn = get_connection()
    for g in groups:
        rows = conn.execute(
            f"SELECT id, content, category, confidence FROM brain_memories WHERE id IN ({','.join('?' for _ in g)})", g
        ).fetchall()
        out.append({"ids": g, "memories": [dict(r) for r in rows]})
    conn.close()
    return out


def merge_group(ids: list[int], keep_id: Optional[int] = None) -> dict:
    if not ids or len(ids) < 2:
        return {"merged": 0}
    conn = get_connection()
    rows = conn.execute(
        f"SELECT * FROM brain_memories WHERE id IN ({','.join('?' for _ in ids)})", ids
    ).fetchall()
    if not rows:
        conn.close()
        return {"merged": 0}
    if keep_id is None:
        keep_id = max(rows, key=lambda r: r["confidence"] or 0)["id"]
    merged = 0
    for r in rows:
        if r["id"] == keep_id:
            continue
        conn.execute("UPDATE brain_memories SET status='superseded' WHERE id=?", (r["id"],))
        _add_version(conn, r["id"], r["content"], r["category"], r["confidence"], "supersede", "owner")
        merged += 1
    keep = conn.execute("SELECT * FROM brain_memories WHERE id=?", (keep_id,)).fetchone()
    if keep:
        _confirm_raise(conn, keep_id)
    conn.commit()
    conn.close()
    return {"merged": merged, "kept": keep_id}


# ── retrieval / chat / narrative ─────────────────────────────────────────────
def retrieve(query: str, k: int = 6) -> list[dict]:
    return semantic_search(query, k=k)


def profile_summary(max_per_cat: int = 4) -> str:
    conn = get_connection()
    rows = conn.execute(
        """SELECT category, content FROM brain_memories
           WHERE status='active' AND deleted_at IS NULL
           ORDER BY confidence DESC, updated_at DESC LIMIT 80"""
    ).fetchall()
    conn.close()
    by: dict[str, list[str]] = {}
    for r in rows:
        by.setdefault(r["category"], [])
        if len(by[r["category"]]) < max_per_cat:
            by[r["category"]].append(r["content"])
    if not by:
        return ""
    parts = []
    for cat in CATEGORY_IDS:
        if by.get(cat):
            parts.append(f"{cat.upper()}: " + "; ".join(by[cat]))
    return "\n".join(parts)


def get_narrative() -> Optional[dict]:
    conn = get_connection()
    row = conn.execute("SELECT * FROM brain_narrative ORDER BY created_at DESC LIMIT 1").fetchone()
    conn.close()
    return dict(row) if row else None


def synthesize_narrative() -> Optional[dict]:
    summary = profile_summary(max_per_cat=8)
    if not summary:
        return None
    sys = ("You are Tobi, a deeply perceptive personal assistant with expert psychology insight. "
           "Write a concise, warm, second-person narrative ('You are...') capturing who the owner is: "
           "personality, values, motivations, working style, and what they need from you. 150-250 words.")
    content = _llm(f"What I know about the owner:\n{summary}\n\nWrite the narrative.",
                   system=sys, max_tokens=500, task_type="simple")
    if not content:
        return None
    conn = get_connection()
    conn.execute("INSERT INTO brain_narrative (content, model_used) VALUES (?, ?)",
                 (content.strip(), "llm"))
    conn.commit()
    conn.close()
    return get_narrative()


def chat(message: str, chat_id: int = DASHBOARD_CHAT_ID) -> dict:
    message = (message or "").strip()
    if not message:
        return {"reply": "", "error": "empty"}
    history = load_conversation_history(chat_id, limit=10)
    summary = profile_summary()
    retrieved = retrieve(message, k=6)
    mem_block = "\n".join(f"- {m['content']}" for m in retrieved) if retrieved else ""
    system = (
        "You are Tobi, the owner's personal AI assistant — sharp, direct, warm, and psychologically astute. "
        "Use what you know about the owner to be genuinely helpful and personal.\n"
    )
    if summary:
        system += f"\nOwner profile:\n{summary}\n"
    if mem_block:
        system += f"\nRelevant memories:\n{mem_block}\n"
    convo = "\n".join(f"{m['role']}: {m['content']}" for m in history)
    prompt = (f"{convo}\nuser: {message}\nassistant:" if convo else message)
    reply = _llm(prompt, system=system, max_tokens=900, task_type="simple")
    if reply is None:
        reply = "I can't reach my language model right now — check the LLM API key in Integrations."
    save_conversation_message(chat_id, "user", message)
    save_conversation_message(chat_id, "assistant", reply)
    # opportunistic learning so the dashboard chat feeds the Brain even without the scheduler
    try:
        sweep_once()
    except Exception as e:
        logger.warning("post-chat sweep failed: %s", e)
    return {"reply": reply}


def _build_chat_system(message: str) -> str:
    """Shared system prompt for chat (streaming + non-streaming): persona + owner
    profile + memories relevant to this message."""
    summary = profile_summary()
    retrieved = retrieve(message, k=6)
    mem_block = "\n".join(f"- {m['content']}" for m in retrieved) if retrieved else ""
    system = (
        "You are Tobi, the owner's personal AI assistant — sharp, direct, warm, and psychologically astute. "
        "Use what you know about the owner to be genuinely helpful and personal.\n"
    )
    if summary:
        system += f"\nOwner profile:\n{summary}\n"
    if mem_block:
        system += f"\nRelevant memories:\n{mem_block}\n"
    return system


def chat_stream(message: str, chat_id: int = DASHBOARD_CHAT_ID):
    """Streaming variant of chat(): yields reply text deltas, persists both turns, and
    runs an opportunistic sweep at the end. Mirrors chat() so the two stay consistent."""
    message = (message or "").strip()
    if not message:
        return
    history = load_conversation_history(chat_id, limit=10)
    system = _build_chat_system(message)
    convo = "\n".join(f"{m['role']}: {m['content']}" for m in history)
    prompt = (f"{convo}\nuser: {message}\nassistant:" if convo else message)

    pieces: list[str] = []
    try:
        from core.model_router import get_llm
        client = get_llm("simple")
        for delta in client.complete_stream(
            [{"role": "user", "content": prompt}], system=system, max_tokens=900
        ):
            if delta:
                pieces.append(delta)
                yield delta
    except Exception as e:
        logger.warning("Brain chat_stream failed: %s", e)

    reply = "".join(pieces).strip()
    if not reply:
        reply = "I can't reach my language model right now — check the LLM API key in Integrations."
        yield reply
    save_conversation_message(chat_id, "user", message)
    save_conversation_message(chat_id, "assistant", reply)
    try:
        sweep_once()
    except Exception as e:
        logger.warning("post-chat sweep failed: %s", e)


def owner_context(query: Optional[str] = None, k: int = 6, max_per_cat: int = 3,
                  header: str = "What Tobi knows about the owner") -> str:
    """Memory-first context block for any agent/task prompt. Combines the always-on
    profile summary with top-k memories relevant to `query` (when given). Returns ""
    when the Brain is empty so callers can inject unconditionally."""
    summary = profile_summary(max_per_cat=max_per_cat)
    lines: list[str] = []
    if summary:
        lines.append(summary)
    if query:
        try:
            retrieved = retrieve(query, k=k)
        except Exception:
            retrieved = []
        extra = [m["content"] for m in retrieved if m.get("content") and m["content"] not in summary]
        if extra:
            lines.append("Relevant:\n" + "\n".join(f"- {c}" for c in extra))
        # GraphRAG: multi-hop connected knowledge the flat top-k above would miss.
        try:
            from core import graph_engine
            gctx = graph_engine.graph_context(query, k=5)
            if gctx:
                lines.append(gctx)
        except Exception:
            pass
    if not lines:
        return ""
    return f"{header}:\n" + "\n".join(lines)


# ── confidence decay (freshness automation) ──────────────────────────────────
DECAY_AFTER_DAYS = 30      # grace period before unconfirmed memories start decaying
DECAY_STEP = 0.03         # confidence lost per decay run once past the grace period
DECAY_FLOOR = 0.2         # never decay below this (keeps the memory, just flags it stale)


def _stale_for(ref: Optional[str], days: int) -> bool:
    if not ref:
        return False
    try:
        dt = datetime.fromisoformat(ref.replace("Z", "")).replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).days >= days
    except Exception:
        return False


def decay_confidences() -> dict:
    """Gently lower confidence of active memories not confirmed within the grace window.
    Owner-confirmed (`confirm_memory`) or re-learned memories reset their clock. This is
    the freshness automation: unconfirmed knowledge fades and surfaces as stale, but is
    never silently deleted. Safe to run daily."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT id, confidence, last_confirmed_at, created_at
           FROM brain_memories
           WHERE status='active' AND deleted_at IS NULL"""
    ).fetchall()
    decayed = 0
    for r in rows:
        if not _stale_for(r["last_confirmed_at"] or r["created_at"], DECAY_AFTER_DAYS):
            continue
        cur = r["confidence"] if r["confidence"] is not None else 0.6
        new = round(max(DECAY_FLOOR, cur - DECAY_STEP), 3)
        if new < cur:
            conn.execute("UPDATE brain_memories SET confidence=? WHERE id=?", (new, r["id"]))
            decayed += 1
    conn.commit()
    conn.close()
    return {"decayed": decayed, "scanned": len(rows)}


# ── Hermes memory mirror (one-way Brain → Hermes) ────────────────────────────
def mirror_to_hermes(limit: int = 50) -> dict:
    """One-way mirror: push active memories not yet synced into Hermes' memory store via
    the `hermes` CLI (same mechanism core/telegram_bot.cmd_note already uses). Best-effort
    and fully degradable — if the CLI is missing or errors, nothing breaks and the rows
    stay unmarked for the next run. Tracked via brain_memories.hermes_synced_at."""
    import shutil
    import subprocess
    if not shutil.which("hermes"):
        return {"mirrored": 0, "skipped": "hermes CLI not found"}
    conn = get_connection()
    rows = conn.execute(
        """SELECT id, content, category FROM brain_memories
           WHERE status='active' AND deleted_at IS NULL AND hermes_synced_at IS NULL
           ORDER BY id ASC LIMIT ?""",
        (limit,),
    ).fetchall()
    mirrored = 0
    for r in rows:
        line = f"[{r['category']}] {r['content']}"[:280]
        try:
            res = subprocess.run(
                ["hermes", "memory", "add", line],
                capture_output=True, timeout=8, check=False,
            )
            if res.returncode == 0:
                conn.execute(
                    "UPDATE brain_memories SET hermes_synced_at=CURRENT_TIMESTAMP WHERE id=?",
                    (r["id"],),
                )
                mirrored += 1
        except Exception as e:
            logger.warning("hermes mirror failed for #%s: %s", r["id"], e)
            break   # CLI is unhealthy this run — stop, retry next time
    conn.commit()
    conn.close()
    return {"mirrored": mirrored}


def remember(content: str, category: Optional[str] = None) -> dict:
    content = (content or "").strip()
    if not content:
        return {"ok": False}
    if not category or category not in CATEGORY_IDS:
        raw = _llm(
            f"Classify this fact about the owner into exactly one category from {CATEGORY_IDS}. "
            f"Reply with only the category id.\n\nFact: {content}",
            max_tokens=10, task_type="classify",
        )
        category = (raw or "").strip().lower()
        if category not in CATEGORY_IDS:
            category = "identity"
    mid = add_memory(content, category, confidence=0.9, source="remember", status="active")
    return {"ok": True, "id": mid, "category": category}


# ── stats ────────────────────────────────────────────────────────────────────
def stats() -> dict:
    conn = get_connection()
    total = conn.execute("SELECT COUNT(*) FROM brain_memories WHERE status='active' AND deleted_at IS NULL").fetchone()[0]
    by_cat = {r["category"]: r["c"] for r in conn.execute(
        "SELECT category, COUNT(*) c FROM brain_memories WHERE status='active' AND deleted_at IS NULL GROUP BY category"
    ).fetchall()}
    by_source = {r["source"]: r["c"] for r in conn.execute(
        "SELECT source, COUNT(*) c FROM brain_memories WHERE status='active' AND deleted_at IS NULL GROUP BY source"
    ).fetchall()}
    pending = conn.execute("SELECT COUNT(*) FROM brain_memories WHERE status='pending'").fetchone()[0]
    conflicts = conn.execute("SELECT COUNT(*) FROM brain_conflicts WHERE status='open'").fetchone()[0]
    conn.close()
    stale = sum(1 for m in list_memories(status="active") if m["stale"])
    return {
        "total": total, "by_category": by_cat, "by_source": by_source,
        "pending": pending, "conflicts": conflicts, "stale": stale,
        "embeddings": emb.is_available(),
    }

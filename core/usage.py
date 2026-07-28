"""
LLM USAGE — Premium Chat (#8 P3).

Real per-call usage logging across **all** TOBI LLM use (chat, Conductor, agents,
research…) → powers the analytics on the Models page + Health, and seeds the bigger
Storage & Usage dashboard (#10).

The model_router clients call ``log()`` after every completion with provider/model +
the provider-reported token counts (or an estimate) + latency, tagged with a *surface*
(``chat`` / ``agent`` / …) and *feature*. Cost is a **manual price table** (per-1M
tokens) — editable later in #10.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone, timedelta
from typing import Optional

# ── manual price table: model fragment → (USD per 1M input, USD per 1M output) ──
# Pattern-matched on the bare model name (longest match wins). Unknown → free (0,0).
PRICES: list[tuple[str, tuple[float, float]]] = [
    ("claude-opus", (15.0, 75.0)),
    ("claude-sonnet", (3.0, 15.0)),
    ("claude-haiku", (0.80, 4.0)),
    ("claude", (3.0, 15.0)),
    ("gpt-4o-mini", (0.15, 0.60)),
    ("gpt-4o", (2.50, 10.0)),
    ("gpt-4.1", (2.0, 8.0)),
    ("gpt-5", (5.0, 15.0)),
    ("o3-mini", (1.10, 4.40)),
    ("o3", (2.0, 8.0)),
    ("o4", (2.0, 8.0)),
    ("gemini-2.5-pro", (1.25, 10.0)),
    ("gemini-2.5-flash", (0.30, 2.50)),
    ("gemini", (0.50, 3.0)),
    ("grok-4", (5.0, 15.0)),
    ("grok-3-mini", (0.30, 0.50)),
    ("grok", (3.0, 15.0)),
    (":free", (0.0, 0.0)),
    ("nemotron", (0.0, 0.0)),
]


def price_for(model: str) -> tuple[float, float]:
    name = (model or "").lower()
    best: tuple[float, float] = (0.0, 0.0)
    best_len = -1
    for frag, price in PRICES:
        if frag in name and len(frag) > best_len:
            best, best_len = price, len(frag)
    return best


def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    pin, pout = price_for(model)
    return round((prompt_tokens or 0) / 1e6 * pin + (completion_tokens or 0) / 1e6 * pout, 6)


def _conn() -> sqlite3.Connection:
    from core.database import get_connection
    return get_connection()


# P3 (#8) extends the existing D34 `llm_usage` table (per-agent/mission, created by
# database.init_database) with the columns we need, rather than a competing table.
_P3_COLUMNS = [
    ("ts", "TEXT"),
    ("surface", "TEXT"),
    ("feature", "TEXT"),
    ("cost_est", "REAL"),
    ("latency_ms", "INTEGER"),
    ("requested_model", "TEXT"),
    ("actual_model", "TEXT"),
    ("turn_id", "TEXT"),
    ("run_id", "TEXT"),
    ("worker_session_id", "INTEGER"),
    ("purpose", "TEXT"),
    ("source", "TEXT"),
    ("is_background", "INTEGER DEFAULT 0"),
    ("attempt", "INTEGER DEFAULT 1"),
    ("status", "TEXT DEFAULT 'succeeded'"),
    ("error_code", "TEXT"),
    ("fallback_reason", "TEXT"),
]


def ensure_schema(conn: sqlite3.Connection) -> None:
    # Create the full table for a fresh DB; on existing DBs this is a no-op and the
    # ALTERs below add the P3 columns to the D34 table.
    conn.execute(
        """CREATE TABLE IF NOT EXISTS llm_usage (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id          TEXT,
            mission_id        INTEGER,
            provider          TEXT,
            model             TEXT,
            prompt_tokens     INTEGER DEFAULT 0,
            completion_tokens INTEGER DEFAULT 0,
            total_tokens      INTEGER DEFAULT 0,
            cost              REAL    DEFAULT 0,
            created_at        DATETIME DEFAULT CURRENT_TIMESTAMP
        )"""
    )
    cols = {r[1] for r in conn.execute("PRAGMA table_info(llm_usage)").fetchall()}
    for name, ddl in _P3_COLUMNS:
        if name not in cols:
            conn.execute(f"ALTER TABLE llm_usage ADD COLUMN {name} {ddl}")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_llm_usage_ts ON llm_usage(ts)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_llm_usage_turn ON llm_usage(turn_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_llm_usage_run ON llm_usage(run_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_llm_usage_status ON llm_usage(status)")


def log(provider: str, model: str, prompt_tokens: int, completion_tokens: int,
        latency_ms: int, surface: str = "agent", feature: str = "",
        cost_est: Optional[float] = None, *, requested_model: str = "",
        actual_model: str = "", turn_id: str = "", run_id: str = "",
        worker_session_id: Optional[int] = None, agent_id: str = "",
        purpose: str = "", source: str = "model_api", is_background: bool = False,
        attempt: int = 1, status: str = "succeeded", error_code: str = "",
        fallback_reason: str = "") -> None:
    """Record one LLM call. Best-effort — never raises into the caller."""
    try:
        if cost_est is None:
            cost_est = estimate_cost(model, prompt_tokens, completion_tokens)
        ptok, ctok = int(prompt_tokens or 0), int(completion_tokens or 0)
        conn = _conn()
        try:
            ensure_schema(conn)
            conn.execute(
                """INSERT INTO llm_usage (
                    ts, surface, feature, provider, model, requested_model, actual_model,
                    turn_id, run_id, worker_session_id, agent_id, purpose, source,
                    is_background, attempt, status, error_code, fallback_reason,
                    prompt_tokens, completion_tokens, total_tokens, cost, cost_est, latency_ms
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    datetime.now(timezone.utc).isoformat(), surface, feature, provider, model,
                    requested_model or None, actual_model or model or None, turn_id or None,
                    run_id or None, worker_session_id, agent_id or None, purpose or None,
                    source or "model_api", 1 if is_background else 0, max(1, int(attempt or 1)),
                    status or "succeeded", error_code or None, fallback_reason or None,
                    ptok, ctok, ptok + ctok, float(cost_est), float(cost_est),
                    int(latency_ms or 0),
                ),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass


def log_failure(provider: str, model: str, latency_ms: int, *, error_code: str,
                **metadata) -> None:
    """Record a failed provider attempt without fabricating token or cost usage."""
    log(provider, model, 0, 0, latency_ms, cost_est=0.0, status="failed",
        error_code=error_code or "ProviderError", **metadata)


def summary(days: int = 7) -> dict:
    """Aggregate the last `days` of usage for the analytics panel. Includes both the
    P3-tagged rows (chat/agent/…) and legacy Office per-mission rows (via created_at)."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=max(1, days))).isoformat()
    conn = _conn()
    try:
        ensure_schema(conn)
        rows = conn.execute(
            "SELECT COALESCE(ts, created_at) AS ts, COALESCE(surface, 'office') AS surface, "
            "provider, model, prompt_tokens, completion_tokens, COALESCE(cost_est, cost) AS cost_est, "
            "latency_ms FROM llm_usage WHERE COALESCE(ts, created_at) >= ? "
            "AND COALESCE(status,'succeeded') != 'failed' ORDER BY ts", (cutoff,)
        ).fetchall()
    finally:
        conn.close()

    total_in = total_out = total_req = total_lat = 0
    total_cost = 0.0
    by_model: dict[str, dict] = {}
    by_surface: dict[str, int] = {}
    by_day: dict[str, dict] = {}
    for r in rows:
        pin, pout, cost, lat = r["prompt_tokens"] or 0, r["completion_tokens"] or 0, r["cost_est"] or 0.0, r["latency_ms"] or 0
        total_in += pin; total_out += pout; total_req += 1; total_lat += lat; total_cost += cost
        m = r["model"] or "?"
        bm = by_model.setdefault(m, {"model": m, "provider": r["provider"], "tokens": 0, "prompt_tokens": 0,
                                     "completion_tokens": 0, "cost": 0.0, "requests": 0})
        bm["tokens"] += pin + pout; bm["prompt_tokens"] += pin; bm["completion_tokens"] += pout
        bm["cost"] += cost; bm["requests"] += 1
        by_surface[r["surface"] or "?"] = by_surface.get(r["surface"] or "?", 0) + pin + pout
        day = (r["ts"] or "")[:10]
        bd = by_day.setdefault(day, {"day": day, "tokens": 0, "cost": 0.0})
        bd["tokens"] += pin + pout; bd["cost"] += cost

    # fill a continuous day series so the chart isn't gappy
    series = []
    today = datetime.now(timezone.utc).date()
    for i in range(max(1, days) - 1, -1, -1):
        d = (today - timedelta(days=i)).isoformat()
        series.append(by_day.get(d, {"day": d, "tokens": 0, "cost": 0.0}))

    models = sorted(by_model.values(), key=lambda x: x["tokens"], reverse=True)
    for m in models:
        m["cost"] = round(m["cost"], 4)
    return {
        "days": days,
        "total_tokens": total_in + total_out,
        "prompt_tokens": total_in,
        "completion_tokens": total_out,
        "total_cost": round(total_cost, 4),
        "requests": total_req,
        "avg_latency_ms": round(total_lat / total_req) if total_req else 0,
        "by_model": models,
        "by_surface": by_surface,
        "by_day": series,
    }


def recent(limit: int = 50) -> list[dict]:
    conn = _conn()
    try:
        ensure_schema(conn)
        rows = conn.execute(
            "SELECT COALESCE(ts, created_at) AS ts, COALESCE(surface, 'office') AS surface, feature, "
            "provider, model, requested_model, COALESCE(actual_model, model) AS actual_model, "
            "turn_id, run_id, worker_session_id, agent_id, purpose, source, is_background, "
            "COALESCE(attempt,1) AS attempt, COALESCE(status,'succeeded') AS status, "
            "error_code, fallback_reason, prompt_tokens, completion_tokens, "
            "COALESCE(cost_est, cost) AS cost_est, latency_ms "
            "FROM llm_usage ORDER BY id DESC LIMIT ?", (max(1, min(limit, 500)),)
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]

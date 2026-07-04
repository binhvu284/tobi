"""
USAGE METER — Storage & Usage (#10, M2/M3).

The analytics layer over the per-call ``llm_usage`` logging that #8 P3 put in
``core/usage.py`` (every ``model_router`` completion auto-logs provider/model/
tokens/latency tagged with surface+feature — that *is* the [S13] instrumentation).
This module adds what the Storage & Usage page needs on top:

- **Price table** [S14]: ``config/llm_prices.yaml`` → mirrored to an ``llm_prices``
  table on load; keeps ``core.usage.PRICES`` (the live cost estimator) in sync.
- **Range-aware overview** [S15][S16][S19]: cost/tokens/requests/latency broken
  down by provider · model · feature/engine (surface) · agent, plus a per-day
  spend series stacked by surface.
- **Per-call log** [S20]: paginated + filterable inspector.
- **Plans** [S17]: manually-configured provider plans → usage-vs-limit bars.
- **Budget** [S18]: monthly $ cap + alert threshold (D21 cost-guard pattern);
  alerts surface in-app only — no autonomous push [S26].
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

RANGES = {"day": 1, "week": 7, "month": 30, "all": None}
PRICES_YAML = Path(__file__).resolve().parent.parent / "config" / "llm_prices.yaml"


def _conn() -> sqlite3.Connection:
    from core.database import get_connection
    return get_connection()


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS llm_prices (
            model              TEXT PRIMARY KEY,   -- name fragment, longest match wins
            price_in_per_mtok  REAL DEFAULT 0,
            price_out_per_mtok REAL DEFAULT 0,
            updated_at         TEXT
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS llm_plans (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            provider      TEXT NOT NULL,
            plan_name     TEXT NOT NULL,
            limit_type    TEXT NOT NULL DEFAULT 'usd',   -- usd | tokens | requests
            limit_value   REAL NOT NULL DEFAULT 0,
            period        TEXT NOT NULL DEFAULT 'month',
            configured_at TEXT
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS usage_budget (
            key             TEXT PRIMARY KEY,
            monthly_cap_usd REAL DEFAULT 0,
            alert_pct       INTEGER DEFAULT 80,
            updated_at      TEXT
        )"""
    )


# ════════════════════════════════════════════════════════════════════════════
# Price table [S14] — YAML → DB mirror → live estimator
# ════════════════════════════════════════════════════════════════════════════
def _load_yaml_prices() -> list[tuple[str, float, float]]:
    """Parse config/llm_prices.yaml. PyYAML if present, else a fallback for the
    flow-mapping line format the file ships with. Empty list on any failure."""
    if not PRICES_YAML.exists():
        return []
    text = PRICES_YAML.read_text(encoding="utf-8")
    try:
        import yaml  # optional
        data = yaml.safe_load(text) or {}
        return [(str(p["model"]), float(p.get("in", 0)), float(p.get("out", 0)))
                for p in data.get("prices", []) if p.get("model")]
    except ImportError:
        pass
    except Exception:
        return []
    out = []
    for line in text.splitlines():  # "- { model: x, in: 1.0, out: 2.0 }"
        line = line.strip()
        if not line.startswith("- {") or not line.endswith("}"):
            continue
        fields = {}
        for part in line[3:-1].split(","):
            if ":" not in part:
                continue
            k, v = part.split(":", 1)
            fields[k.strip()] = v.strip().strip('"').strip("'")
        if fields.get("model"):
            try:
                out.append((fields["model"], float(fields.get("in", 0)), float(fields.get("out", 0))))
            except ValueError:
                pass
    return out


def sync_prices() -> dict:
    """Mirror the YAML price table into llm_prices AND core.usage.PRICES (so the
    at-call-time cost estimator uses the same numbers). Safe to call often."""
    rows = _load_yaml_prices()
    conn = _conn()
    try:
        ensure_schema(conn)
        if rows:
            now = datetime.now(timezone.utc).isoformat()
            for model, pin, pout in rows:
                conn.execute(
                    "INSERT INTO llm_prices (model, price_in_per_mtok, price_out_per_mtok, updated_at) "
                    "VALUES (?,?,?,?) ON CONFLICT(model) DO UPDATE SET "
                    "price_in_per_mtok=excluded.price_in_per_mtok, "
                    "price_out_per_mtok=excluded.price_out_per_mtok, updated_at=excluded.updated_at",
                    (model, pin, pout, now),
                )
            conn.commit()
        table = [dict(r) for r in conn.execute(
            "SELECT model, price_in_per_mtok, price_out_per_mtok FROM llm_prices ORDER BY model"
        ).fetchall()]
    finally:
        conn.close()
    if table:
        from core import usage
        usage.PRICES[:] = [(r["model"], (r["price_in_per_mtok"], r["price_out_per_mtok"]))
                           for r in table]
    return {"from_yaml": len(rows), "active": len(table)}


def get_prices() -> list[dict]:
    conn = _conn()
    try:
        ensure_schema(conn)
        rows = [dict(r) for r in conn.execute(
            "SELECT model, price_in_per_mtok, price_out_per_mtok, updated_at "
            "FROM llm_prices ORDER BY model"
        ).fetchall()]
    finally:
        conn.close()
    if not rows:  # first touch: seed from YAML (or the built-in defaults stay live)
        sync_prices()
        return get_prices() if PRICES_YAML.exists() else []
    return rows


# ════════════════════════════════════════════════════════════════════════════
# Usage reads [S15][S16][S19][S20]
# ════════════════════════════════════════════════════════════════════════════
def _cutoff(range_key: str) -> Optional[str]:
    days = RANGES.get(range_key, 30)
    if days is None:
        return None
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def overview(range_key: str = "month") -> dict:
    """Totals + all four breakdown dims + per-day spend stacked by surface."""
    from core import usage
    cutoff = _cutoff(range_key)
    conn = _conn()
    try:
        usage.ensure_schema(conn)
        q = ("SELECT COALESCE(ts, created_at) AS ts, COALESCE(surface,'office') AS surface, "
             "COALESCE(feature,'') AS feature, provider, model, agent_id, "
             "prompt_tokens, completion_tokens, COALESCE(cost_est, cost) AS cost_est, latency_ms "
             "FROM llm_usage")
        rows = (conn.execute(q + " WHERE COALESCE(ts, created_at) >= ? ORDER BY ts", (cutoff,))
                if cutoff else conn.execute(q + " ORDER BY ts")).fetchall()
    finally:
        conn.close()

    def _bucket(store: dict, key: str, label_field: str) -> dict:
        return store.setdefault(key, {label_field: key, "cost": 0.0, "tokens": 0,
                                      "prompt_tokens": 0, "completion_tokens": 0,
                                      "requests": 0, "latency_sum": 0})

    tot = {"cost": 0.0, "prompt_tokens": 0, "completion_tokens": 0, "requests": 0, "latency_sum": 0}
    by_provider: dict[str, dict] = {}
    by_model: dict[str, dict] = {}
    by_surface: dict[str, dict] = {}
    by_agent: dict[str, dict] = {}
    by_day: dict[str, dict] = {}
    surfaces: set[str] = set()

    for r in rows:
        pin, pout = r["prompt_tokens"] or 0, r["completion_tokens"] or 0
        cost, lat = r["cost_est"] or 0.0, r["latency_ms"] or 0
        surface = r["surface"] or "?"
        surfaces.add(surface)
        tot["cost"] += cost; tot["prompt_tokens"] += pin; tot["completion_tokens"] += pout
        tot["requests"] += 1; tot["latency_sum"] += lat
        for store, key, field in (
            (by_provider, r["provider"] or "?", "provider"),
            (by_model, r["model"] or "?", "model"),
            (by_surface, surface, "surface"),
        ):
            b = _bucket(store, key, field)
            b["cost"] += cost; b["tokens"] += pin + pout
            b["prompt_tokens"] += pin; b["completion_tokens"] += pout
            b["requests"] += 1; b["latency_sum"] += lat
        if r["agent_id"]:
            b = _bucket(by_agent, r["agent_id"], "agent")
            b["cost"] += cost; b["tokens"] += pin + pout
            b["prompt_tokens"] += pin; b["completion_tokens"] += pout
            b["requests"] += 1; b["latency_sum"] += lat
        day = (r["ts"] or "")[:10]
        d = by_day.setdefault(day, {"day": day, "cost": 0.0, "tokens": 0})
        d["cost"] = round(d["cost"] + cost, 6)
        d["tokens"] += pin + pout
        d[surface] = round(d.get(surface, 0.0) + cost, 6)

    def _final(store: dict) -> list[dict]:
        out = sorted(store.values(), key=lambda b: b["cost"], reverse=True)
        for b in out:
            b["cost"] = round(b["cost"], 4)
            b["avg_latency_ms"] = round(b.pop("latency_sum") / b["requests"]) if b["requests"] else 0
        return out

    # continuous day series (stacked by surface) so charts aren't gappy
    days_back = RANGES.get(range_key) or (
        max(1, (datetime.now(timezone.utc).date() -
                datetime.fromisoformat(min(by_day)).date()).days + 1) if by_day else 1)
    days_back = min(days_back, 365)
    series = []
    today = datetime.now(timezone.utc).date()
    for i in range(days_back - 1, -1, -1):
        d = (today - timedelta(days=i)).isoformat()
        series.append(by_day.get(d, {"day": d, "cost": 0.0, "tokens": 0}))

    return {
        "range": range_key,
        "total_cost": round(tot["cost"], 4),
        "total_tokens": tot["prompt_tokens"] + tot["completion_tokens"],
        "prompt_tokens": tot["prompt_tokens"],
        "completion_tokens": tot["completion_tokens"],
        "requests": tot["requests"],
        "avg_latency_ms": round(tot["latency_sum"] / tot["requests"]) if tot["requests"] else 0,
        "by_provider": _final(by_provider),
        "by_model": _final(by_model),
        "by_surface": _final(by_surface),
        "by_agent": _final(by_agent),
        "surfaces": sorted(surfaces),
        "by_day": series,
    }


def calls(limit: int = 50, offset: int = 0, q: str = "", surface: str = "",
          model: str = "") -> dict:
    """Searchable per-call log inspector [S20]."""
    from core import usage
    limit = max(1, min(int(limit or 50), 200))
    offset = max(0, int(offset or 0))
    where, params = [], []
    if q:
        where.append("(model LIKE ? OR feature LIKE ? OR provider LIKE ?)")
        params += [f"%{q}%"] * 3
    if surface:
        where.append("COALESCE(surface,'office') = ?")
        params.append(surface)
    if model:
        where.append("model LIKE ?")
        params.append(f"%{model}%")
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    conn = _conn()
    try:
        usage.ensure_schema(conn)
        total = conn.execute(f"SELECT COUNT(*) FROM llm_usage{clause}", params).fetchone()[0]
        rows = conn.execute(
            "SELECT id, COALESCE(ts, created_at) AS ts, COALESCE(surface,'office') AS surface, "
            "feature, provider, model, agent_id, prompt_tokens, completion_tokens, "
            f"COALESCE(cost_est, cost) AS cost_est, latency_ms FROM llm_usage{clause} "
            "ORDER BY id DESC LIMIT ? OFFSET ?", params + [limit, offset]
        ).fetchall()
    finally:
        conn.close()
    return {"total": total, "limit": limit, "offset": offset,
            "calls": [dict(r) for r in rows]}


# ════════════════════════════════════════════════════════════════════════════
# Plans [S17] & budget [S18]
# ════════════════════════════════════════════════════════════════════════════
def _month_usage(conn: sqlite3.Connection, provider: Optional[str] = None) -> dict:
    start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0,
                                               microsecond=0).isoformat()
    q = ("SELECT COALESCE(SUM(COALESCE(cost_est, cost)),0) AS usd, "
         "COALESCE(SUM(total_tokens),0) AS tokens, COUNT(*) AS requests "
         "FROM llm_usage WHERE COALESCE(ts, created_at) >= ?")
    params: list = [start]
    if provider:
        q += " AND provider = ?"
        params.append(provider)
    r = conn.execute(q, params).fetchone()
    return {"usd": round(r["usd"], 4), "tokens": r["tokens"], "requests": r["requests"]}


def get_plans() -> list[dict]:
    """Configured plans + month-to-date usage vs their limits → progress bars."""
    from core import usage
    conn = _conn()
    try:
        ensure_schema(conn)
        usage.ensure_schema(conn)
        plans = [dict(r) for r in conn.execute(
            "SELECT id, provider, plan_name, limit_type, limit_value, period, configured_at "
            "FROM llm_plans ORDER BY provider"
        ).fetchall()]
        for p in plans:
            u = _month_usage(conn, p["provider"])
            used = {"usd": u["usd"], "tokens": u["tokens"], "requests": u["requests"]
                    }.get(p["limit_type"], u["usd"])
            p["used"] = used
            p["pct"] = round(used / p["limit_value"] * 100, 1) if p["limit_value"] else 0.0
    finally:
        conn.close()
    return plans


def set_plans(plans: list[dict]) -> list[dict]:
    """Replace the configured plan list (manual config — small, owner-edited)."""
    now = datetime.now(timezone.utc).isoformat()
    conn = _conn()
    try:
        ensure_schema(conn)
        conn.execute("DELETE FROM llm_plans")
        for p in plans or []:
            if not (p.get("provider") and p.get("plan_name")):
                continue
            lt = p.get("limit_type") if p.get("limit_type") in ("usd", "tokens", "requests") else "usd"
            conn.execute(
                "INSERT INTO llm_plans (provider, plan_name, limit_type, limit_value, period, configured_at) "
                "VALUES (?,?,?,?,?,?)",
                (str(p["provider"]), str(p["plan_name"]), lt,
                 float(p.get("limit_value") or 0), str(p.get("period") or "month"), now),
            )
        conn.commit()
    finally:
        conn.close()
    return get_plans()


def get_budget() -> dict:
    """Monthly cap + month-to-date spend → ok | warn | over [S18]."""
    from core import usage
    conn = _conn()
    try:
        ensure_schema(conn)
        usage.ensure_schema(conn)
        row = conn.execute(
            "SELECT monthly_cap_usd, alert_pct, updated_at FROM usage_budget WHERE key='global'"
        ).fetchone()
        mtd = _month_usage(conn)
    finally:
        conn.close()
    cap = row["monthly_cap_usd"] if row else 0.0
    alert_pct = row["alert_pct"] if row else 80
    pct = round(mtd["usd"] / cap * 100, 1) if cap else 0.0
    level = "off" if not cap else ("over" if pct >= 100 else "warn" if pct >= alert_pct else "ok")
    return {"monthly_cap_usd": cap, "alert_pct": alert_pct, "spent_usd": mtd["usd"],
            "pct": pct, "level": level,
            "updated_at": row["updated_at"] if row else None}


def set_budget(monthly_cap_usd: float, alert_pct: int = 80) -> dict:
    conn = _conn()
    try:
        ensure_schema(conn)
        conn.execute(
            "INSERT INTO usage_budget (key, monthly_cap_usd, alert_pct, updated_at) "
            "VALUES ('global',?,?,?) ON CONFLICT(key) DO UPDATE SET "
            "monthly_cap_usd=excluded.monthly_cap_usd, alert_pct=excluded.alert_pct, "
            "updated_at=excluded.updated_at",
            (max(0.0, float(monthly_cap_usd or 0)),
             max(1, min(int(alert_pct or 80), 100)),
             datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    finally:
        conn.close()
    return get_budget()


def spend_compact(range_key: str = "month") -> dict:
    """Small spend summary for the Conductor tool + Dashboard widget [S25][S29]."""
    ov = overview(range_key)
    return {
        "range": range_key,
        "total_cost_usd": ov["total_cost"],
        "total_tokens": ov["total_tokens"],
        "requests": ov["requests"],
        "avg_latency_ms": ov["avg_latency_ms"],
        "top_models": [{"model": m["model"], "cost_usd": m["cost"], "tokens": m["tokens"]}
                       for m in ov["by_model"][:5]],
        "by_surface": [{"surface": s["surface"], "cost_usd": s["cost"]}
                       for s in ov["by_surface"][:6]],
        "budget": get_budget(),
    }

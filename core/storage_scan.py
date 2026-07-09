"""
STORAGE SCAN — Storage & Usage (#10, M1).

Answers "where is my disk going?" for every TOBI data resource:

- **agent.db per-table** sizes via the ``dbstat`` virtual table (with a sampled
  estimate fallback when the sqlite build lacks it) [S5].
- **Data dirs** (``~/.mmo_agent`` artifacts, ``~/.hermes`` memory/skills/SOUL),
  **code + deps** (repo · venv · node_modules · dist), **vector index / graph /
  logs** — each walked and attributed [S5].
- Everything rolls up **by feature** (Brain / Graph / Office / Tasks / Projects /
  Documents / Chat / Codebase / Vault / MCP) with dev bulk in a separate
  **System** bucket so deps never drown real data [S6][S7].
- Each scan writes **``storage_snapshots``** rows → growth charts + "what grew
  this week" [S8][S22]. Dependency dirs are walked once and cached for a week
  (they rarely change) [S24].

Read-only: nothing here deletes or mutates owner data [S3]. The encrypted vault
is reported by size + item count only — never values [S28].
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

FEATURES = ["Brain", "Graph", "Office", "Tasks", "Projects", "Documents",
            "Chat", "Codebase", "Vault", "MCP", "System", "Other"]

# ── table → feature map [S6] (prefix match, longest wins; unmapped → Other) ──
TABLE_FEATURES: dict[str, str] = {
    "brain_": "Brain",
    "graph_": "Graph",
    "agents": "Office", "agent_state": "Office", "missions": "Office",
    "mission_steps": "Office", "workflows": "Office", "reports": "Office",
    "lessons": "Office", "revenue": "Office", "strategy": "Office",
    "skills": "Office", "skill_": "Office",
    "tasks": "Tasks", "task_": "Tasks",
    "projects": "Projects", "pm_": "Projects",
    "pm_files": "Documents",
    "chat_": "Chat", "conversations": "Chat", "tobi_actions": "Chat",
    "vault_": "Vault",
    "mcp_": "MCP",
    "llm_": "System", "usage_budget": "System", "storage_snapshots": "System",
    "owner_settings": "System", "sqlite_": "System",
}

PROJECT_DIR = Path(__file__).resolve().parent.parent
# Dep/build dirs → the System bucket, measured once + cached weekly [S7][S24].
DEP_DIRS: list[tuple[str, Path]] = [
    ("venv", PROJECT_DIR / "venv"),
    ("node_modules", PROJECT_DIR / "dashboard" / "node_modules"),
    ("dist", PROJECT_DIR / "dashboard" / "dist"),
]
_DEP_CACHE_DAYS = 7
_SKIP_WALK = {".git", "venv", "node_modules", "dist", "__pycache__"}


def _conn() -> sqlite3.Connection:
    from core.database import get_connection
    return get_connection()


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS storage_snapshots (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            taken_at   TEXT NOT NULL,
            scope      TEXT NOT NULL,          -- db | fs | deps
            feature    TEXT NOT NULL,
            bytes      INTEGER DEFAULT 0,
            item_count INTEGER DEFAULT 0,
            meta_json  TEXT
        )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_storage_snap_at ON storage_snapshots(taken_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_storage_snap_scope ON storage_snapshots(scope, taken_at)")


def feature_for_table(name: str) -> str:
    n = (name or "").lower()
    best, best_len = "Other", -1
    for frag, feat in TABLE_FEATURES.items():
        if n.startswith(frag) and len(frag) > best_len:
            best, best_len = feat, len(frag)
    return best


# ════════════════════════════════════════════════════════════════════════════
# DB scan — per-table bytes + rows [S5]
# ════════════════════════════════════════════════════════════════════════════
def scan_db() -> dict:
    """Per-table size/rows of agent.db. Uses dbstat when available; otherwise
    estimates a table's share of the file by sampled average row size."""
    from core.database import DB_PATH
    db_size = os.path.getsize(DB_PATH) if os.path.exists(DB_PATH) else 0
    tables: list[dict] = []
    conn = _conn()
    try:
        names = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()]
        sizes: dict[str, int] = {}
        try:  # dbstat counts every page a table (incl. its overflow) uses
            for name, pg in conn.execute(
                "SELECT name, SUM(pgsize) FROM dbstat GROUP BY name"
            ).fetchall():
                sizes[name] = int(pg or 0)
        except sqlite3.Error:
            pass
        for name in names:
            try:
                rows = conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
            except sqlite3.Error:
                rows = 0
            size = sizes.get(name)
            if size is None:  # fallback: sample up to 50 rows for an avg size
                size = 0
                try:
                    cols = [r[1] for r in conn.execute(f'PRAGMA table_info("{name}")').fetchall()]
                    if cols and rows:
                        expr = "+".join(f'COALESCE(LENGTH("{c}"),0)' for c in cols)
                        avg = conn.execute(
                            f'SELECT AVG({expr}) FROM (SELECT * FROM "{name}" LIMIT 50)'
                        ).fetchone()[0] or 0
                        size = int(avg * rows)
                except sqlite3.Error:
                    pass
            tables.append({"table": name, "feature": feature_for_table(name),
                           "bytes": size, "rows": rows})
    finally:
        conn.close()
    tables.sort(key=lambda t: t["bytes"], reverse=True)
    return {"db_path": str(DB_PATH), "db_size_bytes": db_size,
            "total_rows": sum(t["rows"] for t in tables), "tables": tables}


# ════════════════════════════════════════════════════════════════════════════
# Filesystem scan — data dirs / code / vector-graph-logs [S5]
# ════════════════════════════════════════════════════════════════════════════
def _walk_size(path: Path, skip: Optional[set] = None) -> tuple[int, int]:
    """(bytes, file_count) under path, ignoring `skip` dir names. Never raises."""
    total = count = 0
    if not path.exists():
        return 0, 0
    if path.is_file():
        try:
            return path.stat().st_size, 1
        except OSError:
            return 0, 0
    for root, dirs, files in os.walk(path, onerror=lambda e: None):
        if skip:
            dirs[:] = [d for d in dirs if d not in skip]
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
                count += 1
            except OSError:
                pass
    return total, count


def _fs_targets() -> list[dict]:
    """Filesystem areas to attribute (agent.db excluded — the DB scan owns it)."""
    from core.database import DB_PATH
    home = Path.home()
    data_dir = Path(DB_PATH).parent          # ~/.mmo_agent
    return [
        {"label": "Repo code & docs", "path": PROJECT_DIR, "feature": "Codebase",
         "skip": _SKIP_WALK | {"graphify-out", "logs"}},
        {"label": "Knowledge graph index", "path": PROJECT_DIR / "graphify-out", "feature": "Codebase"},
        {"label": "Logs", "path": PROJECT_DIR / "logs", "feature": "System"},
        {"label": "Agent data dir", "path": data_dir, "feature": "Office",
         "skip": {"projects"}, "exclude_files": {Path(DB_PATH).name}},
        {"label": "Project resources drive", "path": data_dir / "projects", "feature": "Projects"},
        {"label": "Hermes memory & skills", "path": home / ".hermes", "feature": "Brain"},
        {"label": "Embeddings cache", "path": home / ".cache" / "fastembed", "feature": "Brain"},
    ]


def scan_fs() -> dict:
    items: list[dict] = []
    for t in _fs_targets():
        path: Path = t["path"]
        excl = t.get("exclude_files") or set()
        size, count = _walk_size(path, t.get("skip"))
        if excl and path.exists() and path.is_dir():
            for name in excl:
                fp = path / name
                if fp.exists():
                    try:
                        size -= fp.stat().st_size
                        count -= 1
                    except OSError:
                        pass
        items.append({"label": t["label"], "path": str(path), "feature": t["feature"],
                      "bytes": max(0, size), "files": max(0, count), "exists": path.exists()})
    return {"items": items}


def scan_deps(force: bool = False) -> dict:
    """venv / node_modules / dist → System bucket. Cached for a week [S24]."""
    conn = _conn()
    try:
        ensure_schema(conn)
        if not force:
            cutoff = (datetime.now(timezone.utc) - timedelta(days=_DEP_CACHE_DAYS)).isoformat()
            row = conn.execute(
                "SELECT taken_at, meta_json FROM storage_snapshots WHERE scope='deps' "
                "AND taken_at >= ? ORDER BY id DESC LIMIT 1", (cutoff,)
            ).fetchone()
            if row and row["meta_json"]:
                try:
                    cached = json.loads(row["meta_json"])
                    cached["cached"] = True
                    cached["taken_at"] = row["taken_at"]
                    return cached
                except (json.JSONDecodeError, TypeError):
                    pass
    finally:
        conn.close()
    items = []
    for label, path in DEP_DIRS:
        size, count = _walk_size(path)
        items.append({"label": label, "path": str(path), "feature": "System",
                      "bytes": size, "files": count, "exists": path.exists()})
    return {"items": items, "cached": False}


# ════════════════════════════════════════════════════════════════════════════
# Snapshot writer + full scan [S4][S8]
# ════════════════════════════════════════════════════════════════════════════
def _write_snapshot(conn: sqlite3.Connection, scope: str, rollup: dict[str, dict],
                    meta: Optional[dict] = None) -> None:
    now = datetime.now(timezone.utc).isoformat()
    for feat, agg in rollup.items():
        conn.execute(
            "INSERT INTO storage_snapshots (taken_at, scope, feature, bytes, item_count, meta_json) "
            "VALUES (?,?,?,?,?,?)",
            (now, scope, feat, int(agg.get("bytes", 0)), int(agg.get("items", 0)), None),
        )
    if meta is not None:  # one meta row per batch (feature='__meta__')
        conn.execute(
            "INSERT INTO storage_snapshots (taken_at, scope, feature, bytes, item_count, meta_json) "
            "VALUES (?,?,?,?,?,?)", (now, scope, "__meta__", 0, 0, json.dumps(meta)),
        )


def _rollup(entries: list[dict], bytes_key: str = "bytes", items_key: str = "files") -> dict[str, dict]:
    out: dict[str, dict] = {}
    for e in entries:
        agg = out.setdefault(e["feature"], {"bytes": 0, "items": 0})
        agg["bytes"] += e.get(bytes_key, 0) or 0
        agg["items"] += e.get(items_key, 0) or 0
    return out


def run_scan(scope: str = "all", force_deps: bool = False) -> dict:
    """Run a scan and persist snapshots. scope: 'db' | 'fs' | 'all'."""
    result: dict = {"scope": scope, "taken_at": datetime.now(timezone.utc).isoformat()}
    conn = _conn()
    try:
        ensure_schema(conn)
        if scope in ("db", "all"):
            db = scan_db()
            roll = _rollup(db["tables"], items_key="rows")
            _write_snapshot(conn, "db", roll,
                            meta={"db_size_bytes": db["db_size_bytes"],
                                  "total_rows": db["total_rows"],
                                  "table_count": len(db["tables"])})
            result["db"] = {"size_bytes": db["db_size_bytes"], "tables": len(db["tables"]),
                            "total_rows": db["total_rows"]}
        if scope in ("fs", "all"):
            fs = scan_fs()
            _write_snapshot(conn, "fs", _rollup(fs["items"]))
            deps = scan_deps(force=force_deps)
            if not deps.get("cached"):
                _write_snapshot(conn, "deps", _rollup(deps["items"]),
                                meta={"items": deps["items"]})
            result["fs"] = {"items": len(fs["items"])}
            result["deps"] = {"cached": bool(deps.get("cached"))}
        conn.commit()
    finally:
        conn.close()
    return result


# ════════════════════════════════════════════════════════════════════════════
# Read side — overview / drill-down / trend [S9][S10][S12]
# ════════════════════════════════════════════════════════════════════════════
def _latest_batch(conn: sqlite3.Connection, scope: str) -> tuple[Optional[str], dict[str, dict]]:
    row = conn.execute(
        "SELECT taken_at FROM storage_snapshots WHERE scope=? ORDER BY id DESC LIMIT 1", (scope,)
    ).fetchone()
    if not row:
        return None, {}
    at = row["taken_at"]
    feats: dict[str, dict] = {}
    for r in conn.execute(
        "SELECT feature, bytes, item_count, meta_json FROM storage_snapshots "
        "WHERE scope=? AND taken_at=?", (scope, at)
    ).fetchall():
        feats[r["feature"]] = {"bytes": r["bytes"], "items": r["item_count"],
                               "meta": r["meta_json"]}
    return at, feats


def overview() -> dict:
    """KPIs + per-feature breakdown + growth trend for the page header + Storage tab."""
    conn = _conn()
    try:
        ensure_schema(conn)
        db_at, db_feats = _latest_batch(conn, "db")
        fs_at, fs_feats = _latest_batch(conn, "fs")
        deps_at, deps_feats = _latest_batch(conn, "deps")

        db_meta = {}
        raw = (db_feats.get("__meta__") or {}).get("meta")
        if raw:
            try:
                db_meta = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                pass

        features: dict[str, dict] = {}
        for feat, agg in db_feats.items():
            if feat == "__meta__":
                continue
            f = features.setdefault(feat, {"feature": feat, "bytes": 0, "db_bytes": 0,
                                           "fs_bytes": 0, "items": 0})
            f["bytes"] += agg["bytes"]; f["db_bytes"] += agg["bytes"]; f["items"] += agg["items"]
        for src in (fs_feats, deps_feats):
            for feat, agg in src.items():
                if feat == "__meta__":
                    continue
                f = features.setdefault(feat, {"feature": feat, "bytes": 0, "db_bytes": 0,
                                               "fs_bytes": 0, "items": 0})
                f["bytes"] += agg["bytes"]; f["fs_bytes"] += agg["bytes"]; f["items"] += agg["items"]

        ranked = sorted(features.values(), key=lambda f: f["bytes"], reverse=True)
        data = [f for f in ranked if f["feature"] not in ("System",)]
        system_bytes = sum(f["bytes"] for f in ranked if f["feature"] == "System")
        total = sum(f["bytes"] for f in ranked)
        data_total = sum(f["bytes"] for f in data)

        # growth trend: per-day totals from snapshot history (last 30 days)
        cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        trend_rows = conn.execute(
            "SELECT substr(taken_at,1,10) AS day, scope, taken_at, SUM(bytes) AS b "
            "FROM storage_snapshots WHERE taken_at >= ? AND feature != '__meta__' "
            "GROUP BY day, scope, taken_at ORDER BY taken_at", (cutoff,)
        ).fetchall()
    finally:
        conn.close()

    # last batch per scope per day → summed across scopes (carrying deps forward)
    per_day: dict[str, dict[str, int]] = {}
    for r in trend_rows:
        d = per_day.setdefault(r["day"], {})
        d[r["scope"]] = r["b"]  # batches are grouped by taken_at; later rows overwrite = latest
    trend, last_scopes = [], {}
    for day in sorted(per_day):
        last_scopes.update(per_day[day])
        trend.append({"day": day, "bytes": sum(last_scopes.values())})

    week_delta = month_delta = 0
    if trend:
        latest = trend[-1]["bytes"]
        week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).date().isoformat()
        base_week = next((t["bytes"] for t in trend if t["day"] >= week_ago), trend[0]["bytes"])
        week_delta = latest - base_week
        month_delta = latest - trend[0]["bytes"]

    return {
        "scanned_at": {"db": db_at, "fs": fs_at, "deps": deps_at},
        "total_bytes": total,
        "data_bytes": data_total,
        "system_bytes": system_bytes,
        "db": {"size_bytes": db_meta.get("db_size_bytes", 0),
               "total_rows": db_meta.get("total_rows", 0),
               "table_count": db_meta.get("table_count", 0)},
        "biggest": data[0] if data else None,
        "features": ranked,
        "trend": trend,
        "growth": {"week_delta_bytes": week_delta, "month_delta_bytes": month_delta,
                   "projection_30d_bytes": (trend[-1]["bytes"] + week_delta * 4) if trend else 0},
    }


def category_detail(feature: str, top_n: int = 12) -> dict:
    """Drill-down [S9]: biggest DB tables + biggest files/dirs for one feature."""
    want = (feature or "").strip().lower()
    feature = next((f for f in FEATURES if f.lower() == want), (feature or "").strip())
    db = scan_db()
    tables = [t for t in db["tables"] if t["feature"] == feature][:top_n]

    fs_items: list[dict] = []
    targets = [t for t in _fs_targets() if t["feature"] == feature]
    if feature == "System":
        targets += [{"label": lbl, "path": p, "feature": "System"} for lbl, p in DEP_DIRS]
    for t in targets:
        path = Path(t["path"])
        if not path.exists():
            continue
        skip = t.get("skip") or set()
        if path.is_dir():
            for child in list(path.iterdir())[:400]:
                # honor the same skip/exclude sets as the rollup so the drill-down
                # numbers agree with the feature chart (venv/.git ∉ Codebase)
                if child.name in (t.get("exclude_files") or set()) or child.name in skip:
                    continue
                size, count = _walk_size(child, skip)
                fs_items.append({"name": str(child.relative_to(path.parent)),
                                 "bytes": size, "files": count})
        else:
            size, count = _walk_size(path)
            fs_items.append({"name": path.name, "bytes": size, "files": count})
    fs_items.sort(key=lambda i: i["bytes"], reverse=True)

    # Vault privacy [S28]: only size + item count ever leave this function — the
    # tables list carries no row content, and we add an explicit note.
    out = {"feature": feature, "tables": tables, "fs_items": fs_items[:top_n]}
    if feature == "Vault":
        out["note"] = "Encrypted vault is reported by size and item count only."
    return out


def summary_compact() -> dict:
    """Small storage summary for the Conductor tool + Dashboard widget [S25][S29]."""
    ov = overview()
    top = [{"feature": f["feature"], "bytes": f["bytes"]} for f in ov["features"][:5]
           if f["feature"] != "__meta__"]
    return {
        "total_bytes": ov["total_bytes"],
        "data_bytes": ov["data_bytes"],
        "system_bytes": ov["system_bytes"],
        "db_size_bytes": ov["db"]["size_bytes"],
        "db_rows": ov["db"]["total_rows"],
        "biggest": ov["biggest"],
        "top_features": top,
        "week_delta_bytes": ov["growth"]["week_delta_bytes"],
        "scanned_at": ov["scanned_at"],
    }

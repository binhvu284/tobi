"""
PERFORMANCE DOCTOR (#19) — a "system doctor" for TOBI Mission Control.

Analyzes MC's **runtime performance** (LLM latency/cost/requests, storage growth) **and**
its **code/architecture** (size, coupling, god-modules, TODO debt) to answer one question:
is the system healthy and optimized, or does it need refactoring — and exactly where?

Design (spec §Architecture):
- **Graphify-first** to save tokens: the existing ``graphify-out/graph.json`` (nodes with
  ``source_file``/``community``; links with ``relation`` → import fan-in/fan-out, god-modules)
  is the MAP. Source files are only opened to count LOC (I/O, no tokens); the LLM is used ONLY
  in Deep mode to write a short prose diagnosis over already-computed numbers (never raw code).
- **Deterministic heuristics + graphify** find candidates; grading is a transparent rubric.
- Subsystems are **feature areas** (Brain, Graph, Conductor & Chat, …). Findings are
  file/function-level with severity × effort. Snapshots persist for a score trend.
- The graph's ``built_at_commit`` vs HEAD is reported as a **staleness** finding.

Never raises: a missing graph degrades to a filesystem scan; missing metrics → code-only grade.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).resolve().parent.parent          # the tobi/ repo root
_GRAPH = _ROOT / "graphify-out" / "graph.json"
_AST = _ROOT / "graphify-out" / ".graphify_ast.json"

# Feature-area subsystems, matched by source_file prefix (first match wins). [D14]
SUBSYSTEMS: list[tuple[str, tuple[str, ...]]] = [
    ("Brain", ("core/brain", "core/memory")),
    ("Graph", ("core/graph",)),
    ("Conductor & Chat", ("core/conductor", "core/chat_modes", "core/chat_store", "core/chat_runtime",
                          "core/tool_registry", "core/context_manager", "core/deep_research",
                          "core/premium_readers", "core/youtube_reader", "core/model_router",
                          "core/model_capabilities", "core/net_guard", "core/attachments",
                          "core/task_classifier", "core/agent_runs")),
    ("Terminal", ("core/terminal",)),
    ("Projects", ("core/pm_", "core/projects")),
    ("Integrations & MCP", ("core/mcp", "core/a2a", "core/integrations", "core/vault", "core/hermes")),
    ("Explore", ("core/explore",)),
    ("Storage & Usage", ("core/storage", "core/usage", "core/performance_doctor")),
    ("API", ("api/",)),
    ("Frontend", ("dashboard/src",)),
]

# rubric thresholds
_BIG_FILE = 800          # LOC above which a file starts costing points
_HUGE_FILE = 1800        # LOC above which it's a high-severity split candidate
# Import fan-in+fan-out above which a module is treated as a coupling hub.
#
# Recalibrated 26 -> 40 (2026-07-25) against the real degree distribution of this
# codebase (399 files: median 5, p90 14, p95 18, p99 43, max 100). At 26 the rubric
# flagged 9 modules, but most were correctly-shaped rather than tangled:
#   - shared infrastructure with high fan-IN — core/database.py (88 in), model_router.py
#     (36 in), vault.py (34 in), owner_flags.py (26 in), ToastProvider.tsx (41 in).
#     Many modules depending on one service is the intended shape; "fixing" it means
#     duplicating access or adding indirection that helps no one.
#   - composition roots with high fan-OUT — api/dashboard.py (46 out) and App.tsx
#     (23 out). An app factory must import the routers it mounts; this number went UP
#     as a direct result of decomposing the monolith, i.e. the metric was penalising
#     the refactor it exists to encourage.
# 40 keeps the top ~1% flagged (genuine blast-radius risk) without taxing every shared
# service. KNOWN LIMITATION: degree still sums fan-in and fan-out, so a widely-used
# utility and a genuinely tangled module score alike. Distinguishing them (e.g. flag
# only when BOTH directions are high) is a separate rubric change, deliberately not
# bundled with this recalibration.
_GOD_DEGREE = 40
# An actionable debt marker lives in a COMMENT. Anchoring the match to a comment opener
# stops the metric counting the bare word where it appears as code, data or prose.
#
# The bare-word version scored 14 markers across the whole codebase and 13 of them were
# in THIS file — the marker regex itself, plus the findings text that reports on marker
# debt. The doctor was billing its own rubric as the codebase's only TODO debt (10.2 pts
# off Storage & Usage, the subsystem that owns this module). Real application code has
# none. KNOWN LIMITATION: a marker written in a docstring rather than a `#` comment is
# no longer counted, and prose *about* markers inside a comment still is.
_TODO_RE = re.compile(r"(?:#|//|/\*)[^\n]*?\b(TODO|FIXME|HACK|XXX)\b")
_CODE_EXT = (".py", ".ts", ".tsx", ".js", ".jsx")


# ── graph + code metrics ──────────────────────────────────────────────────────────
def _load_graph() -> Optional[dict]:
    try:
        return json.loads(_GRAPH.read_text(encoding="utf-8"))
    except Exception:
        return None


def _rel_source_files(graph: Optional[dict]) -> list[str]:
    """Unique internal source files graphify indexed (repo-relative, code only)."""
    files: set[str] = set()
    if graph:
        for n in graph.get("nodes", []):
            sf = (n.get("source_file") or "").replace("\\", "/")
            if sf and sf.endswith(_CODE_EXT):
                files.add(sf)
    if not files:  # graph missing → walk the tree (bounded to the source dirs)
        for base in ("core", "api", "dashboard/src", "hermes_skills"):
            for p in (_ROOT / base).rglob("*"):
                if p.suffix in _CODE_EXT and "node_modules" not in p.parts and "dist" not in p.parts:
                    files.add(str(p.relative_to(_ROOT)).replace("\\", "/"))
    return sorted(files)


def _loc(rel: str) -> int:
    """Line count of a repo file (I/O only, never raises)."""
    try:
        with open(_ROOT / rel, "r", encoding="utf-8", errors="ignore") as fh:
            return sum(1 for _ in fh)
    except Exception:
        return 0


def _todo_count(rel: str) -> int:
    try:
        with open(_ROOT / rel, "r", encoding="utf-8", errors="ignore") as fh:
            return sum(len(_TODO_RE.findall(line)) for line in fh)
    except Exception:
        return 0


def _coupling(graph: Optional[dict]) -> tuple[dict[str, int], dict[str, int]]:
    """(fan_in, fan_out) per source_file from import links. fan_out = distinct internal modules
    the file imports; fan_in = distinct files importing it."""
    fan_in: dict[str, set] = defaultdict(set)
    fan_out: dict[str, set] = defaultdict(set)
    if not graph:
        return {}, {}
    id2file = {n.get("id"): (n.get("source_file") or "").replace("\\", "/")
               for n in graph.get("nodes", [])}
    for e in graph.get("links", []):
        if e.get("relation") not in ("imports", "imports_from"):
            continue
        src = id2file.get(e.get("source"), "")
        tgt = id2file.get(e.get("target"), "")     # internal target only (external → "")
        if src and tgt and src != tgt:
            fan_out[src].add(tgt)
            fan_in[tgt].add(src)
    return ({k: len(v) for k, v in fan_in.items()}, {k: len(v) for k, v in fan_out.items()})


def _subsystem_of(rel: str) -> str:
    rel = rel.replace("\\", "/")
    for name, prefixes in SUBSYSTEMS:
        if any(rel.startswith(p) for p in prefixes):
            return name
    return "Other"


def _analyze_code(graph: Optional[dict]) -> dict:
    files = _rel_source_files(graph)
    fan_in, fan_out = _coupling(graph)
    per_file: dict[str, dict] = {}
    for rel in files:
        loc = _loc(rel)
        if loc == 0:
            continue
        fi, fo = fan_in.get(rel, 0), fan_out.get(rel, 0)
        per_file[rel] = {"file": rel, "loc": loc, "fan_in": fi, "fan_out": fo,
                         "degree": fi + fo, "todos": _todo_count(rel),
                         "subsystem": _subsystem_of(rel)}
    return {"files": per_file}


# ── runtime metrics (defensive; missing → code-only) ───────────────────────────────
def _analyze_runtime() -> dict:
    out: dict = {"available": False}
    try:
        from core import usage_meter
        ov = usage_meter.overview("month") or {}
        tot = ov.get("totals") or ov
        out.update({"available": True,
                    "requests": tot.get("requests") or tot.get("calls") or 0,
                    "cost_usd": tot.get("cost") or tot.get("cost_est") or tot.get("cost_usd") or 0,
                    "avg_latency_ms": tot.get("avg_latency_ms") or tot.get("latency_ms") or 0,
                    "by_surface": ov.get("by_surface") or ov.get("surfaces") or []})
    except Exception:
        pass
    try:
        from core import storage_scan
        so = storage_scan.overview() if hasattr(storage_scan, "overview") else {}
        out["storage_bytes"] = (so or {}).get("total_bytes") or (so or {}).get("total") or 0
        out["storage_growth_30d"] = (so or {}).get("growth_30d") or (so or {}).get("delta_month") or 0
    except Exception:
        pass
    return out


# ── grading ────────────────────────────────────────────────────────────────────────
def _grade_letter(score: float) -> str:
    for cut, letter in [(93, "A"), (90, "A-"), (87, "B+"), (83, "B"), (80, "B-"),
                        (77, "C+"), (73, "C"), (70, "C-"), (60, "D"), (0, "F")]:
        if score >= cut:
            return letter
    return "F"


def _grade_subsystems(code: dict, runtime: dict) -> list[dict]:
    by_sub: dict[str, list[dict]] = defaultdict(list)
    for f in code["files"].values():
        by_sub[f["subsystem"]].append(f)

    subs: list[dict] = []
    for name, _ in SUBSYSTEMS + [("Other", ())]:
        fs = by_sub.get(name)
        if not fs:
            continue
        total_loc = sum(f["loc"] for f in fs)
        max_loc = max(f["loc"] for f in fs)
        max_degree = max(f["degree"] for f in fs)
        todos = sum(f["todos"] for f in fs)
        oversized = [f for f in fs if f["loc"] > _BIG_FILE]
        gods = [f for f in fs if f["degree"] >= _GOD_DEGREE]

        score = 100.0
        # size debt — every LOC over the big-file line costs, more for huge files
        score -= min(30.0, sum(max(0, f["loc"] - _BIG_FILE) / 90.0 for f in fs))
        # coupling debt — god-modules
        score -= min(22.0, sum(max(0, f["degree"] - _GOD_DEGREE) * 1.4 for f in gods))
        # TODO/FIXME debt per KLOC
        score -= min(12.0, (todos / max(1.0, total_loc / 1000.0)) * 1.2)
        score = max(0.0, round(score, 1))

        subs.append({
            "name": name, "score": score, "grade": _grade_letter(score),
            "files": len(fs), "total_loc": total_loc, "max_loc": max_loc,
            "max_degree": max_degree, "todos": todos,
            "oversized": len(oversized), "god_modules": len(gods),
        })
    subs.sort(key=lambda s: s["score"])
    return subs


# ── findings ─────────────────────────────────────────────────────────────────────
def _effort(loc: int) -> str:
    return "L" if loc >= _HUGE_FILE else "M" if loc >= _BIG_FILE else "S"


def _build_findings(code: dict, subs: list[dict], freshness: dict, runtime: dict) -> list[dict]:
    findings: list[dict] = []
    sev_w = {"high": 3, "med": 2, "low": 1}

    for f in code["files"].values():
        if f["loc"] >= _BIG_FILE:
            sev = "high" if f["loc"] >= _HUGE_FILE else "med"
            findings.append({
                "title": f"Split {f['file']} (~{f['loc']:,} LOC)",
                "subsystem": f["subsystem"], "severity": sev, "effort": _effort(f["loc"]),
                "detail": f"{f['file']} is {f['loc']:,} lines — a large module is hard to change "
                          f"safely. Extract cohesive groups into focused files.",
                "target": f["file"], "kind": "size",
            })
        if f["degree"] >= _GOD_DEGREE:
            findings.append({
                "title": f"Reduce coupling of {f['file']} (fan-in {f['fan_in']} / fan-out {f['fan_out']})",
                "subsystem": f["subsystem"], "severity": "med", "effort": "M",
                "detail": f"{f['file']} is a hub: {f['fan_in']} modules import it and it imports "
                          f"{f['fan_out']}. High coupling makes changes ripple. Consider interfaces "
                          "or splitting responsibilities.",
                "target": f["file"], "kind": "coupling",
            })

    # TODO debt per subsystem (only the noisiest)
    for s in subs:
        if s["todos"] >= 15:
            findings.append({
                "title": f"{s['todos']} TODO/FIXME markers in {s['name']}",
                "subsystem": s["name"], "severity": "low", "effort": "S",
                "detail": f"{s['name']} carries {s['todos']} unresolved TODO/FIXME/HACK markers — "
                          "triage or convert them into tracked tasks.",
                "target": s["name"], "kind": "debt",
            })

    if freshness.get("stale"):
        findings.append({
            "title": f"Graphify graph is {freshness.get('behind_label', 'behind')} — refresh for accuracy",
            "subsystem": "Storage & Usage", "severity": "low", "effort": "S",
            "detail": f"The analysis map was built at commit {freshness.get('built_short')} but HEAD is "
                      f"{freshness.get('head_short')}. Run `/graphify --update` so hotspots reflect "
                      "current code.", "target": "graphify-out/graph.json", "kind": "freshness",
        })

    if runtime.get("available") and (runtime.get("avg_latency_ms") or 0) >= 9000:
        findings.append({
            "title": f"High average LLM latency (~{int(runtime['avg_latency_ms'])} ms)",
            "subsystem": "Conductor & Chat", "severity": "med", "effort": "M",
            "detail": "Average model latency is high this month — consider a faster default model, "
                      "streaming, or trimming context.", "target": "model_router", "kind": "runtime",
        })

    # rank: severity, then impact (size/coupling worst first), preferring lower effort within tier
    eff_w = {"S": 0, "M": 1, "L": 2}
    findings.sort(key=lambda x: (-sev_w[x["severity"]], eff_w[x["effort"]], x["title"]))
    return findings


# ── freshness ──────────────────────────────────────────────────────────────────────
def _git(*args: str) -> Optional[str]:
    try:
        out = subprocess.run(["git", *args], cwd=str(_ROOT), capture_output=True,
                             text=True, timeout=6)
        return out.stdout.strip() if out.returncode == 0 else None
    except Exception:
        return None


def _freshness(graph: Optional[dict]) -> dict:
    built = (graph or {}).get("built_at_commit") if graph else None
    head = _git("rev-parse", "HEAD")
    res = {"built": built, "head": head, "stale": False,
           "built_short": (built or "?")[:8], "head_short": (head or "?")[:8]}
    if built and head and built != head:
        res["stale"] = True
        behind = _git("rev-list", "--count", f"{built}..{head}")
        res["behind_label"] = f"{behind} commits behind" if behind else "behind"
    elif not graph:
        res["stale"] = True
        res["behind_label"] = "missing — no graph indexed"
    return res


# ── overall + diagnosis ─────────────────────────────────────────────────────────────
def _overall(subs: list[dict], runtime: dict) -> dict:
    if not subs:
        return {"score": 0.0, "grade": "F"}
    total_loc = sum(s["total_loc"] for s in subs) or 1
    score = sum(s["score"] * s["total_loc"] for s in subs) / total_loc  # LOC-weighted
    if runtime.get("available") and (runtime.get("avg_latency_ms") or 0) >= 9000:
        score -= 2.0
    score = max(0.0, round(score, 1))
    return {"score": score, "grade": _grade_letter(score)}


def _quick_diagnosis(overall: dict, subs: list[dict], findings: list[dict], freshness: dict) -> str:
    if not subs:
        return "No code was indexed, sir — I couldn't build a picture. Run `/graphify` first."
    weakest, strongest = subs[0], subs[-1]
    highs = [f for f in findings if f["severity"] == "high"]
    parts = [
        f"Overall optimization **{overall['grade']} ({overall['score']:.0f}/100)**.",
        f"Strongest: **{strongest['name']}** ({strongest['grade']}). "
        f"Weakest: **{weakest['name']}** ({weakest['grade']}).",
    ]
    if highs:
        parts.append(f"{len(highs)} high-severity item(s) — top: {highs[0]['title']}.")
    else:
        parts.append("No high-severity items — mostly incremental cleanups.")
    verdict = ("A refactor is worth scheduling" if overall["score"] < 78 or len(highs) >= 2
               else "No urgent refactor needed; keep an eye on the hotspots")
    parts.append(f"{verdict}, sir.")
    if freshness.get("stale"):
        parts.append(f"(Note: the map is {freshness.get('behind_label', 'stale')} — refresh graphify for precision.)")
    return " ".join(parts)


def _llm_diagnosis(result: dict, model: Optional[str]) -> Optional[str]:
    """Deep mode: ONE strict-budget LLM call over the computed summaries (never raw code)."""
    try:
        from core.model_router import get_llm, set_usage_context
    except Exception:
        return None
    subs = result["subsystems"]
    findings = result["findings"][:8]
    summary = {
        "overall": result["overall"],
        "subsystems": [{"name": s["name"], "grade": s["grade"], "score": s["score"],
                        "max_loc": s["max_loc"], "god_modules": s["god_modules"]} for s in subs],
        "top_findings": [{"title": f["title"], "severity": f["severity"], "effort": f["effort"]}
                         for f in findings],
        "freshness": result["freshness"].get("behind_label", "fresh"),
    }
    prompt = (
        "You are TOBI's system doctor. Below is a computed performance/architecture scorecard for "
        "Mission Control (numbers already derived — do NOT invent new facts). In 4-6 sentences, give "
        "the owner an honest read: is the system healthy and optimized or does it need refactoring, "
        "which subsystem to tackle first and why, and one concrete next step. Butler tone, address "
        "him as 'sir'. Base every claim ONLY on this data:\n\n"
        + json.dumps(summary, ensure_ascii=False)
    )
    prev = set_usage_context("health", "performance")
    try:
        client = get_llm("simple", model=model) if model else get_llm("simple")
        # 900 gives a 4-6 sentence butler diagnosis comfortable headroom so it never
        # gets cut mid-sentence (520 truncated real Deep runs); still well within the
        # ~$0.05-$0.15 Deep budget on the 'simple' tier.
        out = client.complete([{"role": "user", "content": prompt}], max_tokens=900)
        return (out or "").strip() or None
    except Exception:
        return None
    finally:
        set_usage_context(prev["surface"], prev["feature"])


# ── persistence ──────────────────────────────────────────────────────────────────────
def _conn():
    from core.database import get_connection
    return get_connection()


def _ensure_table(conn) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS performance_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            taken_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            depth TEXT, overall_score REAL, overall_grade TEXT,
            subsystems_json TEXT, findings_json TEXT, diagnosis TEXT, meta_json TEXT
        )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_perf_snap_at ON performance_snapshots(taken_at)")


def _save_snapshot(result: dict, depth: str) -> Optional[int]:
    try:
        conn = _conn()
        try:
            _ensure_table(conn)
            cur = conn.execute(
                "INSERT INTO performance_snapshots "
                "(depth, overall_score, overall_grade, subsystems_json, findings_json, diagnosis, meta_json) "
                "VALUES (?,?,?,?,?,?,?)",
                (depth, result["overall"]["score"], result["overall"]["grade"],
                 json.dumps(result["subsystems"], default=str),
                 json.dumps(result["findings"], default=str),
                 result.get("diagnosis", ""),
                 json.dumps({"runtime": result.get("runtime"), "freshness": result.get("freshness"),
                             "generated_ms": result.get("generated_ms")}, default=str)))
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()
    except Exception:
        return None


def trend(limit: int = 30) -> list[dict]:
    """Score over time (oldest→newest) for the trend chart."""
    try:
        conn = _conn()
        try:
            _ensure_table(conn)
            rows = conn.execute(
                "SELECT taken_at, overall_score, overall_grade, depth FROM performance_snapshots "
                "ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        finally:
            conn.close()
        return [{"taken_at": r[0], "score": r[1], "grade": r[2], "depth": r[3]}
                for r in reversed(rows)]
    except Exception:
        return []


def latest() -> Optional[dict]:
    """The most recent stored analysis, rehydrated, with the trend attached."""
    try:
        conn = _conn()
        try:
            _ensure_table(conn)
            r = conn.execute(
                "SELECT id, taken_at, depth, overall_score, overall_grade, subsystems_json, "
                "findings_json, diagnosis, meta_json FROM performance_snapshots "
                "ORDER BY id DESC LIMIT 1").fetchone()
        finally:
            conn.close()
        if not r:
            return None
        meta = json.loads(r[8] or "{}")
        return {
            "id": r[0], "taken_at": r[1], "depth": r[2],
            "overall": {"score": r[3], "grade": r[4]},
            "subsystems": json.loads(r[5] or "[]"), "findings": json.loads(r[6] or "[]"),
            "diagnosis": r[7] or "", "runtime": meta.get("runtime"),
            "freshness": meta.get("freshness"), "trend": trend(),
        }
    except Exception:
        return None


# ── entry point ──────────────────────────────────────────────────────────────────────
def analyze(depth: str = "quick", model: Optional[str] = None) -> dict:
    """Run a Performance analysis. depth: 'quick' (graph + metrics, ~free) or 'deep' (adds one
    strict-budget LLM diagnosis). Always persists a snapshot; never raises."""
    t0 = time.time()
    depth = "deep" if str(depth).lower() == "deep" else "quick"
    graph = _load_graph()
    freshness = _freshness(graph)
    code = _analyze_code(graph)
    runtime = _analyze_runtime()
    subs = _grade_subsystems(code, runtime)
    overall = _overall(subs, runtime)
    findings = _build_findings(code, subs, freshness, runtime)
    result = {
        "depth": depth, "overall": overall, "subsystems": subs, "findings": findings,
        "runtime": runtime, "freshness": freshness,
        "counts": {"files": len(code["files"]), "findings": len(findings),
                   "high": sum(1 for f in findings if f["severity"] == "high")},
    }
    result["diagnosis"] = _quick_diagnosis(overall, subs, findings, freshness)
    if depth == "deep":
        deep = _llm_diagnosis(result, model)
        if deep:
            result["diagnosis"] = deep
            result["deep_synthesized"] = True
    result["generated_ms"] = int((time.time() - t0) * 1000)
    result["id"] = _save_snapshot(result, depth)
    result["trend"] = trend()
    return result

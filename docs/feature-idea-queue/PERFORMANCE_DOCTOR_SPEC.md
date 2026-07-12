# Performance "System Doctor" — Health ▸ Performance tab

> Queue item **#19**. On-demand analysis of TOBI Mission Control's runtime performance **and**
> code/architecture, so the owner (and TOBI) can see the full optimization picture and know
> whether the system needs refactoring. Graphify-first so every run is cheap.

## Locked decisions (15-question intake)

1. **Scope** — runtime **+** code/architecture (full optimization + refactor picture).
2. **Primary substrate** — **graphify graph first** (`graphify-out/graph.json` nodes/links/
   communities as the map); open source only for flagged spots.
3. **Codebase access** — the local working tree.
4. **Trigger** — on-demand button **+** a Conductor tool (no background cost).
5. **Depth** — **Quick** (graph + metrics, ~free) / **Deep** toggle (adds strict-budget LLM synthesis).
6. **Budget** — Deep audit hard-capped ~$0.05–$0.15 (1 LLM synthesis call over computed summaries + a few flagged snippets, never the whole codebase).
7. **Bug detection** — deterministic heuristics + graphify find candidates; LLM only writes the summary.
8. **Quality bar** — graded against **TOBI docs (ARCHITECTURE.md/CLAUDE.md intent) + a general engineering rubric** (size, coupling, cohesion, complexity, TODO debt, runtime errors/latency).
9. **Output** — overall optimization **score gauge** + per-subsystem **grade cards** + ranked **findings** (severity × effort) + a short **diagnosis**.
10. **Refactor advice** — file/function-level, with severity + effort estimate.
11. **Actionability** — optional **Create task** per finding (reuses #7 `create_task`); nothing auto-created.
12. **History** — persisted **snapshots** + score **trend** (mirrors Storage #10).
13. **Chat** — a Conductor **read tool** that can run (Quick) or report the latest analysis.
14. **Subsystems** — by **feature area**: Brain · Graph · Conductor & Chat · Terminal · Projects · Integrations & MCP · Explore · Storage & Usage · API · Frontend.
15. **UI** — a separate **Performance tab** inside the Health page, with a **smooth "running diagnostics" animation** (micro-motion sweep while it works).

## Architecture

**`core/performance_doctor.py`** (never raises; degrades honestly):
- **Graph load** — `graphify-out/graph.json` (nodes: `source_file`, `community`; links: `relation` ∈ imports/imports_from/contains → fan-in/fan-out, god-modules) + `.graphify_ast.json` for per-file symbols. Reports **staleness** (`built_at_commit` vs current HEAD) as a finding.
- **Code metrics** (I/O only, no tokens) — LOC per indexed source file (local read), symbol/fan-in/fan-out per module, god-nodes, TODO/FIXME/HACK density.
- **Runtime metrics** — `usage_meter.overview` (cost/latency/requests, per surface), `storage_scan` (DB/dir size + growth). Defensive; missing data → code-only grade.
- **Grade** — per-subsystem 0–100 + letter from a rubric (penalize oversized files >~800 LOC, high coupling, TODO debt, error/latency); overall = weighted mean.
- **Findings** — ranked file/function-level items `{title, subsystem, severity, effort, detail, target}`.
- **Deep** — one strict-budget LLM call over the computed scorecard/findings **summaries** (no raw code) → prose diagnosis; `set_usage_context("health","performance")`.
- **Snapshots** — `performance_snapshots(id, taken_at, depth, overall_score, overall_grade, subsystems_json, findings_json, diagnosis, meta_json)`; trend = score over time.

**API** (`api/dashboard.py`): `GET /api/health/performance` (latest + trend), `POST /api/health/performance/run` (`{depth}`), `POST /api/health/performance/finding/task` (create task from a finding).

**Conductor**: read tool `analyze_performance` (Quick run or report latest → grounded scorecard + top findings) in `READ_TOOLS`.

**Frontend** (`dashboard/src/pages/Health.tsx`): Overview | Performance tabs; Performance = score gauge + subsystem grade cards + ranked findings (+task) + diagnosis + trend sparkline + Quick/Deep toggle + Run; reuse the radar-scan/`Stagger` motion for the running sweep.

## Verification
`tests/test_performance_doctor.py` (temp DB): graph-based code metrics, subsystem mapping + grading, findings ranking, staleness detection, snapshot persist + trend, Deep synthesis stubbed, graph-missing degradation. Plus `tsc` + build for the Health tab.

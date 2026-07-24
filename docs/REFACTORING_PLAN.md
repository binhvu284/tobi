# TOBI Refactoring Plan

**Date:** 2026-07-18 · **Status:** Proposed (not started) · **Owner sign-off required before any slice touches `main`.**

This plan targets *structural* debt — oversized modules that are hard to navigate, review, and edit safely. It is deliberately **behavior-preserving**: every step is a mechanical move or split with an automated parity check. No logic changes ride along.

---

## 1. Diagnosis

Largest files today (lines):

| Layer | File | Lines | Character |
|---|---|---:|---|
| Backend | **`api/dashboard.py`** | **6,636** | **266 routes** across ~25 path groups — a true monolith (CLAUDE.md already flags it) |
| Backend | `core/conductor.py` | 3,121 | orchestration god-object; real domain complexity |
| Backend | `core/development_store.py` | 1,748 | large but cohesive persistence layer |
| Backend | `core/database.py` | 1,740 | central DDL — big *by design* (single source of truth) |
| Backend | `core/brain.py` | 1,415 | legacy brain runtime |
| Backend | `core/coding_agent.py` / `telegram_bot.py` | 1,344 / 1,306 | cohesive |
| Frontend | `dashboard/src/pages/Chat.tsx` | 1,532 | page god-component |
| Frontend | `dashboard/src/pages/Developer.tsx` | 1,472 | page god-component |
| Frontend | `dashboard/src/api.ts` | 1,034 | client barrel; split already begun |
| Frontend | `dashboard/src/pages/BrainV2.tsx` | 983 | tabs inline in one file |
| Frontend | `dashboard/src/pages/Architecture.tsx` | 804 | panes inline in one file |

**The unlock:** the safe pattern already exists in-repo. `api/developer.py` (638 lines) and `api/brain_v2.py` (463 lines) are `APIRouter`s that import services directly from `core/*` and are registered in `dashboard.py` via `include_router` (lines 191, 200). This refactor **finishes an established pattern** rather than inventing one.

---

## 2. Priority 1 — Decompose `api/dashboard.py`

**Goal:** shrink `dashboard.py` from 6,636 lines to a thin app factory (< ~500 lines): `FastAPI(...)`, `NoCacheAPIMiddleware`, the static React / SPA host, and router registration. Every route group moves to `api/routers/<group>.py`.

### Route-group inventory (extraction units)

Counts from `@app.<method>("/api/<group>...")` decorators:

| Group | Routes | | Group | Routes |
|---|---:|---|---|---:|
| `pm` (projects/resources) | 43 | | `usage` | 7 |
| `mcp` | 29 | | `terminal` | 7 |
| `brain` (legacy v1) | 27 | | `architecture` | 7 |
| `chat` | 19 | | `missions` | 5 |
| `graph` | 16 | | `keys` | 5 |
| `vault` | 11 | | `health` | 4 |
| `explore` | 11 | | `storage` | 3 |
| `tasks` | 9 | | `conductor` | 3 |
| `office` | 9 | | `agents` | 3 |
| `integrations` | 9 | | `abilities` | 3 |
| `llm` | 8 | | (misc: status, workflows, owner, run, proposals, evolution, awakening, hermes) | ~10 |

Already extracted (do not touch): `developer`, `brain/v2`.

### Slice 0 — shared dependency module (prep, no routes move)

Routes close over module-level helpers. Extract the shared surface into **`api/deps.py`** and have `dashboard.py` + future routers import from it:

- Constants: `DB_PATH`, `LOGS_DIR`, `DIST_DIR`
- DB: `_get_conn()`
- Serializers/helpers: `_json_loads`, `fmt_ago`, `_sse`, `_serialize_task`, `_serialize_agent`, `_serialize_mission`, `_append_activity`, `_fetch_activity`, `_fetch_checklist`, `_fetch_task_row`, `_task_deps`, `_legacy_status_from_v1`

Zero behavior change; pure move + import rewire.

### Slices 1…N — one route group per commit

Each `api/routers/<group>.py` carries its **own** Pydantic request models and any group-local helpers, exposes an `APIRouter(prefix="/api/<group>", tags=["<group>"])`, and is registered with `app.include_router(...)` in `dashboard.py`.

**Extraction order — easiest/most-isolated first** (limits blast radius, builds confidence):

1. **Self-contained:** `health` → `usage` → `storage` → `architecture` → `explore` → `office` → `missions` → `agents` → `abilities`
2. **Mid-coupling:** `tasks` → `graph` → `integrations` → `terminal` → `llm` → `vault` → `keys` → `conductor` → `chat`
3. **Heavy/last:** `pm` (43 routes) → `mcp` (29 routes)
4. **Core last of all:** the task/activity/owner-input core and the static-host + SSE plumbing stay in `dashboard.py` (or move to a final `routers/core.py`).

### Verification per slice (four gates — all required)

Route parity alone is **not sufficient**. It confirms a route still *exists*, but a
handler that references a `dashboard.py` module-global (`graph`, `_last`, `json`, a
regex constant…) which didn't travel with its block still imports fine and still
lists in openapi — then throws `NameError` only when the endpoint is *called*. Two
early slices shipped exactly this bug. The gate is therefore:

1. **pyflakes** on the new router + `deps.py` + `dashboard.py` → **zero `undefined name`**.
   This is the gate that catches the transitive-dependency class of bug. Install once:
   `venv/Scripts/python.exe -m pip install pyflakes`.
2. **Import smoke:** `python -c "import api.dashboard"` succeeds.
3. **Route parity:** dump the sorted `(METHOD, path)` set from `app.openapi()` before and
   after; the diff must be empty (baseline: **329 operations**). Script:
   `scratchpad/route_snapshot.py`.
4. **In-process TestClient smoke:** hit 1–2 representative GETs of the moved group and
   assert `200` — the only gate that actually *executes* the handler.

Each undefined name pyflakes reports is resolved by either importing the symbol from
`core.*` (if it was a core import), pulling it from `api/deps.py` (if genuinely shared),
or moving the helper cluster into the router (if now used only by that group).

---

## 3. Priority 2 — Frontend structural cleanup (low risk, mechanical)

- **`api.ts` (1,034)** — finish the split already started (`api.brainV2.ts`, `api.architecture.ts` exist). Carve remaining domains into `api.<domain>.ts` and **re-export from `api.ts`** so no import site changes. Verify with `tsc --noEmit`.
- **`BrainV2.tsx` (983)** — extract tabs/rows into `pages/brain/{LibraryTab,ImportTab,TellTab,MemoryRow,OverviewTab}.tsx`; `BrainV2.tsx` becomes the shell that wires tab state.
- **`Architecture.tsx` (804)** — extract `pages/architecture/{DiagramPane,GuidePanel,MapPanel}.tsx` + the mermaid render/label hooks into a `useMermaidDiagram` module.
- **`Chat.tsx` (1,532) / `Developer.tsx` (1,472)** — larger effort: pull hooks + subcomponents out. Schedule **after** the `api.ts` split so the new API modules are the import target.

Verification: `tsc --noEmit -p dashboard/tsconfig.json` + `vite build` green after each extraction; page renders unchanged (headless screenshot diff for Brain/Architecture).

---

## 4. Priority 3 — `core/conductor.py` (3,121) — deferred

Real domain complexity (routing, grounding, tool execution under risk policy), not just size. Needs its own analysis pass to find safe seams before any split. **Not a quick win — do not bundle it with the mechanical work above.**

---

## 4b. Progress log

Branch `refactor/dashboard-decomposition` (not merged to `main`).

| Slice | What | Result |
|---|---|---|
| 0 | `api/deps.py` — shared primitives (`DB_PATH`, `_get_conn`, `_json_loads`, `fmt_ago`; later `_last`, `LOGS_DIR`) | ✅ verified |
| 1 | `api/routers/health.py` — `/api/health/*` (+ log-tail cluster moved here) | ✅ verified |
| 2 | `api/routers/explore.py` — `/api/explore/*` | ✅ verified |
| 3 | `api/routers/graph.py` — `/api/graph/*` | ✅ verified |
| 4 | `api/routers/storage.py` — `/api/storage/*` | ✅ verified |
| 5 | `api/routers/architecture.py` — `/api/architecture/*` | ✅ verified |
| 6 | `api/routers/agents.py` — `/api/agents/*` (+ re-export `api_agents` for the office aggregate) | ✅ verified |
| 7 | `api/routers/missions.py` — `/api/missions/*` (+ `_sse`, `_serialize_mission`) | ✅ verified |
| 8 | `api/routers/office.py` — `/api/office/*` (imports `api_agents`+`api_missions`) | ✅ verified |
| 9 | `api/routers/usage.py` — `/api/usage/*` | ✅ verified |
| 10 | `api/routers/terminal.py` — `/api/terminal/*` (#11 CLI) | ✅ verified |
| 11 | `api/routers/conductor.py` — `/api/conductor/*` (#7) | ✅ verified |
| 12 | `api/routers/owner.py` — `/api/owner/*` (`_get_conn` via deps) | ✅ verified |
| 13 | `api/routers/keys.py` — `/api/keys/*` (+ `_vault_guard` lifted to deps) | ✅ verified |
| 14 | `api/routers/llm.py` — `/api/llm/*` (usage/config/models/provider-key) | ✅ verified |
| 15 | `core/awakening_detect.py` — moved `_TIER_DEFINITIONS`+`_detect_abilities`+`_ABILITY_NAMES` (~359 lines) out of dashboard to core; fixes the core→api backdep | ✅ verified |
| 16 | `api/routers/mcp.py` — `/api/mcp/*` (10 models + `_mcp_guard` + 29 routes, ~298 lines) | ✅ verified |
| 17 | `api/routers/brain.py` — `/api/brain/*` legacy v1 (`_brain_backend`/`_brain_call` + 10 models + 27 routes, ~303 lines) | ✅ verified |
| 18 | `api/deps.py` — lifted shared task/activity helpers (`_legacy_status_from_v1`, `_append_activity`, `_fetch_*`, `_serialize_task`, `_task_deps`, `_count`) so tasks+pm can share without importing dashboard | ✅ verified |
| 19 | `api/routers/tasks.py` — task constants + 9 models + 3 validators + `/api/tasks/*`+`/done/*` (incl. `api_task_patch`). First half of the tasks/pm hard seam | ✅ verified |
| 20 | `api/routers/pm.py` — `/api/pm/*` (43 routes) — imports `TASK_STATUS_V1`/`ALLOWED_*`/`TaskPatchRequest`/`api_task_patch` from `api.routers.tasks` (one-directional, no cycle). Resolves the seam that failed when pulled from dashboard | ✅ verified |
| 21 | `api/routers/genesis.py` — `/api/vault/*`+`/api/integrations/*`+Google OAuth (9 models + `_genesis_status`/`_integration_view` + 23 routes). Free-var set derived by **isolated pyflakes** (grep missed `registry`/`mcpsec`/MCP-probe globals/awakening symbols/`Request`; a grep-header attempt was caught by the gates and redone) | ✅ verified |
| 22 | `api/routers/abilities.py` — `/api/abilities/*`+`/api/hermes/skills`+`/api/proposals/*` (CoachRequest + 8 routes) | ✅ verified |
| 23 | `api/routers/evolution.py` — `/api/evolution`+`/api/awakening`+`/api/evolution/reflect` (4 evo helpers + 3 routes) | ✅ verified |
| 24 | `api/routers/chat.py` — Premium Chat #8 `/api/chat/*` (8 models + 19 routes incl. the ~565-line streaming turn handler; heavy deps import inline and move unchanged) | ✅ verified |

`api/dashboard.py`: **6,636 → 400 lines (−94%)** — now a thin app shell (setup +
middleware + workflows/feature-triggers/run + startup/shutdown lifecycle + SPA host +
router registration). Slices 1–9 held the route set at 329; the pre-#21 continuation
(10–24) re-baselined to **358 operations** (News V2 + others added since) and holds parity
there through every slice. Gate per slice: pyflakes (no undefined name) + import smoke +
openapi route-parity diff + TestClient smoke. Slices 15–24 used a scripted verbatim
line-range move (preserves line endings, `@app.`→`@router.`).

**Post-Phase-1 size-dimension grade (filesystem-walk, coupling pending graph refresh):**
overall **78.9 (C+)** — up from the D baseline; **API subsystem now 95.2 (A)** (only
`pm.py` 1,195 and `chat.py` 834 remain >800). Remaining overall drag is the later phases:
Conductor & Chat 71.5 (`conductor.py` 3,121), Other 70.0 (`development_store.py` 2,226),
Frontend 74.6.

**Free-var method (adopted slice 21+):** derive a moved block's true module-level
dependencies by wrapping it in a minimal `APIRouter` scaffold and running pyflakes on it in
isolation — it enumerates every undefined name (ignoring strings/comments/inline-imports),
which grep does not. This is the reliable way to build a correct import header; the 4 gates
remain the proof.

> **Pre-#21 continuation (2026-07-24):** this decomposition is being finished as the
> refactor that unblocks **#21 Mission Control Infrastructure V2** (whose own audit names
> `dashboard.py` and `conductor.py` as the top collision risks) and lifts the Performance
> Doctor grade toward A. Landing per-slice on `main` with the 4 gates. See
> `D:\ClaudeData\plans\now-for-the-upcomming-cheerful-globe.md` for the full phased plan.

**Cross-handler coupling pattern:** `api_office_v3_snapshot` calls the agents +
missions list handlers directly (`asyncio.gather`). When a caller and callee land in
different routers, import the callee handler from its router (office.py does this).
While the caller still sits in dashboard, re-import the callee there temporarily and
drop it once the caller moves. The pyflakes gate flags every such dangling reference.

**Remaining in `dashboard.py` (400 LOC, optional):** 6 small routes stay in the shell —
`/api/status`, `/api/projects`, `/api/lessons`, `/api/workflows`, `/api/run/readiness`,
`/api/run/{engine}` — plus app setup, the startup/shutdown `@app.on_event` handlers (which
cannot move to a router), and the SPA static host + catch-all (must remain last). These
could fold into an `api/routers/core.py` to reach ~250 LOC, but the size penalty is already
gone. **Phase-1 route decomposition is functionally complete.** Next levers for overall A
are Phase 2 (`conductor.py` tool extraction) and Phase 5 (frontend god-components).

## 5. Sequencing & guards

**Recommended order:** Slice 0 (`api/deps.py`) → Priority-1 slices in the listed order → Priority-2 `api.ts` split → Brain/Architecture component extraction → (reassess Chat/Developer, then conductor).

**Guards on every step:**
- Additive/mechanical only — **no logic edits** while moving code.
- **One group per commit**, each independently revertible.
- Gate each commit: openapi route-parity (backend) or `tsc` + `vite build` (frontend).
- **Nothing lands on `main` without owner approval** — the repo auto-committer owns that line; coordinate to avoid clobbering.
- Keep `docs/ARCHITECTURE.md` and this file updated as groups move.

**Definition of done:** `api/dashboard.py` < 500 lines; every `/api/*` group lives in its own router; frontend `api.ts` is a thin barrel; Brain/Architecture pages are shell + extracted components; full openapi route set and MC UI unchanged.

---

## Appendix — why this is safe

The two risks in decomposing a monolith are (1) dropping/altering a route and (2) breaking shared state. Both are neutralized: route parity is checked by openapi diff on every slice, and shared state is centralized once in `api/deps.py` (Slice 0) so no route silently loses a helper. The already-extracted `developer.py` / `brain_v2.py` prove the pattern compiles and runs in this codebase.

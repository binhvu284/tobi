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

### Verification per slice (automatic, cheap)

- **Route parity:** snapshot `GET /openapi.json` path+method set **before** the slice, diff **after** → an identical set proves no route was dropped, renamed, or shadowed. This is the primary guardrail for a 266-route move.
- Backend import smoke: `python -c "import api.dashboard"` succeeds (catches broken imports after the move).
- Live spot-check: `curl` 1–2 representative endpoints in the moved group return their pre-move status/shape.

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

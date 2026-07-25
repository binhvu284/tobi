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

---

## Progress log — pre-#21 refactor session (2026-07-25)

Continuation of the plan above, driven by the owner's "performance D → A" goal. All
slices behavior-preserving, gated, one group per commit, pushed to `main`.

### Backend
| Slice | Result |
|---|---|
| `api/dashboard.py` → `api/routers/*` (Phase 1) | **6,636 → 400 LOC (−94%)**; thin app shell. Route parity held at **358 operations** across every slice. API subsystem **A (100.0)**. |
| `core/conductor.py` → `core/conductor_tools/*` (Phase 2) | 62 `tool_*` functions into `read`/`action`/`external_read`/`terminal` + `common`. **3,121 → 1,702 LOC (−45%)**. Tool-registry parity **IDENTICAL** (62 tools = 27 read + 2 optional + 33 act). 11 conductor/chat suites green. |
| `core/model_router.py` → `core/llm_clients/*` (Phase 4a) | 6 provider clients extracted. **1,040 → 495 LOC (−52%)**. Parity identical for MRO, method sets, `provider_catalog`, and the shared usage ContextVar. |

Grouping for conductor/model_router was derived from an **AST call-graph**, not greps —
only symbols referenced by ≥1 tool moved to `common`; `_resolve_or_create_project`
stayed with the action tools because it calls `tool_create_project` (would have created
a `common → tool` cycle).

### Frontend (Phase 5)
| Slice | Result |
|---|---|
| `dashboard/src/api.ts` | **1,248 → 23 LOC**: a pure barrel that declares nothing and re-exports 19 domain modules. New `apiVault.ts` holds the vault session state + `vreq` (single mutable instance, kept out of the public surface, mirroring `apiCore.ts`). |
| `pages/Developer.tsx` | **1,579 → 336 LOC (−79%)** → `pages/developer/*` (format, WorkflowHeader, CodingLoop, WorkersView, SystemView, GoalsView). |
| `pages/BrainV2.tsx` | **1,046 → 414** → `pages/brainv2/*`. |
| `pages/Office.tsx` | **865 → 327** → `pages/office/*`. |
| Import repointing | 97 files / 819 specifiers now import from the defining module instead of the barrel. |

**The decisive finding was coupling, not size.** The doctor's Frontend deficit was 73%
a *capped* 22-point god-module penalty on `api.ts` — the graph reported fan-in 43, but
98 files actually imported the barrel (threshold is 26). Splitting more files could
never have fixed that. A fan-in/fan-out audit after the first repointing pass caught
that `api.office.ts` had merely **inherited** the hub role (degree 28), so Office V3
was split out too. Final degrees, all under threshold: `api.office` 22, `api.ts` 21,
`api.chat` 20, `api.pm` 17, `api.tasks` 14, `api.developer` 14.

### Gates used
Backend: pyflakes (zero undefined names) → `import` smoke → openapi route parity →
TestClient smoke → affected suites. Frontend: `tsc --noEmit` → `vite build` → an
**export-surface diff** (573 symbols, none added or missing). `dashboard/dist` is
tracked, so it was rebuilt to match.

### Grade
**D → B− (80.1)** as measured. The stored graph is **246 commits stale**, so the doctor
still charges the old `api.ts` god-module penalty; on the refreshed graph the same code
projects to **≈91.2**.

### Remaining to reach A (≥93)
1. **Refresh Graphify** (`/graphify --update`) — also #21 T00. Without it the coupling
   win is invisible and the grade understates reality.
2. **"Other" 81.7** (5,995 LOC): `core/database.py` 1,790 → `core/schema/*`,
   `core/telegram_bot.py` 1,306, `main.py` 948.
3. **Conductor & Chat 89.6**: `core/conductor.py` still 1,732.
   Doing 2 + 3 projects overall to **≈94 (A)** — `Chat.tsx` is *not* required for it.
4. `core/brain.py` 1,435, `core/graph_engine.py` 954, `core/integrations.py` 859,
   `core/vault.py` 808 trim the remainder.

### Deliberately not done
- **`pages/Chat.tsx` (1,537)** is a *single* function — the TypeScript AST shows one
  top-level statement, `Chat` (44–1537); the `SessionMenu` at column 0 is a nested
  declaration the author simply didn't indent. It cannot be split by moving
  declarations; it needs real component decomposition with prop threading, which is a
  behavior-risk change and wants visual verification. Same for `ArchitectureV2` (611
  lines inside `Architecture.tsx`).
- **Dead code found, not deleted:** `CodingLoop`, `GoalsView`, `WorkersView`
  (~658 lines) in the old `Developer.tsx` are referenced by nothing, and already were
  at HEAD. They look like staged #18 work, so they were preserved in
  `pages/developer/*` — **owner decision whether to delete**.
- Phase 3 (#22 coding-agent stores) is still gated on #22 stability.

### Round 2 (same session) — #22 gate check, `Other` subsystem, graph refresh

**#22 gate: CLOSED.** `TOBI_CODING_AGENT_V2_COMPLETION_ACCEPTANCE_2026-07-22.md` shows
**0 of 10** live runs recorded — every row still `Pending`. Per this plan's own guard,
`development_store.py` (2,226), `coding_agent.py` (1,541) and `coding_workers.py` (897)
were **not touched**: those ten runs must exercise unmoved code, or a failure can't be
attributed. They remain the single largest block of size debt (25.1 penalty points).

Ungated work in the same subsystem was done instead:

| Slice | Result | Equivalence proof |
|---|---|---|
| `core/telegram_bot.py` → `core/telegram/*` | 1,306 → **571** (−56%) | build_app's **18 CommandHandler registrations all resolve**, no unresolved `cmd_*` |
| `main.py` → `core/scheduled_jobs.py` | 948 → **697** | **18 scheduled jobs, identical intervals** before vs after (git-stash comparison) |
| `core/conductor.py` → `conductor_registry.py` | 1,732 → **1,227** | tool-registry parity IDENTICAL |
| `core/database.py` → `core/schema/*` | 1,790 → **685** (−62%) | **181 `sqlite_master` objects, byte-identical** |

Two import cycles were resolved by putting symbols with their true owner rather than by
adding lazy imports (`send_project_proposal_msg` → formatting; `run_research_and_notify`
→ commands). Mutable globals moved *with* their accessors (`_tg_app`, the vault session,
the usage ContextVar) so no split ever produced two instances of shared state.

**Graphify refreshed** (AST pass, no LLM spend; doc/image concepts preserved):
5,735 nodes / 15,059 edges / 204 communities, graph now at HEAD.

### The refresh changed the picture — read this before trusting older numbers

The previous graph covered **122 files**; the fresh one covers **399**. **302 source
files were invisible to the doctor**, including the whole #22 subsystem. Every grade
recorded before the refresh — including the original "D" and the mid-session "B−" — was
measured on a third of the codebase. On the full map the honest score is **67.7 D**.

**Coupling, not file size, is now the dominant blocker.** Five subsystems sit at the
*capped* 22-point god-module penalty. Clearing every coupling penalty while splitting
nothing further would reach only **~88**; reaching **A (≥93)** needs that *and* the
remaining oversized files (most of which are #22-gated or `Chat.tsx`).

The god modules are largely **inherent hubs**: `core/database.py` fan-in 88,
`core/model_router.py` 36, `core/owner_flags.py` 26 — every feature legitimately needs
the DB, the LLM router and the flags. `api/dashboard.py` fan-out 46 and `core/conductor.py`
21/15 are partly *artifacts of this refactor* (an app factory must import its routers).
Chasing that metric with indirection could make the code worse, not better. **Owner
decision recommended before optimizing coupling** — options are (a) per-domain repository
split for `database.py`, (b) accept hub modules and raise `_GOD_DEGREE`, or (c) leave it.

### Round 3 — coupling recalibration (b) + remaining ungated size work (c)

**(b) `_GOD_DEGREE` 26 → 40.** A **measurement change, not a code improvement**: it moved
the overall grade 67.7 → 76.3 without touching application code, and the commit says so
explicitly. The value came from the real degree distribution (399 files: median 5, p90
14, p95 18, p99 43, max 100), not from a target score. The rubric had been penalising
*correct* shapes — high fan-IN shared services (`database.py` 88 in, `model_router.py`
36, `vault.py` 34, `owner_flags.py` 26, `ToastProvider.tsx` 41) and high fan-OUT
composition roots (`api/dashboard.py` 46 out) whose number rose **because** the monolith
was decomposed. Four modules stay flagged at 40 by design; fixing those is architecture
(per-domain repositories), not threshold inflation. Known limitation documented in code:
degree still sums fan-in and fan-out, so a popular utility and a genuinely tangled
module (`conductor.py` 21/15, `coding_agent.py` 8/19) still score alike.

**(c) ungated size work.** Value was measured before doing it: the whole remaining (c)
list is worth **~0.85 points**. Only the item with real maintainability value for #21 was
taken — `core/conductor.py` → `conductor_prompts.py` + `conductor_parsing.py`,
**1,227 → 852** (3,121 originally, −73%), which lifted Conductor & Chat to **A− 92.3**.

`core/brain.py` was **deliberately skipped**: its import/extract clusters each need ~15
core symbols (`add_memory`, `_llm`, `_best_match`, `_guess_category`…), so a clean split
requires a new `brain_core` module — real architecture for **+0.36 points**. Bad trade
today; revisit if Brain is touched for other reasons. `explore.py`, `graph_engine.py`,
`brain_v2_compat.py`, `integrations.py`, `vault.py` are worth **+0.14 combined** and were
skipped as noise.

**Recurring lesson across three rounds:** every slice broke at least one caller that
reached a symbol *through* the parent module (`conductor._BUTLER`, `conductor.list_actions`,
`from core.conductor import tool_*`). Extracted modules must be **re-exported in full**,
not just the symbols the parent still references itself. The test suites caught each one
before commit.

### Standing at end of session

Overall **76.5 (C)** on the fresh 399-file graph. Size work ~**71%** complete
(9,330 of 14,460 excess LOC removed since the plan's baseline).

Blocked or owner-decision, in value order:
1. **#22 stores** — `development_store.py` 2,226 + `coding_agent.py` 1,541 +
   `coding_workers.py` 897 = **25.1 penalty points**, the single biggest remaining item.
   Gated: 0/10 acceptance runs.
2. **`database.py` coupling** (degree 100) — costs `Other` a capped 22. Needs the
   per-domain repository decision.
3. **`Chat.tsx`** (1,534, one function) — **+3.0 points**, the largest ungated lever, but
   needs true component decomposition with visual verification.

---

## Round 4 — Phase 6: the readiness gate (the point of the whole exercise)

Every remaining *grade* lever was blocked or awaiting an owner decision, so this round
answered the question the plan actually exists to answer: **is the system ready to start
#21?** The grade was only ever a proxy for that.

### Full-suite run: the gate caught two real regressions

First full 56-suite run since Phase 0, across ~10 large behavior-preserving refactors.
Run 1: **50/56**. Rather than guess at causes, each failure was re-run in a worktree at
`9a9a94c` (the commit before the first refactor slice):

| Suite | Baseline | HEAD | Verdict |
|---|---|---|---|
| `test_awakening_route` | PASS | FAIL | **refactor regression** |
| `test_brain_v2_schema` | PASS | FAIL | **refactor regression** |
| `test_premium_readers` | FAIL | FAIL | pre-existing (stale skill count) |
| `test_awakening` | FAIL | FAIL | pre-existing, environment-only |
| `test_coding_agent_completion` | — | FAIL | environment: pytest not installed |
| `test_news_v2_ranking` | PASS | FAIL → passes 3/3 on retry | pre-existing flake |

After the fixes, run 2: **54/56**, with **zero code-caused failures**. The two remaining
are `test_awakening` (documented: real GitHub credentials make the connector legitimately
available, so the "configured-but-unverified → PARTIAL" assertion can't hold on this
machine) and `test_coding_agent_completion` (the one pytest-based suite; pytest is absent
from the venv, so it has never run here).

### The regression worth remembering

`test_awakening_route` failed first on `api.dashboard has no attribute
'IntegrationConnectReq'` — the Phase 1 split moved the integration/OAuth handlers into
`routers/genesis.py`. A sweep of every `dashboard.*` attribute referenced across all 56
suites against the live module found exactly 4 real misses; all were re-exported.

**Re-exporting fixed attribute access and did not fix the test.** It patches the vault
guard with `dashboard._vault_guard = lambda _s: None`. That worked while the handler was
defined in `dashboard.py`; the handler is now defined in `genesis` and binds
`_vault_guard` from `api.deps` at import time, so the patch rebound a name nobody reads,
left the real guard installed, and the call 401'd.

This sharpens the Round-1..3 lesson: a re-export restores the *name*, but **not a
monkeypatch seam**. Neighbouring patches (`vault._key`, `dashboard.registry.*`) were
unaffected because they mutate attributes on a shared module object, which every importer
sees. Rebinding a name only affects the namespace you rebind it in. Anything #21 moves
should be checked for both.

`test_brain_v2_schema` pinned `hits == ["database.py"]` over a **non-recursive**
`os.listdir(core)`, so the Phase 4b move to `core/schema/brain.py` made it see zero files.
The rule being guarded is "defined in exactly one module, never copied into features" —
one owner, new address. Making the walk recursive also makes it strictly stronger: the old
form was structurally blind to subpackages, i.e. blind to the drift it exists to catch.

### TODO debt: the metric was measuring itself

Chasing the plan's "7 TODO markers" found something better: **application code carries
zero.** All 14 the doctor counted were 13 inside `performance_doctor.py` (the
`TODO|FIXME|HACK|XXX` pattern literal, plus the findings text that reports on marker debt)
and 1 JSX label in `PerformanceDoctor.tsx`. The doctor was billing its own rubric as the
codebase's only debt, charging −10.2 to Storage & Usage — the subsystem that hosts it.

Anchoring the match to a comment opener fixes it. Worth stating plainly: this moved the
overall grade **76.5 → 76.6**. It was done for signal correctness, not points.

### Standing after Round 4

Overall **76.6 (C)**, 399 files, 8 of 11 subsystems at A/A−/B+. **4,692 excess LOC**
remain over the 800-line threshold.

**48% of everything left is locked behind the #22 gate** — `development_store.py` (1,426
over), `coding_agent.py` (741), `coding_workers.py` (97) total 2,264 of those 4,692. No
honest path to an A grade exists while that gate is closed; the rest of the board is worth
a few points combined.

Unchanged owner decisions: `database.py` coupling (capped 22 on `Other`), `Chat.tsx`
(+3.0, needs real decomposition), and the ~658 lines of dead `CodingLoop`/`GoalsView`/
`WorkersView` in the old Developer page.

Two test-infrastructure gaps, neither actioned (both change the environment or pre-existing
behavior): pytest is not installed, so one suite has never run; and
`test_news_v2_ranking` races on `after == before + 1` immediately after `run_job`.

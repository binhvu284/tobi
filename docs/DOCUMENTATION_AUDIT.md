# Documentation Audit

## Refresh - 2026-08-28 (#34 live-proof follow-up)

Protocol: [`UPDATE_DOCS_TM01.md`](UPDATE_DOCS_TM01.md). Agent: Codex. The approved 156-call rerun was
verified against source `d1a3448` and the schema-v2 final artifact. Frozen cases, holdouts, formulas,
thresholds, and model IDs were unchanged.

### Active documents updated

- Current state, Runtime, Mission Control, Development, and Roadmap now report the live result rather
  than the superseded `0/156` offline blocker.
- Queue, delivery log, and the #34 implementation addendum now keep #34 In progress only for owner
  dashboard acceptance.
- The owner command now documents its revision-bound D-drive database and default artifact path.

### Archived or removed

None.

### Verification

- Live artifact: 72 cases, 14/14 holdouts, 156/156 model responses, ECR `100`, scoped LDR `8.8021`,
  raw pass `32.0513%`, recovery `67.9487%`, no provider failures, no blocker, direct spend `$0`.
- Owner UI: desktop/mobile Playwright passed with no overflow, console error, or failed request.
- Project gate and final Git/push state are recorded in the delivery commit and owner report.
- No rollout activation, connector, deployment, Supabase, or Vercel action was performed.

## Refresh - 2026-08-28 (TM01, full checkout)

Protocol: [`UPDATE_DOCS_TM01.md`](UPDATE_DOCS_TM01.md). Agent: Codex. Implementation revision
inspected: `685a1a8` on `main`, matching `origin/main` before this docs-only refresh. The
checked-in Graphify output predates the verified revision, so it was used only for navigation and all
#34 claims were checked against current source, tests, artifact, gate definition, and Git history.

### Active documents updated

- Root `README.md` and `docs/README.md`: refreshed the source-of-truth banner and index dates.
- `02_CURRENT_STATE.md`, `ARCHITECTURE.md`, `MISSION_CONTROL.md`, and `RUNTIME_V2.md`:
  replaced the T07 synthetic overclaim with the canonical T08 execution boundary, evidence, and
  live-model blocker.
- `DEVELOPMENT.md`: documented the 29-suite gate, offline blocker, live 156-call command and
  approval boundary, dashboard build, and owner-flow command.
- `03_ROADMAP.md`: updated #34 sequencing and remaining release proof.
- `feature-idea-queue/PREMIUM_CHAT_V2_SPEC.md`: removed one dead link to the historical,
  no-longer-present `ThinkingOrb.tsx` source path while preserving the delivery note.
- `feature-idea-queue/QUEUE.md`, `QUEUE_DELIVERY_LOG.md`, and
  `TOBIVAL_OPERATIONAL_INTELLIGENCE_PLAN.md`: kept #34 In progress, corrected its delivery evidence,
  and appended the T08 implementation addendum without rewriting the accepted original plan.
- `DOCUMENTATION_AUDIT.md`: recorded this refresh, its boundaries, and its checks.

### Archived or removed

None. No active document was superseded, duplicated, or obsolete enough to archive. Historical T00
through T07 evidence remains useful provenance and is explicitly corrected by the T08 addendum.

### Queue and current-work finding

#34 remains In progress. T08 is committed and pushed, all 72 cases and 14 holdouts now use canonical
Runtime evidence, and the shared gate is green. The current artifact has `0` live model responses
and `156` provider failures, so release is correctly blocked by
`model-quality-proof-missing`. A 156-call live rerun and owner dashboard acceptance remain.

### Unresolved code/docs gaps

1. Live strong/weak model quality and the original model-independence outcome are not yet proven.
2. Production routing uses only narrow safe workflows with no required fields; broad typed workflow
   execution and grounded outcomes remain outside normal Chat/Agent paths.
3. The port-8080 dashboard still assumes a trusted single-owner boundary.
4. Graphify is stale and should not be used for exact current graph claims until refreshed.

### Verification

- `git diff --check` over the TM01 files: pass; only existing Windows line-ending warnings were printed.
- Active Markdown relative-link scan: pass, `MARKDOWN_LINKS_OK (70 active files)`.
- Added-line secret-signature scan: pass, `DOC_SECRET_SIGNATURE_SCAN_OK`.
- `& "D:\[PERSONAL PROJECT FILES]\TOBI\.python\venv\Scripts\python.exe" scripts/gate.py`:
  pass, `GATE GREEN (29 of 29 checks pass)`.
- `npm.cmd --prefix dashboard run build`: pass; TypeScript and Vite completed. Vite reported only
  its existing large-chunk advisory.
- No runtime activation, live model call, connector, deployment, Supabase, or Vercel action was
  performed by TM01.
- Existing unrelated changes in `AGENTS.md`, `CLAUDE.md`, `docs/OUTPUT_STYLE_ADHD.md`,
  `artifacts/`, and `%SystemDrive%/` were preserved.

## Refresh - 2026-08-25 (TM01, full checkout)

Protocol: [`UPDATE_DOCS_TM01.md`](UPDATE_DOCS_TM01.md). Agent: Codex. Revision inspected:
`6617575` on `main`; `origin/main` is `31d95ec`. The checkout was already dirty with the active
#21/T15 package and unrelated runtime/UI changes. Those changes were preserved and are clearly
labelled local-only below.

### Active documents updated

- `README.md`: refreshed the index, added architecture/security/acceptance/queue sources, and
  marked the local Morpheus mockup as non-shipped.
- `02_CURRENT_STATE.md`: replaced the partial-refresh banner with a full committed-vs-local
  snapshot and updated freshness language.
- `ARCHITECTURE.md`, `MISSION_CONTROL.md`, and `RUNTIME_V2.md`: updated dates and described the
  committed passive-adapter boundary plus the uncommitted Infrastructure self-check package.
- `DEVELOPMENT.md`: recorded the current revision split, stale Graphify index, and active gate
  command.
- `03_ROADMAP.md`: clarified that #22 is Codex-only qualification and full Agent tier remains
  open.
- `feature-idea-queue/QUEUE.md` and `QUEUE_DELIVERY_LOG.md`: corrected #33 from shipped to local
  work in progress because its implementation is not in committed source yet.
- `archive/README.md`: added the historical handover category.

### Archived

- `HANDOVER_DEVELOPER_MODULE_2026-07-28.md` -> `archive/handovers/`: old branch/commit handover
  is historical and no longer a safe current Developer source.
- `REFACTORING_PLAN.md` -> `archive/roadmaps/`: proposed structural plan is historical; the
  active docs and current package file now describe the live architecture and work boundary.

### Queue and current-work finding

#21 remains complete in committed source. #33 is not closed: the code, tests, diagrams, and spec
are in the current worktree under the active T15 package, but `git log` has no #33 delivery commit.
This correction prevents a new agent from assuming the Health button is already released.

### Unresolved code/docs gaps

1. The active #21/T15 package still needs its own gate, commit, and owner acceptance before #33
   can return to Done.
2. The dashboard and much of the MC API remain a trusted single-owner surface rather than a
   generally authenticated public service.
3. Runtime V2 rollout is still off by default; passive adapters do not replace legacy execution.
4. The Graphify executable is unavailable in this environment and the checked-in index is stale;
   direct source and test verification was used instead.

### Checks

- `git diff --check`: pass. Git printed only existing line-ending normalization warnings.
- Markdown relative-link scan: pass (`MARKDOWN_LINKS_OK`).
- `python scripts/gate.py`: the bare command was unavailable in this PowerShell session; the
  required D-drive interpreter command passed with `GATE GREEN (24 of 24 checks pass)`.
- No code, runtime data, external service, Supabase, or Vercel action was performed by TM01.

## Refresh - 2026-08-25 (TM01, partial)

> Superseded by the full 2026-08-25 TM01 refresh above. Retained only as provenance for the
> earlier narrowed model-routing pass; its scope and unresolved-gap list are not current status.

Protocol: `UPDATE_DOCS_TM01.md`. Agent: Claude Code (Opus 5). Revision inspected:
`6617575` on `main`, 9 commits ahead of `origin/main`, worktree dirty with 221 files
before the refresh.

**Scope was deliberately narrowed to the model-routing area.** A large concurrent change
set from another agent lane was in flight during this refresh -- `core/runtime/self_check.py`,
`core/proc.py`, `core/runtime/transport_failure.py`, four architecture diagram files,
`QUEUE.md`, `QUEUE_DELIVERY_LOG.md`, and `INFRASTRUCTURE_SELF_CHECK_SPEC.md` were all
uncommitted. Those files were left untouched, and the rows describing that work were not
re-verified. Nothing was committed or pushed.

### Active documents updated

- `02_CURRENT_STATE.md` -- Model routing row now lists DeepSeek and records that its key is
  absent in this checkout. Added a TM01 banner line stating exactly which area carries a
  2026-08-25 evidence date and which rows still carry 2026-08-20.
- `ARCHITECTURE.md` -- Provider catalog list now includes DeepSeek. Added the DeepSeek
  endpoint/model/id-resolution paragraph, and a paragraph describing catalog-based escalation
  (`get_escalation_llm`), which was previously undocumented in every current doc despite two
  commits and a dedicated regression test covering it.
- `.env.example` -- Added the `DEEPSEEK_API_KEY`, `GEMINI_API_KEY`, and `XAI_API_KEY` names.
  `DEVELOPMENT.md` names this file as the authority for environment variable names, and all
  three providers existed in the router catalog without an entry here.
- `REFACTORING_PLAN.md` -- Added a status stamp only; the plan body was not revised. Its header
  still read "Proposed (not started)" while two of its three targets had shipped:
  `api/dashboard.py` is 412 lines against a plan figure of 6,636 and a goal of under ~500, and
  `core/conductor.py` is 478 against 3,121. `core/development_store.py` is untouched and has
  grown from 1,748 to 2,658 lines. Line counts measured at `6617575`.
- `README.md` -- Indexed `BRAIN_V2_OPERATIONS.md` as an active operations document, and added a
  level-4 section indexing `REFACTORING_PLAN.md` and `HANDOVER_DEVELOPER_MODULE_2026-07-28.md`.
  All three existed in `docs/` without appearing in the index.

### Checks

- `git diff --check` -- pass (exit 0; only repo-wide CRLF advisories, present on files this
  refresh did not touch).
- `python scripts/gate.py` -- pass, 24/24 `[PASS]`, exit 0.

### Verification performed

- `core/model_router.PROVIDERS` read directly; provider/model resolution exercised for bare
  ids, prefixed ids, and OpenRouter `deepseek/...` ids.
- Live request through `build_client('deepseek:deepseek-v4-flash')` returned HTTP 401 from
  `api.deepseek.com`, proving endpoint and model id, not merely code presence.
- Tests run green: `test_model_routing_usage.py` (6), `test_escalation_without_config.py` (13),
  `test_model_unreachable_message.py`, `test_chat_self_check.py`, `test_codex_auth_freshness.py` (4),
  `test_infrastructure_self_check.py`, `test_vault_payload.py` (17), `test_storage_usage.py` (36),
  `test_premium_readers.py` (72). Dashboard `tsc --noEmit` clean; `vite build` clean.

### Archived

Nothing.

### Queue

Unchanged. The DeepSeek provider was a direct owner request, not a queued item, and
`QUEUE.md` was already being edited in the concurrent lane.

### Unresolved gaps

1. `MISSION_CONTROL.md` still carries a 2026-07-16 evidence date and was not re-verified.
2. Queue item #33 (infrastructure self-check) is marked Done in `QUEUE.md` and its test passes,
   but no current-state or architecture document describes it yet. It belongs to the concurrent
   lane and was left to that lane to document.
3. `get_escalation_llm` walks the catalog without checking key presence, so an enabled provider
   with no key can consume one escalation attempt. Documented as current behavior in
   `ARCHITECTURE.md`; needs an owner decision on whether to filter, not a docs fix.
4. `tests/` mixes pytest files with script-style files that call `raise SystemExit` at module
   level; the latter abort a shared pytest invocation. Not a docs defect, but it makes any
   "run the suite" instruction in `DEVELOPMENT.md` misleading.
5. `tests/test_premium_readers.py` permanently reassigns `model_router.available_models` with no
   cleanup, so it poisons `test_model_routing_usage.py` when both run in one pytest process.
6. `core/development_store.py` is now the single largest backend module at 2,658 lines and is the
   only remaining target in `REFACTORING_PLAN.md`. Needs an owner decision, not a docs fix.
7. `MISSION_CONTROL.md`, `RUNTIME_V2.md`, `DEVELOPMENT.md`, `03_ROADMAP.md`, and `01_VISION.md`
   were read for drift against the model-routing change but were not line-by-line re-verified
   against the whole codebase. They keep their existing evidence dates.


## Refresh - 2026-07-14

The maintained truth documents were rechecked from the previous broad docs baseline (`7802175`)
through current `main` commit `5245a25`. Graphify was used as the first navigation map, then treated
as stale because its stored commit `c39c34a` is 85 commits behind; every material claim below was
verified against current source, tests, queue state, or Git history.

Delivered changes represented in this refresh:

- Awakening External Read now requires adapter readiness and fresh successful-test evidence, with a
  24-hour default TTL; Google credentials remain partial until OAuth and a verified read test.
- Vault credential changes/imports clear stale test proof, and integration endpoints distinguish setup
  success from verified read access.
- Brain sweeps now use fair per-chat cursors, owner-token DB leases, persisted deferred failures,
  bounded exponential retry, malformed-output recovery, and raw-payload cleanup after resolution.
- Conductor can list, read, and search Project v2 resources; safe known read tools may recover from an
  overly narrow route without weakening mode or action-risk policy.
- The Resources UI now uses one upload/link modal, link-card menus, rename/copy/open actions, and
  explicit deletion confirmation.
- Chat Runtime no longer materializes an explicit empty allowlist for a direct-route prediction.
- Queue dependency truth now includes `#18 -> #20 -> #21`, with an explicit no-parallel warning.

Updated current documents:

- `README.md`, `CLAUDE.md`, and `docs/README.md` for the current capability map and snapshot date.
- `02_CURRENT_STATE.md` for verified Awakening/resource/runtime behavior, current metrics, tests, and queue.
- `ARCHITECTURE.md` for data flows, connector evidence, Brain sweep state, route scoping, schema count,
  API size, Graphify staleness, and migration-ledger scope.
- `MISSION_CONTROL.md` for resource UX/tools, Awakening evidence, Brain recovery, and route behavior.
- `DEVELOPMENT.md` for the 15-script test inventory, interpreter constraints, and new invariants.
- `03_ROADMAP.md` for completed #17 protection and the serialized #18/#20/#21 delivery sequence.

Focused local verification during the refresh:

- `tests/test_awakening.py`: `73/73` passed.
- `tests/test_resource_access.py`: `14/14` passed.
- `tests/test_chat_runtime.py`: `8/8` passed after running from the repository root expected by the test.
- `tests/test_awakening_route.py`: not rerun because the available Python 3.12 bundle lacks FastAPI and
  the repository venv points to a removed Python 3.11 Windows Store interpreter; the suite and route
  implementation were inspected instead.

Scope remained documentation-only. No Python/TypeScript behavior, database, runtime data, persona,
skills, external integration, Supabase, Vercel, feature-plan body, archive file, or generated asset was changed.

## Refresh - 2026-07-13

The maintained truth documents were rechecked through commit `2f4ad68` plus the current reviewed
#17 and Agent-checkpoint working-tree follow-ups. This refresh changed documentation only and
preserved all original feature plans and archived specifications.

Updated:

- `README.md` and `docs/README.md`: current subsystem/test map and snapshot date.
- `02_CURRENT_STATE.md`: Chat Runtime v2, Chat/Agent policy, Deep Research, Agent runs/recovery,
  evidence-gated Awakening, Performance Doctor, Brain reliability, current API size, and test scope.
- `ARCHITECTURE.md`: runtime/mode/tool boundaries, Agent persistence, Deep Research/network guard,
  Awakening, Performance Doctor, frontend API-domain extraction, new table families, and security controls.
- `MISSION_CONTROL.md`: current Chat/Agent UX, durable expandable action checkpoints, runtime events,
  artifacts/recovery APIs, Awakening/Performance surfaces, and current truth gaps.
- `DEVELOPMENT.md`: expanded focused test matrix, Python ABI warning, Chat reload acceptance, and
  runtime security invariants.
- `03_ROADMAP.md`: marks #16/#17 as delivered and sequences runtime stabilization before queue #18.

Still intentionally unchanged: feature-plan bodies, archive contents, runtime persona/skills,
ignored owner data, external services, and the in-app Architecture TypeScript page.

### Office V3 delivery addendum

Queue #15 is now delivered at v1. Current-state, architecture, Mission Control, Development, and
Roadmap docs now include the flagged Office command center, additive local artifact/activity state,
Conductor-confirmed mutation boundary, sensitive pending-payload isolation, existing mission SSE,
legacy fallback, and focused verification. The original plan body remains preserved with a delivery
record appended; owner visual acceptance is still open because automated browser setup failed on the
bracketed Windows workspace path.

> Audit completed 2026-07-11 against the current D-drive repository. Scope was documentation only. No Python, TypeScript, database, runtime persona, skill, generated runtime data, or external service was changed.

## Audit Method

The audit compared:

- every active repository Markdown document;
- the preserved feature queue and its status rows;
- root setup/roadmap guides;
- current routes, API decorators, table creation, runtime commands, scheduler jobs, provider catalog, Conductor tools, integrations, and recent commit history;
- both local Graphify output locations, with their generation dates treated as stale metadata rather than current truth.

Ignored runtime/user data under `.tobi/` and `.hermes/` was inventoried but not read as canonical documentation or modified.

During the audit, concurrent commits delivered Premium Ability (#14) and cross-session conversation recall. Those code changes were not produced, edited, or reverted by this documentation task. The final maintained docs were refreshed through commit `389c151` so both delivered systems are represented.

## Active Documents Updated

| File | Reason |
|---|---|
| `README.md` | Repository had no current root entrypoint |
| `CLAUDE.md` | Old map omitted most current subsystems and quoted stale Graphify counts |
| `docs/README.md` | Old index described only three docs and treated legacy Hermes guides as active |
| `docs/01_VISION.md` | Old version overstated Hermes ownership and understated delivered memory/action systems |
| `docs/02_CURRENT_STATE.md` | Last snapshot predated Project v2, Theme v2.1, workspace tabs, Google reads, and TOBI CLI |
| `docs/03_ROADMAP.md` | Claimed TOBI CLI was unbuilt and relied on an unreliable Jarvis percentage |
| `docs/feature-idea-queue/QUEUE.md` | Introduction said every item was waiting to be built even though most rows are delivered |

## Current Documents Added

| File | Purpose |
|---|---|
| `docs/ARCHITECTURE.md` | Runtime, backend, frontend, data, integration, security, and flow reference |
| `docs/MISSION_CONTROL.md` | Current MC route/page map, workspace tabs, Chat, project UI, state, and API domains |
| `docs/DEVELOPMENT.md` | Local setup, commands, persistence, verification, and operational cautions |
| `docs/DOCUMENTATION_AUDIT.md` | This change record and classification |
| `docs/archive/README.md` | Historical-document boundary and archive map |

## Files Archived

The following material remains available but no longer claims current authority:

| Former path | Archive path | Why |
|---|---|---|
| `docs/MISSION_CONTROL_SPEC.md` | `docs/archive/specifications/MISSION_CONTROL_SPEC_2026-06.md` | June Ability/Office requirements called themselves the master source of truth and conflict with the current platform |
| `docs/PROJECT_MODULE_SPEC.md` | `docs/archive/specifications/PROJECT_MODULE_SPEC_2026-06.md` | Pre-build model differs materially from delivered Project v2 |
| `docs/HERMES_SPIKE_RUNBOOK.md` | `docs/archive/legacy-hermes/HERMES_SPIKE_RUNBOOK_2026-06.md` | Verify-first VPS spike is historical and not current operations |
| `docs/PHASE_1_ABILITY_COMPLETE.md` | `docs/archive/completion-notes/PHASE_1_ABILITY_COMPLETE.md` | Historical delivery note |
| `docs/PHASE_2_OFFICE_COMPLETE.md` | `docs/archive/completion-notes/PHASE_2_OFFICE_COMPLETE.md` | Historical delivery note |
| `docs/PHASE_3_UIUX_COMPLETE.md` | `docs/archive/completion-notes/PHASE_3_UIUX_COMPLETE.md` | Historical delivery note |
| `HERMES_QUICK_START.md` | `docs/archive/legacy-hermes/HERMES_QUICK_START.md` | Contains unverified/outdated Hermes commands, models, cost claims, and VPS assumptions |
| `HERMES_SETUP_GUIDE_VPS_TELEGRAM.md` | `docs/archive/legacy-hermes/HERMES_SETUP_GUIDE_VPS_TELEGRAM.md` | Legacy VPS setup, not current local development truth |
| `HERMES_COST_OPTIMIZATION.md` | `docs/archive/legacy-hermes/HERMES_COST_OPTIMIZATION.md` | Static prices/models/config examples are outdated |
| `HERMES_TROUBLESHOOTING_GUIDE.md` | `docs/archive/legacy-hermes/HERMES_TROUBLESHOOTING_GUIDE.md` | Troubleshooting assumes the old Hermes/VPS-only deployment |
| `WEEK_BY_WEEK_ROADMAP.md` | `docs/archive/roadmaps/WEEK_BY_WEEK_MMO_ROADMAP_2026.md` | Old MMO launch schedule is not the active TOBI roadmap |

Short redirect files remain at commonly referenced legacy paths where removing the path would make code comments or historical plans confusing.

## File Removed

`docs/EXPLORE_NEWS_SPEC.md` was removed because it was an older duplicate outside the queue. The preserved original feature record remains at `docs/feature-idea-queue/EXPLORE_NEWS_SPEC.md`, and delivery status remains in `QUEUE.md`.

## Intentionally Preserved

- The documentation refactor did not rewrite feature plans. The concurrent #14 delivery updated its own plan and queue row separately; the queue introduction was corrected here.
- `SOUL.md` remains unchanged because it is copied into Hermes and affects runtime behavior.
- `hermes_skills/` and `.claude/skills/` remain unchanged because they are agent instructions/runtime inputs.
- `.tobi/`, `.hermes/`, database files, project resources, logs, generated Graphify output, and built application assets remain unchanged.
- The in-app `/architecture` page remains unchanged because it is TypeScript code and this task is docs-only.

## Historical Findings From 2026-07-11

The following list is preserved as the original point-in-time audit. Items 2 and 4 were subsequently
superseded by the evidence-based Awakening and backend Chat/Agent mode work; line/route/test counts
also changed. Use the refresh sections above and current-state docs for present truth.

1. The in-app Architecture page contains stale Codespaces/MMO-focused descriptions and should later consume a maintained architecture data source.
2. Evolution's ability definitions and detector are stale; its completion percentage is not reliable.
3. Ability now shows repository Hermes skills read-only, but its curated DB registry and runtime Hermes state remain separate.
4. Chat modes are still mostly frontend state.
5. Mission Control lacks general authentication on most port-8080 endpoints.
6. `api/dashboard.py` has become a 5,700+ line, 238-route ownership hotspot.
7. The current automated test set is small relative to the product surface.
8. The existing `venv` records a stale WindowsApps base-interpreter path and must be recreated before its Python executable can be relied on.

These findings are reflected in current docs and roadmap, but no code fix was made.

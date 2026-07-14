# Documentation Audit

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

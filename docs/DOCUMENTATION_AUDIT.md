# Documentation Audit

> Audit completed 2026-07-11 against the current D-drive repository. Scope was documentation only. No Python, TypeScript, database, runtime persona, skill, generated runtime data, or external service was changed.

## Audit Method

The audit compared:

- every active repository Markdown document;
- the preserved feature queue and its status rows;
- root setup/roadmap guides;
- current routes, API decorators, table creation, runtime commands, scheduler jobs, provider catalog, Conductor tools, integrations, and recent commit history;
- both local Graphify output locations, with their generation dates treated as stale metadata rather than current truth.

Ignored runtime/user data under `.tobi/` and `.hermes/` was inventoried but not read as canonical documentation or modified.

During verification, uncommitted changes appeared in `core/chat_store.py`, `core/conductor.py`, and `core/database.py`. They add cross-session conversation recall and were not produced, edited, or reverted by this documentation task. The maintained docs use committed revision `c3b171b` as their explicit baseline so incomplete concurrent work is not presented as delivered behavior.

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

- Every feature plan under `docs/feature-idea-queue/` remains unchanged except the queue index introduction.
- `SOUL.md` remains unchanged because it is copied into Hermes and affects runtime behavior.
- `hermes_skills/` and `.claude/skills/` remain unchanged because they are agent instructions/runtime inputs.
- `.tobi/`, `.hermes/`, database files, project resources, logs, generated Graphify output, and built application assets remain unchanged.
- The in-app `/architecture` page remains unchanged because it is TypeScript code and this task is docs-only.

## Important Findings Not Implemented Here

1. The in-app Architecture page contains stale Codespaces/MMO-focused descriptions and should later consume a maintained architecture data source.
2. Evolution's ability definitions and detector are stale; its completion percentage is not reliable.
3. Ability does not represent live repository/Hermes skill files.
4. Chat modes are still mostly frontend state.
5. Mission Control lacks general authentication on most port-8080 endpoints.
6. `api/dashboard.py` has become a 5,700+ line, 238-route ownership hotspot.
7. The current automated test set is small relative to the product surface.

These findings are reflected in current docs and roadmap, but no code fix was made.

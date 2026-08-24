# TOBI Documentation

This directory separates current system truth from implementation plans and historical design records.

> TM01 full refresh: 2026-08-25. Committed source is `6617575`; the checkout also contains an
> active, uncommitted #21/T15 worktree package. Current docs distinguish shipped behavior from
> that local work.

## Read Order

1. [`01_VISION.md`](01_VISION.md) - product direction and non-negotiable principles.
2. [`02_CURRENT_STATE.md`](02_CURRENT_STATE.md) - verified implementation status and known mismatches.
3. [`ARCHITECTURE.md`](ARCHITECTURE.md) - runtime, components, data, integrations, and security boundaries.
4. [`MISSION_CONTROL.md`](MISSION_CONTROL.md) - Mission Control pages, workspace tabs, chat, frontend state, and API domains.
5. [`RUNTIME_V2.md`](RUNTIME_V2.md) - canonical runs, rollout, adapters, security, and verification.
6. [`DEVELOPMENT.md`](DEVELOPMENT.md) - setup, commands, tests, and safe operating workflow.
7. [`03_ROADMAP.md`](03_ROADMAP.md) - recommended sequencing for future work.

## Authority Levels

| Level | Source | How to use it |
|---|---|---|
| 1 | Executable code, schemas, tests | Final authority for current behavior |
| 2 | Current docs listed above | Maintained explanation of the code and product |
| 3 | [`feature-idea-queue/QUEUE.md`](feature-idea-queue/QUEUE.md) | Delivery ledger and links to feature plans |
| 4 | Files inside `feature-idea-queue/` | Original requirements and worker plans; preserve for history, but verify delivery notes and code |
| 5 | [`archive/`](archive/) | Superseded specifications, completion notes, and legacy setup material |

When two sources disagree, trust the higher level and update the lower level. A plan marked complete still describes intent; its queue row and the code describe what actually shipped.

## Current Documents

| Document | Maintained content |
|---|---|
| [`01_VISION.md`](01_VISION.md) | Jarvis mission, pillars, and product principles |
| [`02_CURRENT_STATE.md`](02_CURRENT_STATE.md) | Honest feature and risk inventory, refreshed 2026-08-25 |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | Backend/frontend/runtime map and primary data flows, refreshed 2026-08-25 |
| [`MISSION_CONTROL.md`](MISSION_CONTROL.md) | Current MC routes, ownership boundaries, runtime projections, and UI truth gaps |
| [`RUNTIME_V2.md`](RUNTIME_V2.md) | Mission Control Runtime V2 contracts, data, APIs, rollout, adapters, and gates |
| [`architecture/diagrams/`](architecture/diagrams/) | Source diagrams plus guide notes for overall TOBI, MC, and Runtime V2 |
| [`security/MC_V2_THREAT_MODEL.md`](security/MC_V2_THREAT_MODEL.md) | Runtime V2 threat model and security gates |
| [`acceptance/`](acceptance/) | Small local acceptance artifacts and their scope |
| [`feature-idea-queue/QUEUE.md`](feature-idea-queue/QUEUE.md) | Current delivery ledger and plan links |
| [`feature-idea-queue/QUEUE_DELIVERY_LOG.md`](feature-idea-queue/QUEUE_DELIVERY_LOG.md) | Delivery evidence and unresolved limitations |
| [`DEVELOPMENT.md`](DEVELOPMENT.md) | Development, verification, and operations |
| [`03_ROADMAP.md`](03_ROADMAP.md) | Near-term platform and queued work dependencies |
| [`DOCUMENTATION_AUDIT.md`](DOCUMENTATION_AUDIT.md) | What this refactor updated, archived, removed, or intentionally preserved |
| [`BRAIN_V2_OPERATIONS.md`](BRAIN_V2_OPERATIONS.md) | Brain Memory V2 (#20) operations, enablement flags, and rollback runbook |
| [`SIMPLE_RESULT_VN_TM02.md`](SIMPLE_RESULT_VN_TM02.md) | Agent-neutral Vietnamese simplification protocol for dense research, discussion, planning, review, and reporting results |

## Plans And Handovers Kept In This Directory

These are authority level 4: they preserve intent and history, and the code outranks them.

| Document | Maintained content |
|---|---|
| [`archive/roadmaps/TOBI_REFACTORING_PLAN_2026-07-18.md`](archive/roadmaps/TOBI_REFACTORING_PLAN_2026-07-18.md) | Historical structural-debt plan; not current authority |
| [`archive/handovers/HANDOVER_DEVELOPER_MODULE_2026-07-28.md`](archive/handovers/HANDOVER_DEVELOPER_MODULE_2026-07-28.md) | Point-in-time Developer handover; historical |

## Special Files

- [`UPDATE_DOCS_TM01.md`](UPDATE_DOCS_TM01.md) is the agent-neutral full documentation refresh protocol. Run it when the owner says `UPDATE DOCS TM01`; it defines inventory, verification, archive, queue, audit, and handoff rules.
- [`SIMPLE_RESULT_VN_TM02.md`](SIMPLE_RESULT_VN_TM02.md) is the agent-neutral Vietnamese simplification protocol. Run it when the owner says `SIMPLE RESULT VN TM2`; it turns dense results into brief, plain Vietnamese while preserving technical terms where useful.
- `../SOUL.md` and `../hermes_skills/` are runtime inputs, not ordinary documentation. They were not changed during this docs refactor.
- `.tobi/` and `.hermes/` contain ignored runtime or user data. Copies of Markdown files there are not canonical docs.
- `graphify-out/` is generated navigation data. It can help locate code, but its local index may lag recent commits and must not override the code.
- The feature queue is deliberately preserved. Do not rewrite old plans merely because the implementation evolved.
- `morpheus/` contains a local visual mockup only. It is not a shipped route or backend feature until code and queue evidence say so.

## Maintenance Rule

Update `02_CURRENT_STATE.md`, `ARCHITECTURE.md`, and `MISSION_CONTROL.md` when a change alters a user-visible capability, API domain, persistent state owner, security boundary, route, or execution flow. Update the queue row when a queued feature changes status. Move superseded narrative into `archive/` rather than letting two files claim to be current.

For a complete repository-wide refresh, follow [`UPDATE_DOCS_TM01.md`](UPDATE_DOCS_TM01.md). It is deliberately agent-neutral so Codex, Claude Code, OpenCode, Cursor, DeepSeek, and other agents use the same source-of-truth and archive rules. For dense results that need an owner-friendly Vietnamese version, follow [`SIMPLE_RESULT_VN_TM02.md`](SIMPLE_RESULT_VN_TM02.md).

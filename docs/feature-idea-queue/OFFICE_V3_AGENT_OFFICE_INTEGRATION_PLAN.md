# Office V3 - Agent Office Inspired Command Center

## Status

- Queue status: Queued
- Queue item: #15
- Planning mode: Complete; ready for worker implementation when selected
- Implementation boundary: Do not implement from this file until the queue item is picked up
- Primary owner intent: full visible replacement of the current Office UI

## Executive Summary

Office V3 should become a premium pixel-office agent command center inside MC. It should fully replace the current visible Office experience while preserving the useful backend foundations already present in MC: agents, missions, workflows, mission streaming, office stats, and Conductor approvals.

The main product success signal is UI quality. The new Office should feel much more polished, useful, and serious than the current page, while keeping a strong pixel-office identity inspired by the open-source `agent-office` project.

This is a planning-first queue item. It must not start implementation until selected by the owner.

## Owner Decisions

Locked decisions from planning Q&A:

- Office V3 should primarily be an agent command center.
- The visible current Office UI should be fully replaced.
- The main success signal is better UI.
- Current Office fails because of both poor visual/UI and weak usefulness.
- Preserve backend/data foundations only; visible UI is disposable.
- Pixel-office style should remain the main identity.
- Reuse existing Conductor approval/audit for TOBI Office actions.
- Show action history in both global Actions and Office-local activity.
- Add an embedded Office-specific TOBI panel.
- Use `agent-office` as inspiration only, not copied code/assets/packages.
- Most important `agent-office` ideas: live office plus activity.
- Avoid Colyseus; reuse MC FastAPI/SSE/API patterns.
- First work-output feature: mission/task output such as reports, plans, and next actions.
- Save work artifacts, not full editable documents in v1.
- Defer file upload/analysis to Project v2 Resources.
- First screen: live office floor.
- Design reference: premium pixel office.
- UI density: balanced.
- Data model: minimal new models.
- Version history: not in v1; store latest only.
- AI outputs should become reusable Office artifacts.
- Flagship TOBI action: run mission/report.
- TOBI should apply approved changes directly.
- Context selection for agent/mission/artifact is required.
- All Office mutations require explicit confirmation.
- Office artifacts are sensitive by default.
- Files should stay local-only in v1.
- Rollout should be a flagged replacement.
- Testing should be focused backend/frontend checks plus manual UI acceptance.
- Queue item should be #15 with a short preview-safe table row.

## Current Office Module Analysis

Current route and layout:

- `/office` is lazy-loaded in `dashboard/src/App.tsx`.
- Sidebar entry exists under Operation in `dashboard/src/components/AppShell.tsx`.
- Current page is `dashboard/src/pages/Office.tsx`.
- Current page has two visible modes: `hq` and `ops`.
- Current page includes a Phaser scene through `dashboard/src/office/PhaserGame.tsx`.
- Current page has a static/mobile fallback scene, agent cards, mission board, agent modal, mission modal, KPI overlay, mission launcher, and war-room panel.

Current backend/data foundations:

- `api/dashboard.py` exposes:
  - `GET /api/agents`
  - `GET /api/agents/{agent_id}`
  - `POST /api/agents`
  - `PATCH /api/agents/{agent_id}`
  - `DELETE /api/agents/{agent_id}`
  - `GET /api/missions`
  - `GET /api/missions/{mission_id}`
  - `POST /api/missions`
  - `PATCH /api/missions/{mission_id}`
  - `POST /api/missions/{mission_id}/run`
  - `GET /api/missions/{mission_id}/events`
  - mission pause/resume/cancel/inject
  - `GET /api/workflows`
  - `GET /api/office/stats`
- `dashboard/src/api.ts` already has TypeScript types and functions for Agents, Missions, Workflows, and OfficeStats.
- Mission streaming already uses existing MC SSE patterns.

Assessment:

- Keep backend APIs and database foundations.
- Preserve mission stream behavior.
- Preserve the concept of agents, missions, and live war-room.
- Replace the visible Office page structure and visual language.
- Avoid another large single-file Office implementation; split V3 into smaller components.

## Agent-Office Repository Analysis Summary

Reference repository:

- GitHub: `https://github.com/harishkotra/agent-office`
- License: MIT
- Stated purpose: self-growing AI teams in a pixel-art virtual office, powered by local LLMs.
- Stack from README/package manifests:
  - TypeScript monorepo
  - React UI
  - Phaser renderer
  - Colyseus real-time room server
  - Express server
  - SQLite memory store
  - Ollama local LLM adapter
  - OpenAI-compatible adapter
  - optional Tavily search
  - Docker Compose with server, UI, Redis, and Ollama

Important ideas from `agent-office`:

- Pixel-art virtual office as a live agent workspace.
- Agents have roles, personalities, tasks, thoughts, and actions.
- Agents walk to desks/furniture and interact visually.
- Agent-to-agent conversations appear in activity/chat.
- Task assignment can happen from UI or agents.
- Persistent memory and semantic search shape agent behavior.
- System activity log makes invisible agent activity legible.
- Layout/furniture concepts make the office feel spatial and alive.

Things not suitable for direct MC adoption:

- Colyseus server/runtime.
- Separate Node/Express backend.
- Redis/scaling architecture.
- Ollama-first assumption.
- Autonomous hiring in v1.
- Direct package import from `@agent-office/*`.
- Copying sprites/assets/UI/components.

## License And Reuse Strategy

The repo is MIT licensed, which allows reuse if copyright and license notice requirements are followed. However, the owner selected inspiration-only.

Implementation rules:

- Do not copy code from `agent-office`.
- Do not copy art assets or screenshots.
- Do not import `@agent-office` packages.
- Do not add Colyseus, Redis, or a separate Node backend.
- Learn from architecture and UX patterns only.
- If a future worker proposes code reuse, it must be a separate owner-approved decision and include license attribution.

## Office V3 Product Scope

V1 must include:

- Full visual replacement of the current Office page.
- Premium pixel-office first screen.
- Agent presence/status/current work.
- Mission queue and mission control.
- Embedded Office TOBI panel.
- Agent/mission/artifact context selection.
- Office activity feed.
- Reusable Office artifacts for mission reports, plans, summaries, and next actions.
- Flagship TOBI action: run mission/report.
- All Office mutations require confirmation.
- Global Actions audit integration.
- Flagged rollout/fallback to current Office.

V1 must not include:

- Full rich document editor.
- Full document version history.
- Office-specific file upload system.
- Cloud sync.
- Colyseus.
- Redis.
- Separate Office backend service.
- Autonomous agent hiring.
- Direct code/assets/dependency reuse from `agent-office`.

## Office V3 Architecture Plan

Use the existing MC architecture:

- React page under the existing `/office` route.
- Existing app shell, theme system, motion system, toast system, and API client.
- Existing backend route module `api/dashboard.py`.
- Existing SQLite schema/migration style.
- Existing mission SSE stream.
- Existing Conductor risk/approval/audit pattern.
- Existing LLM/model router where TOBI actions require model calls.

Proposed frontend shape:

```text
dashboard/src/pages/Office.tsx
dashboard/src/components/office-v3/
  OfficeV3Shell.tsx
  OfficeFloor.tsx
  AgentDock.tsx
  AgentDetailPanel.tsx
  MissionCommandPanel.tsx
  OfficeTobiPanel.tsx
  OfficeActivityFeed.tsx
  OfficeArtifactPanel.tsx
  OfficeCommandBar.tsx
  OfficeEmptyStates.tsx
```

Implementation guidance:

- `Office.tsx` should become a thin page-level orchestrator.
- Keep Phaser scene lazy-loaded if reused.
- Prefer small reusable panels over one large file.
- Keep current backend calls functional while redesigning the UI.
- Add new API calls only for artifacts/activity/snapshot if needed.

Proposed backend shape:

```text
core/office_artifacts.py
api/dashboard.py Office V3 endpoints
```

Backend should remain simple:

- Fetch current agents/missions/stats.
- Store artifacts.
- Store Office-local activity metadata.
- No separate process.

## UI/UX Redesign Plan

Office V3 must feel like a premium pixel-office command center.

First-screen composition:

- Full-bleed office floor as the main first visual.
- Agent sprites/stations with clear names/status/work state.
- A command rail for mission and agent operations.
- Right-side contextual panel for selected agent, mission, or artifact.
- Embedded Office TOBI panel, context-aware by selection.
- Office activity feed that can collapse/expand.

Visual style:

- Pixel-office identity remains central.
- Polish should be closer to premium SaaS than playful toy UI.
- Use restrained MC-compatible colors and Theme v2 tokens where available.
- Avoid huge unreadable decorative effects.
- Avoid nested cards.
- Use icons for actions from `lucide-react`.
- Keep panels dense enough for repeated serious use.

Required states:

- Loading: existing `PageLoader` or Office-specific loading shell.
- Empty agents/missions: clear empty state and "create first mission" action.
- Error: recoverable panel with retry.
- Mission running: live status, active agent, streamed step text.
- Confirmation required: Conductor-style action card.
- Mobile: stacked office/agents/activity/TOBI sections; if Phaser is too heavy, use static pixel office fallback.

User workflows:

- Select an agent -> see status, current work, skills, recent activity, TOBI actions.
- Select a mission -> see steps, progress, run controls, report/artifact actions.
- Ask TOBI in Office -> TOBI knows selected context.
- Run mission/report -> approved action, mission stream, save artifact.
- Review artifact -> see summary/report/plan and related activity.

## TOBI Integration Plan

Embedded Office TOBI panel:

- Shows selected context chips:
  - selected agent
  - selected mission
  - selected artifact
  - current view
- Provides suggested prompts based on context:
  - "Summarize this mission"
  - "Turn this into next actions"
  - "What is this agent doing?"
  - "Create a report from this mission"
  - "Assign follow-up work"
- Uses existing Conductor approval for actions.
- Shows action status and failure details inline.

Required TOBI actions:

- Create mission/report proposal.
- Summarize mission output.
- Convert mission/artifact into tasks.
- Save result as Office artifact.
- Assign agent work through existing task/mission systems where available.

Behavior:

- TOBI can directly apply approved changes.
- All mutations require confirmation.
- Failed actions must report:
  - what was attempted
  - what changed
  - what did not change
  - how the owner can retry

## Office Action And Tool Bridge Plan

Reuse Conductor patterns. Do not invent a parallel approval system.

Office action bridge should support:

- Read actions:
  - get office snapshot
  - get agent status
  - get mission detail
  - get artifact detail
  - get office activity
- Mutating actions:
  - create mission
  - run mission
  - pause/resume/cancel mission
  - assign work
  - create artifact
  - update artifact
  - convert artifact/mission output to tasks

All mutating actions:

- require explicit owner confirmation
- write global `tobi_actions`
- write Office-local activity row
- avoid logging full sensitive content in generic logs

## Data Model And Storage Plan

Keep data additions minimal.

Recommended new table: `office_artifacts`

Purpose:

- Store reusable reports, plans, summaries, mission notes, and next-action documents.

Suggested fields:

```text
id INTEGER PRIMARY KEY
title TEXT NOT NULL
kind TEXT NOT NULL
content TEXT NOT NULL
source_type TEXT
source_id INTEGER
sensitivity TEXT DEFAULT 'sensitive'
created_by TEXT DEFAULT 'tobi'
created_at TEXT DEFAULT CURRENT_TIMESTAMP
updated_at TEXT DEFAULT CURRENT_TIMESTAMP
```

Recommended new table: `office_activity`

Purpose:

- Store Office-local event history while still using global Actions audit for Conductor actions.

Suggested fields:

```text
id INTEGER PRIMARY KEY
event_type TEXT NOT NULL
actor TEXT NOT NULL
summary TEXT NOT NULL
payload_json TEXT
source_type TEXT
source_id INTEGER
created_at TEXT DEFAULT CURRENT_TIMESTAMP
```

Optional table: `office_layouts`

Only add if the worker implements saved scene layout:

```text
id INTEGER PRIMARY KEY
name TEXT UNIQUE NOT NULL
layout_json TEXT NOT NULL
updated_at TEXT DEFAULT CURRENT_TIMESTAMP
```

Do not add:

- document version tables
- file upload tables
- cloud sync metadata
- external workspace tables

## Backend/API Changes

Add only what is needed for V3.

Suggested endpoints:

```http
GET /api/office/v3/snapshot
GET /api/office/artifacts
POST /api/office/artifacts
GET /api/office/artifacts/{id}
PATCH /api/office/artifacts/{id}
GET /api/office/activity
GET /api/office/layout
PATCH /api/office/layout
```

Snapshot should aggregate:

- agents
- stats
- recent/running missions
- recent artifacts
- recent activity

Keep existing endpoints:

- `/api/agents`
- `/api/missions`
- `/api/missions/{id}/events`
- `/api/office/stats`

Do not break existing API shapes unless the old UI is fully retired behind the flag.

## Frontend State Management Plan

Use local page state and existing API functions.

Recommended state:

- active view/state: floor, mission, artifact, activity
- selected context: agent id, mission id, artifact id
- snapshot loading/error
- mission stream state from existing `useMissionStream`
- TOBI panel draft/action state
- feature flag/fallback state

Avoid:

- new global state library
- duplicating project/task state
- storing sensitive artifact content in localStorage

Add API client functions in `dashboard/src/api.ts`:

- `getOfficeV3Snapshot`
- `getOfficeArtifacts`
- `createOfficeArtifact`
- `patchOfficeArtifact`
- `getOfficeActivity`

## File And Document Handling Plan

V1 should not implement Office-specific file uploads.

Rules:

- If files are needed, reference Project v2 Resources later.
- Office V3 can link to existing project resources in a future phase.
- Office artifacts are text outputs generated from missions or TOBI actions.
- Uploaded files stay local-only if a future phase adds them.

## Security, Privacy, And Permissions Plan

Office artifacts are sensitive by default.

Required rules:

- Do not log full artifact content in broad app logs.
- Do not include full artifact content in `tobi_actions` summaries.
- Do not upload Office files to external services.
- Do not interact with Supabase or Vercel.
- Do not expose provider keys.
- All mutations require confirmation:
  - create mission
  - run mission
  - pause/resume/cancel mission
  - create/update/delete artifact
  - assign work
  - convert to tasks
  - overwrite artifact
- Delete and overwrite must be high-risk.
- Artifact content should only be shared with the LLM when explicitly used as Office context.

## Migration And Backward Compatibility Plan

Use a flagged replacement.

Implementation options:

- `OFFICE_V3_ENABLED` backend/frontend config, or
- frontend constant/local feature flag, or
- temporary internal route during implementation

Expected rollout:

1. Build Office V3 while old Office remains available behind fallback.
2. Verify V3 manually.
3. Promote V3 to `/office`.
4. Keep old Office code temporarily if fallback is cheap.
5. Remove old UI only after owner approval.

No existing agent/mission/workflow data should be migrated or deleted.

Artifact/activity migrations must be:

- idempotent
- additive
- safe on existing databases

## Testing Plan

Backend focused tests:

- Office artifact create/list/detail/update.
- Office activity list/create helper.
- Office snapshot returns agents/missions/stats without crashing.
- Sensitive artifact content is not leaked into summary-only activity fields.
- Mutating Office actions require/produce confirmation through Conductor bridge where implemented.

Frontend checks:

- `npm run build` from `tobi/dashboard`.
- Office route loads.
- Agent selection updates context panel.
- Mission selection/run still works.
- Mission SSE still updates live state.
- TOBI panel shows selected context.
- Artifact list/detail renders.
- Activity feed renders.
- Fallback flag can switch away from V3.

Manual acceptance:

- Desktop layout looks premium and readable.
- Mobile layout is usable.
- Empty/loading/error states are clear.
- No visual overlap in common viewport sizes.
- No huge unexplained blank scene.
- Current app navigation still works.

## Rollback Plan

Rollback should be simple:

- Disable Office V3 flag or route switch.
- Return `/office` to old Office component.
- Keep new artifact/activity tables; they are additive and harmless.
- Do not delete existing missions/agents.
- If new endpoints fail, old endpoints remain intact.

## Dependencies To Add Or Avoid

Avoid new dependencies in v1.

Do not add:

- Colyseus
- Redis
- Express server
- `@agent-office/*` packages
- new document editor frameworks
- cloud storage SDKs

Allowed:

- Existing Phaser if reused.
- Existing framer-motion/lucide/Tailwind/React.
- Existing backend Python/FastAPI/SQLite stack.

## Files Likely To Change

Likely existing files:

- `tobi/dashboard/src/pages/Office.tsx`
- `tobi/dashboard/src/api.ts`
- `tobi/api/dashboard.py`

Likely new frontend files:

- `tobi/dashboard/src/components/office-v3/OfficeV3Shell.tsx`
- `tobi/dashboard/src/components/office-v3/OfficeFloor.tsx`
- `tobi/dashboard/src/components/office-v3/AgentDock.tsx`
- `tobi/dashboard/src/components/office-v3/MissionCommandPanel.tsx`
- `tobi/dashboard/src/components/office-v3/OfficeTobiPanel.tsx`
- `tobi/dashboard/src/components/office-v3/OfficeActivityFeed.tsx`
- `tobi/dashboard/src/components/office-v3/OfficeArtifactPanel.tsx`

Likely new backend files:

- `tobi/core/office_artifacts.py`

Likely tests:

- `tobi/tests/test_office_v3.py`

Docs:

- `tobi/docs/feature-idea-queue/OFFICE_V3_AGENT_OFFICE_INTEGRATION_PLAN.md`
- `tobi/docs/feature-idea-queue/QUEUE.md`

## Risks

- Current Office page is large and can become difficult to refactor safely.
- Pixel-office polish can consume more time than backend work.
- Phaser integration can create layout/performance issues.
- Theme v2 is in progress and may conflict with styling.
- Project v2 and Premium Ability may touch adjacent TOBI context patterns.
- Too much agent-office imitation would pull MC into the wrong architecture.

## Assumptions

- Office V3 is queue item #15.
- Theme v2 may land before Office V3 implementation.
- Worker will not copy code/assets from `agent-office`.
- Worker will not add Colyseus or Redis.
- Worker will keep existing backend mission/agent data.
- Worker will keep all Office mutations approval-gated.
- Worker will treat Office artifacts as sensitive.

## Parallel Work Conflict Warning

High conflict risk if implemented in parallel with:

- Theme v2 final review/fixes
- Any Office UI work
- Agent/mission API changes
- Conductor action/approval rewrites
- Header/tab/page-shell redesign

Lower conflict risk:

- Backend-only unrelated storage/reporting work
- Documentation-only planning
- Non-Office pages

## Final Implementation Task Breakdown

Worker should implement in this order:

1. Add Office V3 feature flag/fallback structure.
2. Split current Office page into a V3 shell without deleting backend integrations.
3. Build premium pixel-office first screen.
4. Build agent dock and selected-agent panel.
5. Build mission command panel using existing mission APIs.
6. Preserve mission SSE live run behavior.
7. Add Office TOBI contextual panel.
8. Add `office_artifacts` and `office_activity` schema helpers.
9. Add minimal artifact/activity API endpoints.
10. Wire artifact creation from mission/report output.
11. Route all mutations through confirmation/audit.
12. Add local Office activity feed.
13. Add empty/loading/error/mobile states.
14. Add focused tests.
15. Run frontend build and manual acceptance checklist.
16. Keep old Office fallback until owner verifies V3.

## Completion Definition

Office V3 is complete when:

- `/office` can show the new premium pixel-office command center.
- Existing agent/mission data appears correctly.
- Mission run/live stream still works.
- Embedded Office TOBI uses selected context.
- Mission/report output can be saved as a reusable artifact.
- Office activity appears locally and relevant actions appear globally.
- All mutations require confirmation.
- No cloud/external storage is introduced.
- Build/tests/manual checks pass or skipped checks are documented.

## Final Queue Row

Use this short row for preview readability:

```md
| 15 | **Office V3** - agent-office inspired command center | 🟡 Queued | [OFFICE_V3_AGENT_OFFICE_INTEGRATION_PLAN.md](OFFICE_V3_AGENT_OFFICE_INTEGRATION_PLAN.md) | Full replacement of current Office UI into a premium pixel-office agent command center. Reuses MC agents/missions/SSE/Conductor; inspiration-only from MIT agent-office; no Colyseus or copied code. High conflict risk with Office, Theme v2, and agent/mission UI work. |
```

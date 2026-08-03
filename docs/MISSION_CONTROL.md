# Mission Control

> Current product and implementation reference for the web cockpit as of 2026-07-16. The old June master specification is preserved in `archive/specifications/` and is not current architecture.

## Purpose

Mission Control (MC) is the owner-facing control surface for TOBI. It combines conversation, memory, projects, tasks, agent/missions, system configuration, integrations, execution history, health, cost, and storage in one React application served by the Python backend.

## Application Shell

MC is composed in this order:

`BrowserRouter -> ThemeProvider -> MotionProvider -> ToastProvider -> WorkspaceTabsProvider -> AppShell -> mounted route panes`

The shell provides:

- desktop sidebar with collapsible navigation groups;
- mobile drawer and bottom navigation;
- global workspace tab strip in the header;
- notifications/toasts and command palette;
- settings/system menu;
- theme and motion behavior shared by every page.

## Workspace Tabs

`WorkspaceTabsContext.tsx` is the source of truth.

| Rule | Current behavior |
|---|---|
| Capacity | Maximum five open workspace tabs |
| Persistence | Tabs, active tab, labels, and icons are restored from localStorage |
| Route identity | One tab per top-level route; all inner routes of one project share `/projects/{id}` identity |
| Page state | Open tab panes remain mounted and inactive panes are hidden, preserving local React state |
| Navigation | Sidebar navigation focuses an existing tab or opens a new one; at capacity the owner must close a tab |
| Closing | At least one tab must remain open; closing the active tab selects a nearby tab |
| Reordering | Header tabs support drag reordering |
| Dynamic projects | Project workspaces set their own tab label and icon while keeping one tab across Overview/Tasks/Goals/Resources/Activity |

Primary browser keys:

- `tobi.workspace.tabs.v2`
- `tobi.workspace.activeTab.v2`
- `tobi.workspace.tabLabels.v1`
- `tobi.workspace.tabIcons.v1`

## Route and Page Map

MC exposes 21 top-level workspace destinations plus dynamic project workspaces.

| Group | Route | Page responsibility | Primary backend/domain |
|---|---|---|---|
| Main | `/dashboard` | Operational overview, widgets, launch actions | status, PM stats, storage/usage, evolution |
| Main | `/inbox` | Notification and owner-attention surface | frontend toast/inbox state and related APIs |
| Main | `/chat` | Persistent multi-model conversation and execution | chat, Conductor, Brain, terminal, model router |
| Main | `/actions` | Audited TOBI action history | `tobi_actions`, Conductor APIs |
| Intelligence | `/brain` | Owner memory browse/edit/review/import/chat | Brain APIs |
| Intelligence | `/graph` | Knowledge graph exploration and editing | Graph APIs |
| Intelligence | `/architecture` | In-app explanatory diagram | Static frontend content; currently stale in places |
| Intelligence | `/ability` | Curated abilities, usage, coaching, versions, repository Hermes skills, and Awakening mirror | Ability/skill tables, Hermes parser, `/api/awakening` |
| Intelligence | `/evolution` | Tier progression, evidence, setup guidance, and reflection | Tier-1 Awakening registry plus legacy later-tier definitions |
| Intelligence | `/health` | Service/integration health and Performance Doctor | health/deep-test/performance APIs |
| Work | `/office` | Office V3 command floor: agents, missions, embedded TOBI, local artifacts/activity; `?legacy=1` fallback | Office V3 snapshot/read/proposal APIs plus existing mission SSE |
| Work | `/projects` | Project list and creation | Project v2 APIs |
| Work | `/projects/:projectId/*` | Full project workspace | Project v2 overview/tasks/goals/resources/activity |
| Work | `/task` | Cross-project and standalone task board | Task APIs |
| Explore | `/news` | AI news, models, tools, social trends | Explore APIs |
| System | `/settings` | Theme, motion, sound, and UI preferences | browser preferences and owner settings |
| System | `/models` | Provider keys, model discovery, routing, usage | LLM config/key APIs and vault |
| System | `/storage` | Storage attribution and LLM usage/cost | Storage and usage APIs |
| System | `/integrations` | Vault, integrations, Google OAuth, Genesis status | Vault/integration APIs |
| System | `/mcp` | MCP server/client, approvals, tools, A2A, tunnel | MCP/A2A APIs |
| System | `/control` | Manual engine readiness and triggers | `/api/run/*` |
| System | `/developer` | Goal assessment, bounded coding sprints, checkpointed worker execution, worker profiles, learning, queue, releases, and evidence | Developer/Coding Agent APIs |

The system menu still displays Document as an unavailable/soon entry; it does not have a route.

## Chat Architecture

### Persisted session model

- `chat_sessions` stores title, selected model, compacted summary metadata, and lifecycle state.
- `chat_messages` stores role/content/model/thinking/feedback/parent relationships. A private `runtime_run_id` link gives one canonical direct-Chat run exactly one replayable assistant response; public session payloads omit that link.
- Editing an earlier message creates a forked session rather than rewriting the original history.
- Compaction summarizes older context while preserving recent messages.
- The left session list and active session load through `dashboard/src/api.ts`.

### Streaming event model

The chat stream can emit:

- text deltas;
- phase/checkpoint events for the visible process timeline;
- pending actions for confirm/cancel cards;
- terminal output lines;
- picker questions;
- references/source metadata;
- model issue notices;
- normalized mode/context/plan/artifact events;
- typed runtime lifecycle events (`turn_started`, context/plan/step events, recovery, completion);
- completion/error events.

`ProcessTrace.tsx`, `ThinkingOrb.tsx`, rich Markdown blocks, and terminal UI render these events. The process timeline is presentation of emitted checkpoints, not an independent execution engine.

### Attachments

- Text, code, JSON, CSV, YAML, and similar uploads are folded into prompt context.
- PDFs use `pypdf` extraction with an honest fallback when extraction fails.
- Up to two YouTube links per turn can be read through the optional transcript dependency, summarized when long, and reduced to a capped excerpt if summarization fails. Unavailable transcripts produce an explicit reader notice.
- Images remain data URLs and use the selected model when it supports vision. Otherwise Chat transparently borrows the first configured vision-capable model; it refuses honestly when none is available.
- Per-file and total text limits protect context size; image count is capped.
- Chat attachments are turn inputs. They are not automatically durable Project resources.
- Premium-reader processing can be disabled with `ENABLE_PREMIUM_READERS` as a rollback switch.

### Modes and capabilities

The primary selector exposes:

| Mode | Current effect |
|---|---|
| Chat | Default conversation mode. Terminal tools are omitted and rejected server-side |
| Agent | Main execution mode. Supports planning, tools, terminal actions, artifacts, persisted runs, and recovery |
| Deep Research | Per-turn capability toggle in the `+` menu; plans searches, gathers/fences sources, synthesizes a report artifact |
| Project context | Automatically selected from explicit or high-confidence project references; ambiguous matches remain shallow and visible |

Legacy `terminal`, `research`, and `project` values are normalized to Agent or Chat-compatible behavior. Mode, capabilities, context, steps, tools, run ID, artifact IDs, and runtime turn ID are stored in message metadata. The `chat.mode_v2` and `chat_runtime_v2` owner settings provide rollback controls.

Plain-text direct Chat can run canonically only when the Chat runtime and every default-off Runtime V2 Chat gate are enabled. The gateway acknowledges the request, gives one worker an expiring lease (so duplicate deliveries cannot both answer), persists success or recovery, and replays the saved response for a completed duplicate. Attachments, read/tool Chat, and Agent remain on shadow/legacy execution. Turning off `runtime.v2_chat_execution` rolls back new direct-Chat work without changing already accepted runs.

Runtime route scopes narrow the usual tool set for speed. They are not permission grants: a known read-only tool can be admitted if the classifier routed too narrowly, while unknown or acting tools remain route-denied and mode/risk/approval policy stays server-authoritative. A direct-route prediction no longer creates an explicit empty allowlist at the Chat gateway.

### Agent run history

- `agent_runs` stores each Agent turn and its status.
- `agent_run_steps` records declared plans, every tool checkpoint, failures, terminal output, approvals, and recovery commands.
- Retry/Skip/Revise/Cancel commands target the original run rather than creating unrelated history.
- Assistant message metadata stores the same owner-facing checkpoint sequence, elapsed time, tools, run ID, and artifacts.
- `ProcessTrace` collapses a completed run to a compact summary; clicking it expands or collapses the durable action history after reload.

### Human review

The composer exposes review behavior for actions:

- ask before required actions;
- auto-accept for the current chat;
- persistent auto-accept preference.

This UI setting does not bypass terminal hard-deny rules or the terminal kill-switch. Terminal execution independently applies its approval mode and command risk.

### Awakening evidence and Brain sweeps

- External Read is `active` only when GitHub, Notion, or Google is adapter-ready and has fresh successful-test metadata. The default evidence lifetime is 24 hours (`AWAKENING_CONNECTOR_TTL_HOURS`).
- Google client credentials are setup only; Google remains partial until OAuth succeeds and a read test verifies access.
- Saving, rotating, or importing a credential resets stale test evidence unless that same flow verifies the connector.
- Brain conversation sweeps use fair per-chat cursors and an owner-token database lease so Chat, Brain, Conductor, scheduler, and manual triggers cannot double-process one sweep.
- Failed or malformed extraction batches are persisted for bounded exponential retry. Other chats continue, and resolved retries clear the duplicate raw payload.

## Project v2 Workspace

One project route remains mounted while the owner moves among inner tabs:

| Tab | Responsibility |
|---|---|
| Overview | Editable description, project metrics, active tasks, resources, goals, activity summary |
| Tasks | Grouped/sortable task list, task drawer, scheduling, estimates, subtasks, dependencies, assignee state |
| Goals | Goal metrics, filters, hierarchy/progress, linked-task rollups |
| Resources | Folders, unified upload/link modal, tags, grid/list views, previews, raw/download/open actions, link-card menus, rename, copy-link, and confirmed deletion |
| Activity | Project audit/history feed |

Project resources can be files or links. The backend performs safe path handling, content extraction, chunking/RAG, Storage accounting, and Graph synchronization. Conductor can list the contents of one project's Resources drive, read extracted text by fuzzy name or resource ID, and search the chunks. Resource text is marked as untrusted data, and binary resources return metadata plus an honest no-text note.

The older `docs/PROJECT_MODULE_SPEC.md` assumptions are not current; its preserved original is in the archive. The Project v2 queue entry and code are the relevant implementation record.

## Themes and Motion

Theme v2 currently defines 12 themes grouped into core, expressive, and brand-inspired families. Theme behavior is token-driven through `themeTokens.ts`, CSS variables, data attributes, self-hosted fonts, and migration of older preferences.

The UI also has Full/Reduced/Off motion modes. MotionProvider combines the owner setting with the operating system reduced-motion preference and applies the more restrictive behavior.

Theme #13 remains in owner-review state. Do not call it complete until the queue status changes.

## Frontend State Ownership

| State | Owner |
|---|---|
| Active route and browser history | React Router |
| Open workspace tabs | WorkspaceTabsContext + localStorage |
| Theme/customization | ThemeProvider + localStorage |
| Motion preference | MotionProvider + localStorage/OS preference |
| Toasts and temporary notifications | ToastProvider |
| Chat sessions/messages | SQLite through Chat APIs |
| Chat composer mode/review/web toggles | Chat page state plus selected localStorage preferences |
| Project data | SQLite and resource filesystem through PM APIs |
| Vault session | Browser memory/header plus backend vault state |
| Terminal mode/kill-switch/jobs | SQLite/terminal process state through Terminal APIs |
| Developer goals/workflows/workers | SQLite development ledger, Git worktrees, Coding Agent runtime, and optional supervised runner service |

## Backend API Domains

The browser client should use functions exported by `dashboard/src/api.ts` or its domain modules, not ad hoc fetch calls. Current extracted modules cover Tasks, Project Management, Brain, Abilities, Office, and Performance over shared `apiCore.ts`.

| Prefix | Domain |
|---|---|
| `/api/status`, `/api/health` | General runtime and health |
| `/api/tasks` | Shared task board and owner-input workflows |
| `/api/pm` | Project v2, goals, tasks, resources, folders, icons, dependencies, activity |
| `/api/chat` | Sessions, messages, streams, runtime config/traces, runs/recovery, artifacts, feedback, activity, compaction |
| `/api/conductor` | Tool/action status, audit, confirmation |
| `/api/terminal` | Engine status, approval mode, kill-switch, jobs, tools |
| `/api/developer` | Goal assessment, workflows, checkpoints, worker profiles, runner health, learning, queue, releases, and owner commands |
| `/api/brain` | Memories, categories, import, review, conflicts, narrative, chat |
| `/api/graph` | Graph data, search, paths, timeline, editing, sync |
| `/api/abilities`, `/api/proposals` | Ability metrics, details, coaching, version governance |
| `/api/hermes/skills` | Read-only repository Hermes skill metadata |
| `/api/evolution`, `/api/awakening` | Tier report/reflection and evidence-gated Tier-1 status |
| `/api/agents`, `/api/missions`, `/api/workflows`, `/api/office` | Office V3 snapshot/config/artifacts/activity/TOBI/action proposals plus existing mission system |
| `/api/vault`, `/api/integrations`, `/api/keys` | Secrets, profiles, provider credentials, connectors |
| `/api/mcp` and `/mcp` | MCP management and Streamable HTTP server |
| `/api/llm` | Provider/model config, discovery, usage, Hermes push |
| `/api/storage`, `/api/usage` | Disk and cost analytics |
| `/api/explore` | News/models/tools/social/config/digest |
| `/api/run` | Manual engine readiness and execution |

Sensitive vault/MCP management calls use `X-Vault-Session`. The broader MC API does not currently have a general login/auth layer.

## Known UI Truth Gaps

1. `/architecture` still describes the older Codespaces/MMO-focused system and understates the current Chat Runtime, Awakening, Project v2, MCP, terminal, and security architecture.
2. Tier 1 uses real Awakening evidence, but later Evolution tiers still rely on legacy definitions.
3. `/ability` combines curated DB abilities, repository Hermes skills, and an Awakening mirror without one unified runtime ownership model.
4. Runtime v2 and legacy Conductor paths coexist behind rollback flags; changes must preserve both contracts until rollout completes.
5. Awakening now requires fresh verified connector evidence, but several other integration and health labels remain configuration-dependent and must not be treated as successful without usable/authorized evidence.

These are documented rather than fixed here because this refactor is docs-only.

## Rules for Future MC Changes

1. Reuse AppShell, workspace tabs, contexts, theme tokens, motion primitives, icons, and `api.ts` conventions.
2. Keep page-specific state inside its mounted route pane; do not create another global navigation store.
3. Extend an existing backend domain before adding a parallel data model.
4. Preserve SSE event compatibility when changing Chat or mission execution.
5. Add explicit loading, empty, setup-needed, permission, error, cancellation, and retry states.
6. Treat external/project content as untrusted when it enters prompts or previews.
7. Update this file, `02_CURRENT_STATE.md`, and the queue delivery row with the implementation.

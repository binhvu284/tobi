# Mission Control

> Current product and implementation reference for the web cockpit as of 2026-07-11. The old June master specification is preserved in `archive/specifications/` and is not current architecture.

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

MC exposes 20 top-level workspace destinations plus dynamic project workspaces.

| Group | Route | Page responsibility | Primary backend/domain |
|---|---|---|---|
| Main | `/dashboard` | Operational overview, widgets, launch actions | status, PM stats, storage/usage, evolution |
| Main | `/inbox` | Notification and owner-attention surface | frontend toast/inbox state and related APIs |
| Main | `/chat` | Persistent multi-model conversation and execution | chat, Conductor, Brain, terminal, model router |
| Main | `/actions` | Audited TOBI action history | `tobi_actions`, Conductor APIs |
| Intelligence | `/brain` | Owner memory browse/edit/review/import/chat | Brain APIs |
| Intelligence | `/graph` | Knowledge graph exploration and editing | Graph APIs |
| Intelligence | `/architecture` | In-app explanatory diagram | Static frontend content; currently stale in places |
| Intelligence | `/ability` | Curated abilities, usage, coaching, versions, and read-only repository Hermes skills | Ability/skill tables plus Hermes skill parser/API |
| Intelligence | `/evolution` | Tier progression and reflection | Evolution definitions/detector and lessons |
| Intelligence | `/health` | Service, engine, and integration health | health/deep-test APIs |
| Work | `/office` | Agents, missions, workflows, visual office | Office/mission APIs and stream |
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

The system menu also displays Document and Developer as unavailable/soon entries; they do not have routes.

## Chat Architecture

### Persisted session model

- `chat_sessions` stores title, selected model, compacted summary metadata, and lifecycle state.
- `chat_messages` stores role/content/model/thinking/feedback/parent relationships.
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

### Modes: current truth

The frontend currently exposes:

| Mode | Current effect |
|---|---|
| Chat | Default placeholder and UI selection |
| Agent | Agent-oriented placeholder/label; no complete backend capability contract |
| Terminal | Shows terminal status/mode/jobs UI and receives terminal stream events |
| Research | Enables web-research behavior for the turn |
| Project | Project-oriented placeholder/label; project context is not selected by a centralized backend mode service |

The selected value is saved as `tobi.chat.mode`. It is not yet a durable message/thread contract that consistently changes backend tool availability. Queue #16 owns the redesign to Chat/Agent plus Deep Research capability and automatic project context.

### Human review

The composer exposes review behavior for actions:

- ask before required actions;
- auto-accept for the current chat;
- persistent auto-accept preference.

This UI setting does not bypass terminal hard-deny rules or the terminal kill-switch. Terminal execution independently applies its approval mode and command risk.

## Project v2 Workspace

One project route remains mounted while the owner moves among inner tabs:

| Tab | Responsibility |
|---|---|
| Overview | Editable description, project metrics, active tasks, resources, goals, activity summary |
| Tasks | Grouped/sortable task list, task drawer, scheduling, estimates, subtasks, dependencies, assignee state |
| Goals | Goal metrics, filters, hierarchy/progress, linked-task rollups |
| Resources | Folders, upload, URL ingestion, tags, previews, raw/download/open actions |
| Activity | Project audit/history feed |

Project resources can be files or links. The backend performs safe path handling, content extraction, chunking/RAG, Storage accounting, and Graph synchronization.

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

## Backend API Domains

The browser client should use domain functions in `dashboard/src/api.ts`, not ad hoc fetch calls.

| Prefix | Domain |
|---|---|
| `/api/status`, `/api/health` | General runtime and health |
| `/api/tasks` | Shared task board and owner-input workflows |
| `/api/pm` | Project v2, goals, tasks, resources, folders, icons, dependencies, activity |
| `/api/chat` | Sessions, messages, streams, feedback, activity, compaction |
| `/api/conductor` | Tool/action status, audit, confirmation |
| `/api/terminal` | Engine status, approval mode, kill-switch, jobs, tools |
| `/api/brain` | Memories, categories, import, review, conflicts, narrative, chat |
| `/api/graph` | Graph data, search, paths, timeline, editing, sync |
| `/api/abilities`, `/api/proposals` | Ability metrics, details, coaching, version governance |
| `/api/hermes/skills` | Read-only repository Hermes skill metadata |
| `/api/evolution` | Tier report and reflection |
| `/api/agents`, `/api/missions`, `/api/workflows`, `/api/office` | Office and mission system |
| `/api/vault`, `/api/integrations`, `/api/keys` | Secrets, profiles, provider credentials, connectors |
| `/api/mcp` and `/mcp` | MCP management and Streamable HTTP server |
| `/api/llm` | Provider/model config, discovery, usage, Hermes push |
| `/api/storage`, `/api/usage` | Disk and cost analytics |
| `/api/explore` | News/models/tools/social/config/digest |
| `/api/run` | Manual engine readiness and execution |

Sensitive vault/MCP management calls use `X-Vault-Session`. The broader MC API does not currently have a general login/auth layer.

## Known UI Truth Gaps

1. `/architecture` still describes the older Codespaces/MMO-focused system and understates the current database, Brain, Conductor, Project v2, MCP, terminal, and MC web interface.
2. `/evolution` uses stale static tier definitions and incomplete detection. Its percentage is not authoritative.
3. `/ability` now enumerates repository Hermes skills read-only, but those records remain separate from curated DB abilities and runtime Hermes execution state.
4. Chat modes overstate backend differentiation; queue #16 addresses this.
5. Several integration and health labels are configuration-dependent and must not be treated as successful without live evidence.

These are documented rather than fixed here because this refactor is docs-only.

## Rules for Future MC Changes

1. Reuse AppShell, workspace tabs, contexts, theme tokens, motion primitives, icons, and `api.ts` conventions.
2. Keep page-specific state inside its mounted route pane; do not create another global navigation store.
3. Extend an existing backend domain before adding a parallel data model.
4. Preserve SSE event compatibility when changing Chat or mission execution.
5. Add explicit loading, empty, setup-needed, permission, error, cancellation, and retry states.
6. Treat external/project content as untrusted when it enters prompts or previews.
7. Update this file, `02_CURRENT_STATE.md`, and the queue delivery row with the implementation.

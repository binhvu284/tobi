# Mission Control

> Current product and implementation reference for the web cockpit as of 2026-08-28. The old June master specification is preserved in `archive/specifications/` and is not current architecture.

## TM01 Refresh Snapshot - 2026-08-28

The current MC shell has Overview, Work, Process, Agents, History, and System views for the
Developer area, shared Runtime V2 Runs projections, and a persistent workspace-tab shell. The
committed runtime keeps rollout controls off and uses passive adapters for non-Chat surfaces.
#34/T08 makes the Evaluations view distinguish canonical evidence, raw model quality, deterministic
recovery, and the exact release blocker. Its live proof banner reports calls returned, model-alone
pass rate, recovery rate, and direct spend in plain language. Health and the release gate use the
same 29-suite list.

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

MC exposes 22 top-level workspace destinations plus dynamic project workspaces.

| Group | Route | Page responsibility | Primary backend/domain |
|---|---|---|---|
| Main | `/ui2` | UI 2.0 live screen (#36): one conversation with TOBI, five agent states, action rows, and a canvas for panels and documents; `?demo=1` runs the design's scripted session | chat stream (Conductor tools), LLM config, projects, conductor status, health |
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

## UI 2.0 Live Screen (#36, phase 1)

`/ui2` is the design shell in [`feature-idea-queue/TOBI_UI_2_SHELL.html`](feature-idea-queue/TOBI_UI_2_SHELL.html) rebuilt as React components. It is the first entry of the rail's Main group and a normal workspace tab.

| Piece | Where | What it is |
|---|---|---|
| Page | `dashboard/src/pages/UI2.tsx` | Lazy route. Owns the menus, the two overlays (end dialog, history sheet) and the keys: `Esc` (leave full screen, close menus, stop the run, lock the microphone), `Alt M`, hold `Space`, `Ctrl U`. Keys only fire while the page is the visible tab. |
| Design system | `dashboard/src/ui2/ui2.css` | Generated by `node scripts/ui2_css.mjs` from the shell: every rule is the shell's own, scoped under `.ui2`; the prototype's rail, tab strip and viewer band are dropped because MC draws its own. Single dark theme, as the shell declares. Regenerate rather than hand-edit. |
| State | `dashboard/src/ui2/session.ts` | One store (`LiveSession`, read through `useSyncExternalStore`): view (standby, boot, live), the five moods, the transcript, the canvas, voice mode, speaker on/off and volume, history. The instance outlives the page, so closing the tab does not end a session. |
| Drivers | `dashboard/src/ui2/drivers.ts` | What runs behind the glass, speaking to the screen only through a `Sink`. `chatDriver` (default) creates a Chat session and streams typed turns through `/api/chat/sessions/:id/stream` in agent mode, mapping thinking phases and runtime step events to action rows, usage to the receipt and context donut, `action` frames to a one-line confirmation that calls `/api/conductor/confirm`, and artifacts to canvas documents. `scriptedDriver` (`?demo=1`) is the shell's own demonstration run. |
| Boot | `session.ts` | Five real checks on the shell's clock: model list, project count, Conductor tool count, canvas, voice. A failed check stops the boot, names the reason, and offers Try again. |
| Graph | `dashboard/src/ui2/brain.ts` | The memory-graph canvas engine, ported from the shell. Reduced motion (system preference or MC's Motion setting) draws it still. |
| Fit | `ui2.css` footer (via the script) | The asleep and waking screens centre their block in the pane and the live screen keeps the head at the top; the head shrinks below 860px and 700px of viewport height; under 900px wide the page is one column and an open canvas takes the whole viewport. The model menu groups models by provider, scrolls, and opens on the model in use. When MC's header is hidden, its "show header" chip floats over the pane's top-right corner, and the page steps its corner controls out from under it (`.chipped`). |

Not there yet, by phase: the voice pipeline (P2: speech in and out, barge-in, WebSocket session; the microphone modes exist as controls, and a live ghost bubble says voice arrives in phase 2), backend session persistence and reload, the budget meter and cap, and real MC pages rendered inside the canvas (P3). History lives in the browser (`localStorage`, key `tobi.ui2.history`) until P3 moves it to the backend. The speaker control is a stored preference with nothing to drive until P2.

## Chat Architecture

### Persisted session model

- `chat_sessions` stores title, selected model, compacted summary metadata, and lifecycle state.
- `chat_messages` stores role/content/model/thinking/feedback/parent relationships. A private `runtime_run_id` link gives one canonical direct-Chat run exactly one replayable assistant response; public session payloads omit that link.
- `chat_developer_dispatches` links one normal-Chat turn, proposal action, queue item, and Developer workflow. Its session/turn identity prevents duplicate work across retry and reload. The proposal keeps a concise objective plus the owner's full message context. Confirmed Queue plans preserve both, while the roadmap row uses a short context-derived title and description instead of flattening the full paste into one table cell.
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
- deterministic Developer proposal actions with context-resolved objectives and request-specific
  acceptance checks, plus linked live run state;
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

Explicit Developer capability requests (`Use Developer to ...` or `/developer ...`) bypass model
interpretation and create a proposal only. The existing confirmation action is the execution boundary:
acceptance creates or reuses one queue item, runs Developer preflight, and starts one durable workflow;
refusal creates none. Chat polls the linked dispatch endpoints for truthful stage, blocker, progress,
changed files, passed checks, and generated artifacts. A worker answer alone cannot mark the run complete.

### Runtime V2 Runs and rollout

`/runs` lists canonical history and opens Timeline, Trace, Evals, and Context views from one shared
reconnectable store. The same store supplies the non-activating loop recipe preference on Developer.
The client resumes from the last event sequence and deduplicates replayed events.

Rollout status reports the four ordered stages and their blockers. Each activation needs seven
consecutive comparisons and passing evaluation evidence. Activation, rollback, and resume require
an unlocked owner vault session. Projects, Office, CLI, Telegram, and scheduler entry points use
passive shadow adapters when Runtime event mirroring is enabled; their existing execution remains
the rollback owner.

The Runs -> Evaluations tab reads the bounded final-acceptance artifact. Canonical v2 artifacts show
category, workflow, lane, case, ECR, LDR, model-response, raw-pass, recovery, and blocker evidence.
Legacy v1 synthetic artifacts are quarantined rather than presented as release proof. The current
canonical artifact records 156/156 live model responses, raw model pass `32.0513%`, deterministic
recovery `67.9487%`, ECR `100`, scoped LDR `8.8021`, and `release_ready=true` with no artifact
blocker. The owner accepted the exact artifact on 2026-08-30, so Mission Control shows the release
gate open; any later artifact change invalidates that acceptance and closes the gate again.

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

- External Read is `active` only when GitHub, Notion, or Google is adapter-ready and has fresh successful-test metadata. The default evidence lifetime is 24 hours (`AWAKENING_CONNECTOR_TTL_HOURS`). On MC startup, a saved GitHub credential with stale proof is verified automatically before the UI opens; fresh proof is reused without a network call, so an ordinary restart does not require another manual GitHub test.
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

## Knowledge Graph Surface

The Graph page offers four arrangements, one at a time, chosen by the reader and frozen once computed. Only `free` runs physics; the other three place every node up front and pin it, so the picture is identical on every load.

| Mode | Arrangement | Node dragging |
|---|---|---|
| `clusters` (default) | One circle per community, sized by member count, circles packed with `d3-hierarchy` `packSiblings` | No |
| `orbit` | Highest-degree node centred, one labelled ring per hop out to an "unconnected" ring | No |
| `columns` | One panel per domain, members ordered by degree | No |
| `free` | Single force system: charge, springs, collision, weak centre pull, mild community nudge | Yes, and drops persist |

`dashboard/src/components/graph/layouts.ts` owns all four as pure functions of `{nodes, edges}`. Nothing else may compute node positions; the page renderer and every embed call `computeLayout`.

### Embedding the graph elsewhere

`GraphSigil` renders the graph as a square canvas asset at any size, for avatars, badges, and cards.

- It reuses `computeLayout`, so an embed can never drift from the page.
- It thins itself to the space it is given: below roughly 200px it keeps only the best-connected nodes, and the count scales with the pixel size. Dot radius has a floor so a 28px sigil still reads.
- Data comes from `graphSnapshot.ts`, a shared store that polls only while something is watching. Every sigil on a page costs one request, not one each.
- The Graph page publishes each unfiltered load into that store, so embeds are current the moment the owner navigates away from it.
- Motion is gated on the app motion setting and pauses when the sigil scrolls out of view.

`WelcomeCard` on the Dashboard is the reference use: the TOBI avatar is a live `orbit` sigil, and the node/link/group counts beside it read the same snapshot.

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
| Runtime Runs/trace/eval/loop state | Shared reconnectable runtime store backed by bounded `/api/runtime` projections |
| Graph layout choice | Graph page + localStorage (`tobi.graph.layout.v2`) |
| Graph data for embedded sigils | `graphSnapshot.ts` shared store, polled while watched and published by the Graph page |

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
| `/api/runtime` | Canonical runs, replay/snapshots, loops, bounded Eval evidence, staged rollout, rollback, and resume |

Sensitive vault/MCP management calls use `X-Vault-Session`. The broader MC API does not currently have a general login/auth layer.

## Known UI Truth Gaps

1. `/architecture` still describes the older Codespaces/MMO-focused system and understates the current Chat Runtime, Awakening, Project v2, MCP, terminal, and security architecture.
2. Tier 1 uses real Awakening evidence, but later Evolution tiers still rely on legacy definitions.
3. `/ability` combines curated DB abilities, repository Hermes skills, and an Awakening mirror without one unified runtime ownership model.
4. Runtime V2 is delivered, but passive adapters intentionally retain legacy execution as the rollback path; deletion needs a separate owner-approved exit review.
5. #34 routes only narrow safe workflows with no required fields through the supported production boundary. Required-field typed resolution and grounded outcomes are not broadly active in normal Chat/Agent work.
6. Awakening now requires fresh verified connector evidence, but several other integration and health labels remain configuration-dependent and must not be treated as successful without usable/authorized evidence.

These are documented rather than fixed here because this refactor is docs-only.

## Rules for Future MC Changes

1. Reuse AppShell, workspace tabs, contexts, theme tokens, motion primitives, icons, and `api.ts` conventions.
2. Keep page-specific state inside its mounted route pane; do not create another global navigation store.
3. Extend an existing backend domain before adding a parallel data model.
4. Preserve SSE event compatibility when changing Chat or mission execution.
5. Add explicit loading, empty, setup-needed, permission, error, cancellation, and retry states.
6. Treat external/project content as untrusted when it enters prompts or previews.
7. Update this file, `02_CURRENT_STATE.md`, and the queue delivery row with the implementation.

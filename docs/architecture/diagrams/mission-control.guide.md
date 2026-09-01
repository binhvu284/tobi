# Mission Control — frontend architecture guide

Mission Control is a React 18 + Vite app under `dashboard/src/`. A provider stack wraps a shell
that mounts workspace route panes; pages call a typed API client that funnels through one shared
HTTP core to the FastAPI backend. Heavy pages are lazy-loaded.

Changed since the last refresh: the Runs pane gained an **Evaluations** view, Chat gained a
**Developer dispatch card** that hands a described limitation to the Developer page, Brain V2 and
News V2 are now the live pages, the Graph pane gained pick-your-own auto layouts and the embeddable
GraphSigil, and the sidebar has a third width — fully closed, with a hover preview. Click any node
to jump to its notes.

## App
`App.tsx` — route composition and the lazy-loading boundaries. Each heavy page is a `React.lazy`
chunk wrapped in a `Suspense` fallback.

## Theme
`ThemeProvider` with `themeTokens.ts` and `index.css` — the token-driven light/dark theme system.

## Motion
`MotionProvider` and `components/motion/` — global motion levels and reusable animation primitives.

## Toast
`ToastProvider` — app-wide toasts (used for copy/export confirmations, errors, and notices).

## Tabs
`WorkspaceTabsProvider` — the five-tab workspace model: persistence, focus/close/reorder, and one
dynamic tab per project workspace.

## Shell
`AppShell.tsx` — sidebar, global header, tab strip, mobile navigation, and the system menu.

## Header
The global header: the workspace tab strip, theme switch, notifications, and the system menu
button, which now sits on the tab strip's centre line.

## Sidebar
Three widths, not two: full labels, icons only, and **fully closed**. In the closed state the rail
reappears as a hover preview, so navigation is one mouse move away instead of a click to reopen.
The chosen width persists.

## Palette
`components/CommandPalette.tsx` — keyboard-first jump to any page, project, or action.

## Panes
The mounted workspace route panes — up to five live route views restored from localStorage.

## Chat
Chat and Agent: persistent sessions, backend-enforced modes, typed runtime events, attachments,
premium readers, per-turn context chips, a live token counter that ticks up while the reply is
being composed, and full-screen preview for pasted images.

## Dispatch
`components/chat/DeveloperDispatchCard.tsx` — when you describe a limitation in ordinary Chat, a
card offers to turn it into Developer work. It creates nothing until you confirm, and after
confirmation it links to the queue item it created so status stays truthful.

## Runs
The Runs pane under Operation. Two views: **Runs**, one live read-only view of every run across
Chat, Projects, Office, the CLI, Telegram and the schedulers; and **Evaluations**, below. Summaries
are bounded, and when the list is empty it says why.

## EvalCenter
`components/runtime/EvalControlCenter.tsx` — the TOBIval control centre added by #34. It shows the
frozen exam cases, each case's recorded decisions and evidence, the live-model results, and whether
the release gate is open. It reads `/api/runtime/evals`, which requires an unlocked vault session.

## Developer
The Developer page — goals, the queue, sprints, review, evidence, and the durable runner. Its
default worker is now the DeepSeek Harness rather than the Codex/OpenCode command-line agents.

## Projects
Full-page project workspaces plus the standalone project/task views.

## Brain
The Brain page — Brain V2 is the live surface: memory browsing, review, quality checks, categories,
and conflict/version handling. `/brain/v2` and `/brain/legacy` both redirect here.

## Graph
The knowledge-graph pane: pick-your-own auto layouts (replacing the old fixed force simulation) and
**GraphSigil**, which renders a snapshot of the graph as an embeddable asset.

## Evolution
Evolution and Ability. Tier I is evidence-gated by Awakening; Tier II now reads the Agent tier
evidence registry and nothing else.

## Architecture
This page — the secure, repository-backed Mermaid viewer that replaced the hardcoded diagram.
Diagram sources live in `docs/architecture/diagrams/`, are validated before rendering, and each
one carries its own Git version history.

## Office
Office V3 — the flagged React shell over the Phaser/SSE mission surface, with the legacy Office
kept as a zero-data-loss fallback.

## Health
The Health page: an Overview tab with live API checks, an **Infrastructure** tab that proves the
Runtime V2 engine works on this machine, and a Performance tab with the system doctor.

## More
The remaining destinations: News V2, Explore, Models, Control Room, Storage, Integrations, MCP,
Actions, Inbox, and Settings.

## Morpheus
`morpheus/` — a separate workspace under `/morpheus/*` with its own shell, tabs, canvas, terminal,
and panels. It does not share the AppShell chrome.

## Client
`api.ts` — the compatibility barrel that re-exports every domain module so existing imports keep
working.

## Domains
Domain API modules (`api.tasks.ts`, `api.pm.ts`, `api.brain.ts`, `api.brainV2.ts`,
`api.abilities.ts`, `api.office.ts`, `api.performance.ts`, `api.architecture.ts`,
`api.runtime.ts`, `api.developer.ts`, `api.chat.ts`, `api.conductor.ts`) split off the barrel by
area.

## Core
`apiCore.ts` — the shared `get`/`request` HTTP layer, the `ApiError` type, and the
backend-mismatch detection every domain module builds on.

## DashAPI
The FastAPI app on port 8090 locally that serves these endpoints and the built React bundle.

## RuntimeAPI
`/api/runtime/*` and `/api/health/*` — canonical runs, run snapshots, evaluation overview and case
detail, rollout state, and the infrastructure self-check. See the **Mission Control Runtime**
diagram.

## RuntimeStore
`stores/runtime.ts` — one shared reconnecting store behind Runs and the Chat run views, so two
pages cannot disagree about the state of the same run.

## InfraCheck
`components/InfrastructureCheck.tsx` — the Health page's Infrastructure tab. One button that runs
twelve read-only checks of this server and then every acceptance suite in its own throwaway
database. Retries are now reported honestly instead of being folded into a single pass.

## Stream
Both deep checks arrive as server-sent events, one row at a time, so a sweep that takes a minute
shows progress instead of a blank panel.

## Async
`components/async-ui.tsx` — `ActionButton`, `BusyOverlay`, `ActivityBar` and `SectionSkeleton`.
Every control that starts async work uses one of these, so nothing can be double-fired or look
frozen. `tests/test_ui_loading_states.py` fails if a control ships without one.

## Lazy
Heavy chunks (Graph's force-graph, Office's Phaser engine, Recharts pages, the Architecture
Mermaid renderer, Runs, Developer, Morpheus, and project workspaces) are lazy-loaded to keep the
main bundle small.

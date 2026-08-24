# Mission Control — frontend architecture guide

Mission Control is a React 18 + TypeScript + Vite app under `dashboard/src/`. A provider stack
wraps a shell that mounts workspace route panes; pages call a typed API client that funnels
through one shared HTTP core to the FastAPI backend. Heavy pages are lazy-loaded. Click any node
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

## Panes
The mounted workspace route panes — up to five live route views restored from localStorage.

## Chat
Chat and Agent: persistent sessions, backend-enforced modes, typed runtime events, attachments,
premium readers, and per-turn context chips.

## Projects
Full-page project workspaces plus the standalone project/task views.

## Brain
The Brain management surface — memory browsing, review, categories, and conflict/version handling.

## Architecture
This page — the secure, repository-backed Mermaid viewer that replaced the hardcoded diagram.

## Client
`api.ts` — the compatibility barrel that re-exports every domain module so existing imports keep
working.

## Domains
Domain API modules (`api.tasks.ts`, `api.pm.ts`, `api.brain.ts`, `api.abilities.ts`,
`api.office.ts`, `api.performance.ts`, `api.architecture.ts`) split off the barrel by area.

## Core
`apiCore.ts` — the shared `get`/`request` HTTP layer, the `ApiError` type, and the
backend-mismatch detection every domain module builds on.

## DashAPI
The FastAPI app on port 8090 locally that serves these endpoints and the built React bundle.

## RuntimeAPI
`/api/runtime/*` and `/api/health/*` — canonical runs, run snapshots, rollout state, and the
infrastructure self-check. Added by queue #21; see the **Mission Control Runtime** diagram.

## Runs
The Runs pane under Operation — one live view of every run across Chat, Projects, Office, the CLI,
Telegram and the schedulers. Read-only, bounded summaries, and when it is empty it says why.

## RuntimeStore
`stores/runtime.ts` — one shared reconnecting store behind Runs and the Chat run views, so two
pages cannot disagree about the state of the same run.

## InfraCheck
`components/InfrastructureCheck.tsx` — the Health page's Infrastructure tab. One button that runs
twelve read-only checks of this server and then every acceptance suite in its own throwaway
database.

## Stream
Both deep checks arrive as server-sent events, one row at a time, so a sweep that takes a minute
shows progress instead of a blank panel.

## Async
`components/async-ui.tsx` — `ActionButton`, `BusyOverlay`, `ActivityBar` and `SectionSkeleton`.
Every control that starts async work uses one of these, so nothing can be double-fired or look
frozen. `tests/test_ui_loading_states.py` fails if a control ships without one.

## Lazy
Heavy chunks (Graph's force-graph, Office's Phaser engine, Recharts pages, the Architecture
Mermaid renderer, and project workspaces) are lazy-loaded to keep the main bundle small.

## Health
The Health page: an Overview tab with live API checks, an **Infrastructure** tab that proves the
Runtime V2 engine works on this machine, and a Performance tab with the system doctor.

## Developer
The Developer page — the Coding Agent control plane: goals, the queue, sprints, review, and the
durable runner.

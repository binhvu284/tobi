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
The FastAPI app on port 8080 that serves these endpoints and the built React bundle.

## Lazy
Heavy chunks (Graph's force-graph, Office's Phaser engine, Recharts pages, the Architecture
Mermaid renderer, and project workspaces) are lazy-loaded to keep the main bundle small.

# TOBI Agent Guide

Read [`docs/README.md`](docs/README.md) first. For implementation work, also read [`docs/02_CURRENT_STATE.md`](docs/02_CURRENT_STATE.md), [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md), and the relevant feature plan or domain section.

## Product Direction

TOBI's mission is a personal Jarvis: persistent owner understanding, safe real-world action, and reliable presence. The MMO/business loop is one implemented capability, not the product identity.

## Source of Truth

1. Code, schemas, and tests define current behavior.
2. Current documents in `docs/` explain that behavior.
3. `docs/feature-idea-queue/QUEUE.md` records delivery status.
4. Feature plans preserve original intent and may contain pre-implementation assumptions.
5. `docs/archive/` is historical only.

## Repository Map

- `main.py`: process entry point, scheduler, Telegram lifecycle, API launch.
- `core/`: Chat runtime/modes, Conductor, Agent runs, Awakening, Brain/Graph, model routing, terminal, projects/resources, integrations, MCP/A2A, storage/usage, Explore, and business engines.
- `api/dashboard.py`: Mission Control API plus static React host. It is a large monolith; inspect the relevant route group before editing.
- `api/server.py`: smaller API-key-protected legacy/external API.
- `dashboard/src/`: Mission Control application, global workspace tabs, pages, components, contexts, themes, and API client.
- `SOUL.md` and `hermes_skills/`: runtime inputs. Treat changes as behavior changes, not docs cleanup.

## Graphify

Generated Graphify data lives in `graphify-out/`. Use it to locate related symbols and flows, then verify the cited code. The local index can lag recent commits, so do not rely on stored node counts or treat the graph as current system truth. Refresh it after code changes when the Graphify tool is available.

## Working Rules

- Keep feature plans intact unless the task explicitly asks to revise a plan.
- Update current docs and the queue row when delivered behavior changes.
- Never expose `.env`, vault, OAuth, token, or key values.
- Do not claim an integration is connected from code presence alone; use current status evidence.
- For Awakening External Read, configured credentials are not proof: connector readiness plus a fresh successful integration test is required, and Google also requires completed OAuth.
- Treat Chat route allowlists as focus hints for safe reads, not permission boundaries. Mode denial, action risk, approval, terminal policy, and server-side validation remain the security boundaries.
- Preserve user/runtime data under `.tobi/`, `.hermes/`, the configured database directory, and project resources.
- Treat port-8080 Mission Control as a trusted single-owner surface unless authentication is added.
- Do not run `main.py start` casually: it starts Telegram and scheduled work. Use the narrower commands in [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) for local verification.
- UI buttons that trigger async work (network calls, renders, exports) MUST show an inline loading state — a spinner and/or a disabled state — for the duration, so the UI never appears frozen and the action can't be double-fired. Re-enable on both success and failure. Use the shared primitives in [`dashboard/src/components/async-ui.tsx`](dashboard/src/components/async-ui.tsx) rather than hand-rolling pending state; they own the re-enable-on-failure guarantee. Pick by blast radius: `ActionButton` when only the control is affected, `BusyOverlay` when one section's data is being replaced, `ActivityBar` for a page-wide refetch, `SectionSkeleton` only where no content exists yet. Never swap loaded content for a skeleton on refresh — it costs the reader their place; dim it instead. `tests/test_developer_loading_states.py` fails if a Developer control ships without one.
- **Backend changes must not drop the loading affordance.** Every regression of this rule so far arrived alongside a backend fix, when a control was rewritten for a new API shape and its pending state was not carried over. After changing an endpoint or a handler signature, re-run `tests/test_developer_loading_states.py`.
- Token efficiency: prefer token-saving methods — graphify-first analysis, targeted file-range reads, and search tools over full-file dumps (`core/performance_doctor.py` is the reference pattern: it reads the graph as a map and opens source only to count lines, never feeding raw code to an LLM). When you use one, name the method and give a rough estimate of the tokens or % saved versus the naive approach.

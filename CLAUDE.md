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
- `core/`: Conductor, Brain, Graph, model routing, terminal, projects/resources, integrations, MCP/A2A, storage/usage, Explore, and business engines.
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
- Preserve user/runtime data under `.tobi/`, `.hermes/`, the configured database directory, and project resources.
- Treat port-8080 Mission Control as a trusted single-owner surface unless authentication is added.
- Do not run `main.py start` casually: it starts Telegram and scheduled work. Use the narrower commands in [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) for local verification.

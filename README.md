# TOBI

TOBI is a single-owner AI assistant platform. The repository contains the Python agent runtime, Mission Control web application, persistent memory and project systems, terminal execution, integrations, and the Hermes bridge.

The long-term goal is a personal Jarvis: an assistant that understands its owner, can safely act across a computer and connected services, and remains available without being prompted.

## Start Here

| Read | Purpose |
|---|---|
| [`docs/README.md`](docs/README.md) | Documentation map and source-of-truth rules |
| [`docs/02_CURRENT_STATE.md`](docs/02_CURRENT_STATE.md) | What is implemented, partial, or misleading today |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Runtime, data, security, and component architecture |
| [`docs/MISSION_CONTROL.md`](docs/MISSION_CONTROL.md) | Current Mission Control routes, state, and UX architecture |
| [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) | Local setup, commands, tests, and operating cautions |
| [`docs/03_ROADMAP.md`](docs/03_ROADMAP.md) | Evidence-based next work and queue dependencies |

## Repository Map

| Path | Responsibility |
|---|---|
| `main.py` | Process entry point, scheduler, Telegram lifecycle, API launch |
| `core/` | Chat runtime/modes, Conductor, Agent runs, Awakening, memory, model routing, terminal, projects, integrations, MCP, and business engines |
| `api/dashboard.py` | Mission Control API and built React application host |
| `api/server.py` | Smaller API-key-protected legacy/external API |
| `dashboard/` | React 18, TypeScript, Vite, Tailwind, Mission Control UI |
| `docs/` | Current documentation, feature queue, and archive |
| `tests/` | Focused Chat/runtime, security, Awakening, terminal, readers, storage/usage, and performance tests |
| `SOUL.md` | Runtime persona input copied into Hermes; changing it changes behavior |
| `hermes_skills/` | Runtime skill inputs copied into Hermes |

## Current Shape

- Mission Control has 20 top-level workspace destinations plus dynamic project workspaces.
- The global header keeps up to five route tabs mounted and restores them from browser storage.
- Chat sessions use backend-enforced Chat/Agent modes. Runtime v2 routes intent, scopes tools, records typed traces, and persists Agent runs, checkpoints, recovery state, and artifacts around the Conductor. Safe known read tools can recover from an overly narrow route, while mode and action-risk boundaries remain authoritative.
- Awakening Tier 1 uses nine evidence-gated abilities rather than a hardcoded completion percentage. External-read evidence expires unless a ready connector has a fresh successful test, and Brain sweeps preserve failed extraction batches for retry.
- The Brain, Graph, Project v2, Office, Terminal, Vault, Integrations, MCP, Explore, Storage, and usage systems are implemented at different maturity levels. Project resources can be inventoried, searched, and read through grounded Conductor tools.
- SQLite is the primary application store. Project resources are stored on disk beside the database.
- Hermes receives persona, skills, memory, and model-routing data through one-way sync paths; it is not the sole runtime or source of truth today.

For commands and environment setup, use [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md). Do not treat archived specifications or feature plans as proof that a feature is live.

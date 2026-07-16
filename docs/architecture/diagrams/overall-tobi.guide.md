# Overall TOBI — architecture guide

TOBI is a single-owner personal-agent platform. The owner reaches it through three surfaces;
every request converges on the Conductor, which grounds answers in memory, routes models, and
executes read/action tools under risk policy. State lives in one SQLite database plus on-disk
project files. Click any node in the diagram to jump to its notes below.

## Owner
The single trusted operator. Mission Control is treated as a trusted single-owner surface; there
is no multi-tenant auth boundary inside it.

## MC
The Mission Control web app (React) — the primary interface. Served by the FastAPI process on
port 8080, which also hosts the UI APIs and SSE streams.

## TG
The Telegram bot surface. Shares the Conductor with Mission Control but stays read-only for
medium/high-risk actions.

## CLI
The `main.py` command line and interactive terminal REPL for local operation and development.

## DashAPI
`api/dashboard.py` — the Mission Control FastAPI app on port 8080: UI APIs, SSE, the static
React host, and the MCP mount. It is the largest module and the main change-collision point.

## Conductor
`core/conductor.py` — conversation routing, the grounded tool loop, permission/risk tiers,
confirmation cards, and the action audit log. Shared by Mission Control Chat and Telegram.

## Brain
`core/brain.py` plus the knowledge graph — durable owner memory, retrieval, review, and the
staged context (a cached stable profile plus task-specific retrieval) fed to Chat and Agent.

## Models
`core/model_router.py` — the provider catalog, fallback, streaming, vision routing, and usage
logging across the configured LLM providers.

## Tools
The Conductor's read and action tools: projects/tasks/goals/resources, the terminal engine,
connected services, MCP/A2A, and the research/execution/CEO/Explore engines.

## Projects
Project v2 data and resources: projects, tasks, goals, and the per-project Resources drive with
inventory/read/search, backed by SQLite plus on-disk resource files.

## Terminal
`core/terminal_engine.py` — full-machine shell execution with risk classification, approval
modes, a hard denylist, and a kill-switch.

## Integrations
`core/integrations.py` and the registry — Notion, GitHub, Google, Vercel, and Supabase adapters.
Connection state is configuration-dependent and evidence-gated, never assumed from code presence.

## MCP
Inbound and outbound Model Context Protocol plus agent-to-agent tooling, with its own auth,
scopes, rate limits, approvals, and call logs.

## Engines
The legacy-but-active business engines: niche research, project execution, the CEO portfolio
loop, and Explore ingestion.

## SQLite
The single embedded database (configurable via `DB_PATH`) holding memory, projects, actions,
runs, usage, and feature tables. Additive migrations only.

## DevControl
The Coding Agent control plane (`core/coding_agent.py` and friends): goal assessment, bounded
sprints, isolated Git worktrees, quality gates, independent review, and a durable runner queue.

## Hermes
One-way persona/skill/memory/model-routing sync paths to Hermes state. Multiple mirrors, not a
unified state owner.

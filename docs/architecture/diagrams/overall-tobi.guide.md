# Overall TOBI — architecture guide

TOBI is a single-owner personal-agent platform. The owner reaches it through three surfaces,
and since queue #21 all of them converge on **one engine**: every request becomes a canonical
*run* with ordered history, one set of rules, and enough saved state to survive a crash. The
Conductor still grounds answers in memory and routes models, but it is now a thin facade in front
of that engine rather than the engine itself.

Rollout controls ship **off**: today the runtime records and compares in shadow mode while the
existing path answers the owner. See the **Mission Control Runtime** diagram for the engine in
detail. State lives in one SQLite database plus on-disk project files. Click any node in the
diagram to jump to its notes below.

## Owner
The single trusted operator. Mission Control is treated as a trusted single-owner surface; there
is no multi-tenant auth boundary inside it.

## MC
The Mission Control web app (React) — the primary interface. Served by the FastAPI process on
port 8090 locally, which also hosts the UI APIs and SSE streams.

## TG
The Telegram bot surface. Shares the Conductor with Mission Control but stays read-only for
medium/high-risk actions.

## CLI
The `main.py` command line and interactive terminal REPL for local operation and development.

## DashAPI
`api/dashboard.py` plus the routers under `api/routers/` — the Mission Control FastAPI app on
port 8090: UI APIs, SSE, the static React host, the runtime API, and the MCP mount.

## Conductor
`core/conductor.py` — now a **compatibility facade**. It still accepts every argument it always
did, but classification, context assembly, the tool loop, recovery and response composition live in
`core/runtime/` services behind it. Shared by Mission Control Chat and Telegram.

## Brain
`core/brain.py` plus the knowledge graph — durable owner memory, retrieval, review, and the
staged context (a cached stable profile plus task-specific retrieval) fed to Chat and Agent.

## Models
`core/model_router.py` — the provider catalog, fallback, streaming, vision routing, and usage
logging across the configured LLM providers.

## Tools
Read and action tools: projects/tasks/goals/resources, the terminal engine, connected services,
MCP/A2A, and the research/execution/CEO/Explore engines. Each one is declared once in the tool
catalog, has its arguments validated before it runs, and leaves a receipt so a retry cannot apply
it twice.

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
runs, usage, and feature tables — plus the 22 canonical `mc_*` runtime tables added by #21.
Additive migrations only, recorded in a shared ledger the Health infrastructure test verifies.

## DevControl
The Coding Agent control plane (`core/coding_agent.py` and friends): goal assessment, bounded
sprints, isolated Git worktrees, quality gates, independent review, and a durable runner queue.

## Hermes
One-way persona/skill/memory/model-routing sync paths to Hermes state. Multiple mirrors, not a
unified state owner.

## Gateway
`core/runtime/gateway.py` — where a Chat or Agent turn enters the runtime. It decides whether the
turn is recorded, executed, or ignored, and never allows execution that is not traced.

## Adapter
`core/runtime/surface_adapter.py` — the compatibility door for Projects, Office, the CLI, Telegram
and the schedulers. Fail-open: if recording breaks, the real work still happens.

## Run
One canonical record per request: objective, surface, state, version, steps and evidence. The
thing this whole item exists to create.

## History
Append-only, strictly ordered events with secrets masked **before** storage. Current state is
rebuilt from these, so a summary can never drift from what actually happened.

## Steps
Leased steps and restart checkpoints: exactly one worker owns a step at a time, and a crash
resumes the same run instead of starting a new one.

## Policy
Permissions, risk tiers, approvals, credentials and budgets decided in one place, failing closed
when anything is missing.

## Catalog
Every tool described once, with its arguments validated before it runs.

## Receipts
Immutable proof that a mutation was applied, so a duplicate request cannot apply it twice.

## Trace
One trace per request joining context, model, tools, approvals, cost and outcome — and the quality
gates that block a release on missing or failed evidence.

## Rollout
Staged activation with a rollback switch. Each stage needs seven consecutive agreeing comparisons
plus quality evidence; one switch returns new work to shadow behaviour without touching runs that
already exist.

## RunsPage
The Runs pane and the Health checks that read this history — including **Health → Infrastructure**,
the one-click test that proves the whole engine works on this machine.

## Sched
The scheduler callbacks in `main.py`. They keep their own execution and enter history through the
adapter.

## Main
`main.py` — the process entry point and orchestrator. `main.py api` serves Mission Control and
the external API; `main.py start` adds Telegram polling and the schedulers.

## TelegramAdapter
`core/telegram_bot.py` — the Telegram surface. It shares the Conductor with Mission Control and
stays read-only for medium and high-risk actions.

## PublicAPI
`api/server.py` — the smaller API-key-protected external API on port 8000, separate from the
Mission Control app.

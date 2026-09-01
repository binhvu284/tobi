# Overall TOBI — architecture guide

TOBI is a single-owner personal-agent platform. The owner reaches it through three surfaces, and
since queue #21 all of them converge on **one engine**: every request becomes a canonical *run*
with ordered history, one set of rules, and enough saved state to survive a crash. The Conductor
still grounds answers in memory and routes models, but it is now a thin facade in front of that
engine rather than the engine itself.

Rollout controls still ship **off**: today the runtime records and compares in shadow mode while
the existing path answers the owner. What changed since the last refresh is the *proof* around it.
Queue #34 (TOBIval) added a frozen exam suite whose result the owner accepted on 2026-08-30, so
activation now has real evidence to stand on instead of an assumption. Queue #35 added the Agent
tier: TOBI can turn a limitation you describe in Chat into a confirmed Developer work item, and it
records evidence for each ability rather than claiming one. The Developer's default coding worker
is now the **DeepSeek Harness**, which runs in-process on the Models-page DeepSeek key; the Codex
and OpenCode command-line workers are still there but sit behind a feature flag.

State lives in one SQLite database plus on-disk project files. See the **Mission Control Runtime**
diagram for the engine in detail. Click any node in the diagram to jump to its notes below.

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

## Sched
The scheduler callbacks in `main.py` — daily reports, six-hour execution, task reminders, weekly
research and reflection, Brain sweeps, Graph sync, Storage scans, Explore refreshes, and the
first-of-month CEO review. They keep their own execution and enter history through the adapter.

## Main
`main.py` — the process entry point and orchestrator. `main.py api` serves Mission Control and
the external API; `main.py start` adds Telegram polling and the schedulers.

## PublicAPI
`api/server.py` — the smaller API-key-protected external API on port 8000, separate from the
Mission Control app.

## DashAPI
`api/dashboard.py` plus the routers under `api/routers/` — the Mission Control FastAPI app on
port 8090: UI APIs, SSE, the static React host, the runtime API, and the MCP mount.

## TelegramAdapter
`core/telegram_bot.py` — the Telegram surface. It shares the Conductor with Mission Control and
stays read-only for medium and high-risk actions.

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

## Workflows
`core/runtime/workflows.py` — the frozen catalog of the bounded jobs TOBI knows how to do, each
with its own required fields, allowed tools, stop condition, and what counts as success. Matching
is deterministic: the same wording always picks the same workflow, and a request outside the
catalog is refused rather than improvised. Added by #34 so a common task no longer depends on
which model happens to be selected.

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

## Cases
`tobival/dataset.py` — 72 frozen exam cases plus 14 held-back ones, locked by a hash so nobody can
quietly edit an exam to make a score look better. Each case runs through the real runtime rather
than a simulation.

## Scorers
`core/runtime/eval_scorers.py` and `eval_metrics.py` — the marking is code, not an opinion. A case
either produced the required evidence or it did not, and the numbers land in immutable records.

## ModelLane
`tobival/model_lane.py` and `core/runtime/eval_live.py` — the live half of the exam. It separates
what the model actually returned from what deterministic recovery rescued afterwards, and the
held-back cases are only ever run once, so a good score cannot come from practising on the answers.

## Proof
The acceptance artifact. The approved live rerun recorded 156 of 156 model responses, raw model
pass 32.05%, deterministic recovery 67.95%, and no provider failures. **The owner accepted it on
2026-08-30**, which is what unblocked the Agent tier work. Production routing is still limited to
narrow, safe workflows with no required fields.

## Rollout
Staged activation with a rollback switch. Each stage needs seven consecutive agreeing comparisons
plus the quality evidence above; one switch returns new work to shadow behaviour without touching
runs that already exist.

## Conductor
`core/conductor.py` — now a **compatibility facade**. It still accepts every argument it always
did, but classification, context assembly, the tool loop, recovery and response composition live in
`core/runtime/` services behind it. Shared by Mission Control Chat and Telegram.

## Brain
`core/brain.py`, the V2 memory services, and the knowledge graph — durable owner memory, retrieval,
review, and the staged context (a cached stable profile plus task-specific retrieval) fed to Chat
and Agent. Brain V2 is now the authoritative path; the legacy Brain UI is still in place.

## Models
`core/model_router.py` — the provider catalog, fallback, streaming, vision routing, and usage
logging across Anthropic, GLM, OpenAI, OpenRouter, DeepSeek, Gemini, Grok, Codex, Ollama, and
custom endpoints.

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

## RunsPage
The Runs pane and its **Evaluations** tab, plus the Health checks that read this history —
including **Health → Infrastructure**, the one-click test that proves the whole engine works on
this machine.

## AgentTier
`core/agent_tier.py` — the seven-ability evidence registry added by #35. An ability counts as
complete only when a real run produced qualifying evidence in the last 24 hours; writing the code
for it grants nothing. Evidence is stored as bounded references, never raw output or secrets.

## Evolution
The Evolution page's Tier II reads that registry and nothing else. Older static ability
definitions remain display labels and can no longer mark an Agent ability complete.

## SQLite
The single embedded database (configurable via `DB_PATH`) holding memory, projects, actions,
runs, usage, and feature tables — plus the canonical `mc_*` runtime and `mc_eval_*` tables.
Additive migrations only, recorded in a shared ledger the Health infrastructure test verifies.

## Files
On-disk project resource files under the database directory: uploads, extracted text, and the
per-project Resources drive. Path traversal is checked and file size is capped.

## Providers
The configured LLM providers the router can reach. Which ones actually work depends on current
keys and provider settings — the Models page is the evidence, not this diagram.

## External
The third-party APIs behind the connected services. Reaching them requires an unlocked vault
credential plus a fresh successful connection test.

## Dispatch
`core/developer_dispatch.py` — when you describe a limitation in ordinary Chat, TOBI proposes
turning it into a Developer work item. The proposal alone changes nothing: no queue row, no
branch, no run.

## Confirm
Nothing is created until you confirm the proposal card in Chat. This is deliberate — describing a
problem out loud must never silently start work.

## Queue
`core/coding_queue_authoring.py` — the confirmed proposal becomes one durable Developer queue item
linked back to the Chat message that asked for it, so status and evidence stay truthful.

## DevControl
The Developer control plane (`core/coding_agent.py` and friends): goal assessment, bounded
sprints, isolated Git worktrees, quality gates, independent review, and a durable runner queue.

## DevDB
The development ledger — the `development_*` and `coding_*` tables holding goals, sessions,
stages, checkpoints, assessments, review evidence, and learning records.

## Worktrees
Each coding run works in its own isolated Git worktree, so an in-progress attempt can never
disturb the checkout you are using.

## Harness
**The default coding worker since 2026-08-30.** `core/coding_workers.py` runs the DeepSeek Harness
in-process on the same typed-tool loop as the built-in worker, using the DeepSeek key from the
Models page. An agent saved with no model still works: it falls back to a DeepSeek model the Models
page reports as usable right now, and if DeepSeek is off, keyless, or has no enabled models, the
error says which of the three it is.

## RunnerQueue
A durable SQLite job queue for the command-line workers, so a coding run survives an API restart
and never executes an external CLI inside the web process.

## RunnerService
`core/coding_runner_service.py` — the separately supervised process that drains that queue, with
encrypted per-job credential envelopes, output events, cancellation, and health reporting.

## CodingCLIs
The Codex and OpenCode command-line workers. Still implemented, but **flag gated**: the default
allowed adapters are the in-process ones, so these run only when the feature is deliberately
switched on.

## Hermes
One-way persona/skill/memory/model-routing sync paths to Hermes state. Multiple mirrors, not a
unified state owner.

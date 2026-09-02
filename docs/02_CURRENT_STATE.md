# Current State

> Verified from the D-drive repository through 2026-08-28. Queue #21 Runtime V2 is complete in committed source. No production activation, deployment, Supabase action, or Vercel action was performed.
>
> TM01 follow-up at source revision `d1a3448`: active docs were compared with current code, tests,
> the live acceptance artifact, queue, and Git history. #34/T08 live proof is complete. Unrelated existing
> worktree changes were preserved and are not treated as #34 evidence. See `DOCUMENTATION_AUDIT.md`.

## TM01 Refresh Snapshot - 2026-08-28

| State | Meaning |
|---|---|
| Verified source | #21 Runtime V2, #33 Infrastructure self-check, and the #34/T08 repair are present through `d1a3448`. The self-contained acceptance CLI now uses a revision-bound D-drive database by default. |
| Local only | Existing changes in `AGENTS.md`, `CLAUDE.md`, `docs/OUTPUT_STYLE_ADHD.md`, `artifacts/`, and `%SystemDrive%/` are unrelated to this refresh and are not delivery evidence. |
| Not verified here | Live integrations, VPS behavior, public deployment, and owner rollout activation. No external service was contacted by this refresh. |
| Freshness | Claims in this file use the 2026-08-28 refresh unless a row explicitly names an older evidence date. |

## Executive Summary

TOBI is now a broad single-owner agent platform, not only the original MMO business loop. The strongest implemented areas are Mission Control, persistent memory, project/task management, conversational tool execution, terminal control, model routing, integrations management, and cross-agent interoperability.

The largest truth gaps are no longer "nothing is built." Chat/Agent mode policy, Tier-1 Awakening evidence, runtime traces, and focused regression suites now exist. The remaining risks are operational hardening: the dashboard API is a large mostly unauthenticated module, legacy and Project-v2 data coexist, external connectors still depend on real authorization and recent test evidence, higher Evolution tiers still use legacy detection, and browser/integration coverage is narrower than the product surface.

## Implemented and Materially Usable

| Area | Current evidence |
|---|---|
| Mission Control shell | React 18 app with 21 top-level destinations, responsive navigation, persistent header tabs, themes, motion, command palette, notifications, and lazy-loaded heavy pages |
| Workspace tabs | Up to five mounted route panes, drag reorder, close/focus, localStorage restore, and one dynamic tab per Project v2 workspace |
| Chat and Agent | Persistent sessions/messages, backend-enforced Chat/Agent modes, hybrid intent routing, typed runtime events/traces, attachments, premium readers, web search, Deep Research, automatic project context, edit/fork, compaction, process checkpoints, persisted Agent runs, run recovery commands, artifacts, action confirmations, terminal output, and cross-session recall. Explicit Developer capability requests produce a no-side-effect proposal; confirmation creates one linked Developer workflow and Chat shows its truthful status and evidence. Runtime tool scopes narrow normal turns for speed but can admit a known safe read tool when the route was too narrow |
| Conductor | Live-data read tools, project/task/goal/resource actions, direct project-resource inventory/read/search, memory writes, integration reads, terminal tools, multi-step tool loop, risk tiers, confirmation cards, and `tobi_actions` audit |
| Brain | Structured memories, categories, confidence, versions, conflicts, import, deduplication, review, semantic retrieval with keyword fallback, decay, and one-way Hermes mirror. Conversation sweeps now use fair per-chat cursors, an owner-token DB lease, durable failed-batch retry, malformed-output recovery, and resolved-payload cleanup |
| Graph | Unified memory/task/project/resource graph, internal and external source sync, search/retrieval, communities, paths, editing, timeline, and saved layout |
| Project v2 | Full-page project workspaces, overview, tasks, goals, resources, activity, custom icons, dependencies, reminders, resource extraction/RAG, graph sync, and Conductor tools. Resources has one upload/link modal, confirmed deletion, link-card menus, preview/navigation, and grounded list/read/search tools |
| Tasks | Standalone task board plus PM-linked tasks, task details, owner-input workflow, notes, commands, high-risk transitions, and audit history |
| Terminal | Full-machine PowerShell/cmd or POSIX shell, Plan/Ask/Accept/Auto modes, low/medium/high risk gate, hard denylist, kill-switch, output redaction, timeouts, background jobs, package installation, and installed-tool registry |
| Premium readers | YouTube URL detection/transcripts with graceful fallback and capped context, explicit model capability checks, and transparent borrowing of an available vision model when the selected model cannot read images |
| Awakening Tier 1 | Central nine-ability evidence registry, `/api/awakening`, guided Evolution/Ability UI, grounded self-report tool, workflow receipts, and reviewed Brain-memory evidence. External Read is active only when the connector is ready and has fresh successful-test evidence (24-hour default). MC startup automatically renews stale GitHub proof from the saved vault credential, while fresh proof skips the network check; Google client credentials remain partial until OAuth and a verified read test complete |
| Runtime diagnostics | Health Performance tab and `performance_doctor` provide Graphify-assisted subsystem scoring, findings, trends, and maintenance-task creation; Chat Runtime v2 records per-stage traces and recovery state |
| Mission Control Runtime V2 | Canonical durable runs, leases, checkpoints, recovery, loops, policy, approvals, tool contracts, receipts, traces, evaluations, System Model, Runs page, staged rollout/rollback, and passive adapters for Projects, Office, CLI, Telegram, and schedulers. All rollout controls default off |
| Coding Agent v2 | Developer goal assessment, bounded sprint contracts, explicit DeepSeek Harness/Codex profiles, portable checkpoints, checkpoint-only worker switching, deterministic quality gates, independent review, encrypted Vault-to-runner credential handoff, supervised service execution, and evidence-backed learning/replay. DeepSeek Harness (added 2026-08-30) drives the in-process typed-tool loop on the DeepSeek API and is qualified alongside Codex CLI; the retired MC Native and OpenCode + GLM agents are hidden from the Agents page but keep their rows so run history still resolves |
| Hermes skill view | Read-only parsing of repository `hermes_skills/*.md` through `/api/hermes/skills`, displayed separately on Ability with execution disabled |
| Model routing | Anthropic, GLM/Z.ai, OpenAI, OpenRouter, DeepSeek, Gemini, Grok, Codex, Ollama, and custom OpenAI-compatible providers; per-task routing, fallback, streaming, vision, and usage logging. DeepSeek (added 2026-08-25) ships the three V4 models with a 1M context, priced in `config/llm_prices.yaml` at peak rates; its key is not set in this checkout, so the provider shows "No key" until the owner adds one |
| Vault and integrations | Encrypted vault, profiles, auto-unlock option, key slots, audit, export/import, live environment injection, and integration management in MC |
| Google connector | OAuth code paths for Drive, Gmail, and Calendar reads are implemented. Credential-stage setup is not treated as verified read access; the OAuth callback must complete and a read test must succeed. Actual availability was not live-tested in this audit |
| Other connectors | Notion and GitHub have read/write methods; Vercel has deployment reads; Supabase has table query/insert methods. Credential rotation/import resets cached test evidence, and actual availability remains configuration- and authorization-dependent |
| MCP and A2A | Inbound MCP server, outbound MCP clients, tool permissions, approvals, OAuth/JWT support, tunnel management, call logs, agent card, peers, and messaging |
| Office V3 and missions | Flagged premium command center with Phaser/static floor, agent dock/detail, mission queue/live SSE controls, embedded context-aware TOBI, confirmed Office mutations, sensitive local artifacts, Office activity, and legacy fallback |
| Explore/News | V1 (live default): news/model/tool/social ingestion, source configuration, scoring, digest, scheduler jobs, News page. News V2 (#23, flag-off behind `news.v2_enabled`/`news.v2_shadow`): `core/news/` evidence ledger with validated contracts, bounded adapters (HN/OpenRouter/GitHub), durable lease/checkpoint refresh jobs, replay-safe interactions with 10s undo, versioned interest profiles, deterministic rank snapshots, `/api/explore/v2` (idempotent mutations, pinned cursors, SSE), four-tab UI (Home/Trending/virtualized Feed/Favorites), deduplicated Inbox alerts on repeated source failures, and 255 checks across seven suites incl. security/perf gates. V1 routes retained for rollback; media fetching pipeline not yet implemented (media renders only if a validated cache row exists); Save-to-Brain returns 501 until #20 acceptance (N11) |
| Storage and usage | Per-feature storage scans, snapshots, usage/cost analytics, plans, budget, call log, dashboard widget, and scheduler jobs |
| Always-on surfaces | `main.py start` runs Telegram polling, both FastAPI services, scheduler jobs, vault startup behavior, and the built Mission Control app |

## Partial, Misleading, or Split

| Area | Honest status |
|---|---|
| Chat modes | The main selector is Chat/Agent. Chat denies terminal capability server-side; Agent enables execution and terminal tools. Legacy Terminal maps to Agent, Research maps to Chat plus web capability, and Project maps to Chat with automatic context. Deep Research is a per-turn capability toggle. Runtime v2 remains flag-controlled for rollback |
| Agent execution | Runs, steps, recovery commands, artifacts, and traces are persisted. Retry/Skip/Revise continues the original run. Completed action checkpoints survive reload and use a compact expandable disclosure. The executor is materially safer but is still evolving from the older prompt-driven Conductor loop |
| Evolution | Tier 1 is an **evidence-based 9-ability registry** surfaced through `/api/evolution` and `/api/awakening`. Active status requires real Brain data, usable connector state, or successful workflow receipts as appropriate. Other tiers still use legacy definitions, so the overall Jarvis percentage is not a complete delivery metric |
| Ability | The page combines curated cards and DB-backed coaching/version flows with a new read-only repository Hermes Skills section. Repository skill availability is live, but execution remains disabled and the curated DB registry is still a separate model |
| Hermes | Persona, skill, memory, and model config sync paths exist, but ownership is split and mostly one-way. TOBI can run without Hermes for many MC features. Older claims that "TOBI is the Hermes daemon" are not true of the current code |
| Project data | Legacy `projects`/business tables coexist with `pm_projects`/Project v2. Some code intentionally bridges them, but the duplicate model increases migration and reporting risk |
| API topology | Port 8080 hosts the built UI, MC APIs, MCP mount, and 259 route handlers in a 6,536-line module. Port 8000 hosts a smaller API-key-protected legacy/external API. Frontend API ownership has begun splitting into domain modules, but backend router extraction remains open |
| Dashboard security | Most port-8080 MC endpoints have no general authentication and CORS allows all origins. Vault/MCP-sensitive operations add vault sessions or MCP auth, but the overall dashboard assumes a trusted single-owner deployment. Public exposure is a material risk |
| Integration status | Code paths or credentials alone are not proof of access. Awakening requires adapter readiness plus fresh successful-test metadata; other surfaces must still use current MC status and an explicit test before claiming availability |
| Personal computer control | Terminal execution is real. Browser automation, screen understanding, GUI control, and a hardened personal-PC service are not implemented |
| Proactivity | Scheduler and Telegram push are real. General event-driven observation and context-aware interruption are not |
| Tests | Focused tracked suites cover the established runtime, security, UI, and compatibility paths. #34/T00 preserves the accepted unchanged-code baseline: ECR `50` and LLM Dependency `85.5769`. The approved T08 rerun executed all 72 cases, including 14 holdouts, through canonical Runtime runs and made 156 bounded Codex subscription calls. All 156 returned; raw model output passed `32.0513%`, deterministic recovery handled `67.9487%`, final ECR is `100`, and scoped LDR is `8.8021`. The artifact has no blocker and reports `release_ready=true`; the owner accepted that exact artifact on 2026-08-30. #35/T02A adds 47 focused Chat-to-Developer checks, including segment-aware request qualification, full owner-context retention, current and legacy Queue authoring, and persisted failed-card retry without duplicate queue work; the shared gate passes 33/33 suites. The dashboard production build and mocked desktop/mobile Playwright owner flow pass. |

## Runtime and Persistence

- Default database: `~/.mmo_agent/agent.db`, configurable with `DB_PATH`.
- Project files: `<database directory>/projects/{project_id}/resources/`.
- Hermes state: `~/.hermes/`, with one-way writes from TOBI.
- Built web application: `dashboard/dist/`, served by `api/dashboard.py`.
- Browser-only preferences: workspace tabs, theme, motion, chat mode, and selected UI options in localStorage.
- The schema is additive and distributed across `core/database.py` plus feature-local lazy initializers. Chat Runtime and Developer/Coding Agent have scoped migration ledgers, but the repository still lacks one migration authority for every subsystem.
- Mission Control Runtime V2 is delivered. It provides validated contracts, immutable redacted run/System history, canonical state, leases, checkpoints, bounded recovery, loops and budgets, policy and approvals, typed tool catalogs and first tool executors, receipts, traces, evaluations, security gates, a System Model, the Runs page, seven-pass staged activation, one-switch rollback, and compatibility adapters for Projects, Office, CLI, Telegram, and schedulers. Direct plain-text Chat is the only implemented canonical execution path; other adapters are passive and keep existing execution as rollback. All owner rollout flags remain off unless explicitly activated. See `docs/RUNTIME_V2.md`.

## Current Queue Reality

- #1 through #12 are recorded as delivered, although several have known follow-ups.
- #13 Theme v2 is in owner-review/in-progress state.
- #14 Premium Ability is delivered at v1, including the follow-up vision-model borrowing and Ability reorganization.
- #16 Chat Mode Backend Upgrade is delivered. #17 Awakening Tier 1 Completion reached owner-runtime acceptance at 9/9 on 2026-07-14 through a successful GitHub read verification, advancing Evolution to the Agent tier. Connector health still follows the 24-hour evidence-freshness rule, but stale GitHub proof is now renewed automatically at MC startup so restarts do not require the owner to press Test again. #19 Performance "System Doctor" is delivered (v1).
- #15 Office V3 is delivered at v1 with owner visual acceptance still open.
- #18 TOBI Coding Agent v1 remains the base continuous goal/lease/worktree/review/deployment system. #22 Coding Agent V2 is qualified for the Codex-only path; its target-VPS soak remains a deployment gate. #21 Mission Control Infrastructure V2, #33 Infrastructure self-check, and #34 TOBIval are complete. #34 owner acceptance is bound to the exact live-proof artifact. For #35 Agent Tier Completion, the owner accepted T00's exact baseline for production revision `fc4d6d7`, dataset `17dda4f3...`, and artifact `9cddb15a...`. T01 installs the evidence registry, T02 qualifies bounded local Agent workflows, and T02A implements confirmed Chat-to-Developer dispatch with durable links and evidence. T02A owner live verification remains, so item #35 and Tier II are not complete. The separately delivered DeepSeek Harness remains outside #35 and its files were not modified or staged. Legacy deletion is explicitly deferred to a separate owner-approved exit review.
- Original plans remain under `feature-idea-queue/`; they are requirements history, not proof of current behavior.

## Highest-Risk Gaps

1. Secure or constrain the port-8080 dashboard before treating it as safely internet-accessible.
2. #34 now has canonical live proof and a scoped LDR of `8.8021`. The model alone passed `32.0513%`
   of attempts and deterministic recovery completed the rest. The remaining #34 decision is owner
   acceptance of the Runs -> Evaluations presentation; broad typed Chat/Agent workflow activation is
   still outside this package.
3. Complete the typed/checkpointed Chat Runtime v2 rollout and keep provider, tool, recovery, and context contracts measurable.
4. Qualify #35's five workflow families so the new Agent registry can replace its correct 0/7 starting state with current production evidence.
5. Keep curated Ability tables, repository skill metadata, Runtime evidence, and Hermes state separate unless a later package defines an explicit shared owner.
6. Add integration, migration, concurrency, and browser-level regression tests around the highest-value workflows.
7. Reduce ownership and change-collision risk in `api/dashboard.py`, frontend API aggregation, and the dual project models.

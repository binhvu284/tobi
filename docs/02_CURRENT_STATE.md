# Current State

> Verified from the D-drive repository on 2026-07-17. This refresh used Graphify-guided navigation plus focused source inspection, Coding Agent v2 (`46/46`), Coding Agent regression (`41/41`), production invariants (`14/14`), Developer recovery checks, Python compilation, and a live isolated supervised acceptance run. Real Codex and OpenCode/GLM 5.2 workers completed bounded sprints, resumed after runner restart, switched at a checkpoint, and recovered safely after forced runner loss. No GitHub mutation, deployment, Supabase action, or Vercel action was performed.

## Executive Summary

TOBI is now a broad single-owner agent platform, not only the original MMO business loop. The strongest implemented areas are Mission Control, persistent memory, project/task management, conversational tool execution, terminal control, model routing, integrations management, and cross-agent interoperability.

The largest truth gaps are no longer "nothing is built." Chat/Agent mode policy, Tier-1 Awakening evidence, runtime traces, and focused regression suites now exist. The remaining risks are operational hardening: the dashboard API is a large mostly unauthenticated module, legacy and Project-v2 data coexist, external connectors still depend on real authorization and recent test evidence, higher Evolution tiers still use legacy detection, and browser/integration coverage is narrower than the product surface.

## Implemented and Materially Usable

| Area | Current evidence |
|---|---|
| Mission Control shell | React 18 app with 21 top-level destinations, responsive navigation, persistent header tabs, themes, motion, command palette, notifications, and lazy-loaded heavy pages |
| Workspace tabs | Up to five mounted route panes, drag reorder, close/focus, localStorage restore, and one dynamic tab per Project v2 workspace |
| Chat and Agent | Persistent sessions/messages, backend-enforced Chat/Agent modes, hybrid intent routing, typed runtime events/traces, attachments, premium readers, web search, Deep Research, automatic project context, edit/fork, compaction, process checkpoints, persisted Agent runs, run recovery commands, artifacts, action confirmations, terminal output, and cross-session recall. Runtime tool scopes narrow normal turns for speed but can admit a known safe read tool when the route was too narrow |
| Conductor | Live-data read tools, project/task/goal/resource actions, direct project-resource inventory/read/search, memory writes, integration reads, terminal tools, multi-step tool loop, risk tiers, confirmation cards, and `tobi_actions` audit |
| Brain | Structured memories, categories, confidence, versions, conflicts, import, deduplication, review, semantic retrieval with keyword fallback, decay, and one-way Hermes mirror. Conversation sweeps now use fair per-chat cursors, an owner-token DB lease, durable failed-batch retry, malformed-output recovery, and resolved-payload cleanup |
| Graph | Unified memory/task/project/resource graph, internal and external source sync, search/retrieval, communities, paths, editing, timeline, and saved layout |
| Project v2 | Full-page project workspaces, overview, tasks, goals, resources, activity, custom icons, dependencies, reminders, resource extraction/RAG, graph sync, and Conductor tools. Resources has one upload/link modal, confirmed deletion, link-card menus, preview/navigation, and grounded list/read/search tools |
| Tasks | Standalone task board plus PM-linked tasks, task details, owner-input workflow, notes, commands, high-risk transitions, and audit history |
| Terminal | Full-machine PowerShell/cmd or POSIX shell, Plan/Ask/Accept/Auto modes, low/medium/high risk gate, hard denylist, kill-switch, output redaction, timeouts, background jobs, package installation, and installed-tool registry |
| Premium readers | YouTube URL detection/transcripts with graceful fallback and capped context, explicit model capability checks, and transparent borrowing of an available vision model when the selected model cannot read images |
| Awakening Tier 1 | Central nine-ability evidence registry, `/api/awakening`, guided Evolution/Ability UI, grounded self-report tool, workflow receipts, and reviewed Brain-memory evidence. External Read is active only when the connector is ready and has fresh successful-test evidence (24-hour default); Google client credentials remain partial until OAuth and a verified read test complete |
| Runtime diagnostics | Health Performance tab and `performance_doctor` provide Graphify-assisted subsystem scoring, findings, trends, and maintenance-task creation; Chat Runtime v2 records per-stage traces and recovery state |
| Coding Agent v2 | Developer goal assessment, bounded sprint contracts, explicit MC Native/Codex/OpenCode profiles, portable checkpoints, checkpoint-only worker switching, deterministic quality gates, independent review, encrypted Vault-to-runner credential handoff, supervised service execution, and evidence-backed learning/replay |
| Hermes skill view | Read-only parsing of repository `hermes_skills/*.md` through `/api/hermes/skills`, displayed separately on Ability with execution disabled |
| Model routing | Anthropic, GLM/Z.ai, OpenAI, OpenRouter, Gemini, Grok, Codex, Ollama, and custom OpenAI-compatible providers; per-task routing, fallback, streaming, vision, and usage logging |
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
| Tests | Focused tracked script suites cover terminal safety, storage/usage, Premium readers, Chat modes/runtime/routes, mode enforcement, network guards, Conductor final guards, Performance Doctor, Office V3, Awakening, project resources, and Coding Agent v1/v2 production invariants. Coding Agent v2 now also has live local Codex/OpenCode supervised acceptance. Browser visual regression, broad live integrations, target-VPS soak, and broad end-to-end behavior remain incomplete |

## Runtime and Persistence

- Default database: `~/.mmo_agent/agent.db`, configurable with `DB_PATH`.
- Project files: `<database directory>/projects/{project_id}/resources/`.
- Hermes state: `~/.hermes/`, with one-way writes from TOBI.
- Built web application: `dashboard/dist/`, served by `api/dashboard.py`.
- Browser-only preferences: workspace tabs, theme, motion, chat mode, and selected UI options in localStorage.
- The schema is additive and distributed across `core/database.py` plus feature-local lazy initializers. Chat Runtime and Developer/Coding Agent have scoped migration ledgers, but the repository still lacks one migration authority for every subsystem.
- Mission Control Runtime V2 now has dormant local foundations: immutable ordered run/System change events, secret-redacted payloads, deterministic projections, canonical run/plan records, immutable effective loop-policy snapshots, legal version-checked states, exclusive expiring step leases, append-only restart checkpoints, bounded delayed retries, typed failure records, one-way recovery commands, same-run cancellation fencing, persisted loop iterations, exact-once usage totals, evidence-backed completion, lower-wins hard limits, one-winner action reservations, immutable receipts, completed replay, and applied/not-applied/unknown crash reconciliation. Chat and Agent now call the canonical gateway only when Runtime V2 events are enabled, recording sanitized requests and lifecycle observations in shadow mode while the legacy route remains authoritative. Agent recovery reuses the linked canonical run, slow acceptance adds at most a 100 ms route wait, canonical IDs stay server-side, and both rollout flags remain off by default.

## Current Queue Reality

- #1 through #12 are recorded as delivered, although several have known follow-ups.
- #13 Theme v2 is in owner-review/in-progress state.
- #14 Premium Ability is delivered at v1, including the follow-up vision-model borrowing and Ability reorganization.
- #16 Chat Mode Backend Upgrade is delivered. #17 Awakening Tier 1 Completion reached owner-runtime acceptance at 9/9 on 2026-07-14 through a successful GitHub read verification, advancing Evolution to the Agent tier; connector health still follows the 24-hour evidence-freshness rule. #19 Performance "System Doctor" is delivered (v1).
- #15 Office V3 is delivered at v1 with owner visual acceptance still open.
- #18 TOBI Coding Agent v1 remains the base continuous goal/lease/worktree/review/deployment system. #22 Coding Agent V2 is qualified for the Codex-only path; its target-VPS soak remains a deployment gate. #21 is in progress: T00-T03 and T04 Runs 1-2 are delivered; Run 3 next adds canonical event replay/reconnect.
- Original plans remain under `feature-idea-queue/`; they are requirements history, not proof of current behavior.

## Highest-Risk Gaps

1. Secure or constrain the port-8080 dashboard before treating it as safely internet-accessible.
2. Complete the typed/checkpointed Chat Runtime v2 rollout and keep provider, tool, recovery, and context contracts measurable.
3. Extend evidence-based Evolution beyond Awakening without weakening the Tier-1 evidence gates.
4. Reconcile curated Ability tables, repository skill metadata, runtime Hermes state, and future Agent-tier capabilities into one explicit ownership model.
5. Add integration, migration, concurrency, and browser-level regression tests around the highest-value workflows.
6. Reduce ownership and change-collision risk in `api/dashboard.py`, frontend API aggregation, and the dual project models.

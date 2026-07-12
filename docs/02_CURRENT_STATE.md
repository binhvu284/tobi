# Current State

> Verified from the D-drive repository on 2026-07-11 through commit `389c151`. This is a code inspection, not a live integration or credential test. Configuration-dependent capabilities are labeled accordingly.

## Executive Summary

TOBI is now a broad single-owner agent platform, not only the original MMO business loop. The strongest implemented areas are Mission Control, persistent memory, project/task management, conversational tool execution, terminal control, model routing, integrations management, and cross-agent interoperability.

The largest truth gaps are no longer "nothing is built." They are alignment and hardening problems: Chat modes do not yet define distinct backend policy, Evolution reports from an outdated ability registry, Ability's curated registry and read-only repository skill view remain separate, the dashboard API is a large mostly unauthenticated monolith, and automated test coverage is narrow relative to the surface area.

## Implemented and Materially Usable

| Area | Current evidence |
|---|---|
| Mission Control shell | React 18 app with 20 top-level destinations, responsive navigation, persistent header tabs, themes, motion, command palette, notifications, and lazy-loaded heavy pages |
| Workspace tabs | Up to five mounted route panes, drag reorder, close/focus, localStorage restore, and one dynamic tab per Project v2 workspace |
| Chat | Persistent sessions/messages, streaming, model selection, attachments, YouTube transcript reading, image-model auto-borrow, web-search opt-in, edit/fork, compaction, feedback, process timeline, action confirmations, terminal output, and cross-session conversation recall |
| Conductor | Live-data read tools, project/task/goal/resource actions, memory writes, integration reads, terminal tools, multi-step tool loop, risk tiers, confirmation cards, and `tobi_actions` audit |
| Brain | Structured memories, categories, confidence, versions, conflicts, import, deduplication, review, semantic retrieval with keyword fallback, sweeps, decay, and one-way Hermes mirror |
| Graph | Unified memory/task/project/resource graph, internal and external source sync, search/retrieval, communities, paths, editing, timeline, and saved layout |
| Project v2 | Full-page project workspaces, overview, tasks, goals, resources, activity, custom icons, dependencies, reminders, resource extraction/RAG, graph sync, and Conductor tools |
| Tasks | Standalone task board plus PM-linked tasks, task details, owner-input workflow, notes, commands, high-risk transitions, and audit history |
| Terminal | Full-machine PowerShell/cmd or POSIX shell, Plan/Ask/Accept/Auto modes, low/medium/high risk gate, hard denylist, kill-switch, output redaction, timeouts, background jobs, package installation, and installed-tool registry |
| Premium readers | YouTube URL detection/transcripts with graceful fallback and capped context, explicit model capability checks, and transparent borrowing of an available vision model when the selected model cannot read images |
| Hermes skill view | Read-only parsing of repository `hermes_skills/*.md` through `/api/hermes/skills`, displayed separately on Ability with execution disabled |
| Model routing | Anthropic, GLM/Z.ai, OpenAI, OpenRouter, Gemini, Grok, Codex, Ollama, and custom OpenAI-compatible providers; per-task routing, fallback, streaming, vision, and usage logging |
| Vault and integrations | Encrypted vault, profiles, auto-unlock option, key slots, audit, export/import, live environment injection, and integration management in MC |
| Google connector | OAuth code paths for Drive, Gmail, and Calendar reads are implemented. Actual availability depends on configured credentials and was not live-tested in this audit |
| Other connectors | Notion and GitHub have read/write methods; Vercel has deployment reads; Supabase has table query/insert methods. Actual availability remains configuration-dependent |
| MCP and A2A | Inbound MCP server, outbound MCP clients, tool permissions, approvals, OAuth/JWT support, tunnel management, call logs, agent card, peers, and messaging |
| Office and missions | Agent registry, workflows, missions, streaming mission events, Phaser office visualization, and control surfaces |
| Explore/News | News, model, tool, and social ingestion; source configuration; scoring; digest; scheduler jobs; News page |
| Storage and usage | Per-feature storage scans, snapshots, usage/cost analytics, plans, budget, call log, dashboard widget, and scheduler jobs |
| Always-on surfaces | `main.py start` runs Telegram polling, both FastAPI services, scheduler jobs, vault startup behavior, and the built Mission Control app |

## Partial, Misleading, or Split

| Area | Honest status |
|---|---|
| Chat modes | `Chat`, `Agent`, `Terminal`, `Research`, and `Project` are selected and persisted in the frontend. Research enables web search and Terminal exposes terminal UI, but the backend request contract does not yet enforce a centralized mode/capability policy. Queue item #16 plans this change |
| Evolution | Tier 1 (Awakening) is now an **evidence-based 9-ability registry** (`core/awakening.py`) surfaced at `/api/evolution` (Tier 1 only) + `/api/awakening`: each ability reports `active/partial/setup_needed/inactive` from real Brain/Conductor/Integrations/Tasks evidence, and Tier 1 reaches 100% only when all 9 are genuinely active (never hardcoded). Other tiers still use the legacy `_TIER_DEFINITIONS`/`_detect_abilities()` bool detector, so the overall Jarvis percentage is still not a full product-completion metric (#17) |
| Ability | The page combines curated cards and DB-backed coaching/version flows with a new read-only repository Hermes Skills section. Repository skill availability is live, but execution remains disabled and the curated DB registry is still a separate model |
| Hermes | Persona, skill, memory, and model config sync paths exist, but ownership is split and mostly one-way. TOBI can run without Hermes for many MC features. Older claims that "TOBI is the Hermes daemon" are not true of the current code |
| Project data | Legacy `projects`/business tables coexist with `pm_projects`/Project v2. Some code intentionally bridges them, but the duplicate model increases migration and reporting risk |
| API topology | Port 8080 hosts the built UI, MC APIs, MCP mount, and 238 route handlers in one 5,700+ line module. Port 8000 hosts a smaller API-key-protected legacy/external API |
| Dashboard security | Most port-8080 MC endpoints have no general authentication and CORS allows all origins. Vault/MCP-sensitive operations add vault sessions or MCP auth, but the overall dashboard assumes a trusted single-owner deployment. Public exposure is a material risk |
| Integration status | Code paths exist, but no claim that an external service is connected should be made without its current MC status/test result |
| Personal computer control | Terminal execution is real. Browser automation, screen understanding, GUI control, and a hardened personal-PC service are not implemented |
| Proactivity | Scheduler and Telegram push are real. General event-driven observation and context-aware interruption are not |
| Tests | Tracked script suites cover terminal safety, storage/usage, and Premium readers/Hermes parsing. Many API, UI, integration, migration, and cross-system paths still rely on manual or one-off verification |

## Runtime and Persistence

- Default database: `~/.mmo_agent/agent.db`, configurable with `DB_PATH`.
- Project files: `<database directory>/projects/{project_id}/resources/`.
- Hermes state: `~/.hermes/`, with one-way writes from TOBI.
- Built web application: `dashboard/dist/`, served by `api/dashboard.py`.
- Browser-only preferences: workspace tabs, theme, motion, chat mode, and selected UI options in localStorage.
- The schema is additive and distributed across `core/database.py` plus feature-local lazy initializers. Static inspection finds 70 table names.

## Current Queue Reality

- #1 through #12 are recorded as delivered, although several have known follow-ups.
- #13 Theme v2 is in owner-review/in-progress state.
- #14 Premium Ability is delivered at v1, including the follow-up vision-model borrowing and Ability reorganization.
- #16 Chat Mode Backend Upgrade and #17 Awakening Tier 1 Completion are delivered (v1); #19 Performance "System Doctor" is delivered (v1).
- #15 Office V3 and #18 TOBI Coding Agent remain queued.
- Original plans remain under `feature-idea-queue/`; they are requirements history, not proof of current behavior.

## Highest-Risk Gaps

1. Secure or constrain the port-8080 dashboard before treating it as safely internet-accessible.
2. Centralize Chat/Agent capability policy so frontend labels cannot diverge from backend permissions.
3. Replace Evolution's stale registry with evidence from real subsystems.
4. Reconcile the curated Ability tables, read-only repository skill registry, and runtime Hermes state into one explicit ownership model.
5. Add integration, API, migration, and browser-level regression tests around the highest-value workflows.
6. Reduce the ownership and change-collision risk in `api/dashboard.py` and the dual project models.

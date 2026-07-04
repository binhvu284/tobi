# 02 — Current State (Honest Inventory)

> **Rule for this document: report what the code actually does, real vs. stub — not the aspirational framing from the dashboard.** Its entire value to a future agent is honesty.
>
> Last refreshed **2026-07-04**, after queue feature #10 (Storage & Usage) shipped. The feature
> queue's per-feature build notes live in [`feature-idea-queue/QUEUE.md`](feature-idea-queue/QUEUE.md).

## Architecture map

Every message/flow travels through these components:

| Layer | File(s) | What it is |
|-------|---------|-----------|
| Orchestrator | `main.py` | Entry point + scheduler. Run modes: `start` (full system), `bot`, `api`, `research`, `execute`, `ceo`, `status`, `test`, `terminal`. |
| Persona sync | `main.py` (`sync_soul_and_skills`) | Copies `SOUL.md` → `~/.hermes/SOUL.md` and `hermes_skills/*.md` → `~/.hermes/skills/tobi/` on startup. |
| Model router | `core/model_router.py` | **7-provider registry** (Anthropic native + OpenAI/OpenRouter/Gemini/Grok/Ollama/custom) with vault-backed keys, default + per-task overrides + ordered fallback (`llm_config` table), streaming, vision, and **auto-logging of every call** to `llm_usage`. Legacy `PRIMARY_MODEL` env still honored. |
| Conductor | `core/conductor.py` | **The conversational command engine** (queue #7): classifier pre-route → memory-first grounding → provider-agnostic JSON tool-loop. 12 read tools + 8 act tools with **tiered risk** (low/medium auto-execute; high = propose → owner confirms), `tobi_actions` audit, butler EN/VN voice, shared by MC chat + Telegram (Telegram capped at read + low-risk). |
| Second brain | `core/brain.py`, `core/embeddings.py` | Long-term owner memory (queue #1): 8-category vault, import/dedup/review, **Telegram auto-learn sweep**, confidence decay, semantic search (fastembed, keyword fallback), one-way Hermes mirror, GraphRAG `owner_context`. |
| Knowledge graph | `core/graph_engine.py` | Obsidian-style graph (queue #2): unified `graph_nodes`/`graph_edges` over memories/tasks/projects + Notion/GitHub mirrors, ref/tag/semantic edges, communities, 45-min sync job. |
| Task classifier | `core/task_classifier.py` | Pure-regex router (no LLM): `SMALLTALK / CODING / RESEARCH / STATUS / EXECUTION / QUESTION`. |
| Telegram UI | `core/telegram_bot.py` | Telegram bot: chat (STATUS/QUESTION routed through the Conductor), `/commands`, inline approval buttons, the sandboxed coding agent, terminal session. |
| Chat store | `core/chat_store.py`, `core/attachments.py` | Premium Chat (queue #8): DB sessions/messages, per-session model, edit→branch forking, compaction; file/image/PDF attachments with native vision. |
| Secrets vault | `core/vault.py`, `core/integrations_registry.py` | Genesis vault (queue #4): scrypt→AES-256-GCM encrypted secrets, `/integrations` page, connect-tests keys and injects `os.environ` live, audit log, profiles, encrypted export/import. |
| MCP hub | `core/mcp_server.py`, `core/mcp_client.py`, `core/mcp_security.py`, `core/a2a.py`, `core/mcp_tunnel.py` | Queue #5: TOBI as MCP **server** (FastMCP at `/mcp`, bearer + OAuth 2.1 JWT, scopes, approval queue) and **client** (multi-transport, per-tool allow/ask/deny), A2A agent card + peers, cloudflared tunnel. |
| Research | `core/research_engine.py` | Tavily web search → LLM niche scoring → business-plan generation. |
| Execution | `core/project_executor.py`, `core/office.py`, `core/office_stream.py` | Runs agent tasks per project; the Office mission engine streams per-step deltas to the Phaser office UI. |
| CEO loop | `core/ceo_loop.py` | Monthly portfolio review, ROI, strategy update, lessons. |
| Storage & usage analytics | `core/storage_scan.py`, `core/usage_meter.py`, `core/usage.py` | Queue #10: per-table + filesystem storage scans → `storage_snapshots` (growth history), price table (`config/llm_prices.yaml` → `llm_prices`), range-aware spend analytics, plans + monthly budget with in-app alerts. `/storage` page. |
| Database | `core/database.py` | SQLite, **~55 tables** across the business core (`projects, tasks, revenue, lessons, strategy, reports, conversations`) + PM system (`pm_*`), Brain (`brain_*`), Graph (`graph_*`), vault (`vault_*`), MCP (`mcp_*`), chat (`chat_*`), skills, office/missions, usage/storage analytics. |
| Integrations | `core/integrations.py` | Notion, GitHub, Google, Vercel, Supabase connectors (key-gated; see below). |
| API + UI | `api/server.py`, `api/dashboard.py`, `dashboard/` | FastAPI REST API + the React **Mission Control** (18+ routes: Dashboard, Chat, Brain, Graph, Office, Projects/Tasks, Actions, Integrations, MCP, Models, Storage, Health, Evolution…) with an 8-theme system and a site-wide motion pass (queue #6). |

DB path: `~/.mmo_agent/agent.db` by default (`DB_PATH` env var).

## What genuinely works today

- **Conversational command of Mission Control** (queue #7/#8): both MC chat and Telegram route through the Conductor — ask about evolution/agents/projects/health, create projects/tasks, run high-risk actions via Confirm/Cancel cards, all grounded in live DB reads and audited in `tobi_actions`.
- **A real owner memory**: the Brain auto-learns durable facts from chat (30-min sweep), supports import/review/dedup, decays stale confidence daily, and is consulted memory-first by chat and the task engines.
- **The full business loop**: research cycle → proposals to Telegram with ✅/❌/✏️ buttons → executor runs tasks every 6h → monthly CEO review → lessons feed back. All wired in `main.py`'s scheduler.
- **Premium chat**: multi-provider model picker, streaming with visible thinking/progress phases, attachments + vision, web-research toggle, edit→branch, session compaction, full-width rich blocks.
- **Encrypted secrets**: keys live in the Genesis vault, injected into `os.environ` on unlock/boot; integrations connect/test/reveal from the `/integrations` page without restarts.
- **Cross-agent interop**: MCP server + client with security (scopes, rate limits, approvals, kill-switch) and A2A discovery/messaging.
- **Cost & storage visibility** (queue #10): every LLM call logs tokens/cost/latency tagged by surface; `/storage` shows what's eating disk and where dollars go, with plans, budget alerts, and Conductor queries ("what's eating my storage?").
- **Scheduler** (`schedule` library, Vietnam GMT+7): daily 08:00 report; 6-hourly execution; Sunday 20:00 research + reflection; brain sweep 30m + decay 04:00; graph sync 45m; storage scans (db hourly, fs daily 04:30); monthly CEO review.
- **REST API** (`api/server.py`) with API-key auth, plus the full dashboard API in `api/dashboard.py`.

## The coding agent — stated honestly

`core/telegram_bot.py` (`_CODING_TOOLS`, `_execute_tool`, `_run_coding_agent`) runs a Claude `tool_use` loop with four tools: `write_file`, `read_file`, `run_bash`, `list_files`.

**It is deliberately confined:**
- File writes are forced to stay inside `PROJECT_DIR` (path normalized, rejected if it escapes).
- `run_bash` runs with `cwd=PROJECT_DIR`, a 30s timeout, and a denylist `_BLOCKED_CMDS`.
- Requires `ANTHROPIC_API_KEY`; without it, falls back to a plain (no-tools) LLM completion.

This is still **the only shell/filesystem control that exists, and it is sandboxed to the project directory.** The upgrade to a real, tiered-permission, full-machine terminal engine is **specced but not built** — queue **#11 TOBI CLI** ([spec](feature-idea-queue/TOBI_CLI_SPEC.md)). Note the *Conductor's* tiered risk model (low/med/high + confirm) **is** built — but it governs MC actions (projects/tasks/missions), not shell access.

## Integrations — reality vs. badges

`core/integrations.py` defines connectors for **Notion, GitHub, Google, Vercel, Supabase**, key-gated via `is_available()`. Since Genesis (queue #4), keys are stored encrypted in the vault, injected live on unlock, and each integration can be connect-tested from `/integrations` — the page's status chips reflect real `test()` calls, and boot auto-connect re-injects cached secrets.

- **Google is still a stub** for Drive/Gmail reading (`read_drive` reports this honestly); its connector test is a placeholder.
- Notion / GitHub / Vercel / Supabase have real REST calls when their keys are configured; the Conductor's `read_notion` / `read_github` tools work against them.
- The honest availability is whatever `core.integrations.check_all()` returns given the currently configured keys — run `python main.py test`.

## Memory — reality

This section used to say "no structured, self-updating model of the owner." **That is no longer true.** What exists now:

- `brain_memories` + categories/versions/conflicts: a structured, confidence-scored owner memory with auto-learn (Telegram sweep), manual `/remember`, import pipelines, review queues, and daily confidence decay.
- **Memory-first retrieval is real**: the Conductor grounds every answer in a profile pass; research/execute/CEO consult task-level memory first; GraphRAG `owner_context` feeds retrieval.
- `conversations` = chat history; `lessons` = outcome self-reflection — both still present and feeding the above.
- `SOUL.md` remains the hand-written persona layer, synced to `~/.hermes/`; freshly-learned memories mirror one-way into Hermes.

Remaining honest gaps: the psychology-profile depth is shallow (facts more than models of mood/intent), and the app↔Hermes memory unification is one-way mirror, not one store.

## Hermes status

- Hermes was configured on **2026-05-27**; `main.py` syncs `SOUL.md` + skills into `~/.hermes/` on startup, the Brain mirrors memories one-way, and `core/hermes_sync.py` pushes LLM routing config one-way on save.
- **The custom Python app and the Hermes runtime remain two loosely-coupled layers.** The `HERMES_*.md` guides still assume a **VPS**, which conflicts with the personal-PC runtime target (see [roadmap](03_ROADMAP.md)) — treat the VPS setup as a migration item.

## Bottom line

Measured as an **autonomous MMO-business agent**, this is a substantially complete system. Measured against the **Jarvis vision**: the owner-model pillar has genuinely moved (Brain + Conductor + memory-first grounding), the always-on plumbing is solid, and **real computer control is still the big gap** — the shell is sandboxed to one directory until queue #11 ships.

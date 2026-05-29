# 02 — Current State (Honest Inventory)

> **Rule for this document: report what the code actually does, real vs. stub — not the aspirational framing from the dashboard.** Its entire value to a future agent is honesty.

## Architecture map

Every message/flow travels through these components:

| Layer | File(s) | What it is |
|-------|---------|-----------|
| Orchestrator | `main.py` | Entry point + scheduler. Run modes: `start` (full system), `bot`, `api`, `research`, `execute`, `ceo`, `status`, `test`, `terminal`. |
| Persona sync | `main.py` (`sync_soul_and_skills`) | Copies `SOUL.md` → `~/.hermes/SOUL.md` and `hermes_skills/*.md` → `~/.hermes/skills/tobi/` on startup. |
| Model router | `core/model_router.py` | `PRIMARY_MODEL` = `openrouter` (free models) \| `claude` \| `auto`. Rate-limit fallback to a secondary OpenRouter model. |
| Task classifier | `core/task_classifier.py` | Pure-regex router (no LLM): `SMALLTALK / CODING / RESEARCH / STATUS / EXECUTION / QUESTION`. |
| Primary UI | `core/telegram_bot.py` | Telegram bot: chat, `/commands`, inline approval buttons, the coding agent, terminal session. |
| Research | `core/research_engine.py` | Tavily web search → LLM niche scoring → business-plan generation. |
| Execution | `core/project_executor.py` | Runs agent tasks per project, updates progress, flags human tasks. |
| CEO loop | `core/ceo_loop.py` | Monthly portfolio review, ROI, strategy update, lessons. |
| Database | `core/database.py` | SQLite, 7 tables: `projects, tasks, revenue, lessons, strategy, reports, conversations`. |
| Integrations | `core/integrations.py` | Notion, GitHub, Google, Vercel, Supabase connectors. |
| API + UI | `api/server.py`, `api/dashboard.py`, `dashboard/` | FastAPI REST API + React dashboard. |

DB path: `~/.mmo_agent/agent.db` by default (`DB_PATH` env var), though a copy exists at `.tobi/agent.db` in the repo.

## What genuinely works today

- **Conversational Telegram bot** with persistent history (`conversations` table; in-memory + DB-backed, last ~50 msgs/chat). Authorization gated to `TELEGRAM_ALLOWED_USERS`.
- **Fast regex routing** before any LLM call, with a SMALLTALK fast-path on a lightweight model.
- **Multi-model routing** with task-type → model mapping and a rate-limit fallback path.
- **The full business loop**: research cycle → business-plan proposals sent to Telegram with ✅/❌/✏️ inline buttons → on approve, project goes active → executor runs tasks every 6h → monthly CEO review → lessons saved. All wired in `main.py`'s scheduler.
- **Scheduler** (`schedule` library, Vietnam GMT+7): daily 08:00 report; every 6h execution; Sunday 20:00 research + weekly self-reflection; monthly (1st) CEO review.
- **Terminal mode** (`python main.py terminal`) for local interactive chat.
- **REST API** (`api/server.py`) with API-key auth for status/projects/lessons/task/research/revenue/approve/reject.

## The coding agent — stated honestly

`core/telegram_bot.py` (`_CODING_TOOLS`, `_execute_tool`, `_run_coding_agent`, roughly lines 120–280) runs a Claude `tool_use` loop with four tools: `write_file`, `read_file`, `run_bash`, `list_files`.

**It is deliberately confined:**
- File writes are forced to stay inside `PROJECT_DIR` (path is normalized and rejected if it escapes the project root).
- `run_bash` runs with `cwd=PROJECT_DIR`, a 30s timeout, and a denylist `_BLOCKED_CMDS` (e.g. `rm -rf /`, `sudo rm`, fork bombs).
- Requires `ANTHROPIC_API_KEY`; without it, falls back to a plain (no-tools) LLM completion.

This is essentially **the only "PC control" that exists today, and it is sandboxed to the project directory.** It is far from "do anything a PC can do."

## Integrations — reality vs. badges

`core/integrations.py` defines connectors for **Notion, GitHub, Google, Vercel, Supabase**. They are **API-key-gated**: `is_available()` returns true only when the relevant key/URL env vars are set.

- **Google is a stub.** `GoogleIntegration.test()` always returns `False` with a "Phase 2: implement OAuth" comment (≈ lines 173–184). It is a placeholder, not a working integration.
- Notion / GitHub / Vercel / Supabase have real REST calls, but only function when their keys are configured.
- **Do not trust the dashboard's "● Active" badges** in `dashboard/src/pages/Ability.tsx` — those are aspirational/marketing labels. The honest availability is whatever `core.integrations.check_all()` returns given the *currently configured* keys. Run `python main.py test` to see the live count.

## Memory — reality

What exists today is **not yet a learned user model**:
- `conversations` table = recent chat history per chat_id.
- `lessons` table = self-reflection + outcomes from cycles (success/failure/insight/warning).
- `SOUL.md` = a **static, hand-written** persona/preferences file, synced to `~/.hermes/`.
- Hermes provides its own persistent memory layer alongside this.

There is no structured profile that Tobi updates about its owner automatically. Understanding of the user is approximated, not modeled.

## Hermes status

- Per the project memory index, Hermes was configured on **2026-05-27** (API keys, fallback model, timezone, memory limits, cron jobs, custom personality, skill bundle, external dirs). See `HERMES_*.md` for setup/troubleshooting/cost guides.
- `main.py` bridges the two worlds by syncing `SOUL.md` and `hermes_skills/*.md` into `~/.hermes/` on startup.
- **The custom Python app and the Hermes runtime are two loosely-coupled layers.** They share persona/skills via file sync, but are not yet a single integrated agent. The `HERMES_*.md` guides also assume a **VPS** deployment, which conflicts with the personal-PC runtime target (see [roadmap](03_ROADMAP.md)).

## Bottom line

Measured as an **autonomous MMO-business agent**, this is a substantially complete system. Measured against the **Jarvis vision** (deep user model, full PC control, proactive always-on personal presence), it is early — strong on the always-on plumbing, thin on the user model, and barely started on real computer control.

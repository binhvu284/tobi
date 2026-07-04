# 03 — Roadmap: Progress Toward the Jarvis End-State

> All percentages are **estimates measured against the Jarvis vision** (not the MMO-agent goal), and each is tied to evidence already in the repo. They are meant to be honest and revisable, not precise.
>
> Last refreshed **2026-07-04**, after queue features #1–#8 and #10 shipped (see
> [`feature-idea-queue/QUEUE.md`](feature-idea-queue/QUEUE.md) for what each delivered).

## Headline: Jarvis-readiness ≈ **40%**

A weighted blend of the three pillars below (Understand ~55% · PC control ~20% · Always-on ~45%, weighted roughly evenly). Up from the ~25% of the previous revision: the owner-model pillar moved the most (the Brain, Conductor grounding, and auto-learning are real now). The number that still holds the headline down is **PC control** — a Jarvis can drive the machine, and Tobi still can't beyond one sandboxed directory.

> ⚠️ This reflects the **Jarvis denominator**. Measured against the *MMO-business-agent* goal instead, the same code is ~80% complete (see the [Business engine](#business-engine--bonus-capability-80-vs-its-own-goal) section). A modest pillar score indicates an ambitious target, not weak code.

---

## Pillar 1 — Understand me fully ≈ **55%** *(was 20%)*

**What exists (evidence):**
- A **structured, self-updating owner memory** — the Brain (queue #1): `brain_memories` with 8 categories, confidence scores, versions and conflict handling (`core/brain.py`).
- **Auto-learning**: a 30-minute sweep extracts durable facts from new chat (dashboard + Telegram), plus `/remember`, import/dedup/review pipelines, and daily confidence decay so stale knowledge resurfaces for re-check.
- **Memory-first retrieval in code, not prose**: the Conductor grounds every conversational answer in a profile pass; research/execute/CEO consult task-level memory before acting; GraphRAG `owner_context` (queue #2) links memories to tasks/projects/external notes.
- Semantic search (fastembed, keyword fallback); one-way memory mirror into Hermes; `conversations` + `lessons` still feed the loop; `SOUL.md` remains the hand-written persona layer.

**Why ~55% (and not more):** the four milestones from the last revision — profile schema, memory-first retrieval, auto-update, and (partially) Hermes unification — **are delivered**. What's missing for a full Jarvis: depth (a psychology/preference *model*, not just facts), proactive use of the profile ("you usually want X at this hour"), and a single unified memory store with Hermes (today it's a one-way mirror).

**Gap → milestones:**
1. Deepen the profile from *facts* to *models*: routines, tastes, moods, standing instructions with priorities.
2. **Proactive recall** — surface relevant memory unprompted at the right moment, not only when queried.
3. Unify app + Hermes memory into one source of truth (two-way, or a single store).

---

## Pillar 2 — Do anything a PC can ≈ **20%** *(was 15%)*

**What exists (evidence):**
- The coding agent with `write_file / read_file / run_bash / list_files` (`core/telegram_bot.py`), **still sandboxed to `PROJECT_DIR`** with a 30s timeout and a `_BLOCKED_CMDS` denylist.
- A real **tiered permission model now exists in the Conductor** (queue #7): low/medium risk acts auto-execute + report, high risk is proposed and waits for owner confirmation, everything audited in `tobi_actions` — but it governs **MC actions** (projects, tasks, missions), not the shell.
- Broader *service* reach: vault-backed integrations (Notion/GitHub/Vercel/Supabase), MCP client for external tools, web research. These act on the world, not the local machine.

**Why ~20%:** local computer control is unchanged — one directory, one denylist. The permission machinery a safe shell needs has been proven on MC actions, which de-risks the real thing, but filesystem/apps/browser/GUI control is still absent.

**Gap → milestones (this is queue #11 — [TOBI_CLI_SPEC.md](feature-idea-queue/TOBI_CLI_SPEC.md), specced, 30 decisions locked, not built):**
1. `core/terminal_engine.py`: full-machine scope × 4 approval modes (Plan/Ask/Accept/Auto) over SOUL.md's risk tiers, hard safety floor + kill-switch.
2. Acquire capability: install/configure/connect tools (pip/npm/winget…), `installed_tools` registry, auto-wire acquired tools into the Conductor/MCP.
3. **Run Tobi on the personal PC** (the chosen runtime) so local control is even possible; cross-platform Windows+POSIX from day one.
4. Later: browser automation, then GUI/desktop automation.

---

## Pillar 3 — Always-on Jarvis presence ≈ **45%** *(was 40%)*

**What exists (evidence):**
- 24/7 daemon + scheduler (`main.py`): daily report, 6-hourly execution, weekly research/reflection, monthly CEO review, brain sweep/decay, graph sync, storage scans.
- **Two live channels**: Telegram (persistent polling, proactive reports/alerts) and the Mission Control web app with streaming chat — both driven by the same Conductor engine.
- Hermes configured for continuous operation; observability got real (Health page, storage/usage analytics #10, `tobi_actions` audit).

**Why ~45%:** genuinely always-on, proactive on a schedule, and now controllable in natural language from two surfaces. Still: the runtime story is VPS-oriented (not the owner's PC), initiative is cron-shaped (it doesn't *notice* things), and there's no voice or ambient desktop presence.

**Gap → milestones:**
1. **Migrate runtime VPS → personal PC** while keeping reliable always-on behavior (reconcile `HERMES_*.md`).
2. **Initiative beyond cron**: watch signals (inbox, servers, prices, calendar) and reach out when something matters.
3. **Richer channels**: voice, system tray/desktop presence, wake-word.

---

## Business engine — bonus capability (~80% vs. its own goal)

The MMO portfolio loop (`research_engine.py` → proposal/approval in `telegram_bot.py` → `project_executor.py` → `ceo_loop.py`, with lessons feeding back) remains **the most complete part of the codebase**, now with the Office mission UI, the PM board, and Conductor-driven creation on top. Measured against "be a working autonomous business agent," it is ~80% done.

It is listed here, separate from the pillars, precisely so the Jarvis percentages aren't misread as "the code is weak." It isn't — it's aimed at a bigger target.

---

## Near-term next steps a future agent can pick up

1. **Build queue #11 (TOBI CLI)** — the single biggest Jarvis-readiness mover; the spec is complete and it delivers the Awakening-tier permission abilities.
2. **Personal-PC deployment path** — decide how the always-on daemon runs locally; reconcile against the VPS assumptions in `HERMES_*.md`.
3. **Build queue #9 (Explore → News)** once the owner supplies API keys + source lists.
4. **Deepen the Brain** from facts to preference/routine models, and design proactive recall.
5. **Confirm owner persona** — resolve the `SOUL.md` "Thomas" vs. git "Vũ Lê Bình" naming before deepening the user model.
6. ~~User-model schema + memory-first retrieval~~ ✅ delivered by queue #1/#7. ~~Permission model for MC actions~~ ✅ delivered by #7 (shell version pending #11). ~~Integration key audit~~ ✅ superseded by the `/integrations` page's live connect-tests.

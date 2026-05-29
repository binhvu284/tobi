# 03 — Roadmap: Progress Toward the Jarvis End-State

> All percentages are **estimates measured against the Jarvis vision** (not the MMO-agent goal), and each is tied to evidence already in the repo. They are meant to be honest and revisable, not precise.

## Headline: Jarvis-readiness ≈ **25%**

A weighted blend of the three pillars below (Understand 20% · PC control 15% · Always-on 40%, weighted roughly evenly). The number is intentionally modest: the always-on plumbing is real, but a Jarvis is defined by the user model and full PC control — and those are the least built.

> ⚠️ This low number reflects the **Jarvis denominator**. Measured against the *MMO-business-agent* goal instead, the same code is ~70–80% complete (see the [Business engine](#business-engine--bonus-capability-7080-vs-its-own-goal) section). Low pillar scores indicate an ambitious target, not weak code.

---

## Pillar 1 — Understand me fully ≈ **20%**

**What exists (evidence):**
- Conversation history per chat (`conversations` table, `core/database.py`; load/save in `telegram_bot.py`).
- A lessons store the system writes to after cycles (`lessons` table; weekly self-reflection in `main.py` `job_weekly_reflection`).
- A static, hand-written persona/preferences file (`SOUL.md`), synced to `~/.hermes/`.
- Hermes persistent memory layer alongside the above.

**Why ~20%:** there is recall of *chat* and *outcomes*, but **no structured, self-updating model of the owner**. Preferences are hand-authored, not learned.

**Gap → milestones:**
1. Define a **user-profile schema** (preferences, projects, people, habits, standing instructions) — a real table/store, not prose.
2. **Memory-first retrieval**: consult the profile before acting on any task (SOUL.md already declares a "Memory-First Rule" — make it real in code).
3. **Auto-update** the profile from interactions and feedback (so the owner never repeats himself).
4. Unify the custom app's memory with the Hermes memory layer so there is one source of truth.

---

## Pillar 2 — Do anything a PC can ≈ **15%**

**What exists (evidence):**
- A coding agent with `write_file / read_file / run_bash / list_files` (`core/telegram_bot.py`), **sandboxed to `PROJECT_DIR`** with a 30s timeout and a `_BLOCKED_CMDS` denylist.
- API-gated integrations (Notion/GitHub/Vercel/Supabase) that can act on a few external services; Google is a stub.

**Why ~15%:** the only general computer capability is a coding agent **locked to the project directory**. No access to the wider filesystem, desktop apps, browser, or GUI; no real permission model beyond a denylist.

**Gap → milestones:**
1. **Run Tobi on the personal PC** (the chosen runtime) so local control is even possible.
2. **Broaden the tool surface safely**: filesystem beyond the project dir, process/app launching, controlled shell.
3. Add **browser automation** and eventually **GUI/desktop automation**.
4. Build a **tiered permission model** that mirrors `SOUL.md`'s risk rules (low-risk → act + log; medium → act + report; high/irreversible → propose + wait), replacing the blunt denylist.

---

## Pillar 3 — Always-on Jarvis presence ≈ **40%**

**What exists (evidence):**
- 24/7 daemon + scheduler (`main.py` `run_daemon`, `setup_schedules`): daily report, 6-hourly execution, weekly research/reflection, monthly CEO review.
- Reachable over **Telegram** with persistent polling; pushes **proactive** reports, human-action alerts, and revenue alerts (`telegram_bot.py` senders).
- Hermes configured for continuous operation (per memory index, 2026-05-27).

**Why ~40%:** genuinely always-on and already proactive on a schedule — the strongest pillar. But it runs against a VPS-oriented setup, its initiative is limited to fixed cron jobs, and the only channel is text chat.

**Gap → milestones:**
1. **Migrate runtime VPS → personal PC** (reconcile with `HERMES_*.md`, which assumes a VPS) while keeping reliable always-on behavior.
2. **Proactive initiative beyond cron**: notice things and reach out, rather than only firing scheduled jobs.
3. **Richer channels**: voice interface and a desktop presence in addition to Telegram.

---

## Business engine — bonus capability (~70–80% vs. its own goal)

The MMO portfolio loop (`research_engine.py` → proposal/approval in `telegram_bot.py` → `project_executor.py` → `ceo_loop.py`, with lessons feeding back) is **the most complete part of the codebase**. Measured against "be a working autonomous business agent," it is ~70–80% done: the full loop runs, with human-in-the-loop approval and self-review.

It is listed here, separate from the pillars, precisely so the low Jarvis percentages aren't misread as "the code is weak." It isn't — it's just aimed at a smaller target than the Jarvis vision.

---

## Near-term next steps a future agent can pick up

1. **Personal-PC deployment path** — decide how the always-on daemon runs locally; reconcile against the VPS assumptions in `HERMES_*.md`.
2. **User-model schema** — design the Pillar-1 profile store and wire memory-first retrieval into `handle_chat`/task flows.
3. **Integration key audit** — run `python main.py test` / `core.integrations.check_all()` and record which integrations are actually live vs. stubbed (Google is a stub).
4. **Permission model** — replace `_BLOCKED_CMDS` with the tiered risk rules already described in `SOUL.md`.
5. **Confirm owner persona** — resolve the `SOUL.md` "Thomas" vs. git "Vũ Lê Bình" naming before deepening the user model.

# 01 — Vision: Tobi as a Personal Jarvis

## Mission statement

**Tobi is a personal AI in the mold of Jarvis (from Iron Man): an assistant that fully understands its owner, can operate his computer and do anything a PC can do, and is available 24/7 — a continuous, proactive presence, not a chatbot you open and close.**

The relationship to aim for is Jarvis ↔ Tony Stark:
- It *knows* him — his projects, preferences, habits, context, history — without being re-told.
- It *acts* for him — on the machine, across his tools, with judgment about what to do autonomously vs. confirm first.
- It's *always there* — listening, anticipating, surfacing the right thing at the right time.

## Foundation: the Hermes framework

Tobi is built on the **Hermes framework** (NousResearch) as its always-on agent runtime, providing:
- a persistent agent process that runs 24/7,
- persistent memory that accumulates across sessions,
- a skills system (Tobi ships skill files in `hermes_skills/`, synced into `~/.hermes/skills/tobi/`).

On top of Hermes, the custom Python layer in `core/` supplies Tobi's own engines (research, execution, CEO loop), its database, its model router, and its integrations. `SOUL.md` defines the persona and is synced into `~/.hermes/SOUL.md` at startup.

> The two layers (custom Python app + Hermes runtime) currently coexist loosely. Tightening that integration is part of the roadmap, not a solved problem.

## The three vision pillars

Everything Tobi should become reduces to three pillars. These are also the axes of the [roadmap](03_ROADMAP.md).

### Pillar 1 — Understand me fully
A **learned, evolving user model**: preferences, active projects, working habits, relationships, recurring context, and decisions — captured automatically from interactions and reused before every task. Today this is approximated by conversation history, a lessons table, and a *hand-written* `SOUL.md`. The vision is a model Tobi maintains itself, so it never has to be told the same thing twice.

### Pillar 2 — Do anything a PC can
**Real local computer control**: the filesystem, applications, the shell, the browser, and GUI automation — with a sensible permission model so Tobi acts freely on low-risk things and confirms high-risk ones. Today this is a single coding agent deliberately confined to the project directory. The vision is full-machine capability: if a human can do it on the PC, Tobi can do it.

### Pillar 3 — Always-on Jarvis presence
**24/7 availability that is proactive, not just reactive**, and reachable across channels. Today Tobi is always-on via a scheduler and reachable over Telegram, and it does push proactive reports/alerts. The vision adds: running on the owner's **personal PC**, initiative beyond fixed cron jobs (noticing and suggesting), and richer interfaces over time (voice, desktop presence).

## The MMO business engine: one capability, not the identity

Tobi can autonomously run a make-money-online business portfolio: discover niches → propose plans → (owner approves) → execute tasks → review monthly → learn. This is genuinely useful and the most complete part of the codebase. **But it is one thing Tobi *does*, not what Tobi *is*.** It serves the vision as living proof that Tobi can own a goal-directed loop from research to execution to self-review — a pattern that generalizes well beyond making money.

## What "done" looks like

A future where the owner can say anything to Tobi — by text or voice, anytime — and Tobi either does it on his machine immediately, or tells him exactly why it's pausing for confirmation; where Tobi already knows the context so it rarely has to ask; and where it occasionally reaches out first because it noticed something worth his attention. That is the bar.

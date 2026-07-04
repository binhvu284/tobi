# The Agency — TOBI's AI Staff for the Owner's Life — Feature Spec (Phase 0)

> **Status:** 🟡 Queued — **Phase 0: idea approved 2026-07-04.** The full requirements round
> (UI-picker Q&A → locked decisions, house style) has NOT happened yet — run it before building.
> This document captures the approved pitch and the owner context that produced it.
>
> **Owner:** Thomas (sole principal). **Head agent:** TOBI (chief of staff).
> **Related:** Office (#3) becomes the visual home; Conductor (#7) tool-loop is each employee's
> engine; Brain (#1) partitions per-agent memory; model_router (#8) + usage metering (#10) per
> agent; MCP (#5) gives employees external tools; Sentinel (queue #12) feeds them signals.

## 1. The pitch (as approved)

The owner becomes the **owner of an AI agency, run by TOBI as chief-of-staff**. Instead of one
TOBI executing serially, he **hires persistent specialist employees**, each a real agent with its
own beat, memory, schedule, tools, and personality:

- **Finance analyst** — watches his crypto/VN-stock/gold positions, weekly portfolio review.
- **Scout** — hunts things he wants: deals, tools, opportunities, heavy-purchase research.
- **Secretary** — mail/calendar triage and drafting (the safe-automation comms he asked for).
- **Tutor** — runs his learning (student hat; wants-to-read-but-doesn't).
- **Coder** — tends his side projects (repos, CI, ideas backlog).
- …and any custom hire, defined by conversation.

They work **in parallel, 24/7**, coordinate through TOBI, report upward, and **appear as
characters in the existing Office** — the game view stops being decoration and becomes a live
window into an actual staff working. Everything is directable by chat: *"Tobi, have Scout find
me a better internet plan; tell Finance to review my portfolio every Monday."*

## 2. Why this (owner context from the 2026-07-04 40-question round)

- Owner wears four hats (office job / side projects / study / business) with **no fixed
  structure** — parallel domains is literally his life shape.
- He called the Office "pretty but demo" and the business engine "toy" — this reuses both as the
  home for something real (his life, not MMO niches).
- His Jarvis moment: *"handles a whole task alone."* A staff multiplies that.
- He wants to **track, manage and direct** while TOBI-and-team execute safe workflows.
- Approved as a transformative direction after rejecting 9 "too basic" utilities.

## 3. Build sketch (to be locked in the requirements round)

- Generalize the existing `agents`/missions tables: an **employee** = persona (name, role,
  chibi appearance, voice) + **beat** (standing objectives) + **schedule** (cron beats +
  event triggers) + **toolset** (scoped subset of Conductor/MCP tools) + **memory partition**
  (Brain category/tag per agent) + risk ceiling (inherits #7 tiers; high-risk always escalates
  to the owner via TOBI).
- **TOBI = router/chief-of-staff**: owner talks to TOBI; TOBI delegates, aggregates reports,
  resolves conflicts; direct DM to an employee optional.
- **Office integration**: each hire gets a desk/char in the Phaser office; their real runs
  drive the existing working/idle/speech-bubble states and courier handoffs.
- **Reporting**: per-employee activity feed + daily/weekly rollups into TOBI's briefing
  (pairs naturally with Sentinel #12).
- Per-employee `llm_usage` surface tag (#10 already breaks down by agent) + budget share.
- `/agency` page (or Office upgrade): roster, hire/fire/edit, beats, reports, costs.

## 4. Open questions for the requirements round (seed list)

1. v1 roster: which 2–3 employees ship first, with which key-free capabilities?
2. Hire UX: template roles vs free-form persona builder vs both?
3. Autonomy: what may an employee do without TOBI's (or the owner's) sign-off?
4. Memory: hard partition per agent vs shared Brain with per-agent lenses?
5. Office v2 scope: reuse #3 art as-is, or extend (new desks, meeting animations)?
6. Cost governance: per-employee budget caps, idle throttling (meter via #10).
7. Relationship to the legacy MMO loop (Sunday/Alphabet/Friday agents): merge or coexist?

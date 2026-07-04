# Life Quest — TOBI as Game Master of the Owner's Real Life — Feature Spec (Phase 0)

> **Status:** 🟡 Queued — **Phase 0: idea approved 2026-07-04.** The full requirements round
> (UI-picker Q&A → locked decisions, house style) has NOT happened yet — run it before building.
> This document captures the approved pitch and the owner context that produced it.
>
> **Owner:** Thomas (sole principal). **Game master:** TOBI.
> **Related:** verification data comes from real systems — Tasks/PM boards, GitHub commits,
> Brain, usage/storage (#10), Sentinel watchers (#12), Agency reports (#13); Evolution page
> aesthetics (tiers/emblems/unlock ceremonies) and the motion system (#6) are the visual base;
> Conductor (#7) makes every quest action chat-drivable.

## 1. The pitch (as approved)

MC has no daily gravity for the owner, his goals live in his head, and his time leaks to gaming —
so **make MC the game**. TOBI becomes **game master of his real life**:

- Goals, projects, habits, and learning become **quest lines**: main quests (year goals),
  side quests, and dailies — with **XP, levels, streaks, and loot**.
- **Loot = real rewards the owner defines**: guilt-free gaming hours, purchases he's been eyeing.
- TOBI **generates quests from what it actually knows**: *"Side quest: clear 50 inbox mails,
  80 XP. Boss fight: ship queue #11 this month."*
- **Completion is verified by real data** — tasks done, commits pushed, spend logged, memories
  saved — not self-reporting.
- TOBI adapts difficulty, narrates progress in the butler voice, and the **character sheet is
  the owner's life stats**; the Evolution page finally measures the owner and TOBI leveling
  **together**.

## 2. Why this (owner context from the 2026-07-04 40-question round)

- He's a gamer (time leak he named himself) — this weaponizes the gaming instinct against
  procrastination instead of fighting it.
- Goals are **in his head only** and he explicitly **wants TOBI to push him** (accountability).
- Journaling/habits "tried, didn't stick" — streak/XP mechanics are the classic fix.
- MC is opened "rarely, when not developing" — a daily quest board is daily gravity.
- Premium = intelligence + polish + all-in-one; the Evolution/motion aesthetic is already built
  to make this feel like a AAA system, not a chore app.
- Approved as a transformative direction after rejecting 9 "too basic" utilities.

## 3. Build sketch (to be locked in the requirements round)

- `core/quest_engine.py`: quest = {line, tier (main/side/daily), objective, **verifier**
  (declarative check against real data: task status, commit count, mail count, streak…),
  XP, deadline, loot link}. Daily tick generates/refreshes quests (GM = Haiku planning,
  Opus for season narratives; metered via #10).
- **Verifiers first-class**: each quest must name a machine-checkable signal — no honor system.
  Sources: tasks/pm tables, GitHub API, Brain writes, llm_usage/storage snapshots, Sentinel
  events (#12), Agency reports (#13).
- **Progression**: XP curve, levels, streak multipliers, seasonal resets; `quest_log`,
  `quest_state`, `loot_ledger` tables; loot redemption is owner-defined and TOBI-tracked.
- **GM voice**: quest briefs/debriefs in butler EN/VN; celebration ceremonies reuse Evolution's
  unlock overlay + toasts (#6 M3).
- `/quest` page: quest board (main/side/dailies), character sheet (life stats), quest log,
  loot shop. Dashboard widget: today's dailies + streak.
- Conductor tools: `list_quests`, `accept_quest`, `complete_check`, `claim_loot`, `set_goal`.

## 4. Open questions for the requirements round (seed list)

1. Scope of v1 quest sources: MC-internal only (tasks/commits/brain) vs + external (mail, markets)?
2. XP/level curve + streak rules; what happens on missed dailies (punishment vs grace)?
3. Loot economy: owner-defined rewards only, or TOBI-suggested; hard rules for redemption?
4. Goal intake: conversational onboarding of the "in my head" year goals → quest lines.
5. How hard does TOBI push (nudge cadence, tone) — ties to the new initiative rules (#12 §4)?
6. Relationship to Evolution page: merge into it vs separate `/quest` page cross-linked?

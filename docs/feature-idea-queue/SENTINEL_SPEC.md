# Sentinel — TOBI's Live Awareness Layer — Feature Spec (Phase 0)

> **Status:** 🟡 Queued — **Phase 0: idea approved 2026-07-04.** The full requirements round
> (UI-picker Q&A → locked decisions, house style) has NOT happened yet — run it before building.
> This document captures the approved pitch and the owner context that produced it.
>
> **Owner:** Thomas (sole principal). **Head agent:** TOBI.
> **Related:** initiative rules change approved by the owner (see §4); Conductor (#7) is the
> acting engine; Brain (#1) stores what Sentinel learns; Genesis vault (#4) holds any new keys;
> usage logging (#10) meters its LLM calls; MCP (#5) can feed external watchers.

## 1. The pitch (as approved)

Today TOBI is a genius with amnesia about *right now* — it knows nothing until the owner types.
A real assistant is already aware. Sentinel is TOBI's **live consciousness**:

- A network of **watchers** over everything connected — inbox, calendar, crypto/VN-stock moves,
  GitHub repos, news spikes, and MC itself (missions, storage, budget, agents) — feeding one
  continuously-maintained **world-state**.
- A page that is a **living situational board**: what TOBI currently knows, what changed, what it
  thinks matters, what it suggests doing — a consciousness stream, not a feed.
- **"While you were away, sir"**: sit down after hours and TOBI opens with a synthesized catch-up
  (price levels broken, mails needing action, missions finished, work left half-done).
- **Every chat starts pre-loaded** with the current world-state, so TOBI always knows where the
  owner left off.
- Watchers are **added/tuned by conversation** ("watch ETH under $3k", "watch this repo's CI").

This is the **initiative engine** the owner asked for — grounded in real awareness, not cron jobs.

## 2. Why this (owner context from the 2026-07-04 40-question round)

- Owner wants **full Jarvis initiative + important-thing alerts + one daily briefing** — explicitly
  retiring the old "no autonomous push" house rule *for the right features*.
- His day has **no fixed structure**; he juggles office job + side projects + study + business
  across **multiple machines**; time leaks to **context switching** and **searching for things**.
- Inbox is **hundreds unread**; he checks **markets daily by hand**; he **forgets deadlines,
  promises, ideas, people details**.
- He rejected 9 single-purpose utility features as "too basic — not much impact to be my truly
  assistant." Sentinel was approved as a transformative direction.

## 3. Build sketch (to be locked in the requirements round)

- `core/sentinel.py`: watcher registry + scheduler ticks; each watcher = {source, condition,
  cadence, last_state, importance-scorer}. Reuse existing connectors (integrations, MCP tools,
  market APIs from Explore #9 when built, `llm_usage`/storage from #10).
- **World-state store**: rolling `sentinel_events` + a compact `world_state` snapshot the
  Conductor injects into every chat turn (token-budgeted, like `owner_context`).
- **Catch-up synthesis**: on session start (MC open / first Telegram msg after gap), generate the
  "while you were away" brief from events since last seen.
- **Alert tiers**: watcher hits are scored → silent log / board item / push (Telegram or MC bell)
  per the owner's new initiative rules; every push is auditable in `tobi_actions`.
- `/sentinel` page: the consciousness board (live stream + watcher cards + world-state inspector).
- Conductor tools: `add_watcher`, `list_watchers`, `whats_new`, `world_state`.

## 4. House-rule change this feature carries

Previous specs enforced "no autonomous push" ([E8], [S26]). The owner has now explicitly opted
into **initiative**: daily briefing + important alerts + full-Jarvis-initiative for safe actions.
Sentinel is where that rule is re-implemented *with control*: per-watcher alert tiers, quiet
hours, and a global initiative dial — decide the details in the requirements round.

## 5. Open questions for the requirements round (seed list)

1. Which watchers ship in v1 (MC-internal + markets + GitHub are key-free; mail/calendar need OAuth)?
2. Alert delivery: Telegram vs MC bell vs both; quiet hours; batching rules.
3. World-state size/retention; how much context is injected per chat turn (token cost).
4. Importance scoring: rules, LLM judge (Haiku), or hybrid; per-watcher sensitivity.
5. Page design: stream-first or board-first; relationship to the Dashboard.
6. LLM budget cap for continuous awareness (meter via #10; D21 guard).

# Premium Chat v2 — reliability + premium UI/UX overhaul

> **Builds on** [PREMIUM_CHAT_SPEC.md](PREMIUM_CHAT_SPEC.md) (#8) and the #7 Conductor.
> **Owner-reviewed via picker rounds** (24 decisions below). **Date:** 2026-06-27.
> **Goal:** permanently kill the message **cut-off**, fix the **can't-create-task** failure, and
> raise the chat to a genuinely **premium** Claude-grade UI/UX. **Storage page is OUT** (that's #10).

---

## Root-cause diagnosis (confirmed in code)

The cut-off + "says yes but no task created" + "thinking leaks into the answer" are **one bug
family**: the Conductor caps model output far too low and never notices truncation.

- Tool-loop step capped at **`max_tokens=600`** (`core/conductor.py:941`); final answer **`900`**
  (`:937`, `:984`); `_safe_complete` default **700** (`:796`).
- **No client checks `finish_reason`/`stop_reason`** (`core/model_router.py`) → truncation is silent.
- A weak model writes prose instead of pure JSON, hits 600 tokens, the **tool-call JSON is
  truncated → unparseable → treated as the final answer** → the tool never runs and the text is cut
  off. The chopped text is then **saved to the DB** (the "cut-off in database").
- Create-**project** usually survives (1 step); create-**task-in-existing-project** is a 2-step
  chain (`list_projects → create_task`) → far more likely to truncate. Matches the report exactly.

---

## Locked decisions (24)

### Reliability & cut-off (P1)
1. **Fix = raise caps + auto-continue** on truncation (detect `finish_reason`/`stop_reason`, continue until complete).
2. **Target answer length ~4k tokens** (generous; rich answers never feel capped).
3. **True token streaming** of the final answer (flows live; replaces compute-then-fake-chunk).
4. **Auto-retry a truncated/invalid tool-call up to 2×** with a firmer "pure JSON only" nudge.
5. **Hard-separate reasoning** from the answer — reasoning only ever appears in the collapsible "Thought for…" panel.
6. **Parse reasoning markers** (`<think>…</think>`, "Reasoning:", o-series traces) and route them to the thinking panel.
7. **Model self-diagnosis** — after retries/continuations fail, TOBI **announces it's a model problem** and suggests switching to a stronger model (links the picker). Default routing is left as-is (no forced Claude).
8. **Stream scope** — tool steps render as **live animated phases**; only the **final answer streams** as text.
9. **Persist the full answer** to `chat_messages` (never the truncated/streamed reconstruction).

### Thinking animation (P2)
10. **Signature AI orb** — one cohesive morphing-gradient orb with particles + glow (not a grab-bag).
11. **Per-phase micro-animations** — the orb changes per phase (recalling memory → using tool X → composing), driven by the live phase events.
12. **Comfortable, premium, reduced-motion-aware** (calm fallback kept).

### Layout & rich visualization (P2)
13. **Centered ~760px reading column** (Claude/ChatGPT style); rich blocks still take full column width.
14. **All four rich-block families:** tables · cards & callouts · code & references · **charts**.
15. **Charts = dependency-free SVG** (bar/line/donut); no Recharts.
16. **Proactive formatting** — system-prompt guidance so TOBI emits `tobi:table/card/callout/chart/...` when it fits.
17. **Code blocks** — copy button + **light dependency-free syntax highlight**.
18. **Comfortable density** (generous spacing, slightly larger text). Assistant = full-width block, user = right bubble.

### Input, attachments, compact, sidebar (P2)
19. **Auto-grow textarea to ~200px** (~7 lines) then scroll; resets after send. Slim toolbar + subtle context % hint.
20. **Image attachments = thumbnail cards** (preview + filename + size + remove); **grid** for multiple.
21. **Compact = inline banner at ~80%** with a progress bar **+ always-available header button**.
22. **Collapsible session sidebar** → thin icon rail, toggle, persisted, **default open**.

### Scope & process
23. **Storage resources page = OUT of v2** (belongs to #10 — do not build here).
24. **Delivery = phased checkpoints**; **Artifacts/side-panel = later** (not v2).

---

## Phased plan

### P1 · Reliability & cut-off — ✅ DONE (built, unit-tested 15/15, **verified live**)

**Shipped:** every `model_router` client now exposes a normalized **`last_finish_reason`** (`length`
when truncated) on both `complete()` and `complete_stream()`, plus a `complete_full()` continuation
helper. The Conductor was rewritten: caps raised to **2048 (tool steps) / 4096 (final)** with
**auto-continue** on a `length` stop; a garbled/truncated tool-call is **retried up to 2×** with a
strict "pure JSON only" nudge; the system prompt now forbids prose around tool-calls and demands
complete sentences; **reasoning is stripped** (`<think>…</think>`, harmony channels, `Reasoning:`)
into a separate field; **model self-diagnosis** returns a "the model is struggling, try a stronger
one" reply + `model_issue` flag after retries fail; and the **final answer truly streams** token-by-
token via a new `on_delta` callback with a prefix-classifier (tool-call JSON is buffered silently,
only real answers stream). The stream endpoint relays live `delta`/`thinking`/`notice` events and
**persists the full reply + reasoning** (reasoning → the `thinking` column).

**Live proof (real model over the SSE API):** a detailed architecture answer streamed **172 delta
events and ended cleanly on a full sentence** (no cut-off); **"add a task to <project>" actually
created the task** (Task ID returned, visible on the PM board) with a complete reply; a "think step by
step" probe returned a clean answer with **no reasoning leaked**. Unit suite **15/15**; all prior
suites green (pm-fix 13, #7 P2 24/P3 17, #8 P1 26/P1b 10/P2 25/P3 23).

#### Original P1 design notes
- **Raise caps:** tool steps → ~1536–2048, final answer → ~4096; `_safe_complete` default up.
- **Expose `finish_reason`/`stop_reason`** from every client (`last_finish_reason`).
- **Auto-continue:** on a `length` finish, append the partial and request a continuation; loop to a
  sane cap; reassemble the full answer.
- **Tool-call robustness:** firmer "respond with ONLY the JSON object, no prose" rule; if a tool-call
  is truncated/unparseable, **retry the step up to 2×** with a stricter nudge.
- **Model self-diagnosis:** count per-turn failures (truncations, unparseable tool-calls, exhausted
  retries); on persistent failure return a butler line — *"the current model seems to be struggling
  with this, sir — consider a stronger one"* — and flag it to the UI (model-issue notice).
- **Reasoning separation:** strip/parse reasoning markers from the answer → a `thinking` field/event;
  the answer body stays clean.
- **True streaming:** the tool-loop gathers context, then the **final compose streams** token-by-token
  via `complete_stream`; the chat SSE endpoint relays real deltas (typed events already exist).
- **Persist full answer**; never store the truncated text.
- **Tests:** reproduction asserting no `finish_reason == "length"` on a long answer; a 2-step
  create-task chain completes and the task lands on the PM board; reasoning stripped from the answer;
  model-incapability path fires on a stubbed failing client. **Live-server verification** over the real SSE API.

### P2 · Premium chat UI/UX (frontend) — ✅ DONE (built, typecheck + `npm run build` clean; backend suite 153/153)

**Shipped (frontend):** the conversation is now a **centered ~760px reading column** with comfortable
density (assistant full-width block, user right bubbles). A new **signature AI orb**
([`components/chat/ThinkingOrb.tsx`](../../dashboard/src/components/chat/ThinkingOrb.tsx)) replaces the
old pulsing dot — a morphing-gradient core + breathing glow + rotating ring + orbiting particles, whose
**colour and micro-animation change per live phase** (recall · read · act · web · think) derived from the
SSE `thinking` events, with a shimmering phase label and a calm reduced-motion fallback. **Dependency-free
SVG charts** ([`components/chat/Charts.tsx`](../../dashboard/src/components/chat/Charts.tsx)) render
`tobi:chart` blocks (bar / line / donut, theme-tinted, animated entrance); **code blocks** gained a light
dependency-free **syntax highlighter**. The **reasoning panel** ("Thought for Xs") now expands the routed
reasoning text **and** tool steps. The composer **auto-grows to ~200px** then scrolls; image attachments
render as **thumbnail cards** (preview + name + size + remove) in a grid; the **session sidebar collapses**
to an icon rail (persisted to `localStorage`, default open); **Compact** is available both inline (~80%
banner) and as a **header button**; and the backend's `notice` (model-issue) event is now handled —
a tasteful inline card offers a **one-tap model switch + Retry**. Proactive formatting guidance was added
to the Conductor system prompt (`_system_prompt`) so TOBI emits `tobi:table/chart/card/callout/keyvalue/
status/reference` blocks when they fit (MC only; suppressed on Telegram).

**New/changed files:** `dashboard/src/components/chat/ThinkingOrb.tsx` (new),
`dashboard/src/components/chat/Charts.tsx` (new), `dashboard/src/components/chat/MarkdownView.tsx`
(chart block + highlight), `dashboard/src/pages/Chat.tsx` (rewritten layout), `dashboard/src/api.ts`
(`onNotice`/`ChatNotice`), `dashboard/src/index.css` (orb + chart keyframes & reduced-motion guards),
`core/conductor.py` (`_system_prompt` formatting guidance).

#### Original P2 design notes
- **Centered ~760px column**, comfortable density; assistant full-width block, user right bubbles.
- **Signature AI orb** thinking component with **per-phase micro-animations** (morphing gradient,
  particle drift, glow), driven by live phase events; reduced-motion calm fallback.
- **Smooth true-stream rendering** of the final answer.
- **Rich blocks:** polish tables, cards/callouts, key-value, status, reference lists; add **SVG charts**
  (bar/line/donut); **code blocks** with copy + light highlight. Proactive `tobi:*` emission.
- **Reasoning panel:** collapsible "Thought for Xs" showing the routed reasoning + tool steps.
- **Input:** auto-grow to ~200px; slim toolbar; context % hint.
- **Attachments:** image **thumbnail cards** + grid; cleaner compact paste UI.
- **Compact:** inline ~80% banner with progress + header button.
- **Sidebar:** collapsible icon-rail toggle, persisted, default open.
- **Model-issue notice:** a tasteful inline card with a one-tap "switch model" affordance.

### Explicitly OUT of v2
Storage resources page (#10) · Artifacts/side-panel canvas · Recharts · full syntax-highlighter
library · forcing a Claude default.

---

## Acceptance criteria
1. A long, rich answer **never cuts off** mid-sentence (verified: no `finish_reason == "length"`), and the **full** text is stored in the DB.
2. "Create a task in <project>" **actually creates the task** (multi-step chain) and it appears on the PM board — no mid-sentence stop.
3. Model **reasoning never appears** in the answer body; it lives in the collapsible panel.
4. When the model genuinely can't perform (after retries), TOBI **says it's a model issue** and offers to switch.
5. The conversation is a **centered ~760px column**; answers render **tables/cards/code/charts** richly; the final answer **streams live**.
6. The thinking state shows a **signature orb with per-phase micro-animations**.
7. Input **auto-grows** to ~200px; pasted images show **thumbnail cards**; the sidebar **collapses**; Compact shows an **inline banner + header button**.

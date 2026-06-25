# TOBI "Living Machine" — Mission Control Motion & UX Pass

> **Queue status:** 🟡 Queued · **Scope:** v1 = global motion system + all 12 pages (phased M1–M4) · **Owner-reviewed:** 30 Q&A captured below
> Part of the [Feature Development Queue](QUEUE.md). A cross-cutting **UX/motion enhancement** of the entire Mission Control dashboard — not a new feature surface. Turns MC from "good static UI" into a cohesive, alive, **sci-fi HUD** that feels like a system thinking.

## Context

MC already has a real motion vocabulary to build on (don't rebuild it — extend it):

- `tobi-loader` (counter-rotating rings + core pulse), `tobi-shimmer`, `tobi-bar-slide`, `tobi-icon-glow` — [`src/index.css`](../../dashboard/src/index.css)
- `tier-unlock` / `ring-expand` / `tier-pulse` (Evolution), `sovereign-gradient` / `aurora-gradient` animated gradients
- `grid-bg`, `scanlines`, `glow-accent|success|warning` utilities
- Office character motion (`char-idle` / `char-working` / `char-eye`)
- 8 CSS-var themes (incl. `hightech`, `gaming`, `midnight`) — `rgb(var(--x) / <alpha>)` token system
- `framer-motion` already used across **24 files**; `useSound`, `useMissionStream` (SSE) hooks present; `ToastProvider` + `ThemeProvider` contexts

What's missing is a **system**: shared motion tokens, route transitions, reusable primitives, and signature moments on the marquee pages. Today motion is per-component and inconsistent. This pass introduces one source of truth and applies it everywhere.

**North star:** *Living machine / sci-fi HUD* — subtle scanlines, glows, data-streams, reactive panels — executed with **balanced** restraint and a **strict 60fps budget (transform/opacity only)**. Premium, not busy.

## Design direction (the spine)

- **Feel:** a system that is alive and thinking. Panels *boot*, numbers *tick*, surfaces *react*. Sci-fi accents on signature surfaces; calm-but-crisp everywhere else.
- **Signature easing:** crisp spring with slight overshoot — `--ease-spring: cubic-bezier(.34, 1.56, .64, 1)` for entrances/toggles; `--ease-out: cubic-bezier(.22, 1, .36, 1)` for exits/calm moves.
- **Timing:** everyday interactions **120–220ms**; signature moments **500–900ms**. Nothing gratuitous.
- **Budget rule:** animate **only `transform` and `opacity`**; no animating layout/`width`/`top`/`box-shadow` size on the hot path (use transforms + pseudo-element glows). `will-change` applied surgically, removed after.

## Decisions (from 30 Q&A)

| # | Area | Decision |
|---|---|---|
| 1 | Signature feel | **Living machine / sci-fi HUD** |
| 2 | Scope | **Global system + all 12 pages**, phased |
| 3 | Intensity | **Balanced** (purposeful, not maximal) |
| 4 | Perf vs rich | **60fps always** — GPU transform/opacity only |
| 5 | Brain upload | **Neural ingestion** — particles stream into a glowing brain, typed live log, gradient-glow pulse, progress bar |
| 6 | Chat thinking | **Animated orb + status phases** ("Recalling memories…" → "Thinking…" → streamed reply w/ caret) |
| 7 | Health check | **Live diagnostic sweep** — per-row radar scan, sequential ping pulse, snap to green/amber/red glow |
| 8 | Sound | **Subtle, opt-in, OFF by default** (Settings toggle; reuse `useSound`) |
| 9 | Route transitions | **HUD panel boot** — fade + 8px slide-up + one-shot scanline sweep + staggered children |
| 10 | Entrance choreography | **Orchestrated top-down stagger** (header → stats → cards, ~30–60ms steps) |
| 11 | Easing personality | **Crisp spring** (slight overshoot) |
| 12 | Ambient background | **Per-page accent atmosphere** (Brain violet, Health green, Evolution gold, Office cyber…) |
| 13 | Buttons | **Border-trace / sweep** on hover; press scale 0.96 |
| 14 | Cards | **Spotlight / cursor-follow glow** (radial glow tracks cursor) |
| 15 | Nav | **Sliding active indicator** (`layoutId`) + icon pop |
| 16 | Command palette | **Spring-in + result stagger + selection glow** |
| 17 | Loaders | **Content-shaped shimmer skeletons** (keep `tobi-loader` for full-page boots) |
| 18 | Numbers | **Count-up + accent flash on change** |
| 19 | Toasts | **Slide + spring + colored edge + drain timer** |
| 20 | Empty states | **Animated illustration + invitation CTA** |
| 21 | Evolution | **Refined glow sweep + toast** (no particle shower) |
| 22 | Office | **Ambient liveliness only** (breathe/blink + desk glow; no deep SSE wiring this pass) |
| 23 | Dashboard | **Signature hero boot sequence** ("system online", once/session) |
| 24 | Kanban | **Smooth reorder only** (layout animation, minimal grab flourish) |
| 25 | Reduced motion | **Respect OS + in-app toggle** (Settings: Full / Reduced / Off) |
| 26 | Modals | **Slide-over panels + fade-scale dialogs** (panels from edge, dialogs center) |
| 27 | Theme switch | **Smooth color crossfade** (~300ms CSS-var transition) |
| 28 | Scroll | **Reveal-on-scroll + sticky condensing headers** (no heavy parallax) |
| 29 | Tech approach | **Centralized motion primitives module** (tokens + variants + shared components) |
| 30 | Rollout | **Foundation first → named effects → marquee pages → rest + polish** |

## Motion-system architecture (the foundation)

A single source of truth, composed everywhere. New `src/lib/` + `src/components/motion/` (neither exists yet).

- **`src/lib/motion.ts`** — tokens + variants:
  - `DUR` (`{ xs: .12, sm: .18, md: .28, lg: .5, xl: .8 }`), `EASE` (`spring`, `out`, `snappy`), `SPRING` presets (`{ type:'spring', stiffness, damping }`).
  - Reusable framer-motion `Variants`: `panelBoot`, `staggerParent`, `staggerChild`, `fade`, `scaleIn`, `slideOver`.
  - `useReducedMotionPref()` — merges OS `prefers-reduced-motion` with the in-app setting (Full/Reduced/Off) from a new `MotionProvider`; returns the active level so every primitive can degrade.
- **`src/context/MotionProvider.tsx`** (new) — holds the Full/Reduced/Off setting (localStorage), exposes it via context; Settings page writes it. When **Reduced/Off**, variants collapse to opacity-only or instant.
- **`src/components/motion/`** (new) — shared primitives, each reduced-motion aware:
  - `<Reveal>` — entrance fade/slide (used by orchestrated stagger + whileInView reveal-on-scroll).
  - `<Stagger>` — parent that cascades children top-down.
  - `<PageBoot>` — the HUD panel-boot route wrapper (slide-up + fade + scanline sweep).
  - `<SpotlightCard>` — card wrapper with cursor-follow radial glow (CSS var `--mx/--my` updated on `pointermove`, pseudo-element glow — no layout cost).
  - `<CountUp>` — animates numeric value old→new + accent flash on change.
  - `<Scanline>` / `<AmbientField>` — the one-shot sweep + the per-page accent atmosphere layer.
  - `<TraceButton>` — border-trace/sweep hover + press-scale.
- **CSS additions** in [`index.css`](../../dashboard/src/index.css): new tokens (`--ease-spring`, `--ease-out`, `--dur-*`), `@keyframes` for `scanline-sweep`, `border-trace`, `ambient-drift`, `count-flash`; a global `[data-motion="reduced"]` / `[data-motion="off"]` guard that neutralizes decorative animation; theme-var `transition` on `:root` for the 300ms theme crossfade.

> **Reduced-motion is a first-class requirement, not an afterthought.** Every primitive checks the active level. `data-motion="off"` ⇒ instant states; `="reduced"` ⇒ opacity-only, no transforms/loops; functionality identical in all modes.

## The three named signature effects

### 1. Brain upload — "Neural ingestion" ([`components/brain/BrainImportModal.tsx`](../../dashboard/src/components/brain/BrainImportModal.tsx))
- On parse/commit: the dropped file "dissolves" into drifting glyph/particles that stream toward a glowing brain/orb glyph (particles = transformed divs, capped count, GPU-only).
- **Live typed log** of the *real* pipeline stages (`parse_import` → chunks → extracted N → dedup → merge suggestions): lines type/append as the backend returns them. Wire to the existing parse/commit responses (counts already returned by `commit_import`).
- **Progress bar** with animated gradient fill; **gradient glow** behind the orb pulses with activity, settles on done.
- Output tie-in: extracted memory cards fade/scale in as the log reports them. Reduced-motion ⇒ plain progress bar + log, no particles.

### 2. Chat thinking — "Animated orb + status phases" ([`pages/Chat.tsx`](../../dashboard/src/pages/Chat.tsx))
- Replace the static "TOBI is thinking…" bubble with a small **pulsing orb** + **phase text** that reflects the real memory-first pipeline: `Recalling memories…` → `Thinking…` → then the **streamed reply** (streaming already shipped in Brain v2 via `streamBrainChat`) with a blinking caret leading the text.
- Phases are time/stage-driven (first delta arrival flips orb→stream). Reduced-motion ⇒ static orb + phase text, no pulse; caret still optional.

### 3. Health check — "Live diagnostic sweep" ([`pages/Health.tsx`](../../dashboard/src/pages/Health.tsx), [`components/HealthBar.tsx`](../../dashboard/src/components/HealthBar.tsx))
- Running a check runs a **sequential ping sweep**: each integration/endpoint row shows a radar/scan shimmer, a traveling pulse moves down the list, each row **snaps to green/amber/red with a glow** as its real result returns.
- Optional overall health figure **counts up** via `<CountUp>`. Reuses the same per-integration test logic as the Genesis/Integrations work. Reduced-motion ⇒ rows resolve with a color fade, no sweep.

## Global system applied (all 12 pages)

- **Route transitions:** wrap `<Routes>` in `App.tsx` with `AnimatePresence` + `useLocation` key; every page mounts inside `<PageBoot>` (fade + slide-up + scanline sweep + staggered children).
- **Entrance:** each page composes `<Stagger>`/`<Reveal>` top-down (header → stat bar → content grid).
- **Per-page atmosphere:** `<AmbientField accent={page}>` renders a faint themed glow/grid behind content, keyed to the page's accent.
- **Micro-interactions:** `<TraceButton>` for primary actions; `<SpotlightCard>` adopted by `TaskCard`, `StatCard`, memory rows, integration cards; `NavBar`/`AppShell` get the sliding `layoutId` indicator + icon pop.
- **Data/state:** `<CountUp>` on revenue/%/counts/Genesis; content-shaped shimmer skeletons in `PageLoader` presets; toast motion upgraded in `ToastProvider`; animated empty states.
- **Overlays:** `TaskDetailPanel` → slide-over; `ConfirmTransitionModal`/`TaskCreateModal`/`MemoryModal` → fade-scale dialog (shared variants).
- **Theme crossfade** + **reveal-on-scroll/sticky headers** as cross-cutting CSS/behavior.

## Marquee moments

- **Dashboard:** once-per-session **hero boot** — "TOBI online" resolves, stat tiles cascade with count-ups, ambient grid ignites (session-flag so returns are fast).
- **Evolution:** refined **glow sweep** across the completing tier node + confident toast (+ optional sound) — reuses `tier-unlock`/`ring-expand`, dialed to "premium" not "fireworks".
- **Office:** ambient liveliness — characters breathe/blink, desks glow softly (no new SSE wiring this pass).
- **Projects/Task:** smooth Kanban reorder via layout animation; minimal grab flourish.

## v1 build phases (everything ships, sequenced)

- **M1 — Foundation:** `lib/motion.ts` tokens+variants, `MotionProvider` + Settings toggle (Full/Reduced/Off), CSS tokens/keyframes + reduced-motion guards, `AnimatePresence` route transitions (`<PageBoot>`), theme crossfade. *Outcome: every page already feels cohesive; a11y solid.*
- **M2 — Named effects:** Brain neural ingestion, Chat orb+phases, Health diagnostic sweep. *Outcome: the three requested wins, visible immediately.*
- **M3 — Marquee pages:** Dashboard hero boot, Evolution refined unlock, Office ambient liveliness, Command Palette spring-in. Shared primitives (`SpotlightCard`, `TraceButton`, `CountUp`, `AmbientField`) adopted on these first.
- **M4 — Remaining pages + polish:** roll primitives across the other pages (Projects, Task, Ability, Architecture, ControlRoom, Settings, Dashboard data), toasts/empty-states/skeletons, scroll reveals, sound cues, final 60fps audit.

## File manifest (high level)

| File | Action |
|---|---|
| `src/lib/motion.ts` | Create — tokens, variants, `useReducedMotionPref` |
| `src/context/MotionProvider.tsx` | Create — Full/Reduced/Off setting |
| `src/components/motion/*` | Create — `Reveal`, `Stagger`, `PageBoot`, `SpotlightCard`, `CountUp`, `Scanline`, `AmbientField`, `TraceButton` |
| `src/index.css` | Edit — motion tokens, keyframes, reduced-motion guard, theme transition |
| `src/App.tsx` | Edit — `AnimatePresence` + `<PageBoot>` route wrapper; mount `MotionProvider` |
| `src/components/AppShell.tsx`, `NavBar.tsx` | Edit — sliding `layoutId` indicator + icon pop |
| `src/components/CommandPalette.tsx` | Edit — spring-in + result stagger + selection glow |
| `src/components/PageLoader.tsx` | Edit — content-shaped shimmer presets |
| `src/context/ToastProvider.tsx` | Edit — slide+spring+edge+timer |
| `src/components/{TaskCard,StatCard,TaskDetailPanel,ConfirmTransitionModal,TaskCreateModal}.tsx` | Edit — adopt primitives |
| `src/components/brain/BrainImportModal.tsx` | Edit — neural ingestion |
| `src/pages/Chat.tsx` | Edit — orb + phases |
| `src/pages/Health.tsx`, `src/components/HealthBar.tsx` | Edit — diagnostic sweep |
| `src/pages/Dashboard.tsx` | Edit — hero boot |
| `src/pages/Evolution.tsx` | Edit — refined unlock |
| `src/pages/Settings.tsx` | Edit — motion toggle |
| All other `src/pages/*` | Edit — compose `<PageBoot>`/`<Reveal>`/`<Stagger>` + `<AmbientField>` |

## Verification (end-to-end)

1. `cd tobi/dashboard && npm run build` clean; no new heavy deps (framer-motion already present).
2. **Cohesion:** every route boots with the HUD panel transition + top-down stagger; nav indicator slides.
3. **Named effects:** Brain import shows particles+typed log+glow and real card output; Chat shows orb→phases→streamed caret; Health runs a sequential sweep resolving to colored states.
4. **A11y:** OS `prefers-reduced-motion` AND the Settings toggle both collapse motion to fade/instant; Off = no transforms/loops; tab/keyboard unaffected.
5. **Perf:** DevTools performance/Rendering — no long frames during route change, card spotlight, count-ups, Brain ingestion; only `transform`/`opacity` on the compositor; `will-change` cleaned up.
6. **Themes:** switching any of the 8 themes crossfades smoothly; per-page atmosphere recolors correctly.
7. **Marquee:** Dashboard hero boot fires once/session; Evolution completion glows + toasts; Office characters idle-live.

## Risks / watch-items

- **Perf regressions** — strict transform/opacity budget; cap particle counts; profile each signature effect; lazy-mount heavy backgrounds. The 60fps rule overrides richness (Decision #4).
- **Motion fatigue** — "balanced" means restraint; signature moments are rare and meaningful, everyday motion is fast/quiet.
- **Reduced-motion correctness** — test all three modes (Full/Reduced/Off) on every primitive; this is a hard requirement, not optional polish.
- **Bundle size** — prefer CSS keyframes + existing `framer-motion`; **no GSAP/Lottie** (Decision #29 chose the lightweight centralized module). Current bundle already warns >500kB — keep motion code lean and tree-shakeable.
- **Don't rebuild existing vocabulary** — extend `index.css` (`tobi-loader`, `tier-unlock`, gradients, `grid-bg`) rather than duplicating it.
- **Scope creep** — deep Office↔SSE mission choreography and gesture-rich Kanban drag are explicitly **deferred** (Decisions #22, #24).

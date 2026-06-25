# TOBI "Living Office" — Game-like Agent Office Visualization

> **Queue status:** ✅ Done (v1, owner-approved) · **Replaces:** the current Office HQ scene (`dashboard/src/pages/Office.tsx`) · **Owner-reviewed:** 30 Q&A + research captured below
> **Built:** Phaser 3 behind a React↔scene `EventBus` in `dashboard/src/office/` (`PhaserGame.tsx`, `scenes/Preloader.ts` procedural art, `scenes/OfficeScene.ts`, `objects/ChibiAgent.ts`, `pathfinding.ts`, `fx.ts`, `iso.ts`, `theme.ts`). Art is **procedural** (decided over the spec's CC0-packs line — zero licensing risk, accent-follows-theme native). Backend untouched. See QUEUE.md row #3 for the feature summary.
> Part of the [Feature Development Queue](QUEUE.md). Turns the static pixel hub-and-spoke into a vibrant, isometric, game-like office where agents work, idle, sleep, talk, and walk — driven by the real mission stream.

## Context

Today's Office (`Office.tsx`) is a flat, "stone-age" hub-and-spoke: SVG pixel sprites on a ring around a core, neon connector lines, a live SSE mission stream, and CodeRain/Scanlines FX. The owner wants it to feel like an **actual lively office** you can **control like a game** — a beautiful isometric room where each agent has a themed desk, characters animate per state (working/idle/sleeping/talking/thinking/error), tasks visibly hand off between agents, and the whole thing mirrors real agent activity in real time.

This is primarily a **heavy UI/UX build**. It reuses the existing backend (agents, `getOfficeStats`, missions, `useMissionStream` SSE) with only light additions.

## Research summary (proven references)

- **a16z AI Town** — agents rendered with **PixiJS/pixi-react** over a tilemap; simulation state decoupled from rendering and **interpolated** from historical buffers for smooth motion. [repo](https://github.com/a16z-infra/ai-town) · [ARCHITECTURE](https://github.com/a16z-infra/ai-town/blob/main/ARCHITECTURE.md)
- **Stanford Smallville / Generative Agents** — 2D sprite world on **Phaser**; agents walk, enter rooms, approach each other, driven by the agent architecture. [paper](https://dl.acm.org/doi/fullHtml/10.1145/3586183.3606763)
- **Phaser vs PixiJS** — Phaser = full game engine (tilemaps, physics, pathfinding, camera, input; official React+Vite+TS template). PixiJS = pure WebGL renderer, lighter, you orchestrate. [comparison](https://generalistprogrammer.com/comparisons/phaser-vs-pixijs) · [Phaser React template](https://phaser.io/news/2024/02/official-phaser-3-and-react-template)
- **Assets** — CC0/free pixel packs ([Kenney](https://kenney.nl), LPC, free [itch office packs](https://itch.io/game-assets/tag-office/tag-pixel-art)); maps via Tiled/LDtk.
- **"Aliveness"** — idle animation is king: mix short (2–4s) + long ambient (30–90s) loops, randomized fidget delays (2–8s), easing, routines, dense independent loops. [NPC animation guide](https://mocaponline.com/blogs/mocap-news/crowd-npc-animation-guide)

## Decisions (from Q&A)

| Area | Decision |
|---|---|
| Art style | **Isometric pixel-art** |
| Characters | **Cute chibi with faces** (expressions per state) |
| Mood / palette | **Neon cyberpunk command center** (evolve today's look) |
| Theming | **Fixed art, accent follows active dashboard theme** |
| FX | **Full juice** (glow, bloom, particles, lighting, event pops) |
| Render tech | **Recommend** → **Phaser 3** (game engine: tilemap + pathfinding + camera + official React/Vite/TS bridge). PixiJS is the lighter alternative. |
| Movement | **Hybrid** — desks + scripted handoff walks **and** free-roam walking (free-roam kept in v1) |
| Scope | **Full redesign** of the HQ scene |
| Office layout | **Single open-plan room** |
| Camera | **Fixed view of the whole office** |
| Agent placement | **Themed desk per agent**, auto-arranged |
| Agent count | **Dynamic up to ~12–15** (procedural desk layout) |
| Agent states | **All**: working, idle, sleeping, talking, thinking, error |
| Work actions | **All**: typing at desk, whiteboard/planning, walking handoffs, role-specific props |
| Mission choreography | **Active agent works + packet/courier walks on handoff** (off the real SSE stream) |
| Ambient life | **All**: idle fidgets, animated props, day/night + lighting, random micro-events |
| Click agent | **Open detail panel** (status, live step text, tokens, controls) |
| Controls | **All**: launch missions, pause/resume/cancel, manage agents, inject instructions |
| Bubbles | **Live speech/thought bubbles** (from mission step text) |
| Hover/select | **Highlight + tooltip; click selects + dims others** |
| Liveness | **Continuous live state** (stats poll + mission SSE) |
| Smoothness | **AI Town-style interpolation** (buffer + tween) |
| In-scene data | **All**: status+action, token/cost, current step text, office KPI overlay |
| Idle (no mission) | **Calm resting office** (agents doze/relax; light ambient + day/night) |
| Assets | **Free/CC0 packs + custom recolor/tweaks** |
| Performance | **Desktop-first + graceful mobile fallback** |
| Audio | **Optional ambient + event SFX, toggle, off by default** |
| Accessibility | **Honor prefers-reduced-motion (calm static fallback) + keyboard select** |
| v1 cut | **Everything in v1** (phased internally below) |
| North star | **"Control it like a game"** |

## Architecture & key choices

- **Render = Phaser 3**, embedded via the **official React + Vite + TS bridge** (an `EventBus` connects React ↔ the Phaser scene). Rationale: the owner wants free-roam walking, real-time choreography, and game-like control with *everything* in v1 — Phaser's built-in **tilemap, pathfinding (easystar.js), camera, input, tweens, particles, and Lights2D** dramatically cut custom work vs. hand-rolling on PixiJS, while still embedding cleanly as one dashboard page. **PixiJS/pixi-react** remains the lighter fallback if Phaser's bundle/àla-carte control becomes a problem; all scene code is isolated so the engine is swappable.
- **Hybrid React HUD + Phaser canvas.** The **scene/world** (room, desks, characters, walking, FX) lives in Phaser; the **HUD** (KPI overlay, agent detail panel, controls, modals, bubbles) stays **React** over the canvas. They communicate through the EventBus: Phaser emits `agent-clicked`/`agent-hover`/`scene-ready`; React emits `mission-update`/`select-agent`/`theme-accent`. This preserves all existing React control flows (`runMission`, `pause/resume/cancel`, `inject`, agent CRUD, `useMissionStream`).
- **Behavior state machine (frontend).** Each agent runs a state machine — `working · idle · sleeping · talking · thinking · error · walking` — fed by: mission SSE `activeAgentId` → that agent **types/works** + bubble shows `step_delta` text; `activeAgentId` change → a **courier/packet walks** the handoff to the next desk; no active mission + recent activity → **idle fidgets**; long idle → **sleeping**; `failed/blocked` → **error**. Ambient layer adds randomized fidgets, prop animation, day/night lighting (real clock), and scripted **micro-events** (coffee run, two agents meet, delivery) when calm.
- **Smoothness via interpolation** (AI Town pattern): buffer incoming state and **tween** positions/animations between sparse (1–2s) updates; walking uses an easystar path tweened tile-to-tile.
- **Theming:** fixed neon-cyberpunk art, but read the live CSS `--accent` (and theme tokens) and pass to Phaser as tint/glow so accents track the active dashboard theme.

## Backend work (`tobi/`) — light

Mostly reuse existing `agents`, `getOfficeStats`, missions, and the SSE stream. Minimal additions in `api/dashboard.py` + `core/database.py`:
- Optional `agents.character` (chibi sprite key) and persisted desk slot (or fully client-side auto-layout). Reuse existing `color`, `role`, `is_head`, `live.status`.
- (Optional) `GET /api/office/scene` that composes `{agents, positions, statuses, current_action, tokens}` server-side; **default plan composes this client-side** from existing `getAgents` + `getOfficeStats` + `useMissionStream` to keep backend untouched.
- No new mission APIs — control reuses `runMission`/`pauseMission`/`resumeMission`/`cancelMission`/`injectMission`/`createAgent`/`updateAgent`/`deleteAgent`.

## Frontend work (`tobi/dashboard/src/`)

1. **Deps** — add `phaser` + `easystarjs`; **lazy-load** the Office route so Phaser stays out of the main bundle. Confirm Vite build.
2. **Engine bridge** (`src/office/`): `PhaserGame.tsx` (mounts the game, exposes the EventBus), `EventBus.ts`, `scenes/OfficeScene.ts` (boot/preload/create/update), `scenes/Preloader.ts` (atlas/tilemap loading).
3. **World** — an isometric **single open-plan room** tilemap (Tiled/LDtk) with a walkable grid; **procedural themed-desk layout** for up to ~15 agents (role-styled props: research bench, code den, CEO desk); shared spots (whiteboard, coffee, lounge) as walk targets.
4. **Characters** — chibi spritesheet atlas with per-state animations (idle/typing/walk/sleep/talk/think/error) + facial expressions; recolored to each agent's `color`; nameplate + status pip; live **speech/thought bubble** rendering `step_delta` text.
5. **Behavior/anim systems** — `agentController.ts` (state machine + interpolation), `pathfinding.ts` (easystar), `ambient.ts` (fidgets/props/day-night/micro-events), `fx.ts` (glow/bloom/particles/lights, event pops, accent-from-theme).
6. **React HUD** (`pages/Office.tsx` rebuilt): restyled **KPI overlay**; **AgentDetailPanel** (status, live step text, tokens, controls); **agent management** modals (reuse existing create/edit); **performance-mode** + **audio** toggles; reduced-motion fallback view.
7. **Wiring** — `useMissionStream` → EventBus `mission-update` → scene choreography; `getOfficeStats` poll → KPI overlay + token counters; theme accent → `theme-accent` event.
8. **Audio** — optional ambient loop + event SFX via the existing `useSound` hook; off by default.
9. **A11y** — `prefers-reduced-motion` renders a calm static office (state icons, no walking/particles); keyboard tab/enter to select agents.

## Visual style (neon cyberpunk, full juice)

Dark iso room with neon rim-light desks, glowing screens, volumetric core glow, particle accents (data motes, coffee steam), Lights2D for pools of light, day/night tint from the real clock, subtle screen-shake/pop on mission start/finish. Accent color tracks the active theme. Pixel-art keeps it cheap to render.

## Performance & fallback

Desktop-first; lazy-loaded engine; pixel-art + sprite batching keeps it light. **Performance mode** strips bloom/particles and caps ambient loops. **Mobile fallback**: a simplified static office (or the current card layout) when the canvas would be too heavy / on small touch screens.

## v1 build phases (everything ships in v1, sequenced)

- **M1 — Scaffold:** Phaser+React bridge, iso room tilemap, procedural themed desks, fixed camera, neon base styling.
- **M2 — Characters + live state:** chibi atlas + state animations, wire `useMissionStream`/`getOfficeStats`, detail panel, bubbles, KPI overlay, controls.
- **M3 — Motion + choreography:** easystar pathfinding, handoff courier walks, idle→sleep, micro-events, interpolation.
- **M4 — Juice + polish:** full FX/lighting/day-night, accent-follows-theme, audio toggle, performance mode, reduced-motion + keyboard, mobile fallback.

## Verification (end-to-end)

1. `cd tobi/dashboard && npm run dev` → open Office: iso room renders with a themed desk per live agent; main bundle stays lean (engine lazy-loaded).
2. Launch a mission (existing flow): the active agent plays **typing/working** with a live bubble of real step text; on handoff a **courier walks** to the next desk; tokens/KPIs update live; finish triggers an event pop.
3. Idle with no mission → **calm resting** office (dozing agents, ambient props, day/night tint); a scripted micro-event fires occasionally.
4. Click an agent → **detail panel** with status/step text/tokens + working **controls** (pause/resume/cancel/inject); hover highlights + tooltip and dims others.
5. Switch dashboard theme → office **accent** retints; toggle **performance mode** (FX strip) and **audio**; enable OS reduced-motion → calm static fallback; tab/enter selects agents.
6. `cd tobi/dashboard && npm run build` clean (Office route code-split).

## Risks / watch-items

- **Bundle size** — Phaser is sizable; lazy-load the route, keep it out of the main chunk, verify build budget.
- **Engine lock-in** — isolate all scene code behind `PhaserGame`/EventBus so a PixiJS swap stays contained if needed.
- **Asset licensing** — stick to CC0/clearly-licensed packs; track sources; recolor rather than redistribute restricted art.
- **Scope ("everything in v1")** — large UI build; the M1–M4 phasing keeps it shippable incrementally without cutting features.
- **Readability vs. juice** — full FX can hurt legibility; keep a calm baseline + performance mode, and lean on clear state pips/bubbles.
- **Reuse, don't rebuild** — preserve the existing mission stream, KPI overlay intent, and agent/mission control APIs; this is a re-skin + behavior layer, not a backend rewrite.

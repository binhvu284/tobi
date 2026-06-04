# Phase 1 — Ability Module: Completion Note

**Date:** 2026-06-02 · **Scope:** all of Mission Control Module 1 (spec §3) that does **not**
depend on Hermes. The live self-evolution loop is the gated Phase 1.5 (see bottom).

Plan: `~/.claude/plans/currently-the-mission-control-goofy-widget.md`. Spec: `MISSION_CONTROL_SPEC.md` §3 + §9.

---

## What shipped

### Premium "Ability" page (replaces the flat capability grid)
`dashboard/src/pages/Ability.tsx` — full rewrite into an RPG character sheet:
- **Tobi Power Level hero** — aggregate XP bar + rank ladder (Dormant → Awakening → Apprentice →
  Operator → Apprentice Jarvis → Jarvis) + level + active/auto/config counts. `[D1][D10]`
- **Compare** — pick 2–3 abilities, overlay them as a **Radar ⟷ grouped-Bars toggle**. `[D11]`
- **Categorized grid** (Communication / Building / Strategy / Learning) — cards with overall XP
  bar, 4 dimension values, level badge, status, token-cost meter, provider logos, "+ compare". `[D12]`
- **Right-side detail panel** — overall + 4 labelled dimension bars, token meter, description,
  trigger, example, **how to level up**, **limitations & guardrails**, **live usage stats**,
  **version history**, and a **coach** box. `[D12][D55]`
- Live poll every **45s**, non-blocking: the page renders curated values even if the API is down. `[D15]`

### New reusable components
- `dashboard/src/components/StatBar.tsx` — gamified 0–100 XP/power bar (gradient + sheen + ticks),
  `sm`/`lg`. Distinct from `HealthBar` (which keeps its health tiers).
- `dashboard/src/components/RadarChart.tsx` — dependency-free SVG radar, overlays 2–3 series.

### Skill registry + governance (backend)
`core/database.py` — new tables via the existing `init_database()` migration idiom, seeded with the
12 abilities:
- `skills` (L1 record / metadata `[D3][D4]`), `skill_metrics` `[D14][D44]`, `skill_deps` `[D50]`,
  `skill_versions` (keep-all ledger `[D54][H15]`), `skill_proposals` (approval inbox `[D13][D48]`).

`api/dashboard.py` — new read + governance endpoints (before the SPA catch-all):
- `GET /api/abilities` — live usage per ability, from existing tables + env-only integration check.
  Fast, no LLM/network; sparse by design (missing key ⇒ curated-only on the frontend). `[D16]`
- `GET /api/abilities/{id}` — registry record + metrics + version history + deps. `[D16]`
- `POST /api/abilities/{id}/coach` — owner coaching → lesson + **queued pending proposal** (no
  autonomous apply). `[D8][H11]`
- `GET /api/proposals` · `POST /api/proposals/{id}/approve|reject` — evolution inbox; **approve**
  writes a new immutable `skill_versions` row + bumps the active version pointer. `[D13][D48]`
- `POST /api/abilities/{id}/rollback/{version}` — **rollback** = copy a prior version's body into a
  new forward version (append-only ledger; never mutates history). Exposed in the detail panel's
  version list. Works fully **without** Hermes. `[D54][H15]`

`dashboard/src/api.ts` — `getAbilities`, `getAbilityDetail`, `coachAbility`, `getProposals`,
`approveProposal`, `rejectProposal` + types.

---

## How to run / verify

```bash
npm --prefix dashboard run build          # tsc + vite, no new deps → green
python main.py api                        # or: uvicorn api.dashboard:app
curl localhost:8080/api/abilities         # live counts from the real DB (sparse-safe)
curl localhost:8080/api/abilities/coding  # record + metrics + versions
```
Open `/ability`: hero + rank, categorized cards with XP bars + token meters, radar↔bars compare
(2–3), detail panel with all fields, Evolution inbox. Coach an ability → it appears in the inbox →
Approve → a new version row is written and the active version bumps.

**Verified this session:** build green; all endpoints exercised (read, coach→proposal,
approve→v2 + pointer bump, reject, double-approve→409, rollback v1→new version, bad-version→404);
`python main.py api` confirmed serving `/api/abilities` + the SPA; Playwright screenshots of hero,
radar overlay (3 series, axis labels un-clipped after an `overflow:visible` fix), bars mode, detail
panel, and the coach→inbox→Approve/Reject round-trip. Test rows were cleaned from the DB afterward.

> **⚠️ Live instance needs a restart.** `python main.py start` was already running (PID seen this
> session) with the *old* Python — so the new `/api/*` routes 404 until that process restarts
> (the rebuilt `dist` is served immediately, so the page loads but the detail panel / live usage /
> coach / Evolution inbox stay inert until restart). Restart the tmux `main.py start` process to
> activate Phase 1. (Not auto-done here: `main.py start` sends outward-facing Telegram messages.)
> Note: the live instance's DB is `/workspaces/tobi/.tobi/agent.db`; `init_database()` seeds the
> skill tables there on startup.

---

## Deferred / gated (NOT in Phase 1)

- **Phase 1.5 — live Hermes self-evolution loop.** The autonomous *generator* behind the proposals
  inbox is stubbed; proposals come from owner coaching / manual creation only. Wiring it to the real
  Hermes (`skill_self_improve.md`, `hermes memory`, prose-only auto-gen `[H8]`, shadow→evidence
  promote `[H7][D9]`, body source-of-truth flip to the Hermes `.md` `[H12]`, de-root + scrubber
  `[H14]`) is **gated behind the H19 verify-first spike** — `docs/HERMES_SPIKE_RUNBOOK.md`, which
  **Thomas runs on the VPS**. The spike wins on any conflict with §9.
- **Phase 2 — Office module** (spec §4): real agent registry, missions, workflows, `llm_usage`,
  replacing the hardcoded `/api/agents` and the fake CPU/MEM `SystemOverlay`.

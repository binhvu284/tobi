# Phase 2 — The Office Module: Completion Note

**Date:** 2026-06-02 · **Scope:** the happy-path of Mission Control Module 2 (spec §4) — a real
multi-agent office with a working, deterministically-verifiable mission engine. The rich
orchestration behaviors are explicit follow-ons (listed at the bottom), kept out of scope on
purpose and documented honestly.

Plan: `~/.claude/plans/currently-the-mission-control-goofy-widget.md`. Spec: `MISSION_CONTROL_SPEC.md` §4.

---

## What shipped

### Data model (`core/database.py`, via `_ensure_office_schema()`)
- `agents` — persona + per-agent model binding + perms + budgets (D22/D25/D26). **D37: the API key
  is referenced by env-var *name* (`key_ref`), never stored as a secret.**
- `agent_state` (D64), `missions` (D57 priority, D61 pinned workflow version, D69 summary),
  `mission_steps` (D64, artifact_ref D67), `workflows` (named + versioned, D61),
  `llm_usage` (per-agent/mission/provider, D34).
- **Seed (D60):** roster = Tobi (head) + Sunday (research/Gemini) + Alphabet (evaluator/GPT) +
  Friday (coder/Opus), all editable; default `standard_delivery` workflow = Sunday→Alphabet→Friday.

### Mission engine (`core/office.py`)
- `run_mission()` — linear, **hub-and-spoke** orchestration (D31/D68): each step gets the accumulated
  prior outputs as Tobi-mediated context; sub-agents never call each other. Writes a `mission_steps`
  row + an `llm_usage` row per step, then Tobi writes a close-out summary (D69). Idempotent re-run.
- `MockLLMClient` — deterministic offline stand-in (canned text + synthetic token counts). Makes the
  whole engine verifiable with **zero keys/network/cost**, and is the only way to get non-zero token
  numbers for the D34 ledger (real free models cost $0). `make_client()` auto-falls back to mock when
  a provider has no client or the `key_ref` env var is absent — a mission always runs, never half-fails.
- Built on the existing `core.model_router.BaseLLMClient` (OpenRouter/Claude) for real providers (D36).

### Backend APIs (`api/dashboard.py`)
- **Registry (replaces the old hardcoded `/api/agents`):** `GET /api/agents` (list + derived live
  block), `GET /api/agents/{id}` (+ empirical scorecard D28), `POST`/`PATCH`/`DELETE` (soft-archive,
  blocks the head + busy agents, D59).
- **Missions:** `GET /api/missions` (board), `GET /api/missions/{id}` (+ steps + usage rollup),
  `POST` (create, pins active workflow version), `PATCH` (status/priority D57),
  `POST /api/missions/{id}/run?mock=` (threadpool so sync LLM calls don't block the loop).
- `GET /api/workflows`; `GET /api/office/stats` — **org KPIs + `check_all()` integration health**,
  the real signals that replace the page's old fake CPU/MEM/NET overlay (D43).

### Frontend (`dashboard/src/pages/Office.tsx` rebuild)
- Kept the pixel-art HQ aesthetic but **driven by the registry**: the 4-quadrant scene uses each
  agent's real name/role/color/sprite/live-status; in-world HUD shows real provider/model/status.
- **HQ ⟷ Ops toggle** (D38). **Ops** = KPI strip + **roster** (agent cards, D40) with an **agent
  config builder modal** (create/edit/archive, D27) + **mission board** (create → run → detail panel
  with steps timeline, cost-by-agent, and Tobi's close-out, D41).
- Ripped out the fake `SystemOverlay` (CPU/MEM/NET) and hardcoded "Health: Optimal"; replaced with
  the real org-status + integration-health panels (D43).
- `api.ts`: agent CRUD, missions, run, workflows, office stats + types.

---

## How to run / verify

```bash
npm --prefix dashboard run build          # tsc + vite → green
python main.py api                        # dashboard on :8080
curl localhost:8080/api/agents            # 4 seed agents + live status
curl -X POST localhost:8080/api/missions -H 'Content-Type: application/json' \
     -d '{"title":"demo","goal":"prove it","priority":"High"}'
curl -X POST 'localhost:8080/api/missions/<id>/run?mock=true'   # deterministic, offline
curl localhost:8080/api/office/stats      # org KPIs + integration health
```
Open `/office`: **HQ** shows the scene + real Org-Status/Integrations panels; **Ops** shows the
roster + mission board. Create a mission → Run (mock) → watch the 3 steps, cost-by-agent, and Tobi's
close-out populate; KPIs update.

**Verified this session (against the real DB `/.tobi/agent.db` via `.env DB_PATH`):** schema + seed;
registry CRUD; a full mission run through the API *and* through the UI (create → run → 3 steps
Sunday→Alphabet→Friday → `llm_usage` per agent → close-out → live KPI update); office stats; build
green; Playwright screenshots of HQ, Ops, and a completed mission. All test rows cleaned afterward.

> **⚠️ Live instance needs a restart** to serve the new Python routes (the rebuilt `dist` is served
> immediately on reload, but `/api/agents` changes shape + the missions/stats routes are new). The
> live `python main.py start` must restart. Not auto-done here (it sends outward-facing Telegram).

---

## Follow-ons (deliberately NOT in this first cut)
- **Orchestration depth:** validation gates (D32), retry/backoff → escalate → circuit-breaker (D33),
  parallel missions + 1-task/agent concurrency caps (D56), priority scheduling + owner bump (D57),
  mid-mission inject / live steering (D58), dynamic Tobi planning beyond fixed templates (D30).
- **Secrets (D37):** real encrypted key store + rotation UI. Today: env-var key *names* only
  (no secret ever stored/sent/logged) — intentionally not a half-built crypto layer.
- **Close-out send (D69):** Telegram delivery via the single Hermes gateway bot (H16). Today the
  summary is recorded; `_notify_closeout()` is a no-op so verification never sends outward.
- **Artifacts (D67):** `mission_steps.artifact_ref` column exists; the on-disk artifact store +
  Deliverables UI are not wired yet.
- **Realtime (D42):** SSE stream; today the Office polls every 10s.
- **Workflow editor (D61):** versioned templates exist + are pinned per mission; the fork/clone UI
  is a follow-on (one seeded workflow today).

# Mission Control — Master State & Specification Document

> **Status:** Phase 1 (Requirements) COMPLETE — 69 core decisions (D1–D69) + 20 Hermes
> integration decisions (H1–H20) = **89 locked decisions.**
> (Module 1 Ability: D1–D21, D44–D55 = 33; Module 2 Office: D22–D43, D56–D69 = 36;
> Hermes bonus round: H1–H20.) Question floor satisfied: ~33 questions for Module 1,
> ~34 for Module 2, 20 for the Hermes round (all clear the ≥30/round intent).
> **Phase 2:** Office module — not started. This document is the portable handover: paste it
> into a fresh session and begin coding with zero context loss. See **§9 Hermes Integration
> Addendum**.
>
> **BUILD STATUS (2026-06-02):**
> - **Phase 1 — Ability module: BUILT** (non-Hermes scope). Premium RPG Ability page + skill
>   registry tables + read/governance/coach APIs + evolution UI (proposals inbox, version ledger,
>   coach→approve→new-version). Verified: build green, endpoints live, screenshots. See
>   `docs/PHASE_1_ABILITY_COMPLETE.md`.
> - **Phase 1.5 — live Hermes self-evolution loop: GATED** behind the H19 verify-first spike
>   (`docs/HERMES_SPIKE_RUNBOOK.md`, Thomas runs on the VPS). Not started.
> - **Phase 2 — Office module: BUILT (2026-06-02), happy-path.** Real agent registry (replaces the
>   hardcoded `/api/agents`), missions + versioned workflows + `llm_usage`, a linear hub-and-spoke
>   mission engine (Sunday→Alphabet→Friday) verifiable offline via a mock LLM client, and an
>   Office rebuild (registry-driven HQ scene + Ops roster/mission-board) with **real org KPIs +
>   integration health replacing the fake CPU/MEM overlay (D43)**. Rich behaviors (D32/D33/D56–D58)
>   + encrypted secret store (D37) + real Telegram close-out send (D69) are documented follow-ons.
>   See `docs/PHASE_2_OFFICE_COMPLETE.md`.
> - **Phase 3 — Gaming-grade UI/UX overhaul: BUILT (2026-06-03).** Office=2D cyberpunk cockpit; all
>   other pages=high-tech SaaS on an **8-theme CSS-variable system** (Settings page, channel-triplet
>   tokens, sans UI + mono data). New **AppShell** (responsive sidebar→drawer+bottom-tabs, top status
>   bar, **⌘K command palette**, route transitions, **toasts + bell inbox**, opt-in UI sound). New
>   **Control Room** + `/api/run/*` triggers (key-prechecked, graceful, mock/dry-run) + Dashboard
>   **launchpad + activity feed + reorderable/hideable widgets**. **Deferred:** SSE (polling+toast
>   used), Task list-rewrite (board auto-themed), resizable/saved-layouts customization. See
>   `docs/PHASE_3_UIUX_COMPLETE.md`.
>
> **Owner:** Thomas (supreme authority). **Head agent:** TOBI. **Date:** 2026-06-01.

---

## 0. How to use this document

This is the single source of truth for the **Mission Control upgrade**: two new/rebuilt
modules — **Ability** (Tobi's capabilities + self-evolution) and **The Office** (multi-agent
orchestration). Every decision is tagged `Dn` and listed in the **Decision Log** (§7) for
traceability. When a section says "decided," it is frozen unless Thomas reopens it.

**Read order for an implementer:** §1 Vision → §2 Glossary → §3 Module 1 → §4 Module 2 →
§5 Cross-cutting → §6 Phasing → §7 Decision Log → §8 Open Questions.

**Codebase guardrails (inherited, non-negotiable):**
- Never commit/paste `.env` values — reference key **names** only.
- Code is the source of truth over docs; if they disagree, trust code and update docs.
- Don't auto-launch `main.py start` (sends outward-facing Telegram messages).

---

## 1. Vision recap

Mission Control is the visual cockpit for turning Tobi into a **personal Jarvis**. Two pillars:

- **Module 1 — Ability:** a data-driven, RPG-style view of *what Tobi can do*, plus a
  **self-evolution engine**: when Tobi meets a task beyond his current skills, he can create
  or improve a skill (under owner-governed gates).
- **Module 2 — The Office:** a visual "company" where **Tobi is the head agent** orchestrating
  a roster of specialized sub-agents (e.g. Sunday=research/Gemini, Alphabet=evaluator/GPT,
  Friday=coder/Opus). Authority chain: **Thomas → Tobi → sub-agents.**

The two modules share **one power language** (the 4 dimensions) and **one skill abstraction**
(agents own skills), so they compose into a single coherent system.

---

## 2. Glossary

| Term | Meaning |
|------|---------|
| **Skill / Ability** | A capability, modeled as a unified 4-layer object (see §3.2). |
| **Agent** | A persistent persona that owns skills + a bound LLM + permissions (§4.1). |
| **Mission** | A goal Tobi orchestrates across agents via a workflow (§4.3). |
| **Workflow** | An ordered graph of steps (a Layer-3 composite skill) run during a mission. |
| **Gate** | An approval/validation checkpoint between steps or before an action. |
| **Power dimensions** | Autonomy, Reliability, Speed, Impact — each 0–100. |
| **Tier** | A skill's maturity band: Core / Learned / Experimental. |
| **Blackboard** | The shared per-mission context agents read/write through. |

---

## 3. MODULE 1 — ABILITY

> **BUILT (Phase 1, 2026-06-02), non-Hermes scope.** Code: `dashboard/src/pages/Ability.tsx`
> (rewrite), `dashboard/src/components/StatBar.tsx` + `RadarChart.tsx` (new), `api/dashboard.py`
> (`GET /api/abilities`, `GET /api/abilities/{id}`, `POST /api/abilities/{id}/coach`,
> `GET /api/proposals`, `POST /api/proposals/{id}/approve|reject`,
> `POST /api/abilities/{id}/rollback/{version}`), `core/database.py`
> (`skills`/`skill_metrics`/`skill_deps`/`skill_versions`/`skill_proposals` + 12-skill seed),
> `dashboard/src/api.ts` (clients/types). The **autonomous generator** behind the proposals
> inbox is intentionally stubbed (owner-coached + manual proposals only); the live Hermes
> generator is the gated Phase 1.5. See `docs/PHASE_1_ABILITY_COMPLETE.md`.

### 3.1 Power model `[D1]`
Each ability is scored on **four dimensions, 0–100**: **Autonomy, Reliability, Speed, Impact**,
plus a derived **overall = round(mean(4 dims))**.

Derived helpers:
- `level(score) = clamp(ceil(score/20), 1, 5)` → Lv 1–5 badge.
- `aggregate = mean(overall of all abilities)` → drives the hero "Tobi Power Level."
- `rank(aggregate)` via thresholds: 0–20 **Dormant**, 21–40 **Awakening**, 41–55 **Apprentice**,
  56–70 **Operator**, 71–89 **Apprentice Jarvis**, 90–100 **Jarvis**.

### 3.2 Skill abstraction — unified 4-layer model `[D3]`
A skill is **one object expressed across four layers**; Tobi self-creates at the *cheapest
sufficient layer*:

1. **L1 — Record (always exists):** DB/YAML row — `name, instructions/prompt, allowed tools,
   model binding, metrics, tier, category, token_cost`.
2. **L2 — Executable (optional):** a sandboxed code module when prompt-config can't do the job.
3. **L3 — Composable:** a workflow DAG of other skills (this is how `research→validate→build`
   becomes one higher-order skill — and how Office workflows are defined, §4.3).
4. **L4 — Capability flag:** the skill surfaces as a permission granted to an agent (§4.1),
   gating *who* may invoke it.

**Dependencies `[D50]`:** an L3 composite **pins the specific child versions** it was built on.
If a child is missing, the parent is **blocked** (won't run) and flagged; if a child changes, the
parent is **re-validated** (re-smoke-tested) before it's trusted again. Dependency edges are stored
so the evolution engine knows the blast radius of any change.

### 3.3 Data source `[D2]` `[D44]`
**Hybrid:** hand-curated baseline dimension values, with **live DB usage overlaid** where it
exists. The page renders curated values even if live data is absent.

**Per-dimension provenance `[D44]`:** **Reliability** and **Speed** are **live-measured** from
real run history (success-rate → Reliability; measured latency → Speed); **Autonomy** and
**Impact** stay **curated** (judgment calls Tobi can revise via the evolution loop). This keeps
the empirical dims honest and the subjective dims stable.

### 3.4 Taxonomy `[D4]`
Group by **tier band** (origin/maturity), not topic:
- **Core** — hand-built, trusted (chat, coding, research, ceo, …).
- **Learned** — Tobi-created, promoted on evidence (e.g. price_scraper).
- **Experimental** — new/unverified, sandboxed.

### 3.5 Self-Evolution Engine

> **Hermes-powered (see §9):** this engine is **not built from scratch** — it instruments and
> governs the self-evolution Hermes already provides (`skill_self_improve.md` + `hermes memory`,
> `[H9]`). Read §9.2–9.4 alongside this section; H-decisions refine every rule below.

**Triggers `[D6]` (ALL active):**
1. Task failure / capability gap, 2. Scheduled self-review (cron), 3. Owner command,
4. Metric-threshold breach (e.g. reliability < 60).
The **self-review schedule is owner-configurable `[D49]`** (cadence + on/off) in settings —
Thomas tunes how aggressively Tobi introspects.

**Gap detection `[D7]` — hybrid reflect → confirm:** a post-failure LLM step classifies the
cause; if "missing skill," it's cross-checked against the registry to confirm no existing skill
covers it before a proposal is raised.

**Create gate `[D5]` + tiered approvals `[D48]`:** Tobi may **autonomously** create/edit L1
prompt-config and L3 compositions; **L2 code modules require Thomas's approval** before they load.
Generalized as a **risk-tiered approval policy `[D48]`:** Tobi auto-approves **low-risk** actions
(new L1 skill, prompt tweak, compose existing trusted skills); **high-risk** actions (new
executable code, granting new tools/permissions, promotion to Core) route to **Thomas's approval
inbox**. Risk tier is an explicit attribute on each proposal.

**Authoring `[D52]`:** Tobi **auto-generates** skill definitions — it writes the `skills.yaml`
entry (name, instructions, tools, model, tier) itself with **no creation gate at L1**; the entry
is fully **editable later** by Thomas. (L2 code still hits the D48 high-risk gate.)

**Improve loop `[D8]` — owner-coached refinement:** Thomas's feedback notes (in The Office) are
folded into the skill's prompt → new version (v2, v3…).

**Promotion `[D9]`:** Experimental→Learned is **automatic on evidence** (≥3 clean real runs);
**Learned→Core requires Thomas's approval.**

### 3.6 Lifecycle, Safety & Governance
- **Sandbox `[D18]`:** generated L2 code runs in an isolated **subprocess** (timeout, no
  `.env`/secrets) against a **smoke test**; only on pass does it enter the approval queue;
  only on Thomas ✅ does it become loadable.
- **Recovery `[D19]` (all):** per-skill **kill-switch** (instant disable) + **version rollback**
  (versions immutable, restorable) + global **safe-mode** freeze + **auto-demote** on metric breach
  (Core→Learned→disabled).
- **Mid-run change `[D46]`:** a skill change/disable while it is in use **lets the current run
  finish** (no yank mid-execution); disabling a skill that a **running mission** depends on raises
  a **blocking warning** that names the affected mission and requires explicit confirmation before
  it takes hold for future runs.
- **Retirement `[D47]`:** retiring a skill is a **soft-archive** by default (hidden from active use,
  history/versions/metrics preserved, restorable). **Hard-delete is owner-only and gated behind a
  confirmation alert** that lists what depends on it.
- **Audit `[D20]`:** full provenance per action (actor, trigger, before/after diff, metric delta,
  timestamp, rationale); Tobi states a justification Thomas can **veto** before autonomous actions
  commit.
- **Cost guard `[D21]`:** daily **token budget** for the engine + per-skill **cooldown**
  (e.g. 7 days) + **Telegram alert** on every autonomous action; over budget → engine pauses.
- **Notifications `[D51]`:** Telegram is the owner's live channel for **all autonomous actions
  AND all pending approvals** — Tobi pushes a message when it acts autonomously and when it needs
  Thomas to approve/reject (the D48 high-risk gate is actionable from Telegram + the inbox).

### 3.7 UI/UX
- **Hero `[D10]`:** aggregate **"Tobi Power Level"** XP bar + **rank title** + Lv, with a compact
  **all-abilities mini-radar** beside it.
- **Compare `[D11]`:** select 2–3 abilities → overlay on a **radar**, toggle to **grouped bars**
  for exact per-dimension values.
- **Cards `[D12]`:** **full RPG character cards** — XP gradient power bar, Lv1–5 badge,
  tier glow, 4 dimension pips, **token-cost meter `[D45]`**, provider logos.
- **Token-cost model `[D45]`:** the cost indicator = **model tier × measured token volume**
  (the skill's bound model's price band multiplied by its observed avg tokens/run), surfaced as a
  Low/Med/High meter with the underlying estimate on hover.
- **Evolution surface `[D13]` (all):** **proposals/approval inbox** (the D5/D9/D48 gates) +
  **NEW/EVOLVED badges** on cards + **evolution timeline/changelog** + **per-skill version history**
  in the detail panel.
- **Version diff view `[D55]`:** version history renders a **detailed, easy-to-understand** diff —
  a readable **text diff** of the prompt/config, the **metric delta** (e.g. Reliability +8), a
  **plain-language change summary**, and **provenance** (actor/trigger/timestamp). No raw JSON dumps.
- **Cold start `[D53]`:** before any data exists, the page shows a **guided empty state**
  ("Your abilities will power up as Tobi works." + a **[Start a task]** CTA), not blank cards.
- **Detail panel:** icon+name, rank/level, overall XP bar, 4 labeled dimension bars, token-cost,
  description, trigger, example output, **how-to-level-up**, **limitations & guardrails**, live
  usage stats, powered-by logos, version history (with the D55 diff view).

### 3.8 Backend & Persistence
- **Storage `[D14]`:** **git-tracked YAML** for curated skill defs (`skills.yaml`, diff-able,
  human-editable; **Tobi auto-writes entries per D52**) + a DB **`skill_metrics`** table for the
  live overlay. Versions/proposals in DB.
- **Version retention `[D54]`:** **every version row is kept forever** (its diff + metric delta +
  provenance), so history/rollback never lose fidelity; only the **large old prompt bodies are
  compressed/pruned** to bound storage — the audit trail stays complete, the bulk shrinks.
- **Live metrics `[D15]`:** **cached snapshot + on-read fallback** — serve cache, recompute on
  read if stale beyond **TTL ~5 min**.
- **API `[D16]`** (FastAPI, `api/dashboard.py`, before the SPA catch-all):
  ```
  GET  /api/abilities                     # list + live metrics + aggregate/rank
  GET  /api/abilities/{id}                # detail + versions + usage
  POST /api/abilities/proposals           # Tobi raises create/improve/promote proposal
  POST /api/abilities/proposals/{id}/approve | /reject
  POST /api/abilities/{id}/coach          # owner-coached refinement note
  ```
- **Integration `[D17]`:** **v1 = descriptive mirror** of existing engines (coding→`executor`,
  research→`research`, chat→`telegram_bot`), linked by a stable `usageKey`/`agent_key` for metric
  joins. **Target state (documented, not built v1): registry-as-dispatcher** — engines become
  skill implementations resolved through the registry. Migration steps to be enumerated in Phase 2.

### 3.9 Suggested seed abilities (~12)
Communication: `chat`, `reports`, `telegram` · Building: `coding`, `terminal`, `executor` ·
Strategy: `research`, `ceo`, `tracker` · Learning: `learning`, `memory` (+1 spare).
(Topic tags retained as metadata; primary grouping is by tier per D4.)

---

## 4. MODULE 2 — THE OFFICE

> **BUILT (Phase 2, 2026-06-02), happy-path scope.** Code: `core/database.py`
> (`agents`/`agent_state`/`missions`/`mission_steps`/`workflows`/`llm_usage` + D60 seed roster +
> default `standard_delivery` workflow), `core/office.py` (mission engine + `MockLLMClient` +
> per-agent provider binding on `model_router`), `api/dashboard.py` (real `/api/agents*` CRUD,
> `/api/missions*` + `/run`, `/api/workflows`, `/api/office/stats`), `dashboard/src/pages/Office.tsx`
> (registry-driven HQ scene + Ops roster/mission-board, real KPIs + integration health), `api.ts`.
> **Follow-ons (scaffolded, not built):** validation gates (D32), retry/escalate/circuit-breaker
> (D33), parallel missions + concurrency caps (D56), prioritization scheduling (D57), mid-mission
> inject (D58), encrypted secret store + rotation (D37 — currently env-var key *names* only), real
> outward Telegram close-out send (D69 — summary recorded, send is a no-op). See
> `docs/PHASE_2_OFFICE_COMPLETE.md`.

### 4.1 Agent identity, hierarchy & authorization
- **Agent = persona that owns skills + a model `[D22]`:**
  `{ id, name, role, avatar, persona/system-prompt, model-config, skills[], permissions, budgets }`.
  Skills (Module 1) are shared capabilities; agents are the "who."
- **Lifecycle `[D23]`:** **persistent named roster** — durable agents (Sunday, Alphabet, Friday)
  that live in the org chart and **accrue stats/history** across many tasks.
- **Bootstrapping `[D60]`:** first run ships a **seeded starter roster** pre-wired to existing
  engines — **Sunday** (research / Gemini), **Alphabet** (evaluator / GPT), **Friday** (coder /
  Opus), under **Tobi** the head agent — all fully **editable/removable**. No empty Office on day one.
- **Offboarding `[D59]`:** deleting/disabling a busy agent is **blocked behind a confirmation**
  that lists its running + queued missions; on confirm, Tobi **reassigns** them to a capable agent
  (or pauses them) and the agent is **soft-archived** (scorecard/history preserved) — never
  hard-erased while it holds work. Ties to the mid-mission rules in §4.3.
- **Principals `[D66]` — single owner:** **Thomas is the sole human principal, hardcoded** as root
  authority. No multi-user/role plumbing in scope (simplest auth; a future teammate would be a
  deliberate refactor). This resolves the dashboard-auth open question: URL-as-secret is acceptable
  for one owner.
- **Authority `[D24]` — grants + approval gates (defense in depth):** each agent holds a scoped
  **grant set**; Tobi can grant only a **subset** of his own authority downward; Thomas holds the
  root grant over Tobi. Actions **beyond** an agent's grant **escalate for approval**.
- **Permission dimensions `[D25]` (all configurable):** model & tool/skill access · spend/token
  budget · autonomy level (auto-run / propose-only / read-only) · can-spawn/can-delegate.

### 4.2 Agent configuration & model binding
- **Model binding `[D26]` — per-agent full LLM config:**
  `{ provider, model, endpoint, temperature, max_tokens, key_ref }`.
- **Routing `[D29]` — fixed primary + global safety fallback:** each agent has one declared model;
  a single system-wide fallback catches total provider outages.
- **Config UI `[D27]` — full builder form/modal:** create/rename via a form (name, role, avatar,
  persona, model, skills, permissions, budgets) — the "hire & configure an employee" flow.
- **Strength `[D28]` — dual view:** the **4 power dimensions** (RPG radar, comparable, rolled up
  from owned skills + the agent's task record) **AND** an empirical **scorecard** (tasks done,
  success-rate, avg latency, cost/task, owner rating).

### 4.3 Inter-agent orchestration
- **Pattern `[D30]` — hybrid templates + dynamic:** Tobi runs a **predefined workflow template**
  (a Layer-3 composite skill) when one matches the goal; otherwise he **plans dynamically** (LLM
  decomposition + runtime delegation, re-planning on results).
- **Communication `[D31]` + delegation depth `[D68]` — blackboard + Tobi-mediated (hub-and-spoke):**
  a shared per-mission **context/blackboard** all agents read/write; **Tobi brokers every handoff**
  (decides the next reader & dispatches). **Sub-agents never call each other directly** — every
  transition is `agent → Tobi → agent`, so Tobi sees/logs all of them and `can-spawn` (D25) is
  effectively **reserved for Tobi**. Cleanest authority + audit story.
- **Validation `[D32]` — configurable gates per workflow:** each step declares its gate type —
  `auto | evaluator(pass/fail+loop) | scored(threshold) | owner`. (E.g. Alphabet rejects → loops
  back to Sunday up to N retries → passes → Friday.)
- **Failure `[D33]` — all:** bounded **retries w/ backoff** → **escalate** (agent→Tobi re-plan→
  Thomas) → **circuit-breaker + budget cap** to stop runaway loops/spend (ties to Module-1 safe-mode).

**Mission execution & concurrency:**
- **Concurrency `[D56]` — parallel, capped per agent:** multiple missions run at once, but **each
  agent works one task at a time** (further work for a busy agent queues behind its current task).
  A **global concurrency cap** + the budget guard prevent runaway parallelism/spend.
- **Prioritization `[D57]` — priority + FIFO tiebreak:** each mission carries a priority
  (**Low/Normal/High/Urgent**); higher priority jumps the queue, ties run in submission order, and
  Thomas can **bump** a queued mission up/down.
- **Mid-mission injection `[D58]` — live steering:** Thomas (or Tobi) can inject new
  instructions into a **running** mission; small additions fold into the active agent's context at
  its next step, large scope changes **pause + re-plan**. Tobi acknowledges and adapts in-scene.
- **Workflow templates `[D61]`:** workflows (L3 composites) are **named, versioned, reusable
  templates**; editing **forks a new version**, a **running mission pins the version it started
  on**, and templates can be **cloned/forked**. (Stored in `workflows.definition_json` with version
  history.)
- **Artifacts `[D67]`:** mission deliverables (reports, generated code, files) are written to an
  **artifact store** — `~/.mmo_agent/artifacts/{mission_id}/` — and referenced by
  `mission_steps.artifact_ref`; the mission view shows a **"Deliverables" list** with view/download
  (and links out for things like a PR).
- **Definition of done `[D69]`:** a mission **completes when its final step's gate passes**; Tobi
  then writes a **close-out summary** (goal, what each agent did, deliverables, total cost) and
  **notifies Thomas via Telegram + the mission board**. Thomas can **reopen** a closed mission.

### 4.4 External LLM API handling
- **Cost tracking `[D34]` — per-agent + per-mission + per-provider:** every call logs to an
  **`llm_usage`** table `(call_id, agent, mission, provider, model, in_tok, out_tok, cost, ts)`;
  rolls up by agent/mission/day. Feeds budgets (D25) and Module-1 cost guards (D21).
- **Rate limits `[D35]` — full:** per-provider **concurrency caps** + request **queue** +
  exponential **backoff** on 429/5xx + **fallback** to the global model when a provider is exhausted.
- **Fallback cost attribution `[D62]`:** when D29 fallback fires, the spend is billed to the
  **originating agent + mission as ordinary spend** (no separate ops budget, no special usage tag),
  **but Tobi records a lesson-learned note** on each fallback (which agent/model failed, why) so the
  self-learning loop (Module 1 `lessons`) can act on chronic provider/model weakness.
- **Provider abstraction `[D36]` — unifying SDK (LiteLLM-style):** one `completion(model, msgs, …)`
  interface normalizing OpenAI / Google / Anthropic. *(Implementation note: vet the chosen lib's
  limits; wrap it behind a thin internal interface so it can be swapped.)*
- **Secrets `[D37]` — encrypted key store in DB + master key from env, rotate via UI.**
  **Hard constraints (to honor the guardrail):** the master decryption key lives **only** in
  `.env`/Codespaces secrets (never git); the ciphertext DB file is **git-ignored**; decrypted
  values are **never logged or returned by any API**; UI shows only configured/missing status.

### 4.5 The Visual Office (UI/UX)
- **Metaphor `[D38]` — pixel-art HQ + dashboard toggle:** immersive HQ scene by default; toggle to
  an **Ops view** (agent cards + KPIs) for serious operations.
- **Live mission `[D39]` — in-scene animation:** the running Sunday→Alphabet→Friday flow is shown
  through HQ characters (working/idle/blocked states, walking artifacts to desks on handoff). Detailed
  flow/timeline analytics live in the Ops view / task system.
- **Agent management `[D40]` — both:** click an agent in-scene → quick **profile panel** (identity,
  model, owned skills, dual strength, live cost, current task, enable/disable); plus a full
  **roster page** (sortable table) for managing many agents.
- **Command surface `[D41]` — all three:** a persistent **command console** (talk to Tobi / assign
  missions in natural language) + a **mission board** (create/assign/track, reuses Task-page patterns)
  + a unified **approvals inbox** for every gate (new skills, promotions, validation, escalations,
  key actions).

### 4.6 State, Memory & Observability
- **Persistence `[D64]` — relational tables:** `missions(id, goal, status, owner, priority,
  workflow_id, started)`, `mission_steps(mission_id, seq, agent, gate, status, artifact_ref,
  verdict)`, `agents(config)`, `agent_state(agent_id, status, current_task)`. Supports replay,
  resume, the queue/priority logic (D57), and the live view.
- **Agent memory `[D65]` — shared org memory only:** one shared knowledge store; agents are stateless
  workers reading/writing the common pool. **Tobi's memory remains the single org-level memory.**
- **Realtime `[D42]` — SSE + polling fallback:** backend pushes mission/agent updates over
  `GET /api/office/stream` (Server-Sent Events); the scene animates on events; client falls back to
  delta-polling if the stream drops.
- **Observability `[D43]` — Org KPIs + integration health:** replaces the current **fake**
  CPU/MEM/firewall readouts with real vitals — agents active/idle, missions running/blocked,
  today's token-spend vs budget, error/escalation rate — plus live provider/DB/Telegram status via
  **`core.integrations.check_all()`**. (Host CPU/MEM via `psutil` = trivial optional add later.)
- **Audit retention `[D63]` — owner-configurable:** the audit log (every autonomous action,
  approval, agent decision) has an **owner-set retention window** (default ~90 days hot) with a
  choice to **archive (compressed, still queryable/exportable) or prune** older entries, plus a
  **full export**. Thomas owns the storage/forensics tradeoff.

---

## 5. Cross-cutting concerns

### 5.1 Tech stack (existing — build within it)
- **Frontend:** React 18 + TypeScript + Vite 5, Tailwind 3, Framer Motion 11, lucide-react,
  React Router v6. Lives in `dashboard/`, built to `dashboard/dist/`.
- **Backend:** FastAPI (Python 3.12) in `api/dashboard.py`, served on **:8080**; API server on :8000.
- **DB:** SQLite at `~/.mmo_agent/agent.db` via `core/database.py`.
- **Engines:** `core/` (model_router, research, executor, ceo loop, classifier, integrations,
  telegram_bot, env_utils).
- **Runtime:** `main.py start` (orchestrator + scheduler); autostarts via `scripts/autostart.sh`
  in a tmux session in Codespaces. Port 8080 is forced **public** in autostart so the Telegram link
  opens externally.
- **Charts:** custom SVG (no new chart dependency) — radar + StatBar reuse the `HealthBar` visual recipe.

### 5.2 Consolidated data model (new tables)
```
-- Ability (defs in git-tracked skills.yaml; metrics + dynamic state in DB)
skill_metrics(skill_id, dim|metric, value, source, updated_at)
skill_versions(skill_id, version, prompt, tools, model, created_at, change_note, metric_delta)
skill_proposals(id, type[create|improve|promote], skill_id?, payload, status, rationale, created_at)

-- Office
agents(id, name, role, avatar, persona, model_config_json, permissions_json, budgets_json, status)
                                                 -- status includes 'archived' (soft-offboard, D59)
agent_state(agent_id, status, current_task, updated_at)
missions(id, goal, status, owner, priority, workflow_id?, workflow_version?, started_at, finished_at)
                                                 -- priority: low|normal|high|urgent (D57); pins workflow_version (D61)
mission_steps(mission_id, seq, agent_id, gate_type, status, artifact_ref, verdict)
workflows(id, name, version, definition_json, created_at)   -- L3 composites, versioned (D61)
skill_deps(parent_skill_id, child_skill_id, child_version)  -- pinned dependency edges (D50)
llm_usage(call_id, agent_id, mission_id, provider, model, in_tok, out_tok, cost, ts)
                                                 -- fallback billed as ordinary spend, NO special tag (D62);
                                                 -- the fallback event is recorded instead as a row in `lessons` (D62)
secrets(provider, ciphertext, key_ref, status)  -- encrypted; master key from env only
audit_log(id, actor, trigger, action, target, diff_json, metric_delta, rationale, ts)
                                                 -- owner-configurable retention/archive (D63)
```
*(The blackboard can live as a JSON column on `missions` or a `mission_context` table.)*

### 5.3 Shared "power language"
Abilities (§3.1) and agents (§4.2) use the **same 4 dimensions + level/rank helpers**, so the
RPG radar, StatBar, and comparison components are **reused across both modules**.

### 5.4 Reusable frontend assets (already present)
`components/HealthBar.tsx` (gradient/sheen bar recipe → new `StatBar`/XP bar), `Logo.tsx`,
`StatCard.tsx`, the Architecture-page sticky detail-panel pattern, Health-page poll pattern, the
Task-page Kanban patterns (for the mission board).

---

## 6. Phasing & rollout

**Phase A — Ability (read + curated):** YAML defs + `GET /api/abilities` (live overlay, cached) +
RPG cards + hero + compare + detail panel. *No evolution actions yet.* De-risks, ships visible value.

**Phase B — Ability evolution:** proposals/approval inbox (risk-tiered, D48), coach endpoint,
versioning + readable diff view (D54/D55), timeline, dependencies (D50), governance (kill-switch,
rollback, safe-mode, cost guard, mid-run/retirement rules D46/D47), Telegram notifications (D51),
owner-configurable self-review (D49). L2 code-gen sandbox can lag to B.2.

**Phase C — Office foundations:** agents schema + builder UI + roster page + per-agent LLM config
(LiteLLM abstraction, encrypted secrets) + dual strength view + `llm_usage` tracking.

**Phase D — Orchestration:** versioned workflow templates (L3), blackboard, Tobi-mediated handoffs,
gates, failure handling, **mission queue (concurrency cap + priority + per-agent serialization),
live mid-mission steering, agent offboarding/reassign**, mission board + command console +
approvals inbox (incl. the D48 risk-tiered gates).

**Phase E — Live Office:** pixel-art HQ wired to real state, SSE stream, in-scene handoff animation,
Ops view with real Org-KPI observability (replace fake telemetry).

> Each phase ends with: `npm --prefix dashboard run build` green + a Playwright screenshot pass +
> a backend smoke (`curl` the new endpoints against the real DB).

---

## 7. Decision Log (69)

> Module 1 (Ability): D1–D21, D44–D55 (33). Module 2 (Office): D22–D43, D56–D69 (36).

| # | Module/Area | Decision |
|---|---|---|
| D1 | Power model | 4 dims (Autonomy/Reliability/Speed/Impact) + derived overall |
| D2 | Data source | Hybrid curated baseline + live DB overlay |
| D3 | Skill abstraction | Unified 4-layer: Record→Executable→Composable→Capability-flag |
| D4 | Taxonomy | Tier bands: Core / Learned / Experimental |
| D5 | Create gate | Auto L1+L3; L2 code modules need Thomas ✅ |
| D6 | Triggers | All: failure, scheduled, owner command, metric breach |
| D7 | Gap detect | Hybrid LLM-reflect → registry-confirm |
| D8 | Improve loop | Owner-coached refinement |
| D9 | Promotion | Auto Exp→Learned (evidence); Learned→Core needs ✅ |
| D10 | Hero | Power Level + rank + mini all-abilities radar |
| D11 | Compare | Radar ⟷ grouped-bars toggle (2–3) |
| D12 | Cards | Full RPG character cards |
| D13 | Evolution UI | Inbox + badges + timeline + version history |
| D14 | Storage | Git-tracked YAML defs + DB metrics |
| D15 | Live metrics | Cached snapshot + on-read fallback (TTL ~5min) |
| D16 | API | Read + evolution endpoints (proposals/approve/coach) |
| D17 | Integration | v1 descriptive mirror; target = registry-as-dispatcher |
| D18 | Sandbox | Subprocess (no secrets) + smoke test → approval queue |
| D19 | Recovery | Kill-switch + rollback + safe-mode + auto-demote |
| D20 | Audit | Full provenance + owner-rationale veto |
| D21 | Cost guard | Token budget + per-skill cooldown + Telegram alerts |
| D22 | Agent identity | Persona that owns skills + a model |
| D23 | Lifecycle | Persistent named roster (stats accrue) |
| D24 | Authority | Scoped grants + approval gates (defense in depth) |
| D25 | Permissions | All: model/tool, budget, autonomy, can-spawn |
| D26 | Model bind | Per-agent full LLM config |
| D27 | Agent config UI | Full builder form/modal |
| D28 | Agent strength | Power axes + empirical scorecard |
| D29 | Model routing | Fixed primary + global safety fallback |
| D30 | Orchestration | Hybrid templates + dynamic planning |
| D31 | Comms | Blackboard + Tobi-mediated handoffs |
| D32 | Validation | Configurable gates per workflow |
| D33 | Failure | Retry + escalate + circuit-breaker |
| D34 | Cost tracking | Per-agent + per-mission + per-provider (`llm_usage`) |
| D35 | Rate limits | Caps + queue + backoff + fallback |
| D36 | Provider abstraction | Unifying SDK (LiteLLM-style) behind thin interface |
| D37 | Secrets | Encrypted DB store + master key in env, rotate via UI |
| D38 | Office view | Pixel-art HQ + dashboard toggle |
| D39 | Mission view | In-scene handoff animation |
| D40 | Agent panel | In-scene quick panel + roster page |
| D41 | Command | Console + mission board + approvals inbox |
| D42 | Realtime | SSE + polling fallback |
| D43 | Observability | Org KPIs + integration health (real, not fake) |
| D44 | Dim provenance | Reliability + Speed live-measured; Autonomy + Impact curated |
| D45 | Token cost | Model tier × measured token volume → Low/Med/High meter |
| D46 | Mid-run change | Finish current run; blocking warning if disabling a skill a running mission uses |
| D47 | Retirement | Soft-archive default; owner hard-delete behind confirmation alert |
| D48 | Tiered approvals | Tobi auto-approves low-risk; Thomas approves high-risk (code/perms/Core) |
| D49 | Self-review schedule | Owner-configurable cadence + on/off |
| D50 | Dependencies | Pin child versions; block parent if missing; revalidate on change |
| D51 | Notifications | Telegram = all autonomous actions + all pending approvals |
| D52 | Authoring | Tobi auto-generates `skills.yaml` entry, no L1 gate, editable later |
| D53 | Cold start | Guided empty state ("abilities power up as Tobi works" + Start-a-task) |
| D54 | Version retention | Keep all version rows (diff+metrics); compress/prune old prompt bodies |
| D55 | Diff view | Detailed readable diff: text diff + metric delta + plain summary + provenance |
| D56 | Concurrency | Parallel missions, 1 task/agent, global cap + budget guard |
| D57 | Prioritization | Priority field (Low/Normal/High/Urgent) + FIFO tiebreak + owner bump |
| D58 | Mid-mission inject | Live steering into running missions (fold-in / pause+re-plan) |
| D59 | Offboarding | Block busy-agent delete w/ confirm → reassign/pause → soft-archive |
| D60 | Bootstrapping | Seeded starter roster (Sunday/Alphabet/Friday), editable/removable |
| D61 | Workflows | Named versioned templates; edit forks version; running mission pins version |
| D62 | Fallback cost | Charge agent+mission as ordinary spend (no tag) + record `lessons` note |
| D63 | Audit retention | Owner-configurable window + archive-or-prune + full export |
| D64 | Office state | Missions + steps + agents + agent-state tables (was STATE) |
| D65 | Agent memory | Shared org memory only (Tobi = org memory) (was MEM) |
| D66 | Principals | Single owner — Thomas hardcoded as root; no multi-user plumbing |
| D67 | Artifacts | Artifact store `~/.mmo_agent/artifacts/{mission}/` + `artifact_ref`; Deliverables list |
| D68 | Delegation depth | Tobi-mediated only (hub-and-spoke); `can-spawn` reserved for Tobi |
| D69 | Mission done | Final gate pass → Tobi close-out summary → Telegram + board; owner can reopen |

---

## 8. Open questions / deferred (to resolve in Phase 2)

1. **Exact curated dimension values + copy** for each seed ability (Thomas to author, or Tobi-draft → approve).
2. **Concrete model IDs** for "Gemini Pro 3 / GPT 5.5 / Opus 8" — map to real provider model strings at build time.
3. **Token price table** for cost estimation (per model, per provider) — needed for `llm_usage.cost`.
4. **Registry-as-dispatcher migration** (D17 target) — enumerate refactor steps for `core/` engines.
5. **LiteLLM vetting** — confirm it supports the chosen providers/models and streaming; else hand-roll adapters.
6. **Workflow definition format** — finalize the L3 JSON/YAML schema for `workflows.definition_json`.
7. ~~Auth on the dashboard~~ — **RESOLVED (D66):** single-owner system, so URL-as-secret
   (port-public) is the accepted auth posture; no per-user login in scope. *(Revisit only if D66 is
   ever reopened to multi-principal.)*
8. ~~Number/identity of seed agents~~ — **RESOLVED (D60):** seed roster = Tobi (head) + Sunday
   (research/Gemini) + Alphabet (evaluator/GPT) + Friday (coder/Opus), all editable. *(Remaining
   detail for Phase 2: the exact persona prompts + skill assignments per seed agent.)*

---

## 9. Hermes Integration Addendum (H1–H20)

> **Bonus scope, requested by Thomas:** *"Since Tobi uses Hermes as core tech, take advantage
> of Hermes — it can create skills itself, which may help the self-improve module a lot."* This
> addendum is the result of a dedicated 20-question round (H1–H20). It **refines** §3.5
> (Self-Evolution), §4 (Office), and §5 (data model); where an H-decision narrows or supersedes an
> earlier `Dn`, that is called out explicitly. Like the rest of this document, it is **Phase-1
> requirements only — no code until Thomas approves Phase 2**, and Phase 2 itself is gated behind
> the H19 verify-first spike.

### 9.1 The core relationship — what Hermes is, what Mission Control is

- **Hermes = Tobi's always-on brain `[H2][H17]`.** The Hermes daemon (24/7 on the VPS) *is* Tobi:
  the head agent's reasoning, its **self-evolution engine**, and its **canonical memory** all live
  in Hermes. Tobi is not a separate process that "calls" Hermes — Tobi runs *as* Hermes.
- **Mission Control = the powerful cockpit/tool that serves Hermes `[H1]`.** MC does **not** replace
  Hermes; it is the authoring surface, governance layer, visualization, and the **orchestrator of
  external sub-agents**. (Thomas's words: *"MC will be like a powerful tool for Hermes."*)
- **Orchestration split `[H18]`:** the **MC mission engine** drives multi-agent workflows
  (Sunday→Alphabet→Friday) and calls each external LLM through the provider abstraction `[D36]`.
  **Hermes is one participant** — the head reasoning + skills + memory — not the workflow runner.
- **Sub-agent identity `[H17]`:** Sunday / Alphabet / Friday remain **per-agent external LLM
  configs `[D26]`** (Gemini / GPT / Opus), orchestrated by MC. They are *not* Hermes instances.

### 9.2 Skills: Hermes-native generation ↔ Mission Control's 4-layer model

This is the heart of the bonus and the place the two systems must reconcile cleanly.

- **A Hermes skill maps to L1+L2 `[H3]`.** Hermes skills are markdown files in `~/.hermes/skills/`.
  A prose/instructional skill is an **L1 Record**; a skill that carries executable commands maps to
  **L2 Executable** — and L2 still passes the D18 sandbox + D48 high-risk approval gate.
- **Hermes may *execute* command-bearing skills but only *generate* prose-only skills `[H8]` (vs
  `[H3]`):** when Hermes **auto-creates** a skill on its own, it is restricted to **L1 prose**. Any
  code/command body is **generated through the MC L2 pipeline** (sandbox → smoke test → Thomas
  approval), never auto-written-and-run by Hermes. This is the safety seam between "Hermes can
  create skills itself" and the D5/D48 create gate.
- **Hermes skills can be workflows that invoke MC abilities `[H5]`.** A Hermes skill body may
  describe an **L3 composition** that references MC-registered abilities/sub-agents. (Thomas:
  *"a Hermes skill could be a workflow which applies/includes abilities in MC."*) Hermes reasons;
  MC executes the composed steps.
- **`skill_self_improve.md` is the canonical self-evolution engine `[H9]`.** The existing Hermes
  skill (triggers: after important task / on Thomas feedback / error repeated >2× / weekly Sun 20:00
  GMT+7; lesson JSON capture; "update skill file only when pattern ≥3× OR Thomas feedback OR
  impact ≥7"; weekly reflection → Telegram) **is** the §3.5 loop. MC **instruments and visualizes**
  it (proposals inbox, evolution timeline, version history `[D13]`) — it does not reimplement it.

**Reconciliation — H12 narrows H4 and D14 (authoritative):**
- **Skill *bodies* are canonical as Hermes `.md` files `[H12]`** in `~/.hermes/skills/`.
- **MC holds skill *metadata* in a sidecar DB, keyed by filename `[H12]`** (tier, dims, metrics,
  version pointers, risk tier, deps).
- Therefore **`skills.yaml` `[D14][H4]` is demoted from "the body source" to a git-tracked
  metadata mirror/index** — useful for D14 traceability and diffing, but the **`.md` file is the
  source of truth for the instruction body.** Authoring flow (H4) becomes: edit metadata in MC →
  MC writes/updates the Hermes `.md` body and refreshes the `skills.yaml` mirror.

### 9.3 Self-evolution control flow (refines §3.5)

- **Triggering is bidirectional `[H6]`:** Hermes **self-triggers** evolution (its native
  triggers above), **and** MC can **request** an evolution (e.g. owner clicks "improve this skill,"
  or a metric breach `[D6]` raises a proposal). Both funnel into the same engine.
- **Dry-run before promote `[H7]`:** a proposed new/edited skill runs in a **shadow/sandbox**
  first; it is **evidence-promoted** (`Experimental→Learned`, `[D9]`) only on clean runs — exactly
  the D9 "≥3 clean runs" rule, now explicitly wired through the Hermes shadow path.
- **Coaching, one store `[H11]`:** Thomas's feedback may arrive via **either** the MC Office UI
  **or** the Telegram gateway; both land in **one** lesson/coaching store (Hermes memory, see H10).
- **Versioning owned by MC `[H15]`:** MC owns the version ledger (`[D54]` keep-all). **Kill** =
  move/flag the skill out of the active set; **rollback** = rewrite the active `.md` body from a
  prior version row. The Hermes skills dir always reflects the *current active* version; MC retains
  full history.

### 9.4 Memory (narrows D65)

- **Hermes memory is canonical; MC indexes it `[H10]`.** Org/agent memory `[D65]` **is** the Hermes
  memory store (`~/.hermes/memory/`, `hermes memory add/search`). MC **mirrors/indexes** it for
  display and cross-linking but does not own a competing memory of record. This **narrows D65**
  ("shared org memory only / Tobi = org memory") to: *that org memory physically lives in Hermes.*

### 9.5 Safety, secrets & footprint (refines §3.6, honors D37)

- **De-root + sandbox + secret-scrub `[H14]`:** the Hermes daemon currently runs `User=root`
  (per `HERMES_QUICK_START.md`). Phase 2 must move it to a **non-root service user** with **no read
  access to `.env`/Codespaces secrets**. A **pre-save scrubber** rejects any generated skill that
  references secret **key-names** or destructive shell. This upholds D37 (master key never in
  git/logs) and the inherited "never paste `.env`" guardrail at the skill-generation boundary.
- **One Telegram bot `[H16]`:** there is a **single** Telegram surface — the **Hermes gateway**
  (restricted to Thomas's user ID). MC notifications `[D21][D51]` are **emitted through that same
  bot**, not a second bot.
- **Auto-commit Hermes skills to the repo `[H13]`:** skill `.md` changes are auto-committed to git
  (audit + rollback substrate), complementing the MC version ledger `[H15]` and the D20 provenance
  log. (Subject to the H14 scrubber passing first.)

### 9.6 Boundaries & rollout

- **Hermes scope = brain only `[H17]`** (restated): reasoning + self-evolution + memory. Everything
  multi-agent/orchestration/visual is MC.
- **Hard dependency on Hermes `[H20]`:** self-evolution lives **entirely** in Hermes. If Hermes is
  unavailable, **self-improvement pauses**; core chat/missions still run on MC's own engines. A
  single point of failure is **accepted** for simplicity (revisit only if it bites).
- **Phase 0 verify-first spike `[H19]` — GATING PREREQUISITE.** Before *any* Phase 2 feature code,
  a no-feature spike must empirically confirm the installed Hermes supports: `skill_generation`,
  the skills-dir format + file locking, the memory API, the gateway API, and tool/delegation. The
  H-series is the **plan**; the spike **validates/adjusts** it. **If the spike contradicts an
  H-decision, the spike wins and this addendum is updated.** (Per standing directive, even this
  spike waits for Thomas's explicit Phase-2 approval.)

### 9.7 Net effect on the self-improve module

The bonus turns §3.5 from "MC builds a self-evolution engine" into **"MC instruments and governs
the self-evolution engine Hermes already has."** Hermes supplies the always-on triggers, the
lesson capture, the skill-file authoring, and the memory of record (`skill_self_improve.md` +
`hermes memory`). Mission Control supplies the **cockpit**: visualization (Ability page), the
approval/governance gates (D48/D18), the version ledger (D54/H15), the metadata model (H12), and
the orchestration of external sub-agents (H18). Less to build, safer by construction, and it
leverages the core tech instead of duplicating it.

---

## 10. Hermes Decision Log (H1–H20)

| #   | Topic | Decision |
|-----|-------|----------|
| H1  | MC ↔ Hermes role | MC = powerful **tool/cockpit for Hermes** (not a replacement) |
| H2  | Tobi runtime | **Tobi *is* the Hermes daemon** (brain runs as Hermes) |
| H3  | Hermes skill ↔ layers | Hermes skill maps to **L1** (prose) **+ L2** (command-bearing) |
| H4  | Authoring source | `skills.yaml` authoring **renders** the `.md` — *narrowed by H12* (see below) |
| H5  | Skill-as-workflow | A Hermes skill may be an **L3 workflow** that includes MC abilities |
| H6  | Trigger ownership | **Bidirectional:** Hermes self-triggers **+** MC can request evolution |
| H7  | Promotion path | **Shadow/sandbox dry-run → evidence-promote** (wires D9 through Hermes) |
| H8  | Auto-gen limit | Hermes **auto-generates prose (L1) only**; code (L2) via MC pipeline + approval |
| H9  | Engine ownership | `skill_self_improve.md` = **canonical engine**; MC **instruments** it |
| H10 | Memory of record | **Hermes memory canonical; MC indexes/mirrors** — *narrows D65* |
| H11 | Coaching channels | Office UI **and** Telegram both feed **one** lesson store |
| H12 | Skill storage split | **Bodies = Hermes `.md` (canonical); metadata = MC sidecar DB keyed by filename** — *supersedes H4/D14 for the body source* |
| H13 | Versioning substrate | **Auto-commit** Hermes skill `.md` changes to the repo |
| H14 | Daemon hardening | **De-root + sandbox + secret-scrub** generated skills (upholds D37) |
| H15 | Version ownership | **MC owns versions:** kill = move/flag; rollback = rewrite prior body |
| H16 | Telegram surface | **One bot** = the Hermes gateway; MC alerts ride it |
| H17 | Hermes scope | **Brain only** (reasoning + self-evolution + memory); sub-agents = external LLMs |
| H18 | Orchestration split | **MC orchestrates the workforce; Hermes is one participant** |
| H19 | De-risk | **Phase 0 verify-first spike** before any feature code (gating; spike wins on conflict) |
| H20 | Dependency posture | **Hard-depend on Hermes;** self-improve pauses if Hermes down (SPOF accepted) |

---

*End of Master Specification. This document + the codebase are sufficient to begin Phase 2
implementation — gated behind the H19 verify-first spike and Thomas's explicit Phase-2 approval.*

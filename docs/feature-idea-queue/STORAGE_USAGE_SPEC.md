# Storage & Usage — Feature Spec & Requirements

> **Status:** 🟡 Queued — Phase 1 (Requirements) COMPLETE. 30 locked decisions (S1–S30) from a
> single UI-picker question round. **Not built.** Portable handover in the same format as the other
> queue specs; paste into a fresh session to build, gated behind Thomas's approval.
>
> **Owner:** Thomas (sole principal). **Head agent:** TOBI. **Date:** 2026-06-26.
>
> **Related specs/code:** queryable via [CONDUCTOR_SPEC.md](CONDUCTOR_SPEC.md) (#7); secrets via
> [GENESIS_SPEC.md](GENESIS_SPEC.md) (#4) vault; reuses the `llm_usage` table + `core/office.py`
> cost logging, `core/model_router.py` (instrumentation target), `core/database.py` schema, the
> Health page (D43 org KPIs), and Recharts (approved in [EXPLORE_NEWS_SPEC.md](EXPLORE_NEWS_SPEC.md)).

---

## 1. Vision

A single **Storage & Usage** management page in Mission Control that makes every TOBI data
resource and every LLM dollar **visible and analyzable in rich, bar-led visuals**. It answers two
questions at a glance:

1. **Where is my disk going?** — total local storage, broken down by TOBI feature (Brain, Graph,
   Office, Tasks, Projects, Documents, Chat, Codebase, Vault, MCP) with growth over time.
2. **Where are my tokens/dollars going?** — LLM spend and usage across provider / model / feature /
   agent, against the plans I'm on.

Lives in the **bottom system menu** (next to Settings / Integrations / MCP) `[S1]`, as an
**Overview header + two tabs (Storage · LLM Usage)** `[S2]`. **Read-only analytics in v1** `[S3]`
— cleanup/prune actions are a later phase. Built **both tabs together** `[S30]`.

---

## 2. Architecture & TOBI integration

- **Refresh = scheduled + manual `[S4]`.** A background scan on the Hermes scheduler writes
  snapshots to SQLite → **instant page loads**; a **"Scan now"** button forces a fresh scan.
- **Cadence = tuned per scope `[S21]`:** DB table sizes cheap → hourly-ish · filesystem walks
  expensive → daily · usage rolls up **continuously** as calls happen.
- **Dependency dirs measured once + cached `[S24]`:** `venv/`, `dashboard/node_modules/`, `dist/`
  are walked once and cached, refreshed weekly (they rarely change) — keeps scans fast.
- **Usage instrumentation `[S13]` (the core change):** today only `core/office.py` writes
  `llm_usage` (and `cost` is stubbed 0). Add a logging hook **at `core/model_router.py`** so
  **every** LLM call — chat, Brain, research, CEO, classifier, Office — records a usage row tagged
  with its **source/feature**. This is the prerequisite for a real usage view.
- **Cost = manual price table `[S14]`:** a maintained per-model/provider price table
  (`config/llm_prices.yaml` → mirrored to a `llm_prices` table); `cost = tokens × price`.
  Deterministic, offline, no secrets. (OpenRouter pricing can refresh it later.)
- **Conductor-queryable `[S25]`:** the page's live data is exposed to the **TOBI Conductor (#7)**
  so Thomas can ask *"what's eating my storage?"* / *"how much did I spend on Opus this month?"*.
- **Alerts = in-app + on-request `[S26]`:** budget warnings show in the page + bell inbox; TOBI
  reports spend over Telegram **only when asked** (no autonomous push — consistent house preference).
- **Vault privacy `[S28]`:** the encrypted vault is shown by **size + item count only** — never any
  secret values (metadata only).

---

## 3. Tab 1 — Storage

- **Scan surfaces `[S5]` (all):** **SQLite `agent.db` per-table** (via dbstat/row analysis) ·
  **data dirs** (`~/.mmo_agent` artifacts+db, `~/.hermes` memory+skills+SOUL) · **code + deps**
  (repo, `venv/`, `node_modules/`, `dist/`) · **vector index + logs** (fastembed store,
  `graphify-out/`, log files, caches).
- **Categorize by feature `[S6]`:** Brain · Graph · Office · Tasks · Projects · Documents · Chat ·
  Codebase · Vault · MCP. (A path→feature and table→feature map drives the rollup.)
- **Dev bulk in a separate "System" bucket `[S7]`** so deps/build don't visually drown out real
  TOBI data.
- **Overview KPIs `[S12]` (all):** **total local storage** (auto KB/MB/GB) + breakdown ·
  **agent.db size + total row counts** · **biggest consumer** highlight · **growth rate**
  (Δ week/month + simple projection).
- **Charts `[S10]` (all):** ranked **horizontal bars** (your preference) · **treemap** (nested
  "what's eating disk") · **donut / 100%-stacked** share · **growth area/line** from snapshots.
- **Drill-down = both `[S9]`:** category totals **+** top-N biggest items per category (largest
  chats, memories, artifacts, tables).
- **History = snapshot over time `[S8]`** (powers the growth chart + "what grew this week").
- **External = local-only v1 `[S11]`** — service quotas (Notion/Drive/GitHub/Supabase) deferred.

---

## 4. Tab 2 — LLM Usage

- **Instrument all calls `[S13]`** (see §2) → unified usage rows with source/feature.
- **Breakdown dims `[S15]` (all):** by **provider** · **model** · **feature/engine** (chat / Brain
  / research / Office / CEO) · **agent** (Sunday / Alphabet / Friday / TOBI).
- **Metrics `[S16]` (all):** **cost ($)** · **tokens** (prompt/completion/total) · **request
  count** · **avg latency**.
- **Plan/quota = manual plan + limit bars `[S17]`:** configure each provider's plan/quota (Claude
  Max, OpenAI tier, OpenRouter credits…) → usage-vs-limit progress bars. Offline, every provider.
- **Budgets `[S18]`:** set a **monthly $ cap**; warn when nearing/over (reuses the D21 cost-guard
  pattern; alert delivery per `[S26]`).
- **Time `[S19]`:** Day / Week / Month / All **range selector** + **stacked-area spend-over-time**.
- **Call log `[S20]`:** roll-ups/charts **plus** a searchable per-call log inspector (model,
  feature, tokens, cost, latency, time).

---

## 5. UI/UX, data model, API

**UI `[S2][S27][S29]`:** bottom-system-menu route; Overview header + **Storage** / **LLM Usage**
tabs; inherits the **8-theme** styling; charts via **Recharts + a treemap** component. A compact
**storage + spend summary widget** is cross-linked on the **Dashboard** (and/or Health page),
linking into this page `[S29]`.

**Schema changes (`core/database.py`):**
```
-- extend the existing unified usage table [S23]
ALTER llm_usage ADD COLUMN source     TEXT;     -- engine: chat|brain|research|ceo|classifier|office
ALTER llm_usage ADD COLUMN feature    TEXT;     -- finer tag (e.g. brain.summarize)
ALTER llm_usage ADD COLUMN latency_ms INTEGER;  -- per-call latency
-- (existing Office rows default source='office'); cost now populated from the price table

-- new tables
storage_snapshots(id, taken_at, scope, feature, bytes, item_count, meta_json)   -- history [S22]
llm_prices(provider, model, price_in_per_mtok, price_out_per_mtok, updated_at)   -- mirror of config [S14]
llm_plans(provider, plan_name, limit_type, limit_value, period, configured_at)  -- plan/quota bars [S17]
usage_budget(key, monthly_cap_usd, alert_pct, updated_at)                       -- budget cap [S18]
```
Top-N drill items are computed on read (cached) from source tables/filesystem — not stored.

**Backend:** `core/storage_scan.py` (dbstat + path-walk → feature rollup + snapshot writer),
`core/usage_meter.py` (model_router hook + price-table cost calc + plan/budget eval). Scheduler:
`job_storage_scan` (db hourly / fs daily). No new secrets — keys stay in the Genesis vault `[S28]`.

**API (FastAPI `api/dashboard.py`, before SPA catch-all):**
```
GET  /api/storage/overview            # KPIs + per-feature breakdown + snapshot trend
GET  /api/storage/category/{feature}  # drill-down: top-N biggest items
POST /api/storage/scan                # manual "Scan now"
GET  /api/usage/overview              # totals + dims + spend-over-time (range param)
GET  /api/usage/calls                 # paginated, filterable per-call log
GET  /api/usage/plans  | POST         # plan/quota bars (read / configure)
GET  /api/usage/budget | POST         # monthly cap (read / set)
```

---

## 6. Phasing & rollout (built together `[S30]`, internally staged)

- **M1 — Storage tab:** scan engine + `storage_snapshots`, feature rollup, Overview KPIs, bars +
  treemap + donut + growth chart, drill-down, deps "System" bucket. (Touches no LLM path.)
- **M2 — LLM Usage tab:** `model_router` instrumentation + `llm_usage` schema extension + price
  table → cost; provider/model/feature/agent breakdowns, metrics, range + trend, call log.
- **M3 — Plans, budgets & glue:** manual plan/quota bars, monthly cap + in-app alerts, Conductor
  #7 querying, Dashboard/Health cross-link widget.

> Each milestone ends with: `npm --prefix dashboard run build` green + Playwright screenshot pass +
> backend smoke (`curl` the new endpoints against the real DB) — same gate as the other specs.

---

## 7. Open inputs from Thomas

1. **Price table seed** `[S14]` — confirm per-model $/Mtok in `config/llm_prices.yaml` (I'll draft
   defaults for the models in use: Opus/Sonnet/Haiku, GPT-x, Gemini, plus OpenRouter passthrough).
2. **Plan/quota values** `[S17]` — which plans you're actually on (e.g. Claude Max tier, OpenAI
   tier, OpenRouter credit balance) so the limit bars are real.
3. **Monthly budget cap** `[S18]` — the $ figure + alert threshold (e.g. warn at 80%).

---

## 8. Decision Log (S1–S30)

| # | Area | Decision |
|---|---|---|
| S1 | Placement | **Bottom system menu** (with Settings/Integrations/MCP) |
| S2 | Structure | **Overview + two tabs** (Storage · LLM Usage) |
| S3 | Actions | **Read-only v1**; cleanup/prune actions later |
| S4 | Refresh | **Scheduled (Hermes) + manual "Scan now"** |
| S5 | Scan surfaces | **All:** DB per-table + data dirs + code/deps + vector index/logs |
| S6 | Categories | **By feature** (Brain/Graph/Office/Tasks/Projects/Docs/Chat/Codebase/Vault/MCP) |
| S7 | Dev bulk | venv/node_modules/dist → **separate "System" bucket** |
| S8 | History | **Snapshot over time** (growth charts) |
| S9 | Drill-down | **Both** — category totals + top-N biggest items |
| S10 | Charts | **All:** horizontal bars + treemap + donut/stacked + growth area |
| S11 | External | **Local-only v1** (service quotas later) |
| S12 | KPIs | **All:** total storage + DB size/rows + biggest consumer + growth rate |
| S13 | Instrument | **Instrument `model_router`** → log every call with source/feature tag |
| S14 | Cost calc | **Manual price table** (config → `llm_prices`), cost = tokens × price |
| S15 | Usage dims | **All:** provider + model + feature/engine + agent |
| S16 | Usage metrics | **All:** cost $ + tokens + request count + avg latency |
| S17 | Plan/quota | **Manual plan + usage-vs-limit bars** |
| S18 | Budgets | **Monthly cap + alert** (D21 pattern) |
| S19 | Time | **Range selector** (D/W/M/All) + stacked-area trend |
| S20 | Call log | **Aggregates + searchable per-call log** |
| S21 | Cadence | **Tuned per scope** (DB frequent / fs daily / usage continuous) |
| S22 | Persistence | **New `storage_snapshots` table** (usage history reuses llm_usage ts) |
| S23 | Usage schema | **Extend `llm_usage`** (source/feature/latency + real cost) |
| S24 | Dep sizing | **Measure once, cache** (weekly refresh) |
| S25 | Conductor | **Queryable via #7** ("what's eating storage / spend on Opus") |
| S26 | Alert channel | **In-app + on-request** (no autonomous Telegram push) |
| S27 | Styling/charts | 8-theme + **Recharts + treemap** |
| S28 | Vault privacy | **Size + count only** (never values) |
| S29 | Cross-link | **Summary widget** on Dashboard (and/or Health) → links here |
| S30 | Phasing | **Both tabs together** (internally staged M1→M3) |

---

*End of spec. Sufficient to begin the build once Thomas approves and provides the §7 inputs.*

# Explore → News — Feature Spec & Requirements (Queue Entry)

> **Status:** Phase 1 (Requirements) COMPLETE — 28 locked decisions (E1–E28) from a single
> UI-picker question round. **Not built.** This document is the portable handover in the same
> format as `MISSION_CONTROL_SPEC.md`: paste into a fresh session to begin Phase 2 (build),
> gated behind Thomas's explicit approval.
>
> **Owner:** Thomas (sole principal, inherited `[D66]`). **Head agent:** TOBI.
> **Date:** 2026-06-26. **Queue status:** READY (awaiting two inputs — see §8).

---

## 1. Vision

A new **`Explore`** top-level sidebar section in Mission Control — a set of personal "interesting
pages" Thomas builds for himself, each **conducted by TOBI** (Tobi-mediated fetch → dedupe →
summarize → rank, the same hub-and-spoke spirit as the Office). **News** is the first page.

News is a **read-only consumption surface** that pulls the latest AI news from public APIs and
TOBI summarizes/ranks it for Thomas. Three tabs:

1. **Models** — which model is currently strongest/most popular, with a leaderboard + benchmark
   charts, auto-updating the moment a new model ships.
2. **Tools** — what AI tools are trending/standout right now, each briefly explained.
3. **Social-Trending** — hot AI chatter scanned from Reddit / the web / X, summarized by TOBI into
   a ranked "for you" feed, with an **owner-tunable interest algorithm**.

A shared **news backbone** (NewsData.io / GDELT / RSS / GNews) feeds a slim "Top AI headlines"
rail and enriches all three tabs.

---

## 2. Architecture & TOBI integration ("Conductor")

- **Conductor = Tobi-mediated pipeline `[E2]`.** Not static API embeds — TOBI orchestrates
  **fetch → dedupe → summarize → rank** for every tab. "Conductor" is shorthand for the existing
  Tobi-mediated pattern, not a new visualized mode.
- **Engine = standalone, logged `[E6]`.** A dedicated News job (not the full Office mission engine)
  that calls `core/model_router`, logs every call to **`llm_usage`**, and respects the **D21
  cost-guard** pattern (token budget + pause-on-over-budget).
- **Summarization model policy:** **Haiku** for bulk per-item summaries; **Opus** reserved for the
  editorial digest / "TOBI's take." (Default Claude models per the latest IDs.)
- **Voice = neutral + optional "TOBI's take" `[E5]`.** Each item shows a concise neutral summary;
  an expandable **"TOBI's take"** adds opinion/recommendation on demand.
- **Refresh model = scheduled + manual `[E7]`.** Background scans run on the always-on Hermes
  scheduler (like the existing daily/6-hourly jobs) and write to SQLite + cache → **instant page
  loads**; a **"Refresh now"** button forces an on-demand scan.
- **Cadence = per-pillar tuned `[E24]`:** News ~hourly · Tools every few hours · Social a few
  times/day · Models daily. (Each matched to how fast it actually changes.)
- **No autonomous push `[E8]`.** TOBI does **not** interrupt with Telegram alerts. It surfaces News
  only **on request** via the existing gateway — e.g. *"Hey TOBI, summarize today's news for me"* →
  TOBI returns the digest in chat. (One bot only, the Hermes gateway `[H16]`.)
- **Secrets `[E25]`.** All new API keys live in the **D37 encrypted secret store** with a
  **Settings → Explore** config panel (connect / toggle / status). Reference key **names** only,
  never values (inherited guardrail).
- **LLM budget = Low (~$5/mo) `[E26]`** for summarization, enforced via the D21 guard.

---

## 3. Tab 1 — Models

- **Strength = blended composite, tunable `[E9]`.** Combine **benchmark intelligence**
  (Artificial Analysis Intelligence Index) + **human Elo** (LMArena) + **real-usage popularity**
  (OpenRouter) into one re-weightable score.
- **New-model freshness (hard requirement) `[E9a]`.** A model must appear **the day it ships**.
  Source strategy: **OpenRouter `GET /api/v1/models`** is the live spine (new models surface almost
  immediately, with price + context), **enriched** by Artificial Analysis benchmarks + LMArena Elo
  **as they land**. A model can render with "benchmarks pending" before scores exist.
- **Scope = frontier only `[E11]`** — top-tier flagship models; others searchable but not listed.
- **Compare UI = both `[E10]`:** a **sortable leaderboard table** (primary) **+** reuse of the
  Ability `RadarChart`/grouped-bars for a **2–3 model deep compare**.
- **Columns (all present):** provider/owner · intelligence · price (in/out) · speed (tok/s) ·
  latency · context window · popularity rank · release date. **Default sort = Intelligence `[E12]`.**
- **Charts:** price/speed scatter + per-model trend-over-time line (Recharts, see `[E28]`).

---

## 4. Tab 2 — Tools

- **Sources `[E13]` (all):** **Hacker News** (Algolia API, free/no-key) · **Product Hunt**
  (GraphQL, personal token) · **GitHub trending** (existing `GITHUB_TOKEN`, star-velocity) ·
  **Newsletters / X** (curated list — *Thomas to provide*, see §8).
- **"Trending" = velocity + AI judge `[E14]`.** Recent velocity (votes/stars in 24–48h) surfaces
  candidates; **TOBI curates** which are genuine standouts.
- **Card fields `[E15]`:** name + one-liner + provider + links (always) **plus** *why it's
  trending* · *pricing / free tier* · *category tag* · *TOBI's take*.
- **Filtering `[E16]`:** category filters (agents / coding / media-gen / infra / voice…) **+ mute**
  categories permanently.

---

## 5. Tab 3 — Social-Trending (the complex pillar)

- **Sources `[E17]` (connectable, per-source toggle):**
  - **Reddit** ✅ primary — OAuth, free tier. Seed subs: r/LocalLLaMA, r/singularity,
    r/MachineLearning, r/OpenAI, r/ArtificialIntelligence; **hot posts + their top comments** for
    context `[E21]`. (Sub list owner-editable.)
  - **Tavily** ✅ — web-scan layer (`search`/`crawl`/`research`) across blogs+news+social.
  - **X / Twitter** — toggle present but **OFF until Thomas opts in `[E22]`** (pay-per-use,
    ~$0.005/post read; needs a spend cap set at opt-in time).
  - **TikTok** — toggle present, **deferred** until Research-API approval (app-gated, US/EU/Brazil).
  - **Facebook** — **noted infeasible** (public-content Graph API effectively closed).
- **Owner-tunable algorithm `[E18]` (knobs in Settings → Explore):** **source weights** ·
  **recency-vs-engagement** slider · **keyword include/exclude** (boost/mute topics) ·
  **editable interest prompt** (the natural-language "is this interesting to me" prompt TOBI uses).
- **Interest model `[E19]` = rule-based now, learn later.** v1 ranks via the manual knobs only;
  thumbs/click-through learning is a later version (consistent with read-only v1).
- **Layout `[E20]` = ranked "for you" feed:** ranked list, each item an **expandable AI summary**
  with source badge, engagement metric, time metric, and permalink.

---

## 6. News backbone & time metrics

- **Sources `[E23]` (all):** **NewsData.io** (primary, 89 langs, `NEWSDATA_API_KEY`) · **GDELT**
  (free/no-key, volume+sentiment trends) · **RSS** (TechCrunch AI, The Verge, VentureBeat, MIT Tech
  Review… free) · **GNews** (`GNEWS_API_KEY`, secondary breadth).
- **Language `[E25b]` = English, VN-weighted** — English content, boosting AI news relevant to
  Vietnam/SEA.
- **Time-metric detail `[E27]` (all):** published time + **how-long-trending** · **GDELT volume
  sparkline** · **velocity/acceleration** (heating vs cooling) · **freshness badge** (New / Hot /
  Cooling).

---

## 7. UI/UX, data model, API

**UI `[E1][E3][E28]`:** new **Explore** section in the AppShell sidebar (scaffolded for future
siblings — Markets / Learn / Watch); **News** page = three **tabs** (Models / Tools / Social) + a
top "Top AI headlines" rail. Inherits the **8-theme CSS-variable** SaaS styling (not the cyberpunk
Office look). Charts via **Recharts** (the one approved new dep) for scatter + sparklines; reuse
`RadarChart`/`StatBar` for model compare. Read-only — no item actions in v1.

**New tables (SQLite `~/.mmo_agent/agent.db`):**
```
explore_sources(id, pillar, name, kind, enabled, weight, config_json, status, last_scan_at)
explore_items(id, pillar, source_id, ext_id, title, url, summary, tobi_take,
              raw_json, score, engagement, published_at, first_seen_at, freshness, ts)
explore_models(model_id, provider, owner, intelligence, elo, popularity,
               price_in, price_out, speed, latency, context, released_at, composite, updated_at)
explore_config(key, value_json)   -- algorithm knobs, weights, interest prompt, keyword lists
```
LLM calls reuse **`llm_usage`**; keys reuse the **`secrets`** store `[D37]`.

**API (FastAPI `api/dashboard.py`, before SPA catch-all):**
```
GET  /api/explore/news            # headlines rail + per-tab payload (cached)
GET  /api/explore/models          # leaderboard + composite + charts data
GET  /api/explore/tools           # trending tools
GET  /api/explore/social          # ranked "for you" feed
POST /api/explore/refresh         # manual "refresh now" (per-pillar or all)
GET  /api/explore/config          # algorithm knobs + source toggles
POST /api/explore/config          # update weights / prompt / keywords / toggles
```

---

## 8. Open inputs still needed from Thomas

1. **Trusted Newsletters / X accounts** for the Tools tab `[E13]` — provide the list.
2. **Confirm/edit the Reddit seed sub list** `[E21]` (defaults proposed in §5).
3. **X spend cap** — set when/if he opts X in `[E22]`.
4. **Provider account sign-ups** to generate the API keys named in §10 (free tiers cover most).

---

## 9. Phasing & rollout

- **Phase A — Backbone + Models (read, cached):** Explore section + AppShell nav, ingestion job +
  scheduler hook, `secrets`/`explore_*` tables, news backbone + headlines rail, **Models tab**
  (leaderboard + compare + new-model freshness). Ships visible value, de-risks the pipeline.
- **Phase B — Tools + Social:** trending Tools tab (HN/PH/GitHub + AI-judge), Social-Trending feed
  (Reddit + Tavily) with the Settings → Explore algorithm knobs + source toggles.
- **Phase C — Conductor polish:** editorial "TOBI's take" + on-request digest ("summarize today's
  news"), GDELT time-metric charts, X opt-in path, mute/keyword refinements.

> Each phase ends with: `npm --prefix dashboard run build` green + a Playwright screenshot pass +
> a backend smoke (`curl` the new endpoints against the real DB) — same gate as the MC spec.

---

## 10. External resources appendix (key **names** only — never values)

| Pillar | Source | Env key name | Free tier | Notes |
|---|---|---|---|---|
| Models | OpenRouter (model list) | — (public) | yes | live new-model spine |
| Models | OpenRouter (rankings) | `OPENROUTER_API_KEY` | yes | usage popularity |
| Models | Artificial Analysis | `ARTIFICIALANALYSIS_API_KEY` | yes (rate-limited) | Intelligence Index |
| Models | LMArena / HF dataset | `HF_TOKEN` (optional) | yes | human Elo |
| Tools | Hacker News (Algolia) | — (none) | unlimited | Show HN / front page |
| Tools | Product Hunt | `PRODUCTHUNT_API_TOKEN` | yes (non-commercial OK) | trending launches |
| Tools | GitHub trending | `GITHUB_TOKEN` (existing) | yes | star velocity |
| Social | Reddit | `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET` | yes (personal) | posts + top comments |
| Social | Tavily | `TAVILY_API_KEY` | yes | web-scan layer |
| Social | X / Twitter | `X_BEARER_TOKEN` | pay-per-use | OFF until opt-in |
| Social | TikTok | `TIKTOK_CLIENT_KEY` / `TIKTOK_CLIENT_SECRET` | app-gated | deferred |
| News | NewsData.io | `NEWSDATA_API_KEY` | 200/day, 89 langs | primary |
| News | GDELT | — (none) | free | volume/sentiment trends |
| News | RSS feeds | — (none) | free | baseline |
| News | GNews | `GNEWS_API_KEY` | 100/day | secondary |

---

## 11. Decision Log (E1–E28)

| # | Area | Decision |
|---|---|---|
| E1 | Placement | New top-level **Explore** section; News first page; scaffolded for siblings |
| E2 | Conductor | Tobi-mediated **fetch→dedupe→summarize→rank** pipeline (not static embeds) |
| E3 | Layout | Three **tabs**: Models / Tools / Social |
| E4 | Page mode | **Read-only** in v1 (no item actions) |
| E5 | Voice | Neutral summary **+ optional "TOBI's take"** |
| E6 | Engine | Standalone job, **logged to `llm_usage` + D21 guards** (not full Office engine) |
| E7 | Refresh | **Scheduled (Hermes) + manual "Refresh now"**; cache → instant loads |
| E8 | Push | **No autonomous push**; on-request only via gateway ("summarize today's news") |
| E9 | Model strength | **Blended composite** (intelligence + Elo + popularity), tunable |
| E9a | Freshness | New models appear **day-of**: OpenRouter live list + AA/LMArena fill-in |
| E10 | Model compare UI | **Both** — leaderboard table + radar/bars deep-compare |
| E11 | Model scope | **Frontier only** (rest searchable) |
| E12 | Default sort | **Intelligence** (all standard columns present) |
| E13 | Tool sources | **HN + Product Hunt + GitHub trending + Newsletters/X** |
| E14 | Trending def | **Velocity + AI judge** |
| E15 | Tool card fields | why-trending + pricing + category + TOBI's take (+ name/provider/links) |
| E16 | Tool filters | Category **filter + mute** |
| E17 | Social sources | Reddit + Tavily + X(opt-in) + TikTok(deferred); Facebook infeasible |
| E18 | Algorithm knobs | source weights + recency/engagement + keyword inc/exc + editable prompt |
| E19 | Interest model | **Rule-based now, learn later** |
| E20 | Feed layout | Ranked **"for you" feed** with expandable summaries |
| E21 | Reddit | Seed AI subs, **posts + top comments** (editable list) |
| E22 | X budget | **Off until opt-in** (pay-per-use; cap set on enable) |
| E23 | News sources | **NewsData.io + GDELT + RSS + GNews** |
| E24 | Cadence | **Per-pillar tuned** (News~hourly / Tools~hrs / Social~daily×N / Models daily) |
| E25 | Secrets+lang | Keys in **D37 encrypted store** + Settings panel; **English, VN-weighted** |
| E26 | LLM budget | **Low (~$5/mo)** summarization cap (Haiku bulk, Opus digest) |
| E27 | Time metrics | published+duration + **volume sparkline** + velocity + freshness badge |
| E28 | Styling/charts | Inherit 8-theme SaaS styling; **add Recharts** for scatter + sparklines |

---

*End of spec. Sufficient to begin Phase 2 once Thomas approves and provides the §8 inputs.*

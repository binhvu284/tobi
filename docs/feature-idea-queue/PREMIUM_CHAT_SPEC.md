# Premium Chat — multi-model conversational workspace

> **One-liner:** Upgrade TOBI's chat from a minimal streaming bubble into a **premium, multi-model
> chat workspace** rivaling Claude / ChatGPT / Gemini / Grok: a real model picker + provider config
> (one source of truth that also drives Hermes), visible thinking + token/time meters, a `+` tools
> menu (files, image-paste, Drive, web research, connector tools), rich block output rendered in the
> chat space, message actions (copy / regenerate / edit-branch), per-model context "energy bar",
> sessions, compaction, a system-action log, and usage/cost analytics.
>
> **Queue #8** · **Date:** 2026-06-26 · **Owner-reviewed via 30 Q&A** (Appendix A) ·
> **Relates to:** [CONDUCTOR_SPEC.md](CONDUCTOR_SPEC.md) (#7, connector-as-tools), Genesis vault (#4).
>
> **Status: ✅ Done (v1) — P1 + P2 + P3 all shipped & tested** (needs backend restart + `pip install pypdf`
> for PDF text). See **§6 Phased plan** for the checkpoints.

---

## Post-delivery fixes (owner-reported, live-verified)

After a first hands-on test the owner hit three real issues; all fixed and **verified against a live
server** (started on a temp DB, driven over the real SSE API):

1. **"Create project but nothing shows up / serious hallucination."** Root cause was a **data-layer
   mismatch**, not a model hallucination: the Conductor's `create_project`/`list_projects`/`create_task`/
   `complete_task`/`update_project_progress`/`delete_task`/`assign_task` wrote/read the **legacy
   `projects` table**, while every user-facing page uses the **PM system** (`pm_projects` + `tasks.pm_project_id`).
   Repointed all of them to the PM tables (status `active`, progress auto-recalc via the API's
   `_pm_recalc_progress`, activity logged to `pm_activity`); `list_projects` now returns the **real id**
   so create→task chains target the right project. `assign_task` now sets a **canonical Tasks-board key**
   (`tobi|research|coder|ceo`, with friendly aliases) instead of an office-agent id. **Live proof:** a chat
   "Create a project called Newsletter Engine" → "Add a task: draft the welcome email" → "what tasks do I
   have?" produced a project + task that appear on **`/api/pm/projects`** and the project's task list, with
   the reply grounded to the real ids; an unknowable query (revenue) **refused instead of inventing**.
2. **"Thinking effect is not good."** The turn ran the whole tool-loop synchronously, so the user stared at
   a static "Thinking…" for the model's full latency (~16 s). Added an **`on_event` progress callback** to
   `conductor.answer` that fires a live phase per tool ("Creating the project…", "Reading your projects…"),
   bridged to the SSE stream via a **thread→async queue**, so the thinking panel narrates the work in real
   time with tool chips.
3. **"Output answer stays in a box."** The assistant message was wrapped in a bordered bubble; made it a
   **full-width, borderless block** spanning the chat (user messages stay bubbles), matching the spec's
   "assistant full-width blocks."

**Regression status after the fixes:** `test_pm_fix` 13/13 (Conductor→PM board), #7 P2 24/24 · P3 17/17,
#8 P1 26/26 · P1b 10/10 · P2 25/25 · P3 23/23; frontend build clean.

---

## P3 — Meters & analytics ✅ (built & tested, this run) — #8 COMPLETE

**Real per-call usage logging** — `core/usage.py` **extends the existing D34 `llm_usage` table** (rather
than competing with it — exactly what #10 envisions) with `ts / surface / feature / cost_est / latency_ms`.
The `model_router` **clients auto-log every `complete()`** (real provider token counts when available, else
an estimate) tagged with a process-global **surface** (`set_usage_context`) — the chat stream endpoint sets
`chat`, everything else defaults to `agent`, and legacy **Office** per-mission rows fold in via `created_at`.
A **manual price table** (per-1M in/out, longest-fragment match) drives `estimate_cost`.

**Analytics** — `GET /api/llm/usage?days=` aggregates weekly **tokens / cost / requests / avg-latency**,
**by-model** columns, **by-surface**, and a gap-filled **per-day** series. Rendered on the **Models page**
(KPI row + per-model bars + tokens/day trend, 7d/30d toggle — dependency-free CSS bars) and a compact
**Health** widget (KPIs + top models + a "Models →" cross-link).

**Context energy bar** — per the current model's real **context limit** (`context_limit`, exposed on each
`available_models()` entry), % full from a client token estimate; turns **warning at ≥80%** with an inline
**Compact** button.

**Compact** — `POST /api/chat/sessions/{id}/compact` summarizes the **older** turns (LLM) into one stored
`summary` message while keeping the most recent `keep` verbatim (`chat_store.compact_session`); the summary
**feeds back into context** (surfaced by `recent_history` as a user-role line) and renders as a "compacted"
callout. The energy bar drops; a loading shimmer covers the call.

**Tests:** price/cost + logging + summary aggregation (chat + office surfaces) + client auto-log +
per-model context limits + compaction (summarize/keep/feed-back/no-op) = **23/23**; **regressions intact**
(#8 P2 25/25, P1 26/26, P1b 10/10; #7 P3 17/17); app imports with all P3 routes + the `llm_usage`
extension applied on boot; frontend `npm run build` clean (`tsc` no errors; main bundle ~731 kB, +~7 kB).

---

## P2 — Tools & actions ✅ (built & tested, this run)

**`+` menu** in the composer (popover, badge counts active tools): **Upload file**, **Attach image**
(or **paste** straight into the box), **Web research** toggle, **Show thinking** toggle, **Connector
toggles** (the session's connected integrations → live tools), and a **Choose from Drive** item left as
honest "soon" (Google read isn't wired — matches the Conductor's `read_drive`).

**Attachments** — `core/attachments.py` splits uploads into (a) **text** (txt/md/code/json/csv + **PDF**
via `pypdf`, graceful "install pypdf" note if absent) folded into the turn as context for the normal
tool-loop, and (b) **images** kept as data-URLs. Images go through a **native vision** path —
`model_router.vision_complete()` builds the provider-correct multimodal message (**Anthropic image
blocks / OpenAI `image_url`**) and calls the model directly (no tool-loop); `supports_vision()` gates it,
and a non-vision model gets an honest "switch to Claude/GPT-4o/Gemini" note instead.

**Web research → live tool + citations** — a new **opt-in** Conductor tool **`web_search`** (reuses
`research_engine.tavily_search`, mock-fallback without a key) that is **only advertised when the owner
toggles Web research** (so #7's base 10-tool catalog is untouched — it lives in `OPTIONAL_TOOLS`, wired
into `ALL_TOOLS`/`RISK` for execution). The directive asks TOBI to cite sources in a `tobi:reference`
block, which the P1 renderer already draws.

**Connector emphasis** — enabling a connector adds a per-turn **directive** naming it so TOBI prefers its
tools (the read tools already exist from #7); the toggle gates intent, not availability.

**Message actions** — **Edit → branch**: editing a user message **forks** the session up to that point
into a NEW session (`chat_store.fork_session`, original preserved + switchable in the sidebar, marked `↳`)
and runs the edited turn there; **feedback** 👍/👎 (`chat_messages.feedback` + `/api/chat/messages/{id}/
feedback`). Copy / Regenerate / Remember carried from P1.

**System action log** — an **Activity panel** (header toggle) listing this session's **TOBI Actions**
(#7, scoped via `list_actions(chat_id=…)`) with tool/risk/status badges; inline **tool chips** during a
turn and on the collapsed "Thought for Xs" already cover the inline-chip half.

**API:** stream request gains `attachments` / `web_research` / `thinking` / `connectors`; new
`POST /api/chat/sessions/{id}/fork`, `POST /api/chat/messages/{id}/feedback`,
`GET /api/chat/sessions/{id}/activity`. `requirements.txt` adds `pypdf`.

**Tests:** web_search opt-in + answer-runs-it + directives + attachments split/extract + vision
flags & native message format + feedback + fork + scoped activity = **25/25**; **#7 P3 17/17, #8 P1 26/26,
P1b 10/10 regressions intact**; frontend `npm run build` clean (`tsc` no errors; main bundle ~724 kB, +~10 kB).

---

## P1 — Foundation & feel ✅ (built & tested, this run)

**Provider abstraction + vault-backed routing** — refactored `core/model_router.py` into a **7-provider
registry** (Anthropic native · OpenAI · OpenRouter · Google Gemini · xAI Grok · Ollama-local · custom
OpenAI-compatible) over three client kinds (`ClaudeClient` native, `OpenRouterClient` w/ headers+429
fallback, `OpenAICompatibleClient` for the rest) + a `FallbackClient` that tries an **ordered chain**.
Routing prefs (global **default** + **per-task overrides** + **fallback** + per-provider base_url/models)
live in a new **`llm_config`** table (non-secret → no vault needed to read); **API keys stay in the
Genesis vault** (#4), read via `os.getenv`. `get_llm(task_type, model=None)` honours an explicit model
(chat picker) → per-task override → default → **legacy `PRIMARY_MODEL` env** (fully backward-compatible:
unconfigured = today's behaviour). Introspection: `provider_catalog()` (key-presence/base_url/models),
`available_models()` (flat `provider:model` picker list), `discover_models()` (live OpenRouter/OpenAI/
Ollama fetch → persists, else known defaults).

**Hermes alignment (MC → Hermes push)** — `core/hermes_sync.py` writes the chosen routing to Hermes on
every save, **one-way & defensive** (never crashes the save): JSON sidecar `~/.hermes/config/tobi_models.json`
(always) + `hermes.yaml` `cost_optimization.model_routing` patch (if PyYAML present) + `hermes config set`
(if a `hermes` binary is on PATH).

**Sessions** — `core/chat_store.py`: `chat_sessions` (title/model/timestamps) + `chat_messages`
(role/content/model/tokens/`thinking`, `parent_id` reserved for P2 branching). Create / **auto-title**
(heuristic from the first message) / rename / delete / **per-session model**. Each session maps to a
stable **negative `chat_id`** so the Conductor's per-conversation state (pending actions, rolling history)
is isolated per session without colliding with the dashboard chat (990001) or Telegram ids.

**Typed streaming + thinking UX** — new SSE endpoint `POST /api/chat/sessions/{id}/stream` emits
**typed events**: `thinking` (phase + tool chips), `delta` (smoothed chunks), `action` (high-risk
confirmation), `usage` (tokens + latency), `done`. The Conductor (#7) `answer()` now accepts **`model`**
(thread the picker) + **`history`** (session store owns context). Chat UI: live **timer + phase + tool
chips** while working, collapsing to **"Thought for Xs · N tok"** (expandable); **Stop** (AbortController,
keeps partial) + **Regenerate**; per-message **Copy** + **Remember**.

**Rich output (full-width)** — dependency-free `components/chat/MarkdownView.tsx`: headings, bold/italic/
inline-code, links, ordered/unordered lists, fenced **code w/ copy**, **GFM tables**, blockquotes, hr —
**plus structured ```tobi:card | tobi:table | tobi:callout | tobi:keyvalue | tobi:reference | tobi:status```
JSON blocks** as components. **Assistant = full-width blocks; user = bubbles.**

**Model config page** — `/models` (sidebar bottom-menu, `Cpu` icon): provider cards (key-status, vault-gated
key save, enable toggle, editable base_url for Ollama/custom, **Discover models**), **Routing** (default +
per-task overrides + drag-ordered **fallback chain**), **Push to Hermes** button + result, P3 analytics
placeholder. Vault-unlock gate inline.

**API:** chat sessions CRUD + `/append` + `/stream`; `/api/llm/config` (GET/POST, POST also pushes Hermes),
`/api/llm/models`, `/api/llm/provider/{id}/key` (vault-gated), `/api/llm/discover/{id}`, `/api/llm/hermes-push`.
`init_database` eagerly creates `chat_sessions`/`chat_messages`/`llm_config` (modules also create lazily).

**Tests:** `model_router` config/catalog/resolution/fallback + `chat_store` sessions/messages/auto-title +
`hermes_sync` push = **26/26**; per-session turn (model+history threading through the Conductor, persistence,
tool-loop) = **10/10**; **#7 Conductor P3 regression intact = 17/17**; frontend `npm run build` clean
(`tsc` no errors; main bundle ~714 kB, +~37 kB for the whole workspace).

---

## 1. Current state → the gap

Today `dashboard/src/pages/Chat.tsx` is a **single streaming bubble list** wired to
`brain.chat_stream` with a "remember" action. There is **no** model picker, provider config,
thinking UI, token/context meter, file/image input, `+` menu, rich output, message actions,
sessions, or analytics. The router (`core/model_router.py`) is **env-driven** (`PRIMARY_MODEL`),
OpenRouter + Claude only, with fallback only on a 429. This upgrade closes all of that.

---

## 2. Expected result (definition of success)

A premium chat where:
- I **see and switch the active model**, configure providers/keys/models in a Settings page that is
  the **single source of truth** — and **Hermes' model config is driven from it**.
- *"I connected many LLM endpoints in MC; the Hermes LLM agent is configured from this as well."* ✅
- TOBI **shows its thinking/reasoning** (native when the model supports it), with a **live timer +
  token count**, collapsing to **"Thought for Xs"**.
- A **`+` menu** opens file upload, Drive pick, image paste, thinking toggle, web research, and
  **connector toggles** (Notion/Vercel/Supabase…) that become **live tools** for that message.
- Output renders **richly in the chat space** — cards, tables, lists, headers, icons, links,
  references — as **full-width blocks**, not cramped bubbles.
- Each message has **copy / regenerate / edit**, and editing **branches** the conversation.
- A **context-window energy bar** shows % full for the *current model's* real limit; at **~80%** it
  **alerts me to Compact** (summarize old turns, keep recent) with a **loading bar**.
- **Sessions** persist (auto-title, rename, delete, per-session model); a **system log** announces
  TOBI's actions/status/errors; a **usage dashboard** shows weekly tokens, per-model columns, cost, latency.

---

## 3. Deep research — what the best do, and what we adopt

| Capability | Claude | ChatGPT | Gemini | Grok | **TOBI adopts** |
|---|---|---|---|---|---|
| **Model picker / routing** | Model selector | Dropdown + "Auto" | Model selector | Mode selector | Default model + **per-task overrides** + **ordered fallback**, all vault-configured |
| **Visible reasoning** | Extended thinking (collapsible) | o-series reasoning summary | "Thinking" | "Think" mode | **Native traces when available + simulated fallback**, "Thought for Xs" |
| **Live metrics** | minimal | minimal | minimal | minimal | **Timer + live token count + tool-step chips** (power-user grade) |
| **Tools / connectors** | MCP + connectors | Connectors (Drive/GitHub…) + tools | Extensions | Tools | **`+` connector toggles → live function-calling tools** (via Conductor #7) |
| **Rich output** | **Artifacts** | **Canvas** | **Canvas** | inline | **Rich markdown + structured blocks** in chat space (artifacts/canvas considered later) |
| **Files / image** | upload + paste | upload + paste | upload | upload | **Native vision/docs + text fallback**, **paste image** |
| **Web search** | web search + cites | search + cites | grounding + cites | live search | **Reuse research engine + inline citations** |
| **Message actions** | copy/edit/retry | copy/edit(branch)/regen/feedback | copy/edit/regen | copy/regen | **Copy / regenerate / edit→branch / feedback** |
| **Sessions / projects** | Projects | Projects + history | Gems | history | **DB sessions: auto-title, rename, delete, per-session model** |
| **Context / compaction** | long ctx + memory | memory | long ctx | long ctx | **Per-model context energy bar + Compact (summarize) at ~80%** |
| **Usage analytics** | API console | API console | — | — | **In-app weekly tokens + per-model columns + cost + latency** |

**Takeaway:** the consumer apps hide the plumbing; power tools (LibreChat / OpenWebUI / API consoles)
expose model config, token/context meters, and usage. TOBI is a *personal* tool → we adopt the
**polish of the consumer apps + the transparency of the power tools.**

---

## 4. Feature spec (locked by the 30 Q&A)

### 4.1 Model config page (Settings → Models) — single source of truth
- **Storage:** reuse the **Genesis vault** with a dedicated **LLM-config surface** (provider, API key,
  base_url, discovered models). Keys encrypted; never returned in plaintext.
- **Providers (v1):** Anthropic (Claude), OpenAI (GPT), OpenRouter, **Google Gemini, xAI Grok, Ollama
  (local), and any OpenAI-compatible custom endpoint**. Connect → fetch/choose models.
- **Routing:** a **global default** model + **optional per-task overrides** (research/coding/simple/…)
  + an **ordered fallback chain** (try A→B→C on error/rate-limit).
- **Hermes alignment:** this page is the **master**; on save it **pushes to Hermes** — writing
  `~/.hermes` model config / invoking `hermes config set` — so TOBI's router **and** Hermes agents use
  the same models. Per-task/agent routing is **editable** here.
- **Analytics on the page (+ Health summary):** weekly **token trend**, **model-usage columns**
  (provider icon + model), **cost ($)** estimate, **calls/latency** — from **real per-call usage logging**
  across **all** TOBI LLM use (chat + agents + research + CEO), filterable by surface.

### 4.2 Thinking / reasoning UX
- **Native extended-thinking** rendered (collapsible) when the model emits it; **tasteful simulated
  "thinking…"** otherwise.
- During generation: **elapsed timer**, **live token count**, **tool-step chips** ("searching web…",
  "reading Notion…"); after finishing, collapse reasoning to **"Thought for Xs"** (expandable).
- **Stop / interrupt** button (keeps partial output) **+ one-click regenerate** (optionally a different model).
- Answer streams in **smoothed chunks** for a calm, non-jittery feel.

### 4.3 Input box + `+` menu
- `+` opens: **Upload file**, **Choose from Drive**, **Paste/attach image**, **Thinking toggle**,
  **Web research**, **Connector toggles** (connected 3rd-party apps: Notion/Vercel/Supabase…).
- **Attachments:** sent **natively** to vision/doc-capable models; **text-extracted** fallback otherwise.
  Types: **images (paste + upload), PDF, docs/text/code, Drive files**.
- **Connector ON → live tools:** the model gets that app's tools (function-calling) for the message —
  shares the **Conductor #7** tool layer.
- **Web research:** reuses the existing research/Tavily pipeline with **inline citations**.

### 4.4 Rich output in the chat space
- **Rich markdown** (tables, headers, lists, code with copy, links) **+ structured blocks** (cards,
  reference/citation lists, callouts, key-value, status) rendered as **components**.
- **Layout:** **assistant content is full-width blocks** spanning the chat; **my messages stay as
  bubbles**. (Artifacts/canvas side-panel is a later option.)

### 4.5 Message actions
- **Copy** (message + per-code-block), **Regenerate/reload** (optionally switch model), **Edit** a user
  message, **Branch** (edit **creates a new branch**, original preserved + switchable), **feedback** (👍/👎).

### 4.6 Context window + Compact
- **Energy bar** per the **current model's real context limit**, % full from **accurate token counting**
  (tiktoken for OpenAI-compatible, Anthropic token counting for Claude; per-model max table).
- **Compact:** at **~80%** full, alert + **one-click Compact** with a **loading bar** — **summarize older
  turns** (store the summary) while **keeping recent turns verbatim**; the summary persists to the session.

### 4.7 Sessions
- **DB-stored** sessions: **auto-generated titles**, **rename**, **delete**, and **each session remembers
  its model**. Sidebar list (search/pin later). (Telegram session sharing = later consideration.)

### 4.8 System action log
- **Inline status chips** between messages ("reading Notion…", "done", "error: …") **+ a collapsible
  activity/log panel** with history of TOBI's actions, statuses, and errors.

---

## 5. Architecture notes

- **Provider registry + vault config:** refactor `core/model_router.py` into a **provider abstraction**
  (Anthropic native; OpenAI/OpenRouter/Gemini/Grok/Ollama/custom via OpenAI-compatible client + base_url),
  reading **default + per-task + fallback** from the **vault-backed LLM config** (not just `PRIMARY_MODEL`).
- **Usage logging:** a `llm_usage` table (ts, surface, task_type, provider, model, prompt_tok,
  completion_tok, cost_est, latency_ms) written on every call → powers analytics.
- **Streaming protocol:** extend the SSE chat stream to carry typed events — `delta`, `thinking`,
  `tool_step`, `usage`, `done` — so the UI can render reasoning, chips, and live counters.
- **Rich blocks:** a fenced/JSON block convention the model emits (e.g. ```tobi:card`/`tobi:table`) →
  a block renderer; unknown/none → plain rich markdown.
- **Sessions/branches:** `chat_sessions` (id, title, model, created/updated) + `chat_messages`
  (session_id, role, content, parent_id for branching, model, tokens, ts).
- **Hermes sync:** a small adapter writes the chosen models to `~/.hermes` config / `hermes config set`
  on save (MC → Hermes push).
- **Token/context:** per-model context-limit table + tokenizer helpers for the energy bar + compaction trigger.

---

## 6. Phased plan (checkpointed)

- **P1 · Foundation & feel.** Provider registry + **vault-backed model config page** (+ Hermes push) +
  **model picker** in chat; **sessions** (create/rename/delete, per-session model); **thinking UX**
  (timer/token count/Thought-for-Xs/stop+regenerate); **rich block output** (full-width). *Checkpoint.*
- **P2 · Tools & actions.** `+` menu — **file upload, image paste, Drive, web research, connector
  toggles → live tools**; **message actions** (copy/regenerate/edit→branch/feedback); **system action
  log** (chips + panel). *Checkpoint.*
- **P3 · Meters & analytics.** **Usage logging** + **analytics** (weekly tokens, model columns, cost,
  latency) on the model page + Health; **context energy bar**; **Compact** (summarize, ~80% alert,
  loading bar). *Checkpoint → done.*

---

## 7. Acceptance criteria

1. Connect ≥2 providers in the model page; switch the chat model live; **Hermes config reflects the change**.
2. Ask something hard → see **thinking + live timer/token count**, then **"Thought for Xs"**; **Stop** works.
3. `+` menu: **paste an image** and **upload a PDF** answered correctly; toggle **Notion** → TOBI uses it as a tool.
4. A response renders a **table + card + reference list** as full-width blocks; **copy / regenerate / edit-branch** all work.
5. Long session: **energy bar** fills to ~80% → **Compact** summarizes and the bar drops; session **auto-titled & renamable**.
6. Model page shows **weekly tokens, per-model columns, cost, latency** from real logged usage.

---

## 8. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Provider sprawl / differing APIs | OpenAI-compatible abstraction + Anthropic native; capability flags (vision/thinking/tools) per model |
| Hermes coupling breakage | MC→Hermes **push** only (one-way); write config defensively, never crash chat on Hermes failure |
| Token/context inaccuracy | Real tokenizers + provider-reported usage; energy bar labeled "estimate" where needed |
| Streaming complexity (thinking+tools+usage) | Typed SSE events with graceful degradation (always at least `delta`+`done`) |
| Compaction losing context | Summarize-and-store, keep recent verbatim; summary visible/editable; never silent-destroy |
| Secrets exposure | Reuse vault encryption; keys never returned; provider config audited |

---

## 9. Dependencies

- **Genesis vault (#4)** — encrypted LLM key/config storage.
- **TOBI Conductor (#7)** — the tool/function-calling layer connector-toggles plug into.
- **Research engine** (`core/research_engine.py` / Tavily) — in-chat web research + citations.
- **Hermes** config (`~/.hermes`, `hermes config set`) — push target for model routing.
- Refactor of `core/model_router.py`; new `llm_usage`, `chat_sessions`, `chat_messages` tables.

---

## Appendix A — Full 30-question interview

**Model config:** storage = **reuse Genesis vault (LLM section)** · providers = **Anthropic + OpenAI +
OpenRouter + Gemini/Grok/Ollama/custom** · routing = **default + per-task overrides** · fallback =
**ordered chain**.
**Hermes:** **single source of truth** · **MC→Hermes push** · mechanism = **write ~/.hermes / hermes
config set** · per-task agent routing = **editable**.
**Analytics:** **log real usage per call** · scope = **all TOBI LLM usage (filterable)** · charts =
**weekly trend + model columns + cost + calls/latency** · location = **model page + Health**.
**Thinking:** **native + simulated fallback** · live = **timer + token count + Thought-for-Xs + tool
chips** · **stop + regenerate** · **smoothed chunks**.
**Input/+menu:** attachments = **native vision/docs + text fallback** · types = **images(paste+upload) +
PDF + docs/code + Drive** · connectors ON = **live tools** · web research = **research engine + citations**.
**Rich output:** **rich markdown + structured blocks** · layout = **assistant full-width blocks, user
bubbles** · actions = **copy + regenerate + edit + branch/feedback** · edit = **branch (keep both)**.
**Context/sessions/compact:** energy bar = **accurate tokenizer + per-model max** · compact =
**summarize old / keep recent (auto-suggest + manual)** · threshold = **~80%** · sessions = **DB-stored,
auto-title + rename/delete, per-session model**.
**System log / delivery:** log = **inline chips + side activity panel** · delivery = **phased w/
checkpoints (P1 config+sessions+thinking/rich → P2 +menu/files/connectors/actions → P3 analytics+context+compact)**.

---

## Appendix B — Evidence index (code is source of truth)

- Current chat UI: `dashboard/src/pages/Chat.tsx` (streaming bubbles, `streamBrainChat`).
- Router to refactor: `core/model_router.py` (env `PRIMARY_MODEL`, OpenRouter + Claude, 429 fallback).
- Chat backend: `core/brain.py` `chat`/`chat_stream`; `api/dashboard.py` `/api/brain/chat` (+SSE).
- Creds: `core/vault.py`, `core/integrations_registry.py`. Tools: Conductor #7. Research: `core/research_engine.py`.
- Hermes config: `HERMES_COST_OPTIMIZATION.md` (`hermes config set`, `model_routing`, `~/.hermes`).

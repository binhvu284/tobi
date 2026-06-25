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

# TOBI Conductor — conversational command of all of Mission Control

> **One-liner:** Turn TOBI from a chat-that-remembers into the **conductor of Mission Control** —
> a single conversational brain (MC chat *and* Telegram) that, grounded in an optimized second
> brain, can **read and act on every MC feature** by talking to me. Projects, tasks, agents,
> evolution, architecture, health, and external sources (Notion/GitHub/Drive) all become things
> TOBI can answer about and operate — accurately, from live data.
>
> **Queue #7** · **Date:** 2026-06-26 · **Builds on:** [SECOND_BRAIN_DIRECTION.md](SECOND_BRAIN_DIRECTION.md)
> (the memory substrate) · **Owner-reviewed via 30 Q&A** (Appendix A).
>
> **Status: ✅ Done (v1) — P0 (reused) · P1 · P2 · P3 all shipped & tested.** `core/conductor.py` is the one
> shared engine: classifier pre-route → memory-first grounding → provider-agnostic JSON tool-loop →
> butler voice + EN/VN mirror + strict grounding, with **7 read tools** (`get_evolution`,
> `explain_architecture`, `office_status`, `list_projects`, `list_tasks`, `check_health`, `recall`).
> Wired into **both surfaces** — MC chat (`/api/brain/chat` + SSE repointed through the Conductor) and
> Telegram (`handle_chat` STATUS/QUESTION). 17/17 venv read tests pass.
>
> **P2 (act):** **7 act tools** with risk tiers — low/medium (`create_project`/`create_task`/`complete_task`/
> `remember`/`update_project_progress`) auto-execute & report; high (`delete_task`/`run_mission`) are
> **proposed** and run only after the owner confirms (Confirm/Cancel card surfaced via an SSE `action` event,
> **or** a typed "yes"/"có"). **Surface asymmetry enforced** (MC full · Telegram read+low-only). **TOBI Actions
> audit** (lazy `tobi_actions` table → `/actions` page + `/api/conductor/actions`/`/confirm`). **Log-and-learn**
> (habit notes to the Brain). 24/24 venv act tests pass; frontend builds clean.
>
> **P3 (external + chains):** 3 external read tools over the existing connectors (`read_notion` w/ a new
> `get_page_content` block reader · `read_github` · `read_drive` honest-stub), all graceful when a source isn't
> connected; new `assign_task` act tool. **Multi-step chains** in one turn (e.g. read_notion → create_project →
> create_task → assign_task), each step grounded in the prior step's ids; **stop-on-failure** halts and reports
> exactly what was done vs. failed. Catalog: **10 read + 8 act tools**. 17/17 venv P3 tests pass. **Acceptance set
> all green** (§6). Conductor v1 complete.

---

## 1. The problem (owner's words)

> "Currently TOBI has many features in Mission Control, but those features can't actually link and
> coordinate. TOBI also has no impact on Mission Control features. Need to restructure / refactor /
> extend so the features in MC are connected to TOBI — **TOBI can have a huge impact on MC just by
> communicating with me.**"

Today the pieces exist but are **siloed**:
- **MC features** are separate pages backed by separate DB ops / API endpoints (Projects, Tasks,
  Office/Agents, Evolution, Architecture, Health, Integrations). Nothing lets one *drive* another.
- **TOBI's chat** is essentially **memory Q&A** (`brain.chat`) — it can talk about *me*, but it
  can't read live MC state or take MC actions.
- **The two chat surfaces** (MC dashboard chat, Telegram) don't share one brain or one tool set.
- There is **no conversational control plane** — no way to say "create this project and assign it,"
  or ask "what tier am I on?" and get the *real* number.

**Result:** TOBI is a smart memory, not yet a Jarvis that *runs the house*.

---

## 2. Expected result (definition of success)

TOBI has an **optimized second brain**, interacts well in chat, and can **interact with any feature
in Mission Control** (create task, project, check health, …) — all requestable from **both** the MC
chat and Telegram. **Every feature and TOBI are connected to each other.** Concretely, these all work:

- *"TOBI, read this project in Notion and create the project + tasks and assign them in Mission Control."*
- *"TOBI, what is my level right now on the evolution roadmap?"* →
  "According to my evolution data, I'm currently in the **Genesis** tier, sir — about **92%** complete,
  with 11 of 12 abilities active."
- *"TOBI, how many agents do I have in the office, and list the role of each."* →
  "There are currently **4** agents in the office, sir: <list with roles>. All are free for a new task right now."
- *"TOBI, report the agent status right now."* →
  "Of course, sir. Agent **<name>** is working on project **<project>**, task **<task>** — **70%** complete.
  **3** agents are free right now."
- *"TOBI, explain your architecture for me."* →
  "Of course, sir. According to my architecture data, <grounded explanation>."
- *"TOBI, check system health"* / *"create a project / task"* — from either surface.

Every numeric/state claim above must come from a **live tool call**, never the model's imagination.

---

## 3. What already exists to reuse (don't rebuild)

This is mostly a **connective layer**, not a rewrite — the raw materials are here:

| Capability | Where | Reuse as |
|---|---|---|
| Native **tool-use loop** (Anthropic `tool_use`, tool defs + dispatcher) | `core/telegram_bot.py` `_run_coding_agent` / `_CODING_TOOLS` / `_execute_tool` | The pattern for the **MC Tool Catalog** + agent loop |
| **Memory-first** brain (`owner_context`, retrieval, profile) | `core/brain.py` | Grounding substrate on every turn |
| **All MC features as DB ops + APIs** | `core/database.py`, `api/dashboard.py`, `core/office*.py`, `graph_engine.py` | Backends each tool calls |
| **Regex classifier** (SMALLTALK/CODING/STATUS/EXECUTION/RESEARCH) | `core/task_classifier.py` | Cheap **pre-router** in front of the tool-loop |
| **Two chat surfaces** | MC `/api/brain/chat` (+ SSE), Telegram handlers | The two front doors onto one engine |
| **Genesis vault** (encrypted creds) + **integrations registry** | `core/vault.py`, `core/integrations_registry.py` | Auth for external tools (Notion/GitHub/Drive) |
| **Live evolution/genesis status, office stats, health** | `_genesis_status`, `getOfficeStats`, `/api/health` | Read tools return exact live data |

**The gap = the orchestration layer**: a shared engine + a catalog of MC tools + permissioning +
grounding + the second-brain context, wired into both surfaces.

---

## 4. The design (locked by the 30 Q&A)

### 4.1 Architecture — one shared **Conductor** engine

```
        ┌─────────────────┐         ┌────────────────────┐
        │  MC chat (web)  │         │  Telegram (mobile) │
        │  full power     │         │  read + safe ops   │
        └────────┬────────┘         └─────────┬──────────┘
                 │   (thin adapters: buttons/modals vs inline buttons)
                 └──────────────┬──────────────┘
                                ▼
               ┌──────────────────────────────────┐
               │   CONDUCTOR  (one shared engine)  │
               │  1. classifier pre-route (cheap)  │
               │  2. memory-first context (brain)  │
               │  3. tool-loop (native func-calls) │  ← scoped tool set per intent
               │  4. risk gate + confirmation      │
               │  5. log + learn (write to brain)  │
               └───────────────┬───────────────────┘
                               ▼
        ┌──────────────── MC TOOL CATALOG ───────────────┐
        │ READ: evolution · architecture · agents/office │
        │       projects · tasks · health · notion/github│
        │ ACT : create/update project · create/assign/   │
        │       complete task · run mission · ext writes  │
        └───────────────────┬─────────────────────────────┘
                            ▼  (existing DB ops / dashboard APIs / integrations)
                 Projects · Tasks · Office · Evolution · Architecture · Health · Vault
```

- **Hybrid routing:** the regex classifier cheaply pre-routes (smalltalk/coding stay fast); anything
  about MC state or actions enters the **tool-loop** with an **intent-scoped** subset of tools
  (saves tokens, reduces wrong-tool errors).
- **One engine, thin adapters:** MC chat and Telegram share the Conductor; only rendering differs
  (MC confirm-modal / "Open page →" links vs Telegram inline buttons / URL).
- **Strict grounding:** every number/status comes from a tool call. No live tool → say so + offer to fetch.

### 4.2 MC Tool Catalog (v1 target)

| Area | Read tools | Act tools (risk tier) |
|---|---|---|
| **Evolution** | `get_evolution()` → tier, %, abilities | — |
| **Architecture** | `explain_architecture()` → grounded from architecture data | — |
| **Office/Agents** | `list_agents()`, `agent_status()` → count, roles, working/free, current mission+progress | `assign_agent()` (medium) |
| **Projects** | `list_projects()`, `get_project()` | `create_project()` (low), `update_project()` (medium), archive (medium), delete (**confirm**) |
| **Tasks** | `list_tasks()`, `get_task()` | `create_task()` (low), `assign_task()` (medium), `complete_task()` (low), delete (**confirm**) |
| **Missions** | `mission_status()` | `run_mission()` (**confirm**) |
| **Health** | `check_health()`, `deep_test()` | — |
| **Brain** | `recall(query)` | `remember(fact)` (low) |
| **External** | `read_notion(url)`, `read_github(repo)`, `read_drive()/gmail` | external writes (**confirm**) |

Each tool is a thin wrapper over an **existing** DB op / API → low risk to build.

### 4.3 Permissions & confirmation (tiered)

- **SOUL.md 3-tier model:** low = auto-execute + report · medium = act + report · high = propose + wait.
- **Always confirm:** delete/destructive, run/execute missions. (External writes also gated.)
- **Without confirmation:** only **trivially-reversible** acts (e.g. archive, mark done).
- **Confirm UX:** inline **buttons** (Telegram) / confirm button/modal (MC), with **typed "yes"** fallback.
- **Surface asymmetry:** **Telegram = read + safe ops**; **MC = full power** (risky actions live at the desk).

### 4.4 Voice, language, grounding

- **Persona:** polished **butler "sir"** tone (Jarvis/Alfred), consistent with the examples.
- **Language:** **mirror my message** (English ↔ Vietnamese per turn).
- **Uncertainty:** *"I don't have that data, sir"* + **offer to fetch** (run the check / connect the source).
  Never fabricate numbers or status.
- **Transparency:** a **brief working status** ("Checking evolution data…") then the clean answer.
- **Deep links:** when relevant, link to the MC page (MC chat shows "Open Evolution →"; Telegram gets a URL).

### 4.5 Second brain (the substrate)

- Built on the **optimized second brain** from [SECOND_BRAIN_DIRECTION.md](SECOND_BRAIN_DIRECTION.md)
  (Awakening "Understand Me": auto-profile, memory-first retrieval, entity extraction).
- **Memory-first context** (recommended balance): an **always-on compact profile header** on every
  turn + **on-demand retrieval** when the message is personal/contextual — quality without token bloat.
- **Log + learn:** actions TOBI takes are recorded **and** mined for preferences (e.g. "always assigns
  research tasks to agent X") → written back to the brain.

### 4.6 Orchestration, failure, audit, proactivity

- **Multi-step chains in v1:** e.g. *read Notion → create project → create tasks → assign* in one
  request, with the confirmation gate before state changes.
- **On partial failure:** **stop and report clearly** — exactly what succeeded and what didn't.
- **Audit:** a visible **"TOBI Actions"** log in Mission Control, backed by DB (every action: what, when, result).
- **Proactivity:** **suggest-then-act** — "Want me to create tasks for this, sir?" → acts on yes
  (auto only the trivial/low-risk).

---

## 5. Phased plan (checkpointed)

- **P0 · Foundation — optimized second brain.** Complete the Awakening "Understand Me" memory-first
  layer per the report (profile + retrieval + extraction). *Grounds everything below.* *Checkpoint.*
- **P1 · Read/answer all features.** Conductor engine + classifier pre-route + **read** tool catalog
  (evolution, architecture, agents, projects, tasks, health) wired into **both** surfaces, strict
  grounding, butler voice. → All "answer about MC" examples pass. *Checkpoint.*
- **P2 · Actions (internal MC).** Add **act** tools (create/assign/update/complete, run-mission) with
  tiered permissions + confirmation UX + the **TOBI Actions** audit view + log-and-learn. *Checkpoint.*
- **P3 · External orchestration + chains.** Notion/GitHub/Drive read tools + **multi-step chains**
  (Notion → project → tasks → assign), stop-on-failure reporting. → All examples pass. *Checkpoint → done.*

---

## 6. Acceptance set (must all pass)

1. **Evolution tier + Architecture explain** — exact live tier/% and a grounded architecture explanation.
2. **Agent count/roles + status report** — real counts, roles, who's working on what at X% and who's free.
3. **Notion → create project/tasks/assign** — read a Notion project and build it in MC with assignments.
4. **Health + create task/project by chat** — "check health" and "create a project/task," on **both** surfaces.

Plus: every numeric/state answer is **tool-sourced** (no fabrication); risky actions are **confirmed**;
Telegram is read+safe while MC is full power.

---

## 7. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Model invents numbers/status | **Strict grounding**: numbers only from tools; refuse + offer to fetch otherwise |
| Wrong/destructive action | Tiered gate + **confirm** on delete/mission-run; Telegram can't do risky ops |
| Tool sprawl / token cost | **Intent-scoped** tool sets; classifier pre-route; compact profile header |
| Two surfaces drift | **One shared engine**, thin adapters only |
| Partial multi-step failure | **Stop + report**; audit log; (rollback considered later) |
| Second brain not ready | P0 foundation first; read-only P1 still useful without write actions |

---

## 8. Dependencies

- **Second brain** (Awakening "Understand Me") — [SECOND_BRAIN_DIRECTION.md](SECOND_BRAIN_DIRECTION.md). *(P0)*
- **Genesis vault** (#4) — credentials for external tools.
- **Integrations registry** (#4) + connectors (`core/integrations.py`) — Notion/GitHub/Drive reads.
- Existing tool-use loop, classifier, brain, and all MC DB ops / APIs.

---

## Appendix A — Full 30-question interview

**Scope:** full scope (read **and** act) · **all** areas (Projects/Tasks, Office/Agents,
Evolution/Architecture, Health/Integrations) · **full read + write** v1 · **breadth-first**.
**Permissions:** **tiered** (SOUL.md 3-tier) · confirm on **delete + run/execute missions** ·
confirm UX = **buttons + typed yes** · destructive only if **trivially-reversible**.
**Architecture:** **hybrid** (classifier pre-route + function-calling tool-loop) · **one shared engine** ·
**intent-scoped** tools · classifier = *my call* → **keep as cheap pre-router**.
**Surfaces:** **Telegram read+safe, MC full** · **brief status then answer** · **both co-equal** ·
**deep-link to MC pages**.
**Voice/grounding:** **butler "sir"** · **mirror my language** · uncertainty = **say it + offer to fetch** ·
**strict live-data-only** grounding.
**Brain/external:** memory-first = *my call* → **always-on compact profile + on-demand retrieval** ·
**log + learn** write-back · external orchestration **in v1** · sources = **Notion + GitHub + Drive/Gmail**.
**Orchestration:** **full chains in v1** · partial failure = **stop + report** · audit = **MC view + DB** ·
**suggest-then-act**.
**Delivery:** **phased with checkpoints** (P1 read → P2 act → P3 external) · acceptance = **all four**
example sets (evolution+architecture, agents count/status, Notion→create, health+create).

---

## Appendix B — Evidence index (code is source of truth)

- Tool-use loop pattern: `core/telegram_bot.py` `_run_coding_agent` L363, `_CODING_TOOLS`/`_execute_tool` L255–417.
- Brain memory-first: `core/brain.py` `owner_context` / `retrieve` / `chat`.
- Live status reads: `api/dashboard.py` `_genesis_status` / `/api/evolution`, `getOfficeStats`, `/api/health`.
- MC write ops: `core/database.py` (projects/tasks/agents CRUD), `api/dashboard.py` PM endpoints.
- Creds + external: `core/vault.py`, `core/integrations_registry.py`, `core/integrations.py`.

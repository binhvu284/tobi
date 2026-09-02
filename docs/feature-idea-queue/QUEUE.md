# Feature Development Queue

One row per item, newest first. Everything explaining the columns is below the table.

> Queue snapshot refreshed 2026-09-02. #21, #33, and #34 are committed and green.
> #34/T08 is owner-accepted and Done. #35/T00 is owner-accepted; #35/T01-T02 are complete; T02A is engineering-green and awaiting owner retest.

| # | ID | Name | Description | Status | Notes |
|---|----|------|-------------|--------|-------|
| 37 | `DEV-QUEUE-037` | [**Prepare a proposal to fix the next real MC limitation**](PREPARE_A_PROPOSAL_TO_FIX_THE_NEXT_REAL_MC_LIMITATION_PLAN.md) | prepare a proposal to fix the next real MC limitation | Draft | Created from an owner-confirmed Mission Control Chat proposal. |
| 36 | `FOUND_BASE-CORE-20D-013` | [**TOBI Agent Mission Control UI 2.0**](TOBI_UI_2_SPEC.md) | One live screen where you talk to TOBI and he runs the whole of Mission Control for you. | 🟡 Queued (spec in discussion) | The UI shell is finished and accepted as a working prototype, not a mockup: [TOBI_UI_2_SHELL.html](TOBI_UI_2_SHELL.html), open in any browser, no build step. It fixes both screens, five agent states, tool-call rows with folding, failure and retry, stop, the three voice modes, the canvas panel/document split, and the full token and scale system. Build the front end to match it exactly. Everything behind the glass is still open: voice providers, the real-time transport and turn-taking, how every MC feature becomes something TOBI can do from this screen, session state, and what a live session may spend or do unattended. The 30-question owner review is running now; the size is provisional until it closes. |
| 35 | `UPG-CORE-8D32H-012` | [**TOBI Agent Tier Completion**](AGENT_TIER_COMPLETION_PLAN.md) | TOBI finishes assigned digital work safely and proves exactly what happened. | 🔵 In progress (T02A Round 4 repair green; owner retest next) | T00 is owner-accepted. T01 supplies the persisted seven-ability evidence registry. T02 routes seven qualified local Agent workflows through canonical Runtime. T02A adds no-side-effect Chat-to-Developer proposals, one confirmed linked workflow, truthful status/evidence, and generated-artifact access. Round 4 keeps the concise instruction objective while preserving the full owner message in the proposal, risk decision, confirmation card, Queue description, and generated plan; bare pronoun requests clarify when no supporting detail exists. After confirmation, Chat-created work deliberately enters the canonical `QUEUE.md`; before confirmation it cannot change the roadmap. Focused checks pass 47/47, the shared gate passes 33/33, TypeScript passes, and the production dashboard build passes. Owner live retest remains. Tier II remains evidence-derived; package code alone grants no percentage. DeepSeek Harness remains outside #35. [history](QUEUE_DELIVERY_LOG.md#item-35) |
| 34 | `UPG-CORE-2D12H-011` | [**TOBIval Operational Intelligence and Model Independence**](TOBIVAL_OPERATIONAL_INTELLIGENCE_PLAN.md) | Real exams prove TOBI's quality, while common MC work relies less on the selected model. | ✅ Done | T08 repairs the overclaimed T07 evidence path. The approved live rerun used all 72 frozen cases and 14 holdouts without changing the baseline. It recorded 156/156 model responses, ECR `100`, scoped LDR `8.8021`, raw model pass `32.0513%`, deterministic recovery `67.9487%`, no provider failures, and no artifact blocker. The default owner CLI, shared 29-suite gate, dashboard build, and desktop/mobile Eval checks pass. The owner accepted the revision-bound artifact on 2026-08-30. Production routing remains limited to narrow safe workflows with no required fields. [history](QUEUE_DELIVERY_LOG.md#item-34) |
| 33 | `CHECK-CORE-4H-007` | [**One-click infrastructure test**](INFRASTRUCTURE_SELF_CHECK_SPEC.md) | One button on Health that proves the whole engine works on this machine. | ✅ Done (merged `a317604`) | Health -> Infrastructure and the shared release-suite registry are committed. The inherited #21 gate passed 24/24 on 2026-08-25, including infrastructure and no-console-window checks. [history](QUEUE_DELIVERY_LOG.md#item-33) |
| 32 | `UPG-CORE-3H-010` | [**Health checks run together**](HEALTH_CHECKS_CONCURRENT_SPEC.md) | The health button finishes in one check's time, not all of them added up. | ✅ Done (merged) | Was 20-50s, sequential, showing nothing until the end. A regression from #30's honest chat check (18.5s of it). Now concurrent and streamed: integrations instant, Telegram and Tavily at 2.3s, chat check at 8.3s. Both synchronous network calls moved off the event loop. [history](QUEUE_DELIVERY_LOG.md#item-32) |
| 31 | `FIX-CORE-8H-002` | [**Pages tell you when they fail to load**](PAGES_REPORT_LOAD_FAILURES_SPEC.md) | A page that cannot load its data says so, instead of just looking empty. | ✅ Done (merged `04e2148`) | 79 handlers across 29 files: `LoadFailure` where a page cannot render, `softFail` for background work, stated reasons where silence is right. `/api/health` 4,076ms -> under 500ms. [history](QUEUE_DELIVERY_LOG.md#item-31) |
| 30 | `CHECK-CHAT-2H-006` | [**Chat self-check**](CHAT_SELF_CHECK_SPEC.md) | One button that proves Chat really works, not just that a model replies. | ✅ Done (merged `be5e198`) | Health and the startup banner now run a real two-turn conversation with a tool. Caught the `input_text` defect live. [history](QUEUE_DELIVERY_LOG.md#item-30) |
| 29 | `CHECK-DEV-8H-005` | [**Fallback recovery test**](FALLBACK_RECOVERY_TEST_PLAN.md) | Checks TOBI recovers properly when a step fails midway. | ⏸️ On hold (absorbed by #34) | Preserve its history, but do not implement it separately. #34 includes recovery, provider failure, and duplicate-side-effect cases in one frozen Eval baseline. [history](QUEUE_DELIVERY_LOG.md#item-29) |
| 28 | `CHECK-DEV-3H-004` | [**Coding Agent V2 OpenCode acceptance fixture**](CODING_AGENT_V2_OPENCODE_ACCEPTANCE_PLAN.md) | The same coding-agent proof, run with a different worker. | ✅ Done (merged 2026-07-30) | OpenCode is locked out of V2 development after this run. [history](QUEUE_DELIVERY_LOG.md#item-28) |
| 27 | `CHECK-DEV-3H-003` | [**Coding Agent V2 MC Native acceptance fixture**](CODING_AGENT_V2_MC_NATIVE_ACCEPTANCE_PLAN.md) | A tiny safe job used to prove the coding agent works end to end. | 🟡 Ready (waiting on #22 matrix) | Run only after the final #22 patch is active. Never in parallel with #28. [history](QUEUE_DELIVERY_LOG.md#item-27) |
| 26 | `CHECK-CHAT-3H-002` | [**Regression suite for the chat task classifier**](REGRESSION_SUITE_FOR_THE_CHAT_TASK_CLASSIFIER_PLAN.md) | Locks in how TOBI decides what a message is about, so it cannot drift. | ✅ Done (merged 2026-07-28) | [history](QUEUE_DELIVERY_LOG.md#item-26) |
| 25 | `FIX-SKILL-3H-001` | [**Awakening external read requires verified test evidence**](AWAKENING_EXTERNAL_READ_REQUIRES_VERIFIED_TEST_EVIDENCE_PLAN.md) | A connector counts as working only after a real test passes, not a saved key. | ✅ Done (merged 2026-07-28) | Configured credentials are never proof on their own. [history](QUEUE_DELIVERY_LOG.md#item-25) |
| 24 | `CHECK-DEV-8H-001` | [**testing**](TESTING_PLAN.md) | Placeholder. Needs a real name and purpose. | ⚪ Draft (needs a real name) | Rename it or delete it. [history](QUEUE_DELIVERY_LOG.md#item-24) |
| 23 | `UPG-NEWS-3D-009` | [**News Page V2**](NEWS_PAGE_V2_PLAN.md) | A personal news feed that learns what you like and tells you why it showed it. | 🟢 Engineering complete (v2 - 100%) | Every part is built, including Save to Brain and asking TOBI about the News in Chat. Flag still off: run `python scripts/news_launch_gate.py` and look at the page in your themes, then turn it on. [history](QUEUE_DELIVERY_LOG.md#item-23) |
| 22 | `UPG-DEV-3D-008` | [**TOBI Coding Agent V2**](TOBI_CODING_AGENT_V2_PLAN.md) | The coding agent saves its progress, so a crash resumes instead of restarting. | ✅ Done (Codex-only V2 qualified 2026-08-01) | Codex is the only qualified worker. [history](QUEUE_DELIVERY_LOG.md#item-22) |
| 21 | `FOUND_BASE-CORE-5D20H-002` | [**Mission Control Infrastructure V2**](MISSION_CONTROL_INFRASTRUCTURE_V2_PLAN.md) | One engine behind every request, so nothing is lost when something crashes. | ✅ Done (v2 foundation) | T00-T15 delivered. Owner main-gate test T1-T4 passes; "the model is struggling" was a sandboxed server with no network, now reported honestly. Rollout controls remain off. [history](QUEUE_DELIVERY_LOG.md#item-21) |
| 20 | `UPG-BRAIN-3D-007` | [**Brain Context & Architecture V2**](BRAIN_CONTEXT_ARCHITECTURE_V2_PLAN.md) | Memory that is checked for quality before TOBI uses it to answer. | ✅ Done (V2 authoritative) | The legacy Brain UI is still in place. [history](QUEUE_DELIVERY_LOG.md#item-20) |
| 19 | `NEW-CORE-8H-003` | [**Performance "System Doctor"**](PERFORMANCE_DOCTOR_SPEC.md) | A health check that finds what is slow and tells you why. | ✅ Done (v1) | [history](QUEUE_DELIVERY_LOG.md#item-19) |
| 18 | `FOUND-DEV-3D-009` | [**TOBI Coding Agent / Controlled Self-Development System**](TOBI_CODING_AGENT_SELF_DEVELOPMENT_PLAN.md) | TOBI can write and ship its own code changes, under your approval. | ✅ Done (backend - VPS acceptance pending) | Superseded by #22. [history](QUEUE_DELIVERY_LOG.md#item-18) |
| 17 | `UPG-SKILL-1D8H-006` | [**Awakening Tier 1 Completion**](AWAKENING_TIER_1_COMPLETION_PLAN.md) | Proves TOBI's nine core abilities really work, with evidence, not claims. | ✅ Done (fully re-verified) | [history](QUEUE_DELIVERY_LOG.md#item-17) |
| 16 | `UPG-CHAT-3D-005` | [**Chat Mode Backend Upgrade**](CHAT_MODE_BACKEND_UPGRADE_PLAN.md) | Chat and Agent modes behave differently and honestly, with a Deep Research switch. | ✅ Done (v1 + security follow-up) | Two UX follow-ups are still open. [history](QUEUE_DELIVERY_LOG.md#item-16) |
| 15 | `UPG-OFFICE-1D8H-004` | [**Office V3**](OFFICE_V3_AGENT_OFFICE_INTEGRATION_PLAN.md) | The office becomes a command center you can actually run missions from. | ✅ Done (v1) | [history](QUEUE_DELIVERY_LOG.md#item-15) |
| 14 | `FOUND-SKILL-1D8H-008` | [**TOBI Premium Ability**](TOBI_PREMIUM_ABILITY_PLAN.md) | TOBI can read YouTube videos and images, and manage its own skills. | ✅ Done (v1 + review follow-up) | [history](QUEUE_DELIVERY_LOG.md#item-14) |
| 13 | `UPG-THEME-1D8H-003` | [**Theme v2 System Upgrade**](THEME_V2_SYSTEM_UPGRADE_PLAN.md) | Twelve themes that restyle the whole app without breaking any page. | 🔵 In progress (v2.1b - 85%) | An owner-review round is built and waiting to be looked at. [history](QUEUE_DELIVERY_LOG.md#item-13) |
| 12 | `UPG-PROJ-3D-002` | [**Project v2**](PROJECT_V2_SPEC.md) | A full workspace per project: tasks, files, icons and progress in one place. | ✅ Done (v1 + v1.1) | [history](QUEUE_DELIVERY_LOG.md#item-12) |
| 11 | `FOUND-CLI-1D8H-007` | [**TOBI CLI**](TOBI_CLI_SPEC.md) | Run TOBI from a terminal with a `tobi` command. | ✅ Done (v1, P0-P3) | [history](QUEUE_DELIVERY_LOG.md#item-11) |
| 10 | `FOUND-CORE-20H-006` | [**Storage & Usage**](STORAGE_USAGE_SPEC.md) | See how much space TOBI uses and what each AI call costs you. | ✅ Done (v1, M1-M3) | [history](QUEUE_DELIVERY_LOG.md#item-10) |
| 9 | `FOUND-NEWS-1D8H-005` | [**Explore → News**](EXPLORE_NEWS_SPEC.md) | A page that gathers AI news, new models and tools worth knowing about. | ✅ Done (v1, A+B+C) | Replaced by #23. [history](QUEUE_DELIVERY_LOG.md#item-9) |
| 8 | `UPG-CHAT-3D-001` | [**Premium Chat**](PREMIUM_CHAT_SPEC.md) | A proper chat workspace where you can switch models mid-conversation. | ✅ Done (v1, P1-P3) | [history](QUEUE_DELIVERY_LOG.md#item-8) |
| 7 | `FOUND_BASE-CHAT-1D8H-001` | [**TOBI Conductor**](CONDUCTOR_SPEC.md) | Talk to Mission Control in plain words and it does the work for you. | ✅ Done (v1, P0-P3) | Being decomposed by #21 T08. [history](QUEUE_DELIVERY_LOG.md#item-7) |
| 6 | `FOUND-THEME-20H-004` | [**Living Machine**](MOTION_UX_SPEC.md) | Motion and polish across every page, so the app feels alive instead of static. | ✅ Done (v1, M1-M4) | [history](QUEUE_DELIVERY_LOG.md#item-6) |
| 5 | `NEW-LINK-3D-002` | [**MCP Hub**](MCP_SPEC.md) | Lets other AI tools use TOBI, and lets TOBI use theirs. | ✅ Done (v1, M1-M4) | [history](QUEUE_DELIVERY_LOG.md#item-5) |
| 4 | `FOUND-LINK-1D8H-003` | [**Genesis Complete**](GENESIS_SPEC.md) | Connect outside services and store their keys safely, inside Mission Control. | ✅ Done (v1) | Never expose vault, token or key values. [history](QUEUE_DELIVERY_LOG.md#item-4) |
| 3 | `FOUND-OFFICE-20H-002` | [**Living Office**](OFFICE_LIVING_SPEC.md) | A small game-like office where you watch TOBI's agents work. | ✅ Done (v1) | [history](QUEUE_DELIVERY_LOG.md#item-3) |
| 2 | `NEW-BRAIN-20H-001` | [**Graph View**](GRAPH_VIEW_SPEC.md) | A map of your notes and how they connect, like a web you can explore. | ✅ Done (v1) | [history](QUEUE_DELIVERY_LOG.md#item-2) |
| 1 | `FOUND-BRAIN-1D8H-001` | [**Brain**](BRAIN_SPEC.md) | TOBI remembers what matters about you, learns from chats, and keeps a profile. | ✅ Done (v1+v2) | Rebuilt by #20. [history](QUEUE_DELIVERY_LOG.md#item-1) |

---

## How To Read A Row

Six columns, and each answers one question:

| Column | Answers |
|---|---|
| **#** | Which item, in the order it was created |
| **ID** | What kind of work, where, how big — see [Item Code](#item-code) below |
| **Name** | What it is called, linked to its spec |
| **Description** | What it does, in one plain sentence anyone can picture |
| **Status** | Where it stands right now, with a short note in brackets |
| **Notes** | The one thing everyone working on TOBI needs to know today |

Full delivery detail for every item lives in [QUEUE_DELIVERY_LOG.md](QUEUE_DELIVERY_LOG.md), linked from each row. It is the evidence behind the status; the queue itself stays readable. Preserve old plans as design history.

## Item Code
<a id="item-code"></a>

Every row carries a code you can read at a glance, and use as the item's name in commits, branches, or conversation.

```
TYPE - AREA - TIME - NNN            FOUND_BASE-CORE-5D20H-002
 |      |      |     |              a hidden foundation, in the MC platform,
 |      |      |     +-- unique     about 140 hours of work, second one ever
 |      |      +-- how much work
 |      +-- where in TOBI
 +-- what kind of work
```

**TYPE** — what kind of work it is:

| Code | Means |
|---|---|
| `NEW` | Adds a feature to an area that already exists |
| `FOUND` | Creates a **new area**, and you can see and try it |
| `FOUND_BASE` | Creates a new foundation you **cannot** see — everything else stands on it |
| `UPG` | Rebuilds or extends an existing area |
| `FIX` | Repairs something broken |
| `CHECK` | Proves a feature actually works |

**AREA** — where in TOBI, six letters or fewer. Today: `BRAIN` `CHAT` `NEWS` `DEV` `PROJ` `OFFICE` `LINK` `SKILL` `THEME` `CORE` `CLI`. New ones arrive through `FOUND`.

**TIME** — real working hours. `1D` = 24H, `1M` = 30D, at most two units, minimum `0H` (under an hour). Taken from the upper end of this table's own estimate, counting one focus day as four working hours — so the code never promises something smaller than it turns out to be.

**NNN** — three digits, counted separately for each TYPE, oldest first. `UPG-…-001` was the first upgrade ever; `CHECK-…-006` is the sixth check. The code is unique on its own.

## Solo-Founder Time

`Solo time` is `full scope -> work left`. `done` means no planned implementation remains; `same` means the full estimate remains.

One focus day means 3-5 focused owner hours using Claude Code and/or Codex: preparing the prompt or plan, running the agent, reviewing its diff, testing locally, fixing ordinary mistakes, and recording the handoff. Calendar estimates assume 3-4 productive focus days per week and include a 25-35% allowance for AI rework and integration debugging. They exclude external approvals, provider outages, and major scope changes.

Token totals are no longer the primary measure because subscription tools, hidden context, retries, and model choice make Claude Code/Codex token counts difficult to compare reliably.

### Calibration Versus The Previous Model

| Previous band | Previous generic estimate | New solo-founder calibration |
|---|---|---|
| `XS` | <=0.5 day; <25k tokens | 1-3 focused hours; same day |
| `S` | 0.5-1 day; 25k-75k tokens | 2-5 focused hours; 1-2 calendar days |
| `M` | 1-3 days; 75k-200k tokens | 1-2 focus days; 1-4 calendar days |
| `L` | 3-7 days; 200k-500k tokens | 3-5 focus days; 1-2 calendar weeks |
| `XL` | 1-3 weeks; 500k-1M tokens | 5-8 focus days; 2-3 calendar weeks |
| `XXL` | 3-6 weeks; 1M-2M tokens | 10-18 focus days; 3-6 calendar weeks |
| `EPIC` | 6+ weeks; 2M+ tokens | 20-35 focus days; 2-4 calendar months |

> Gate update (2026-07-14): #17 reached 9/9 owner-runtime acceptance through a verified GitHub read, Evolution advanced to Agent, and #18's start prerequisite is now satisfied. Connector health remains evidence-gated and subject to the 24-hour freshness rule.

### Review Closure — Items #14 and #16 (2026-07-12)

The detailed historical delivery notes above are preserved. Their previously listed review gaps
are now closed: #14 uses structural JSON envelopes for untrusted transcript data; #16 has aligned
server-side review modes, DNS-pinned SSRF protection including Drive metadata, persisted exact-step
recovery, approval-to-run propagation, reloadable/openable artifacts, and structural research-source
isolation. See each linked plan's **Final Review Closure** for the authoritative current status.

<!-- Add new rows above as features are discussed. Status legend: 🟡 Queued · 🔵 In progress · ✅ Done · ⏸️ On hold -->

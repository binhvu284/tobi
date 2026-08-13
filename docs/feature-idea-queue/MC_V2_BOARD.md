# #21 Mission Control V2 — Owner Board

**This page is for the owner.** One screen, plain words, no jargon. It answers three questions:
where are we, what is the next package, and what does that package actually mean.

The agent-facing document is [`MISSION_CONTROL_INFRASTRUCTURE_V2_PLAN.md`](MISSION_CONTROL_INFRASTRUCTURE_V2_PLAN.md)
— 1,100 lines of specification. You never need to read it. This board is its summary.

`QUEUE.md` is unchanged: #21 stays one row, exactly like #23 stays one row while shipping N01–N12.
Its status column carries the same short progress note this board tracks.

---

## Status

**In progress.** T00 through T07 and T08 Runs 1, 2A, 2B, and 3A are owner-accepted. T08 Run 3B1 is
delivered and awaits owner acceptance.

**Delivered:** 8 complete packages plus T08 Runs 1, 2A, 2B, 3A, and 3B1, about **91-96%** of total effort.

**Next:** accept T08 Run 3B1, then plan Run 3B2. One parsed call now executes behind a typed service;
Conductor still owns model iteration, batching, combined approvals, and the step budget.

---

## The one thing #21 is for

> Today, a request behaves differently depending on where it came from — Chat, Telegram, a page
> button, the CLI, a scheduler. Each path has its own memory of what happened, and a crash loses
> it. After #21, every request becomes the same kind of *run*: one record, one history, one set
> of rules, and it survives a restart.

When you are deep in fixing something and cannot remember why this item exists, read that
paragraph. If what you are fixing does not serve it, it belongs in a new queue item.

## What #21 is deliberately not

Straight from the plan, and the reason it stays finishable:

- not multi-tenant hosting, not a SaaS
- not replacing SQLite
- not adopting Temporal / Trigger.dev / Inngest — build the small local version first
- not unrestricted autonomous computer control, not agent swarms
- not deleting legacy Chat, Conductor, `agent_runs`, or `tobi_actions` in this release
- **not rebuilding the frontend design system** — this is why #21 is a backend item
- not changing Supabase or Vercel

---

## The 17 packages

Ordered. Each one ships and is reviewable on its own. Risk is the plan's own rating, not mine.

| # | Plain-English goal | Needs | Risk | Done |
|---|---|---|---|---|
| T00 | **Check the ground first.** #22 qualification and current ownership are reconciled. Every shared table and API has one declared owner. → [evidence](MC_V2_OWNERSHIP_MATRIX.md) | #22 | Med | Done |
| T01 | **Agree the shapes.** Shared validated contracts now define runs, tools, loops, errors, evaluations, and system relationships. Seven independent rollout flags default off, so live behavior is unchanged. | T00 | Med | Done |
| T02 | **Write everything down, in order.** Immutable ordered run/System history, secret redaction before storage, and deterministic current-state rebuilds are delivered locally. No live caller is switched. | T01 | High | Done |
| T03 | **Make runs survive a crash.** Canonical storage, versioned states, exclusive leases, restart checkpoints, bounded retries, recovery commands, cancellation fencing, persisted loop progress, hard limits, action reservations, immutable receipts, and fail-closed crash reconciliation are delivered. | T02 | High | Done |
| T04 | **Point Chat and Agent at the new engine**, quietly at first (both run side by side and get compared before anything switches over). | T03 | High | Done |
| T05 | **One place decides what is allowed.** Permissions, approvals, credentials, budgets — currently spread across many files. | T01 | High | Done |
| T06 | **One list of tools.** Every tool described once, in one format, with its arguments checked before it runs. | T01, T05 | High | Done |
| T07 | **Move the first real tools over:** files, terminal, projects. Each mutation gets a receipt, and a retry cannot double-apply it. | T03, T06 | High | Done |
| T08 | **Shrink the Conductor.** It currently does routing, planning, permissions, execution, and replies all in one file. Pull those out one at a time until it is a thin wrapper. | T04, T07 | High | Runs 1, 2A, 2B, and 3A accepted; Run 3B1 delivered, acceptance pending |
| T09 | **Let Brain memory actually change answers.** Relevant memory influences what TOBI does; stale or private memory does not leak into it. | T00, T08 | High | ☐ |
| T10 | **Make Hermes and the coding agent workers, not bosses.** They execute bounded requests; they cannot change the authoritative record. | T00, T03, T06 | High | ☐ |
| T11 | **See everything.** One trace per request joining context, model, tools, approvals, cost, and outcome — plus the quality gates that block a release on regression. | T09, T10 | Med | ☐ |
| T11A | **Map the system to itself.** Typed records for subsystems, capabilities, risks, and limitations. Foundation only — not the Atlas page. | T02, T11 | Med | ☐ |
| T12 | **Attack it on purpose.** Threat model, then deliberately inject failures: injection, secrets, over-reach, budgets, paths. | T05, T11 | High | ☐ |
| T13 | **The Runs page.** One live view of every run, shared across pages, reconnecting where it left off. Foundation only — no redesign. | T04, T11, T11A | Med | ☐ |
| T14 | **Turn it on slowly.** Compare old and new side by side, activate one surface at a time, and prove the rollback switch works. | T12, T13 | High | ☐ |
| T15 | **Everything else:** Projects, Office, CLI, Telegram, schedulers, and docs. Legacy deletion is a separate decision you make later. | T14 | High | ☐ |

Phases group these into checkpoints you can stop at: **T00** (ground truth) · **T01** (shapes) ·
**T02–T04** (durable runs) · **T05–T07** (policy and tools) · **T08–T09** (Conductor and memory) ·
**T10–T12** (observability and security) · **T13–T14** (UI and rollout) · **T15** (the rest).

Stopping after any phase leaves a working system. That is the point of the ordering.

### T08 run split

| Run | What moves out of `conductor.py` | T08 after acceptance |
|---|---|---|
| 1 | Model output classification, safe streaming/reset, continuation, reasoning cleanup, and text chunking | 15-20% |
| 2A | Compatibility intent/tool-loop decision plus episodic-recall detection | 25-30% |
| 2B | Context assembly using the existing manifest, Brain, history, attachments, and prompt owners | 35-45% |
| 3A | Persisted retry, skip, revise, and resume checkpoint handling | 45-55% |
| 3B1 | One parsed tool call validated and dispatched through compatibility execution boundaries | 58-68% |
| 3B2 | Tool-loop iteration, batching, proposals, and step-budget orchestration | 70-82% |
| 4 | Final response composition and a thin compatibility-only `answer()` facade; golden-case closeout | 100% |

**Owner action now:** accept **T08 Run 3B1** and release Run 3B2 planning. Review one condition: the
diff extracts one-call validation and dispatch only, while Conductor still owns model iteration,
batching, combined approvals, and step-budget exhaustion exactly as before.

---

## How each package runs

Six steps. Your attention is needed in three of them, about 25 minutes total per package.

| | Step | Who | Time |
|---|---|---|---|
| 1 | **Frame it.** Fill in Purpose, Not doing, and Files expected in [`.claude/CURRENT_WORK.md`](../../.claude/CURRENT_WORK.md). | you + agent | 10 min |
| 2 | **Plan it.** Agent goes into plan mode — it physically cannot write files — and shows what it will change and how it will prove it. **You approve here.** This is the cheapest place to say no. | agent, you approve | 15 min |
| 3 | **Write the failing check first.** Set `Gate: red`. The check must fail against today's code. If it passes, it is not testing anything and gets rewritten. | agent | 20 min |
| 4 | **Build.** Set `Gate: green`. The agent cannot end its turn while the check is red. | agent, unattended | — |
| 5 | **Gate.** `scripts/gate.py` runs automatically. The agent does not get to grade itself. | automatic | — |
| 6 | **Accept.** Re-read the Purpose line. Did it do *that*? More files touched than listed in step 1 means the work drifted — say so before merging. | you | 5 min |

Step 3 is the one that is always skipped and the one that matters most. A check written after
the code just agrees with the code.

### When a package finishes

1. Tick its box above.
2. Add one dated row to §26 of the plan (the agent does this).
3. Update the #21 status column in `QUEUE.md` — e.g. `🟠 In progress (T00-T02 delivered)`.
   One row, same format as every other item.
4. Reset `.claude/CURRENT_WORK.md` to the next package and set `Gate: no` until step 3 of the
   next cycle.

---

## Where each document lives

| Document | Who reads it | What it is |
|---|---|---|
| `QUEUE.md` | **you** | One row per item. The ledger. Never gets split. |
| `MC_V2_BOARD.md` (this page) | **you** | #21 in plain words. Where we are, what is next. |
| `MC_V2_OWNERSHIP_MATRIX.md` | **you** + agent | T00's finding: who owns which table and API today, and who should. |
| `MISSION_CONTROL_INFRASTRUCTURE_V2_PLAN.md` | agent | The full specification. 1,100 lines. |
| `.claude/CURRENT_WORK.md` | agent | The one package being built right now. |
| `CLAUDE.md` / `AGENTS.md` | agent | Permanent working rules. Not item-specific. |

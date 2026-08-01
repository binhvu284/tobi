# #21 T00 — Ownership Matrix

**Status:** complete 2026-08-01. The ownership map was finished 2026-07-30; #22's Codex-only
qualification is merged at `e9bc5fe`, closing the remaining start gate.

T00 asks one question: *when two parts of TOBI write to the same place, which one is in charge?*
Until that has an answer, every later package is guessing. This page is the answer for the
database and the API. It changes no code.

---

## The short version

| | |
|---|---|
| Tables in the database | **146** |
| Tables only one part of the code writes to — already fine | **117** |
| Tables more than one part writes to | **29** |
| API routes | **365** |
| API routes that clash | **0** |

**The API is clean.** 365 routes across 15 modules, and not one path is registered twice. Nothing
to fix there. That was the cheaper of the two risks and it came back green.

**The 29 shared tables are not 29 problems.** They fall into four groups, and only the first is
real work:

| Group | Tables | What it means |
|---|---|---|
| **Nobody is in charge** | **11** | No single module owns the table. Every caller writes to it directly. **This is T00's actual finding.** |
| Someone is in charge, but callers go around them | 7 | `core/news/repository.py` exists and is the right owner; six sibling files write to News tables without using it. Mechanical fix. |
| Mid-migration on purpose | 8 | Brain V1→V2. Two writers is what a migration looks like. #20 owns this, not #21. |
| Leave alone for now | 3 | Developer/coding tables. Codex is working in these files right now. |

---

## The 11 tables with no owner

Ranked by how many different files write to them. "Writers" counts runtime code only —
one-time backfills inside `core/schema/` are excluded, because those run at setup and are not
a second authority.

| Table | Writers | Who writes to it today | Who should own it |
|---|---|---|---|
| `tasks` | **7** | `api/routers/tasks.py`, `conductor_tools/action_tools.py`, `api/routers/pm.py`, `news/telemetry.py`, `pm_reminders.py`, `telegram/commands.py`, `telegram/pm_helpers.py` | **New.** Nothing owns it. It is declared in `core/database.py`, which is only the schema file. |
| `missions` | **5** | `office_stream.py`, `office.py`, `api/routers/missions.py`, `conductor_tools/action_tools.py`, `office_artifacts.py` | **New.** `office.py` and `office_stream.py` are peers; neither is the authority. |
| `pm_projects` | **4** | `api/routers/pm.py`, `conductor_tools/action_tools.py`, `telegram/pm_helpers.py`, `telegram/commands.py` | **New.** |
| `pm_activity` | **4** | `telegram/pm_helpers.py`, `api/routers/pm.py`, `conductor_tools/common.py`, `telegram/commands.py` | **New.** |
| `agent_state` | 3 | `office.py`, `office_stream.py`, `api/routers/agents.py` | **New**, same owner as `missions`. |
| `llm_usage` | 3 | `office.py`, `office_stream.py`, `usage.py` | **`core/usage.py`** — it already exists and is the obvious owner; Office writes around it. |
| `owner_settings` | 3 | `vault.py`, `api/routers/owner.py`, `owner_flags.py` | **`core/owner_flags.py`** — it declares the table. |
| `pm_goals` | 3 | `api/routers/pm.py`, `conductor_tools/action_tools.py`, `telegram/pm_helpers.py` | **New**, same owner as `pm_projects`. |
| `pm_resources` | 2 | `api/routers/pm.py`, `conductor_tools/action_tools.py` | **New**, same owner as `pm_projects`. |
| `mission_steps` | 2 | `office.py`, `office_stream.py` | **New**, same owner as `missions`. |
| `mcp_server_config` | 2 | `mcp_security.py`, `mcp_tunnel.py` | **`core/mcp_security.py`** — the security module should be the one writing security config. |

Collapsed into the modules that need to exist, it is **three new owners, not eleven**:

| Proposed owner | Covers | Notes |
|---|---|---|
| a **tasks store** | `tasks` | The single worst case. Seven writers including Telegram, News telemetry, and the Conductor's action tools. |
| a **PM store** | `pm_projects`, `pm_goals`, `pm_activity`, `pm_resources` | The same three callers write to all four tables. One owner covers the set. |
| an **Office store** | `missions`, `mission_steps`, `agent_state` | `office.py` and `office_stream.py` currently duplicate write paths for the same rows. |

Plus three tables where the owner already exists and just needs to be enforced:
`llm_usage` → `usage.py`, `owner_settings` → `owner_flags.py`, `mcp_server_config` → `mcp_security.py`.

### Why `tasks` is the one to watch

Seven files write to it, and they belong to five unrelated subsystems: the Tasks page, the PM page,
the Conductor's action tools, the Telegram bot, and News telemetry. Any change to what a task row
means has to be made correctly in seven places at once. That is the exact shape of the D10 defect
on the Developer page — a vocabulary copied into seven files, where one copy went stale and nothing
detected it.

---

## The 7 News tables — owner exists, callers bypass it

`core/news/repository.py` declares these tables and is already the right owner. Six sibling
modules write to them directly instead of going through it.

| Table | Bypassing writers |
|---|---|
| `news_items` | `interactions.py`, `normalizer.py`, `spotlight.py`, `llm.py`, `recap.py` |
| `news_interactions` | `interactions.py` |
| `news_interaction_events` | `interactions.py` |
| `news_item_sources` | `normalizer.py` |
| `news_media_cache` | `media.py` |
| `news_model_metrics` | `normalizer.py` |
| `news_model_releases` | `normalizer.py` |

Lower risk than the group above: the destination is agreed, only the route to it is inconsistent.
This is a cleanup that can happen any time, and it does not need to happen before #21 starts.

---

## The 8 Brain tables — not a finding

`brain_v2_compat.py` writes to both the V1 and V2 tables. That is what a compatibility layer is
for, and #20 shipped it deliberately. Recording it here only so a later reader does not mistake
it for drift and try to "fix" it.

Tables: `brain_memory_v2`, `brain_memories`, `brain_categories`, `brain_imports`,
`brain_memory_evidence`, `brain_memory_tags`, `brain_memory_versions`, `brain_narrative`.

**One decision #21 must not make on its own:** when Brain V1 is retired, these collapse to one
writer each. #21's T09 consumes Brain but must not schedule that retirement — that belongs to #20.

---

## The 3 deferred tables

`coding_stages`, `coding_artifacts`, `development_tasks`. In each, `core/coding_agent.py` writes
directly alongside `core/development_store.py`, which is the declared owner.

The post-#22 check still finds direct compatibility writes in `core/coding_agent.py` alongside
the declared owner, `core/development_store.py`. Ownership is therefore resolved, but access is
not yet centralized. T10 owns that adapter work because it migrates the accepted #22 workflow.

---

## Security check

`core/vault.py` writes to `owner_settings`, which looked worth confirming. Checked: it stores
which credential slot is currently active — a label like `"personal"`. No key material passes
through it. Not a finding.

---

## How this was produced, and what it cannot see

Static scan of every `.py` under `core/` and `api/`, matching `CREATE TABLE`, `INSERT`/`UPDATE`/
`DELETE`, and route decorators. Every count below was cross-checked against source before being
written down. Three things the raw scan got wrong, and what was done about them:

| Raw scan said | Truth | Fix |
|---|---|---|
| A table named `is` exists with 2 writers | A prose comment: *"no CREATE TABLE is scattered across features"* | Comments stripped before matching |
| `core/schema/tasks.py` is a 9× writer to `tasks` | One-time column backfills behind the migration entry point | `core/schema/**` counted as migration, not runtime |
| `GET /profile` is registered twice | Two different prefixes: `/api/brain/v2/profile` and `/api/explore/v2/profile` | Not a collision |

**Limits, stated plainly.** The scan reads SQL written as literal text. A table name built at
runtime, or a write issued through an ORM-style helper, would not be counted. So the 29 is a
floor, not a ceiling — there may be more sharing than this, but not less. Anything found later
gets added here rather than handled ad hoc.

---

## Scale check — the plan's SQLite non-goal, now measured

§1.2 lists *"replacing SQLite before measured contention requires it"* as a non-goal. Nobody had
measured it, and T02 (append-only event store) plus T03 (durable runtime, several surfaces writing
at once) are the two packages that would break the assumption if it were wrong. Measured on this
machine, on the D: drive:

**Data volume is not the risk.** The live database is 57 MB and **19,985 rows across 144 tables**.
The largest table, `development_events`, holds 5,557 rows. 36 tables are empty.

**Concurrency is not the risk either.** Benchmarked against a table shaped like the planned event
store — append-only, ~450-byte JSON payload, indexed on `(run_id, seq)`:

| Concurrent writers | Writes/sec | p99 write | Lock errors |
|---|---|---|---|
| 1 | 11,383 | 0.19 ms | 0 |
| 4 | 11,805 | 0.70 ms | 0 |
| 8 | 10,486 | 1.13 ms | 0 |

Zero lock contention at every level, and a reader running against four hammering writers saw
**p99 0.34 ms** — WAL doing exactly what it is for. At this rate SQLite writes TOBI's entire
current history in about two seconds. The non-goal holds by roughly three orders of magnitude.

### One measured defect: a missing pragma costs 10x write throughput

`core/database.py` sets `journal_mode=WAL`, `busy_timeout=8000`, and `foreign_keys=ON`, but never
sets `synchronous`. SQLite therefore runs at the default `FULL`, which fsyncs on every commit:

| `synchronous` | Writes/sec (1 writer) | p50 |
|---|---|---|
| `FULL` — **what TOBI runs today** | **1,095** | 0.90 ms |
| `NORMAL` | **11,383** | 0.05 ms |

**The honest trade-off.** In WAL mode `NORMAL` cannot corrupt the database; the documented risk is
losing the most recently committed transactions if the machine loses power or the OS crashes. For
a local single-owner assistant that is usually the right trade, and it is what most WAL deployments
run. But #21's entire purpose is durable runs, so this is the owner's call, not a silent tuning
change. It is recorded here rather than applied.

Not urgent at 20k rows. It becomes relevant the moment T02 starts appending an event per tool call.

### What the real bottleneck is

The Developer page took 9.7 seconds to render against these same 20k rows before it was fixed. The
cause was never data volume — it was 500 queries across 50 fresh connections in one request. An
AST scan finds **124 loops in `core/` and `api/` that contain a database call**, concentrated in
`development_store.py` (9), `graph_engine.py` (9), `explore.py` (7), and `api/routers/pm.py` (6).
Most are harmless loops over short lists. The point is the shape: **TOBI's scaling risk is access
patterns, not storage.**

So the guard #21 needs is not a database migration. It is a check that a request's query count
stays bounded — the same kind of budget test that now protects `/api/developer/overview`.

## What this changes for T01

T01 defines the typed shapes. Three of them are now pinned by evidence rather than by preference:

1. **A tasks owner must exist before anything else writes to `tasks`.** Seven writers is the
   largest single ownership gap in the codebase.
2. **PM and Office each need one store**, because in both cases an API router, the Conductor's
   action tools, and a third surface all write the same rows independently.
3. **`usage.py`, `owner_flags.py`, and `mcp_security.py` should be enforced as owners**, not
   created. The modules are already there; callers just go around them.

## T00 closure

`QUEUE.md` records #22 as Codex-only V2 qualified on 2026-08-01. Its same-run recovery, queue
safety, validation, review, delivery synchronization, active-time tracking, and History evidence
are accepted. The ownership findings above are assigned to later #21 packages, so no unresolved
table or API owner blocks T01.

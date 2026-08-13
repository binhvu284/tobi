# Current work

One package at a time. This file is the only thing that changes between packages — `CLAUDE.md`
points here and never needs editing again.

Read this before writing code. Re-read the Purpose line whenever you have been fixing something
for more than an hour: if what you are fixing does not serve that line, stop and log it instead.

---

**Item:** #21 Mission Control Infrastructure V2
**Package:** T09 Run 2 - Bounded route/tool influence and turn-linked evidence

**Purpose (one sentence, plain words):**
Let eligible delivered #20 memory influence fallback routing, safe read-tool candidates, planning,
and response style while the current request, policy, approval, availability, and safety stay stronger.

**Not doing:**
- No new Brain schema, memory lifecycle, ranking, feedback verdict, or Graph authority.
- No sensitive, stale, contradicted, pending, rejected, archived, or superseded memory influence.
- No memory-granted permission, credential, tool execution, policy weakening, or instruction authority.
- No memory-triggered mutation, terminal, network, connector, browser, coding, or external read.
- No override of an explicit request, deterministic action/read route, clarification, or selected mode.
- No change to accepted T08 Conductor signatures, execution, model selection, or public result fields.
- No activation of dormant canonical executors, Runtime tools, or rollout flags.
- No T10 Hermes/coding adapter, T11 observability/evals, T13 Runs page, or T14 activation work.
- No Telegram, CLI, Office, scheduler, or remaining-surface migration; T15 owns those adapters.
- No Supabase, Vercel, external integration, or production-runtime interaction.

**Files expected:**
- `.claude/CURRENT_WORK.md`
- `docs/feature-idea-queue/MC_V2_BOARD.md`
- `docs/feature-idea-queue/MISSION_CONTROL_INFRASTRUCTURE_V2_PLAN.md`
- `docs/feature-idea-queue/QUEUE.md`
- `docs/feature-idea-queue/QUEUE_DELIVERY_LOG.md`
- `core/runtime/owner_intelligence.py`
- `core/context_manager.py`
- `core/chat_runtime.py`
- `api/routers/chat.py`
- `tests/test_mc_runtime_owner_intelligence_routing.py`
- `tests/test_chat_runtime.py` (route contract only)
- `tests/test_chat_runtime_route.py` (turn-linked context evidence only)

**Gate: no**

```gate
```

---

## How the Gate line works

`scripts/gate.py` reads the line above and the fenced `gate` block, and runs on every stop.

| Value | Meaning | When to use it |
|---|---|---|
| `Gate: no` | Nothing is enforced. | Between packages, or during planning and discussion. |
| `Gate: red` | The checks **must fail**. Stopping is refused if they all pass. | Right after writing a new test, before implementing. |
| `Gate: green` | The checks **must pass**. Stopping is refused if any fail. | While implementing, until it is done. |

`red` is the step that matters. A test written after the code just agrees with the code. Running
it against the unchanged codebase and watching it fail is the only proof it tests anything.

Commands go one per line inside the fence, exactly as you would type them:

```
python -m compileall -q core api
python tests/test_runtime_contracts.py
```

Run it yourself at any time: `python scripts/gate.py`

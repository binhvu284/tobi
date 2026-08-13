# Current work

One package at a time. This file is the only thing that changes between packages — `CLAUDE.md`
points here and never needs editing again.

Read this before writing code. Re-read the Purpose line whenever you have been fixing something
for more than an hour: if what you are fixing does not serve that line, stop and log it instead.

---

**Item:** #21 Mission Control Infrastructure V2
**Package:** T10 Run 1 - Versioned worker capability boundary

**Purpose (one sentence, plain words):**
Make Mission Control the authority for versioned Hermes/coding-worker capabilities and return a
structured recovery result when a requested worker is unavailable.

**Not doing:**
- No Hermes authority over canonical runs, policies, approvals, tools, events, receipts, or projections.
- No direct worker execution, external call, model call, terminal call, or queue mutation in Run 1.
- No change to accepted #22 Goal/Queue/checkpoint semantics; later T10 runs adapt them.
- No new coding queue, checkpoint, evidence, or job persistence schema.
- No live Developer, CLI, Chat, Conductor, scheduler, Telegram, or Office caller switch.
- No activation of dormant Runtime flags or change to accepted T09 owner intelligence.
- No T11 telemetry/evals, T11A System Model, T12 security, T13 UI, or T14 rollout work.
- No Supabase, Vercel, external integration, or production-runtime interaction.

**Files expected:**
- `.claude/CURRENT_WORK.md`
- `docs/feature-idea-queue/MC_V2_BOARD.md`
- `docs/feature-idea-queue/MISSION_CONTROL_INFRASTRUCTURE_V2_PLAN.md`
- `docs/feature-idea-queue/QUEUE.md`
- `docs/feature-idea-queue/QUEUE_DELIVERY_LOG.md`
- `core/hermes_sync.py`
- `core/hermes_skills.py`
- `core/runtime/worker_capabilities.py`
- `tests/test_mc_runtime_worker_capabilities.py`

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

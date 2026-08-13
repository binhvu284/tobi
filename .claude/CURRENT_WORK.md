# Current work

One package at a time. This file is the only thing that changes between packages — `CLAUDE.md`
points here and never needs editing again.

Read this before writing code. Re-read the Purpose line whenever you have been fixing something
for more than an hour: if what you are fixing does not serve that line, stop and log it instead.

---

**Item:** #21 Mission Control Infrastructure V2
**Package:** T10 Run 3 - Canonical coding-run history bridge

**Purpose (one sentence, plain words):**
Link each accepted #22 coding session to one Mission Control run and mirror its redacted lifecycle,
checkpoint, and evidence history without replacing the readable Developer record.

**Not doing:**
- No replacement, deletion, or mutation of accepted #22 Goal/Queue/session/checkpoint/evidence history.
- No worker, model, terminal, GitHub, release, deployment, approval, or policy behavior change.
- No reverse write from a worker into canonical Runtime state; only the MC adapter may append events.
- No new database schema; derive idempotent canonical identity from the coding session.
- No Developer UI, CLI, Telegram, Office, scheduler, Chat, or Conductor caller migration.
- No activation change to Chat/Agent Runtime flags or accepted T09/T10 Runs 1-2 contracts.
- No T11 telemetry/evals, T11A System Model, T12 security, T13 UI, or T14 rollout work.
- No Supabase, Vercel, external integration, or production-runtime interaction.

**Files expected:**
- `.claude/CURRENT_WORK.md`
- `docs/feature-idea-queue/MC_V2_BOARD.md`
- `docs/feature-idea-queue/MISSION_CONTROL_INFRASTRUCTURE_V2_PLAN.md`
- `docs/feature-idea-queue/QUEUE.md`
- `docs/feature-idea-queue/QUEUE_DELIVERY_LOG.md`
- `core/coding_agent.py`
- `core/runtime/coding_adapter.py`
- `core/runtime/repository.py`
- `tests/test_mc_runtime_coding_adapter.py`
- accepted #22 regression tests

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

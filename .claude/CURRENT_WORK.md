# Current work

One package at a time. This file is the only thing that changes between packages — `CLAUDE.md`
points here and never needs editing again.

Read this before writing code. Re-read the Purpose line whenever you have been fixing something
for more than an hour: if what you are fixing does not serve that line, stop and log it instead.

---

**Item:** #21 Mission Control Infrastructure V2
**Package:** T11 - Unified trace and TOBIval release/autonomy gates

**Purpose (one sentence, plain words):**
Join each canonical run's bounded evidence into one redacted trace and make local evaluation
regressions block release activation or autonomy increases.

**Not doing:**
- No raw prompts, context bodies, tool output, credentials, diffs, or provider errors in telemetry.
- No model, tool, worker, approval, policy, Brain, connector, or coding execution behavior change.
- No activation flag change and no live release or autonomy increase.
- No remote telemetry vendor; storage and evaluation remain local-first.
- No T11A System Model, T12 security, T13 UI, T14 rollout, or T15 adapter work.
- No Supabase, Vercel, external integration, or production-runtime interaction.

**Files expected:**
- `.claude/CURRENT_WORK.md`
- `docs/feature-idea-queue/MC_V2_BOARD.md`
- `docs/feature-idea-queue/MISSION_CONTROL_INFRASTRUCTURE_V2_PLAN.md`
- `docs/feature-idea-queue/QUEUE.md`
- `docs/feature-idea-queue/QUEUE_DELIVERY_LOG.md`
- `core/runtime/trace.py`
- `core/runtime/evals.py`
- `core/runtime/repository.py`
- `tests/test_mc_runtime_evals.py`
- accepted Runtime and Developer regression tests

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

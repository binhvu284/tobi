# Current work

One package at a time. This file is the only thing that changes between packages — `CLAUDE.md`
points here and never needs editing again.

Read this before writing code. Re-read the Purpose line whenever you have been fixing something
for more than an hour: if what you are fixing does not serve that line, stop and log it instead.

---

**Item:** #21 Mission Control Infrastructure V2
**Package:** T13 - Runs Center and shared frontend projection foundation

**Purpose (one sentence, plain words):**
Give the owner one compact Runs Center with shared reconnectable run, trace, evaluation, context,
capability, loop, and recovery state while preserving the existing dashboard design.

**Not doing:**
- No broad dashboard redesign and no full Atlas page.
- No activation, execution, policy, approval, tool, model, worker, or legacy behavior change.
- No unbounded payload, prompt, context body, tool output, secret, or raw error in API/UI state.
- No T14 rollout or T15 adapter work.
- No Supabase, Vercel, external integration, or production-runtime interaction.

**Files expected:**
- `.claude/CURRENT_WORK.md`
- `docs/feature-idea-queue/MC_V2_BOARD.md`
- `docs/feature-idea-queue/MISSION_CONTROL_INFRASTRUCTURE_V2_PLAN.md`
- `docs/feature-idea-queue/QUEUE.md`
- `docs/feature-idea-queue/QUEUE_DELIVERY_LOG.md`
- `api/routers/runtime.py`
- `dashboard/src/api/runtime.ts`
- `dashboard/src/stores/runtime.ts`
- `dashboard/src/pages/Runs.tsx`
- narrow Developer integration files
- backend, frontend, and Playwright tests

**Gate: green**

```gate
python tests/test_mc_runtime_runs_view.py
python tests/test_mc_runtime_runs_ui.py
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

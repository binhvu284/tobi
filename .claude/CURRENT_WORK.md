# Current work

One package at a time. This file is the only thing that changes between packages — `CLAUDE.md`
points here and never needs editing again.

Read this before writing code. Re-read the Purpose line whenever you have been fixing something
for more than an hour: if what you are fixing does not serve that line, stop and log it instead.

---

**Item:** #21 Mission Control Infrastructure V2
**Package:** T07 Run 3B2B - approved cooperative managed-job cancellation (delivered; awaiting owner acceptance)

**Purpose (one sentence, plain words):**
Add one approved, idempotent cancellation request that the matching authenticated managed wait
worker observes and completes itself, while restart reads remain truthful and no app process targets an OS PID.

**Not doing:**
- No live tool routing, policy cutover, caller integration, owner-flag change, API, or UI.
- No change to accepted start/list/output or foreground terminal behavior.
- No arbitrary command, caller directory, environment input, or broader background operation.
- No parent-side terminate, signal, PID lookup/storage, process-tree control, replacement worker, or
  call to legacy `kill_job`; only the authenticated worker may finalize cancellation.
- No claim that a job stopped when only a request exists: stale or missing worker proof stays unknown.
- No rebuild of `mc_terminal_jobs`, new cancellation table, or write to legacy `terminal_jobs`.
- No cancellation of another owner's job; the canonical job's originating owner must match the
  approved cancel action owner.
- No automatic retry after an uncertain cancellation write; reconcile durable evidence first.
- No `install_package`, `configure_tool`, `connect_tool`, `set_terminal_mode`, or capability-registry migration.
- No weakening or redesign of the existing terminal engine, legacy jobs, or callers.
- No T07 closure or T08 release in the implementation commit; both require explicit owner acceptance
  after delivery.
- No Conductor decomposition; T08 owns it.
- No Runs page or broad frontend redesign; T13 owns it.
- No Telegram, CLI, Office, scheduler, or remaining-surface adapters.
- No Supabase, Vercel, external integration, or production-runtime interaction.

**Files expected:**
- `core/schema/runtime.py`
- `core/runtime/terminal_jobs.py`
- `core/runtime/terminal_job_worker.py`
- `core/runtime/terminal_tools.py`
- `tests/test_mc_runtime_terminal_jobs.py`
- `.claude/CURRENT_WORK.md`
- `docs/feature-idea-queue/MC_V2_BOARD.md`
- `docs/feature-idea-queue/MISSION_CONTROL_INFRASTRUCTURE_V2_PLAN.md`
- `docs/feature-idea-queue/QUEUE.md`

**Gate: green**

```gate
"D:/[PERSONAL PROJECT FILES]/TOBI/.python/venv/Scripts/python.exe" tests/test_mc_runtime_terminal_jobs.py
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

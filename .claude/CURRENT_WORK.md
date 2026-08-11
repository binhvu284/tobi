# Current work

One package at a time. This file is the only thing that changes between packages — `CLAUDE.md`
points here and never needs editing again.

Read this before writing code. Re-read the Purpose line whenever you have been fixing something
for more than an hour: if what you are fixing does not serve that line, stop and log it instead.

---

**Item:** #21 Mission Control Infrastructure V2
**Package:** T07 Run 3B2A - dormant managed background start/read/restart foundation (delivered; awaiting owner acceptance)

**Purpose (one sentence, plain words):**
Add one durable, bounded background wait job whose typed duration, identity, status, redacted output,
and restart truth survive the app process, without changing any live route or adding cancellation yet.

**Not doing:**
- No live tool routing, policy cutover, caller integration, or flag change.
- No change to accepted `terminal_status@1`, `run_command@1`, or `run_command@2` behavior.
- No arbitrary shell command: the only new start input is a typed 1-300 second duration translated
  to an internal managed wait worker, with no caller command string or working directory.
- No cancellation, terminate, kill, or OS-PID targeting; Run 3B2B owns approved cancellation.
- No replacement launch when a started job has stale or missing worker evidence; report it as unknown.
- No reuse, migration, or write to legacy `terminal_jobs`; the additive `mc_terminal_jobs` record is
  canonical and stores no raw command, directory, secret, or worker token.
- No `install_package`, `configure_tool`, `connect_tool`, `set_terminal_mode`, or capability-registry migration.
- No weakening or redesign of the existing terminal engine, legacy background jobs, or callers.
- No owner flag, API, UI, visible behavior, live streaming, or external queue/service.
- No T07 closure or T08 release; both wait for Run 3B2B delivery and owner acceptance.
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
- `tests/test_mc_runtime_approvals.py`
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

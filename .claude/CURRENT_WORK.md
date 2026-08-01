# Current work

One package at a time. This file is the only thing that changes between packages — `CLAUDE.md`
points here and never needs editing again.

Read this before writing code. Re-read the Purpose line whenever you have been fixing something
for more than an hour: if what you are fixing does not serve that line, stop and log it instead.

---

**Item:** #21 Mission Control Infrastructure V2
**Package:** T02 - ordered event store and rebuildable projections (not started)

**Purpose (one sentence, plain words):**
Every accepted runtime event can be written once in order and used to rebuild the same current
run and system state after a restart.

**Not doing:**
- No workflow execution engine, leases, retries, or checkpoint controller; T03 owns them.
- No live Chat, Agent, Telegram, CLI, scheduler, Office, or Projects adapter switch.
- No Conductor rewrite or Runs page.
- No Supabase, Vercel, external integration, or production-runtime interaction.

**Files expected:**
- Set after T02 planning and before its first code edit.

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

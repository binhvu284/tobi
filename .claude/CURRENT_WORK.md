# Current work

One package at a time. This file is the only thing that changes between packages — `CLAUDE.md`
points here and never needs editing again.

Read this before writing code. Re-read the Purpose line whenever you have been fixing something
for more than an hour: if what you are fixing does not serve that line, stop and log it instead.

---

**Item:** #21 Mission Control Infrastructure V2
**Package:** T14 - Shadow comparison, staged activation, and rollback proof

**Purpose (one sentence, plain words):**
Compare legacy and Runtime V2 safely, require seven consecutive local passes before each staged
activation, and prove one master rollback returns new work to legacy behavior without data loss.

**Not doing:**
- No Projects, Office, CLI, Telegram, scheduler, or other T15 adapter cutover.
- No raw prompt, response, tool output, secret, or error body in comparison evidence.
- No automatic stage advancement and no activation that bypasses the existing evaluation gate.
- No legacy deletion or external service interaction.
- No Supabase, Vercel, external integration, or production-runtime interaction.

**Files expected:**
- `.claude/CURRENT_WORK.md`
- `core/owner_flags.py`
- `core/runtime/config.py`
- `core/runtime/rollout.py`
- `core/schema/runtime.py`
- `api/routers/runtime.py`
- queue status and delivery evidence documents
- focused rollout and regression tests

**Gate: green**

```gate
../.python/venv/Scripts/python.exe tests/test_mc_runtime_rollout.py
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

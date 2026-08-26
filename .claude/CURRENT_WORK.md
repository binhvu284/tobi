# Current work

One package at a time. This file is the only thing that changes between packages — `CLAUDE.md`
points here and never needs editing again.

Read this before writing code. Re-read the Purpose line whenever you have been fixing something
for more than an hour: if what you are fixing does not serve that line, stop and log it instead.

---

**Item:** #34 TOBIval Operational Intelligence and Model Independence
**Package:** T05 - Live Eval Attachment And Enforced Regression Gates

**Purpose (one sentence, plain words):**
Attach bounded Eval suites to canonical Runtime evidence and block only affected release or autonomy
scope when required proof is missing, stale, failed, or unsafe.

**Not doing:**
- No T06 Eval API or dashboard.
- No production Chat routing switch or full-suite work inside an owner turn.
- No holdout execution or tuning against the 14 holdout cases.
- No model calls.
- No owner-facing API or dashboard work; those belong to T06.
- No Runtime V2 activation, connector writes, deployment, Supabase, or Vercel interaction.

**Files expected:**
- `.claude/CURRENT_WORK.md`
- `core/schema/runtime.py`
- `core/runtime/contracts.py`
- `core/runtime/evals.py`
- `core/runtime/eval_live.py`
- `core/runtime/rollout.py`
- `tests/test_tobival_runtime_gates.py`
- inherited Eval runner, rollout, security, and schema-ledger tests
- queue, delivery-log, and development docs

**Gate: green**

```gate
../.python/venv/Scripts/python.exe tests/test_tobival_runtime_gates.py
../.python/venv/Scripts/python.exe tests/test_tobival_runner.py
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

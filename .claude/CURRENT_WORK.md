# Current work

One package at a time. This file is the only thing that changes between packages — `CLAUDE.md`
points here and never needs editing again.

Read this before writing code. Re-read the Purpose line whenever you have been fixing something
for more than an hour: if what you are fixing does not serve that line, stop and log it instead.

---

**Item:** #34 TOBIval Operational Intelligence and Model Independence
**Package:** T01 - Real runner, scorers, and immutable results

**Purpose (one sentence, plain words):**
Execute frozen development cases, score observed behavior from bounded evidence, and persist
immutable results against canonical Runtime runs instead of accepting manually inserted passes.

**Not doing:**
- No T02 deterministic workflow routing or production Chat behavior changes.
- No holdout execution or tuning against the 14 holdout cases.
- No model calls; T01 uses deterministic test executors only.
- No API or dashboard work; those belong to T05/T06.
- No Runtime V2 activation, connector writes, deployment, Supabase, or Vercel interaction.

**Files expected:**
- `.claude/CURRENT_WORK.md`
- `core/runtime/evals.py` existing persistence ownership
- `core/runtime/eval_dataset.py`
- `core/runtime/eval_scorers.py`
- `core/runtime/eval_runner.py`
- `core/runtime/eval_metrics.py`
- `core/runtime/trace.py` bounded evidence-reference projection
- `tests/test_tobival_scorers.py`
- `tests/test_tobival_runner.py`
- queue, delivery-log, and development docs

**Gate: green**

```gate
../.python/venv/Scripts/python.exe tests/test_tobival_scorers.py
../.python/venv/Scripts/python.exe tests/test_tobival_runner.py
../.python/venv/Scripts/python.exe tests/test_mc_runtime_evals.py
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

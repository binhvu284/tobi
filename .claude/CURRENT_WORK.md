# Current work

One package at a time. This file is the only thing that changes between packages — `CLAUDE.md`
points here and never needs editing again.

Read this before writing code. Re-read the Purpose line whenever you have been fixing something
for more than an hour: if what you are fixing does not serve that line, stop and log it instead.

---

**Item:** #34 TOBIval Operational Intelligence and Model Independence
**Package:** T00 - Metric contract, frozen dataset, and unchanged-code baseline

**Purpose (one sentence, plain words):**
Freeze the exam, formulas, supported scope, model lanes, and unchanged-code result before any
production behavior changes, so later improvement claims cannot move the target.

**Not doing:**
- No edits to `core/`, `api/`, or `dashboard/` production behavior.
- No holdout execution or tuning against the 14 holdout cases.
- No model benchmark outside the approved exact model IDs, 168-call limit, and `$0` direct-cost cap.
- No Runtime V2 activation, connector writes, deployment, Supabase, or Vercel interaction.
- No T01 implementation until the owner reviews and accepts the recorded baseline.

**Files expected:**
- `.claude/CURRENT_WORK.md`
- `tobival/` metric, dataset, and baseline tooling
- `scripts/tobival.py`
- `tests/evals/v1/` frozen manifest, fixtures, workflow scope, lock, and baseline evidence
- `tests/test_tobival_metric_contracts.py`
- `tests/test_tobival_baseline_harness.py`
- queue, delivery-log, and development docs

**Gate: green**

```gate
../.python/venv/Scripts/python.exe tests/test_tobival_metric_contracts.py
../.python/venv/Scripts/python.exe tests/test_tobival_baseline_harness.py
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

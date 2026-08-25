# Current work

One package at a time. This file is the only thing that changes between packages — `CLAUDE.md`
points here and never needs editing again.

Read this before writing code. Re-read the Purpose line whenever you have been fixing something
for more than an hour: if what you are fixing does not serve that line, stop and log it instead.

---

**Item:** #34 TOBIval Operational Intelligence and Model Independence
**Package:** T02 - Deterministic Supported-Workflow Catalog

**Purpose (one sentence, plain words):**
Route common Mission Control requests through versioned workflow definitions without model
judgment, while failing closed on ambiguity, missing fields, and tool-boundary violations.

**Not doing:**
- No T03 entity or typed argument resolution.
- No production Chat routing switch; the new adapter remains additive until later packages connect it.
- No holdout execution or tuning against the 14 holdout cases.
- No model calls.
- No API or dashboard work; those belong to T05/T06.
- No Runtime V2 activation, connector writes, deployment, Supabase, or Vercel interaction.

**Files expected:**
- `.claude/CURRENT_WORK.md`
- `core/runtime/workflows.py`
- `core/task_classifier.py`
- `core/chat_runtime.py`
- `core/runtime/trace.py`
- `core/runtime/eval_runner.py`
- `tests/test_tobival_workflows.py`
- inherited Chat Runtime and Runtime Eval tests
- queue, delivery-log, and development docs

**Gate: green**

```gate
../.python/venv/Scripts/python.exe tests/test_tobival_workflows.py
../.python/venv/Scripts/python.exe tests/test_chat_runtime.py
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

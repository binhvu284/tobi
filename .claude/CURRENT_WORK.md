# Current work

One package at a time. This file is the only thing that changes between packages — `CLAUDE.md`
points here and never needs editing again.

Read this before writing code. Re-read the Purpose line whenever you have been fixing something
for more than an hour: if what you are fixing does not serve that line, stop and log it instead.

---

**Item:** #34 TOBIval Operational Intelligence and Model Independence
**Package:** T03 - Typed Entity And Argument Resolution

**Purpose (one sentence, plain words):**
Resolve project, task, and resource identities plus tool arguments into exact validated requests,
while asking bounded questions instead of letting a model invent or silently choose identifiers.

**Not doing:**
- No T04 grounded outcome templates or provider recovery.
- No production Chat routing switch; typed resolution remains additive until later packages connect it.
- No holdout execution or tuning against the 14 holdout cases.
- No model calls.
- No API or dashboard work; those belong to T05/T06.
- No Runtime V2 activation, connector writes, deployment, Supabase, or Vercel interaction.

**Files expected:**
- `.claude/CURRENT_WORK.md`
- `core/runtime/typed_resolution.py`
- existing `core/runtime/workflows.py` and canonical tool catalog contracts
- `tests/test_tobival_typed_resolution.py`
- inherited canonical project-tool and tool-registry tests
- queue, delivery-log, and development docs

**Gate: green**

```gate
../.python/venv/Scripts/python.exe tests/test_tobival_typed_resolution.py
../.python/venv/Scripts/python.exe tests/test_mc_runtime_project_tools.py
../.python/venv/Scripts/python.exe tests/test_mc_runtime_tool_registry.py
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

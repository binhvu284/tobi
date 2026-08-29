# Current work

One package at a time. This file is the only thing that changes between packages — `CLAUDE.md`
points here and never needs editing again.

Read this before writing code. Re-read the Purpose line whenever you have been fixing something
for more than an hour: if what you are fixing does not serve that line, stop and log it instead.

---

**Item:** Quick task - Keep Awakening complete across MC restarts
**Package:** Automatic GitHub proof refresh at startup
**Status:** Done. Both MC startup paths auto-refresh stale GitHub proof; focused gate green on 2026-08-30. #35 remains unstarted.

**Purpose (one sentence, plain words):**
Keep the owner's completed Awakening tier complete after MC restarts by automatically refreshing stale
GitHub read proof from the already-saved credential, without requiring another manual Integrations test.

**Not doing:**
- No #35 implementation or Agent-tier behavior changes.
- No credential changes, secret exposure, or manual GitHub test.
- No weakening of the 24-hour connector-proof freshness rule.
- No Notion, Google, Supabase, Vercel, or deployment interaction.

**Files expected:**
- `.claude/CURRENT_WORK.md`
- `core/awakening.py`
- `main.py`
- `api/dashboard.py`
- `tests/test_awakening.py`
- Awakening owner and delivery documentation

**Gate: green**

```gate
../.python/venv/Scripts/python.exe tests/test_awakening.py
../.python/venv/Scripts/python.exe tests/test_awakening_route.py
../.python/venv/Scripts/python.exe tests/test_integration_test_reasons.py
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

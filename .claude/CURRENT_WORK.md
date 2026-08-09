# Current work

One package at a time. This file is the only thing that changes between packages — `CLAUDE.md`
points here and never needs editing again.

Read this before writing code. Re-read the Purpose line whenever you have been fixing something
for more than an hour: if what you are fixing does not serve that line, stop and log it instead.

---

**Item:** #21 Mission Control Infrastructure V2
**Package:** T07 - file, terminal, and project tool migration planning (not started)

**Purpose (one sentence, plain words):**
Plan the first reviewable migration of file, terminal, and project tools to canonical policy,
receipts, and retry protection without changing live execution before owner approval.

**Not doing:**
- No implementation before the owner approves the T07 plan.
- No live tool routing, policy cutover, caller integration, or flag change during planning.
- No attempt to migrate every tool domain in one run; planning must select a small first slice.
- No deletion or bypass of legacy tool registries.
- No unrestricted terminal or filesystem authority.
- No Conductor decomposition; T08 owns it.
- No Runs page or broad frontend redesign; T13 owns it.
- No Telegram, CLI, Office, scheduler, or remaining-surface adapters.
- No Supabase, Vercel, external integration, or production-runtime interaction.

**Files expected:**
- `.claude/CURRENT_WORK.md`
- T07 planning evidence only

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

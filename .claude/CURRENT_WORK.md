# Current work

One package at a time. This file is the only thing that changes between packages — `CLAUDE.md`
points here and never needs editing again.

Read this before writing code. Re-read the Purpose line whenever you have been fixing something
for more than an hour: if what you are fixing does not serve that line, stop and log it instead.

---

**Item:** #21 Mission Control Infrastructure V2
**Package:** T04 Run 3 - SSE replay and reconnect (not started)

**Purpose (one sentence, plain words):**
Chat and Agent can resume canonical event reading after a known cursor without duplicate events,
while the legacy stream remains authoritative.

**Not doing:**
- No implementation before the owner approves the T04 Run 3 plan.
- No owner-visible behavior change; the legacy path remains authoritative.
- No gateway-on execution or flag activation; T04 Run 4 owns it.
- No default-on or irreversible Chat/Agent cutover.
- No central policy or canonical tool-registry migration; T05 and T06 own them.
- No migration of real file, terminal, or project tools; T07 owns them.
- No Conductor decomposition; T08 owns it.
- No Runs page or broad frontend redesign; T13 owns it.
- No Telegram, CLI, Office, scheduler, or remaining-surface adapters.
- No Supabase, Vercel, external integration, or production-runtime interaction.

**Files expected:** To be set during T04 Run 3 planning.

**Gate: no**

```gate
# Set during T04 Run 3 planning.
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

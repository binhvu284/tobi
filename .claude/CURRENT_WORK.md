# Current work

One package at a time. This file is the only thing that changes between packages — `CLAUDE.md`
points here and never needs editing again.

Read this before writing code. Re-read the Purpose line whenever you have been fixing something
for more than an hour: if what you are fixing does not serve that line, stop and log it instead.

---

**Item:** #21 Mission Control Infrastructure V2
**Package:** T04 Run 2 - Chat/Agent shadow route wiring (not started)

**Purpose (one sentence, plain words):**
Chat and Agent send each request through the canonical gateway in shadow mode while the legacy
path still answers, so differences are measurable without changing owner-visible behavior.

**Not doing:**
- No owner-visible behavior change; the legacy path remains authoritative.
- No SSE replay/reconnect API; T04 Run 3 owns it.
- No gateway-on execution or flag activation; T04 Run 4 owns it.
- No default-on or irreversible Chat/Agent cutover.
- No central policy or canonical tool-registry migration; T05 and T06 own them.
- No migration of real file, terminal, or project tools; T07 owns them.
- No Conductor decomposition; T08 owns it.
- No Runs page or broad frontend redesign; T13 owns it.
- No Telegram, CLI, Office, scheduler, or remaining-surface adapters.
- No Supabase, Vercel, external integration, or production-runtime interaction.

**Files expected:** To be fixed during the approved T04 Run 2 plan.

**Gate: no**

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

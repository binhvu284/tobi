# Current work

One package at a time. This file is the only thing that changes between packages — `CLAUDE.md`
points here and never needs editing again.

Read this before writing code. Re-read the Purpose line whenever you have been fixing something
for more than an hour: if what you are fixing does not serve that line, stop and log it instead.

---

**Item:** #21 Mission Control Infrastructure V2
**Package:** T06 Run 3 - dormant parity, validated call preparation, and activation boundary (delivered; owner closure review pending)

**Purpose (one sentence, plain words):**
Prove canonical catalog parity, prepare only allowlisted and schema-valid calls, and define the
owner-reviewed activation boundary without changing any live catalog or execution path.

**Not doing:**
- No T06 closure or T07 start before the owner accepts the delivery evidence.
- No live tool discovery, routing, policy cutover, or caller integration.
- No tool invocation, tool output handling, or activation; this run only prepares validated calls
  and reports whether every later activation condition is satisfied.
- No second authoritative catalog alongside existing tool registries.
- No migration of real file, terminal, or project tools; T07 owns them.
- No raw credential access, Vault broker work, or tool execution.
- No Conductor decomposition; T08 owns it.
- No Runs page or broad frontend redesign; T13 owns it.
- No Telegram, CLI, Office, scheduler, or remaining-surface adapters.
- No Supabase, Vercel, external integration, or production-runtime interaction.

**Files expected:**
- `.claude/CURRENT_WORK.md`
- `core/runtime/contracts.py`
- `core/runtime/tool_catalog.py`
- `tests/test_mc_runtime_tool_catalog.py`
- `docs/feature-idea-queue/MC_V2_BOARD.md`
- `docs/feature-idea-queue/MISSION_CONTROL_INFRASTRUCTURE_V2_PLAN.md`
- `docs/feature-idea-queue/QUEUE.md`

**Gate: green**

```gate
venv/Scripts/python.exe tests/test_mc_runtime_tool_catalog.py
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

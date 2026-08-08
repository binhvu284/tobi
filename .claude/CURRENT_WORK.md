# Current work

One package at a time. This file is the only thing that changes between packages — `CLAUDE.md`
points here and never needs editing again.

Read this before writing code. Re-read the Purpose line whenever you have been fixing something
for more than an hour: if what you are fixing does not serve that line, stop and log it instead.

---

**Item:** #21 Mission Control Infrastructure V2
**Package:** T06 Run 2 - dormant legacy and MCP catalog adapters (plan ready; awaiting approval)

**Purpose (one sentence, plain words):**
Adapt existing Conductor/Chat, inbound MCP, and persisted outbound MCP metadata into isolated
canonical registry snapshots without changing any live catalog or execution path.

**Not doing:**
- No implementation before the owner approves this Run 2 plan.
- No live tool discovery, routing, policy cutover, or caller integration.
- No second authoritative catalog alongside existing tool registries.
- No global registry singleton or startup registration.
- No database migration; outbound MCP uses the already-persisted input schema and truthful fallbacks.
- No migration of real file, terminal, or project tools; T07 owns them.
- No raw credential access, Vault broker work, or tool execution.
- No Conductor decomposition; T08 owns it.
- No Runs page or broad frontend redesign; T13 owns it.
- No Telegram, CLI, Office, scheduler, or remaining-surface adapters.
- No Supabase, Vercel, external integration, or production-runtime interaction.

**Files expected:**
- `.claude/CURRENT_WORK.md`
- `core/runtime/contracts.py`
- `core/runtime/tool_adapters.py`
- `core/mcp_client.py`
- `tests/test_mc_runtime_tool_adapters.py`
- current board, queue, architecture, current-state, and implementation-log docs after delivery

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

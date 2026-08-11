# Current work

One package at a time. This file is the only thing that changes between packages — `CLAUDE.md`
points here and never needs editing again.

Read this before writing code. Re-read the Purpose line whenever you have been fixing something
for more than an hour: if what you are fixing does not serve that line, stop and log it instead.

---

**Item:** #21 Mission Control Infrastructure V2
**Package:** T08 Run 2B - Compatibility context assembly extraction (implemented; awaiting owner acceptance)

**Purpose (one sentence, plain words):**
Move Conductor's existing context-source, prompt, attachment, and history assembly behind one typed
Runtime service without changing what reaches the model or any public answer behavior.

**Not doing:**
- No Run 3 planning or implementation until the owner accepts Run 2B.
- No change to `core/context_manager.py`, `ContextManifest`, Brain retrieval/profile selection,
  project or attachment trust fences, context budgets, prompt text/tool docs, history storage, or
  any Chat/Office/Telegram caller.
- No change to the Run 2A classifier/tool decision, detailed Chat `RouteDecision`, route scopes,
  budgets, clarification behavior, or API caller.
- No reorder of context resolution, classification, attachment expansion, prompt construction,
  model selection, or fallback history loading.
- No change to the `conductor.answer()` signature, result fields, reply text, event order, model
  selection/fallback, policy, approvals, tool catalog/execution, persistence, or owner flags.
- No T09 Brain-context integration, T11 observability expansion, T13 Runs page, or T14 activation work.
- No Telegram, CLI, Office, scheduler, or remaining-surface migration; T15 owns those adapters.
- No Supabase, Vercel, external integration, or production-runtime interaction.

**Files expected:**
- `.claude/CURRENT_WORK.md`
- `docs/feature-idea-queue/MC_V2_BOARD.md`
- `docs/feature-idea-queue/MISSION_CONTROL_INFRASTRUCTURE_V2_PLAN.md`
- `docs/feature-idea-queue/QUEUE.md`
- `docs/feature-idea-queue/QUEUE_DELIVERY_LOG.md` (added after the accepted Queue split in `d40bc5c`)
- `core/runtime/context_assembler.py`
- `core/conductor.py`
- `tests/test_mc_runtime_context_assembler.py`

**Gate: green**

```gate
"D:/[PERSONAL PROJECT FILES]/TOBI/.python/venv/Scripts/python.exe" tests/test_mc_runtime_context_assembler.py
"D:/[PERSONAL PROJECT FILES]/TOBI/.python/venv/Scripts/python.exe" tests/test_mc_runtime_intent_router.py
"D:/[PERSONAL PROJECT FILES]/TOBI/.python/venv/Scripts/python.exe" tests/test_mc_runtime_response_composer.py
"D:/[PERSONAL PROJECT FILES]/TOBI/.python/venv/Scripts/python.exe" tests/test_conductor_context.py
"D:/[PERSONAL PROJECT FILES]/TOBI/.python/venv/Scripts/python.exe" tests/test_context_manager.py
"D:/[PERSONAL PROJECT FILES]/TOBI/.python/venv/Scripts/python.exe" tests/test_premium_readers_route.py
"D:/[PERSONAL PROJECT FILES]/TOBI/.python/venv/Scripts/python.exe" tests/test_chat_runtime.py
"D:/[PERSONAL PROJECT FILES]/TOBI/.python/venv/Scripts/python.exe" tests/test_chat_runtime_route.py
"D:/[PERSONAL PROJECT FILES]/TOBI/.python/venv/Scripts/python.exe" tests/test_mc_runtime_gateway_route.py
"D:/[PERSONAL PROJECT FILES]/TOBI/.python/venv/Scripts/python.exe" tests/test_mc_runtime_gateway_live_chat.py
"D:/[PERSONAL PROJECT FILES]/TOBI/.python/venv/Scripts/python.exe" tests/test_conductor_final_guard.py
"D:/[PERSONAL PROJECT FILES]/TOBI/.python/venv/Scripts/python.exe" tests/test_conductor_mixed_reply.py
"D:/[PERSONAL PROJECT FILES]/TOBI/.python/venv/Scripts/python.exe" tests/test_chat_modes.py
"D:/[PERSONAL PROJECT FILES]/TOBI/.python/venv/Scripts/python.exe" tests/test_resource_access.py
"D:/[PERSONAL PROJECT FILES]/TOBI/.python/venv/Scripts/python.exe" tests/test_mode_enforcement.py
"D:/[PERSONAL PROJECT FILES]/TOBI/.python/venv/Scripts/python.exe" -m compileall -q core api
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

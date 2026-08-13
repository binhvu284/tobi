# Current work

One package at a time. This file is the only thing that changes between packages — `CLAUDE.md`
points here and never needs editing again.

Read this before writing code. Re-read the Purpose line whenever you have been fixing something
for more than an hour: if what you are fixing does not serve that line, stop and log it instead.

---

**Item:** #21 Mission Control Infrastructure V2
**Package:** T08 Run 3A - Compatibility checkpoint recovery extraction (implemented; awaiting owner acceptance)

**Purpose (one sentence, plain words):**
Move Conductor's persisted retry, skip, revise, and resume checkpoint handling behind one typed
Runtime service without changing validation, safety, execution, receipts, or public answer behavior.

**Not doing:**
- No Run 3B1 planning or implementation until the owner accepts Run 3A.
- No ordinary tool-loop extraction; Run 3B1 owns one-call validation/execution and Run 3B2 owns
  loop iteration, batching, and step-budget orchestration.
- No activation of the dormant canonical executor or T07 tool runtimes. Their run, lease, policy,
  approval, and receipt requirements remain unchanged and default-off.
- No change to checkpoint command ownership or persistence in `core/agent_runs.py` or the Runtime
  repository/control modules.
- No change to retry identity, validation, denied/allowed tool checks, Terminal safety decisions,
  review-mode approval behavior, action logging, receipts, failure text, or model continuation.
- No change to pending-action confirmation, ordinary tool-call parsing/execution, plan events,
  picker behavior, step budgets, or batched proposals.
- No change to the `conductor.answer()` signature, result fields, reply text, event order, model
  selection/fallback, context, routing, policy, approvals, tool catalog/execution, persistence, or
  owner flags.
- No T09 Brain-context integration, T11 observability expansion, T13 Runs page, or T14 activation work.
- No Telegram, CLI, Office, scheduler, or remaining-surface migration; T15 owns those adapters.
- No Supabase, Vercel, external integration, or production-runtime interaction.

**Files expected:**
- `.claude/CURRENT_WORK.md`
- `docs/feature-idea-queue/MC_V2_BOARD.md`
- `docs/feature-idea-queue/MISSION_CONTROL_INFRASTRUCTURE_V2_PLAN.md`
- `docs/feature-idea-queue/QUEUE.md`
- `docs/feature-idea-queue/QUEUE_DELIVERY_LOG.md`
- `core/runtime/checkpoint_recovery.py`
- `core/conductor.py`
- `tests/test_mc_runtime_checkpoint_recovery.py`

**Gate: green**

```gate
"D:/[PERSONAL PROJECT FILES]/TOBI/.python/venv/Scripts/python.exe" tests/test_mc_runtime_checkpoint_recovery.py
"D:/[PERSONAL PROJECT FILES]/TOBI/.python/venv/Scripts/python.exe" tests/test_mode_enforcement.py
"D:/[PERSONAL PROJECT FILES]/TOBI/.python/venv/Scripts/python.exe" tests/test_chat_modes.py
"D:/[PERSONAL PROJECT FILES]/TOBI/.python/venv/Scripts/python.exe" tests/test_resource_access.py
"D:/[PERSONAL PROJECT FILES]/TOBI/.python/venv/Scripts/python.exe" tests/test_terminal_engine.py
"D:/[PERSONAL PROJECT FILES]/TOBI/.python/venv/Scripts/python.exe" tests/test_chat_runtime.py
"D:/[PERSONAL PROJECT FILES]/TOBI/.python/venv/Scripts/python.exe" tests/test_chat_runtime_route.py
"D:/[PERSONAL PROJECT FILES]/TOBI/.python/venv/Scripts/python.exe" tests/test_conductor_final_guard.py
"D:/[PERSONAL PROJECT FILES]/TOBI/.python/venv/Scripts/python.exe" tests/test_conductor_mixed_reply.py
"D:/[PERSONAL PROJECT FILES]/TOBI/.python/venv/Scripts/python.exe" tests/test_mc_runtime_response_composer.py
"D:/[PERSONAL PROJECT FILES]/TOBI/.python/venv/Scripts/python.exe" tests/test_mc_runtime_intent_router.py
"D:/[PERSONAL PROJECT FILES]/TOBI/.python/venv/Scripts/python.exe" tests/test_mc_runtime_context_assembler.py
"D:/[PERSONAL PROJECT FILES]/TOBI/.python/venv/Scripts/python.exe" tests/test_mc_runtime_policy.py
"D:/[PERSONAL PROJECT FILES]/TOBI/.python/venv/Scripts/python.exe" tests/test_mc_runtime_policy_facts.py
"D:/[PERSONAL PROJECT FILES]/TOBI/.python/venv/Scripts/python.exe" tests/test_mc_runtime_approvals.py
"D:/[PERSONAL PROJECT FILES]/TOBI/.python/venv/Scripts/python.exe" tests/test_mc_runtime_tool_registry.py
"D:/[PERSONAL PROJECT FILES]/TOBI/.python/venv/Scripts/python.exe" tests/test_mc_runtime_tool_catalog.py
"D:/[PERSONAL PROJECT FILES]/TOBI/.python/venv/Scripts/python.exe" tests/test_mc_runtime_tool_adapters.py
"D:/[PERSONAL PROJECT FILES]/TOBI/.python/venv/Scripts/python.exe" tests/test_mc_runtime_project_tools.py
"D:/[PERSONAL PROJECT FILES]/TOBI/.python/venv/Scripts/python.exe" tests/test_mc_runtime_file_tools.py
"D:/[PERSONAL PROJECT FILES]/TOBI/.python/venv/Scripts/python.exe" tests/test_mc_runtime_terminal_tools.py
"D:/[PERSONAL PROJECT FILES]/TOBI/.python/venv/Scripts/python.exe" tests/test_mc_runtime_terminal_jobs.py
"D:/[PERSONAL PROJECT FILES]/TOBI/.python/venv/Scripts/python.exe" tests/test_mc_runtime_action_receipts.py
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

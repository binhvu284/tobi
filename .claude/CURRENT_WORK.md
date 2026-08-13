# Current work

One package at a time. This file is the only thing that changes between packages — `CLAUDE.md`
points here and never needs editing again.

Read this before writing code. Re-read the Purpose line whenever you have been fixing something
for more than an hour: if what you are fixing does not serve that line, stop and log it instead.

---

**Item:** #21 Mission Control Infrastructure V2
**Package:** T08 Run 3B2 - Compatibility tool-loop orchestration extraction (delivered; awaiting owner acceptance)

**Purpose (one sentence, plain words):**
Move Conductor's model/tool iteration, ordered call batching, combined proposals, and step-budget
fallback behind one typed Runtime service without changing what executes or what the owner sees.

**Not doing:**
- No release of Run 4 planning or T08 closeout before owner acceptance of this Run 3B2 delivery.
- No work outside the approved Run 3B2 implementation scope.
- No change to the accepted Run 3A checkpoint-recovery service or persisted recovery behavior.
- No change to accepted one-call validation or dispatch. Run 3B2 invokes the Run 3B1 service once
  per parsed call and does not absorb policy, registry, Terminal, audit, approval, or receipt logic.
- No change to tool-call parsing or deduplication; the existing parser remains authoritative.
- No final-answer cleanup, reasoning removal, mixed tool/prose handling, model escalation/selection,
  or no-tools direct-answer extraction; Run 4 owns those remaining Conductor responsibilities.
- No activation of the dormant canonical executor, durable loop controller, or T07 tool runtimes.
- No new validation, execution, policy, approval, receipt, proposal, or action authority.
- No change to retry limits, model/tool call order, per-call step identity, corrective prompts,
  combined proposal timing, tool-step budgets, forced-final prompts, or token-limit continuation.
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
- `core/runtime/tool_loop_orchestrator.py`
- `core/conductor.py`
- `tests/test_mc_runtime_tool_loop_orchestrator.py`
- `tests/test_mc_runtime_tool_call_executor.py` (superseded Run 3B1 source-location assertion only)
- `tests/test_mc_runtime_checkpoint_recovery.py` (superseded source-location assertion only)

**Gate: green**

```gate
"C:/Users/LE BINH/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe" tests/test_mc_runtime_tool_loop_orchestrator.py
"C:/Users/LE BINH/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe" tests/test_mc_runtime_tool_call_executor.py
"C:/Users/LE BINH/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe" tests/test_mc_runtime_checkpoint_recovery.py
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

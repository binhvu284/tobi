# Current work

One package at a time. This file is the only thing that changes between packages — `CLAUDE.md`
points here and never needs editing again.

Read this before writing code. Re-read the Purpose line whenever you have been fixing something
for more than an hour: if what you are fixing does not serve that line, stop and log it instead.

---

**Item:** #35 TOBI Agent Tier Completion
**Package:** T02 - Owner-Wording Live Repair
**Status:** T00 and T01 complete. T02 owner-wording repair is implemented; owner live retest is pending.

**Purpose (one sentence, plain words):**
Make the owner's normal wording `list all project` enter T02 canonical Runtime instead of the legacy
model loop, without widening another Agent or Developer route.

**Not doing:**
- No Chat-to-Developer dispatch (T02A), coding worker execution, or changes to DeepSeek Harness.
- No browser automation, GitHub action, Telegram delivery, external connector action, or proactive work.
- No changes to DeepSeek Harness or another agent's Developer-worker implementation.
- No live model calls, browser submissions, GitHub writes, Telegram delivery, Supabase, Vercel, merge,
  deployment, deletion, spending, or credential changes.
- No changes to frozen #34 cases, formulas, model IDs, holdouts, or acceptance artifacts.
- No Operator opportunity selection, prioritization, ROI scoring, or autonomous business experiments.

**Files expected:**
- `.claude/CURRENT_WORK.md`
- `core/runtime/agent_workflows.py`
- `core/runtime/file_tools.py`
- `core/chat_runtime_contracts.py`
- `core/chat_runtime.py`
- `core/owner_flags.py`
- `core/conductor_registry.py`
- `api/routers/chat.py`
- `core/agent_tier.py`
- `core/runtime/self_check.py`
- `tests/test_agent_tier_workflows.py`
- `tests/test_mc_runtime_file_tools.py`
- `docs/feature-idea-queue/AGENT_TIER_COMPLETION_PLAN.md`
- `docs/feature-idea-queue/QUEUE.md`
- `docs/feature-idea-queue/QUEUE_DELIVERY_LOG.md`
- focused #35 documentation plus the inherited #21/#34/T00 gate

**Gate: green - the owner-wording repair and all 32 suites must pass**

```gate
../.python/venv/Scripts/python.exe tests/test_agent_tier_workflows.py
../.python/venv/Scripts/python.exe tests/test_agent_tier_registry.py
../.python/venv/Scripts/python.exe tests/test_agent_tier_baseline.py
../.python/venv/Scripts/python.exe tests/test_mc_runtime_contracts.py
../.python/venv/Scripts/python.exe tests/test_mc_runtime_event_store.py
../.python/venv/Scripts/python.exe tests/test_mc_runtime_repository.py
../.python/venv/Scripts/python.exe tests/test_mc_runtime_gateway_live_chat.py
../.python/venv/Scripts/python.exe tests/test_mc_runtime_policy.py
../.python/venv/Scripts/python.exe tests/test_mc_runtime_tool_catalog.py
../.python/venv/Scripts/python.exe tests/test_mc_runtime_project_tools.py
../.python/venv/Scripts/python.exe tests/test_mc_runtime_file_tools.py
../.python/venv/Scripts/python.exe tests/test_mc_runtime_terminal_jobs.py
../.python/venv/Scripts/python.exe tests/test_mc_runtime_conductor_facade.py
../.python/venv/Scripts/python.exe tests/test_mc_runtime_owner_intelligence.py
../.python/venv/Scripts/python.exe tests/test_mc_runtime_coding_adapter.py
../.python/venv/Scripts/python.exe tests/test_mc_runtime_evals.py
../.python/venv/Scripts/python.exe tests/test_mc_runtime_system_model.py
../.python/venv/Scripts/python.exe tests/test_mc_runtime_security.py
../.python/venv/Scripts/python.exe tests/test_mc_runtime_runs_view.py
../.python/venv/Scripts/python.exe tests/test_mc_runtime_runs_ui.py
../.python/venv/Scripts/python.exe tests/test_mc_runtime_rollout.py
../.python/venv/Scripts/python.exe tests/test_mc_runtime_surface_adapters.py
../.python/venv/Scripts/python.exe tests/test_model_unreachable_message.py
../.python/venv/Scripts/python.exe tests/test_runtime_schema_ledger.py
../.python/venv/Scripts/python.exe tests/test_infrastructure_self_check.py
../.python/venv/Scripts/python.exe tests/test_no_console_windows.py
../.python/venv/Scripts/python.exe tests/test_ui_loading_states.py
../.python/venv/Scripts/python.exe tests/test_tobival_acceptance.py
../.python/venv/Scripts/python.exe tests/test_tobival_model_dependency.py
../.python/venv/Scripts/python.exe tests/test_tobival_api.py
../.python/venv/Scripts/python.exe tests/test_tobival_workflows.py
../.python/venv/Scripts/python.exe tests/test_chat_runtime.py
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

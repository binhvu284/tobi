# Current work

One package at a time. This file is the only thing that changes between packages — `CLAUDE.md`
points here and never needs editing again.

Read this before writing code. Re-read the Purpose line whenever you have been fixing something
for more than an hour: if what you are fixing does not serve that line, stop and log it instead.

---

**Item:** #21 Mission Control Infrastructure V2
**Package:** T15 - Remaining surface adapters, documentation, and #21 closeout

**Purpose (one sentence, plain words):**
Give Projects, Office, CLI, Telegram, and schedulers one safe compatibility adapter into canonical
run history, document the final system, and close #21 without deleting legacy behavior.

**Not doing:**
- No raw request, prompt, response, tool output, secret, or error body in adapter history.
- No replacement of existing Projects, Office, CLI, Telegram, or scheduler execution.
- No activation flag change in the real owner database.
- No legacy deletion; retirement remains a separate owner-approved decision.
- No Supabase, Vercel, external integration, or production-runtime interaction.

**Files expected:**
- `.claude/CURRENT_WORK.md`
- `core/runtime/surface_adapter.py`
- `api/runtime_surface.py` and API composition wiring
- narrow `main.py`, Telegram, and scheduler entrypoint wiring
- architecture, operation, API, testing, security, queue, and legacy-exit docs
- focused adapter and full final gate tests

**Gate: green**

```gate
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

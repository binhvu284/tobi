# Current work

One package at a time. This file is the only thing that changes between packages — `CLAUDE.md`
points here and never needs editing again.

Read this before writing code. Re-read the Purpose line whenever you have been fixing something
for more than an hour: if what you are fixing does not serve that line, stop and log it instead.

---

**Item:** #21 Mission Control Infrastructure V2
**Package:** T07 Run 2B - dormant bounded file write slice (delivered; awaiting owner acceptance)

**Purpose (one sentence, plain words):**
Expose the existing coding broker's `write_file` operation through canonical validation, approval,
one immutable receipt, exact replay, and hash-based crash reconciliation without changing any live route.

**Not doing:**
- No live tool routing, policy cutover, caller integration, or flag change.
- No `replace_text`, search, patch, command, or terminal execution; Run 3 owns terminal tools.
- No change to `CodingToolBroker`, coding policy, accepted #22 workers, worktree setup, or their live imports.
- No deletion, bypass, or duplication of legacy tool registries or filesystem path authority.
- No unguarded overwrite: the caller must provide the expected current SHA-256 hash, or `absent` for a new file.
- No automatic retry while a write outcome is uncertain; current file evidence must reconcile it first.
- No unrestricted filesystem authority; the existing approved-worktree, protected-path, forbidden-path, and file-size rules remain decisive.
- No new table, migration, owner flag, API, UI, or visible behavior.
- No Conductor decomposition; T08 owns it.
- No Runs page or broad frontend redesign; T13 owns it.
- No Telegram, CLI, Office, scheduler, or remaining-surface adapters.
- No Supabase, Vercel, external integration, or production-runtime interaction.

**Files expected:**
- `core/runtime/tool_execution.py`
- `core/runtime/actions.py`
- `core/runtime/file_tools.py`
- `tests/test_mc_runtime_file_tools.py`
- `tests/test_mc_runtime_project_tools.py`
- `.claude/CURRENT_WORK.md`
- `docs/feature-idea-queue/MC_V2_BOARD.md`
- `docs/feature-idea-queue/MISSION_CONTROL_INFRASTRUCTURE_V2_PLAN.md`
- `docs/feature-idea-queue/QUEUE.md`

**Gate: green**

```gate
"D:/[PERSONAL PROJECT FILES]/TOBI/.python/venv/Scripts/python.exe" tests/test_mc_runtime_file_tools.py
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

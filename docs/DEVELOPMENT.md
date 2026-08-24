# Development and Operations

This guide describes the current repository commands. It does not replace the archived Hermes/VPS notes, and it does not claim that external services are configured.

## TM01 Refresh Snapshot - 2026-08-25

The verified base is commit `6617575`, with `origin/main` at `31d95ec`. The checkout is not clean:
the active #21/T15 package adds Infrastructure self-check, hidden-window process spawning, new
diagram files, and related tests/UI. Do not use `git status` as proof that those changes shipped;
run the active gate and inspect the commit after the package is closed.

Graphify is available only as the checked-in navigation output for this checkout; the generated
index predates the current revision. Use it to find likely files, then verify current code and
tests directly.

## Prerequisites

- Windows development is the actively represented local setup (`venv/Scripts/python.exe`, PowerShell-capable terminal engine).
- The existing D-drive virtual environment was created with Python 3.11.9, but its recorded base-interpreter path is stale in the current environment. The repository has no formal Python-version pin. Recreate the environment with a compatible Python 3.11 installation if `venv\Scripts\python.exe --version` fails.
- Node.js and npm are required for Mission Control.
- Optional native/runtime tools are needed only for the features that use them, such as Hermes, cloudflared, package managers, or fastembed dependencies.

## Initial Setup

From the repository root:

```powershell
python -m venv venv
venv\Scripts\python.exe -m pip install -r requirements.txt
npm install
npm install -C dashboard
Copy-Item .env.example .env
```

Fill only the environment variables needed for the surfaces being tested. Never place real values in documentation, commits, logs, or screenshots.

The Genesis vault can manage supported secrets from Mission Control after the application is running. Environment variables remain supported for compatibility and startup.

## Development Commands

| Command | Use |
|---|---|
| `npm run dev` | Runs the Python `start` process through nodemon and watches the built dashboard. This includes Telegram and scheduler behavior when configured |
| `npm run dev:backend` | Runs nodemon using `venv/Scripts/python.exe main.py start` |
| `npm run dev:frontend` | Type-checks/builds the dashboard in watch mode; port 8080 serves the resulting `dashboard/dist` |
| `npm run build` | Runs TypeScript checking and a production Vite build (`npm.cmd` may be required when PowerShell script execution is disabled) |
| `venv\Scripts\python.exe main.py api` | Starts only the two web APIs and built MC host; safer for UI/API work than the full daemon |
| `venv\Scripts\python.exe main.py status` | Prints database-backed status without starting the daemon |
| `venv\Scripts\python.exe main.py terminal` | Starts the interactive TOBI terminal/Conductor REPL |
| `venv\Scripts\python.exe main.py test` | Tests configured connections and may contact external services; run only when that is intended |
| `venv\Scripts\python.exe -m core.coding_runner_service` | Runs the durable external coding-worker service; use with `TOBI_CODING_RUNNER_MODE=service` |

For the current #34/T01 package gate, run from `tobi/` with the bundled D-drive interpreter:

```powershell
& "D:\[PERSONAL PROJECT FILES]\TOBI\.python\venv\Scripts\python.exe" scripts/gate.py
```

This is separate from `venv\Scripts\python.exe`; use the interpreter named by the active
`.claude/CURRENT_WORK.md` when validating the package.

The T01 Gate runs the executable scorer, canonical runner, and inherited Runtime Eval checks. All
fixtures use a temporary database; no model or holdout is called.

The local TOBIval baseline commands are:

```powershell
& "D:\[PERSONAL PROJECT FILES]\TOBI\.python\venv\Scripts\python.exe" scripts/tobival.py verify
& "D:\[PERSONAL PROJECT FILES]\TOBI\.python\venv\Scripts\python.exe" scripts/tobival.py baseline --output tests/evals/baselines/5ffa3d93fd18ade107694947226e440947f1225c/unchanged-baseline.json
& "D:\[PERSONAL PROJECT FILES]\TOBI\.python\venv\Scripts\python.exe" scripts/tobival.py run-model-baseline
```

`verify` and `baseline` are offline. `run-model-baseline` makes 168 bounded model calls and refuses
to start until `tests/evals/v1/benchmark.json` records owner approval. Development runs exclude all
14 holdouts; only the final-acceptance purpose can load them. An existing model artifact is immutable;
replacement requires both `--replace` and `--confirm` plus renewed owner authorization.

`main.py start`, `research`, `execute`, `ceo`, `test`, and configured Telegram flows can cause external calls or messages. Choose the narrowest command for the task.

## Ports

| Port | Service |
|---|---|
| 8080 default | Mission Control static app, MC API, SSE, and MCP mount |
| 8000 default | Smaller API-key-protected external/legacy API |
| 5173 | Vite dev server only when `npm run dev -C dashboard` is run directly; it proxies `/api` and `/done` to 8080 |

`API_PORT`, `DASHBOARD_PORT`, and `DASHBOARD_URL` can override defaults.

## Environment Variable Groups

The exact names are documented in `.env.example`.

| Group | Examples |
|---|---|
| Model routing | `PRIMARY_MODEL`, provider API keys |
| Telegram | bot token, allowed users, chat ID |
| Research | Tavily key |
| Web services | API/dashboard ports and public URL |
| Persistence | `DB_PATH` |
| External API | `API_KEY` |
| Integrations | Notion, GitHub, Google OAuth, Vercel, Supabase names |
| Hermes | `HERMES_DIR` |
| Coding runner | `TOBI_CODING_RUNNER_MODE`, runner startup timeout, optional runner key path, profile-specific API key names |

Do not infer connection success from a populated environment name. Use the relevant MC status and an explicit test when external interaction is authorized.

## Persistent and Generated Data

| Location | Content | Git status |
|---|---|---|
| `~/.mmo_agent/agent.db` or `DB_PATH` | Primary SQLite state | External to repo by default |
| `<DB dir>/projects/{id}/resources/` | Project resource files | External to repo by default |
| `~/.hermes/` | Hermes config, persona, skills, and mirrored state | External runtime state |
| `.tobi/`, `.hermes/`, `logs/` | Repo-local runtime/user data when present | Ignored; never treat as docs source |
| `<DB dir>/developer/runner-envelope.key` | AES-GCM key for profile-specific API-key transfer to the supervised runner | Ignored runtime secret; back up and permission like the database |
| `dashboard/dist/` | Built Mission Control assets | Tracked in the current repository |
| `graphify-out/` | Generated code/document graph | Ignored and may be stale |
| `node_modules/`, `venv/` | Dependencies | Ignored |

Back up the configured database directory before schema or migration work. Do not delete ignored runtime folders as part of docs or UI cleanup.

## Verification

### Backend tests

Tracked tests are standalone Python scripts rather than one pytest suite. Run the narrowest affected scripts first:

```powershell
venv\Scripts\python.exe tests\test_terminal_engine.py
venv\Scripts\python.exe tests\test_storage_usage.py
venv\Scripts\python.exe tests\test_premium_readers.py
venv\Scripts\python.exe tests\test_premium_readers_route.py
venv\Scripts\python.exe tests\test_chat_modes.py
venv\Scripts\python.exe tests\test_mode_enforcement.py
venv\Scripts\python.exe tests\test_net_guard.py
venv\Scripts\python.exe tests\test_chat_runtime.py
venv\Scripts\python.exe tests\test_chat_runtime_route.py
venv\Scripts\python.exe tests\test_conductor_final_guard.py
venv\Scripts\python.exe tests\test_mc_runtime_control.py
venv\Scripts\python.exe tests\test_awakening.py
venv\Scripts\python.exe tests\test_awakening_route.py
venv\Scripts\python.exe tests\test_resource_access.py
venv\Scripts\python.exe tests\test_performance_doctor.py
venv\Scripts\python.exe tests\test_office_v3.py
venv\Scripts\python.exe tests\test_coding_agent.py
venv\Scripts\python.exe tests\test_coding_agent_v2.py
venv\Scripts\python.exe tests\test_coding_agent_production.py
venv\Scripts\python.exe tests\test_mc_runtime_contracts.py
venv\Scripts\python.exe tests\test_mc_runtime_event_store.py
venv\Scripts\python.exe tests\test_mc_runtime_repository.py
venv\Scripts\python.exe tests\test_mc_runtime_leases.py
venv\Scripts\python.exe tests\test_mc_runtime_loop_control.py
venv\Scripts\python.exe tests\test_mc_runtime_action_receipts.py
```

Rebuild and verify every dormant MC Runtime V2 projection from local event history:

```powershell
venv\Scripts\python.exe -m core.runtime.rebuild --all --verify
```

Correct output is one JSON object with `"verified": true`. The command changes only derived projection rows; immutable event history is never rewritten.

The repository acceptance scripts verify canonical runs, validated plan graphs, immutable loop-policy snapshots, secret redaction, version-checked state changes, exclusive expiring step leases, stale-worker fencing, append-only restart checkpoints, exact-once loop usage, evidence-backed completion, deterministic hard-limit stops, one-winner action reservations, immutable receipts, completed replay, and fail-closed crash reconciliation. These foundations remain dormant until a later adapter package switches a live surface.

The route suites use FastAPI/TestClient and must run with the same Python ABI as the installed `pydantic_core`. If the checked-in virtual-environment launcher points to a removed Windows Store interpreter, recreate the venv rather than mixing an incompatible Python runtime with its site-packages. A dependency-light bundled interpreter can run some unit scripts, but it is not a substitute for the project environment when FastAPI or compiled packages are required.

### Frontend checks

```powershell
npm run build
```

For user-facing MC changes, also verify the affected route in a browser at desktop and mobile widths, plus the relevant theme/motion modes.

For Chat/Agent changes, verify both the live stream and a page reload. The stored assistant message must retain mode, tools, checkpoints, run ID, artifact IDs, and elapsed time; completed `ProcessTrace` history must expand and collapse.

### API smoke

Use `main.py api` for local smoke work. Confirm only the domain endpoints relevant to the change. Do not run connection tests, integrations, deployments, or destructive endpoints as a generic health check.

## Graphify Workflow

Graphify output can narrow the first reading pass, but this checkout has no installed `graphify`
command. The checked-in `graphify-out/` map was generated on 2026-08-19 and is stale relative to
the current revision, so direct `rg` and source/test verification remains required.

When Graphify is installed:

```powershell
graphify query "how does this feature work"
graphify path "source" "target"
graphify . --update
```

Read the complete target file before editing. Generated graph output is navigation assistance, not an architecture contract.

## Security and Operations Notes

- Most port-8080 MC APIs do not have general authentication. Bind or expose them only within a trusted single-owner boundary.
- The Codespaces path can make port 8080 public automatically. Review deployment visibility before using real secrets or data.
- Set a non-default `API_KEY`; the smaller API has a fallback value in code.
- Vault sessions protect sensitive vault/MCP operations, but they do not secure every MC route.
- Terminal Auto mode still has a hard denylist, but it is not an OS sandbox.
- External content, repository files, URLs, and MCP output can contain prompt injection or unsafe instructions.
- Deep Research/readable-link fetching must continue through `net_guard`; do not replace it with direct `requests.get` calls.
- Chat mode capability denial and human-review policy are backend boundaries, not frontend-only controls.
- Chat route scopes may widen only to known safe read tools. Do not convert route narrowing into a permission system or bypass mode/risk policy.
- Connector credentials are not durable proof of access. Preserve `test_status`/`last_tested_at` invalidation on credential changes, and do not mark Google verified before OAuth plus a successful read test.
- Brain sweep changes must preserve per-chat fairness, owner-token lease checks, deferred failed payloads, and cleanup after recovery.
- External coding workers must stay inside isolated worktrees. Preserve explicit worker profiles, checkpoint-only switching, bounded output/deadlines, encrypted one-secret envelopes, and owner gates for protected paths, GitHub, merge, and deployment.
- Never use live production integrations as a routine test target.

## Documentation Delivery Rule

When implementation changes a route, API domain, table family, security boundary, execution policy, or user-visible capability:

1. update the relevant feature queue row;
2. update `02_CURRENT_STATE.md`;
3. update `ARCHITECTURE.md` or `MISSION_CONTROL.md` as appropriate;
4. record any superseded doc in `DOCUMENTATION_AUDIT.md` or the archive index;
5. verify local Markdown links before handoff.

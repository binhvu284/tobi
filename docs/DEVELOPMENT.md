# Development and Operations

This guide describes the current repository commands. It does not replace the archived Hermes/VPS notes, and it does not claim that external services are configured.

## Prerequisites

- Windows development is the actively represented local setup (`venv/Scripts/python.exe`, PowerShell-capable terminal engine).
- The current D-drive virtual environment reports Python 3.11.9. The repository has no formal Python-version pin, so use a compatible 3.11 environment unless a dedicated upgrade validates all dependencies.
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
| `npm run build` | Runs TypeScript checking and a production Vite build |
| `venv\Scripts\python.exe main.py api` | Starts only the two web APIs and built MC host; safer for UI/API work than the full daemon |
| `venv\Scripts\python.exe main.py status` | Prints database-backed status without starting the daemon |
| `venv\Scripts\python.exe main.py terminal` | Starts the interactive TOBI terminal/Conductor REPL |
| `venv\Scripts\python.exe main.py test` | Tests configured connections and may contact external services; run only when that is intended |

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

Do not infer connection success from a populated environment name. Use the relevant MC status and an explicit test when external interaction is authorized.

## Persistent and Generated Data

| Location | Content | Git status |
|---|---|---|
| `~/.mmo_agent/agent.db` or `DB_PATH` | Primary SQLite state | External to repo by default |
| `<DB dir>/projects/{id}/resources/` | Project resource files | External to repo by default |
| `~/.hermes/` | Hermes config, persona, skills, and mirrored state | External runtime state |
| `.tobi/`, `.hermes/`, `logs/` | Repo-local runtime/user data when present | Ignored; never treat as docs source |
| `dashboard/dist/` | Built Mission Control assets | Tracked in the current repository |
| `graphify-out/` | Generated code/document graph | Ignored and may be stale |
| `node_modules/`, `venv/` | Dependencies | Ignored |

Back up the configured database directory before schema or migration work. Do not delete ignored runtime folders as part of docs or UI cleanup.

## Verification

### Backend tests

Tracked tests currently cover terminal safety/execution and storage/usage behavior:

```powershell
venv\Scripts\python.exe -m pytest tests
```

Run focused modules while iterating:

```powershell
venv\Scripts\python.exe -m pytest tests\test_terminal_engine.py
venv\Scripts\python.exe -m pytest tests\test_storage_usage.py
```

`pytest` is not pinned in `requirements.txt`; use the existing development environment or add it only in a dedicated dependency change.

### Frontend checks

```powershell
npm run build
```

For user-facing MC changes, also verify the affected route in a browser at desktop and mobile widths, plus the relevant theme/motion modes.

### API smoke

Use `main.py api` for local smoke work. Confirm only the domain endpoints relevant to the change. Do not run connection tests, integrations, deployments, or destructive endpoints as a generic health check.

## Graphify Workflow

Graphify output can narrow the first reading pass, but the checked-in/local generated indexes currently predate recent Terminal, Theme, Project, and Chat changes.

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
- Never use live production integrations as a routine test target.

## Documentation Delivery Rule

When implementation changes a route, API domain, table family, security boundary, execution policy, or user-visible capability:

1. update the relevant feature queue row;
2. update `02_CURRENT_STATE.md`;
3. update `ARCHITECTURE.md` or `MISSION_CONTROL.md` as appropriate;
4. record any superseded doc in `DOCUMENTATION_AUDIT.md` or the archive index;
5. verify local Markdown links before handoff.

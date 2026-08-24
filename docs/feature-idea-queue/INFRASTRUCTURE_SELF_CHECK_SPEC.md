# One-Click Infrastructure Test

`CHECK-CORE-4H-007` · Queue item #33 · delivered 2026-08-21

## The one thing this is for

> Health could say `healthy` while Mission Control was completely broken. On 2026-08-20 a server
> ran for hours reporting green with no internet at all, and a second one served a database it
> had created itself thirty seconds earlier. Nothing on the page checked either thing. This is
> one button that checks everything, including the things that were actually wrong.

## Where it lives

**Health → Infrastructure → Run infrastructure test.** About a minute. Nothing is written to your
data at any point.

## What it checks

Two halves, because neither is enough on its own.

### This server (instant, read-only)

Twelve checks only a *running* server can answer. An offline test suite can never fail on any of
these, and every incident so far has been one of them.

| Check | Catches |
|---|---|
| Serving the right database | A server pointed at an empty or unexpected database file |
| Canonical history tables are present | A half-applied or missing runtime schema |
| This server can reach the internet | A server started inside an agent sandbox — the 2026-08-20 defect |
| Secrets are masked before storage | Redaction silently switched off |
| The Runs page can read history | The Runs view failing or exposing raw bodies |
| The runtime engine is wired in | Engine mode and the nine rollout flags |
| Rollout controls answer | Stage, rollback switch, and what is blocking each stage |
| Every surface has an adapter | Projects, Office, CLI, Telegram, schedulers |
| This server serves the runtime API | The runtime router failing to mount |
| The page you are reading is current | A dashboard build older than the source |
| Saved keys are loaded | A locked vault making every connector read as unavailable |
| A failing model has somewhere to go | An empty fallback chain, so a model failure has no recovery |

Each failed row carries the next thing to do about it, not just the fact that it failed.

### The foundation (about a minute)

Every acceptance suite for #21, each run as its own process against its own throwaway database.
Twenty-three suites, **362 individual proofs**, covering T01 through T15 plus the interface rules:

shared shapes · written history · durable runs · Chat and Agent routing · permissions ·
the tool catalog · project, file and terminal actions · the Conductor facade · owner memory ·
worker boundaries · traces and release gates · the system model · security probes ·
the Runs page · staged rollout · every surface adapter · honest model errors ·
the migration ledger · loading states · and this test itself.

## Why it runs the release gate's own suites

There is exactly one list of "the checks that matter", and both the button and the release gate
read it. `tests/test_infrastructure_self_check.py` fails if they ever differ, so green on the
Health page and green at release can never come to mean different things.

## Rules it follows

1. **Never touches owner data.** Each suite gets a fresh temporary database; the wiring checks
   only read.
2. **Never leaks.** Suite output is a child process's stdout. Keys, tokens and bot credentials
   are masked before anything reaches the page.
3. **Never red for a reason you cannot act on.** Three suites start real worker processes and
   wait on real timeouts. A failure is re-run once before it is believed; a suite that passes the
   second time is shown as passing and labelled `passed on retry`, so a genuine failure still
   fails twice and a timing flake never sends you hunting.
4. **Suites run one at a time**, on purpose — running them together is what made one lose a race
   it should have won.

## What it found on its first run

| Finding | Status |
|---|---|
| The runtime migration ledger recorded nothing, so the whole runtime schema was re-applied on every database call | Fixed — `core/schema/runtime.py` writes `applied_at` itself instead of trusting a default owned by another module |
| The vault is locked, so 37 saved keys are not loaded | Owner action: unlock once in Integrations, re-enable auto-connect |

## Files

| File | Role |
|---|---|
| `core/runtime/self_check.py` | The suite registry, the wiring checks, and the runner |
| `api/routers/health.py` | `/api/health/infrastructure` and `/api/health/infrastructure/stream` |
| `dashboard/src/components/InfrastructureCheck.tsx` | The tab, the button, and the result display |
| `tests/test_infrastructure_self_check.py` | Checks the checker |
| `tests/test_runtime_schema_ledger.py` | The ledger defect this found |

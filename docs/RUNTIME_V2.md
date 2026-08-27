# Mission Control Runtime V2

> Verified 2026-08-28 against committed Runtime V2 and #34/T08 source through `685a1a8`. No
> rollout activation, deployment, Supabase action, or Vercel action was performed.

## Current Status

Queue #21 is complete. Runtime V2 supplies one validated contract family, durable SQLite history,
recovery controls, policy and tool boundaries, evaluation gates, a System Model, the Runs page,
staged rollout, and compatibility adapters for every current request surface.

All Runtime V2 rollout controls default off. The #21 implementation and activation tests used
temporary local databases; they did not change the owner's live flags or call an external service.

The Infrastructure self-check is committed; Health and the release gate now execute the same 29
suites.
#34/T00 freezes the accepted TOBIval baseline. T01 adds executable scorers and a runner that attaches
bounded observed evidence to canonical traces and the existing immutable Eval tables. T02 adds a
hash-verified 21-workflow catalog, deterministic selection and tool boundaries, plus bounded workflow
version and selection-reason trace evidence. T03 resolves current project/task/resource identities,
validates proposed arguments through canonical tool schemas, and freezes accepted requests with stable
hashes and idempotency keys. T04 composes no-model outcomes from typed evidence and blocks action-success
claims without the matching receipt; malformed structured output has one bounded repair and optional
escalation before a truthful failure. T05 adds immutable suite/control/finding-event records, scoped
freshness gates, and an explicit bounded live-suite service; `RolloutController` checks the affected
scope server-side. T06 adds a vault-protected Eval projection/API and the Runs -> Evaluations owner
view, including truthful unavailable states and bounded case evidence. T07 added the frozen
final-acceptance runner and bounded local artifact.

T08 repairs the final claim. Every frozen case now enters a canonical Runtime lifecycle and records
bounded route, context, validation, execution, and final-outcome decision ownership. The acceptance
report separates live model responses and raw pass rate from deterministic recovery, quarantines
legacy v1 synthetic artifacts, and blocks release with `model-quality-proof-missing` when no live
response exists. A narrow production `route_turn` boundary handles safe supported workflows with no
required fields; broader typed workflows remain outside normal Chat/Agent execution. No rollout flag
was activated.

## Request Flow

1. A surface validates or adapts a request into `RunRequest`.
2. Runtime stores one canonical run and an ordered accepted event.
3. Active work uses version checks, a lease (so two workers cannot own one step), checkpoints,
   bounded retries, loop limits, central policy, approvals, and immutable action receipts.
4. Every saved event is redacted before persistence.
5. Trace, evaluation, System, and Runs projections rebuild from bounded references rather than raw
   prompts, responses, file bodies, tool output, secrets, or provider errors.
6. Recovery resumes or closes the same run; it does not invent a replacement history.

## Surface Ownership

| Surface | Runtime V2 behavior | Existing execution owner |
|---|---|---|
| Chat and Agent | Canonical gateway; direct plain-text Chat has a gated active path, and #34 adds a narrow deterministic route for safe supported requests with no required fields; other routes retain shadow compatibility | Chat route and Conductor |
| Developer/Coding | Accepted #22 history is mirrored into one canonical run | DevelopmentStore and Coding Agent V2 |
| Projects | Mutating `/api/pm` requests create passive shadow runs when event mirroring is enabled | Project v2 routes and services |
| Office | Mutating `/api/office` requests create passive shadow runs when event mirroring is enabled | Office routes, missions, and artifacts |
| CLI | Each `main.py` command is wrapped by the passive adapter | Existing CLI command handler |
| Telegram | Each message handler is wrapped by the passive adapter | Existing Telegram handler and Conductor |
| Scheduler | Every registered callback is wrapped by the passive adapter | Existing scheduled job function |

Passive means the adapter records only surface, operation, status, and evidence references. If the
adapter fails, legacy work continues. Routine Projects/Office polling reads are not recorded unless
the caller supplies `X-Request-ID` or `Idempotency-Key`, preventing unbounded history growth.

## Data

Runtime schema versions are recorded as `mc-runtime-v2-001` through `mc-runtime-v2-014`.
Authoritative history includes runs, events, steps, checkpoints, commands, loops, approvals,
policy decisions, receipts, evaluations, System entities and edges, rollout comparisons, terminal
jobs, and bounded preferences. Immutable history tables reject update and delete operations at the
database layer. Current projections can be rebuilt from history.

## API

| Endpoint | Purpose |
|---|---|
| `GET /api/runtime/runs` | Bounded run list with cursor and surface/status filters |
| `GET /api/runtime/runs/{id}/snapshot?after=N` | Detail plus only events after sequence `N` |
| `GET /api/runtime/runs/{id}/events` | Session-scoped event replay and live tail |
| `GET /api/runtime/loops` | Loop recipes and current Developer preference |
| `PUT /api/runtime/preferences/developer-loop` | Save a non-activating Developer loop preference |
| `GET /api/runtime/rollout` | Stage, rollback state, comparison streaks, and blockers |
| `POST /api/runtime/rollout/activate/{stage}` | Advance exactly one evidence-ready stage |
| `POST /api/runtime/rollout/rollback` | Return new work to shadow behavior |
| `POST /api/runtime/rollout/resume` | Recheck gates and resume the approved stage |

Rollout mutations require `X-Vault-Session`. Stages are `direct_chat`, `read_chat`, `actions`, and
`agent`. Each stage needs seven consecutive passing comparisons and the release gate; Agent also
needs the autonomy gate. Stages cannot be skipped or moved backward.

## Security Rules

- No raw request, prompt, response, attachment body, file content, diff, tool output, secret, or raw
  provider error belongs in Runtime history, traces, comparisons, or frontend state.
- Unknown contracts, tools, policies, approvals, stages, and adapter inputs fail closed.
- Mutation receipts and approvals are identity-bound and replay-safe.
- Rollback changes only new work. Accepted run mode and immutable evidence never change.
- Runtime does not make the mostly unauthenticated port-8080 dashboard safe for public exposure.

## Verification

Run the final package gate from `tobi/`:

```powershell
& "D:\[PERSONAL PROJECT FILES]\TOBI\.python\venv\Scripts\python.exe" scripts/gate.py
```

The gate covers the 29 shared #21/#33/#34 release suites. Focused tests remain under
`tests/test_mc_runtime_*.py` and `tests/test_tobival_*.py`.
The dashboard production build is `npm.cmd --prefix dashboard run build`.

## Legacy Exit

No legacy code or table was deleted. The required owner decision and evidence are recorded in
[`feature-idea-queue/MC_V2_LEGACY_EXIT_REVIEW.md`](feature-idea-queue/MC_V2_LEGACY_EXIT_REVIEW.md).
Retirement is a new queue item, not unfinished #21 work.

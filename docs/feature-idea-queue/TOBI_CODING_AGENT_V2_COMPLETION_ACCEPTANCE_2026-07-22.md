# TOBI Coding Agent V2 Completion Acceptance - 2026-07-22

> Queue: #22
> State: Implementation complete; local live-run and owner browser acceptance pending.
> Dependency: #21 remains blocked until every local gate below passes.

## Acceptance Graph

```mermaid
flowchart LR
  A[Automated contracts] --> B[Ten real local runs]
  B --> C[Owner browser review]
  C --> D[Close queue 22]
  D --> E[Unblock queue 21]
  C --> F[Later VPS soak]
```

## Automated Evidence

| Gate | Result | Evidence |
|---|---|---|
| Python compilation | Pass | Completion runtime, persistence, tools, workers, loop, and API modules compile under Python 3.11. |
| Focused backend suite | Pass | 14 tests passed across completion, production, V2, tools, Process, Queue, and recovery coverage. |
| Dashboard type/build gate | Pass | `npm run build` completed; TypeScript and Vite production build succeeded. |
| Patch hygiene | Pass | `git diff --check` completed without whitespace errors. |
| Goal execution removal | Pass | Tests verify Goals do not create synthetic tasks or coding sprints. |
| Strict readiness | Pass | Tests verify disabled or unhealthy agents are blocked before session creation and alternatives are returned. |
| Same-run retry | Pass | Tests verify stale recovery keeps the workflow identity and records a restart event. |
| Evidence qualification | Pass | Tests verify Goal qualification is derived from linked criterion evidence. |
| Queue conflict protection | Pass | Tests verify canonical queue insertion and hash-conflict rejection. |

## Ten-Run Local Matrix

Record the workflow ID, Queue item, agent, evidence, result, and defect link for every run. A run is not a pass when it requires direct database repair or an undocumented manual workaround.

| # | Scenario | State | Required proof |
|---:|---|---|---|
| 1 | MC Native happy path | Pending | Ready Queue item reaches verified completion with criterion evidence and scorecard. |
| 2 | Codex happy path | Pending | Authorized Codex session completes on one durable run and draft delivery is owner-gated. |
| 3 | OpenCode happy path | Pending | Authorized OpenCode session completes with selected provider/model shown consistently. |
| 4 | Protected-path approval | Pending | Preflight blocks Start, approval is explicit, and the approved scope is audited. |
| 5 | Invalid agent preflight | Pending | Disabled or unauthorized agent creates no run and healthy alternatives are offered. |
| 6 | Fallback agent switch | Pending | Mid-run failure pauses; owner switches agent at the same checkpoint without duplicate effects. |
| 7 | Backend restart resume | Pending | Restart reconciles Git, process, checkpoint, and side effects and safely resumes the same run. |
| 8 | Hung worker recovery | Pending | Heartbeat/no-output thresholds produce a structured recovery state and preserve evidence. |
| 9 | Main drift or conflict | Pending | Repository drift produces a safe owner action; no branch or Queue content is silently overwritten. |
| 10 | Auto classification | Pending | Item blocker permits independent eligible work; system failure stops Auto. |

## Owner Browser Acceptance

- Overview has a true idle launchpad and never substitutes a historical workflow for an active run.
- Work presents Goals as outcomes/evidence and Queue items as executable work with one clear create/edit path.
- Preflight explains blockers and healthy agent alternatives before creating a run.
- Process prioritizes raw output, verified gates, pinned approval/recovery actions, copy log, and one foreground run.
- Agents clearly show priority, enabled state, health, authorization, tool, provider/model, last success, and configuration.
- History can replay logs, checkpoints, diffs, evidence, scorecard, and outcome without mutating the run.
- System contains Storage, Learning, and Version with advanced details behind progressive disclosure.
- Idle, active, approval, failed, recovery, completed, and history states remain understandable without reading raw payloads.

## Closure Rule

1. Complete and record all ten real local runs.
2. Complete the owner browser checklist.
3. Fix every blocker or document a consciously accepted non-blocking limitation.
4. Change #22 to Done and change #21 from Blocked to Queued.
5. Keep the 24-hour and 72-hour VPS soak as deployment gates before calling the continuous loop production-proven.

## Rollback

- Disable the Coding Agent V2 completion feature flag and retain additive Goal links, readiness snapshots, attempts, evidence, scorecards, and historical runs.
- Continue serving legacy workflow routes through compatibility adapters.
- Do not delete historical synthetic Goal tasks; keep them hidden from active Work.

## Run Log

### Run 1 — MC Native happy path — 2026-07-25 — BLOCKED (not attempted, no run created)

No workflow was created, so there is no workflow ID to record. The run was stopped by
preflight, which is the correct behavior: this is live confirmation of the "Strict
readiness" automated gate, not a defect in it. Nothing was mutated to work around the
blockers — the Closure Rule states a run is not a pass when it needs direct database
repair or an undocumented manual workaround, and that applies equally to manufacturing
the preconditions.

Authoritative preflight output (`completion.preflight(queue_id, active_probe=False)`
against the live DB):

| Queue item | Resolved agent | Ready | Blockers |
|---|---|---|---|
| #24 `testing` | `codex-chatgpt` (default fallback) | **False** | `reviewer_unavailable` |
| #22 (self) | `mc-native` | **False** | `reviewer_unavailable`, `agent_disabled`, `scope_too_large`, `protected_scope_approval` |

**Root blocker — `reviewer-default` is disabled.** `coding_completion.py` treats a
reviewer as unavailable when the profile is missing, `enabled` is falsy, or its adapter
is not `model_review`. This profile has `adapter=model_review` and `health=ready`; only
`enabled` is 0. **Every one of the ten scenarios requires an independent reviewer, so no
run can reach verified completion until this flag is on.**

Profile state, ordered by `updated_at`:

| Slug | enabled | health | updated_at |
|---|---:|---|---|
| `reviewer-default` | 0 | ready | 2026-07-18T18:15:21Z |
| `opencode-glm` | 0 | ready | 2026-07-18T18:15:22Z |
| `mc-native` | 0 | needs_auth | 2026-07-18T18:15:24Z |
| `codex-chatgpt` | 1 | ready | (live probe) |
| `hermes-legacy` | 1 | disabled | (live probe) |

Three profiles were disabled inside a **3-second window on 2026-07-18**, which reads as
programmatic rather than hand-edited. That is **four days before this acceptance matrix
was written**, so the ten runs have been unrunnable since before the matrix existed —
which explains 0/10 recorded runs against a system that has otherwise been exercised
(7 coding sessions, 22 worker sessions, 24 checkpoints, 555 development events).
**Worth diagnosing before re-enabling**: if a health-probe or policy path disabled them,
flipping the flags by hand will regress.

Additional blockers for run 1 specifically:

1. **Vault locked.** `/api/vault/status` reports `unlocked: false`; every
   `/api/developer/*` route returns `401 "Unlock the Mission Control vault to use
   Developer."` Requires the owner's master password in the browser.
2. **`mc-native` is disabled and `needs_auth`** — "codex is installed but its native
   login is not authorized." Run 1 is by definition the MC Native path, so the fallback
   to `codex-chatgpt` does not satisfy it; that is run 2.
3. **No Ready-scoped Queue item.** Statuses are 18 completed / 8 planned / 2 approved,
   with no Ready item. #24 is the only small candidate; the system judges #22 itself
   `scope_too_large` for one continuous session.

**Owner unblock sequence** (each step is owner-only — credentials or live config):

1. Unlock the Mission Control vault.
2. Diagnose *why* the three profiles were disabled on 2026-07-18, then enable
   `reviewer-default`. This alone unblocks all ten scenarios.
3. Authorize the codex native login and enable `mc-native` (run 1 needs it; `codex-chatgpt`
   is already enabled and ready, which is run 2's agent).
4. Provide or scope a Ready Queue item small enough for one continuous session.

After steps 1–4 the run can be re-attempted with no code change.

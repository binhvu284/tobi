# Queue Delivery Log

Full delivery detail for every queue item, moved out of `QUEUE.md` so the queue stays
readable. Nothing was shortened or removed here — each section is the note that row carried,
verbatim. `QUEUE.md` links to these sections; this file is the evidence behind them.


<a id="item-35"></a>

## 35. TOBI Agent Tier Completion

`UPG-CORE-8D32H-012`

Owner approved the direction and requested the implementation plan on 2026-08-28. #35 completes
Tier II - Agent before TOBI begins Tier III - Operator. Agent means TOBI can repeatedly complete a
bounded task assigned by the owner; Operator later means TOBI can decide which work is worth doing.

The plan replaces the outdated static Tier II checklist with seven evidence-gated abilities and
qualifies five workflow families: Project execution, local file/Terminal diagnosis, Coding
maintenance, bounded Playwright browser work, and GitHub monitoring/action with Telegram delivery.
T00 freezes 30 cases including five holdouts and records an unchanged-code baseline before production
behavior changes. Final qualification requires at least 18/20 real Mission Control runs to complete
or recover as expected, evidence for every success claim, and zero critical safety, fabricated
success, secret-leak, or duplicate-external-effect failures.

On 2026-08-30, the owner approved T02A - Chat-to-Developer Dispatch as part of #35 Coding
maintenance. Normal Chat must be able to prepare a no-side-effect Developer proposal, request owner
confirmation, create exactly one durable queue item and workflow, show live status and approvals in
the reply, and expose generated files, images, plans, diffs, and test reports through a session
artifact menu. T02A reuses the current Developer control plane and remains inside the existing six
Coding maintenance cases and four real qualification runs.

#35 is Ready and unblocked after #34 reached owner-accepted Done status on 2026-08-30. T00 may start;
later packages remain gated by the plan's baseline and owner decisions. The item reuses Brain V2,
Runtime V2, Coding Agent V2, TOBIval,
Projects, Terminal, existing integrations, Telegram, Evolution, Agent timeline, and Runs. It does
not authorize Operator work, unrestricted browser/desktop control, autonomous publishing, spending,
deployment, merge, deletion, parallel multi-agent orchestration, Supabase, or Vercel interaction.

On 2026-08-30, the owner started T00 and clarified that the concurrent Developer changes belong to
the separate DeepSeek Harness agent package. T00 did not modify, stage, or test-fix that work. After
the separate agent committed and pushed it, T00 rebound its read-only source proof to the current
production revision `fc4d6d7`. Its baseline scope remains `committed_revision_only`, so no
uncommitted worktree content is included.

T00 now freezes seven ability contracts, five workflow-family manifests, 30 synthetic/redacted cases,
and five sealed holdouts. Dataset hash
`17dda4f32ee99105e9423df4895d075e4daff1dab50c18b02dbf915d7c6cf19c` and artifact SHA-256
`9cddb15ae19ce9cefddfcc8c2afefadc79986004e1553313493c92f3986d460d` bind the exact review
evidence. The unchanged-code qualification result is 0/7 active abilities, 0% frozen-case completion
or recovery, 0% interruption recovery, 0% evidence integrity, 0/20 real MC qualification, 17 explicit
blockers, and `release_ready=false`. The zero scores mean no #35 qualification run exists yet; they do
not erase the Runtime, tool, Developer, integration, or UI components already present.

The red-first target failed before implementation as required. After implementation,
`tests/test_agent_tier_baseline.py` passes 26/26 and the inherited #21/#34 gate passes 30/30. Health's
existing Infrastructure registry now includes the T00 proof so the owner button and release gate run
the same suites. Production Agent execution, Runtime routing, APIs, and dashboard behavior remained
unchanged during T00.

The owner accepted that exact T00 baseline on 2026-08-30. The separate acceptance record is bound to
production commit `fc4d6d7`, dataset hash `17dda4f3...`, and artifact SHA-256 `9cddb15a...`; changing
any of them invalidates acceptance instead of silently reusing it.

T01 is complete on 2026-08-31. A persisted Agent evidence registry now owns all seven Tier II ability
statuses across five workflow-family pillars. Evidence must be current, bounded, and tied to the
current release; missing, stale, revoked, malformed, or secret-like references fail closed. Evolution
reads that registry instead of the legacy static checklist and shows the evidence, freshness, missing
proof, and next action. The correct starting result is 0/7 until later #35 packages qualify real
workflows. The red-first target failed for the missing registry; afterward its 17 checks, the 31-suite
shared gate, dashboard build, and desktop/mobile owner flow pass. No external service, model call,
DeepSeek Harness file, or production workflow was used or changed in T01. T02 is next.

T02 is complete on 2026-09-01. Normal Mission Control Agent turns now qualify seven bounded local
workflows before the model loop: Project listing/task creation, local file listing/reading, Terminal
status/approved typed command, and read-only Coding workflow status. The accepted typed request and
run identity survive retry and reload; duplicate HTTP delivery creates no second run, user message,
reply, or side effect. Missing IDs, paths, or titles produce bounded clarification. Mutations pause on
the existing owner confirmation card, then resume the same canonical Runtime run with an immutable
receipt. Successful runs record only bounded current-release evidence, so code presence alone still
cannot increase Tier II. The scoped `agent.local_workflows` switch and #21 master rollback restore the
previous Agent path. T02 focused checks pass 20/20 and the shared gate passes 32/32. T02A Developer
dispatch, DeepSeek Harness, browser/external action, live model calls, Supabase, and Vercel were not
part of this package.

The owner's first production check on 2026-09-01 used `list all project`. It returned correct data but
did not prove T02: the live database showed legacy Agent run `156`, model `codex:gpt-5.6-sol`, 175
completion tokens, 15.2 seconds, no linked canonical response, and no matching `mc_runs` row. A
red-first repair now recognizes bounded `list/show` wording with optional `all/my/the` and singular or
plural `project`. The focused live-HTTP test uses the owner's exact phrase and proves one canonical
run, `model=not_used`, and duplicate-free replay. A restarted-server owner retest remains the final
live confirmation of this wording repair.

T02A is implemented on 2026-09-01 and remains inside #35 Coding maintenance. Explicit normal-Chat
requests such as `Use Developer to ...` and `/developer ...` now produce a durable, owner-readable
proposal containing the objective, project, acceptance checks, scope, and risk. Proposal creation has
zero queue, preflight, workflow, or worker side effects. Accepting the existing confirmation card
creates or reuses exactly one Developer queue item, runs preflight once, and starts one linked durable
workflow across retry, reconnect, and reload. Refusal creates no Developer work. Chat shows truthful
running, waiting, blocked, failed, canceled, and completed states; completion requires linked changed
files, passed checks, and generated evidence. The session artifact rail separates owner uploads from
Developer plans, diffs, checks, and files, and each run links to its exact Developer workflow. The
red-first checks failed before the dispatch module and HTTP branch existed; the focused contract now
passes 20/20 and the complete shared gate passes 33/33. The production dashboard build passes. A
mocked Playwright owner flow verifies proposal, Accept, live run status, generated artifacts, and
desktop/mobile layout with zero console errors, failed requests, or horizontal overflow. Owner live
verification remains before T02A is accepted. No DeepSeek Harness worker, browser/external action,
model call, Supabase, or Vercel path was changed or used.


<a id="item-34"></a>

## 34. TOBIval Operational Intelligence and Model Independence

`UPG-CORE-2D12H-011`

Owner approved the plan on 2026-08-25. T00 is active locally; production behavior has not changed.
#34 turns #21's Eval
case/run/finding and release-gate foundation into an executable local benchmark, then moves common
Mission Control routes, required fields, tool boundaries, typed arguments, evidence checks, and
bounded outcomes out of unverified model-only judgment. The release targets are Eval Completion
`>=90%`, LLM Dependency `<=50%` for a frozen supported-workflow manifest, `>=95%` reference-model
completion or structured recovery, and zero critical safety or duplicate-side-effect failures.

Truth comes before building: T00 freezes 72 total cases including 14 holdouts, formulas, supported scope, exact
strong/weak model IDs, spend cap, and fixture hashes, then records an unchanged-code baseline whose
target checks must fail before production behavior changes. The final acceptance independently
recomputes the same metrics from unchanged cases across strong, weak, and no-model lanes. Open-ended
coding, research, and writing are reported separately and cannot be hidden inside the `<=50%`
claim. Implementation waits for #33 to be committed and closed. #29 is absorbed into #34's recovery
and model-failure dataset and must not run as separate overlapping work.

T00 started locally on 2026-08-25 after commit `a317604` and the inherited 24/24 gate proved #33
green. The package adds no `core/`, `api/`, or `dashboard/` behavior. It freezes 72 synthetic cases
including 14 guarded holdouts, 21 supported workflows, the ECR/LDR formulas, source hashes, and a
dataset lock. The owner approved strong `codex:gpt-5.6-sol`, weak `codex:gpt-5.4-mini`, 168 bounded
calls, and `$0` direct spend through Codex subscription. The completed baseline is tied to production
commit `5ffa3d93`: ECR `50`, Unguarded Decision Share `100`, Quality Loss `42.3077`, final LLM
Dependency `85.5769`, strong reliability `44.8276%`, weak reliability `18.9655%`, no-model
reliability `0%`, and direct cost `$0`. It fails the intended ECR/LDR targets and proves the work is
needed. One weak-model response was structurally malformed and scored `0`; all other 167 probes were
scored. The owner accepted both immutable artifact hashes on 2026-08-25, closing T00 and allowing
T01 to begin.

T01 is green locally on 2026-08-25. `core/runtime/eval_dataset.py` loads the hash-verified 58-case
development set and keeps all 14 holdouts behind the final-acceptance purpose. The scorer registry
executes `structured_evidence` and inherited `evidence_ratio`, uses structured expected leaves, and
forces score `0` for missing, stale, unsafe, or unlinked evidence. `EvalRunner` requires a canonical
Runtime run and trace, stores only score, hashes, and bounded references in the existing immutable
Eval tables, makes exact replay idempotent, and rejects changed identities. Failed runs create one
bounded finding. ECR is derived from persisted proof rather than a percentage supplied by a caller.
The focused Gate passes `3/3`; contracts, event store, repository, Eval, Runs projection, and Runs UI
regressions pass `93/93`. No model, holdout, rollout flag, connector, API, or dashboard was used.

T02 is green locally on 2026-08-26. `core/runtime/workflows.py` verifies the accepted dataset hash
before loading all 21 versioned workflow definitions. It selects known intents without a model,
clarifies equal matches and missing required fields, reports unsupported open-ended work, and rejects
any proposed workflow or tool outside the selected allowlist. Additive adapters expose the selection
through the existing task classifier and Chat Runtime, while production `route_turn` remains unchanged
until T03 can resolve typed fields and identities. Canonical traces and Eval evidence now include
bounded workflow-version and selection-reason references. The focused Gate passes `3/3`; `156`
relevant workflow, Chat, Runtime, and TOBIval checks pass. The T00 unchanged-source sentinel remains
red by design because implementation source now differs from accepted production commit `5ffa3d93`.
No model, holdout, owner rollout flag, external service, API route, or dashboard was used.

T03 is green locally on 2026-08-26. `core/runtime/typed_resolution.py` performs read-only bounded
identity lookup against the existing `pm_projects`, `tasks`, and `pm_resources` tables. Exact IDs and
unique names become canonical integers; missing, invented, cross-project, or multiple matches cannot
produce a tool call and instead return at most five owner choices. `TypedRequestResolver` enforces the
T02 workflow/tool boundary, rejects unknown fields, validates types with the existing canonical JSON
Schema catalog, and stores accepted arguments as an immutable canonical JSON snapshot plus hash.
Equivalent name/ID proposals from reference and weaker model lanes produce the same contract hash.
Retries reconstruct the same validated call and idempotency key; the inherited executor proves the
mutation replays without a second effect. Trace payloads contain only typed-request, workflow, and
tool references. The focused Gate passes `3/3`; `90` relevant T01-T03, tool, trace, resource, and
idempotency checks pass. No model, holdout, production route, external service, or rollout flag was used.

T04 is green locally on 2026-08-26. `core/runtime/grounded_outcomes.py` turns typed results,
receipts, policy decisions, connector freshness, and recovery state into bounded owner-readable
outcomes without requiring a model. A reversible or terminal action cannot claim success without the
exact matching receipt and allowed tool. Structured model output gets at most one deterministic repair
and one configured escalation; unrecoverable output becomes an explicit bounded failure, while
provider transport failures keep their truthful provider classification. Outcome traces contain only
workflow, result, and evidence references. The focused Gate passes `3/3`; all `17` T04 checks plus
response-composer, provider-failure, action-receipt, policy, runner, and typed-resolution regressions
pass. Production Chat, Runtime flags, external services, and accepted baseline/holdout results remain
unchanged.

T05 is green locally on 2026-08-26. Runtime schema v14 adds immutable case-control, suite-run, and
finding-lifecycle records without prompt, response, tool-output, provider-error, or secret columns.
`LiveEvalService` runs only explicit manual suites or scheduled samples capped at five cases; holdouts
remain inaccessible and normal Chat/Conductor routes do not import it. The real runner now projects
typed evidence references that the gate can consume. `EvalRepository.gate` enforces each registered
case's capability scope and freshness window, uses the latest append-only finding status, and keeps
legacy unscoped #21 cases fail-closed. `RolloutController` checks the affected stage scope server-side.
The focused Gate passes `3/3`; `14` T05 checks plus `76` runner, rollout, Eval, security, and schema
checks pass. All Runtime execution flags remain off; no model, holdout, owner activation, external
service, Supabase, Vercel, or deployment was used.

T06 is green locally on 2026-08-26. The vault-protected Runtime Eval API projects current ECR,
truthful LDR availability, lane/category/workflow rates, scoped release gates, regressions, findings,
suite freshness, and bounded case evidence without private bodies. Mission Control exposes that
projection under Runs -> Evaluations with explicit loading, locked, unavailable, and missing-proof
states. Existing Runs details retain linked Eval results. The focused Gate passes `3/3`; `12` API
checks plus `28` inherited Runs and live-gate checks pass. The production dashboard build and
Playwright desktop/mobile checks pass with no overflow, console error, or failed request. No model,
holdout, Runtime flag, external service, Supabase, Vercel, or deployment was used. T07 final
acceptance is next.

T07 is technically green and waiting for owner dashboard acceptance on 2026-08-26. The final runner
executes all `72` frozen cases in strong, weak, and no-model compatibility lanes without changing a
fixture, threshold, formula, model ID, or holdout. It made `156` bounded calls against the approved
Codex subscription models, below the `168` ceiling, used `44,354` measured tokens, cost `$0` direct,
and completed in `484.594` seconds. Raw strong output averaged `0.5513` and required `48` bounded
recoveries; raw weak output averaged `0.4231` and required `60`, while both final lane completion
rates reached `100%`. ECR is `100`, LDR is `2.0312`, all `14/14` holdouts pass, and critical safety,
fabricated-success, and duplicate-mutation failures remain zero. The private Evaluations page loads
this bounded artifact, shows the result on desktop/mobile, and blocks release only with
`owner-acceptance-required`. The inherited gate passes `25/25`; production build and Playwright pass
with no overflow, console error, or failed request. At that stage, #34 was not Done until the owner
accepted the corrected view.

T08 truth repair is committed and pushed in `d426619` and `685a1a8` on 2026-08-28 after owner
review found that T07's synthetic compatibility harness did not prove canonical production execution
or live model independence. `CanonicalEvalExecutor` now sends every frozen case through a real
Runtime lifecycle and records bounded run/trace IDs plus route, context, validation, execution, and
final-outcome decision provenance. The final report is schema v2 with
`evidence_scope=canonical_runtime`; legacy v1 synthetic artifacts are quarantined. Raw model
responses, raw pass rate, provider failures, and deterministic recovery are reported separately.

The committed bounded artifact runs all `72` cases and `14` holdouts, reports ECR `100` and
scoped LDR `8.8021`, and records `156` recoveries. It also records `0` live model responses and
`156` provider failures, so release correctly remains blocked by
`model-quality-proof-missing`. Health and the release gate share the same `29` suites, all green,
and the dashboard production build passes. Production `route_turn` now uses the frozen workflow
boundary only for narrow safe routes with no required fields; broader typed resolution and grounded
outcomes are not claimed as active in normal Chat/Agent execution. The remaining work is an
explicitly approved 156-call live rerun followed by owner dashboard acceptance.

The owner approved that rerun on 2026-08-28. Against source `d1a3448`, all 156 approved Codex
subscription calls returned: 78 strong and 78 weak. Raw model output passed `32.0513%`; bounded
deterministic recovery handled `67.9487%`, producing final ECR `100`, scoped LDR `8.8021`, and
14/14 holdouts passed. There were no provider failures, no artifact blocker, no direct spend, and
`release_ready=true`. The owner CLI now defaults to a revision-bound D-drive database and the final
artifact path, avoiding the earlier home-directory SQLite failure. Mission Control shows the live
proof in plain language and Playwright passes on desktop/mobile with no overflow, console error, or
failed request. At that stage, #34 remained In progress only for owner dashboard acceptance;
production routing was still intentionally narrow.

The owner accepted the corrected Evaluations result on 2026-08-30. Acceptance is bound to SHA-256
`c9ecf8d93bfa460df562f51b2f3bd12f582d799fb917200379868bc43f097810`, the exact canonical
final-acceptance artifact reviewed by the owner. Mission Control opens the release gate only while
that artifact remains unchanged. #34 is Done and #35 is unblocked; production routing remains
intentionally narrow as recorded above.


<a id="item-32"></a>

## 32. Health checks run together

`UPG-CORE-3H-010`

Spec written 2026-08-13, awaiting owner approval. No implementation yet.

<a id="item-31"></a>

## 31. Pages tell you when they fail to load

`FIX-CORE-8H-002`

Spec written 2026-08-12, awaiting owner approval. No implementation yet.

<a id="item-30"></a>

## 30. Chat self-check

`CHECK-CHAT-2H-006`

The Health page's deep check reported the AI healthy on 2026-08-01 while every Chat request failed, because it sends one message and the defect only appeared on the second. Replaces that one-shot probe with a bounded real conversation that uses one read-only tool, on the streaming path with the route's own token budgets - the exact path the shipped `input_text` defect lived in. Reports Chat working, Chat broken with the provider's real error text (redacted), or model unavailable. No new setting, flag, or credential; works with whichever model is selected. Guarded by `tests/test_chat_self_check.py`, which must fail against current `main` first and must report broken when the `_to_input` role tagging is reverted. Four files only: `core/chat_self_check.py` (new), `api/routers/health.py`, `dashboard/src/pages/Health.tsx`, and the test. Deliberately touches nothing owned by #21 T07 (`core/runtime/*`, `core/schema/runtime.py`), T08 (`core/conductor.py`), or T13 (Runs page).


<a id="item-29"></a>

## 29. Fallback recovery test

`CHECK-DEV-8H-005`

Created in Developer Work.

Owner-approved #34 planning absorbs this draft into its frozen recovery, provider-failure, and
idempotency case matrix. Preserve this entry as history, but do not implement #29 independently.


<a id="item-28"></a>

## 28. Coding Agent V2 OpenCode acceptance fixture

`CHECK-DEV-3H-004`

The final supported-scope Codex attempt used the independent reviewer, passed every stage without retries or tool failures, and merged through PR #5. The failed OpenCode attempt remains historical evidence; OpenCode is locked for future development under the Codex-only V2 rollout.


<a id="item-27"></a>

## 27. Coding Agent V2 MC Native acceptance fixture

`CHECK-DEV-3H-003`

Isolated documentation-only run for matrix scenario 1. Run after the final qualification patch is active; do not run in parallel with #28 because Developer permits one foreground workflow.


<a id="item-26"></a>

## 26. Regression suite for the chat task classifier

`CHECK-CHAT-3H-002`

Coding run #16 delivered `tests/test_task_classifier.py` in PR #3. Final qualification reconciliation records the merged SHA, closes stale attempts, restores committed-file evidence, creates the scorecard, and keeps the Queue item Done.


<a id="item-25"></a>

## 25. Awakening external read requires verified test evidence

`FIX-SKILL-3H-001`

Written by coding run 15 (Codex) — the first run to execute the check its own acceptance criteria named, and the first to pass all seven policy-permitted gates. `_connector_states` now requires connector readiness **and** fresh successful vault test evidence before reporting a read connector as verified; a present token that is dummy, expired, revoked, or merely untested reports `partial`, enforcing CLAUDE.md's "configured credentials are not proof" rule at the point it is evaluated rather than only asserting it in prose. Freshness reuses the existing 24h `AWAKENING_CONNECTOR_TTL_HOURS` window. Verified independently of the run: `tests/test_awakening.py` 73 checks green, `test_awakening_route` green, and a direct four-case probe (untested / fresh / stale / failed) returns the intended classification. **Post-delivery restart fix (2026-08-30):** both full `tobi start` and API-only MC startup now reuse fresh GitHub proof or automatically verify stale proof from the already-saved vault credential before the dashboard is served. The 24-hour truth gate remains intact, but the owner no longer has to open Integrations, press GitHub Test, and refresh Evolution after each restart. Focused gate: Awakening 78/78, Awakening routes 10/10, integration reasons 6/6.


<a id="item-24"></a>

## 24. testing

`CHECK-DEV-8H-001`

Created in Developer Work.


<a id="item-23"></a>

## 23. News Page V2

`UPG-NEWS-3D-009`

Four-tab evidence-backed News system with ranked models, GitHub/tools discovery, virtualized personalized feed, Favorites, durable refresh jobs, transparent learning, and V1 rollback. Shipped: N01 `core/news/` contracts + 12-table ledger schema, idempotent V1 copy, retention/cursor/interaction primitives, `news.v2_enabled` flag (off), 46-check suite; N02 bounded adapter framework (retry/rate-limit/redaction/partial-failure isolation) + HN/OpenRouter/GitHub adapters + canonical normalizer ingest, 34-check stubbed-HTTP suite; N03 durable refresh engine (per-tab lease join, per-source checkpoints + resume, cancel/retry-failed, owner schedules, `news.v2_shadow`-gated hourly+nightly scheduler jobs), 25-check suite; N04 interactions + learning (replay-safe like/dislike with exact 10s undo ledger, favorite/note retention protection, meaningful-dwell aggregation, versioned interest profiles w/ committed-dislike semantics, bounded immediate modifier, ±5 context cap w/ direct-action precedence, deterministic Why-shown reasons), 35-check suite; N05 versioned rank snapshots (Top-10 model formula w/ fresh-evidence + 2-family eligibility and within-source normalization, honest snapshot-only GitHub growth w/ collecting state, 55/25/10/10 feed formula w/ diversity constraints + immediate dislike hiding, per-tab rebuild wired into refresh, per-kind snapshot pruning), 26-check suite; N06 `/api/explore/v2` surface (flag-gated 503, snapshot reads w/ pinned cursors + 15-40 clamp, Idempotency-Key + optimistic-version mutations w/ replay short-circuit, refresh start/join/commands + SSE, settings, safe media route, legacy /api/explore/* retained), 46-check suite; N07 V2 shell (four tabs, freshness/source-health chips, per-tab refresh w/ job polling, ungated /config flag switch in News.tsx — V1 untouched and default) + N08 Home (Top-10 rank hierarchy via theme-token-mapped news vars w/ motion-safe pulse, Latest Releases always sourced+timed, full-screen keyset-paginated Model Explorer); N09 Trending (GitHub growth table w/ honest Collecting-history chips — growth only from persisted snapshots, week/month/all windows, top-3 rank ladder; featured Tool Discovery + alternatives; Source Explore projection w/ per-source latest items); N10 Feed + Favorites (@tanstack/react-virtual windowed feed against the workspace scroller w/ pinned-cursor infinite scroll, For You|Latest modes, source filter, non-jumping 'N new posts' banner activated only by the owner, shared NewsCard w/ like/dislike + inline 10s undo countdown, favorite, private notes editor, deterministic Why-shown reasons, open/bounded-dwell events fire-and-forget once per item, media from validated cache w/ reserved aspect; desktop sticky rail w/ transparent 'What TOBI learned' profile + mobile bottom-sheet drawer; Favorites reuses the renderer, server-side source/note filters + client-side search, note editing, never auto-refreshes); N12 rollout gates (43-check security/perf/telemetry suite: script/data/file URLs rejected at the contract, injection text inert, media route serves validated cache only w/ zero proxy capability, cursor tampering 422, secrets redacted end-to-end into alerts; 10k-item corpus meets every plan-§9 gate — rebuild 0.13s w/ FEED_CANDIDATE_CAP=500 bounded snapshots, page read 2ms, /feed 22ms, interaction 13ms, refresh ack 16ms, retention 0.02s; repeated source failures now raise ONE deduplicated Inbox task via core/news/telemetry.py). OWNER-SIDE GATES before flag flip (plan §11/§12): visual QA across themes/motion modes, 20-item evidence review (≥80% trustworthy, ≥70% relevant, zero fabricated), 7 consecutive clean local refresh runs in shadow. Runbook: 1) set news.v2_shadow=1 + restart MC → background collection while V1 stays live; 2) after gates, news.v2_enabled=1 → V2 UI; rollback = flip the flag off (V1 routes/data intact, no down-migration). Deferred: N11 Brain adapter (#20 acceptance; save-to-brain=501), media fetch pipeline (cards render media only from a validated cache row; populating the cache is future work).


<a id="item-22"></a>

## 22. TOBI Coding Agent V2

`UPG-DEV-3D-008`

Bounded Codex development with an independent reviewer is qualified. Same-run recovery, queue safety, validation, review, delivery synchronization, active-time tracking, and History evidence passed local regression. MC Native, OpenCode, and Claude Code remain locked for future qualification. This does not qualify the Developer runtime to execute #21 as one large job.


<a id="item-33"></a>

## 33. One-click infrastructure test

`CHECK-CORE-4H-007`

Delivered in `a317604` on 2026-08-25. The inherited package gate then passed 24/24, including the
infrastructure self-check and process-window regression suites.
Health gains an **Infrastructure** tab with one button. It runs twelve
read-only checks of the running server — which database file is open, whether this process can
reach the internet at all, whether every canonical table and migration is present, what the
rollout switches say, whether the vault is loaded, whether a failing model has a fallback — and
then every #21 acceptance suite, each as its own process against its own throwaway database.
Twenty-three suites, 362 individual proofs, about 55 seconds, streamed row by row.

The button and the release gate read one list, and `tests/test_infrastructure_self_check.py`
fails if they ever differ, so a green page and a green gate cannot come to mean different things.
Suite output is redacted before it reaches the page, and a failed suite is re-run once before it
is believed — three of them start real worker processes, and a health light that goes red for a
lost race is worse than no light.

**Local follow-up, observed 2026-08-25 - the button flashed console windows, and it was never only
the button.**
TOBI runs as a background server, so when it starts a child process Windows has no console to lend
it and creates a new one: a black window that appears, steals focus for a moment, and vanishes. The
infrastructure test starts 23 children in a row, which turned a quiet long-standing defect into an
obvious one. Twenty call sites did it — `git rev-parse` on every health check, `tasklist` on
startup, the Hermes worker, the cloudflared tunnel, the terminal engine, the coding tools — while
four others already passed `CREATE_NO_WINDOW`, which is how a rule that lives only in reviewers'
heads ends up half-applied. `core/proc.no_window()` is now the one spelling, every server-side
spawn passes it, and `tests/test_no_console_windows.py` reads the syntax tree and fails if a call
site forgets. The Hermes worker keeps its own process group and gains the flag rather than
swapping one for the other.

**Architecture page updated for the new engine, 2026-08-21.** `overall-tobi` now shows every
surface converging on the runtime rather than on the Conductor; `mission-control` gains the Runs
pane, the shared runtime store and the Health infrastructure panel; and a third diagram,
**Mission Control Runtime**, follows one request from the surface it arrived on to the receipt it
leaves behind — identity, durable steps, policy, catalog, receipts, history, projections, traces,
rollout, and the shadow path it is compared against. Every node in the new diagram has guide notes.
The two architecture suites no longer pin a diagram count; they derive it from the allowlist and
additionally require each registered diagram to exist on disk and pass the validator.

Its first run found a real defect. `schema_migrations` is created by two modules with different
definitions; Chat's runtime got there first on the owner's database, so its `applied_at NOT NULL`
with no default was in force, and the runtime's `INSERT OR IGNORE ... (version)` violated it —
silently, because `OR IGNORE` swallows constraint violations. The ledger stayed empty,
`_schema_is_ready()` answered False forever, and the entire runtime schema was re-applied at all
62 of its call sites on every runtime database operation. Fixed by writing `applied_at` explicitly
and aligning both definitions; the live database repaired itself on the next restart, recording
all 13 versions. The committed package is now recorded as Done; Runtime rollout flags remain off.

<a id="item-21"></a>

## 21. Mission Control Infrastructure V2

`FOUND_BASE-CORE-5D20H-002`

T08 is complete at `5b0a19a`; T09 at `34c4b1d` and `0f2a3e2`; T10 Runs 1-2 at `3ff2edd` and `6db02df`. T10 Run 3 is complete locally: each accepted #22 coding session creates or reuses one deterministic canonical run and mirrors ordered lifecycle, checkpoint, evidence, failure, completion, and owner-command references. Duplicate delivery does not duplicate history, changed content fails closed, and raw prompts, credentials, diffs, evidence bodies, and worker output never enter canonical history. Adapter failure keeps the complete Developer record authoritative. The focused gate passed 10/10; 72 current Developer and 121 Runtime/state checks also passed. One historical all-in-one check still expects Queue #18 to depend on #17, but the current Queue truthfully says #18 is superseded by #22 and declares no such dependency. T11 trace and evaluation gates are active.

T11 is complete locally. A deterministic trace now joins only bounded context, model, tool, policy, approval, receipt, recovery, usage, and outcome references from canonical history. Three additive append-only local evaluation tables store versioned cases by fixture hash, immutable result references, and findings. Eight required TOBIval categories are seeded, and release or autonomy increases fail closed on missing, failed, incomplete, below-threshold, or unsafe evidence. The enforced 19/19 gate and 76 Runtime regression checks passed. T11A is active.

T11A is complete locally. `SystemModelRepository` validates all typed T01 System entities, requires source evidence, rejects dangling or evidence-free relationships, gives read-only filtered entity/edge/snapshot queries, and prevents connected-entity deletion. Stable version identities replay exactly and changed content conflicts. The derived current rows rebuild deterministically from T02 append-only history, while the module has no execution authority. The enforced 11/11 gate and 45 contract/event/evaluation regressions passed. T12 is active.

T12 is complete locally. The documented threat matrix covers prompt injection, secret leakage, authority over-reach, budget exhaustion, network SSRF, path traversal, supply-chain metadata, and fail-closed recovery. Synthetic probes exercise the accepted control owners and project unsafe outcomes into T11 as a high-severity finding that blocks release and autonomy. The red run found that embedded `token=...` text was not redacted; the shared event-store redactor now masks it before persistence. The enforced 13/13 gate and 150 policy, event, network, registry, budget, memory, file, terminal, and evaluation regressions passed. T13 is active.

T13 is complete locally. The Runs page and Developer loop selector consume one shared reconnectable store backed by bounded, redacted runtime projections. Run detail joins ordered events, traces, evaluations, context references, capabilities, loop state, and recovery without prompt, request, tool-output, secret, or raw-error bodies. Loop selection persists as configuration and cannot activate execution. The focused backend and frontend checks passed 23/23, the production dashboard built, and desktop/mobile Playwright checks passed with no overflow or console errors. T14 is active.

T14 is complete at `ba4ceb8`. Immutable comparisons retain only route, manifest hash, policy, outcome, latency, and evidence references. Each ordered stage requires seven consecutive matches plus the T11 release gate; Agent also requires the autonomy gate. Stages cannot skip or move backward, controls default off, and owner-authenticated commands activate, roll back, or resume. One master rollback returns new work to shadow mode while preserving the approved stage and all comparison history. Seven consecutive final local runs, the 23-check gate, T04 live activation, T12 security, T13 Runs, and compile regressions passed.

T15 and Queue #21 are complete. Projects and Office use one passive HTTP boundary; CLI, Telegram, and all 18 scheduler callbacks use the same fail-open compatibility adapter. When event mirroring is enabled, each accepted request records only bounded surface, operation, status, and evidence references in one disabled canonical run; request and response bodies are never read. Adapter failures cannot interrupt legacy work, duplicate delivery reuses the run, and the first terminal outcome remains authoritative. Runtime operations, architecture, security, verification, and legacy-exit docs now describe the delivered system. The focused adapter gate passed 17/17; the final cross-package gate covers every T01-T15 boundary. All real owner rollout controls remain off, and legacy deletion is deferred to a separate owner-approved Queue item.

**Owner test, 2026-08-20 — three defects found and fixed.** The owner's main-gate run stopped at T3,
with Chat answering every message "the current model is struggling — switch to a stronger model".
The model was never contacted: Mission Control had been started inside an agent sandbox with no
outbound network, so every provider call raised a connection error, every integration test failed,
and the isolated test gate on `8181` had also created a fresh empty database instead of opening the
copied one. Fixed: (1) `core/runtime/transport_failure.py` classifies a failed provider call into one
bounded code and owns its owner-facing sentence, `generate_step` stamps it on the client, and both
failure paths — the tool loop's give-up branch and the composer's exhausted escalation — now say the
model was never reached instead of blaming its output; the Chat card drops the model picker for that
case, since switching models cannot fix a connection. (2) Failed provider calls no longer log the
provider's error body, which can carry the request URL and Authorization header. (3) A vault
auto-unlock that cannot unwrap its saved key now logs why, and the deep health check says
"vault locked — the saved key was not loaded" instead of the untrue "not configured". Two unguarded
buttons on the Runs page gained the required pending state. Gate 21/21. Main gate T1-T4 and the
isolated gate T5 verified after the fix.


<a id="item-20"></a>

## 20. Brain Context & Architecture V2

`UPG-BRAIN-3D-007`

Stable legacy Brain UI now runs on V2; Remember, sweep, Chat/Agent context, Conductor, and MCP recall use V2 when enabled. Live cutover reconciled 11 rows: 63 active match legacy, 0 missing links, 0 lifecycle mismatches. Rollback/restore, 501 backend checks, and dashboard build passed. [Operations evidence](../BRAIN_V2_OPERATIONS.md).


<a id="item-19"></a>

## 19. Performance "System Doctor"

`NEW-CORE-8H-003`

**Built this session (15-question intake, all locked).** A **graphify-first** system-doctor so every run is cheap. **`core/performance_doctor.py`:** loads `graphify-out/graph.json` as the MAP (nodes→`source_file`/community; links→import fan-in/fan-out → god-modules), reads source only to count **LOC** (I/O, no tokens), and derives per-file size/coupling/TODO metrics → grades **feature-area subsystems** (Brain · Graph · Conductor & Chat · Terminal · Projects · Integrations & MCP · Explore · Storage & Usage · API · Frontend) on a transparent 0–100 rubric + overall LOC-weighted score; ranked **file/function-level findings** (severity × effort); **runtime** signals folded in from `usage_meter`/`storage_scan` (defensive); reports **graph staleness** (`built_at_commit` vs HEAD) as a finding. **Quick** = graph+metrics (~free, ~280ms); **Deep** = one strict-budget LLM diagnosis over the computed summaries (never raw code; `set_usage_context("health","performance")`). Persists **`performance_snapshots`** → score **trend**; `latest()` rehydrates. **API:** `GET /api/health/performance` (latest+trend), `POST /api/health/performance/run` (`{depth}`), `POST /api/health/performance/finding/task` (find-or-create a "TOBI Maintenance" project → #7 `create_task`). **Conductor read tool `analyze_performance`** (Quick run or report latest → grounded scorecard) so chat can answer "do we need a refactor, sir?". **Frontend:** a **Performance tab** in Health (`components/PerformanceDoctor.tsx`) — animated **score gauge**, subsystem grade cards, ranked findings with **+Task**, TOBI diagnosis, trend sparkline, Quick/Deep toggle, and a smooth **"running diagnostics"** sweep (cycling phases + radar-scan placeholders, reduced-motion aware). **First real run on this repo:** overall **C- (71)** — flags `api/dashboard.py` (~6.3k LOC), `core/conductor.py` (~2.6k), `dashboard/src/api.ts` (~1.8k) as high-severity splits; weakest **Frontend (F)**, strongest **Storage & Usage (A)**; graph 68 commits stale. **Tests:** `tests/test_performance_doctor.py` **21/21** (scorecard, subsystem grading, findings ranking, staleness, snapshot+trend+latest, Deep synthesis stubbed, graph-missing degradation); `tsc` + `vite build` clean.


<a id="item-18"></a>

## 18. TOBI Coding Agent / Controlled Self-Development System

`FOUND-DEV-3D-009`

Prerequisite #17 accepted. Durable goal/iteration/lease loop, brokered Ollama/current-model fallback worker, typed tools, independent fail-closed review, restart reconciliation, exact-SHA deployment/rollback, Goals UI/API/CLI, and production invariant suite delivered. Sandbox goals run continuously to `qualified_local`; GitHub/merge/deploy remain owner-gated. Complete the documented VPS/model burn-in before calling the live service production-proven or starting #20.


<a id="item-17"></a>

## 17. Awakening Tier 1 Completion

`UPG-SKILL-1D8H-006`

**Final Codex qualification fix (2026-07-13; review findings closed):** External Read now requires connector readiness plus fresh successful-test evidence (24-hour default); Google client credentials remain `partial` until OAuth and a verified read test complete; secret rotation/import clears stale evidence. Brain sweep now uses unique owner-token leases with conditional renew/release, fair per-chat selection, persisted deferred batches with bounded exponential retry, malformed-output recovery, and raw-payload cleanup after resolution, so repeated provider failures no longer discard owner memory. **Verified:** Awakening `73/73`, Awakening routes `10/10`, conductor guard `9/9`, mode enforcement `18/18`, chat modes `76/76`, premium readers `72/72` plus routes `16/16`, net guard `25/25`, chat runtime unit+route, performance doctor `21/21`, and Storage `32/32`. — **Second Codex review follow-up (87% → the two remaining P1s fixed):** (1) **Connector honesty — verified, not merely present**: External Read is now `active` only from **cached successful-test evidence** (vault `test_status='ok'` + `last_tested_at`, written by the Integrations Test/connect flow), `partial` when configured-but-unverified, `setup_needed` otherwise — so an expired/revoked/invalid or merely-present credential can no longer produce a false 100% (`core/awakening._connector_states`). (2) **Sweep starvation/replay fixed**: `brain.sweep_once` now uses **per-chat cursors** (`brain_sweep_cursors`) so one chat's failure can't block or force reprocessing of the others, a **poison batch is skipped after 3 tries** so it can't starve its own chat forever, and serialization moved to a **DB-backed lease** (`brain_sweep_lease`, reclaimable after a crash) instead of an in-process lock. (3) **Persona + receipt proven end-to-end**: a test drives a real `summarize_repo` through `conductor.answer()` and asserts a `tobi_actions` receipt is written **and** the action-turn system prompt carries the butler persona. `tests/test_awakening.py` **59/59**; regressions green. — *(first review follow-up below)* **Codex review follow-up (74% → hardened):** (1) **Connector states distinguished** — External Read now uses each integration's own readiness (`is_connected` for Google = completed OAuth; `is_available` for GitHub/Notion = token present), so a configured-but-unauthorized connector no longer reports active (kills a false 100%). (2) **Simple Automation gated on receipts** — active only after each of the 3 workflows has a successful `tobi_actions` receipt (not mere tool registration); `summarize_repo` (a read tool) is now audited to Actions, and a receipt counts as executed only when the read genuinely succeeded (`available` + no error) — so an unavailable/error run never fakes success. (3) **Brain sweep failed-gap fixed** — `sweep_once` no longer advances the high-water mark past a failed batch (a later session's success can't drag the cursor past an earlier transient LLM failure), and is now **serialized by a process lock** so concurrent sweeps (chat/Brain/Conductor/scheduler/manual) can't double-extract or race the cursor. (4) **Persona checked behaviorally** — evidence + test now verify the SAME butler persona anchors the MC and Telegram system prompts, not just `_BUTLER` length. `tests/test_awakening.py` **54/54** (adds connector-state, receipt-gating, failed/unavailable-workflow, failure-gap, concurrent-sweep, and cross-surface persona checks); regressions green. — *(v1 below)* **Built this session (gap-fill, all 14 locked decisions; owner calls: guided completion panel · automations chat/TOBI-only · one release).** **Single source of truth = `core/awakening.py`** — an evidence detector (never raises) that inspects real Brain / Conductor / Integrations / Tasks state and returns the **9 Tier-1 abilities** in 3 categories (Persistent Memory: owner_profile/conversation/preference memory · Identity & Personality: consistent_persona/contextual_self_awareness/evolution_tracking · Basic Real-World Action: internal_task_management/external_read_access/simple_automation), each `active\|partial\|setup_needed\|inactive` with evidence[], missing[], and setup deep-links. **Only `active` counts → Tier 1 hits 100% only on real evidence, never hardcoded.** Memory abilities read existing `brain_memories` (active only; source distinguishes conversation-derived; **sensitive-category memories stay `pending` until the owner reviews**, so they never auto-activate). Connectors count as configured from credential presence (no live network probe; no Supabase/Vercel calls). **Evolution API:** `/api/evolution` special-cases Tier 1 to the registry (4-valued status + `pillar_labels`), persists the 4-valued snapshot; new **`GET /api/awakening`** (single source for the guided panel + Ability mirror). **Conductor (+5 tools, audited):** read `awakening_status` (grounds "what tier am I / what's missing"), `summarize_repo` (untrusted repo bundle); act `update_task` (medium — the missing CRUD verb), `save_note` (low), `create_task_from_conversation` (low). **Frontend:** Evolution page — 4-valued ability cards (status badge + evidence + missing + setup buttons), per-tier category labels, and a **"Complete Awakening" guided panel** (9-ability checklist + inline setup deep-links + progress); Ability page — a compact Awakening **mirror** reading `/api/awakening` (incl. a sensitive-review nudge). **Tests:** `tests/test_awakening.py` **46/46** (registry shape/9 ids/3 categories; each status reachable; structural+tool abilities activate from real registration; memory abilities activate from seeded Brain data; missing connector → setup_needed not failure; sensitive pending not counted; **progress=100 only when all 9 active**; full task CRUD incl. update_task with delete gated high-risk; the 3 workflows; awakening_status grounded; shared persona). Regressions green (conductor_final_guard 9, mode_enforcement 18, chat_modes 76, performance_doctor 21, premium_readers 72/route 16, net_guard 25, chat_runtime); `tsc` + `vite build` clean. On a fresh/unconfigured system it honestly shows 5/9 (the 4 data-dependent abilities need owner memories + a read connector). Legacy `_TIER_DEFINITIONS[1]` kept intact (rollback = drop the Tier-1 override + unregister the 5 tools; data preserved). — *(original intent)* Gap-fill release to make Tier 1 Awakening reach 100% in Evolution from real evidence; reuse Brain, Conductor, Actions, Integrations, Tasks; no unsafe full-terminal/desktop control (Agent-tier).


<a id="item-16"></a>

## 16. Chat Mode Backend Upgrade

`UPG-CHAT-3D-005`

**Review 2026-07-12 (70% → hardened) follow-up shipped:** the two **High** findings that blocked qualification are fixed. (1) **Mode = a REAL capability boundary, not just prompting** [D11][D23] — `chat_modes.denied_tools_for(ctx)` (Chat denies the whole terminal surface: `run_command`/`install_package`/`configure_tool`/`connect_tool`/`kill_job`/`set_terminal_mode`; Agent denies nothing) is threaded into `conductor.answer(denied_tools=…)`: denied tools are **not advertised** (the TERMINAL system-prompt section is dropped and replaced with a "not available in this mode" line, and denied ACT tools are filtered from the catalog) **and rejected server-side** in the tool loop even if the model calls them anyway (the terminal engine is never reached) — so Chat genuinely cannot run a shell. (2) **Deep Research SSRF closed** — new `core/net_guard.py` (scheme allowlist; resolve host and reject private/loopback/link-local/reserved/multicast/metadata IPs incl. `localhost` and obfuscated decimal IPs; **manual redirect following that re-validates every hop**; body size cap); `pm_resources.fetch_readable` now fetches through `net_guard.safe_get`, so DR (and project-resource link ingestion) can no longer be steered at `169.254.169.254`/RFC1918/loopback. **Mediums also addressed:** (3) **DR source isolation** — `_evidence_block` fences each source (`<<<SOURCE n \| title=… \| url=…>>>` … `<<<END SOURCE n>>>`) with attribution OUTSIDE the content, and the synthesis prompt marks sources UNTRUSTED and forbids following instructions inside them (mirrors #14). (4) **Human Review backend-authoritative** — `review_mode` is passed into `conductor.answer`; **`always`** proposes EVERY acting tool for confirmation (never auto-runs low/medium acts) so the client can't self-approve the policy. **Tests:** new `tests/test_mode_enforcement.py` **12** (deny policy, prompt advertises terminal only when allowed, server-side rejection w/ engine-never-invoked, `always` proposes-not-runs) + `tests/test_net_guard.py` **20** (scheme/loopback/private/link-local/metadata/decimal-IP rejection, public pass, redirect-to-private blocked, size cap) + `test_chat_modes.py` **66→71** (DR source-isolation fencing). Regressions green: premium_readers 72, premium_readers_route 16, conductor_final_guard 9, terminal 67, storage 32. **Open UX follow-ups (Medium, frontend — not yet done):** (a) **Retry/Skip/Revise** still starts a fresh NL turn rather than resuming the persisted `waiting_user` run (needs run-continuation endpoints + transitions carrying the original run/step id); (b) **artifact chips** render from live turn state but don't yet re-resolve stored `artifact_ids` on reload or open the artifact (fetch APIs exist, Chat.tsx not wired). — *(v1 build below)* **Built this session (all 30 locked decisions; owner calls: flag ON by default · timeline reuses ProcessTrace · standard DR budget).** Modes are now a **backend contract**, not labels [D1][D4]. **`core/chat_modes.py` (new):** `normalize()` (legacy map: terminal→agent+terminal_intent, research→chat+web, project→chat, unknown→chat [D27]) · `build_directives()` (single directive composer — chat-mode output line-identical to legacy; agent plan-then-act + terminal-intent lines) · `extra_tools_for()` · **`chat.mode_v2` owner_settings flag, default ON** [D29] (`GET/POST /api/chat/config`; off = byte-identical legacy route, old 5-mode UI) · `detect_project_context()` (word-boundary match vs `pm_projects`, longest-first with span consumption, `#id` pattern; 1 match → `project_overview` + top-3 resource snippets, 2+ → shallow disambiguation line + chips only, guards + try/except-total) [D19]. **Conductor diff = 3 additions only:** `tool_outline_plan` in OPTIONAL_TOOLS (advertised solely via extra_tools → Telegram untouched), one loop special-case emitting `{"type":"plan",steps}` events, `_TOOL_PHASE` entry — a prose plan would end the turn, so the plan rides the tool protocol [D9]. **Route (`chat_session_stream`):** `ChatSendReq` += `mode/deep_research/review_mode` (old clients → chat); ordering = YouTube reader → project context (`context` SSE chips [D20]) → **Deep Research branch** → vision → tool loop; new SSE events **`mode`** (first frame), **`plan`**, **`context`**, **`artifact`**, notice `run_paused` [D10] + `dr_images_skipped`. **`core/deep_research.py` (new) [D14][D15]:** plan ≤5 queries (LLM) → `tavily_search` (≤10 unique sources) → `fetch_readable` top-3 → synthesis into summary/key-findings/evidence/caveats/next-questions ending in a ```tobi:reference``` block of **exactly the retrieved sources**; honest no-key caveat (checks TAVILY_API_KEY itself); usage-logged `chat/deep_research`; one-shot toggle resets after Send, regenerate replays from opts. **`core/agent_runs.py` (new) [D8]:** `agent_runs`+`agent_run_steps` (statuses incl. `waiting_user`/`waiting_approval`), steps recorded live from the SSE consumer (interrupt-safe), `GET /api/chat/sessions/{sid}/runs` + `/api/chat/runs/{id}`. **Artifacts [D21]:** `chat_artifacts` in chat_store + `add/list/get`, `task_result` **only when the run acted** (≥1 act tool), `research_report` for DR, endpoints + SSE. **`chat_messages.meta` column** (additive; carried through add/get/fork/compact — the 4 sites) persists mode/steps/tools/chips/run_id/artifact_ids → **finished traces + chips now survive reload**. **Frontend:** selector = **Chat/Agent** [D23] (legacy 5 behind flag; localStorage migration terminal→agent, research/project→chat [spec §15]); mobile bottom-sheet mode menu [D25]; `+` menu **Deep Research** toggle + quick "Deep" button [D24]; slash: `/chat` added, `/terminal`→Agent+toast, `/research`→DR arm, `/project` retired; `baseOpts()` keeps mode on branch/starter/picker continuations; plan → numbered checkpoints in the **ProcessTrace orb timeline** [D7]; **TurnChips** (Agent chip · `Project: name` links · resources count · artifact pills); **run_paused → Retry/Skip/Revise** card [D10]; TerminalMode console appears in Agent mode when a command produces output [D13]. **Verified:** `tests/test_chat_modes.py` **66/66** (normalizer matrix, flag, directives, outline_plan + Telegram guard, meta incl. fork/compact carry, runs/steps, artifacts, DR stubbed incl. no-key + failure paths, context detection incl. span-consumption fix); regressions green (#14 58, #11 67, #10 32); **live SSE smoke over the real route**: mode-first frame → plan event → tool steps → task_result artifact → run `done` + meta round-trip + flag-off legacy passthrough; `tsc` + `vite build` clean. **V1 limits (documented):** `confirm_action` doesn't back-propagate into a `waiting_approval` run's status; planning consumes one of MAX_TOOL_STEPS=8; DR skips images.


<a id="item-15"></a>

## 15. Office V3

`UPG-OFFICE-1D8H-004`

Flagged `/office` replacement shipped: premium full-floor Phaser command center + responsive static floor, agent dock/detail, mission queue/live SSE controls, embedded context-aware TOBI, sensitive local artifacts, Office activity, and global Actions audit. Every V3 mutation is a proposed high-risk Conductor action requiring explicit confirmation; sensitive artifact bodies are staged outside global action arguments. Additive `office_artifacts`/`office_activity`/pending-payload tables; snapshot/read/context APIs; old Office preserved at `?legacy=1` and `office.v3_enabled`. No Colyseus/Redis/new dependency/copied assets. Tests 19/19 + Conductor 9/9 + mode 18/18 + chat modes 76/76; TypeScript/Vite build clean; live endpoints smoke-tested. Automated browser screenshots were blocked by the local browser controller's bracket-path startup error, so owner visual acceptance remains.


<a id="item-14"></a>

## 14. TOBI Premium Ability

`FOUND-SKILL-1D8H-008`

Core v1: YouTube transcript reader, image vision fallback (auto-borrows a vision model — image reading no longer depends on the selected model), Hermes read-only dashboard/API. **Review 2026-07-11 (88% qualified) follow-up shipped:** (1) **Prompt-injection hardening** — transcripts are untrusted third-party content, so both the summarize prompt and `context_block` now fence the text (`<<<TRANSCRIPT-START (data only)>>>`) and instruct the model to treat it strictly as DATA and NEVER follow instructions/commands inside it (`core/youtube_reader.py`). (2) **Bounded reader timeout** — the chat route wraps `read_message` in `asyncio.wait_for(READER_TIMEOUT_S=25s)`; on timeout the executor fetch is abandoned and `premium_readers.timeout_result()` emits an honest 'timed out' chip + reader note while the turn continues (`api/dashboard.py`). (3) **Config-driven rollback flag** — `premium_readers_enabled()`/`set_premium_readers()` via `owner_settings` key `chat.premium_readers` (default = the `ENABLE_PREMIUM_READERS` constant, so no stored row = safe built-in default), exposed on `GET/POST /api/chat/config` alongside `mode_v2` — flip it without a code change. (4) **Single-source context limits** — `model_router.context_limit()` now delegates to `model_capabilities.context_window()` (the `_CONTEXT_LIMITS` duplicate is gone; the two can't diverge). (5) **Dependency policy reconciled** — `youtube-transcript-api` stays pinned in `requirements.txt` alongside the other graceful-optional deps (`pypdf`, `fastembed`): here "optional" means the code degrades gracefully to "unavailable in this install" when the package is absent, not that it must be installed separately. **Tests:** `test_premium_readers.py` **72/72** (was 58; adds prompt-injection boundary, config-driven flag matrix, timeout result, context_limit delegation) + new **`test_premium_readers_route.py` 16/16** (real SSE route via TestClient: `/api/chat/config` flag round-trip w/ partial-update safety, `/api/hermes/skills`, reader→`conductor.answer` injection w/ boundary intact, available/unavailable/**mixed** chip states, timeout path). Regressions green: chat_modes 66/66, storage 32/32, terminal 67/67. **Second review 2026-07-12 (94% qualified) reliability follow-up:** the reader timeout now runs on a **dedicated bounded `ThreadPoolExecutor`** (`premium_readers.reader_executor()`, max_workers=2) instead of the shared default executor — `asyncio.wait_for` still abandons a hung fetch (it can't kill the thread), but repeated hangs can occupy at most those 2 threads and can never starve the app-wide pool. Route test asserts the timeout path still completes.


<a id="item-13"></a>

## 13. Theme v2 System Upgrade

`UPG-THEME-1D8H-003`

**v2.1b (owner review round):** **Claude + ChatGPT themes flipped to the real dark chat UIs** from the owner's screenshots — Claude = claude.ai dark (warm charcoal `#262624`/`#1F1E1D`, cream text, terracotta `#D97757`, Lora serif display), ChatGPT = chatgpt.com dark (`#212121`/`#171717`/`#2F2F2F`, soft white, teal signal); **official logos as theme icons** (`src/theme/brandIcons.tsx` — Claude starburst + OpenAI knot from the lobehub path set, `ThemeIcon` type now accepts both lucide + brand marks, used in Settings/quick-switch/palette). **Ornament fixes:** chinese dragon → **hanging gold lanterns** (strings/ribs/tassels below the chat header via per-corner `at` offsets) + medallion halo; claude → the **official Claude starburst** as corner + avatar-halo watermark; japanese petals constrained to **side margins** (never cross the reading column); fixed a real bug — `motif-breathe` animated `opacity`, overriding every ornament's inline per-spec opacity (animations beat inline styles) → transform-only now. Screenshot-verified all four + Settings gallery; suite green (parity/migration/contrast); tsc+build clean. — **v2.1 design-quality pass (owner feedback: expressive themes felt "hard/dazzling", brand themes missing, light-theme cohesion broke):** now **12 themes** in 3 groups — core (Dark/Light/High Tech), expressive (**Neon Arena/Washi/Lacquer/Jarvis OS**, all repaletted calm-premium), brand (**Vercel/Notion Calm/Linear Flow/ChatGPT/Claude**, tasteful homage, lucide icons). **Self-hosted fonts** (`src/theme/fonts.ts`, `@fontsource` latin woff2 — Rajdhani/Chakra Petch/Zen Maru Gothic/ZCOOL XiaoWei/Geist/Inter/Lora) via `--font-ui`/`--font-display` per theme (Office's Google-CDN Rajdhani `<link>` removed → bundled); new `--overlay`/`--selection`/`--font-numeric` tokens. **Cohesion sweep:** `bg/border/ring-white/*`→`overlay/*` across 22 files (scheme-aware ink-on-light) + targeted hardcode fixes (Evolution ring, StatBar/HealthBar tracks, RadarChart, Brain tab, Architecture chip, PageLoader presets, `.sovereign/.aurora-text`). **Chat ambient ornaments (M2.5)** — per-theme signature motifs concentrated in Chat (owner's main surface): procedural inline-SVG `ChatAmbient`+`ornaments` (sakura branch+petals·gold dragon+clouds·arc-reactor rings·HUD hex brackets·Claude spark), corner-anchored + drifting particles + a faint avatar-halo watermark, radial-masked & opacity≤~0.2, honoring `data-motion` + a per-theme **decorations** toggle. `index.css` fully regenerated from `computeCssVars` (parity-enforced). Settings: grouped **preview cards** (real mini-UI per theme) + decoration toggle. **Verified:** `tsc`+build clean; node suite green (migration matrix · `computeCssVars` key-set · **CSS↔tokens parity all 12** · WCAG contrast text≥4.5/muted≥3/accent≥2.6); **Playwright screenshots of all 12** reviewed + iterated (ornament placement/opacity); fonts self-hosted (0 `fonts.googleapis`, 27 woff2 bundled); decorations-off & motion-off guards confirmed hide ornaments while theme stays. **Open:** owner click-through; brand-inspired GitHub/VS Code + Aurora/Solar remain proposals. — *(v2.0 baseline below)* **Built per spec (all 6 phases):** new `src/context/themeTokens.ts` — centralized ThemeV2 model (id/label/description/icon/mode/tokens/defaults/customizable/migrationFrom; color triplets + typography/shape/elevation/component/background/dataViz/motion token groups), pure `migratePrefs` (midnight→gaming, contrast→dark, warm→dark, scientific→light, unknown→dark, malformed-JSON→defaults, preserves fontScale/density/sound, adds `customByTheme`, writes back v2 shape to `tobi.prefs`), `computeCssVars`/`computeDataAttrs`. `ThemeProvider` rewritten (inline CSS-var application on `<html>` with stale-key cleanup — instant switching + crossfade preserved; `useTheme()` shape backward-compatible + `custom`/`setCustom`/`resetCustom`; legacy `THEMES`/`THEME_META` exports derived). `index.css`: 7 active theme blocks (Dark/Light kept; **Gaming/High Tech upgraded**; **Japanese/Chinese/Jarvis OS added**; removed themes' CSS deleted) each with full new var set (`--radius-*`, `--shadow-card/popover`, `--tracking-ui`, `--spacing-scale`, `--bg-overlay-opacity`, `--chart-1..6`, `--theme-glow`, `--theme-accent-2`); background styles (grid/gradient/paper/hud on body via `data-bg-style`); `.tv2-card`/`.tv2-btn`/`.tv2-popover` component classes driven by `data-card-style`/`data-button-style`. Tailwind `rounded-md/lg/xl/2xl` + `shadow-2xl` now track the vars → shape/elevation personality applies app-wide without page rewrites; `accent2` color added. Settings: Theme v2 panel (icon+name+description+real swatch cards), guided per-theme customizer (accent presets, radius, cards, buttons, background, shadows, typography, animation, contrast + Reset theme / Reset all), **disabled Theme v3 import placeholder** (no file input); Density gains `spacious`. AppShell quick switch + CommandPalette use the active list w/ icons (guarded lookups). Storage charts prefer `--chart-1..6`. Office pinned-dark + root-accent bridge untouched. **Verified:** `tsc` + `npm run build` clean; 30+ node assertions on migration matrix + token output (all pass); built CSS contains the 3 new themes / zero removed-theme blocks. **Open:** owner click-through of the §12 manual matrix; brand-inspired + Aurora/Solar themes remain proposals only.


<a id="item-12"></a>

## 12. Project v2

`UPG-PROJ-3D-002`

**Built this session (branch `project-v2`):** backend — `_ensure_pm_v2_schema` (project icon fields + `resources_bytes`, task `start_at`/`reminder_at`, tables `pm_folders`/`pm_resources`/`pm_task_deps`/`pm_goal_tasks`/`pm_icons`, goal `mode`, idempotent `pm_files`→Resources migration), `core/pm_resources.py` (disk store under `<data>/projects/{id}/resources`, ≤100MB, traversal guard, text extraction txt/md/code/PDF/docx, URL classify + YouTube-transcript + readable-web fetch, icon validation), 15+ endpoints (overview snapshot, resources list/upload/link/patch/delete/raw, folders, icons upload+serve, task deps, goal↔task rollup links; task patch += start/reminder/description/estimate; project delete cleans the resources dir), Conductor read tool **`project_overview`**. Frontend — `WorkspaceTabsContext` extended for dynamic `/projects/{id}` tabs (one tab per project, inner-tab route updates in place, dynamic labels via `setTabLabel`, persisted); route `/projects/:projectId/*` (lazy `ProjectWorkspace`, own 73kB chunk); sidebar Projects → **Recents** sub-list; new `components/project/*` — `ProjectIcon` + **IconPicker** (emoji + 40-icon lucide pack + upload→DB, downscaled 128px), **OverviewTab** bento (editable description, 8 metric tiles, scrollable active tasks, resources card, goals summary, activity), **TasksTab** pro list (status groups, manual drag reorder + due/priority sort toggle, quick-add, assignee filter; right **TaskDrawer** expandable to full width: status/priority/assignee, start/due/reminder/estimate, plain description, rich subtasks w/ assignee+due, blocks/blocked-by deps), **GoalsTab** (5 metric cards, search, status/priority/due filters, task-link rollup), **ResourcesTab** Drive-style (drag-drop upload, folders+breadcrumb+drag-move, grid/list, per-type icons, tags, preview panel: image/video/audio/PDF/text inline + download/open-external, add-link modal), **ActivityTab**; `Projects.tsx` home rewired to navigate (drawer deleted, −900 lines). **Verified:** backend 6/6 unit tests; live HTTP smoke all endpoints 200 (upload→disk→Storage bytes, deps both directions, icon served, overview grounded); `tsc` + vite build clean; conductor tool returns grounded snapshot. **v1.1 shipped this session:** reminder scheduler job (`core/pm_reminders.py` + `job_task_reminders` every 2 min → Telegram alert; idempotent `reminder_fired_at`); Storage dedicated **'Project resources drive'** bucket (`storage_scan._fs_targets`, carved out of the Office data-dir walk so it isn't double-counted); **Graph-node sync** — resources become `resource`-domain nodes linked to their project, pruned inside `graph_engine.sync_internal`; **TOBI act tools** `create_resource` (url link or text note), `set_project_description`, `pick_project_icon` (auto-picks by category/name) + read tool `search_project_resources`; **resource RAG embeddings** — `pm_resource_chunks` via fastembed with keyword fallback, indexed on upload/link and dropped on delete. Only **Google-Drive import** remains (blocked on the Google connector). Verified: temp-DB integration test passes (act tools, RAG search hit, reminders, chunks stored, `reminder_fired_at` column). Turns the right-side `ProjectDrawer` popup into a **full-page workspace** that opens as a tab in the forthcoming **Global Header Tab System** (plug-in + graceful fallback — full-page-one-at-a-time until that ships, no throwaway code; deep-link `/projects/:id/:tab`). Tabs kept & upgraded: **Overview** (bento layout; owner+TOBI plain-text description w/ overwrite-confirm; scrollable active tasks; task/time/resources/effort metric tiles; `project_overview(id)` read tool so chat is grounded), **Tasks** (single **pro List** view — status groups, manual drag + sort toggle; right-drawer detail expandable to full page; start/due/**reminder**; rich one-level subtasks w/ assignee+due; **estimate**; **blocks/blocked-by deps**; no labels; recurring deferred; TOBI full create/edit/**bulk**/delete w/ delete+bulk>N confirm via chat card, applied one-by-one + audited), **Goals** (metric cards + search + status/priority/due filters; optional task-link rollup), **Docs→Resources** (Google-Drive-style: disk-backed files under `~/.mmo_agent/projects/{id}/`, ≤100MB, folders+tags, drag-drop upload + URL import (Google Docs/Sheets/Slides, **YouTube→transcript**, readable web, PDF/GitHub) + **Drive copy**; in-app preview + open-external; curated per-type icons; **per-project content RAG**; resources become **Graph nodes**; sizes tracked by Storage #10 both per-project + dedicated bucket), **Activity**. **Missions** → disabled **"Soon"** at end of nav. **Bonus:** project **icons** = emoji + vector icon pack + **custom upload** (stored in DB); TOBI **auto-picks icon+accent** on chat-create; change from Overview + create modal. **Backend:** extend PM schema (new `pm_resources`/`pm_folders`/`pm_resource_chunks`/`pm_icons`/`pm_task_deps`/`pm_goal_tasks` + task/project columns); **auto-migrate** old `pm_files`→Resource link items; single big release. Reuses Conductor #7 (tools/tiers/audit), Storage #10, graph_engine, motion primitives. **60 Q&A captured (D1–D60).** Depends on the **Global Header Tab System** (to be queued).


<a id="item-11"></a>

## 11. TOBI CLI

`FOUND-CLI-1D8H-007`

**Built this session (all four phases).** **P0 engine — `core/terminal_engine.py`:** hybrid **risk classifier** (static rules → low/medium/high + a hard **denylist**; network commands auto-medium [D9]; self-modify forced high [D27]; optional Haiku judge for ambiguous [D8]); **two-axis gate** — approval **mode** (Plan/Ask/Accept/Auto, `owner_settings terminal.mode`) × command **risk** → run/confirm/plan/refuse [D6][D17]; **safety floor** (denylist Auto-can't-bypass + global **kill-switch** + **secret redaction** of keys/tokens/vault values [D25]); cross-platform **shell** (PowerShell/cmd · bash/sh) [D26]; **background jobs** (`terminal_jobs`: start→id→list/inspect/kill, ring-buffer output) [D11]; per-risk **timeouts** [D12]; live-output sink for SSE streaming. **P1 surfaces:** repointed the toy `_execute_tool.run_bash` onto the engine (**removed `_BLOCKED_CMDS` + PROJECT_DIR lock** [D5]); **Conductor tools** `run_command`/`install_package` (dynamically gated by the engine, not the static tier), `configure_tool`/`connect_tool`/`kill_job`/`set_terminal_mode` + read tools `terminal_status`/`list_jobs`/`job_output`/`list_installed_tools` — all inherit `tobi_actions` audit + confirm-card + EN/VN voice [D3][D22][D24]; **Telegram capped at Ask** (medium/high propose a typed-confirm, low auto) [D18]; **Chat terminal mode** [D19] — `TerminalMode.tsx` panel (approval-mode switch, kill-switch, live xterm console via new SSE `terminal` events, background-job list, capability chips) wired into the existing mode selector; 7 `/api/terminal/*` endpoints. **P2 acquire:** `install_package` across pip/pipx/npm/pnpm/winget/choco/scoop (auto-pick available, shell-injection-guarded) [D13]; `configure_tool` (writes config files) + `connect_tool` (references an **existing** vault/env credential — never plaintext in chat) [D14]; **`installed_tools` capability registry** surfaced in MC + **mirrored to `~/.hermes/skills`**; auto-wire **offer** on install [D15][D16]. **P3 CLI/REPL:** upgraded `main.py terminal` REPL (routes through the Conductor + `/mode` `/status` `/jobs` `/kill` `!<cmd>` direct-run with inline confirm) [D4]; **`tobi hermes <args>`** thin Hermes passthrough + MC logging [D2][D20]; localhost-trust reused. **Evolution [D30]:** `_detect_abilities` now marks Awakening **`tiered_permissions` + `full_filesystem`** active (evidence = the engine module is present), seeding Agent `shell_full_access`. **Verified:** `tests/test_terminal_engine.py` **67/67** (classifier, denylist-in-every-mode, two-axis gate matrix, kill-switch, redaction, real exec + exit codes, background start/list/kill, registry, acquire command-building, and LLM-stubbed Conductor gate→run→audit + confirm/plan flows); Storage #10 regression 32/32; `tsc` + `vite build` clean; FastAPI app registers all 7 terminal routes. **Open (owner inputs, defaults shipped):** confirm the exact denylist patterns, the terminal-loop monthly spend cap, install-timeout values, and whether admin-elevation installs should confirm even in Accept [§13]. `terminal_sessions` table reserved; remote owner-token deferred until remote CLI use is wanted.


<a id="item-10"></a>

## 10. Storage & Usage

`FOUND-CORE-20H-006`

Bottom-system-menu **`/storage`** page, **Overview header + 2 tabs**, read-only v1 [S3]. **M1 (Storage):** `core/storage_scan.py` — agent.db **per-table via dbstat** (sampled-estimate fallback) + data dirs (`~/.mmo_agent` excl. the db, `~/.hermes`, fastembed cache) + repo/graphify-out/logs, **feature rollup** (Brain/Graph/Office/Tasks/Projects/Docs/Chat/Codebase/Vault/MCP) with venv/node_modules/dist in a separate **System bucket** cached weekly [S7][S24]; every scan writes **`storage_snapshots`** → 30-day growth trend + Δweek/Δmonth + 30d projection [S8]; drill-down = top tables + top files/dirs per feature (honors the same skip sets as the rollup); vault size+count only [S28]. **M2 (LLM Usage):** instrumentation was already live from #8 P3 (`model_router` auto-logs every call w/ surface/feature/latency); added `core/usage_meter.py` — **`config/llm_prices.yaml` → `llm_prices` table → live estimator sync** [S14] (synced at API startup), **range-aware overview** (D/W/M/All) across **all 4 dims** (provider/model/surface·feature/agent) with cost+tokens+requests+avg-latency [S15][S16], per-day spend **stacked by surface**, paginated+searchable **call log** [S20], **`llm_plans`** usage-vs-limit bars [S17], **`usage_budget`** monthly cap + alert-% → ok/warn/over [S18] (in-app toast→bell only, no TG push [S26]). 9 endpoints: `/api/storage/{overview,category/{f},scan}` + `/api/usage/{overview,calls,plans,budget,prices}`. Scheduler: `job_storage_scan_db` hourly + `job_storage_scan_fs` daily 04:30 [S21]. **M3 (glue):** Conductor #7 read tools **`storage_status`** + **`llm_spend`** [S25]; **Dashboard "Storage & Spend" widget** → links here [S29] (new dash widgets now auto-append past a saved layout). Frontend: lazy-loaded **Recharts** page (bars/treemap/donut/growth-area + stacked spend area, theme-var driven so all 8 themes work; main bundle untouched), plan/budget inline editors, HardDrive sidebar entry. **Tests 32/32** (`tests/test_storage_usage.py`, isolated temp DB); build clean; live-server smoke: all 9 endpoints + both tabs + drill-down + Dashboard widget verified w/ Playwright. Owner inputs still open: real plan values + budget cap (defaults editable in-page); price table pre-seeded in `config/llm_prices.yaml`.


<a id="item-9"></a>

## 9. Explore → News

`FOUND-NEWS-1D8H-005`

New top-level **Explore** sidebar section; **`/news`** page = 3 tabs + top headlines rail. `core/explore.py` — standalone engine: **fetch → dedupe → summarize → score → store**, every LLM call logged to `llm_usage` (surface=`explore`) under a **D21 monthly USD cap** (~$5). 4 SQLite tables (`explore_sources/items/models/config`). **Models tab:** frontier-only leaderboard from **OpenRouter live list** (new models land day-of) with a **blended composite** (intelligence + elo + popularity, weights owner-tunable) + **sortable table** + **Recharts price×intelligence scatter** + click-to-**compare radar** (reuses `RadarChart`). **Tools tab:** HN (Algolia) + GitHub trending + Product Hunt, AI-summarized, source filter, expandable cards. **Social tab:** Reddit (seed subs, hot posts) + Tavily + X (opt-in pay-per-use with cap) → ranked "for you" feed, freshness badges (New/Hot/Cooling). **News backbone:** NewsData.io + GDELT + RSS + GNews (EN). **Config drawer:** per-source toggle/weight, recency-vs-engagement slider, keyword include/exclude, editable interest prompt, model-composite weights, X opt-in + cap, monthly budget. **Conductor digest:** `POST /api/explore/digest` returns TOBI's daily brief (on-request via #7). 10 `/api/explore/*` endpoints. Scheduler: news hourly / tools 3h / social 6h / models 03:30. All keys in Genesis vault (#4); free sources (OpenRouter/HN/GDELT/RSS/Reddit) work with no keys — others activate when added in Integrations ("Explore sources" entry). No autonomous push (E8). Live-verified: 27 RSS + 145 OpenRouter models pulled + real LLM digest on first run. Frontend lazy-loaded (Recharts shared chunk with Storage).


<a id="item-8"></a>

## 8. Premium Chat

`UPG-CHAT-3D-001`

Upgrade Chat to rival Claude/ChatGPT/Gemini/Grok: vault-backed **model config page** (Anthropic/OpenAI/OpenRouter/Gemini/Grok/Ollama/custom; default + per-task overrides + ordered fallback) that is the **single source of truth** and **pushes to Hermes**; **usage analytics** from real per-call logging. Chat UX: **visible thinking**, **`+` menu** (file/image-paste/Drive/web-research/**connector→live-tools** via #7), **rich block output** full-width, **copy/regenerate/edit→branch**, **context energy bar** + **Compact** at ~80%, **DB sessions**, **system action log**. Phased P1 config+sessions+thinking/rich → P2 +menu/files/connectors/actions → P3 analytics+context+compact. 30 Q&A captured. Reuses Genesis vault (#4), Conductor (#7), research engine. **P1 (Foundation & feel) built & tested — needs backend restart to load:** refactored `core/model_router.py` into a **7-provider registry** (Anthropic native + OpenAI/OpenRouter/Gemini/Grok/Ollama/custom via an OpenAI-compatible client) + `FallbackClient` (ordered chain), with routing prefs (**default + per-task overrides + fallback** + provider base_url/models) in a new **`llm_config`** table while **keys stay in the Genesis vault**; `get_llm(task_type, model=None)` honours picker→override→default→**legacy `PRIMARY_MODEL`** (fully backward-compatible). **`core/hermes_sync.py`** pushes routing to `~/.hermes` on save (JSON sidecar always + `hermes.yaml` patch if PyYAML + `hermes config set` if on PATH) — one-way, never crashes. **`core/chat_store.py`** DB **sessions** (create/auto-title/rename/delete, **per-session model**, stable negative `chat_id` per session) + **messages** (model/tokens/thinking, `parent_id` reserved for P2 branch). Conductor (#7) `answer()` now takes **`model` + `history`**. New **typed SSE** `POST /api/chat/sessions/{id}/stream` (`thinking`/`delta`/`action`/`usage`/`done`) drives the chat's **live timer + tool chips → "Thought for Xs"**, **Stop** (keeps partial) + **Regenerate**, **Copy/Remember**. Dependency-free **`MarkdownView`** renders rich markdown (tables/code-with-copy/lists/links) + structured **```tobi:card\|table\|callout\|keyvalue\|reference\|status```** blocks **full-width** (assistant blocks, user bubbles). New **`/models`** config page (provider cards w/ vault-gated key save + Discover, default/overrides/fallback editor, Push-to-Hermes, P3 analytics placeholder) in the sidebar bottom-menu. Endpoints: chat sessions CRUD + `/append` + `/stream`; `/api/llm/{config,models,provider/{id}/key,discover/{id},hermes-push}`; `init_database` eagerly creates the 3 tables. **Tests: 26/26** (router/store/hermes) **+ 10/10** (per-session turn: model+history threading + persistence + tool-loop) **+ #7 P3 regression 17/17 intact**; frontend **build clean** (tsc no errors, ~714 kB main, +~37 kB). **P2 (Tools & actions) built & tested — needs restart + `pip install pypdf`:** composer **`+` menu** (Upload file · Attach image / **paste** · **Web research** toggle · **Show thinking** toggle · **Connector** toggles → live tools · Drive=soon). **`core/attachments.py`** splits uploads → **text** (txt/md/code/json/csv + **PDF** via pypdf, graceful note if absent) folded into the turn as context, and **images** → **native vision** via `model_router.vision_complete()` (provider-correct Anthropic-image-block / OpenAI-`image_url`; `supports_vision()` gate + honest fallback note). New **opt-in** Conductor tool **`web_search`** (Tavily/research engine, mock-fallback) advertised **only** when Web research is toggled (lives in `OPTIONAL_TOOLS`, so #7's base 10-tool catalog is untouched) → cites in a `tobi:reference` block. Connector toggles add a per-turn **directive**. **Message actions:** **Edit → branch** forks the session up to that message into a new `↳` session (original preserved, `chat_store.fork_session`) and runs the edit there; **feedback 👍/👎** (`chat_messages.feedback`). **Activity panel** = this session's **TOBI Actions** (#7) via `list_actions(chat_id=…)`. New endpoints: `/api/chat/sessions/{id}/fork`, `/api/chat/messages/{id}/feedback`, `/api/chat/sessions/{id}/activity`; stream req gains attachments/web_research/thinking/connectors; `requirements.txt` += pypdf. **Tests: 25/25** (web_search opt-in + answer-runs-it + directives + attachments + vision format + feedback + fork + scoped activity) **+ regressions intact (#7 P3 17/17, #8 P1 26/26, P1b 10/10)**; build clean (~724 kB main, +~10 kB). **P3 (Meters & analytics) built & tested — #8 COMPLETE:** **`core/usage.py` extends the existing D34 `llm_usage` table** (+ `ts/surface/feature/cost_est/latency_ms` — what #10 wants) with a **manual price table**; **clients auto-log every `complete()`** (real provider tokens else estimate) tagged with a process-global **surface** (`set_usage_context`; chat endpoint sets `chat`, legacy **Office** rows fold in via `created_at`). **Analytics** `GET /api/llm/usage?days=` (tokens/cost/requests/latency + by-model + by-surface + per-day) on the **Models page** (KPIs + per-model bars + tokens/day trend, 7d/30d, dependency-free) and a compact **Health** widget. **Context energy bar** per the model's real `context_limit` (now on each `available_models()` entry), **warn ≥80%** → inline **Compact** = `POST /api/chat/sessions/{id}/compact` summarizes older turns into one stored `summary` message (LLM), keeps recent verbatim (`chat_store.compact_session`), feeds the summary back as context (`recent_history`) + renders a "compacted" callout. **Tests: 23/23** (price/cost + logging + summary across chat+office + client auto-log + context limits + compaction) **+ all regressions intact**; build clean (~731 kB main, +~7 kB). **⚠️ Post-delivery fixes (owner-reported, live-verified on a real server):** (1) **the "create project but nothing shows / hallucination" bug was a data-layer mismatch** — the Conductor wrote the legacy `projects` table while the Projects/Tasks pages read the **PM system**; repointed every project/task tool to `pm_projects` + `tasks.pm_project_id` (see #7 row). Live: chat create-project + add-task now appear on the PM board, grounded to real ids; unknowable queries refuse instead of inventing. (2) **Thinking UX** — added a Conductor `on_event` progress callback bridged to SSE via a thread→async queue, so the panel narrates live phases ("Creating the project…", "Reading your projects…") instead of a static "Thinking…" during the model's latency. (3) **Output** — assistant replies render **full-width/borderless** (not a cramped bubble). Suites after fixes: `test_pm_fix` 13/13, #7 P2 24/P3 17, #8 P1 26/P1b 10/P2 25/P3 23; build clean.


<a id="item-7"></a>

## 7. TOBI Conductor

`FOUND_BASE-CHAT-1D8H-001`

**⚠️ Post-delivery fix (live-verified):** the act/read tools targeted the **legacy `projects` table** but the UI uses the **PM system** — so chat-created projects/tasks never showed up (looked like hallucination). Repointed `create_project`/`list_projects`/`create_task`/`complete_task`/`update_project_progress`/`delete_task` to **`pm_projects` + `tasks.pm_project_id`** (status `active`, auto progress recalc, `pm_activity` log; `list_projects` returns the real id for chaining); `assign_task` → canonical Tasks-board key (`tobi\|research\|coder\|ceo` + aliases). Verified on a live server: create project → add task → list, all appear on `/api/pm/projects` + the project's task list, grounded to real ids. — Turn TOBI into the **conductor of MC**: one shared engine (MC chat + Telegram) that reads & acts on every feature by conversation, grounded in the optimized second brain ([SECOND_BRAIN_DIRECTION.md](SECOND_BRAIN_DIRECTION.md)) with **strict live-data grounding**. Hybrid (classifier pre-route → intent-scoped function-calling tool-loop), one shared engine + thin adapters, **tiered permissions** (confirm on delete/mission-run; Telegram read+safe, MC full), butler "sir" voice, mirror EN/VN, **log+learn**, multi-step chains (Notion→project→tasks→assign), **TOBI Actions** audit view, suggest-then-act. Phased P0 second-brain → P1 read → P2 act → P3 external. 30 Q&A captured. Reuses the tool-use loop, Brain, classifier, Genesis vault. **P0 (second brain) already in place** from #1 (8-category memory-first brain + retrieval + GraphRAG `owner_context`). **P1 (read/answer all features) built & tested:** `core/conductor.py` — one shared engine: regex **classifier pre-route** (smalltalk/coding answer directly; MC-state queries enter the loop) → memory-first **profile grounding** → **provider-agnostic JSON tool-loop** (model emits `{"tool","args"}`, engine executes + feeds back, ≤5 steps; works over the plain `complete()` string interface so it runs on OpenRouter *and* Claude, no native-tool-use lock-in) → **butler "sir" voice + EN/VN mirroring + strict grounding** (numbers/status only from tool results, else "I don't have that yet, sir" + offer to fetch). **7 read tools** over live DB/helpers: `get_evolution`, `explain_architecture`, `office_status`, `list_projects`, `list_tasks`, `check_health`, `recall`. Wired into **both surfaces**: MC chat (repointed `/api/brain/chat` + SSE `/api/brain/chat/stream` through the Conductor, brain fallback; streams the grounded answer in chunks — the M2 thinking-orb covers the "working" phase) and **Telegram** (`handle_chat` STATUS/QUESTION → Conductor, read-only/safe; EXECUTION stays legacy). `/api/conductor/status` introspection. **17/17 venv tests pass** (live tools return real data — GENESIS tier, 4 agents/4 free, db_ok, memories; tool-call parsing incl. fenced/embedded; multi-tool loop; smalltalk bypass). **P2 (act tools + tiered permissions + confirmation + audit + log-and-learn) built & tested:** **7 act tools** over existing sync DB ops with **risk tiers** — low (`create_project`, `create_task`, `complete_task`, `remember`) + medium (`update_project_progress`) **auto-execute & report**; high (`delete_task`, `run_mission`) are **proposed and only run after the owner confirms**. **Confirmation UX both ways:** the chat turn returns a `pending_action` (surfaced over SSE as an `action` event) → MC Chat renders a **Confirm/Cancel card**; a **typed "yes"/"có"** (EN+VN affirm/negate sets) also resolves the latest pending action. **Surface asymmetry enforced:** MC = full power; **Telegram = read + low-risk only** (medium/high blocked with "do it from Mission Control"). **TOBI Actions audit:** lazy `tobi_actions` table logs every proposed/executed/rejected/failed action (tool, args, risk, summary, result, timestamps) → new **`/actions`** page (sidebar Main) with risk/status badges + count-ups + live refresh; `/api/conductor/actions` + `/api/conductor/confirm` + `/api/conductor/status`. **Log-and-learn:** every 5th execution of a tool writes a habit note to the Brain. **24/24 venv tests pass** (risk tiers; act tools mutate an isolated temp DB; high-risk propose-not-execute; confirm executes; typed-yes; low-risk auto; Telegram blocks medium/high; audit log + status). Frontend builds clean. **P3 (external + chains) built & tested — #7 COMPLETE:** **3 external read tools** over the existing connectors (`read_notion` — search + `get_page_content` block reader added to `NotionIntegration`; `read_github` — repo info/issues/commits; `read_drive` — honest "not wired yet"), all graceful when a source isn't connected. New **`assign_task`** act tool (medium → `tasks.agent_key`). **Multi-step chains** in one turn (step budget 8): e.g. `read_notion → create_project → create_task → assign_task → answer`, each step grounded in the previous step's real ids. **Stop-on-failure:** a failed state-change halts the chain and reports exactly what was done and what failed (no fabricated success). Catalog now **10 read + 8 act tools** (`/api/conductor/status` → phase P3). **17/17 venv P3 tests pass** (external graceful; assign_task; dynamic-id chain in correct order; stop-on-failure halts+reports; counts). **Acceptance set all green:** evolution+architecture, agents count/status, Notion→create project/tasks/assign, health + create on both surfaces — every number tool-sourced, risky acts confirmed, Telegram read+safe.


<a id="item-6"></a>

## 6. Living Machine

`FOUND-THEME-20H-004`

Cross-cutting motion system: route transitions, per-page atmosphere, micro-interactions + 3 named effects (Brain neural-ingestion upload, Chat thinking orb, Health diagnostic sweep). Centralized motion primitives, strict 60fps, reduced-motion first-class. 30 Q&A captured. Phased M1–M4. **M1 (Foundation) built & building clean:** `src/lib/motion.ts` (DUR/EASE/SPRING tokens + level-aware variants `panelBoot`/`staggerParent`/`staggerChild`/`fade`/`scaleIn`/`slideOver`); `MotionProvider` (Full/Reduced/Off, localStorage, merges OS `prefers-reduced-motion` — the more restrictive wins — and writes `data-motion` on `<html>`); 8 primitives in `components/motion/` (`Reveal`, `Stagger`/`StaggerItem`, `PageBoot`, `Scanline`, `AmbientField`, `SpotlightCard`, `CountUp`, `TraceButton`), each reduced-motion aware; `index.css` motion tokens + keyframes (`scanline-sweep`/`ambient-drift`/`border-trace`/`count-flash`) + first-class `[data-motion="reduced"\|"off"]` guards + `[data-theme-anim]` crossfade; route transitions now use `<PageBoot>` (slide-up + fade + one-shot scanline sweep, keyed per path, no exit-gating so no blank frame); AppShell sliding `layoutId` nav pill + icon pop (namespaced per sidebar instance via `LayoutGroup`); ThemeProvider 300ms theme crossfade window; Settings **Motion** toggle (Full/Reduced/Off + OS-clamp note). Bundle ~+4kB only. **M2 (named signature effects) built & building clean:** (1) **Brain neural ingestion** — `components/brain/NeuralIngestion.tsx`: glyph particles converge into a glowing brain orb under a live typed pipeline log (`Reading…`→`Parsing…`→`Extracting…`→`✓ Extracted N memories`→`Ready to review`) + animated progress bar; wired into `BrainImportModal` (real `parseImport` count drives completion, then cards reveal via `Stagger`/`StaggerItem`). (2) **Chat orb + phases** — `Chat.tsx` `ThinkingOrb` (pulsing orb + cycling `Recalling memories…`→`Connecting context…`→`Thinking…`) replaces the static bubble; streamed reply now leads with a blinking caret (`.chat-caret`) on the live assistant message. (3) **Health diagnostic sweep** — `Health.tsx`: running a check shows radar-scan rows (`.radar-scan-overlay`, staggered ping pulse) while every API is tested, then results cascade in via `Stagger` each snapping to green/red with a one-shot `SnapRing` glow; overall HP figure now `CountUp`s (HealthBar). All three degrade correctly (reduced ⇒ no particles/sweep/pulse, plain log + color fade; off ⇒ instant). Bundle +11kB. **M3 (marquee pages) built & building clean:** **Dashboard** — once-per-session `HeroBoot` "TOBI · SYSTEM ONLINE" overlay (sessionStorage flag, grid ignite + scanline + spring logo), `AmbientField` accent atmosphere behind content, KPI tiles now `SpotlightCard` (cursor-follow glow) + `CountUp`, Launchpad actions → `TraceButton` (border sweep). **Command Palette** — already spring-in; added result `Stagger` cascade + sliding `layoutId` selection pill with glow ring. **Evolution** — unlock overlay gains a refined horizontal glow-sweep across the tier node (premium, not fireworks) + a confident success **toast** (logged to the bell inbox) alongside the existing rings/emblem/`sfx.tierUp`. **Office** — ambient liveliness (breathe/blink + desk glow + reduced-motion static fallback) already shipped in #3, so Decision #22 is satisfied with no rebuild. Bundle +3kB. **M4 (remaining pages + polish) built & building clean — #6 complete:** **ToastProvider** upgraded (Decision #19) — colored left **edge bar** + bottom **drain timer** (`scaleX`, matches the 4.2s auto-dismiss) + slide/spring entrance, all reduced/off-aware. **Atmosphere rollout** — `AmbientField` (now `z-index:-1` so a page just needs `relative` + the tag) adopted on **Ability** (purple), **Architecture** (accent), **Task** (accent), **Projects**, **ControlRoom** (success); **Task** metrics became `SpotlightCard` + `CountUp`. Every other route already inherits the global `<PageBoot>` HUD transition + sliding nav + theme crossfade from M1, so cohesion is universal (Inbox/Integrations/Mcp are centered/gated layouts left at the baseline transition by design). **60fps audit (static):** all new motion is transform/opacity (variants, scaleX drain, particle x/y/scale); the few paint bits (`radar-scan` bg-position during a check, `count-flash` text-shadow) are brief one-shots in line with the existing `tobi-shimmer` vocabulary; every decorative loop is killed by the `[data-motion="reduced"\|"off"]` guards; no lingering `will-change`. Final bundle 677kB (≈+20kB total for the whole motion system). **Three modes verified by construction** (Full/Reduced/Off collapse correctly across every primitive).


<a id="item-5"></a>

## 5. MCP Hub

`NEW-LINK-3D-002`

TOBI as MCP server (others connect in) + client (connects out), MCP+A2A, dedicated MC page. Reuses Genesis vault for creds. Everything in v1 (phased M1–M4). **M1 (MCP server) built & tested:** `mcp` SDK added; `_ensure_mcp_schema` (7 tables); `core/mcp_server.py` FastMCP (Streamable HTTP) mounted at `/mcp` exposing 6 tools (`ask_tobi`/`query_brain`/`get_status`/`list_projects`/`recent_lessons` + sensitive `run_mission`) + resources + prompts; `core/mcp_security.py` (bearer-token auth, per-client scopes, rate limit, audit, approval queue); `McpAuthMiddleware` (authn+rate-limit+scope at the edge); approval-gating for sensitive tools; `/api/mcp/*` mgmt API (vault-session gated); slash-less `/mcp`→`/mcp/` redirect. **M2 (outbound client) built & tested:** `core/mcp_client.py` multi-transport connection manager (Streamable HTTP, SSE, stdio) — add+test (block on failure), tool discovery → `mcp_tools`, **per-tool allow/ask/deny** permission model (new tools default `ask`, untrusted posture), owner 'try-it' override, `ask`→approval queue, vault-backed creds, refresh, `health_check_all` (stateless reconnect-per-op), outbound audit, `available_tools_for_agent()` for the Conductor loop; `/api/mcp/connections/*` + `/api/mcp/tools/*` endpoints. e2e tests pass for both M1 (401-gate, scope-deny, registration, mount) and M2 (block-on-fail, discover, allow/ask/deny, try-it, refresh, health, audit, delete). **M3 (MC UI) built:** `/mcp` page (sidebar bottom-menu, `Workflow` icon) with vault-unlock gate; **Server tab** (inbound endpoint URL+copy, exposed-tools list w/ approval badges, inbound-client token issuance w/ scopes + revoke), **Clients tab** (add-server modal w/ transport+block-on-fail, connection cards: status/test/refresh/enable/kill-switch + per-tool allow/ask/deny + enable + **try-it** modal), **Activity tab** (in/out call inspector), pending-**approvals banner** (approve/reject), server enable toggle. **M4 (reach + interop) built & tested:** **OAuth 2.1 JWT** inbound (HS256 key in vault, scope claim → tools; accepted alongside issued tokens — verified over the wire) + `resolve_inbound`; **host-allowlist / transport security** (localhost locked by default; `exposed` relaxes it for tunnels — fixes the DNS-rebinding 421); **cloudflared tunnel** manager (`core/mcp_tunnel.py`, start/stop/status, public URL persisted, graceful if absent); **A2A** (`core/a2a.py`: agent card from MCP tools served at `/.well-known/agent.json`, peer discovery/add/remove/message) + `/.well-known/oauth-protected-resource`; UI: Server-tab **OAuth** + **Tunnel** cards, new **A2A tab** (card editor + peers + message). e2e M4 tests pass (OAuth logic+HTTP gate, host-allowlist, A2A card/well-known/peers, tunnel graceful). All four milestones shipped.


<a id="item-4"></a>

## 4. Genesis Complete

`FOUND-LINK-1D8H-003`

**Built & tested (needs backend restart to load).** `core/vault.py` (scrypt KDF → AES-256-GCM, per-secret nonce, AAD-bound, in-memory key + auto-relock, verifier; 14 unit tests pass), `_ensure_vault_schema` (vault_meta/profiles/secrets/audit), `core/integrations_registry.py` (reuses `integrations.py` `.test()` + LLM/Telegram pings, maps each → Genesis abilities), 16 `/api/vault/*` + `/api/integrations/*` endpoints gated by an `X-Vault-Session` token (full HTTP e2e pass — no value leaks, reveal needs master pw, audit logs metadata only). Frontend: `/integrations` page (setup/unlock gate, Genesis % header + live celebration, core-prereq-first cards with connect/test/reveal/remove, custom secrets, audit panel, profiles, encrypted export/import, reload/lock). Adds `cryptography` to requirements. Connect tests the key (block-on-failure) → injects into `os.environ` → Genesis % advances live, no restart. **Final follow-ups now built (M4 complete):** **Complete-Genesis wizard** — a `GenesisWizard` stepper (required-first; connect-&-continue / skip; live % bar + completion celebration) launched from the Genesis header when incomplete; **Health cross-link** — a *Genesis & Integrations* panel on the Health page (live %, per-integration connected chips, "Manage → /integrations" link). Verified earlier this run: integrations auto-connect on boot, lessons-store activated → 12/12.


<a id="item-3"></a>

## 3. Living Office

`FOUND-OFFICE-20H-002`

Owner-approved. Phaser 3 behind a React↔scene `EventBus` (`dashboard/src/office/`), lazy-loaded Office route (engine in its own chunk). **Procedural art** (no external packs) — iso room auto-sized to the roster, themed desk per live agent, chibi characters with per-state faces/anim (working/idle/sleeping/thinking/error) + speech bubbles streaming real `step_delta`. **M3 motion:** easystar pathfinding, handoff **courier packets** desk→desk, free-roam **micro-events** (coffee runs), idle→sleep calm office, interpolated walking. **M4 juice:** per-monitor neon glow, accent data-motes + coffee steam, subtle day/night brightness (no heavy tint), mission start/finish shake/flash, **audio toggle** (event SFX) + **performance mode** (footer), keyboard agent nav, panel-aware camera + collapsible KPI panel, reduced-motion/mobile → static `HqBase` fallback. All existing mission/agent control flows preserved (backend untouched).


<a id="item-2"></a>

## 2. Graph View

`NEW-BRAIN-20H-001`

Built: unified `graph_nodes`/`graph_edges` store, `core/graph_engine.py` (internal sync + ref/tag/semantic edges + degree), 13 `/api/graph/*` endpoints, `job_graph_sync` (45m). Frontend `/graph` page — lazy-loaded `react-force-graph-2d` canvas (glow/hulls/particles + perf toggle), domain switcher, keyword+semantic fly-to search, filters, detail panel, drag-to-pin, connect-mode linking, timeline scrubber. Local/Obsidian + Notion + GitHub mirrors; Google awaits its connector. AI features (path/ask/insights) still v2.


<a id="item-1"></a>

## 1. Brain

`FOUND-BRAIN-1D8H-001`

v1: Brain + Chat pages, vault, import/dedup/review, chat wired to memory. v2 shipped: Telegram auto-learn + `/brain` `/remember`, one-way Hermes mirror, confidence-decay automation, SSE streaming chat, task-level memory-first consultation (research/execute/CEO). Semantic search needs `pip install fastembed` (else keyword fallback).


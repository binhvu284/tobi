# Mission Control Runtime — architecture guide

Before queue #21, a request behaved differently depending on where it came from — Chat, Telegram,
a page button, the CLI, a scheduler. Each path kept its own memory of what happened, and a crash
lost it. After #21 every request becomes the same kind of thing: **one run**, with one history,
one set of rules, and it survives a restart.

This diagram is that engine, followed left to right: a request arrives, becomes a run, is decided
on, does its work, and leaves a receipt. Click any node to jump to its notes.

Rollout controls ship **off**. In shadow mode the old path still answers the owner while the new
engine records and compares alongside it — which is exactly why the two paths both appear here.

Two things joined the diagram since the last refresh. **Deterministic selection** (#34) means a
common request is matched to a frozen workflow and typed arguments before a model is involved at
all, so the answer stops depending on which model is selected. **TOBIval** (#34) is the exam suite
that must pass before any of this can be switched on; the owner accepted its result on 2026-08-30.
Chat-to-Developer dispatch (#35) is the third addition: a limitation you describe in Chat can
become one confirmed Developer work item on the same canonical run.

## ChatIn
A Chat or Agent turn from Mission Control. The one surface that can eventually be *executed* by
the runtime rather than only recorded by it, which is why it has its own activation stage.

## Surfaces
Projects, Office, the CLI, Telegram, and all 18 scheduler callbacks. These enter through a
compatibility adapter and are **recorded**, never re-routed: their existing execution is
untouched.

## Coding
Developer sessions (queue #22, extended by #35). Each accepted session creates or reuses one
deterministic run and mirrors its lifecycle. The worker cannot change the authoritative record
itself. The default worker is now the in-process DeepSeek Harness.

## Dispatch
`core/developer_dispatch.py` — a limitation described in ordinary Chat becomes a *proposal*, not
work. No queue row, no branch, no run is created at this point.

## Confirm
The proposal only becomes work when the owner confirms the card in Chat. The confirmed item is
linked back to the message that asked for it, so status and evidence stay truthful rather than
optimistic.

## AgentTier
`core/agent_tier.py` — the seven-ability evidence registry. An ability is complete only while a
real run's qualifying evidence is fresh (24 hours); it stores bounded references, never raw output
or secrets, and it fails closed.

## Gateway
`core/runtime/gateway.py` — the entry point for Chat and Agent. It decides whether this turn is
recorded (shadow), executed (on), or ignored (off), and it never lets execution happen untraced.

## AdapterIn
`core/runtime/surface_adapter.py` — fail-open by design. If recording breaks, the real work still
happens; a Projects action never fails because history could not be written.

## Identity
Every request carries an identity. The same identity delivered twice is the same request, not two
of them.

## Reuse
Duplicate delivery reuses the existing run and its single final receipt. This is what makes a
retry safe.

## Run
The canonical record: objective, surface, state, version, and everything below it. One row that
every other part of this diagram points at.

## Plan
A validated step graph. A plan that references a step that does not exist, or loops back on
itself, is refused before anything runs.

## Lease
A step is owned by exactly one worker for a bounded time. Two workers cannot hold the same step,
and an expired worker cannot commit a result.

## Work
The step actually running — a model turn, a tool, a terminal job.

## Checkpoint
Progress written down as it happens, so the work does not have to start over.

## Resume
After a crash or restart, the same run continues from its checkpoint. It does not become a new
run, and the old one does not disappear.

## Retry
Bounded retries, cancellation fencing, and fail-closed handling of unknown outcomes. "We do not
know if it worked" is treated as failure, never as success.

## Policy
`core/runtime/policy.py` — permissions, risk tiers, approvals, credentials and budgets decided in
one place instead of spread across the files that happen to need them.

## Approval
High-risk actions wait for the owner. The approval result lands on the *same* run rather than
starting a new one.

## Budget
Token, cost, time and step limits. Exhaustion stops the run rather than quietly continuing.

## Creds
Whether a credential is actually available for this tool, not merely configured somewhere.

## Catalog
`core/runtime/tool_catalog.py` — every tool described once, in one format.

## Validate
Arguments are checked against the tool's declared shape *before* it runs, so a malformed call
fails at the boundary instead of halfway through.

## Reserve
A mutation reserves its action first. This is what makes the receipt below meaningful.

## Execute
Files, terminal, projects and connectors — the tools that change something.

## Receipt
An immutable record that this action was applied. A retry finds the receipt and does not apply it
a second time.

## Events
Append-only, strictly ordered history. Nothing is edited or deleted; a correction is another
event.

## Redact
Secrets are masked **before** anything is written, not before it is displayed. A key that reaches
storage is already a leak.

## Store
The 22 canonical SQLite tables. Their migrations are recorded in the shared ledger, which the
Health infrastructure test checks.

## Projection
Current state rebuilt deterministically from the events, so the summary can never drift from the
history it came from.

## RunsView
`core/runtime/runs_view.py` — bounded summaries only: labels, states, timestamps, counts and
references. Never a prompt, a body, a secret, or raw tool output.

## RunsPage
The Runs pane under Operation. One live view of every run, shared across pages, reconnecting
where it left off. When it is empty it says *why* it is empty.

## Traces
One trace per request joining context, model, tools, approvals, cost and outcome.

## Workflows
`core/runtime/workflows.py` — the frozen catalog of bounded jobs TOBI knows how to do, each with
its required fields, allowed tools, stop condition, and success evidence. Selection is
deterministic: the same wording always picks the same workflow, and a request outside the catalog
is refused rather than improvised.

## Typed
`core/runtime/typed_resolution.py` — the request's arguments are resolved into the workflow's
declared shape before anything runs. Guessing a value is not an option.

## Missing
A required field that is absent produces exactly one clarifying question, not a plausible
invention and not a silent failure.

## Grounded
`core/runtime/grounded_outcomes.py` — when the workflow and its arguments fully determine the
answer, the result is produced without a model at all. This is what makes common Mission Control
work stop depending on which model is selected.

## Cases
`tobival/dataset.py` — 72 frozen exam cases plus 14 held-back ones, locked by a hash so an exam
cannot be quietly edited to improve a score. Each case runs through the real runtime lifecycle and
stores its run and trace IDs.

## Runner
`core/runtime/eval_runner.py` and `eval_executor.py` — the canonical runner. It records route,
context, validation, execution, and final-outcome ownership for every case, so a result can be
traced to the decision that produced it.

## Scorers
`core/runtime/eval_scorers.py` and `eval_metrics.py` — marking is executable code, not judgement.
A case either produced the required evidence or it did not, and the numbers land in immutable
records.

## Lane
`tobival/model_lane.py` and `core/runtime/eval_live.py` — the live half. It keeps the raw model
response separate from what deterministic recovery rescued afterwards, and the held-back cases run
once, so a score cannot come from practising on the answers.

## Gate
The release gate. Missing, failed, or below-threshold evidence blocks activation rather than
warning about it. The approved live rerun recorded 156 of 156 model responses, raw model pass
32.05%, deterministic recovery 67.95%, and no provider failures; **the owner accepted it on
2026-08-30**. Production routing is still limited to narrow, safe workflows with no required
fields.

## EvalPage
The **Evaluations** view on the Runs page — the owner-facing projection of all of the above:
cases, decisions, evidence, live results, and whether the gate is open.

## Rollout
`core/runtime/rollout.py` — staged activation: shadow, then direct chat, then read chat, then
actions, then agent. A stage cannot be skipped or moved backwards.

## Compare
Each stage needs seven consecutive runs where the old and new paths agree, plus the quality gate
above. Comparisons keep route, policy, outcome, latency and evidence references only.

## Rollback
One switch returns **new** work to shadow behaviour. Runs already recorded are untouched, and the
approved stage is preserved so resuming does not start the streak again.

## Shadow
The default today. The old path answers the owner; the new engine records what it would have done
and the two are compared.

## Legacy
`core/conductor.py` is now a thin compatibility facade over the runtime services. Legacy tools and
tables are still in place; deleting them is a separate owner-approved decision.

## Health
**Health → Infrastructure** runs this whole diagram as a test: twelve read-only checks of the
running server, then every acceptance suite in its own throwaway database.

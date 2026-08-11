# #30 Chat Self-Check — prove Chat works, not just that a model answers

## For the owner, in one paragraph

The Health page has a button that checks everything. On 2026-08-01 it reported the AI as **OK**
while Chat was completely broken — every request failing, all day. It was not lying. It asks the
model one question and gets one answer, and that genuinely worked. The bug only appeared on the
*second* message of a conversation, which the check never sends.

This item makes the check do what the owner actually does: hold a short conversation that uses a
tool. If that works, Chat works. If it does not, the page shows the real error instead of a
guess.

**No new setting. Nothing to configure. Works with whichever model is selected.**

---

## Purpose

> One sentence: the Health page tells the truth about whether Chat can complete a real request.

## Why now

Evidence from 2026-08-01, all recorded:

| What happened | Where |
|---|---|
| `/api/health/deep` ran `llm_complete("Reply with exactly: OK")` and passed | [`api/routers/health.py:233-236`](../../api/routers/health.py#L233-L236) |
| Chat failed on runs 82, 83, 85, 86, 87 with `model.malformed_output` | `chat_turn_events` |
| Real cause: turn 2 rejected with HTTP 400 `Invalid value: 'input_text'` | fixed in `ca7cbd4` |
| Owner was told "the current model is struggling" and sent to the model picker twice | Chat UI |

A one-message check cannot see a bug that needs two messages. Every future defect in the tool
loop, the tool registry, policy, or context assembly has the same blind spot today.

This is also the [non-technical-user standard](../../CLAUDE.md) applied to diagnosis: when TOBI
breaks, the owner should be able to press one button and be told what is wrong, without reading
code or logs.

## What it does

Replaces the single-shot LLM probe with a bounded real conversation:

1. Send a fixed, harmless request that requires one **read-only** tool — the same shape as
   "list my projects".
2. Let the Conductor run its normal loop: model turn → tool → model turn → answer.
3. Report one of three outcomes, each with the real detail:

| Outcome | Meaning shown to the owner |
|---|---|
| **Chat works** | The tool ran and a plain answer came back |
| **Chat is broken** | The exact failure, redacted — e.g. the HTTP 400 body |
| **Model unavailable** | The provider could not be reached at all |

It must run the **streaming** path with the **route's own token budgets**, because that is the
path Chat uses and the path the 2026-08-01 bug lived in. A check that runs an easier path than
the real one is not a check.

## Acceptance criteria

Each names a check that will actually run, so the evidence can exist:

1. Must leave `tests/test_chat_self_check.py` green, covering: a healthy two-turn conversation
   reports working; a second-turn transport failure reports broken **and** includes the
   provider's own error text; a first-turn failure is reported as model-unavailable, not as a
   Chat defect.
2. Must prove the check would have caught the shipped defect: with `_to_input` reverted to tag
   assistant messages `input_text`, the self-check reports **broken**; with the fix in place it
   reports **working**. A check that passes either way is not a guard.
3. Must exercise the streaming path and the route token budgets, asserted in the test, not the
   non-streaming defaults.
4. Must write no chat message, no conversation row, no action, and no owner-visible history —
   asserted by row counts before and after.
5. Must redact secrets from any error text it surfaces, reusing the existing `_redact` helper in
   `api/routers/health.py`.
6. Must complete or time out within 60 seconds and never leave the Health request hanging.
7. Must leave `tests/test_codex_client_backends.py` and `tests/test_conductor_mixed_reply.py`
   green.

## Non-goals

- No change to `core/conductor.py` — #21 T08 owns that file.
- No change to anything under `core/runtime/` or `core/schema/runtime.py` — #21 T07 owns those.
- No new Runs page or shared projection client — #21 T13 owns that.
- No scheduled or automatic execution. The owner presses the button, as today.
- No new owner setting, flag, provider, or credential.
- No write tools, no network calls beyond the model the owner already selected.
- No redesign of the Health page; one row changes and one is added.

## Files expected

| File | Change |
|---|---|
| `core/chat_self_check.py` | **new** — runs the bounded conversation, returns a typed result |
| `api/routers/health.py` | swap the one-shot LLM probe for the self-check; keep the row shape |
| `dashboard/src/pages/Health.tsx` | show the outcome and its detail (existing row layout) |
| `tests/test_chat_self_check.py` | **new** — the guard |

Four files. Anything beyond this list means the work drifted.

## Verification

1. Guard first: run `tests/test_chat_self_check.py` against current `main` and confirm it
   **fails**. Record the failing output.
2. Implement, then confirm green.
3. Revert `_to_input` in a scratch copy and confirm the self-check reports **broken** — criterion
   2 above.
4. Regression: `test_codex_client_backends`, `test_conductor_mixed_reply`,
   `test_escalation_without_config`, `test_conductor_final_guard`, `test_chat_modes`.
5. pyflakes clean on every touched module; `tsc --noEmit` and `npm run build` green.
6. Live: restart MC, press the Health deep-check button, confirm it reports Chat working and the
   whole call returns in under 60 seconds.

## Risks

| Risk | Guard |
|---|---|
| The check itself costs tokens on every press | Bounded: one read tool, small token cap, owner-triggered only |
| It could pollute chat history | Criterion 4 asserts zero rows written |
| It could leak a key in an error message | Criterion 5 reuses the existing redactor |
| File collision with Codex on #21 | None of the four files are in T07's or T08's declared set; re-check before starting |

## Size

Half a focus day. One package, one reviewable diff.

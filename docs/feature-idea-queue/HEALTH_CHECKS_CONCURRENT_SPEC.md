# #32 `UPG-CORE-3H-010` — Health checks run together and appear as they finish

## For the owner, in one paragraph

Pressing **Run full health check** takes 20 to 50 seconds, and shows nothing at all until every
check has finished. The checks do not depend on each other — Telegram has no idea what the chat
check is doing — but they run strictly one after another anyway. This makes them run at the same
time, and shows each result the moment it lands. Telegram and Tavily appear in about a second;
only the slow one keeps spinning.

Nothing to configure. Same checks, same answers, same page.

---

## Purpose

> One sentence: the Health button finishes in the time of its slowest check, not the sum of all
> of them, and fills the page in as it goes.

## Why now

Measured on 2026-08-13, one real run of `/api/health/deep`:

| Check | Time |
|---|---|
| Chat self-check | **18,453 ms** |
| Tavily | 1,557 ms |
| Telegram | 1,549 ms |
| notion, github, google, vercel, supabase | 0 ms (not configured) |
| **Wall clock** | **20–50 s**, varying with the model call |

**This is a regression I introduced.** Before [`be5e198`](../../api/routers/health.py) that first
row was a one-second `llm_complete("Reply with exactly: OK")` ping. Replacing it with a real
two-turn conversation was the right call — it is what made the check honest, and it caught the
defect the ping could not — but it turned a four-second button into a fifty-second one, and I
did not re-measure the button afterwards.

Sequential execution was survivable when every check took a second. It is not survivable now.

## What it does

**1. Run the independent checks concurrently.** The chat check already runs on a worker thread;
Telegram, Tavily and each integration are synchronous `requests` calls run one at a time through
`_timed_check`. All of them move to `asyncio.gather` over `asyncio.to_thread`, so the endpoint
costs its slowest check rather than their sum.

**2. Stream each result as it arrives.** Today the page shows nothing for the whole run. The
endpoint gains a streaming form so a row appears the moment its check returns, and the existing
non-streaming response stays for any caller that wants one object.

**3. Stop blocking the event loop.** Two synchronous network calls still sit inside async
handlers:

| Location | Call | Worst case |
|---|---|---|
| [`api/routers/genesis.py:468`](../../api/routers/genesis.py#L468) | `requests.get(USERINFO_URL, timeout=10)` | 10 s frozen app |
| [`api/routers/health.py:278,290`](../../api/routers/health.py#L278) | Telegram `getMe`, Tavily search | 10 s, 12 s |

**Stated honestly: neither could be made to freeze anything in testing**, because both services
short-circuit when unconfigured, and a heartbeat probe measured 0 ms of loop blocking across a
49-second run. They are a structural risk with no reproduced symptom. They are in scope because
the same files are already open for point 1, not because they are hurting today.

## Acceptance criteria

Each names a check that will actually run, so the evidence can exist:

1. Must leave `tests/test_health_concurrency.py` green, and that suite must **fail** against
   current `main` — recorded before the fix.
2. Must prove concurrency by construction, not by wall clock: with every check stubbed to sleep
   250 ms, the endpoint must complete in under 500 ms, where sequential execution would need
   the sum.
3. Must keep the response shape byte-compatible for the non-streaming caller — same keys, same
   nesting, same `ok`/`detail`/`latency_ms` per check — asserted against a recorded sample.
4. Must report each check's own duration, not the wall clock, so a slow check is still
   identifiable after they overlap.
5. Must leave the event loop free throughout: a heartbeat task scheduled alongside the endpoint
   must keep ticking, asserted for `api_health_deep` and for `google_oauth_status`.
6. Must surface a failing check exactly as it does now — one broken integration must not abort
   the others, asserted by making one check raise.
7. Must leave `tests/test_health_endpoint_budget.py`, `tests/test_chat_self_check.py` and
   `tests/test_ui_silent_failures.py` green.
8. Must leave `tsc --noEmit` at exit 0 and `npm run build` green.

## Non-goals

- No change to what any check actually tests. The chat self-check keeps its two real turns; this
  is about when they run, not what they prove.
- No change to `core/runtime/**`, `core/schema/runtime.py`, or `core/conductor.py` — #21 T07 and
  T08 own those.
- No new Runs page or shared projection client — #21 T13 owns that.
- No redesign of the Health page. The existing rows stay; they simply arrive earlier.
- No automatic or scheduled running of the deep check. The owner presses the button, as today.
- No new owner setting, flag, or credential.
- No caching of results between presses. A health check that answers from a cache is not a
  health check.

## Files expected

| File | Change |
|---|---|
| `api/routers/health.py` | gather the checks; stream results; take the two sync calls off the loop |
| `api/routers/genesis.py` | take the Google userinfo call off the loop |
| `dashboard/src/pages/Health.tsx` | render rows as they arrive |
| `dashboard/src/api.abilities.ts` | the streaming client |
| `tests/test_health_concurrency.py` | **new** — the guard |

Five files. Anything beyond this shape means the work drifted.

## Verification

1. Guard first: run `tests/test_health_concurrency.py` against current `main`, confirm it
   **fails**, record the output.
2. Implement, then confirm green.
3. Prove the guard has teeth: force one check back to sequential and confirm criterion 2 goes
   red.
4. Regression: `test_health_endpoint_budget`, `test_chat_self_check`, `test_ui_silent_failures`,
   `test_ui_loading_states`.
5. `tsc --noEmit` exit 0, `npm run build` green, `dashboard/dist` rebuilt.
6. Live: restart MC, press **Run full health check**, and confirm Telegram and Tavily appear
   within about two seconds while the chat check is still running, and that the total is close to
   the chat check alone.

## Risks

| Risk | Guard |
|---|---|
| Concurrency hides a check that silently never returns | Each check keeps its own timeout; criterion 4 keeps per-check durations visible |
| Streaming changes the shape existing callers rely on | Criterion 3 asserts the non-streaming response is unchanged |
| One failing check aborts the rest once they share a gather | Criterion 6 asserts isolation by making one raise |
| Five concurrent outbound calls trip a provider rate limit | Only one call per provider, once per button press |
| Collision with #21 | None of these files are in T07's or T08's declared set; re-check before starting |

## Size

`3H`. One package, one reviewable diff.

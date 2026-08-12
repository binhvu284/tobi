# #31 `FIX-CORE-8H-002` — Pages tell you when they fail to load

## For the owner, in one paragraph

When a page cannot load its data, it currently shows you nothing. Not an error, not a warning —
it just looks empty, exactly as it would if you genuinely had no data. There are **65 places
across 23 files** that do this. So when something breaks, the screen looks normal, and you either
miss a real failure or go hunting for one that was never there. This item makes every page say
what happened and offer one button to try again.

Nothing to configure. One shared piece used everywhere, so every page behaves the same way.

---

## Purpose

> One sentence: a page that failed to load says so, in plain words, with a way to retry.

## Why now

The whole of 2026-08-01 was spent on TOBI reporting success while failing. The backend now tells
the truth; the frontend still does not.

| What the owner saw | What was true |
|---|---|
| Health: "LLM OK" | Every Chat request was failing — fixed in `be5e198` |
| Chat: "the current model is struggling" | The model was never asked — fixed in `ca7cbd4` |
| **A page that looks empty** | **The request failed and nothing said so — this item** |

The rule was written the same day in [`CLAUDE.md`](../../CLAUDE.md): *error messages must be true
and actionable*. This applies it to the pages.

The shape of the defect, verbatim from `pages/Storage.tsx:148`:

```ts
getStorageOverview().then(setOv).catch(() => {})
```

Confirmed by hand in `Storage.tsx`, `Projects.tsx`, and `Dashboard.tsx`. Counted by a scan that
excludes `sessionStorage`/`JSON.parse` guards, so the 65 is close but approximate; the item fixes
what the guard test finds, not a fixed list.

| File | Silent failures |
|---|---|
| `pages/Mcp.tsx` | 8 |
| `pages/Dashboard.tsx` | 7 |
| `pages/Ability.tsx` | 7 |
| `pages/Storage.tsx` | 5 |
| `pages/Chat.tsx`, `pages/Brain.tsx`, `components/chat/TerminalMode.tsx` | 4 each |
| 16 more files | 26 |

## What it does

**1. One new primitive**, beside the existing ones in
[`components/async-ui.tsx`](../../dashboard/src/components/async-ui.tsx):

```tsx
<LoadFailure error={err} onRetry={load} what="your storage data" />
```

Renders a short plain-language line, the real reason underneath, and a **Try again** button:

```
⚠  Couldn't load your storage data.
   Connection refused — the API server may be down.        [Try again]
```

It sits in `async-ui.tsx` on purpose. That file already owns `ActionButton`, `BusyOverlay`,
`ActivityBar` and `SectionSkeleton`, and the rule that they must be used rather than hand-rolled
is already enforced. A second home would be a second thing to remember.

**2. A guard that makes it stick.** `tests/test_ui_loading_states.py` already scans every
component and fails when an async control ships without a pending state — the same discipline
problem, solved once. A sibling suite does the same for swallowed failures, so the next
`.catch(() => {})` fails the build instead of shipping quietly.

**3. The Health endpoint stops freezing the server.**
[`api/routers/health.py:110`](../../api/routers/health.py#L110) makes a **blocking** HTTP call
inside an `async def`:

```python
r = requests.get(f"http://localhost:{API_PORT}/health", timeout=2)
```

Measured warm: `/api/health` takes **4,076 ms** while every other endpoint answers in 8–30 ms.
Because the call is synchronous inside an async handler, every other request waits behind it —
the whole app pauses, not just the Health page. Moved off the event loop, with the timeout
honoured.

## Acceptance criteria

Each names a check that will actually run, so the evidence can exist:

1. Must leave `tests/test_ui_silent_failures.py` green, and that suite must **fail** against
   current `main` — recorded before the fix.
2. Must fail if any component under `dashboard/src/` swallows a data-fetch rejection with an
   empty handler, proven by adding one `.catch(() => {})` to a scratch component and watching the
   suite go red.
3. Must leave `tests/test_ui_loading_states.py` green — the pending-state rule is not weakened by
   this change.
4. Must show the provider's or network's real reason, not a generic phrase, asserted on at least
   one page by rendering with a rejected fetch.
5. Must offer a retry that re-runs only the failed request, not a full page reload.
6. Must bring `/api/health` warm response time under 500 ms with the API server unreachable, and
   must keep its response shape unchanged — asserted in `tests/test_health_endpoint_budget.py`.
7. Must leave `tsc --noEmit` at exit 0 and `npm run build` green.

## Non-goals

- No redesign of any page, no new layout, no theme change.
- No change to `core/runtime/**`, `core/schema/runtime.py`, or `core/conductor.py` — #21 T07 and
  T08 own those.
- No new Runs page or shared projection client — #21 T13 owns that.
- No change to what any endpoint returns, only to how long `/api/health` blocks.
- No new owner setting, flag, or credential.
- No retry-on-a-timer, no automatic refetch loops. The owner presses the button.
- No conversion of pages to a data-fetching library; this is a failure affordance, not a rewrite.

## Files expected

| File | Change |
|---|---|
| `dashboard/src/components/async-ui.tsx` | add `LoadFailure` |
| `tests/test_ui_silent_failures.py` | **new** — the guard |
| `tests/test_health_endpoint_budget.py` | **new** — the 500 ms budget |
| `api/routers/health.py` | move the blocking call off the event loop |
| ~23 page and component files under `dashboard/src/` | replace each silent swallow |

The 23 UI files are mechanical, one pattern repeated. Any file touched beyond this shape means
the work drifted.

## Verification

1. Guard first: run both new suites against current `main`, confirm each **fails**, record the
   output.
2. Implement, then confirm green.
3. Prove the guard has teeth: add one `.catch(() => {})` to a scratch component and confirm
   `tests/test_ui_silent_failures.py` goes red.
4. Regression: `test_ui_loading_states`, `test_chat_self_check`, `test_chat_modes`.
5. `tsc --noEmit` exit 0, `npm run build` green, `dashboard/dist` rebuilt.
6. Live: restart MC, stop the API server, open two pages, and confirm each says what failed and
   recovers on **Try again** — and that other pages stay responsive while Health is loading.

## Risks

| Risk | Guard |
|---|---|
| A "failure" that is really an empty result starts showing a scary error | Criterion 4 asserts on the real reason; empty results keep their existing empty state |
| 23 files is a wide diff | One repeated pattern, no logic changes, and the guard test is the reviewer |
| Moving the health call off the loop changes its result | Criterion 6 asserts the response shape is unchanged |
| Collision with #21 | None of these files are in T07's or T08's declared set; re-check before starting |

## Size

`8H` — about one focus day. One package, one reviewable diff.

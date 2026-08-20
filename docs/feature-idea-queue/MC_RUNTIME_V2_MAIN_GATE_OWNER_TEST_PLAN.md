# Runtime V2 Main Gate Owner Test Plan

## Use This Plan Now

This is the owner test for the current main Mission Control gate.

Use this URL:

```text
http://127.0.0.1:8090
```

This plan does not assume Runtime V2 is activated. It tests what the main gate is allowed to do
today, and it stops before asking the owner to inspect a Run that cannot exist.

## What This Test Proves

| Test area | What it means |
|---|---|
| Latest code | The browser is talking to the newest local TOBI code, not an old server |
| Chat path | TOBI can still reply normally through Chat |
| Runs page | Runs gives a truthful empty-state reason when Runtime V2 is not activated |
| Runtime gate | The owner does not waste time testing Direct Chat Runs while the rollout is blocked |

## T1. Confirm Latest Server - 2 Minutes

Owner action:

1. Open `http://127.0.0.1:8090`.
2. Confirm the page loads and the top-right status says `Live`.
3. Ask Codex in this task: `check main gate version`.

Correct result:

Codex must report that `/api/health` on `8090` returns the current Git revision. If the revision is
old, stop. Do not continue testing until Codex restarts the local server.

## T2. Confirm Main Chat Still Works - 5 Minutes

Owner action:

1. Open `Chat`.
2. Create a new session named `Main Gate Runtime Smoke`.
3. Set the composer mode to `Chat`.
4. Turn off optional Web and connector chips for this test.
5. Send exactly:

```text
Reply with exactly: RUNTIME V2 ACTIVE
```

Correct result:

TOBI replies:

```text
RUNTIME V2 ACTIVE
```

Pass if Chat replies normally.

Fail if Chat gives a provider error, malformed-output warning, or asks to switch model.

## T3. Confirm Runs Gives The Right Reason - 3 Minutes

Owner action:

1. Open `Runs` under `Operation`.
2. Set `Surface` to `All Surfaces`.
3. Set `Status` to `All Statuses`.

Correct result on the current main gate:

Runs may show `0 runs`. That is acceptable only if the empty message explains that canonical Runtime
Runs are not active yet, for example:

```text
No canonical runs yet; direct Chat rollout is blocked by comparison-streak:0/7
```

Pass if the page says why there are no Runs.

Fail if the page only says `No matching runs`, shows a loading loop, or shows an error screen.

## T4. Confirm We Should Not Do The Old T3 Yet - 1 Minute

Owner action:

Ask Codex in this task:

```text
is direct chat runtime active?
```

Correct result:

Codex checks `/api/runtime/rollout`.

If `direct_chat.allowed` is `false`, stop. Do not run the old durable-Run test. Chat can reply, but
the main gate is not allowed to write Runtime V2 Runs.

If `direct_chat.allowed` is `true` and the stage is activated, Codex gives a separate Direct Chat
Runtime test.

## T5. Confirm Test Gate Is Fresh - 2 Minutes

Owner action:

1. Open `http://127.0.0.1:8181`.
2. Confirm the page loads.
3. Ask Codex in this task: `check test gate version`.

Correct result:

Codex must report that `/api/health` on `8181` returns the current Git revision.

Pass if `8181` is fresh and healthy.

Fail if `8181` is old, offline, or pointed at the wrong database.

## Stop Rules

Stop immediately if any of these happen:

1. `8090` or `8181` reports an old revision.
2. Chat fails before Runs testing.
3. Runs shows `0 runs` without explaining why.
4. A plan asks you to inspect a newest Runtime Run before Codex has confirmed Direct Chat Runtime is active.

## Result Format

Report only this:

```text
T1:
T2:
T3:
T4:
T5:
Screenshot if failed:
```

If everything matches, report:

```text
Main gate test matched expected results.
```

# Mission Control Runtime V2 Owner Experience Test Plan

## Document Control

| Field | Decision |
|---|---|
| Related Queue item | `#21 Mission Control Infrastructure V2` |
| Status | Ready for owner review; test execution has not started |
| Owner test time | 60 minutes |
| Owner interaction | Mission Control UI only |
| Test machine | Owner's Windows PC |
| Data posture | Isolated copy first; never write test data to the live database |
| Activation posture | Temporary Direct Chat activation in the isolated copy, followed by rollback and resume proof |
| Deep failure testing | Codex runs it separately and reports the result |

## 1. Purpose

Give the owner a simple, visible experience of what Runtime V2 changes. The test must prove that
Mission Control can show one durable Run, preserve it across refresh and recovery, record other
surfaces without replacing them, and roll new execution back without breaking Chat.

This is an experience test, not production activation. Passing it does not authorize changing the
live owner database or retiring legacy execution.

## 2. What The Owner Should Notice

| Before Runtime V2 | Experience during this test |
|---|---|
| Work was spread across separate histories | Chat, Projects, and Office appear in one Runs view |
| A failure was mainly visible through logs | Failure and recovery evidence stays attached to one Run |
| Rollback was an engineering operation | Codex can switch the isolated runtime back to shadow while the UI remains usable |
| Technical evidence was difficult to inspect | Timeline, Trace, Evals, and Context are available from one Run detail |
| Duplicate or resumed work was difficult to reason about | Automated checks prove one request identity and same-Run recovery |

## 3. Safety Boundary

The following rules are mandatory:

1. Use SQLite's backup function to copy the live database. Do not copy an open database file with a
   normal filesystem command because its write-ahead log may contain newer data.
2. Store the isolated database at
   `D:\[PERSONAL PROJECT FILES]\TOBI\.runtime-v2-test\agent.db`.
3. Start only `main.py api`. Do not run `main.py start`, Telegram polling, or schedulers.
4. Use dashboard port `8181` and API port `8100`. If either belongs to another process, use `8182`
   and `8101`; never stop an unknown process.
5. Never change Runtime flags in the live database.
6. Synthetic comparison or evaluation evidence must be labelled `owner-experience-test` and exist
   only in the isolated database.
7. The Chat test may contact only the model provider already selected in Mission Control. Do not
   contact Supabase, Vercel, Telegram, or any other external integration.
8. Stop immediately if the server reports the live database path, if the test URL is not the
   agreed test port, or if any secret/raw request body appears in Runs.

## 4. Responsibilities

| Person | Responsibility |
|---|---|
| Codex | Backup, isolated setup, preflight, temporary activation, prepared failure cases, rollback, deep tests, cleanup, and final evidence report |
| Owner | Use only the browser UI, perform the seven tests below, and report only unexpected results |

## 5. Codex Preparation

These steps happen before the owner's 60-minute clock starts.

### P1. Capture And Isolate

1. Record the live database path, current Runtime flags, current rollout stage, rollback state,
   current Git revision, and processes using ports `8080`, `8100`, and `8181`.
2. Create the D-drive test folder if missing.
3. Produce a consistent SQLite backup at the test path using a read-only source connection and the
   SQLite backup API.
4. Open the copy and confirm that its absolute path differs from the live path.
5. Save a checksum and row counts for `owner_settings`, `mc_runs`, and `mc_run_events` in the
   preparation report. Do not print record bodies.

### P2. Prove The Build

Run from `D:\[PERSONAL PROJECT FILES]\TOBI\tobi` with the maintained D-drive Python runtime:

```powershell
& "D:\[PERSONAL PROJECT FILES]\TOBI\.python\venv\Scripts\python.exe" scripts/gate.py
& "D:\[PERSONAL PROJECT FILES]\TOBI\.python\venv\Scripts\python.exe" tests/test_mc_runtime_surface_adapters.py
& "D:\[PERSONAL PROJECT FILES]\TOBI\.python\venv\Scripts\python.exe" tests/test_office_v3.py
```

Required result: `19/19` final gate suites, `17/17` T15 checks, and `19/19` Office checks. Any red
result blocks the owner test.

### P3. Start The Isolated UI

Start the API-only process with these process-local values:

```powershell
$env:DB_PATH="D:\[PERSONAL PROJECT FILES]\TOBI\.runtime-v2-test\agent.db"
$env:DASHBOARD_PORT="8181"
$env:API_PORT="8100"
& "D:\[PERSONAL PROJECT FILES]\TOBI\.python\venv\Scripts\python.exe" main.py api
```

Required result: `http://127.0.0.1:8181` serves Mission Control and its API reports the isolated
database. The owner runs no command.

### P4. Prepare Direct Chat Demonstration

1. Confirm the selected Chat model is ready without revealing its credential.
2. Add seven clearly labelled synthetic passing comparisons and the required passing evaluation
   references to the isolated copy only.
3. Unlock the copied Vault for this process and call the real guarded activation endpoint for
   `direct_chat`.
4. Confirm the isolated status is `stage=direct_chat`, `rollback=false`, and every unrelated owner
   setting matches the backup snapshot.
5. Prepare, but do not yet resolve, one isolated approval Run and one isolated recoverable failed
   Run. Store their Run IDs in the private test worksheet.

## 6. Owner Test Script

Before T1, Codex must tell the owner the exact test URL to use for this run. Use that one URL for
T1-T7. If the URL is `8181`, `/api/health` must show the latest expected revision and the isolated
database path. If Codex explicitly moves the test to a main-gate URL such as `8090`, the owner must
not create disposable Project or Office data unless Codex confirms it is safe for that database.

### T1. Confirm Isolation - 5 Minutes

1. Open `http://127.0.0.1:8181`.
2. Confirm the browser address ends in port `8181`.
3. Open Projects and confirm familiar copied records are visible.
4. Do not open the normal port `8080` during this test.

Expected result: Mission Control looks normal and copied data is visible. Codex confirms in chat
that the process is using `.runtime-v2-test\agent.db`.

### T2. Experience Active Direct Chat - 10 Minutes

1. Open Chat.
2. Create a new session named `Runtime V2 Test`.
3. In the message box toolbar, set the mode selector to `Chat`. Do not leave it on `Agent`.
4. Turn off optional Web/connector chips for this test unless Codex explicitly asks for them.
5. Send: `Reply with exactly: RUNTIME V2 ACTIVE`.
6. Wait for the reply, then open Runs from the Operation navigation group.
7. Set Surface to `chat` and open the newest Run.

Expected result: Chat replies normally. One new Chat Run appears, reaches a successful state, and
contains ordered status/evidence events. It must not display the raw prompt.

If Chat replies but `Runs` with Surface `chat` shows `0 runs`, check the message you sent. If the
composer or reply metadata says `Agent`, the test was run in the wrong mode. Switch the mode selector
to `Chat` and repeat T2 before starting T3.

### T3. Inspect One Durable Run - 8 Minutes

Goal: prove the Chat Run from T2 is saved and can be inspected after refresh.

Start T3 only after T2 produced one visible Run with `Surface` set to `chat`. If the Runs list says
`0 runs`, stop and repeat T2 in `Chat` mode. Do not continue T3 with an Agent reply.

| Step | Owner action | Correct result |
|---|---|---|
| 1 | In the left sidebar, open `Runs` under `Operation`. | The Runs page opens. The connection label is `ready` or returns to `ready` after loading. |
| 2 | Set `Surface` to `chat`. | The list shows Chat Runs only. |
| 3 | Click the newest Run at the top of the list. | A detail panel opens for one Run. Copy or note the visible Run ID. |
| 4 | Click `Timeline`. | Events are listed in sequence order, from the smallest number to the largest. |
| 5 | Click `Trace`. | You can see labelled sections for model, policy, approval, receipt, recovery, and outcome. It is OK if a section says `None`. |
| 6 | Click `Evals`, then click `Context`. | Both tabs open without an error screen. Empty or `None` values are acceptable. |
| 7 | Refresh the browser with `F5`, return to `Runs`, set `Surface` to `chat`, and open the same Run ID again. | The same Run ID appears with the same event order. Refresh did not create a duplicate Run. |

Pass if: the same Run survives refresh, the event order is stable, and no duplicate Chat Run appears
just because the browser refreshed.

Fail if: the Run disappears, the event order changes, the page errors, or refresh creates a new Run.

### T4. See Other Surfaces In The Same History - 12 Minutes

Goal: prove Projects and Office can appear in Runs without replacing their normal behavior.

Do this test only on the isolated test URL unless Codex explicitly confirms the current database is
safe for disposable data.

| Step | Owner action | Correct result |
|---|---|---|
| 1 | Open `Projects` from the left sidebar. | The Projects page opens normally. |
| 2 | Create one project named exactly `Runtime V2 Test Project`. Put `temporary owner test` in any required text field. | The project is created or saved like a normal Project action. |
| 3 | Open `Office`. Create one clearly temporary item if the page offers a simple create action. If there is no obvious create action, stop and tell Codex `T4 Office action is not obvious`. | Office either creates the temporary item normally or Codex records that the owner should not guess. |
| 4 | Open `Runs`, set `Surface` to `projects`, and click the newest Project Run. | One Project Run exists and reaches a successful state. |
| 5 | Set `Surface` to `office` and click the newest Office Run. | One Office Run exists if an Office action was performed. |

Pass if: each action you performed still works normally and appears as one bounded Run.

Fail if: Projects or Office breaks, the action creates multiple Runs, or the Run exposes the full
body text instead of bounded labels and references.

### T5. Observe Approval And Same-Run Recovery - 10 Minutes

Goal: prove approval and recovery evidence update on the same Run instead of creating confusing new
history.

Important: in this test, `Codex` means this Codex task/session, not TOBI Chat inside Mission
Control. The Runs page is read-only for these actions, so the owner inspects while Codex performs the
prepared action.

| Step | Owner action | Codex action | Correct result |
|---|---|---|---|
| 1 | Ask this Codex session: `show prepared approval`. | Codex gives one Run ID. | You have one approval Run ID to inspect. |
| 2 | In Mission Control, open `Runs` and search or filter until that Run ID is selected. Open `Timeline` and `Trace`. | None. | The Run shows approval-related evidence and is not completed yet. |
| 3 | Ask this Codex session: `resolve approval`. | Codex resolves the prepared approval in the test database. | After browser refresh, the same Run ID shows the approval result. |
| 4 | Ask this Codex session: `show prepared recovery`. | Codex gives one recovery Run ID. | You have one recovery Run ID to inspect. |
| 5 | Open that recovery Run and note its current state. Then ask this Codex session: `resume prepared recovery`. | Codex resumes the prepared recovery in the test database. | After browser refresh, the same Run ID updates instead of a different Run replacing it. |

Pass if: approval and recovery update the original Run IDs.

Fail if: the Run ID changes, the old Run disappears, or the UI gives you an action button that does
not work.

### T6. Experience Rollback And Resume - 10 Minutes

Goal: prove Codex can switch only the test runtime back to shadow mode, then resume Direct Chat.

Important: do not run rollback commands yourself. Ask this Codex session to do them.

| Step | Owner action | Correct result |
|---|---|---|
| 1 | Ask this Codex session: `rollback now`. Wait until Codex says rollback is on. | Codex confirms the test rollback switch is on. |
| 2 | In Mission Control Chat, send `Reply with exactly: RUNTIME V2 ACTIVE`. | Chat still replies normally. |
| 3 | Open `Runs`, set `Surface` to `chat`, and inspect the newest Chat Run. | The new Run reflects rollback/shadow behavior, and earlier Runs did not change. |
| 4 | Ask this Codex session: `resume now`. Wait until Codex says rollback is off. | Codex confirms Direct Chat is active again. |
| 5 | Send `Reply with exactly: RUNTIME V2 ACTIVE` once more and inspect the newest Chat Run. | Chat still replies normally, and new Runs return to Direct Chat behavior. |

Pass if: Chat works before, during, and after rollback, and older Runs stay unchanged.

Fail if: Chat stops working, rollback affects older Runs, or Codex cannot prove the switch changed
back.

### T7. Check Privacy And Reconnection - 5 Minutes

Goal: prove Runs shows safe summaries, not private raw data.

| Step | Owner action | Correct result |
|---|---|---|
| 1 | Open the latest Chat Run, Project Run, Office Run, approval Run, and recovery Run available from T2-T6. | Each Run opens without an error screen. |
| 2 | In each Run, look through `Timeline`, `Trace`, `Evals`, and `Context`. | You see labels, states, timestamps, counts, model names, and evidence references. |
| 3 | Check for unsafe data: full Chat prompt, full Project or Office body text, API keys, tokens, provider raw error bodies, terminal output, or raw tool output. | None of those unsafe values are visible. |
| 4 | Refresh the browser once, then change the Surface filter twice. | The connection returns to `ready`, records do not duplicate, and selected data stays bounded. |

Pass if: only bounded labels and references are visible.

Fail if: any secret, full body text, raw prompt, raw provider error body, or raw tool output appears.

## 7. Owner Unexpected-Result Report

The owner reports only tests that did not match the expected result:

```text
Test ID:
What I clicked:
Expected:
What happened instead:
Approximate time:
Screenshot available: Yes/No
```

If every test matches, report: `T1-T7 matched expected results.`

## 8. Codex Deep Verification

After the owner's UI test, Codex must use isolated databases and deterministic fixtures to verify:

| Area | Required proof |
|---|---|
| Duplicate delivery | Identical request identity reuses one Run and one final action receipt |
| Concurrency | Two workers cannot own the same leased step |
| Restart | A checkpoint resumes the same Run after simulated process loss |
| Stale worker | Expired worker proof cannot commit success |
| Recovery | Retry limits, cancellation, and unknown outcomes fail safely |
| Security | Injection, secret, path, network, budget, and authority probes remain blocked |
| Rollout | Stage skips fail; seven-pass evidence is required; rollback affects only new work |
| Adapters | Recording failure never interrupts Projects, Office, CLI, Telegram, or scheduler work |
| Browser | Desktop and mobile Runs views have no overlap, horizontal overflow, or console errors |

Codex reports `Passed`, `Failed`, and `Needs owner attention` counts plus the exact failing test IDs.

## 9. Cleanup And Restoration

1. Stop only the test-owned API process.
2. Confirm ports `8181` and `8100` are released.
3. Re-read the live database Runtime flags and compare them with the pre-test snapshot.
4. Confirm no live owner setting or live Runtime row changed during the test.
5. Keep the isolated database until the owner accepts the report; delete it only with explicit
   approval.
6. Do not commit logs, database files, screenshots containing private data, or synthetic evidence.

## 10. Completion Standard

The experience test is complete only when T1-T7 have an owner result, all deep checks are reported,
the live state comparison is clean, rollback and resume are proven in the isolated copy, and every
unexpected result has a concrete follow-up owner decision.

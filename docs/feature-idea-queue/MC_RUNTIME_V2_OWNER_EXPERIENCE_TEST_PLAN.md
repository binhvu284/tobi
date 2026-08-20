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
3. Send: `Reply with exactly: RUNTIME V2 ACTIVE`.
4. Wait for the reply, then open Runs from the Operation navigation group.
5. Set Surface to `chat` and open the newest Run.

Expected result: Chat replies normally. One new Chat Run appears, reaches a successful state, and
contains ordered status/evidence events. It must not display the raw prompt.

### T3. Inspect One Durable Run - 8 Minutes

1. Open Timeline and read the events from lowest sequence to highest.
2. Open Trace and confirm model, policy, approval, receipt, recovery, and outcome sections exist,
   even when some sections say `None`.
3. Open Evals and Context.
4. Refresh the browser once and reopen the same Run.

Expected result: the same Run ID and event order remain. Refresh does not create duplicate events.
Connection returns to `ready` after loading.

### T4. See Other Surfaces In The Same History - 12 Minutes

1. Open Projects and create `Runtime V2 Test Project` with clearly disposable test content.
2. Perform one clearly labelled Office action, such as creating a test artifact or mission.
3. Return to Runs and filter Surface to `projects`.
4. Open the newest Project Run, then repeat with Surface set to `office`.

Expected result: each UI mutation creates one passive successful Run. Projects and Office still
behave through their existing owners; Runtime records bounded operation and outcome references.

### T5. Observe Approval And Same-Run Recovery - 10 Minutes

1. Tell Codex `show prepared approval` and open the Run ID it provides.
2. Inspect its Trace and Timeline.
3. Tell Codex `resolve approval`, then refresh that same Run.
4. Tell Codex `show prepared recovery`, open the second Run ID, and note its failed/recovering state.
5. Tell Codex `resume prepared recovery`, then refresh the same Run.

Expected result: approval and recovery evidence update under the original Run IDs. The current Runs
page is read-only, so Codex performs the commands. Missing Runs-page action buttons are a known
frontend limitation and are not an unexpected test result.

### T6. Experience Rollback And Resume - 10 Minutes

1. Tell Codex `rollback now` and wait for confirmation that the isolated rollback switch is on.
2. Return to Chat and send the same exact prompt from T2.
3. Confirm Chat still replies, then inspect the newest Chat Run.
4. Tell Codex `resume now` and wait for the isolated rollback switch to return off.
5. Send the prompt once more and inspect the newest Chat Run.

Expected result: Chat remains usable throughout. New work returns to shadow behavior during
rollback and returns to the approved Direct Chat stage after resume. Earlier Runs do not change.

### T7. Check Privacy And Reconnection - 5 Minutes

1. Inspect every visible field in the latest Chat, Project, Office, approval, and recovery Runs.
2. Look for the Chat prompt, Project/Office body text, credentials, provider errors, or tool output.
3. Refresh Runs and change filters twice.

Expected result: only bounded labels, states, timestamps, counts, and evidence references appear.
No raw body or secret is visible, and filtering/reconnection does not duplicate records.

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

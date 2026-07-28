# Handover — Developer module / #22 Coding Agent V2

**Written:** 2026-07-28, end of session
**Author:** Claude (Opus 5), working as the owner's agent in Mission Control
**For:** the next agent (Codex) picking this up
**Branch:** `main`, all work pushed. HEAD at handover: `90684d7`.

---

## 0. Read this first

**One live blocker stands between #26 and the first real delivery.** Section 4 has it, with a
diagnosis that is 90% confirmed and the single command that settles the rest. Everything before
that is context; everything after is backlog.

**The working principle of this whole session, and the thing to keep:**

> A run must prove its preconditions *before* an implementer is spent, not discover them
> halfway through delivery.

Six of the eight defects below were found by burning a full agent sprint and reading the crash.
Each fix therefore came in two halves: repair the thing, *and* move the discovery of that class
of problem into preflight where it costs nothing. Please keep doing the second half.

**Verification discipline in force.** Every guard test in this session was run against the
pre-fix code and confirmed to fail. A test that cannot fail is not a guard, and I have written
one by accident in this codebase before. Do the same and say so in the commit.

---

## 1. Where #22 actually stands

`#22 Coding Agent V2` is implementation-complete; it closes only on the ten-run acceptance
matrix in [`docs/feature-idea-queue/TOBI_CODING_AGENT_V2_COMPLETION_ACCEPTANCE_2026-07-22.md`](feature-idea-queue/TOBI_CODING_AGENT_V2_COMPLETION_ACCEPTANCE_2026-07-22.md)
plus owner browser acceptance. **#21 Mission Control Infrastructure V2 is blocked on that.**

| # | Scenario | State |
|---|---|---|
| 1 | MC Native happy path | Pending |
| 2 | Codex happy path | **Partial** — local half done (run 15); push/PR half blocked, see §4 |
| 3 | OpenCode happy path | Pending |
| 4 | Protected-path approval | **Passed** 2026-07-28 (deterministic) |
| 5 | Invalid agent preflight | **Passed** 2026-07-28 (deterministic) |
| 6 | Fallback agent switch | Pending — needs a live mid-run failure |
| 7 | Backend restart resume | Pending — needs a restart mid-run |
| 8 | Hung worker recovery | Pending — needs a hung worker |
| 9 | Main drift or conflict | Pending — needs a deliberate conflict |
| 10 | Auto classification | **Passed** 2026-07-28 (deterministic) |

Started the session at **0 real passes**. 4, 5 and 10 were provable without spending agent time
because they test decisions made *before* any agent starts; the six still pending genuinely need
a live worker and a real failure condition, and should not be faked.

**Closure rule (the owner's, verbatim):** *"A run is not a pass when it requires direct database
repair or an undocumented manual workaround."*

### Run history

| Run | Item | Outcome |
|---|---|---|
| 1–9 | various | canceled — see the defect log |
| 10 | #26 | `locally_complete`, but the reviewer passed it **without the evidence it demanded**; not counted |
| 11–14 | #25 | canceled/paused at review |
| **15** | **#25** | **First end-to-end local completion.** All 7 then-permitted gates green, merged to main as `e4f1c4a` |
| 16 | #26 | Work correct, all 4 checks pass, **blocked at review** — §4 |

---

## 2. What shipped this session

29 commits. Grouped by the problem each solved. Full detail for every defect is in the
acceptance doc's "Defects found during acceptance" section — **read D12–D19 there before
touching this code.**

### The contract between backend and frontend

| Commit | Change |
|---|---|
| `5f0259a` | The workflow state vocabulary lived in **7 copies**. Now one authority: [`core/coding_states.py`](../core/coding_states.py), a generated TS mirror `dashboard/src/developer.states.ts`, and a drift test that fails if they diverge. **Never add an eighth copy.** |
| `266a5e9` | Deleted 696 LOC of dead frontend; merged the split `pages/`/`components/` developer trees |
| `12c34ed` | Progress is **derived**, not a hardcoded integer per stage. 100% only when the result is reachable (owner's definition: *"when I could try, test, use the result or check github"*). Keyed on the **commit gate**, never `head_sha` — `prepare` seeds `head_sha` with `base_sha`, which made 3 canceled runs read 100%. |
| `df18e21`, `0729f88` | History derives progress too; items that ran but did not ship are reachable again |

### Runs getting permanently stuck (D12–D15, D17)

Each of these looked identical to the owner: press Retry, get the same failure, forever.

- **D12** — Windows 32,767-char command-line limit. Checkpoint handoff inflated the launch
  command past it; the error surfaced as `FileNotFoundError`. Fixed by feeding the prompt on
  **stdin** (`codex exec -`) and trimming the handoff 44,387 → 285 chars. (`2d88759`)
- **D13** — A failed run resumed the *same poisoned* agent session and failed identically. Now
  falls back to a fresh session. Also stripped PowerShell CLIXML from error surfaces. (`b1d49a4`)
- **D14** — My own refactor broke a monkeypatch seam. **Re-exporting a name restores attribute
  access but NOT a patch point**; patch where it is *defined*. This bit three times. (`e61f9d5`)
- **D15** — Retrying a quality-gate failure re-ran the same gate on unchanged code. Those
  failures now reopen the **code** stage. (`05cb75a`)
- **D17** — *A passing check killed the run that produced it.* `tests/test_awakening.py` ends
  with an emoji; the console locale is **cp1258**; `subprocess.run(text=True)` decoded with it,
  the reader thread died, `stdout` came back `None`, and `None + str` was a `TypeError`. Fixed by
  pinning `encoding="utf-8", errors="replace"` everywhere in the pipeline. (`5ae1ac5`)

  Two more found in the same trace, both in `5ae1ac5`:
  - **Every changed path lost its first character.** `git status --porcelain -z` records are
    `"XY PATH"`; an unstaged edit's status is `" M"`; `_run` returned `stdout.strip()`, eating
    the leading space. Run 15 recorded `ore/awakening.py`. **This is security-relevant** —
    `changed_files()` feeds `assert_write_paths`, so a truncated `core/coding_agent.py` stops
    matching the protected entry guarding it.
  - **`internal_error` discarded the traceback**, reporting only the exception class name.
    Finding that `TypeError` cost a full agent run. Tracebacks are now kept as an event and an
    artifact.

### The evidence loop (the structural one)

`92db816` — **The root cause of runs 9–14.** Acceptance criteria were authored independently of
validation commands, so a criterion naming `tests/test_awakening.py` could never be evidenced —
the pipeline never ran that file. Six of six runs with test-naming criteria were unpassable from
authoring.

Two halves:
- **(A)** Validation commands are now **derived from the criteria** — [`core/coding_criteria.py`](../core/coding_criteria.py) `derive_checks()`.
- **(B)** Preflight **refuses** an item whose criteria no configured check can evidence.

Run 15 was the first run where the criteria-named check actually executed, and the reviewer
qualified it *citing that evidence by name*.

### Preflight prerequisites (the pattern to continue)

| Commit | Blocker added | Catches |
|---|---|---|
| `7229b97` | `github_app_unconfigured` | capability on, Coding App not configured — would push a branch then dead-end on PR creation |
| `35953c6` | `reviewer_model_unconfigured` | reviewer has no model — run 16 spent **two** Codex sprints discovering this |

Both are **system blockers** (see `CodingAgent.start_next_queued`): they reject every item
identically, so Auto stops rather than walking the queue reproducing one failure. Item-scoped
blockers (scope, dependencies, protected paths) only skip that item.

### Integration diagnosis

- `7e9fb0b` — every connector test caught bare `Exception` and returned *"check your
  connection"*, hiding 404s, 401s, `PolicyDenied`, and invalid PEMs. `_reason()` now appends the
  real cause. **This is why three correct GitHub App credentials could not be saved and Update
  looked like a dead button.**
- `44914b9` — the Coding App private key is a multi-line `.pem` entered in a **single-line**
  field. `normalize_private_key()` rebuilds it from the base64 body; all 8 paste variants now
  load. `describe_private_key()` names the real failure (Client ID pasted, truncated paste,
  encrypted key) **without ever echoing key material** — there is a test asserting that.
- `79ac085` — **D19**, see §4.

### Performance

| Commit | Before | After |
|---|---|---|
| `1b37634` | `/overview` 5.23 MB, 997 ms, ~500 queries across 50 connections | 15.3 KB, 117 ms |
| `90684d7` | `/storage` **9,695 ms** to return 421 bytes — walked 410 MB of worktrees with `rglob`+`stat` on every 5-second poll | 1,327 ms cold (scandir), **15 ms** warm (120 s TTL) |

Whole page, all eight endpoints sequentially: **~10 s → 2.3 s cold / 1.2 s warm** against a
15,000 ms budget. Both have byte/time budget tests so the regression cannot return silently.

### UI

`81f005b`, `c18eb24` — the owner's standing complaint was that **every backend fix lost the
loading affordance**. Shared primitives now own the guarantee:
[`dashboard/src/components/async-ui.tsx`](../dashboard/src/components/async-ui.tsx) —
`ActionButton` / `BusyOverlay` / `ActivityBar` / `SectionSkeleton`, chosen by blast radius.
`tests/test_ui_loading_states.py` scans all 136 `.tsx` files and fails the build if any async
control ships without one. **Re-run it after every endpoint or handler-signature change** —
CLAUDE.md now mandates this.

---

## 3. Delivered outside the matrix

**#25 Awakening external read requires verified test evidence** — written by run 15 (Codex),
merged `e4f1c4a`, queue row updated.

`_connector_states` now requires connector readiness **and** fresh successful vault test
evidence. A token that is dummy, expired, revoked, or merely untested reports `partial`.
Verified in production against the live server: GitHub, Notion and Google all hold valid tokens
and show "Connected", but **only GitHub — the one with a fresh test — reports verified.** Under
the old code all three counted.

Freshness reuses the existing 24 h `AWAKENING_CONNECTOR_TTL_HOURS` window.

---

## 4. THE LIVE BLOCKER — start here

**Symptom:** #26 (run 16) stops at the review gate with
`Independent coding review is unavailable: AuthenticationError`. Progress 44%, 4/9 gates.

**The work itself is correct and complete.** `tests/test_task_classifier.py` exists, covers all
seven classify outcomes with ASCII-only inputs, the 60-character smalltalk boundary, and
coding-over-project precedence. All four validation commands pass, including the criteria-derived
`python tests/test_task_classifier.py` (22 checks). Only the reviewer is failing.

### What is already ruled out

| Ruled out | Evidence |
|---|---|
| Stale MC process | MC started 18:51:30; the Codex fix `79ac085` landed 18:18:50. It **has** the fix. |
| Wrong default model | `llm_config.updated_at` = 18:33 local, 20 min **before** the 18:53 run. Already `codex:gpt-5.6-sol`. |
| Config caching | `load_llm_config()` reads the DB on every call. No cache. |
| The model itself | A fresh process with identical config calls `get_llm("coding_review")` and gets `'ok'` back. Chain is a single `CodexClient:gpt-5.6-sol`. |
| Expired CLI credentials | `~/.codex/auth.json` token is valid for another **91 hours**; account id present. |

### The diagnosis (high confidence, one step from proven)

**The server and my CLI use different Codex tokens.**

`CodexClient.__init__` resolves auth in this order:

```python
token = api_key or os.getenv("CODEX_ACCESS_TOKEN") or os.getenv("CODEX_API_KEY")
if not token:
    token = self._read_codex_auth()      # ~/.codex/auth.json — the CLI's live, rotating token
```

- **My CLI process:** no `CODEX_ACCESS_TOKEN` in the environment → falls through to
  `auth.json` → fresh token → **works**.
- **The MC server:** `vault.inject_env()` runs at boot and puts the vault's
  `CODEX_ACCESS_TOKEN` into `os.environ` → `CodexClient` takes it and **never reaches
  `auth.json`** → 401.

The vault's `CODEX_ACCESS_TOKEN` is marked `test_status=untested` and has never been validated.
ChatGPT session tokens rotate; the Codex CLI keeps `auth.json` refreshed, but the vault copy is
frozen from whenever it was pasted.

This also explains the shape of the whole problem: **the Codex CLI worker kept succeeding while
review could not start.** The CLI is a separate binary with its own auth; only the in-process
library client reads the vault-injected variable.

### The command that settles it

The vault is locked to a bare CLI process (`VaultLocked`), so run this **inside the server
process**, or unlock first. Compare the two tokens' `exp` claims — do **not** print the tokens:

```python
import os, json, base64, time, sqlite3
from core import vault
from core.llm_clients.codex import CodexClient

def exp(tok, label):
    p = tok.split(".")[1]; p += "=" * (-len(p) % 4)
    e = json.loads(base64.urlsafe_b64decode(p)).get("exp")
    print(label, time.strftime("%Y-%m-%d %H:%M", time.localtime(e)), "expired" if e < time.time() else "valid")

exp(CodexClient._read_codex_auth(), "auth.json ")
vault.inject_env(sqlite3.connect(".tobi/agent.db"))
exp(os.environ["CODEX_ACCESS_TOKEN"], "vault     ")
```

### Suggested fix, in order of preference

1. **Prefer the live source when the stored one is stale.** In `CodexClient.__init__`, if
   `auth.json` holds a token whose `exp` is later than the environment's, use `auth.json`. A
   rotating credential should not be shadowed by a frozen copy of itself.
2. **Fall back on 401.** Catch `AuthenticationError` on the first call and retry once with
   `_read_codex_auth()`, the same shape as the D13 poisoned-session fallback in
   `core/coding_workers.py`.
3. **Owner action / immediate unblock:** delete `CODEX_ACCESS_TOKEN` (and `OPENAI_API_KEY` if
   unused) from the vault so `auth.json` is used. Verify first — do not delete a credential the
   owner may need elsewhere.

**Then extend preflight**, per the working principle: `reviewer_model_problem()` in
[`core/coding_review.py`](../core/coding_review.py) validates that a model *is configured and in
the catalog*, but not that it *authenticates*. A cheap live probe there — or reuse of the
connector test's freshness evidence — would have caught this before either sprint was spent.
That is the third time this session the same lesson appeared.

### One more trap, already documented

`codex:gpt-5.6` is offered by `available_models()` but the backend rejects it:
*"not supported when using Codex with a ChatGPT account."* It is platform-API-only. The owner
selected exactly that one first, on my recommendation — I read it from the catalog without
testing the call. **The catalog advertises models a subscription account cannot use.** Verified
working on this account: `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.5`, `gpt-5.4-mini`.

---

## 5. Environment — read before running anything

These are load-bearing and each one cost real time to learn.

- **`DB_PATH`.** The server loads `.env`; a bare `venv/Scripts/python.exe -c ...` does **not**,
  and silently defaults to an empty DB on C:. The live database is
  `.tobi/agent.db` — note `.tobi/developer/development.db` exists but is **0 bytes and a decoy**.
- **Restart semantics.** MC is uvicorn on port **8090**, no `--reload`. `dashboard/dist` is
  served from disk per request, so a frontend rebuild needs no restart — **any `core/` or `api/`
  edit does.** Several apparent failures this session were an un-restarted server.
- **Console is cp1258.** It cannot *print* emoji and — the expensive half — cannot *decode*
  them from a subprocess. Always pass `encoding="utf-8", errors="replace"` and treat streams as
  `(x or "")`. See D17.
- **Windows command line caps at 32,767 chars** and `_platform_cli_command` inflates ~3.7×
  (base64 → UTF-16LE → base64). Prompts over ~8,800 chars cannot launch. See D12.
- **A background auto-committer commits to `main` between pushes.** Always
  `git fetch origin main` and check `main..origin/main` is empty before pushing. It has swept
  uncommitted WIP before — and I swept *its* WIP into one of my commits this session
  (`6559f20` carries three unrelated storage files; the work is sound, the label is wrong).
- **`git checkout --` is blocked** by the policy's forbidden-arguments list and by the harness
  classifier. To restore a file, read it from `git show HEAD:<path>` and write it back.
- **Never** print `.env`, vault, OAuth, token or key values.
- **Do not run `main.py start` casually** — it starts Telegram and scheduled work.

### Test suites

Node-style scripts (`python tests/<name>.py`, non-zero exit on failure):

```
test_coding_agent              test_developer_states_sync     test_criteria_evidence
test_coding_agent_v2           test_coding_worker_actions     test_developer_recovery
test_developer_queue           test_developer_overview_budget test_developer_storage_budget
test_check_output_decoding     test_github_app_credentials    test_integration_test_reasons
test_codex_client_backends     test_ui_loading_states         test_awakening
```

Pytest: `test_acceptance_scenarios`, `test_coding_agent_completion`, `test_developer_process`,
`test_coding_agent_production`.

**All green at handover.** `tests/test_awakening.py` aborts at the first failure, which masked
D14 for an entire refactor — worth changing to report all failures.

### A trap in the test fixtures

Several suites loaded `config/coding_policy.v1.json` and inherited whatever capabilities and
Models config the machine happened to have. They broke twice this session — once when `github`
was enabled, once when the reviewer-model check was added — because they were **reporting the
owner's configuration instead of the behaviour they claim to cover**. They now pin
`github`/`merge`/`deploy` explicitly and stub `reviewer_model_problem`. If you add a preflight
check that reads machine state, expect to do the same, and pin it rather than weakening the
check.

---

## 6. Policy state

`config/coding_policy.v1.json` — hash `69547069b4287f51549e314d7069238f6a90a148577e4824a78bd8724611e9cb`.

```
observe            true
sandbox            true
external_workers   true
github             true      <- enabled 2026-07-28, Coding App verified
merge              false     <- deliberate
deploy             false     <- deliberate
```

**9 of 11 gates permitted** (`merge_deploy` and `health` excluded). `github` lets a run push its
branch and open a **draft** PR the owner can read and close. `merge` would change `main` and
`deploy` would ship; neither has been demonstrated by a single run, so they stay off. Earning
them one at a time is the point of three separate flags.

Editing this file changes `policy_hash` and **invalidates every in-flight run** — check none are
live first. It is also a protected path.

---

## 7. Backlog

**Blocking #26 / scenario 2**
1. §4 — the Codex token source.
2. Then Retry #26; it should clear review → commit → scan → **push → draft PR**. First write to
   the real `binhvu284/tobi`; blast radius is a branch and a draft PR.

**Acceptance**
3. Scenarios 1, 3, 6, 7, 8, 9 — all need live runs with real failure conditions.
4. Scenario 2's PR half, once §4 clears.

**Housekeeping**
5. **410 MB across 14 worktrees**, mostly from cancelled runs. System tab → cleanup.
6. Junk queue items `#900000001`–`#900000004` — remove via the Off-queue modal.

**Performance (page now at 1.2 s warm; not urgent)**
7. `/goals` calls `work_state()` and builds **136 KB** for a payload the page reads one field
   of. Biggest remaining per-poll cost at ~450 ms, alongside `queue_state()` at ~455 ms.
8. The page fetches **all eight endpoints for every tab**; only Overview and Process need
   polling. Split into per-tab loaders.
9. `refreshOverview()` triggers the full eight-endpoint fan-out on every `stage_*` event.
10. `activeIsTerminal` sits in the stream effect deps (`pages/Developer.tsx:197`); when a run
    goes terminal the effect tears down, calls `setEvents([])` and reconnects from sequence 0 —
    refetching the whole event log at the exact moment nothing more will arrive.

**Quality**
11. `test_awakening.py` should report all failures, not abort at the first.
12. The review stage stores only `{"error_code": ...}`; the reviewer's actual reasoning survives
    only in the on-disk artifact. Persisting it would let both the owner and the correction pass
    see *why* a run failed. (This was "Fix C" in the original plan and is still undone.)

---

## 8. Owner working agreements

- Open every reply with `**<item ID or task type> | <progress>% complete**`.
- **Keep chat reports short and plain.** The owner wants the whole picture, not the detail —
  detailed writing belongs in the repo, like this file. Explain any unavoidable jargon.
- Do not claim an integration is connected from code presence alone; use current status
  evidence.
- Report outcomes faithfully: if a test fails, say so with the output; if a step was skipped,
  say that.

---

*Everything asserted here was verified against the live database, the running server, or a real
subprocess at the time of writing. Where something is a hypothesis rather than a fact — §4's
token diagnosis is the only one — it is labelled as such and paired with the command that
settles it.*

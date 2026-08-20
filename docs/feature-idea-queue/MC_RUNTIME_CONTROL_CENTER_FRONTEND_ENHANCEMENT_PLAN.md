# Mission Control Runtime Control Center Frontend Enhancement Plan

## Document Control

| Field | Decision |
|---|---|
| Related foundation | `#21 Mission Control Infrastructure V2` |
| Proposal | Enhance the existing `/runs` page into the Runtime Control Center |
| Status | Draft for owner and Claude Fable 5 review; implementation is not authorized |
| Product priority | Owner control and trust |
| Change size | Major focused enhancement inside the existing Runs experience |
| Core UI posture | Frozen; preserve the current Mission Control shell and primary Runs layout |
| Authority | No review suggestion or code change is accepted until the owner approves it explicitly |

## 1. Product Outcome

The enhanced Runs page must answer five questions without requiring the owner to understand backend
internals:

1. What is TOBI doing now?
2. What needs my decision?
3. Why did this Run stop, fail, or wait?
4. What evidence proves what happened?
5. Can I safely approve, retry, resume, cancel, activate, or roll back?

This is not a redesign of Mission Control. It adds useful Runtime controls and upgrades outdated
technical presentation inside the existing Runs route, layout, and visual language.

## 2. Non-Negotiable Core Freeze

The following product surfaces are frozen for this proposal:

| Frozen area | Rule |
|---|---|
| Mission Control shell | Do not replace or restructure the global shell |
| Sidebar and navigation | Do not rename, reorder, remove, or regroup navigation items |
| Route structure | Keep `/runs`; do not add a new top-level Runtime route |
| Workspace tabs | Do not change their model, placement, or behavior |
| Global design system | Do not replace typography, spacing, colors, borders, theme tokens, or motion rules |
| Other pages | Do not redesign Chat, Projects, Office, Developer, Dashboard, or any unrelated page |
| Runs primary layout | Preserve the current header, filters, run list on the left, and selected Run detail on the right |
| Runs information model | Preserve Timeline, Trace, Evals, and Context; enhance them rather than remove them |
| Existing behavior | Do not remove current filters, pagination, reconnect behavior, loop selection, or empty/error states |
| Legacy runtime | Do not delete or bypass any rollback path, legacy table, or compatibility adapter |
| External services | Do not add Supabase, Vercel, analytics, telemetry, or third-party frontend services |
| Dependencies | Do not add a UI framework, chart library, state library, or icon library |
| Morpheus | Do not touch any Morpheus source, route, styling, asset, or build work |

Any reviewer recommendation that conflicts with this table is automatically out of scope. It must
be written as a separate optional proposal and cannot enter implementation without new owner
approval.

## 3. Allowed Change Boundary

### 3.1 Files That May Change After Approval

| Area | Allowed files or location | Purpose |
|---|---|---|
| Existing Runs page | `dashboard/src/pages/Runs.tsx` | Keep the current layout and compose enhanced Runtime elements |
| Runtime UI elements | `dashboard/src/components/runtime/` | Add status, attention, recovery, approval, rollout, and evidence components |
| Runtime frontend data | `dashboard/src/api.runtime.ts`, `dashboard/src/stores/runtime.ts` | Add typed projections, guarded commands, stream recovery, and filter state |
| Runtime API | `api/routers/runtime.py` | Add bounded owner-facing read and mutation endpoints |
| Runtime projection/service | `core/runtime/runs_view.py`, one optional new Runtime-only operator service | Derive overview, attention, available actions, and invoke accepted control owners |
| Verification | Runtime-focused backend, frontend source, and Playwright tests | Prove safety, behavior, layout, and rollback |
| Documentation | This plan and the Runtime V2 operations guide | Record approved behavior and exact delivered changes |

### 3.2 Files That Must Not Change Without Separate Owner Approval

- `dashboard/src/App.tsx`
- `dashboard/src/components/AppShell.tsx`
- `dashboard/src/index.css`
- theme, motion, workspace-tab, or global provider modules
- Chat, Projects, Office, Developer, Dashboard, or Morpheus page implementations
- non-Runtime API routers or core execution owners
- existing database tables or migrations

If implementation discovers that one of these files must change, work stops. The implementer must
write an amendment showing the exact file, exact behavior, reason, risk, test, and rollback before
the owner decides.

## 4. Exact UI Change Register

Only the following visible changes are proposed.

| ID | Existing element | Approved proposal to review | Preserved behavior |
|---|---|---|---|
| UI-01 | Runs title and connection label | Add a compact Runtime status strip below the existing header: active stage, rollback state, release gate, and data freshness | Existing title, icon, refresh button, and header position remain |
| UI-02 | Flat newest-first list | Add segmented views inside the existing left pane: `Needs me`, `Active`, `Failed`, `Completed`, and `All` | Existing list, selection, pagination, and left-pane width remain |
| UI-03 | Surface and status selects | Keep both selects and add bounded text search plus date range in the same filter band | Existing filters and backend values remain compatible |
| UI-04 | Basic Run rows | Add attention marker, elapsed time, step progress, and plain-language state to each row | Run ID, surface, mode, status, timestamp, and click behavior remain |
| UI-05 | Technical detail heading | Add a compact stage rail and a one-sentence server-derived explanation under the existing Run heading | Existing detail position and metadata remain |
| UI-06 | Read-only detail | Add one collapsible action band for server-approved approval/recovery commands | No action is guessed by the browser; existing detail stays readable when locked |
| UI-07 | Raw reference-heavy tabs | Keep Timeline, Trace, Evals, and Context names while grouping references by meaning and adding plain labels/tooltips | Existing evidence and tab order remain available |
| UI-08 | No rollout controls | Add a right-side drawer launched from the Runtime status strip for four rollout stages, blockers, activate, rollback, and resume | No permanent third column and no change to the primary two-column layout |
| UI-09 | Generic loading/error text | Upgrade loading, empty, reconnecting, stale-version, blocked-action, and Vault-locked states within current panels | Existing refresh and reconnect fallback remain |
| UI-10 | No safe fallback for new UI | Keep the current Runs view as the default fallback behind a dedicated default-off Runtime Control Center flag | `/runs` remains usable if the enhancement or API is unavailable |

No other visible change is part of this plan.

## 5. Layout And Visual Rules

1. Preserve the current desktop two-column grid: Run worklist left, selected Run detail right.
2. Preserve the current mobile behavior: the content remains single-column and no control may cause
   horizontal page overflow.
3. Use existing Tailwind utilities, color tokens, font scale, borders, and Lucide icons.
4. Do not add a hero, marketing copy, decorative background, illustration, nested cards, floating
   sections, gradient ornaments, or oversized headings.
5. Use full-width bands and bordered operational panels. Cards are allowed only for repeated Run
   rows, modal decisions, or a genuinely contained evidence item.
6. Keep button dimensions stable while loading. Use icons for refresh, close, retry, cancel, and
   rollback, with tooltips and accessible labels.
7. Use existing motion settings. Full mode may animate status changes with opacity/transform only;
   Reduced and Off must remain static.
8. Every label must fit at 390px mobile width and 200% browser zoom without overlap.

## 6. Owner Workflows

### 6.1 Find What Needs Attention

1. Owner opens `/runs` as today.
2. `Needs me` is selected automatically only when attention items exist; otherwise `All` remains the
   default to preserve current behavior.
3. Each attention row states `Approval needed`, `Recovery choice needed`, `Blocked`, or `Failed`.
4. Selecting the row opens the same existing detail area and highlights the relevant evidence.

Target: identify all owner-blocking work within 10 seconds and reach its evidence within two clicks.

### 6.2 Approve Or Reject

1. The action band appears only when the server returns a pending approval in `available_actions`.
2. The owner unlocks the Vault if needed.
3. The panel shows action name, target reference, risk, expiry, and the consequence of approval or
   rejection without showing secret or raw argument bodies.
4. Owner chooses Approve or Reject and confirms once.
5. The button waits for the server result; the page does not claim success early.
6. The same Run refreshes and the approval event appears in Timeline and Trace.

### 6.3 Retry, Resume, Or Cancel

1. The server offers only legal actions for the current version and state.
2. Retry and Resume show which step will continue. Cancel explains that active steps and loop work
   will stop.
3. Owner confirms; the browser sends the current Run version and an idempotency key.
4. A version conflict reloads the Run and explains that its state changed before the command.
5. Successful commands remain visible in the same Run history.

`skip_step`, `revise`, and `provide_input` are excluded from V1 because their payload and owner
experience are not yet defined strongly enough for safe generic controls.

### 6.4 Activate Or Roll Back

1. Owner opens the rollout drawer from the status strip.
2. Four fixed stages appear in order: Direct Chat, Read Chat, Actions, Agent.
3. Each stage shows comparison progress out of seven, release evaluation status, and exact blockers.
4. Only the next legal evidence-ready stage has an Activate button.
5. Activation requires Vault unlock and a confirmation naming the surface being changed.
6. Rollback is visible whenever any stage is active and requires one confirmation.
7. Resume rechecks all current evidence before restoring the approved stage.

## 7. Backend And Public Interface Changes

### 7.1 Read Projections

| Interface | Change |
|---|---|
| `GET /api/runtime/overview` | New bounded projection with status counts, attention counts, freshness, rollout state, release/autonomy gates, and Control Center flag |
| `GET /api/runtime/runs` | Add optional `q`, `from`, `to`, and `needs_attention`; keep current cursor, limit, surface, and status behavior |
| `GET /api/runtime/runs/{run_id}/snapshot` | Add bounded approvals, commands, available actions, step progress, elapsed time, and plain-language state explanation |
| `GET /api/runtime/runs/{run_id}/events` | Accept the Run's bounded string session ID so every current surface can reconnect; preserve sequence resume and duplicate prevention |

Search `q` is capped at 80 characters and matches only Run ID, request ID, session ID, safe label,
and surface. It never searches raw request/event bodies.

The dedicated fallback setting is `runtime.control_center_v1` in the existing `owner_settings`
table. It defaults to false, requires no schema migration, and is read only by the Runtime operator
service. False, missing, malformed, or unavailable always renders the current Runs experience.

### 7.2 Guarded Mutations

| Interface | Accepted input | Control owner |
|---|---|---|
| `POST /api/runtime/runs/{run_id}/commands` | `action`, `expected_version`, `idempotency_key` | Existing `RuntimeControl`; actions limited to `retry_step`, `resume`, `cancel` |
| `POST /api/runtime/approvals/{approval_id}/decision` | `decision=approve|reject`, `idempotency_key` | Existing `ApprovalService`; owner/session/authentication are derived server-side |
| Existing rollout activate endpoint | Next stage path value only | Existing `RolloutController.activate` |
| Existing rollout rollback endpoint | No body | Existing `RolloutController.rollback` |
| Existing rollout resume endpoint | No body | Existing `RolloutController.resume` |

Every mutation requires `X-Vault-Session`. The API must reject unknown action names, stale Run
versions, wrong owner/session identity, expired approvals, stage skips, insufficient evidence, and
changed idempotency content.

Mutation responses return the accepted command/decision identity and a fresh bounded snapshot. They
never return raw command payloads, prompts, responses, tool output, credentials, or provider errors.

## 8. Frontend Data Behavior

1. Load overview, first Run page, and selected Run snapshot together.
2. Stream events only for the selected Run. Reconnect from its last sequence.
3. Poll overview every 15 seconds and fall back to four-second selected-Run snapshots if streaming
   disconnects.
4. Deduplicate by event ID and sequence; never append an older event over newer state.
5. Keep filter and selected Run state in the URL so refresh/back navigation remains predictable.
6. The backend supplies `available_actions`; the UI never derives authority from status text.
7. Critical actions are never optimistic. Disable the pressed control, wait for the server, then
   display the verified result.
8. If the new overview/API fails, render the preserved current Runs experience and one truthful
   non-blocking status message.

## 9. Failure And Safety States

| Condition | Required behavior |
|---|---|
| Vault locked | History stays readable; all mutation controls are disabled with one Unlock action |
| Evidence gate blocked | Activation button is disabled and every blocker is listed in plain language |
| Version conflict | Reload the Run, keep the panel open, and explain that state changed |
| Duplicate click | Reuse the idempotency key and show one command result |
| API unavailable | Keep last verified data, show stale time, retry with bounded backoff |
| Event stream lost | Mark reconnecting, resume after last sequence, then reconcile with snapshot |
| Unknown backend value | Show `Unknown`, disable related action, and record a frontend error without raw data |
| Rollback active | Show persistent warning in the Runs header and keep Resume guarded by current evidence |
| Feature flag off | Render the unchanged current Runs experience |

## 10. Implementation Packages

### R00. Baseline Freeze And Owner Approval

- Capture desktop/mobile screenshots of the current `/runs` page in current themes and motion modes.
- Record current layout dimensions, filters, tabs, route, store behavior, API responses, and tests.
- Attach this exact UI change register to the Claude Fable 5 review.
- Do not write implementation code until the owner approves the final register.

### R01. Bounded Read Projections

- Add overview, attention filtering, enriched snapshots, all-surface reconnect, and contract tests.
- Keep mutations absent and the Control Center flag default off.
- Prove no raw body or secret can enter the new responses.

### R02. Read-Only Enhanced Runs

- Build UI-01 through UI-05, UI-07, UI-09, and the fallback in UI-10.
- Preserve the two-column layout and all existing tabs and filters.
- Verify build, desktop/mobile layout, theme modes, reduced motion, and API failure fallback.

### R03. Guarded Owner Actions

- Add approval, recovery, cancellation, rollout, rollback, and resume APIs and UI.
- Require Vault session, backend action availability, idempotency, current version, confirmation, and
  fresh result projection.
- Prove every denial and conflict is truthful and leaves the Run unchanged.

### R04. Owner Acceptance And Controlled Enablement

- Enable the Control Center flag only in an isolated database.
- Run the owner experience plan and fix only approved defects.
- Enable in the live local database only after owner visual acceptance and a clean rollback drill.
- Keep the old Runs experience available through the default-off flag until a later owner decision.

## 11. Verification And Acceptance

### Backend

- Contract and pagination tests for every new projection/filter.
- Vault-locked, wrong-session, expired-approval, stale-version, duplicate-command, and changed-content
  rejection tests.
- Stage-order, seven-pass evidence, release/autonomy gate, rollback, and resume regressions.
- Redaction probes covering prompts, response bodies, file/tool output, secrets, and raw errors.
- Existing #21 final gate remains `19/19` green.

### Frontend

- Source/component tests for overview, attention, filters, stage rail, action availability, and
  feature-flag fallback.
- Store tests for sequence deduplication, reconnect, stale snapshots, filter URL state, mutation
  pending state, and conflict reload.
- Production build with no new dependency.
- Playwright at 1440x900, 1024x768, and 390x844 for loading, empty, attention, active, blocked,
  approval, recovery, rollback, reconnecting, error, and fallback states.
- No console errors, inaccessible controls, clipped text, incoherent overlap, or page-level
  horizontal overflow at 200% zoom.

### Owner Acceptance

- Identify active work and every attention item within 10 seconds.
- Reach an approval or recovery action within two clicks after Vault unlock.
- Reach rollback within two clicks and never bypass confirmation.
- Understand why activation is blocked without opening logs or documentation.
- Refresh/reconnect without duplicate events or commands.
- Confirm visually that AppShell, navigation, routes, themes, motion, and other pages are unchanged.

## 12. Claude Fable 5 Review Protocol

Claude Fable 5 reviews this document before implementation under these rules:

1. Review is read-only. Do not edit source, plans, Queue status, routes, or generated assets.
2. Do not propose replacing the core shell, navigation, workspace model, theme system, global CSS,
   two-column Runs layout, or existing page workflows.
3. Evaluate product value, owner clarity, authority boundaries, API feasibility, failure behavior,
   visual fit, accessibility, performance, verification, and rollback.
4. Every recommendation must use this table:

| Field | Required review content |
|---|---|
| Change ID | Existing `UI/API/R` ID or a new `REV-##` ID |
| Exact surface/file | Where the recommendation applies |
| Current approved behavior | What this plan currently says |
| Proposed difference | Exact addition, removal, or wording change |
| Owner value | What becomes easier, safer, or clearer |
| Risk | What could regress or confuse the owner |
| Verification | Exact test or visual evidence required |
| Core-freeze impact | `None` or the exact frozen rule it conflicts with |

5. Recommendations with a core-freeze impact are automatically separate proposals.
6. The owner marks each recommendation `Approve`, `Modify`, or `Reject`.
7. Only approved recommendations may update this plan. No implementation begins until the owner
   approves the complete replacement change register.

## 13. Implementation Change Control

Before the first code edit, the implementation worker must publish an Approved Change Manifest
containing:

| Required field | Meaning |
|---|---|
| Approved change IDs | Exact UI/API/package IDs being implemented |
| Exact files | Every existing file expected to change and every new file expected |
| Visible difference | What the owner will see before versus after |
| Preserved behavior | What must remain identical |
| Data/API difference | Added endpoint or field, with no hidden contract change |
| Tests | Focused gate and browser states proving the change |
| Rollback | How to return to the current Runs experience |

More files touched than the approved manifest is a stop condition. The worker must not absorb an
unrelated cleanup, refactor, design-system change, or old-infrastructure migration into this item.

## 14. Explicit Non-Goals

- No Mission Control redesign.
- No new navigation destination.
- No global shell, theme, motion, or workspace-tab rewrite.
- No redesign of Chat, Projects, Office, Developer, Dashboard, or Morpheus.
- No new database authority or replacement Runtime engine.
- No legacy deletion.
- No unrestricted autonomous controls.
- No hidden configuration required for the page to remain usable.
- No production activation before owner visual acceptance and rollback proof.

## 15. Completion Standard

The proposal is ready for implementation only after Claude Fable 5 returns the required structured
review, the owner approves every accepted difference, the Approved Change Manifest is frozen, and
the implementation package names its exact files and gates. Delivery is complete only when all
backend/frontend checks pass, the owner confirms the core UI is unchanged, the isolated experience
test passes, and the fallback to the current Runs view remains proven.

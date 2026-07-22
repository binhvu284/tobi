# Brain Memory V2 - Operations and Rollback (#20)

Brain V2 is the typed, quality-gated owner-memory backend. The owner-facing
Mission Control Brain page keeps the proven legacy UI and its `/api/brain/*`
contract; when V2 is enabled, those routes translate to the V2 repository.
Legacy rows remain as rollback mirrors for non-sensitive memories.

## Owner Flags

Flags live in `owner_settings` and are managed through the existing owner
settings API.

| Flag | Values | Effect |
|---|---|---|
| `brain.v2_shadow` | `0`/`1` (fresh-install default `0`) | Legacy remains authoritative while Remember also evaluates/writes V2 best-effort data. |
| `brain.v2_enabled` | `0`/`1` (fresh-install default `0`) | V2 becomes authoritative for the Brain page, Remember, automatic sweep routing, Chat/Agent profile context, retrieval, and MCP/conductor recall. This flag wins over shadow. |

Fresh installations stay flag-dark per the approved rollout plan. The current
owner instance completed cutover on 2026-07-22 and runs with
`brain.v2_enabled=1`, `brain.v2_shadow=0`.

## Owner Surface

- Mission Control -> Brain (`/brain`) uses the established Brain UI.
- Old `/brain/legacy` and `/brain/v2` bookmarks redirect to `/brain`.
- The Add control keeps manual entry as its default action and exposes a small
  dropdown with `Add item manually` plus disabled `Tell TOBI (Soon)`.
- The existing Browse, Search, Review, Edit, Confirm, Delete, Import,
  Duplicate Cleaner, Narrative, and Ask Brain workflows keep their response
  shapes while V2 is authoritative.
- The advanced `/api/brain/v2/*` job and diagnostic APIs remain available for
  native import, migration, feedback, influence, cleanup, and operations.

## Compatibility Cutover

`core.brain_v2_compat.ensure_ready()` is additive and idempotent:

1. Reconcile linked V2 lifecycle states to the accepted legacy state once.
2. Migrate active/pending legacy rows without an existing `compat_ref`.
3. Copy owner-visible version history into V2 compatibility history.
4. Keep non-sensitive legacy rows synchronized as rollback mirrors.
5. Keep V2 authoritative after cutover; legacy writes made during rollback are
   reconciled when V2 is enabled again.

The cutover ledger is stored in `brain_v2_cutover_state`. Compatibility history
and conflict decisions are stored in `brain_memory_v2_versions` and
`brain_memory_v2_conflict_resolutions`.

## Sensitive Memory and Vault

- Sensitive canonical text, behavior implications, and evidence are AES-GCM
  encrypted in `brain_secure_payloads`.
- Plaintext columns and compatibility history use `[sensitive:redacted]`.
- Converting an existing memory to sensitive scrubs the live legacy mirror and
  both compatibility-history stores.
- A locked vault redacts sensitive UI reads, excludes them from LLM context,
  and maps blocked legacy-page writes to HTTP 423.
- Archive is reversible. Owner-confirmed V2 purge permanently deletes the
  selected memory and its protected payload; external backups may retain bytes.

## Rollback

Set `brain.v2_enabled=0` and `brain.v2_shadow=0` to restore the legacy Brain
backend. V2 rows remain intact. Re-enable `brain.v2_enabled=1` to reconcile any
accepted active/pending legacy writes and return to V2.

The live 2026-07-22 exercise verified:

| Check | Result |
|---|---:|
| Active legacy memories | 63 |
| Active V2 memories | 63 |
| Missing active/pending legacy links | 0 |
| Linked lifecycle mismatches | 0 |
| Rollback active count | 63 |
| Restored backend | `brain_v2` |

Pre-cutover backup:
`tobi/.tobi/backups/brain-v2-cutover-20260722-175640.db` (local/ignored).

## Verification

- New compatibility suite: `tests/test_brain_v2_legacy_compat.py` - 27 checks.
- Brain contracts/schema/repository/ingest/golden/remember/import/migration/
  retrieval/feedback/API/acceptance suites - 430 checks.
- Context/conductor adjacency suites - 44 checks.
- Total focused backend checks in the completion run: 501.
- Acceptance gates: precision 100%, active trash 0%, corrections 100%,
  security failures 0, cached context p95 about 140 ms, memory tokens 33.7%
  below legacy, retrieval proxy 100%.
- Dashboard `tsc && vite build` passes.
- Automated visual attachment was blocked by the local browser controller's
  bracket-path startup error; owner click-through remains the visual check.

## Maintenance

- Native V2 import uploads are encrypted and purged on commit/cancel; run
  `brain_import.expire_jobs()` to enforce the 24-hour abandoned-job TTL.
- Run `tests/test_brain_acceptance.py` before changing the rollout flag or
  retrieval weights.
- Keep all Brain V2 schema DDL centralized in `core/database.py`.
- Do not remove legacy tables or rollback mirrors without a separate approved
  deletion plan and a verified database backup.

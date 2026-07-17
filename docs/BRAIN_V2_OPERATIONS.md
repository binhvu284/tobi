# Brain Memory V2 — Operations & Rollback (#20)

The typed, quality-gated owner-memory system. Everything below is additive to the
legacy Brain: legacy `brain_memories` rows and `/api/brain/*` behavior are never
modified by V2.

## Flags (owner_settings — Settings page or `PATCH /api/owner/settings`)

| Flag | Values | Effect |
|---|---|---|
| `brain.v2_shadow` | `0`/`1` (default 0) | Remember runs legacy exactly as today AND writes a V2 copy alongside (`compat_ref` links the rows). Zero behavior change; builds real V2 data for evaluation. |
| `brain.v2_enabled` | `0`/`1` (default 0) | V2 authoritative: Remember routes through the quality gates (legacy compat row still written), and Chat/Agent context uses the V2 stable profile + ranked recall. Wins over shadow. |

**Rollback = turn the flag off.** `brain.v2_enabled=0` restores the legacy
context/remember path byte-for-byte (verified by `tests/test_brain_remember_v2.py`
and `tests/test_brain_retrieval.py`). No data is lost either way — V2 rows stay
in their tables and resume when re-enabled.

## Staged rollout (spec T13)

1. **Shadow** (`brain.v2_shadow=1`): run days-to-weeks. Watch `/brain/v2` Overview:
   pending queue growth, conflict count, and whether shadow rows look sane.
2. **Curate before flipping on**: the stable profile is built from ACTIVE
   memories — review the Library first (archive junk, approve good pending rows).
   Whatever is active goes into every turn's context.
3. **Chat on** (`brain.v2_enabled=1`): V2 profile + recall enter chat context.
   Verify tone/behavior for a few days; the `brain_recall` context item carries
   owner-visible chips.
4. **Agent surfaces** inherit the same flag (mode budgets: chat 6/1,200 tokens,
   agent 10/2,400).

## Sensitive memory & the vault

- Sensitive V2 memories exist only AES-GCM-encrypted (`brain_secure_payloads`);
  the plaintext column holds `[sensitive:redacted]`.
- Locked vault ⇒ sensitive memories are redacted in the UI and **excluded from
  LLM context entirely**; imports/migrations wait or fail closed (HTTP 423).
- Owner **purge** permanently deletes a memory + its encrypted payload
  (SQLite `secure_delete`); archive is the reversible alternative.

## Maintenance

- **Import temp data**: encrypted uploads are purged on commit/cancel; call
  `brain_import.expire_jobs()` (or any future scheduler hook) to enforce the
  24-hour TTL on abandoned jobs.
- **Cleanup center** (`/brain/v2` Overview): deterministic merge/archive/
  revalidate recommendations; nothing applies without per-proposal confirmation.
- **Acceptance gates**: `python tests/test_brain_acceptance.py` measures the spec
  release thresholds (precision, trash rate, correction accuracy, injection=0,
  p95 ≤300 ms, token increase ≤20%, retrieval proxy). Run before any flag
  promotion. Latest run: precision 100%, trash 0%, corrections 100%, failures 0,
  p95 ≈139 ms, memory tokens −33.7% vs legacy.
- **Test suites** (plain python, isolated temp DBs): `test_brain_contracts`,
  `_v2_schema`, `_repository`, `test_vault_payload`, `_ingest`, `_golden`,
  `_remember_v2`, `_import`, `_migration`, `_retrieval`, `_feedback`,
  `_v2_api`, `_acceptance`.

## Surfaces

- **UI**: Mission Control → Brain → **Brain V2** (`/brain/v2`): Overview /
  Library / Import / Migration / Ask Brain.
- **API**: `/api/brain/v2/*` (see `api/brain_v2.py`) — legacy `/api/brain/*`
  untouched.
- **Known limitation**: T06 migration maps legacy categories deterministically
  (no model inference, per spec) — e.g. legacy "identity" rules migrate as
  `identity` type. Retype/curate via the Library; the pending queue exists for
  exactly this.

# TOBI "Genesis Complete" — In-MC Integrations & Secrets Manager

> **Queue status:** 🔵 Built — awaiting owner verification (needs backend restart) · **Completes:** Evolution **Genesis (Tier 0)** · **Owner-reviewed:** 30 Q&A + code grounding below
> **Built:** `core/vault.py` (scrypt→AES-256-GCM, in-memory key + auto-relock, verifier; 14 unit tests), `core/database._ensure_vault_schema`, `core/integrations_registry.py`, 16 `/api/vault/*`+`/api/integrations/*` endpoints (session-token gated; full HTTP e2e passes), and `dashboard/src/pages/Integrations.tsx` (+ `api.ts`, nav, loader preset). `cryptography` added to requirements. Wizard + Health cross-link left as optional follow-ups.
> Part of the [Feature Development Queue](QUEUE.md). Builds a secure, in-Mission-Control way to configure, validate, and manage the API keys/tokens that gate Genesis — replacing today's `.env`-only setup.

## Context

Genesis (Tier 0) is defined in `api/dashboard.py` `_TIER_DEFINITIONS` and its abilities are auto-detected by `_detect_abilities()`. The abilities still gating completion are **API-key checks** read from the environment: `ANTHROPIC_API_KEY`/`OPENROUTER_API_KEY` (LLM + coding agent + cron + reports), `TELEGRAM_BOT_TOKEN` (bot), `GITHUB_TOKEN`, `NOTION_API_KEY`, `VERCEL_TOKEN`, `SUPABASE_URL`. Today these can only be set by hand-editing `.env` (`core/env_utils.safe_load_dotenv` + `os.getenv`) — there is **no in-MC way to configure them**.

The owner wants the **integration-configuration step to happen inside MC**, with a real **encrypted secrets vault** (this stores the most sensitive data in the system — API keys and tokens — so security is paramount). The outcome: configure keys in MC → abilities flip active → **Genesis completes**. The codebase already encodes the relevant principle that secrets are referenced by env-var *name*, never stored inline (agent `key_ref`, "D37").

This is framed as an **Integrations & Secrets manager** (Genesis completion is the result). Top priority: **frictionless connect/test** with security solid-but-unobtrusive.

## Decisions (from Q&A)

| Area | Decision |
|---|---|
| Framing | **Integrations & Secrets manager**; Genesis completes as a result |
| Secret storage | **Encrypted in local SQLite** (app-managed vault) |
| Unlock | **Master password** (KDF-derived key) |
| Process consumption | **Inject into `os.environ` on startup + reload endpoint** (live reload, no restart) |
| UI exposure | **Masked by default; revealable after re-entering the master password** |
| Access gate | **Session unlock** with master password (auto-relock on timeout) |
| Audit | **Full log**: create/update/delete/test/reveal, timestamped |
| .env | **Import into vault on first run; keep `.env` as fallback** |
| Catalog (v1) | Core **LLM + Telegram**, tools **GitHub/Notion/Vercel/Supabase**, **forward-looking placeholders** (Google/Gmail/Stripe), **generic custom secrets** |
| Validation | **Test-and-block-on-failure** via existing `core/integrations.py` `.test()` |
| OAuth | **API-keys now; OAuth integrations 'coming in Awakening'** (but store OAuth client id/secret types now) |
| Catalog design | **Registry-driven** (each integration = a config entry) |
| Placement | **New dedicated 'Integrations' page** in nav |
| Layout | **Status cards** (Connect/Test/Edit/Remove + abilities unlocked) |
| Guided flow | **Page + optional 'Complete Genesis' wizard** |
| Tier link | Each integration **shows abilities it unlocks + live Genesis %** |
| Completion bar | **All 12 Genesis abilities active** |
| Optionality | **Required vs optional split** per integration |
| Live update | **Re-run detection on save** → Evolution updates immediately |
| Celebration | **Tier-unlock animation + notification** (reuse Evolution FX + toast/`useSound`) |
| Apply changes | **Live reload (no restart)** |
| Backup | **Encrypted export/import** (password-protected) |
| Environments | **Env profiles (local / VPS)** |
| Lifecycle | **Track added/last-tested; auto-warn on failure/stale** |
| Secret types | **API keys/tokens, connection URLs, OAuth client id+secret, webhook/custom** |
| Health link | **Reuse Health deep-test in both places** |
| Errors | **Clear cause + how-to-fix / get-key link** |
| Prereqs | **LLM + Telegram surfaced as 'core prerequisites' first** |
| Scope | **Everything in v1** (phased internally) |
| North star | **Frictionless connect/test** (security solid, unobtrusive) |

## Security architecture (the heart)

- **Crypto:** Python `cryptography`. Master password → **KDF** (scrypt or argon2id, params + random salt stored in `vault_meta`) → 32-byte key. Each secret encrypted with **AES-256-GCM** (per-secret nonce). A **verifier** blob (encrypt a known token) lets us validate the password without storing it. The derived key is **held only in server memory** while the vault is unlocked, cleared on lock/timeout.
- **Unlock session:** `POST /api/vault/unlock` (master password) caches the derived key in memory + issues a short-lived session token; auto-relock after inactivity. Every vault endpoint requires the existing **`X-API-Key`** *and* an unlocked session.
- **Exposure:** list/status return only `last4` + metadata. Full value only via `POST /api/integrations/{id}/reveal` after re-entering the master password. Secrets are **never** logged.
- **Audit:** `vault_audit` records every create/update/delete/test/reveal with timestamp + integration (never the value).
- **Consumption:** on backend startup (or unlock), decrypt the active profile and overlay into `os.environ` (so all existing `os.getenv` calls keep working); `.env` remains a **fallback** for any key not in the vault. `POST /api/vault/reload` re-injects live so a new key works without restart.
- **Backup:** `export` produces a password-protected encrypted blob; `import` restores it (supports moving local↔VPS).
- **Recovery caveat:** losing the master password makes the vault unrecoverable by design — mitigated by encrypted export + a clear one-time warning at setup.

## Data model — new tables (`core/database.py`, idempotent `_ensure_vault_schema(conn)`)

- **`vault_meta`** — `id, kdf TEXT, kdf_salt BLOB, kdf_params TEXT, verifier BLOB, active_profile TEXT, created_at`.
- **`vault_profiles`** — `name PK ('local'|'vps'|…), label, created_at`.
- **`vault_secrets`** — `id, profile, name (env-var NAME), integration_id, secret_type ('api_key'|'url'|'oauth'|'webhook'|'custom'), ciphertext BLOB, nonce BLOB, last4 TEXT, test_status TEXT, added_at, updated_at, last_tested_at`. Unique `(profile, name)`.
- **`vault_audit`** — `id, ts, action, integration_id, name, ok, detail`.
- Reuse existing `evolution_snapshots` for tier state (already present).

## Backend work (`tobi/`)

1. **`core/vault.py`** (new) — `setup(master)`, `unlock(master)`, `lock()`, `is_unlocked()`, `get/set/delete_secret`, `list_secrets()`, `reveal(name, master)`, `export(pw)/import(pw)`, `inject_env()`, `reload()`, profile CRUD, audit writer. Owns all crypto.
2. **`core/integrations_registry.py`** (new) — the **registry**: each entry = `{id, label, category, fields:[{name, type, label, help_url}], test, abilities_unlocked:[ability_id], required|optional}`. `test` reuses `core/integrations.py` connectors (`NotionIntegration.test()`, `GitHubIntegration`, `VercelIntegration`, `SupabaseIntegration`) + LLM/Telegram pings. Core prereqs (LLM, Telegram) flagged first.
3. **Startup hook** — in `main.py`/`env_utils`: after vault unlock, `vault.inject_env()` overlays secrets onto `os.environ` (vault wins, `.env` fallback). First-run migration imports existing `.env` values into the vault.
4. **API endpoints** in `api/dashboard.py` (`_get_conn()` + Pydantic + `/api/*`; all gated by `X-API-Key` + unlocked session):
   - Vault: `POST /api/vault/setup`, `POST /api/vault/unlock`, `POST /api/vault/lock`, `GET /api/vault/status`, `GET /api/vault/audit`, `POST /api/vault/export`, `POST /api/vault/import`, `POST /api/vault/reload`, `GET/POST /api/vault/profiles`.
   - Integrations: `GET /api/integrations` (catalog + status + abilities + required/optional + Genesis %), `POST /api/integrations/{id}/connect` (save + test, block on failure), `POST /api/integrations/{id}/test`, `POST /api/integrations/{id}/reveal` (re-auth), `DELETE /api/integrations/{id}`.
   - `GET /api/evolution` (existing) re-runs `_detect_abilities()` so Genesis % updates live on save.

## Frontend work (`tobi/dashboard/src/`)

1. **Routing/nav** — register `/integrations` in `App.tsx`; nav item in `AppShell.tsx` (`Plug`/`KeyRound` icon); `PageLoader` preset `integrations`.
2. **`api.ts`** — types (`Integration`, `IntegrationStatus`, `VaultStatus`, `AuditEntry`, `Profile`) + functions for every endpoint.
3. **`pages/Integrations.tsx`** — `VaultUnlockGate` (setup/unlock with master password) wrapping the page; **Genesis progress header** (live %); **Core prerequisites** section (LLM, Telegram) first; **Tools** cards (GitHub/Notion/Vercel/Supabase); **Coming soon** locked cards (OAuth/Google/Gmail/Stripe); **Custom secrets**; **profile switcher**; **audit log** panel; **export/import**; optional **"Complete Genesis" wizard** (stepper through required keys).
4. **Components** — `IntegrationCard` (status pill, abilities-unlocked chips, Connect/Test/Edit/Remove, clear error + how-to-fix link), `SecretField` (masked + reveal-with-password), `VaultUnlockModal`, `GenesisWizard`, `AuditLogPanel`, `ProfileSwitcher`. Reuse `useToast`, theme tokens, `ConfirmTransitionModal` for destructive actions.
5. **`pages/Evolution.tsx`** — consume live `/api/evolution`; fire the existing **tier-unlock FX** (`.tier-unlock`/`ring-expand`) + toast + `useSound` when Genesis flips to complete.
6. **`pages/Health.tsx`** — surface the same per-integration live status (shared test logic).

## Genesis completion logic

- Registry maps each integration → `abilities_unlocked` and `required|optional`. Genesis "complete" = **all 12 abilities active** per `_detect_abilities()` (keys + `SOUL.md` + DB rows). The UI shows required vs optional so the owner sees exactly what's left; configuring a required key and passing its test re-runs detection and advances the bar live.

## v1 build phases (everything ships in v1, sequenced)

- **M1 — Vault core + security:** `core/vault.py` crypto, schema, setup/unlock/inject, `.env` import, audit. Unit-tested.
- **M2 — Registry + endpoints:** integration registry (reusing connectors), connect/test/reveal/remove APIs, live detection on save.
- **M3 — Integrations page UI:** unlock gate, prereqs-first cards, status/test/errors, Genesis % header, custom secrets, audit panel.
- **M4 — Genesis polish:** wizard, Evolution live update + tier-unlock celebration, Health reuse, profiles, export/import, lifecycle warnings.

## Verification (end-to-end)

1. **Backend:** `python main.py api`; first run **imports `.env`** into the vault; `vault_*` tables created.
2. **Setup/unlock:** set a master password; relock/unlock; wrong password rejected via verifier.
3. **Connect:** on the Integrations page, paste a GitHub token → **Test passes** → saved; a bad key is **blocked** with a clear how-to-fix message.
4. **Live reload + detection:** after connecting, the key works **without restart** (reload endpoint) and the **Evolution Genesis %** advances immediately; completing all required keys flips **Genesis → complete** with the **tier-unlock animation + toast**.
5. **Security:** list/status show only `last4`; reveal requires the master password; `vault_audit` logs each action; secrets never appear in logs/responses.
6. **Profiles + backup:** switch local↔VPS profile; encrypted **export then import** round-trips.
7. **Health:** per-integration live status matches on both Integrations and Health pages.
8. `cd tobi/dashboard && npm run build` clean; backend imports without error.

## Risks / watch-items

- **Master-password loss = unrecoverable vault** (by design) — mitigate with encrypted export + explicit setup warning.
- **Key in process memory / `.env` fallback plaintext** — acceptable for local-only; document it; vault is the source of truth.
- **Crypto correctness** — use vetted `cryptography` primitives (AES-GCM + scrypt/argon2); never hand-roll; cover with unit tests.
- **Live reload safety** — `inject_env()` must be idempotent and not clobber unrelated env; re-test integrations after reload.
- **Frictionless vs secure** — north star is low-friction; keep the session-unlock smooth, reserve re-auth for reveals/destructive actions only.
- **Reuse, don't duplicate** — build on existing `core/integrations.py` `.test()` methods, the Health deep-test, and the Evolution detection/FX already present.

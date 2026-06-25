# TOBI "Brain" — Long-term Owner Memory

> **Queue status:** 🟡 Queued · **Scope:** v1 (this doc) + v2 (deferred section) · **Owner-reviewed:** 30 Q&A captured below
> Part of the [Feature Development Queue](QUEUE.md). Addresses Vision Pillar 1 — "Understand me fully" (`../01_VISION.md`, ~20% → this is the next milestone per `../03_ROADMAP.md`).

## Context

TOBI's north-star is a personal Jarvis (`../01_VISION.md`). **Pillar 1 — "Understand me fully"** sits at ~20% and `../03_ROADMAP.md` explicitly calls for the missing pieces: a real user-profile *store* (not prose), memory-first retrieval, and auto-update from interactions. Today the only owner knowledge is a static `SOUL.md`, raw `conversations`, and `lessons` — there is **no structured, queryable profile TOBI maintains about its owner**. There is even a registered-but-unimplemented `memory` skill (`core/database.py` seed).

**Brain** is that layer: a secure, categorized, self-growing memory of who the owner is — facts, preferences, relationships, goals, habits, health, and a **deep psychology profile** — so TOBI can consult, decide, and act with genuine understanding. It grows two ways: (1) **auto-learning** from conversation, (2) **bulk import** of `.md`/`.json` personal context. A dashboard UI manages it (categorized cards, dedup, import-review).

This spec reflects 30 clarifying answers from the owner (summarized below).

## Decisions (from Q&A)

| Area | Decision |
|---|---|
| v1 build | Auto-learn **and** import, in parallel |
| Storage source-of-truth | **Recommend** → SQLite (MC DB) is canonical; Hermes-memory mirror deferred to v2 |
| Chat surface (v1) | **New dashboard Chat page** in Mission Control; Telegram learning → v2 |
| Approval | **Hybrid by confidence**; sensitive categories (Psychology/Relationships/Health) **always** reviewed |
| Categories | Comprehensive fixed set; TOBI may **propose** new ones for approval |
| Psychology | **Full depth** (values, comms/decision style, motivators, stressors, risk, cognition, triggers, defenses, blind spots) |
| Psych UI | Discrete cards **+ synthesized "TOBI's view of me" narrative** |
| Extraction | **Periodic background sweep** over unprocessed messages |
| Conflicts | **Flag for owner to resolve** |
| Freshness | Track **last-confirmed**, surface stale for re-check (no silent loss) |
| Import parsing | **Flexible LLM parse** of any shape → **split into atomic cards** |
| Import overlaps | **Auto-merge** overlaps (shown in review), **full per-card edit** before save, Save/Reject/Save-All |
| Dedup | **Semantic (embeddings)**; "Clean duplicates" shows **merge preview to confirm** |
| Embeddings | **Local / on-device**, stored in v1 (enables semantic search + dedup) |
| Versioning | **Full version history** per memory |
| Retrieval into chat | **Always-on synthesized summary + top-k semantic retrieval** |
| Security | **Local-only**, OS-level (no app-level encryption in v1) |
| Memory-first | **Wire into the dashboard chat now** |
| Brain page UI | **List rows (1/line)**, category **tabs**, **filter** button, **search** bar, **color-coded** categories, rich metadata cards |
| Detail/edit | **Draggable center modal** |
| v1 extras | **Stats panel**, **explicit "remember this" capture**, **"TOBI's view of me" narrative** |
| Deferred → v2 | Telegram auto-learn + `/brain` `/remember` commands; Hermes-memory sync |

## Architecture & key choices

- **Source of truth = SQLite** (`~/.mmo_agent/agent.db`) via existing `core/database.py`. Rationale: matches all existing dashboard data, trivial fast queries, and the dashboard already reads SQLite through `api/dashboard.py`. The spec's "Hermes memory is canonical" is satisfied later by a **one-way mirror job (v2)** — not worth the complexity for v1.
- **Embeddings = local, dependency-light.** Use **`fastembed`** (ONNX runtime, no PyTorch — clean on Windows) with a small model (e.g. `BAAI/bge-small-en-v1.5`, 384-dim). Store vectors as a `BLOB` (numpy `float32.tobytes()`) on the memory row. **Retrieval/dedup = brute-force cosine in NumPy** over all active vectors — at personal scale (hundreds–low thousands of memories) this is sub-millisecond and avoids native `sqlite-vec` build issues on Windows. Wrap in a new `core/embeddings.py` that **degrades gracefully**: if `fastembed` isn't installed, semantic features no-op and the UI falls back to keyword search (feature-flagged, never crashes).
- **LLM work** (extraction, import-split, narrative synthesis, merge) reuses `core/model_router.py:llm_complete(prompt, task_type=..., system=...)`. Add a small `core/brain.py` engine module that owns these prompts.
- **No app-level encryption** in v1 per decision; the existing `X-API-Key` guard on `api/dashboard.py` stays.

## Data model — new tables (in `core/database.py`, idempotent via an `_ensure_brain_schema(conn)` called from `init_database()`)

- **`brain_memories`** — the cards.
  `id, content TEXT, category TEXT, confidence REAL DEFAULT 0.6, source TEXT('manual'|'auto'|'import'|'remember'), status TEXT('active'|'pending'|'archived'|'superseded'), context TEXT, embedding BLOB, embed_model TEXT, created_at, updated_at, last_confirmed_at, deleted_at`.
  Indexes on `(category, status)`, `(status)`, `(last_confirmed_at)`.
- **`brain_memory_versions`** — immutable history (mirrors the existing `skill_versions` ledger pattern). `id, memory_id FK, content, category, confidence, change_kind('create'|'edit'|'merge'|'confirm'|'supersede'), changed_by('owner'|'auto'|'import'), created_at`.
- **`brain_categories`** — taxonomy + color + order; seeded with the comprehensive set, supports TOBI-proposed (`status pending|approved`). Seed: Identity, Preferences, Psychology, Relationships, Goals, Work/Projects, Habits/Routines, Health, each with a distinct accent color (drives the UI color system).
- **`brain_conflicts`** — open conflicts to resolve. `id, memory_id, candidate_content, candidate_category, reason, status('open'|'resolved'), created_at`.
- **`brain_imports`** — import audit. `id, filename, source_type('md'|'json'), card_count, created_at`.
- **`brain_sweep_state`** — high-water mark so the sweep only processes new `conversations.id` (`last_processed_convo_id`).
- **`brain_narrative`** — synthesized "TOBI's view of me", versioned. `id, content, model_used, created_at`.
- Reuse the existing **`conversations`** table for the dashboard chat (new `chat_id`, e.g. a constant `DASHBOARD_CHAT_ID`), via existing `save_conversation_message` / `load_conversation_history`.

DB helper functions to add (same style as `add_lesson`/`get_all_lessons`): `add_memory`, `update_memory` (writes a version row), `list_memories(filters)`, `get_memory`, `soft_delete_memory`, `confirm_memory`, `merge_memories`, `list_pending`, `list_conflicts`, `resolve_conflict`, `all_active_embeddings()`, category CRUD, narrative get/set, sweep-state get/set.

## Backend work (`tobi/`)

1. **`core/embeddings.py`** (new) — `embed(texts) -> list[np.ndarray]`, `cosine_topk(query_vec, candidates, k)`, lazy model load, graceful no-op if lib missing. Add `fastembed` + `numpy` to `requirements.txt`.
2. **`core/brain.py`** (new) — the engine:
   - `extract_from_messages(messages) -> [candidate cards]` (LLM, atomic, categorized, confidence).
   - `route_candidate(card)` → apply **hybrid rule**: sensitive category OR confidence < threshold OR conflicts-with-existing ⇒ `status='pending'` (or open a `brain_conflicts` row); else `status='active'`. Auto-merge near-duplicates (cosine ≥ τ) into the existing card (records a `merge` version).
   - `import_file(name, bytes) -> [candidate cards]` (LLM flexible parse → atomic split; same routing/merge).
   - `find_duplicates() -> [groups]` and `merge_group(...)` for the Clean-duplicates preview/confirm.
   - `retrieve(query, k)` and `profile_summary()` (cached synthesized summary) for chat injection.
   - `synthesize_narrative()` → writes `brain_narrative`.
3. **Sweep job** — add `job_brain_sweep()` to `main.py` scheduler (alongside `job_weekly_reflection`), running every N minutes: load new `conversations` since `brain_sweep_state`, call `extract_from_messages`, route candidates, advance high-water mark.
4. **API endpoints** in `api/dashboard.py` (follow the `_get_conn()` + Pydantic + `/api/*` pattern):
   - `GET /api/brain/memories` (filters: category, source, status, stale, `q`) · `GET /api/brain/memories/{id}` · `POST` · `PATCH` · `DELETE`.
   - `GET /api/brain/categories` · `POST /api/brain/categories` (+approve pending).
   - `GET /api/brain/pending` · `POST /api/brain/pending/{id}/(accept|reject)`.
   - `GET /api/brain/conflicts` · `POST /api/brain/conflicts/{id}/resolve`.
   - `POST /api/brain/search/semantic` (embed query → cosine top-k).
   - `POST /api/brain/import` (multipart or JSON body) → returns review candidates (with auto-merge annotations); `POST /api/brain/import/commit` (save selected/edited).
   - `GET /api/brain/duplicates` (preview groups) · `POST /api/brain/duplicates/merge`.
   - `GET /api/brain/stats` (counts per category, total, pending, conflicts, stale, growth).
   - `GET/POST /api/brain/narrative` (read / regenerate).
   - `POST /api/brain/remember` (explicit high-confidence capture).
   - `POST /api/brain/chat` — build system prompt = SOUL + `profile_summary()` + top-k `retrieve(message)`; call `llm_complete`; persist both turns to `conversations`; return reply. (Non-streaming first; optional SSE later mirroring `/api/missions/{id}/events`.)

## Frontend work (`tobi/dashboard/src/`)

1. **Routing/nav** — register `/brain` and `/chat` in `App.tsx`; add nav items in `AppShell.tsx` `NAV` (icons: `Brain`, `MessagesSquare` from lucide). Add `PageLoader` presets `brain` and `chat` in `components/PageLoader.tsx`.
2. **`api.ts`** — add types (`Memory`, `MemoryCategory`, `BrainStats`, `ImportCandidate`, `Conflict`, `ChatMessage`) and functions for every endpoint above (reuse `get`/`request` helpers and a `toQuery` like the existing one).
3. **`pages/Brain.tsx`** — header with **stats panel**; **category tabs** (color-coded from `brain_categories`); **search bar** + **filter button** (source/status/stale, plus a semantic "ask" toggle); **list rows, one memory per line**, each row color-keyed to its category with rich metadata (category, confidence, source, last-confirmed); buttons: **Import**, **Clean duplicates**, **Review (pending N / conflicts N)**, **Add memory**. A secondary **"TOBI's view of me"** narrative panel/section.
4. **Components** (reuse existing patterns):
   - `components/MemoryModal.tsx` — **draggable center modal** for view/edit; reuse the `useDragControls` + `GripHorizontal` + `createPortal` pattern from `pages/Office.tsx` (mission modal).
   - `components/BrainImportModal.tsx` — file input (`.md,.json`, `FileReader`) → POST import → **review list** with per-card edit (text/category/confidence), auto-merge badges, Save/Reject per card + **Save All**/Reject All.
   - `components/CleanDuplicatesModal.tsx` — shows merge-preview groups; confirm → merge.
   - `components/ReviewInbox.tsx` — pending queue + conflict resolver (accept/reject/choose-version).
   - `components/MemoryRow.tsx`, `components/CategoryTabs.tsx`.
   - Use `useToast` for all outcomes; `ConfirmTransitionModal` pattern for destructive confirms.
5. **`pages/Chat.tsx`** — simple chat (message list + composer) calling `POST /api/brain/chat`; a "Remember this" affordance on any message → `POST /api/brain/remember`. This is the v1 learning surface (the sweep reads its persisted `conversations`).

## Color system (category distinction)

Each `brain_categories` row carries an accent (CSS color). Memory rows render a left color-bar + category chip in that color; reuse the theme-token approach (`bg-x/10`, `text-x`, `border-x/30`) from `TaskCard.tsx`. Keeps contrast high and categories instantly distinguishable per the owner's note.

## v1 scope vs deferred

- **In v1:** dashboard Chat page + auto-learn sweep, import (.md/.json) with review, Brain page (list/tabs/filter/search/semantic), dedup (semantic, merge-preview), pending+conflict review, full versioning, local embeddings, stats, "remember this", narrative, chat wired to Brain (summary + top-k).
- **v2 (✅ shipped):** Telegram auto-learn + `/brain` `/remember` (`core/telegram_bot.py`), one-way Hermes-memory mirror (`brain.mirror_to_hermes`, tracked via `brain_memories.hermes_synced_at`, runs in `job_brain_sweep`), confidence-decay automation (`brain.decay_confidences` → daily `job_brain_decay`), SSE streaming chat (`POST /api/brain/chat/stream` + `brain.chat_stream` + `model_router.complete_stream`; frontend `streamBrainChat`), task-level memory-first consultation (`brain.owner_context` injected into `project_executor.execute_task`, `research_engine`, `ceo_loop`).

## Verification (end-to-end)

1. **Backend up:** `python main.py api` (or existing run mode); confirm `init_database()` creates the new tables (`sqlite3 ~/.mmo_agent/agent.db ".tables"`).
2. **Embeddings:** unit-check `core/embeddings.py embed(["hello"])` returns a 384-dim vector; verify graceful no-op when `fastembed` absent.
3. **Dashboard:** `cd tobi/dashboard && npm run dev`.
   - Chat page: send messages → reply returns; messages persist to `conversations`.
   - Run the sweep (`job_brain_sweep()` or a manual trigger) → candidates appear; a sensitive-category item lands in **pending**, a confident neutral one goes **active**.
   - Brain page: tabs/search/filter work; semantic "ask" returns relevant cards; edit via draggable modal writes a version row.
   - Import a sample `.md` and `.json` → review list with atomic cards + auto-merge badges → edit one, Save All → cards appear.
   - Create a near-duplicate, click **Clean duplicates** → merge preview → confirm → single merged card with a `merge` version.
   - Create a contradicting memory → appears in **conflict** review → resolve.
   - Stats panel counts update; "TOBI's view of me" regenerates.
4. **Memory-first proof:** state a preference in Chat, let it save, start a new chat turn → TOBI's reply reflects it (summary/top-k injection working).
5. `cd tobi/dashboard && npm run build` clean; backend imports without error.

## Risks / watch-items

- **`fastembed` on Windows** — must degrade gracefully if install fails (semantic features off, keyword search still works). Pin a CPU/ONNX build.
- **Free OpenRouter models** for extraction may produce noisy JSON — wrap extraction in strict JSON parsing with a retry/repair step; low-confidence by default so the hybrid gate catches misses.
- **Sweep idempotency** — strictly drive off `brain_sweep_state.last_processed_convo_id` to avoid re-extracting/duplicating.
- **Privacy tradeoff** — local-only storage by decision, BUT auto-extraction/import/narrative necessarily send memory text to the LLM provider (OpenRouter) during processing. Unavoidable for v1; a fully-local extraction LLM is a possible v2 hardening.

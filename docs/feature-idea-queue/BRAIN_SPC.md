# TOBI "Brain" — Implementation Plan (SPC)

> **Queue status:** 🟡 Queued · **v1 scope only** · **Read with:** [`BRAIN_SPEC.md`](BRAIN_SPEC.md) (design doc) · [`QUEUE.md`](QUEUE.md) (queue index)
>
> This document is the **build plan**: phased milestones, exact file manifests, task checklists, verification gates, risks, and dependencies. The spec defines *what*; this defines *how, in what order, and what "done" looks like.*

---

## Pre-flight Checklist

Complete these before writing any code:

- [ ] **Audit DB init pattern** — Confirm `core/database.py:init_database()` uses `_ensure_*_schema(conn)` helpers; verify the existing 7 tables boot cleanly with `python main.py test`.
- [ ] **Verify `fastembed` installs on Windows** — `pip install fastembed` in the project venv. If it fails, confirm the graceful-degradation path (semantic features no-op, keyword fallback works). Document the working version/command.
- [ ] **Audit existing API patterns** — Confirm `api/dashboard.py` uses `_get_conn()` → function → Pydantic → `/api/*` router; review an existing endpoint pair (e.g. `get_lessons` + `add_lesson`) as the template.
- [ ] **Confirm `model_router.py:llm_complete` signature** — Verify the call pattern (`prompt`, `task_type`, `system`) so `core/brain.py` matches it exactly.
- [ ] **Confirm `conversations` table structure** — Check `id` column type (INTEGER PRIMARY KEY autoincrement?) for the sweep high-water mark; confirm `save_conversation_message` / `load_conversation_history` signatures.
- [ ] **Dashboard build check** — `cd tobi/dashboard && npm run build` must pass clean before starting. Fix any pre-existing build errors first.
- [ ] **Create a test `.md` and `.json` import sample** — Small files (~5 facts each) to use during M2/M3 verification.

---

## Phase Map

| Phase  | What                                   | Blocks   | Est. effort |
| ------ | -------------------------------------- | -------- | ----------- |
| **M1** | Schema + Embeddings                    | Nothing  | Small       |
| **M2** | Brain Engine (`core/brain.py` + sweep) | M1       | Large       |
| **M3** | API Layer (endpoints + chat)           | M2       | Medium      |
| **M4** | Dashboard Frontend                     | M3 (API) | Large       |
| **M5** | Wiring, Polish & Verification          | M3 + M4  | Medium      |

**Dependency graph:** M1 → M2 → M3 → M4 → M5. M3/M4 can partially overlap (build frontend pages against the API contract while endpoints are being finished).

---

## M1 — Schema + Embeddings

**Objective:** All 7 new DB tables exist and `core/embeddings.py` works (or degrades gracefully).

### File manifest

| File                 | Action | What                                                        |
| -------------------- | ------ | ----------------------------------------------------------- |
| `core/database.py`   | Edit   | Add `_ensure_brain_schema(conn)` + all helper functions     |
| `core/embeddings.py` | Create | `embed()`, `cosine_topk()`, lazy model load, graceful no-op |
| `requirements.txt`   | Edit   | Add `fastembed` + `numpy`                                   |

### Task checklist

- [ ] **M1.1** — Add `_ensure_brain_schema(conn)` to `core/database.py`:
  - Table `brain_memories` (columns per spec: `id`, `content`, `category`, `confidence`, `source`, `status`, `context`, `embedding BLOB`, `embed_model TEXT`, `created_at`, `updated_at`, `last_confirmed_at`, `deleted_at`; indexes on `(category, status)`, `(status)`, `(last_confirmed_at)`)
  - Table `brain_memory_versions` (`id`, `memory_id FK`, `content`, `category`, `confidence`, `change_kind`, `changed_by`, `created_at`)
  - Table `brain_categories` (`id`, `name`, `color`, `sort_order`, `status`)
  - Table `brain_conflicts` (`id`, `memory_id`, `candidate_content`, `candidate_category`, `reason`, `status`, `created_at`)
  - Table `brain_imports` (`id`, `filename`, `source_type`, `card_count`, `created_at`)
  - Table `brain_sweep_state` (`id`, `last_processed_convo_id`)
  - Table `brain_narrative` (`id`, `content`, `model_used`, `created_at`)
  - Seed `brain_categories` with: Identity (#6366f1), Preferences (#f59e0b), Psychology (#ec4899), Relationships (#10b981), Goals (#8b5cf6), Work/Projects (#3b82f6), Habits/Routines (#14b8a6), Health (#ef4444)
  - Seed `brain_sweep_state` with `last_processed_convo_id = 0`
- [ ] **M1.2** — Call `_ensure_brain_schema(conn)` from `init_database()` (above the `conn.close()`).
- [ ] **M1.3** — Add DB helper functions in the same style as `add_lesson`/`get_all_lessons`:
  - `add_memory(...)` → returns id
  - `update_memory(id, fields...)` → writes a `brain_memory_versions` row first
  - `list_memories(filters: category, source, status, stale_days, search_q)` → returns list
  - `get_memory(id)` → single row
  - `soft_delete_memory(id)`
  - `confirm_memory(id)` → sets `last_confirmed_at = now()`
  - `merge_memories(kept_id, absorbed_ids...)` → writes merge versions, soft-deletes absorbed
  - `list_pending()` / `list_conflicts()` / `resolve_conflict(id, chosen_memory_id)`
  - `all_active_embeddings()` → `[(id, embedding BLOB), ...]` for brute-force cosine
  - Category CRUD: `list_categories()`, `add_category(...)`, `approve_category(id)`
  - Narrative: `get_narrative()`, `set_narrative(content, model)`
  - Sweep state: `get_sweep_state()`, `update_sweep_state(last_id)`
  - Import: `add_import_record(filename, source_type, card_count)`
  - `get_brain_stats()` → counts per category, total, pending, conflicts, stale
- [ ] **M1.4** — Create `core/embeddings.py`:
  - Lazy-load `fastembed` model (`BAAI/bge-small-en-v1.5`, 384-dim) on first `embed()` call
  - `embed(texts: list[str]) -> list[np.ndarray]` — batch-encode, return float32 vectors
  - `cosine_topk(query_vec, candidates: list[(id, np.ndarray)], k=10) -> list[(id, float)]` — brute-force NumPy cosine, sort descending
  - If `fastembed` not installed: `embed()` raises a caught exception; `cosine_topk()` returns empty. Callers (API endpoints, brain engine) check and fall back to keyword search.
  - Store model name so `brain_memories.embed_model` can be recorded
- [ ] **M1.5** — Add `fastembed` and `numpy` to `requirements.txt`. Pin known-working versions.

### Verification gate (M1)

```bash
# 1. DB tables
python main.py test              # init_database runs; confirm no errors
sqlite3 ~/.mmo_agent/agent.db ".tables" | grep brain

# 2. Embeddings
python -c "
from core.embeddings import embed, cosine_topk
import numpy as np
vecs = embed(['hello world', 'foo bar'])
print(len(vecs), vecs[0].shape)  # 2, (384,)
k = cosine_topk(vecs[0], [(1, vecs[1])], k=1)
print(k)  # [(1, score)]
"

# 3. Graceful degradation (uninstall fastembed, confirm no crash)
pip uninstall fastembed -y
python -c "from core.embeddings import embed; print(embed(['test']))"  # raises, caught, fallback works
pip install fastembed  # reinstall
```

---

## M2 — Brain Engine

**Objective:** `core/brain.py` handles extraction, routing, import, dedup, retrieval, narrative, and remember. Sweep job runs in the scheduler.

### File manifest

| File            | Action | What                                 |
| --------------- | ------ | ------------------------------------ |
| `core/brain.py` | Create | All engine functions                 |
| `main.py`       | Edit   | Add `job_brain_sweep()` to scheduler |

### Task checklist

- [ ] **M2.1** — Create `core/brain.py` with these functions:

  **Extraction & Routing:**
  - `extract_from_messages(messages: list[dict]) -> list[dict]` — Build prompt: "Given these conversation messages, extract atomic facts about the user. Return JSON array of {content, category, confidence (0–1), context (which message)}." Call `llm_complete(prompt, task_type="extraction", system="You are Tobi's memory extraction engine...")`. Parse JSON strictly; retry once on parse failure; on second failure, return [] (no crash). Each card is `{content, category, confidence, source: 'auto', context}`.
  - `route_candidate(card: dict) -> str` — Apply hybrid rules:
    1. If category in `{'Psychology', 'Relationships', 'Health'}` → `'pending'`
    2. If `confidence < 0.65` → `'pending'`
    3. Check for conflicts: cosine similarity ≥ 0.92 to any active card with *contradicting* content (LLM quick-check: "Do these two facts contradict?" with `task_type="quick"`) → create `brain_conflicts` row → `'conflict'`
    4. Check for near-duplicates: cosine ≥ 0.92 to an existing active card *without* contradiction → merge into existing (update content if richer, write merge version) → `'merged'`
    5. Otherwise → `'active'`
  - `process_extracted_cards(cards: list[dict]) -> dict` — Calls `route_candidate` on each, writes to DB via helpers, returns `{active, pending, merged, conflict}` counts.

  **Import:**
  - `parse_import_file(filename: str, content: str) -> list[dict]` — LLM prompt: "Parse this file into atomic facts about the user. Return JSON array of {content, category, confidence}." Flexible: handles .md (prose/bullets) and .json (any shape). Split into atomic cards (no compound facts).
  - `import_preview(cards: list[dict]) -> list[dict]` — For each card, check cosine overlap with existing actives (annotate with `overlaps_with` / `auto_merge_suggestion`). Return enriched list for the review UI.

  **Dedup:**
  - `find_duplicate_groups() -> list[list[dict]]` — `all_active_embeddings()` → pairwise cosine; group cards with similarity ≥ 0.88. Return groups of ≥ 2.
  - `merge_duplicate_group(memory_ids: list[int], kept_id: int)` — Merge absorbed into kept; write merge versions; soft-delete absorbed.

  **Retrieval:**
  - `retrieve(query: str, k: int = 10) -> list[dict]` — Embed query → `cosine_topk` against `all_active_embeddings()` → return full card rows. Falls back to keyword `LIKE` search if embeddings unavailable.

  **Narrative:**
  - `synthesize_narrative() -> str` — LLM prompt: "You are Tobi. Based on these memories about your owner, write 'TOBI's view of me' — a first-person narrative (~300–500 words) describing who he is: his values, communication style, motivators, stressors, risk profile, cognitive patterns, defenses, blind spots. Be honest and insightful, not flattering." Categorize by Psychology → Preferences → Goals → Habits → Relationships. Write to `brain_narrative`.

  **Remember:**
  - `remember_this(content: str, category: str = None) -> int` — High-confidence manual capture. If no category, auto-classify via LLM quick-call. Always `status='active'`, `source='remember'`, `confidence=1.0`. Returns memory ID.

- [ ] **M2.2** — Add `job_brain_sweep()` to `main.py`:
  - Read `brain_sweep_state.last_processed_convo_id`
  - Query `conversations` where `id > last_processed_convo_id`, ordered by id ASC, limit 50
  - If any rows: format as messages, call `extract_from_messages` → `process_extracted_cards`; advance high-water mark to max id
  - Schedule: every 15 minutes (alongside the existing schedule setup in `setup_schedules`)
  - Wrap in try/except — sweep failures must never crash the daemon
  - Call `profile_summary()` after sweep if cards were added (bust cache)

- [ ] **M2.3** — Wire `profile_summary()` into chat system prompt (prep for M3):
  - Add a helper `build_chat_system_prompt() -> str` that returns: SOUL.md content + `profile_summary()` + "Here are relevant memories: {top-k retrieve of message}"
  - This will be called from the M3 chat endpoint

### Verification gate (M2)

```bash
# 1. Extraction
python -c "
from core.brain import extract_from_messages
msgs = [{'role': 'user', 'content': 'I prefer dark mode everywhere and I hate notifications. My main project is Shiney Automations.'}]
cards = extract_from_messages(msgs)
print(cards)  # Should find ~2-3 atomic cards with categories
"

# 2. Routing
python -c "
from core.brain import process_extracted_cards
# Feed in test cards covering sensitive + neutral + low-confidence
result = process_extracted_cards(test_cards)
print(result)  # {active: N, pending: M, merged: P, conflict: Q}
"

# 3. Import
python -c "
from core.brain import parse_import_file
cards = parse_import_file('test.md', open('test_import.md').read())
print(len(cards), cards[:2])
"

# 4. Sweep job (manual trigger)
python -c "from main import job_brain_sweep; job_brain_sweep()"
# Check DB for new brain_memories rows

# 5. Narrative
python -c "from core.brain import synthesize_narrative; print(synthesize_narrative()[:200])"
```

---

## M3 — API Layer

**Objective:** All 15 Brain endpoints live in `api/dashboard.py`; chat endpoint wired to Brain; existing auth (`X-API-Key`) protects all routes.

### File manifest

| File               | Action       | What                                                        |
| ------------------ | ------------ | ----------------------------------------------------------- |
| `api/dashboard.py` | Edit         | Add Brain router + all endpoints                            |
| `api/server.py`    | Edit (maybe) | Register Brain router if separate file; otherwise no change |

### Task checklist

Follow the existing pattern: `_get_conn()` → function → Pydantic model → `@router.get/post/patch/delete("/api/brain/...")`.

- [ ] **M3.1** — Core CRUD:
  - `GET /api/brain/memories` — Query params: `category`, `source`, `status`, `stale_days`, `q` (keyword search). Returns `list[Memory]`.
  - `GET /api/brain/memories/{id}` — Single card with version history.
  - `POST /api/brain/memories` — Manual create. Body: `{content, category, confidence, source='manual'}`. Returns `Memory`.
  - `PATCH /api/brain/memories/{id}` — Update fields; writes version row. Returns updated `Memory`.
  - `DELETE /api/brain/memories/{id}` — Soft delete (sets `deleted_at`).

- [ ] **M3.2** — Categories:
  - `GET /api/brain/categories` — All categories, ordered by `sort_order`.
  - `POST /api/brain/categories` — Add proposed category (status='pending'); or approve pending if admin.

- [ ] **M3.3** — Inbox (pending + conflicts):
  - `GET /api/brain/pending` — All memories with `status='pending'`.
  - `POST /api/brain/pending/{id}/accept` — Set to `active`, write confirm version.
  - `POST /api/brain/pending/{id}/reject` — Soft delete.
  - `GET /api/brain/conflicts` — All open conflicts with candidate details.
  - `POST /api/brain/conflicts/{id}/resolve` — Body: `{chosen_memory_id}`. Resolve conflict, soft-delete loser.

- [ ] **M3.4** — Search:
  - `POST /api/brain/search/semantic` — Body: `{query: str, k: int = 10}`. Embed → cosine top-k → return cards. Falls back to keyword if embeddings unavailable (return keyword results + `{"search_mode": "keyword"}`).

- [ ] **M3.5** — Import:
  - `POST /api/brain/import` — Accept multipart file upload (`.md`, `.json`) OR JSON body `{content, filename}`. Call `parse_import_file` → `import_preview` → return review list (enriched cards with `overlaps_with`, `auto_merge_suggestion`). Do NOT commit yet.
  - `POST /api/brain/import/commit` — Body: `{cards: [{content, category, confidence, action: 'save'|'reject'}]}`. Save accepted cards; add `brain_imports` record. Return `{saved: N, rejected: M}`.

- [ ] **M3.6** — Dedup:
  - `GET /api/brain/duplicates` — Returns groups from `find_duplicate_groups()`.
  - `POST /api/brain/duplicates/merge` — Body: `{group: [{memory_id, action: 'keep'|'absorb'}]}`. Merge absorbed into kept. Returns updated kept card.

- [ ] **M3.7** — Stats, Narrative, Remember:
  - `GET /api/brain/stats` — Counts per category, total active, pending, conflicts, stale (>30 days since confirmed).
  - `GET /api/brain/narrative` — Returns latest `brain_narrative` row.
  - `POST /api/brain/narrative` — Regenerate via `synthesize_narrative()`. Returns new narrative.
  - `POST /api/brain/remember` — Body: `{content, category?}`. High-confidence capture. Returns `Memory`.

- [ ] **M3.8** — Chat endpoint:
  - `POST /api/brain/chat` — Body: `{message: str}`.
    1. `DASHBOARD_CHAT_ID = "dashboard"` (constant in `database.py`)
    2. Load recent history via `load_conversation_history(DASHBOARD_CHAT_ID, limit=20)`
    3. Build system prompt: `SOUL.md` + `profile_summary()` + top-10 `retrieve(message)`
    4. Call `llm_complete(prompt=message, system=system_prompt, task_type="chat", conversation_history=history)`
    5. Save user message + assistant reply via `save_conversation_message(DASHBOARD_CHAT_ID, role, content)`
    6. Return `{reply: str, memories_used: [ids]}`

  Non-streaming for v1 (SSE streaming deferred to v2 per spec).

### Verification gate (M3)

```bash
# Start API
python main.py api &
sleep 2

# 1. CRUD
curl -s http://localhost:8000/api/brain/memories | jq length
curl -s -X POST http://localhost:8000/api/brain/memories \
  -H "Content-Type: application/json" \
  -d '{"content":"I prefer dark mode","category":"Preferences","confidence":0.9}' | jq .id

# 2. Import
curl -s -X POST http://localhost:8000/api/brain/import \
  -F "file=@test_import.md" | jq length

# 3. Chat
curl -s -X POST http://localhost:8000/api/brain/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"What do you know about me?"}' | jq .reply

# 4. Search
curl -s -X POST http://localhost:8000/api/brain/search/semantic \
  -H "Content-Type: application/json" \
  -d '{"query":"my projects"}' | jq length

# 5. Stats
curl -s http://localhost:8000/api/brain/stats | jq

# Cleanup
kill %1
```

---

## M4 — Dashboard Frontend

**Objective:** Chat page + Brain page fully functional in the dashboard, all components built, color system applied.

### File manifest

| File                                                | Action | What                                                             |
| --------------------------------------------------- | ------ | ---------------------------------------------------------------- |
| `dashboard/src/App.tsx`                             | Edit   | Add `/brain` and `/chat` routes                                  |
| `dashboard/src/components/AppShell.tsx`             | Edit   | Add Brain + Chat nav items (lucide `Brain`, `MessagesSquare`)    |
| `dashboard/src/components/PageLoader.tsx`           | Edit   | Add `brain` and `chat` preset shapes                             |
| `dashboard/src/api.ts`                              | Edit   | Add Brain types + all API functions                              |
| `dashboard/src/pages/Chat.tsx`                      | Create | Chat page (message list + composer + "remember this")            |
| `dashboard/src/pages/Brain.tsx`                     | Create | Brain page (stats header, tabs, search, filter, list, narrative) |
| `dashboard/src/components/MemoryModal.tsx`          | Create | Draggable modal for view/edit memory                             |
| `dashboard/src/components/BrainImportModal.tsx`     | Create | Import file upload + review + commit                             |
| `dashboard/src/components/CleanDuplicatesModal.tsx` | Create | Merge preview + confirm                                          |
| `dashboard/src/components/ReviewInbox.tsx`          | Create | Pending review + conflict resolver                               |
| `dashboard/src/components/MemoryRow.tsx`            | Create | Single memory list row (color bar + content + meta)              |
| `dashboard/src/components/CategoryTabs.tsx`         | Create | Horizontal tab bar, color-coded                                  |

### Task checklist

- [ ] **M4.1** — Types in `api.ts`:
  - Add interfaces: `Memory`, `MemoryCategory`, `BrainStats`, `ImportCandidate`, `ImportOverlap`, `Conflict`, `DuplicateGroup`, `ChatMessage`, `Narrative`
  - Add functions (reuse `get`/`request` helpers + `toQuery` pattern):
    - `fetchMemories(filters?)`, `fetchMemory(id)`, `createMemory(data)`, `updateMemory(id, data)`, `deleteMemory(id)`
    - `fetchCategories()`, `createCategory(data)`
    - `fetchPending()`, `acceptPending(id)`, `rejectPending(id)`, `fetchConflicts()`, `resolveConflict(id, chosenId)`
    - `semanticSearch(query, k)`
    - `importFile(file)` → preview, `commitImport(cards)`
    - `fetchDuplicates()`, `mergeDuplicates(group)`
    - `fetchBrainStats()`
    - `fetchNarrative()`, `regenerateNarrative()`
    - `rememberThis(content, category?)`
    - `sendChatMessage(message)` → `{reply, memoriesUsed}`

- [ ] **M4.2** — Routing & navigation:
  - `App.tsx`: Add `<Route path="/brain" element={<Brain />} />` and `<Route path="/chat" element={<Chat />} />`
  - `AppShell.tsx`: Add to NAV array: `{ name: 'Chat', path: '/chat', icon: MessagesSquare }` and `{ name: 'Brain', path: '/brain', icon: Brain }`
  - `PageLoader.tsx`: Add `brain` and `chat` skeleton presets (reuse the pattern from existing presets)

- [ ] **M4.3** — Chat page (`pages/Chat.tsx`):
  - **Layout:** Full-height flex column: message list (flex-1, overflow-y-auto) + composer bar (sticky bottom).
  - **Message list:** Map over local `messages` state. User messages right-aligned (bg-primary/10), Tobi messages left-aligned (bg-muted). Show timestamp.
  - **Composer:** Textarea + Send button (lucide `Send`). Enter sends, Shift+Enter newline.
  - **State:** `messages: ChatMessage[]`, `input: string`, `loading: boolean`.
  - **Send flow:** Append user message → set loading → `await sendChatMessage(input)` → append assistant reply → scroll to bottom.
  - **"Remember this":** Each assistant message has a small `Brain` icon button. Click → `await rememberThis(message.content)` → toast "Saved to Brain".
  - **Empty state:** Friendly prompt: "Chat with Tobi. He learns about you from every conversation."
  - **Error state:** Toast on failure, message stays in input.

- [ ] **M4.4** — Brain page (`pages/Brain.tsx`):
  - **Header:** Stats bar — 6 pill badges: Total, Active, Pending (amber), Conflicts (red), Stale (gray), Categories (count). Fetch via `fetchBrainStats()` on mount + on mutation.
  - **Category tabs:** Horizontal scrollable tab bar from `fetchCategories()`. Each tab = color dot + name + count. "All" tab as default. Color comes from `category.color` (CSS var pattern: `style={{ '--cat-color': category.color }}`).
  - **Search bar:** Text input (lucide `Search`) + toggle "Semantic" / "Keyword". Debounced (300ms). On change: semantic → `semanticSearch(q)`, keyword → `fetchMemories({q})`.
  - **Filter button:** Dropdown/popover with checkboxes: Source (manual/auto/import/remember), Status (active/pending/archived), Stale (>30 days). Applies to `fetchMemories`.
  - **Memory list:** Vertical list of `MemoryRow` components. One per line. Color bar on left (4px wide, category.color). Content (truncated to 1 line), category chip (small pill with category color bg/10 + text), confidence %, source icon, last-confirmed relative date.
  - **Action buttons (header row):**
    - **Import** → opens `BrainImportModal`
    - **Clean duplicates** → opens `CleanDuplicatesModal`
    - **Review (N pending / M conflicts)** → opens `ReviewInbox` (badge counts from stats)
    - **+ Add memory** → opens `MemoryModal` in create mode
  - **"TOBI's view of me" panel:** Collapsible section at page bottom. Shows latest narrative text (italic, muted bg). "Regenerate" button → `regenerateNarrative()` → toast + refresh.
  - **Click a memory row** → opens `MemoryModal` in view/edit mode.

- [ ] **M4.5** — `MemoryModal.tsx` (draggable center modal):
  - Reuse the pattern from `pages/Office.tsx` mission modal: `useDragControls` + `GripHorizontal` + `createPortal` to `document.body`.
  - **View mode:** Read-only fields: content (textarea-sized), category (colored chip), confidence (badge), source, context (if any), created/updated/last-confirmed timestamps. Version history accordion at bottom.
  - **Edit mode:** Toggle via "Edit" button. Content editable textarea, category select dropdown, confidence slider (0–1, step 0.05). Save → `updateMemory` → toast + close. Cancel reverts.
  - **Delete:** Red "Delete" button → `ConfirmTransitionModal` pattern → `deleteMemory` → toast + refresh list.
  - **Confirm:** "Confirm this memory" button → `confirmMemory` → updates `last_confirmed_at`.

- [ ] **M4.6** — `BrainImportModal.tsx`:
  - **Step 1 — Upload:** File input (accept `.md,.json`). `FileReader` → `importFile(file)` → loading spinner → transition to step 2.
  - **Step 2 — Review:** List of atomic cards. Each card has: content (editable textarea), category (select, pre-filled), confidence (display). Auto-merge badges: "Overlaps with: [existing memory content snippet]" in amber. Per-card actions: Save / Reject.
  - **Step 3 — Commit:** "Save All" button → `commitImport(acceptedCards)` → toast "Imported N memories" → close + refresh Brain page. "Reject All" → close with confirmation.

- [ ] **M4.7** — `CleanDuplicatesModal.tsx`:
  - List groups from `fetchDuplicates()`. Each group: 2–5 similar memory cards side-by-side. Radio button to select the "kept" card. Preview merged content (kept's content + "[Merged from: ...]" annotation).
  - "Merge group" button per group OR "Merge all groups" at bottom.
  - Calls `mergeDuplicates(group)` → toast → refresh.

- [ ] **M4.8** — `ReviewInbox.tsx`:
  - Two tabs: "Pending" + "Conflicts".
  - **Pending tab:** List of pending memories. Each: content, category, confidence, context (which conversation it came from). Actions: ✓ Accept (green), ✕ Reject (red). Calls `acceptPending` / `rejectPending`.
  - **Conflicts tab:** List of conflicts. Each: original memory + conflicting candidate side-by-side. Select which to keep. "Resolve" button → `resolveConflict(id, chosenId)`.

- [ ] **M4.9** — `MemoryRow.tsx` + `CategoryTabs.tsx`:
  - `MemoryRow`: Li-style row with left color bar. Responsive: on mobile, hide confidence/source, show only content + category chip. Click handler → opens modal.
  - `CategoryTabs`: Flex row, overflow-x-auto, gap-2. Each tab: small colored circle + name + count badge. Active tab has underline + bold. "All" tab always first. On click → filter Brain list.

- [ ] **M4.10** — Color system across all components:
  - Each category has a `color` field from `brain_categories`. Apply consistently:
    - Left bar on memory rows: `backgroundColor: category.color`
    - Category chip: `backgroundColor: category.color + '15'`, `color: category.color`, `borderColor: category.color + '30'`
    - Tab indicator: `borderBottom: '2px solid ' + category.color`
  - Use inline styles for dynamic colors; keep Tailwind for layout/spacing.

- [ ] **M4.11** — Toast feedback everywhere:
  - Every mutation (create, update, delete, import, merge, resolve, remember, regenerate) fires a `useToast` call with success/error.
  - Follow existing toast patterns in the dashboard.

### Verification gate (M4)

```bash
cd tobi/dashboard && npm run dev
# Open http://localhost:5173

# 1. Nav: click Chat → page loads; click Brain → page loads
# 2. Chat: type "Hi Tobi, I'm a morning person and I love coffee" → reply returns
# 3. Click "remember this" on Tobi's reply → toast "Saved to Brain"
# 4. Navigate to Brain → see the new memory in the list (Preferences category, amber color bar)
# 5. Run sweep (manual trigger from backend) → check pending inbox for any auto-extracted cards
# 6. Click a memory → draggable modal opens; edit content → save → version appears
# 7. Import test_import.md → review cards → edit one → Save All → cards appear
# 8. Create a near-duplicate manually → Clean duplicates → merge preview → confirm
# 9. Check stats panel updates; "TOBI's view of me" narrative section shows
# 10. Semantic search: type "coffee" → relevant card shows
# 11. Switch category tabs → list filters correctly
```

---

## M5 — Wiring, Polish & End-to-End Verification

**Objective:** Confirm memory-first chat works, sweep is idempotent, all edge cases handled, build is clean.

### File manifest

| File                           | Action | What                                 |
| ------------------------------ | ------ | ------------------------------------ |
| `dashboard/src/pages/Chat.tsx` | Edit   | Confirm memory injection visible     |
| `main.py`                      | Edit   | Confirm sweep schedule + idempotency |
| `core/brain.py`                | Edit   | Edge-case hardening if needed        |

### Task checklist

- [ ] **M5.1** — Memory-first proof:
  - State a preference in Chat: "I always deploy on Fridays."
  - Let sweep process it (or manually trigger).
  - Start a new chat: "When should I deploy?" → Tobi's reply references Friday preference.
  - Verify `profile_summary()` includes the preference.
  - Verify top-k `retrieve()` returns the memory card.

- [ ] **M5.2** — Sweep idempotency:
  - Run sweep twice with no new messages → second run processes 0 cards, high-water mark unchanged.
  - Add new conversation messages → sweep processes only the new ones.
  - Verify `brain_sweep_state.last_processed_convo_id` advances correctly.

- [ ] **M5.3** — Edge cases:
  - [ ] Empty conversations → sweep returns 0 cards (no crash).
  - [ ] Very long message (>4000 chars) → extraction prompt handles it (truncate if needed, note in context).
  - [ ] Non-English messages → extraction still attempts; may produce lower confidence (routing sends to pending).
  - [ ] LLM returns malformed JSON → retry once, then skip (logged, not crashed).
  - [ ] `fastembed` not installed → semantic search falls back to keyword; dedup/merge show "Embeddings unavailable" message; everything else works.
  - [ ] DB locked (another process) → sweep retries on next interval (WAL mode).
  - [ ] Category with zero memories → tab still shows (count = 0).
  - [ ] Import file with zero extractable facts → toast "No facts found in file."

- [ ] **M5.4** — A11y:
  - Modal focus trap (focus locks inside `MemoryModal`, `BrainImportModal`, etc.).
  - Keyboard: Tab through memory rows, Enter to open, Escape to close modal.
  - ARIA labels on icon-only buttons ("Remember this", "Edit", "Delete").
  - `prefers-reduced-motion`: no animation on modal open/close; instant tab switches.

- [ ] **M5.5** — Build verification:
  ```bash
  cd tobi/dashboard && npm run build
  # Must pass with zero errors. Check chunk sizes — Brain/Chat routes should be code-split.
  ```

- [ ] **M5.6** — Full path walkthrough (the spec's verification section):
  1. Backend up: `python main.py api` — tables exist.
  2. Embeddings: `embed(["test"])` returns 384-dim vector.
  3. Dashboard: Chat page sends/receives; messages persist.
  4. Sweep processes chat → candidates appear.
  5. Brain page: tabs, search, filter, semantic search, edit modal, version history.
  6. Import .md/.json → review → commit.
  7. Duplicates: create overlap → Clean → merge.
  8. Conflicts: create contradiction → resolve.
  9. Stats + narrative update.
  10. Memory-first: new chat references saved memory.
  11. `npm run build` clean.

- [ ] **M5.7** — Update QUEUE.md status:
  - Change Brain row status from `🟡 Queued` to `✅ Done`.

---

## Risk Register

| Risk                                                 | Likelihood | Impact | Mitigation                                                                                                                                      |
| ---------------------------------------------------- | ---------- | ------ | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| `fastembed` fails on Windows                         | Medium     | Medium | Graceful degradation built in from M1; keyword fallback for search; dedup becomes manual-only. Document exact working install command.          |
| OpenRouter free models produce bad JSON              | High       | Low    | Strict JSON parse + single retry + low-confidence default routing (goes to pending, not active). Extraction failures logged, never crash.       |
| Sweep extracts noise (greetings, small talk)         | High       | Low    | Prompt instructs "atomic facts about the user only, not chitchat." Low-confidence extraction → pending review. Owner can reject noise in inbox. |
| Sweep non-idempotent (duplicate cards)               | Medium     | High   | Strict high-water mark via `brain_sweep_state`. Merge routing catches near-duplicates (cosine 0.92+). Version history preserved.                |
| Privacy: memory text sent to OpenRouter              | Certain    | Medium | Documented tradeoff in spec. v2 hardening = local extraction LLM. Owner aware — this is the v1 decision.                                        |
| Phaser-sized bundle problem (Brain is smaller scope) | Low        | Low    | Brain has zero heavy deps (no game engine, no canvas). Only `fastembed` is backend-only. Frontend bundle impact is minimal.                     |
| Chat page feels slow (non-streaming)                 | Low        | Medium | v1 is non-streaming per spec; acceptable for a dashboard chat. SSE streaming is a v2 item. Keep response times under 5s via fast model routing. |
| Scope creep (v2 features pulled into v1)             | Medium     | High   | Strict gate: Telegram commands + Hermes sync are v2 ONLY. If someone tries to add them, point to this SPC and the v2 section of BRAIN_SPEC.md.  |

---

## File Build Order (Flat List)

Execute in this exact order, verifying each step before moving on:

| #   | File                                                                                          | Phase |
| --- | --------------------------------------------------------------------------------------------- | ----- |
| 1   | `core/database.py` — add `_ensure_brain_schema` + all helpers                                 | M1    |
| 2   | `core/embeddings.py` — create                                                                 | M1    |
| 3   | `requirements.txt` — add `fastembed`, `numpy`                                                 | M1    |
| 4   | **VERIFY M1**                                                                                 | —     |
| 5   | `core/brain.py` — create (extraction, routing, import, dedup, retrieval, narrative, remember) | M2    |
| 6   | `main.py` — add `job_brain_sweep` + schedule                                                  | M2    |
| 7   | **VERIFY M2**                                                                                 | —     |
| 8   | `api/dashboard.py` — add Brain router + 15 endpoints + chat                                   | M3    |
| 9   | **VERIFY M3**                                                                                 | —     |
| 10  | `dashboard/src/api.ts` — add Brain types + API functions                                      | M4    |
| 11  | `dashboard/src/App.tsx` — add routes                                                          | M4    |
| 12  | `dashboard/src/components/AppShell.tsx` — add nav items                                       | M4    |
| 13  | `dashboard/src/components/PageLoader.tsx` — add presets                                       | M4    |
| 14  | `dashboard/src/components/CategoryTabs.tsx` — create                                          | M4    |
| 15  | `dashboard/src/components/MemoryRow.tsx` — create                                             | M4    |
| 16  | `dashboard/src/components/MemoryModal.tsx` — create                                           | M4    |
| 17  | `dashboard/src/components/ReviewInbox.tsx` — create                                           | M4    |
| 18  | `dashboard/src/components/BrainImportModal.tsx` — create                                      | M4    |
| 19  | `dashboard/src/components/CleanDuplicatesModal.tsx` — create                                  | M4    |
| 20  | `dashboard/src/pages/Chat.tsx` — create                                                       | M4    |
| 21  | `dashboard/src/pages/Brain.tsx` — create                                                      | M4    |
| 22  | **VERIFY M4**                                                                                 | —     |
| 23  | Edge-case hardening (all files)                                                               | M5    |
| 24  | A11y pass                                                                                     | M5    |
| 25  | `npm run build` clean check                                                                   | M5    |
| 26  | Full walkthrough (spec verification 1–6)                                                      | M5    |
| 27  | Update `QUEUE.md` → ✅ Done                                                                    | M5    |

---

## Notes

- **Reuse, don't rebuild.** Brain piggybacks on the existing `conversations` table, `model_router.py:llm_complete`, `api/dashboard.py` patterns, and the `useDragControls` + `createPortal` modal pattern from Office. No new infrastructure.
- **No new dependencies** beyond `fastembed` + `numpy` (both pip-installable, no system libs).
- **Keep it shippable.** M1 should take <1 hour. M2 is the heavy lift (extraction prompts + routing logic). M3 is boilerplate-heavy but straightforward. M4 is the largest surface area — break it into component-by-component commits.
- **The spec is the source of truth.** If this SPC contradicts `BRAIN_SPEC.md`, the spec wins. Update this SPC to match.


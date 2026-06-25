# Second Brain — Direction Analysis & Recommendation

> **Question on the table:** To build the **Awakening · "Understand Me"** pillar (make Tobi a
> second brain that stores real data, never forgets, and uses a graph to cut tokens), do we
> **(1) develop the current Mission Control Brain/graph**, or **(2) restructure around an Obsidian vault**?
>
> **Author:** Systems architecture analysis · **Date:** 2026-06-25 · **Inputs:** full read of
> `core/brain.py`, `core/graph_engine.py`, `core/database.py`, the Evolution tier registry in
> `api/dashboard.py`, plus a 60-question discovery interview with the owner (Appendix A).

---

## 0. TL;DR — the recommendation

**Build a HYBRID, and it is mostly an *extension*, not a rewrite.**

- Keep **Tobi's SQLite Brain + unified graph + local embeddings** as the **engine and source of
  truth** — it is already ~70–80% of what "Understand Me" needs, and it is the only part that can do
  programmatic hybrid retrieval and run 24/7 on a server.
- Add a **readable, two-way Markdown projection** (an Obsidian-compatible vault: `profile.md`,
  `people/<name>.md`, daily notes, decisions) as the **human browse/edit surface** and a portable,
  git-backed life-record. A file-watcher reflects your edits back into the engine; **your hand-written
  blocks are sacred and never overwritten.**

**Why not "Obsidian-centric":** your vault is empty, Obsidian isn't yet a habit, you don't actually
value its plugin ecosystem, you want the graph *inside Mission Control*, and Obsidian has no
server-side retrieval engine. Centering on it would mean adopting a new tool to get capabilities you
already have — while losing transactional integrity, embeddings, and encryption options.

**Why not "pure MC, ignore markdown":** you explicitly want a readable profile, person-notes,
two-way sync, would install a bridge plugin, and want to *own a readable record forever*. A markdown
layer is cheap to add on top of the engine and buys transparency, portability, and occasional editing.

The hybrid is the synthesis that satisfies *every* hard constraint you gave. Full reasoning in §6–§7.

---

## 1. What we're actually deciding

This is **not** a greenfield "pick a tool" decision. Tobi **already has a second brain**, and it
**already ingests Obsidian**. So the real axes are:

| Axis | The genuine question |
|---|---|
| **Source of truth** | Does the canonical store live in SQLite (engine) or in `.md` files (vault)? |
| **Write direction** | One-way (vault → Tobi), or two-way (Tobi also writes readable notes)? |
| **Editing surface** | Where do *you* read/curate — Mission Control, Obsidian, or both? |
| **Retrieval engine** | Who computes embeddings / graph-walk / hybrid recall? (Obsidian can't, server-side.) |
| **Depth of ingest** | The current 500-note / 500-char cap, or full-text chunked? |

Everything below resolves these against the code reality and your stated needs.

---

## 2. Honest assessment of what Tobi has TODAY

You asked me to assess the existing build candidly. Here it is, from the source.

### 2.1 The Brain engine — `core/brain.py` (substantial, underused)

A genuine long-term **owner-memory** system, not a stub:

- **8 memory categories:** `identity, preferences, psychology, relationships, goals, work, habits, health`.
- **Auto-learn pipeline:** `extract_from_messages()` (LLM extraction) → confidence scoring
  (`AUTO_CONF_THRESHOLD = 0.7` auto-saves) → **semantic dedup/merge** (`MERGE_THRESHOLD = 0.88`) →
  **conflict detection** (same category, cosine in [0.62, 0.88)) → **staleness decay** (90 days).
- **Retrieval:** `retrieve(query, k)` and `owner_context(query)` — embeddings with keyword fallback.
- **Narrative synthesis:** `synthesize_narrative()` writes a prose "who is the owner" summary.
- **Sensitive-category handling**, pending-approval queue, import parser, duplicate finder, versioning.
- **A full Brain UI** is already exposed in the dashboard (memories CRUD, semantic search, pending,
  conflicts, import, duplicates, narrative, sweep) — see `api/dashboard.py:3533–3698`.

**Already wired into real task paths** (this is the important part):
`brain.owner_context(...)` is called inside **`ceo_loop.py`**, **`project_executor.py`**, and
**`research_engine.py`** before their LLM calls. So *memory-first retrieval already exists* for those
flows — it just isn't uniform or surfaced.

### 2.2 The graph engine — `core/graph_engine.py` (strong foundation)

- **One unified node/edge store** across `memory · task · project` + **read-only mirrors** of
  `notion · github · gdrive · local`.
- **Local embeddings** (`fastembed`) on every node → **semantic edges** (cosine ≥ `0.70`, top-4),
  plus **ref edges** and **tag edges**, with **community detection** (label propagation) and degree
  centrality. Deliberately tuned **anti-hairball** (sparse, meaningful edges).
- `owner_context`-style **prompt-ready graph block** (`graph_engine.py:647`) — graph-connected facts
  formatted for injection. **This is the token-optimization primitive you're asking for, already present.**

### 2.3 Obsidian is ALREADY integrated — `_sync_local()` (but shallow & one-way)

`core/graph_engine.py:811` already:
- reads **`OBSIDIAN_VAULT`** (or `GRAPH_LOCAL_DIRS`),
- ingests **up to 500 `.md` files**,
- parses **`[[wikilinks]]` → ref edges**,
- embeds each note into the unified graph.

**But:** it's **one-way (vault → graph), read-only**, **capped at 500 notes**, and stores only a
**500-character summary** per note (no full-text, no chunking). Tobi never writes back.

### 2.4 The real gaps (why "Understand Me" reads 0/3 today)

The three Awakening abilities are **hard-coded to `False`** — `_detect_abilities()` returns only Tier-0
keys and notes *"All Tier 1+ abilities default to False (not yet built)."* So even though the Brain
implements most of the behavior, the abilities **cannot light up until detection is wired**. The
genuine engineering gaps are:

| Ability | What exists | What's missing |
|---|---|---|
| **user_profile_table** | Brain facts-by-category + narrative | A first-class, queryable *profile* surface + a readable `profile.md` projection; detection hook |
| **memory_first_retrieval** | `owner_context()` in CEO/executor/research | Uniform wiring into `build_system_prompt()` + the **chat** path; detection hook |
| **entity_extraction** | `extract_from_messages()` exists, runs in **sweep** (batch) | **Real-time** background extraction **after each message**; people as first-class nodes; detection hook |

**Verdict:** the hard 70–80% (embeddings, dedup, conflict, graph, communities, retrieval primitive,
Obsidian ingest) is **built and working**. What remains is **wiring, depth, a readable projection, and
detection** — exactly the "moderate, 1–2 week" shape you indicated.

---

## 3. The target: Awakening · "Understand Me"

From the tier registry (`api/dashboard.py`):

1. **Structured auto-updating user profile** — preferences, projects, habits, relationships, updated
   from every interaction (replaces hand-writing SOUL.md).
2. **Memory-first retrieval in all tasks** — every task consults your profile *first*.
3. **Entity extraction from conversations** — auto-extract people/projects/preferences/decisions and
   persist them.

All three are **memory features the Brain was designed for** — they are not Obsidian features.

---

## 4. Your context, synthesized (the 60 answers)

The full interview is in Appendix A. The decisive signals:

| Theme | Your answer | Architectural implication |
|---|---|---|
| Obsidian today | Installed, **barely used, empty vault** | No existing investment to preserve; Obsidian-centric = adopt-from-scratch |
| Plugin ecosystem | **Not valued much** | Obsidian's main differentiator doesn't apply to you |
| Graph view | **Want it in Mission Control** | MC stays the visualization home |
| Purpose | **Know me deeply** (personal Jarvis) | This is the Brain's exact remit, not a notes-app remit |
| "Never forget" | **My conversations with Tobi** | Chat-derived memory is primary → engine-side capture |
| Graph value | **Critical — connections matter** | Keep/strengthen the unified graph |
| Sources | **All** (chats, Obsidian, Notion, GDrive, email, GitHub) | Favors the unified mirror model already in place |
| Sensitivity | Personal + financial + work-confidential | Encryption-ready store matters; secrets stay in the Genesis vault |
| Plaintext `.md` locally | **Fine** | Unblocks a readable markdown layer for non-secret memory |
| Hosting | **Local + my git backup** | Markdown vault in git = perfect portable backup |
| Source of truth | **"Recommend for me"** | Decided below: **engine = truth, markdown = projection** |
| Hand-edit | **Occasionally**; manual edits **sacred** | Two-way sync with human-block protection |
| Depth | **Two-way sync**, would **install a bridge plugin** | Justifies the markdown projection layer |
| Ingest cap | **Full-text + chunking** | Replace the 500-char summary path |
| Unify | **One unified graph**; **MC is home** | Extend, don't fork |
| Extraction | **Aggressive auto-save**, but **confirm risky/sensitive** | Brain's confidence + sensitive model already does this |
| Profile store | **Readable markdown note** | `profile.md` projection of the DB |
| Psych profile | **Yes, full** | Brain already scaffolds this |
| SOUL.md | **Propose → I approve** | Gated writer, not autonomous |
| People | **Light**, but **first-class linked nodes**, from all sources | Add a `people` domain to the graph + `people/*.md` |
| Automation | **Fully auto background** + **near-real-time vault watch** | Background extractor + file-watcher |
| Scope / effort | **Full second-brain overhaul**, **1–2 weeks**, **incremental checkpoints**, **balanced refactor** | Aggressive on the memory layer, reuse the engine |
| Success | **All three** (knows me · cheap · queryable); top = **never re-explain myself** | Memory-first continuity is the win condition |
| Users | **Just me, forever** | No multi-tenant complexity needed |
| Final lean | **"You decide"** | Recommendation is mine to make → §7 |

---

## 5. Option space

| Option | Description |
|---|---|
| **A. Extend Mission Control** | Deepen the SQLite Brain/graph; Obsidian stays a minor read-only input. |
| **B. Obsidian-centric** | The vault becomes the primary store and UI; Tobi reads/writes `.md` as truth. |
| **C. Hybrid (recommended)** | SQLite engine = source of truth + retrieval; a two-way readable markdown vault as projection/edit surface. |

---

## 6. Head-to-head comparison

Scored against **your** stated needs (✅ fits, ⚠️ partial, ❌ conflicts).

| Dimension | A · Extend MC | B · Obsidian-centric | C · Hybrid |
|---|---|---|---|
| **Programmatic hybrid retrieval** (your "let Tobi decide", token-cheap) | ✅ native | ❌ Obsidian has no server-side retrieval API; plugins aren't programmable for Tobi | ✅ native (engine) |
| **24/7 server operation** (always-on) | ✅ | ❌ Obsidian is a desktop UI app, not a service | ✅ |
| **Unified graph (memory+task+project+notes)** | ✅ | ⚠️ only notes; tasks/projects live elsewhere | ✅ |
| **Token optimization via graph** | ✅ `graph_engine` block exists | ❌ no embeddings/graph-walk engine without plugins | ✅ |
| **Readable / portable / git-backed record** | ⚠️ DB isn't human-browsable | ✅ markdown is the point | ✅ markdown projection |
| **Occasional hand-editing, edits sacred** | ⚠️ via dashboard forms only | ✅ edit files directly | ✅ files + protected blocks |
| **Encryption for sensitive memory** | ✅ can reuse Genesis AES | ❌ plaintext `.md` only | ✅ engine encrypt-ready; secrets stay in vault |
| **Leverages existing build** | ✅ fully | ❌ discards most of it | ✅ fully + adds layer |
| **Mobile** (you: nice-to-have) | ⚠️ Telegram | ✅ Obsidian mobile | ⚠️ Telegram (+vault on phone if synced) |
| **Plugin ecosystem** (you: not valued) | n/a | ✅ but you don't want it | n/a |
| **Build effort this phase** | ✅ lowest | ❌ highest (re-platform) | ⚠️ moderate (+ markdown layer & watcher) |
| **Lock-in / ownership** | ⚠️ DB is yours but opaque | ✅ plain files | ✅ plain files + DB |
| **Conflict/merge complexity** | ✅ none | ⚠️ file-vs-file | ⚠️ managed (projection + sacred blocks) |

**Reading the table:** Option B wins exactly the rows you said *don't* matter (plugins, mobile-critical,
files-as-truth) and **loses every row tied to your real goals** (retrieval, 24/7, unified graph, token
cost, encryption, reuse). Option A wins the engineering rows but misses the readable/portable/editable
desires you repeatedly expressed (profile.md, person-notes, two-way, "own a record forever"). **Option C
takes A's engine and adds exactly the markdown affordances you asked for — at moderate cost.**

---

## 7. Recommendation — Hybrid ("engine + readable mirror")

> **Decision I'm making on the deferred questions:** **Source of truth = the SQLite Brain/graph
> engine. Markdown = a two-way readable *projection*, not the master.** Tobi *does* write back (readable
> notes), but the engine arbitrates. Your hand-authored blocks are fenced and never overwritten.

### 7.1 Four layers

```
┌─────────────────────────────────────────────────────────────────────┐
│ L4 · CAPTURE / EXTRACTION                                           │
│   • After each message → background extract_from_messages()         │
│   • Aggressive auto-save (conf ≥ 0.7); risky/sensitive → confirm Q  │
│   • Upserts facts + people/project nodes into the engine            │
├─────────────────────────────────────────────────────────────────────┤
│ L3 · RETRIEVAL (memory-first)                                      │
│   • profile_context() + hybrid (embeddings ⊕ graph-walk ⊕ keyword) │
│   • Wired into build_system_prompt() + chat + every task handler    │
│   • Adaptive token budget per task  ← the "cheaper memory" win      │
├─────────────────────────────────────────────────────────────────────┤
│ L2 · MARKDOWN PROJECTION (the vault)  ⇄ two-way, git-backed        │
│   • profile.md · people/<name>.md · projects/ · daily/ · decisions/ │
│   • File-watcher ingests your edits; <!-- tobi:auto --> vs human    │
│     blocks; human blocks are SACRED                                  │
├─────────────────────────────────────────────────────────────────────┤
│ L1 · ENGINE (source of truth)  — extend, don't replace             │
│   • SQLite Brain (facts, categories, psych) + unified graph_nodes/  │
│     edges + fastembed embeddings + communities                      │
│   • Encryption-ready; secrets remain in the Genesis vault           │
└─────────────────────────────────────────────────────────────────────┘
```

### 7.2 What we reuse vs build

- **Reuse as-is:** embeddings, semantic/ref edges, community detection, dedup/conflict/decay, the Brain
  dashboard UI, `owner_context`, the MC graph view.
- **Extend:** `_sync_local()` → **full-text + chunked** ingest, lift the 500 cap, add a **file-watcher**
  for near-real-time sync; add a **`people` graph domain**.
- **Build new:** the **markdown projection writer** (DB → readable notes, with sacred human blocks),
  the **real-time post-message extractor**, uniform **memory-first wiring**, and the **detection hooks**
  that finally flip the three abilities to active.

### 7.3 How this completes "Understand Me" 3/3

| Ability | Hybrid implementation |
|---|---|
| user_profile_table | Brain facts (engine) **+ generated `profile.md`** you can read/edit; detection hook checks profile rows |
| memory_first_retrieval | `profile_context()` injected into `build_system_prompt()` + chat + task handlers; detection hook checks call-site |
| entity_extraction | Background `extract_from_messages()` after each message; people → first-class linked nodes + `people/*.md` |

---

## 8. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Two-way sync merge conflicts | Projection model: DB is truth; only fenced **human blocks** sync back; "you always win" on those |
| Sensitive data in plaintext `.md` | Sensitive categories stay **engine-only / encrypted**; vault gets non-secret memory; you opted plaintext-OK locally anyway |
| Aggressive extraction saves wrong facts | Confidence gate + **confirm-queue for risky/sensitive**; easy delete; auto-decay |
| "Full overhaul" scope creep vs 1–2 wks | Deliver **incrementally with checkpoints** (§9); engine reuse keeps it bounded |
| File-watcher churn / 500-cap perf | Chunk + debounce; index incrementally; cap lifted with batched embedding |

---

## 9. Proposed build plan (1–2 weeks, checkpointed)

- **M1 — Wire what exists (fast win):** add detection hooks + uniform `profile_context()` into
  `build_system_prompt()`/chat → **abilities flip toward active**; surface profile in MC. *Checkpoint.*
- **M2 — Real-time extraction:** background post-message `extract_from_messages()` with confidence +
  confirm-queue; add **people** domain as first-class linked nodes. *Checkpoint.*
- **M3 — Deepen ingest:** full-text + chunked `_sync_local()`, lift the 500 cap, **file-watcher** for
  near-real-time vault sync. *Checkpoint.*
- **M4 — Markdown projection:** DB → `profile.md` / `people/*.md` / `decisions/`, sacred human blocks,
  git-backed; two-way reconcile. *Checkpoint → Awakening "Understand Me" = 3/3.*

---

## 10. Decisions made on your behalf (you said "you decide")

1. **Source of truth = SQLite engine; markdown = projection.** (Integrity, retrieval, encryption.)
2. **Tobi writes back** readable notes, but only the engine is authoritative; **human blocks are sacred.**
3. **Keep Mission Control as home**; the vault is a companion surface, not a replacement.
4. **Do not re-platform onto Obsidian.** Adopt its *file format and editability*, not its app-as-architecture.

If you disagree with #1 or #2, that's the only fork that materially changes the plan — say the word and
I'll re-scope toward "markdown-as-truth."

---

## Appendix A — Full 60-question interview

**Obsidian reality:** installed-but-barely-used · empty vault · local-first (+git backup later) ·
values Smart Connections/Dataview/Templater *in principle*.
**Workflow:** let Tobi structure it · wants daily journaling · mixed capture · wants graph **in MC**.
**Purpose:** know me deeply · never-forget = **my chats** · graph connections **critical** · about **me**.
**Sources/scale:** **all** sources · medium (1–10k) · **constantly** changing · sensitive (personal+financial+work).
**Truth/editing:** *recommend for me* · edit **occasionally** · write-back *unsure* · **my edits win**.
**Retrieval:** goal = **cheaper long-term memory** · **hybrid** · let Tobi decide context · few-sec latency OK.
**Access:** **MC dashboard** primary · mobile nice · always-online · **24/7**.
**Privacy:** local + git backup · encryption nice-not-blocking · **plaintext `.md` fine** · cloud sync don't-care.
**Depth/effort:** **two-way sync** · would install bridge plugin · plugins **not** valued · **moderate** effort.
**Existing build:** *assess it honestly* · **full-text+chunking** ingest · **one unified graph** · **MC is home**.
**Extraction/profile:** **aggressive auto-save** · profile as **readable markdown** · **full** psych profile · SOUL.md **propose→approve**.
**People:** **light** · from chats+Obsidian+email+manual · **first-class linked nodes** · plaintext OK locally.
**Automation:** **fully auto background** · **near-real-time** vault watch · Tobi auto-clean + spot-fix · **confirm risky** facts.
**Scope:** **full second-brain overhaul** · **1–2 weeks** · **incremental checkpoints** · **balanced** refactor.
**Success:** **all three** · top outcome = **never re-explain myself** · **single-user** forever · direction = **"you decide."**

---

## Appendix B — Evidence index (code is source of truth)

- `core/brain.py` — categories L33–35; thresholds L28–32; `extract_from_messages` L508; `retrieve` L758;
  `synthesize_narrative` L791; `chat`/`chat_stream` L810/858.
- `core/graph_engine.py` — tunables L28–32; domains L42–51; `upsert_node` L55; `sync_internal` L202;
  `build_semantic_edges` L295; graph context block L647; **`_sync_local` (Obsidian) L811–846**; `rebuild` L870.
- `api/dashboard.py` — Awakening "understand" abilities L2651–2661; `_detect_abilities` returns Tier-0 only,
  *"Tier 1+ default to False"* L2934–2949; Brain API surface L3533–3698.
- Related prior art: `docs/feature-idea-queue/BRAIN_SPEC.md`.

# TOBI "Graph View" — Second-Brain Knowledge Graph

> **Queue status:** 🟡 Queued · **Depends on:** Brain ([BRAIN_SPEC.md](BRAIN_SPEC.md)) for embeddings + memory nodes · **Owner-reviewed:** 30 Q&A captured below
> Part of the [Feature Development Queue](QUEUE.md). Extends Brain into an Obsidian-style, glowing-neuron graph that unifies memories, tasks, projects, and integrated personal data (Notion/GitHub/Drive/Obsidian) into one navigable "second brain."

## Context

The owner wants an Obsidian-like **graph view** where every piece of their world is a node — Brain memories, tasks, projects, and data pulled from Notion, GitHub, Google Drive, and local/Obsidian vaults — interconnected and explorable as a living neuron map inside Mission Control. The aesthetic target is **modern, scientific, glowing** (bloom, animated link "flow," cluster halos). This is the visual + relational layer on top of the Brain: where Brain stores *what TOBI knows*, Graph View shows *how it all connects*.

`core/integrations.py` already ships connectors (Notion, GitHub, Google, Vercel, Supabase) with a `get_integration(name)` factory, so the "second brain" sources are largely wired. `graphify-out/` is empty (graphify is a *code*-navigation tool and unused here) — this is a fresh **owner-data** graph, unrelated to graphify.

This spec reflects 30 clarifying answers from the owner (summarized below).

## Decisions (from Q&A)

| Area | Decision |
|---|---|
| Node scope (v1) | **Everything**: memories + tasks + projects + integrations |
| Data model | **Per-domain graphs + switcher**, backed by **one unified node/edge store** (enables an "All" cross-domain view) |
| Render library | **Recommend** → `react-force-graph-2d` (canvas, glow via shadowBlur, built-in directional-particle "flow", drag/zoom/hover). Fallback to Sigma/Cosmograph only if scale demands. |
| Dimension | **2D** with glow/bloom |
| Node visual | Color + **icon** by **domain + category** |
| Edge sources | **All**: explicit references + semantic similarity (embeddings) + shared tags/categories + manual links |
| Embeddings | **Embed every node type** (reuse Brain `core/embeddings.py`) for cross-domain semantic links |
| Edge visual | **Thickness (strength) + color (type) + animated particle flow** |
| Integrations (v1) | **Notion, GitHub, Google Drive/Docs, Local files / Obsidian vault** |
| Integration sync | **Periodic background sync** (snapshots) |
| Integration granularity | **Rich sub-nodes** (pages, repos, issues, commits, docs) |
| Integration editability | **Read-only mirrors** + MC-side links/notes |
| Interactions | **All**: click→detail panel, hover→preview+highlight neighbors, double-click→expand, drag→pin |
| Navigation | **Global graph + focus-on-click** |
| Filters | **All**: by domain, category/tag, time, connection strength |
| Search | **Keyword + semantic**, highlight + **fly-to** |
| Layout | **Force-directed (organic)** |
| Clustering visual | **Glowing hulls + color** |
| FX level | **Full neuron mode** (bloom, link particles, node pulsing) **+ a performance toggle** |
| Node size | **Connection count (degree)** |
| Scale | **Plan for growth** (WebGL/canvas + filtering + progressive load) |
| Compute | **Recommend** → **backend builds the graph** (nodes/edges API), frontend renders |
| Freshness | **On load + manual refresh** |
| Layout persistence | **Save manual pins; auto-layout the rest** |
| Placement | **Dedicated "Graph" page + domain switcher** |
| Editing | **Full**: create nodes, draw/delete edges, edit content from the graph |
| Manual linking | **Drag node-to-node** |
| Time dimension | **Timeline scrubber** to replay graph growth |
| AI features | **Deferred to v2**: find-path, ask-the-graph, auto-insights, suggest-links |

## Architecture & key choices

- **Unified graph store in SQLite** (same DB as Brain). Internal domains (memory/task/project) are **registered** as graph nodes that reference their source rows; integration items are **mirrored** in as read-only nodes. One store = one place for edges, embeddings, saved positions, and cross-domain links — while the UI's per-domain switcher just filters by `domain`.
- **Render = `react-force-graph-2d`** (vasturiano). Rationale: best fit for the requested 2D glowing-neuron look — custom `nodeCanvasObject` (bloom via `shadowBlur`, color/icon, size by degree), `linkDirectionalParticles` for the animated "flow," `onRenderFramePre` to draw glowing cluster **hulls**, plus built-in drag/zoom/hover and d3-force layout. A **performance mode** strips bloom/particles and caps nodes for large graphs; if the graph routinely exceeds ~10k visible nodes we revisit Sigma.js/Cosmograph (noted as a swap-in, isolated behind our canvas wrapper).
- **Backend builds the graph.** A `/api/graph` endpoint returns filtered `{nodes, edges}` (including precomputed semantic links), keeping heavy work (embeddings, ref-resolution, degree) server-side and the client a pure renderer — this is what makes "plan for growth" tractable.
- **Embeddings reuse Brain's `core/embeddings.py`** (local fastembed). Every node gets an embedding; semantic edges = top-k cosine above a threshold, **capped per node** to avoid a hairball.
- **Security:** inherits Brain's local-only posture; integration data is mirrored locally, never re-shared externally (except the unavoidable LLM calls already used elsewhere).

## Data model — new tables (`core/database.py`, idempotent `_ensure_graph_schema(conn)` from `init_database()`)

- **`graph_nodes`** — `id, domain TEXT('memory'|'task'|'project'|'notion'|'github'|'gdrive'|'local'), ref_kind TEXT, ref_id INTEGER/TEXT (link to source row or external id), title, summary, category, color, icon, source_url, embedding BLOB, embed_model, degree INTEGER DEFAULT 0, x REAL, y REAL, pinned INTEGER DEFAULT 0, created_at, updated_at, deleted_at`. Indexes on `(domain)`, `(category)`, `(ref_kind, ref_id)`.
- **`graph_edges`** — `id, source_id FK, target_id FK, edge_type TEXT('ref'|'semantic'|'tag'|'manual'), weight REAL DEFAULT 1, directed INTEGER DEFAULT 0, created_by TEXT('system'|'owner'), created_at, deleted_at`. Unique-ish guard on `(source_id, target_id, edge_type)`.
- **`graph_sync_state`** — `source TEXT PK, last_synced_at, cursor TEXT, item_count`.
- Reuse Brain's `brain_memories.embedding`; other domains' embeddings live on `graph_nodes`.

DB helpers (mirroring existing `add_*`/`list_*` style): `upsert_node`, `get_node`, `list_nodes(filters)`, `delete_node`, `upsert_edge`, `delete_edge`, `list_edges(filters)`, `recompute_degree`, `save_positions(pins)`, sync-state get/set, `timeline_events(from,to)`.

## Backend work (`tobi/`)

1. **`core/graph_engine.py`** (new):
   - `sync_internal()` — register/refresh memory/task/project nodes from existing tables; build **ref edges** (task→project via `pm_project_id`, task→goal, memory→category-as-node or hull, etc.).
   - `sync_source(name)` — pull from a `core/integrations.py` connector → upsert **read-only rich sub-nodes** (Notion page/subpage, GitHub repo/issue/commit, Drive doc, local/Obsidian `.md`) + ref edges; embed them.
   - `build_semantic_edges()` — top-k cosine per node (capped) → `semantic` edges; `build_tag_edges()` — shared tag/category.
   - `get_graph(filters)` — return filtered nodes+edges; `expand(node_id)` — neighbors for progressive load; `search(q)` — keyword + semantic → node ids.
   - (v2) `find_path(a,b)`, `ask(q)`, `insights()`, `suggest_links()`.
2. **Scheduler** — add `job_graph_sync()` to `main.py` (periodic): `sync_internal()` + `sync_source()` for each connected integration + `build_semantic_edges()` + `recompute_degree()`.
3. **API endpoints** in `api/dashboard.py` (`_get_conn()` + Pydantic + `/api/*`):
   - `GET /api/graph` (filters: `domain`, `category`, `from`, `to`, `min_weight`, `q`) → `{nodes, edges}`.
   - `GET /api/graph/node/{id}` (detail + source content + connections) · `POST /api/graph/nodes` · `PATCH` · `DELETE`.
   - `POST /api/graph/edges` (manual link) · `DELETE /api/graph/edges/{id}`.
   - `POST /api/graph/node/{id}/expand` · `POST /api/graph/layout` (save pins/positions).
   - `POST /api/graph/sync/{source}` (manual) · `GET /api/graph/sources` (status).
   - `GET /api/graph/timeline` (events for the scrubber) · `GET /api/graph/search?q=`.

## Frontend work (`tobi/dashboard/src/`)

1. **Deps** — add `react-force-graph-2d` (+ `d3-force`, `d3-quadtree` as needed). Confirm Vite build size; lazy-load the Graph page to keep the main bundle lean.
2. **Routing/nav** — register `/graph` in `App.tsx`; nav item in `AppShell.tsx` (`Share2`/`Workflow`/`Brain` lucide icon); `PageLoader` preset `graph`.
3. **`api.ts`** — types (`GraphNode`, `GraphEdge`, `GraphResponse`, `GraphFilters`, `TimelineEvent`) + functions for every endpoint.
4. **`pages/Graph.tsx`** — header with **domain switcher tabs** (All / Memory / Tasks / Projects / Notion / GitHub / Drive / Local), **filter panel** (domain toggles, category/tag, time range, min connection strength), **search bar** (keyword + semantic, fly-to), **legend**, **performance-mode toggle**, **refresh**, and a bottom **timeline scrubber**.
5. **Components** (`components/graph/`):
   - `ForceGraphCanvas.tsx` — wraps `ForceGraph2D`; custom `nodeCanvasObject` (glow via `shadowBlur`, domain/category color + icon, size by `degree`, gentle pulse), link styling (width=weight, color=type, `linkDirectionalParticles` flow), **cluster hulls** via `onRenderFramePre` (convex hull + glow per category/domain), hover→highlight neighbors (dim others), click→detail, double-click→`expand`, **drag-to-pin**, and **drag node-to-node** to create an edge. All rendering logic isolated here so the lib can be swapped if scale demands.
   - `NodeDetailPanel.tsx` — slide-in panel: content, metadata, source link (open in Notion/GitHub/…), connections list, add/remove links, edit (for editable domains).
   - `GraphFilters.tsx`, `GraphLegend.tsx`, `TimelineScrubber.tsx`, `GraphToolbar.tsx`.
   - Reuse `useToast`, theme tokens, and the existing glow utilities in `index.css` (extend with a bloom/pulse keyframe set).

## Visual style (glowing neuron)

- Bloom approximated in 2D canvas via layered `shadowBlur` + additive draws; node **pulse** on a `requestAnimationFrame` loop; **link particles** for "synapse" flow; **cluster halos** as soft glowing hulls tinted by domain/category; dark canvas with subtle grid (reuse `.grid-bg`). Honors the per-category color system shared with Brain.

## Performance (plan for growth)

Backend-side filtering; **cap semantic edges per node**; **level-of-detail** (hide labels when zoomed out, throttle/disable particles past a node threshold); **progressive expand** instead of loading everything; **performance mode** toggle (no bloom/particles, simplified nodes); lazy-loaded route. These keep it smooth from hundreds to many thousands of nodes; beyond that, swap the canvas wrapper to Sigma/Cosmograph.

## v1 scope vs deferred

- **In v1:** unified graph store; internal domains + **all four integrations** (rich sub-nodes, periodic sync, read-only); force-directed 2D neuron view with glow/hulls/particles + performance toggle; all interactions; global+focus nav; all filters; keyword+semantic fly-to search; **full editing** (nodes + edges) with **drag-to-link**; saved pins; **timeline scrubber**.
- **v2 (not built now):** AI features — **find-path (X↔Y)**, **ask-the-graph**, **auto-insights**, **suggest-links-to-confirm**; optional 3D mode; two-way integration sync.

## Verification (end-to-end)

1. **Backend:** `python main.py api`; confirm `graph_*` tables created; `job_graph_sync()` populates nodes/edges from internal data + a connected source.
2. **Embeddings/semantic edges:** verify nodes get embeddings and `semantic` edges appear (capped per node).
3. **Dashboard:** `cd tobi/dashboard && npm run dev` → open `/graph`.
   - Domain switcher filters correctly; "All" shows cross-domain edges.
   - Glow/particles/hulls render; performance-mode toggle strips them.
   - Click→detail panel (with working source link for an integration node); hover highlights neighbors; double-click expands; drag pins; **drag node-to-node creates an edge** (persists via `/api/graph/edges`).
   - Filters (domain/category/time/strength) and keyword+semantic search fly-to all work.
   - Timeline scrubber replays node/edge appearance over time.
   - Manual refresh + per-source sync update the graph.
4. `cd tobi/dashboard && npm run build` clean (Graph route lazy-loaded); backend imports without error.

## Risks / watch-items

- **Bundle size** — `react-force-graph-2d` + d3 is sizable; lazy-load the route and keep it out of the main chunk.
- **Hairball / over-linking** — cap semantic edges per node and gate by a similarity threshold; lean on hulls + tags rather than drawing every tag edge.
- **Integration rate limits / sync cost** — periodic sync with cursors in `graph_sync_state`; back off and surface per-source status.
- **Scale ceiling** — isolate all rendering in `ForceGraphCanvas.tsx` so a Sigma/Cosmograph swap is a contained change if node counts explode.
- **Privacy** — integration content mirrored locally only; same local-first posture as Brain.

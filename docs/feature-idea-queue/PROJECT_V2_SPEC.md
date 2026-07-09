# Project v2 — Full-page project workspace, pro Tasks, a real Resources drive, and full TOBI control

> Queue item **#12** · Status: 🟡 Queued · 60 Q&A captured (owner-reviewed this session).
> Upgrades `dashboard/src/pages/Projects.tsx` (1419-line right-side `ProjectDrawer` popup + 6 tabs)
> into a **full-page project workspace** that opens as a tab in the forthcoming **Global Header Tab
> System**, with an upgraded Overview, a professional single-view Task manager, a Google-Drive-style
> **Resources** tab (renames "Docs"), a richer Goals tab, custom project icons, and end-to-end TOBI
> (Conductor #7) read+act control with the existing approval model.

## Mission

Scale Projects from a quick-peek drawer into a real, full-page **workspace** you live in — open several
projects at once (via the global header tabs), manage tasks like Trello/Asana/ClickUp, keep a per-project
**drive** of files + online resources (tracked by Storage #10, searchable by chat), and let **TOBI**
create/edit/organize everything by conversation, asking approval only for high-risk actions.

## Current state (what exists today)

- **`Projects.tsx`** — grid/list of projects → click opens a **right-side drawer** (`ProjectDrawer`,
  `max-w-2xl`) with 6 tabs: **Overview, Tasks, Goals, Docs, Missions, Activity**. Drag-reorder, status
  filters, search, create-modal (emoji-only icon from a fixed 18-set, accent color, KPI), save-as-template.
- **Tasks tab** — flat list, inline title edit, priority (P0–P3) + status selects, assignee (owner/tobi),
  due date, JSON **subtasks** (title+done only, via `/api/pm/projects/{id}/tasks/{tid}/subtasks`).
- **Docs tab** — attach a **filename or URL only** (no real upload/storage); `pm_files` rows.
- **Backend** — PM system: `pm_projects`, `tasks` (`pm_project_id`), `pm_goals`, `pm_missions`,
  `pm_activity`, `pm_files`, `pm_templates`; `/api/pm/*` endpoints. **Conductor #7** already drives
  `pm_projects` + `tasks.pm_project_id` (create/edit/complete/delete/assign, tiered permissions, `tobi_actions` audit).
- **Storage #10** already rolls a **Projects/Docs** feature bucket and per-feature sizes.

## Dependency — Global Header Tab System (separate queue item, not built yet)

The Notion-style **"open multiple projects as tabs"** requirement is delivered by a **Global Header Tab
System** the owner is queuing separately. Project v2 does **not** build its own tab bar. **[D2, D7, D8]**

**Plug-in with graceful fallback [D9]:** each project opens as a **full-page workspace** and *registers*
itself with the global tab system **if present**. Until that ships, you open **one project full-page at a
time** (deep-linked URL) with **no throwaway tab code** — multi-tab "just works" once the header system
lands. The global system owns tab persistence (**restore across sessions [D3]**), the **max-5-open cap +
horizontal scroll + overflow menu [D4]**, and the "open a 6th → the global system decides" behavior **[D7]**.

---

## Decisions (60 Q&A)

### A. Navigation & workspace shell
- **D1 Open mode:** Full-page **workspace** (header + inner tab strip + full-width content) replaces the
  drawer popup.
- **D2 Multi-project tabs:** Live in the **Global Header Tab System** (separate feature) — not a project-local bar.
- **D3 Persistence:** Open project tabs **restore across reloads/sessions** (owned by the global tab system).
- **D4 Overflow/cap:** **Max 5** open project tabs, horizontal scroll + **overflow menu** (global tab system property).
- **D5 URL routing:** **Deep-linkable** `/projects/:id/:tab` — back/forward works, links shareable, restore = reopen URLs.
- **D6 Projects home:** **Both** — sidebar "Projects" entry **collapse/expands** to a list **and** a full grid/list is reachable.
- **D7 6th tab:** Delegated to the global tab system (opening more projects = opening tabs there).
- **D8 Coexistence:** **No** separate project tab bar; reuse the global header bar's tab logic.
- **D9 Dependency mode:** **Plug-in + graceful fallback** — full-page now (1 at a time), auto-gains multi-tab later. No throwaway code.
- **D10 Sidebar list:** "Projects" expands to **Recents + All** (collapsible); clicking opens the project workspace.

### B. Overview tab
- **D11 Layout:** **Bento** (asymmetric card grid) — different-sized cards for hierarchy.
- **D12 Components (all):** Description (owner+TOBI) · Active tasks (scrollable) · Metric stat cards · Resources-usage + Goals summary + Recent activity.
- **D13 Description editor:** **Plain multiline** (consistent, simple).
- **D14 TOBI on description:** **Draft/edit with approval to overwrite** — append is free, overwriting owner text confirms; edits **attributed** (owner vs TOBI).
- **D15 Metric cards (all):** **Task** (done/total, %, overdue, active) · **Time** (days-to-deadline, created/updated, last-activity) · **Resources+Goals** (size/count, on-track/at-risk, KPI) · **Effort/estimate** (sum of estimates, est vs done).
- **D16 TOBI reads metrics:** New Conductor read tool **`project_overview(id)`** returns the whole snapshot so chat answers are grounded in real numbers.

### C. Tasks tab (single, pro List view)
- **D17 Views:** **List only** — one upgraded, professional List view (no Kanban/Table/Calendar in v2).
- **D18 Default:** List.
- **D19 Grouping:** By **Status** (Planned · In progress · Paused · Blocked · Done), group-by available.
- **D20 Ordering:** **Manual drag (persisted)** + a **sort toggle** (due/priority on demand).
- **D21 Task detail:** **Right drawer, expandable to full page** (title, plain description, dates, subtasks, deps, activity).
- **D22 Dates:** Optional **start** + optional **due** + optional **reminder** (pings chat/Telegram before due).
- **D23 Task description:** **Plain multiline**.
- **D24 Subtasks:** **One level, rich** — each has its own checkbox, **assignee**, and **due**; progress **rolls up** to the parent.
- **D25 Extra fields:** **Assignee + Estimate** and **Dependencies**. (No labels, no task attachments, no per-task goal field.)
- **D26 Labels:** **None** — rely on priority + status.
- **D27 Dependencies:** **Yes — simple blocks / blocked-by** (blocked tasks show a badge; no Gantt).
- **D28 Recurring:** **Deferred** to a later phase.
- **D29 TOBI task caps (all):** create/rename/edit fields · move status/reorder/subtasks · **bulk/multi-task** · delete + set dependencies.
- **D30 High-risk (approval):** **Delete task(s)** and **bulk writes over a threshold** (> N tasks in one command).
- **D31 Approval UX:** **Confirm/Cancel card in chat** (existing Conductor pattern + typed "yes/có").
- **D32 Bulk execution:** Applied **one-by-one**, each change logged individually to **TOBI Actions**; a bulk op above the threshold takes **one upfront approval**, then streams through.

### D. Goals tab
- **D33 Metric cards:** **Total + avg progress** · **Completed + overdue** · **Weighted/priority progress** (above the list).
- **D34 Search:** **Title + description**.
- **D35 Filters:** **Status/progress bucket** · **Priority** · **Due window**.
- **D36 Goal↔task:** **Optional task link + rollup** — a goal may link tasks (auto-advances progress); **metric mode still works** per goal.

### E. Resources tab (renames "Docs" → **Resources**)
- **D37 Backend:** **Real files on disk**, size **tracked** by Storage #10.
- **D38 Location:** `~/.mmo_agent/projects/{id}/resources/`.
- **D39 Upload limit:** **~100 MB/file** (warn near the cap).
- **D40 Storage-page integration:** **Both** — per-project size (shown on Overview) **and** a dedicated bucket, rolling into the existing Projects bucket.
- **D41 Sources:** **Device upload** (drag-drop + picker, core) · **Paste/import a URL** (online resources) · **Google Drive import** (copy). *(Chat-attachment/Notion promotion deferred.)*
- **D42 First-class link types:** **Google Docs/Sheets/Slides** · **YouTube** (transcript) · **Web page** (readable extract) · **PDF URL + GitHub** file/repo.
- **D43 YouTube:** Store link + **fetch transcript** as searchable text (no auto-summary by default).
- **D44 Drive import:** **Copy into the TOBI store** (counts to storage, works offline, TOBI can read).
- **D45 Layout:** **Google-Drive-style** — grid/list toggle + **folders** + breadcrumb.
- **D46 Organization:** **Folders + tags**.
- **D47 Auto-categorize:** **Manual only** — TOBI organizes only on command.
- **D48 Preview:** **In-app preview** (PDF/image/text/markdown/video) **+ open-external** (Office → metadata + open in Drive/externally).
- **D49 TOBI on resources (all):** add link/file + fetch (URL/YouTube/Drive) · read/summarize · search · organize + **delete (approval)**.
- **D50 Content indexing (RAG):** **Index text content per project** (extract from docs/PDF/transcripts → embeddings via fastembed, keyword fallback) so chat pulls real passages.
- **D51 File icons:** **Curated icon set per type** (.md/.doc/.xls/.pdf/.txt/image/video/link/Drive/YouTube/GitHub), color-coded.
- **D52 Graph/Brain:** Resources **become Graph nodes** linked to their project (reuse `graph_engine`).

### F. Project icons (bonus)
- **D53 Library:** **Emoji + curated vector icon pack (lucide/brand) + custom upload** (PNG/SVG).
- **D54 Storage:** Custom icons stored in the **TOBI database** (resized, dimension-capped; travels with backup/export).
- **D55 TOBI auto-pick:** When TOBI **creates a project from chat**, it **auto-picks a fitting icon + accent** from the name/description.
- **D56 Change icon:** From the **Overview tab** (click the icon → picker) **and** the create modal.

### G. Scope, data, phasing
- **D57 Missions tab:** Move to a **disabled "Soon"** tab at the **end** of the nav.
- **D58 Backend:** **Extend the PM schema** (one source of truth the Conductor already uses).
- **D59 Migration:** **Auto-migrate in place** — existing projects/tasks keep working; old `pm_files` docs convert to **Resource "link" items**; new fields default empty.
- **D60 Phasing:** **Single big release** (all workstreams shipped together; build order below is internal only).

---

## Architecture

### Frontend
- **`ProjectWorkspace`** (new, full-page) replaces `ProjectDrawer`. Route **`/projects/:id/:tab`** (deep-link
  **D5**); on mount it **registers with the Global Header Tab System if available**, else renders standalone
  full-page **[D9]**. Header = icon (click → **IconPicker**) + name/status/edit + actions; inner tab strip:
  **Overview · Tasks · Goals · Resources · Activity · Missions(Soon, disabled, last) [D57]**.
- **Sidebar** — "Projects" entry becomes **collapse/expandable** (Recents + All) **[D10]**; the grid/list stays
  as the reachable home **[D6]**.
- **Overview** — **bento** card grid **[D11]** with: plain-text **Description** (owner/TOBI attributed) **[D12–D14]**,
  **Active tasks** (scrollable, click → task drawer), **metric stat tiles** (task/time/resources+goals/effort
  **[D15]**, reuse `SpotlightCard`/`CountUp`), **Resources-usage** card (size + count + type breakdown), **Goals
  summary**, **Recent activity**.
- **Tasks** — one **pro List view [D17]**: grouped by status **[D19]**, **manual drag order + sort toggle
  [D20]**, inline fields, rich **subtasks [D24]**, **dependency** badges **[D27]**, quick-add. Click → **right
  drawer, expandable to full page [D21]** (start/due/reminder **[D22]**, plain description **[D23]**, subtasks,
  deps, estimate/assignee **[D25]**, activity).
- **Goals** — **metric cards [D33]** + **search [D34]** + **filters [D35]** above the existing goal list;
  goal detail gains **optional task-link rollup [D36]**.
- **Resources** — **Drive-style [D45]**: grid/list toggle, **folders + breadcrumb**, tags **[D46]**, drag-drop
  **upload [D41]**, "Add link" (URL/YouTube/Drive) modal **[D42–D44]**, **type icons [D51]**, **in-app preview
  + open-external [D48]**.
- **IconPicker** (new) — emoji tab + **icon-pack** tab (lucide/brand) + **upload** tab **[D53]**; used by Overview
  header and create modal **[D56]**.

### Backend (extend PM schema **[D58]**)
- **`pm_projects`** += `description` (plain text), `icon_type` (`emoji|icon|custom`), `icon_value` (emoji char /
  icon key / `pm_icons` ref), `resources_bytes` (cache). Keep `accent_color`.
- **`tasks`** += `start_at`, `reminder_at`, `estimate_min`, `description` (plain); upgrade `sub_tasks` JSON to
  rich items `{id,title,completed,assignee,due_at}`; **dependencies** via `pm_task_deps(task_id, blocks_task_id)`.
- **`pm_goals`** += `mode` (`metric|task_rollup`); **`pm_goal_tasks(goal_id, task_id)`** for linkage/rollup **[D36]**.
- **`pm_folders`** (new) — `id, project_id, parent_id, name`.
- **`pm_resources`** (new) — `id, project_id, folder_id, kind (file|link), name, ext/type, source
  (device|url|drive|youtube|web|github|pdf), size_bytes, disk_path, url, mime, thumb, tags(JSON),
  created_by (owner|tobi), created_at`.
- **`pm_resource_chunks`** (new, RAG **[D50]**) — extracted text chunks + embeddings (fastembed; keyword
  fallback), joined to `graph_nodes` for the **Graph** link **[D52]**.
- **`pm_icons`** (new) — `id, project_id, mime, bytes/base64` (capped) for custom uploads **[D54]**.
- **Storage #10** — resource sizes roll into the Projects bucket + a dedicated **Project Resources** bucket;
  per-project size surfaced to Overview **[D40]**.

### API (extend `/api/pm/*`)
- `GET /api/pm/projects/{id}/overview` — full metrics snapshot (drives Overview + the `project_overview` tool).
- Tasks: extend patch to accept `start_at/reminder_at/estimate_min/description`; `.../deps` add/remove;
  reminder scheduler job (chat/Telegram ping).
- Resources: `GET/POST /resources` (multipart upload), `DELETE /resources/{rid}`, `PATCH` (move/tag/rename),
  `POST /resources/import-url` (Docs/web/PDF/GitHub/YouTube), `POST /resources/import-drive`, `GET
  /resources/{rid}/content` (preview/summary/RAG), `GET/POST /folders`.
- Icons: `POST /api/pm/icons` (upload), used by project patch.

### TOBI / Conductor (#7) integration
- **Read tools:** `project_overview(id)` **[D16]**, `search_resources`, `read_resource`.
- **Act tools (existing tiers + `tobi_actions` audit):** tasks — create/rename/edit/move/reorder/subtasks/
  **bulk**/delete/deps **[D29]**; resources — add/import/organize/**delete** **[D49]**; project — `edit_description`
  **[D14]**, `set_icon` + **auto-pick on create [D55]**.
- **Permissions [D30–D32]:** low-risk auto-executes; **delete** and **bulk > N** are **proposed → Confirm/Cancel
  card in chat** (typed "yes/có"); bulk applies **one-by-one**, each logged.

### Migration **[D59]**
- Idempotent `_ensure_pm_v2_schema` adds columns/tables; on first load, each `pm_files` row → a `pm_resources`
  **link** item; existing tasks gain empty new fields; Docs tab label → **Resources**; Missions tab → disabled "Soon".

## Verification / acceptance
1. Open a project → **full-page workspace** at `/projects/:id/overview`; deep-link + back/forward work; registers as a global tab when that system exists, else standalone.
2. **Overview** bento shows description (owner/TOBI edit + overwrite-confirm), scrollable active tasks, all metric tiles, resources size; `project_overview(id)` answers "how's Alpha?" grounded.
3. **Tasks** list: drag-order persists, sort toggle, right-drawer detail (start/due/reminder, subtasks w/ assignee+due, deps badge, estimate); TOBI bulk-completes via chat (one-by-one, logged), delete/bulk>N confirm.
4. **Goals** metric cards + search + filters; a goal with linked tasks rolls up.
5. **Resources**: drag-drop upload (disk, ≤100MB), folders+tags, add YouTube (transcript stored+searchable), Drive copy, in-app preview; size shows on Overview + Storage page; content RAG answers a "what does the spec say…?" query; resource appears as a Graph node.
6. **Icons**: emoji/icon-pack/upload picker from Overview + create; TOBI auto-picks on chat-create.
7. Missions tab shows as disabled **"Soon"** at the end; migration converts old docs; `npm run build` clean; PM/Conductor regressions green.

## Risks / watch-items
- **Global Header Tab System not yet built** — must ship the plug-in/fallback so nothing is throwaway (**D9**).
- **File handling** — size cap, mime/type sniffing, path-traversal safety, thumbnails; keep bytes on disk, metadata in DB.
- **Online ingestion** — YouTube transcript + readable-web fetch can fail/limit; degrade gracefully; Google Docs/Drive need the Google connector (honest "connect first").
- **RAG cost/size** — index only text, per-project; reuse fastembed + keyword fallback; watch `pm_resource_chunks` growth in Storage.
- **Scope** — "all at once" is large; build order (workspace+Overview+Tasks → Resources+Goals → icons+RAG/Graph+TOBI polish) is internal sequencing, single release.
- **Reuse, don't rebuild** — keep the PM backend, Conductor tools/permissions/audit, Storage buckets, graph_engine, motion primitives; this is an upgrade layer.

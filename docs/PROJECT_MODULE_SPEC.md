# Mission Control — Project Module Specification

> **Status:** Requirements COMPLETE — 30 decisions locked (P1–P30).
> **Phase:** Specification PENDING APPROVAL. Do not implement until the user approves.
> **Session:** 2026-06-03

---

## 0. Purpose

The **Project** module lets you and Tobi jointly manage any initiative — software features, research sprints, business campaigns, personal goals — in one place. Tobi is a first-class actor: it can create, update, and complete work autonomously (with autonomy level depending on project type), and all its actions are fully visible and auditable.

---

## 1. Data Model

### 1.1 Project

| Field | Type | Notes |
|---|---|---|
| `id` | UUID | Primary key |
| `name` | string | Required |
| `description` | string | Markdown |
| `status` | enum | `idea \| active \| done \| archived` |
| `size` | enum | `small \| medium \| large \| epic` |
| `category` | string | e.g. `business`, `personal`, `research`, `health` |
| `emoji_icon` | string | Optional emoji for card identity |
| `accent_color` | string | Hex — card accent |
| `deadline` | date | Optional |
| `kpi_link` | object | `{ mode: "linked" \| "custom", kpi_id?: string, metric_name?: string, target_value?: number, current_value?: number }` |
| `progress_pct` | number | 0–100, auto-derived from Goals weighted completion |
| `template_id` | UUID? | If created from a saved template |
| `created_by` | enum | `user \| tobi` |
| `created_at` | datetime | |
| `updated_at` | datetime | |

**P1 — Status lifecycle:** `idea → active → done → archived`. Both user and Tobi can change status (Tobi may auto-transition to `active` on research/business projects without asking).

**P2 — Size indicator:** `small / medium / large / epic` badge displayed on project cards and inside the project header.

**P3 — Progress calculation:** Weighted by Goal completion. `progress_pct = avg(goals[].progress_pct)`. If no goals exist, falls back to `completed_tasks / total_tasks`.

**P4 — KPI link:** On creation, user (or Tobi) can either link to an existing Office KPI by ID or define a custom `metric_name + target_value`. Tobi can update `current_value` via API.

---

### 1.2 Goal

| Field | Type | Notes |
|---|---|---|
| `id` | UUID | |
| `project_id` | UUID | FK → Project |
| `title` | string | e.g. "Reach 1000 users" |
| `metric_name` | string | e.g. "MAU", "MRR", "tasks done" |
| `target_value` | number | |
| `current_value` | number | Tobi or user update this |
| `progress_pct` | number | `(current_value / target_value) * 100` |
| `due_date` | date | |
| `owner` | enum | `user \| tobi` |
| `created_at` | datetime | |

**P5 — Goals drive project progress.** Each goal has equal weight unless manually weighted (v2 scope).

---

### 1.3 Task

Extends the existing Task model with two new fields:

| New Field | Type | Notes |
|---|---|---|
| `project_id` | UUID? | Nullable — tasks can be standalone or project-owned |
| `goal_id` | UUID? | Nullable — optionally linked to a Goal |
| `time_estimate` | string | e.g. "2h", "3d" — free text |
| `sub_tasks` | JSON array | `[{ id, title, completed }]` — one level deep, max 20 per task |
| `sort_order` | number | For drag-and-drop ordering within status group |

**P6 — Task module integration:** The existing Task module page shows ALL tasks (standalone + project-owned). A `Project` column is added with a filter chip. Tasks inside a project also appear in their project's Tasks tab.

**P7 — Task fields:** title, description (markdown), status (`todo \| in_progress \| review \| done \| blocked`), priority (`low \| medium \| high \| urgent`), assignee (`user \| tobi`), due_date, time_estimate, sub_tasks (one level, max 20), sort_order.

**P8 — Sub-tasks:** One level deep. Completing all sub-tasks can optionally auto-complete the parent (user toggle).

---

### 1.4 Mission

| Field | Type | Notes |
|---|---|---|
| `id` | UUID | |
| `project_id` | UUID | FK → Project |
| `prompt` | string | The instruction given to Tobi |
| `status` | enum | `queued \| running \| done \| failed` |
| `output` | text | Tobi's result/log |
| `tasks_created` | int | How many tasks Tobi added |
| `docs_created` | int | |
| `duration_ms` | int | |
| `created_by` | enum | `user \| tobi` |
| `created_at` | datetime | |
| `completed_at` | datetime? | |

**P9 — Missions = Tobi's autonomous jobs** inside a project context. Tobi can self-create missions on research/business projects; personal projects require user initiation.

---

### 1.5 Activity Log Entry

| Field | Type | Notes |
|---|---|---|
| `id` | UUID | |
| `project_id` | UUID | |
| `actor` | enum | `user \| tobi` |
| `action_type` | string | e.g. `task.created`, `goal.updated`, `status.changed`, `mission.completed` |
| `summary` | string | Human-readable short description |
| `diff` | JSON? | Field-level before/after for expandable detail |
| `created_at` | datetime | |

**P10 — Activity log detail:** Shows high-level summary by default. Click to expand and see field-level diffs (e.g. `Goal 1 target: 500 → 1000`).

---

### 1.6 Template

| Field | Type | Notes |
|---|---|---|
| `id` | UUID | |
| `name` | string | |
| `description` | string | |
| `source_project_id` | UUID | The project this was saved from |
| `snapshot` | JSON | Frozen copy of goals, tasks (without dates/assignees) |
| `created_at` | datetime | |

**P11 — Templates:** Users can save any project as a reusable template. On project creation, an optional template picker loads the snapshot's goals and tasks into the new project.

---

## 2. UI / UX

### 2.1 Projects List Page (`/projects`)

**P12 — Dual view, switchable:**
- **Card Grid** (default): 3-column responsive grid of project cards.
- **Table / List**: sortable rows with columns Name, Status, Size, Progress, Deadline, Task count.
- Toggle buttons (grid/list icon) in the top-right. Preference saved in localStorage.
- Global search bar + filter chips (Status, Size, Category, Assignee).

**P13 — Project Card (grid view) fields:**
- Emoji icon + accent color strip at top
- Project name (bold)
- Size badge (Small / Medium / Large / Epic)
- Status badge (colored pill)
- Progress bar + % (driven by Goals)
- Deadline (red if overdue)
- Task count (e.g. "4 / 10 tasks")
- Last activity timestamp

**P14 — Top bar actions:**
- `+ New Project` button → opens creation modal (P19)
- Search input
- Filter chips row

---

### 2.2 Project Detail Page (`/projects/:id`)

**P15 — Tabbed layout:**

```
[Overview]  [Tasks]  [Goals]  [Docs]  [Missions]  [Activity]
```

**Overview tab** (default):
- Project header: emoji icon, name, status badge, size badge, progress bar (%), deadline, edit button
- Two-column section below:
  - Left: Goals summary cards (title, progress bar, current/target, due date)
  - Right: Recent Activity feed (last 10 entries, actor avatar, timestamp)
- KPI widget (if linked): shows metric name, current vs target, trend

**Tasks tab:**
- Inline Notion-style editable table
- Columns: `[ ] Title | Status | Priority | Assignee | Due Date | Est. | Goal`
- Quick-add bar at top: type task name + Enter to create (auto-assigns to project, status=Todo)
- Filter chips: Status, Assignee; Sort: Priority, Due Date, Created
- Drag handles on rows for reordering within the same status group
- Click row to expand inline detail: description (markdown), sub-tasks checklist, comments

**Goals tab:**
- Cards list, each showing: title, metric, progress bar, current/target values, due date, owner badge
- `+ Add Goal` button → inline form
- Tobi can update `current_value` via API; UI shows last-updated timestamp

**Docs tab:**
- File attachment list: filename, size, upload date, uploader (user or Tobi), download/delete actions
- `+ Attach File` button → file picker
- No inline editor in v1 — external files only

**Missions tab:**
- Prompt input textarea + `Run Mission` button
- Mission log below: chronological list of past missions
  - Each entry: timestamp, prompt summary, status badge, duration, "View output" expandable
  - Running missions show a live spinner + elapsed time
  - Completed missions show task/doc counts added

**Activity tab:**
- Full chronological feed of all actions on this project
- Each entry: actor avatar (you or Tobi robot icon), action summary, timestamp
- Click to expand: field-level diff JSON in a collapsible panel
- Filter by actor (All / You / Tobi)

---

### 2.3 Project Creation Modal

**P16 — Modal triggered by `+ New Project`:**

Fields:
1. Name (required)
2. Description (optional, markdown)
3. Status (default: `idea`)
4. Size (default: `medium`)
5. Category (optional text/tag)
6. Emoji icon (picker, optional)
7. Deadline (date picker, optional)
8. KPI: radio `Link existing Office KPI | Define custom | Skip`
   - If linked: dropdown of Office KPIs
   - If custom: metric name + target value inputs
9. Template: optional dropdown of saved templates (pre-fills goals/tasks on create)

Actions: `Cancel` | `Create Project`

---

### 2.4 Task Quick-Add

**P17:** A single input bar fixed at the top of the Tasks tab. Type task name, press Enter → task created with `status=todo`, `assignee=user`, no due date. Escape cancels. The row appears immediately (optimistic UI) at the bottom of the Todo group.

---

### 2.5 Sub-tasks

**P18:** Inside an expanded task row, a sub-task checklist is shown. `+ Add sub-task` appends a new input. Checking all sub-items shows a prompt "Mark parent as done?" (dismiss or confirm). Max 20 sub-tasks per task.

---

## 3. Tobi Integration

### 3.1 Autonomy Rules

**P19:**
| Project category | Tobi autonomy |
|---|---|
| `business`, `research` | Full — Tobi can create projects, add tasks, update goals, run missions without asking |
| `personal`, `health` | Requires explicit user command before any create/update action |
| Any | Tobi can always read and post to activity log |

---

### 3.2 Tobi Notification Channels

**P20 — All four channels active:**
1. **Toast** in Mission Control UI (if tab is open)
2. **Activity feed** — silent log in Activity tab
3. **Badge** on the Projects nav item (unread Tobi-action count, clears on tab visit)
4. **Telegram message** — summary of what Tobi did

---

## 4. API Endpoints

All endpoints live under `/api/projects`. Tobi uses these same endpoints (authenticated via internal token).

**P21 — Projects CRUD:**
```
GET    /api/projects               — list all projects (filter: status, category, size)
POST   /api/projects               — create project
GET    /api/projects/:id           — get project detail
PATCH  /api/projects/:id           — update project fields
DELETE /api/projects/:id           — archive/delete project
```

**P22 — Tasks CRUD within project:**
```
GET    /api/projects/:id/tasks          — list tasks (filter: status, assignee, goal_id)
POST   /api/projects/:id/tasks          — create task
PATCH  /api/projects/:id/tasks/:tid     — update task fields (including sub_tasks, sort_order)
DELETE /api/projects/:id/tasks/:tid     — delete task
```

**P23 — Goals:**
```
GET    /api/projects/:id/goals          — list goals
POST   /api/projects/:id/goals          — create goal
PATCH  /api/projects/:id/goals/:gid     — update goal (Tobi uses this to push current_value)
DELETE /api/projects/:id/goals/:gid     — delete goal
```

**P24 — Missions:**
```
GET    /api/projects/:id/missions        — list missions
POST   /api/projects/:id/missions        — create + queue a mission
GET    /api/projects/:id/missions/:mid   — get mission detail + output
PATCH  /api/projects/:id/missions/:mid   — update status/output (Tobi updates as it runs)
```

**P25 — Activity log:**
```
GET    /api/projects/:id/activity        — list activity entries (filter: actor)
POST   /api/projects/:id/activity        — Tobi posts its own action entries
```

**P26 — Files:**
```
GET    /api/projects/:id/files           — list attached files
POST   /api/projects/:id/files           — upload file (multipart)
DELETE /api/projects/:id/files/:fid      — delete file
```

**P27 — Templates:**
```
GET    /api/projects/templates           — list saved templates
POST   /api/projects/templates           — save project as template
DELETE /api/projects/templates/:tid      — delete template
```

**P28 — Health module registration:**
All `/api/projects/*` endpoints are registered in the Health module's API endpoint list so connectivity can be monitored from the Health page.

---

## 5. Dashboard Integration

**P29 — Projects summary widget on Dashboard:**
- Widget title: "Projects"
- Shows: active project count, tasks due today (across all projects), last Tobi mission summary
- Clicking the widget navigates to `/projects`
- Consistent with the existing widget system (customizable position, dismissible)

---

## 6. Task Module Integration

**P30 — Task module updates:**
- Add `project_id` (nullable) and `goal_id` (nullable) columns to the Task model and DB schema
- Task list page adds a `Project` column (shows project name badge, or "—" for standalone)
- Filter chip `Project` added to the Task page filter bar
- Tasks created inside a project appear in the Task module automatically

---

## 7. Database Schema (SQLite)

```sql
CREATE TABLE projects (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  description TEXT,
  status TEXT NOT NULL DEFAULT 'idea',
  size TEXT NOT NULL DEFAULT 'medium',
  category TEXT,
  emoji_icon TEXT,
  accent_color TEXT,
  deadline TEXT,
  kpi_mode TEXT,
  kpi_id TEXT,
  kpi_metric_name TEXT,
  kpi_target_value REAL,
  kpi_current_value REAL,
  progress_pct REAL DEFAULT 0,
  template_id TEXT,
  created_by TEXT DEFAULT 'user',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE project_goals (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  metric_name TEXT,
  target_value REAL NOT NULL DEFAULT 100,
  current_value REAL NOT NULL DEFAULT 0,
  progress_pct REAL GENERATED ALWAYS AS (CASE WHEN target_value > 0 THEN (current_value / target_value) * 100 ELSE 0 END) STORED,
  due_date TEXT,
  owner TEXT DEFAULT 'user',
  created_at TEXT NOT NULL
);

CREATE TABLE project_missions (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  prompt TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued',
  output TEXT,
  tasks_created INTEGER DEFAULT 0,
  docs_created INTEGER DEFAULT 0,
  duration_ms INTEGER,
  created_by TEXT DEFAULT 'user',
  created_at TEXT NOT NULL,
  completed_at TEXT
);

CREATE TABLE project_activity (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  actor TEXT NOT NULL,
  action_type TEXT NOT NULL,
  summary TEXT NOT NULL,
  diff TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE project_files (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  filename TEXT NOT NULL,
  file_path TEXT NOT NULL,
  file_size INTEGER,
  mime_type TEXT,
  uploaded_by TEXT DEFAULT 'user',
  created_at TEXT NOT NULL
);

CREATE TABLE project_templates (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  description TEXT,
  source_project_id TEXT,
  snapshot TEXT NOT NULL,
  created_at TEXT NOT NULL
);

-- Extend tasks table (migration):
ALTER TABLE tasks ADD COLUMN project_id TEXT REFERENCES projects(id) ON DELETE SET NULL;
ALTER TABLE tasks ADD COLUMN goal_id TEXT REFERENCES project_goals(id) ON DELETE SET NULL;
ALTER TABLE tasks ADD COLUMN time_estimate TEXT;
ALTER TABLE tasks ADD COLUMN sub_tasks TEXT DEFAULT '[]';
ALTER TABLE tasks ADD COLUMN sort_order INTEGER DEFAULT 0;
```

---

## 8. Implementation Phases

| Phase | Scope | Notes |
|---|---|---|
| **P-A Backend** | DB schema migration, all API endpoints (CRUD), activity log auto-posting | No UI yet |
| **P-B Projects list page** | `/projects` page: card grid + list toggle, search, filters, create modal | |
| **P-C Project detail page** | Tabbed layout: Overview + Tasks + Goals tabs | Core loop |
| **P-D Missions + Docs + Activity tabs** | Missions prompt/log, file attachments, full activity feed | |
| **P-E Task module update** | Add Project column + filter to existing Task page | |
| **P-F Dashboard widget** | Projects summary widget on Dashboard | |
| **P-G Templates** | Save-as-template flow + template picker on project creation | |
| **P-H Tobi wiring** | Telegram commands to create/update projects; autonomy rules enforced | |

---

*Total locked decisions: P1–P30 (30 decisions). Spec ready for implementation approval.*

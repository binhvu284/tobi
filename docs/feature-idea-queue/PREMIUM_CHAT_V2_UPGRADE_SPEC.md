# Premium Chat v2 Upgrade — Full Spec

> Built from 30 Q&A decisions. Ship all features in one pass.

## Features

### 1 — Psychology category unlock (display bug fix)
**Decision:** Admin toggle via TOBI command. Override stored in DB (`category_overrides` or similar),
UI reads it to determine lock state. Psychology override was already issued — the DB record must exist
and the frontend must read it correctly.

### 2 — TOBI reads full tier/evolution data
**Decision:** Inject **full tier roadmap** (all tier names, descriptions, XP thresholds, milestones,
unlockable features) into system prompt every session. Granularity = everything on the Evolution page.

### 3 — UI picker for user-detail questions
**Decision:**
- **Trigger:** TOBI detects missing context AND manual command ("ask me for my details")
- **Style:** Multi-step wizard (one question per screen with progress indicator)
- **Categories:** Context-dependent — TOBI generates questions based on what it needs to know
- **Storage:** Backend DB but session-scoped (injected into current session context, not permanent profile)

### 4 — MC Goal CRUD (inside Project panels)
**Decision:**
- **Location:** Inside project detail/panel (not a separate page or route)
- **Fields:** Title + description + due date + priority (low/medium/high)
- **Sub-goals:** One level deep (goal → sub-goals, sub-goals can't have children)
- **Rename project:** Modal with old→new name preview; TOBI can batch-rename multiple projects
- **Goal delete:** Trash icon + "Are you sure?" popover confirm
- **TOBI autonomy:** Fully autonomous during missions (create/edit/delete without asking)

### 5 — Message & Action Timestamps in Chat
**Decision:**
- **Messages:** Always visible, small/muted (not distracting)
- **Format:** Relative by default ("2 min ago"), absolute on hover ("Thu Jul 3, 10:45 AM")
- **Actions/tool steps:** Grouped by minute — one timestamp per group, not per individual step

### 6 — Clock + Calendar in dashboard header
**Decision:**
- **Style:** Icon-only (clock icon + calendar icon in header); hover reveals popover
- **Clock popover:** Live digital time (HH:MM, running)
- **Calendar popover:** Current date + mini month-grid with today highlighted
- **Timezone:** User-configurable in Settings; default = Vietnam (UTC+7)
- **TOBI context injection:** Smart — only when TOBI detects a time-sensitive query
- **TOBI tool:** `get_current_datetime()` tool call available for precise mid-task queries

### 7 — Chat prompt draft persistence
**Decision:**
- **Scope:** Per conversation (each chat has its own draft, keyed by session ID)
- **Storage:** localStorage
- **Clear:** On message send (standard behavior)

### 8 — MC image reading
**Decision:**
- **Input methods:** Drag & drop, paperclip/attach button, Ctrl+V clipboard paste
- **Actions:** Analyze+describe, extract text/OCR from screenshots, use as task reference
- **Display:** Thumbnail preview before sending; image included in mission context

### 9 — Hermes → MC full wiring
**Decision:**
- **Scope:** All Hermes features (web research, file read/write, PC control, everything)
- **Trigger:** Auto-detected by TOBI + user can override with slash command (e.g. `/research`)
- **Results display:** Same as regular TOBI steps in the mission step log (no visual difference)

## Implementation Plan

### Backend changes
- `api/dashboard.py`: Add goal CRUD endpoints under projects; add `get_current_datetime` tool; wire Hermes tools into conductor; add tier data endpoint; add category unlock override read
- `core/conductor.py`: Add goal management tools (create/edit/delete/list goals + sub-goals); add `get_current_datetime`; inject tier data into system prompt; smart datetime injection
- DB: `pm_goals` table (title, description, due_date, priority, project_id, parent_goal_id for sub-goals)

### Frontend changes
- `dashboard/src/pages/Chat.tsx`: Timestamps on messages (always visible, muted), action group timestamps, draft persistence to localStorage per session
- `dashboard/src/components/AppShell.tsx`: Clock icon + Calendar icon in header with hover popovers
- `dashboard/src/pages/MissionControl.tsx` (or project panel): Goal CRUD UI inside project panels, image attach (drag/paperclip/paste), rename project modal
- `dashboard/src/pages/Evolution.tsx` or Psychology: Fix lock state display
- `dashboard/src/pages/Settings.tsx`: Timezone selector
- New: `dashboard/src/components/chat/PickerWizard.tsx` — multi-step wizard for user-detail questions
- New: `dashboard/src/components/ClockCalendar.tsx` — header clock/calendar icons with popovers

## 30 Q&A Decisions Index

| Q | Topic | Answer |
|---|-------|--------|
| 1 | Psychology unlock | Admin toggle (DB override) |
| 2 | Tier data source | Inject full data in system prompt always |
| 3 | Picker trigger | Both auto + manual |
| 4 | Picker style | Multi-step wizard |
| 5 | Picker categories | Context-dependent |
| 6 | Picker storage | Backend DB, session-scoped |
| 7 | Rename project confirm | Modal old→new preview, batch capable |
| 8 | Goal fields | Title + desc + due date + priority |
| 9 | Goal UI location | Inside project panel |
| 10 | Goal delete | Trash + popover confirm |
| 11 | Message timestamps | Always visible, small/muted |
| 12 | Timestamp format | Relative default, absolute on hover |
| 13 | Action timestamps | Group by minute, one stamp per group |
| 14 | Clock style | Icon-only, hover for popover |
| 15 | Calendar popup | Date + mini month grid |
| 16 | Clock → TOBI | Smart inject (time-sensitive queries only) |
| 17 | Clock timezone | User-configurable, default Vietnam |
| 18 | Draft scope | Per conversation |
| 19 | Draft clear | On send |
| 20 | MC image input | Drag+drop + paperclip + Ctrl+V |
| 21 | MC image action | Analyze + OCR + reference |
| 22 | Hermes scope | All features |
| 23 | Hermes display | Same as TOBI steps |
| 24 | Hermes trigger | Auto + slash command |
| 25 | Sub-goals | One level deep |
| 26 | TOBI goal autonomy | Fully autonomous |
| 27 | Tier prompt detail | Full (names, desc, XP, unlocks, milestones) |
| 28 | Clock as tool | Yes — `get_current_datetime()` tool |
| 29 | Draft storage | localStorage |
| 30 | Delivery | All in one pass |

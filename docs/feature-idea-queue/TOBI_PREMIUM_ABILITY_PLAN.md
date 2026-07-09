# TOBI Premium Ability Plan

## Status

- Queue status: Queued
- Queue item: #14
- Planned after: Theme v2 System Upgrade
- Implementation owner: worker agent
- Planning owner: Codex planner
- Scope: planning and future implementation only; do not implement from this file until the queue item is selected.

## Executive Summary

Upgrade TOBI Chat into a more capable power-user workspace by adding reliable YouTube reading, clearer image reading behavior, and a read-only Hermes skill registry surface. Upgrade the Ability page from a mostly static showcase into a live skill dashboard that shows TOBI abilities and Hermes skill files with status, source, risk, and version metadata.

The first visible win is the YouTube reader: when the owner pastes a supported YouTube link into any chat mode, TOBI should fetch the transcript after Send, chunk and summarize long transcripts, and use the result as chat context. If no transcript is available, TOBI must say so honestly.

This is not a paid-tier gating feature. "Premium" means stronger practical capability for the owner's local TOBI app.

## Current System Analysis

Important current surfaces:

- `dashboard/src/pages/Chat.tsx`
  - Already supports chat sessions, model selection, modes, file upload, image paste, attachments, web research toggle, connector toggles, human review, queued turns, and typed stream handling.
- `dashboard/src/api.ts`
  - Already defines `ChatAttachment`, `ChatTurnOptions`, `streamChatSession`, Ability API types, LLM config types, and Hermes push types.
- `api/dashboard.py`
  - Already has chat session routes, chat stream route, Ability routes, and LLM Hermes push routes.
- `core/attachments.py`
  - Already splits attachments into text-like content and images.
  - Images are kept as data URLs for native vision calls.
- `core/model_router.py`
  - Already has `supports_vision()` and `vision_complete()`.
  - Existing capability detection is regex-like and should be upgraded into a local registry.
- `core/conductor.py`
  - Already accepts `attachments_text`, `directives`, and optional tools.
- `core/pm_resources.py`
  - Already detects common YouTube URLs and has optional transcript fetch logic.
- `dashboard/src/pages/Ability.tsx`
  - Uses a large static `ABILITIES` list mixed with some live ability detail/usage APIs.
  - Needs a cleaner live dashboard model.
- `tobi/hermes_skills/`
  - Existing repo skill files:
    - `skill_ceo_agent.md`
    - `skill_research_pm_learning.md`
    - `skill_self_improve.md`

## Product Decisions

Locked decisions from owner answers:

- Primary goal: upgrade Chat first.
- Premium meaning: power-user reading/reasoning capability, not subscription gating.
- First visible win: YouTube reader.
- YouTube detection: auto-detect links in user messages.
- Processing timing: process after Send.
- Chat modes: support all modes first - Chat, Agent, Terminal, Research, Project.
- Vision model fallback: explain limitation and continue.
- Image strategy: keep current native vision path.
- Model capability source: local registry.
- Image use case priority: screenshots, UI, dashboards, errors, visual debugging.
- Image limits: conservative.
- Image storage: answer-only; do not save extracted image descriptions by default.
- YouTube supported URLs: `youtube.com/watch`, `youtu.be`, `youtube.com/shorts`.
- Transcript unavailable: explain limitation honestly.
- Long video handling: chunk and summarize.
- Hermes role: both staged discovery and future execution design.
- Hermes v1 source: repo skill files.
- Hermes execution: approval-gated if included later.
- Ability page goal: live skill dashboard.
- Skill card priority: status, source, risk, version, last activity.
- Hermes tracking: read-only derived in v1.
- YouTube UI: subtle chip.
- Icon policy: lucide for generic actions, brand icons where current style supports them.
- Processing feedback: reuse existing thinking/tool status.
- Content storage: do not store raw transcript/media by default.
- Network permission: pasted link implies consent to fetch transcript.
- Hermes permission: Conductor human review required for execution.
- Dependency policy: use existing/optional dependency; fail gracefully.
- Testing depth: focused tests plus manual acceptance checks.
- Queue priority: queued after Theme v2, likely #14.

## Architecture Plan

Add a small reader layer between the chat stream request and Conductor/model execution.

Target flow:

1. Frontend sends the chat turn with message text, mode, selected model, attachments, web research flag, connector flags, and current session id.
2. Backend detects media/readable inputs:
   - image attachments from existing attachment flow
   - YouTube URLs in message text
   - existing text/PDF attachments
3. Backend builds a `reader_context` object:
   - `attachments_text`
   - `image_data_urls`
   - `youtube_context`
   - `reader_notices`
4. Backend emits status events through existing chat stream mechanics:
   - reading YouTube transcript
   - using image-capable model
   - transcript unavailable
   - selected model cannot read images
5. Backend routes:
   - image turns with vision-capable model to native `vision_complete()`
   - YouTube transcript context into the normal Conductor/model answer path
   - text/PDF attachments into existing `attachments_text`
6. Frontend shows compact chips/status only; no heavy preview panel in v1.

Recommended new modules:

- `core/model_capabilities.py`
  - Local provider/model capability registry.
  - Exposes `capabilities_for(model_id)`, `supports_vision(model_id)`, and maybe `supports_reasoning(model_id)`.
  - `model_router.supports_vision()` should delegate here for backward compatibility.
- `core/youtube_reader.py`
  - URL detection.
  - Transcript fetch wrapper around existing optional transcript logic.
  - Transcript chunking/summarization preparation.
  - Honest fallback results.
- `core/premium_readers.py`
  - Orchestrates attachments plus YouTube context for chat stream.
  - Keeps policy centralized so chat route does not become more tangled.
- `core/hermes_skills.py`
  - Read-only parser for repo Hermes markdown skill files.
  - Does not execute or write skills.

## Theme And UX Fit

This feature must preserve the existing Premium Chat style and should not perform a broad visual redesign.

Required UI rules:

- Keep Chat's first screen as the usable chat workspace.
- Do not add a landing page or explainer.
- Do not create nested cards inside cards.
- Use icon buttons where the meaning is standard.
- Use lucide icons for generic actions.
- Use the existing brand-icon approach only if the project already has an equivalent YouTube icon source.
- Keep YouTube reader UI compact:
  - a small chip when a YouTube URL is detected or processed
  - status in existing thinking/tool area while reading
  - clear assistant message if unavailable
- Do not add a large transcript preview panel in v1.

## Image Reader Implementation Plan

Keep the existing native vision strategy:

- Continue accepting uploaded and pasted images through `Chat.tsx`.
- Continue sending images as data URLs.
- Keep `core/attachments.py` as the splitter for attachments.
- Move model capability checks to `core/model_capabilities.py`.
- Keep `model_router.vision_complete()` as the provider-specific multimodal call.
- Improve fallback copy:
  - If a selected model cannot see images, TOBI should say it cannot inspect the attached image with that model.
  - TOBI should continue answering from any text, PDF, or YouTube context available.
- Keep conservative image limits:
  - Do not increase image count in this feature unless current implementation is broken.
  - Keep caps documented in code or comments.
- Do not store generated image descriptions by default.

Acceptance examples:

- Owner pastes an app screenshot and asks "what is wrong here?"
  - If model supports vision, TOBI inspects it.
  - If model does not support vision, TOBI says the model cannot see images and suggests selecting a vision-capable model.
- Owner sends image plus text/PDF.
  - If vision fails, TOBI can still use text/PDF context.

## Model Capability And Vision Adapter Strategy

Create a local registry so worker agents do not rely on fragile regex checks.

Suggested schema:

```python
MODEL_CAPABILITIES = {
    "openai:gpt-4o": {"vision": True, "reasoning": False, "context": 128000},
    "openai:gpt-4.1": {"vision": True, "reasoning": False, "context": 1000000},
    "anthropic:claude-3-5-sonnet": {"vision": True, "reasoning": False, "context": 200000},
    "anthropic:claude-3-7-sonnet": {"vision": True, "reasoning": True, "context": 200000},
}
```

Implementation notes:

- Keep registry permissive but explicit.
- Include fallback pattern matching only as a backup.
- Preserve existing public function names where possible:
  - `model_router.supports_vision(model_id)`
  - `model_router.vision_complete(...)`
- Frontend `ModelMenu` can keep its current quick badges, but should preferably consume capability metadata later if API already exposes it.
- Do not block Send if the model cannot read images. Explain and continue.

## YouTube Reader Implementation Plan

Add YouTube reading to normal chat turns.

Supported URLs in v1:

- `https://www.youtube.com/watch?v=...`
- `https://youtu.be/...`
- `https://www.youtube.com/shorts/...`

Out of scope for v1:

- playlists
- channel pages
- live stream pages
- embedded URL variants
- video frame analysis
- audio transcription

Backend behavior:

1. Detect supported YouTube URLs in the user message.
2. For each detected URL, fetch transcript using existing optional transcript approach from `pm_resources.py` or a wrapper around it.
3. If transcript is found:
   - normalize transcript text
   - include video id and source URL
   - chunk if long
   - summarize or compact before passing to Conductor if needed
4. If transcript is unavailable:
   - add a clear notice
   - do not pretend TOBI watched the video
5. Add context to the chat prompt:
   - label it as YouTube transcript content
   - include URL/video id
   - preserve enough timestamp information only if already available and cheap

Context format example:

```text
[YouTube transcript context]
Source: https://youtu.be/VIDEO_ID
Video id: VIDEO_ID
Transcript summary:
...
Relevant transcript excerpts:
...
```

Long transcript strategy:

- Use simple chunking by character count or transcript segment boundaries.
- Keep the prompt safe by limiting total transcript context.
- If summarization uses an LLM, use the configured model router and log usage normally.
- If summarization fails, fall back to capped transcript excerpt and say it is partial.

Dependency policy:

- Reuse existing optional `youtube_transcript_api` logic if present.
- Do not make app startup fail when the dependency is missing.
- If dependency is missing, return a graceful unavailable result.

## YouTube UI/UX Plan

Frontend changes in `Chat.tsx`:

- Detect YouTube URLs locally only for UI chip display.
- Show a subtle chip near attachment/tool chips:
  - label: `YouTube`
  - state examples: `detected`, `reading`, `transcript ready`, `unavailable`
- Do not fetch from frontend.
- Do not preview transcript in composer.
- Use existing stream events/status to update chip if practical.
- If status plumbing is expensive, v1 can show only `YouTube link` before Send and rely on assistant/status messages after Send.

Recommended icons:

- Generic link/video: lucide `Youtube` if available; otherwise `Video`, `Link`, or `Globe`.
- Keep styling consistent with existing compact chips.

Assistant behavior:

- If transcript is read successfully, answer normally.
- If transcript unavailable, say:
  - "I could not read the transcript for that YouTube link."
  - Then explain the likely reason only if known.
- Do not say "I watched the video."

## Hermes Integration Plan

V1 is read-only discovery plus a future execution placeholder.

Do:

- Parse `tobi/hermes_skills/*.md`.
- Return skill metadata through an API.
- Display Hermes skills in Ability page.
- Mark Hermes execution as `approval_required` or `not_enabled`.
- Preserve current Hermes config push behavior on Models page.

Do not:

- Modify Hermes markdown files.
- Execute Hermes skills automatically.
- Read machine-level `~/.hermes` folders.
- Create DB migrations solely for Hermes tracking in v1.

API suggestion:

```http
GET /api/hermes/skills
```

Response suggestion:

```json
{
  "items": [
    {
      "id": "skill_ceo_agent",
      "name": "CEO Agent Skill",
      "source": "hermes_repo_file",
      "file_path": "tobi/hermes_skills/skill_ceo_agent.md",
      "status": "available",
      "risk_tier": "approval_required",
      "version": 1,
      "description": "Parsed summary from first heading or intro text",
      "last_modified": "..."
    }
  ],
  "count": 3
}
```

Parser rules:

- id = file stem without `.md`
- name = first markdown heading, cleaned
- description = first useful paragraph after headings, capped
- status = `available`
- source = `hermes_repo_file`
- risk_tier = `approval_required`
- version = `1` unless a better version marker is found
- last_modified = file modified time

## Hermes Skill Registry Tracking Plan

Tracking is read-only derived in v1:

- No DB mirror.
- No skill execution metrics for Hermes skills unless execution already exists.
- Ability page can show "No runs yet" or "Read-only source" for Hermes skills.
- If worker chooses to cache results in memory for performance, cache only during request lifecycle.

Future v2/v3 placeholder:

- DB mirror for skill metadata.
- Execution history.
- Version history.
- Promotion workflow from repo skill to TOBI managed skill.
- Import from machine Hermes home folder after explicit owner approval.

## Ability Page Upgrade Plan

Goal: live skill dashboard.

Required behavior:

- Keep existing Ability route `/ability`.
- Preserve current live usage loading from `getAbilities()`.
- Preserve detail/coaching/proposal/rollback flows for DB-backed skills.
- Add Hermes skills as a separate source group or filter.
- Avoid breaking existing static ability cards during migration.

Suggested page model:

```ts
type AbilitySource = 'core_static' | 'tobi_db' | 'hermes_repo_file'

type UnifiedAbility = {
  id: string
  name: string
  source: AbilitySource
  status: 'active' | 'available' | 'config' | 'inactive' | 'not_enabled'
  risk_tier: 'low' | 'medium' | 'high' | 'approval_required' | 'unknown'
  version?: number
  category?: string
  description?: string
  last_active?: string | null
  can_coach: boolean
  can_rollback: boolean
  can_execute: boolean
}
```

Dashboard sections:

- Summary header:
  - total abilities
  - active abilities
  - Hermes skills discovered
  - approval-required abilities
- Filters:
  - source
  - status
  - risk
- Cards or rows:
  - name
  - source badge
  - status badge
  - risk badge
  - version
  - last active
- Detail drawer:
  - DB-backed skill: current detail/coaching/version tools.
  - Hermes skill: file source, description, status, execution disabled/approval-required note.

UI caution:

- Current `Ability.tsx` is large. Worker should avoid a full rewrite unless necessary.
- Prefer adding a small API fetch for Hermes skills and a unified display layer.
- If refactor is needed, split components carefully but keep behavior intact.

## Ability Execution Pipeline Proposal

Do not enable automatic Hermes execution in v1.

Future execution pipeline should be documented in code comments or plan notes:

1. Chat/Conductor identifies a Hermes skill candidate.
2. Conductor creates a pending action with:
   - skill id
   - source file
   - intended input
   - risk
   - summary
3. Owner approves or rejects through existing human review flow.
4. Execution runs only after approval.
5. Result is logged in `tobi_actions`.
6. Any learned improvement becomes a proposal, not an automatic skill edit.

This keeps Hermes aligned with existing Conductor safety.

## Data Model And API Changes

Prefer no migrations in v1 unless worker discovers they are required.

Likely additions:

- `GET /api/hermes/skills`
- Maybe extend chat stream events with reader status:
  - `event: thinking`
  - or existing `notice` event with `kind: "reader_status"`

Avoid:

- new persistent transcript table
- new image summary table
- Hermes DB mirror table
- skill execution tables

If a worker decides a migration is unavoidable, it must be documented and kept idempotent.

## Frontend State Management Plan

Chat:

- Add local derived YouTube URL detection from the input.
- Add compact chip state:
  - detected before send
  - optional stream-updated status after send
- Keep attachments state unchanged.
- Keep queued turns behavior unchanged.
- Do not add global state.

Ability:

- Add local state for Hermes skills:
  - loading
  - items
  - error ignored or shown quietly
- Combine existing static/live ability data with Hermes API results through `useMemo`.
- Keep polling conservative; Hermes files do not need a frequent poll.

## Backend And Service Changes

Chat stream route:

- Keep existing route path.
- Before answering, call the reader layer to prepare context.
- Append YouTube context to `attachments_text` or a separate context block.
- Emit notices/status when a reader fails or succeeds.

Model router:

- Add capability registry.
- Preserve existing function names.

PM resources:

- Reuse URL parsing/transcript helpers where possible.
- If logic is moved, keep old PM Resources behavior intact.

Hermes skills:

- Implement read-only parser.
- Add API endpoint.
- Handle missing folder gracefully with empty list.

## Security, Privacy, Permissions, And Rate Limits

Required:

- No Supabase or Vercel interaction.
- Do not store raw transcripts by default.
- Do not store image data beyond normal chat request/session behavior.
- Do not read secrets.
- Do not read machine-level Hermes home folders.
- Pasted YouTube link is treated as permission to fetch transcript.
- Hermes execution must use Conductor approval.
- Any future Hermes write/edit must be a separate queue item or explicit owner approval.

Rate/size safety:

- Limit number of YouTube links processed per turn. Suggested v1 max: 2.
- Limit transcript context passed to model.
- Limit transcript summarization chunks.
- Keep image count cap conservative.
- Fail closed with clear explanation.

## Error Handling And Fallback Behavior

YouTube:

- No supported URL: no reader behavior.
- Unsupported URL variant: ignore or explain only if it looks like YouTube.
- Dependency missing: "YouTube transcript reading is unavailable in this install."
- Transcript unavailable: "I could not read the transcript for that YouTube link."
- Transcript too long: chunk and summarize; if summarization fails, use capped excerpt and state partial context.

Images:

- Selected model supports vision: use native vision.
- Selected model does not support vision: explain and continue with text context.
- Provider vision call fails: explain failure and continue if possible.

Hermes:

- Folder missing: show zero Hermes skills, no crash.
- Bad markdown file: skip file or include minimal metadata with parse warning.
- API error: Ability page still renders current abilities.

## Migration And Backward Compatibility

- Existing chat sessions must still load.
- Existing attachments must still work.
- Existing image vision path must still work.
- Existing PM Resources YouTube import must still work.
- Existing Ability coaching/proposal/rollback must still work.
- Existing Models Hermes push must still work.
- No required data migration for v1.

## Testing Plan

Focused backend tests:

- YouTube URL detection:
  - watch URL
  - youtu.be URL
  - shorts URL
  - non-YouTube URL
  - multiple links with cap
- Transcript fallback:
  - transcript available
  - transcript unavailable
  - dependency unavailable
- Capability registry:
  - known vision model returns true
  - known non-vision model returns false
  - unknown model uses safe fallback
- Hermes parser:
  - parses existing three files
  - handles missing folder
  - handles malformed markdown
- Chat context:
  - YouTube transcript context is included in answer path
  - unavailable transcript produces honest notice

Frontend/manual tests:

- Paste YouTube link in Chat mode.
- Paste YouTube link in Research mode.
- Paste YouTube link while another turn is queued.
- Upload/paste image with a vision model.
- Upload/paste image with a non-vision model.
- Ability page shows Hermes skill count and cards.
- Ability page DB-backed skill detail still opens.
- Existing build passes.

Suggested commands for worker:

```powershell
cd "D:\[PERSONAL PROJECT FILES]\TOBI\tobi"
python -m pytest tests -q
cd dashboard
npm run build
```

Worker may narrow test commands if the full suite is too slow, but must document what was and was not run.

## Rollback Plan

Rollback should be simple:

- Disable YouTube reader call in chat stream route.
- Keep existing attachment handling untouched.
- Keep `model_router.supports_vision()` backward-compatible.
- If Hermes parser fails, Ability page should omit Hermes section and continue.
- No migrations means no DB rollback should be needed.

Optional config flag:

```python
ENABLE_PREMIUM_READERS = True
```

If added, default should be true for local development but easy to turn off.

## Files Likely To Change

Likely backend files:

- `tobi/api/dashboard.py`
- `tobi/core/attachments.py`
- `tobi/core/model_router.py`
- `tobi/core/pm_resources.py`
- `tobi/core/premium_readers.py` (new)
- `tobi/core/youtube_reader.py` (new)
- `tobi/core/model_capabilities.py` (new)
- `tobi/core/hermes_skills.py` (new)

Likely frontend files:

- `tobi/dashboard/src/pages/Chat.tsx`
- `tobi/dashboard/src/pages/Ability.tsx`
- `tobi/dashboard/src/api.ts`
- `tobi/dashboard/src/components/chat/ModelMenu.tsx` (optional)

Likely tests:

- `tobi/tests/test_premium_readers.py` (new)
- `tobi/tests/test_youtube_reader.py` (new or combined)
- `tobi/tests/test_hermes_skills.py` (new)
- Existing chat/attachment/model tests if present

Docs:

- `tobi/docs/feature-idea-queue/QUEUE.md`
- `tobi/docs/feature-idea-queue/TOBI_PREMIUM_ABILITY_PLAN.md`

## Risks

- YouTube transcripts may often be unavailable.
- Optional transcript dependency may not be installed.
- Long transcript summarization can add latency and LLM cost.
- Current image vision route bypasses the Conductor tool loop.
- Ability page is large and static-heavy, so refactor risk is moderate.
- Hermes execution can become unsafe if not approval-gated.
- Theme v2 and header/chat UI work may conflict with Chat/Ability UI edits.

## Assumptions

- This is queued after Theme v2.
- The worker will not implement paid gating.
- The worker will not store raw transcripts or image descriptions by default.
- The worker will not touch Supabase or Vercel.
- The worker will treat repo Hermes skill files as canonical for v1.
- The worker will preserve current chat/session/attachment behavior.

## Parallel Work Conflict Warning

High conflict risk if implemented at the same time as:

- Theme v2 System Upgrade
- Header tab system
- Chat UI layout/menu cleanup
- Any major Ability page redesign
- Any broad model router rewrite

Safer parallel items:

- Backend-only storage/reporting work
- Documentation-only queue planning
- Non-chat, non-Ability pages

## Final Queued Task Plan

Worker should implement in this order:

1. Add `core/model_capabilities.py` and route `model_router.supports_vision()` through it.
2. Add `core/youtube_reader.py` with URL detection, transcript fetch wrapper, chunking, and fallback result types.
3. Add `core/premium_readers.py` to assemble chat reader context.
4. Wire YouTube context and reader notices into `api/dashboard.py` chat stream route.
5. Preserve and lightly improve current image-reader fallback behavior.
6. Add compact YouTube chip/status behavior in `Chat.tsx`.
7. Add `core/hermes_skills.py` read-only parser.
8. Add `GET /api/hermes/skills`.
9. Extend `api.ts` with Hermes skill types and API function.
10. Upgrade `Ability.tsx` to show Hermes skills in a live dashboard model without breaking existing DB-backed skill actions.
11. Add focused backend tests for capabilities, YouTube reader, and Hermes parser.
12. Run frontend build and selected tests.
13. Update the queue item status/notes only after implementation is complete.

Completion definition:

- YouTube links in chat are detected and read when transcripts are available.
- Long transcripts are safely compacted.
- Unavailable transcripts are reported honestly.
- Images still work through native vision.
- Non-vision models fail gracefully.
- Ability page shows repo Hermes skills read-only.
- Existing chat and Ability behavior is not broken.
- Tests/build are run or skipped with clear reason.

// Office V3 command center — split out of api.office.ts (pre-#21 refactor) so the
// Office API stops being an import hub; re-exported from './api' as before.
import { get, request } from './apiCore'
import type { Agent, Mission, OfficeStats } from './api.office'
import type { PendingAction } from './api.brain'

// ── Office V3 command center ───────────────────────────────────────────────────
export type OfficeArtifactKind = 'report' | 'plan' | 'summary' | 'next_actions' | 'mission_note'
export type OfficeArtifact = {
  id: number; title: string; kind: OfficeArtifactKind; preview: string; content?: string
  source_type?: string | null; source_id?: string | null; sensitivity: 'sensitive'
  created_by: string; created_at: string; updated_at: string
}
export type OfficeActivity = {
  id: number; event_type: string; actor: string; summary: string; payload_json?: string | null
  source_type?: string | null; source_id?: string | null; created_at: string
}
export type OfficeV3Snapshot = {
  enabled: boolean; agents: Agent[]; missions: Mission[]; stats: OfficeStats['stats']
  integrations: Record<string, boolean>; artifacts: OfficeArtifact[]; activity: OfficeActivity[]
  timestamp: string
}
export type OfficeContextRef = { type: 'agent' | 'mission' | 'artifact'; id: string | number; label: string }
export type OfficeAskResult = {
  reply: string; tools_used: string[]; pending_action?: PendingAction | null; context: OfficeContextRef[]
}
export type OfficeActionName =
  | 'office_create_artifact' | 'office_update_artifact' | 'office_delete_artifact'
  | 'office_create_mission' | 'office_run_mission' | 'office_control_mission'
  | 'office_convert_to_tasks'

export async function getOfficeV3Config(): Promise<{ enabled: boolean; fallback: string }> {
  return get('/api/office/v3/config')
}
export async function setOfficeV3Config(enabled: boolean): Promise<{ enabled: boolean }> {
  return request('/api/office/v3/config', { method: 'POST', body: JSON.stringify({ enabled }) })
}
export async function getOfficeV3Snapshot(): Promise<OfficeV3Snapshot> { return get('/api/office/v3/snapshot') }
export async function getOfficeArtifacts(limit = 60): Promise<{ items: OfficeArtifact[]; count: number }> {
  return get(`/api/office/artifacts?limit=${limit}`)
}
export async function getOfficeArtifact(id: number): Promise<OfficeArtifact> { return get(`/api/office/artifacts/${id}`) }
export async function getOfficeActivity(limit = 60): Promise<{ items: OfficeActivity[]; count: number }> {
  return get(`/api/office/activity?limit=${limit}`)
}
export async function proposeOfficeAction(action: OfficeActionName, args: Record<string, unknown>): Promise<{ pending_action: PendingAction }> {
  return request('/api/office/v3/actions/propose', { method: 'POST', body: JSON.stringify({ action, args }) })
}
export async function askOfficeTobi(message: string, context: { agent_id?: string; mission_id?: number; artifact_id?: number }): Promise<OfficeAskResult> {
  return request('/api/office/v3/ask', { method: 'POST', body: JSON.stringify({ message, ...context }) })
}

// ── Feature triggers (Control Room / ⌘K) ───────────────────────────
export type EngineName = 'research' | 'report' | 'ceo' | 'execute'
export type RunResult = { ok: boolean; engine?: string; message?: string; detail?: string; needs?: string }
export type Readiness = { engine: string; label: string; ready: boolean; needs?: string; note?: string }
export async function runEngine(name: EngineName): Promise<RunResult> {
  return request(`/api/run/${name}`, { method: 'POST' })
}
export async function getRunReadiness(): Promise<{ engines: Readiness[]; timestamp: string }> {
  return get('/api/run/readiness')
}

import { get, request } from './apiCore'
import type { PendingAction } from './api.brain'

export async function getAgents(): Promise<AgentsReport> {
  return get('/api/agents')
}

export type Project = {
  id: number
  name: string
  type: string
  niche: string
  status: string
  revenue_total: number
  progress_pct: number
  created_at: string
}

export type Lesson = {
  id: number
  lesson_type: 'success' | 'failure' | 'insight' | 'warning'
  title: string
  content: string
  impact_score: number
  created_at: string
}

export type Todo = {
  id: number
  title: string
  project_name: string
  priority: number
}

// ── The Office (Mission Control §4) ─────────────────────────────────
export type AgentLive = {
  status: 'online' | 'working' | 'idle' | 'offline'
  detail: string
  last_active: string | null
  current_mission_id: number | null
}

export type Agent = {
  id: string
  name: string
  role: string | null
  persona: string | null
  provider: string
  model: string | null
  key_ref: string | null
  temperature: number
  max_tokens: number
  autonomy: string
  can_spawn: boolean
  daily_budget_tokens: number
  skills: string[]
  color: string | null
  sprite: string | null
  is_head: boolean
  status: string
  live: AgentLive
  scorecard?: Record<string, number>
}

export type AgentsReport = { agents: Agent[]; timestamp: string }

export type AgentUpsert = {
  id?: string
  name: string
  role?: string
  persona?: string
  provider: string
  model?: string
  key_ref?: string
  temperature?: number
  max_tokens?: number
  autonomy?: string
  can_spawn?: boolean
  daily_budget_tokens?: number
  skills?: string[]
  color?: string
  sprite?: string
}

export type MissionStep = {
  id: number; seq: number; agent_id: string; action: string
  status: 'pending' | 'running' | 'done' | 'failed'
  input: string | null; output: string | null; tokens: number
  started_at: string | null; completed_at: string | null
}

export type MissionUsage = { agent_id: string; provider: string; model: string; total_tokens: number; calls: number }

export type Mission = {
  id: number; title: string; goal: string | null
  status: 'planned' | 'running' | 'blocked' | 'done' | 'cancelled'
  priority: 'Low' | 'Normal' | 'High' | 'Urgent'
  workflow_id: number | null; workflow_version: number | null
  summary: string | null; cost_tokens: number
  created_at: string; started_at: string | null; completed_at: string | null
  steps?: MissionStep[]; usage?: MissionUsage[]
}

export type Workflow = { id: number; name: string; version: number; is_active: number; steps: { agent_id: string; action: string }[] }

export type OfficeStats = {
  stats: {
    agents_active: number; agents_working: number
    missions_total: number; missions_running: number; missions_done: number
    missions_by_status: Record<string, number>
    tokens_total: number; steps_total: number
  }
  integrations: Record<string, boolean>
  timestamp: string
}

export async function getAgent(id: string): Promise<Agent> { return get(`/api/agents/${id}`) }
export async function createAgent(payload: AgentUpsert): Promise<Agent> {
  return request('/api/agents', { method: 'POST', body: JSON.stringify(payload) })
}
export async function updateAgent(id: string, payload: AgentUpsert): Promise<Agent> {
  return request(`/api/agents/${id}`, { method: 'PATCH', body: JSON.stringify(payload) })
}
export async function deleteAgent(id: string): Promise<{ ok: boolean }> {
  return request(`/api/agents/${id}`, { method: 'DELETE' })
}
export async function getMissions(status = 'all'): Promise<{ items: Mission[]; count: number; timestamp: string }> {
  return get(`/api/missions?status=${status}`)
}
export async function getMission(id: number): Promise<Mission> { return get(`/api/missions/${id}`) }
export async function createMission(payload: { title: string; goal?: string; priority?: string; workflow_id?: number }): Promise<Mission> {
  return request('/api/missions', { method: 'POST', body: JSON.stringify(payload) })
}
export async function patchMission(id: number, payload: { status?: string; priority?: string; title?: string; goal?: string }): Promise<Mission> {
  return request(`/api/missions/${id}`, { method: 'PATCH', body: JSON.stringify(payload) })
}
export async function runMission(id: number, mock = false): Promise<{ ok: boolean; streaming?: boolean; mission_id?: number; error?: string }> {
  return request(`/api/missions/${id}/run?mock=${mock}`, { method: 'POST' })
}
export async function pauseMission(id: number) { return request(`/api/missions/${id}/pause`, { method: 'POST' }) }
export async function resumeMission(id: number) { return request(`/api/missions/${id}/resume`, { method: 'POST' }) }
export async function cancelMission(id: number) { return request(`/api/missions/${id}/cancel`, { method: 'POST' }) }
export async function injectMission(id: number, text: string) { return request(`/api/missions/${id}/inject`, { method: 'POST', body: JSON.stringify({ text }) }) }
export async function getWorkflows(): Promise<{ items: Workflow[]; count: number }> { return get('/api/workflows') }
export async function getOfficeStats(): Promise<OfficeStats> { return get('/api/office/stats') }

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

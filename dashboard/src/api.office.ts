import { get, request } from './apiCore'

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

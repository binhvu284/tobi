async function get(path: string) {
  const res = await fetch(path, { cache: 'no-cache' })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

async function request(path: string, init: RequestInit) {
  const res = await fetch(path, {
    cache: 'no-cache',
    headers: { 'Content-Type': 'application/json', ...(init.headers || {}) },
    ...init,
  })
  if (!res.ok) {
    const maybeJson = await res.json().catch(() => null)
    const detail = maybeJson?.detail
    const err: any = new Error(typeof detail === 'string' ? detail : `HTTP ${res.status}`)
    err.status = res.status
    err.detail = detail
    throw err
  }
  if (res.status === 204) return null
  return res.json()
}

export async function getStatus() {
  return get('/api/status')
}

export async function getProjects() {
  return get('/api/projects')
}

export async function getAgents(): Promise<AgentsReport> {
  return get('/api/agents')
}

export async function getLessons() {
  return get('/api/lessons')
}

export async function getHealth(): Promise<HealthReport> {
  return get('/api/health')
}

export async function runDeepTest(): Promise<DeepTestReport> {
  return get('/api/health/deep')
}

export async function markDone(taskId: number): Promise<boolean> {
  const res = await request(`/done/${taskId}`, { method: 'POST' })
  return Boolean(res)
}

export type TaskStatus =
  | 'planned'
  | 'in_progress'
  | 'paused'
  | 'blocked'
  | 'needs_owner_input'
  | 'done'
  | 'cancelled'

export type TaskPriority = 'P0' | 'P1' | 'P2' | 'P3'
export type TaskAgent = 'tobi' | 'research' | 'coder' | 'ceo'

export type TaskActivity = {
  id: number
  type: string
  author: string
  message: string
  payload: Record<string, any>
  created_at: string
}

export type OwnerInputChecklistItem = {
  item_key: string
  label: string
  input_type: string
  required: boolean
  placeholder?: string | null
  value_text?: string | null
  file_path?: string | null
  status?: string | null
  updated_at?: string
}

export type TaskItem = {
  id: number
  title: string
  objective: string
  success_criteria?: string | null
  description?: string | null
  status: TaskStatus
  priority: TaskPriority
  owner: string
  agent: TaskAgent
  project_id?: number | null
  project_name?: string | null
  task_type?: string
  due_at?: string | null
  is_overdue: boolean
  created_at: string
  updated_at: string
  started_at?: string | null
  completed_at?: string | null
  artifacts: Array<Record<string, any>>
  risk_flags: string[]
  checklist: OwnerInputChecklistItem[]
  activity?: TaskActivity[]
}

export type TaskMetrics = {
  open_tasks: number
  overdue: number
  needs_owner_input: number
  blocked: number
  p0_p1: number
  cycle_time_hours?: number | null
  timestamp: string
}

export type HighRiskAuditItem = {
  id: number
  task_id: number
  task_title: string
  activity_type: string
  author: string
  message: string
  payload: Record<string, any>
  created_at: string
}

export type TaskListFilters = {
  status?: TaskStatus[]
  priority?: TaskPriority[]
  owner?: string[]
  agent?: TaskAgent[]
  project_id?: number
  overdue?: boolean
  q?: string
}

export type TaskCreatePayload = {
  title: string
  objective?: string
  success_criteria?: string
  description?: string
  status?: TaskStatus
  priority?: TaskPriority
  owner?: string
  agent?: TaskAgent
  project_id?: number
  due_at?: string
  checklist?: OwnerInputChecklistItem[]
  risk_flags?: string[]
}

export type TaskPatchPayload = {
  status?: TaskStatus
  priority?: TaskPriority
  agent?: TaskAgent
  due_at?: string | null
  owner?: string
  title?: string
  objective?: string
  success_criteria?: string
  require_confirmation?: boolean
  confirmed?: boolean
}

function toQuery(filters: TaskListFilters): string {
  const params = new URLSearchParams()
  filters.status?.forEach((s) => params.append('status', s))
  filters.priority?.forEach((p) => params.append('priority', p))
  filters.owner?.forEach((o) => params.append('owner', o))
  filters.agent?.forEach((a) => params.append('agent', a))
  if (typeof filters.project_id === 'number') params.set('project_id', String(filters.project_id))
  if (typeof filters.overdue === 'boolean') params.set('overdue', String(filters.overdue))
  if (filters.q?.trim()) params.set('q', filters.q.trim())
  const q = params.toString()
  return q ? `?${q}` : ''
}

export async function getTaskMetrics(): Promise<TaskMetrics> {
  return get('/api/tasks/metrics')
}

export async function getTasks(filters: TaskListFilters = {}): Promise<{ items: TaskItem[]; total: number; timestamp: string }> {
  return get(`/api/tasks${toQuery(filters)}`)
}

export async function getTask(taskId: number): Promise<TaskItem> {
  return get(`/api/tasks/${taskId}`)
}

export async function createTask(payload: TaskCreatePayload): Promise<TaskItem> {
  return request('/api/tasks', { method: 'POST', body: JSON.stringify(payload) })
}

export async function patchTask(taskId: number, payload: TaskPatchPayload): Promise<TaskItem> {
  return request(`/api/tasks/${taskId}`, { method: 'PATCH', body: JSON.stringify(payload) })
}

export async function addTaskNote(taskId: number, note: string, author = 'owner'): Promise<void> {
  await request(`/api/tasks/${taskId}/notes`, { method: 'POST', body: JSON.stringify({ note, author }) })
}

export async function submitOwnerInput(taskId: number, items: OwnerInputChecklistItem[], author = 'owner'): Promise<{ ok: boolean; items: number }> {
  return request(`/api/tasks/${taskId}/owner-input`, {
    method: 'POST',
    body: JSON.stringify({ items, author }),
  })
}

export async function evaluateOwnerInput(taskId: number, author = 'tobi'): Promise<{ passed: boolean; missing: string[]; message: string }> {
  return request(`/api/tasks/${taskId}/evaluate-input`, {
    method: 'POST',
    body: JSON.stringify({ author }),
  })
}

export async function sendTaskCommand(taskId: number, command: string, author = 'owner'): Promise<{ ok: boolean; task_id: number; ack: string }> {
  return request(`/api/tasks/${taskId}/command`, {
    method: 'POST',
    body: JSON.stringify({ command, author }),
  })
}

export async function deleteTask(taskId: number): Promise<{ ok: boolean }> {
  return request(`/api/tasks/${taskId}`, { method: 'DELETE' })
}

export async function getHighRiskTaskAudit(limit = 50): Promise<{ items: HighRiskAuditItem[]; count: number; timestamp: string }> {
  return get(`/api/tasks/audit/high-risk?limit=${limit}`)
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

// ── Health diagnostics ──────────────────────────────────────────────
export type LivenessCheck = { ok: boolean; detail: string; latency_ms?: number }
export type LogEntry = { level: 'ERROR' | 'WARNING'; msg: string; source: string }

export type HealthReport = {
  timestamp: string
  overall: 'healthy' | 'degraded' | 'issue'
  score: number          // 0–100 overall health
  score_notes: string[]  // what's pulling health below 100
  up: Record<string, LivenessCheck>
  configured: Record<string, boolean>
  activity: Record<string, string | null>
  data: {
    active_projects?: number
    pending_human_tasks?: number
    blocked_tasks?: number
    revenue_this_month?: number
  }
  recent_errors: LogEntry[]
}

export type DeepTestReport = {
  timestamp: string
  llm: LivenessCheck & { provider?: string }
  integrations: Record<string, LivenessCheck>
  summary?: { ok: number; total: number }
}

// ── Ability module (Mission Control §3) ─────────────────────────────
export type AbilityUsage = {
  count?: number
  done?: number
  success_rate?: number | null
  avg_impact?: number | null
  success?: number
  failure?: number
  revenue_tracked?: number
  configured?: number
  of?: number
  last_active?: string | null
}

export type AbilitiesReport = {
  timestamp: string
  abilities: Record<string, AbilityUsage>
}

export type SkillRecord = {
  id: string
  name: string
  category: string | null
  layer: string
  tier: string
  instructions: string | null
  status: string
  risk_tier: string
  version: number
  created_at: string
  updated_at: string
}

export type SkillVersion = {
  id: number
  version: number
  diff_summary: string | null
  metric_snapshot_json: string | null
  provenance_json: string | null
  created_at: string
}

export type SkillDetail = {
  skill: SkillRecord
  metrics: {
    skill_id: string; runs: number; successes: number
    last_run_at: string | null; avg_latency_ms: number | null; token_volume: number
  } | null
  versions: SkillVersion[]
  deps: { child_id: string; pinned_version: number | null }[]
}

export type Proposal = {
  id: number
  skill_id: string | null
  kind: 'create' | 'edit' | 'promote'
  risk_tier: 'low' | 'high'
  title: string | null
  status: 'pending' | 'approved' | 'rejected'
  rationale: string | null
  created_at: string
  resolved_at: string | null
  payload: Record<string, unknown>
}

export async function getAbilities(): Promise<AbilitiesReport> {
  return get('/api/abilities')
}

export async function getAbilityDetail(id: string): Promise<SkillDetail> {
  return get(`/api/abilities/${id}`)
}

export async function coachAbility(id: string, note: string, author = 'owner'): Promise<{ ok: boolean; proposal_id: number }> {
  return request(`/api/abilities/${id}/coach`, { method: 'POST', body: JSON.stringify({ note, author }) })
}

export async function getProposals(status = 'pending'): Promise<{ items: Proposal[]; count: number; timestamp: string }> {
  return get(`/api/proposals?status=${status}`)
}

export async function approveProposal(id: number): Promise<{ ok: boolean; new_version: number | null }> {
  return request(`/api/proposals/${id}/approve`, { method: 'POST' })
}

export async function rejectProposal(id: number): Promise<{ ok: boolean }> {
  return request(`/api/proposals/${id}/reject`, { method: 'POST' })
}

export async function rollbackAbility(id: string, version: number): Promise<{ ok: boolean; new_version: number }> {
  return request(`/api/abilities/${id}/rollback/${version}`, { method: 'POST' })
}

// ── Evolution / Tier progression ────────────────────────────────────
export type AbilityStatus = 'active' | 'inactive'

export type TierAbility = {
  id: string
  name: string
  description: string
  how_to_unlock: string | null
  effort: string
  status: AbilityStatus
  just_activated: boolean
}

export type TierPillars = {
  understand: TierAbility[]
  control: TierAbility[]
  presence: TierAbility[]
}

export type TierData = {
  id: number
  roman: string
  name: string
  tagline: string
  color_key: string
  pillars: TierPillars
  active_count: number
  total_count: number
  progress_pct: number
  complete: boolean
}

export type EvolutionReport = {
  tiers: TierData[]
  current_tier: number
  jarvis_pct: number
  total_active: number
  total_abilities: number
  just_unlocked: number[]
  missing_in_current_tier: TierAbility[]
  timestamp: string
}

export async function getEvolution(): Promise<EvolutionReport> {
  return get('/api/evolution')
}

// ── Project Module ──────────────────────────────────────────────────
export type PMProjectStatus = 'idea' | 'active' | 'done' | 'archived'
export type PMProjectSize   = 'small' | 'medium' | 'large' | 'epic'
export type PMGoalOwner     = 'user' | 'tobi'
export type PMMissionStatus = 'queued' | 'running' | 'done' | 'failed'

export type PMProject = {
  id: number
  name: string
  description: string | null
  status: PMProjectStatus
  size: PMProjectSize
  category: string | null
  emoji_icon: string
  accent_color: string
  deadline: string | null
  kpi_mode: string | null
  kpi_id: string | null
  kpi_metric_name: string | null
  kpi_target_value: number | null
  kpi_current_value: number
  progress_pct: number
  template_id: number | null
  created_by: string
  created_at: string
  updated_at: string
  task_count: number
  task_done: number
  goal_count: number
}

export type PMGoal = {
  id: number
  project_id: number
  title: string
  metric_name: string | null
  target_value: number
  current_value: number
  progress_pct: number
  due_date: string | null
  owner: PMGoalOwner
  created_at: string
  updated_at: string
}

export type PMMission = {
  id: number
  project_id: number
  prompt: string
  status: PMMissionStatus
  output: string | null
  tasks_created: number
  docs_created: number
  duration_ms: number | null
  created_by: string
  created_at: string
  completed_at: string | null
}

export type PMActivity = {
  id: number
  project_id: number
  actor: string
  action_type: string
  summary: string
  diff: Record<string, any> | null
  created_at: string
}

export type PMFile = {
  id: number
  project_id: number
  filename: string
  file_path: string | null
  file_size: number | null
  mime_type: string | null
  uploaded_by: string
  created_at: string
}

export type PMTemplate = {
  id: number
  name: string
  description: string | null
  source_project_id: number | null
  snapshot: { goals: PMGoal[]; tasks: { title: string; priority: string }[] }
  created_at: string
}

export type PMStats = {
  active_projects: number
  total_projects: number
  tasks_due_today: number
  last_mission: { prompt: string; status: string; created_at: string } | null
  timestamp: string
}

export type PMProjectCreate = {
  name: string
  description?: string
  status?: PMProjectStatus
  size?: PMProjectSize
  category?: string
  emoji_icon?: string
  accent_color?: string
  deadline?: string
  kpi_mode?: string
  kpi_id?: string
  kpi_metric_name?: string
  kpi_target_value?: number
  template_id?: number
  created_by?: string
}

export type PMProjectPatch = Partial<Omit<PMProjectCreate, 'created_by'>> & { kpi_current_value?: number }

export type PMGoalCreate = {
  title: string
  metric_name?: string
  target_value?: number
  current_value?: number
  due_date?: string
  owner?: PMGoalOwner
}

export type PMTaskCreate = {
  title: string
  objective?: string
  description?: string
  status?: string
  priority?: string
  agent?: string
  due_at?: string
  time_estimate?: string
  pm_goal_id?: number
}

// Projects
export async function pmListProjects(params?: { status?: string; category?: string; size?: string; q?: string }): Promise<{ items: PMProject[]; count: number }> {
  const p = new URLSearchParams()
  if (params?.status) p.set('status', params.status)
  if (params?.category) p.set('category', params.category)
  if (params?.size) p.set('size', params.size)
  if (params?.q) p.set('q', params.q)
  const qs = p.toString()
  return get(`/api/pm/projects${qs ? `?${qs}` : ''}`)
}
export async function pmGetProject(id: number): Promise<PMProject> { return get(`/api/pm/projects/${id}`) }
export async function pmCreateProject(payload: PMProjectCreate): Promise<PMProject> {
  return request('/api/pm/projects', { method: 'POST', body: JSON.stringify(payload) })
}
export async function pmPatchProject(id: number, payload: PMProjectPatch): Promise<PMProject> {
  return request(`/api/pm/projects/${id}`, { method: 'PATCH', body: JSON.stringify(payload) })
}
export async function pmDeleteProject(id: number): Promise<{ ok: boolean }> {
  return request(`/api/pm/projects/${id}`, { method: 'DELETE' })
}

// Goals
export async function pmListGoals(projectId: number): Promise<{ items: PMGoal[]; count: number }> {
  return get(`/api/pm/projects/${projectId}/goals`)
}
export async function pmCreateGoal(projectId: number, payload: PMGoalCreate): Promise<PMGoal> {
  return request(`/api/pm/projects/${projectId}/goals`, { method: 'POST', body: JSON.stringify(payload) })
}
export async function pmPatchGoal(projectId: number, goalId: number, payload: Partial<PMGoalCreate>): Promise<PMGoal> {
  return request(`/api/pm/projects/${projectId}/goals/${goalId}`, { method: 'PATCH', body: JSON.stringify(payload) })
}
export async function pmDeleteGoal(projectId: number, goalId: number): Promise<{ ok: boolean }> {
  return request(`/api/pm/projects/${projectId}/goals/${goalId}`, { method: 'DELETE' })
}

// Tasks
export async function pmListTasks(projectId: number, params?: { status?: string; assignee?: string }): Promise<{ items: TaskItem[]; count: number }> {
  const p = new URLSearchParams()
  if (params?.status) p.set('status', params.status)
  if (params?.assignee) p.set('assignee', params.assignee)
  const qs = p.toString()
  return get(`/api/pm/projects/${projectId}/tasks${qs ? `?${qs}` : ''}`)
}
export async function pmCreateTask(projectId: number, payload: PMTaskCreate): Promise<TaskItem> {
  return request(`/api/pm/projects/${projectId}/tasks`, { method: 'POST', body: JSON.stringify(payload) })
}
export async function pmPatchSubtasks(projectId: number, taskId: number, subtasks: { id: string; title: string; completed: boolean }[]): Promise<{ ok: boolean }> {
  return request(`/api/pm/projects/${projectId}/tasks/${taskId}/subtasks`, { method: 'PATCH', body: JSON.stringify(subtasks) })
}

// Missions
export async function pmListMissions(projectId: number): Promise<{ items: PMMission[]; count: number }> {
  return get(`/api/pm/projects/${projectId}/missions`)
}
export async function pmCreateMission(projectId: number, prompt: string): Promise<PMMission> {
  return request(`/api/pm/projects/${projectId}/missions`, { method: 'POST', body: JSON.stringify({ prompt, created_by: 'user' }) })
}

// Activity
export async function pmListActivity(projectId: number, actor?: string): Promise<{ items: PMActivity[]; count: number }> {
  const qs = actor ? `?actor=${actor}` : ''
  return get(`/api/pm/projects/${projectId}/activity${qs}`)
}

// Files
export async function pmListFiles(projectId: number): Promise<{ items: PMFile[]; count: number }> {
  return get(`/api/pm/projects/${projectId}/files`)
}
export async function pmCreateFile(projectId: number, payload: { filename: string; file_size?: number; mime_type?: string }): Promise<PMFile> {
  return request(`/api/pm/projects/${projectId}/files`, { method: 'POST', body: JSON.stringify(payload) })
}
export async function pmDeleteFile(projectId: number, fileId: number): Promise<{ ok: boolean }> {
  return request(`/api/pm/projects/${projectId}/files/${fileId}`, { method: 'DELETE' })
}

// Templates
export async function pmListTemplates(): Promise<{ items: PMTemplate[]; count: number }> { return get('/api/pm/templates') }
export async function pmCreateTemplate(payload: { name: string; description?: string; source_project_id: number }): Promise<PMTemplate> {
  return request('/api/pm/templates', { method: 'POST', body: JSON.stringify(payload) })
}
export async function pmDeleteTemplate(id: number): Promise<{ ok: boolean }> {
  return request(`/api/pm/templates/${id}`, { method: 'DELETE' })
}

// Stats
export async function pmGetStats(): Promise<PMStats> { return get('/api/pm/stats') }

async function get(path: string) {
  const res = await fetch(path, { cache: 'no-cache' })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

async function request(path: string, init: RequestInit) {
  const isFormData = init.body instanceof FormData
  const res = await fetch(path, {
    cache: 'no-cache',
    ...init,
    // headers must come AFTER ...init so a caller's headers merge *into* the
    // defaults instead of replacing them (otherwise Content-Type is lost → 422).
    // For FormData bodies we must NOT set Content-Type — the browser needs to
    // set multipart/form-data with its own boundary or FastAPI rejects the upload.
    headers: {
      ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
      ...(init.headers || {}),
    },
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

// ── Performance "system doctor" (#19) ────────────────────────────────────────
export type PerfSubsystem = {
  name: string; score: number; grade: string; files: number; total_loc: number
  max_loc: number; max_degree: number; todos: number; oversized: number; god_modules: number
}
export type PerfFinding = {
  title: string; subsystem: string; severity: 'high' | 'med' | 'low'
  effort: 'S' | 'M' | 'L'; detail: string; target: string; kind: string
}
export type PerfFreshness = { built_short?: string; head_short?: string; stale?: boolean; behind_label?: string }
export type PerfRuntime = { available?: boolean; requests?: number; cost_usd?: number; avg_latency_ms?: number; storage_bytes?: number } | null
export type PerfTrendPoint = { taken_at: string; score: number; grade: string; depth: string }
export type PerfReport = {
  available?: boolean
  id?: number; taken_at?: string; depth?: string
  overall?: { score: number; grade: string }
  subsystems?: PerfSubsystem[]
  findings?: PerfFinding[]
  diagnosis?: string
  runtime?: PerfRuntime
  freshness?: PerfFreshness
  counts?: { files: number; findings: number; high: number }
  trend?: PerfTrendPoint[]
  deep_synthesized?: boolean
  generated_ms?: number
}

export async function getPerformance(): Promise<PerfReport> {
  return get('/api/health/performance')
}
export async function runPerformance(depth: 'quick' | 'deep'): Promise<PerfReport> {
  return request('/api/health/performance/run', { method: 'POST', body: JSON.stringify({ depth }) })
}
export async function createPerformanceTask(
  f: { title: string; detail?: string; subsystem?: string; severity?: string },
): Promise<{ ok: boolean; project_id: number; task: unknown }> {
  return request('/api/health/performance/finding/task', { method: 'POST', body: JSON.stringify(f) })
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
export type TaskAgent = 'tobi' | 'research' | 'coder' | 'ceo' | 'owner'

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
  // Project v2 fields
  start_at?: string | null
  reminder_at?: string | null
  time_estimate?: string | null
  pm_project_id?: number | null
  pm_goal_id?: number | null
  sub_tasks?: PMSubTask[]
  blocks?: number[]
  blocked_by?: number[]
}

export type PMSubTask = { id: string; title: string; completed: boolean; assignee?: string; due_at?: string | null }

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
  description?: string
  start_at?: string | null
  reminder_at?: string | null
  time_estimate?: string | null
  before_task_id?: number
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

// Read-only repo Hermes skills for the Ability dashboard (#14).
export type HermesSkill = {
  id: string
  name: string
  source: 'hermes_repo_file'
  file_path: string
  status: 'available' | string
  risk_tier: 'approval_required' | string
  can_execute: boolean
  version: number
  description: string
  last_modified: string | null
  parse_warning?: boolean
}
export async function getHermesSkills(): Promise<{ items: HermesSkill[]; count: number }> {
  return get('/api/hermes/skills')
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

export type ReflectResult = {
  ok: boolean
  lesson: { title: string; content: string; lesson_type: string }
  lessons_store_active: boolean
  stats: Record<string, number>
}

/** Run an on-demand self-reflection — writes lesson #1 and activates the
 * Genesis lessons_store ability. */
export async function reflectNow(): Promise<ReflectResult> {
  return request('/api/evolution/reflect', { method: 'POST' })
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
  icon_type?: 'emoji' | 'icon' | 'custom'
  icon_value?: string | null
  resources_bytes?: number
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
  description: string | null
  metric_name: string | null
  target_value: number
  current_value: number
  progress_pct: number
  due_date: string | null
  priority: 'low' | 'medium' | 'high'
  owner: PMGoalOwner
  parent_goal_id: number | null
  mode?: 'metric' | 'task'
  linked_task_ids?: number[]
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

export type PMProjectPatch = Partial<Omit<PMProjectCreate, 'created_by'>> & {
  kpi_current_value?: number
  icon_type?: 'emoji' | 'icon' | 'custom'
  icon_value?: string | null
}

export type PMGoalCreate = {
  title: string
  description?: string
  metric_name?: string
  target_value?: number
  current_value?: number
  due_date?: string
  priority?: 'low' | 'medium' | 'high'
  owner?: PMGoalOwner
  parent_goal_id?: number | null
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
export async function pmReorderProjects(order: number[]): Promise<{ ok: boolean; count: number }> {
  return request('/api/pm/projects/reorder', { method: 'POST', body: JSON.stringify({ order }) })
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
export async function pmPostActivity(projectId: number, payload: { actor?: string; action_type: string; summary: string; diff?: Record<string, any> }): Promise<{ ok: boolean }> {
  return request(`/api/pm/projects/${projectId}/activity`, { method: 'POST', body: JSON.stringify(payload) })
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

// ── Project v2: Overview · Resources · Folders · Icons · Deps · Goal-links ────
export type PMResource = {
  id: number; project_id: number; folder_id: number | null
  kind: 'file' | 'link'; name: string; ext: string | null
  source: 'device' | 'url' | 'drive' | 'youtube' | 'web' | 'github' | 'pdf'
  rtype: string; size_bytes: number; disk_path: string | null; url: string | null
  mime: string | null; thumb: string | null; tags: string[]; has_text: boolean
  created_by: string; created_at: string; updated_at: string
}
export type PMFolder = { id: number; project_id: number; parent_id: number | null; name: string; created_at: string }
export type PMResourcesResponse = { items: PMResource[]; folders: PMFolder[]; count: number }

export type PMOverviewMetrics = {
  task_total: number; task_done: number; task_active: number; task_overdue: number
  progress_pct: number; goals_count: number; goals_avg_pct: number; goals_completed: number
  resources_count: number; resources_bytes: number; resources_by_type: Record<string, number>
  estimate_total_min: number; estimate_done_min: number; deadline_days: number | null
  created_at: string; updated_at: string; last_activity: string | null
}
export type PMOverview = {
  project: PMProject; metrics: PMOverviewMetrics
  active_tasks: TaskItem[]; goals: PMGoal[]; activity: PMActivity[]
}

export async function pmGetOverview(projectId: number): Promise<PMOverview> {
  return get(`/api/pm/projects/${projectId}/overview`)
}

// Resources
export async function pmListResources(projectId: number, folderId?: number | null): Promise<PMResourcesResponse> {
  const qs = folderId != null ? `?folder_id=${folderId}` : ''
  return get(`/api/pm/projects/${projectId}/resources${qs}`)
}
export async function pmUploadResource(projectId: number, file: File, folderId?: number | null): Promise<PMResource> {
  const fd = new FormData()
  fd.append('file', file)
  if (folderId != null) fd.append('folder_id', String(folderId))
  return request(`/api/pm/projects/${projectId}/resources/upload`, { method: 'POST', body: fd })
}
export async function pmAddResourceLink(projectId: number, url: string, name?: string, folderId?: number | null): Promise<PMResource> {
  return request(`/api/pm/projects/${projectId}/resources/link`, {
    method: 'POST', body: JSON.stringify({ url, name, folder_id: folderId ?? null }),
  })
}
export async function pmPatchResource(projectId: number, rid: number, patch: { name?: string; folder_id?: number | null; tags?: string[] }): Promise<PMResource> {
  return request(`/api/pm/projects/${projectId}/resources/${rid}`, { method: 'PATCH', body: JSON.stringify(patch) })
}
export async function pmDeleteResource(projectId: number, rid: number): Promise<{ ok: boolean }> {
  return request(`/api/pm/projects/${projectId}/resources/${rid}`, { method: 'DELETE' })
}
export function pmResourceRawUrl(projectId: number, rid: number): string {
  return `/api/pm/projects/${projectId}/resources/${rid}/raw`
}

// Folders
export async function pmCreateFolder(projectId: number, name: string, parentId?: number | null): Promise<PMFolder> {
  return request(`/api/pm/projects/${projectId}/folders`, { method: 'POST', body: JSON.stringify({ name, parent_id: parentId ?? null }) })
}
export async function pmRenameFolder(projectId: number, fid: number, name: string): Promise<PMFolder> {
  return request(`/api/pm/projects/${projectId}/folders/${fid}`, { method: 'PATCH', body: JSON.stringify({ name }) })
}
export async function pmDeleteFolder(projectId: number, fid: number): Promise<{ ok: boolean }> {
  return request(`/api/pm/projects/${projectId}/folders/${fid}`, { method: 'DELETE' })
}

// Icons
export async function pmUploadIcon(dataUrl: string, projectId?: number): Promise<{ ok: boolean; id: number; url: string }> {
  return request('/api/pm/icons', { method: 'POST', body: JSON.stringify({ data_url: dataUrl, project_id: projectId ?? null }) })
}
export function pmIconUrl(iconId: number | string): string { return `/api/pm/icons/${iconId}` }

// Task dependencies
export async function pmAddTaskDep(taskId: number, blocksId: number): Promise<{ ok: boolean }> {
  return request(`/api/pm/tasks/${taskId}/deps`, { method: 'POST', body: JSON.stringify({ blocks_id: blocksId }) })
}
export async function pmRemoveTaskDep(taskId: number, blocksId: number): Promise<{ ok: boolean }> {
  return request(`/api/pm/tasks/${taskId}/deps/${blocksId}`, { method: 'DELETE' })
}

// Goal ↔ task links (rollup goals)
export async function pmLinkGoalTask(projectId: number, goalId: number, taskId: number): Promise<{ ok: boolean }> {
  return request(`/api/pm/projects/${projectId}/goals/${goalId}/tasks`, { method: 'POST', body: JSON.stringify({ task_id: taskId }) })
}
export async function pmUnlinkGoalTask(projectId: number, goalId: number, taskId: number): Promise<{ ok: boolean }> {
  return request(`/api/pm/projects/${projectId}/goals/${goalId}/tasks/${taskId}`, { method: 'DELETE' })
}

// ── Brain (long-term owner memory) ───────────────────────────────────────────
export type Memory = {
  id: number
  content: string
  category: string
  confidence: number
  source: string
  status: string
  context?: string | null
  created_at: string
  updated_at: string
  last_confirmed_at?: string | null
  stale: boolean
  has_embedding?: boolean
  score?: number
}
export type MemoryCategory = {
  id: string; label: string; color: string; icon: string
  sort_order: number; sensitive: number; is_locked: number; status: string
}
export type BrainStats = {
  total: number
  by_category: Record<string, number>
  by_source: Record<string, number>
  pending: number
  conflicts: number
  stale: number
  embeddings: boolean
}
export type MemoryVersion = {
  id: number; memory_id: number; content: string; category: string
  confidence: number; change_kind: string; changed_by: string; created_at: string
}
export type Conflict = {
  id: number; memory_id: number; candidate_content: string; candidate_category: string
  candidate_confidence: number; candidate_source: string; reason: string; status: string; created_at: string
  existing_content?: string; existing_category?: string; existing_confidence?: number
}
export type ImportCandidate = {
  content: string; category: string; confidence: number
  merge_into?: number; merge_score?: number
}
export type DuplicateGroup = { ids: number[]; memories: Memory[] }
export type ChatMessage = { role: string; content: string }

export type MemoryFilters = { category?: string; source?: string; status?: string; q?: string; stale?: boolean }

function brainQuery(f: MemoryFilters): string {
  const p = new URLSearchParams()
  if (f.category && f.category !== 'all') p.set('category', f.category)
  if (f.source && f.source !== 'all') p.set('source', f.source)
  if (f.status) p.set('status', f.status)
  if (f.q?.trim()) p.set('q', f.q.trim())
  if (f.stale) p.set('stale', 'true')
  const q = p.toString()
  return q ? `?${q}` : ''
}

export async function getBrainStats(): Promise<BrainStats> { return get('/api/brain/stats') }
export async function getBrainCategories(): Promise<{ categories: MemoryCategory[] }> { return get('/api/brain/categories') }
export async function patchBrainCategory(catId: string, payload: { is_locked?: number; label?: string; color?: string }): Promise<{ ok: boolean }> {
  return request(`/api/brain/categories/${catId}`, { method: 'PATCH', body: JSON.stringify(payload) })
}
export async function getOwnerSettings(): Promise<Record<string, string>> { return get('/api/owner/settings') }
export async function patchOwnerSettings(payload: Record<string, string>): Promise<{ ok: boolean }> {
  return request('/api/owner/settings', { method: 'PATCH', body: JSON.stringify(payload) })
}
export async function getMemories(f: MemoryFilters = {}): Promise<{ items: Memory[] }> { return get(`/api/brain/memories${brainQuery(f)}`) }
export async function getMemory(id: number): Promise<Memory> { return get(`/api/brain/memories/${id}`) }
export async function createMemory(payload: { content: string; category: string; confidence?: number; source?: string }): Promise<Memory> {
  return request('/api/brain/memories', { method: 'POST', body: JSON.stringify(payload) })
}
export async function patchMemory(id: number, payload: { content?: string; category?: string; confidence?: number }): Promise<Memory> {
  return request(`/api/brain/memories/${id}`, { method: 'PATCH', body: JSON.stringify(payload) })
}
export async function deleteMemory(id: number): Promise<{ ok: boolean }> { return request(`/api/brain/memories/${id}`, { method: 'DELETE' }) }
export async function confirmMemory(id: number): Promise<Memory> { return request(`/api/brain/memories/${id}/confirm`, { method: 'POST' }) }
export async function getMemoryVersions(id: number): Promise<{ versions: MemoryVersion[] }> { return get(`/api/brain/memories/${id}/versions`) }
export async function searchMemories(query: string, k = 12): Promise<{ items: Memory[] }> {
  return request('/api/brain/search', { method: 'POST', body: JSON.stringify({ query, k }) })
}
export async function getPendingMemories(): Promise<{ items: Memory[] }> { return get('/api/brain/pending') }
export async function acceptPending(id: number): Promise<Memory> { return request(`/api/brain/pending/${id}/accept`, { method: 'POST' }) }
export async function rejectPending(id: number): Promise<{ ok: boolean }> { return request(`/api/brain/pending/${id}/reject`, { method: 'POST' }) }
export async function getConflicts(): Promise<{ items: Conflict[] }> { return get('/api/brain/conflicts') }
export async function resolveConflict(id: number, decision: 'keep_existing' | 'use_candidate' | 'keep_both'): Promise<{ ok: boolean }> {
  return request(`/api/brain/conflicts/${id}/resolve`, { method: 'POST', body: JSON.stringify({ decision }) })
}
export async function parseImport(filename: string, content: string): Promise<{ items: ImportCandidate[] }> {
  return request('/api/brain/import', { method: 'POST', body: JSON.stringify({ filename, content }) })
}
export async function commitImport(filename: string, source_type: string, items: ImportCandidate[]): Promise<{ saved: number; merged: number }> {
  return request('/api/brain/import/commit', { method: 'POST', body: JSON.stringify({ filename, source_type, items }) })
}
export async function getDuplicates(): Promise<{ groups: DuplicateGroup[] }> { return get('/api/brain/duplicates') }
export async function mergeDuplicates(ids: number[], keep_id?: number): Promise<{ merged: number; kept?: number }> {
  return request('/api/brain/duplicates/merge', { method: 'POST', body: JSON.stringify({ ids, keep_id }) })
}
export async function getNarrative(): Promise<{ content: string | null; created_at?: string }> { return get('/api/brain/narrative') }
export async function makeNarrative(): Promise<{ content: string; created_at?: string }> { return request('/api/brain/narrative', { method: 'POST' }) }
export async function rememberFact(content: string, category?: string): Promise<{ ok: boolean; id?: number; category?: string }> {
  return request('/api/brain/remember', { method: 'POST', body: JSON.stringify({ content, category }) })
}
export async function brainChat(message: string): Promise<{ reply: string }> {
  return request('/api/brain/chat', { method: 'POST', body: JSON.stringify({ message }) })
}
/** Brain v2: stream the chat reply token-by-token. `onDelta` fires per chunk; resolves
 *  when the `done` event arrives. Falls back transparently to a single chunk when the
 *  model provider can't stream (backend emits one delta then done). */
export type PendingAction = { id: number; tool: string; summary: string; risk: string; items?: PendingAction[] }

export async function streamBrainChat(
  message: string,
  onDelta: (text: string) => void,
  onAction?: (action: PendingAction) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch('/api/brain/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message }),
    signal,
  })
  if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`)
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    let idx: number
    while ((idx = buffer.indexOf('\n\n')) >= 0) {
      const frame = buffer.slice(0, idx)
      buffer = buffer.slice(idx + 2)
      let event = 'message'
      let data = ''
      for (const line of frame.split('\n')) {
        if (line.startsWith('event:')) event = line.slice(6).trim()
        else if (line.startsWith('data:')) data += line.slice(5).trim()
      }
      if (event === 'delta' && data) {
        try { const o = JSON.parse(data); if (o.text) onDelta(o.text) } catch { /* ignore */ }
      } else if (event === 'action' && data) {
        try { const o = JSON.parse(data); if (o && o.id != null) onAction?.(o as PendingAction) } catch { /* ignore */ }
      } else if (event === 'error') {
        const o = (() => { try { return JSON.parse(data) } catch { return {} as { detail?: string } } })()
        throw new Error(o.detail || 'stream error')
      } else if (event === 'done') {
        return
      }
    }
  }
}
export async function getChatHistory(): Promise<{ items: ChatMessage[] }> { return get('/api/brain/chat/history') }
export async function runBrainSweep(): Promise<Record<string, number>> { return request('/api/brain/sweep', { method: 'POST' }) }

// ── Conductor (queue #7) — TOBI Actions audit + confirm ──────────────────────────
export type ConductorAction = {
  id: number; chat_id?: number; surface: string; tool: string; risk: string
  status: string; summary: string; result?: unknown; created_at: string; executed_at?: string | null
}
export type ConductorStatus = {
  phase: string
  read_tools: { name: string; description: string }[]
  act_tools: { name: string; risk: string; description: string }[]
  surfaces: Record<string, string>
}
export async function getConductorActions(limit = 50): Promise<{ count: number; actions: ConductorAction[] }> {
  return get(`/api/conductor/actions?limit=${limit}`)
}
export async function getConductorStatus(): Promise<ConductorStatus> { return get('/api/conductor/status') }
export async function confirmConductorAction(
  action_id: number, decision: 'approve' | 'reject',
): Promise<{ ok: boolean; status: string; summary?: string; result?: unknown; error?: string }> {
  return request('/api/conductor/confirm', { method: 'POST', body: JSON.stringify({ action_id, decision }) })
}

// ── TOBI CLI / Terminal engine (#11) ─────────────────────────────────────────────
export type TerminalMode = 'plan' | 'ask' | 'accept' | 'auto'
export type TerminalStatus = {
  enabled: boolean; mode: TerminalMode; os: string; shell: string; cwd: string
  package_managers: string[]; tools_registered: number; modes: TerminalMode[]
}
export type TerminalJob = {
  id: number; command: string; status: string; exit_code: number | null
  cwd?: string; risk?: string; started_at?: string; ended_at?: string; live?: boolean
}
export type InstalledTool = {
  name: string; version?: string; channel?: string; how_to_use?: string
  wired?: number; status?: string; updated_at?: string
}

export async function getTerminalStatus(): Promise<TerminalStatus> { return get('/api/terminal/status') }
export async function setTerminalMode(mode: TerminalMode): Promise<{ ok: boolean; mode: TerminalMode }> {
  return request('/api/terminal/mode', { method: 'POST', body: JSON.stringify({ mode }) })
}
export async function setTerminalKillSwitch(enabled: boolean): Promise<{ ok: boolean; enabled: boolean }> {
  return request('/api/terminal/killswitch', { method: 'POST', body: JSON.stringify({ enabled }) })
}
export async function getTerminalJobs(): Promise<{ count: number; jobs: TerminalJob[] }> { return get('/api/terminal/jobs') }
export async function killTerminalJob(jobId: number): Promise<{ ok?: boolean; error?: string; status?: string }> {
  return request(`/api/terminal/jobs/${jobId}/kill`, { method: 'POST' })
}
export async function getInstalledTools(): Promise<{ count: number; tools: InstalledTool[] }> { return get('/api/terminal/tools') }

// ── Premium Chat (#8): multi-model sessions, typed stream, LLM config ────────────
export type ChatSession = {
  id: number; title: string; model: string | null
  created_at: string; updated_at: string; message_count?: number
}
// ── Chat Mode contract (#16) ──────────────────────────────────────────────────
export type ChatModeId = 'chat' | 'agent'
export type ChatCapabilities = { web_search?: boolean; deep_research?: boolean; terminal_intent?: boolean; connectors?: string[] }
export type ChatModeEvent = { mode: ChatModeId; legacy_mode?: string | null; capabilities?: ChatCapabilities }
export type ContextChip = { id: number; name: string }
export type ChatContextEvent = { projects: ContextChip[]; resources: { name?: string }[]; auto?: boolean }
export type ChatPlanEvent = { steps: string[]; title?: string }
export type ChatArtifactEvent = { id: number; kind: string; title: string }
export type ChatTurnMeta = {
  mode?: ChatModeId; legacy_mode?: string | null; capabilities?: ChatCapabilities
  steps?: string[]; tools?: string[]; run_id?: number; artifact_ids?: number[]
  context?: { projects?: ContextChip[]; resources?: { name?: string }[] }
  turn_id?: string
}
export type ChatRuntimeMode = 'off' | 'shadow' | 'on'
export async function getChatConfig(): Promise<{ mode_v2: boolean; chat_runtime_v2?: ChatRuntimeMode }> { return get('/api/chat/config') }
export async function setChatConfig(modeV2: boolean): Promise<{ mode_v2: boolean }> {
  return request('/api/chat/config', { method: 'POST', body: JSON.stringify({ mode_v2: modeV2 }) })
}
export type AgentRun = {
  id: number; session_id: number; message_id?: number | null; mode: string; status: string
  title?: string | null; error?: string | null; created_at: string; updated_at: string
  completed_at?: string | null; step_count?: number; steps?: AgentRunStep[]
}
export type AgentRunStep = {
  id: number; run_id: number; type: string; status: string; title?: string | null
  summary?: string | null; tool?: string | null; risk?: string | null
  payload_json?: string | null; created_at: string; completed_at?: string | null
}
export async function getSessionRuns(id: number, limit = 20): Promise<{ runs: AgentRun[] }> {
  return get(`/api/chat/sessions/${id}/runs?limit=${limit}`)
}
export async function getAgentRun(runId: number): Promise<AgentRun> { return get(`/api/chat/runs/${runId}`) }
export type AgentRunCommand = 'resume' | 'retry_step' | 'skip_step' | 'revise' | 'cancel'
export type AgentRunCommandResult = {
  run_id: number; session_id?: number; status: string; requires_turn: boolean; recovery_prompt?: string
}
export async function commandAgentRun(runId: number, command: AgentRunCommand, revision = ''): Promise<AgentRunCommandResult> {
  return request(`/api/chat/runs/${runId}/commands`, {
    method: 'POST', body: JSON.stringify({ command, revision }),
  })
}
export type ChatRuntimeEvent = {
  turn_id: string; seq: number; type: string; stage: string; timestamp: string; data: Record<string, any>
}
export type ChatTurnTrace = {
  id: string; session_id: number; run_id?: number | null; status: string; mode: string; model?: string | null
  route?: string | null; first_event_ms?: number | null; first_token_ms?: number | null; total_ms?: number | null
  error_code?: string | null; events: Array<{ seq: number; event_type: string; stage: string; payload: Record<string, any>; created_at: string }>
}
export async function getChatTurnTrace(turnId: string): Promise<ChatTurnTrace> {
  return get(`/api/chat/turns/${encodeURIComponent(turnId)}/trace`)
}
export type ChatArtifact = {
  id: number; session_id: number; run_id?: number | null; kind: string
  title?: string | null; content?: string; meta_json?: string | null; created_at: string
}
export async function getSessionArtifacts(id: number, limit = 50): Promise<{ artifacts: ChatArtifact[] }> {
  return get(`/api/chat/sessions/${id}/artifacts?limit=${limit}`)
}
export async function getChatArtifact(artifactId: number): Promise<ChatArtifact> {
  return get(`/api/chat/artifacts/${artifactId}`)
}

export type ChatStoredMessage = {
  id: number; role: string; content: string; parent_id?: number | null
  model?: string | null; tokens?: number | null; thinking?: string | null
  feedback?: number | null; meta?: string | null; created_at: string
}
export type ChatUsage = { prompt_tokens: number; completion_tokens: number; model: string; latency_ms: number }
export type ReaderChip = { url: string; state: string; title?: string | null }
export type ChatNotice = { kind: 'model_issue' | 'reader' | string; reader?: string; items?: ReaderChip[]; run_id?: number }
export type PickerQuestion = { question: string; options?: string[] }
export type ChatPicker = { topic: string; questions: PickerQuestion[] }
export type ChatStreamHandlers = {
  onDelta: (text: string) => void
  onThinking?: (phase: string, tools?: string[]) => void
  onAction?: (action: PendingAction) => void
  onPicker?: (picker: ChatPicker) => void
  onUsage?: (usage: ChatUsage) => void
  onNotice?: (notice: ChatNotice) => void
  onReset?: () => void
  onTerminal?: (line: string) => void   // live stdout from a run_command execution (#11)
  // ── #16 mode contract events ──
  onMode?: (mode: ChatModeEvent) => void          // normalized mode echo (first frame)
  onContext?: (ctx: ChatContextEvent) => void     // auto project context chips
  onPlan?: (plan: ChatPlanEvent) => void          // agent-mode declared plan
  onArtifact?: (artifact: ChatArtifactEvent) => void  // durable artifact produced
  onTurnStarted?: (event: ChatRuntimeEvent) => void
  onRuntimeEvent?: (event: ChatRuntimeEvent) => void
  onRecoveryRequired?: (event: ChatRuntimeEvent) => void
}

export async function getChatSessions(): Promise<{ sessions: ChatSession[] }> { return get('/api/chat/sessions') }
export async function createChatSession(model?: string | null, title?: string): Promise<ChatSession> {
  return request('/api/chat/sessions', { method: 'POST', body: JSON.stringify({ model, title }) })
}
export async function getChatSession(id: number): Promise<{ session: ChatSession; messages: ChatStoredMessage[] }> {
  return get(`/api/chat/sessions/${id}`)
}
export async function patchChatSession(id: number, payload: { title?: string; model?: string | null }): Promise<ChatSession> {
  return request(`/api/chat/sessions/${id}`, { method: 'PATCH', body: JSON.stringify(payload) })
}
export async function deleteChatSession(id: number): Promise<{ ok: boolean }> {
  return request(`/api/chat/sessions/${id}`, { method: 'DELETE' })
}
export async function appendChatMessage(id: number, content: string, role = 'assistant'): Promise<{ ok: boolean }> {
  return request(`/api/chat/sessions/${id}/append`, { method: 'POST', body: JSON.stringify({ role, content }) })
}
export async function forkChatSession(id: number, beforeMessageId: number): Promise<ChatSession> {
  return request(`/api/chat/sessions/${id}/fork`, { method: 'POST', body: JSON.stringify({ before_message_id: beforeMessageId }) })
}
export async function setMessageFeedback(messageId: number, value: number | null): Promise<{ ok: boolean; feedback: number | null }> {
  return request(`/api/chat/messages/${messageId}/feedback`, { method: 'POST', body: JSON.stringify({ value }) })
}
export type SessionActivity = { count: number; actions: ConductorAction[] }
export async function getSessionActivity(id: number, limit = 50): Promise<SessionActivity> {
  return get(`/api/chat/sessions/${id}/activity?limit=${limit}`)
}

export type ChatAttachment = { name: string; mime: string; kind: 'text' | 'image' | 'pdf' | 'file'; text?: string; data_url?: string }
export type ChatTurnOptions = {
  attachments?: ChatAttachment[]; web_research?: boolean; thinking?: boolean; connectors?: string[]
  mode?: ChatModeId; deep_research?: boolean; review_mode?: 'ask' | 'session' | 'always'   // #16
  client_turn_id?: string; resume_run_id?: number
}

/** Stream a premium chat turn: typed SSE (thinking / delta / action / usage / done).
 *  Resolves on `done`; aborts cleanly via `signal` (keeps partial output). */
export async function streamChatSession(
  sessionId: number, message: string, model: string | null | undefined,
  handlers: ChatStreamHandlers, signal?: AbortSignal, options?: ChatTurnOptions,
): Promise<void> {
  const res = await fetch(`/api/chat/sessions/${sessionId}/stream`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message, model, ...(options || {}), client_turn_id: options?.client_turn_id || crypto.randomUUID(),
    }), signal,
  })
  if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`)
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    let idx: number
    while ((idx = buffer.indexOf('\n\n')) >= 0) {
      const frame = buffer.slice(0, idx); buffer = buffer.slice(idx + 2)
      let event = 'message', data = ''
      for (const line of frame.split('\n')) {
        if (line.startsWith('event:')) event = line.slice(6).trim()
        else if (line.startsWith('data:')) data += line.slice(5).trim()
      }
      if (!data && event !== 'done') continue
      const parse = () => { try { return JSON.parse(data) } catch { return {} } }
      if (event === 'delta') { const o = parse(); if (o.text) handlers.onDelta(o.text) }
      else if (event === 'thinking') { const o = parse(); handlers.onThinking?.(o.phase || '', o.tools) }
      else if (event === 'action') { const o = parse(); if (o && o.id != null) handlers.onAction?.(o as PendingAction) }
      else if (event === 'picker') { const o = parse(); if (o && Array.isArray(o.questions) && o.questions.length) handlers.onPicker?.(o as ChatPicker) }
      else if (event === 'usage') { handlers.onUsage?.(parse() as ChatUsage) }
      else if (event === 'notice') { const o = parse(); if (o && o.kind) handlers.onNotice?.(o as ChatNotice) }
      else if (event === 'reset') { handlers.onReset?.() }
      else if (event === 'terminal') { const o = parse(); if (o && typeof o.line === 'string') handlers.onTerminal?.(o.line) }
      else if (event === 'mode') { const o = parse(); if (o && o.mode) handlers.onMode?.(o as ChatModeEvent) }
      else if (event === 'context') { const o = parse(); if (o && Array.isArray(o.projects)) handlers.onContext?.(o as ChatContextEvent) }
      else if (event === 'plan') { const o = parse(); if (o && Array.isArray(o.steps)) handlers.onPlan?.(o as ChatPlanEvent) }
      else if (event === 'artifact') { const o = parse(); if (o && o.id != null) handlers.onArtifact?.(o as ChatArtifactEvent) }
      else if (event === 'turn_started') { const o = parse() as ChatRuntimeEvent; if (o?.turn_id) { handlers.onTurnStarted?.(o); handlers.onRuntimeEvent?.(o) } }
      else if (event === 'recovery_required') { const o = parse() as ChatRuntimeEvent; if (o?.turn_id) { handlers.onRecoveryRequired?.(o); handlers.onRuntimeEvent?.(o) } }
      else if (['context_ready', 'plan_ready', 'step_started', 'step_completed', 'step_failed', 'model_escalated', 'turn_completed'].includes(event)) {
        const o = parse() as ChatRuntimeEvent; if (o?.turn_id) handlers.onRuntimeEvent?.(o)
      }
      else if (event === 'error') { throw new Error(parse().detail || 'stream error') }
      else if (event === 'done') return
    }
  }
}

export type LlmProvider = {
  id: string; label: string; kind: string; key_env: string | null
  needs_key: boolean; key_present: boolean; key_last4?: string | null; editable_base_url: boolean
  base_url: string; enabled: boolean; models: string[]
}
export type LlmConfig = {
  default_model: string
  task_overrides: Record<string, string>
  fallback: string[]
  providers: Record<string, { enabled?: boolean; base_url?: string; models?: string[] }>
}
export type AvailableModel = { id: string; provider: string; model: string; label: string; context?: number }
export type HermesPush = { ok: boolean; json?: boolean; yaml?: boolean; cli?: boolean; targets?: string[]; detail: string }
export type LlmConfigResponse = { config: LlmConfig; providers: LlmProvider[]; models: AvailableModel[]; hermes?: HermesPush }

export async function getLlmConfig(): Promise<LlmConfigResponse> { return get('/api/llm/config') }
export async function getLlmModels(): Promise<{ models: AvailableModel[] }> { return get('/api/llm/models') }
export async function saveLlmConfig(config: LlmConfig): Promise<LlmConfigResponse> {
  return request('/api/llm/config', { method: 'POST', body: JSON.stringify({ config }) })
}
export async function setLlmProviderKey(provider: string, value: string): Promise<{ ok: boolean; providers: LlmProvider[]; models: AvailableModel[] }> {
  return vreq(`/api/llm/provider/${provider}/key`, { method: 'POST', body: JSON.stringify({ value }) })
}

// ── multi-key slots: several accounts per provider/secret, one active at a time ──
export type KeySlot = { label: string; last4: string | null; active: boolean; env?: boolean; added_at: string | null; updated_at: string | null }
export type KeySlotsResponse = { ok: boolean; name: string; slots: KeySlot[]; providers: LlmProvider[]; models: AvailableModel[] }
export async function listKeySlots(name: string): Promise<KeySlotsResponse> { return vreq(`/api/keys/${name}`) }
export async function addKeySlot(name: string, value: string, label?: string, activate = false): Promise<KeySlotsResponse> {
  return vreq(`/api/keys/${name}`, { method: 'POST', body: JSON.stringify({ value, label: label || null, activate }) })
}
export async function activateKeySlot(name: string, label: string): Promise<KeySlotsResponse> {
  return vreq(`/api/keys/${name}/activate`, { method: 'POST', body: JSON.stringify({ label }) })
}
export async function deactivateKeySlots(name: string): Promise<KeySlotsResponse> {
  return vreq(`/api/keys/${name}/deactivate`, { method: 'POST' })
}
export async function deleteKeySlot(name: string, label: string): Promise<KeySlotsResponse> {
  return vreq(`/api/keys/${name}/delete`, { method: 'POST', body: JSON.stringify({ label }) })
}
export async function discoverLlmModels(provider: string): Promise<{ ok: boolean; models: string[] }> {
  return request(`/api/llm/discover/${provider}`, { method: 'POST' })
}
export async function pushHermesConfig(): Promise<HermesPush> { return request('/api/llm/hermes-push', { method: 'POST' }) }

// ── Usage analytics + Compact (P3) ───────────────────────────────────────────────
export type UsageModel = { model: string; provider: string; tokens: number; prompt_tokens: number; completion_tokens: number; cost: number; requests: number }
export type UsageDay = { day: string; tokens: number; cost: number }
export type UsageSummary = {
  days: number; total_tokens: number; prompt_tokens: number; completion_tokens: number
  total_cost: number; requests: number; avg_latency_ms: number
  by_model: UsageModel[]; by_surface: Record<string, number>; by_day: UsageDay[]
}
export async function getLlmUsage(days = 7): Promise<UsageSummary> { return get(`/api/llm/usage?days=${days}`) }
export async function compactSession(id: number, model?: string | null): Promise<{ compacted: boolean; messages: ChatStoredMessage[]; summary?: string; detail?: string }> {
  return request(`/api/chat/sessions/${id}/compact`, { method: 'POST', body: JSON.stringify({ model }) })
}

// ── Graph View ────────────────────────────────────────────────────────────────
export interface GraphNode {
  id: number
  domain: string
  ref_kind?: string | null
  ref_id?: string | null
  title: string
  summary?: string | null
  category?: string | null
  color?: string | null
  icon?: string | null
  source_url?: string | null
  degree: number
  community?: number | null
  community_label?: string | null
  x?: number | null
  y?: number | null
  pinned?: number
  has_embedding?: boolean
}
export interface GraphCommunity { cid: number; label: string; color: string; count: number }
export interface GraphEdge {
  id: number
  source: number
  target: number
  type: 'ref' | 'semantic' | 'tag' | 'manual'
  weight: number
  directed?: number
  created_by?: string
}
export interface GraphData { nodes: GraphNode[]; edges: GraphEdge[] }
export interface GraphSource {
  source: string; domain: string; available: boolean; nodes: number
  last_synced_at?: string | null; item_count?: number
}
export interface GraphSearchResult { id: number; title: string; domain: string; score: number }
export interface TimelineEvent { id: number; domain: string; ts: string }
export interface GraphFilters {
  domain?: string; category?: string; q?: string
  min_weight?: number; date_from?: string; date_to?: string
}

function graphQuery(f: GraphFilters = {}): string {
  const p = new URLSearchParams()
  if (f.domain && f.domain !== 'all') p.set('domain', f.domain)
  if (f.category) p.set('category', f.category)
  if (f.q) p.set('q', f.q)
  if (f.min_weight) p.set('min_weight', String(f.min_weight))
  if (f.date_from) p.set('date_from', f.date_from)
  if (f.date_to) p.set('date_to', f.date_to)
  const s = p.toString()
  return s ? `?${s}` : ''
}

export async function getGraph(f: GraphFilters = {}): Promise<GraphData> { return get(`/api/graph${graphQuery(f)}`) }
export async function getGraphSources(): Promise<{ sources: GraphSource[] }> { return get('/api/graph/sources') }
export async function getGraphCommunities(): Promise<{ communities: GraphCommunity[] }> { return get('/api/graph/communities') }
export async function getGraphPath(a: number, b: number): Promise<{ path: GraphNode[] }> { return get(`/api/graph/path?a=${a}&b=${b}`) }
export async function graphRetrieve(query: string, k = 8, hops = 1): Promise<{ results: GraphNode[] }> {
  return request('/api/graph/retrieve', { method: 'POST', body: JSON.stringify({ query, k, hops }) })
}
export async function getGraphTimeline(): Promise<{ events: TimelineEvent[] }> { return get('/api/graph/timeline') }
export async function searchGraph(q: string, k = 12): Promise<{ results: GraphSearchResult[]; mode: string }> {
  return get(`/api/graph/search?q=${encodeURIComponent(q)}&k=${k}`)
}
export async function getGraphNode(id: number): Promise<GraphNode & { connections: GraphData }> {
  return get(`/api/graph/node/${id}`)
}
export async function createGraphNode(payload: { title: string; summary?: string; category?: string; domain?: string }): Promise<GraphNode> {
  return request('/api/graph/nodes', { method: 'POST', body: JSON.stringify(payload) })
}
export async function updateGraphNode(id: number, payload: { title?: string; summary?: string; category?: string }): Promise<GraphNode> {
  return request(`/api/graph/nodes/${id}`, { method: 'PATCH', body: JSON.stringify(payload) })
}
export async function deleteGraphNode(id: number): Promise<{ ok: boolean }> {
  return request(`/api/graph/nodes/${id}`, { method: 'DELETE' })
}
export async function createGraphEdge(source_id: number, target_id: number, edge_type = 'manual', weight = 1): Promise<{ ok: boolean; id: number }> {
  return request('/api/graph/edges', { method: 'POST', body: JSON.stringify({ source_id, target_id, edge_type, weight }) })
}
export async function deleteGraphEdge(id: number): Promise<{ ok: boolean }> {
  return request(`/api/graph/edges/${id}`, { method: 'DELETE' })
}
export async function saveGraphLayout(pins: { id: number; x: number; y: number; pinned: boolean }[]): Promise<{ saved: number }> {
  return request('/api/graph/layout', { method: 'POST', body: JSON.stringify({ pins }) })
}
export async function syncGraph(source: string): Promise<Record<string, unknown>> {
  return request(`/api/graph/sync/${source}`, { method: 'POST' })
}

// ── Genesis Complete: vault + integrations ──────────────────────────
// Session token from unlock/setup, kept in memory only (never persisted).
let _vaultSession: string | null = null
export function setVaultSession(t: string | null) { _vaultSession = t }
function vaultHeaders(): Record<string, string> {
  return _vaultSession ? { 'X-Vault-Session': _vaultSession } : {}
}
function vreq(path: string, init: RequestInit = {}) {
  return request(path, { ...init, headers: { ...vaultHeaders(), ...(init.headers || {}) } })
}

export type Profile = { name: string; label: string | null; created_at: string | null }
export type VaultStatus = {
  crypto_available: boolean; setup: boolean; unlocked: boolean
  active_profile: string; secret_count: number; profiles: Profile[]; auto_lock_seconds: number
}
export type GenesisStatus = { abilities: Record<string, boolean>; active: number; total: number; pct: number; complete: boolean }
export type IntegrationField = {
  name: string; label: string; type: string; help_url?: string | null
  set: boolean; last4: string | null; test_status: string | null
}
export type IntegrationAbility = { id: string; name: string; active: boolean }
export type Integration = {
  id: string; label: string; category: 'core' | 'tools' | 'coming_soon' | 'custom'
  required: boolean; available: boolean; icon?: string | null; blurb?: string | null; coming_in?: string | null
  fields: IntegrationField[]; connected: boolean; abilities: IntegrationAbility[]
}
export type IntegrationsResponse = { integrations: Integration[]; genesis: GenesisStatus; vault: VaultStatus }
export type AuditEntry = { ts: string; action: string; integration_id: string | null; name: string | null; ok: boolean | null; detail: string | null }

export async function getVaultStatus(): Promise<VaultStatus> { return get('/api/vault/status') }
export async function vaultSetup(master: string, import_env = true) {
  const r = await request('/api/vault/setup', { method: 'POST', body: JSON.stringify({ master, import_env }) })
  setVaultSession(r.session); return r
}
export async function vaultUnlock(master: string) {
  const r = await request('/api/vault/unlock', { method: 'POST', body: JSON.stringify({ master }) })
  setVaultSession(r.session); return r
}
export async function vaultLock() { setVaultSession(null); return vreq('/api/vault/lock', { method: 'POST' }) }
export async function vaultReload() { return vreq('/api/vault/reload', { method: 'POST' }) }
export async function getVaultAudit(limit = 100): Promise<{ entries: AuditEntry[] }> { return vreq(`/api/vault/audit?limit=${limit}`) }
export async function vaultExport(password: string): Promise<{ blob: string }> {
  return vreq('/api/vault/export', { method: 'POST', body: JSON.stringify({ password }) })
}
export async function vaultImport(blob: string, password: string) {
  return vreq('/api/vault/import', { method: 'POST', body: JSON.stringify({ blob, password }) })
}
export async function getVaultProfiles(): Promise<{ profiles: Profile[]; active: string }> { return get('/api/vault/profiles') }
export async function createVaultProfile(name: string, label?: string, activate = true) {
  return vreq('/api/vault/profiles', { method: 'POST', body: JSON.stringify({ name, label, activate }) })
}

export async function getIntegrations(): Promise<IntegrationsResponse> { return get('/api/integrations') }
export async function connectIntegration(id: string, fields: Record<string, string>) {
  return vreq(`/api/integrations/${id}/connect`, { method: 'POST', body: JSON.stringify({ fields }) })
}
export async function testIntegration(id: string): Promise<{ ok: boolean; message: string; genesis: GenesisStatus }> {
  return vreq(`/api/integrations/${id}/test`, { method: 'POST' })
}
export async function revealSecret(name: string, master: string): Promise<{ value: string }> {
  return vreq('/api/integrations/reveal', { method: 'POST', body: JSON.stringify({ name, master }) })
}
export async function addCustomSecret(name: string, value: string, secret_type = 'custom') {
  return vreq('/api/integrations/custom', { method: 'POST', body: JSON.stringify({ name, value, secret_type }) })
}
export async function removeIntegration(id: string) { return vreq(`/api/integrations/${id}`, { method: 'DELETE' }) }

export async function googleOAuthUrl(): Promise<string> {
  const base = import.meta.env.VITE_API_BASE || ''
  return `${base}/api/integrations/google/oauth/start`
}
export async function googleOAuthStatus(): Promise<{ configured: boolean; connected: boolean; email: string; redirect_uri: string }> {
  return get('/api/integrations/google/status')
}
export async function googleDisconnect(): Promise<{ ok: boolean }> {
  return vreq('/api/integrations/google/disconnect', { method: 'POST' })
}

// ── MCP Hub (#5) ─────────────────────────────────────────────────────────
export type McpServerConfigRow = {
  id: number; enabled: number; transport: string; public_url: string | null
  tunnel_status: string; auth_modes_json: string; rate_limit_json: string; updated_at: string
}
export type McpSelfTool = { name: string; description: string; sensitive: boolean }
export type McpOAuth = { enabled: boolean; issuer: string | null; audience: string | null; alg: string }
export type McpTunnel = { available: boolean; running: boolean; public_url: string | null; mcp_url?: string | null }
export type McpServerInfo = {
  available: boolean; config: McpServerConfigRow; tools: McpSelfTool[]; mount: string | null
  exposed: boolean; oauth: McpOAuth; tunnel: McpTunnel
}
export type A2aSkill = { id: string; name: string; description?: string }
export type A2aCard = { name: string; description: string; version: string; url: string; skills: A2aSkill[] }
export type A2aPeer = { id: number; name: string; endpoint: string; status: string; skills: string[] }
export type McpClient = {
  id: number; name: string; auth_type: string; scopes: string[]
  status: string; created_at: string; last_seen: string | null
}
export type McpIssuedClient = { ok: boolean; id: number; name: string; scopes: string[]; token: string }
export type McpConnection = {
  id: number; name: string; transport: string; endpoint: string
  enabled: number; status: string; last_tested_at: string | null; tools_count: number
}
export type McpExternalTool = { id: number; source: string; name: string; enabled: number; permission: 'allow' | 'ask' | 'deny' }
export type McpCallLog = {
  id: number; ts: string; direction: 'in' | 'out'; peer: string | null
  tool: string | null; status: string | null; latency_ms: number | null; error: string | null
}
export type McpApproval = {
  id: number; client: string | null; tool: string | null; args: string | null
  status: string; created_at: string; decided_at: string | null
}

// Server (M1)
export async function getMcpServerConfig(): Promise<McpServerInfo> { return vreq('/api/mcp/server/config') }
export async function setMcpServerConfig(body: { enabled?: boolean; public_url?: string; rate_limit_per_minute?: number }) {
  return vreq('/api/mcp/server/config', { method: 'PUT', body: JSON.stringify(body) })
}
export async function getMcpClients(): Promise<{ clients: McpClient[] }> { return vreq('/api/mcp/clients') }
export async function issueMcpClient(name: string, scopes: string[]): Promise<McpIssuedClient> {
  return vreq('/api/mcp/clients', { method: 'POST', body: JSON.stringify({ name, scopes }) })
}
export async function setMcpClientScopes(id: number, scopes: string[]) {
  return vreq(`/api/mcp/clients/${id}`, { method: 'PATCH', body: JSON.stringify({ scopes }) })
}
export async function revokeMcpClient(id: number) { return vreq(`/api/mcp/clients/${id}`, { method: 'DELETE' }) }

// Activity + approvals (M1)
export async function getMcpLogs(limit = 100, direction?: 'in' | 'out'): Promise<{ logs: McpCallLog[] }> {
  return vreq(`/api/mcp/logs?limit=${limit}${direction ? `&direction=${direction}` : ''}`)
}
export async function getMcpApprovals(status = 'pending'): Promise<{ approvals: McpApproval[] }> {
  return vreq(`/api/mcp/approvals?status=${status}`)
}
export async function approveMcp(id: number) { return vreq(`/api/mcp/approvals/${id}/approve`, { method: 'POST' }) }
export async function rejectMcp(id: number) { return vreq(`/api/mcp/approvals/${id}/reject`, { method: 'POST' }) }

// Connections + external tools (M2)
export async function getMcpConnections(): Promise<{ connections: McpConnection[] }> { return vreq('/api/mcp/connections') }
export async function addMcpConnection(body: { name: string; transport: string; endpoint: string; token?: string }) {
  return vreq('/api/mcp/connections', { method: 'POST', body: JSON.stringify(body) })
}
export async function testMcpConnection(id: number) { return vreq(`/api/mcp/connections/${id}/test`, { method: 'POST' }) }
export async function refreshMcpConnection(id: number) { return vreq(`/api/mcp/connections/${id}/refresh`, { method: 'POST' }) }
export async function setMcpConnectionEnabled(id: number, enabled: boolean) {
  return vreq(`/api/mcp/connections/${id}`, { method: 'PATCH', body: JSON.stringify({ enabled }) })
}
export async function deleteMcpConnection(id: number) { return vreq(`/api/mcp/connections/${id}`, { method: 'DELETE' }) }
export async function mcpHealth() { return vreq('/api/mcp/connections/health', { method: 'POST' }) }
export async function getMcpTools(source?: string): Promise<{ tools: McpExternalTool[] }> {
  return vreq(`/api/mcp/tools${source ? `?source=${source}` : ''}`)
}
export async function setMcpTool(id: number, body: { enabled?: boolean; permission?: string }) {
  return vreq(`/api/mcp/tools/${id}`, { method: 'PATCH', body: JSON.stringify(body) })
}
export async function invokeMcpTool(id: number, args: Record<string, unknown>): Promise<{ ok: boolean; content?: string; error?: string; pending?: boolean; approval_id?: number; message?: string }> {
  return vreq(`/api/mcp/tools/${id}/invoke`, { method: 'POST', body: JSON.stringify({ args }) })
}

// M4 — OAuth, tunnel exposure, A2A
export async function setMcpOAuth(body: { enabled: boolean; issuer?: string; audience?: string; algorithm?: string; secret?: string }) {
  return vreq('/api/mcp/server/oauth', { method: 'PUT', body: JSON.stringify(body) })
}
export async function getMcpTunnel(): Promise<McpTunnel> { return vreq('/api/mcp/server/tunnel') }
export async function setMcpTunnel(action: 'start' | 'stop', port?: number): Promise<{ ok: boolean; public_url?: string; mcp_url?: string; error?: string; note?: string }> {
  return vreq('/api/mcp/server/tunnel', { method: 'POST', body: JSON.stringify({ action, port }) })
}
export async function getA2aCard(): Promise<{ card: A2aCard }> { return vreq('/api/mcp/a2a/card') }
export async function setA2aCard(body: { name?: string; description?: string; version?: string }): Promise<{ ok: boolean; card: A2aCard }> {
  return vreq('/api/mcp/a2a/card', { method: 'PUT', body: JSON.stringify(body) })
}
export async function getA2aPeers(): Promise<{ peers: A2aPeer[] }> { return vreq('/api/mcp/a2a/peers') }
export async function addA2aPeer(url: string) { return vreq('/api/mcp/a2a/peers', { method: 'POST', body: JSON.stringify({ url }) }) }
export async function removeA2aPeer(id: number) { return vreq(`/api/mcp/a2a/peers/${id}`, { method: 'DELETE' }) }
export async function a2aMessage(id: number, text: string): Promise<{ ok: boolean; status?: number; response?: string; error?: string }> {
  return vreq(`/api/mcp/a2a/peers/${id}/message`, { method: 'POST', body: JSON.stringify({ text }) })
}

// ── Storage & Usage (#10) ─────────────────────────────────────────────────────
export type StorageFeature = { feature: string; bytes: number; db_bytes: number; fs_bytes: number; items: number }
export type StorageOverview = {
  scanned_at: { db: string | null; fs: string | null; deps: string | null }
  total_bytes: number; data_bytes: number; system_bytes: number
  db: { size_bytes: number; total_rows: number; table_count: number }
  biggest: StorageFeature | null
  features: StorageFeature[]
  trend: { day: string; bytes: number }[]
  growth: { week_delta_bytes: number; month_delta_bytes: number; projection_30d_bytes: number }
}
export type StorageCategoryDetail = {
  feature: string
  tables: { table: string; feature: string; bytes: number; rows: number }[]
  fs_items: { name: string; bytes: number; files: number }[]
  note?: string
}
export type UsageBucket = {
  provider?: string; model?: string; surface?: string; agent?: string
  cost: number; tokens: number; prompt_tokens: number; completion_tokens: number
  requests: number; avg_latency_ms: number
}
export type UsageOverview = {
  range: string; total_cost: number; total_tokens: number; prompt_tokens: number
  completion_tokens: number; requests: number; avg_latency_ms: number
  by_provider: UsageBucket[]; by_model: UsageBucket[]; by_surface: UsageBucket[]
  by_agent: UsageBucket[]; surfaces: string[]
  by_day: ({ day: string; cost: number; tokens: number } & Record<string, number | string>)[]
}
export type UsageCall = {
  id: number; ts: string; surface: string; feature: string | null; provider: string
  model: string; agent_id: string | null; prompt_tokens: number; completion_tokens: number
  cost_est: number; latency_ms: number
}
export type UsagePlan = {
  id?: number; provider: string; plan_name: string; limit_type: 'usd' | 'tokens' | 'requests'
  limit_value: number; period: string; used?: number; pct?: number
}
export type UsageBudget = {
  monthly_cap_usd: number; alert_pct: number; spent_usd: number; pct: number
  level: 'off' | 'ok' | 'warn' | 'over'; updated_at: string | null
}
export async function getStorageOverview(): Promise<StorageOverview> { return get('/api/storage/overview') }
export async function getStorageCategory(feature: string, top = 12): Promise<StorageCategoryDetail> {
  return get(`/api/storage/category/${encodeURIComponent(feature)}?top=${top}`)
}
export async function runStorageScan(scope: 'db' | 'fs' | 'all' = 'all', forceDeps = false): Promise<{ scan: unknown; overview: StorageOverview }> {
  return request(`/api/storage/scan?scope=${scope}&force_deps=${forceDeps}`, { method: 'POST' })
}
export async function getUsageOverview(range: 'day' | 'week' | 'month' | 'all' = 'month'): Promise<UsageOverview> {
  return get(`/api/usage/overview?range=${range}`)
}
export async function getUsageCalls(opts: { limit?: number; offset?: number; q?: string; surface?: string; model?: string } = {}): Promise<{ total: number; limit: number; offset: number; calls: UsageCall[] }> {
  const p = new URLSearchParams()
  if (opts.limit) p.set('limit', String(opts.limit))
  if (opts.offset) p.set('offset', String(opts.offset))
  if (opts.q) p.set('q', opts.q)
  if (opts.surface) p.set('surface', opts.surface)
  if (opts.model) p.set('model', opts.model)
  return get(`/api/usage/calls?${p.toString()}`)
}
export async function getUsagePlans(): Promise<{ plans: UsagePlan[] }> { return get('/api/usage/plans') }
export async function setUsagePlans(plans: UsagePlan[]): Promise<{ plans: UsagePlan[] }> {
  return request('/api/usage/plans', { method: 'POST', body: JSON.stringify({ plans }) })
}
export async function getUsageBudget(): Promise<UsageBudget> { return get('/api/usage/budget') }
export async function setUsageBudget(monthly_cap_usd: number, alert_pct = 80): Promise<UsageBudget> {
  return request('/api/usage/budget', { method: 'POST', body: JSON.stringify({ monthly_cap_usd, alert_pct }) })
}

// ── Explore → News (#9) ───────────────────────────────────────────────────────
export type ExploreSource = {
  id: number; pillar: string; name: string; kind: string
  enabled: boolean; weight: number; status: string; last_scan_at: string | null
}
export type ExploreItem = {
  pillar: string; source_name: string; ext_id: string; title: string; url: string | null
  summary: string | null; tobi_take: string | null; score: number; engagement: number
  published_at: string | null; first_seen_at: string; freshness: string | null; ts: string
}
export type ExploreModel = {
  model_id: string; provider: string | null; owner: string | null
  intelligence: number | null; elo: number | null; popularity: number | null
  price_in: number | null; price_out: number | null; speed: number | null; latency: number | null
  context: number | null; released_at: string | null; composite: number; updated_at: string
}
export type ExploreConfig = {
  model_weights: { intelligence: number; elo: number; popularity: number }
  source_weights: Record<string, number>
  recency_vs_engagement: number
  keyword_include: string[]
  keyword_exclude: string[]
  interest_prompt: string
  muted_categories: string[]
  x_enabled: boolean
  x_cap_usd: number
  reddit_subs: string[]
  monthly_budget_usd: number
}
export type ExploreStatus = {
  last_scan: Record<string, string | null>
  budget: { spent_usd: number; cap_usd: number; ok: boolean }
  sources: ExploreSource[]
}

export async function getExploreStatus(): Promise<ExploreStatus> { return get('/api/explore/status') }
export async function getExploreNews(limit = 20): Promise<{ items: ExploreItem[]; sources: ExploreSource[] }> {
  return get(`/api/explore/news?limit=${limit}`)
}
export async function getExploreModels(limit = 60): Promise<{ models: ExploreModel[]; weights: ExploreConfig['model_weights'] }> {
  return get(`/api/explore/models?limit=${limit}`)
}
export async function getExploreTools(limit = 40): Promise<{ items: ExploreItem[]; sources: ExploreSource[] }> {
  return get(`/api/explore/tools?limit=${limit}`)
}
export async function getExploreSocial(limit = 40): Promise<{ items: ExploreItem[]; sources: ExploreSource[] }> {
  return get(`/api/explore/social?limit=${limit}`)
}
export async function refreshExplore(pillar: 'models' | 'tools' | 'social' | 'news' | 'all' = 'all'): Promise<{ ok: boolean; results: Record<string, unknown>; status: ExploreStatus }> {
  return request('/api/explore/refresh', { method: 'POST', body: JSON.stringify({ pillar }) })
}
export async function getExploreConfig(): Promise<{ config: ExploreConfig; sources: ExploreSource[] }> {
  return get('/api/explore/config')
}
export async function saveExploreConfig(updates: Partial<ExploreConfig>): Promise<{ ok: boolean; config: ExploreConfig; sources: ExploreSource[] }> {
  return request('/api/explore/config', { method: 'POST', body: JSON.stringify({ updates }) })
}
export async function setExploreSource(name: string, enabled: boolean, weight?: number): Promise<{ ok: boolean; sources: ExploreSource[] }> {
  return request(`/api/explore/sources/${name}`, { method: 'POST', body: JSON.stringify({ enabled, weight: weight ?? null }) })
}
export async function exploreDigest(days = 1): Promise<{ text: string }> {
  return request('/api/explore/digest', { method: 'POST', body: JSON.stringify({}) })
}

// ── Explore scout stream: real per-step refresh progress (SSE) ─────────────────
export type ScoutEvent =
  | { phase: 'pillar'; pillar: string; index: number; total: number }
  | { phase: 'start'; pillar: string; total_sources: number }
  | { phase: 'fetch'; pillar?: string; source: string; status: 'start' | 'done'; items?: number }
  | { phase: 'summarize'; pillar?: string; done: number; total: number; title?: string }
  | { phase: 'score'; pillar?: string }
  | { phase: 'done'; pillar?: string; items: number; sources: Record<string, number>; ts: string }
  | { phase: 'complete'; status: ExploreStatus }
  | { phase: 'error'; detail?: string; error?: string }

/** Stream the scout refresh; `onEvent` fires per SSE event, resolves on `complete`. */
export async function streamExploreRefresh(
  pillar: 'models' | 'tools' | 'social' | 'news' | 'all',
  onEvent: (ev: ScoutEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`/api/explore/refresh/stream?pillar=${pillar}`, {
    method: 'POST', signal,
  })
  if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`)
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    let idx: number
    // SSE frames are separated by a blank line
    while ((idx = buffer.indexOf('\n\n')) >= 0) {
      const frame = buffer.slice(0, idx)
      buffer = buffer.slice(idx + 2)
      let event = 'progress'; let data = ''
      for (const line of frame.split('\n')) {
        if (line.startsWith('event:')) event = line.slice(6).trim()
        else if (line.startsWith('data:')) data += line.slice(5).trim()
      }
      if (!data) continue
      try { onEvent({ phase: event, ...JSON.parse(data) } as ScoutEvent) } catch { /* ignore */ }
    }
  }
}

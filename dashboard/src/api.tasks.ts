import { get, request } from './apiCore'

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

import { get, request } from './apiCore'
import type { TaskItem } from './api.tasks'

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

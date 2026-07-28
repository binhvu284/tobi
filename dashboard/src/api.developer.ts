// Developer: controlled TOBI coding workflows (queue #18)
//
// Split out of api.ts (pre-#21 refactor) to shrink the barrel; every symbol is
// re-exported from './api', so existing import sites are unchanged.
import { get, request } from './apiCore'
import { vaultHeaders, vreq } from './apiVault'
// Types belong to the LLM/keys group still in the barrel; type-only import (erased at
// build time, so this creates no runtime import cycle).
import type { AvailableModel, LlmProvider } from './api'

// ── Developer: controlled TOBI coding workflows (queue #18) ──────────────────
export type DeveloperStage = {
  id: number; session_id: number; node_id: string; position: number; title: string
  status: string; attempts: number; checks_json?: string; result_json?: string
  started_at?: string | null; completed_at?: string | null
}
export type DeveloperWorkflow = {
  id: number; task_id: number; queue_id: number; title: string; plan_path: string
  target_version?: string | null; risk: string; state: string; stage: string; progress: number
  branch?: string | null; worktree?: string | null; base_sha?: string | null; head_sha?: string | null
  blocker?: string | null; error_code?: string | null; created_at: string; updated_at: string
  completed_at?: string | null; stages: DeveloperStage[]
  worker_profile_slug?: string; reviewer_profile_slug?: string
  active_worker_session_id?: number | null; current_sprint_id?: number | null
  sprint_budget_json?: string; v2_enabled?: number
  checkpoints?: DeveloperCheckpoint[]; worker_session?: DeveloperWorkerSession | null
  sprint?: DeveloperSprint | null; assessment?: { id: number; payload: DeveloperAssessment } | null
  pull_request?: {
    number?: number | null; url?: string | null; draft?: number; ci_state?: string | null
    conflict_state?: string | null; merge_state?: string | null; merged_at?: string | null
    merge_commit_sha?: string | null; updated_at?: string | null
  } | null
  owner_state?: string; readiness?: { id: number; status: string; payload: DeveloperReadiness } | null
  evidence?: Array<Record<string, unknown>>; scorecard?: { payload: DeveloperScorecard } | null
  delivery?: DeveloperDelivery
}
/** Whether this run produced a result the owner can open, and how to reach it. Keyed on the
 *  commit gate server-side -- head_sha alone is only the branch point. */
export type DeveloperDelivery = {
  reachable: boolean; kind: 'pull_request' | 'local_branch' | 'none'
  branch?: string | null; head_sha?: string | null; url?: string | null
  state?: string; draft?: boolean; merged?: boolean; merge_commit_sha?: string | null
  ci_state?: string | null; conflict_state?: string | null; updated_at?: string | null
  allowed_actions?: string[]
}
export type DeveloperChanges = {
  files: Array<{ path?: string; status?: string; insertions?: number; deletions?: number } | string>
  stat: string; head_sha?: string | null
}
export type DeveloperCheckpoint = {
  id: number; session_id: number; worker_session_id?: number | null; sequence: number
  head_sha?: string | null; status: string; handoff_json: string; created_at: string
}
export type DeveloperWorkerSession = {
  id: number; session_id: number; profile_slug: string; adapter: string; model?: string
  external_session_id?: string | null; status: string; error_code?: string | null
}
export type DeveloperSprint = {
  id: number; goal_id: number; sequence: number; title: string; objective: string
  acceptance_criteria_json: string; budget_json: string; risk: string; status: string
  checkpoint_sha?: string | null
}
export type DeveloperSprintPlan = {
  sequence: number; title: string; objective: string; acceptance_criteria: string[]
  budget: { max_files: number; max_changed_lines: number; max_subsystems: number; max_minutes: number; max_worker_steps: number }
  risk: string
}
export type DeveloperAssessment = {
  route: 'direct' | 'decompose' | 'owner_review'; risk: string; score: number
  reasons: string[]; relevant_files: string[]; sprints: DeveloperSprintPlan[]
  owner_review_required: boolean
}
export type DeveloperWorkerProfile = {
  slug: string; name: string; adapter: 'native' | 'codex' | 'opencode' | 'hermes' | 'model_review'
  model: string; auth_mode: 'inherited' | 'native_login' | 'vault_env'; credential_env: string
  reviewer_profile: string; enabled: boolean; config: Record<string, unknown>
  health_status: string; health_detail?: string | null; last_probed_at?: string | null
  runner_mode?: 'local' | 'service'
  runner?: { status: string; detail: string; nodes?: Array<Record<string, unknown>> } | null
}
export type DeveloperWorkerCatalog = {
  workers: DeveloperWorkerProfile[]
  models: AvailableModel[]
  providers: LlmProvider[]
  routing: { default_model: string; coding: string; coding_review: string }
}
export type DeveloperWorkerLogin = {
  interactive_required: boolean; command?: string[]; provider?: string; detail: string; steps?: string[]
}
export type DeveloperWorkerModels = {
  models: AvailableModel[]; source: string; detail: string
}
export type DeveloperQueueItem = {
  id: number; queue_id: number; title: string; plan_path: string; plan_hash: string
  status: string; risk: string; target_version?: string | null; queue_status?: string | null
  queue_effort?: string | null; dependencies_json: string; acceptance_criteria_json?: string
  owner_state?: string; worker_profile_slug?: string; reviewer_profile_slug?: string
  fallback_profiles_json?: string; validation_commands_json?: string
}
export type DeveloperRelease = {
  id: number; version: string; tier?: string | null; source: string; queue_item?: number | null
  commit_sha?: string | null; tag?: string | null; risk?: string | null; status: string
  notes?: string | null; created_at: string; released_at?: string | null
}
export type DeveloperOverview = {
  active_workflow: DeveloperWorkflow | null
  /** No longer sent. The array held every session in full and had no reader — it made this
   *  endpoint 5.2 MB on a 5-second poll. Run history has its own endpoint. */
  workflows?: DeveloperWorkflow[]
  summary: { states: Record<string, number>; releases: DeveloperRelease[]; deployments: unknown[] }
  policy: {
    version: number; hash: string; capabilities: Record<string, boolean>
    github_configured: boolean; deployment_configured: boolean
  }
  process?: { auto_queue: boolean }
  acceptance_mode?: boolean
}
export type DeveloperAcceptanceScenario = { id: string; label: string; description: string }
export type DeveloperAcceptanceState = {
  enabled: boolean; workflow_id?: number | null; scenarios: DeveloperAcceptanceScenario[]
  faults: Array<Record<string, unknown>>
}
export type DeveloperStorage = {
  worktree_root: string; worktree_bytes: number; worktree_count: number; git_available: boolean
  artifact_bytes: number; artifact_count: number; index_bytes: number; total_developer_bytes: number
  warning_bytes: number; blocked_new_workflows: boolean; retention_days: number
  cleanup_eligible_artifacts: number; cleanup_eligible_worktrees: number
}
export type DeveloperEvent = {
  id: number; session_id: number; sequence: number; actor: string; event_type: string
  payload: Record<string, unknown>; created_at: string
}
export type DeveloperGoal = {
  id: number; title: string; objective: string; acceptance_criteria_json: string
  validation_commands_json: string; autonomy: 'sandbox' | 'pr' | 'merge_deploy'
  preferred_models_json: string; status: string; max_iterations: number; iteration_count: number
  worker_profile_slug?: string; reviewer_profile_slug?: string; assessment_json?: string; budget_json?: string
  current_session_id?: number | null; last_error?: string | null; created_at: string; updated_at: string
  qualification_percent?: number; evidence_json?: string; gaps_json?: string
  evidence?: Array<Record<string, unknown>>; gaps?: string[]
  items?: Array<{ task_id: number; queue_id: number; title: string; status: string; owner_state?: string }>
}
export type DeveloperReadinessIssue = { code: string; message: string; field?: string | null; recoverable: boolean }
export type DeveloperReadiness = {
  readiness_id: number; queue_id: number; ready: boolean; status: 'ready' | 'blocked'
  selected_agent: string; reviewer: string; fallback_agents: string[]
  validation_commands: string[][]; blockers: DeveloperReadinessIssue[]; warnings: DeveloperReadinessIssue[]
  alternatives: Array<{ slug: string; name: string; adapter: string; model?: string; detail?: string }>
  protected_paths: string[]; policy_hash: string; plan_hash: string; assessment: DeveloperAssessment
}
export type DeveloperScorecard = {
  session_id: number; queue_id: number; state: string; stage: string; duration_seconds?: number | null
  agent: string; reviewer: string; attempts: number; retries: number; tool_failures: number
  checks: Array<Record<string, unknown>>; evidence: Array<Record<string, unknown>>; outcome: string
  error_code?: string | null; generated_at: string
}

export async function getDeveloperOverview(signal?: AbortSignal): Promise<DeveloperOverview> {
  return vreq('/api/developer/overview', { signal })
}
// Queue tab (#18 UI continuation): items + the owner's Next slot and priority order.
export type DeveloperQueueState = {
  items: DeveloperQueueItem[]; order: number[]; next_queue_id: number | null; auto_queue: boolean; queue_hash: string
}
export type DeveloperQueuePlan = { queue_id: number; plan_path: string; title: string; markdown: string }
export async function getDeveloperQueue(signal?: AbortSignal): Promise<DeveloperQueueState> {
  return vreq('/api/developer/queue', { signal })
}
export async function setDeveloperQueueOrder(order: number[], nextQueueId: number | null): Promise<DeveloperQueueState> {
  return vreq('/api/developer/queue/order', { method: 'POST', body: JSON.stringify({ order, next_queue_id: nextQueueId }) })
}
export async function restoreDeveloperQueueItem(queueId: number): Promise<DeveloperQueueState> {
  return vreq(`/api/developer/queue/${queueId}/restore`, { method: 'POST' })
}
export async function removeDeveloperQueueItem(queueId: number): Promise<DeveloperQueueState> {
  return vreq(`/api/developer/queue/${queueId}/remove`, { method: 'POST' })
}
export async function getDeveloperQueuePlan(queueId: number, signal?: AbortSignal): Promise<DeveloperQueuePlan> {
  return vreq(`/api/developer/queue/${queueId}/plan`, { signal })
}
export async function createDeveloperQueueItem(input: {
  title: string; objective: string; acceptance_criteria: string[]; dependencies?: number[]
  effort?: string; risk?: 'low' | 'medium' | 'high' | 'critical'; goal_ids?: number[]
  expected_queue_hash: string; plan_markdown?: string | null
}): Promise<{ item: DeveloperQueueItem; queue_id: number; queue_hash: string }> {
  return vreq('/api/developer/queue/items', { method: 'POST', body: JSON.stringify(input) })
}
export async function preflightDeveloperQueueItem(queueId: number, input: {
  selected_agent?: string; reviewer?: string; fallback_agents?: string[]
  validation_commands?: string[][]; protected_paths_approved?: boolean; active_probe?: boolean
} = {}): Promise<DeveloperReadiness> {
  return vreq(`/api/developer/queue/${queueId}/preflight`, { method: 'POST', body: JSON.stringify(input) })
}
export async function getDeveloperWork(signal?: AbortSignal): Promise<{
  items: DeveloperQueueItem[]; goals: DeveloperGoal[]; links: Array<Record<string, unknown>>
}> {
  return vreq('/api/developer/work', { signal })
}
export async function getDeveloperVersions(signal?: AbortSignal): Promise<{ releases: DeveloperRelease[] }> {
  return vreq('/api/developer/versions', { signal })
}
export async function getDeveloperStorage(signal?: AbortSignal): Promise<DeveloperStorage> {
  return vreq('/api/developer/storage', { signal })
}
export async function getDeveloperGoals(signal?: AbortSignal): Promise<{ goals: DeveloperGoal[]; loop: { enabled: boolean; owner: string } }> {
  return vreq('/api/developer/goals', { signal })
}
export async function assessDeveloperGoal(input: {
  title: string; objective: string; acceptance_criteria: string[]; validation_commands?: string[][]
}): Promise<DeveloperAssessment> {
  return vreq('/api/developer/goals/assess', { method: 'POST', body: JSON.stringify(input) })
}
export async function createDeveloperGoal(input: {
  title: string; objective: string; acceptance_criteria: string[]
}): Promise<DeveloperGoal> {
  return vreq('/api/developer/goals', { method: 'POST', body: JSON.stringify(input) })
}
export async function commandDeveloperGoal(
  goalId: number, command: 'evaluate' | 'archive' | 'delete' | 'cancel',
): Promise<DeveloperGoal> {
  return vreq(`/api/developer/goals/${goalId}/commands`, {
    method: 'POST', body: JSON.stringify({ command, idempotency_key: crypto.randomUUID() }),
  })
}
export async function startDeveloperWorkflow(queueId: number, readinessId?: number): Promise<DeveloperWorkflow> {
  return vreq('/api/developer/workflows', {
    method: 'POST', body: JSON.stringify({ queue_id: queueId, readiness_id: readinessId, idempotency_key: crypto.randomUUID(), start: true }),
  })
}
export async function prepareDeveloperWorkflow(queueId: number, readinessId?: number): Promise<DeveloperWorkflow> {
  return vreq('/api/developer/workflows', {
    method: 'POST', body: JSON.stringify({ queue_id: queueId, readiness_id: readinessId, idempotency_key: crypto.randomUUID(), start: false }),
  })
}
export async function getDeveloperHistory(signal?: AbortSignal): Promise<{ workflows: DeveloperWorkflow[] }> {
  return vreq('/api/developer/workflows/history', { signal })
}
export async function getDeveloperScorecard(workflowId: number): Promise<DeveloperScorecard> {
  return vreq(`/api/developer/workflows/${workflowId}/scorecard`)
}
/** The diff a finished run produced. Fetched on demand rather than embedded in the workflow,
 *  because it shells out to git and the overview listing builds every workflow at once. */
export async function getDeveloperChanges(
  workflowId: number, signal?: AbortSignal,
): Promise<DeveloperChanges> {
  return vreq(`/api/developer/workflows/${workflowId}/changes`, { signal })
}
export async function commandDeveloperWorkflow(
  workflowId: number,
  command: 'pause' | 'resume' | 'cancel' | 'retry' | 'remove' | 'sync_delivery' | 'reconcile_base',
): Promise<DeveloperWorkflow> {
  return vreq(`/api/developer/workflows/${workflowId}/commands`, {
    method: 'POST', body: JSON.stringify({ command, idempotency_key: crypto.randomUUID() }),
  })
}
export async function getDeveloperAcceptance(
  workflowId?: number, signal?: AbortSignal,
): Promise<DeveloperAcceptanceState> {
  const query = workflowId ? `?workflow_id=${workflowId}` : ''
  return vreq(`/api/developer/acceptance${query}`, { signal })
}
export async function armDeveloperAcceptanceFault(
  workflowId: number, scenario: string,
): Promise<DeveloperAcceptanceState> {
  return vreq(`/api/developer/workflows/${workflowId}/acceptance-faults`, {
    method: 'POST', body: JSON.stringify({ scenario }),
  })
}
export async function switchDeveloperWorker(workflowId: number, profileSlug: string): Promise<DeveloperWorkflow> {
  return vreq(`/api/developer/workflows/${workflowId}/switch-worker`, {
    method: 'POST', body: JSON.stringify({ profile_slug: profileSlug }),
  })
}
export async function getDeveloperWorkers(
  probe = false, signal?: AbortSignal,
): Promise<DeveloperWorkerCatalog> {
  return vreq(`/api/developer/workers?probe=${probe ? 'true' : 'false'}`, { signal })
}
export async function saveDeveloperWorker(
  slug: string,
  input: Omit<DeveloperWorkerProfile, 'slug' | 'health_status' | 'health_detail' | 'last_probed_at'>,
): Promise<DeveloperWorkerProfile> {
  return vreq(`/api/developer/workers/${encodeURIComponent(slug)}`, {
    method: 'PUT', body: JSON.stringify(input),
  })
}
export async function probeDeveloperWorker(slug: string): Promise<DeveloperWorkerProfile> {
  return vreq(`/api/developer/workers/${encodeURIComponent(slug)}/probe`, { method: 'POST' })
}
export async function getDeveloperWorkerLogin(slug: string): Promise<DeveloperWorkerLogin> {
  return vreq(`/api/developer/workers/${encodeURIComponent(slug)}/login`)
}
export async function setDeveloperProcessSettings(autoQueue: boolean): Promise<{
  auto_queue: boolean; next_workflow?: DeveloperWorkflow | null
}> {
  return vreq('/api/developer/process/settings', {
    method: 'PATCH', body: JSON.stringify({ auto_queue: autoQueue }),
  })
}
export async function getDeveloperWorkerModels(slug: string, refresh = false): Promise<DeveloperWorkerModels> {
  return vreq(`/api/developer/workers/${encodeURIComponent(slug)}/models?refresh=${refresh ? 'true' : 'false'}`)
}
export async function getDeveloperLearning(signal?: AbortSignal): Promise<{
  records: Array<Record<string, unknown>>; playbooks: Array<Record<string, unknown>>
}> {
  return vreq('/api/developer/learning', { signal })
}
export async function replayDeveloperLearning(playbookSlug?: string): Promise<{
  results: Array<{ slug: string; qualified: boolean; cases: number; passed: number; pass_rate: number }>
}> {
  return vreq('/api/developer/learning/replay', {
    method: 'POST', body: JSON.stringify({ playbook_slug: playbookSlug || null }),
  })
}
export async function approveDeveloperWorkflow(
  workflowId: number, purpose: 'special_paths' | 'merge_deploy', master: string,
): Promise<DeveloperWorkflow> {
  const reauth = await vreq('/api/developer/reauth', {
    method: 'POST', body: JSON.stringify({ workflow_id: workflowId, purpose, master }),
  })
  return vreq(`/api/developer/workflows/${workflowId}/approve`, {
    method: 'POST', body: JSON.stringify({ purpose, challenge: reauth.challenge }),
  })
}
export async function rejectDeveloperWorkflow(
  workflowId: number, purpose: 'special_paths' | 'merge_deploy',
): Promise<DeveloperWorkflow> {
  return vreq(`/api/developer/workflows/${workflowId}/reject`, {
    method: 'POST', body: JSON.stringify({ purpose }),
  })
}
export async function cleanupDeveloperStorage(master: string): Promise<{ removed_artifacts: number; removed_worktrees: number }> {
  const reauth = await vreq('/api/developer/reauth', {
    method: 'POST', body: JSON.stringify({ purpose: 'developer_cleanup', master }),
  })
  return vreq('/api/developer/storage/cleanup', {
    method: 'POST', body: JSON.stringify({ challenge: reauth.challenge }),
  })
}
export async function streamDeveloperEvents(
  workflowId: number,
  after: number,
  onEvent: (event: DeveloperEvent) => void,
  signal?: AbortSignal,
  onStatus?: (status: 'connected' | 'heartbeat') => void,
): Promise<void> {
  const res = await fetch(`/api/developer/workflows/${workflowId}/events?after=${after}`, {
    cache: 'no-cache', headers: vaultHeaders(), signal,
  })
  if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`)
  onStatus?.('connected')
  const reader = res.body.getReader(); const decoder = new TextDecoder(); let buffer = ''
  for (;;) {
    const { done, value } = await reader.read(); if (done) break
    buffer += decoder.decode(value, { stream: true })
    let idx = -1
    while ((idx = buffer.indexOf('\n\n')) >= 0) {
      const frame = buffer.slice(0, idx); buffer = buffer.slice(idx + 2)
      if (frame.trimStart().startsWith(':')) {
        onStatus?.('heartbeat')
        continue
      }
      const data = frame.split('\n').find(line => line.startsWith('data:'))?.slice(5).trim()
      if (data) { try { onEvent(JSON.parse(data) as DeveloperEvent) } catch { /* ignore */ } }
    }
  }
}

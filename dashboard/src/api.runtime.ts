import { get, request } from './apiCore'
import { vreq } from './apiVault'

export type RuntimeRunSummary = {
  run_id: string
  request_id: string
  session_id: string
  surface: string
  mode: string
  status: string
  version: number
  contract_version: string
  legacy_run_id: string | null
  created_at: string
  updated_at: string
  completed_at: string | null
  label: string
}

export type RuntimeRolloutDecision = {
  stage: string
  allowed: boolean
  consecutive_passes: number
  required_passes: number
  blockers: string[]
}

export type RuntimeRolloutStatus = {
  stage: string
  rollback: boolean
  decisions: Record<string, RuntimeRolloutDecision>
}

export type RuntimeEvent = {
  event_id: string
  sequence: number
  event_type: string
  stage: string
  actor: string
  timestamp: string
  trace_id: string
  payload: Record<string, string | number | boolean>
}

export type RuntimeTraceSpan = Omit<RuntimeEvent, 'trace_id' | 'payload'> & {
  references: Array<{ kind: string; ref: string }>
}

export type RuntimeTrace = {
  trace_id: string
  run_id: string
  surface: string
  status: string
  spans: RuntimeTraceSpan[]
  context_refs: string[]
  model_refs: string[]
  tool_refs: string[]
  policy_decision_refs: string[]
  approval_refs: string[]
  receipt_refs: string[]
  recovery_refs: string[]
  outcome_refs: string[]
  usage: Record<string, number>
}

export type RuntimeEvaluation = {
  eval_run_id: string
  eval_case_id: string
  eval_case_version: string
  category: string
  status: string
  threshold: number | null
  score: number | null
  trace_id: string | null
  evidence_refs: string[]
  started_at: string | null
  completed_at: string | null
}

export type RuntimeLoop = {
  recipe_id: string
  recipe_version: string
  loop_type: string
  enabled: boolean
  iteration: number
  status: string
  stop_reason: string | null
  usage: Record<string, number>
}

export type RuntimeRunDetail = {
  run: RuntimeRunSummary
  loop: RuntimeLoop | null
  steps: Array<Record<string, string | number | null>>
  events: RuntimeEvent[]
  last_sequence: number
  trace: RuntimeTrace
  evaluations: RuntimeEvaluation[]
  recovery: Array<Pick<RuntimeEvent, 'event_id' | 'sequence' | 'event_type' | 'stage' | 'timestamp'>>
  context_refs: string[]
  capabilities: Array<{
    entity_id: string
    entity_type: string
    canonical_key: string
    name: string
    status: string
    version: string
    source_ref: string
    observed_at: string
  }>
}

export type RuntimeLoopRecipe = {
  recipe_id: string
  version: string
  name: string
  loop_type: string
  created_at: string
}

export type RuntimeLoopSelection = { recipe_id: string; version: string }

export type RuntimeLoops = {
  items: RuntimeLoopRecipe[]
  developer_selection: RuntimeLoopSelection | null
}

export type RuntimeEvalOverview = {
  metrics: {
    ecr: { overall: number; categories: Record<string, number>; case_count: number; source: string }
    ldr: { value: number | null; status: string; formula: string; unguarded_decision_share: number | null; quality_loss: number | null; missing: string[] }
  }
  freshness: { latest_suite_at: string | null; latest_suite_id: string | null }
  lanes: Record<string, { status: string; case_count: number; passed: number; completion_rate: number | null }>
  categories: Array<{ category: string; case_count: number; passed: number; pass_rate: number | null }>
  workflows: Array<{ workflow_id: string; case_count: number; passed: number; pass_rate: number | null }>
  gates: Record<string, { scope: string; allowed: boolean; required_cases: string[]; passed_cases: string[]; blockers: string[] }>
  regressions: Array<{ case_ref: string; latest_eval_run_id: string; status: string }>
  findings: Array<{ finding_id: string; eval_run_id: string; category: string; severity: string; summary: string; remediation_owner: string; status: string; evidence_refs: string[] }>
  suites: Array<{ suite_run_id: string; trigger: string; lane: string; status: string; case_count: number; capability_refs: string[]; started_at: string; completed_at: string }>
  cases: Array<{ eval_case_id: string; version: string; category: string; workflow_id: string; status: string; score: number | null; threshold: number; completed_at: string | null; release_gate: boolean; autonomy_gate: boolean }>
  acceptance: { status: string; release_ready: boolean; case_count: number; holdout_count: number; holdout_passed: number; model_calls: number; approved_model_call_ceiling: number; cost_usd: number; duration_seconds: number } | null
  next_action: string
}

export type RuntimeEvalCaseDetail = {
  case: { eval_case_id: string; version: string; category: string; workflow_id?: string; objective: string; scorer: string; threshold: number; required_evidence: string[]; release_gate: boolean; autonomy_gate: boolean; created_at: string }
  control: { capability_refs: string[]; freshness_seconds: number; sample_eligible: boolean; created_at: string } | null
  runs: Array<{ eval_run_id: string; lane?: string; status: string; score: number | null; threshold: number; run_id: string | null; trace_id: string | null; completed_at: string | null; evidence_refs: string[] }>
  findings: RuntimeEvalOverview['findings']
}

export async function getRuntimeRuns(params: {
  limit?: number
  cursor?: string | null
  surface?: string
  status?: string
} = {}): Promise<{ items: RuntimeRunSummary[]; next_cursor: string | null }> {
  const query = new URLSearchParams()
  query.set('limit', String(params.limit ?? 50))
  if (params.cursor) query.set('cursor', params.cursor)
  if (params.surface) query.set('surface', params.surface)
  if (params.status) query.set('status', params.status)
  return get(`/api/runtime/runs?${query}`)
}

export async function getRuntimeRollout(): Promise<RuntimeRolloutStatus> {
  return get('/api/runtime/rollout')
}

export async function getRuntimeRun(runId: string, after = 0): Promise<RuntimeRunDetail> {
  return get(`/api/runtime/runs/${encodeURIComponent(runId)}/snapshot?after=${after}`)
}

export async function getRuntimeLoops(): Promise<RuntimeLoops> {
  return get('/api/runtime/loops')
}

export async function getRuntimeEvals(signal?: AbortSignal): Promise<RuntimeEvalOverview> {
  return vreq('/api/runtime/evals', { signal })
}

export async function getRuntimeEvalCase(evalCaseId: string, version: string, signal?: AbortSignal): Promise<RuntimeEvalCaseDetail> {
  return vreq(`/api/runtime/evals/cases/${encodeURIComponent(evalCaseId)}?version=${encodeURIComponent(version)}`, { signal })
}

export async function setDeveloperLoop(selection: RuntimeLoopSelection): Promise<RuntimeLoopSelection> {
  return request('/api/runtime/preferences/developer-loop', {
    method: 'PUT',
    body: JSON.stringify(selection),
  })
}

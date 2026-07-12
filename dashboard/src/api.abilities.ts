import { get, request } from './apiCore'

export async function getHealth(): Promise<HealthReport> {
  return get('/api/health')
}
export async function runDeepTest(): Promise<DeepTestReport> {
  return get('/api/health/deep')
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

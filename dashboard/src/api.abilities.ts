import { get, request } from './apiCore'

export async function getHealth(): Promise<HealthReport> {
  return get('/api/health')
}
export async function runDeepTest(): Promise<DeepTestReport> {
  return get('/api/health/deep')
}

/** The same checks, delivered one at a time as each finishes.
 *
 *  The checks run concurrently now, so the whole run costs its slowest one — about eighteen
 *  seconds for the chat round-trip. Telegram and Tavily answer in roughly one, and there is no
 *  reason to hide them for the other seventeen. `onCheck` fires per result; the promise settles
 *  when every check is in. */
export async function runDeepTestStream(
  onCheck: (name: string, result: LivenessCheck) => void,
  signal?: AbortSignal,
): Promise<{ ok: number; total: number } | null> {
  const response = await fetch('/api/health/deep/stream', { signal })
  if (!response.ok || !response.body) throw new Error(`Health check failed (HTTP ${response.status})`)

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let summary: { ok: number; total: number } | null = null

  // Server-sent events are separated by a blank line, and a chunk can split one in half, so
  // only whole events are parsed and the remainder is carried to the next read.
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const events = buffer.split('\n\n')
    buffer = events.pop() ?? ''
    for (const raw of events) {
      const line = raw.split('\n').find(l => l.startsWith('data:'))
      if (!line) continue
      const payload = JSON.parse(line.slice(5))
      if (payload.name) onCheck(payload.name, payload.result)
      else if (payload.summary) summary = payload.summary
    }
  }
  return summary
}

// ── Infrastructure self-check (#21) ───────────────────────────

/** One read-only check of the running server: which database, whether it can reach the
 *  internet, whether the canonical tables are there. `hint` is only set when it failed, and is
 *  the next thing the owner should do about it. */
export type WiringCheck = {
  id: string
  label: string
  ok: boolean
  detail: string
  hint?: string
  duration_ms?: number
}

/** One acceptance suite, run in its own throwaway database. `checks` is how many individual
 *  proofs ran inside it; `retried` means the first run failed and the second passed, which is a
 *  timing flake rather than a defect — shown, never hidden. */
export type SuiteResult = {
  id: string
  label: string
  package: string
  proves: string
  ok: boolean
  checks: number
  failed?: number
  detail: string
  retried?: boolean
  duration_ms?: number
}

export type InfraSummary = {
  ok: number
  total: number
  checks: number
  failed_ids: string[]
  flaky_ids: string[]
}

export type InfraReport = {
  timestamp: string
  wiring: WiringCheck[]
  suites: SuiteResult[]
  summary?: InfraSummary
}

/** Run the whole #21 infrastructure sweep, delivering each row as it lands.
 *
 *  The wiring checks answer in under a second; the suites take about a minute in total because
 *  they run one at a time on purpose (several start real worker processes, and running them
 *  together is what made one lose a race it should have won). `onStart` gives the page the full
 *  list up front so it can show every row as pending rather than growing a list from nothing. */
export async function runInfrastructureCheckStream(
  handlers: {
    onStart?: (plan: { wiring: { id: string; label: string }[]; suites: { id: string; label: string; package: string; proves: string }[] }) => void
    onWiring?: (row: WiringCheck) => void
    onSuite?: (row: SuiteResult) => void
  },
  signal?: AbortSignal,
): Promise<InfraSummary | null> {
  const response = await fetch('/api/health/infrastructure/stream', { signal })
  if (!response.ok || !response.body) throw new Error(`Infrastructure check failed (HTTP ${response.status})`)

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let summary: InfraSummary | null = null

  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const events = buffer.split('\n\n')
    buffer = events.pop() ?? ''
    for (const raw of events) {
      const lines = raw.split('\n')
      const event = lines.find(l => l.startsWith('event:'))?.slice(6).trim()
      const data = lines.find(l => l.startsWith('data:'))
      if (!event || !data) continue
      const payload = JSON.parse(data.slice(5))
      if (event === 'start') handlers.onStart?.(payload)
      else if (event === 'wiring') handlers.onWiring?.(payload as WiringCheck)
      else if (event === 'suite') handlers.onSuite?.(payload as SuiteResult)
      else if (event === 'done') summary = payload.summary as InfraSummary
    }
  }
  return summary
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
  // Not a one-shot model ping any more: a real short conversation that uses a tool. `state`
  // separates "the model could not be reached" from "the model answered and Chat still could
  // not finish" — the second is what a one-shot probe could never see. See
  // core/chat_self_check.py.
  llm: LivenessCheck & {
    provider?: string
    state?: 'working' | 'broken' | 'model_unavailable'
    tools_used?: string[]
    model_turns?: number
  }
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
export type AbilityStatus = 'active' | 'partial' | 'setup_needed' | 'inactive'

export type AbilitySetupAction = { label: string; route: string }

export type TierAbility = {
  id: string
  name: string
  description: string
  how_to_unlock?: string | null
  effort?: string
  status: AbilityStatus
  just_activated: boolean
  // Rich fields present on Tier 1 (Awakening) abilities (#17)
  category?: string
  category_label?: string
  short_name?: string
  evidence?: string[]
  missing?: string[]
  setup_actions?: AbilitySetupAction[]
  risk?: 'low' | 'medium' | 'high'
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
  pillar_labels?: Partial<Record<'understand' | 'control' | 'presence', string>>
  active_count: number
  total_count: number
  progress_pct: number
  complete: boolean
}

// ── Awakening (#17): Tier 1 evidence report ─────────────────────────────────────
export type AwakeningAbility = TierAbility & {
  category: string
  category_label: string
  short_name: string
  evidence: string[]
  missing: string[]
  setup_actions: AbilitySetupAction[]
  status: AbilityStatus
}

export type AwakeningReport = {
  tier: number
  tier_name: string
  categories: { key: string; label: string }[]
  abilities: AwakeningAbility[]
  active_count: number
  total: number
  progress_pct: number
  complete: boolean
  sensitive_pending_review: number
  timestamp: string
}

export async function getAwakening(): Promise<AwakeningReport> {
  return get('/api/awakening')
}

export type EvolutionReport = {
  tiers: TierData[]
  version: string
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

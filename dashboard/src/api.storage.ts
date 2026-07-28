// Storage & Usage (#10)
//
// Split out of api.ts (pre-#21 refactor) to shrink the barrel; every symbol is
// re-exported from './api', so existing import sites are unchanged.
import { get, request } from './apiCore'

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
  provider?: string; model?: string; surface?: string; agent?: string; purpose?: string
  cost: number; tokens: number; prompt_tokens: number; completion_tokens: number
  requests: number; avg_latency_ms: number
}
export type UsageMetric = 'tokens' | 'requests' | 'cost' | 'latency'
export type UsageWorkload = {
  workload: string; model_calls: number | null; sessions?: number
  tokens: number | null; cost: number | null; usage_reported: boolean
}
export type DeveloperUsageAgent = {
  agent: string; profile_slug: string; adapter: string; model: string
  sessions: number; completed: number; failed: number; usage_reported: boolean
}
export type UsageOverview = {
  range: string; metric: UsageMetric; total_cost: number; total_tokens: number; prompt_tokens: number
  completion_tokens: number; requests: number; avg_latency_ms: number
  by_provider: UsageBucket[]; by_model: UsageBucket[]; by_surface: UsageBucket[]
  by_agent: UsageBucket[]; by_purpose: UsageBucket[]; surfaces: string[]
  by_day: ({ day: string; cost: number; tokens: number } & Record<string, number | string>)[]
  attempts: number; failed_attempts: number; fallback_calls: number; calls_per_turn: number | null
  coverage: {
    attributed_calls: number; total_model_calls: number; attribution_pct: number
    developer_sessions: number; developer_usage_reported: number
  }
  workloads: UsageWorkload[]
  developer_agents: DeveloperUsageAgent[]
  developer_sessions: { total: number; completed: number; failed: number; usage_reported: number }
}
export type UsageCall = {
  id: number; ts: string; surface: string; feature: string | null; provider: string
  model: string; requested_model: string | null; actual_model: string | null
  turn_id: string | null; run_id: string | null; worker_session_id: number | null
  agent_id: string | null; purpose: string | null; source: string; is_background: number
  attempt: number; status: string; error_code: string | null; fallback_reason: string | null
  prompt_tokens: number; completion_tokens: number; cost_est: number; latency_ms: number
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
export async function getUsageOverview(range: 'day' | 'week' | 'month' | 'all' = 'month', metric: UsageMetric = 'tokens'): Promise<UsageOverview> {
  return get(`/api/usage/overview?range=${range}&metric=${metric}`)
}
export async function getUsageCalls(opts: { limit?: number; offset?: number; q?: string; surface?: string; model?: string; status?: string; source?: string; purpose?: string } = {}): Promise<{ total: number; limit: number; offset: number; calls: UsageCall[] }> {
  const p = new URLSearchParams()
  if (opts.limit) p.set('limit', String(opts.limit))
  if (opts.offset) p.set('offset', String(opts.offset))
  if (opts.q) p.set('q', opts.q)
  if (opts.surface) p.set('surface', opts.surface)
  if (opts.model) p.set('model', opts.model)
  if (opts.status) p.set('status', opts.status)
  if (opts.source) p.set('source', opts.source)
  if (opts.purpose) p.set('purpose', opts.purpose)
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

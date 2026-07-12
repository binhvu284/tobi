import { get, request } from './apiCore'

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

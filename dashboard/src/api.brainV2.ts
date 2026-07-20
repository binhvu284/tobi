import { get, request } from './apiCore'

// ── Brain Memory V2 (#20 T09) — /api/brain/v2/* client ───────────────────────
export type V2Evidence = {
  id: number; excerpt: string; source_ref: string | null; trust: string; redacted: boolean
}
export type V2Memory = {
  id: number
  distilled_text: string
  memory_type: string
  behavior_implication: string
  tags: string[]
  scope_type: string
  scope_key: string | null
  authority: 'soft' | 'hard'
  explicitness: 'explicit' | 'inferred'
  confidence: number
  quality_score: number
  trust: 'trusted' | 'untrusted'
  sensitive: boolean
  status: string
  redacted: boolean
  compat_ref: number | null
  evidence: V2Evidence[]
  created_at: string
  updated_at: string
}
export type V2Stats = {
  by_status: Record<string, number>
  by_type: Record<string, number>
  conflicted: number
  sensitive: number
  aging_pending: number
  vault_unlocked: boolean
}
export type V2JobStatus = {
  id: number; filename: string; status: string
  total_chunks: number; next_chunk: number; progress: number
  running?: boolean                                   // a background worker is driving the dry-run (#20)
  candidates_by_outcome: Record<string, number>
  extraction_errors: number; error: string | null
  applied?: number; skipped?: number
}
export type V2Candidate = {
  id: number; chunk_index: number
  candidate: Record<string, unknown> | null
  sensitive: boolean
  proposed_outcome: string | null; proposed_status: string | null
  matched_id: number | null
  approved: boolean | null
  applied_memory_id: number | null
  error: string | null
}
export type V2MigrationStatus = {
  id: number; status: string; total_legacy: number; scanned: number
  next_legacy_id: number; groups: Record<string, number>
  applied: number; errors: number
  snapshot: { legacy_by_status: Record<string, number>; legacy_by_category: Record<string, number>; v2_rows: number } | null
  applied_now?: number; remaining_approved?: number
}
export type V2MigrationItem = {
  id: number; legacy_id: number; group: string | null
  candidate: Record<string, unknown> | null
  sensitive: boolean
  proposed_outcome: string | null; proposed_status: string | null
  matched_legacy_id: number | null
  approved: boolean | null
  applied_memory_id: number | null
  error: string | null
}
export type V2RecallItem = {
  memory_id: number; text: string; behavior_implication: string
  type: string; authority: string; scope: string
  hedged: boolean; precedence: number; score: number
  signals: Record<string, number>
  chip: {
    memory_id: number; text: string; type: string; scope: string
    confidence: number; quality: number; hedged: boolean; evidence: string
  }
}
export type V2Influence = { surface: string; turn_ref: string | null; query_hint: string; at: string }
export type V2CleanupProposal = {
  action: 'merge' | 'archive' | 'revalidate'
  memory_id?: number; keep_id?: number; merge_id?: number
  reason: string
}

export async function v2Stats(): Promise<V2Stats> { return get('/api/brain/v2/stats') }
export async function v2Profile(): Promise<{ profile: string; version: string; token_budget: number }> {
  return get('/api/brain/v2/profile')
}
export async function v2Memories(f: { status?: string; memory_type?: string; limit?: number } = {}): Promise<V2Memory[]> {
  const p = new URLSearchParams()
  if (f.status) p.set('status', f.status)
  if (f.memory_type) p.set('memory_type', f.memory_type)
  if (f.limit) p.set('limit', String(f.limit))
  const q = p.toString()
  return get(`/api/brain/v2/memories${q ? `?${q}` : ''}`)
}
export async function v2Remember(content: string, category?: string):
  Promise<{ ok: boolean; action?: string; v2?: { id?: number | null; outcome?: string; status?: string | null; skipped?: string } }> {
  return request('/api/brain/v2/remember', { method: 'POST', body: JSON.stringify({ content, category }) })
}
export async function v2Memory(id: number): Promise<V2Memory> { return get(`/api/brain/v2/memories/${id}`) }
export async function v2SetStatus(id: number, status: string): Promise<V2Memory> {
  return request(`/api/brain/v2/memories/${id}/status`, { method: 'POST', body: JSON.stringify({ status }) })
}
export async function v2EditMemory(id: number, patch: { distilled_text?: string; memory_type?: string; behavior_implication?: string }): Promise<V2Memory> {
  return request(`/api/brain/v2/memories/${id}/edit`, { method: 'POST', body: JSON.stringify(patch) })
}
export async function v2Feedback(id: number, verdict: 'useful' | 'irrelevant' | 'wrong', turn_ref?: string):
  Promise<{ ok: boolean; usefulness: number }> {
  return request(`/api/brain/v2/memories/${id}/feedback`,
    { method: 'POST', body: JSON.stringify({ verdict, turn_ref }) })
}
export async function v2Influence(id: number): Promise<V2Influence[]> {
  return get(`/api/brain/v2/memories/${id}/influence`)
}
export async function v2Purge(id: number): Promise<{ ok: boolean }> {
  // permanent, irreversible — the backend requires explicit confirmation (#20 P1)
  return request(`/api/brain/v2/memories/${id}/purge?confirm=true`, { method: 'DELETE' })
}
export async function v2Recall(query: string, mode: 'chat' | 'agent' = 'chat'): Promise<V2RecallItem[]> {
  return request('/api/brain/v2/recall', { method: 'POST', body: JSON.stringify({ query, mode }) })
}

export async function v2ImportCreate(filename: string, content: string): Promise<V2JobStatus> {
  return request('/api/brain/v2/import-jobs', { method: 'POST', body: JSON.stringify({ filename, content }) })
}
export async function v2ImportStatus(jobId: number): Promise<V2JobStatus> {
  return get(`/api/brain/v2/import-jobs/${jobId}`)
}
export async function v2ImportCandidates(jobId: number): Promise<V2Candidate[]> {
  return get(`/api/brain/v2/import-jobs/${jobId}/candidates`)
}
export async function v2ImportCommand(jobId: number, command: 'run' | 'step' | 'resume' | 'cancel' | 'retry' | 'commit'):
  Promise<V2JobStatus> {
  return request(`/api/brain/v2/import-jobs/${jobId}/commands`, { method: 'POST', body: JSON.stringify({ command }) })
}
export async function v2ImportDecide(jobId: number, approve: boolean,
  payload: { ids?: number[]; outcome?: string }): Promise<{ ok: boolean; decided: number }> {
  return request(`/api/brain/v2/import-jobs/${jobId}/candidates/${approve ? 'approve' : 'reject'}`,
    { method: 'POST', body: JSON.stringify(payload) })
}

export async function v2MigrationCreate(): Promise<V2MigrationStatus> {
  return request('/api/brain/v2/migration/runs', { method: 'POST' })
}
export async function v2MigrationStatus(runId: number): Promise<V2MigrationStatus> {
  return get(`/api/brain/v2/migration/runs/${runId}`)
}
export async function v2MigrationItems(runId: number, group?: string): Promise<V2MigrationItem[]> {
  return get(`/api/brain/v2/migration/runs/${runId}/items${group ? `?group=${encodeURIComponent(group)}` : ''}`)
}
export async function v2MigrationCommand(runId: number, command: 'run' | 'resume' | 'apply' | 'cancel'):
  Promise<V2MigrationStatus> {
  return request(`/api/brain/v2/migration/runs/${runId}/commands`, { method: 'POST', body: JSON.stringify({ command }) })
}
export async function v2MigrationDecide(runId: number, approve: boolean,
  payload: { ids?: number[]; group?: string }): Promise<{ ok: boolean; decided: number }> {
  return request(`/api/brain/v2/migration/runs/${runId}/items/${approve ? 'approve' : 'reject'}`,
    { method: 'POST', body: JSON.stringify(payload) })
}

export async function v2CleanupPreview(): Promise<{ proposals: V2CleanupProposal[] }> {
  return request('/api/brain/v2/cleanup/preview', { method: 'POST' })
}
export async function v2CleanupApply(actions: V2CleanupProposal[]): Promise<{ ok: boolean; applied: number }> {
  return request('/api/brain/v2/cleanup/apply', { method: 'POST', body: JSON.stringify({ actions }) })
}

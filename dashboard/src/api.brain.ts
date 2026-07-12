import { get, request } from './apiCore'

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

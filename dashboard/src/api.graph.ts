// Graph View
//
// Split out of api.ts (pre-#21 refactor) to shrink the barrel; every symbol is
// re-exported from './api', so existing import sites are unchanged.
import { get, request } from './apiCore'

// ── Graph View ────────────────────────────────────────────────────────────────
export interface GraphNode {
  id: number
  domain: string
  ref_kind?: string | null
  ref_id?: string | null
  title: string
  summary?: string | null
  category?: string | null
  color?: string | null
  icon?: string | null
  source_url?: string | null
  degree: number
  community?: number | null
  community_label?: string | null
  x?: number | null
  y?: number | null
  pinned?: number
  has_embedding?: boolean
}
export interface GraphCommunity { cid: number; label: string; color: string; count: number }
export interface GraphEdge {
  id: number
  source: number
  target: number
  type: 'ref' | 'semantic' | 'tag' | 'manual'
  weight: number
  directed?: number
  created_by?: string
}
export interface GraphData { nodes: GraphNode[]; edges: GraphEdge[] }
export interface GraphSource {
  source: string; domain: string; available: boolean; nodes: number
  last_synced_at?: string | null; item_count?: number
}
export interface GraphSearchResult { id: number; title: string; domain: string; score: number }
export interface TimelineEvent { id: number; domain: string; ts: string }
export interface GraphFilters {
  domain?: string; category?: string; q?: string
  min_weight?: number; date_from?: string; date_to?: string
}

function graphQuery(f: GraphFilters = {}): string {
  const p = new URLSearchParams()
  if (f.domain && f.domain !== 'all') p.set('domain', f.domain)
  if (f.category) p.set('category', f.category)
  if (f.q) p.set('q', f.q)
  if (f.min_weight) p.set('min_weight', String(f.min_weight))
  if (f.date_from) p.set('date_from', f.date_from)
  if (f.date_to) p.set('date_to', f.date_to)
  const s = p.toString()
  return s ? `?${s}` : ''
}

export async function getGraph(f: GraphFilters = {}): Promise<GraphData> { return get(`/api/graph${graphQuery(f)}`) }
export async function getGraphSources(): Promise<{ sources: GraphSource[] }> { return get('/api/graph/sources') }
export async function getGraphCommunities(): Promise<{ communities: GraphCommunity[] }> { return get('/api/graph/communities') }
export async function getGraphPath(a: number, b: number): Promise<{ path: GraphNode[] }> { return get(`/api/graph/path?a=${a}&b=${b}`) }
export async function graphRetrieve(query: string, k = 8, hops = 1): Promise<{ results: GraphNode[] }> {
  return request('/api/graph/retrieve', { method: 'POST', body: JSON.stringify({ query, k, hops }) })
}
export async function getGraphTimeline(): Promise<{ events: TimelineEvent[] }> { return get('/api/graph/timeline') }
export async function searchGraph(q: string, k = 12): Promise<{ results: GraphSearchResult[]; mode: string }> {
  return get(`/api/graph/search?q=${encodeURIComponent(q)}&k=${k}`)
}
export async function getGraphNode(id: number): Promise<GraphNode & { connections: GraphData }> {
  return get(`/api/graph/node/${id}`)
}
export async function createGraphNode(payload: { title: string; summary?: string; category?: string; domain?: string }): Promise<GraphNode> {
  return request('/api/graph/nodes', { method: 'POST', body: JSON.stringify(payload) })
}
export async function updateGraphNode(id: number, payload: { title?: string; summary?: string; category?: string }): Promise<GraphNode> {
  return request(`/api/graph/nodes/${id}`, { method: 'PATCH', body: JSON.stringify(payload) })
}
export async function deleteGraphNode(id: number): Promise<{ ok: boolean }> {
  return request(`/api/graph/nodes/${id}`, { method: 'DELETE' })
}
export async function createGraphEdge(source_id: number, target_id: number, edge_type = 'manual', weight = 1): Promise<{ ok: boolean; id: number }> {
  return request('/api/graph/edges', { method: 'POST', body: JSON.stringify({ source_id, target_id, edge_type, weight }) })
}
export async function deleteGraphEdge(id: number): Promise<{ ok: boolean }> {
  return request(`/api/graph/edges/${id}`, { method: 'DELETE' })
}
export async function saveGraphLayout(pins: { id: number; x: number; y: number; pinned: boolean }[]): Promise<{ saved: number }> {
  return request('/api/graph/layout', { method: 'POST', body: JSON.stringify({ pins }) })
}
export async function syncGraph(source: string): Promise<Record<string, unknown>> {
  return request(`/api/graph/sync/${source}`, { method: 'POST' })
}

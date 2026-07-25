// Explore -> News (#9), News V2 (#23), and the scout SSE stream
//
// Split out of api.ts (pre-#21 refactor) to shrink the barrel; every symbol is
// re-exported from './api', so existing import sites are unchanged.
import { get, request } from './apiCore'

// ── Explore → News (#9) ───────────────────────────────────────────────────────
export type ExploreSource = {
  id: number; pillar: string; name: string; kind: string
  enabled: boolean; weight: number; status: string; last_scan_at: string | null
}
export type ExploreItem = {
  pillar: string; source_name: string; ext_id: string; title: string; url: string | null
  summary: string | null; tobi_take: string | null; score: number; engagement: number
  published_at: string | null; first_seen_at: string; freshness: string | null; ts: string
}
export type ExploreModel = {
  model_id: string; provider: string | null; owner: string | null
  intelligence: number | null; elo: number | null; popularity: number | null
  price_in: number | null; price_out: number | null; speed: number | null; latency: number | null
  context: number | null; released_at: string | null; composite: number; updated_at: string
}
export type ExploreConfig = {
  model_weights: { intelligence: number; elo: number; popularity: number }
  source_weights: Record<string, number>
  recency_vs_engagement: number
  keyword_include: string[]
  keyword_exclude: string[]
  interest_prompt: string
  muted_categories: string[]
  x_enabled: boolean
  x_cap_usd: number
  reddit_subs: string[]
  monthly_budget_usd: number
}
export type ExploreStatus = {
  last_scan: Record<string, string | null>
  budget: { spent_usd: number; cap_usd: number; ok: boolean }
  sources: ExploreSource[]
}

export async function getExploreStatus(): Promise<ExploreStatus> { return get('/api/explore/status') }
export async function getExploreNews(limit = 20): Promise<{ items: ExploreItem[]; sources: ExploreSource[] }> {
  return get(`/api/explore/news?limit=${limit}`)
}
export async function getExploreModels(limit = 60): Promise<{ models: ExploreModel[]; weights: ExploreConfig['model_weights'] }> {
  return get(`/api/explore/models?limit=${limit}`)
}
export async function getExploreTools(limit = 40): Promise<{ items: ExploreItem[]; sources: ExploreSource[] }> {
  return get(`/api/explore/tools?limit=${limit}`)
}
export async function getExploreSocial(limit = 40): Promise<{ items: ExploreItem[]; sources: ExploreSource[] }> {
  return get(`/api/explore/social?limit=${limit}`)
}
export async function refreshExplore(pillar: 'models' | 'tools' | 'social' | 'news' | 'all' = 'all'): Promise<{ ok: boolean; results: Record<string, unknown>; status: ExploreStatus }> {
  return request('/api/explore/refresh', { method: 'POST', body: JSON.stringify({ pillar }) })
}
export async function getExploreConfig(): Promise<{ config: ExploreConfig; sources: ExploreSource[] }> {
  return get('/api/explore/config')
}
export async function saveExploreConfig(updates: Partial<ExploreConfig>): Promise<{ ok: boolean; config: ExploreConfig; sources: ExploreSource[] }> {
  return request('/api/explore/config', { method: 'POST', body: JSON.stringify({ updates }) })
}
export async function setExploreSource(name: string, enabled: boolean, weight?: number): Promise<{ ok: boolean; sources: ExploreSource[] }> {
  return request(`/api/explore/sources/${name}`, { method: 'POST', body: JSON.stringify({ enabled, weight: weight ?? null }) })
}
export async function exploreDigest(days = 1): Promise<{ text: string }> {
  return request('/api/explore/digest', { method: 'POST', body: JSON.stringify({}) })
}

// ── News V2 (#23): /api/explore/v2 — flag-gated; V1 above stays for rollback ────
export type NewsV2Config = { enabled: boolean; shadow: boolean }
export type NewsV2RankEntry = {
  model_id: string; score: number; components: Record<string, number>
  families: number; sources: string[]; formula_version: string
}
export type NewsV2Release = {
  id: number; model_id: string | null; title: string; source_url: string
  released_at: string | null; observed_at: string
}
export type NewsV2ReleaseNews = {
  item_id: number; title: string; url: string; source: string | null
  excerpt: string | null; recap: string | null; media_key: string | null
  published_at: string | null; first_seen_at: string | null
  interaction?: NewsV2Interaction
}
export type NewsV2SourceHealth = {
  state: string; sources: Record<string, { state?: string; error?: string }>; updated_at: string
} | null
export type NewsV2Home = {
  top: NewsV2RankEntry[]; snapshot_id: number | null; releases: NewsV2Release[]
  release_news: NewsV2ReleaseNews[]
  source_health: Record<string, NewsV2SourceHealth>; freshness: Record<string, string>
}
export type NewsV2ModelMetric = {
  category: string; source: string; metric: string; value: number
  confidence: number; observed_at: string; formula_version: string
}
export type NewsV2Models = {
  models: { model_id: string; metrics: NewsV2ModelMetric[] }[]; next_cursor: string | null
}
export type NewsV2RefreshJob = {
  id: number; tab: string; state: string; error: string | null
  checkpoints: Record<string, { state?: string; error?: string; reason?: string }>
  metrics: Record<string, number>; updated_at: string
}
export async function getNewsV2Config(): Promise<NewsV2Config> { return get('/api/explore/v2/config') }
export async function getNewsV2Home(): Promise<NewsV2Home> { return get('/api/explore/v2/home') }
export async function getNewsV2Models(params: { q?: string; category?: string; cursor?: string; limit?: number } = {}): Promise<NewsV2Models> {
  const qs = new URLSearchParams()
  if (params.q) qs.set('q', params.q)
  if (params.category) qs.set('category', params.category)
  if (params.cursor) qs.set('cursor', params.cursor)
  if (params.limit) qs.set('limit', String(params.limit))
  return get(`/api/explore/v2/models?${qs.toString()}`)
}
export type NewsV2GithubEntry = {
  repo: string; stars: number; growth?: number; baseline_date?: string; status: 'ok' | 'collecting'
  description?: string; language?: string | null; topic?: string
  item_id?: number; interaction?: NewsV2Interaction
}
export type NewsV2Interaction = {
  reaction: string; favorite: number; note: string | null; opens: number; dwell_ms: number; version: number
}
export type NewsV2ItemEntry = {
  item_id: number; title: string; source: string; url?: string; item_type?: string
  excerpt?: string | null; published_at?: string | null; first_seen_at?: string
  media_key?: string | null; topic?: string; score?: number; trust?: string; engagement?: number
  recap?: string | null
  reasons?: { reason: string; strength: number }[]; interaction?: NewsV2Interaction
}
export async function getNewsV2TrendingGithub(window: 'week' | 'month' | 'all', q = '', topic = ''): Promise<{ entries: NewsV2GithubEntry[]; snapshot_id: number | null; next_cursor: string | null; topics?: string[] }> {
  const qs = new URLSearchParams({ section: 'github', window, limit: '30' })
  if (q.trim()) qs.set('q', q.trim())
  if (topic.trim() && topic !== 'All topics') qs.set('topic', topic.trim())
  return get(`/api/explore/v2/trending?${qs.toString()}`)
}
export async function getNewsV2TrendingTools(): Promise<{ entries: NewsV2ItemEntry[] }> {
  return get('/api/explore/v2/trending?section=tools&limit=15')
}
export async function getNewsV2TrendingSources(): Promise<{ sources: { source: string; items: number; latest_observed: string }[] }> {
  return get('/api/explore/v2/trending?section=sources')
}
export async function getNewsV2Feed(params: { mode: 'for_you' | 'latest' | 'favorites'; cursor?: string; limit?: number; source?: string; has_note?: boolean }): Promise<{ mode: string; entries: NewsV2ItemEntry[]; next_cursor: string | null; snapshot_id?: number | null }> {
  const qs = new URLSearchParams({ mode: params.mode })
  if (params.cursor) qs.set('cursor', params.cursor)
  if (params.limit) qs.set('limit', String(params.limit))
  if (params.source) qs.set('source', params.source)
  if (params.has_note) qs.set('has_note', 'true')
  return get(`/api/explore/v2/feed?${qs.toString()}`)
}
export async function postNewsV2Refresh(tab: 'home' | 'trending' | 'feed', sources?: string[]): Promise<{ job_id: number; joined: boolean }> {
  return request('/api/explore/v2/refresh', { method: 'POST', body: JSON.stringify(sources && sources.length ? { tab, sources } : { tab }) })
}
export async function getNewsV2RefreshJob(jobId: number): Promise<NewsV2RefreshJob> {
  return get(`/api/explore/v2/refresh/${jobId}`)
}
export async function postNewsV2RefreshCommand(jobId: number, command: 'cancel' | 'retry_failed'): Promise<NewsV2RefreshJob> {
  return request(`/api/explore/v2/refresh/${jobId}/commands`, { method: 'POST', body: JSON.stringify({ command }) })
}
export type NewsV2Settings = {
  schedules: Record<string, string>; enabled_sources: string[]
  context_classes: Record<string, boolean>; schedule_options: string[]
  known_sources: string[]; tab_sources: Record<string, string[]>
  unconfigured?: string[]
}
export async function getNewsV2Settings(): Promise<NewsV2Settings> { return get('/api/explore/v2/settings') }
export type NewsV2Leaderboard = {
  category: string; sources: string[]
  entries: { model_id: string; score: number; metrics: number; observed_at: string }[]
}
export async function getNewsV2ModelLeaderboards(): Promise<{ categories: NewsV2Leaderboard[] }> {
  return get('/api/explore/v2/models/leaderboards')
}
export async function patchNewsV2Settings(patch: {
  schedules?: Record<string, string>; enabled_sources?: string[]; context_classes?: Record<string, boolean>
}): Promise<{ schedules: Record<string, string>; enabled_sources: string[]; context_classes: Record<string, boolean> }> {
  return request('/api/explore/v2/settings', { method: 'PATCH', body: JSON.stringify(patch) })
}
// Mutations (N06 contract): every write carries an Idempotency-Key (replays return
// current state, replayed:true) and the optimistic interaction version (stale → 409).
export type NewsV2InteractionState = NewsV2Interaction & { item_id: number; replayed: boolean }
export function newsV2IdemKey(): string {
  return (crypto.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`)
}
export async function patchNewsV2Interaction(
  itemId: number, action: 'like' | 'dislike' | 'undo' | 'favorite' | 'unfavorite', version: number,
): Promise<NewsV2InteractionState> {
  return request(`/api/explore/v2/items/${itemId}/interaction`, {
    method: 'PATCH', headers: { 'Idempotency-Key': newsV2IdemKey() },
    body: JSON.stringify({ action, version }),
  })
}
export async function putNewsV2Note(itemId: number, note: string | null, version: number): Promise<NewsV2InteractionState> {
  return request(`/api/explore/v2/items/${itemId}/note`, {
    method: 'PUT', headers: { 'Idempotency-Key': newsV2IdemKey() },
    body: JSON.stringify({ note, version }),
  })
}
export async function postNewsV2Event(
  itemId: number, event: { type: 'open' } | { type: 'dwell'; ms: number },
): Promise<NewsV2Interaction & { item_id: number; recorded: boolean }> {
  return request(`/api/explore/v2/items/${itemId}/events`, {
    method: 'POST', headers: { 'Idempotency-Key': newsV2IdemKey() },
    body: JSON.stringify(event),
  })
}
export async function getNewsV2Profile(): Promise<{
  version: number; topics: Record<string, number>; sources: Record<string, number>
  types: Record<string, number>; provenance: Record<string, unknown>
}> {
  return get('/api/explore/v2/profile')
}

// ── Explore scout stream: real per-step refresh progress (SSE) ─────────────────
export type ScoutEvent =
  | { phase: 'pillar'; pillar: string; index: number; total: number }
  | { phase: 'start'; pillar: string; total_sources: number }
  | { phase: 'fetch'; pillar?: string; source: string; status: 'start' | 'done'; items?: number }
  | { phase: 'summarize'; pillar?: string; done: number; total: number; title?: string }
  | { phase: 'score'; pillar?: string }
  | { phase: 'done'; pillar?: string; items: number; sources: Record<string, number>; ts: string }
  | { phase: 'complete'; status: ExploreStatus }
  | { phase: 'error'; detail?: string; error?: string }

/** Stream the scout refresh; `onEvent` fires per SSE event, resolves on `complete`. */
export async function streamExploreRefresh(
  pillar: 'models' | 'tools' | 'social' | 'news' | 'all',
  onEvent: (ev: ScoutEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`/api/explore/refresh/stream?pillar=${pillar}`, {
    method: 'POST', signal,
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
    // SSE frames are separated by a blank line
    while ((idx = buffer.indexOf('\n\n')) >= 0) {
      const frame = buffer.slice(0, idx)
      buffer = buffer.slice(idx + 2)
      let event = 'progress'; let data = ''
      for (const line of frame.split('\n')) {
        if (line.startsWith('event:')) event = line.slice(6).trim()
        else if (line.startsWith('data:')) data += line.slice(5).trim()
      }
      if (!data) continue
      try { onEvent({ phase: event, ...JSON.parse(data) } as ScoutEvent) } catch { /* ignore */ }
    }
  }
}

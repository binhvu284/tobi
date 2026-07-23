import { get, request } from './apiCore'
import type { PendingAction } from './api.brain'

// Barrel for the Mission Control API client. Cold domain groups were split into
// sibling modules (#19 refactor) to shrink this file; every symbol is re-exported
// here so existing `from '../api'` / `from './api'` imports keep working unchanged.
export * from './api.performance'
export * from './api.tasks'
export * from './api.office'
export * from './api.abilities'
export * from './api.pm'
export * from './api.brain'
export * from './api.architecture'

export async function getStatus() {
  return get('/api/status')
}

export async function getProjects() {
  return get('/api/projects')
}

export async function getLessons() {
  return get('/api/lessons')
}

// ── Conductor (queue #7) — TOBI Actions audit + confirm ──────────────────────────
export type ConductorAction = {
  id: number; chat_id?: number; surface: string; tool: string; risk: string
  status: string; summary: string; result?: unknown; created_at: string; executed_at?: string | null
}
export type ConductorStatus = {
  phase: string
  read_tools: { name: string; description: string }[]
  act_tools: { name: string; risk: string; description: string }[]
  surfaces: Record<string, string>
}
export async function getConductorActions(limit = 50): Promise<{ count: number; actions: ConductorAction[] }> {
  return get(`/api/conductor/actions?limit=${limit}`)
}
export async function getConductorStatus(): Promise<ConductorStatus> { return get('/api/conductor/status') }
export async function confirmConductorAction(
  action_id: number, decision: 'approve' | 'reject',
): Promise<{ ok: boolean; status: string; summary?: string; result?: unknown; error?: string }> {
  return request('/api/conductor/confirm', { method: 'POST', body: JSON.stringify({ action_id, decision }) })
}

// ── TOBI CLI / Terminal engine (#11) ─────────────────────────────────────────────
export type TerminalMode = 'plan' | 'ask' | 'accept' | 'auto'
export type TerminalStatus = {
  enabled: boolean; mode: TerminalMode; os: string; shell: string; cwd: string
  package_managers: string[]; tools_registered: number; modes: TerminalMode[]
}
export type TerminalJob = {
  id: number; command: string; status: string; exit_code: number | null
  cwd?: string; risk?: string; started_at?: string; ended_at?: string; live?: boolean
}
export type InstalledTool = {
  name: string; version?: string; channel?: string; how_to_use?: string
  wired?: number; status?: string; updated_at?: string
}

export async function getTerminalStatus(): Promise<TerminalStatus> { return get('/api/terminal/status') }
export async function setTerminalMode(mode: TerminalMode): Promise<{ ok: boolean; mode: TerminalMode }> {
  return request('/api/terminal/mode', { method: 'POST', body: JSON.stringify({ mode }) })
}
export async function setTerminalKillSwitch(enabled: boolean): Promise<{ ok: boolean; enabled: boolean }> {
  return request('/api/terminal/killswitch', { method: 'POST', body: JSON.stringify({ enabled }) })
}
export async function getTerminalJobs(): Promise<{ count: number; jobs: TerminalJob[] }> { return get('/api/terminal/jobs') }
export async function killTerminalJob(jobId: number): Promise<{ ok?: boolean; error?: string; status?: string }> {
  return request(`/api/terminal/jobs/${jobId}/kill`, { method: 'POST' })
}
export async function getInstalledTools(): Promise<{ count: number; tools: InstalledTool[] }> { return get('/api/terminal/tools') }

// ── Premium Chat (#8): multi-model sessions, typed stream, LLM config ────────────
export type ChatSession = {
  id: number; title: string; model: string | null
  created_at: string; updated_at: string; message_count?: number
}
// ── Chat Mode contract (#16) ──────────────────────────────────────────────────
export type ChatModeId = 'chat' | 'agent'
export type ChatCapabilities = { web_search?: boolean; deep_research?: boolean; terminal_intent?: boolean; connectors?: string[] }
export type ChatModeEvent = { mode: ChatModeId; legacy_mode?: string | null; capabilities?: ChatCapabilities }
export type ContextChip = { id: number; name: string }
export type ChatContextEvent = { projects: ContextChip[]; resources: { name?: string }[]; auto?: boolean }
export type ChatPlanEvent = { steps: string[]; title?: string }
export type ChatArtifactEvent = { id: number; kind: string; title: string }
// #20 review P1: per-memory feedback chip — one per recalled owner memory, so the
// owner can rate each memory useful/irrelevant/wrong from the Chat turn.
export type MemoryChip = {
  memory_id: number; text: string; type: string; scope: string
  confidence: number; quality: number; hedged: boolean; evidence: string
}
export type ChatMemoryChipsEvent = { chips: MemoryChip[] }
export type ChatTurnMeta = {
  mode?: ChatModeId; legacy_mode?: string | null; capabilities?: ChatCapabilities
  steps?: string[]; tools?: string[]; run_id?: number; artifact_ids?: number[]
  context?: { projects?: ContextChip[]; resources?: { name?: string }[] }
  memoryChips?: MemoryChip[]
  turn_id?: string
}
export type ChatRuntimeMode = 'off' | 'shadow' | 'on'
export async function getChatConfig(): Promise<{ mode_v2: boolean; chat_runtime_v2?: ChatRuntimeMode }> { return get('/api/chat/config') }
export async function setChatConfig(modeV2: boolean): Promise<{ mode_v2: boolean }> {
  return request('/api/chat/config', { method: 'POST', body: JSON.stringify({ mode_v2: modeV2 }) })
}
export type AgentRun = {
  id: number; session_id: number; message_id?: number | null; mode: string; status: string
  title?: string | null; error?: string | null; created_at: string; updated_at: string
  completed_at?: string | null; step_count?: number; steps?: AgentRunStep[]
}
export type AgentRunStep = {
  id: number; run_id: number; type: string; status: string; title?: string | null
  summary?: string | null; tool?: string | null; risk?: string | null
  payload_json?: string | null; created_at: string; completed_at?: string | null
}
export async function getSessionRuns(id: number, limit = 20): Promise<{ runs: AgentRun[] }> {
  return get(`/api/chat/sessions/${id}/runs?limit=${limit}`)
}
export async function getAgentRun(runId: number): Promise<AgentRun> { return get(`/api/chat/runs/${runId}`) }
export type AgentRunCommand = 'resume' | 'retry_step' | 'skip_step' | 'revise' | 'cancel'
export type AgentRunCommandResult = {
  run_id: number; session_id?: number; status: string; requires_turn: boolean; recovery_prompt?: string
}
export async function commandAgentRun(runId: number, command: AgentRunCommand, revision = ''): Promise<AgentRunCommandResult> {
  return request(`/api/chat/runs/${runId}/commands`, {
    method: 'POST', body: JSON.stringify({ command, revision }),
  })
}
export type ChatRuntimeEvent = {
  turn_id: string; seq: number; type: string; stage: string; timestamp: string; data: Record<string, any>
}
export type ChatTurnTrace = {
  id: string; session_id: number; run_id?: number | null; status: string; mode: string; model?: string | null
  route?: string | null; first_event_ms?: number | null; first_token_ms?: number | null; total_ms?: number | null
  error_code?: string | null; events: Array<{ seq: number; event_type: string; stage: string; payload: Record<string, any>; created_at: string }>
}
export async function getChatTurnTrace(turnId: string): Promise<ChatTurnTrace> {
  return get(`/api/chat/turns/${encodeURIComponent(turnId)}/trace`)
}
export type ChatArtifact = {
  id: number; session_id: number; run_id?: number | null; kind: string
  title?: string | null; content?: string; meta_json?: string | null; created_at: string
}
export async function getSessionArtifacts(id: number, limit = 50): Promise<{ artifacts: ChatArtifact[] }> {
  return get(`/api/chat/sessions/${id}/artifacts?limit=${limit}`)
}
export async function getChatArtifact(artifactId: number): Promise<ChatArtifact> {
  return get(`/api/chat/artifacts/${artifactId}`)
}

export type ChatStoredMessage = {
  id: number; role: string; content: string; parent_id?: number | null
  model?: string | null; tokens?: number | null; thinking?: string | null
  feedback?: number | null; meta?: string | null; created_at: string
}
export type ChatUsage = { prompt_tokens: number; completion_tokens: number; model: string; latency_ms: number }
export type ReaderChip = { url: string; state: string; title?: string | null }
export type ChatNotice = { kind: 'model_issue' | 'reader' | string; reader?: string; items?: ReaderChip[]; run_id?: number }
export type PickerQuestion = { question: string; options?: string[] }
export type ChatPicker = { topic: string; questions: PickerQuestion[] }
export type ChatStreamHandlers = {
  onDelta: (text: string) => void
  onThinking?: (phase: string, tools?: string[]) => void
  onAction?: (action: PendingAction) => void
  onPicker?: (picker: ChatPicker) => void
  onUsage?: (usage: ChatUsage) => void
  onNotice?: (notice: ChatNotice) => void
  onReset?: () => void
  onTerminal?: (line: string) => void   // live stdout from a run_command execution (#11)
  // ── #16 mode contract events ──
  onMode?: (mode: ChatModeEvent) => void          // normalized mode echo (first frame)
  onContext?: (ctx: ChatContextEvent) => void     // auto project context chips
  onPlan?: (plan: ChatPlanEvent) => void          // agent-mode declared plan
  onArtifact?: (artifact: ChatArtifactEvent) => void  // durable artifact produced
  onMemoryChips?: (event: ChatMemoryChipsEvent) => void  // per-memory feedback chips (#20)
  onTurnStarted?: (event: ChatRuntimeEvent) => void
  onRuntimeEvent?: (event: ChatRuntimeEvent) => void
  onRecoveryRequired?: (event: ChatRuntimeEvent) => void
}

export async function getChatSessions(): Promise<{ sessions: ChatSession[] }> { return get('/api/chat/sessions') }
export async function createChatSession(model?: string | null, title?: string): Promise<ChatSession> {
  return request('/api/chat/sessions', { method: 'POST', body: JSON.stringify({ model, title }) })
}
export async function getChatSession(id: number): Promise<{ session: ChatSession; messages: ChatStoredMessage[] }> {
  return get(`/api/chat/sessions/${id}`)
}
export async function patchChatSession(id: number, payload: { title?: string; model?: string | null }): Promise<ChatSession> {
  return request(`/api/chat/sessions/${id}`, { method: 'PATCH', body: JSON.stringify(payload) })
}
export async function deleteChatSession(id: number): Promise<{ ok: boolean }> {
  return request(`/api/chat/sessions/${id}`, { method: 'DELETE' })
}
export async function appendChatMessage(id: number, content: string, role = 'assistant'): Promise<{ ok: boolean }> {
  return request(`/api/chat/sessions/${id}/append`, { method: 'POST', body: JSON.stringify({ role, content }) })
}
export async function forkChatSession(id: number, beforeMessageId: number): Promise<ChatSession> {
  return request(`/api/chat/sessions/${id}/fork`, { method: 'POST', body: JSON.stringify({ before_message_id: beforeMessageId }) })
}
export async function setMessageFeedback(messageId: number, value: number | null): Promise<{ ok: boolean; feedback: number | null }> {
  return request(`/api/chat/messages/${messageId}/feedback`, { method: 'POST', body: JSON.stringify({ value }) })
}
export type SessionActivity = { count: number; actions: ConductorAction[] }
export async function getSessionActivity(id: number, limit = 50): Promise<SessionActivity> {
  return get(`/api/chat/sessions/${id}/activity?limit=${limit}`)
}

export type ChatAttachment = { name: string; mime: string; kind: 'text' | 'image' | 'pdf' | 'file'; text?: string; data_url?: string }
export type ChatTurnOptions = {
  attachments?: ChatAttachment[]; web_research?: boolean; thinking?: boolean; connectors?: string[]
  mode?: ChatModeId; deep_research?: boolean; review_mode?: 'ask' | 'session' | 'always'   // #16
  client_turn_id?: string; resume_run_id?: number
}

/** Stream a premium chat turn: typed SSE (thinking / delta / action / usage / done).
 *  Resolves on `done`; aborts cleanly via `signal` (keeps partial output). */
export async function streamChatSession(
  sessionId: number, message: string, model: string | null | undefined,
  handlers: ChatStreamHandlers, signal?: AbortSignal, options?: ChatTurnOptions,
): Promise<void> {
  const res = await fetch(`/api/chat/sessions/${sessionId}/stream`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message, model, ...(options || {}), client_turn_id: options?.client_turn_id || crypto.randomUUID(),
    }), signal,
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
      const frame = buffer.slice(0, idx); buffer = buffer.slice(idx + 2)
      let event = 'message', data = ''
      for (const line of frame.split('\n')) {
        if (line.startsWith('event:')) event = line.slice(6).trim()
        else if (line.startsWith('data:')) data += line.slice(5).trim()
      }
      if (!data && event !== 'done') continue
      const parse = () => { try { return JSON.parse(data) } catch { return {} } }
      if (event === 'delta') { const o = parse(); if (o.text) handlers.onDelta(o.text) }
      else if (event === 'thinking') { const o = parse(); handlers.onThinking?.(o.phase || '', o.tools) }
      else if (event === 'action') { const o = parse(); if (o && o.id != null) handlers.onAction?.(o as PendingAction) }
      else if (event === 'picker') { const o = parse(); if (o && Array.isArray(o.questions) && o.questions.length) handlers.onPicker?.(o as ChatPicker) }
      else if (event === 'usage') { handlers.onUsage?.(parse() as ChatUsage) }
      else if (event === 'notice') { const o = parse(); if (o && o.kind) handlers.onNotice?.(o as ChatNotice) }
      else if (event === 'reset') { handlers.onReset?.() }
      else if (event === 'terminal') { const o = parse(); if (o && typeof o.line === 'string') handlers.onTerminal?.(o.line) }
      else if (event === 'mode') { const o = parse(); if (o && o.mode) handlers.onMode?.(o as ChatModeEvent) }
      else if (event === 'context') { const o = parse(); if (o && Array.isArray(o.projects)) handlers.onContext?.(o as ChatContextEvent) }
      else if (event === 'plan') { const o = parse(); if (o && Array.isArray(o.steps)) handlers.onPlan?.(o as ChatPlanEvent) }
      else if (event === 'artifact') { const o = parse(); if (o && o.id != null) handlers.onArtifact?.(o as ChatArtifactEvent) }
      else if (event === 'memory_chips') { const o = parse(); if (o && Array.isArray(o.chips)) handlers.onMemoryChips?.(o as ChatMemoryChipsEvent) }
      else if (event === 'turn_started') { const o = parse() as ChatRuntimeEvent; if (o?.turn_id) { handlers.onTurnStarted?.(o); handlers.onRuntimeEvent?.(o) } }
      else if (event === 'recovery_required') { const o = parse() as ChatRuntimeEvent; if (o?.turn_id) { handlers.onRecoveryRequired?.(o); handlers.onRuntimeEvent?.(o) } }
      else if (['context_ready', 'plan_ready', 'step_started', 'step_completed', 'step_failed', 'model_escalated', 'turn_completed'].includes(event)) {
        const o = parse() as ChatRuntimeEvent; if (o?.turn_id) handlers.onRuntimeEvent?.(o)
      }
      else if (event === 'error') { throw new Error(parse().detail || 'stream error') }
      else if (event === 'done') return
    }
  }
}

export type LlmProvider = {
  id: string; label: string; kind: string; key_env: string | null
  needs_key: boolean; key_present: boolean; key_last4?: string | null; editable_base_url: boolean
  base_url: string; enabled: boolean; models: string[]
}
export type LlmConfig = {
  default_model: string
  task_overrides: Record<string, string>
  fallback: string[]
  providers: Record<string, { enabled?: boolean; base_url?: string; models?: string[] }>
}
export type AvailableModel = { id: string; provider: string; model: string; label: string; context?: number }
export type HermesPush = { ok: boolean; json?: boolean; yaml?: boolean; cli?: boolean; targets?: string[]; detail: string }
export type LlmConfigResponse = { config: LlmConfig; providers: LlmProvider[]; models: AvailableModel[]; hermes?: HermesPush }

export async function getLlmConfig(): Promise<LlmConfigResponse> { return get('/api/llm/config') }
export async function getLlmModels(): Promise<{ models: AvailableModel[] }> { return get('/api/llm/models') }
export async function saveLlmConfig(config: LlmConfig): Promise<LlmConfigResponse> {
  return request('/api/llm/config', { method: 'POST', body: JSON.stringify({ config }) })
}
export async function setLlmProviderKey(provider: string, value: string): Promise<{ ok: boolean; providers: LlmProvider[]; models: AvailableModel[] }> {
  return vreq(`/api/llm/provider/${provider}/key`, { method: 'POST', body: JSON.stringify({ value }) })
}

// ── multi-key slots: several accounts per provider/secret, one active at a time ──
export type KeySlot = { label: string; last4: string | null; active: boolean; env?: boolean; added_at: string | null; updated_at: string | null }
export type KeySlotsResponse = { ok: boolean; name: string; slots: KeySlot[]; providers: LlmProvider[]; models: AvailableModel[] }
export async function listKeySlots(name: string): Promise<KeySlotsResponse> { return vreq(`/api/keys/${name}`) }
export async function addKeySlot(name: string, value: string, label?: string, activate = false): Promise<KeySlotsResponse> {
  return vreq(`/api/keys/${name}`, { method: 'POST', body: JSON.stringify({ value, label: label || null, activate }) })
}
export async function activateKeySlot(name: string, label: string): Promise<KeySlotsResponse> {
  return vreq(`/api/keys/${name}/activate`, { method: 'POST', body: JSON.stringify({ label }) })
}
export async function deactivateKeySlots(name: string): Promise<KeySlotsResponse> {
  return vreq(`/api/keys/${name}/deactivate`, { method: 'POST' })
}
export async function deleteKeySlot(name: string, label: string): Promise<KeySlotsResponse> {
  return vreq(`/api/keys/${name}/delete`, { method: 'POST', body: JSON.stringify({ label }) })
}
export async function discoverLlmModels(provider: string): Promise<{ ok: boolean; models: string[] }> {
  return request(`/api/llm/discover/${provider}`, { method: 'POST' })
}
export async function pushHermesConfig(): Promise<HermesPush> { return request('/api/llm/hermes-push', { method: 'POST' }) }

// ── Usage analytics + Compact (P3) ───────────────────────────────────────────────
export type UsageModel = { model: string; provider: string; tokens: number; prompt_tokens: number; completion_tokens: number; cost: number; requests: number }
export type UsageDay = { day: string; tokens: number; cost: number }
export type UsageSummary = {
  days: number; total_tokens: number; prompt_tokens: number; completion_tokens: number
  total_cost: number; requests: number; avg_latency_ms: number
  by_model: UsageModel[]; by_surface: Record<string, number>; by_day: UsageDay[]
}
export async function getLlmUsage(days = 7): Promise<UsageSummary> { return get(`/api/llm/usage?days=${days}`) }
export async function compactSession(id: number, model?: string | null): Promise<{ compacted: boolean; messages: ChatStoredMessage[]; summary?: string; detail?: string }> {
  return request(`/api/chat/sessions/${id}/compact`, { method: 'POST', body: JSON.stringify({ model }) })
}

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

// ── Genesis Complete: vault + integrations ──────────────────────────
// Session token is scoped to this browser tab. sessionStorage survives route changes
// and reloads, but disappears when the tab closes and is never written to localStorage.
const VAULT_SESSION_KEY = 'tobi.vault.session'
const _vaultListeners = new Set<() => void>()
function storedVaultSession(): string | null {
  try { return typeof sessionStorage === 'undefined' ? null : sessionStorage.getItem(VAULT_SESSION_KEY) }
  catch { return null }
}
let _vaultSession: string | null = storedVaultSession()
export function getVaultSession() { return _vaultSession }
export function hasVaultSession() { return !!_vaultSession }
export function subscribeVaultSession(listener: () => void) {
  _vaultListeners.add(listener)
  return () => _vaultListeners.delete(listener)
}
export function setVaultSession(t: string | null) {
  _vaultSession = t || null
  try {
    if (_vaultSession) sessionStorage.setItem(VAULT_SESSION_KEY, _vaultSession)
    else sessionStorage.removeItem(VAULT_SESSION_KEY)
  } catch { /* memory-only fallback */ }
  _vaultListeners.forEach(listener => listener())
}
function vaultHeaders(): Record<string, string> {
  return _vaultSession ? { 'X-Vault-Session': _vaultSession } : {}
}
async function vreq(path: string, init: RequestInit = {}) {
  try {
    return await request(path, { ...init, headers: { ...vaultHeaders(), ...(init.headers || {}) } })
  } catch (error) {
    if ((error as { status?: number })?.status === 401) setVaultSession(null)
    throw error
  }
}

export type Profile = { name: string; label: string | null; created_at: string | null }
export type VaultStatus = {
  crypto_available: boolean; setup: boolean; unlocked: boolean
  active_profile: string; secret_count: number; profiles: Profile[]; auto_lock_seconds: number
}
export type GenesisStatus = { abilities: Record<string, boolean>; active: number; total: number; pct: number; complete: boolean }
export type IntegrationField = {
  name: string; label: string; type: string; help_url?: string | null
  set: boolean; last4: string | null; test_status: string | null
}
export type IntegrationAbility = { id: string; name: string; active: boolean }
export type Integration = {
  id: string; label: string; category: 'core' | 'tools' | 'coming_soon' | 'custom'
  required: boolean; available: boolean; icon?: string | null; blurb?: string | null; coming_in?: string | null
  fields: IntegrationField[]; connected: boolean; abilities: IntegrationAbility[]
}
export type IntegrationsResponse = { integrations: Integration[]; genesis: GenesisStatus; vault: VaultStatus }
export type AuditEntry = { ts: string; action: string; integration_id: string | null; name: string | null; ok: boolean | null; detail: string | null }

export async function getVaultStatus(): Promise<VaultStatus> { return get('/api/vault/status') }
export async function vaultSetup(master: string, import_env = true) {
  const r = await request('/api/vault/setup', { method: 'POST', body: JSON.stringify({ master, import_env }) })
  setVaultSession(r.session); return r
}
export async function vaultUnlock(master: string) {
  const r = await request('/api/vault/unlock', { method: 'POST', body: JSON.stringify({ master }) })
  setVaultSession(r.session); return r
}
export async function vaultLock() { setVaultSession(null); return vreq('/api/vault/lock', { method: 'POST' }) }
export async function vaultReload() { return vreq('/api/vault/reload', { method: 'POST' }) }
export async function getVaultAudit(limit = 100): Promise<{ entries: AuditEntry[] }> { return vreq(`/api/vault/audit?limit=${limit}`) }
export async function vaultExport(password: string): Promise<{ blob: string }> {
  return vreq('/api/vault/export', { method: 'POST', body: JSON.stringify({ password }) })
}
export async function vaultImport(blob: string, password: string) {
  return vreq('/api/vault/import', { method: 'POST', body: JSON.stringify({ blob, password }) })
}
export async function getVaultProfiles(): Promise<{ profiles: Profile[]; active: string }> { return get('/api/vault/profiles') }
export async function createVaultProfile(name: string, label?: string, activate = true) {
  return vreq('/api/vault/profiles', { method: 'POST', body: JSON.stringify({ name, label, activate }) })
}

export async function getIntegrations(): Promise<IntegrationsResponse> { return get('/api/integrations') }
export async function connectIntegration(id: string, fields: Record<string, string>) {
  return vreq(`/api/integrations/${id}/connect`, { method: 'POST', body: JSON.stringify({ fields }) })
}
export async function testIntegration(id: string): Promise<{ ok: boolean; message: string; genesis: GenesisStatus }> {
  return vreq(`/api/integrations/${id}/test`, { method: 'POST' })
}
export async function revealSecret(name: string, master: string): Promise<{ value: string }> {
  return vreq('/api/integrations/reveal', { method: 'POST', body: JSON.stringify({ name, master }) })
}
export async function addCustomSecret(name: string, value: string, secret_type = 'custom') {
  return vreq('/api/integrations/custom', { method: 'POST', body: JSON.stringify({ name, value, secret_type }) })
}
export async function removeIntegration(id: string) { return vreq(`/api/integrations/${id}`, { method: 'DELETE' }) }

export async function googleOAuthUrl(): Promise<string> {
  const base = import.meta.env.VITE_API_BASE || ''
  return `${base}/api/integrations/google/oauth/start`
}
export async function googleOAuthStatus(): Promise<{ configured: boolean; connected: boolean; email: string; redirect_uri: string }> {
  return get('/api/integrations/google/status')
}
export async function googleDisconnect(): Promise<{ ok: boolean }> {
  return vreq('/api/integrations/google/disconnect', { method: 'POST' })
}

// ── MCP Hub (#5) ─────────────────────────────────────────────────────────
export type McpServerConfigRow = {
  id: number; enabled: number; transport: string; public_url: string | null
  tunnel_status: string; auth_modes_json: string; rate_limit_json: string; updated_at: string
}
export type McpSelfTool = { name: string; description: string; sensitive: boolean }
export type McpOAuth = { enabled: boolean; issuer: string | null; audience: string | null; alg: string }
export type McpTunnel = { available: boolean; running: boolean; public_url: string | null; mcp_url?: string | null }
export type McpServerInfo = {
  available: boolean; config: McpServerConfigRow; tools: McpSelfTool[]; mount: string | null
  exposed: boolean; oauth: McpOAuth; tunnel: McpTunnel
}
export type A2aSkill = { id: string; name: string; description?: string }
export type A2aCard = { name: string; description: string; version: string; url: string; skills: A2aSkill[] }
export type A2aPeer = { id: number; name: string; endpoint: string; status: string; skills: string[] }
export type McpClient = {
  id: number; name: string; auth_type: string; scopes: string[]
  status: string; created_at: string; last_seen: string | null
}
export type McpIssuedClient = { ok: boolean; id: number; name: string; scopes: string[]; token: string }
export type McpConnection = {
  id: number; name: string; transport: string; endpoint: string
  enabled: number; status: string; last_tested_at: string | null; tools_count: number
}
export type McpExternalTool = { id: number; source: string; name: string; enabled: number; permission: 'allow' | 'ask' | 'deny' }
export type McpCallLog = {
  id: number; ts: string; direction: 'in' | 'out'; peer: string | null
  tool: string | null; status: string | null; latency_ms: number | null; error: string | null
}
export type McpApproval = {
  id: number; client: string | null; tool: string | null; args: string | null
  status: string; created_at: string; decided_at: string | null
}

// Server (M1)
export async function getMcpServerConfig(): Promise<McpServerInfo> { return vreq('/api/mcp/server/config') }
export async function setMcpServerConfig(body: { enabled?: boolean; public_url?: string; rate_limit_per_minute?: number }) {
  return vreq('/api/mcp/server/config', { method: 'PUT', body: JSON.stringify(body) })
}
export async function getMcpClients(): Promise<{ clients: McpClient[] }> { return vreq('/api/mcp/clients') }
export async function issueMcpClient(name: string, scopes: string[]): Promise<McpIssuedClient> {
  return vreq('/api/mcp/clients', { method: 'POST', body: JSON.stringify({ name, scopes }) })
}
export async function setMcpClientScopes(id: number, scopes: string[]) {
  return vreq(`/api/mcp/clients/${id}`, { method: 'PATCH', body: JSON.stringify({ scopes }) })
}
export async function revokeMcpClient(id: number) { return vreq(`/api/mcp/clients/${id}`, { method: 'DELETE' }) }

// Activity + approvals (M1)
export async function getMcpLogs(limit = 100, direction?: 'in' | 'out'): Promise<{ logs: McpCallLog[] }> {
  return vreq(`/api/mcp/logs?limit=${limit}${direction ? `&direction=${direction}` : ''}`)
}
export async function getMcpApprovals(status = 'pending'): Promise<{ approvals: McpApproval[] }> {
  return vreq(`/api/mcp/approvals?status=${status}`)
}
export async function approveMcp(id: number) { return vreq(`/api/mcp/approvals/${id}/approve`, { method: 'POST' }) }
export async function rejectMcp(id: number) { return vreq(`/api/mcp/approvals/${id}/reject`, { method: 'POST' }) }

// Connections + external tools (M2)
export async function getMcpConnections(): Promise<{ connections: McpConnection[] }> { return vreq('/api/mcp/connections') }
export async function addMcpConnection(body: { name: string; transport: string; endpoint: string; token?: string }) {
  return vreq('/api/mcp/connections', { method: 'POST', body: JSON.stringify(body) })
}
export async function testMcpConnection(id: number) { return vreq(`/api/mcp/connections/${id}/test`, { method: 'POST' }) }
export async function refreshMcpConnection(id: number) { return vreq(`/api/mcp/connections/${id}/refresh`, { method: 'POST' }) }
export async function setMcpConnectionEnabled(id: number, enabled: boolean) {
  return vreq(`/api/mcp/connections/${id}`, { method: 'PATCH', body: JSON.stringify({ enabled }) })
}
export async function deleteMcpConnection(id: number) { return vreq(`/api/mcp/connections/${id}`, { method: 'DELETE' }) }
export async function mcpHealth() { return vreq('/api/mcp/connections/health', { method: 'POST' }) }
export async function getMcpTools(source?: string): Promise<{ tools: McpExternalTool[] }> {
  return vreq(`/api/mcp/tools${source ? `?source=${source}` : ''}`)
}
export async function setMcpTool(id: number, body: { enabled?: boolean; permission?: string }) {
  return vreq(`/api/mcp/tools/${id}`, { method: 'PATCH', body: JSON.stringify(body) })
}
export async function invokeMcpTool(id: number, args: Record<string, unknown>): Promise<{ ok: boolean; content?: string; error?: string; pending?: boolean; approval_id?: number; message?: string }> {
  return vreq(`/api/mcp/tools/${id}/invoke`, { method: 'POST', body: JSON.stringify({ args }) })
}

// M4 — OAuth, tunnel exposure, A2A
export async function setMcpOAuth(body: { enabled: boolean; issuer?: string; audience?: string; algorithm?: string; secret?: string }) {
  return vreq('/api/mcp/server/oauth', { method: 'PUT', body: JSON.stringify(body) })
}
export async function getMcpTunnel(): Promise<McpTunnel> { return vreq('/api/mcp/server/tunnel') }
export async function setMcpTunnel(action: 'start' | 'stop', port?: number): Promise<{ ok: boolean; public_url?: string; mcp_url?: string; error?: string; note?: string }> {
  return vreq('/api/mcp/server/tunnel', { method: 'POST', body: JSON.stringify({ action, port }) })
}
export async function getA2aCard(): Promise<{ card: A2aCard }> { return vreq('/api/mcp/a2a/card') }
export async function setA2aCard(body: { name?: string; description?: string; version?: string }): Promise<{ ok: boolean; card: A2aCard }> {
  return vreq('/api/mcp/a2a/card', { method: 'PUT', body: JSON.stringify(body) })
}
export async function getA2aPeers(): Promise<{ peers: A2aPeer[] }> { return vreq('/api/mcp/a2a/peers') }
export async function addA2aPeer(url: string) { return vreq('/api/mcp/a2a/peers', { method: 'POST', body: JSON.stringify({ url }) }) }
export async function removeA2aPeer(id: number) { return vreq(`/api/mcp/a2a/peers/${id}`, { method: 'DELETE' }) }
export async function a2aMessage(id: number, text: string): Promise<{ ok: boolean; status?: number; response?: string; error?: string }> {
  return vreq(`/api/mcp/a2a/peers/${id}/message`, { method: 'POST', body: JSON.stringify({ text }) })
}

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
  provider?: string; model?: string; surface?: string; agent?: string
  cost: number; tokens: number; prompt_tokens: number; completion_tokens: number
  requests: number; avg_latency_ms: number
}
export type UsageOverview = {
  range: string; total_cost: number; total_tokens: number; prompt_tokens: number
  completion_tokens: number; requests: number; avg_latency_ms: number
  by_provider: UsageBucket[]; by_model: UsageBucket[]; by_surface: UsageBucket[]
  by_agent: UsageBucket[]; surfaces: string[]
  by_day: ({ day: string; cost: number; tokens: number } & Record<string, number | string>)[]
}
export type UsageCall = {
  id: number; ts: string; surface: string; feature: string | null; provider: string
  model: string; agent_id: string | null; prompt_tokens: number; completion_tokens: number
  cost_est: number; latency_ms: number
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
export async function getUsageOverview(range: 'day' | 'week' | 'month' | 'all' = 'month'): Promise<UsageOverview> {
  return get(`/api/usage/overview?range=${range}`)
}
export async function getUsageCalls(opts: { limit?: number; offset?: number; q?: string; surface?: string; model?: string } = {}): Promise<{ total: number; limit: number; offset: number; calls: UsageCall[] }> {
  const p = new URLSearchParams()
  if (opts.limit) p.set('limit', String(opts.limit))
  if (opts.offset) p.set('offset', String(opts.offset))
  if (opts.q) p.set('q', opts.q)
  if (opts.surface) p.set('surface', opts.surface)
  if (opts.model) p.set('model', opts.model)
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
export type NewsV2SourceHealth = {
  state: string; sources: Record<string, { state?: string; error?: string }>; updated_at: string
} | null
export type NewsV2Home = {
  top: NewsV2RankEntry[]; snapshot_id: number | null; releases: NewsV2Release[]
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
  description?: string; language?: string | null
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
export async function getNewsV2TrendingGithub(window: 'week' | 'month' | 'all', q = ''): Promise<{ entries: NewsV2GithubEntry[]; snapshot_id: number | null; next_cursor: string | null }> {
  const qs = new URLSearchParams({ section: 'github', window, limit: '30' })
  if (q.trim()) qs.set('q', q.trim())
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
  pull_request?: { number?: number | null; url?: string | null; draft?: number; ci_state?: string | null } | null
  owner_state?: string; readiness?: { id: number; status: string; payload: DeveloperReadiness } | null
  evidence?: Array<Record<string, unknown>>; scorecard?: { payload: DeveloperScorecard } | null
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
  workflows: DeveloperWorkflow[]
  summary: { states: Record<string, number>; releases: DeveloperRelease[]; deployments: unknown[] }
  policy: {
    version: number; hash: string; capabilities: Record<string, boolean>
    github_configured: boolean; deployment_configured: boolean
  }
  process?: { auto_queue: boolean }
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
export async function getDeveloperHistory(signal?: AbortSignal): Promise<{ workflows: DeveloperWorkflow[] }> {
  return vreq('/api/developer/workflows/history', { signal })
}
export async function getDeveloperScorecard(workflowId: number): Promise<DeveloperScorecard> {
  return vreq(`/api/developer/workflows/${workflowId}/scorecard`)
}
export async function commandDeveloperWorkflow(
  workflowId: number, command: 'pause' | 'resume' | 'cancel' | 'retry' | 'remove',
): Promise<DeveloperWorkflow> {
  return vreq(`/api/developer/workflows/${workflowId}/commands`, {
    method: 'POST', body: JSON.stringify({ command, idempotency_key: crypto.randomUUID() }),
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

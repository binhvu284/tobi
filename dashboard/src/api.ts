import { get, request } from './apiCore'
import { vreq } from './apiVault'
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
export * from './api.graph'
export * from './api.genesis'
export * from './api.mcp'
export * from './api.storage'
export * from './api.explore'
export * from './api.developer'

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


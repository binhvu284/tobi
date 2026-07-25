// Multi-key slots + usage analytics/Compact (P3)
//
// Split out of api.ts (pre-#21 refactor) so the barrel stops being an import hub;
// still re-exported from './api' for any consumer that wants the barrel.
import { get, request } from './apiCore'
import { vreq } from './apiVault'
import type { PendingAction } from './api.brain'
import type { AvailableModel, ChatStoredMessage, HermesPush, LlmProvider } from './api.chat'

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

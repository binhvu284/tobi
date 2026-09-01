// Conductor (queue #7) — TOBI Actions audit + confirm
//
// Split out of api.ts (pre-#21 refactor) so the barrel stops being an import hub;
// still re-exported from './api' for any consumer that wants the barrel.
import { get, request } from './apiCore'
import { vreq } from './apiVault'
import type { PendingAction } from './api.brain'

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
): Promise<{
  ok: boolean; status: string; summary?: string; result?: unknown; error?: string
  developer_dispatch?: { status: string; blocker?: string | null; workflow_id?: number | null }
}> {
  return request('/api/conductor/confirm', { method: 'POST', body: JSON.stringify({ action_id, decision }) })
}

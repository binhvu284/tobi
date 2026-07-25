// TOBI CLI / Terminal engine (#11)
//
// Split out of api.ts (pre-#21 refactor) so the barrel stops being an import hub;
// still re-exported from './api' for any consumer that wants the barrel.
import { get, request } from './apiCore'
import { vreq } from './apiVault'
import type { PendingAction } from './api.brain'

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

// Genesis Complete: vault + integrations (session-token scoped)
//
// Split out of api.ts (pre-#21 refactor) to shrink the barrel; every symbol is
// re-exported from './api', so existing import sites are unchanged.
import { get, request } from './apiCore'
import { setVaultSession, vreq } from './apiVault'
// The vault session lives in apiVault.ts (single instance); re-exported here so the
// barrel keeps exporting it exactly as before.
export { getVaultSession, hasVaultSession, setVaultSession, subscribeVaultSession } from './apiVault'

// ── Genesis Complete: vault + integrations ──────────────────────────
// Session token is scoped to this browser tab. sessionStorage survives route changes
// and reloads, but disappears when the tab closes and is never written to localStorage.

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

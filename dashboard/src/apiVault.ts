// Vault session state + the vault-scoped fetch helper, shared by every API module that
// calls a vault-gated endpoint (genesis, mcp, developer, and the keys/LLM calls still in
// the barrel).
//
// Lives outside the api.ts barrel (like apiCore.ts) for two reasons: the session token is
// mutable module state that must exist exactly ONCE, and vreq/vaultHeaders stay internal
// rather than becoming part of the public `from '../api'` surface.
import { request } from './apiCore'

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
export function vaultHeaders(): Record<string, string> {
  return _vaultSession ? { 'X-Vault-Session': _vaultSession } : {}
}
export async function vreq(path: string, init: RequestInit = {}) {
  try {
    return await request(path, { ...init, headers: { ...vaultHeaders(), ...(init.headers || {}) } })
  } catch (error) {
    if ((error as { status?: number })?.status === 401) setVaultSession(null)
    throw error
  }
}

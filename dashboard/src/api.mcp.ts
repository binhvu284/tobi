// MCP Hub (#5) — server, activity, connections, OAuth/tunnel/A2A
//
// Split out of api.ts (pre-#21 refactor) to shrink the barrel; every symbol is
// re-exported from './api', so existing import sites are unchanged.
import { get, request } from './apiCore'
import { vreq } from './apiVault'

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

import { get, request } from './apiCore'

// ── Architecture V2 (#20): repo-backed Mermaid diagrams + git history ────────
export type ArchDiagramMeta = { id: string; title: string; description: string }
export type ArchDiagramList = { items: ArchDiagramMeta[]; count: number }
export type ArchDiagram = {
  id: string; title: string; description: string
  content: string          // validated Mermaid flowchart source (empty when valid=false)
  guide: string            // markdown guide with ## <node-id> sections
  valid: boolean
  reasons: string[]
}
export type ArchVersion = { sha: string; short: string; date: string; subject: string }
export type ArchHistory = { items: ArchVersion[]; count: number; available: boolean }
export type ArchVersionContent = { id: string; sha: string; short: string; content: string; valid: boolean }
export type ArchConfig = { v2_enabled: boolean }

export async function getArchitectureDiagrams(): Promise<ArchDiagramList> {
  return get('/api/architecture/diagrams')
}
export async function getArchitectureDiagram(id: string): Promise<ArchDiagram> {
  return get(`/api/architecture/diagrams/${encodeURIComponent(id)}`)
}
export async function getArchitectureHistory(id: string, limit = 10): Promise<ArchHistory> {
  return get(`/api/architecture/diagrams/${encodeURIComponent(id)}/history?limit=${limit}`)
}
export async function getArchitectureVersion(id: string, sha: string): Promise<ArchVersionContent> {
  return get(`/api/architecture/diagrams/${encodeURIComponent(id)}/versions/${encodeURIComponent(sha)}`)
}
export async function getArchitectureConfig(): Promise<ArchConfig> {
  return get('/api/architecture/config')
}
export async function setArchitectureConfig(v2_enabled: boolean): Promise<ArchConfig> {
  return request('/api/architecture/config', { method: 'POST', body: JSON.stringify({ v2_enabled }) })
}

import { useEffect, useState, type ReactNode } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Workflow, Server, Plug, RefreshCw, Trash2, Plus, Play, Copy, Check, X,
  ShieldCheck, Activity, KeyRound, ChevronDown, AlertTriangle, Loader2,
  ArrowDownLeft, ArrowUpRight, Globe, Radio, Users, Send,
} from 'lucide-react'
import {
  getVaultStatus,
  getMcpServerConfig, setMcpServerConfig, getMcpClients, issueMcpClient, revokeMcpClient,
  getMcpConnections, addMcpConnection, testMcpConnection, refreshMcpConnection,
  setMcpConnectionEnabled, deleteMcpConnection, getMcpTools, setMcpTool, invokeMcpTool,
  getMcpLogs, getMcpApprovals, approveMcp, rejectMcp,
  setMcpOAuth, setMcpTunnel, getA2aCard, setA2aCard, getA2aPeers, addA2aPeer, removeA2aPeer, a2aMessage,
  type McpServerInfo, type McpClient, type McpConnection, type McpExternalTool,
  type McpCallLog, type McpApproval, type A2aCard, type A2aPeer,
} from '../api'
import { useToast } from '../context/ToastProvider'
import { useVaultSession } from '../hooks/useVaultSession'
import VaultUnlockPanel from '../components/VaultUnlockPanel'

// ── shared styles ────────────────────────────────────────────────────────────
const card = 'rounded-xl border border-border bg-surface'
const btn = 'inline-flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1.5 text-xs font-medium text-muted transition-colors hover:border-accent/40 hover:text-text disabled:opacity-50'
const btnPrimary = 'inline-flex items-center justify-center gap-1.5 rounded-md bg-accent/15 px-3 py-1.5 text-xs font-semibold text-accent transition-colors hover:bg-accent/25 disabled:opacity-50'
const input = 'w-full rounded-md border border-border bg-bg px-3 py-2 text-sm text-text outline-none focus:border-accent/50'

function StatusPill({ status }: { status: string | null | undefined }) {
  const s = (status || 'unknown').toLowerCase()
  const map: Record<string, string> = {
    connected: 'bg-success/15 text-success', active: 'bg-success/15 text-success',
    error: 'bg-danger/15 text-danger', revoked: 'bg-danger/15 text-danger',
    disabled: 'bg-muted/15 text-muted', unknown: 'bg-muted/15 text-muted',
    pending: 'bg-warning/15 text-warning',
  }
  return <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold tracking-wide ${map[s] ?? map.unknown}`}>{s}</span>
}

function CopyBtn({ text, label }: { text: string; label?: string }) {
  const [done, setDone] = useState(false)
  return (
    <button onClick={() => { navigator.clipboard.writeText(text); setDone(true); setTimeout(() => setDone(false), 1200) }}
      className={btn} title="Copy">
      {done ? <Check size={12} className="text-success" /> : <Copy size={12} />} {label}
    </button>
  )
}

function Toggle({ on, onClick, disabled }: { on: boolean; onClick: () => void; disabled?: boolean }) {
  return (
    <button onClick={onClick} disabled={disabled}
      className={`relative h-5 w-9 shrink-0 rounded-full transition-colors ${on ? 'bg-accent/70' : 'bg-overlay/10'} disabled:opacity-50`}>
      <span className={`absolute top-0.5 h-4 w-4 rounded-full bg-white transition-transform ${on ? 'translate-x-4' : 'translate-x-0.5'}`} />
    </button>
  )
}

const PERM_CLS: Record<string, string> = {
  allow: 'border-success/40 text-success', ask: 'border-warning/40 text-warning', deny: 'border-danger/40 text-danger',
}

// ── unlock gate ──────────────────────────────────────────────────────────────
// ── modals ───────────────────────────────────────────────────────────────────
function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  return (
    <div className="fixed inset-0 z-[140] flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      <motion.div initial={{ opacity: 0, scale: 0.97, y: 8 }} animate={{ opacity: 1, scale: 1, y: 0 }}
        className={`${card} w-full max-w-md p-5`} onClick={e => e.stopPropagation()}>
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-sm font-bold text-heading">{title}</h3>
          <button onClick={onClose} className="text-muted hover:text-text"><X size={16} /></button>
        </div>
        {children}
      </motion.div>
    </div>
  )
}

function IssueClientModal({ tools, onClose, onDone }: { tools: string[]; onClose: () => void; onDone: () => void }) {
  const [name, setName] = useState('')
  const [all, setAll] = useState(true)
  const [picked, setPicked] = useState<Set<string>>(new Set())
  const [busy, setBusy] = useState(false)
  const [token, setToken] = useState<string | null>(null)
  const toast = useToast().toast

  const issue = async () => {
    setBusy(true)
    try {
      const scopes = all ? ['*'] : [...picked]
      const r = await issueMcpClient(name.trim() || 'client', scopes.length ? scopes : ['*'])
      setToken(r.token); onDone()
    } catch (e) { toast({ kind: 'error', title: 'Could not issue token', detail: (e as Error).message }) }
    finally { setBusy(false) }
  }

  return (
    <Modal title="Issue inbound client token" onClose={onClose}>
      {token ? (
        <div className="space-y-3">
          <p className="text-xs text-muted">Copy this token now — it's shown <b className="text-text">once</b> and only stored hashed.</p>
          <div className="rounded-md border border-accent/30 bg-bg p-2.5 font-mono text-[11px] break-all text-accent">{token}</div>
          <div className="flex justify-end gap-2"><CopyBtn text={token} label="Copy" /><button onClick={onClose} className={btnPrimary}>Done</button></div>
        </div>
      ) : (
        <div className="space-y-3">
          <input value={name} onChange={e => setName(e.target.value)} placeholder="Client name (e.g. Claude Desktop)" className={input} autoFocus />
          <label className="flex items-center gap-2 text-xs text-muted">
            <Toggle on={all} onClick={() => setAll(a => !a)} /> Allow all tools ( * )
          </label>
          {!all && (
            <div className="max-h-40 space-y-1 overflow-y-auto rounded-md border border-border p-2">
              {tools.map(t => (
                <label key={t} className="flex items-center gap-2 text-xs text-text">
                  <input type="checkbox" checked={picked.has(t)}
                    onChange={e => setPicked(p => { const n = new Set(p); e.target.checked ? n.add(t) : n.delete(t); return n })} />
                  {t}
                </label>
              ))}
              {tools.length === 0 && <p className="text-xs text-muted">No exposed tools.</p>}
            </div>
          )}
          <div className="flex justify-end gap-2"><button onClick={onClose} className={btn}>Cancel</button>
            <button onClick={issue} disabled={busy} className={btnPrimary}>{busy ? <Loader2 size={13} className="animate-spin" /> : <KeyRound size={13} />} Issue</button></div>
        </div>
      )}
    </Modal>
  )
}

function AddConnectionModal({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const [name, setName] = useState('')
  const [transport, setTransport] = useState('http')
  const [endpoint, setEndpoint] = useState('')
  const [token, setToken] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const toast = useToast().toast

  const add = async () => {
    setBusy(true); setErr(null)
    try {
      await addMcpConnection({ name: name.trim(), transport, endpoint: endpoint.trim(), token: token.trim() || undefined })
      toast({ kind: 'success', title: 'Connected', detail: name }); onDone(); onClose()
    } catch (e) { setErr((e as Error).message) } finally { setBusy(false) }
  }
  return (
    <Modal title="Add MCP server" onClose={onClose}>
      <div className="space-y-3">
        <input value={name} onChange={e => setName(e.target.value)} placeholder="Name" className={input} autoFocus />
        <div className="flex gap-2">
          <select value={transport} onChange={e => setTransport(e.target.value)} className={`${input} w-32`}>
            <option value="http">HTTP</option><option value="sse">SSE</option><option value="stdio">stdio</option>
          </select>
          <input value={endpoint} onChange={e => setEndpoint(e.target.value)}
            placeholder={transport === 'stdio' ? '["python","server.py"] or command' : 'https://host/mcp'} className={`${input} flex-1`} />
        </div>
        {transport !== 'stdio' && (
          <input value={token} onChange={e => setToken(e.target.value)} placeholder="Bearer token (optional — stored in vault)" className={input} />
        )}
        <p className="text-[11px] text-muted">It's tested on add — if the handshake fails, nothing is saved.</p>
        {err && <p className="text-xs text-danger">{err}</p>}
        <div className="flex justify-end gap-2"><button onClick={onClose} className={btn}>Cancel</button>
          <button onClick={add} disabled={busy || !name || !endpoint} className={btnPrimary}>{busy ? <Loader2 size={13} className="animate-spin" /> : <Plus size={13} />} Add & test</button></div>
      </div>
    </Modal>
  )
}

function TryItModal({ tool, onClose }: { tool: McpExternalTool; onClose: () => void }) {
  const [argsText, setArgsText] = useState('{\n  \n}')
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<string | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const run = async () => {
    setBusy(true); setErr(null); setResult(null)
    let args: Record<string, unknown> = {}
    try { args = argsText.trim() ? JSON.parse(argsText) : {} } catch { setErr('Arguments must be valid JSON'); setBusy(false); return }
    try {
      const r = await invokeMcpTool(tool.id, args)
      if (r.pending) setResult(`⏳ ${r.message || 'Pending approval'}`)
      else if (r.ok) setResult(r.content || '(empty result)')
      else setErr(r.error || 'Call failed')
    } catch (e) { setErr((e as Error).message) } finally { setBusy(false) }
  }
  return (
    <Modal title={`Try: ${tool.name}`} onClose={onClose}>
      <div className="space-y-3">
        <div className="text-[11px] text-muted">Arguments (JSON)</div>
        <textarea value={argsText} onChange={e => setArgsText(e.target.value)} rows={5}
          className={`${input} font-mono text-xs`} spellCheck={false} />
        {err && <p className="text-xs text-danger">{err}</p>}
        {result && <pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded-md border border-border bg-bg p-2.5 text-xs text-text">{result}</pre>}
        <div className="flex justify-end gap-2"><button onClick={onClose} className={btn}>Close</button>
          <button onClick={run} disabled={busy} className={btnPrimary}>{busy ? <Loader2 size={13} className="animate-spin" /> : <Play size={13} />} Run</button></div>
      </div>
    </Modal>
  )
}

// ── connection card ──────────────────────────────────────────────────────────
function ConnectionCard({ conn, tools, reload }: { conn: McpConnection; tools: McpExternalTool[]; reload: () => void }) {
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState<string | null>(null)
  const [tryTool, setTryTool] = useState<McpExternalTool | null>(null)
  const toast = useToast().toast

  const act = async (k: string, fn: () => Promise<unknown>, okMsg?: string) => {
    setBusy(k)
    try { await fn(); if (okMsg) toast({ kind: 'success', title: okMsg }); reload() }
    catch (e) { toast({ kind: 'error', title: 'Failed', detail: (e as Error).message }) } finally { setBusy(null) }
  }
  return (
    <div className={card}>
      <div className="flex items-center gap-3 p-3">
        <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-bg text-muted"><Plug size={16} /></span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="truncate text-sm font-semibold text-heading">{conn.name}</span>
            <StatusPill status={conn.status} />
            <span className="rounded bg-bg px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-muted">{conn.transport}</span>
          </div>
          <div className="truncate text-[11px] text-muted">{conn.tools_count} tools · {conn.endpoint}</div>
        </div>
        <Toggle on={!!conn.enabled} onClick={() => act('en', () => setMcpConnectionEnabled(conn.id, !conn.enabled))} />
        <button className={btn} disabled={busy === 'test'} onClick={() => act('test', () => testMcpConnection(conn.id), 'Tested')} title="Test">
          {busy === 'test' ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
        </button>
        <button className={btn} onClick={() => act('del', () => deleteMcpConnection(conn.id), 'Removed')} title="Delete (kill-switch)"><Trash2 size={12} /></button>
        <button className={btn} onClick={() => setOpen(o => !o)}><ChevronDown size={14} className={`transition-transform ${open ? 'rotate-180' : ''}`} /></button>
      </div>
      <AnimatePresence>
        {open && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="overflow-hidden">
            <div className="space-y-1 border-t border-border/60 p-3">
              {tools.length === 0 && <p className="text-xs text-muted">No tools discovered. Try refresh.</p>}
              {tools.map(t => (
                <div key={t.id} className="flex items-center gap-2 rounded-md px-2 py-1.5 hover:bg-overlay/5">
                  <span className="flex-1 truncate text-xs text-text">{t.name}</span>
                  <select value={t.permission} onChange={e => act('perm', () => setMcpTool(t.id, { permission: e.target.value }))}
                    className={`rounded border bg-bg px-1.5 py-1 text-[11px] ${PERM_CLS[t.permission]}`}>
                    <option value="allow">allow</option><option value="ask">ask</option><option value="deny">deny</option>
                  </select>
                  <Toggle on={!!t.enabled} onClick={() => act('ten', () => setMcpTool(t.id, { enabled: !t.enabled }))} />
                  <button className={btn} onClick={() => setTryTool(t)}><Play size={11} /> Try</button>
                </div>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
      {tryTool && <TryItModal tool={tryTool} onClose={() => setTryTool(null)} />}
    </div>
  )
}

// ── OAuth config ─────────────────────────────────────────────────────────────
function OAuthCard({ info, reload }: { info: McpServerInfo; reload: () => void }) {
  const o = info.oauth
  const [enabled, setEnabled] = useState(o.enabled)
  const [issuer, setIssuer] = useState(o.issuer || '')
  const [audience, setAudience] = useState(o.audience || '')
  const [secret, setSecret] = useState('')
  const [busy, setBusy] = useState(false)
  const toast = useToast().toast
  const save = async () => {
    setBusy(true)
    try {
      await setMcpOAuth({ enabled, issuer: issuer.trim() || undefined, audience: audience.trim() || undefined, secret: secret.trim() || undefined })
      setSecret(''); reload(); toast({ kind: 'success', title: 'OAuth saved' })
    } catch (e) { toast({ kind: 'error', title: 'Failed', detail: (e as Error).message }) } finally { setBusy(false) }
  }
  return (
    <div className={`${card} p-4`}>
      <div className="mb-3 flex items-center justify-between">
        <span className="flex items-center gap-2 text-sm font-semibold text-heading"><ShieldCheck size={15} className="text-accent" /> OAuth 2.1 (JWT)</span>
        <Toggle on={enabled} onClick={() => setEnabled(e => !e)} />
      </div>
      <p className="mb-3 text-[11px] text-muted">Accept OAuth access tokens alongside issued tokens. Verified with an HS256 signing key (stored in the vault).</p>
      <div className="grid gap-2 sm:grid-cols-2">
        <input value={issuer} onChange={e => setIssuer(e.target.value)} placeholder="Issuer (iss)" className={input} />
        <input value={audience} onChange={e => setAudience(e.target.value)} placeholder="Audience (aud)" className={input} />
      </div>
      <input type="password" value={secret} onChange={e => setSecret(e.target.value)} placeholder="HS256 signing key (blank = keep current)" className={`${input} mt-2`} />
      <div className="mt-3 flex justify-end"><button onClick={save} disabled={busy} className={btnPrimary}>{busy ? <Loader2 size={13} className="animate-spin" /> : <Check size={13} />} Save OAuth</button></div>
    </div>
  )
}

// ── tunnel / internet exposure ───────────────────────────────────────────────
function TunnelCard({ info, reload }: { info: McpServerInfo; reload: () => void }) {
  const t = info.tunnel
  const [busy, setBusy] = useState(false)
  const toast = useToast().toast
  const act = async (action: 'start' | 'stop') => {
    setBusy(true)
    try {
      const r = await setMcpTunnel(action)
      if (r.ok) toast({ kind: 'success', title: action === 'start' ? 'Tunnel up' : 'Tunnel stopped', detail: r.note })
      else toast({ kind: 'error', title: 'Tunnel', detail: r.error })
      reload()
    } catch (e) { toast({ kind: 'error', title: 'Failed', detail: (e as Error).message }) } finally { setBusy(false) }
  }
  return (
    <div className={`${card} p-4`}>
      <div className="mb-2 flex items-center justify-between">
        <span className="flex items-center gap-2 text-sm font-semibold text-heading"><Globe size={15} className="text-accent" /> Internet exposure</span>
        <StatusPill status={t.running ? 'connected' : info.exposed ? 'pending' : 'disabled'} />
      </div>
      {!t.available ? (
        <p className="text-[11px] text-muted">Install <code className="text-text">cloudflared</code> to expose TOBI's MCP server via a secure quick tunnel.</p>
      ) : t.running && t.public_url ? (
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <code className="flex-1 truncate rounded-md border border-border bg-bg px-2.5 py-1.5 text-xs text-accent">{t.mcp_url || `${t.public_url}/mcp`}</code>
            <CopyBtn text={t.mcp_url || `${t.public_url}/mcp`} />
          </div>
          <button onClick={() => act('stop')} disabled={busy} className={btn}>{busy ? <Loader2 size={12} className="animate-spin" /> : <X size={12} />} Stop tunnel</button>
        </div>
      ) : (
        <button onClick={() => act('start')} disabled={busy} className={btnPrimary}>{busy ? <Loader2 size={13} className="animate-spin" /> : <Radio size={13} />} Start tunnel</button>
      )}
      {info.exposed && <p className="mt-2 text-[10px] text-warning">Exposed mode relaxes the Host allowlist — restart the server to fully apply.</p>}
    </div>
  )
}

// ── A2A tab ──────────────────────────────────────────────────────────────────
function A2aTab({ selfCard, peers, reload }: { selfCard: A2aCard | null; peers: A2aPeer[]; reload: () => void }) {
  const [name, setName] = useState(selfCard?.name || '')
  const [desc, setDesc] = useState(selfCard?.description || '')
  const [url, setUrl] = useState('')
  const [busy, setBusy] = useState(false)
  const [msgPeer, setMsgPeer] = useState<A2aPeer | null>(null)
  const toast = useToast().toast
  useEffect(() => { setName(selfCard?.name || ''); setDesc(selfCard?.description || '') }, [selfCard])
  const cardUrl = `${window.location.origin}/.well-known/agent.json`

  const saveCard = async () => {
    setBusy(true)
    try { await setA2aCard({ name, description: desc }); reload(); toast({ kind: 'success', title: 'Agent card saved' }) }
    catch (e) { toast({ kind: 'error', title: 'Failed', detail: (e as Error).message }) } finally { setBusy(false) }
  }
  const addPeer = async () => {
    setBusy(true)
    try { await addA2aPeer(url.trim()); setUrl(''); reload(); toast({ kind: 'success', title: 'Peer added' }) }
    catch (e) { toast({ kind: 'error', title: 'Could not add peer', detail: (e as Error).message }) } finally { setBusy(false) }
  }
  return (
    <div className="space-y-4">
      <div className={`${card} p-4`}>
        <div className="mb-3 text-sm font-semibold text-heading">TOBI's agent card</div>
        <div className="mb-3 flex items-center gap-2">
          <code className="flex-1 truncate rounded-md border border-border bg-bg px-2.5 py-1.5 text-xs text-accent">{cardUrl}</code>
          <CopyBtn text={cardUrl} label="Copy" />
        </div>
        <div className="grid gap-2 sm:grid-cols-2">
          <input value={name} onChange={e => setName(e.target.value)} placeholder="Agent name" className={input} />
          <input value={desc} onChange={e => setDesc(e.target.value)} placeholder="Description" className={input} />
        </div>
        {selfCard?.skills?.length ? (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {selfCard.skills.map(s => <span key={s.id} className="rounded-full bg-bg px-2 py-0.5 text-[10px] text-muted">{s.name}</span>)}
          </div>
        ) : null}
        <div className="mt-3 flex justify-end"><button onClick={saveCard} disabled={busy} className={btnPrimary}><Check size={13} /> Save card</button></div>
      </div>

      <div className={`${card} p-4`}>
        <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-heading"><Users size={15} className="text-accent" /> Peer agents</div>
        <div className="mb-3 flex gap-2">
          <input value={url} onChange={e => setUrl(e.target.value)} placeholder="Peer URL (its /.well-known/agent.json is fetched)" className={`${input} flex-1`} />
          <button onClick={addPeer} disabled={busy || !url} className={btnPrimary}><Plus size={13} /> Add</button>
        </div>
        <div className="space-y-1">
          {peers.map(p => (
            <div key={p.id} className="flex items-center gap-2 rounded-md px-2 py-1.5 hover:bg-overlay/5">
              <Radio size={13} className="text-muted" />
              <span className="text-xs font-medium text-text">{p.name}</span>
              <span className="truncate text-[11px] text-muted">{p.skills.join(', ')}</span>
              <button className={`${btn} ml-auto`} onClick={() => setMsgPeer(p)}><Send size={11} /> Message</button>
              <button className={btn} onClick={() => removeA2aPeer(p.id).then(reload)}><Trash2 size={11} /></button>
            </div>
          ))}
          {!peers.length && <p className="text-xs text-muted">No peers. Add another agent's URL to discover its card.</p>}
        </div>
      </div>
      {msgPeer && <MessagePeerModal peer={msgPeer} onClose={() => setMsgPeer(null)} />}
    </div>
  )
}

// (style alias removed — A2aTab uses the shared `card` constant directly)

function MessagePeerModal({ peer, onClose }: { peer: A2aPeer; onClose: () => void }) {
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [out, setOut] = useState<string | null>(null)
  const send = async () => {
    setBusy(true); setOut(null)
    try { const r = await a2aMessage(peer.id, text); setOut(r.ok ? (r.response || 'sent') : (r.error || `status ${r.status}`)) }
    catch (e) { setOut((e as Error).message) } finally { setBusy(false) }
  }
  return (
    <Modal title={`Message ${peer.name}`} onClose={onClose}>
      <div className="space-y-3">
        <textarea value={text} onChange={e => setText(e.target.value)} rows={3} placeholder="Message…" className={input} />
        {out && <pre className="max-h-40 overflow-auto whitespace-pre-wrap rounded-md border border-border bg-bg p-2 text-xs text-text">{out}</pre>}
        <div className="flex justify-end gap-2"><button onClick={onClose} className={btn}>Close</button>
          <button onClick={send} disabled={busy || !text} className={btnPrimary}>{busy ? <Loader2 size={13} className="animate-spin" /> : <Send size={13} />} Send</button></div>
      </div>
    </Modal>
  )
}

// ── main page ────────────────────────────────────────────────────────────────
export default function Mcp() {
  const hasSession = useVaultSession()
  const [gate, setGate] = useState<'loading' | 'setup' | 'locked' | 'ready' | 'error'>('loading')
  const [gateError, setGateError] = useState('')
  const [tab, setTab] = useState<'server' | 'clients' | 'a2a' | 'activity'>('server')
  const [server, setServer] = useState<McpServerInfo | null>(null)
  const [clients, setClients] = useState<McpClient[]>([])
  const [connections, setConnections] = useState<McpConnection[]>([])
  const [extTools, setExtTools] = useState<McpExternalTool[]>([])
  const [logs, setLogs] = useState<McpCallLog[]>([])
  const [logDir, setLogDir] = useState<'all' | 'in' | 'out'>('all')
  const [approvals, setApprovals] = useState<McpApproval[]>([])
  const [a2aCard, setA2aCardState] = useState<A2aCard | null>(null)
  const [a2aPeers, setA2aPeers] = useState<A2aPeer[]>([])
  const [showIssue, setShowIssue] = useState(false)
  const [showAdd, setShowAdd] = useState(false)
  const toast = useToast().toast

  const loadServer = () => { getMcpServerConfig().then(setServer).catch(() => {}); getMcpClients().then(r => setClients(r.clients)).catch(() => {}) }
  const loadClients = () => {
    getMcpConnections().then(r => setConnections(r.connections)).catch(() => {})
    getMcpTools().then(r => setExtTools(r.tools)).catch(() => {})
  }
  const loadApprovals = () => getMcpApprovals('pending').then(r => setApprovals(r.approvals)).catch(() => {})
  const loadActivity = () => getMcpLogs(120, logDir === 'all' ? undefined : logDir).then(r => setLogs(r.logs)).catch(() => {})
  const loadA2a = () => {
    getA2aCard().then(r => setA2aCardState(r.card)).catch(() => {})
    getA2aPeers().then(r => setA2aPeers(r.peers)).catch(() => {})
  }

  const probe = () => {
    getMcpServerConfig().then(s => { setServer(s); setGateError(''); setGate('ready'); loadServer(); loadClients(); loadApprovals() })
      .catch((e: { status?: number; message?: string }) => {
        if (e?.status === 401) setGate('locked')
        else { setGateError(e?.message || 'MCP data is unavailable.'); setGate('error') }
      })
  }
  useEffect(() => {
    getVaultStatus().then(s => {
      if (!s.setup) setGate('setup')
      else if (!hasSession) setGate('locked')
      else probe()
    }).catch((e: Error) => { setGateError(e.message); setGate('error') })
  }, [hasSession])
  useEffect(() => { if (gate === 'ready' && tab === 'activity') loadActivity() }, [gate, tab, logDir])
  useEffect(() => { if (gate === 'ready' && tab === 'a2a') loadA2a() }, [gate, tab])

  if (gate === 'loading') return <div className="flex h-full items-center justify-center text-muted"><Loader2 className="animate-spin" /></div>
  if (gate === 'setup') return (
    <div className="flex h-full items-center justify-center p-6 text-center">
      <div className={`${card} max-w-sm p-6`}>
        <KeyRound size={22} className="mx-auto mb-2 text-accent" />
        <h2 className="text-base font-bold text-heading">Vault not set up</h2>
        <p className="mt-1 text-xs text-muted">MCP credentials live in the encrypted vault. Set it up on the Integrations page first.</p>
        <a href="/integrations" className={`${btnPrimary} mt-4`}>Go to Integrations</a>
      </div>
    </div>
  )
  if (gate === 'locked') return <VaultUnlockPanel title="Unlock MCP" detail="One unlock authorizes protected Mission Control tools in this browser tab." />
  if (gate === 'error') return <div className="flex h-full items-center justify-center p-6"><div className="w-full max-w-md border-l-2 border-danger bg-danger/5 px-4 py-4"><div className="flex items-start gap-3"><AlertTriangle size={17} className="mt-0.5 shrink-0 text-danger" /><div><div className="text-sm font-semibold text-heading">MCP data unavailable</div><p className="mt-1 text-xs leading-5 text-muted">{gateError}</p><button onClick={probe} className={`${btn} mt-3`}><RefreshCw size={13} /> Retry</button></div></div></div></div>

  const mountUrl = server?.mount ? `${window.location.origin}${server.mount}` : null
  const cfg = server?.config
  const rateLimit = (() => { try { return JSON.parse(cfg?.rate_limit_json || '{}').per_minute ?? 60 } catch { return 60 } })()

  const setEnabled = async (en: boolean) => {
    try { await setMcpServerConfig({ enabled: en }); loadServer(); toast({ kind: 'success', title: en ? 'Server enabled' : 'Server disabled' }) }
    catch (e) { toast({ kind: 'error', title: 'Failed', detail: (e as Error).message }) }
  }
  const decide = async (id: number, ok: boolean) => {
    try { await (ok ? approveMcp(id) : rejectMcp(id)); loadApprovals(); toast({ kind: ok ? 'success' : 'info', title: ok ? 'Approved' : 'Rejected' }) }
    catch (e) { toast({ kind: 'error', title: 'Failed', detail: (e as Error).message }) }
  }

  return (
    <div className="space-y-5 p-4 md:p-6">
      {/* header */}
      <div className="flex items-center gap-3">
        <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-accent/15 text-accent"><Workflow size={20} /></span>
        <div className="flex-1">
          <h1 className="text-xl font-bold text-heading">MCP Hub</h1>
          <p className="text-xs text-muted">TOBI as an MCP server (others connect in) and client (TOBI connects out).</p>
        </div>
        {cfg && <Toggle on={!!cfg.enabled} onClick={() => setEnabled(!cfg.enabled)} />}
      </div>

      {/* pending approvals banner */}
      {approvals.length > 0 && (
        <div className={`${card} border-warning/40 p-3`}>
          <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-warning"><AlertTriangle size={14} /> {approvals.length} pending approval{approvals.length > 1 ? 's' : ''}</div>
          <div className="space-y-1.5">
            {approvals.map(a => (
              <div key={a.id} className="flex items-center gap-2 rounded-md bg-bg/50 px-2.5 py-1.5">
                <span className="flex-1 truncate text-xs text-text"><b>{a.tool}</b> <span className="text-muted">· {a.client || 'agent'} · {a.args}</span></span>
                <button className={`${btn} border-success/40 text-success`} onClick={() => decide(a.id, true)}><Check size={12} /> Approve</button>
                <button className={`${btn} border-danger/40 text-danger`} onClick={() => decide(a.id, false)}><X size={12} /> Reject</button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* tabs */}
      <div className="flex gap-1 border-b border-border">
        {([['server', 'Server', Server], ['clients', 'Clients (outbound)', Plug], ['a2a', 'A2A', Users], ['activity', 'Activity', Activity]] as const).map(([k, label, Icon]) => (
          <button key={k} onClick={() => setTab(k)}
            className={`flex items-center gap-1.5 border-b-2 px-3 py-2 text-xs font-semibold transition-colors ${tab === k ? 'border-accent text-accent' : 'border-transparent text-muted hover:text-text'}`}>
            <Icon size={13} /> {label}
          </button>
        ))}
      </div>

      {/* ── SERVER TAB ── */}
      {tab === 'server' && (
        <div className="space-y-4">
          <div className={`${card} p-4`}>
            <div className="mb-3 text-sm font-semibold text-heading">Inbound endpoint</div>
            {mountUrl ? (
              <div className="flex items-center gap-2">
                <code className="flex-1 truncate rounded-md border border-border bg-bg px-3 py-2 text-xs text-accent">{mountUrl}</code>
                <CopyBtn text={mountUrl} label="Copy URL" />
              </div>
            ) : <p className="text-xs text-danger">MCP server not mounted.</p>}
            <div className="mt-3 flex flex-wrap gap-4 text-xs text-muted">
              <span>Transport: <b className="text-text">Streamable HTTP</b></span>
              <span>Auth: <b className="text-text">Bearer token</b> · OAuth 2.1 <span className="text-muted/60">(soon)</span></span>
              <span>Rate limit: <b className="text-text">{rateLimit}/min</b></span>
            </div>
          </div>

          <div className={`${card} p-4`}>
            <div className="mb-2 text-sm font-semibold text-heading">Exposed tools</div>
            <div className="space-y-1">
              {server?.tools.map(t => (
                <div key={t.name} className="flex items-start gap-2 rounded-md px-2 py-1.5 hover:bg-overlay/5">
                  <span className="mt-0.5 text-accent"><ShieldCheck size={13} /></span>
                  <div className="min-w-0 flex-1">
                    <span className="text-xs font-medium text-text">{t.name}</span>
                    {t.sensitive && <span className="ml-2 rounded bg-warning/15 px-1.5 py-0.5 text-[9px] font-semibold text-warning">APPROVAL</span>}
                    <div className="truncate text-[11px] text-muted">{t.description}</div>
                  </div>
                </div>
              ))}
              {!server?.tools.length && <p className="text-xs text-muted">No exposed tools.</p>}
            </div>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            {server && <OAuthCard info={server} reload={loadServer} />}
            {server && <TunnelCard info={server} reload={loadServer} />}
          </div>

          <div className={`${card} p-4`}>
            <div className="mb-2 flex items-center justify-between">
              <span className="text-sm font-semibold text-heading">Inbound clients</span>
              <button className={btnPrimary} onClick={() => setShowIssue(true)}><Plus size={13} /> Issue token</button>
            </div>
            <div className="space-y-1">
              {clients.map(c => (
                <div key={c.id} className="flex items-center gap-2 rounded-md px-2 py-1.5 hover:bg-overlay/5">
                  <KeyRound size={13} className="text-muted" />
                  <span className="text-xs font-medium text-text">{c.name}</span>
                  <StatusPill status={c.status} />
                  <span className="truncate text-[11px] text-muted">{c.scopes.join(', ')}</span>
                  <span className="ml-auto text-[10px] text-muted">{c.last_seen ? `seen ${new Date(c.last_seen).toLocaleString('en-GB')}` : 'never used'}</span>
                  <button className={btn} onClick={() => revokeMcpClient(c.id).then(loadServer)}><Trash2 size={11} /></button>
                </div>
              ))}
              {!clients.length && <p className="text-xs text-muted">No clients yet. Issue a token to let an external agent connect.</p>}
            </div>
          </div>
        </div>
      )}

      {/* ── CLIENTS TAB ── */}
      {tab === 'clients' && (
        <div className="space-y-3">
          <div className="flex justify-end"><button className={btnPrimary} onClick={() => setShowAdd(true)}><Plus size={13} /> Add server</button></div>
          {connections.map(conn => (
            <ConnectionCard key={conn.id} conn={conn} reload={loadClients}
              tools={extTools.filter(t => t.source === String(conn.id))} />
          ))}
          {!connections.length && (
            <div className={`${card} p-8 text-center text-sm text-muted`}>
              No outbound connections. Add an external MCP server to use its tools.
            </div>
          )}
        </div>
      )}

      {/* ── A2A TAB ── */}
      {tab === 'a2a' && <A2aTab selfCard={a2aCard} peers={a2aPeers} reload={loadA2a} />}

      {/* ── ACTIVITY TAB ── */}
      {tab === 'activity' && (
        <div className={`${card} overflow-hidden`}>
          <div className="flex items-center gap-1 border-b border-border p-2">
            {(['all', 'in', 'out'] as const).map(d => (
              <button key={d} onClick={() => setLogDir(d)}
                className={`rounded px-2.5 py-1 text-[11px] font-medium ${logDir === d ? 'bg-accent/15 text-accent' : 'text-muted hover:text-text'}`}>
                {d === 'all' ? 'All' : d === 'in' ? 'Inbound' : 'Outbound'}
              </button>
            ))}
            <button onClick={loadActivity} className={`${btn} ml-auto`}><RefreshCw size={12} /> Refresh</button>
          </div>
          <div className="max-h-[60vh] overflow-y-auto">
            {logs.map(l => (
              <div key={l.id} className="flex items-center gap-2 border-b border-border/40 px-3 py-2 text-xs">
                <span className={l.direction === 'in' ? 'text-accent' : 'text-success'}>{l.direction === 'in' ? <ArrowDownLeft size={13} /> : <ArrowUpRight size={13} />}</span>
                <span className="w-36 shrink-0 truncate text-muted">{new Date(l.ts).toLocaleString('en-GB')}</span>
                <span className="w-28 shrink-0 truncate text-text">{l.peer || '—'}</span>
                <span className="flex-1 truncate text-text">{l.tool || '—'}</span>
                <StatusPill status={l.status} />
                {l.latency_ms != null && <span className="w-14 shrink-0 text-right text-[10px] text-muted">{l.latency_ms}ms</span>}
              </div>
            ))}
            {!logs.length && <p className="px-3 py-8 text-center text-xs text-muted">No calls logged yet.</p>}
          </div>
        </div>
      )}

      {showIssue && <IssueClientModal tools={(server?.tools || []).map(t => t.name)} onClose={() => setShowIssue(false)} onDone={loadServer} />}
      {showAdd && <AddConnectionModal onClose={() => setShowAdd(false)} onDone={loadClients} />}
    </div>
  )
}

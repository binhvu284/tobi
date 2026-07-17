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

import {
  card, btn, btnPrimary, input, PERM_CLS,
  StatusPill, CopyBtn, Toggle, Modal, IssueClientModal, AddConnectionModal,
  TryItModal, ConnectionCard, OAuthCard, TunnelCard, A2aTab, MessagePeerModal,
} from '../components/mcp/McpParts'
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

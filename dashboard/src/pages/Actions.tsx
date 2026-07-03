import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { RefreshCw, History, CheckCircle2, XCircle, Clock, AlertTriangle, ShieldAlert, MessagesSquare, Bot, Smartphone } from 'lucide-react'
import { getConductorActions, getConductorStatus, type ConductorAction, type ConductorStatus } from '../api'
import { AmbientField, Stagger, StaggerItem, CountUp } from '../components/motion'
import PageLoader from '../components/PageLoader'

const RISK: Record<string, string> = {
  read: 'bg-muted/15 text-muted', low: 'bg-success/15 text-success',
  medium: 'bg-warning/15 text-warning', high: 'bg-danger/15 text-danger',
}
const STATUS: Record<string, { cls: string; Icon: typeof CheckCircle2 }> = {
  executed: { cls: 'text-success', Icon: CheckCircle2 },
  proposed: { cls: 'text-warning', Icon: Clock },
  rejected: { cls: 'text-muted', Icon: XCircle },
  failed: { cls: 'text-danger', Icon: AlertTriangle },
}

function when(s?: string | null) {
  if (!s) return '—'
  try { return new Date(s).toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) }
  catch { return s }
}

export default function Actions() {
  const [data, setData] = useState<{ count: number; actions: ConductorAction[] } | null>(null)
  const [status, setStatus] = useState<ConductorStatus | null>(null)
  const [loading, setLoading] = useState(true)

  const load = () => {
    getConductorActions(100).then(setData).catch(() => setData({ count: 0, actions: [] })).finally(() => setLoading(false))
    getConductorStatus().then(setStatus).catch(() => {})
  }
  useEffect(() => { load(); const t = setInterval(load, 20000); return () => clearInterval(t) }, [])

  if (loading && !data) return <PageLoader preset="control" />

  const actions = data?.actions ?? []
  const executed = actions.filter(a => a.status === 'executed').length
  const proposed = actions.filter(a => a.status === 'proposed').length

  return (
    <div className="relative space-y-4 p-6">
      <AmbientField tone="rgb(var(--accent))" />

      <div className="flex items-center justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-bold text-heading"><History size={20} /> TOBI Actions</h1>
          <p className="mt-1 text-xs text-muted">
            Everything TOBI has done or proposed by conversation — what, when, and the result.
            {status && <span className="ml-1 text-accent">· {status.phase}</span>}
          </p>
        </div>
        <button onClick={load} className="flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-xs text-muted transition-colors hover:text-text">
          <RefreshCw size={13} /> Refresh
        </button>
      </div>

      <div className="grid grid-cols-3 gap-3">
        {[
          { label: 'Total actions', val: actions.length, c: 'text-accent' },
          { label: 'Executed', val: executed, c: 'text-success' },
          { label: 'Awaiting confirm', val: proposed, c: proposed ? 'text-warning' : 'text-muted' },
        ].map(k => (
          <div key={k.label} className="rounded-xl border border-border bg-surface p-4">
            <div className="text-xs text-muted">{k.label}</div>
            <div className={`text-2xl font-bold ${k.c}`}><CountUp value={k.val} /></div>
          </div>
        ))}
      </div>

      {actions.length === 0 ? (
        <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-border py-16 text-muted">
          <Bot size={36} className="opacity-40" />
          <div className="text-sm">No actions yet.</div>
          <Link to="/chat" className="flex items-center gap-1.5 text-sm text-accent hover:underline">
            <MessagesSquare size={14} /> Ask TOBI to do something
          </Link>
        </div>
      ) : (
        <Stagger className="overflow-hidden rounded-xl border border-border bg-surface" step={0.025}>
          {actions.map(a => {
            const st = STATUS[a.status] ?? STATUS.proposed
            const result = a.result as { error?: string } | null | undefined
            return (
              <StaggerItem key={a.id} className="flex items-start gap-3 border-b border-border/60 px-4 py-3 last:border-b-0">
                <st.Icon size={16} className={`mt-0.5 shrink-0 ${st.cls}`} />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm text-text">{a.summary}</span>
                    <span className={`rounded-full px-1.5 py-0.5 text-[10px] font-semibold uppercase ${RISK[a.risk] ?? RISK.read}`}>{a.risk}</span>
                    <span className="flex items-center gap-1 text-[10px] text-muted">
                      {a.surface === 'telegram' ? <Smartphone size={10} /> : <MessagesSquare size={10} />}{a.surface}
                    </span>
                    {a.status === 'proposed' && <span className="flex items-center gap-1 text-[10px] text-warning"><ShieldAlert size={10} /> awaiting confirm</span>}
                  </div>
                  <div className="mt-0.5 font-mono text-[11px] text-muted">
                    {a.tool} · {a.status} · {when(a.executed_at || a.created_at)}
                    {result?.error && <span className="text-danger"> · {result.error}</span>}
                  </div>
                </div>
              </StaggerItem>
            )
          })}
        </Stagger>
      )}
    </div>
  )
}

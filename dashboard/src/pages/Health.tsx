import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { RefreshCw, Activity, AlertTriangle, CheckCircle2, Database, Server, Loader2 } from 'lucide-react'
import Logo from '../components/Logo'
import HealthBar from '../components/HealthBar'
import PageLoader from '../components/PageLoader'
import {
  getHealth, runDeepTest,
  type HealthReport, type DeepTestReport, type LivenessCheck,
} from '../api'

const OVERALL = {
  healthy: { label: 'All systems healthy', cls: 'border-success/40 bg-success/10 text-success', dot: 'bg-success' },
  degraded: { label: 'Degraded — needs a look', cls: 'border-warning/40 bg-warning/10 text-warning', dot: 'bg-warning' },
  issue: { label: 'Issue detected', cls: 'border-danger/40 bg-danger/10 text-danger', dot: 'bg-danger' },
} as const

// Friendly labels + which keys map to a brand <Logo>.
const SERVICE_LABEL: Record<string, string> = {
  telegram: 'Telegram', openrouter: 'OpenRouter', anthropic: 'Claude', openai: 'OpenAI',
  tavily: 'Tavily', notion: 'Notion', github: 'GitHub', google: 'Google',
  vercel: 'Vercel', supabase: 'Supabase',
}

const ACTIVITY_LABEL: Record<string, string> = {
  last_conversation: 'Last conversation',
  last_task_completed: 'Last task completed',
  last_lesson: 'Last lesson recorded',
  last_strategy_ceo: 'Last CEO strategy',
  last_report: 'Last report',
}

function Dot({ ok }: { ok: boolean }) {
  return <span className={`inline-block h-2 w-2 rounded-full ${ok ? 'bg-success' : 'bg-danger'}`} />
}

function Section({ title, icon, children, hint }: {
  title: string; icon: React.ReactNode; children: React.ReactNode; hint?: string
}) {
  return (
    <div className="rounded-lg border border-border bg-surface p-5">
      <div className="mb-1 flex items-center gap-2 text-sm font-semibold text-heading">
        {icon}{title}
      </div>
      {hint && <div className="mb-3 text-xs text-muted">{hint}</div>}
      {children}
    </div>
  )
}

export default function Health() {
  const [health, setHealth] = useState<HealthReport | null>(null)
  const [updated, setUpdated] = useState<string>('')
  const [deep, setDeep] = useState<DeepTestReport | null>(null)
  const [deepLoading, setDeepLoading] = useState(false)

  const load = async () => {
    try {
      const h = await getHealth()
      setHealth(h)
      setUpdated(new Date().toLocaleTimeString('en-GB'))
    } catch {
      /* leave previous state; banner stays */
    }
  }

  useEffect(() => {
    load()
    const t = setInterval(load, 30000)
    return () => clearInterval(t)
  }, [])

  const onDeepTest = async () => {
    setDeepLoading(true)
    try {
      setDeep(await runDeepTest())
    } catch {
      setDeep(null)
    } finally {
      setDeepLoading(false)
    }
  }

  // Re-run the full evaluation: refresh the health snapshot AND live-test every API.
  const runFull = async () => { await load(); await onDeepTest() }

  if (!health) {
    return <PageLoader preset="health" />
  }

  const overall = OVERALL[health.overall]
  const upChecks = Object.entries(health.up)
  const configured = Object.entries(health.configured)
  const activity = Object.entries(health.activity)

  return (
    <div className="space-y-4 p-6">
      {/* Header + overall banner */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-bold text-heading">
            <Activity size={20} /> Health
          </h1>
          <p className="mt-1 text-xs text-muted">Live diagnostics — where Tobi is healthy and where to look if not.</p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={runFull} disabled={deepLoading}
            className="flex items-center gap-1.5 rounded-lg border border-accent/40 bg-accent/10 px-3 py-1.5 text-xs font-medium text-accent transition-colors hover:bg-accent/20 disabled:opacity-50">
            {deepLoading ? <Loader2 size={13} className="animate-spin" /> : <Activity size={13} />}
            {deepLoading ? 'Checking all APIs…' : 'Run full health check'}
          </button>
          <button onClick={load} className="flex items-center gap-1.5 rounded border border-border px-3 py-1.5 text-xs text-muted transition-colors hover:text-text">
            <RefreshCw size={13} /> {updated && `Updated ${updated}`}
          </button>
        </div>
      </div>

      {/* Overall health hero — the HP bar */}
      <motion.div
        initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
        className={`rounded-xl border p-5 ${overall.cls}`}
      >
        <div className="mb-3 flex items-center gap-2.5">
          <span className="relative flex h-3 w-3">
            <span className={`absolute inline-flex h-full w-full animate-ping rounded-full opacity-60 ${overall.dot}`} />
            <span className={`relative inline-flex h-3 w-3 rounded-full ${overall.dot}`} />
          </span>
          <span className="text-sm font-semibold uppercase tracking-wider">Overall health · {overall.label}</span>
        </div>

        <HealthBar score={health.score} size="lg" />

        <div className="mt-3 text-xs">
          {health.score_notes.length === 0 ? (
            <span className="text-muted">All systems nominal — nothing pulling health down.</span>
          ) : (
            <ul className="space-y-1">
              {health.score_notes.map((n, i) => (
                <li key={i} className="flex items-start gap-1.5 text-muted">
                  <span className="text-warning">▾</span>
                  <span>{n}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </motion.div>

      {/* Liveness */}
      <Section title="Liveness" icon={<Server size={15} className="text-accent" />}
        hint="Verifiable up/down checks — red here means something is actually broken.">
        <div className="grid gap-3 sm:grid-cols-2">
          {upChecks.map(([key, c]: [string, LivenessCheck]) => (
            <div key={key} className="flex items-start gap-3 rounded border border-border bg-bg p-3">
              {key === 'database' ? <Database size={16} className="mt-0.5 text-muted" /> : <Server size={16} className="mt-0.5 text-muted" />}
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <Dot ok={c.ok} />
                  <span className="text-sm font-medium text-text capitalize">{key.replace('_', ' ')}</span>
                </div>
                <div className="mt-0.5 break-words text-xs text-muted">{c.detail}</div>
              </div>
            </div>
          ))}
        </div>
      </Section>

      {/* Configured services */}
      <Section title="Configured services" icon={<CheckCircle2 size={15} className="text-success" />}
        hint="Whether a key/credential is present. Grey = not set up yet — this is a config state, not a failure.">
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
          {configured.map(([key, ok]) => (
            <div key={key}
              className={`flex items-center gap-2 rounded-lg border p-2.5 ${ok ? 'border-success/30 bg-success/5' : 'border-border bg-bg opacity-60'}`}>
              <Logo name={key} size={18} />
              <div className="min-w-0">
                <div className="truncate text-xs font-medium text-text">{SERVICE_LABEL[key] ?? key}</div>
                <div className={`text-[10px] ${ok ? 'text-success' : 'text-muted'}`}>{ok ? 'configured' : 'not set'}</div>
              </div>
            </div>
          ))}
        </div>
      </Section>

      {/* Activity */}
      <Section title="Recent activity" icon={<Activity size={15} className="text-purple" />}
        hint="When each subsystem last wrote data. Quiet ≠ broken — it just means nothing happened recently.">
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {activity.map(([key, val]) => (
            <div key={key} className="flex items-center justify-between rounded border border-border bg-bg px-3 py-2">
              <span className="text-xs text-muted">{ACTIVITY_LABEL[key] ?? key}</span>
              <span className="text-xs font-medium text-text">{val ?? '—'}</span>
            </div>
          ))}
        </div>
        {/* Quick data facts */}
        <div className="mt-3 flex flex-wrap gap-2 text-xs">
          <span className="rounded bg-bg px-2 py-1 text-muted">Active projects: <span className="text-text">{health.data.active_projects ?? 0}</span></span>
          <span className="rounded bg-bg px-2 py-1 text-muted">Pending human tasks: <span className="text-text">{health.data.pending_human_tasks ?? 0}</span></span>
          <span className="rounded bg-bg px-2 py-1 text-muted">Blocked tasks: <span className={health.data.blocked_tasks ? 'text-warning' : 'text-text'}>{health.data.blocked_tasks ?? 0}</span></span>
          <span className="rounded bg-bg px-2 py-1 text-muted">Revenue this month: <span className="text-text">${health.data.revenue_this_month ?? 0}</span></span>
        </div>
      </Section>

      {/* Recent errors */}
      <Section title={`Recent errors & warnings${health.recent_errors.length ? ` (${health.recent_errors.length})` : ''}`}
        icon={<AlertTriangle size={15} className="text-warning" />}
        hint="Tail of the live log — the most direct pointer to what's going wrong.">
        {health.recent_errors.length === 0 ? (
          <div className="flex items-center gap-2 text-sm text-success"><CheckCircle2 size={15} /> No recent errors</div>
        ) : (
          <div className="max-h-72 space-y-1 overflow-y-auto rounded border border-border bg-bg p-3 font-mono text-xs">
            {health.recent_errors.map((e, i) => (
              <div key={i} className="flex gap-2 leading-relaxed">
                <span className={`shrink-0 font-bold ${e.level === 'ERROR' ? 'text-danger' : 'text-warning'}`}>{e.level}</span>
                <span className="break-all text-text">{e.msg}</span>
              </div>
            ))}
          </div>
        )}
      </Section>

      {/* Live API status — checks EVERY external API Tobi uses */}
      <Section title="API status — live check of every API" icon={<Activity size={15} className="text-accent" />}
        hint="On-demand: a real LLM round-trip + live network tests to Telegram, Tavily, and each integration. Latency shown per API.">
        <div className="mb-3 flex flex-wrap items-center gap-3">
          <button onClick={onDeepTest} disabled={deepLoading}
            className="flex items-center gap-2 rounded border border-accent/40 bg-accent/10 px-3 py-1.5 text-xs font-medium text-accent transition-colors hover:bg-accent/20 disabled:opacity-50">
            {deepLoading ? <Loader2 size={13} className="animate-spin" /> : <Activity size={13} />}
            {deepLoading ? 'Checking all APIs…' : 'Check all APIs'}
          </button>
          {deep?.summary && (
            <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${deep.summary.ok === deep.summary.total ? 'bg-success/15 text-success' : deep.summary.ok === 0 ? 'bg-danger/15 text-danger' : 'bg-warning/15 text-warning'}`}>
              {deep.summary.ok}/{deep.summary.total} APIs reachable
            </span>
          )}
          {deep && <span className="text-[10px] text-muted">tested {new Date(deep.timestamp).toLocaleTimeString('en-GB')}</span>}
        </div>
        {!deep && !deepLoading && <div className="text-xs text-muted">No live check yet — click <b>Check all APIs</b> (or “Run full health check” up top) to test every API now.</div>}
        {deep && (
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            <div className="flex items-center gap-2 rounded border border-border bg-bg p-2.5">
              <Dot ok={deep.llm.ok} />
              <div className="min-w-0 flex-1">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs font-medium text-text">LLM ({deep.llm.provider ?? 'model'})</span>
                  {deep.llm.latency_ms != null && <span className="shrink-0 font-mono text-[10px] text-muted">{deep.llm.latency_ms}ms</span>}
                </div>
                <div className="truncate text-[10px] text-muted">{deep.llm.detail}</div>
              </div>
            </div>
            {Object.entries(deep.integrations).map(([name, c]) => (
              <div key={name} className="flex items-center gap-2 rounded border border-border bg-bg p-2.5">
                <Dot ok={c.ok} />
                <Logo name={name} size={16} />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-xs font-medium text-text">{SERVICE_LABEL[name] ?? name}</span>
                    {c.latency_ms ? <span className="shrink-0 font-mono text-[10px] text-muted">{c.latency_ms}ms</span> : null}
                  </div>
                  <div className="truncate text-[10px] text-muted">{c.detail}</div>
                </div>
              </div>
            ))}
          </div>
        )}
      </Section>
    </div>
  )
}

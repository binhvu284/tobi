import { useEffect, useState } from 'react'
import { softFail } from '../lib/report'
import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import { RefreshCw, Activity, AlertTriangle, CheckCircle2, Database, Server, Loader2, KeyRound, ExternalLink, Cpu, Stethoscope } from 'lucide-react'
import Logo from '../components/Logo'
import HealthBar from '../components/HealthBar'
import PageLoader from '../components/PageLoader'
import { LoadFailure } from '../components/async-ui'
import PerformanceDoctor from '../components/PerformanceDoctor'
import { Stagger, StaggerItem } from '../components/motion'
import { useReducedMotionPref } from '../context/MotionProvider'
import { getLlmUsage, type UsageSummary } from '../api.keys'
import { getHealth, runDeepTestStream, type HealthReport, type DeepTestReport, type LivenessCheck } from '../api.abilities'
import { getIntegrations, type IntegrationsResponse } from '../api.genesis'

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

/** One-shot tier-colored glow when a diagnostic row snaps to its result. */
function SnapRing({ ok }: { ok: boolean }) {
  const reduced = useReducedMotionPref() !== 'full'
  if (reduced) return null
  return (
    <motion.span aria-hidden className="pointer-events-none absolute inset-0 rounded"
      style={{ background: `radial-gradient(circle at 14px 50%, rgb(${ok ? 'var(--success)' : 'var(--danger)'} / 0.35), transparent 60%)` }}
      initial={{ opacity: 0.9 }} animate={{ opacity: 0 }} transition={{ duration: 0.9, ease: 'easeOut' }} />
  )
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
  const [deepError, setDeepError] = useState<unknown>(null)
  const [gen, setGen] = useState<IntegrationsResponse | null>(null)
  const [usage, setUsage] = useState<UsageSummary | null>(null)
  const [tab, setTab] = useState<'overview' | 'performance'>('overview')
  const reduced = useReducedMotionPref() !== 'full'

  const load = async () => {
    getIntegrations().then(setGen).catch(softFail('health data'))  // Genesis/integrations cross-link (read-only)
    getLlmUsage(7).then(setUsage).catch(softFail('health data'))   // LLM usage summary (Premium Chat #8 P3)
    try {
      const h = await getHealth()
      setHealth(h)
      setUpdated(new Date().toLocaleTimeString('en-GB'))
    } catch (error) { softFail('health data')(error) }
  }

  useEffect(() => {
    load()
    const t = setInterval(load, 30000)
    return () => clearInterval(t)
  }, [])

  // Rows appear as each check finishes rather than all at the end. The chat round-trip takes
  // about eighteen seconds; Telegram and Tavily take about one, and used to be hidden behind it.
  const onDeepTest = async () => {
    setDeepLoading(true)
    setDeepError(null)
    const partial: DeepTestReport = {
      timestamp: new Date().toISOString(), llm: { ok: false, detail: 'Checking…' }, integrations: {},
    }
    setDeep(partial)
    try {
      const summary = await runDeepTestStream((name, result) => {
        if (name === 'llm') partial.llm = result as DeepTestReport['llm']
        else partial.integrations[name] = result
        setDeep({ ...partial, integrations: { ...partial.integrations } })
      })
      setDeep({ ...partial, integrations: { ...partial.integrations }, summary: summary ?? undefined })
    } catch (error) {
      // Keep whatever already arrived — half a health report still tells him something.
      setDeepError(error)
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
  // Targets shown during the live diagnostic sweep (real names if we have a prior
  // run, else the configured services as a stand-in until results return).
  const scanTargets = deep
    ? ['llm', ...Object.keys(deep.integrations)]
    : ['llm', ...configured.filter(([, ok]) => ok).map(([k]) => k)]

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
        {tab === 'overview' && (
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
        )}
      </div>

      {/* Tabs: Overview (live checks) | Performance (system doctor) */}
      <div className="flex items-center gap-1 border-b border-border">
        {([['overview', 'Overview', Activity], ['performance', 'Performance', Stethoscope]] as const).map(([key, label, Icon]) => (
          <button key={key} onClick={() => setTab(key)}
            className={`relative flex items-center gap-1.5 px-3 py-2 text-xs font-medium transition-colors ${tab === key ? 'text-accent' : 'text-muted hover:text-text'}`}>
            <Icon size={13} /> {label}
            {tab === key && <motion.span layoutId="health-tab" className="absolute inset-x-0 -bottom-px h-0.5 rounded-full bg-accent" />}
          </button>
        ))}
      </div>

      {deepError != null && (
        <LoadFailure error={deepError} what="the full health check" onRetry={onDeepTest} />
      )}

      {tab === 'performance' && <PerformanceDoctor />}

      {tab === 'overview' && (<>
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

      {/* Genesis & Integrations — cross-link to the Integrations page */}
      {gen && (
        <Section title="Genesis & Integrations" icon={<KeyRound size={15} className="text-accent" />}
          hint="Tier 0 completion and the connected API keys that power it.">
          <div className="flex items-center gap-3">
            <div className="min-w-0 flex-1">
              <div className="mb-1 flex items-center justify-between text-xs">
                <span className="text-muted">{gen.genesis.complete ? 'Genesis complete 🎉' : `${gen.genesis.pct}% complete`}</span>
                <span className="text-muted">{gen.genesis.active}/{gen.genesis.total} abilities</span>
              </div>
              <div className="h-2 w-full overflow-hidden rounded-full bg-border/40">
                <div className={`h-full rounded-full transition-all duration-700 ${gen.genesis.complete ? 'bg-success' : 'bg-accent'}`}
                  style={{ width: `${gen.genesis.pct}%` }} />
              </div>
            </div>
            <Link to="/integrations" className="flex shrink-0 items-center gap-1 rounded-lg border border-accent/40 bg-accent/10 px-3 py-1.5 text-xs font-medium text-accent transition-colors hover:bg-accent/20">
              Manage <ExternalLink size={12} />
            </Link>
          </div>
          <div className="mt-3 flex flex-wrap gap-1.5">
            {gen.integrations.filter(i => i.available).map(i => (
              <span key={i.id} className={`flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] ${i.connected ? 'bg-success/15 text-success' : 'bg-border/40 text-muted'}`}>
                {i.connected ? <CheckCircle2 size={10} /> : <span className="h-1.5 w-1.5 rounded-full bg-current opacity-50" />}{i.label}
              </span>
            ))}
          </div>
        </Section>
      )}

      {/* LLM usage — cross-link to the Models page (Premium Chat #8 P3) */}
      {usage && usage.requests > 0 && (
        <Section title="LLM usage (7 days)" icon={<Cpu size={15} className="text-accent" />}
          hint="Real per-call logging across chat, agents & research. Full breakdown on the Models page.">
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {[
              { label: 'Tokens', value: usage.total_tokens >= 1000 ? `${(usage.total_tokens / 1000).toFixed(1)}k` : String(usage.total_tokens) },
              { label: 'Cost', value: `$${usage.total_cost.toFixed(usage.total_cost < 1 ? 4 : 2)}` },
              { label: 'Requests', value: usage.requests.toLocaleString() },
              { label: 'Avg latency', value: `${usage.avg_latency_ms}ms` },
            ].map(k => (
              <div key={k.label} className="rounded-lg border border-border bg-bg px-3 py-2">
                <div className="text-[10px] uppercase tracking-wide text-muted">{k.label}</div>
                <div className="mt-0.5 text-base font-bold text-heading">{k.value}</div>
              </div>
            ))}
          </div>
          <div className="mt-3 flex items-center justify-between">
            <div className="flex flex-wrap gap-1.5">
              {usage.by_model.slice(0, 3).map(m => (
                <span key={m.model} className="rounded-full bg-bg px-2 py-0.5 text-[10px] text-muted">{m.model.split(':').pop()} · {m.requests}×</span>
              ))}
            </div>
            <Link to="/models" className="flex shrink-0 items-center gap-1 text-xs font-medium text-accent hover:underline">Models <ExternalLink size={12} /></Link>
          </div>
        </Section>
      )}

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

        {/* Live diagnostic sweep — radar scan rows cascade while every API is pinged */}
        {deepLoading && (
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {scanTargets.map((name, i) => (
              <div key={name} className="relative flex items-center gap-2 overflow-hidden rounded border border-accent/30 bg-bg p-2.5">
                {!reduced && <span className="radar-scan-overlay" style={{ animationDelay: `${i * 0.12}s` }} />}
                <span className="relative z-10 flex h-2 w-2">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-accent opacity-60" />
                  <span className="relative inline-flex h-2 w-2 rounded-full bg-accent" />
                </span>
                {name !== 'llm' && <Logo name={name} size={16} />}
                <div className="relative z-10 min-w-0 flex-1">
                  <span className="text-xs font-medium text-text">{name === 'llm' ? 'LLM' : (SERVICE_LABEL[name] ?? name)}</span>
                  <div className="truncate text-[10px] text-accent/80">testing…</div>
                </div>
              </div>
            ))}
          </div>
        )}

        {!deepLoading && deep && (
          <Stagger className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3" step={0.07}>
            {/* Chat round-trip. The old card said "LLM" and went green on a one-shot ping,
                which stayed green through a full day of Chat being broken. It now reports
                what the owner actually cares about, and when it fails the reason is shown in
                full rather than truncated — the whole point is that he can act on it. */}
            <StaggerItem className={`relative flex items-center gap-2 overflow-hidden rounded border border-border bg-bg p-2.5${deep.llm.ok ? '' : ' sm:col-span-2 lg:col-span-3'}`}>
              <SnapRing ok={deep.llm.ok} />
              <Dot ok={deep.llm.ok} />
              <div className="relative z-10 min-w-0 flex-1">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs font-medium text-text">
                    {deep.llm.state === 'working' ? 'Chat works'
                      : deep.llm.state === 'model_unavailable' ? 'Model unavailable'
                      : deep.llm.state === 'broken' ? 'Chat is broken'
                      : `LLM (${deep.llm.provider ?? 'model'})`}
                    {deep.llm.tools_used?.length ? (
                      <span className="ml-1.5 font-normal text-muted">· ran {deep.llm.tools_used.join(', ')}</span>
                    ) : null}
                  </span>
                  {deep.llm.latency_ms != null && <span className="shrink-0 font-mono text-[10px] text-muted">{deep.llm.latency_ms}ms</span>}
                </div>
                <div className={deep.llm.ok ? 'truncate text-[10px] text-muted' : 'mt-0.5 break-words text-[10px] text-muted'}>
                  {deep.llm.detail}
                </div>
              </div>
            </StaggerItem>
            {Object.entries(deep.integrations).map(([name, c]) => (
              <StaggerItem key={name} className="relative flex items-center gap-2 overflow-hidden rounded border border-border bg-bg p-2.5">
                <SnapRing ok={c.ok} />
                <Dot ok={c.ok} />
                <Logo name={name} size={16} />
                <div className="relative z-10 min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-xs font-medium text-text">{SERVICE_LABEL[name] ?? name}</span>
                    {c.latency_ms ? <span className="shrink-0 font-mono text-[10px] text-muted">{c.latency_ms}ms</span> : null}
                  </div>
                  <div className="truncate text-[10px] text-muted">{c.detail}</div>
                </div>
              </StaggerItem>
            ))}
          </Stagger>
        )}
      </Section>
      </>)}
    </div>
  )
}

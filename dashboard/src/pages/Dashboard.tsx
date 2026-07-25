import { useEffect, useState, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { motion, AnimatePresence, Reorder } from 'framer-motion'
import {
  RefreshCw, CheckCircle, HeartPulse, FlaskConical, FileText, Crown, Building2, Zap, Plus,
  Loader2, GripVertical, Eye, EyeOff, SlidersHorizontal, Play, FolderKanban,
} from 'lucide-react'
import HealthBar from '../components/HealthBar'
import Loader from '../components/Loader'
import PageLoader from '../components/PageLoader'
import { AmbientField, CountUp, SpotlightCard, TraceButton } from '../components/motion'
import { useReducedMotionPref } from '../context/MotionProvider'
import { getStatus, getProjects, getLessons } from '../api.core'
import { getHealth, type HealthReport } from '../api.abilities'
import { runEngine, type Project, type Lesson, type Todo, type EngineName } from '../api.office'
import { pmGetStats, pmListProjects, type PMStats, type PMProject } from '../api.pm'
import { getStorageOverview, getUsageOverview, getUsageBudget, type StorageOverview, type UsageOverview, type UsageBudget } from '../api.storage'
import { markDone } from '../api.tasks'
import { fmtBytes, fmtUsd } from '../lib/format'
import { useToast } from '../context/ToastProvider'

/** Once-per-session "system online" hero boot for the Dashboard. */
function HeroBoot() {
  const level = useReducedMotionPref()
  const [show, setShow] = useState(() => {
    if (level === 'off') return false
    try { return sessionStorage.getItem('tobi.dash.booted') !== '1' } catch { return true }
  })
  useEffect(() => {
    try { sessionStorage.setItem('tobi.dash.booted', '1') } catch { /* ignore */ }
    if (!show) return
    const t = setTimeout(() => setShow(false), level === 'full' ? 1300 : 650)
    return () => clearTimeout(t)
  }, [show, level])
  return (
    <AnimatePresence>
      {show && (
        <motion.div className="absolute inset-0 z-30 flex flex-col items-center justify-center gap-3 overflow-hidden bg-bg"
          initial={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.45, ease: 'easeOut' }}>
          <div className="grid-bg pointer-events-none absolute inset-0 opacity-60" />
          <span className="page-scanline" />
          <motion.div initial={{ scale: 0.6, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} transition={{ type: 'spring', stiffness: 260, damping: 18 }}
            className="glow-accent relative flex h-16 w-16 items-center justify-center rounded-2xl border border-accent/50 bg-accent/10 text-accent">
            <Zap size={30} />
          </motion.div>
          <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 }} className="text-center">
            <div className="text-2xl font-bold tracking-[0.3em] text-heading">TOBI</div>
            <div className="mt-1 flex items-center justify-center gap-2 text-[11px] uppercase tracking-[0.4em] text-accent">
              <span className="h-1.5 w-1.5 rounded-full bg-success" /> System online
            </div>
          </motion.div>
          <div className="tobi-runbar mt-2 h-0.5 w-40" style={{ background: 'rgb(var(--border) / 0.4)' }} />
        </motion.div>
      )}
    </AnimatePresence>
  )
}

const PM_STATUS_COLOR: Record<string, string> = {
  idea: 'bg-purple/20 text-purple', active: 'bg-accent/20 text-accent',
  done: 'bg-success/20 text-success', archived: 'bg-muted/20 text-muted',
}
const LESSON_EMOJI: Record<string, string> = { success: '✅', failure: '❌', insight: '💡', warning: '⚠️' }

const DEFAULT_ORDER = ['launchpad', 'health', 'storage', 'kpis', 'pm_projects', 'activity', 'todos']
type DashCfg = { order: string[]; hidden: string[] }
const loadCfg = (): DashCfg => {
  try {
    const cfg = { order: DEFAULT_ORDER, hidden: [], ...JSON.parse(localStorage.getItem('tobi.dash') || '{}') }
    // widgets shipped after the user saved a layout still appear (appended at the end)
    cfg.order = [...cfg.order, ...DEFAULT_ORDER.filter((id: string) => !cfg.order.includes(id))]
    return cfg
  } catch { return { order: DEFAULT_ORDER, hidden: [] } }
}

export default function Dashboard() {
  const [status, setStatus] = useState<{ revenue?: { this_month?: number; total?: number }; human_todos?: Todo[] } | null>(null)
  const [projects, setProjects] = useState<Project[]>([])
  const [lessons, setLessons] = useState<Lesson[]>([])
  const [todos, setTodos] = useState<Todo[]>([])
  const [health, setHealth] = useState<HealthReport | null>(null)
  const [pmStats, setPmStats] = useState<PMStats | null>(null)
  const [pmProjects, setPmProjects] = useState<PMProject[]>([])
  const [storage, setStorage] = useState<StorageOverview | null>(null)
  const [usage, setUsage] = useState<UsageOverview | null>(null)
  const [budget, setBudget] = useState<UsageBudget | null>(null)
  const [loading, setLoading] = useState(true)
  const [lastUpdated, setLastUpdated] = useState('')
  const [busy, setBusy] = useState<string | null>(null)
  const [edit, setEdit] = useState(false)
  const [cfg, setCfg] = useState<DashCfg>(loadCfg)
  const { toast } = useToast()

  const saveCfg = (c: DashCfg) => { setCfg(c); try { localStorage.setItem('tobi.dash', JSON.stringify(c)) } catch { /* ignore */ } }
  const toggleHidden = (id: string) => saveCfg({ ...cfg, hidden: cfg.hidden.includes(id) ? cfg.hidden.filter(x => x !== id) : [...cfg.hidden, id] })

  const load = useCallback(async () => {
    try {
      const [s, p, l] = await Promise.all([getStatus(), getProjects(), getLessons()])
      setStatus(s); setProjects(p); setLessons(l); setTodos(s.human_todos || [])
      setLastUpdated(new Date().toLocaleTimeString('en-GB'))
    } catch { /* keep prior */ } finally { setLoading(false) }
    getHealth().then(setHealth).catch(() => {})
    pmGetStats().then(setPmStats).catch(() => {})
    pmListProjects().then(r => setPmProjects(r.items)).catch(() => {})
    getStorageOverview().then(setStorage).catch(() => {})
    getUsageOverview('month').then(setUsage).catch(() => {})
    getUsageBudget().then(setBudget).catch(() => {})
  }, [])
  useEffect(() => { load(); const id = setInterval(load, 30_000); return () => clearInterval(id) }, [load])

  async function handleDone(taskId: number) { await markDone(taskId); setTodos(prev => prev.filter(t => t.id !== taskId)) }

  const runQuick = async (name: EngineName, label: string) => {
    setBusy(name); toast({ kind: 'info', title: `${label}…`, detail: 'Triggered from launchpad' })
    try { const r = await runEngine(name); toast({ kind: r.ok ? 'success' : 'error', title: r.message || label, detail: r.detail }); load() }
    catch (e) { toast({ kind: 'error', title: label, detail: (e as Error).message }) } finally { setBusy(null) }
  }

  const rev = status?.revenue || {}
  const activeCount = projects.filter(p => p.status === 'active').length

  const QUICK = [
    { id: 'research', label: 'Run research', icon: FlaskConical, run: () => runQuick('research', 'Research') },
    { id: 'execute', label: 'Execution cycle', icon: Building2, run: () => runQuick('execute', 'Execution cycle') },
    { id: 'ceo', label: 'CEO review', icon: Crown, run: () => runQuick('ceo', 'CEO review') },
    { id: 'report', label: 'Daily report', icon: FileText, run: () => runQuick('report', 'Daily report') },
  ]

  // ── Widgets ──
  const W: Record<string, { title: string; node: React.ReactNode }> = {
    launchpad: {
      title: 'Launchpad', node: (
        <div className="rounded-xl border border-border bg-surface p-4">
          <div className="mb-3 text-xs font-semibold uppercase tracking-widest text-muted">Launchpad</div>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
            {QUICK.map(q => {
              const Icon = q.icon; const running = busy === q.id
              return (
                <TraceButton key={q.id} onClick={q.run} disabled={running}
                  className="flex flex-col items-center gap-1.5 rounded-lg border border-border bg-bg p-3 text-center text-xs text-text transition-colors hover:border-accent/50 disabled:opacity-50">
                  {running ? <Loader2 size={18} className="animate-spin text-accent" /> : <Icon size={18} className="text-accent" />}
                  <span>{q.label}</span>
                </TraceButton>
              )
            })}
            <Link to="/office" className="flex flex-col items-center gap-1.5 rounded-lg border border-border bg-bg p-3 text-center text-xs text-text hover:border-accent/50">
              <Plus size={18} className="text-success" /><span>New mission</span>
            </Link>
            <Link to="/ability" className="flex flex-col items-center gap-1.5 rounded-lg border border-border bg-bg p-3 text-center text-xs text-text hover:border-accent/50">
              <Zap size={18} className="text-purple" /><span>Coach skill</span>
            </Link>
          </div>
        </div>
      ),
    },
    health: {
      title: 'System health', node: health ? (
        <Link to="/health" className="block rounded-xl border border-border bg-surface p-4 transition-colors hover:border-overlay/20">
          <div className="mb-2 flex items-center justify-between">
            <span className="flex items-center gap-1.5 text-xs uppercase tracking-wider text-muted"><HeartPulse size={13} /> System Health</span>
            <span className="text-xs text-muted">View details →</span>
          </div>
          <HealthBar score={health.score} size="sm" />
        </Link>
      ) : <div className="rounded-xl border border-border bg-surface p-4"><Loader size={28} label="Health loading…" /></div>,
    },
    storage: {
      title: 'Storage & spend', node: (
        <Link to="/storage" className="block rounded-xl border border-border bg-surface p-4 transition-colors hover:border-overlay/20">
          <div className="mb-2 flex items-center justify-between">
            <span className="flex items-center gap-1.5 text-xs uppercase tracking-wider text-muted">💾 Storage & Spend</span>
            <span className="text-xs text-muted">View details →</span>
          </div>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <div>
              <div className="text-[10px] uppercase tracking-wider text-muted">Total storage</div>
              <div className="text-lg font-bold text-heading">{storage ? fmtBytes(storage.total_bytes) : '—'}</div>
            </div>
            <div>
              <div className="text-[10px] uppercase tracking-wider text-muted">Biggest</div>
              <div className="truncate text-lg font-bold text-heading">{storage?.biggest?.feature ?? '—'}</div>
            </div>
            <div>
              <div className="text-[10px] uppercase tracking-wider text-muted">LLM spend (30d)</div>
              <div className="text-lg font-bold text-heading">{usage ? fmtUsd(usage.total_cost) : '—'}</div>
            </div>
            <div>
              <div className="text-[10px] uppercase tracking-wider text-muted">Budget</div>
              {budget && budget.level !== 'off' ? (
                <div className={`text-lg font-bold ${budget.level === 'over' ? 'text-danger' : budget.level === 'warn' ? 'text-warning' : 'text-success'}`}>
                  {budget.pct}%
                </div>
              ) : <div className="text-lg font-bold text-muted">—</div>}
            </div>
          </div>
        </Link>
      ),
    },
    kpis: {
      title: 'KPIs', node: (
        <div className="grid grid-cols-3 gap-4">
          {[
            { label: 'Active Projects', val: activeCount, c: 'text-accent', icon: '📁', prefix: '' },
            { label: 'Revenue (month)', val: Math.round(rev.this_month ?? 0), c: 'text-success', icon: '💰', prefix: '$' },
            { label: 'Pending Todos', val: todos.length, c: todos.length ? 'text-warning' : 'text-muted', icon: '📋', prefix: '' },
          ].map(k => (
            <SpotlightCard key={k.label} className="rounded-xl border border-border bg-surface p-4">
              <div className="mb-1 text-xs text-muted">{k.icon} {k.label}</div>
              <div className={`text-2xl font-bold ${k.c}`}><CountUp value={k.val} prefix={k.prefix} /></div>
            </SpotlightCard>
          ))}
        </div>
      ),
    },
    pm_projects: {
      title: 'My Projects', node: (
        <div className="overflow-hidden rounded-xl border border-border bg-surface">
          <div className="flex items-center justify-between border-b border-border px-5 py-3">
            <span className="flex items-center gap-2 text-sm font-semibold text-heading"><FolderKanban size={15} className="text-accent" /> My Projects</span>
            <Link to="/projects" className="text-xs text-muted hover:text-accent transition-colors">Open all →</Link>
          </div>
          {!pmStats ? (
            <Loader size={28} label="Loading…" />
          ) : (
            <div className="grid grid-cols-3 divide-x divide-border">
              <div className="px-5 py-4 text-center">
                <div className="text-2xl font-bold text-accent">{pmStats.active_projects}</div>
                <div className="text-xs text-muted mt-1">Active</div>
              </div>
              <div className="px-5 py-4 text-center">
                <div className={`text-2xl font-bold ${pmStats.tasks_due_today > 0 ? 'text-warning' : 'text-muted'}`}>{pmStats.tasks_due_today}</div>
                <div className="text-xs text-muted mt-1">Tasks due today</div>
              </div>
              <div className="px-5 py-4 text-center">
                <div className="text-2xl font-bold text-text">{pmStats.total_projects}</div>
                <div className="text-xs text-muted mt-1">Total</div>
              </div>
            </div>
          )}
          {pmProjects.length > 0 ? (
            <div className="divide-y divide-border border-t border-border">
              {pmProjects.slice(0, 6).map(p => (
                <Link key={p.id} to="/projects" className="flex items-center gap-3 px-5 py-2.5 hover:bg-overlay/[0.02] transition-colors">
                  <span className="text-lg leading-none">{p.emoji_icon}</span>
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm font-medium text-text">{p.name}</div>
                    <div className="flex items-center gap-2 text-[11px] text-muted">
                      <span>{p.task_done}/{p.task_count} tasks</span>
                      {p.category && <span className="truncate">· {p.category}</span>}
                    </div>
                  </div>
                  <div className="flex w-24 items-center gap-2 shrink-0">
                    <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-border">
                      <div className="h-full rounded-full" style={{ width: `${p.progress_pct}%`, background: p.accent_color || 'rgb(var(--accent))' }} />
                    </div>
                    <span className="text-[11px] tabular-nums text-muted">{p.progress_pct}%</span>
                  </div>
                  <span className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium ${PM_STATUS_COLOR[p.status] || 'bg-muted/20 text-muted'}`}>
                    {p.status}
                  </span>
                </Link>
              ))}
              {pmProjects.length > 6 && (
                <Link to="/projects" className="block px-5 py-2 text-center text-xs text-muted hover:text-accent transition-colors">
                  +{pmProjects.length - 6} more project{pmProjects.length - 6 === 1 ? '' : 's'} →
                </Link>
              )}
            </div>
          ) : (
            <div className="border-t border-border px-5 py-3 text-center text-xs text-muted">
              No projects yet — <Link to="/projects" className="text-accent">create one →</Link>
            </div>
          )}
          {pmStats?.last_mission && (
            <div className="border-t border-border px-5 py-2 text-xs text-muted truncate">
              ⚡ Last mission: {pmStats.last_mission.prompt.slice(0, 60)}…
            </div>
          )}
        </div>
      ),
    },
    activity: {
      title: 'Activity', node: (
        <div className="overflow-hidden rounded-xl border border-border bg-surface">
          <div className="border-b border-border px-5 py-3 text-sm font-semibold text-heading">📡 Recent Activity</div>
          <div className="divide-y divide-border">
            {lessons.length === 0 ? <div className="py-6 text-center text-sm italic text-muted">No activity yet</div> :
              lessons.slice(0, 6).map(l => (
                <div key={l.id} className="px-5 py-3">
                  <div className="mb-0.5 text-xs font-semibold text-heading">{LESSON_EMOJI[l.lesson_type] || '📌'} {l.title || l.lesson_type.toUpperCase()}</div>
                  <div className="line-clamp-2 text-xs leading-relaxed text-muted">{l.content}</div>
                </div>
              ))}
          </div>
        </div>
      ),
    },
    todos: {
      title: 'Owner Todos', node: (
        <div className="overflow-hidden rounded-xl border border-border bg-surface">
          <div className="border-b border-border px-5 py-3 text-sm font-semibold text-heading">📋 Owner Todos</div>
          <div className="divide-y divide-border">
            {todos.length === 0 ? <div className="py-6 text-center text-sm text-muted"><CheckCircle size={16} className="mr-1 inline text-success" /> All clear!</div> :
              todos.map(t => (
                <div key={t.id} className="flex items-center justify-between gap-3 px-5 py-3">
                  <div><div className="text-xs text-text">{t.title}</div><div className="text-xs text-muted">📁 {t.project_name || '—'}</div></div>
                  <button onClick={() => handleDone(t.id)} className="shrink-0 rounded-md bg-success/20 px-3 py-1 text-xs text-success hover:bg-success/30">Done</button>
                </div>
              ))}
          </div>
        </div>
      ),
    },
  }

  const visible = cfg.order.filter(id => W[id] && !cfg.hidden.includes(id))

  return (
    <div className="relative p-6">
      <AmbientField />
      <HeroBoot />
      <div className="relative z-10">
      <div className="mb-6 flex items-center justify-between">
        <div><h1 className="text-xl font-bold text-heading">Dashboard</h1><p className="mt-0.5 text-xs text-muted">Tobi&apos;s live operating status</p></div>
        <div className="flex items-center gap-3">
          <button onClick={() => setEdit(e => !e)} className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs transition-colors ${edit ? 'border-accent text-accent' : 'border-border text-muted hover:text-text'}`}>
            <SlidersHorizontal size={12} /> {edit ? 'Done' : 'Customize'}
          </button>
          <button onClick={load} className="flex items-center gap-1.5 text-xs text-muted transition-colors hover:text-text">
            <RefreshCw size={12} /> {lastUpdated ? `Updated ${lastUpdated}` : 'Loading…'}
          </button>
        </div>
      </div>

      {edit && (
        <div className="mb-4 rounded-lg border border-accent/30 bg-accent/10 p-3 text-xs text-text">
          <span className="font-semibold text-accent">Customize mode:</span> drag <GripVertical size={11} className="inline" /> to reorder, toggle <Eye size={11} className="inline" /> to show/hide. Saved to this browser.
          <div className="mt-2 flex flex-wrap gap-1.5">
            {cfg.order.filter(id => W[id]).map(id => (
              <button key={id} onClick={() => toggleHidden(id)} className={`flex items-center gap-1 rounded border px-1.5 py-0.5 ${cfg.hidden.includes(id) ? 'border-border text-muted' : 'border-accent/40 text-accent'}`}>
                {cfg.hidden.includes(id) ? <EyeOff size={10} /> : <Eye size={10} />} {W[id].title}
              </button>
            ))}
          </div>
        </div>
      )}

      {loading ? <PageLoader preset="dashboard" compact /> : (
        edit ? (
          <Reorder.Group axis="y" values={cfg.order} onReorder={(o) => saveCfg({ ...cfg, order: o })} className="space-y-4">
            {cfg.order.filter(id => W[id]).map(id => (
              <Reorder.Item key={id} value={id} className="flex items-stretch gap-2">
                <div className="flex cursor-grab items-center rounded-lg border border-border bg-surface px-1 text-muted active:cursor-grabbing"><GripVertical size={16} /></div>
                <div className={`min-w-0 flex-1 ${cfg.hidden.includes(id) ? 'opacity-40' : ''}`}>{W[id].node}</div>
              </Reorder.Item>
            ))}
          </Reorder.Group>
        ) : (
          <motion.div initial="hidden" animate="show" variants={{ show: { transition: { staggerChildren: 0.05 } } }} className="space-y-4">
            {visible.map(id => (
              <motion.div key={id} variants={{ hidden: { opacity: 0, y: 12 }, show: { opacity: 1, y: 0 } }}>{W[id].node}</motion.div>
            ))}
          </motion.div>
        )
      )}
      </div>
    </div>
  )
}

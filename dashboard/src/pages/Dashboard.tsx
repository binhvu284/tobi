import { useEffect, useState, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { motion, Reorder } from 'framer-motion'
import {
  RefreshCw, CheckCircle, HeartPulse, FlaskConical, FileText, Crown, Building2, Zap, Plus,
  Loader2, GripVertical, Eye, EyeOff, SlidersHorizontal, Play, FolderKanban,
} from 'lucide-react'
import HealthBar from '../components/HealthBar'
import Loader from '../components/Loader'
import PageLoader from '../components/PageLoader'
import {
  getStatus, getProjects, getLessons, getHealth, markDone, runEngine, pmGetStats,
  type Project, type Lesson, type Todo, type HealthReport, type EngineName, type PMStats,
} from '../api'
import { useToast } from '../context/ToastProvider'

const STATUS_COLOR: Record<string, string> = {
  active: 'bg-accent/20 text-accent', pending: 'bg-warning/20 text-warning', approved: 'bg-warning/20 text-warning',
  completed: 'bg-success/20 text-success', failed: 'bg-danger/20 text-danger', paused: 'bg-muted/20 text-muted',
}
const LESSON_EMOJI: Record<string, string> = { success: '✅', failure: '❌', insight: '💡', warning: '⚠️' }

const DEFAULT_ORDER = ['launchpad', 'health', 'kpis', 'pm_projects', 'projects', 'activity', 'todos']
type DashCfg = { order: string[]; hidden: string[] }
const loadCfg = (): DashCfg => { try { return { order: DEFAULT_ORDER, hidden: [], ...JSON.parse(localStorage.getItem('tobi.dash') || '{}') } } catch { return { order: DEFAULT_ORDER, hidden: [] } } }

export default function Dashboard() {
  const [status, setStatus] = useState<{ revenue?: { this_month?: number; total?: number }; human_todos?: Todo[] } | null>(null)
  const [projects, setProjects] = useState<Project[]>([])
  const [lessons, setLessons] = useState<Lesson[]>([])
  const [todos, setTodos] = useState<Todo[]>([])
  const [health, setHealth] = useState<HealthReport | null>(null)
  const [pmStats, setPmStats] = useState<PMStats | null>(null)
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
                <button key={q.id} onClick={q.run} disabled={running}
                  className="flex flex-col items-center gap-1.5 rounded-lg border border-border bg-bg p-3 text-center text-xs text-text transition-colors hover:border-accent/50 disabled:opacity-50">
                  {running ? <Loader2 size={18} className="animate-spin text-accent" /> : <Icon size={18} className="text-accent" />}
                  <span>{q.label}</span>
                </button>
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
        <Link to="/health" className="block rounded-xl border border-border bg-surface p-4 transition-colors hover:border-white/20">
          <div className="mb-2 flex items-center justify-between">
            <span className="flex items-center gap-1.5 text-xs uppercase tracking-wider text-muted"><HeartPulse size={13} /> System Health</span>
            <span className="text-xs text-muted">View details →</span>
          </div>
          <HealthBar score={health.score} size="sm" />
        </Link>
      ) : <div className="rounded-xl border border-border bg-surface p-4"><Loader size={28} label="Health loading…" /></div>,
    },
    kpis: {
      title: 'KPIs', node: (
        <div className="grid grid-cols-3 gap-4">
          {[
            { label: 'Active Projects', val: activeCount, c: 'text-accent', icon: '📁' },
            { label: 'Revenue (month)', val: `$${(rev.this_month ?? 0).toFixed(0)}`, c: 'text-success', icon: '💰' },
            { label: 'Pending Todos', val: todos.length, c: todos.length ? 'text-warning' : 'text-muted', icon: '📋' },
          ].map(k => (
            <div key={k.label} className="rounded-xl border border-border bg-surface p-4">
              <div className="mb-1 text-xs text-muted">{k.icon} {k.label}</div>
              <div className={`text-2xl font-bold ${k.c}`}>{k.val}</div>
            </div>
          ))}
        </div>
      ),
    },
    projects: {
      title: 'Projects', node: (
        <div className="overflow-hidden rounded-xl border border-border bg-surface">
          <div className="border-b border-border px-5 py-3 text-sm font-semibold text-heading">📁 Projects</div>
          {projects.length === 0 ? (
            <div className="py-8 text-center text-sm text-muted">No projects yet — <Link to="/office" className="text-accent">run research →</Link></div>
          ) : (
            <table className="w-full text-sm">
              <thead><tr className="text-xs uppercase tracking-wider text-muted">
                {['Name', 'Type', 'Progress', 'Revenue', 'Status'].map(h => <th key={h} className="border-b border-border px-5 py-3 text-left">{h}</th>)}
              </tr></thead>
              <tbody>{projects.map((p, i) => (
                <tr key={p.id} className={i % 2 ? 'bg-white/[0.015]' : ''}>
                  <td className="px-5 py-3 font-medium text-heading">{p.name}</td>
                  <td className="px-5 py-3 text-muted">{p.type}</td>
                  <td className="px-5 py-3"><div className="flex items-center gap-2">
                    <div className="h-1.5 w-20 overflow-hidden rounded-full bg-border"><div className="h-full rounded-full bg-accent" style={{ width: `${p.progress_pct ?? 0}%` }} /></div>
                    <span className="text-xs text-muted">{p.progress_pct ?? 0}%</span></div></td>
                  <td className="px-5 py-3 text-success">${(p.revenue_total || 0).toFixed(2)}</td>
                  <td className="px-5 py-3"><span className={`whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_COLOR[p.status] || 'bg-muted/20 text-muted'}`}>{p.status}</span></td>
                </tr>
              ))}</tbody>
            </table>
          )}
        </div>
      ),
    },
    pm_projects: {
      title: 'My Projects', node: (
        <Link to="/projects" className="block overflow-hidden rounded-xl border border-border bg-surface hover:border-accent/40 transition-colors">
          <div className="flex items-center justify-between border-b border-border px-5 py-3">
            <span className="flex items-center gap-2 text-sm font-semibold text-heading"><FolderKanban size={15} className="text-accent" /> My Projects</span>
            <span className="text-xs text-muted">Open →</span>
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
          {pmStats?.last_mission && (
            <div className="border-t border-border px-5 py-2 text-xs text-muted truncate">
              ⚡ Last mission: {pmStats.last_mission.prompt.slice(0, 60)}…
            </div>
          )}
        </Link>
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
    <div className="p-6">
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
  )
}

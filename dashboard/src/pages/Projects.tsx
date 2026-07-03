import { useCallback, useEffect, useRef, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Plus, RefreshCw, LayoutGrid, List, Search, X, ChevronRight,
  Target, Zap, FileText, Calendar, User, Bot,
  CheckCircle2, Circle, Trash2, Pencil, Save,
  Paperclip, Activity, TrendingUp, Play,
  ChevronDown, ChevronUp, FolderOutput,
} from 'lucide-react'
import {
  pmListProjects, pmCreateProject, pmPatchProject, pmDeleteProject, pmReorderProjects,
  pmListGoals, pmCreateGoal, pmPatchGoal, pmDeleteGoal,
  pmListTasks, pmCreateTask, patchTask, deleteTask,
  pmListMissions, pmCreateMission,
  pmListActivity,
  pmListFiles, pmCreateFile, pmDeleteFile,
  pmListTemplates, pmCreateTemplate,
  pmGetProject,
  type PMProject, type PMGoal, type PMMission, type PMActivity, type PMFile,
  type TaskItem, type TaskStatus,
} from '../api'
import { useToast } from '../context/ToastProvider'
import PageLoader from '../components/PageLoader'
import { AmbientField } from '../components/motion'

// ── Constants ────────────────────────────────────────────────────────────────
const STATUS_CFG: Record<string, { label: string; color: string; dot: string }> = {
  idea:     { label: 'Idea',     color: 'bg-purple-500/15 text-purple-400 border-purple-500/30', dot: 'bg-purple-400' },
  active:   { label: 'Active',   color: 'bg-accent/15 text-accent border-accent/30',             dot: 'bg-accent' },
  done:     { label: 'Done',     color: 'bg-success/15 text-success border-success/30',          dot: 'bg-success' },
  archived: { label: 'Archived', color: 'bg-muted/15 text-muted border-muted/30',                dot: 'bg-muted' },
}
const SIZE_CFG: Record<string, string> = {
  small:  'text-[10px] bg-white/5 text-muted px-1.5 py-0.5 rounded uppercase tracking-wide',
  medium: 'text-[10px] bg-accent/10 text-accent px-1.5 py-0.5 rounded uppercase tracking-wide',
  large:  'text-[10px] bg-warning/10 text-warning px-1.5 py-0.5 rounded uppercase tracking-wide',
  epic:   'text-[10px] bg-danger/10 text-danger px-1.5 py-0.5 rounded uppercase tracking-wide',
}
const TASK_STATUS_COLORS: Record<string, string> = {
  planned:          'bg-muted/15 text-muted',
  in_progress:      'bg-accent/15 text-accent',
  paused:           'bg-warning/15 text-warning',
  blocked:          'bg-danger/15 text-danger',
  needs_owner_input:'bg-orange-400/15 text-orange-400',
  done:             'bg-success/15 text-success',
  cancelled:        'bg-muted/10 text-muted',
}
const PRIORITY_COLORS: Record<string, string> = {
  P0: 'text-danger', P1: 'text-warning', P2: 'text-accent', P3: 'text-muted',
}
const EMOJIS = ['📁','🚀','💡','🎯','📊','🛠','🌱','🔬','📱','💼','🎨','🏗','⚡','🔐','🌍','🧪','📝','🤖']
const ACCENTS = ['#58a6ff','#3fb950','#f0883e','#d29922','#8b5cf6','#ec4899','#06b6d4','#10b981','#f43f5e']

function fmtDate(s?: string | null) {
  if (!s) return '—'
  try { return new Date(s).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' }) } catch { return s }
}
function fmtAgo(s?: string | null) {
  if (!s) return '—'
  try {
    const m = Math.floor((Date.now() - new Date(s).getTime()) / 60000)
    if (m < 1) return 'just now'
    if (m < 60) return `${m}m ago`
    const h = Math.floor(m / 60)
    if (h < 24) return `${h}h ago`
    return `${Math.floor(h / 24)}d ago`
  } catch { return s }
}

// ── Shared: progress bar ──────────────────────────────────────────────────────
function Bar({ pct, color = 'bg-accent' }: { pct: number; color?: string }) {
  return (
    <div className="h-1.5 w-full rounded-full bg-white/8 overflow-hidden">
      <motion.div className={`h-full rounded-full ${color}`}
        initial={{ width: 0 }} animate={{ width: `${Math.min(100, pct)}%` }}
        transition={{ duration: 0.5, ease: 'easeOut' }} />
    </div>
  )
}

// ── Project card (grid) ───────────────────────────────────────────────────────
function ProjectCard({ project, onClick, onDelete }: { project: PMProject; onClick: () => void; onDelete: () => void }) {
  const cfg = STATUS_CFG[project.status] ?? STATUS_CFG.idea
  const overdue = project.deadline && project.status !== 'done' && new Date(project.deadline) < new Date()
  return (
    <motion.div layout initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.95 }} whileHover={{ y: -2 }} onClick={onClick}
      className="group relative cursor-pointer rounded-xl border border-border bg-surface p-4 hover:border-accent/40 transition-colors"
      style={{ borderTop: `3px solid ${project.accent_color ?? '#58a6ff'}` }}>
      <button onClick={e => { e.stopPropagation(); onDelete() }} title="Delete project"
        className="absolute right-2 top-2 z-10 flex h-6 w-6 items-center justify-center rounded-md border border-border bg-surface text-muted opacity-0 transition-all hover:border-danger/50 hover:text-danger group-hover:opacity-100">
        <Trash2 size={12} />
      </button>
      <div className="flex items-start justify-between gap-2 mb-3">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-2xl leading-none">{project.emoji_icon}</span>
          <div className="min-w-0">
            <div className="font-semibold text-sm text-text truncate">{project.name}</div>
            {project.category && <div className="text-[11px] text-muted truncate">{project.category}</div>}
          </div>
        </div>
        <div className="flex items-center gap-1.5 shrink-0 pr-7">
          <span className={SIZE_CFG[project.size] ?? SIZE_CFG.medium}>{project.size}</span>
          <span className={`flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium ${cfg.color}`}>
            <span className={`h-1.5 w-1.5 rounded-full ${cfg.dot}`} />{cfg.label}
          </span>
        </div>
      </div>
      <div className="mb-3">
        <div className="flex justify-between text-[11px] mb-1">
          <span className="text-muted">Progress</span>
          <span className="text-text font-medium">{project.progress_pct}%</span>
        </div>
        <Bar pct={project.progress_pct} />
      </div>
      <div className="flex items-center justify-between text-[11px] text-muted">
        <div className="flex items-center gap-3">
          <span className="flex items-center gap-1"><CheckCircle2 size={11} />{project.task_done}/{project.task_count}</span>
          {project.goal_count > 0 && <span className="flex items-center gap-1"><Target size={11} />{project.goal_count}</span>}
        </div>
        {project.deadline && (
          <span className={`flex items-center gap-1 ${overdue ? 'text-danger' : ''}`}>
            <Calendar size={11} />{fmtDate(project.deadline)}
          </span>
        )}
      </div>
      <ChevronRight size={14} className="absolute right-3 bottom-3 text-muted opacity-0 group-hover:opacity-100 transition-opacity" />
    </motion.div>
  )
}

// ── Project row (list) ────────────────────────────────────────────────────────
function ProjectRow({ project, onClick, onDelete }: { project: PMProject; onClick: () => void; onDelete: () => void }) {
  const cfg = STATUS_CFG[project.status] ?? STATUS_CFG.idea
  const overdue = project.deadline && project.status !== 'done' && new Date(project.deadline) < new Date()
  return (
    <motion.div layout initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      onClick={onClick}
      className="group flex items-center gap-4 px-4 py-3 border-b border-border hover:bg-white/3 cursor-pointer transition-colors">
      <span className="text-xl w-7 text-center">{project.emoji_icon}</span>
      <div className="flex-1 min-w-0">
        <div className="text-sm font-medium text-text truncate">{project.name}</div>
        {project.category && <div className="text-[11px] text-muted">{project.category}</div>}
      </div>
      <span className={`flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium ${cfg.color}`}>
        <span className={`h-1.5 w-1.5 rounded-full ${cfg.dot}`} />{cfg.label}
      </span>
      <span className={SIZE_CFG[project.size] ?? SIZE_CFG.medium}>{project.size}</span>
      <div className="w-28">
        <div className="flex justify-between text-[11px] mb-0.5">
          <span className="text-muted">{project.progress_pct}%</span>
          <span className="text-muted">{project.task_done}/{project.task_count}</span>
        </div>
        <Bar pct={project.progress_pct} />
      </div>
      <span className={`text-[11px] w-16 text-right ${overdue ? 'text-danger' : 'text-muted'}`}>{fmtDate(project.deadline)}</span>
      <button onClick={e => { e.stopPropagation(); onDelete() }} title="Delete project"
        className="text-muted opacity-0 transition-all hover:text-danger group-hover:opacity-100"><Trash2 size={14} /></button>
      <ChevronRight size={14} className="text-muted opacity-0 group-hover:opacity-100 transition-opacity" />
    </motion.div>
  )
}

// ── Create project modal ──────────────────────────────────────────────────────
function CreateModal({ onClose, onCreate, templates }: {
  onClose: () => void
  onCreate: (p: PMProject) => void
  templates: { id: number; name: string }[]
}) {
  const [name, setName] = useState('')
  const [desc, setDesc] = useState('')
  const [status, setStatus] = useState<'idea' | 'active'>('idea')
  const [size, setSize] = useState<'small' | 'medium' | 'large' | 'epic'>('medium')
  const [cat, setCat] = useState('')
  const [emoji, setEmoji] = useState('📁')
  const [accent, setAccent] = useState('#58a6ff')
  const [deadline, setDeadline] = useState('')
  const [tplId, setTplId] = useState<number | ''>('')
  const [kpiMode, setKpiMode] = useState<'' | 'custom'>('')
  const [kpiMetric, setKpiMetric] = useState('')
  const [kpiTarget, setKpiTarget] = useState('')
  const [saving, setSaving] = useState(false)
  const { toast } = useToast()

  async function submit() {
    if (!name.trim()) return
    setSaving(true)
    try {
      const p = await pmCreateProject({
        name: name.trim(), description: desc || undefined, status, size,
        category: cat || undefined, emoji_icon: emoji, accent_color: accent,
        deadline: deadline || undefined,
        template_id: tplId ? Number(tplId) : undefined,
        kpi_mode: kpiMode || undefined,
        kpi_metric_name: kpiMetric || undefined,
        kpi_target_value: kpiTarget ? parseFloat(kpiTarget) : undefined,
      })
      toast({ kind: 'success', title: 'Project created', detail: p.name })
      onCreate(p)
    } catch (e) {
      toast({ kind: 'error', title: 'Create failed', detail: (e as Error).message })
    } finally { setSaving(false) }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
      <motion.div initial={{ opacity: 0, scale: 0.95, y: 10 }} animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95 }}
        className="w-full max-w-lg rounded-2xl border border-border bg-surface shadow-2xl">
        <div className="flex items-center justify-between px-6 pt-5 pb-4 border-b border-border">
          <h2 className="text-base font-semibold text-heading">New Project</h2>
          <button onClick={onClose} className="text-muted hover:text-text"><X size={18} /></button>
        </div>
        <div className="px-6 py-4 space-y-4 max-h-[70vh] overflow-y-auto">
          <div className="flex gap-3">
            <div>
              <label className="text-[11px] text-muted uppercase tracking-wider">Icon</label>
              <div className="flex flex-wrap gap-1 w-28 mt-1">
                {EMOJIS.map(e => (
                  <button key={e} onClick={() => setEmoji(e)}
                    className={`w-7 h-7 flex items-center justify-center rounded text-base transition-colors ${emoji === e ? 'bg-accent/20 ring-1 ring-accent' : 'hover:bg-white/5'}`}>
                    {e}
                  </button>
                ))}
              </div>
            </div>
            <div className="flex-1 space-y-3">
              <div>
                <label className="text-[11px] text-muted uppercase tracking-wider">Name *</label>
                <input autoFocus value={name} onChange={e => setName(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && submit()}
                  className="mt-1 w-full rounded-lg border border-border bg-panel px-3 py-2 text-sm text-text outline-none focus:border-accent"
                  placeholder="Project name" />
              </div>
              <div>
                <label className="text-[11px] text-muted uppercase tracking-wider">Description</label>
                <textarea value={desc} onChange={e => setDesc(e.target.value)} rows={2}
                  className="mt-1 w-full rounded-lg border border-border bg-panel px-3 py-2 text-sm text-text outline-none focus:border-accent resize-none"
                  placeholder="Optional" />
              </div>
            </div>
          </div>
          <div>
            <label className="text-[11px] text-muted uppercase tracking-wider">Accent colour</label>
            <div className="flex gap-2 mt-1">
              {ACCENTS.map(c => (
                <button key={c} onClick={() => setAccent(c)}
                  className={`w-6 h-6 rounded-full transition-transform ${accent === c ? 'ring-2 ring-offset-1 ring-offset-surface scale-110' : ''}`}
                  style={{ background: c }} />
              ))}
            </div>
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="text-[11px] text-muted uppercase tracking-wider">Status</label>
              <select value={status} onChange={e => setStatus(e.target.value as 'idea' | 'active')}
                className="mt-1 w-full rounded-lg border border-border bg-panel px-2 py-2 text-sm text-text outline-none focus:border-accent">
                <option value="idea">Idea</option><option value="active">Active</option>
              </select>
            </div>
            <div>
              <label className="text-[11px] text-muted uppercase tracking-wider">Size</label>
              <select value={size} onChange={e => setSize(e.target.value as typeof size)}
                className="mt-1 w-full rounded-lg border border-border bg-panel px-2 py-2 text-sm text-text outline-none focus:border-accent">
                <option value="small">Small</option><option value="medium">Medium</option>
                <option value="large">Large</option><option value="epic">Epic</option>
              </select>
            </div>
            <div>
              <label className="text-[11px] text-muted uppercase tracking-wider">Category</label>
              <input value={cat} onChange={e => setCat(e.target.value)}
                className="mt-1 w-full rounded-lg border border-border bg-panel px-2 py-2 text-sm text-text outline-none focus:border-accent"
                placeholder="e.g. Business" />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-[11px] text-muted uppercase tracking-wider">Deadline</label>
              <input type="date" value={deadline} onChange={e => setDeadline(e.target.value)}
                className="mt-1 w-full rounded-lg border border-border bg-panel px-2 py-2 text-sm text-text outline-none focus:border-accent" />
            </div>
            {templates.length > 0 && (
              <div>
                <label className="text-[11px] text-muted uppercase tracking-wider">Template</label>
                <select value={tplId} onChange={e => setTplId(e.target.value ? Number(e.target.value) : '')}
                  className="mt-1 w-full rounded-lg border border-border bg-panel px-2 py-2 text-sm text-text outline-none focus:border-accent">
                  <option value="">None</option>
                  {templates.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
                </select>
              </div>
            )}
          </div>
          <div>
            <label className="text-[11px] text-muted uppercase tracking-wider">KPI</label>
            <select value={kpiMode} onChange={e => setKpiMode(e.target.value as '' | 'custom')}
              className="mt-1 w-full rounded-lg border border-border bg-panel px-2 py-2 text-sm text-text outline-none focus:border-accent">
              <option value="">Skip</option><option value="custom">Define custom KPI</option>
            </select>
            {kpiMode === 'custom' && (
              <div className="flex gap-2 mt-2">
                <input value={kpiMetric} onChange={e => setKpiMetric(e.target.value)} placeholder="Metric name"
                  className="flex-1 rounded-lg border border-border bg-panel px-2 py-1.5 text-sm text-text outline-none focus:border-accent" />
                <input value={kpiTarget} onChange={e => setKpiTarget(e.target.value)} placeholder="Target" type="number"
                  className="w-24 rounded-lg border border-border bg-panel px-2 py-1.5 text-sm text-text outline-none focus:border-accent" />
              </div>
            )}
          </div>
        </div>
        <div className="flex justify-end gap-3 px-6 py-4 border-t border-border">
          <button onClick={onClose} className="px-4 py-2 text-sm text-muted hover:text-text rounded-lg hover:bg-white/5">Cancel</button>
          <button onClick={submit} disabled={saving || !name.trim()}
            className="px-4 py-2 text-sm font-medium bg-accent text-white rounded-lg hover:bg-accent/90 disabled:opacity-50 transition-colors">
            {saving ? 'Creating…' : 'Create Project'}
          </button>
        </div>
      </motion.div>
    </div>
  )
}

// ── Tab: Overview ─────────────────────────────────────────────────────────────
function TabOverview({ project, goals, activity }: {
  project: PMProject; goals: PMGoal[]; activity: PMActivity[]
}) {
  const overdue = project.deadline && project.status !== 'done' && new Date(project.deadline) < new Date()
  return (
    <div className="p-5 space-y-5">
      <div className="rounded-xl border border-border bg-panel p-4 space-y-3">
        <div className="flex items-center gap-3">
          <span className="text-3xl">{project.emoji_icon}</span>
          <div className="flex-1">
            <div className="text-lg font-bold text-heading">{project.name}</div>
            {project.description && <div className="text-sm text-muted mt-0.5">{project.description}</div>}
          </div>
          <div className="text-right">
            <div className="text-2xl font-bold text-accent">{project.progress_pct}%</div>
            <div className="text-[11px] text-muted">{project.task_done}/{project.task_count} tasks</div>
          </div>
        </div>
        <Bar pct={project.progress_pct} />
        <div className="flex items-center gap-3 flex-wrap text-[12px]">
          <span className={`flex items-center gap-1 rounded-full border px-2 py-0.5 font-medium ${(STATUS_CFG[project.status] ?? STATUS_CFG.idea).color}`}>
            {(STATUS_CFG[project.status] ?? STATUS_CFG.idea).label}
          </span>
          <span className={SIZE_CFG[project.size] ?? SIZE_CFG.medium}>{project.size}</span>
          {project.deadline && (
            <span className={`flex items-center gap-1 ${overdue ? 'text-danger' : 'text-muted'}`}>
              <Calendar size={12} />{fmtDate(project.deadline)}
            </span>
          )}
          {project.category && <span className="text-muted">{project.category}</span>}
        </div>
        {project.kpi_metric_name && (
          <div className="rounded-lg bg-white/4 px-3 py-2 flex items-center justify-between text-sm">
            <span className="text-muted">KPI: {project.kpi_metric_name}</span>
            <span className="font-medium text-accent">{project.kpi_current_value} / {project.kpi_target_value}</span>
          </div>
        )}
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-wider text-muted mb-2">Goals</div>
          {goals.length === 0
            ? <div className="text-sm text-muted rounded-lg border border-border p-3">No goals yet</div>
            : goals.slice(0, 4).map(g => (
              <div key={g.id} className="rounded-lg border border-border bg-panel p-3 mb-2">
                <div className="flex justify-between text-[12px] mb-1">
                  <span className="text-text font-medium truncate">{g.title}</span>
                  <span className="text-accent ml-2 shrink-0">{g.progress_pct}%</span>
                </div>
                <Bar pct={g.progress_pct} />
                {g.metric_name && <div className="text-[11px] text-muted mt-1">{g.current_value}/{g.target_value} {g.metric_name}</div>}
              </div>
            ))
          }
        </div>
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-wider text-muted mb-2">Recent Activity</div>
          {activity.length === 0
            ? <div className="text-sm text-muted rounded-lg border border-border p-3">No activity yet</div>
            : activity.slice(0, 8).map(a => (
              <div key={a.id} className="flex items-start gap-2 text-[12px] mb-1.5">
                <span className={`mt-0.5 rounded-full p-1 ${a.actor === 'tobi' ? 'bg-accent/15 text-accent' : 'bg-white/8 text-muted'}`}>
                  {a.actor === 'tobi' ? <Bot size={10} /> : <User size={10} />}
                </span>
                <div className="flex-1 min-w-0">
                  <span className="text-text">{a.summary}</span>
                  <span className="text-muted ml-2">{fmtAgo(a.created_at)}</span>
                </div>
              </div>
            ))
          }
        </div>
      </div>
    </div>
  )
}

// ── Tab: Tasks ────────────────────────────────────────────────────────────────
type PMTask = TaskItem & { sub_tasks?: { id: string; title: string; completed: boolean }[]; time_estimate?: string; pm_goal_id?: number }

function TabTasks({ projectId, onTaskChange }: { projectId: number; onTaskChange: () => void }) {
  const [tasks, setTasks] = useState<PMTask[]>([])
  const [loading, setLoading] = useState(true)
  const [quickAdd, setQuickAdd] = useState('')
  const [addingDetails, setAddingDetails] = useState(false)
  const [newTitle, setNewTitle] = useState('')
  const [newPriority, setNewPriority] = useState('P2')
  const [newAssignee, setNewAssignee] = useState('owner')
  const [newDue, setNewDue] = useState('')
  const [filterStatus, setFilterStatus] = useState('all')
  const [filterAssignee, setFilterAssignee] = useState('all')
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editTitle, setEditTitle] = useState('')
  const { toast } = useToast()

  const load = useCallback(async () => {
    try {
      const r = await pmListTasks(projectId)
      setTasks(r.items as PMTask[])
    } catch { /* keep prior */ } finally { setLoading(false) }
  }, [projectId])

  useEffect(() => { load() }, [load])

  async function addTask(title: string, priority = 'P2', agent = 'tobi', due_at?: string) {
    if (!title.trim()) return
    try {
      await pmCreateTask(projectId, { title: title.trim(), priority, agent, due_at: due_at || undefined })
      load(); onTaskChange()
      toast({ kind: 'success', title: 'Task added' })
    } catch (e) { toast({ kind: 'error', title: 'Failed', detail: (e as Error).message }) }
  }

  async function handleQuickAdd() {
    await addTask(quickAdd)
    setQuickAdd('')
  }

  async function handleDetailAdd() {
    await addTask(newTitle, newPriority, newAssignee === 'owner' ? 'tobi' : 'tobi', newDue)
    setNewTitle(''); setNewDue(''); setAddingDetails(false)
  }

  async function toggleDone(task: PMTask) {
    const next: TaskStatus = task.status === 'done' ? 'planned' : 'done'
    try {
      await patchTask(task.id, { status: next, confirmed: true })
      load(); onTaskChange()
    } catch (e) { toast({ kind: 'error', title: 'Update failed', detail: (e as Error).message }) }
  }

  async function changeStatus(task: PMTask, status: string) {
    try {
      await patchTask(task.id, { status: status as TaskStatus, confirmed: true })
      load(); onTaskChange()
    } catch (e) { toast({ kind: 'error', title: 'Update failed', detail: (e as Error).message }) }
  }

  async function changePriority(task: PMTask, priority: string) {
    try {
      await patchTask(task.id, { priority: priority as any, confirmed: true })
      load()
    } catch { /* ignore */ }
  }

  async function saveTitle(task: PMTask) {
    if (!editTitle.trim()) return
    try {
      await patchTask(task.id, { title: editTitle.trim() })
      setEditingId(null); load()
    } catch { toast({ kind: 'error', title: 'Update failed' }) }
  }

  async function removeTask(task: PMTask) {
    try {
      await deleteTask(task.id)
      load(); onTaskChange()
      toast({ kind: 'success', title: 'Task deleted' })
    } catch (e) { toast({ kind: 'error', title: 'Delete failed', detail: (e as Error).message }) }
  }

  const displayed = tasks.filter(t => {
    if (filterStatus !== 'all' && t.status !== filterStatus) return false
    if (filterAssignee === 'me' && t.agent !== 'tobi') return false
    if (filterAssignee === 'tobi' && t.agent === 'tobi') return false
    return true
  })

  return (
    <div className="flex flex-col h-full">
      {/* Quick-add bar */}
      <div className="flex gap-2 p-4 border-b border-border">
        <input value={quickAdd} onChange={e => setQuickAdd(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && handleQuickAdd()}
          className="flex-1 rounded-lg border border-border bg-panel px-3 py-2 text-sm text-text outline-none focus:border-accent"
          placeholder="Quick add task… (Enter)" />
        <button onClick={handleQuickAdd} disabled={!quickAdd.trim()}
          className="rounded-lg bg-accent px-3 py-2 text-white hover:bg-accent/90 disabled:opacity-50 transition-colors">
          <Plus size={16} />
        </button>
        <button onClick={() => setAddingDetails(d => !d)}
          className={`rounded-lg border px-3 py-2 text-sm transition-colors ${addingDetails ? 'border-accent text-accent bg-accent/10' : 'border-border text-muted hover:text-text'}`}>
          Details
        </button>
      </div>

      {/* Detailed add form */}
      <AnimatePresence>
        {addingDetails && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }} className="overflow-hidden border-b border-border">
            <div className="p-4 space-y-3">
              <input value={newTitle} onChange={e => setNewTitle(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleDetailAdd()}
                autoFocus placeholder="Task title *"
                className="w-full rounded-lg border border-border bg-panel px-3 py-2 text-sm text-text outline-none focus:border-accent" />
              <div className="flex gap-2">
                <select value={newPriority} onChange={e => setNewPriority(e.target.value)}
                  className="rounded-lg border border-border bg-panel px-2 py-1.5 text-sm text-text outline-none focus:border-accent">
                  <option value="P0">P0 — Critical</option><option value="P1">P1 — High</option>
                  <option value="P2">P2 — Normal</option><option value="P3">P3 — Low</option>
                </select>
                <select value={newAssignee} onChange={e => setNewAssignee(e.target.value)}
                  className="rounded-lg border border-border bg-panel px-2 py-1.5 text-sm text-text outline-none focus:border-accent">
                  <option value="owner">Me</option><option value="tobi">Tobi</option>
                </select>
                <input type="date" value={newDue} onChange={e => setNewDue(e.target.value)}
                  className="flex-1 rounded-lg border border-border bg-panel px-2 py-1.5 text-sm text-text outline-none focus:border-accent" />
              </div>
              <div className="flex gap-2">
                <button onClick={handleDetailAdd} disabled={!newTitle.trim()}
                  className="px-3 py-1.5 text-sm bg-accent text-white rounded-lg hover:bg-accent/90 disabled:opacity-50">Add Task</button>
                <button onClick={() => setAddingDetails(false)}
                  className="px-3 py-1.5 text-sm text-muted hover:text-text rounded-lg hover:bg-white/5">Cancel</button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Filters */}
      <div className="flex items-center gap-2 px-4 py-2 border-b border-border overflow-x-auto shrink-0">
        <span className="text-[11px] text-muted shrink-0">Status:</span>
        {['all','planned','in_progress','blocked','done'].map(s => (
          <button key={s} onClick={() => setFilterStatus(s)}
            className={`text-[11px] px-2 py-1 rounded-full border shrink-0 transition-colors ${filterStatus === s ? 'bg-accent/15 border-accent/30 text-accent' : 'border-border text-muted hover:text-text'}`}>
            {s === 'all' ? 'All' : s.replace('_', ' ')}
          </button>
        ))}
        <span className="text-[11px] text-muted shrink-0 ml-2">Assign:</span>
        {[['all','All'],['me','Me'],['tobi','Tobi']].map(([v, l]) => (
          <button key={v} onClick={() => setFilterAssignee(v)}
            className={`text-[11px] px-2 py-1 rounded-full border shrink-0 transition-colors ${filterAssignee === v ? 'bg-accent/15 border-accent/30 text-accent' : 'border-border text-muted hover:text-text'}`}>
            {l}
          </button>
        ))}
      </div>

      {/* Task list */}
      <div className="flex-1 overflow-y-auto">
        {loading ? (
          <PageLoader preset="projects" compact />
        ) : displayed.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-32 gap-2 text-muted">
            <CheckCircle2 size={28} className="text-muted/30" />
            <span className="text-sm">No tasks yet — use the bar above</span>
          </div>
        ) : (
          <div className="divide-y divide-border/50">
            {displayed.map(task => (
              <div key={task.id}>
                <div className="flex items-center gap-2 px-4 py-2.5 hover:bg-white/2 group">
                  {/* Checkbox */}
                  <button onClick={() => toggleDone(task)} className="shrink-0">
                    {task.status === 'done'
                      ? <CheckCircle2 size={16} className="text-success" />
                      : <Circle size={16} className="text-muted hover:text-accent" />}
                  </button>

                  {/* Title (inline editable) */}
                  {editingId === task.id ? (
                    <input autoFocus value={editTitle} onChange={e => setEditTitle(e.target.value)}
                      onKeyDown={e => { if (e.key === 'Enter') saveTitle(task); if (e.key === 'Escape') setEditingId(null) }}
                      onBlur={() => saveTitle(task)}
                      className="flex-1 rounded border border-accent bg-panel px-2 py-0.5 text-sm text-text outline-none" />
                  ) : (
                    <span
                      onDoubleClick={() => { setEditingId(task.id); setEditTitle(task.title) }}
                      className={`flex-1 text-sm cursor-text ${task.status === 'done' ? 'line-through text-muted' : 'text-text'}`}
                      title="Double-click to edit">
                      {task.title}
                    </span>
                  )}

                  {/* Priority */}
                  <select value={task.priority} onChange={e => changePriority(task, e.target.value)}
                    onClick={e => e.stopPropagation()}
                    className={`text-[11px] bg-transparent border-0 outline-none cursor-pointer ${PRIORITY_COLORS[task.priority] ?? 'text-muted'}`}>
                    <option value="P0">P0</option><option value="P1">P1</option>
                    <option value="P2">P2</option><option value="P3">P3</option>
                  </select>

                  {/* Status */}
                  <select value={task.status} onChange={e => changeStatus(task, e.target.value)}
                    onClick={e => e.stopPropagation()}
                    className={`text-[11px] px-1.5 py-0.5 rounded-full border-0 outline-none cursor-pointer ${TASK_STATUS_COLORS[task.status] ?? 'bg-muted/10 text-muted'}`}>
                    <option value="planned">Planned</option>
                    <option value="in_progress">In Progress</option>
                    <option value="paused">Paused</option>
                    <option value="blocked">Blocked</option>
                    <option value="done">Done</option>
                  </select>

                  {/* Assignee */}
                  <span className={`text-[11px] flex items-center gap-1 ${task.agent === 'tobi' ? 'text-accent' : 'text-muted'}`}>
                    {task.agent === 'tobi' ? <Bot size={11} /> : <User size={11} />}
                  </span>

                  {/* Due date */}
                  {task.due_at && (
                    <span className={`text-[11px] flex items-center gap-1 ${task.is_overdue ? 'text-danger' : 'text-muted'}`}>
                      <Calendar size={11} />{fmtDate(task.due_at)}
                    </span>
                  )}

                  {/* Actions */}
                  <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                    <button onClick={() => { setExpandedId(expandedId === task.id ? null : task.id) }}
                      className="text-muted hover:text-text">
                      {expandedId === task.id ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                    </button>
                    <button onClick={() => removeTask(task)} className="text-muted hover:text-danger">
                      <Trash2 size={13} />
                    </button>
                  </div>
                </div>

                {/* Sub-tasks */}
                <AnimatePresence>
                  {expandedId === task.id && (
                    <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }} className="overflow-hidden border-t border-border/30 bg-white/2">
                      <SubTasks task={task} projectId={projectId} />
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

// ── Sub-tasks ─────────────────────────────────────────────────────────────────
function SubTasks({ task, projectId }: { task: PMTask; projectId: number }) {
  const initial = (task.sub_tasks ?? []).map(s => ({ id: s.id || crypto.randomUUID(), title: s.title, completed: !!s.completed }))
  const [items, setItems] = useState(initial)
  const [newSub, setNewSub] = useState('')
  const { toast } = useToast()

  async function persist(next: typeof items) {
    setItems(next)
    try {
      const r = await fetch(`/api/pm/projects/${projectId}/tasks/${task.id}/subtasks`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ subtasks: next }),
      })
      if (!r.ok) throw new Error(await r.text())
    } catch { toast({ kind: 'error', title: 'Sub-task save failed' }) }
  }

  async function addSub() {
    if (!newSub.trim()) return
    await persist([...items, { id: crypto.randomUUID(), title: newSub.trim(), completed: false }])
    setNewSub('')
  }

  return (
    <div className="pl-10 pr-4 py-2 space-y-1">
      {items.map(s => (
        <div key={s.id} className="flex items-center gap-2 group/sub">
          <button onClick={() => persist(items.map(x => x.id === s.id ? { ...x, completed: !x.completed } : x))}>
            {s.completed ? <CheckCircle2 size={13} className="text-success" /> : <Circle size={13} className="text-muted" />}
          </button>
          <span className={`text-[12px] flex-1 ${s.completed ? 'line-through text-muted' : 'text-text'}`}>{s.title}</span>
          <button onClick={() => persist(items.filter(x => x.id !== s.id))}
            className="text-muted hover:text-danger opacity-0 group-hover/sub:opacity-100 transition-opacity">
            <X size={12} />
          </button>
        </div>
      ))}
      <div className="flex gap-2">
        <input value={newSub} onChange={e => setNewSub(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && addSub()}
          className="text-[12px] flex-1 bg-transparent border-b border-border text-text outline-none focus:border-accent py-0.5"
          placeholder="+ Sub-task (Enter to add)" />
      </div>
    </div>
  )
}

// ── Tab: Goals ────────────────────────────────────────────────────────────────
function TabGoals({ projectId, goals, onRefresh }: { projectId: number; goals: PMGoal[]; onRefresh: () => void }) {
  const [adding, setAdding] = useState(false)
  const [title, setTitle] = useState('')
  const [metric, setMetric] = useState('')
  const [target, setTarget] = useState('100')
  const [current, setCurrent] = useState('0')
  const [due, setDue] = useState('')
  const [editMap, setEditMap] = useState<Record<number, string>>({})
  const { toast } = useToast()

  async function createGoal() {
    if (!title.trim()) return
    try {
      await pmCreateGoal(projectId, { title: title.trim(), metric_name: metric || undefined,
        target_value: parseFloat(target) || 100, current_value: parseFloat(current) || 0,
        due_date: due || undefined })
      setTitle(''); setMetric(''); setTarget('100'); setCurrent('0'); setDue('')
      setAdding(false); onRefresh()
      toast({ kind: 'success', title: 'Goal added' })
    } catch (e) { toast({ kind: 'error', title: 'Failed', detail: (e as Error).message }) }
  }

  async function updateCurrent(g: PMGoal, raw: string) {
    const v = parseFloat(raw)
    if (isNaN(v)) return
    try {
      await pmPatchGoal(projectId, g.id, { current_value: v })
      setEditMap(m => { const n = { ...m }; delete n[g.id]; return n })
      onRefresh()
    } catch { toast({ kind: 'error', title: 'Update failed' }) }
  }

  async function deleteGoal(g: PMGoal) {
    try { await pmDeleteGoal(projectId, g.id); onRefresh() }
    catch { toast({ kind: 'error', title: 'Delete failed' }) }
  }

  return (
    <div className="p-5 space-y-4">
      {goals.length === 0 && !adding && (
        <div className="text-center py-8 text-muted">
          <Target size={32} className="mx-auto mb-2 text-muted/40" />
          <div className="text-sm">No goals yet. Goals drive project progress %.</div>
        </div>
      )}
      {goals.map(g => (
        <div key={g.id} className="rounded-xl border border-border bg-panel p-4 space-y-2">
          <div className="flex items-start justify-between gap-2">
            <div className="flex-1">
              <div className="font-semibold text-sm text-text">{g.title}</div>
              <div className="text-[12px] text-muted mt-0.5 flex items-center gap-2">
                {editMap[g.id] !== undefined ? (
                  <>
                    <input autoFocus type="number" value={editMap[g.id]}
                      onChange={e => setEditMap(m => ({ ...m, [g.id]: e.target.value }))}
                      onKeyDown={e => { if (e.key === 'Enter') updateCurrent(g, editMap[g.id]); if (e.key === 'Escape') setEditMap(m => { const n = { ...m }; delete n[g.id]; return n }) }}
                      className="w-20 rounded border border-accent bg-panel px-2 py-0.5 text-sm text-text outline-none" />
                    <span>/ {g.target_value} {g.metric_name}</span>
                    <button onClick={() => updateCurrent(g, editMap[g.id])} className="text-success"><Save size={13} /></button>
                    <button onClick={() => setEditMap(m => { const n = { ...m }; delete n[g.id]; return n })} className="text-muted"><X size={13} /></button>
                  </>
                ) : (
                  <button onClick={() => setEditMap(m => ({ ...m, [g.id]: String(g.current_value) }))}
                    className="hover:text-accent transition-colors">
                    {g.current_value}{g.metric_name ? ` / ${g.target_value} ${g.metric_name}` : ''} ✎
                  </button>
                )}
              </div>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <span className="text-lg font-bold text-accent">{g.progress_pct}%</span>
              {g.due_date && <span className="text-[11px] text-muted flex items-center gap-1"><Calendar size={11} />{fmtDate(g.due_date)}</span>}
              <button onClick={() => deleteGoal(g)} className="text-muted hover:text-danger transition-colors"><Trash2 size={13} /></button>
            </div>
          </div>
          <Bar pct={g.progress_pct} />
        </div>
      ))}

      {adding ? (
        <div className="rounded-xl border border-accent/30 bg-panel p-4 space-y-3">
          <div className="text-sm font-medium text-text">New Goal</div>
          <input value={title} onChange={e => setTitle(e.target.value)} placeholder="Goal title *"
            autoFocus onKeyDown={e => e.key === 'Enter' && createGoal()}
            className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-text outline-none focus:border-accent" />
          <div className="grid grid-cols-3 gap-2">
            <input value={metric} onChange={e => setMetric(e.target.value)} placeholder="Metric (e.g. MAU)"
              className="rounded-lg border border-border bg-surface px-2 py-1.5 text-sm text-text outline-none focus:border-accent" />
            <input value={target} onChange={e => setTarget(e.target.value)} type="number" placeholder="Target"
              className="rounded-lg border border-border bg-surface px-2 py-1.5 text-sm text-text outline-none focus:border-accent" />
            <input value={current} onChange={e => setCurrent(e.target.value)} type="number" placeholder="Current"
              className="rounded-lg border border-border bg-surface px-2 py-1.5 text-sm text-text outline-none focus:border-accent" />
          </div>
          <input value={due} onChange={e => setDue(e.target.value)} type="date"
            className="w-full rounded-lg border border-border bg-surface px-2 py-1.5 text-sm text-text outline-none focus:border-accent" />
          <div className="flex gap-2">
            <button onClick={createGoal} disabled={!title.trim()}
              className="px-3 py-1.5 text-sm bg-accent text-white rounded-lg hover:bg-accent/90 disabled:opacity-50">Add Goal</button>
            <button onClick={() => setAdding(false)} className="px-3 py-1.5 text-sm text-muted hover:text-text rounded-lg hover:bg-white/5">Cancel</button>
          </div>
        </div>
      ) : (
        <button onClick={() => setAdding(true)} className="flex items-center gap-2 text-sm text-muted hover:text-accent transition-colors">
          <Plus size={15} /> Add Goal
        </button>
      )}
    </div>
  )
}

// ── Tab: Missions ─────────────────────────────────────────────────────────────
function TabMissions({ projectId }: { projectId: number }) {
  const [missions, setMissions] = useState<PMMission[]>([])
  const [prompt, setPrompt] = useState('')
  const [saving, setSaving] = useState(false)
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const { toast } = useToast()

  useEffect(() => { pmListMissions(projectId).then(r => setMissions(r.items)).catch(() => {}) }, [projectId])

  async function runMission() {
    if (!prompt.trim()) return
    setSaving(true)
    try {
      const m = await pmCreateMission(projectId, prompt.trim())
      setMissions(prev => [m, ...prev]); setPrompt('')
      toast({ kind: 'info', title: 'Mission queued', detail: 'Tobi will pick this up via Telegram' })
    } catch (e) { toast({ kind: 'error', title: 'Failed', detail: (e as Error).message }) }
    finally { setSaving(false) }
  }

  const STATUS_BADGE: Record<string, string> = {
    queued:  'bg-warning/15 text-warning',
    running: 'bg-accent/15 text-accent',
    done:    'bg-success/15 text-success',
    failed:  'bg-danger/15 text-danger',
  }

  return (
    <div className="p-5 space-y-4">
      <div className="rounded-xl border border-border bg-panel p-4 space-y-3">
        <div className="text-[11px] font-semibold uppercase tracking-wider text-muted">Assign Tobi a Mission</div>
        <textarea value={prompt} onChange={e => setPrompt(e.target.value)} rows={3}
          className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-text outline-none focus:border-accent resize-none"
          placeholder="e.g. Research top 5 competitors and create tasks for each finding…" />
        <button onClick={runMission} disabled={saving || !prompt.trim()}
          className="flex items-center gap-2 px-4 py-2 text-sm font-medium bg-accent text-white rounded-lg hover:bg-accent/90 disabled:opacity-50 transition-colors">
          <Play size={14} />{saving ? 'Queuing…' : 'Queue Mission'}
        </button>
      </div>
      <div className="text-[11px] font-semibold uppercase tracking-wider text-muted">Mission Log</div>
      {missions.length === 0
        ? <div className="text-sm text-muted text-center py-6">No missions yet</div>
        : missions.map(m => (
          <div key={m.id} className="rounded-xl border border-border bg-panel overflow-hidden">
            <div className="flex items-start gap-3 p-3 cursor-pointer hover:bg-white/2"
              onClick={() => setExpandedId(expandedId === m.id ? null : m.id)}>
              <Bot size={16} className="text-accent mt-0.5 shrink-0" />
              <div className="flex-1 min-w-0">
                <div className="text-sm text-text line-clamp-2">{m.prompt}</div>
                <div className="flex items-center gap-3 mt-1 text-[11px] text-muted">
                  <span>{fmtAgo(m.created_at)}</span>
                  {m.tasks_created > 0 && <span>{m.tasks_created} tasks created</span>}
                  {m.duration_ms && <span>{(m.duration_ms / 1000).toFixed(1)}s</span>}
                </div>
              </div>
              <span className={`text-[11px] px-2 py-0.5 rounded-full font-medium shrink-0 ${STATUS_BADGE[m.status] ?? 'bg-muted/10 text-muted'}`}>
                {m.status}
              </span>
            </div>
            <AnimatePresence>
              {expandedId === m.id && m.output && (
                <motion.div initial={{ height: 0 }} animate={{ height: 'auto' }} exit={{ height: 0 }}
                  className="overflow-hidden border-t border-border/40">
                  <pre className="p-3 text-[12px] text-muted font-mono whitespace-pre-wrap">{m.output}</pre>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        ))
      }
    </div>
  )
}

// ── Tab: Docs ─────────────────────────────────────────────────────────────────
function TabDocs({ projectId }: { projectId: number }) {
  const [files, setFiles] = useState<PMFile[]>([])
  const [filename, setFilename] = useState('')
  const [adding, setAdding] = useState(false)
  const { toast } = useToast()

  useEffect(() => { pmListFiles(projectId).then(r => setFiles(r.items)).catch(() => {}) }, [projectId])

  async function attach() {
    if (!filename.trim()) return
    try {
      const f = await pmCreateFile(projectId, { filename: filename.trim() })
      setFiles(prev => [f, ...prev]); setFilename(''); setAdding(false)
      toast({ kind: 'success', title: 'File attached' })
    } catch { toast({ kind: 'error', title: 'Failed' }) }
  }

  async function del(f: PMFile) {
    try { await pmDeleteFile(projectId, f.id); setFiles(prev => prev.filter(x => x.id !== f.id)) }
    catch { toast({ kind: 'error', title: 'Failed' }) }
  }

  return (
    <div className="p-5 space-y-4">
      {files.length === 0 && !adding
        ? <div className="text-center py-8 text-muted"><Paperclip size={32} className="mx-auto mb-2 text-muted/40" /><div className="text-sm">No files attached yet.</div></div>
        : files.map(f => (
          <div key={f.id} className="flex items-center gap-3 rounded-lg border border-border bg-panel px-3 py-2.5 group">
            <FileText size={16} className="text-muted shrink-0" />
            <div className="flex-1 min-w-0">
              <div className="text-sm text-text truncate">{f.filename}</div>
              <div className="text-[11px] text-muted">{f.uploaded_by} · {fmtAgo(f.created_at)}</div>
            </div>
            <button onClick={() => del(f)} className="text-muted hover:text-danger opacity-0 group-hover:opacity-100 transition-opacity"><Trash2 size={14} /></button>
          </div>
        ))
      }
      {adding ? (
        <div className="flex gap-2">
          <input value={filename} onChange={e => setFilename(e.target.value)} autoFocus
            onKeyDown={e => e.key === 'Enter' && attach()}
            className="flex-1 rounded-lg border border-border bg-panel px-3 py-2 text-sm text-text outline-none focus:border-accent"
            placeholder="Filename or URL" />
          <button onClick={attach} disabled={!filename.trim()} className="px-3 py-2 text-sm bg-accent text-white rounded-lg disabled:opacity-50">Attach</button>
          <button onClick={() => setAdding(false)} className="px-3 py-2 text-sm text-muted rounded-lg hover:bg-white/5"><X size={16} /></button>
        </div>
      ) : (
        <button onClick={() => setAdding(true)} className="flex items-center gap-2 text-sm text-muted hover:text-accent transition-colors">
          <Plus size={15} /> Attach File
        </button>
      )}
    </div>
  )
}

// ── Tab: Activity ─────────────────────────────────────────────────────────────
function TabActivity({ projectId }: { projectId: number }) {
  const [items, setItems] = useState<PMActivity[]>([])
  const [filter, setFilter] = useState<'all' | 'user' | 'tobi'>('all')
  const [expandedId, setExpandedId] = useState<number | null>(null)

  useEffect(() => {
    pmListActivity(projectId, filter === 'all' ? undefined : filter)
      .then(r => setItems(r.items)).catch(() => {})
  }, [projectId, filter])

  return (
    <div className="p-5 space-y-4">
      <div className="flex gap-2">
        {(['all','user','tobi'] as const).map(a => (
          <button key={a} onClick={() => setFilter(a)}
            className={`text-[11px] px-3 py-1 rounded-full border transition-colors ${filter === a ? 'bg-accent/15 border-accent/30 text-accent' : 'border-border text-muted hover:text-text'}`}>
            {a === 'all' ? 'All' : a === 'user' ? 'Me' : 'Tobi'}
          </button>
        ))}
      </div>
      {items.length === 0
        ? <div className="text-center py-8 text-muted"><Activity size={32} className="mx-auto mb-2 text-muted/40" /><div className="text-sm">No activity yet</div></div>
        : items.map(a => (
          <div key={a.id} className="rounded-lg border border-border bg-panel overflow-hidden">
            <div className="flex items-start gap-3 px-3 py-2.5 cursor-pointer hover:bg-white/2"
              onClick={() => setExpandedId(expandedId === a.id ? null : a.id)}>
              <span className={`mt-0.5 rounded-full p-1.5 ${a.actor === 'tobi' ? 'bg-accent/15 text-accent' : 'bg-white/8 text-muted'}`}>
                {a.actor === 'tobi' ? <Bot size={11} /> : <User size={11} />}
              </span>
              <div className="flex-1 min-w-0">
                <span className="text-sm text-text">{a.summary}</span>
                <div className="text-[11px] text-muted mt-0.5">{fmtAgo(a.created_at)}</div>
              </div>
              {a.diff && <span className="text-muted">{expandedId === a.id ? <ChevronUp size={14} /> : <ChevronDown size={14} />}</span>}
            </div>
            <AnimatePresence>
              {expandedId === a.id && a.diff && (
                <motion.div initial={{ height: 0 }} animate={{ height: 'auto' }} exit={{ height: 0 }}
                  className="overflow-hidden border-t border-border/40">
                  <pre className="p-3 text-[11px] text-muted font-mono">{JSON.stringify(a.diff, null, 2)}</pre>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        ))
      }
    </div>
  )
}

// ── Project detail drawer ─────────────────────────────────────────────────────
type Tab = 'overview' | 'tasks' | 'goals' | 'docs' | 'missions' | 'activity'

function ProjectDrawer({ project: initial, onClose, onUpdated, onDelete }: {
  project: PMProject; onClose: () => void; onUpdated: (p: PMProject) => void; onDelete: () => void
}) {
  const [project, setProject] = useState(initial)
  const [tab, setTab] = useState<Tab>('overview')
  const [goals, setGoals] = useState<PMGoal[]>([])
  const [activity, setActivity] = useState<PMActivity[]>([])
  const [editing, setEditing] = useState(false)
  const [editName, setEditName] = useState(project.name)
  const [editStatus, setEditStatus] = useState<string>(project.status)
  const [savingTpl, setSavingTpl] = useState(false)
  const [tplName, setTplName] = useState('')
  const [showTplInput, setShowTplInput] = useState(false)
  const { toast } = useToast()

  const reload = useCallback(async () => {
    try {
      const [g, a, p] = await Promise.all([
        pmListGoals(project.id),
        pmListActivity(project.id),
        pmGetProject(project.id),
      ])
      setGoals(g.items); setActivity(a.items); setProject(p); onUpdated(p)
    } catch { /* keep prior */ }
  }, [project.id])

  useEffect(() => { reload() }, [reload])

  async function saveEdit() {
    try {
      const p = await pmPatchProject(project.id, { name: editName, status: editStatus as any })
      setProject(p); onUpdated(p); setEditing(false)
    } catch (e) { toast({ kind: 'error', title: 'Update failed', detail: (e as Error).message }) }
  }

  async function saveTemplate() {
    if (!tplName.trim()) return
    setSavingTpl(true)
    try {
      await pmCreateTemplate({ name: tplName.trim(), source_project_id: project.id })
      toast({ kind: 'success', title: 'Template saved', detail: tplName })
      setShowTplInput(false); setTplName('')
    } catch (e) { toast({ kind: 'error', title: 'Failed', detail: (e as Error).message }) }
    finally { setSavingTpl(false) }
  }

  const TABS: { id: Tab; label: string; icon: React.FC<any> }[] = [
    { id: 'overview',  label: 'Overview',  icon: LayoutGrid },
    { id: 'tasks',     label: 'Tasks',     icon: CheckCircle2 },
    { id: 'goals',     label: 'Goals',     icon: Target },
    { id: 'docs',      label: 'Docs',      icon: FileText },
    { id: 'missions',  label: 'Missions',  icon: Zap },
    { id: 'activity',  label: 'Activity',  icon: Activity },
  ]

  return (
    <>
      <div className="fixed inset-0 z-40 bg-black/40" onClick={onClose} />
      <motion.div initial={{ x: '100%' }} animate={{ x: 0 }} exit={{ x: '100%' }}
        transition={{ type: 'spring', damping: 28, stiffness: 300 }}
        className="fixed right-0 top-0 bottom-0 z-50 w-full max-w-2xl bg-surface border-l border-border shadow-2xl flex flex-col">

        {/* Header */}
        <div className="flex items-center gap-3 px-5 py-4 border-b border-border shrink-0"
          style={{ borderTop: `3px solid ${project.accent_color}` }}>
          <span className="text-2xl">{project.emoji_icon}</span>
          <div className="flex-1 min-w-0">
            {editing ? (
              <div className="flex items-center gap-2">
                <input value={editName} onChange={e => setEditName(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && saveEdit()}
                  className="flex-1 rounded-lg border border-accent bg-panel px-2 py-1 text-sm text-text outline-none" />
                <select value={editStatus} onChange={e => setEditStatus(e.target.value)}
                  className="rounded-lg border border-border bg-panel px-2 py-1 text-sm text-text outline-none">
                  <option value="idea">Idea</option><option value="active">Active</option>
                  <option value="done">Done</option><option value="archived">Archived</option>
                </select>
                <button onClick={saveEdit} className="text-success"><Save size={15} /></button>
                <button onClick={() => setEditing(false)} className="text-muted"><X size={15} /></button>
              </div>
            ) : (
              <div className="flex items-center gap-2">
                <h2 className="font-bold text-heading truncate">{project.name}</h2>
                <button onClick={() => setEditing(true)} className="text-muted hover:text-text"><Pencil size={13} /></button>
              </div>
            )}
          </div>
          <button onClick={() => setShowTplInput(s => !s)} title="Save as template"
            className="text-muted hover:text-accent transition-colors"><FolderOutput size={16} /></button>
          <button onClick={reload} className="text-muted hover:text-text"><RefreshCw size={15} /></button>
          <button onClick={onDelete} title="Delete project" className="text-muted hover:text-danger transition-colors"><Trash2 size={16} /></button>
          <button onClick={onClose} className="text-muted hover:text-text ml-1"><X size={18} /></button>
        </div>

        {/* Save-as-template input */}
        <AnimatePresence>
          {showTplInput && (
            <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }} className="overflow-hidden border-b border-border">
              <div className="flex gap-2 px-5 py-3">
                <input value={tplName} onChange={e => setTplName(e.target.value)} autoFocus
                  onKeyDown={e => e.key === 'Enter' && saveTemplate()}
                  placeholder="Template name"
                  className="flex-1 rounded-lg border border-border bg-panel px-3 py-1.5 text-sm text-text outline-none focus:border-accent" />
                <button onClick={saveTemplate} disabled={savingTpl || !tplName.trim()}
                  className="px-3 py-1.5 text-sm bg-accent text-white rounded-lg disabled:opacity-50">Save</button>
                <button onClick={() => setShowTplInput(false)} className="text-muted hover:text-text"><X size={16} /></button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Tabs */}
        <div className="flex items-center gap-0 px-4 border-b border-border overflow-x-auto shrink-0">
          {TABS.map(({ id, label, icon: Icon }) => (
            <button key={id} onClick={() => setTab(id)}
              className={`flex items-center gap-1.5 px-3 py-2.5 text-[12px] font-medium whitespace-nowrap border-b-2 transition-colors ${tab === id ? 'border-accent text-accent' : 'border-transparent text-muted hover:text-text'}`}>
              <Icon size={13} />{label}
            </button>
          ))}
        </div>

        {/* Tab content */}
        <div className="flex-1 overflow-y-auto min-h-0">
          <AnimatePresence mode="wait">
            <motion.div key={tab} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }} transition={{ duration: 0.12 }} className="h-full">
              {tab === 'overview'  && <TabOverview project={project} goals={goals} activity={activity} />}
              {tab === 'tasks'     && <TabTasks projectId={project.id} onTaskChange={reload} />}
              {tab === 'goals'     && <TabGoals projectId={project.id} goals={goals} onRefresh={reload} />}
              {tab === 'docs'      && <TabDocs projectId={project.id} />}
              {tab === 'missions'  && <TabMissions projectId={project.id} />}
              {tab === 'activity'  && <TabActivity projectId={project.id} />}
            </motion.div>
          </AnimatePresence>
        </div>
      </motion.div>
    </>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function Projects() {
  const [projects, setProjects] = useState<PMProject[]>([])
  const [loading, setLoading] = useState(true)
  const [view, setView] = useState<'grid' | 'list'>(() =>
    (localStorage.getItem('tobi.projects.view') as 'grid' | 'list') || 'grid')
  const [search, setSearch] = useState('')
  const [filterStatus, setFilterStatus] = useState('all')
  const [showCreate, setShowCreate] = useState(false)
  const [selected, setSelected] = useState<PMProject | null>(null)
  const [templates, setTemplates] = useState<{ id: number; name: string }[]>([])
  const [dragId, setDragId] = useState<number | null>(null)
  const { toast } = useToast()
  const projectsRef = useRef<PMProject[]>([])
  useEffect(() => { projectsRef.current = projects }, [projects])

  const load = useCallback(async () => {
    try { const r = await pmListProjects(); setProjects(r.items) }
    catch { /* keep */ } finally { setLoading(false) }
  }, [])

  useEffect(() => {
    load()
    pmListTemplates().then(r => setTemplates(r.items)).catch(() => {})
  }, [load])

  function setViewPref(v: 'grid' | 'list') {
    setView(v); localStorage.setItem('tobi.projects.view', v)
  }

  const filtered = projects.filter(p => {
    if (filterStatus !== 'all' && p.status !== filterStatus) return false
    if (search && !p.name.toLowerCase().includes(search.toLowerCase()) &&
        !(p.category ?? '').toLowerCase().includes(search.toLowerCase())) return false
    return true
  })

  async function handleDelete(p: PMProject) {
    if (!confirm(`Delete "${p.name}"? This cannot be undone.`)) return
    try { await pmDeleteProject(p.id); load(); toast({ kind: 'success', title: 'Deleted' }) }
    catch (e) { toast({ kind: 'error', title: 'Failed', detail: (e as Error).message }) }
  }

  // ── drag-to-reorder (only in the default unfiltered view) ──
  const canReorder = filterStatus === 'all' && !search.trim()
  function onDragOverItem(overId: number) {
    if (dragId == null || dragId === overId) return
    setProjects(prev => {
      const from = prev.findIndex(p => p.id === dragId)
      const to = prev.findIndex(p => p.id === overId)
      if (from < 0 || to < 0 || from === to) return prev
      const next = [...prev]
      const [moved] = next.splice(from, 1)
      next.splice(to, 0, moved)
      return next
    })
  }
  async function onDragEndItem() {
    const id = dragId; setDragId(null)
    if (id == null) return
    try { await pmReorderProjects(projectsRef.current.map(p => p.id)) }
    catch (e) { toast({ kind: 'error', title: 'Reorder failed', detail: (e as Error).message }); load() }
  }
  const dragProps = (id: number) => canReorder ? {
    draggable: true,
    onDragStart: (e: React.DragEvent) => { setDragId(id); e.dataTransfer.effectAllowed = 'move' },
    onDragOver: (e: React.DragEvent) => { e.preventDefault(); onDragOverItem(id) },
    onDrop: (e: React.DragEvent) => e.preventDefault(),
    onDragEnd: onDragEndItem,
  } : {}

  const counts = ['all','idea','active','done','archived'].map(s => ({
    s, label: s === 'all' ? 'All' : (STATUS_CFG[s]?.label ?? s),
    n: s === 'all' ? projects.length : projects.filter(p => p.status === s).length,
  }))

  return (
    <div className="relative flex flex-col h-full min-h-0">
      <AmbientField />
      {/* Header */}
      <div className="flex items-center justify-between gap-4 px-6 py-4 border-b border-border shrink-0">
        <div>
          <h1 className="text-xl font-bold text-heading tracking-tight">Projects</h1>
          <div className="text-[12px] text-muted mt-0.5">
            {projects.filter(p => p.status === 'active').length} active · {projects.length} total
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={load} className="text-muted hover:text-text p-2 rounded-lg hover:bg-white/5"><RefreshCw size={15} /></button>
          <div className="flex rounded-lg border border-border overflow-hidden">
            <button onClick={() => setViewPref('grid')}
              className={`p-2 transition-colors ${view === 'grid' ? 'bg-accent/15 text-accent' : 'text-muted hover:text-text'}`}><LayoutGrid size={15} /></button>
            <button onClick={() => setViewPref('list')}
              className={`p-2 transition-colors ${view === 'list' ? 'bg-accent/15 text-accent' : 'text-muted hover:text-text'}`}><List size={15} /></button>
          </div>
          <button onClick={() => setShowCreate(true)}
            className="flex items-center gap-2 rounded-lg bg-accent px-3 py-2 text-sm font-medium text-white hover:bg-accent/90 transition-colors">
            <Plus size={15} /> New Project
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-4 px-6 py-3 border-b border-border overflow-x-auto shrink-0">
        <div className="relative flex-1 max-w-xs">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
          <input value={search} onChange={e => setSearch(e.target.value)}
            className="w-full rounded-lg border border-border bg-panel pl-8 pr-3 py-1.5 text-sm text-text outline-none focus:border-accent"
            placeholder="Search projects…" />
        </div>
        <div className="flex items-center gap-1.5">
          {counts.map(({ s, label, n }) => (
            <button key={s} onClick={() => setFilterStatus(s)}
              className={`flex items-center gap-1.5 text-[11px] px-2.5 py-1 rounded-full border transition-colors ${filterStatus === s ? 'bg-accent/15 border-accent/30 text-accent' : 'border-border text-muted hover:text-text'}`}>
              {label} <span className="opacity-60">{n}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto">
        {loading ? (
          <PageLoader preset="projects" compact />
        ) : filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-48 gap-3 text-muted">
            <TrendingUp size={40} className="text-muted/30" />
            <div className="text-sm">{search || filterStatus !== 'all' ? 'No matching projects' : 'No projects yet'}</div>
            {!search && filterStatus === 'all' && (
              <button onClick={() => setShowCreate(true)}
                className="flex items-center gap-2 text-sm text-accent hover:underline">
                <Plus size={14} /> Create your first project
              </button>
            )}
          </div>
        ) : view === 'grid' ? (
          <div className="p-6 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            <AnimatePresence>
              {filtered.map(p => (
                <div key={p.id} {...dragProps(p.id)}
                  className={`${canReorder ? 'cursor-grab active:cursor-grabbing' : ''} ${dragId === p.id ? 'opacity-40' : ''}`}
                  title={canReorder ? 'Drag to reorder' : undefined}>
                  <ProjectCard project={p} onClick={() => setSelected(p)} onDelete={() => handleDelete(p)} />
                </div>
              ))}
            </AnimatePresence>
          </div>
        ) : (
          <div>
            <div className="flex items-center gap-4 px-4 py-2 border-b border-border text-[11px] font-semibold uppercase tracking-wider text-muted">
              <span className="w-7" /><span className="flex-1">Name</span>
              <span className="w-20">Status</span><span className="w-16">Size</span>
              <span className="w-28">Progress</span><span className="w-16 text-right">Deadline</span>
              <span className="w-5" />
            </div>
            <AnimatePresence>
              {filtered.map(p => (
                <div key={p.id} {...dragProps(p.id)}
                  className={`${canReorder ? 'cursor-grab active:cursor-grabbing' : ''} ${dragId === p.id ? 'opacity-40' : ''}`}
                  title={canReorder ? 'Drag to reorder' : undefined}>
                  <ProjectRow project={p} onClick={() => setSelected(p)} onDelete={() => handleDelete(p)} />
                </div>
              ))}
            </AnimatePresence>
          </div>
        )}
      </div>

      {/* Modals */}
      <AnimatePresence>
        {showCreate && (
          <CreateModal
            onClose={() => setShowCreate(false)}
            onCreate={p => { setProjects(prev => [p, ...prev]); setShowCreate(false); setSelected(p) }}
            templates={templates}
          />
        )}
        {selected && (
          <ProjectDrawer
            project={selected}
            onClose={() => setSelected(null)}
            onDelete={() => { const p = selected; setSelected(null); handleDelete(p) }}
            onUpdated={updated => {
              setProjects(prev => prev.map(p => p.id === updated.id ? updated : p))
              setSelected(updated)
            }}
          />
        )}
      </AnimatePresence>
    </div>
  )
}


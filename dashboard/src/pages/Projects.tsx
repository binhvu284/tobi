import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AnimatePresence, motion } from 'framer-motion'
import {
  Plus, RefreshCw, LayoutGrid, List, Search, X, ChevronRight,
  Target, Calendar, CheckCircle2, Trash2, TrendingUp,
} from 'lucide-react'
import {
  pmListProjects, pmCreateProject, pmDeleteProject, pmReorderProjects,
  pmListTemplates,
  type PMProject,
} from '../api'
import { useToast } from '../context/ToastProvider'
import PageLoader from '../components/PageLoader'
import { AmbientField } from '../components/motion'
import ProjectIcon from '../components/project/ProjectIcon'
import { Bar, fmtDate, STATUS_CFG } from '../components/project/shared'

// ── Constants ────────────────────────────────────────────────────────────────
const SIZE_CFG: Record<string, string> = {
  small:  'text-[10px] bg-white/5 text-muted px-1.5 py-0.5 rounded uppercase tracking-wide',
  medium: 'text-[10px] bg-accent/10 text-accent px-1.5 py-0.5 rounded uppercase tracking-wide',
  large:  'text-[10px] bg-warning/10 text-warning px-1.5 py-0.5 rounded uppercase tracking-wide',
  epic:   'text-[10px] bg-danger/10 text-danger px-1.5 py-0.5 rounded uppercase tracking-wide',
}
const EMOJIS = ['📁','🚀','💡','🎯','📊','🛠','🌱','🔬','📱','💼','🎨','🏗','⚡','🔐','🌍','🧪','📝','🤖']
const ACCENTS = ['#58a6ff','#3fb950','#f0883e','#d29922','#8b5cf6','#ec4899','#06b6d4','#10b981','#f43f5e']

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
          <ProjectIcon project={project} size={24} />
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
      <span className="flex w-7 justify-center"><ProjectIcon project={project} size={20} /></span>
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


// ── Main page ─────────────────────────────────────────────────────────────────
export default function Projects() {
  const navigate = useNavigate()
  const [projects, setProjects] = useState<PMProject[]>([])
  const [loading, setLoading] = useState(true)
  const [view, setView] = useState<'grid' | 'list'>(() =>
    (localStorage.getItem('tobi.projects.view') as 'grid' | 'list') || 'grid')
  const [search, setSearch] = useState('')
  const [filterStatus, setFilterStatus] = useState('all')
  const [showCreate, setShowCreate] = useState(false)
  const [templates, setTemplates] = useState<{ id: number; name: string }[]>([])
  const [dragId, setDragId] = useState<number | null>(null)
  const { toast } = useToast()
  const projectsRef = useRef<PMProject[]>([])
  useEffect(() => { projectsRef.current = projects }, [projects])
  // Project v2 (#12): opening a project goes to the full-page workspace.
  const openProject = (p: PMProject) => navigate(`/projects/${p.id}/overview`)

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
            className="tv2-btn flex items-center gap-2 px-3 py-2 text-sm font-medium">
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
                  <ProjectCard project={p} onClick={() => openProject(p)} onDelete={() => handleDelete(p)} />
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
                  <ProjectRow project={p} onClick={() => openProject(p)} onDelete={() => handleDelete(p)} />
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
            onCreate={p => { setProjects(prev => [p, ...prev]); setShowCreate(false); openProject(p) }}
            templates={templates}
          />
        )}
      </AnimatePresence>
    </div>
  )
}


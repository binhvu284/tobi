import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { AnimatePresence } from 'framer-motion'
import {
  LayoutGrid, CheckCircle2, Target, FolderOpen, Activity as ActivityIcon, Zap,
  ArrowLeft, Pencil, Save, X, Trash2, RefreshCw, Calendar,
} from 'lucide-react'
import {
  pmGetOverview, pmListGoals, pmListTasks, pmPatchProject, pmDeleteProject,
  type PMOverview, type PMGoal, type TaskItem,
} from '../api'
import { useToast } from '../context/ToastProvider'
import { useWorkspaceTabs, projectTabKey } from '../context/WorkspaceTabsContext'
import { pushRecentProject } from '../components/AppShell'
import PageLoader from '../components/PageLoader'
import { AmbientField } from '../components/motion'
import ProjectIcon from '../components/project/ProjectIcon'
import IconPicker from '../components/project/IconPicker'
import OverviewTab from '../components/project/OverviewTab'
import TasksTab from '../components/project/TasksTab'
import GoalsTab from '../components/project/GoalsTab'
import ResourcesTab from '../components/project/ResourcesTab'
import ActivityTab from '../components/project/ActivityTab'
import { STATUS_CFG, fmtDate } from '../components/project/shared'

type TabId = 'overview' | 'tasks' | 'goals' | 'resources' | 'activity'
const TABS: { id: TabId; label: string; icon: typeof LayoutGrid }[] = [
  { id: 'overview',  label: 'Overview',  icon: LayoutGrid },
  { id: 'tasks',     label: 'Tasks',     icon: CheckCircle2 },
  { id: 'goals',     label: 'Goals',     icon: Target },
  { id: 'resources', label: 'Resources', icon: FolderOpen },
  { id: 'activity',  label: 'Activity',  icon: ActivityIcon },
]

/** Project v2 (#12): the full-page project workspace at /projects/:id/:tab.
 * Registers itself as a Global Header tab (label = project name) and deep-links
 * every inner tab. Replaces the old right-side ProjectDrawer popup. */
export default function ProjectWorkspace() {
  const { projectId, '*': splat } = useParams()
  const pid = Number(projectId)
  const navigate = useNavigate()
  const { toast } = useToast()
  const { setTabLabel, setTabIcon } = useWorkspaceTabs()

  const tab: TabId = (TABS.some(t => t.id === splat) ? splat : 'overview') as TabId
  const setTab = (t: TabId) => navigate(`/projects/${pid}/${t}`)

  const [ov, setOv] = useState<PMOverview | null>(null)
  const [goals, setGoals] = useState<PMGoal[]>([])
  const [tasks, setTasks] = useState<TaskItem[]>([])
  const [missing, setMissing] = useState(false)
  const [editing, setEditing] = useState(false)
  const [editName, setEditName] = useState('')
  const [pickerOpen, setPickerOpen] = useState(false)
  const registered = useRef(false)

  const reload = useCallback(async () => {
    try {
      const [o, g, t] = await Promise.all([pmGetOverview(pid), pmListGoals(pid), pmListTasks(pid)])
      setOv(o); setGoals(g.items); setTasks(t.items)
      return o
    } catch (e) {
      if ((e as { status?: number }).status === 404) setMissing(true)
      return null
    }
  }, [pid])

  useEffect(() => { setOv(null); setMissing(false); reload() }, [reload])

  // Register with the global tab system + sidebar recents once the project loads (D9/D10).
  useEffect(() => {
    const p = ov?.project
    if (!p || registered.current) return
    registered.current = true
    const key = projectTabKey(`/projects/${pid}`)
    if (key) {
      setTabLabel(key, p.name)
      setTabIcon(key, {
        icon_type: p.icon_type, icon_value: p.icon_value,
        emoji_icon: p.emoji_icon, accent_color: p.accent_color,
      })
    }
    pushRecentProject({
      id: p.id, name: p.name,
      icon_type: p.icon_type, icon_value: p.icon_value,
      emoji_icon: p.emoji_icon, accent_color: p.accent_color,
    })
  }, [ov, pid, setTabLabel, setTabIcon])
  useEffect(() => { registered.current = false }, [pid])

  // Tasks drawer state lives here so Overview's active-task list can open it too.
  const [openTask, setOpenTask] = useState<TaskItem | null>(null)
  const openTaskInTab = (t: TaskItem) => { setOpenTask(t); if (tab !== 'tasks') setTab('tasks') }

  const project = ov?.project

  async function saveName() {
    if (!project || !editName.trim() || editName === project.name) { setEditing(false); return }
    try {
      await pmPatchProject(pid, { name: editName.trim() })
      setEditing(false); const o = await reload()
      const key = projectTabKey(`/projects/${pid}`)
      if (key && o) setTabLabel(key, o.project.name)
    } catch (e) { toast({ kind: 'error', title: 'Rename failed', detail: (e as Error).message }) }
  }

  async function changeStatus(status: string) {
    try { await pmPatchProject(pid, { status: status as any }); reload() }
    catch (e) { toast({ kind: 'error', title: 'Update failed', detail: (e as Error).message }) }
  }

  async function removeProject() {
    if (!project) return
    if (!window.confirm(`Delete "${project.name}"? This cannot be undone.`)) return
    try { await pmDeleteProject(pid); toast({ kind: 'success', title: 'Project deleted' }); navigate('/projects') }
    catch (e) { toast({ kind: 'error', title: 'Delete failed', detail: (e as Error).message }) }
  }

  const cfg = useMemo(() => STATUS_CFG[project?.status ?? 'idea'] ?? STATUS_CFG.idea, [project?.status])

  if (missing) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 text-muted">
        <FolderOpen size={36} className="text-muted/30" />
        <div className="text-sm">This project doesn't exist (anymore).</div>
        <button onClick={() => navigate('/projects')} className="flex items-center gap-1.5 text-sm text-accent hover:underline">
          <ArrowLeft size={14} /> All projects
        </button>
      </div>
    )
  }
  if (!project) return <PageLoader preset="projects" />

  return (
    <div className="relative flex h-full min-h-0 flex-col">
      <AmbientField />

      {/* Workspace header */}
      <header className="shrink-0 border-b border-border px-5 pt-4">
        <div className="flex items-center gap-3">
          <button onClick={() => navigate('/projects')} title="All projects"
            className="rounded-lg p-1.5 text-muted transition-colors hover:bg-overlay/5 hover:text-text">
            <ArrowLeft size={16} />
          </button>
          <div className="relative">
            <button onClick={() => setPickerOpen(o => !o)} title="Change icon (D56)"
              className="flex h-10 w-10 items-center justify-center rounded-xl border border-border bg-panel transition-colors hover:border-accent/40">
              <ProjectIcon project={project} size={24} />
            </button>
            <AnimatePresence>
              {pickerOpen && (
                <div className="absolute left-0 top-12 z-40">
                  <IconPicker projectId={pid}
                    onClose={() => setPickerOpen(false)}
                    onPick={async choice => {
                      setPickerOpen(false)
                      try { await pmPatchProject(pid, choice); reload() }
                      catch (e) { toast({ kind: 'error', title: 'Icon change failed', detail: (e as Error).message }) }
                    }} />
                </div>
              )}
            </AnimatePresence>
          </div>
          <div className="min-w-0 flex-1">
            {editing ? (
              <div className="flex items-center gap-2">
                <input autoFocus value={editName} onChange={e => setEditName(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter') saveName(); if (e.key === 'Escape') setEditing(false) }}
                  className="rounded-lg border border-accent bg-panel px-2 py-1 text-base font-bold text-heading outline-none" />
                <button onClick={saveName} className="text-success"><Save size={15} /></button>
                <button onClick={() => setEditing(false)} className="text-muted"><X size={15} /></button>
              </div>
            ) : (
              <div className="flex items-center gap-2">
                <h1 className="truncate text-lg font-bold tracking-tight text-heading">{project.name}</h1>
                <button onClick={() => { setEditName(project.name); setEditing(true) }}
                  className="text-muted transition-colors hover:text-text"><Pencil size={13} /></button>
              </div>
            )}
            <div className="mt-0.5 flex flex-wrap items-center gap-2 text-[11px] text-muted">
              <select value={project.status} onChange={e => changeStatus(e.target.value)}
                className={`cursor-pointer rounded-full border px-2 py-0.5 text-[11px] font-medium outline-none ${cfg.color}`}
                style={{ background: 'transparent' }}>
                <option value="idea">Idea</option><option value="active">Active</option>
                <option value="done">Done</option><option value="archived">Archived</option>
              </select>
              {project.category && <span>{project.category}</span>}
              {project.deadline && <span className="flex items-center gap-1"><Calendar size={11} />{fmtDate(project.deadline)}</span>}
              <span>{Math.round(project.progress_pct)}% · {project.task_done}/{project.task_count} tasks</span>
            </div>
          </div>
          <button onClick={() => reload()} title="Refresh" className="rounded-lg p-2 text-muted transition-colors hover:bg-overlay/5 hover:text-text">
            <RefreshCw size={15} />
          </button>
          <button onClick={removeProject} title="Delete project" className="rounded-lg p-2 text-muted transition-colors hover:bg-overlay/5 hover:text-danger">
            <Trash2 size={15} />
          </button>
        </div>

        {/* Inner tab strip — Missions last as a disabled 'Soon' (D57) */}
        <nav className="mt-2 flex items-center gap-0 overflow-x-auto">
          {TABS.map(({ id, label, icon: Icon }) => (
            <button key={id} onClick={() => setTab(id)}
              className={`flex items-center gap-1.5 whitespace-nowrap border-b-2 px-3 py-2 text-[12px] font-medium transition-colors ${
                tab === id ? 'border-accent text-accent' : 'border-transparent text-muted hover:text-text'}`}>
              <Icon size={13} />{label}
              {id === 'resources' && (ov?.metrics.resources_count ?? 0) > 0 && (
                <span className="rounded bg-overlay/8 px-1 text-[10px] text-muted">{ov!.metrics.resources_count}</span>
              )}
            </button>
          ))}
          <span title="Missions are being reimagined — coming soon"
            className="flex cursor-not-allowed items-center gap-1.5 whitespace-nowrap border-b-2 border-transparent px-3 py-2 text-[12px] font-medium text-muted/50">
            <Zap size={13} /> Missions
            <span className="rounded bg-muted/15 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide">Soon</span>
          </span>
        </nav>
      </header>

      {/* Tab content */}
      <div className="min-h-0 flex-1 overflow-hidden">
        {tab === 'overview' && (
          <div className="h-full overflow-y-auto">
            {ov && <OverviewTab ov={ov} onChanged={reload} onOpenTask={openTaskInTab} />}
          </div>
        )}
        {tab === 'tasks' && (
          <TasksTab projectId={pid} onTaskChange={reload}
            openTask={openTask} onOpenTask={setOpenTask} onCloseTask={() => setOpenTask(null)} />
        )}
        {tab === 'goals' && (
          <div className="h-full overflow-y-auto">
            <GoalsTab projectId={pid} goals={goals} tasks={tasks} onRefresh={reload} />
          </div>
        )}
        {tab === 'resources' && <ResourcesTab projectId={pid} onChanged={reload} />}
        {tab === 'activity' && (
          <div className="h-full overflow-y-auto">
            <ActivityTab projectId={pid} />
          </div>
        )}
      </div>
    </div>
  )
}

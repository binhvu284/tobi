import { useCallback, useEffect, useMemo, useState } from 'react'
import { RefreshCw, Plus } from 'lucide-react'
import {
  addTaskNote,
  createTask,
  deleteTask,
  evaluateOwnerInput,
  getProjects,
  getHighRiskTaskAudit,
  getTask,
  getTaskMetrics,
  getTasks,
  patchTask,
  sendTaskCommand,
  submitOwnerInput,
  type OwnerInputChecklistItem,
  type Project,
  type TaskAgent,
  type TaskCreatePayload,
  type TaskItem,
  type TaskMetrics,
  type TaskPriority,
  type TaskStatus,
  type HighRiskAuditItem,
} from '../api'
import KanbanColumn from '../components/KanbanColumn'
import TaskFilters from '../components/TaskFilters'
import TaskDetailPanel from '../components/TaskDetailPanel'
import TaskCreateModal from '../components/TaskCreateModal'
import ConfirmTransitionModal from '../components/ConfirmTransitionModal'
import PageLoader from '../components/PageLoader'

const statusOrder: TaskStatus[] = [
  'planned',
  'in_progress',
  'paused',
  'blocked',
  'needs_owner_input',
  'done',
  'cancelled',
]

const statusLabel: Record<TaskStatus, string> = {
  planned: 'Planned',
  in_progress: 'In Progress',
  paused: 'Paused',
  blocked: 'Blocked',
  needs_owner_input: 'Needs Owner Input',
  done: 'Done',
  cancelled: 'Cancelled',
}

type ConfirmState = {
  open: boolean
  taskId: number | null
  patch: { status?: TaskStatus; priority?: TaskPriority; agent?: TaskAgent }
  title: string
  detail: string
}

const defaultConfirm: ConfirmState = {
  open: false,
  taskId: null,
  patch: {},
  title: '',
  detail: '',
}

export default function Task() {
  const [tasks, setTasks] = useState<TaskItem[]>([])
  const [metrics, setMetrics] = useState<TaskMetrics | null>(null)
  const [projects, setProjects] = useState<Project[]>([])
  const [selected, setSelected] = useState<TaskItem | null>(null)
  const [updated, setUpdated] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [audit, setAudit] = useState<HighRiskAuditItem[]>([])

  const [q, setQ] = useState('')
  const [statusFilter, setStatusFilter] = useState<TaskStatus | 'all'>('all')
  const [priorityFilter, setPriorityFilter] = useState<TaskPriority | 'all'>('all')
  const [agentFilter, setAgentFilter] = useState<TaskAgent | 'all'>('all')
  const [ownerFilter, setOwnerFilter] = useState<string | 'all'>('all')
  const [projectFilter, setProjectFilter] = useState<string | 'all'>('all')
  const [overdueOnly, setOverdueOnly] = useState(false)

  const [createOpen, setCreateOpen] = useState(false)
  const [confirm, setConfirm] = useState<ConfirmState>(defaultConfirm)
  const [dragTaskId, setDragTaskId] = useState<number | null>(null)
  const [dropStatus, setDropStatus] = useState<TaskStatus | null>(null)

  const load = useCallback(async () => {
    setError('')
    const filters = {
      q: q.trim() || undefined,
      status: statusFilter === 'all' ? undefined : [statusFilter],
      priority: priorityFilter === 'all' ? undefined : [priorityFilter],
      agent: agentFilter === 'all' ? undefined : [agentFilter],
      owner: ownerFilter === 'all' ? undefined : [ownerFilter],
      project_id: projectFilter === 'all' ? undefined : Number(projectFilter),
      overdue: overdueOnly ? true : undefined,
    }
    const [taskRes, metricRes, projectRes, auditRes] = await Promise.all([
      getTasks(filters),
      getTaskMetrics(),
      getProjects(),
      getHighRiskTaskAudit(15),
    ])
    setTasks(taskRes.items)
    setMetrics(metricRes)
    setProjects(projectRes)
    setAudit(auditRes.items)
    setUpdated(new Date().toLocaleTimeString('en-GB'))

    if (selected) {
      const fresh = taskRes.items.find((t) => t.id === selected.id)
      if (fresh) {
        const detail = await getTask(fresh.id)
        setSelected(detail)
      }
    }
  }, [q, statusFilter, priorityFilter, agentFilter, ownerFilter, projectFilter, overdueOnly, selected?.id])

  useEffect(() => {
    setLoading(true)
    load().catch(() => setError('Failed to load tasks.')).finally(() => setLoading(false))
    const id = setInterval(() => load().catch(() => setError('Background refresh failed.')), 30_000)
    return () => clearInterval(id)
  }, [load])

  const grouped = useMemo(() => {
    const g: Record<TaskStatus, TaskItem[]> = {
      planned: [],
      in_progress: [],
      paused: [],
      blocked: [],
      needs_owner_input: [],
      done: [],
      cancelled: [],
    }
    for (const t of tasks) g[t.status].push(t)
    return g
  }, [tasks])

  const doPatch = useCallback(async (taskId: number, patch: { status?: TaskStatus; priority?: TaskPriority; agent?: TaskAgent; due_at?: string | null; confirmed?: boolean }) => {
    try {
      const updatedTask = await patchTask(taskId, patch)
      setTasks((prev) => prev.map((t) => (t.id === taskId ? { ...t, ...updatedTask } : t)))
      if (selected?.id === taskId) setSelected(updatedTask)
      await load()
    } catch (err: any) {
      if (err?.status === 409 && err?.detail?.code === 'confirmation_required') {
        setConfirm({
          open: true,
          taskId,
          patch,
          title: 'Confirmation required',
          detail: err?.detail?.message || 'This transition requires confirmation.',
        })
        return
      }
      throw err
    }
  }, [load, selected?.id])

  const requestConfirm = useCallback((taskId: number, patch: { status?: TaskStatus; priority?: TaskPriority; agent?: TaskAgent }, title: string, detail: string) => {
    setConfirm({ open: true, taskId, patch, title, detail })
  }, [])

  const isHighRiskPatch = useCallback((task: TaskItem | undefined, patch: { status?: TaskStatus; priority?: TaskPriority; agent?: TaskAgent }) => {
    if (!task) return false
    if (patch.status && (patch.status === 'done' || patch.status === 'cancelled')) return true
    if (patch.priority && patch.priority === 'P0' && task.priority !== 'P0') return true
    if (patch.agent && patch.agent !== task.agent) return true
    return false
  }, [])

  const openTask = async (task: TaskItem) => {
    const detail = await getTask(task.id)
    setSelected(detail)
  }

  const handleCreate = async (payload: TaskCreatePayload) => {
    await createTask(payload)
    await load()
  }

  return (
    <div className="space-y-4 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-heading">Task</h1>
          <p className="mt-1 text-xs text-muted">Mission workflow board to manage and interact with TOBI.</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setCreateOpen(true)}
            className="flex items-center gap-1.5 rounded border border-accent/40 bg-accent/10 px-3 py-1.5 text-xs font-medium text-accent hover:bg-accent/20"
          >
            <Plus size={13} /> Create task
          </button>
          <button
            onClick={() => {
              setLoading(true)
              load().catch(() => setError('Failed to refresh tasks.')).finally(() => setLoading(false))
            }}
            className="flex items-center gap-1.5 rounded border border-border px-3 py-1.5 text-xs text-muted hover:text-text"
          >
            <RefreshCw size={13} /> {updated ? `Updated ${updated}` : 'Refresh'}
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded border border-danger/40 bg-danger/10 px-3 py-2 text-xs text-danger">
          {error}
        </div>
      )}

      {metrics && (
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-6">
          <Metric label="Open" value={metrics.open_tasks} />
          <Metric label="Overdue" value={metrics.overdue} danger={metrics.overdue > 0} />
          <Metric label="Need input" value={metrics.needs_owner_input} warn={metrics.needs_owner_input > 0} />
          <Metric label="Blocked" value={metrics.blocked} warn={metrics.blocked > 0} />
          <Metric label="P0/P1" value={metrics.p0_p1} />
          <Metric label="Cycle hrs" value={metrics.cycle_time_hours ?? '-'} />
        </div>
      )}

      <TaskFilters
        q={q}
        onQ={setQ}
        status={statusFilter}
        onStatus={setStatusFilter}
        priority={priorityFilter}
        onPriority={setPriorityFilter}
        agent={agentFilter}
        onAgent={setAgentFilter}
        owner={ownerFilter}
        onOwner={setOwnerFilter}
        projectId={projectFilter}
        onProjectId={setProjectFilter}
        projectOptions={projects.map((p) => ({ id: p.id, name: p.name }))}
        overdueOnly={overdueOnly}
        onOverdueOnly={setOverdueOnly}
      />

      {loading ? (
        <PageLoader preset="task" compact />
      ) : (
        <div className="flex gap-4 overflow-x-auto pb-2">
          <div className="flex min-w-0 flex-1 gap-3">
            {statusOrder.map((status) => (
              <KanbanColumn
                key={status}
                title={statusLabel[status]}
                status={status}
                tasks={grouped[status] || []}
                onOpen={openTask}
                onMove={(taskId, to) => {
                  const task = tasks.find((t) => t.id === taskId)
                  if (isHighRiskPatch(task, { status: to })) {
                    requestConfirm(taskId, { status: to }, 'High-risk transition', `Changing status to ${to} requires confirmation.`)
                    return
                  }
                  void doPatch(taskId, { status: to })
                }}
                onDragStart={(taskId) => setDragTaskId(taskId)}
                onDragEnd={() => {
                  setDragTaskId(null)
                  setDropStatus(null)
                }}
                onDropToStatus={(targetStatus) => {
                  setDropStatus(targetStatus)
                  if (dragTaskId == null) return
                  const task = tasks.find((t) => t.id === dragTaskId)
                  if (!task || task.status === targetStatus) return
                  const patch = { status: targetStatus as TaskStatus }
                  if (isHighRiskPatch(task, patch)) {
                    requestConfirm(dragTaskId, patch, 'High-risk drag transition', `Dropping into ${targetStatus} requires confirmation.`)
                  } else {
                    void doPatch(dragTaskId, patch)
                  }
                  setDragTaskId(null)
                  setDropStatus(null)
                }}
                onDragOverStatus={setDropStatus}
                isDropTarget={dropStatus === status}
              />
            ))}
          </div>

          {selected && (
            <TaskDetailPanel
              task={selected}
              onClose={() => setSelected(null)}
              onPatch={doPatch}
              onRequestConfirm={requestConfirm}
              onDelete={async (taskId) => {
                await deleteTask(taskId)
                if (selected?.id === taskId) setSelected(null)
                await load()
              }}
              onAddNote={async (taskId, note) => {
                await addTaskNote(taskId, note)
                if (selected?.id === taskId) setSelected(await getTask(taskId))
                await load()
              }}
              onSubmitChecklist={async (taskId, items) => {
                await submitOwnerInput(taskId, items as OwnerInputChecklistItem[])
                if (selected?.id === taskId) setSelected(await getTask(taskId))
                await load()
              }}
              onEvaluateChecklist={async (taskId) => {
                await evaluateOwnerInput(taskId)
                if (selected?.id === taskId) setSelected(await getTask(taskId))
                await load()
              }}
              onSendCommand={async (taskId, command) => {
                await sendTaskCommand(taskId, command)
                if (selected?.id === taskId) setSelected(await getTask(taskId))
                await load()
              }}
            />
          )}
        </div>
      )}

      <section className="rounded-lg border border-border bg-surface p-4">
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-heading">High-Risk Audit</h2>
          <span className="text-xs text-muted">Latest {audit.length}</span>
        </div>
        {audit.length === 0 ? (
          <p className="text-xs text-muted">No high-risk transitions recorded yet.</p>
        ) : (
          <div className="max-h-48 space-y-1 overflow-y-auto">
            {audit.map((entry) => (
              <div key={entry.id} className="rounded border border-border bg-bg px-2 py-1.5 text-xs">
                <p className="text-text">{entry.task_title} · {entry.message}</p>
                <p className="text-[10px] text-muted">{entry.author} · {new Date(entry.created_at).toLocaleString('en-GB')}</p>
              </div>
            ))}
          </div>
        )}
      </section>

      <TaskCreateModal open={createOpen} projects={projects} onClose={() => setCreateOpen(false)} onCreate={handleCreate} />

      <ConfirmTransitionModal
        open={confirm.open}
        title={confirm.title}
        detail={confirm.detail}
        onCancel={() => setConfirm(defaultConfirm)}
        onConfirm={async () => {
          if (!confirm.taskId) return
          await doPatch(confirm.taskId, { ...confirm.patch, confirmed: true })
          setConfirm(defaultConfirm)
        }}
      />
    </div>
  )
}

function Metric({ label, value, warn = false, danger = false }: { label: string; value: string | number; warn?: boolean; danger?: boolean }) {
  const color = danger ? 'text-danger' : warn ? 'text-warning' : 'text-text'
  return (
    <div className="rounded-lg border border-border bg-surface p-3">
      <p className="text-[11px] uppercase tracking-wider text-muted">{label}</p>
      <p className={`mt-1 text-lg font-semibold ${color}`}>{value}</p>
    </div>
  )
}

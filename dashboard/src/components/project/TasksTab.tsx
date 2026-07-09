import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Plus, X, CheckCircle2, Circle, Calendar, Bot, User, Trash2, GripVertical,
  ArrowUpDown, Bell, Timer, Link2, ChevronRight, Maximize2, Minimize2, Ban,
} from 'lucide-react'
import {
  pmListTasks, pmCreateTask, patchTask, deleteTask, pmPatchSubtasks,
  pmAddTaskDep, pmRemoveTaskDep,
  type TaskItem, type TaskStatus, type PMSubTask,
} from '../../api'
import { useToast } from '../../context/ToastProvider'
import PageLoader from '../PageLoader'
import { fmtDate, TASK_STATUS_COLORS, PRIORITY_COLORS } from './shared'

type SortMode = 'manual' | 'due' | 'priority'
const STATUS_ORDER: TaskStatus[] = ['in_progress', 'planned', 'paused', 'blocked', 'needs_owner_input', 'done', 'cancelled']
const STATUS_LABEL: Record<string, string> = {
  in_progress: 'In progress', planned: 'Planned', paused: 'Paused', blocked: 'Blocked',
  needs_owner_input: 'Needs input', done: 'Done', cancelled: 'Cancelled',
}

/** Tasks (#12 D17–D32): one professional List view — status groups, manual drag order
 * + sort toggle, quick add, right-drawer detail expandable to full page. */
export default function TasksTab({ projectId, onTaskChange, openTask, onOpenTask, onCloseTask }: {
  projectId: number
  onTaskChange: () => void
  openTask: TaskItem | null            // drawer state lives in the workspace (Overview can open it too)
  onOpenTask: (t: TaskItem) => void
  onCloseTask: () => void
}) {
  const { toast } = useToast()
  const [tasks, setTasks] = useState<TaskItem[]>([])
  const [loading, setLoading] = useState(true)
  const [quickAdd, setQuickAdd] = useState('')
  const [sort, setSort] = useState<SortMode>('manual')
  const [filterAssignee, setFilterAssignee] = useState<'all' | 'me' | 'tobi'>('all')
  const [dragId, setDragId] = useState<number | null>(null)
  const tasksRef = useRef<TaskItem[]>([])
  useEffect(() => { tasksRef.current = tasks }, [tasks])

  const load = useCallback(async () => {
    try {
      const r = await pmListTasks(projectId)
      setTasks(r.items)
      return r.items
    } catch { return [] } finally { setLoading(false) }
  }, [projectId])

  useEffect(() => { load() }, [load])

  // keep the open drawer's task fresh after list reloads
  useEffect(() => {
    if (!openTask) return
    const fresh = tasks.find(t => t.id === openTask.id)
    if (fresh && fresh !== openTask) onOpenTask(fresh)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tasks])

  async function addTask() {
    const title = quickAdd.trim()
    if (!title) return
    setQuickAdd('')
    try {
      await pmCreateTask(projectId, { title })
      await load(); onTaskChange()
    } catch (e) { toast({ kind: 'error', title: 'Add failed', detail: (e as Error).message }) }
  }

  async function toggleDone(t: TaskItem) {
    const next: TaskStatus = t.status === 'done' ? 'planned' : 'done'
    try { await patchTask(t.id, { status: next, confirmed: true }); await load(); onTaskChange() }
    catch (e) { toast({ kind: 'error', title: 'Update failed', detail: (e as Error).message }) }
  }

  async function removeTask(t: TaskItem) {
    if (!window.confirm(`Delete task "${t.title}"?`)) return
    try {
      await deleteTask(t.id)
      if (openTask?.id === t.id) onCloseTask()
      await load(); onTaskChange()
    } catch (e) { toast({ kind: 'error', title: 'Delete failed', detail: (e as Error).message }) }
  }

  // ── manual drag-to-reorder within a status group (persists via before_task_id) ──
  async function onDropOn(target: TaskItem) {
    const id = dragId; setDragId(null)
    if (id == null || id === target.id) return
    const src = tasksRef.current.find(t => t.id === id)
    if (!src || src.status !== target.status) return   // reorder within the same group only
    try {
      await patchTask(id, { before_task_id: target.id, confirmed: true })
      await load()
    } catch (e) { toast({ kind: 'error', title: 'Reorder failed', detail: (e as Error).message }) }
  }

  const filtered = tasks.filter(t => {
    if (filterAssignee === 'me' && t.owner !== 'owner') return false
    if (filterAssignee === 'tobi' && t.agent !== 'tobi') return false
    return true
  })

  const groups = useMemo(() => {
    const sorted = [...filtered]
    if (sort === 'due') sorted.sort((a, b) => (a.due_at || '9999').localeCompare(b.due_at || '9999'))
    if (sort === 'priority') sorted.sort((a, b) => (a.priority || 'P2').localeCompare(b.priority || 'P2'))
    const by: Partial<Record<string, TaskItem[]>> = {}
    for (const t of sorted) (by[t.status] ??= []).push(t)
    return STATUS_ORDER.filter(s => by[s]?.length).map(s => ({ status: s, items: by[s]! }))
  }, [filtered, sort])

  return (
    <div className="flex h-full min-h-0">
      {/* List column */}
      <div className="flex min-w-0 flex-1 flex-col">
        {/* Quick add + toolbar */}
        <div className="flex items-center gap-2 border-b border-border px-4 py-3">
          <div className="flex min-w-0 flex-1 items-center gap-2 rounded-lg border border-border bg-panel px-3 py-2 focus-within:border-accent">
            <Plus size={14} className="shrink-0 text-muted" />
            <input value={quickAdd} onChange={e => setQuickAdd(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && addTask()}
              className="min-w-0 flex-1 bg-transparent text-sm text-text outline-none"
              placeholder="Add a task… (Enter)" />
          </div>
          <button onClick={() => setSort(s => s === 'manual' ? 'due' : s === 'due' ? 'priority' : 'manual')}
            title="Sort: manual → due → priority"
            className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-2 text-[11px] transition-colors ${sort !== 'manual' ? 'border-accent/40 text-accent' : 'border-border text-muted hover:text-text'}`}>
            <ArrowUpDown size={13} /> {sort === 'manual' ? 'Manual' : sort === 'due' ? 'Due date' : 'Priority'}
          </button>
          <div className="flex rounded-lg border border-border p-0.5 text-[11px]">
            {([['all', 'All'], ['me', 'Me'], ['tobi', 'TOBI']] as const).map(([v, l]) => (
              <button key={v} onClick={() => setFilterAssignee(v)}
                className={`rounded px-2 py-1 ${filterAssignee === v ? 'bg-accent/15 text-accent' : 'text-muted hover:text-text'}`}>{l}</button>
            ))}
          </div>
        </div>

        {/* Grouped list */}
        <div className="min-h-0 flex-1 overflow-y-auto">
          {loading ? <PageLoader preset="projects" compact />
            : groups.length === 0 ? (
              <div className="flex h-40 flex-col items-center justify-center gap-2 text-muted">
                <CheckCircle2 size={26} className="text-muted/30" />
                <span className="text-sm">No tasks yet — add one above, or ask TOBI in chat.</span>
              </div>
            ) : groups.map(g => (
              <section key={g.status}>
                <header className="sticky top-0 z-10 flex items-center gap-2 border-b border-border/60 bg-surface/95 px-4 py-1.5 backdrop-blur">
                  <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${TASK_STATUS_COLORS[g.status]}`}>
                    {STATUS_LABEL[g.status] ?? g.status}
                  </span>
                  <span className="text-[11px] text-muted">{g.items.length}</span>
                </header>
                {g.items.map(t => (
                  <TaskRow key={t.id} t={t} selected={openTask?.id === t.id}
                    draggable={sort === 'manual'}
                    dragging={dragId === t.id}
                    onDragStart={() => setDragId(t.id)}
                    onDragEnd={() => setDragId(null)}
                    onDropOn={() => onDropOn(t)}
                    onClick={() => onOpenTask(t)}
                    onToggleDone={() => toggleDone(t)}
                    onDelete={() => removeTask(t)} />
                ))}
              </section>
            ))}
        </div>
      </div>

      {/* Right drawer (expandable to full page width) */}
      <AnimatePresence>
        {openTask && (
          <TaskDrawer key={openTask.id} projectId={projectId} task={openTask} allTasks={tasks}
            onClose={onCloseTask}
            onChanged={async () => { await load(); onTaskChange() }} />
        )}
      </AnimatePresence>
    </div>
  )
}

function TaskRow({ t, selected, draggable, dragging, onDragStart, onDragEnd, onDropOn, onClick, onToggleDone, onDelete }: {
  t: TaskItem; selected: boolean; draggable: boolean; dragging: boolean
  onDragStart: () => void; onDragEnd: () => void; onDropOn: () => void
  onClick: () => void; onToggleDone: () => void; onDelete: () => void
}) {
  const subs = (t.sub_tasks ?? []) as PMSubTask[]
  const subDone = subs.filter(s => s.completed).length
  const blockedBy = t.blocked_by ?? []
  return (
    <div draggable={draggable}
      onDragStart={onDragStart} onDragEnd={onDragEnd}
      onDragOver={e => e.preventDefault()} onDrop={e => { e.preventDefault(); onDropOn() }}
      onClick={onClick}
      className={`group flex cursor-pointer items-center gap-2 border-b border-border/40 px-4 py-2.5 transition-colors ${
        selected ? 'bg-accent/8' : 'hover:bg-overlay/3'} ${dragging ? 'opacity-40' : ''}`}>
      {draggable && <GripVertical size={13} className="shrink-0 cursor-grab text-muted/40 opacity-0 group-hover:opacity-100" />}
      <button onClick={e => { e.stopPropagation(); onToggleDone() }} className="shrink-0">
        {t.status === 'done'
          ? <CheckCircle2 size={16} className="text-success" />
          : <Circle size={16} className="text-muted hover:text-accent" />}
      </button>
      <span className={`min-w-0 flex-1 truncate text-sm ${t.status === 'done' ? 'text-muted line-through' : 'text-text'}`}>
        {t.title}
      </span>
      {blockedBy.length > 0 && t.status !== 'done' && (
        <span className="flex shrink-0 items-center gap-1 rounded bg-danger/10 px-1.5 py-0.5 text-[10px] text-danger" title={`Blocked by ${blockedBy.length} task(s)`}>
          <Ban size={9} /> blocked
        </span>
      )}
      {subs.length > 0 && (
        <span className="shrink-0 text-[11px] text-muted">{subDone}/{subs.length}</span>
      )}
      {t.time_estimate && (
        <span className="flex shrink-0 items-center gap-0.5 text-[11px] text-muted"><Timer size={10} />{t.time_estimate}</span>
      )}
      <span className={`shrink-0 text-[11px] font-medium ${PRIORITY_COLORS[t.priority] ?? 'text-muted'}`}>{t.priority}</span>
      <span className={`shrink-0 ${t.agent === 'tobi' ? 'text-accent' : 'text-muted'}`} title={t.agent === 'tobi' ? 'TOBI' : 'You'}>
        {t.agent === 'tobi' ? <Bot size={12} /> : <User size={12} />}
      </span>
      {t.due_at && (
        <span className={`flex w-14 shrink-0 items-center justify-end gap-1 text-[11px] ${t.is_overdue ? 'text-danger' : 'text-muted'}`}>
          <Calendar size={10} />{fmtDate(t.due_at)}
        </span>
      )}
      <button onClick={e => { e.stopPropagation(); onDelete() }}
        className="shrink-0 text-muted opacity-0 transition-opacity hover:text-danger group-hover:opacity-100">
        <Trash2 size={13} />
      </button>
      <ChevronRight size={13} className="shrink-0 text-muted/50" />
    </div>
  )
}

// ── Task detail drawer (right side, expandable to full width — D21/D22/D23/D24/D27) ──
function TaskDrawer({ projectId, task, allTasks, onClose, onChanged }: {
  projectId: number; task: TaskItem; allTasks: TaskItem[]
  onClose: () => void; onChanged: () => Promise<void> | void
}) {
  const { toast } = useToast()
  const [wide, setWide] = useState(false)
  const [title, setTitle] = useState(task.title)
  const [desc, setDesc] = useState(task.description || '')
  const [subs, setSubs] = useState<PMSubTask[]>((task.sub_tasks ?? []) as PMSubTask[])
  const [newSub, setNewSub] = useState('')
  const [depPick, setDepPick] = useState('')

  useEffect(() => {
    setTitle(task.title); setDesc(task.description || '')
    setSubs((task.sub_tasks ?? []) as PMSubTask[])
  }, [task.id]) // eslint-disable-line react-hooks/exhaustive-deps

  async function patch(p: Parameters<typeof patchTask>[1], confirm = false) {
    try { await patchTask(task.id, { ...p, ...(confirm ? { confirmed: true } : {}) }); await onChanged() }
    catch (e) { toast({ kind: 'error', title: 'Update failed', detail: (e as Error).message }) }
  }

  async function persistSubs(next: PMSubTask[]) {
    setSubs(next)
    try { await pmPatchSubtasks(projectId, task.id, next as any); await onChanged() }
    catch { toast({ kind: 'error', title: 'Sub-task save failed' }) }
  }

  const others = allTasks.filter(t => t.id !== task.id)
  const blocks = (task.blocks ?? []).map(id => allTasks.find(t => t.id === id)).filter(Boolean) as TaskItem[]
  const blockedBy = (task.blocked_by ?? []).map(id => allTasks.find(t => t.id === id)).filter(Boolean) as TaskItem[]

  const input = 'w-full rounded-lg border border-border bg-surface px-2.5 py-1.5 text-sm text-text outline-none focus:border-accent'
  const label = 'mb-1 block text-[10px] font-semibold uppercase tracking-wide text-muted'

  return (
    <motion.aside
      initial={{ x: 40, opacity: 0 }} animate={{ x: 0, opacity: 1 }} exit={{ x: 40, opacity: 0 }}
      transition={{ type: 'spring', stiffness: 380, damping: 32 }}
      className={`flex h-full shrink-0 flex-col border-l border-border bg-panel transition-[width] duration-200 ${wide ? 'w-full lg:w-[56rem]' : 'w-full sm:w-96'}`}>
      {/* Header */}
      <div className="flex items-center gap-2 border-b border-border px-4 py-3">
        <button onClick={() => patch({ status: task.status === 'done' ? 'planned' : 'done' }, true)} className="shrink-0">
          {task.status === 'done' ? <CheckCircle2 size={17} className="text-success" /> : <Circle size={17} className="text-muted hover:text-accent" />}
        </button>
        <input value={title} onChange={e => setTitle(e.target.value)}
          onBlur={() => title.trim() && title !== task.title && patch({ title: title.trim() })}
          onKeyDown={e => e.key === 'Enter' && (e.target as HTMLInputElement).blur()}
          className="min-w-0 flex-1 bg-transparent text-sm font-semibold text-heading outline-none" />
        <button onClick={() => setWide(w => !w)} title={wide ? 'Shrink' : 'Expand to full page'}
          className="shrink-0 rounded p-1 text-muted hover:text-text">
          {wide ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
        </button>
        <button onClick={onClose} className="shrink-0 rounded p-1 text-muted hover:text-text"><X size={16} /></button>
      </div>

      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4">
        {/* Status / priority / assignee */}
        <div className="grid grid-cols-3 gap-2">
          <div>
            <span className={label}>Status</span>
            <select value={task.status} onChange={e => patch({ status: e.target.value as TaskStatus }, true)} className={input}>
              {STATUS_ORDER.map(s => <option key={s} value={s}>{STATUS_LABEL[s] ?? s}</option>)}
            </select>
          </div>
          <div>
            <span className={label}>Priority</span>
            <select value={task.priority} onChange={e => patch({ priority: e.target.value as any }, true)} className={input}>
              <option value="P0">P0 — Critical</option><option value="P1">P1 — High</option>
              <option value="P2">P2 — Normal</option><option value="P3">P3 — Low</option>
            </select>
          </div>
          <div>
            <span className={label}>Assignee</span>
            <select value={task.agent} onChange={e => patch({ agent: e.target.value as any }, true)} className={input}>
              <option value="tobi">TOBI</option><option value="research">Research</option>
              <option value="coder">Coder</option><option value="ceo">CEO</option>
            </select>
          </div>
        </div>

        {/* Dates (start / due / reminder — D22) + estimate */}
        <div className="grid grid-cols-2 gap-2">
          <div>
            <span className={label}>Start</span>
            <input type="date" value={(task.start_at || '').slice(0, 10)}
              onChange={e => patch({ start_at: e.target.value || null })} className={input} />
          </div>
          <div>
            <span className={label}>Due</span>
            <input type="date" value={(task.due_at || '').slice(0, 10)}
              onChange={e => patch({ due_at: e.target.value || null })} className={input} />
          </div>
          <div>
            <span className={label}><Bell size={9} className="mr-1 inline" />Reminder</span>
            <input type="datetime-local" value={(task.reminder_at || '').slice(0, 16)}
              onChange={e => patch({ reminder_at: e.target.value || null })} className={input} />
          </div>
          <div>
            <span className={label}><Timer size={9} className="mr-1 inline" />Estimate</span>
            <input placeholder="e.g. 2h / 1d" defaultValue={task.time_estimate || ''}
              onBlur={e => e.target.value !== (task.time_estimate || '') && patch({ time_estimate: e.target.value || null })}
              className={input} />
          </div>
        </div>

        {/* Description (plain text — D23) */}
        <div>
          <span className={label}>Description</span>
          <textarea value={desc} onChange={e => setDesc(e.target.value)} rows={wide ? 8 : 4}
            onBlur={() => desc !== (task.description || '') && patch({ description: desc })}
            placeholder="Details, context, steps…"
            className={`${input} resize-none leading-relaxed`} />
        </div>

        {/* Sub-tasks — one level, rich (checkbox + assignee + due — D24) */}
        <div>
          <span className={label}>Sub-tasks {subs.length > 0 && `· ${subs.filter(s => s.completed).length}/${subs.length}`}</span>
          <div className="space-y-1.5">
            {subs.map(s => (
              <div key={s.id} className="group/sub flex items-center gap-2 rounded-lg border border-border/60 bg-surface px-2 py-1.5">
                <button onClick={() => persistSubs(subs.map(x => x.id === s.id ? { ...x, completed: !x.completed } : x))}>
                  {s.completed ? <CheckCircle2 size={14} className="text-success" /> : <Circle size={14} className="text-muted" />}
                </button>
                <span className={`min-w-0 flex-1 truncate text-[13px] ${s.completed ? 'text-muted line-through' : 'text-text'}`}>{s.title}</span>
                <select value={s.assignee || 'owner'} onChange={e => persistSubs(subs.map(x => x.id === s.id ? { ...x, assignee: e.target.value } : x))}
                  className="shrink-0 rounded border-0 bg-transparent text-[10px] text-muted outline-none">
                  <option value="owner">Me</option><option value="tobi">TOBI</option>
                </select>
                <input type="date" value={(s.due_at || '').slice(0, 10)}
                  onChange={e => persistSubs(subs.map(x => x.id === s.id ? { ...x, due_at: e.target.value || null } : x))}
                  className="w-[7.2rem] shrink-0 rounded border border-border/50 bg-transparent px-1 py-0.5 text-[10px] text-muted outline-none" />
                <button onClick={() => persistSubs(subs.filter(x => x.id !== s.id))}
                  className="shrink-0 text-muted opacity-0 transition-opacity hover:text-danger group-hover/sub:opacity-100"><X size={12} /></button>
              </div>
            ))}
            <div className="flex items-center gap-2">
              <input value={newSub} onChange={e => setNewSub(e.target.value)}
                onKeyDown={e => {
                  if (e.key === 'Enter' && newSub.trim()) {
                    persistSubs([...subs, { id: crypto.randomUUID(), title: newSub.trim(), completed: false, assignee: 'owner' }])
                    setNewSub('')
                  }
                }}
                placeholder="+ Sub-task (Enter to add)"
                className="flex-1 border-b border-border bg-transparent py-1 text-[12px] text-text outline-none focus:border-accent" />
            </div>
          </div>
        </div>

        {/* Dependencies (blocks / blocked-by — D27) */}
        <div>
          <span className={label}><Link2 size={9} className="mr-1 inline" />Dependencies</span>
          <div className="space-y-1.5">
            {blockedBy.map(b => (
              <DepRow key={`by-${b.id}`} kind="Blocked by" t={b} onRemove={async () => { await pmRemoveTaskDep(b.id, task.id); await onChanged() }} />
            ))}
            {blocks.map(b => (
              <DepRow key={`bl-${b.id}`} kind="Blocks" t={b} onRemove={async () => { await pmRemoveTaskDep(task.id, b.id); await onChanged() }} />
            ))}
            <div className="flex gap-1.5">
              <select value={depPick} onChange={e => setDepPick(e.target.value)} className={`${input} flex-1`}>
                <option value="">+ This task blocks…</option>
                {others.map(t => <option key={t.id} value={t.id}>{t.title}</option>)}
              </select>
              <button disabled={!depPick}
                onClick={async () => {
                  try { await pmAddTaskDep(task.id, Number(depPick)); setDepPick(''); await onChanged() }
                  catch (e) { toast({ kind: 'error', title: 'Failed', detail: (e as Error).message }) }
                }}
                className="rounded-lg border border-border px-2.5 text-[11px] text-muted transition-colors hover:border-accent/40 hover:text-accent disabled:opacity-40">
                Add
              </button>
            </div>
          </div>
        </div>

        {/* Meta */}
        <div className="border-t border-border/60 pt-2 text-[10px] text-muted">
          Created {fmtDate(task.created_at)} · Updated {fmtDate(task.updated_at)}
          {task.completed_at && <> · Completed {fmtDate(task.completed_at)}</>}
        </div>
      </div>
    </motion.aside>
  )
}

function DepRow({ kind, t, onRemove }: { kind: string; t: TaskItem; onRemove: () => void }) {
  return (
    <div className="group/dep flex items-center gap-2 rounded-lg border border-border/60 bg-surface px-2 py-1.5">
      <span className={`shrink-0 rounded px-1.5 py-0.5 text-[9px] font-semibold uppercase ${kind === 'Blocks' ? 'bg-warning/15 text-warning' : 'bg-danger/15 text-danger'}`}>
        {kind}
      </span>
      <span className={`min-w-0 flex-1 truncate text-[12px] ${t.status === 'done' ? 'text-muted line-through' : 'text-text'}`}>{t.title}</span>
      <button onClick={onRemove} className="shrink-0 text-muted opacity-0 transition-opacity hover:text-danger group-hover/dep:opacity-100">
        <X size={12} />
      </button>
    </div>
  )
}

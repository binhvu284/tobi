import { useMemo, useState } from 'react'
import {
  Plus, X, Save, Trash2, Calendar, Target, ChevronDown, ChevronUp, Search,
  CheckCircle2, AlertTriangle, Gauge, ListChecks,
} from 'lucide-react'
import { ActionButton } from '../async-ui'
import { pmCreateGoal, pmPatchGoal, pmDeleteGoal, pmLinkGoalTask, pmUnlinkGoalTask, type PMGoal } from '../../api.pm'
import type { TaskItem } from '../../api.tasks'
import { useToast } from '../../context/ToastProvider'
import { Bar, fmtDate } from './shared'

const PRIORITY_BADGE: Record<string, string> = {
  low: 'bg-muted/15 text-muted', medium: 'bg-accent/15 text-accent', high: 'bg-danger/15 text-danger',
}
const PRIORITY_WEIGHT: Record<string, number> = { low: 1, medium: 2, high: 3 }

type Bucket = 'all' | 'not_started' | 'in_progress' | 'done' | 'overdue'
type DueWin = 'all' | 'overdue' | 'week' | 'month' | 'none'

/** Goals (#12 D33–D36): metric cards above the list + search + filters; goals may
 * link tasks (rollup mode) or stay metric-based. */
export default function GoalsTab({ projectId, goals, tasks, onRefresh }: {
  projectId: number; goals: PMGoal[]; tasks: TaskItem[]; onRefresh: () => void
}) {
  const { toast } = useToast()
  const [q, setQ] = useState('')
  const [bucket, setBucket] = useState<Bucket>('all')
  const [prio, setPrio] = useState<'all' | 'low' | 'medium' | 'high'>('all')
  const [due, setDue] = useState<DueWin>('all')
  const [adding, setAdding] = useState(false)

  const top = goals.filter(g => g.parent_goal_id == null)
  const subsOf = (id: number) => goals.filter(g => g.parent_goal_id === id)

  // ── metric cards (D33) ──
  const m = useMemo(() => {
    const now = Date.now()
    const done = top.filter(g => g.progress_pct >= 100)
    const overdue = top.filter(g => g.progress_pct < 100 && g.due_date && new Date(g.due_date).getTime() < now)
    const avg = top.length ? top.reduce((s, g) => s + g.progress_pct, 0) / top.length : 0
    const wSum = top.reduce((s, g) => s + (PRIORITY_WEIGHT[g.priority] ?? 2), 0)
    const weighted = wSum ? top.reduce((s, g) => s + g.progress_pct * (PRIORITY_WEIGHT[g.priority] ?? 2), 0) / wSum : 0
    return { total: top.length, avg: Math.round(avg), done: done.length, overdue: overdue.length, weighted: Math.round(weighted) }
  }, [top])

  // ── search + filters (D34/D35) ──
  const shown = top.filter(g => {
    if (q) {
      const needle = q.toLowerCase()
      if (!g.title.toLowerCase().includes(needle) && !(g.description || '').toLowerCase().includes(needle)) return false
    }
    if (prio !== 'all' && g.priority !== prio) return false
    const now = Date.now()
    const overdue = g.progress_pct < 100 && !!g.due_date && new Date(g.due_date).getTime() < now
    if (bucket === 'not_started' && g.progress_pct > 0) return false
    if (bucket === 'in_progress' && (g.progress_pct <= 0 || g.progress_pct >= 100)) return false
    if (bucket === 'done' && g.progress_pct < 100) return false
    if (bucket === 'overdue' && !overdue) return false
    if (due !== 'all') {
      if (due === 'none') { if (g.due_date) return false }
      else if (!g.due_date) return false
      else {
        const d = new Date(g.due_date).getTime()
        if (due === 'overdue' && (d >= now || g.progress_pct >= 100)) return false
        if (due === 'week' && (d < now || d > now + 7 * 864e5)) return false
        if (due === 'month' && (d < now || d > now + 31 * 864e5)) return false
      }
    }
    return true
  })

  const cards = [
    { label: 'Goals', value: String(m.total), icon: Target, tone: 'text-accent' },
    { label: 'Avg progress', value: `${m.avg}%`, icon: Gauge, tone: 'text-accent' },
    { label: 'Completed', value: String(m.done), icon: CheckCircle2, tone: 'text-success' },
    { label: 'Overdue', value: String(m.overdue), icon: AlertTriangle, tone: m.overdue ? 'text-danger' : 'text-muted' },
    { label: 'Weighted', value: `${m.weighted}%`, icon: ListChecks, tone: 'text-accent' },
  ]

  return (
    <div className="mx-auto max-w-4xl space-y-4 p-5">
      {/* Metric cards */}
      <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-5">
        {cards.map(c => (
          <div key={c.label} className="rounded-xl border border-border bg-panel px-3 py-2.5">
            <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wide text-muted">
              <c.icon size={11} className={c.tone} /> {c.label}
            </div>
            <div className="mt-1 text-lg font-bold text-heading">{c.value}</div>
          </div>
        ))}
      </div>

      {/* Search + filters */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative min-w-[12rem] flex-1">
          <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted" />
          <input value={q} onChange={e => setQ(e.target.value)} placeholder="Search goals…"
            className="w-full rounded-lg border border-border bg-panel py-1.5 pl-8 pr-3 text-sm text-text outline-none focus:border-accent" />
        </div>
        <select value={bucket} onChange={e => setBucket(e.target.value as Bucket)}
          className="rounded-lg border border-border bg-panel px-2 py-1.5 text-[12px] text-text outline-none">
          <option value="all">All statuses</option><option value="not_started">Not started</option>
          <option value="in_progress">In progress</option><option value="done">Done</option>
          <option value="overdue">Overdue</option>
        </select>
        <select value={prio} onChange={e => setPrio(e.target.value as typeof prio)}
          className="rounded-lg border border-border bg-panel px-2 py-1.5 text-[12px] text-text outline-none">
          <option value="all">All priority</option><option value="high">High</option>
          <option value="medium">Medium</option><option value="low">Low</option>
        </select>
        <select value={due} onChange={e => setDue(e.target.value as DueWin)}
          className="rounded-lg border border-border bg-panel px-2 py-1.5 text-[12px] text-text outline-none">
          <option value="all">Any due date</option><option value="overdue">Overdue</option>
          <option value="week">This week</option><option value="month">This month</option>
          <option value="none">No date</option>
        </select>
      </div>

      {shown.length === 0 && !adding && (
        <div className="py-8 text-center text-muted">
          <Target size={30} className="mx-auto mb-2 text-muted/40" />
          <div className="text-sm">{goals.length ? 'No goals match the filters.' : 'No goals yet. Goals drive project progress %.'}</div>
        </div>
      )}

      {shown.map(g => (
        <GoalCard key={g.id} projectId={projectId} g={g} subs={subsOf(g.id)} tasks={tasks} onRefresh={onRefresh} />
      ))}

      {adding ? (
        <NewGoalForm projectId={projectId} onDone={() => { setAdding(false); onRefresh() }} onCancel={() => setAdding(false)} />
      ) : (
        <button onClick={() => setAdding(true)} className="flex items-center gap-2 text-sm text-muted transition-colors hover:text-accent">
          <Plus size={15} /> Add Goal
        </button>
      )}
    </div>
  )
}

function GoalCard({ projectId, g, subs, tasks, onRefresh }: {
  projectId: number; g: PMGoal; subs: PMGoal[]; tasks: TaskItem[]; onRefresh: () => void
}) {
  const { toast } = useToast()
  const [editVal, setEditVal] = useState<string | null>(null)
  const [confirmDel, setConfirmDel] = useState(false)
  const [expanded, setExpanded] = useState(false)
  const [linkPick, setLinkPick] = useState('')
  const linked = (g.linked_task_ids ?? []).map(id => tasks.find(t => t.id === id)).filter(Boolean) as TaskItem[]
  const isRollup = g.mode === 'task' || linked.length > 0

  async function saveCurrent() {
    const v = parseFloat(editVal || '')
    if (isNaN(v)) return
    try { await pmPatchGoal(projectId, g.id, { current_value: v }); setEditVal(null); onRefresh() }
    catch { toast({ kind: 'error', title: 'Update failed' }) }
  }

  return (
    <div className="space-y-2 rounded-xl border border-border bg-panel p-4">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-sm font-semibold text-text">{g.title}</span>
            {g.priority && g.priority !== 'medium' && (
              <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide ${PRIORITY_BADGE[g.priority] || ''}`}>{g.priority}</span>
            )}
            {isRollup && (
              <span className="rounded bg-accent/10 px-1.5 py-0.5 text-[10px] text-accent" title="Progress rolls up from linked tasks">
                {linked.filter(t => t.status === 'done').length}/{linked.length} tasks
              </span>
            )}
          </div>
          {g.description && <div className="mt-0.5 text-[12px] leading-snug text-muted">{g.description}</div>}
          {!isRollup && (
            <div className="mt-0.5 flex flex-wrap items-center gap-2 text-[12px] text-muted">
              {editVal !== null ? (
                <>
                  <input autoFocus type="number" value={editVal} onChange={e => setEditVal(e.target.value)}
                    onKeyDown={e => { if (e.key === 'Enter') saveCurrent(); if (e.key === 'Escape') setEditVal(null) }}
                    className="w-20 rounded border border-accent bg-panel px-2 py-0.5 text-sm text-text outline-none" />
                  <span>/ {g.target_value} {g.metric_name}</span>
                  <button onClick={saveCurrent} className="text-success"><Save size={13} /></button>
                  <button onClick={() => setEditVal(null)} className="text-muted"><X size={13} /></button>
                </>
              ) : (
                <button onClick={() => setEditVal(String(g.current_value))} className="transition-colors hover:text-accent">
                  {g.current_value}{g.metric_name ? ` / ${g.target_value} ${g.metric_name}` : ''} ✎
                </button>
              )}
            </div>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <span className="text-lg font-bold text-accent">{g.progress_pct}%</span>
          {g.due_date && <span className="flex items-center gap-1 text-[11px] text-muted"><Calendar size={11} />{fmtDate(g.due_date)}</span>}
          <button onClick={() => setExpanded(x => !x)} className="text-muted transition-colors hover:text-text" title="Sub-goals & linked tasks">
            {expanded ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
          </button>
          {confirmDel ? (
            <span className="flex items-center gap-1.5 rounded-lg border border-danger/40 bg-danger/10 px-2 py-1">
              <span className="text-[10px] text-danger">Delete?</span>
              <ActionButton onAction={async () => { await pmDeleteGoal(projectId, g.id); onRefresh() }} className="text-[10px] font-medium text-danger hover:underline">Yes</ActionButton>
              <button onClick={() => setConfirmDel(false)} className="text-[10px] text-muted hover:text-text">No</button>
            </span>
          ) : (
            <button onClick={() => setConfirmDel(true)} className="text-muted transition-colors hover:text-danger"><Trash2 size={13} /></button>
          )}
        </div>
      </div>
      <Bar pct={g.progress_pct} />

      {expanded && (
        <div className="space-y-2 pt-1">
          {/* Linked tasks (rollup — D36) */}
          <div className="text-[10px] font-semibold uppercase tracking-wide text-muted">Linked tasks</div>
          {linked.map(t => (
            <div key={t.id} className="group/lt flex items-center gap-2 rounded-lg border border-border/60 bg-surface px-2 py-1.5">
              <CheckCircle2 size={13} className={t.status === 'done' ? 'text-success' : 'text-muted/40'} />
              <span className={`min-w-0 flex-1 truncate text-[12px] ${t.status === 'done' ? 'text-muted line-through' : 'text-text'}`}>{t.title}</span>
              <ActionButton onAction={async () => { await pmUnlinkGoalTask(projectId, g.id, t.id); onRefresh() }}
                icon={<X size={12} />}
                className="text-muted opacity-0 transition-opacity hover:text-danger group-hover/lt:opacity-100" />
            </div>
          ))}
          <div className="flex gap-1.5">
            <select value={linkPick} onChange={e => setLinkPick(e.target.value)}
              className="min-w-0 flex-1 rounded-lg border border-dashed border-border bg-surface px-2 py-1.5 text-[12px] text-muted outline-none">
              <option value="">+ Link a task (progress rolls up)…</option>
              {tasks.filter(t => !(g.linked_task_ids ?? []).includes(t.id)).map(t => (
                <option key={t.id} value={t.id}>{t.title}</option>
              ))}
            </select>
            <button disabled={!linkPick}
              onClick={async () => {
                try { await pmLinkGoalTask(projectId, g.id, Number(linkPick)); setLinkPick(''); onRefresh() }
                catch (e) { toast({ kind: 'error', title: 'Link failed', detail: (e as Error).message }) }
              }}
              className="rounded-lg border border-border px-2.5 text-[11px] text-muted transition-colors hover:border-accent/40 hover:text-accent disabled:opacity-40">
              Link
            </button>
          </div>

          {/* Sub-goals (existing one-level nesting) */}
          {subs.length > 0 && (
            <>
              <div className="pt-1 text-[10px] font-semibold uppercase tracking-wide text-muted">Sub-goals</div>
              {subs.map(sg => (
                <div key={sg.id} className="rounded-lg border border-border/60 bg-surface px-3 py-2">
                  <div className="mb-1 flex justify-between text-[12px]">
                    <span className="truncate text-text">{sg.title}</span>
                    <span className="ml-2 shrink-0 text-accent">{sg.progress_pct}%</span>
                  </div>
                  <Bar pct={sg.progress_pct} />
                </div>
              ))}
            </>
          )}
        </div>
      )}
    </div>
  )
}

function NewGoalForm({ projectId, onDone, onCancel }: { projectId: number; onDone: () => void; onCancel: () => void }) {
  const { toast } = useToast()
  const [title, setTitle] = useState('')
  const [desc, setDesc] = useState('')
  const [metric, setMetric] = useState('')
  const [target, setTarget] = useState('100')
  const [priority, setPriority] = useState<'low' | 'medium' | 'high'>('medium')
  const [dueDate, setDueDate] = useState('')

  async function create() {
    if (!title.trim()) return
    try {
      await pmCreateGoal(projectId, {
        title: title.trim(), description: desc || undefined, metric_name: metric || undefined,
        target_value: parseFloat(target) || 100, due_date: dueDate || undefined, priority,
      })
      onDone()
    } catch (e) { toast({ kind: 'error', title: 'Failed', detail: (e as Error).message }) }
  }

  const input = 'rounded-lg border border-border bg-surface px-2.5 py-1.5 text-sm text-text outline-none focus:border-accent'
  return (
    <div className="space-y-3 rounded-xl border border-accent/30 bg-panel p-4">
      <div className="text-sm font-medium text-text">New Goal</div>
      <input autoFocus value={title} onChange={e => setTitle(e.target.value)} onKeyDown={e => e.key === 'Enter' && create()}
        placeholder="Goal title *" className={`${input} w-full`} />
      <textarea value={desc} onChange={e => setDesc(e.target.value)} rows={2} placeholder="Description (optional)"
        className={`${input} w-full resize-none`} />
      <div className="grid grid-cols-4 gap-2">
        <input value={metric} onChange={e => setMetric(e.target.value)} placeholder="Metric" className={input} />
        <input value={target} onChange={e => setTarget(e.target.value)} type="number" placeholder="Target" className={input} />
        <select value={priority} onChange={e => setPriority(e.target.value as any)} className={input}>
          <option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option>
        </select>
        <input value={dueDate} onChange={e => setDueDate(e.target.value)} type="date" className={input} />
      </div>
      <div className="flex gap-2">
        <button onClick={create} disabled={!title.trim()}
          className="rounded-lg bg-accent px-3 py-1.5 text-sm text-white hover:bg-accent/90 disabled:opacity-50">Add Goal</button>
        <button onClick={onCancel} className="rounded-lg px-3 py-1.5 text-sm text-muted hover:bg-overlay/5 hover:text-text">Cancel</button>
      </div>
    </div>
  )
}

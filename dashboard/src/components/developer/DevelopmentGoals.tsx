import { useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { AnimatePresence, motion } from 'framer-motion'
import {
  Archive, ChevronDown, CircleAlert, FilePlus2, MoreHorizontal,
  Plus, RefreshCw, Target, Trash2, X,
} from 'lucide-react'
import type { DeveloperGoal } from '../../api'

export type GoalCommand = 'evaluate' | 'archive' | 'delete' | 'cancel'

type GoalCreateInput = {
  title: string
  objective: string
  acceptance_criteria: string[]
}

function label(value: string) {
  return value.replace(/_/g, ' ').replace(/\b\w/g, char => char.toUpperCase())
}

function parseList(raw?: string): string[] {
  if (!raw) return []
  try {
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed.map(String) : []
  } catch {
    return []
  }
}

function GoalStatus({ status }: { status: string }) {
  const tone = status === 'qualified' || status === 'completed' || status === 'qualified_local'
    ? 'border-success/30 bg-success/10 text-success'
    : status === 'archived' || status === 'canceled'
      ? 'border-border bg-overlay/5 text-muted'
      : 'border-accent/30 bg-accent/10 text-accent'
  return <span className={`inline-flex rounded border px-2 py-0.5 text-[10px] font-medium ${tone}`}>{label(status)}</span>
}

function GoalActions({ goal, busy, onCommand }: {
  goal: DeveloperGoal
  busy: boolean
  onCommand: (id: number, command: GoalCommand) => Promise<boolean>
}) {
  const [open, setOpen] = useState(false)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const menuRef = useRef<HTMLDivElement>(null)
  const [position, setPosition] = useState({ top: 0, left: 0 })

  useEffect(() => {
    if (!open) return
    const close = (event: MouseEvent) => {
      const target = event.target as Node
      if (!triggerRef.current?.contains(target) && !menuRef.current?.contains(target)) setOpen(false)
    }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [open])

  const toggle = () => {
    if (open) return setOpen(false)
    const rect = triggerRef.current?.getBoundingClientRect()
    if (!rect) return
    setPosition({
      top: Math.min(window.innerHeight - 126, rect.bottom + 4),
      left: Math.max(8, rect.right - 192),
    })
    setOpen(true)
  }

  const run = async (command: GoalCommand) => {
    if (command === 'delete' && !window.confirm(`Delete goal "${goal.title}"? Historical run evidence remains stored.`)) return
    setOpen(false)
    await onCommand(goal.id, command)
  }

  return (
    <>
      <button ref={triggerRef} type="button" title="Goal actions" onClick={toggle} disabled={busy}
        className="inline-flex h-8 w-8 items-center justify-center rounded-md text-muted hover:bg-overlay/10 hover:text-text disabled:opacity-40">
        <MoreHorizontal size={16} />
      </button>
      {createPortal(<AnimatePresence>{open && (
        <motion.div ref={menuRef} initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -4 }}
          style={position} className="fixed z-[100] w-48 rounded-md border border-border bg-surface p-1 shadow-2xl">
          <button type="button" onClick={() => void run('evaluate')} className="flex h-9 w-full items-center gap-2 rounded px-2 text-xs text-text hover:bg-overlay/10"><RefreshCw size={14} /> Re-evaluate evidence</button>
          {goal.status !== 'archived' && <button type="button" onClick={() => void run('archive')} className="flex h-9 w-full items-center gap-2 rounded px-2 text-xs text-text hover:bg-overlay/10"><Archive size={14} /> Archive goal</button>}
          <button type="button" onClick={() => void run('delete')} className="flex h-9 w-full items-center gap-2 rounded px-2 text-xs text-danger hover:bg-danger/10"><Trash2 size={14} /> Delete goal</button>
        </motion.div>
      )}</AnimatePresence>, document.body)}
    </>
  )
}

function GoalDialog({ open, busy, onClose, onCreate }: {
  open: boolean
  busy: boolean
  onClose: () => void
  onCreate: (input: GoalCreateInput) => Promise<boolean>
}) {
  const [title, setTitle] = useState('')
  const [objective, setObjective] = useState('')
  const [criteria, setCriteria] = useState('')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    const escape = (event: KeyboardEvent) => { if (event.key === 'Escape' && !busy) onClose() }
    document.addEventListener('keydown', escape)
    return () => document.removeEventListener('keydown', escape)
  }, [open, busy, onClose])

  const acceptance = criteria.split('\n').map(item => item.trim()).filter(Boolean)
  const valid = title.trim().length >= 3 && objective.trim().length >= 10 && acceptance.length > 0
  const submit = async () => {
    if (!valid) return
    setError(null)
    const saved = await onCreate({ title: title.trim(), objective: objective.trim(), acceptance_criteria: acceptance })
    if (!saved) return setError('The goal was not saved. Your draft is still available.')
    setTitle(''); setObjective(''); setCriteria(''); onClose()
  }

  return <AnimatePresence>{open && (
    <motion.div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 p-3 backdrop-blur-sm"
      initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
      <motion.section role="dialog" aria-modal="true" aria-labelledby="new-goal-title"
        initial={{ opacity: 0, y: 10, scale: 0.99 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 6, scale: 0.99 }}
        className="w-full max-w-2xl rounded-lg border border-border bg-surface shadow-2xl">
        <header className="flex items-center justify-between border-b border-border px-5 py-4">
          <div><h2 id="new-goal-title" className="font-semibold text-text">New outcome goal</h2><p className="mt-0.5 text-xs text-muted">Define success first. Link executable Queue items after saving.</p></div>
          <button type="button" title="Close" onClick={onClose} disabled={busy} className="inline-flex h-8 w-8 items-center justify-center rounded-md text-muted hover:bg-overlay/10 hover:text-text"><X size={17} /></button>
        </header>
        <div className="space-y-4 px-5 py-5">
          <label className="block"><span className="mb-1.5 block text-xs text-muted">Goal title</span><input autoFocus value={title} onChange={event => setTitle(event.target.value)} placeholder="Coding runs recover safely after restart" className="h-10 w-full rounded-md border border-border bg-background px-3 text-sm text-text outline-none focus:border-accent" /></label>
          <label className="block"><span className="mb-1.5 block text-xs text-muted">Desired outcome</span><textarea value={objective} onChange={event => setObjective(event.target.value)} rows={3} placeholder="Describe the owner-visible outcome and important boundaries." className="w-full resize-y rounded-md border border-border bg-background px-3 py-2 text-sm text-text outline-none focus:border-accent" /></label>
          <label className="block"><span className="mb-1.5 block text-xs text-muted">Acceptance criteria, one per line</span><textarea value={criteria} onChange={event => setCriteria(event.target.value)} rows={6} placeholder={'A paused run resumes with the same run ID\nCompleted writes are not duplicated\nRecovery evidence is visible in History'} className="w-full resize-y rounded-md border border-border bg-background px-3 py-2 text-sm text-text outline-none focus:border-accent" /></label>
          <div className="flex items-start gap-2 border-l-2 border-accent/50 pl-3 text-xs text-muted"><CircleAlert size={14} className="mt-0.5 shrink-0 text-accent" /> Goals do not run agents. Create or link bounded Queue items to produce evidence for these criteria.</div>
          {error && <div className="border-l-2 border-danger pl-3 text-xs text-danger">{error}</div>}
        </div>
        <footer className="flex justify-end gap-2 border-t border-border px-5 py-4">
          <button type="button" onClick={onClose} disabled={busy} className="h-9 rounded-md border border-border px-3 text-sm text-text hover:bg-overlay/10">Cancel</button>
          <button type="button" onClick={() => void submit()} disabled={busy || !valid} className="inline-flex h-9 items-center gap-2 rounded-md bg-accent px-3 text-sm font-medium text-background disabled:opacity-40"><Plus size={15} /> Save goal</button>
        </footer>
      </motion.section>
    </motion.div>
  )}</AnimatePresence>
}

export default function DevelopmentGoals({ goals, busy, onCreate, onCommand, onCreateItem }: {
  goals: DeveloperGoal[]
  busy: boolean
  onCreate: (input: GoalCreateInput) => Promise<boolean>
  onCommand: (id: number, command: GoalCommand) => Promise<boolean>
  onCreateItem: (goalId: number) => void
}) {
  const [dialogOpen, setDialogOpen] = useState(false)
  const ordered = useMemo(() => [...goals].sort((a, b) => (b.updated_at ?? '').localeCompare(a.updated_at ?? '')), [goals])

  return <section className="mx-auto max-w-7xl">
    <header className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div><div className="flex items-center gap-2"><Target size={17} className="text-accent" /><h2 className="text-base font-semibold text-text">Outcome goals</h2></div><p className="mt-1 text-xs text-muted">Desired outcomes, qualification evidence, and the Queue items responsible for delivery.</p></div>
      <button type="button" onClick={() => setDialogOpen(true)} className="inline-flex h-9 items-center justify-center gap-2 rounded-md bg-accent px-3 text-sm font-medium text-background hover:brightness-110"><Plus size={15} /> New goal</button>
    </header>

    {!ordered.length ? <div className="rounded-md border border-dashed border-border py-12 text-center"><Target size={22} className="mx-auto text-muted" /><p className="mt-3 text-sm text-text">No outcome goals yet</p><p className="mt-1 text-xs text-muted">Create a goal, then break it into bounded Queue items.</p><button type="button" onClick={() => setDialogOpen(true)} className="mt-4 text-xs font-medium text-accent hover:underline">Create the first goal</button></div> : (
      <div className="space-y-2">{ordered.map(goal => {
        const criteria = parseList(goal.acceptance_criteria_json)
        const evidence = goal.evidence ?? []
        const percent = Math.max(0, Math.min(100, Number(goal.qualification_percent ?? 0)))
        return <details key={goal.id} className="group rounded-md border border-border bg-surface/30 open:bg-surface/60">
          <summary className="flex cursor-pointer list-none items-center gap-3 px-4 py-3.5">
            <ChevronDown size={15} className="shrink-0 text-muted transition-transform group-open:rotate-180" />
            <div className="min-w-0 flex-1"><div className="flex flex-wrap items-center gap-2"><span className="truncate text-sm font-medium text-text">{goal.title}</span><GoalStatus status={goal.status} /></div><p className="mt-1 line-clamp-1 text-[11px] text-muted">{goal.objective}</p></div>
            <div className="hidden w-40 sm:block"><div className="flex justify-between text-[10px] text-muted"><span>Qualified</span><span className="tabular-nums text-text">{percent}%</span></div><div className="mt-1 h-1 overflow-hidden rounded bg-overlay/10"><div className="h-full rounded bg-success transition-[width]" style={{ width: `${percent}%` }} /></div></div>
            <div className="hidden min-w-24 text-right text-[11px] text-muted md:block">{goal.items?.length ?? 0} linked item{goal.items?.length === 1 ? '' : 's'}</div>
            <GoalActions goal={goal} busy={busy} onCommand={onCommand} />
          </summary>
          <div className="grid border-t border-border lg:grid-cols-[minmax(0,1fr)_320px]">
            <div className="px-4 py-4 lg:border-r lg:border-border">
              <div className="mb-3 flex items-center justify-between"><h3 className="text-[10px] font-semibold uppercase text-muted">Evidence matrix</h3><button type="button" onClick={() => void onCommand(goal.id, 'evaluate')} disabled={busy} className="inline-flex h-8 items-center gap-1.5 rounded-md border border-border px-2.5 text-xs text-text hover:bg-overlay/10 disabled:opacity-40"><RefreshCw size={13} /> Evaluate</button></div>
              <div className="space-y-2">{criteria.map((criterion, index) => {
                const row = evidence.find(item => Number(item.index) === index || String(item.criterion) === criterion)
                const passed = String(row?.status ?? '') === 'passed'
                return <div key={`${goal.id}-${index}`} className="grid gap-2 rounded border border-border/70 px-3 py-2.5 sm:grid-cols-[20px_minmax(0,1fr)_auto]">
                  <span className={`mt-0.5 inline-flex h-4 w-4 items-center justify-center rounded-full border text-[9px] ${passed ? 'border-success bg-success/15 text-success' : 'border-border text-muted'}`}>{passed ? '✓' : index + 1}</span>
                  <div><p className="text-xs text-text">{criterion}</p>{row?.status ? <p className="mt-1 text-[10px] text-muted">{label(String(row.status))}</p> : null}</div>
                  <span className={`text-[10px] font-medium ${passed ? 'text-success' : 'text-warning'}`}>{passed ? 'Proven' : 'Needs evidence'}</span>
                </div>
              })}</div>
              {!criteria.length && <p className="text-xs text-muted">No acceptance criteria were stored for this legacy goal.</p>}
            </div>
            <aside className="px-4 py-4"><div className="mb-3 flex items-center justify-between"><h3 className="text-[10px] font-semibold uppercase text-muted">Linked work</h3><button type="button" onClick={() => onCreateItem(goal.id)} className="inline-flex h-8 items-center gap-1.5 rounded-md border border-border px-2.5 text-xs text-text hover:bg-overlay/10"><FilePlus2 size={13} /> Create item</button></div>
              <div className="space-y-2">{goal.items?.map(item => <div key={item.task_id} className="flex items-center justify-between gap-3 border-l-2 border-accent/40 pl-3"><div className="min-w-0"><p className="truncate text-xs text-text">#{item.queue_id} {item.title}</p><p className="mt-0.5 text-[10px] text-muted">{label(item.owner_state ?? item.status)}</p></div></div>)}{!goal.items?.length && <p className="text-xs text-muted">No Queue items linked yet.</p>}</div>
              {!!goal.gaps?.length && <div className="mt-4 border-t border-border pt-3"><h4 className="text-[10px] font-semibold uppercase text-warning">Open gaps</h4>{goal.gaps.map(gap => <p key={gap} className="mt-1.5 text-[10px] leading-4 text-muted">{gap}</p>)}</div>}
            </aside>
          </div>
        </details>
      })}</div>
    )}
    <GoalDialog open={dialogOpen} busy={busy} onClose={() => setDialogOpen(false)} onCreate={onCreate} />
  </section>
}

// Queue tab (#18 UI continuation): Main Thread → Next slot → drag-ordered
// priority list, with Completed and Plan Detail modals. Ordering persists via
// POST /api/developer/queue/order; auto mode promotes Next → Main server-side.
// The Auto switch is the shared AutoQueueToggle, so it stays in lockstep with
// the same control on the Process tab (both write developer.auto_queue).
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { AnimatePresence, motion } from 'framer-motion'
import {
  Archive, ArrowUpFromLine, CheckCircle2, ChevronRight, FileText, GripVertical,
  Loader2, Maximize2, Minimize2, Play, Plus, RotateCcw, Search, Sparkles, Target, TestTube2,
  ShieldCheck, Trash2, Upload, X,
} from 'lucide-react'
import { createDeveloperQueueItem, getDeveloperQueue, getDeveloperQueuePlan, preflightDeveloperQueueItem, removeDeveloperQueueItem, restoreDeveloperQueueItem, setDeveloperQueueOrder, type DeveloperGoal, type DeveloperQueueItem, type DeveloperQueuePlan, type DeveloperQueueState, type DeveloperReadiness, type DeveloperWorkflow } from '../../api.developer'
import { TERMINAL_STATES } from '../../developer.states'
import { ActionButton } from '../async-ui'
import { useToast } from '../../context/ToastProvider'
import MarkdownView from '../chat/MarkdownView'
import AutoQueueToggle from './AutoQueueToggle'

function label(value: string) {
  return value.replace(/_/g, ' ').replace(/\b\w/g, char => char.toUpperCase())
}

function deps(item: DeveloperQueueItem): number[] {
  try { return JSON.parse(item.dependencies_json) as number[] } catch { return [] }
}

/** Why an item is off the queue. `status` alone cannot say: a locally-complete run, a
 *  canceled run and a failed run all leave the task at 'approved', and only owner_state
 *  distinguishes them. */
function offQueueReason(item: DeveloperQueueItem): string {
  if (item.status === 'completed') return 'Shipped'
  const owner = item.owner_state
  if (owner && owner !== 'Ready') return label(owner)
  return item.status === 'approved' ? 'Ran, not shipped' : label(item.status)
}

/** One-line item card used in the Next slot and the priority list. */
function ItemCard({ item, badge, draggable, busy, prominent, onDragStart, onDragEnd, onOpen, onStart }: {
  item: DeveloperQueueItem; badge: ReactNode; draggable: boolean; busy: boolean; prominent?: boolean
  onDragStart?: (event: React.DragEvent) => void; onDragEnd?: () => void
  onOpen: () => void; onStart?: () => void
}) {
  const after = deps(item)
  return (
    <div draggable={draggable} onDragStart={onDragStart} onDragEnd={onDragEnd} onClick={onOpen}
      className={`group flex items-center gap-2.5 rounded-md border border-border bg-surface/70 px-2.5 py-2 text-sm transition-colors hover:border-accent/40 ${draggable ? 'cursor-grab active:cursor-grabbing' : 'cursor-pointer'}`}>
      {draggable && <GripVertical size={14} className="shrink-0 text-muted/60" />}
      {badge}
      <div className="min-w-0 flex-1">
        <span className="font-medium text-text">#{item.queue_id}</span>
        <span className="ml-1.5 truncate text-text/90">{item.title}</span>
      </div>
      <span className="hidden shrink-0 text-[11px] text-muted sm:inline">
        {after.length ? `after ${after.map(id => `#${id}`).join(' ')}` : item.queue_effort ?? ''}
      </span>
      <span className="shrink-0 rounded border border-border px-1.5 py-0.5 text-[10px] uppercase text-muted">{item.risk}</span>
      {onStart && (
        <button disabled={busy} title={`Start #${item.queue_id} now`}
          onClick={event => { event.stopPropagation(); onStart() }}
          className={prominent
            ? 'inline-flex h-7 shrink-0 items-center gap-1.5 rounded-md bg-accent px-2.5 text-[11px] font-semibold text-background shadow-sm transition-[filter] hover:brightness-110 disabled:opacity-40'
            : 'inline-flex h-7 shrink-0 items-center gap-1.5 rounded-md border border-accent/40 bg-accent/10 px-2 text-[11px] font-medium text-accent transition-colors hover:bg-accent/20 disabled:opacity-40'}>
          <Play size={12} /><span className="hidden sm:inline">Start{prominent ? ' now' : ''}</span>
        </button>
      )}
    </div>
  )
}

export default function QueueBoard({ state, active, busy, autoQueue, autoQueueBusy, acceptanceMode, goals, createForGoalId, createRequestId, onAutoQueue, onStart, onPrepare, onOpenProcess, onConfigureReviewer, onState }: {
  state: DeveloperQueueState
  active: DeveloperWorkflow | null
  busy: boolean
  autoQueue: boolean
  autoQueueBusy: boolean
  acceptanceMode: boolean
  goals: DeveloperGoal[]
  createForGoalId?: number | null
  createRequestId?: number
  onAutoQueue: (enabled: boolean) => void
  onStart: (queueId: number, readinessId: number) => void
  onPrepare: (queueId: number, readinessId: number) => void
  onOpenProcess: () => void
  onConfigureReviewer: () => void
  onState: (next: DeveloperQueueState) => void
}) {
  const { toast } = useToast()
  const [saving, setSaving] = useState(false)
  const [draggingId, setDraggingId] = useState<number | null>(null)
  const [overSlot, setOverSlot] = useState<'next' | number | null>(null)
  const [completedOpen, setCompletedOpen] = useState(false)
  const [addOpen, setAddOpen] = useState(false)
  const [planFor, setPlanFor] = useState<DeveloperQueueItem | null>(null)
  const [preflightFor, setPreflightFor] = useState<DeveloperQueueItem | null>(null)
  const [readiness, setReadiness] = useState<DeveloperReadiness | null>(null)
  const [preflightBusy, setPreflightBusy] = useState(false)
  const suppressClick = useRef(false)

  useEffect(() => {
    if (createRequestId && createForGoalId != null) setAddOpen(true)
  }, [createRequestId, createForGoalId])

  const byId = useMemo(() => new Map(state.items.map(item => [item.queue_id, item])), [state.items])
  const nextItem = state.next_queue_id != null ? byId.get(state.next_queue_id) ?? null : null
  // Everything that is off the queue, not only what shipped. Starting a run moves an item to
  // 'approved' and nothing moves it back unless the run merges and deploys, so a run that
  // finished locally, was canceled, or failed left its item in neither list -- visible only
  // as a History row with no action on it. The live run is excluded because it is not idle.
  const offQueue = useMemo(() => state.items.filter(item =>
    item.status !== 'planned' && item.status !== 'deleted' &&
    !(active && !TERMINAL_STATES.has(active.state) && active.queue_id === item.queue_id),
  ), [state.items, active])

  // Priority list = saved order first, then any planned item the order does not
  // know yet (new QUEUE.md rows), excluding the Next slot.
  const priorityList = useMemo(() => {
    const planned = state.items.filter(item => item.status === 'planned' && item.queue_id !== state.next_queue_id)
    const pos = new Map(state.order.map((id, index) => [id, index]))
    return [...planned].sort((a, b) => {
      const pa = pos.has(a.queue_id) ? pos.get(a.queue_id)! : 1_000 + state.items.indexOf(a)
      const pb = pos.has(b.queue_id) ? pos.get(b.queue_id)! : 1_000 + state.items.indexOf(b)
      return pa - pb
    })
  }, [state, byId])

  const persist = useCallback(async (order: number[], nextId: number | null) => {
    const before = state
    onState({ ...state, order, next_queue_id: nextId })   // optimistic
    setSaving(true)
    try {
      onState(await setDeveloperQueueOrder(order, nextId))
    } catch (err) {
      onState(before)                                     // revert
      toast({ kind: 'error', title: 'Queue order was not saved', detail: err instanceof Error ? err.message : String(err) })
    } finally { setSaving(false) }
  }, [state, onState, toast])

  // ── drag handlers ──────────────────────────────────────────────────────────
  const dragStart = (id: number) => (event: React.DragEvent) => {
    event.dataTransfer.setData('text/plain', String(id))
    event.dataTransfer.effectAllowed = 'move'
    setDraggingId(id)
  }
  const dragEnd = () => {
    setDraggingId(null); setOverSlot(null)
    suppressClick.current = true
    window.setTimeout(() => { suppressClick.current = false }, 180)
  }
  const draggedId = (event: React.DragEvent): number | null => {
    const raw = event.dataTransfer.getData('text/plain')
    const id = Number(raw || draggingId)
    return Number.isFinite(id) && id > 0 ? id : null
  }

  const dropOnNext = (event: React.DragEvent) => {
    event.preventDefault(); setOverSlot(null)
    const id = draggedId(event)
    if (id == null || id === state.next_queue_id) return
    // previous Next returns to the head of the list
    const rest = priorityList.map(item => item.queue_id).filter(qid => qid !== id)
    const order = state.next_queue_id != null ? [state.next_queue_id, ...rest] : rest
    void persist(order, id)
  }

  // Drop into the priority list at `index`. Used by each row (precise position)
  // and by the section itself (drop anywhere / into an empty list = append),
  // which is what lets a lone Next item be dragged back into the list.
  const dropOnList = (index: number) => (event: React.DragEvent) => {
    event.preventDefault(); event.stopPropagation(); setOverSlot(null)
    const id = draggedId(event)
    if (id == null) return
    const ids = priorityList.map(item => item.queue_id).filter(qid => qid !== id)
    ids.splice(Math.min(index, ids.length), 0, id)
    // dragging the Next card back into the list clears the slot
    void persist(ids, id === state.next_queue_id ? null : state.next_queue_id)
  }

  const openPlan = (item: DeveloperQueueItem) => {
    if (suppressClick.current) return
    setPlanFor(item)
  }

  const reviewStart = async (item: DeveloperQueueItem, options: { protected_paths_approved?: boolean; selected_agent?: string } = {}) => {
    setPreflightFor(item); setPreflightBusy(true)
    try { setReadiness(await preflightDeveloperQueueItem(item.queue_id, options)) }
    catch (err) {
      setReadiness(null)
      toast({ kind: 'error', title: 'Readiness check failed', detail: err instanceof Error ? err.message : String(err) })
    } finally { setPreflightBusy(false) }
  }

  const createItem = async (input: { title: string; objective: string; acceptance_criteria: string[]; goal_ids: number[]; plan_markdown?: string | null }) => {
    try {
      await createDeveloperQueueItem({ ...input, expected_queue_hash: state.queue_hash })
      onState(await getDeveloperQueue())
      setAddOpen(false)
      toast({ kind: 'success', title: 'Queue item created', detail: 'The plan and QUEUE.md were updated together.' })
    } catch (err) {
      toast({ kind: 'error', title: 'Queue item was not created', detail: err instanceof Error ? err.message : String(err) })
    }
  }

  // ── restore / remove (Completed modal) ─────────────────────────────────────
  const [rowBusy, setRowBusy] = useState<number | null>(null)
  const [confirmRemove, setConfirmRemove] = useState<number | null>(null)
  const restore = async (id: number) => {
    setRowBusy(id)
    try {
      onState(await restoreDeveloperQueueItem(id))
      toast({ kind: 'success', title: `#${id} is back in the queue` })
    } catch (err) {
      toast({ kind: 'error', title: `#${id} was not restored`, detail: err instanceof Error ? err.message : String(err) })
    } finally { setRowBusy(null) }
  }
  const remove = async (id: number) => {
    setRowBusy(id)
    try {
      onState(await removeDeveloperQueueItem(id))
      setConfirmRemove(null)
      toast({ kind: 'success', title: `#${id} removed from the queue` })
    } catch (err) {
      toast({ kind: 'error', title: `#${id} was not removed`, detail: err instanceof Error ? err.message : String(err) })
    } finally { setRowBusy(null) }
  }

  const mainItem = active ? byId.get(active.queue_id) : null
  const startTarget = nextItem ?? priorityList[0] ?? null
  const dragging = draggingId != null

  return (
    <div className="space-y-4">
      {/* ── 1. Main Thread ─────────────────────────────────────────────────── */}
      <section className="relative overflow-hidden rounded-lg border border-accent/25 bg-surface/70 px-4 py-4">
        <div className="absolute inset-y-0 left-0 w-1 bg-accent" />
        <div className="mb-2 flex items-center justify-between">
          <div className="text-[10px] font-semibold uppercase tracking-wide text-accent">Main thread</div>
          {saving && <span className="inline-flex items-center gap-1 text-[10px] text-muted"><Loader2 size={11} className="animate-spin" /> saving order</span>}
        </div>
        {active ? (
          <div className="flex flex-wrap items-center gap-3">
            <div className="min-w-0 flex-1">
              <button onClick={() => mainItem && openPlan(mainItem)} className="text-left">
                <span className="text-sm font-semibold text-text">#{active.queue_id} {active.title}</span>
              </button>
              <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted">
                <span className="rounded-full border border-accent/35 bg-accent/10 px-2 py-0.5 text-[10px] font-medium text-accent">{label(active.state)}</span>
                <span>{label(active.stage)} · {Math.round((active.progress || 0) * 100)}%</span>
                {active.sprint?.title && <span className="truncate">· {active.sprint.title}</span>}
                {active.blocker && <span className="text-danger">· {active.blocker}</span>}
              </div>
              <div className="mt-2 h-1.5 w-full max-w-md overflow-hidden rounded-full bg-background/70">
                <div className="h-full rounded-full bg-accent transition-all" style={{ width: `${Math.round((active.progress || 0) * 100)}%` }} />
              </div>
            </div>
            <button onClick={onOpenProcess}
              className="inline-flex h-8 items-center gap-1.5 rounded-md border border-border px-2.5 text-xs text-text hover:border-accent/40">
              Open process <ChevronRight size={13} />
            </button>
          </div>
        ) : (
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm text-muted">Idle — no development item is running.</p>
            {startTarget && (
              <button disabled={busy} onClick={() => void reviewStart(startTarget)}
                className="inline-flex h-9 items-center gap-2 rounded-md bg-accent px-3.5 text-sm font-semibold text-background shadow-sm transition-[filter] hover:brightness-110 disabled:opacity-40">
                {busy ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />} Start #{startTarget.queue_id} now
              </button>
            )}
          </div>
        )}
      </section>

      {/* ── 2. Next Item slot ──────────────────────────────────────────────── */}
      <section
        onDragOver={event => { event.preventDefault(); setOverSlot('next') }}
        onDragLeave={() => setOverSlot(current => (current === 'next' ? null : current))}
        onDrop={dropOnNext}
        className={`rounded-lg border border-dashed px-4 py-3 transition-colors ${overSlot === 'next' ? 'border-accent bg-accent/5' : 'border-border bg-surface/40'}`}>
        <div className="mb-2 flex items-center justify-between">
          <div className="text-[10px] font-semibold uppercase tracking-wide text-muted">Next item</div>
          <AutoQueueToggle enabled={autoQueue} busy={autoQueueBusy} onChange={onAutoQueue} />
        </div>
        {nextItem ? (
          <ItemCard item={nextItem} draggable busy={busy} prominent
            badge={<span className="shrink-0 rounded bg-accent/15 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-accent">Next</span>}
            onDragStart={dragStart(nextItem.queue_id)} onDragEnd={dragEnd}
            onOpen={() => openPlan(nextItem)} onStart={() => void reviewStart(nextItem)} />
        ) : (
          <p className="py-1 text-xs text-muted">Drag an item here to stage it. {autoQueue ? 'Auto mode will promote it when the main thread frees up.' : 'Turn Auto on to promote it automatically.'}</p>
        )}
      </section>

      {/* ── 3. Priority list ───────────────────────────────────────────────── */}
      {/* The whole section is a drop target so an item can always be dragged
          back in — including into an empty list or the gaps between rows. Rows
          stop propagation so they still control precise insertion position. */}
      <section
        onDragOver={dragging ? (event => { event.preventDefault(); setOverSlot(priorityList.length) }) : undefined}
        onDrop={dragging ? dropOnList(priorityList.length) : undefined}>
        <div className="mb-2 flex items-center justify-between gap-2">
          <div className="text-[10px] font-semibold uppercase tracking-wide text-muted">Priority queue · {priorityList.length}</div>
          <div className="flex items-center gap-2">
            <button onClick={() => setAddOpen(true)} title="Add a new queue item"
              className="inline-flex items-center gap-1.5 rounded-md border border-accent/40 bg-accent/10 px-2 py-1 text-[11px] font-medium text-accent transition-colors hover:bg-accent/20">
              <Plus size={13} /> Add item
            </button>
            <button onClick={() => setCompletedOpen(true)}
              className="inline-flex items-center gap-1.5 rounded-md border border-border px-2 py-1 text-[11px] text-muted hover:text-text">
              <Archive size={12} /> Off queue · {offQueue.length}
            </button>
          </div>
        </div>
        {priorityList.length === 0 ? (
          <p className={`rounded-lg border border-dashed px-4 py-6 text-center text-xs transition-colors ${dragging ? 'border-accent bg-accent/5 text-accent' : 'border-border bg-surface/40 text-muted'}`}>
            {dragging ? 'Drop here to move it back into the queue' : 'Every planned item is staged or running.'}
          </p>
        ) : (
          <div className="space-y-1.5">
            {priorityList.map((item, index) => (
              <div key={item.queue_id}
                onDragOver={event => { event.preventDefault(); event.stopPropagation(); setOverSlot(index) }}
                onDragLeave={() => setOverSlot(current => (current === index ? null : current))}
                onDrop={dropOnList(index)}
                className={`rounded-md transition-shadow ${overSlot === index ? 'ring-1 ring-accent/60' : ''} ${draggingId === item.queue_id ? 'opacity-40' : ''}`}>
                <ItemCard item={item} draggable busy={busy}
                  badge={<span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-overlay/10 text-[10px] font-semibold text-muted">{index + 1}</span>}
                  onDragStart={dragStart(item.queue_id)} onDragEnd={dragEnd}
                  onOpen={() => openPlan(item)} onStart={() => void reviewStart(item)} />
              </div>
            ))}
            {/* tail affordance: drop after the last card */}
            <div className={`h-6 rounded-md border border-dashed transition-colors ${overSlot === priorityList.length && dragging ? 'border-accent bg-accent/5' : 'border-transparent'}`} />
          </div>
        )}
      </section>

      <CompletedModal open={completedOpen} onClose={() => { setCompletedOpen(false); setConfirmRemove(null) }}
        items={offQueue} rowBusy={rowBusy} confirmRemove={confirmRemove}
        onOpenPlan={item => setPlanFor(item)} onRestore={restore}
        onAskRemove={setConfirmRemove} onRemove={remove} />
      <AddItemModal open={addOpen} goals={goals} initialGoalId={createForGoalId} onClose={() => setAddOpen(false)} onSubmit={createItem} />
      <ReadinessModal item={preflightFor} report={readiness} busy={preflightBusy}
        allowPrepare={acceptanceMode}
        onClose={() => { setPreflightFor(null); setReadiness(null) }}
        onConfigureReviewer={() => {
          setPreflightFor(null); setReadiness(null)
          onConfigureReviewer()
        }}
        onRefresh={options => preflightFor && reviewStart(preflightFor, options)}
        onPrepare={() => {
          if (!preflightFor || !readiness?.ready) return
          onPrepare(preflightFor.queue_id, readiness.readiness_id)
          setPreflightFor(null); setReadiness(null)
        }}
        onStart={() => {
          if (!preflightFor || !readiness?.ready) return
          onStart(preflightFor.queue_id, readiness.readiness_id)
          setPreflightFor(null); setReadiness(null)
        }} />
      <PlanModal item={planFor} onClose={() => setPlanFor(null)} />
    </div>
  )
}

// ── 4. Completed Items modal ─────────────────────────────────────────────────
function CompletedModal({ open, onClose, items, rowBusy, confirmRemove, onOpenPlan, onRestore, onAskRemove, onRemove }: {
  open: boolean; onClose: () => void; items: DeveloperQueueItem[]
  rowBusy: number | null; confirmRemove: number | null
  onOpenPlan: (item: DeveloperQueueItem) => void
  onRestore: (id: number) => void; onAskRemove: (id: number | null) => void; onRemove: (id: number) => void
}) {
  const [query, setQuery] = useState('')
  useEffect(() => { if (open) setQuery('') }, [open])
  const filtered = items.filter(item =>
    !query.trim() || `#${item.queue_id} ${item.title}`.toLowerCase().includes(query.trim().toLowerCase()))
  return createPortal(
    <AnimatePresence>
      {open && (
        <motion.div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 p-3 backdrop-blur-sm"
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose}>
          <motion.section role="dialog" aria-modal="true" onClick={event => event.stopPropagation()}
            initial={{ opacity: 0, y: 12, scale: 0.985 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 8, scale: 0.985 }}
            transition={{ duration: 0.16 }}
            className="flex max-h-[85vh] w-full max-w-2xl flex-col rounded-lg border border-border bg-surface shadow-2xl">
            <header className="flex items-center justify-between border-b border-border px-5 py-4">
              <div><h2 className="font-semibold text-text">Items off the queue</h2><p className="mt-0.5 text-xs text-muted">Everything that shipped, stopped, or was canceled. Push one back into the queue to run it again, or remove it from the list.</p></div>
              <button onClick={onClose} title="Close" className="inline-flex h-8 w-8 items-center justify-center rounded-md text-muted hover:bg-overlay/10 hover:text-text"><X size={17} /></button>
            </header>
            <div className="border-b border-border px-5 py-3">
              <div className="relative">
                <Search size={13} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-muted" />
                <input autoFocus value={query} onChange={event => setQuery(event.target.value)} placeholder="Search by id or title"
                  className="h-9 w-full rounded-md border border-border bg-background pl-8 pr-3 text-sm text-text outline-none focus:border-accent" />
              </div>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto px-5 py-3">
              {filtered.length === 0 ? (
                <p className="py-8 text-center text-xs text-muted">{items.length === 0 ? 'Every item is still in the queue.' : 'No item off the queue matches the search.'}</p>
              ) : filtered.map(item => (
                <div key={item.queue_id} className="flex items-center gap-2.5 border-b border-border/60 py-2.5 last:border-b-0">
                  <CheckCircle2 size={14} className={`shrink-0 ${item.status === 'completed' ? 'text-success' : 'text-muted'}`} />
                  <button onClick={() => onOpenPlan(item)} className="min-w-0 flex-1 text-left">
                    <span className="text-sm font-medium text-text">#{item.queue_id} {item.title}</span>
                    <span className="ml-2 hidden text-[11px] text-muted sm:inline">{offQueueReason(item)}</span>
                  </button>
                  <button disabled={rowBusy != null} onClick={() => onRestore(item.queue_id)} title="Push back to queue"
                    className="inline-flex h-7 items-center gap-1 rounded-md border border-border px-2 text-[11px] text-muted hover:text-accent disabled:opacity-40">
                    {rowBusy === item.queue_id ? <Loader2 size={12} className="animate-spin" /> : <ArrowUpFromLine size={12} />} Requeue
                  </button>
                  {confirmRemove === item.queue_id ? (
                    <span className="flex items-center gap-1">
                      <button disabled={rowBusy != null} onClick={() => onRemove(item.queue_id)}
                        className="inline-flex h-7 items-center gap-1 rounded-md border border-danger/40 bg-danger/10 px-2 text-[11px] font-medium text-danger disabled:opacity-40">
                        {rowBusy === item.queue_id ? <Loader2 size={12} className="animate-spin" /> : <Trash2 size={12} />} Confirm
                      </button>
                      <button disabled={rowBusy != null} onClick={() => onAskRemove(null)}
                        className="inline-flex h-7 items-center rounded-md border border-border px-2 text-[11px] text-muted">Keep</button>
                    </span>
                  ) : (
                    <button disabled={rowBusy != null} onClick={() => onAskRemove(item.queue_id)} title="Remove from the queue list (QUEUE.md is untouched)"
                      className="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted hover:text-danger disabled:opacity-40"><Trash2 size={13} /></button>
                  )}
                </div>
              ))}
            </div>
          </motion.section>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body,
  )
}

// Add one canonical Queue item and plan in a single conflict-checked operation.
function AddItemModal({ open, goals, initialGoalId, onClose, onSubmit }: {
  open: boolean; goals: DeveloperGoal[]; initialGoalId?: number | null; onClose: () => void
  onSubmit: (input: { title: string; objective: string; acceptance_criteria: string[]; goal_ids: number[]; plan_markdown?: string | null }) => void
}) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [criteria, setCriteria] = useState('')
  const [selGoals, setSelGoals] = useState<number[]>([])
  const [planMode, setPlanMode] = useState<'tobi' | 'upload' | null>(null)
  const [planFile, setPlanFile] = useState<string | null>(null)
  const [planMarkdown, setPlanMarkdown] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (!open) return
    setName(''); setDescription(''); setCriteria(''); setSelGoals(initialGoalId == null ? [] : [initialGoalId]); setPlanMode(null); setPlanFile(null); setPlanMarkdown(null)
  }, [open, initialGoalId])

  const toggleGoal = (id: number) =>
    setSelGoals(current => (current.includes(id) ? current.filter(x => x !== id) : [...current, id]))

  const inputClass = 'w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-text outline-none transition-colors placeholder:text-muted/70 focus:border-accent'

  return createPortal(
    <AnimatePresence>
      {open && (
        <motion.div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 p-3 backdrop-blur-sm"
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose}>
          <motion.section role="dialog" aria-modal="true" onClick={event => event.stopPropagation()}
            initial={{ opacity: 0, y: 12, scale: 0.985 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 8, scale: 0.985 }}
            transition={{ duration: 0.16 }}
            className="flex max-h-[88vh] w-full max-w-lg flex-col rounded-lg border border-border bg-surface shadow-2xl">
            <header className="flex items-start justify-between gap-3 border-b border-border px-5 py-4">
              <div>
                <div className="flex items-center gap-2"><h2 className="font-semibold text-text">Add queue item</h2></div>
                <p className="mt-0.5 text-xs text-muted">Describe the work, pick goals, and choose how the plan is created.</p>
              </div>
              <button onClick={onClose} title="Close" className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-muted hover:bg-overlay/10 hover:text-text"><X size={17} /></button>
            </header>

            <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-5 py-4">
              <div className="flex items-start gap-2 rounded-md border border-accent/25 bg-accent/5 px-3 py-2 text-[11px] leading-5 text-accent/90">
                <Sparkles size={13} className="mt-0.5 shrink-0" />
                <span>Mission Control writes the plan and Queue row together. A stale Queue is rejected instead of overwritten.</span>
              </div>

              <label className="block">
                <span className="mb-1 block text-[11px] font-medium uppercase tracking-wide text-muted">Item name</span>
                <input value={name} onChange={event => setName(event.target.value)} placeholder="e.g. Queue drag-and-drop polish" className={inputClass} autoFocus />
              </label>

              <label className="block">
                <span className="mb-1 block text-[11px] font-medium uppercase tracking-wide text-muted">Description</span>
                <textarea value={description} onChange={event => setDescription(event.target.value)} rows={3}
                  placeholder="What should this item accomplish, and how will you know it’s done?" className={`${inputClass} resize-y`} />
              </label>

              <label className="block">
                <span className="mb-1 block text-[11px] font-medium uppercase tracking-wide text-muted">Acceptance criteria · one per line</span>
                <textarea value={criteria} onChange={event => setCriteria(event.target.value)} rows={3}
                  placeholder={'The idle state is visible\nA disabled agent cannot start a run'} className={`${inputClass} resize-y`} />
              </label>

              <div>
                <span className="mb-1.5 flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wide text-muted"><Target size={12} /> Goals</span>
                {goals.length === 0 ? (
                  <p className="rounded-md border border-dashed border-border px-3 py-2.5 text-xs text-muted">No development goals yet — create one on the Goals tab, then link it here.</p>
                ) : (
                  <div className="flex flex-wrap gap-1.5">
                    {goals.map(goal => {
                      const on = selGoals.includes(goal.id)
                      return (
                        <button key={goal.id} type="button" onClick={() => toggleGoal(goal.id)}
                          className={`inline-flex max-w-full items-center gap-1 rounded-full border px-2.5 py-1 text-[11px] transition-colors ${on ? 'border-accent bg-accent/10 text-accent' : 'border-border text-muted hover:border-accent/40 hover:text-text'}`}>
                          {on ? <CheckCircle2 size={11} className="shrink-0" /> : <Target size={11} className="shrink-0" />}
                          <span className="truncate">{goal.title}</span>
                        </button>
                      )
                    })}
                  </div>
                )}
              </div>

              <div>
                <span className="mb-1.5 block text-[11px] font-medium uppercase tracking-wide text-muted">Plan</span>
                <div className="grid grid-cols-2 gap-2">
                  <button type="button" onClick={() => { setPlanMode('tobi'); setPlanFile(null) }}
                    className={`inline-flex items-center justify-center gap-1.5 rounded-md border px-3 py-2.5 text-xs font-medium transition-colors ${planMode === 'tobi' ? 'border-accent bg-accent/10 text-accent' : 'border-border text-text hover:border-accent/40'}`}>
                    <Sparkles size={14} /> Plan by TOBI
                  </button>
                  <button type="button" onClick={() => fileRef.current?.click()}
                    className={`inline-flex items-center justify-center gap-1.5 rounded-md border px-3 py-2.5 text-xs font-medium transition-colors ${planMode === 'upload' ? 'border-accent bg-accent/10 text-accent' : 'border-border text-text hover:border-accent/40'}`}>
                    <Upload size={14} /> Upload .md file
                  </button>
                  <input ref={fileRef} type="file" accept=".md,.markdown,text/markdown" className="hidden"
                    onChange={event => { const file = event.target.files?.[0]; if (file) { setPlanMode('upload'); setPlanFile(file.name); void file.text().then(setPlanMarkdown) } }} />
                </div>
                {planMode === 'tobi' && <p className="mt-1.5 text-[11px] text-accent/80">TOBI will draft the plan from the name, description, and selected goals.</p>}
                {planMode === 'upload' && planFile && <p className="mt-1.5 inline-flex items-center gap-1.5 text-[11px] text-muted"><FileText size={11} /> {planFile}</p>}
              </div>
            </div>

            <footer className="flex items-center justify-between gap-3 border-t border-border px-5 py-3">
              <span className="text-[11px] text-muted">Creates one Draft item. Preflight is still required.</span>
              <div className="flex items-center gap-2">
                <button onClick={onClose} className="inline-flex h-8 items-center rounded-md border border-border px-3 text-xs text-text hover:bg-overlay/5">Cancel</button>
                {/* Creating an item runs plan authoring server-side and is among the slowest
                    actions here. Validation-only disabling let it be fired repeatedly. */}
                <ActionButton disabled={name.trim().length < 3 || description.trim().length < 10 || !criteria.trim()}
                  onAction={() => onSubmit({ title: name, objective: description, acceptance_criteria: criteria.split('\n').map(item => item.trim()).filter(Boolean), goal_ids: selGoals, plan_markdown: planMarkdown })}
                  icon={<Plus size={13} />}
                  className="inline-flex h-8 items-center gap-1.5 rounded-md bg-accent px-3 text-xs font-semibold text-background transition-[filter] hover:brightness-110">
                  Create item
                </ActionButton>
              </div>
            </footer>
          </motion.section>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body,
  )
}

// ── 6. Plan Detail modal ─────────────────────────────────────────────────────
function ReadinessModal({ item, report, busy, allowPrepare, onClose, onConfigureReviewer, onRefresh, onPrepare, onStart }: {
  item: DeveloperQueueItem | null; report: DeveloperReadiness | null; busy: boolean
  allowPrepare: boolean
  onClose: () => void
  onConfigureReviewer: () => void
  onRefresh: (options: { protected_paths_approved?: boolean; selected_agent?: string }) => void
  onPrepare: () => void
  onStart: () => void
}) {
  return createPortal(
    <AnimatePresence>{item && <motion.div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 p-3 backdrop-blur-sm" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose}>
      <motion.section role="dialog" aria-modal="true" onClick={event => event.stopPropagation()} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 8 }} className="w-full max-w-2xl overflow-hidden rounded-lg border border-border bg-surface shadow-2xl">
        <header className="flex items-start justify-between gap-3 border-b border-border px-5 py-4"><div><div className="text-[10px] font-semibold uppercase text-accent">Strict readiness</div><h2 className="mt-1 text-sm font-semibold text-text">#{item.queue_id} {item.title}</h2><p className="mt-1 text-xs text-muted">No run is created until every blocking gate passes.</p></div><button onClick={onClose} title="Close" className="inline-flex h-8 w-8 items-center justify-center rounded-md text-muted hover:bg-overlay/10 hover:text-text"><X size={17} /></button></header>
        <div className="max-h-[65vh] space-y-4 overflow-y-auto px-5 py-4">
          {busy && <div className="flex items-center gap-2 py-8 text-sm text-muted"><Loader2 size={15} className="animate-spin" /> Checking plan, policy, agents, dependencies, and validation...</div>}
          {!busy && report && <>
            <div className={`flex items-center gap-3 rounded-md border px-3 py-3 ${report.ready ? 'border-success/30 bg-success/5' : 'border-warning/30 bg-warning/5'}`}><span className={`flex h-8 w-8 items-center justify-center rounded-md ${report.ready ? 'bg-success/10 text-success' : 'bg-warning/10 text-warning'}`}>{report.ready ? <CheckCircle2 size={16} /> : <Target size={16} />}</span><div><div className="text-xs font-semibold text-text">{report.ready ? 'Ready to start one durable run' : `${report.blockers.length} blocker${report.blockers.length === 1 ? '' : 's'} must be resolved`}</div><div className="mt-0.5 text-[11px] text-muted">{report.selected_agent} · reviewer {report.reviewer}</div></div></div>
            {report.blockers.length > 0 && <div className="space-y-2">{report.blockers.map(issue => <div key={`${issue.code}-${issue.message}`} className="rounded-md border border-danger/25 bg-danger/5 px-3 py-2"><div className="text-[10px] font-semibold uppercase text-danger">{label(issue.code)}</div><div className="mt-1 text-xs leading-5 text-text">{issue.message}</div></div>)}</div>}
            {report.blockers.some(issue => issue.code.startsWith('reviewer_')) && <button onClick={onConfigureReviewer} className="inline-flex h-8 items-center gap-2 rounded-md border border-accent/40 bg-accent/10 px-3 text-xs font-medium text-accent hover:bg-accent/15"><ShieldCheck size={13} /> Configure reviewer</button>}
            {report.blockers.some(issue => issue.code === 'protected_scope_approval') && <ActionButton onAction={() => onRefresh({ protected_paths_approved: true })} icon={<CheckCircle2 size={13} />} className="inline-flex h-8 items-center gap-2 rounded-md border border-warning/40 bg-warning/10 px-3 text-xs font-medium text-warning"> Acknowledge protected scope</ActionButton>}
            {report.alternatives.length > 0 && <div><div className="mb-2 text-[10px] font-semibold uppercase text-muted">Developer agent</div><div className="flex flex-wrap gap-2"><div className="rounded-md border border-accent/45 bg-accent/10 px-3 py-2 text-left"><div className="text-xs font-medium text-text">{label(report.selected_agent)}</div><div className="mt-0.5 text-[10px] text-accent">Selected</div></div>{report.alternatives.map(agent => <ActionButton key={agent.slug} onAction={() => onRefresh({ selected_agent: agent.slug })} className="rounded-md border border-border px-3 py-2 text-left hover:border-accent/40"><div className="text-xs font-medium text-text">{agent.name}</div><div className="mt-0.5 text-[10px] text-muted">{agent.adapter}{agent.model ? ` · ${agent.model}` : ''}</div></ActionButton>)}</div></div>}
            {report.warnings.length > 0 && <details><summary className="cursor-pointer text-xs text-warning">{report.warnings.length} warning{report.warnings.length === 1 ? '' : 's'}</summary><div className="mt-2 space-y-1">{report.warnings.map(issue => <p key={issue.code + issue.message} className="text-[11px] text-muted">{issue.message}</p>)}</div></details>}
          </>}
        </div>
        <footer className="flex items-center justify-between border-t border-border px-5 py-3"><span className="text-[11px] text-muted">Bound to the current plan and policy hash.</span><div className="flex gap-2"><button onClick={onClose} className="h-8 rounded-md border border-border px-3 text-xs text-text">Cancel</button>{allowPrepare && <button disabled={!report?.ready || busy} onClick={onPrepare} className="inline-flex h-8 items-center gap-2 rounded-md border border-warning/40 bg-warning/10 px-3 text-xs font-semibold text-warning disabled:opacity-40"><TestTube2 size={13} /> Prepare test</button>}<button disabled={!report?.ready || busy} onClick={onStart} className="inline-flex h-8 items-center gap-2 rounded-md bg-accent px-3 text-xs font-semibold text-background disabled:opacity-40"><Play size={13} /> Start run</button></div></footer>
      </motion.section>
    </motion.div>}</AnimatePresence>,
    document.body,
  )
}

function PlanModal({ item, onClose }: { item: DeveloperQueueItem | null; onClose: () => void }) {
  const [plan, setPlan] = useState<DeveloperQueuePlan | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [maximized, setMaximized] = useState(false)
  useEffect(() => {
    setPlan(null); setError(null); setMaximized(false)
    if (!item) return
    const controller = new AbortController()
    getDeveloperQueuePlan(item.queue_id, controller.signal)
      .then(setPlan)
      .catch(err => { if (!controller.signal.aborted) setError(err instanceof Error ? err.message : String(err)) })
    return () => controller.abort()
  }, [item])
  return createPortal(
    <AnimatePresence>
      {item && (
        <motion.div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 p-3 backdrop-blur-sm"
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose}>
          <motion.section role="dialog" aria-modal="true" onClick={event => event.stopPropagation()}
            initial={{ opacity: 0, y: 12, scale: 0.985 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 8, scale: 0.985 }}
            transition={{ duration: 0.16 }}
            className={`flex flex-col rounded-lg border border-border bg-surface shadow-2xl transition-[width,height,max-width,max-height] ${maximized ? 'h-[95vh] max-h-[95vh] w-full max-w-[97vw]' : 'max-h-[90vh] w-full max-w-4xl'}`}>
            <header className="flex items-center justify-between gap-3 border-b border-border px-5 py-4">
              <div className="min-w-0">
                <h2 className="truncate font-semibold text-text">#{item.queue_id} {item.title}</h2>
                <p className="mt-0.5 truncate font-mono text-[11px] text-muted">{plan?.plan_path ?? item.plan_path}</p>
              </div>
              <div className="flex shrink-0 items-center gap-1">
                <button onClick={() => setMaximized(current => !current)} title={maximized ? 'Exit full screen' : 'Full screen'}
                  className="inline-flex h-8 w-8 items-center justify-center rounded-md text-muted hover:bg-overlay/10 hover:text-text">
                  {maximized ? <Minimize2 size={16} /> : <Maximize2 size={16} />}
                </button>
                <button onClick={onClose} title="Close" className="inline-flex h-8 w-8 items-center justify-center rounded-md text-muted hover:bg-overlay/10 hover:text-text"><X size={17} /></button>
              </div>
            </header>
            <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
              {error ? (
                <div className="flex items-center gap-2 rounded-md border border-danger/40 bg-danger/10 px-3 py-2 text-xs text-danger"><FileText size={13} /> {error}</div>
              ) : !plan ? (
                <div className="flex items-center justify-center gap-2 py-12 text-sm text-muted"><Loader2 size={15} className="animate-spin" /> Loading the plan…</div>
              ) : (
                <div className="tobi-answer max-w-none text-sm leading-relaxed"><MarkdownView content={plan.markdown} /></div>
              )}
            </div>
            {plan && (
              <footer className="flex items-center justify-between border-t border-border px-5 py-3 text-[11px] text-muted">
                <span className="inline-flex items-center gap-1.5"><RotateCcw size={11} /> Plans sync from QUEUE.md; active and completed status comes from Developer</span>
                <span>{(plan.markdown.length / 1024).toFixed(1)} KiB</span>
              </footer>
            )}
          </motion.section>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body,
  )
}

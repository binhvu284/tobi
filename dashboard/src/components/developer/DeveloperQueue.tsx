// Queue tab (#18 UI continuation): Main Thread → Next slot → drag-ordered
// priority list, with Completed and Plan Detail modals. Ordering persists via
// POST /api/developer/queue/order; auto mode promotes Next → Main server-side.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { AnimatePresence, motion } from 'framer-motion'
import {
  Archive, ArrowUpFromLine, CheckCircle2, ChevronRight, FileText, GripVertical,
  Loader2, Play, RotateCcw, Search, Trash2, X, Zap,
} from 'lucide-react'
import {
  getDeveloperQueuePlan, removeDeveloperQueueItem, restoreDeveloperQueueItem,
  setDeveloperQueueOrder, type DeveloperQueueItem, type DeveloperQueuePlan,
  type DeveloperQueueState, type DeveloperWorkflow,
} from '../../api'
import { useToast } from '../../context/ToastProvider'
import MarkdownView from '../chat/MarkdownView'

function label(value: string) {
  return value.replace(/_/g, ' ').replace(/\b\w/g, char => char.toUpperCase())
}

function deps(item: DeveloperQueueItem): number[] {
  try { return JSON.parse(item.dependencies_json) as number[] } catch { return [] }
}

/** One-line item card used in the Next slot and the priority list. */
function ItemCard({ item, badge, draggable, busy, onDragStart, onDragEnd, onOpen, onStart }: {
  item: DeveloperQueueItem; badge: React.ReactNode; draggable: boolean; busy: boolean
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
          className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-muted opacity-0 transition-opacity hover:bg-accent/15 hover:text-accent group-hover:opacity-100 disabled:opacity-30">
          <Play size={13} />
        </button>
      )}
    </div>
  )
}

export default function QueueBoard({ state, active, busy, autoQueue, autoQueueBusy, onAutoQueue, onStart, onOpenProcess, onState }: {
  state: DeveloperQueueState
  active: DeveloperWorkflow | null
  busy: boolean
  autoQueue: boolean
  autoQueueBusy: boolean
  onAutoQueue: (enabled: boolean) => void
  onStart: (queueId: number) => void
  onOpenProcess: () => void
  onState: (next: DeveloperQueueState) => void
}) {
  const { toast } = useToast()
  const [saving, setSaving] = useState(false)
  const [draggingId, setDraggingId] = useState<number | null>(null)
  const [overSlot, setOverSlot] = useState<'next' | number | null>(null)
  const [completedOpen, setCompletedOpen] = useState(false)
  const [planFor, setPlanFor] = useState<DeveloperQueueItem | null>(null)
  const suppressClick = useRef(false)

  const byId = useMemo(() => new Map(state.items.map(item => [item.queue_id, item])), [state.items])
  const nextItem = state.next_queue_id != null ? byId.get(state.next_queue_id) ?? null : null
  const completed = useMemo(() => state.items.filter(item => item.status === 'completed'), [state.items])

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
              <button disabled={busy} onClick={() => onStart(startTarget.queue_id)}
                className="inline-flex h-8 items-center gap-1.5 rounded-md bg-accent px-3 text-xs font-medium text-background disabled:opacity-40">
                {busy ? <Loader2 size={13} className="animate-spin" /> : <Play size={13} />} Start #{startTarget.queue_id}
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
          <button disabled={autoQueueBusy} onClick={() => onAutoQueue(!autoQueue)} title="When on, the Next item starts automatically once the main thread is free"
            className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[10px] font-medium transition-colors disabled:opacity-50 ${autoQueue ? 'border-success/40 bg-success/10 text-success' : 'border-border text-muted hover:text-text'}`}>
            {autoQueueBusy ? <Loader2 size={10} className="animate-spin" /> : <Zap size={10} />} Auto {autoQueue ? 'on' : 'off'}
          </button>
        </div>
        {nextItem ? (
          <ItemCard item={nextItem} draggable busy={busy}
            badge={<span className="shrink-0 rounded bg-accent/15 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-accent">Next</span>}
            onDragStart={dragStart(nextItem.queue_id)} onDragEnd={dragEnd}
            onOpen={() => openPlan(nextItem)} onStart={() => onStart(nextItem.queue_id)} />
        ) : (
          <p className="py-1 text-xs text-muted">Drag an item here to stage it. {autoQueue ? 'Auto mode will promote it when the main thread frees up.' : 'Turn Auto on to promote it automatically.'}</p>
        )}
      </section>

      {/* ── 3. Priority list ───────────────────────────────────────────────── */}
      <section>
        <div className="mb-2 flex items-center justify-between">
          <div className="text-[10px] font-semibold uppercase tracking-wide text-muted">Priority queue · {priorityList.length}</div>
          <button onClick={() => setCompletedOpen(true)}
            className="inline-flex items-center gap-1.5 rounded-md border border-border px-2 py-1 text-[11px] text-muted hover:text-text">
            <Archive size={12} /> Completed · {completed.length}
          </button>
        </div>
        {priorityList.length === 0 ? (
          <p className="rounded-lg border border-border bg-surface/40 px-4 py-6 text-center text-xs text-muted">Every planned item is staged or running.</p>
        ) : (
          <div className="space-y-1.5">
            {priorityList.map((item, index) => (
              <div key={item.queue_id}
                onDragOver={event => { event.preventDefault(); setOverSlot(index) }}
                onDragLeave={() => setOverSlot(current => (current === index ? null : current))}
                onDrop={dropOnList(index)}
                className={`rounded-md transition-shadow ${overSlot === index ? 'ring-1 ring-accent/60' : ''} ${draggingId === item.queue_id ? 'opacity-40' : ''}`}>
                <ItemCard item={item} draggable busy={busy}
                  badge={<span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-overlay/10 text-[10px] font-semibold text-muted">{index + 1}</span>}
                  onDragStart={dragStart(item.queue_id)} onDragEnd={dragEnd}
                  onOpen={() => openPlan(item)} onStart={() => onStart(item.queue_id)} />
              </div>
            ))}
            {/* tail drop zone: drop after the last card */}
            <div onDragOver={event => { event.preventDefault(); setOverSlot(priorityList.length) }}
              onDragLeave={() => setOverSlot(current => (current === priorityList.length ? null : current))}
              onDrop={dropOnList(priorityList.length)}
              className={`h-6 rounded-md border border-dashed transition-colors ${overSlot === priorityList.length ? 'border-accent bg-accent/5' : 'border-transparent'}`} />
          </div>
        )}
      </section>

      <CompletedModal open={completedOpen} onClose={() => { setCompletedOpen(false); setConfirmRemove(null) }}
        items={completed} rowBusy={rowBusy} confirmRemove={confirmRemove}
        onOpenPlan={item => setPlanFor(item)} onRestore={restore}
        onAskRemove={setConfirmRemove} onRemove={remove} />
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
              <div><h2 className="font-semibold text-text">Completed items</h2><p className="mt-0.5 text-xs text-muted">Push an item back into the queue, or remove it from the list.</p></div>
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
                <p className="py-8 text-center text-xs text-muted">{items.length === 0 ? 'Nothing is completed yet.' : 'No completed item matches the search.'}</p>
              ) : filtered.map(item => (
                <div key={item.queue_id} className="flex items-center gap-2.5 border-b border-border/60 py-2.5 last:border-b-0">
                  <CheckCircle2 size={14} className="shrink-0 text-success" />
                  <button onClick={() => onOpenPlan(item)} className="min-w-0 flex-1 text-left">
                    <span className="text-sm font-medium text-text">#{item.queue_id} {item.title}</span>
                    <span className="ml-2 hidden text-[11px] text-muted sm:inline">{item.queue_status ?? ''}</span>
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

// ── 5. Plan Detail modal ─────────────────────────────────────────────────────
function PlanModal({ item, onClose }: { item: DeveloperQueueItem | null; onClose: () => void }) {
  const [plan, setPlan] = useState<DeveloperQueuePlan | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    setPlan(null); setError(null)
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
            className="flex max-h-[90vh] w-full max-w-4xl flex-col rounded-lg border border-border bg-surface shadow-2xl">
            <header className="flex items-center justify-between gap-3 border-b border-border px-5 py-4">
              <div className="min-w-0">
                <h2 className="truncate font-semibold text-text">#{item.queue_id} {item.title}</h2>
                <p className="mt-0.5 truncate font-mono text-[11px] text-muted">{plan?.plan_path ?? item.plan_path}</p>
              </div>
              <button onClick={onClose} title="Close" className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-muted hover:bg-overlay/10 hover:text-text"><X size={17} /></button>
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
                <span className="inline-flex items-center gap-1.5"><RotateCcw size={11} /> Synced from QUEUE.md</span>
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

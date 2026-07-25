// Extracted from BrainV2.tsx (pre-#21 refactor) — verbatim move.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Brain as BrainIcon, Lock, Unlock, RefreshCw, Upload, Sparkles, ArrowLeft,
  ThumbsUp, ThumbsDown, XCircle, Trash2, Archive, CheckCircle2, ChevronDown,
  ChevronRight, Loader2, ShieldAlert, Search, Database, GitMerge, Eye, Play,
  X, Filter, CheckSquare, Square, Plus, CalendarClock, TrendingUp, ArrowDownAZ, Eraser, Pencil,
} from 'lucide-react'
import {
  type V2Memory, type V2Stats, type V2JobStatus, type V2Candidate,
  type V2MigrationStatus, type V2MigrationItem, type V2RecallItem,
  type V2Influence, type V2CleanupProposal,
  v2Stats, v2Profile, v2Memories, v2SetStatus, v2EditMemory, v2Feedback, v2Influence,
  v2Purge, v2Recall, v2Remember, v2ImportCreate, v2ImportCandidates, v2ImportCommand, v2ImportStatus,
  v2ImportDecide, v2MigrationCreate, v2MigrationItems, v2MigrationCommand,
  v2MigrationDecide, v2CleanupPreview, v2CleanupApply,
} from '../../api.brainV2'
import { useToast } from '../../context/ToastProvider'
import { Badge, errMsg, statusTone } from './parts'


// ── migration tab ─────────────────────────────────────────────────────────────
export function MigrationTab() {
  const { toast } = useToast()
  const [run, setRun] = useState<V2MigrationStatus | null>(null)
  const [items, setItems] = useState<V2MigrationItem[]>([])
  const [group, setGroup] = useState<string>('all')
  const [busy, setBusy] = useState(false)

  const refresh = useCallback(async (id: number) => {
    setItems(await v2MigrationItems(id))
  }, [])

  const start = useCallback(async () => {
    setBusy(true)
    try {
      const r = await v2MigrationCreate()
      const done = await v2MigrationCommand(r.id, 'run')
      setRun(done)
      await refresh(r.id)
      toast({ kind: 'success', title: 'Preview complete — review the grouped proposals' })
    } catch (e) { toast({ kind: 'error', title: errMsg(e) }) }
    finally { setBusy(false) }
  }, [refresh, toast])

  const apply = useCallback(async () => {
    if (!run) return
    setBusy(true)
    try {
      const st = await v2MigrationCommand(run.id, 'apply')
      setRun(st)
      await refresh(run.id)
      toast({ kind: 'success', title: `Applied ${st.applied_now ?? st.applied} approved items — legacy rows untouched` })
    } catch (e) { toast({ kind: 'error', title: errMsg(e) }) }
    finally { setBusy(false) }
  }, [run, refresh, toast])

  const decide = useCallback(async (approve: boolean, payload: { ids?: number[]; group?: string }) => {
    if (!run) return
    try { await v2MigrationDecide(run.id, approve, payload); await refresh(run.id) }
    catch (e) { toast({ kind: 'error', title: errMsg(e) }) }
  }, [run, refresh, toast])

  const visible = useMemo(() => group === 'all' ? items : items.filter(i => i.group === group), [items, group])
  const approvedCount = useMemo(() => items.filter(i => i.approved === true && !i.applied_memory_id).length, [items])
  const triaging = run !== null && (run.status === 'ready' || run.status === 'applied')

  return (
    <div className="space-y-3">
      <div className="rounded-xl border border-border bg-surface/40 p-3.5">
        <p className="text-xs text-muted">Preview reclassifies every legacy memory into V2 groups. Nothing changes until you approve and apply — and legacy memories are <span className="text-text">never modified</span> either way.</p>
        {!run && (
          <button disabled={busy} onClick={start}
            className="mt-2 flex items-center gap-1.5 rounded-lg border border-accent/40 bg-accent/10 px-3 py-1.5 text-xs font-medium text-accent hover:bg-accent/20 disabled:opacity-50">
            {busy ? <Loader2 size={13} className="animate-spin" /> : <Eye size={13} />} Run preview
          </button>
        )}
      </div>
      {run && (
        <>
          <div className="flex flex-wrap items-center gap-2 rounded-xl border border-border bg-surface/40 p-3">
            <Badge tone={run.status === 'applied' ? 'success' : 'accent'}>{run.status}</Badge>
            <span className="text-xs text-muted">{run.scanned}/{run.total_legacy} scanned · {run.applied} applied · {approvedCount} approved waiting</span>
            <div className="ml-auto flex gap-1.5">
              {triaging && (
                <button disabled={busy || approvedCount === 0} onClick={apply}
                  title={approvedCount === 0 ? 'Approve items first — ✓ a row, a group, or Approve all' : undefined}
                  className="rounded-lg border border-success/40 bg-success/10 px-2 py-1 text-[11px] font-medium text-success disabled:opacity-40">
                  Apply approved ({approvedCount})
                </button>
              )}
              <button onClick={() => { setRun(null); setItems([]) }}
                className="rounded-lg border border-border px-2 py-1 text-[11px] text-muted hover:text-text">Close</button>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            {['all', ...Object.keys(run.groups)].map(g => (
              <button key={g} onClick={() => setGroup(g)}
                className={`rounded-full border px-2.5 py-1 text-[11px] ${group === g ? 'border-accent/50 bg-accent/15 text-accent' : 'border-border text-muted hover:text-text'}`}>
                {g}{g !== 'all' && ` (${run.groups[g]})`}
              </button>
            ))}
            {triaging && (
              <span className="ml-auto flex gap-1.5">
                <button onClick={() => decide(true, group === 'all' ? {} : { group })}
                  className="rounded-lg border border-success/40 px-2 py-1 text-[11px] text-success hover:bg-success/10">
                  Approve {group === 'all' ? 'all' : group}
                </button>
                <button onClick={() => decide(false, group === 'all' ? {} : { group })}
                  className="rounded-lg border border-border px-2 py-1 text-[11px] text-muted hover:text-danger">
                  Reject {group === 'all' ? 'all' : group}
                </button>
              </span>
            )}
          </div>
          <div className="space-y-1.5">
            {visible.map(i => (
              <div key={i.id} className="flex items-start gap-2 rounded-xl border border-border bg-surface/40 px-3 py-2">
                <div className="min-w-0 flex-1">
                  {i.error
                    ? <p className="text-xs text-danger">error: {i.error}</p>
                    : <p className="truncate text-xs text-text">{i.sensitive && <ShieldAlert size={11} className="mr-1 inline text-warning" />}{String(i.candidate?.distilled_text ?? '')}</p>}
                  <div className="mt-1 flex gap-1.5">
                    {i.group && <Badge tone="accent">{i.group}</Badge>}
                    {i.proposed_outcome && <Badge tone={statusTone(i.proposed_status || '')}>{i.proposed_outcome}</Badge>}
                    {i.approved !== null && <Badge tone={i.approved ? 'success' : 'danger'}>{i.approved ? 'approved' : 'rejected'}</Badge>}
                    {i.applied_memory_id && <Badge tone="purple">applied #{i.applied_memory_id}</Badge>}
                  </div>
                </div>
                {!i.error && !i.applied_memory_id && triaging && (
                  <div className="flex shrink-0 gap-1">
                    <button onClick={() => decide(true, { ids: [i.id] })}
                      className={`rounded-lg border px-2 py-1 text-[11px] ${i.approved === true ? 'border-success/50 bg-success/15 text-success' : 'border-border text-muted hover:text-success'}`}>✓</button>
                    <button onClick={() => decide(false, { ids: [i.id] })}
                      className={`rounded-lg border px-2 py-1 text-[11px] ${i.approved === false ? 'border-danger/50 bg-danger/15 text-danger' : 'border-border text-muted hover:text-danger'}`}>✗</button>
                  </div>
                )}
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

// ── tell tobi tab (coming soon) ───────────────────────────────────────────────
export function TellTab() {
  return (
    <div className="rounded-2xl border border-dashed border-purple/30 bg-purple/5 px-6 py-12 text-center">
      <div className="mx-auto mb-3 flex h-11 w-11 items-center justify-center rounded-xl border border-purple/30 bg-purple/10 text-purple">
        <Sparkles size={20} />
      </div>
      <h3 className="text-sm font-semibold text-heading">Tell TOBI <span className="ml-1 rounded-full bg-warning/15 px-1.5 py-0.5 text-[10px] font-medium text-warning">coming soon</span></h3>
      <p className="mx-auto mt-2 max-w-md text-xs leading-relaxed text-muted">
        A conversational way to teach TOBI about you — add facts, correct what it got wrong, and set
        rules in plain language, each routed through the same quality gate. It's on the way.
      </p>
      <p className="mx-auto mt-3 max-w-md text-[11px] text-muted">
        For now: use <span className="text-text">+ Add</span> in the Library to remember something, and the
        <span className="text-text"> Semantic</span> toggle there to see what TOBI would recall.
      </p>
    </div>
  )
}

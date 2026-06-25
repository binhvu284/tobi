import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { motion } from 'framer-motion'
import { X, Check, Trash2, Loader2, Inbox, GitBranch } from 'lucide-react'
import {
  type Memory, type Conflict,
  getPendingMemories, acceptPending, rejectPending,
  getConflicts, resolveConflict,
} from '../../api'

export default function ReviewInbox({ onClose, onChange }: { onClose: () => void; onChange: () => void }) {
  const [tab, setTab] = useState<'pending' | 'conflicts'>('pending')
  const [pending, setPending] = useState<Memory[] | null>(null)
  const [conflicts, setConflicts] = useState<Conflict[] | null>(null)
  const [busy, setBusy] = useState<number | null>(null)

  const load = () => {
    getPendingMemories().then(r => setPending(r.items)).catch(() => setPending([]))
    getConflicts().then(r => setConflicts(r.items)).catch(() => setConflicts([]))
  }
  useEffect(load, [])

  const act = async (fn: () => Promise<unknown>, id: number) => {
    setBusy(id); try { await fn(); load(); onChange() } finally { setBusy(null) }
  }

  return createPortal(
    <>
      <div className="fixed inset-0 z-[180] bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div className="pointer-events-none fixed inset-0 z-[181] flex items-center justify-center p-4">
      <motion.div initial={{ opacity: 0, y: 16, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }}
        className="pointer-events-auto flex max-h-[85vh] w-[94vw] max-w-2xl flex-col overflow-hidden rounded-xl border border-border bg-surface shadow-2xl">
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <span className="flex items-center gap-2 text-sm font-semibold text-heading"><Inbox size={15} className="text-accent" /> Review inbox</span>
          <button onClick={onClose} className="text-muted hover:text-text"><X size={16} /></button>
        </div>

        <div className="flex gap-1 border-b border-border px-3 pt-2">
          {(['pending', 'conflicts'] as const).map(t => (
            <button key={t} onClick={() => setTab(t)}
              className={`rounded-t-md px-3 py-1.5 text-xs capitalize ${tab === t ? 'bg-accent/15 text-accent' : 'text-muted hover:text-text'}`}>
              {t} {t === 'pending' ? `(${pending?.length ?? 0})` : `(${conflicts?.length ?? 0})`}
            </button>
          ))}
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto p-4">
          {tab === 'pending' && (
            !pending ? <Loading /> : pending.length === 0 ? <Empty text="Nothing waiting for review." /> :
              <div className="space-y-2">
                {pending.map(m => (
                  <div key={m.id} className="flex items-start gap-2 rounded-lg border border-border bg-bg p-2.5">
                    <div className="min-w-0 flex-1">
                      <div className="text-xs text-text">{m.content}</div>
                      <div className="mt-1 text-[10px] uppercase tracking-wide text-muted">{m.category} · {m.source} · {Math.round(m.confidence * 100)}%</div>
                    </div>
                    <button onClick={() => act(() => acceptPending(m.id), m.id)} disabled={busy === m.id}
                      className="rounded border border-success/40 bg-success/10 p-1.5 text-success hover:bg-success/20" title="Accept"><Check size={13} /></button>
                    <button onClick={() => act(() => rejectPending(m.id), m.id)} disabled={busy === m.id}
                      className="rounded border border-danger/40 bg-danger/10 p-1.5 text-danger hover:bg-danger/20" title="Reject"><Trash2 size={13} /></button>
                  </div>
                ))}
              </div>
          )}

          {tab === 'conflicts' && (
            !conflicts ? <Loading /> : conflicts.length === 0 ? <Empty text="No conflicts to resolve." /> :
              <div className="space-y-2">
                {conflicts.map(c => (
                  <div key={c.id} className="rounded-lg border border-border bg-bg p-2.5">
                    <div className="mb-1.5 flex items-center gap-1 text-[10px] uppercase tracking-wide text-warning"><GitBranch size={11} /> {c.reason}</div>
                    <div className="grid grid-cols-1 gap-1.5 sm:grid-cols-2">
                      <div className="rounded border border-border bg-surface p-2 text-xs">
                        <div className="mb-0.5 text-[10px] uppercase text-muted">Existing</div>
                        <div className="text-text">{c.existing_content || '—'}</div>
                      </div>
                      <div className="rounded border border-accent/30 bg-accent/5 p-2 text-xs">
                        <div className="mb-0.5 text-[10px] uppercase text-accent">New</div>
                        <div className="text-text">{c.candidate_content}</div>
                      </div>
                    </div>
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      <button onClick={() => act(() => resolveConflict(c.id, 'keep_existing'), c.id)} disabled={busy === c.id} className="rounded border border-border px-2 py-1 text-[11px] text-muted hover:text-text">Keep existing</button>
                      <button onClick={() => act(() => resolveConflict(c.id, 'use_candidate'), c.id)} disabled={busy === c.id} className="rounded border border-accent/40 bg-accent/10 px-2 py-1 text-[11px] text-accent">Use new</button>
                      <button onClick={() => act(() => resolveConflict(c.id, 'keep_both'), c.id)} disabled={busy === c.id} className="rounded border border-border px-2 py-1 text-[11px] text-muted hover:text-text">Keep both</button>
                    </div>
                  </div>
                ))}
              </div>
          )}
        </div>
      </motion.div>
      </div>
    </>,
    document.body,
  )
}

function Loading() { return <div className="flex items-center justify-center gap-2 py-10 text-muted"><Loader2 size={16} className="animate-spin" /> Loading…</div> }
function Empty({ text }: { text: string }) { return <div className="py-10 text-center text-sm text-muted">{text}</div> }

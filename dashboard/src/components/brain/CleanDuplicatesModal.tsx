import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { motion } from 'framer-motion'
import { X, Loader2, GitMerge, Sparkles } from 'lucide-react'
import { type DuplicateGroup, getDuplicates, mergeDuplicates } from '../../api.brain'

export default function CleanDuplicatesModal({ onClose, onDone }: { onClose: () => void; onDone: (merged: number) => void }) {
  const [groups, setGroups] = useState<DuplicateGroup[] | null>(null)
  const [keep, setKeep] = useState<Record<number, number>>({}) // groupIndex -> memory id to keep
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    getDuplicates().then(({ groups }) => {
      setGroups(groups)
      const k: Record<number, number> = {}
      groups.forEach((g, i) => { k[i] = g.memories.reduce((a, b) => (b.confidence > a.confidence ? b : a), g.memories[0]).id })
      setKeep(k)
    }).catch(() => setGroups([]))
  }, [])

  const mergeAll = async () => {
    if (!groups) return
    setBusy(true)
    try {
      let total = 0
      for (let i = 0; i < groups.length; i++) {
        const res = await mergeDuplicates(groups[i].ids, keep[i])
        total += res.merged
      }
      onDone(total)
    } finally { setBusy(false) }
  }

  return createPortal(
    <>
      <div className="fixed inset-0 z-[180] bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div className="pointer-events-none fixed inset-0 z-[181] flex items-center justify-center p-4">
      <motion.div initial={{ opacity: 0, y: 16, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }}
        className="pointer-events-auto flex max-h-[85vh] w-[94vw] max-w-2xl flex-col overflow-hidden rounded-xl border border-border bg-surface shadow-2xl">
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <span className="flex items-center gap-2 text-sm font-semibold text-heading"><Sparkles size={15} className="text-accent" /> Clean duplicates</span>
          <button onClick={onClose} className="text-muted hover:text-text"><X size={16} /></button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto p-4">
          {!groups && <div className="flex items-center justify-center gap-2 py-12 text-muted"><Loader2 size={18} className="animate-spin" /> Scanning…</div>}
          {groups && groups.length === 0 && <div className="py-12 text-center text-sm text-muted">No duplicate memories found. 🎉</div>}
          {groups && groups.length > 0 && (
            <div className="space-y-3">
              <p className="text-xs text-muted">Pick which memory to keep in each group. The rest will be superseded (kept in history).</p>
              {groups.map((g, i) => (
                <div key={i} className="rounded-lg border border-border bg-bg p-2.5">
                  <div className="mb-1.5 text-[10px] uppercase tracking-wider text-muted">Group {i + 1} · {g.memories.length} similar</div>
                  <div className="space-y-1.5">
                    {g.memories.map(mem => (
                      <label key={mem.id} className={`flex cursor-pointer items-start gap-2 rounded border px-2 py-1.5 text-xs ${keep[i] === mem.id ? 'border-accent/50 bg-accent/10 text-text' : 'border-border text-muted'}`}>
                        <input type="radio" name={`g${i}`} checked={keep[i] === mem.id} onChange={() => setKeep(k => ({ ...k, [i]: mem.id }))} className="mt-0.5" />
                        <span className="flex-1">{mem.content}<span className="ml-1 text-[10px] text-muted">({Math.round(mem.confidence * 100)}%)</span></span>
                      </label>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {groups && groups.length > 0 && (
          <div className="flex items-center justify-end border-t border-border px-4 py-3">
            <button onClick={mergeAll} disabled={busy}
              className="flex items-center gap-1.5 rounded-md border border-accent/50 bg-accent/15 px-3 py-1.5 text-xs font-medium text-accent hover:bg-accent/25 disabled:opacity-50">
              {busy ? <Loader2 size={13} className="animate-spin" /> : <GitMerge size={13} />} Merge {groups.length} {groups.length === 1 ? 'group' : 'groups'}
            </button>
          </div>
        )}
      </motion.div>
      </div>
    </>,
    document.body,
  )
}

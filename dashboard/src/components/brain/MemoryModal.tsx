import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { motion, useDragControls } from 'framer-motion'
import { X, GripHorizontal, Trash2, CheckCircle2, History, Save } from 'lucide-react'
import { type Memory, type MemoryCategory, type MemoryVersion, patchMemory, deleteMemory, confirmMemory, getMemoryVersions, createMemory } from '../../api.brain'

type Props = {
  memory: Memory | 'new'
  categories: MemoryCategory[]
  onClose: () => void
  onSaved: () => void
}

export default function MemoryModal({ memory, categories, onClose, onSaved }: Props) {
  const isNew = memory === 'new'
  const m = isNew ? null : (memory as Memory)
  const [content, setContent] = useState(m?.content ?? '')
  const [category, setCategory] = useState(m?.category ?? (categories[0]?.id ?? 'identity'))
  const [confidence, setConfidence] = useState(m?.confidence ?? 0.7)
  const [busy, setBusy] = useState(false)
  const [versions, setVersions] = useState<MemoryVersion[] | null>(null)
  const drag = useDragControls()

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const cat = categories.find(c => c.id === category)
  const accent = cat?.color ?? '#a78bfa'

  const save = async () => {
    if (!content.trim()) return
    setBusy(true)
    try {
      if (isNew) await createMemory({ content: content.trim(), category, confidence })
      else await patchMemory(m!.id, { content: content.trim(), category, confidence })
      onSaved(); onClose()
    } finally { setBusy(false) }
  }
  const remove = async () => { if (!m) return; setBusy(true); try { await deleteMemory(m.id); onSaved(); onClose() } finally { setBusy(false) } }
  const confirm = async () => { if (!m) return; setBusy(true); try { await confirmMemory(m.id); onSaved() } finally { setBusy(false) } }
  const loadVersions = async () => { if (!m) return; setVersions((await getMemoryVersions(m.id)).versions) }

  return createPortal(
    <>
      <div className="fixed inset-0 z-[180] bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div className="pointer-events-none fixed inset-0 z-[181] flex items-center justify-center p-4">
      <motion.div
        drag dragControls={drag} dragListener={false} dragMomentum={false}
        initial={{ opacity: 0, scale: 0.97 }} animate={{ opacity: 1, scale: 1 }}
        className="pointer-events-auto w-[92vw] max-w-lg overflow-hidden rounded-xl border bg-surface shadow-2xl"
        style={{ borderColor: `${accent}55`, boxShadow: `0 0 40px ${accent}22` }}
      >
        <div onPointerDown={(e) => drag.start(e)}
          className="flex cursor-grab items-center justify-between border-b border-border px-4 py-2.5 active:cursor-grabbing"
          style={{ background: `${accent}14` }}>
          <span className="flex items-center gap-2 text-xs font-semibold tracking-wide text-heading">
            <GripHorizontal size={14} className="text-muted" /> {isNew ? 'New memory' : 'Memory'}
          </span>
          <button onClick={onClose} className="text-muted hover:text-text"><X size={15} /></button>
        </div>

        <div className="space-y-3 p-4">
          <textarea value={content} onChange={e => setContent(e.target.value)} rows={4} autoFocus
            placeholder="What should TOBI remember about you?"
            className="w-full resize-none rounded-lg border border-border bg-bg px-3 py-2 text-sm text-text outline-none focus:border-accent/50" />

          <div className="flex flex-wrap items-center gap-3">
            <select value={category} onChange={e => setCategory(e.target.value)}
              className="rounded-md border border-border bg-bg px-2 py-1.5 text-xs text-text outline-none">
              {categories.map(c => <option key={c.id} value={c.id}>{c.label}</option>)}
            </select>
            <label className="flex items-center gap-2 text-[11px] text-muted">
              confidence
              <input type="range" min={0} max={1} step={0.05} value={confidence}
                onChange={e => setConfidence(parseFloat(e.target.value))} />
              <span className="w-8 font-mono text-text">{Math.round(confidence * 100)}%</span>
            </label>
          </div>

          {m && (
            <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted">
              <span className="rounded border border-border px-1.5 py-0.5 uppercase tracking-wide">{m.source}</span>
              <span className="rounded border border-border px-1.5 py-0.5">{m.status}</span>
              {m.stale && <span className="rounded border border-warning/40 bg-warning/10 px-1.5 py-0.5 text-warning">stale</span>}
              <span>updated {new Date(m.updated_at).toLocaleDateString()}</span>
            </div>
          )}

          {versions && (
            <div className="max-h-40 space-y-1 overflow-y-auto rounded-lg border border-border bg-bg p-2">
              {versions.length === 0 ? <div className="text-[11px] text-muted">No history</div> :
                versions.map(v => (
                  <div key={v.id} className="text-[11px] text-muted">
                    <span className="font-mono text-accent">{v.change_kind}</span> · {v.changed_by} · {new Date(v.created_at).toLocaleString()}
                    <div className="truncate text-text">{v.content}</div>
                  </div>
                ))}
            </div>
          )}
        </div>

        <div className="flex items-center justify-between border-t border-border px-4 py-2.5">
          <div className="flex items-center gap-2">
            {m && <button onClick={remove} disabled={busy} className="flex items-center gap-1 rounded-md border border-danger/40 bg-danger/10 px-2 py-1.5 text-xs text-danger hover:bg-danger/20"><Trash2 size={12} /> Delete</button>}
            {m && <button onClick={confirm} disabled={busy} className="flex items-center gap-1 rounded-md border border-success/40 bg-success/10 px-2 py-1.5 text-xs text-success hover:bg-success/20"><CheckCircle2 size={12} /> Confirm</button>}
            {m && <button onClick={loadVersions} className="flex items-center gap-1 rounded-md border border-border px-2 py-1.5 text-xs text-muted hover:text-text"><History size={12} /> History</button>}
          </div>
          <button onClick={save} disabled={busy || !content.trim()}
            className="flex items-center gap-1.5 rounded-md border border-accent/50 bg-accent/15 px-3 py-1.5 text-xs font-medium text-accent hover:bg-accent/25 disabled:opacity-50">
            <Save size={13} /> {isNew ? 'Create' : 'Save'}
          </button>
        </div>
      </motion.div>
      </div>
    </>,
    document.body,
  )
}

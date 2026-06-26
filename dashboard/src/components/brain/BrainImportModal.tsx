import { useState } from 'react'
import { createPortal } from 'react-dom'
import { motion } from 'framer-motion'
import { X, Upload, Check, Loader2, GitMerge, CheckCheck, FileText } from 'lucide-react'
import { type ImportCandidate, type MemoryCategory, parseImport, commitImport } from '../../api'
import NeuralIngestion from './NeuralIngestion'
import { Stagger, StaggerItem } from '../motion'

type Props = { categories: MemoryCategory[]; onClose: () => void; onDone: (saved: number, merged: number) => void }
type Row = ImportCandidate & { _id: number; _merge: boolean }

function confTone(c: number) {
  if (c >= 0.8) return '#3fb950'
  if (c >= 0.6) return '#d29922'
  return '#f85149'
}

export default function BrainImportModal({ categories, onClose, onDone }: Props) {
  const [filename, setFilename] = useState('import')
  const [sourceType, setSourceType] = useState('md')
  const [rows, setRows] = useState<Row[] | null>(null)
  const [ingesting, setIngesting] = useState(false)
  const [parsedCount, setParsedCount] = useState<number | null>(null)
  const [busyId, setBusyId] = useState<number | null>(null)
  const [savingAll, setSavingAll] = useState(false)
  const [error, setError] = useState('')
  const [saved, setSaved] = useState(0)
  const [merged, setMerged] = useState(0)
  const [rejected, setRejected] = useState(0)

  const onFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setError(''); setRows(null); setParsedCount(null); setIngesting(true)
    setSaved(0); setMerged(0); setRejected(0)
    try {
      const text = await file.text()
      setFilename(file.name)
      setSourceType(file.name.endsWith('.json') ? 'json' : 'md')
      const { items } = await parseImport(file.name, text)
      setRows(items.map((it, i) => ({ ...it, _id: i, _merge: false })))
      if (items.length === 0) { setError('No memories could be extracted from that file.'); setIngesting(false) }
      else setParsedCount(items.length) // → NeuralIngestion plays its completion, then reveals the cards
    } catch (err) {
      setError((err as Error).message || 'Failed to parse file'); setIngesting(false)
    }
  }

  const update = (id: number, patch: Partial<Row>) =>
    setRows(rs => rs!.map(r => r._id === id ? { ...r, ...patch } : r))

  const toCandidate = (r: Row): ImportCandidate => ({
    content: r.content, category: r.category, confidence: r.confidence,
    ...(r._merge && r.merge_into ? { merge_into: r.merge_into, merge_score: r.merge_score } : {}),
  })

  const accept = async (r: Row) => {
    setBusyId(r._id)
    try {
      const res = await commitImport(filename, sourceType, [toCandidate(r)])
      setSaved(s => s + res.saved); setMerged(m => m + res.merged)
      setRows(rs => rs!.filter(x => x._id !== r._id))
    } catch (err) {
      setError((err as Error).message || 'Failed to save card')
    } finally { setBusyId(null) }
  }

  const reject = (r: Row) => {
    setRejected(n => n + 1)
    setRows(rs => rs!.filter(x => x._id !== r._id))
  }

  const acceptAll = async () => {
    if (!rows || rows.length === 0) return
    setSavingAll(true)
    try {
      const res = await commitImport(filename, sourceType, rows.map(toCandidate))
      setSaved(s => s + res.saved); setMerged(m => m + res.merged)
      setRows([])
    } catch (err) {
      setError((err as Error).message || 'Failed to save cards')
    } finally { setSavingAll(false) }
  }

  const finish = () => {
    if (saved + merged > 0) onDone(saved, merged)
    else onClose()
  }

  const remaining = rows?.length ?? 0
  const done = rows !== null && remaining === 0 && (saved + merged + rejected) > 0

  return createPortal(
    <>
      <div className="fixed inset-0 z-[180] bg-black/60 backdrop-blur-sm" onClick={finish} />
      <div className="pointer-events-none fixed inset-0 z-[181] flex items-center justify-center p-4">
        <motion.div initial={{ opacity: 0, y: 16, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }}
          className="pointer-events-auto flex max-h-[85vh] w-[94vw] max-w-2xl flex-col overflow-hidden rounded-xl border border-border bg-surface shadow-2xl">
          <div className="flex items-center justify-between border-b border-border px-4 py-3">
            <span className="flex items-center gap-2 text-sm font-semibold text-heading">
              <Upload size={15} className="text-accent" /> Import memories from .md / .json
            </span>
            <button onClick={finish} className="text-muted hover:text-text"><X size={16} /></button>
          </div>

          {/* progress bar while reviewing */}
          {rows && (saved + merged + rejected + remaining) > 0 && (
            <div className="flex items-center gap-3 border-b border-border bg-bg/50 px-4 py-2 text-[11px] text-muted">
              <span className="flex items-center gap-1 text-success"><Check size={11} /> {saved} kept</span>
              {merged > 0 && <span className="flex items-center gap-1 text-purple"><GitMerge size={11} /> {merged} merged</span>}
              <span className="flex items-center gap-1 text-danger"><X size={11} /> {rejected} rejected</span>
              <span className="ml-auto">{remaining} to review</span>
            </div>
          )}

          <div className="min-h-0 flex-1 overflow-y-auto p-4">
            {ingesting && (
              <NeuralIngestion filename={filename} result={parsedCount} onReveal={() => setIngesting(false)} />
            )}
            {!ingesting && !rows && (
              <label className="flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-border bg-bg py-12 text-muted hover:border-accent/50 hover:text-text">
                <Upload size={22} />
                <span className="text-sm">Choose a .md or .json file</span>
                <span className="text-[11px]">TOBI rewrites it into clean, categorized memory cards you review one by one</span>
                <input type="file" accept=".md,.json,.txt" className="hidden" onChange={onFile} />
              </label>
            )}
            {!ingesting && error && <div className="mt-3 rounded border border-danger/40 bg-danger/10 px-3 py-2 text-xs text-danger">{error}</div>}

            {!ingesting && done && (
              <div className="flex flex-col items-center justify-center gap-2 py-12 text-center">
                <div className="flex h-12 w-12 items-center justify-center rounded-full border border-success/40 bg-success/10 text-success"><CheckCheck size={22} /></div>
                <div className="text-sm font-medium text-heading">Import complete</div>
                <div className="text-xs text-muted">{saved} kept{merged ? `, ${merged} merged` : ''}, {rejected} rejected</div>
              </div>
            )}

            {!ingesting && rows && rows.length > 0 && (
              <Stagger className="space-y-2">
                {rows.map(r => {
                  const cat = categories.find(c => c.id === r.category)
                  const color = cat?.color ?? '#a78bfa'
                  const conf = r.confidence ?? 0.6
                  return (
                    <StaggerItem key={r._id} className="rounded-lg border border-border bg-bg p-2.5">
                      <div className="flex items-start gap-2">
                        <span title="From imported file" className="mt-0.5 text-muted"><FileText size={13} /></span>
                        <textarea value={r.content} onChange={e => update(r._id, { content: e.target.value })} rows={2}
                          className="w-full resize-none rounded border border-border bg-surface px-2 py-1.5 text-xs text-text outline-none focus:border-accent/50" />
                      </div>
                      <div className="mt-2 flex flex-wrap items-center gap-2">
                        <select value={r.category} onChange={e => update(r._id, { category: e.target.value })}
                          className="rounded border bg-surface px-1.5 py-1 text-[11px] text-text outline-none"
                          style={{ borderColor: `${color}55` }}>
                          {categories.map(c => <option key={c.id} value={c.id}>{c.label}</option>)}
                        </select>
                        {/* confidence bar */}
                        <div className="flex items-center gap-1.5" title="Confidence">
                          <div className="h-1.5 w-16 overflow-hidden rounded-full bg-border">
                            <div className="h-full rounded-full" style={{ width: `${Math.round(conf * 100)}%`, background: confTone(conf) }} />
                          </div>
                          <span className="w-8 font-mono text-[10px] text-muted">{Math.round(conf * 100)}%</span>
                        </div>
                        {r.merge_into && (
                          <button onClick={() => update(r._id, { _merge: !r._merge })}
                            title={r._merge ? 'Will merge into an existing memory' : 'Click to merge into the matching existing memory'}
                            className={`flex items-center gap-1 rounded border px-1.5 py-0.5 text-[10px] ${r._merge ? 'border-purple/60 bg-purple/15 text-purple' : 'border-border text-muted hover:text-text'}`}>
                            <GitMerge size={10} /> {r._merge ? 'merging' : 'merge?'}
                          </button>
                        )}
                        <div className="ml-auto flex items-center gap-1.5">
                          <button onClick={() => reject(r)} disabled={busyId === r._id}
                            className="flex items-center gap-1 rounded border border-border px-2 py-1 text-[11px] text-muted hover:border-danger/40 hover:text-danger disabled:opacity-50">
                            <X size={11} /> Reject
                          </button>
                          <button onClick={() => accept(r)} disabled={busyId === r._id}
                            className="flex items-center gap-1 rounded border border-success/40 bg-success/10 px-2 py-1 text-[11px] text-success hover:bg-success/20 disabled:opacity-50">
                            {busyId === r._id ? <Loader2 size={11} className="animate-spin" /> : <Check size={11} />} Accept
                          </button>
                        </div>
                      </div>
                    </StaggerItem>
                  )
                })}
              </Stagger>
            )}
          </div>

          {rows && rows.length > 0 && (
            <div className="flex items-center justify-between border-t border-border px-4 py-3">
              <button onClick={() => { setRejected(n => n + rows.length); setRows([]) }} className="text-xs text-muted hover:text-danger">Reject all</button>
              <button onClick={acceptAll} disabled={savingAll}
                className="flex items-center gap-1.5 rounded-md border border-accent/50 bg-accent/15 px-3 py-1.5 text-xs font-medium text-accent hover:bg-accent/25 disabled:opacity-50">
                {savingAll ? <Loader2 size={13} className="animate-spin" /> : <CheckCheck size={13} />} Accept all {remaining}
              </button>
            </div>
          )}

          {done && (
            <div className="flex items-center justify-end border-t border-border px-4 py-3">
              <button onClick={finish}
                className="flex items-center gap-1.5 rounded-md border border-accent/50 bg-accent/15 px-3 py-1.5 text-xs font-medium text-accent hover:bg-accent/25">
                <Check size={13} /> Done
              </button>
            </div>
          )}
        </motion.div>
      </div>
    </>,
    document.body,
  )
}

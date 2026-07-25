// Resource create/confirm/add modals, extracted from ResourcesTab.tsx.
import { useRef, useState } from 'react'
import { motion } from 'framer-motion'
import { FolderPlus, X, Trash2, Loader2, Link2, Upload, Plus } from 'lucide-react'
import type { PMResource, PMFolder } from '../../api.pm'
import { fmtBytes } from './shared'
import { RTypeIcon, ytId } from './resourceHelpers'

export function FolderNameModal({ title = 'New folder', cta = 'Create', initial = '', onClose, onSubmit }: {
  title?: string; cta?: string; initial?: string
  onClose: () => void; onSubmit: (name: string) => Promise<void>
}) {
  const [name, setName] = useState(initial)
  const [busy, setBusy] = useState(false)
  const submit = async () => {
    if (!name.trim() || busy) return
    setBusy(true)
    try { await onSubmit(name.trim()) } finally { setBusy(false) }
  }
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm" onClick={onClose}>
      <motion.div initial={{ opacity: 0, scale: 0.95, y: 8 }} animate={{ opacity: 1, scale: 1, y: 0 }} exit={{ opacity: 0, scale: 0.95 }}
        onClick={e => e.stopPropagation()} className="w-full max-w-sm rounded-2xl border border-border bg-surface p-5 shadow-2xl">
        <div className="mb-3 flex items-center justify-between">
          <div className="flex items-center gap-2 text-sm font-semibold text-heading"><FolderPlus size={15} className="text-accent" /> {title}</div>
          <button onClick={onClose} className="text-muted hover:text-text"><X size={16} /></button>
        </div>
        <input autoFocus value={name} onChange={e => setName(e.target.value)} onFocus={e => e.target.select()}
          onKeyDown={e => { if (e.key === 'Enter') submit(); if (e.key === 'Escape') onClose() }}
          placeholder="Folder name"
          className="mb-3 w-full rounded-lg border border-border bg-panel px-3 py-2 text-sm text-text outline-none focus:border-accent" />
        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="rounded-lg px-3 py-1.5 text-sm text-muted hover:bg-overlay/5 hover:text-text">Cancel</button>
          <button disabled={busy || !name.trim()} onClick={submit}
            className="flex items-center gap-1.5 rounded-lg bg-accent px-3 py-1.5 text-sm font-medium text-white hover:bg-accent/90 disabled:opacity-50">
            {busy ? <Loader2 size={13} className="animate-spin" /> : <FolderPlus size={13} />} {cta}
          </button>
        </div>
      </motion.div>
    </div>
  )
}

export function ConfirmFolderDelete({ folder, onClose, onConfirm }: { folder: PMFolder; onClose: () => void; onConfirm: () => Promise<void> }) {
  const [busy, setBusy] = useState(false)
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm" onClick={onClose}>
      <motion.div initial={{ opacity: 0, scale: 0.95, y: 8 }} animate={{ opacity: 1, scale: 1, y: 0 }} exit={{ opacity: 0, scale: 0.95 }}
        onClick={e => e.stopPropagation()} className="w-full max-w-sm rounded-2xl border border-border bg-surface p-5 shadow-2xl">
        <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-heading">
          <Trash2 size={15} className="text-danger" /> Delete folder
        </div>
        <p className="mb-4 text-[13px] leading-relaxed text-muted">
          Delete <span className="font-medium text-text">"{folder.name}"</span>?
          Files inside move to the root — nothing is deleted.
        </p>
        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="rounded-lg px-3 py-1.5 text-sm text-muted hover:bg-overlay/5 hover:text-text">Cancel</button>
          <button disabled={busy}
            onClick={async () => { setBusy(true); try { await onConfirm() } finally { setBusy(false) } }}
            className="flex items-center gap-1.5 rounded-lg bg-danger px-3 py-1.5 text-sm font-medium text-white hover:bg-danger/90 disabled:opacity-50">
            {busy ? <Loader2 size={13} className="animate-spin" /> : <Trash2 size={13} />} Delete
          </button>
        </div>
      </motion.div>
    </div>
  )
}

export function ConfirmResourceDelete({ resource, onClose, onConfirm }: {
  resource: PMResource; onClose: () => void; onConfirm: () => Promise<void>
}) {
  const [busy, setBusy] = useState(false)
  const vid = resource.source === 'youtube' ? ytId(resource.url || '') : null

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm" onClick={onClose}>
      <motion.div initial={{ opacity: 0, scale: 0.95, y: 8 }} animate={{ opacity: 1, scale: 1, y: 0 }} exit={{ opacity: 0, scale: 0.95 }}
        onClick={e => e.stopPropagation()} className="w-full max-w-sm rounded-2xl border border-border bg-surface p-5 shadow-2xl">
        <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-heading">
          <Trash2 size={15} className="text-danger" /> Delete resource
        </div>
        {/* Preview of what's being deleted */}
        <div className="mb-4 flex items-center gap-3 rounded-xl border border-border bg-panel p-3">
          {vid ? (
            <img src={`https://i.ytimg.com/vi/${vid}/mqdefault.jpg`} alt="" loading="lazy"
              className="h-12 w-20 shrink-0 rounded-lg object-cover" />
          ) : (
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-lg bg-overlay/5">
              <RTypeIcon rtype={resource.rtype} size={22} />
            </div>
          )}
          <div className="min-w-0 flex-1">
            <div className="truncate text-[13px] font-medium text-text">{resource.name}</div>
            <div className="text-[11px] text-muted">
              {resource.rtype}{resource.kind === 'file' ? ` · ${fmtBytes(resource.size_bytes)}` : ` · ${resource.source}`}
            </div>
          </div>
        </div>
        <p className="mb-4 text-[13px] leading-relaxed text-muted">
          {resource.kind === 'file'
            ? 'The stored file will be permanently removed from disk.'
            : 'This link will be removed from the project.'}
        </p>
        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="rounded-lg px-3 py-1.5 text-sm text-muted hover:bg-overlay/5 hover:text-text">Cancel</button>
          <button disabled={busy}
            onClick={async () => { setBusy(true); try { await onConfirm() } finally { setBusy(false) } }}
            className="flex items-center gap-1.5 rounded-lg bg-danger px-3 py-1.5 text-sm font-medium text-white hover:bg-danger/90 disabled:opacity-50">
            {busy ? <Loader2 size={13} className="animate-spin" /> : <Trash2 size={13} />} Delete
          </button>
        </div>
      </motion.div>
    </div>
  )
}

export function AddLinkModal({ onClose, onAdd }: { onClose: () => void; onAdd: (url: string) => Promise<void> }) {
  const [raw, setRaw] = useState('')
  const [busy, setBusy] = useState(false)
  const [progress, setProgress] = useState<{ done: number; total: number; failed: number } | null>(null)

  const urls = raw.split('\n').map(s => s.trim()).filter(s => s.startsWith('http'))
  const count = urls.length
  const singleKind = count === 1
    ? urls[0].includes('youtu') ? 'YouTube — title & transcript fetched automatically'
      : urls[0].includes('docs.google') || urls[0].includes('drive.google') ? 'Google Drive/Docs — title fetched automatically'
      : urls[0].includes('github.com') ? 'GitHub — repo/file reference'
      : urls[0].toLowerCase().endsWith('.pdf') ? 'PDF link'
      : 'Web page — readable extract stored for search'
    : ''

  async function submit() {
    if (!count || busy) return
    setBusy(true)
    setProgress({ done: 0, total: count, failed: 0 })
    let done = 0
    let failed = 0
    for (const u of urls) {
      try { await onAdd(u) } catch { failed++ }
      done++
      setProgress({ done, total: count, failed })
    }
    setBusy(false)
    if (failed === 0) onClose()
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm" onClick={busy ? undefined : onClose}>
      <motion.div initial={{ opacity: 0, scale: 0.95, y: 8 }} animate={{ opacity: 1, scale: 1, y: 0 }} exit={{ opacity: 0, scale: 0.95 }}
        onClick={e => e.stopPropagation()} className="w-full max-w-md rounded-2xl border border-border bg-surface p-5 shadow-2xl">
        <div className="mb-3 flex items-center justify-between">
          <div className="flex items-center gap-2 text-sm font-semibold text-heading"><Link2 size={15} className="text-accent" /> Add links</div>
          <button onClick={onClose} disabled={busy} className="text-muted hover:text-text disabled:opacity-40"><X size={16} /></button>
        </div>
        <textarea autoFocus value={raw} onChange={e => setRaw(e.target.value)} disabled={busy}
          placeholder={'Paste one or more links — one per line:\n\nhttps://youtube.com/watch?v=…\nhttps://docs.google.com/…\nhttps://github.com/…'}
          rows={5}
          className="mb-2 w-full resize-none rounded-lg border border-border bg-panel px-3 py-2 text-sm text-text outline-none focus:border-accent disabled:opacity-60" />
        {singleKind && !busy && (
          <div className="mb-3 rounded-lg bg-accent/8 px-3 py-1.5 text-[11px] text-accent">{singleKind}</div>
        )}
        {count > 1 && !busy && (
          <div className="mb-3 rounded-lg bg-accent/8 px-3 py-1.5 text-[11px] text-accent">{count} links ready — titles fetched automatically</div>
        )}
        {progress && busy && (
          <div className="mb-3 rounded-lg border border-border bg-panel px-3 py-2">
            <div className="flex items-center justify-between text-[11px] text-muted">
              <span className="flex items-center gap-1.5"><Loader2 size={12} className="animate-spin" /> Adding links…</span>
              <span>{progress.done} / {progress.total}</span>
            </div>
            <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-overlay/8">
              <div className="h-full rounded-full bg-accent transition-all duration-300"
                style={{ width: `${(progress.done / progress.total) * 100}%` }} />
            </div>
          </div>
        )}
        {progress && !busy && progress.failed > 0 && (
          <div className="mb-3 rounded-lg bg-danger/10 px-3 py-2 text-[11px] text-danger">
            {progress.failed} of {progress.total} link(s) failed — check the URLs and try again.
          </div>
        )}
        <div className="flex justify-end gap-2">
          <button onClick={onClose} disabled={busy} className="rounded-lg px-3 py-1.5 text-sm text-muted hover:bg-overlay/5 hover:text-text disabled:opacity-40">Cancel</button>
          <button disabled={busy || count === 0} onClick={submit}
            className="flex items-center gap-1.5 rounded-lg bg-accent px-3 py-1.5 text-sm font-medium text-white hover:bg-accent/90 disabled:opacity-50">
            {busy ? <Loader2 size={13} className="animate-spin" /> : <Link2 size={13} />}
            {count > 1 ? `Add ${count} links` : 'Add link'}
          </button>
        </div>
      </motion.div>
    </div>
  )
}

export function AddResourceModal({ onClose, onUpload, onAddLink }: {
  onClose: () => void
  onUpload: (files: FileList | File[]) => Promise<void>
  onAddLink: (url: string) => Promise<void>
}) {
  const [tab, setTab] = useState<'upload' | 'link'>('upload')
  const [dragOver, setDragOver] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [raw, setRaw] = useState('')
  const [busy, setBusy] = useState(false)
  const [progress, setProgress] = useState<{ done: number; total: number; failed: number } | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  const urls = raw.split('\n').map(s => s.trim()).filter(s => s.startsWith('http'))
  const count = urls.length

  async function doUpload(files: FileList | File[]) {
    setUploading(true)
    try { await onUpload(files) } finally { setUploading(false) }
    onClose()
  }

  async function submitLinks() {
    if (!count || busy) return
    setBusy(true)
    setProgress({ done: 0, total: count, failed: 0 })
    let done = 0, failed = 0
    for (const u of urls) {
      try { await onAddLink(u) } catch { failed++ }
      done++; setProgress({ done, total: count, failed })
    }
    setBusy(false)
    if (failed === 0) onClose()
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
      onClick={() => (uploading || busy) ? undefined : onClose}>
      <motion.div initial={{ opacity: 0, scale: 0.95, y: 8 }} animate={{ opacity: 1, scale: 1, y: 0 }} exit={{ opacity: 0, scale: 0.95 }}
        onClick={e => e.stopPropagation()} className="w-full max-w-md rounded-2xl border border-border bg-surface p-5 shadow-2xl">
        <div className="mb-4 flex items-center justify-between">
          <div className="flex items-center gap-2 text-sm font-semibold text-heading"><Plus size={15} className="text-accent" /> Add Resource</div>
          <button onClick={onClose} disabled={uploading || busy} className="text-muted hover:text-text disabled:opacity-40"><X size={16} /></button>
        </div>

        {/* Tabs */}
        <div className="mb-3 flex gap-1 rounded-lg border border-border bg-panel p-1">
          <button onClick={() => setTab('upload')}
            className={`flex flex-1 items-center justify-center gap-1.5 rounded-md py-1.5 text-[12px] font-medium transition-colors ${tab === 'upload' ? 'bg-accent text-white' : 'text-muted hover:text-text'}`}>
            <Upload size={13} /> Upload
          </button>
          <button onClick={() => setTab('link')}
            className={`flex flex-1 items-center justify-center gap-1.5 rounded-md py-1.5 text-[12px] font-medium transition-colors ${tab === 'link' ? 'bg-accent text-white' : 'text-muted hover:text-text'}`}>
            <Link2 size={13} /> Link
          </button>
        </div>

        {/* Upload tab */}
        {tab === 'upload' && (
          <>
            <div
              onDragOver={e => { e.preventDefault(); setDragOver(true) }}
              onDragLeave={() => setDragOver(false)}
              onDrop={e => { e.preventDefault(); setDragOver(false); if (e.dataTransfer.files?.length) doUpload(e.dataTransfer.files) }}
              onClick={() => fileRef.current?.click()}
              className={`flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed py-8 transition-colors ${dragOver ? 'border-accent bg-accent/5' : 'border-border hover:border-accent/40 hover:bg-overlay/3'}`}>
              {uploading ? (
                <><Loader2 size={28} className="animate-spin text-accent" /><span className="mt-2 text-[12px] text-muted">Uploading…</span></>
              ) : (
                <><Upload size={28} className="text-muted/50" /><span className="mt-2 text-[12px] font-medium text-text">Drop files here or click to browse</span><span className="mt-0.5 text-[10px] text-muted">Any file type — images, PDFs, docs, code…</span></>
              )}
            </div>
            <input ref={fileRef} type="file" multiple className="hidden"
              onChange={e => { if (e.target.files?.length) doUpload(e.target.files); e.target.value = '' }} />
          </>
        )}

        {/* Link tab */}
        {tab === 'link' && (
          <>
            <textarea autoFocus value={raw} onChange={e => setRaw(e.target.value)} disabled={busy}
              placeholder={'Paste one or more links — one per line:\n\nhttps://youtube.com/watch?v=…\nhttps://docs.google.com/…\nhttps://github.com/…'}
              rows={5}
              className="w-full resize-none rounded-lg border border-border bg-panel px-3 py-2 text-sm text-text outline-none focus:border-accent disabled:opacity-60" />
            {count > 0 && !busy && (
              <div className="mt-2 rounded-lg bg-accent/8 px-3 py-1.5 text-[11px] text-accent">{count} link{count > 1 ? 's' : ''} ready — titles fetched automatically</div>
            )}
            {progress && busy && (
              <div className="mt-2 rounded-lg border border-border bg-panel px-3 py-2">
                <div className="flex items-center justify-between text-[11px] text-muted">
                  <span className="flex items-center gap-1.5"><Loader2 size={12} className="animate-spin" /> Adding links…</span>
                  <span>{progress.done} / {progress.total}</span>
                </div>
                <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-overlay/8">
                  <div className="h-full rounded-full bg-accent transition-all duration-300" style={{ width: `${(progress.done / progress.total) * 100}%` }} />
                </div>
              </div>
            )}
            {progress && !busy && progress.failed > 0 && (
              <div className="mt-2 rounded-lg bg-danger/10 px-3 py-2 text-[11px] text-danger">{progress.failed} of {progress.total} link(s) failed — check the URLs and try again.</div>
            )}
            <div className="mt-3 flex justify-end gap-2">
              <button onClick={onClose} disabled={busy} className="rounded-lg px-3 py-1.5 text-sm text-muted hover:bg-overlay/5 hover:text-text disabled:opacity-40">Cancel</button>
              <button disabled={busy || count === 0} onClick={submitLinks}
                className="flex items-center gap-1.5 rounded-lg bg-accent px-3 py-1.5 text-sm font-medium text-white hover:bg-accent/90 disabled:opacity-50">
                {busy ? <Loader2 size={13} className="animate-spin" /> : <Link2 size={13} />}
                {count > 1 ? `Add ${count} links` : 'Add link'}
              </button>
            </div>
          </>
        )}
      </motion.div>
    </div>
  )
}

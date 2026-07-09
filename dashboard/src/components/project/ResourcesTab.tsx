import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Upload, Link2, FolderPlus, Folder, LayoutGrid, List as ListIcon, X, Trash2,
  Search, ChevronRight, Home, Loader2, ExternalLink, Tag, FileText, FileSpreadsheet,
  Presentation, FileImage, FileVideo, FileAudio, FileArchive, FileCode2, File as FileIcon,
  Youtube, Github, Globe2, HardDrive, Download, Pencil,
} from 'lucide-react'
import {
  pmListResources, pmUploadResource, pmAddResourceLink, pmPatchResource,
  pmDeleteResource, pmCreateFolder, pmRenameFolder, pmDeleteFolder, pmResourceRawUrl,
  type PMResource, type PMFolder,
} from '../../api'
import { useToast } from '../../context/ToastProvider'
import { fmtAgo, fmtBytes } from './shared'

/** Curated per-type icon set (#12 D51). */
const RTYPE_ICON: Record<string, { Icon: typeof FileIcon; tone: string }> = {
  doc:     { Icon: FileText,        tone: 'text-sky-400' },
  pdf:     { Icon: FileText,        tone: 'text-red-400' },
  sheet:   { Icon: FileSpreadsheet, tone: 'text-emerald-400' },
  slides:  { Icon: Presentation,    tone: 'text-amber-400' },
  image:   { Icon: FileImage,       tone: 'text-violet-400' },
  video:   { Icon: FileVideo,       tone: 'text-pink-400' },
  audio:   { Icon: FileAudio,       tone: 'text-teal-400' },
  archive: { Icon: FileArchive,     tone: 'text-orange-400' },
  code:    { Icon: FileCode2,       tone: 'text-cyan-400' },
  youtube: { Icon: Youtube,         tone: 'text-red-500' },
  github:  { Icon: Github,          tone: 'text-text' },
  web:     { Icon: Globe2,          tone: 'text-sky-400' },
  link:    { Icon: Link2,           tone: 'text-accent' },
  file:    { Icon: FileIcon,        tone: 'text-muted' },
}

function RTypeIcon({ rtype, size = 16, className = '' }: { rtype?: string | null; size?: number; className?: string }) {
  const { Icon, tone } = RTYPE_ICON[rtype || 'file'] ?? RTYPE_ICON.file
  return <Icon size={size} className={`${tone} ${className}`} />
}

/** Resources (#12 D37–D51): Drive-style — grid/list toggle, folders + breadcrumb,
 * drag-drop upload, add-link (YouTube/Docs/web/PDF/GitHub), tags, in-app preview. */
export default function ResourcesTab({ projectId, onChanged }: { projectId: number; onChanged: () => void }) {
  const { toast } = useToast()
  const [items, setItems] = useState<PMResource[]>([])
  const [folders, setFolders] = useState<PMFolder[]>([])
  const [loading, setLoading] = useState(true)
  const [folderId, setFolderId] = useState<number | null>(null)   // null = root
  const [view, setView] = useState<'grid' | 'list'>(() => (localStorage.getItem('tobi.resources.view') as any) || 'grid')
  const [q, setQ] = useState('')
  const [dragOver, setDragOver] = useState(false)
  const [uploading, setUploading] = useState(0)
  const [linkOpen, setLinkOpen] = useState(false)
  const [folderOpen, setFolderOpen] = useState(false)
  const [folderToRename, setFolderToRename] = useState<PMFolder | null>(null)
  const [folderToDelete, setFolderToDelete] = useState<PMFolder | null>(null)
  const [preview, setPreview] = useState<PMResource | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  const load = useCallback(async () => {
    try {
      const r = await pmListResources(projectId)
      setItems(r.items); setFolders(r.folders)
    } catch { /* keep */ } finally { setLoading(false) }
  }, [projectId])

  useEffect(() => { load() }, [load])

  const setViewPref = (v: 'grid' | 'list') => { setView(v); localStorage.setItem('tobi.resources.view', v) }

  async function uploadFiles(files: FileList | File[]) {
    const list = Array.from(files)
    if (!list.length) return
    setUploading(list.length)
    for (const f of list) {
      try {
        await pmUploadResource(projectId, f, folderId)
      } catch (e) {
        toast({ kind: 'error', title: `Upload failed: ${f.name}`, detail: (e as Error).message })
      } finally {
        setUploading(n => Math.max(0, n - 1))
      }
    }
    await load(); onChanged()
  }

  async function removeResource(r: PMResource) {
    if (!window.confirm(`Delete "${r.name}"?${r.kind === 'file' ? ' The stored file is removed too.' : ''}`)) return
    try {
      await pmDeleteResource(projectId, r.id)
      if (preview?.id === r.id) setPreview(null)
      await load(); onChanged()
    } catch (e) { toast({ kind: 'error', title: 'Delete failed', detail: (e as Error).message }) }
  }

  async function addFolder(name: string) {
    try { await pmCreateFolder(projectId, name, folderId); setFolderOpen(false); await load() }
    catch (e) { toast({ kind: 'error', title: 'Failed', detail: (e as Error).message }) }
  }

  async function renameFolder(f: PMFolder, name: string) {
    try { await pmRenameFolder(projectId, f.id, name); setFolderToRename(null); await load() }
    catch (e) { toast({ kind: 'error', title: 'Rename failed', detail: (e as Error).message }) }
  }

  async function removeFolder(f: PMFolder) {
    try {
      if (folderId === f.id) setFolderId(f.parent_id ?? null)
      await pmDeleteFolder(projectId, f.id)
      setFolderToDelete(null); await load()
    } catch (e) { toast({ kind: 'error', title: 'Failed', detail: (e as Error).message }) }
  }

  async function moveTo(r: PMResource, target: number | null) {
    try { await pmPatchResource(projectId, r.id, { folder_id: target ?? 0 }); await load() }
    catch (e) { toast({ kind: 'error', title: 'Move failed', detail: (e as Error).message }) }
  }

  // breadcrumb chain for the current folder
  const crumb = useMemo(() => {
    const chain: PMFolder[] = []
    let cur = folders.find(f => f.id === folderId)
    while (cur) { chain.unshift(cur); cur = folders.find(f => f.id === cur!.parent_id) }
    return chain
  }, [folderId, folders])

  const hereFolders = folders.filter(f => (f.parent_id ?? null) === folderId)
  const hereItems = items.filter(r => (r.folder_id ?? null) === folderId)
  const searching = q.trim().length > 0
  const shown = searching
    ? items.filter(r => r.name.toLowerCase().includes(q.toLowerCase()) || r.tags.some(t => t.toLowerCase().includes(q.toLowerCase())))
    : hereItems

  return (
    <div className="flex h-full min-h-0"
      onDragOver={e => { e.preventDefault(); setDragOver(true) }}
      onDragLeave={e => { if (e.currentTarget === e.target) setDragOver(false) }}
      onDrop={e => { e.preventDefault(); setDragOver(false); if (e.dataTransfer.files?.length) uploadFiles(e.dataTransfer.files) }}>
      <div className="flex min-w-0 flex-1 flex-col">
        {/* Toolbar */}
        <div className="flex flex-wrap items-center gap-2 border-b border-border px-4 py-3">
          <div className="relative min-w-[10rem] flex-1">
            <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted" />
            <input value={q} onChange={e => setQ(e.target.value)} placeholder="Search files, links, #tags…"
              className="w-full rounded-lg border border-border bg-panel py-1.5 pl-8 pr-3 text-sm text-text outline-none focus:border-accent" />
          </div>
          <button onClick={() => fileRef.current?.click()}
            className="flex items-center gap-1.5 rounded-lg bg-accent px-3 py-1.5 text-[12px] font-medium text-white transition-colors hover:bg-accent/90">
            {uploading > 0 ? <Loader2 size={13} className="animate-spin" /> : <Upload size={13} />} Upload
          </button>
          <input ref={fileRef} type="file" multiple className="hidden"
            onChange={e => { if (e.target.files?.length) uploadFiles(e.target.files); e.target.value = '' }} />
          <button onClick={() => setLinkOpen(true)}
            className="flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-[12px] text-muted transition-colors hover:border-accent/40 hover:text-accent">
            <Link2 size={13} /> Add link
          </button>
          <button onClick={() => setFolderOpen(true)}
            className="flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-[12px] text-muted transition-colors hover:border-accent/40 hover:text-accent">
            <FolderPlus size={13} /> Folder
          </button>
          <div className="flex overflow-hidden rounded-lg border border-border">
            <button onClick={() => setViewPref('grid')} className={`p-1.5 ${view === 'grid' ? 'bg-accent/15 text-accent' : 'text-muted hover:text-text'}`}><LayoutGrid size={14} /></button>
            <button onClick={() => setViewPref('list')} className={`p-1.5 ${view === 'list' ? 'bg-accent/15 text-accent' : 'text-muted hover:text-text'}`}><ListIcon size={14} /></button>
          </div>
        </div>

        {/* Breadcrumb */}
        <div className="flex items-center gap-1 border-b border-border/60 px-4 py-1.5 text-[12px]">
          <button onClick={() => setFolderId(null)}
            className={`flex items-center gap-1 rounded px-1.5 py-0.5 transition-colors ${folderId === null && !searching ? 'text-text' : 'text-muted hover:text-text'}`}
            onDragOver={e => e.preventDefault()}
            onDrop={e => { e.preventDefault(); const id = e.dataTransfer.getData('resource-id'); if (id) { const r = items.find(x => x.id === Number(id)); if (r) moveTo(r, null) } }}>
            <Home size={11} /> Resources
          </button>
          {crumb.map(f => (
            <span key={f.id} className="flex items-center gap-1">
              <ChevronRight size={11} className="text-muted/50" />
              <button onClick={() => setFolderId(f.id)} className={`rounded px-1.5 py-0.5 transition-colors ${folderId === f.id ? 'text-text' : 'text-muted hover:text-text'}`}>
                {f.name}
              </button>
            </span>
          ))}
          {searching && <span className="ml-2 text-muted">— search results ({shown.length})</span>}
        </div>

        {/* Content (drop zone) */}
        <div className={`relative min-h-0 flex-1 overflow-y-auto p-4 ${dragOver ? 'ring-2 ring-inset ring-accent/60' : ''}`}>
          {dragOver && (
            <div className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center bg-accent/5">
              <div className="rounded-xl border border-accent/40 bg-surface px-4 py-2 text-sm text-accent shadow-xl">Drop to upload here</div>
            </div>
          )}
          {loading ? (
            <div className="flex items-center gap-2 py-8 text-sm text-muted"><Loader2 size={14} className="animate-spin" /> Loading…</div>
          ) : (
            <>
              {/* Folders first (hidden while searching) */}
              {!searching && hereFolders.length > 0 && (
                <div className={view === 'grid' ? 'mb-3 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5' : 'mb-3 space-y-1'}>
                  {hereFolders.map(f => (
                    <div key={f.id} onDoubleClick={() => setFolderId(f.id)} onClick={() => setFolderId(f.id)}
                      onDragOver={e => e.preventDefault()}
                      onDrop={e => { e.preventDefault(); const id = e.dataTransfer.getData('resource-id'); if (id) { const r = items.find(x => x.id === Number(id)); if (r) moveTo(r, f.id) } }}
                      className="group flex cursor-pointer items-center gap-2 rounded-lg border border-border bg-panel px-3 py-2 transition-colors hover:border-accent/40">
                      <Folder size={15} className="shrink-0 text-warning" />
                      <span className="min-w-0 flex-1 truncate text-[13px] text-text">{f.name}</span>
                      <button onClick={e => { e.stopPropagation(); setFolderToRename(f) }} title="Rename"
                        className="shrink-0 text-muted opacity-0 transition-opacity hover:text-text group-hover:opacity-100"><Pencil size={12} /></button>
                      <button onClick={e => { e.stopPropagation(); setFolderToDelete(f) }} title="Delete"
                        className="shrink-0 text-muted opacity-0 transition-opacity hover:text-danger group-hover:opacity-100"><Trash2 size={12} /></button>
                    </div>
                  ))}
                </div>
              )}

              {shown.length === 0 && hereFolders.length === 0 ? (
                <div className="flex flex-col items-center gap-2 py-12 text-muted">
                  <HardDrive size={30} className="text-muted/30" />
                  <div className="text-sm">{searching ? 'Nothing matches.' : 'This project has no resources yet.'}</div>
                  {!searching && <div className="text-[11px]">Drag files anywhere here, or use Upload / Add link.</div>}
                </div>
              ) : view === 'grid' ? (
                <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3 lg:grid-cols-5">
                  {shown.map(r => (
                    <div key={r.id} draggable onDragStart={e => e.dataTransfer.setData('resource-id', String(r.id))}
                      onClick={() => setPreview(r)}
                      className={`group cursor-pointer rounded-xl border bg-panel p-3 transition-colors ${preview?.id === r.id ? 'border-accent/50' : 'border-border hover:border-accent/40'}`}>
                      <div className="mb-2 flex h-14 items-center justify-center rounded-lg bg-white/3">
                        <RTypeIcon rtype={r.rtype} size={26} />
                      </div>
                      <div className="truncate text-[12px] font-medium text-text" title={r.name}>{r.name}</div>
                      <div className="mt-0.5 flex items-center justify-between text-[10px] text-muted">
                        <span>{r.kind === 'file' ? fmtBytes(r.size_bytes) : r.source}</span>
                        <span>{fmtAgo(r.created_at)}</span>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="divide-y divide-border/40 overflow-hidden rounded-xl border border-border">
                  {shown.map(r => (
                    <div key={r.id} draggable onDragStart={e => e.dataTransfer.setData('resource-id', String(r.id))}
                      onClick={() => setPreview(r)}
                      className={`group flex cursor-pointer items-center gap-3 px-3 py-2 transition-colors ${preview?.id === r.id ? 'bg-accent/8' : 'hover:bg-white/3'}`}>
                      <RTypeIcon rtype={r.rtype} size={16} />
                      <span className="min-w-0 flex-1 truncate text-[13px] text-text">{r.name}</span>
                      {r.tags.slice(0, 3).map(t => (
                        <span key={t} className="rounded bg-white/5 px-1.5 py-0.5 text-[10px] text-muted">#{t}</span>
                      ))}
                      <span className="w-16 shrink-0 text-right text-[11px] text-muted">{r.kind === 'file' ? fmtBytes(r.size_bytes) : r.source}</span>
                      <span className="w-16 shrink-0 text-right text-[11px] text-muted">{fmtAgo(r.created_at)}</span>
                      <button onClick={e => { e.stopPropagation(); removeResource(r) }}
                        className="shrink-0 text-muted opacity-0 transition-opacity hover:text-danger group-hover:opacity-100"><Trash2 size={13} /></button>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      </div>

      {/* Preview panel (D48) */}
      <AnimatePresence>
        {preview && (
          <PreviewPanel key={preview.id} projectId={projectId} r={preview}
            onClose={() => setPreview(null)} onDelete={() => removeResource(preview)}
            onTags={async tags => {
              try { await pmPatchResource(projectId, preview.id, { tags }); await load() }
              catch { toast({ kind: 'error', title: 'Tag save failed' }) }
            }} />
        )}
      </AnimatePresence>

      {/* Add-link modal (D41/D42) */}
      <AnimatePresence>
        {linkOpen && (
          <AddLinkModal onClose={() => setLinkOpen(false)}
            onAdd={async (url, name) => {
              try {
                await pmAddResourceLink(projectId, url, name || undefined, folderId)
                setLinkOpen(false); await load(); onChanged()
              } catch (e) { toast({ kind: 'error', title: 'Add link failed', detail: (e as Error).message }) }
            }} />
        )}
      </AnimatePresence>

      {/* New-folder / rename-folder modal */}
      <AnimatePresence>
        {folderOpen && <FolderNameModal onClose={() => setFolderOpen(false)} onSubmit={addFolder} />}
        {folderToRename && (
          <FolderNameModal key={folderToRename.id} title="Rename folder" cta="Rename" initial={folderToRename.name}
            onClose={() => setFolderToRename(null)} onSubmit={name => renameFolder(folderToRename, name)} />
        )}
      </AnimatePresence>

      {/* Delete-folder confirm */}
      <AnimatePresence>
        {folderToDelete && (
          <ConfirmFolderDelete folder={folderToDelete}
            onClose={() => setFolderToDelete(null)} onConfirm={() => removeFolder(folderToDelete)} />
        )}
      </AnimatePresence>
    </div>
  )
}

function FolderNameModal({ title = 'New folder', cta = 'Create', initial = '', onClose, onSubmit }: {
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
          <button onClick={onClose} className="rounded-lg px-3 py-1.5 text-sm text-muted hover:bg-white/5 hover:text-text">Cancel</button>
          <button disabled={busy || !name.trim()} onClick={submit}
            className="flex items-center gap-1.5 rounded-lg bg-accent px-3 py-1.5 text-sm font-medium text-white hover:bg-accent/90 disabled:opacity-50">
            {busy ? <Loader2 size={13} className="animate-spin" /> : <FolderPlus size={13} />} {cta}
          </button>
        </div>
      </motion.div>
    </div>
  )
}

function ConfirmFolderDelete({ folder, onClose, onConfirm }: { folder: PMFolder; onClose: () => void; onConfirm: () => Promise<void> }) {
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
          <button onClick={onClose} className="rounded-lg px-3 py-1.5 text-sm text-muted hover:bg-white/5 hover:text-text">Cancel</button>
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

function PreviewPanel({ projectId, r, onClose, onDelete, onTags }: {
  projectId: number; r: PMResource
  onClose: () => void; onDelete: () => void; onTags: (tags: string[]) => void
}) {
  const raw = pmResourceRawUrl(projectId, r.id)
  const [tagInput, setTagInput] = useState('')
  const isImage = r.rtype === 'image'
  const isVideo = r.rtype === 'video'
  const isAudio = r.rtype === 'audio'
  const isPdf = r.rtype === 'pdf' && r.kind === 'file'
  const isText = ['doc', 'code'].includes(r.rtype) && r.kind === 'file' && ['md', 'txt', 'json', 'csv', 'log', 'py', 'ts', 'js'].includes(r.ext || '')

  return (
    <motion.aside initial={{ x: 40, opacity: 0 }} animate={{ x: 0, opacity: 1 }} exit={{ x: 40, opacity: 0 }}
      transition={{ type: 'spring', stiffness: 380, damping: 32 }}
      className="flex h-full w-full shrink-0 flex-col border-l border-border bg-panel sm:w-96">
      <div className="flex items-center gap-2 border-b border-border px-4 py-3">
        <RTypeIcon rtype={r.rtype} size={16} />
        <span className="min-w-0 flex-1 truncate text-sm font-semibold text-heading" title={r.name}>{r.name}</span>
        <button onClick={onDelete} className="shrink-0 rounded p-1 text-muted hover:text-danger"><Trash2 size={14} /></button>
        <button onClick={onClose} className="shrink-0 rounded p-1 text-muted hover:text-text"><X size={16} /></button>
      </div>

      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-4">
        {/* Inline preview by type */}
        {isImage && <img src={raw} alt={r.name} className="w-full rounded-lg border border-border" />}
        {isVideo && <video src={raw} controls className="w-full rounded-lg border border-border" />}
        {isAudio && <audio src={raw} controls className="w-full" />}
        {isPdf && <iframe src={raw} title={r.name} className="h-80 w-full rounded-lg border border-border bg-white" />}
        {isText && <TextPeek url={raw} />}
        {r.kind === 'link' && (
          <a href={r.url || '#'} target="_blank" rel="noreferrer"
            className="flex items-center gap-2 rounded-lg border border-border bg-surface px-3 py-2.5 text-sm text-accent transition-colors hover:border-accent/40">
            <ExternalLink size={14} /> Open {r.source === 'youtube' ? 'on YouTube' : r.source === 'drive' ? 'in Google Drive' : r.source === 'github' ? 'on GitHub' : 'link'}
          </a>
        )}
        {r.kind === 'file' && !isImage && !isVideo && !isAudio && !isPdf && !isText && (
          <div className="rounded-lg border border-dashed border-border px-3 py-4 text-center text-[12px] text-muted">
            No inline preview for .{r.ext || 'this type'} — download to open externally.
          </div>
        )}
        {r.kind === 'file' && (
          <a href={raw} download={r.name}
            className="flex items-center gap-2 rounded-lg border border-border bg-surface px-3 py-2 text-[12px] text-muted transition-colors hover:border-accent/40 hover:text-accent">
            <Download size={13} /> Download ({fmtBytes(r.size_bytes)})
          </a>
        )}
        {r.has_text && (
          <div className="rounded-lg bg-accent/8 px-3 py-2 text-[11px] text-accent">
            Text extracted — TOBI can search &amp; summarize this resource in chat.
          </div>
        )}

        {/* Meta */}
        <div className="space-y-1 rounded-lg border border-border/60 bg-surface p-3 text-[11px] text-muted">
          <div className="flex justify-between"><span>Type</span><span className="text-text">{r.rtype}{r.ext ? ` (.${r.ext})` : ''}</span></div>
          <div className="flex justify-between"><span>Source</span><span className="text-text">{r.source}</span></div>
          {r.kind === 'file' && <div className="flex justify-between"><span>Size</span><span className="text-text">{fmtBytes(r.size_bytes)}</span></div>}
          <div className="flex justify-between"><span>Added</span><span className="text-text">{fmtAgo(r.created_at)} by {r.created_by}</span></div>
        </div>

        {/* Tags (D46) */}
        <div>
          <div className="mb-1 flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wide text-muted"><Tag size={10} /> Tags</div>
          <div className="flex flex-wrap items-center gap-1.5">
            {r.tags.map(t => (
              <span key={t} className="group/tag flex items-center gap-1 rounded-full bg-white/5 px-2 py-0.5 text-[11px] text-muted">
                #{t}
                <button onClick={() => onTags(r.tags.filter(x => x !== t))} className="opacity-0 transition-opacity group-hover/tag:opacity-100"><X size={9} /></button>
              </span>
            ))}
            <input value={tagInput} onChange={e => setTagInput(e.target.value)}
              onKeyDown={e => {
                if (e.key === 'Enter' && tagInput.trim()) {
                  const t = tagInput.trim().replace(/^#/, '')
                  if (t && !r.tags.includes(t)) onTags([...r.tags, t])
                  setTagInput('')
                }
              }}
              placeholder="+ tag" className="w-16 border-b border-border bg-transparent py-0.5 text-[11px] text-text outline-none focus:border-accent" />
          </div>
        </div>
      </div>
    </motion.aside>
  )
}

function TextPeek({ url }: { url: string }) {
  const [text, setText] = useState<string | null>(null)
  useEffect(() => {
    let live = true
    fetch(url).then(r => r.text()).then(t => { if (live) setText(t.slice(0, 20000)) }).catch(() => { if (live) setText(null) })
    return () => { live = false }
  }, [url])
  if (text == null) return <div className="text-[12px] text-muted">Loading preview…</div>
  return (
    <pre className="max-h-80 overflow-auto whitespace-pre-wrap rounded-lg border border-border bg-surface p-3 font-mono text-[11px] leading-relaxed text-text">
      {text}
    </pre>
  )
}

function AddLinkModal({ onClose, onAdd }: { onClose: () => void; onAdd: (url: string, name: string) => Promise<void> }) {
  const [url, setUrl] = useState('')
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)

  const kind = url.includes('youtu') ? 'YouTube — the transcript is fetched & stored for search'
    : url.includes('docs.google') || url.includes('drive.google') ? 'Google Drive/Docs — opens in Drive'
    : url.includes('github.com') ? 'GitHub — repo/file reference'
    : url.toLowerCase().endsWith('.pdf') ? 'PDF link'
    : url.startsWith('http') ? 'Web page — a readable extract is stored for search' : ''

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm" onClick={onClose}>
      <motion.div initial={{ opacity: 0, scale: 0.95, y: 8 }} animate={{ opacity: 1, scale: 1, y: 0 }} exit={{ opacity: 0, scale: 0.95 }}
        onClick={e => e.stopPropagation()} className="w-full max-w-md rounded-2xl border border-border bg-surface p-5 shadow-2xl">
        <div className="mb-3 flex items-center justify-between">
          <div className="flex items-center gap-2 text-sm font-semibold text-heading"><Link2 size={15} className="text-accent" /> Add online resource</div>
          <button onClick={onClose} className="text-muted hover:text-text"><X size={16} /></button>
        </div>
        <input autoFocus value={url} onChange={e => setUrl(e.target.value)}
          placeholder="Paste a link — Google Docs/Sheets, YouTube, article, PDF, GitHub…"
          className="mb-2 w-full rounded-lg border border-border bg-panel px-3 py-2 text-sm text-text outline-none focus:border-accent" />
        <input value={name} onChange={e => setName(e.target.value)} placeholder="Display name (optional)"
          className="mb-2 w-full rounded-lg border border-border bg-panel px-3 py-2 text-sm text-text outline-none focus:border-accent" />
        {kind && <div className="mb-3 rounded-lg bg-accent/8 px-3 py-1.5 text-[11px] text-accent">{kind}</div>}
        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="rounded-lg px-3 py-1.5 text-sm text-muted hover:bg-white/5 hover:text-text">Cancel</button>
          <button disabled={busy || !url.trim().startsWith('http')}
            onClick={async () => { setBusy(true); try { await onAdd(url.trim(), name.trim()) } finally { setBusy(false) } }}
            className="flex items-center gap-1.5 rounded-lg bg-accent px-3 py-1.5 text-sm font-medium text-white hover:bg-accent/90 disabled:opacity-50">
            {busy ? <Loader2 size={13} className="animate-spin" /> : <Link2 size={13} />} Add
          </button>
        </div>
      </motion.div>
    </div>
  )
}

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Upload, Link2, FolderPlus, Folder, LayoutGrid, List as ListIcon, X, Trash2,
  Search, ChevronRight, ChevronLeft, Home, Loader2, ExternalLink, Tag, Info,
  FileText, FileSpreadsheet, Presentation, FileImage, FileVideo, FileAudio,
  FileArchive, FileCode2, File as FileIcon, Youtube, Github, Globe2, HardDrive,
  Download, Pencil, MoreVertical, Copy, Plus,
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

function ytId(url: string): string | null {
  const m = (url || '').match(/(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/shorts\/|youtube\.com\/embed\/)([A-Za-z0-9_-]{11})/)
  return m ? m[1] : null
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
  const [addOpen, setAddOpen] = useState(false)
  const [folderOpen, setFolderOpen] = useState(false)
  const [folderToRename, setFolderToRename] = useState<PMFolder | null>(null)
  const [folderToDelete, setFolderToDelete] = useState<PMFolder | null>(null)
  const [resourceToRename, setResourceToRename] = useState<PMResource | null>(null)
  const [resourceToDelete, setResourceToDelete] = useState<PMResource | null>(null)
  const [previewId, setPreviewId] = useState<number | null>(null)
  const preview = previewId != null ? items.find(r => r.id === previewId) ?? null : null
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

  function removeResource(r: PMResource) {
    setResourceToDelete(r)
  }

  async function confirmDeleteResource() {
    if (!resourceToDelete) return
    const r = resourceToDelete
    try {
      await pmDeleteResource(projectId, r.id)
      setPreviewId(null)
      setResourceToDelete(null)
      await load(); onChanged()
    } catch (e) { toast({ kind: 'error', title: 'Delete failed', detail: (e as Error).message }) }
  }

  async function renameResource(r: PMResource, name: string) {
    try { await pmPatchResource(projectId, r.id, { name }); setResourceToRename(null); await load() }
    catch (e) { toast({ kind: 'error', title: 'Rename failed', detail: (e as Error).message }) }
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
          <input ref={fileRef} type="file" multiple className="hidden"
            onChange={e => { if (e.target.files?.length) uploadFiles(e.target.files); e.target.value = '' }} />
          <button onClick={() => setFolderOpen(true)}
            className="flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-[12px] text-muted transition-colors hover:border-accent/40 hover:text-accent">
            <FolderPlus size={13} /> Folder
          </button>
          <button onClick={() => setAddOpen(true)}
            className="flex items-center gap-1.5 rounded-lg bg-accent px-3 py-1.5 text-[12px] font-medium text-white transition-colors hover:bg-accent/90">
            {uploading > 0 ? <Loader2 size={13} className="animate-spin" /> : <Plus size={13} />} Add Resource
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
                  {shown.map(r => {
                    const ytThumb = r.source === 'youtube' ? ytId(r.url || '') : null
                    return (
                    <div key={r.id} draggable onDragStart={e => e.dataTransfer.setData('resource-id', String(r.id))}
                      onClick={() => setPreviewId(r.id)}
                      className={`group relative cursor-pointer rounded-xl border bg-panel p-3 transition-colors ${previewId === r.id ? 'border-accent/50' : 'border-border hover:border-accent/40'}`}>
                      {/* Hover actions — 3-dot menu for links, inline for files */}
                      {r.kind === 'link' ? (
                        <CardMenu resource={r} onRename={() => setResourceToRename(r)} onDelete={() => removeResource(r)} />
                      ) : (
                        <div className="absolute right-2 top-2 z-20 flex gap-0.5 opacity-0 transition-opacity group-hover:opacity-100">
                          <button onClick={e => { e.stopPropagation(); setResourceToRename(r) }} title="Rename"
                            className="rounded-md bg-black/50 p-1 text-white/70 backdrop-blur-sm transition-colors hover:bg-black/70 hover:text-white">
                            <Pencil size={11} />
                          </button>
                          <button onClick={e => { e.stopPropagation(); removeResource(r) }} title="Delete"
                            className="rounded-md bg-black/50 p-1 text-white/70 backdrop-blur-sm transition-colors hover:bg-red-500/80 hover:text-white">
                            <Trash2 size={11} />
                          </button>
                        </div>
                      )}
                      {ytThumb ? (
                        <div className="relative mb-2 overflow-hidden rounded-lg bg-black/40" style={{ aspectRatio: '16 / 9' }}>
                          <img src={`https://i.ytimg.com/vi/${ytThumb}/mqdefault.jpg`} alt="" loading="lazy"
                            className="absolute inset-0 h-full w-full object-cover" />
                          <div className="absolute inset-0 bg-black/0 transition-colors group-hover:bg-black/25" />
                          {/* Play button on hover */}
                          <div className="absolute inset-0 flex items-center justify-center opacity-0 transition-opacity group-hover:opacity-100">
                            <div className="flex h-9 w-12 items-center justify-center rounded-xl bg-[#ff0033] shadow-lg">
                              <svg viewBox="0 0 24 24" fill="white" className="ml-0.5 h-4 w-4"><path d="M8 5v14l11-7z" /></svg>
                            </div>
                          </div>
                          {/* YouTube badge */}
                          <div className="absolute bottom-1.5 left-1.5 z-10 flex items-center gap-1 rounded-full bg-black/70 px-2 py-0.5 backdrop-blur-sm">
                            <Youtube size={10} className="text-red-500" />
                            <span className="text-[9px] font-medium text-white">YouTube</span>
                          </div>
                        </div>
                      ) : (
                        <div className="mb-2 flex h-14 items-center justify-center rounded-lg bg-overlay/3">
                          <RTypeIcon rtype={r.rtype} size={26} />
                        </div>
                      )}
                      <div className="truncate text-[12px] font-medium text-text" title={r.name}>{r.name}</div>
                      <div className="mt-0.5 flex items-center justify-between text-[10px] text-muted">
                        <span>{r.kind === 'file' ? fmtBytes(r.size_bytes) : r.source}</span>
                        <span>{fmtAgo(r.created_at)}</span>
                      </div>
                    </div>
                    )
                  })}
                </div>
              ) : (
                <div className="divide-y divide-border/40 overflow-hidden rounded-xl border border-border">
                  {shown.map(r => (
                    <div key={r.id} draggable onDragStart={e => e.dataTransfer.setData('resource-id', String(r.id))}
                      onClick={() => setPreviewId(r.id)}
                      className={`group flex cursor-pointer items-center gap-3 px-3 py-2 transition-colors ${previewId === r.id ? 'bg-accent/8' : 'hover:bg-overlay/3'}`}>
                      <RTypeIcon rtype={r.rtype} size={16} />
                      <span className="min-w-0 flex-1 truncate text-[13px] text-text">{r.name}</span>
                      {r.tags.slice(0, 3).map(t => (
                        <span key={t} className="rounded bg-overlay/5 px-1.5 py-0.5 text-[10px] text-muted">#{t}</span>
                      ))}
                      <span className="w-16 shrink-0 text-right text-[11px] text-muted">{r.kind === 'file' ? fmtBytes(r.size_bytes) : r.source}</span>
                      <span className="w-16 shrink-0 text-right text-[11px] text-muted">{fmtAgo(r.created_at)}</span>
                      {r.kind === 'link' ? (
                        <ListCardMenu resource={r} onRename={() => setResourceToRename(r)} onDelete={() => removeResource(r)} />
                      ) : (
                        <>
                          <button onClick={e => { e.stopPropagation(); setResourceToRename(r) }} title="Rename"
                            className="shrink-0 text-muted opacity-0 transition-opacity hover:text-text group-hover:opacity-100"><Pencil size={13} /></button>
                          <button onClick={e => { e.stopPropagation(); removeResource(r) }}
                            className="shrink-0 text-muted opacity-0 transition-opacity hover:text-danger group-hover:opacity-100"><Trash2 size={13} /></button>
                        </>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      </div>

      {/* Preview lightbox */}
      <AnimatePresence>
        {preview && (
          <PreviewModal key={preview.id} projectId={projectId} resource={preview} resources={shown}
            onClose={() => setPreviewId(null)} onDelete={() => removeResource(preview)}
            onNavigate={r => setPreviewId(r.id)}
            onRename={async name => { await pmPatchResource(projectId, preview.id, { name }); await load() }}
            onTags={async tags => {
              try { await pmPatchResource(projectId, preview.id, { tags }); await load() }
              catch { toast({ kind: 'error', title: 'Tag save failed' }) }
            }} />
        )}
      </AnimatePresence>

      {/* Add Resource modal (upload + link combined) */}
      <AnimatePresence>
        {addOpen && (
          <AddResourceModal
            onClose={() => { setAddOpen(false); load(); onChanged() }}
            onUpload={files => uploadFiles(files)}
            onAddLink={async url => { await pmAddResourceLink(projectId, url, undefined, folderId) }}
          />
        )}
      </AnimatePresence>

        {/* New-folder / rename-folder / rename-resource modal */}
        <AnimatePresence>
          {folderOpen && <FolderNameModal onClose={() => setFolderOpen(false)} onSubmit={addFolder} />}
          {folderToRename && (
            <FolderNameModal key={folderToRename.id} title="Rename folder" cta="Rename" initial={folderToRename.name}
              onClose={() => setFolderToRename(null)} onSubmit={name => renameFolder(folderToRename, name)} />
          )}
          {resourceToRename && (
            <FolderNameModal key={`res-${resourceToRename.id}`} title="Rename resource" cta="Rename" initial={resourceToRename.name}
              onClose={() => setResourceToRename(null)} onSubmit={name => renameResource(resourceToRename, name)} />
          )}
        </AnimatePresence>

      {/* Delete-folder confirm */}
      <AnimatePresence>
        {folderToDelete && (
          <ConfirmFolderDelete folder={folderToDelete}
            onClose={() => setFolderToDelete(null)} onConfirm={() => removeFolder(folderToDelete)} />
        )}
      </AnimatePresence>

      {/* Delete-resource confirm */}
      <AnimatePresence>
        {resourceToDelete && (
          <ConfirmResourceDelete resource={resourceToDelete}
            onClose={() => setResourceToDelete(null)} onConfirm={confirmDeleteResource} />
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

function ConfirmResourceDelete({ resource, onClose, onConfirm }: {
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

function PreviewModal({ projectId, resource, resources, onClose, onNavigate, onDelete, onRename, onTags }: {
  projectId: number; resource: PMResource; resources: PMResource[]
  onClose: () => void; onNavigate: (r: PMResource) => void
  onDelete: () => void; onRename: (name: string) => Promise<void>; onTags: (tags: string[]) => void
}) {
  const [showInfo, setShowInfo] = useState(true)
  const [tagInput, setTagInput] = useState('')
  const [renaming, setRenaming] = useState(false)
  const [renameVal, setRenameVal] = useState(resource.name)
  const r = resource
  const raw = pmResourceRawUrl(projectId, r.id)

  const index = Math.max(0, resources.findIndex(x => x.id === r.id))
  const hasPrev = index > 0
  const hasNext = index < resources.length - 1

  const isImage = r.rtype === 'image'
  const isVideo = r.rtype === 'video'
  const isAudio = r.rtype === 'audio'
  const isPdf = r.rtype === 'pdf' && r.kind === 'file'
  const isText = ['doc', 'code'].includes(r.rtype) && r.kind === 'file'
    && ['md', 'txt', 'json', 'csv', 'log', 'py', 'ts', 'js', 'yaml', 'yml', 'xml', 'html', 'css', 'sh'].includes(r.ext || '')
  const ytVideoId = r.source === 'youtube' ? ytId(r.url || '') : null
  const isYouTube = !!ytVideoId
  const hasFallback = r.kind === 'file' && !isImage && !isVideo && !isAudio && !isPdf && !isText

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
      else if (e.key === 'ArrowLeft' && hasPrev) onNavigate(resources[index - 1])
      else if (e.key === 'ArrowRight' && hasNext) onNavigate(resources[index + 1])
      else if ((e.key === 'i' || e.key === 'I') && !e.ctrlKey && !e.metaKey) setShowInfo(s => !s)
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [index, hasPrev, hasNext, resources, onClose, onNavigate])

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      transition={{ duration: 0.2 }}
      className="fixed inset-0 z-[60] flex bg-black/85 backdrop-blur-md" onClick={onClose}>
      <motion.div initial={{ scale: 0.96, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0.96, opacity: 0 }}
        transition={{ type: 'spring', stiffness: 400, damping: 35 }}
        onClick={e => e.stopPropagation()} className="relative flex h-full w-full overflow-hidden">

        {/* ── Content stage ── */}
        <div className="relative flex min-w-0 flex-1 flex-col">
          {/* Floating top bar */}
          <div className="absolute inset-x-0 top-0 z-20 flex items-center gap-3 bg-gradient-to-b from-black/70 to-transparent px-5 py-4">
            <RTypeIcon rtype={r.rtype} size={18} className="shrink-0" />
            <div className="min-w-0 flex-1">
              <div className="truncate text-[15px] font-semibold text-white">{r.name}</div>
              <div className="text-[11px] text-white/40">
                {r.rtype}{r.ext ? ` · .${r.ext}` : ''} · {r.kind === 'file' ? fmtBytes(r.size_bytes) : r.source}
              </div>
            </div>
            <button onClick={() => setShowInfo(s => !s)} title="Toggle details (I)"
              className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[12px] transition-colors ${showInfo ? 'bg-overlay/15 text-white' : 'bg-overlay/5 text-white/50 hover:bg-overlay/10'}`}>
              <Info size={13} /> Details
            </button>
            <button onClick={onDelete} title="Delete"
              className="flex items-center rounded-lg bg-overlay/5 px-3 py-1.5 text-[12px] text-white/50 transition-colors hover:bg-red-500/20 hover:text-red-400">
              <Trash2 size={14} />
            </button>
            <button onClick={onClose} title="Close (Esc)"
              className="flex items-center rounded-lg bg-overlay/5 px-3 py-1.5 text-[12px] text-white/50 transition-colors hover:bg-overlay/15 hover:text-white">
              <X size={17} />
            </button>
          </div>

          {/* Nav arrows */}
          {hasPrev && (
            <button onClick={() => onNavigate(resources[index - 1])}
              className="absolute left-4 top-1/2 z-20 flex h-11 w-11 -translate-y-1/2 items-center justify-center rounded-full bg-overlay/8 text-white/60 backdrop-blur-sm transition-all hover:bg-overlay/15 hover:text-white"
              title="Previous (←)">
              <ChevronLeft size={22} />
            </button>
          )}
          {hasNext && (
            <button onClick={() => onNavigate(resources[index + 1])}
              className="absolute right-4 top-1/2 z-20 flex h-11 w-11 -translate-y-1/2 items-center justify-center rounded-full bg-overlay/8 text-white/60 backdrop-blur-sm transition-all hover:bg-overlay/15 hover:text-white"
              title="Next (→)">
              <ChevronRight size={22} />
            </button>
          )}

          {/* Content renderer */}
          <div className="flex flex-1 items-center justify-center p-6 pt-20 pb-14">
            <AnimatePresence mode="wait">
              <motion.div key={r.id}
                initial={{ opacity: 0, scale: 0.97 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0 }}
                transition={{ duration: 0.15 }}
                className="flex h-full w-full items-center justify-center">
                {isImage && (
                  <img src={raw} alt={r.name} className="max-h-full max-w-full rounded-xl object-contain shadow-2xl" />
                )}
                {isVideo && (
                  <video src={raw} controls autoPlay className="max-h-full max-w-full rounded-xl shadow-2xl" />
                )}
                {isAudio && (
                  <div className="flex flex-col items-center gap-6">
                    <div className="flex h-32 w-32 items-center justify-center rounded-3xl bg-gradient-to-br from-accent/20 to-purple/20">
                      <FileAudio size={56} className="text-accent" />
                    </div>
                    <div className="text-sm font-medium text-white/80">{r.name}</div>
                    <audio src={raw} controls className="w-80" />
                  </div>
                )}
                {isPdf && (
                  <iframe src={raw} title={r.name} className="h-full w-full rounded-xl border-0 bg-white shadow-2xl" />
                )}
                {isText && <TextViewer url={raw} />}
                {isYouTube && <YouTubeEmbed url={r.url || ''} title={r.name} />}
                {r.kind === 'link' && !isYouTube && (
                  <div className="flex flex-col items-center gap-5 text-center">
                    <div className="flex h-28 w-28 items-center justify-center rounded-3xl bg-overlay/5">
                      <RTypeIcon rtype={r.rtype} size={52} />
                    </div>
                    <div>
                      <div className="mb-1 text-lg font-semibold text-white">{r.name}</div>
                      <div className="max-w-md break-all text-[13px] text-white/40">{r.url}</div>
                    </div>
                    <a href={r.url || '#'} target="_blank" rel="noreferrer"
                      className="flex items-center gap-2 rounded-xl bg-accent px-6 py-2.5 text-sm font-medium text-white transition-colors hover:bg-accent/90">
                      <ExternalLink size={15} />
                      Open {r.source === 'drive' ? 'in Google Drive' : r.source === 'github' ? 'on GitHub' : 'Link'}
                    </a>
                  </div>
                )}
                {hasFallback && (
                  <div className="flex flex-col items-center gap-5 text-center">
                    <div className="flex h-28 w-28 items-center justify-center rounded-3xl bg-overlay/5">
                      <RTypeIcon rtype={r.rtype} size={52} />
                    </div>
                    <div>
                      <div className="mb-1 text-lg font-semibold text-white">{r.name}</div>
                      <div className="text-[13px] text-white/40">No inline preview for .{r.ext || 'this type'}</div>
                    </div>
                    <a href={raw} download={r.name}
                      className="flex items-center gap-2 rounded-xl bg-overlay/10 px-6 py-2.5 text-sm font-medium text-white transition-colors hover:bg-overlay/15">
                      <Download size={15} /> Download ({fmtBytes(r.size_bytes)})
                    </a>
                  </div>
                )}
              </motion.div>
            </AnimatePresence>
          </div>

          {/* Bottom counter */}
          {resources.length > 1 && (
            <div className="absolute inset-x-0 bottom-0 z-20 flex items-center justify-center bg-gradient-to-t from-black/60 to-transparent py-3">
              <span className="rounded-full bg-overlay/10 px-3 py-1 text-[11px] text-white/50 backdrop-blur-sm">
                {index + 1} of {resources.length}
              </span>
            </div>
          )}
        </div>

        {/* ── Details sidebar ── */}
        <AnimatePresence>
          {showInfo && (
            <motion.aside initial={{ x: 320, opacity: 0 }} animate={{ x: 0, opacity: 1 }} exit={{ x: 320, opacity: 0 }}
              transition={{ type: 'spring', stiffness: 400, damping: 35 }}
              className="flex w-80 shrink-0 flex-col border-l border-overlay/8 bg-panel">
              <div className="border-b border-overlay/8 px-5 py-4">
                <div className="mb-0.5 flex items-center justify-between">
                  <span className="text-[10px] font-semibold uppercase tracking-wider text-muted">Name</span>
                  <button onClick={() => { setRenameVal(r.name); setRenaming(s => !s) }} title="Rename"
                    className="text-muted transition-colors hover:text-accent"><Pencil size={12} /></button>
                </div>
                {renaming ? (
                  <input autoFocus value={renameVal} onChange={e => setRenameVal(e.target.value)}
                    onFocus={e => e.target.select()}
                    onKeyDown={e => {
                      if (e.key === 'Enter' && renameVal.trim()) { onRename(renameVal.trim()); setRenaming(false) }
                      if (e.key === 'Escape') setRenaming(false)
                    }}
                    onBlur={() => setRenaming(false)}
                    className="w-full rounded-lg border border-accent bg-surface px-2.5 py-1.5 text-sm text-heading outline-none" />
                ) : (
                  <div className="break-words text-sm font-medium text-heading">{r.name}</div>
                )}
              </div>

              <div className="min-h-0 flex-1 space-y-5 overflow-y-auto p-5">
                {/* Properties */}
                <div className="space-y-2">
                  <div className="text-[10px] font-semibold uppercase tracking-wider text-muted">Properties</div>
                  <div className="space-y-1.5 text-[12px]">
                    <div className="flex justify-between gap-2"><span className="text-muted">Type</span><span className="text-right text-text">{r.rtype}{r.ext ? ` · .${r.ext}` : ''}</span></div>
                    <div className="flex justify-between gap-2"><span className="text-muted">Source</span><span className="text-right capitalize text-text">{r.source}</span></div>
                    {r.kind === 'file' && <div className="flex justify-between gap-2"><span className="text-muted">Size</span><span className="text-right text-text">{fmtBytes(r.size_bytes)}</span></div>}
                    <div className="flex justify-between gap-2"><span className="text-muted">Added</span><span className="text-right text-text">{fmtAgo(r.created_at)}</span></div>
                    <div className="flex justify-between gap-2"><span className="text-muted">By</span><span className="text-right text-text">{r.created_by}</span></div>
                  </div>
                </div>

                {r.has_text && (
                  <div className="rounded-lg bg-accent/8 px-3 py-2 text-[11px] leading-relaxed text-accent">
                    Text extracted — TOBI can search &amp; summarize this resource in chat.
                  </div>
                )}

                {/* Tags */}
                <div>
                  <div className="mb-2 flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider text-muted">
                    <Tag size={10} /> Tags
                  </div>
                  <div className="flex flex-wrap items-center gap-1.5">
                    {r.tags.map(t => (
                      <span key={t} className="group/tag flex items-center gap-1 rounded-full bg-overlay/5 px-2 py-0.5 text-[11px] text-muted">
                        #{t}
                        <button onClick={() => onTags(r.tags.filter(x => x !== t))}
                          className="opacity-0 transition-opacity group-hover/tag:opacity-100"><X size={9} /></button>
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
                      placeholder="+ tag" className="w-20 border-b border-border bg-transparent py-0.5 text-[11px] text-text outline-none focus:border-accent" />
                  </div>
                </div>

                {/* Actions */}
                {r.kind === 'file' && (
                  <a href={raw} download={r.name}
                    className="flex items-center justify-center gap-2 rounded-xl border border-border bg-surface px-3 py-2.5 text-[13px] text-text transition-colors hover:border-accent/40 hover:text-accent">
                    <Download size={14} /> Download ({fmtBytes(r.size_bytes)})
                  </a>
                )}
                {r.kind === 'link' && (
                  <a href={r.url || '#'} target="_blank" rel="noreferrer"
                    className={`flex items-center justify-center gap-2 rounded-xl px-3 py-2.5 text-[13px] font-medium text-white transition-colors ${isYouTube ? 'bg-[#ff0033] hover:bg-[#ff0033]/90' : 'bg-accent hover:bg-accent/90'}`}>
                    {isYouTube ? <Youtube size={14} /> : <ExternalLink size={14} />}
                    {isYouTube ? 'Watch on YouTube' : 'Open link'}
                  </a>
                )}
              </div>
            </motion.aside>
          )}
        </AnimatePresence>
      </motion.div>
    </motion.div>
  )
}

function TextViewer({ url }: { url: string }) {
  const [text, setText] = useState<string | null>(null)
  useEffect(() => {
    let live = true
    setText(null)
    fetch(url).then(r => r.text()).then(t => { if (live) setText(t) }).catch(() => { if (live) setText(null) })
    return () => { live = false }
  }, [url])

  if (text == null) return (
    <div className="flex items-center gap-2 text-sm text-white/50">
      <Loader2 size={15} className="animate-spin" /> Loading…
    </div>
  )
  const lines = text.split('\n').length
  return (
    <div className="flex h-full w-full max-w-4xl flex-col overflow-hidden rounded-xl border border-overlay/8 bg-panel shadow-2xl">
      <div className="flex items-center justify-between border-b border-overlay/8 px-4 py-2 text-[11px] text-muted">
        <span>Text preview</span>
        <span>{lines.toLocaleString()} lines · {(text.length / 1024).toFixed(1)} KB</span>
      </div>
      <pre className="min-h-0 flex-1 overflow-auto whitespace-pre-wrap p-4 font-mono text-[12px] leading-relaxed text-text">
        {text}
      </pre>
    </div>
  )
}

function AddLinkModal({ onClose, onAdd }: { onClose: () => void; onAdd: (url: string) => Promise<void> }) {
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

// ── 3-dot card menu (for link-type resources) ────────────────────────────────
function CardMenu({ resource, onRename, onDelete }: {
  resource: PMResource; onRename: () => void; onDelete: () => void
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const { toast } = useToast()

  useEffect(() => {
    if (!open) return
    const onDoc = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false) }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [open])

  const copyLink = () => {
    navigator.clipboard?.writeText(resource.url || '').then(() => toast({ kind: 'success', title: 'Link copied' })).catch(() => {})
    setOpen(false)
  }

  return (
    <div className="absolute right-2 top-2 z-30" ref={ref}>
      <button onClick={e => { e.stopPropagation(); setOpen(o => !o) }}
        className="rounded-md bg-black/50 p-1 text-white/70 backdrop-blur-sm transition-colors hover:bg-black/70 hover:text-white">
        <MoreVertical size={14} />
      </button>
      <AnimatePresence>
        {open && (
          <motion.div initial={{ opacity: 0, scale: 0.95, y: -4 }} animate={{ opacity: 1, scale: 1, y: 0 }} exit={{ opacity: 0, scale: 0.95 }}
            transition={{ duration: 0.12 }}
            className="absolute right-0 top-full mt-1 w-40 overflow-hidden rounded-xl border border-border bg-surface py-1 shadow-2xl backdrop-blur-xl">
            <button onClick={e => { e.stopPropagation(); copyLink() }}
              className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-[12px] text-text hover:bg-bg/60">
              <Copy size={13} className="text-muted" /> Copy link
            </button>
            <button onClick={e => { e.stopPropagation(); setOpen(false); onRename() }}
              className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-[12px] text-text hover:bg-bg/60">
              <Pencil size={13} className="text-muted" /> Rename
            </button>
            <button onClick={e => { e.stopPropagation(); setOpen(false); onDelete() }}
              className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-[12px] text-danger hover:bg-danger/10">
              <Trash2 size={13} /> Delete
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

function ListCardMenu({ resource, onRename, onDelete }: {
  resource: PMResource; onRename: () => void; onDelete: () => void
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const { toast } = useToast()

  useEffect(() => {
    if (!open) return
    const onDoc = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false) }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [open])

  const copyLink = () => {
    navigator.clipboard?.writeText(resource.url || '').then(() => toast({ kind: 'success', title: 'Link copied' })).catch(() => {})
    setOpen(false)
  }

  return (
    <div className="relative shrink-0" ref={ref}>
      <button onClick={e => { e.stopPropagation(); setOpen(o => !o) }}
        className="text-muted opacity-0 transition-opacity hover:text-text group-hover:opacity-100">
        <MoreVertical size={14} />
      </button>
      <AnimatePresence>
        {open && (
          <motion.div initial={{ opacity: 0, scale: 0.95, y: -4 }} animate={{ opacity: 1, scale: 1, y: 0 }} exit={{ opacity: 0, scale: 0.95 }}
            transition={{ duration: 0.12 }}
            className="absolute right-0 top-full z-50 mt-1 w-40 overflow-hidden rounded-xl border border-border bg-surface py-1 shadow-2xl backdrop-blur-xl">
            <button onClick={e => { e.stopPropagation(); copyLink() }}
              className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-[12px] text-text hover:bg-bg/60">
              <Copy size={13} className="text-muted" /> Copy link
            </button>
            <button onClick={e => { e.stopPropagation(); setOpen(false); onRename() }}
              className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-[12px] text-text hover:bg-bg/60">
              <Pencil size={13} className="text-muted" /> Rename
            </button>
            <button onClick={e => { e.stopPropagation(); setOpen(false); onDelete() }}
              className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-[12px] text-danger hover:bg-danger/10">
              <Trash2 size={13} /> Delete
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

// ── Add Resource modal (upload + link combined) ──────────────────────────────
function AddResourceModal({ onClose, onUpload, onAddLink }: {
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

function YouTubeEmbed({ url, title }: { url: string; title: string }) {
  const vid = ytId(url)
  const [playing, setPlaying] = useState(false)
  const [hover, setHover] = useState(false)

  if (!vid) return null

  return (
    <div className="flex w-full max-w-5xl flex-col items-center gap-5">
      {/* Player / thumbnail */}
      <div className="relative w-full max-w-4xl overflow-hidden rounded-xl bg-black shadow-2xl"
        style={{ aspectRatio: '16 / 9' }}>
        {playing ? (
          <iframe
            src={`https://www.youtube.com/embed/${vid}?autoplay=1&rel=0`}
            title={title}
            className="h-full w-full"
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
            allowFullScreen />
        ) : (
          <button onClick={() => setPlaying(true)} onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}
            className="group relative h-full w-full cursor-pointer">
            <img
              src={`https://i.ytimg.com/vi/${vid}/maxresdefault.jpg`}
              onError={e => { (e.target as HTMLImageElement).src = `https://i.ytimg.com/vi/${vid}/hqdefault.jpg` }}
              alt={title}
              className="h-full w-full object-cover" />
            {/* Gradient overlay */}
            <div
              className={`absolute inset-0 bg-gradient-to-t from-black/60 via-transparent to-black/10 transition-opacity duration-300 ${hover ? 'opacity-100' : 'opacity-70'}`} />
            {/* Play button */}
            <div className="absolute inset-0 flex items-center justify-center">
              <div
                className={`flex h-14 w-20 items-center justify-center rounded-2xl shadow-2xl transition-all duration-200 ${hover ? 'scale-110 bg-[#ff0033]' : 'bg-[#ff0033]/90'}`}>
                <svg viewBox="0 0 24 24" fill="white" className="ml-1 h-7 w-7">
                  <path d="M8 5v14l11-7z" />
                </svg>
              </div>
            </div>
          </button>
        )}
      </div>

      {/* Title + open link */}
      <div className="w-full max-w-4xl space-y-1">
        <h3 className="text-lg font-semibold leading-snug text-white">{title}</h3>
        <a href={url} target="_blank" rel="noreferrer"
          className="inline-flex items-center gap-1.5 text-[12px] text-white/40 transition-colors hover:text-red-400">
          <Youtube size={13} /> Watch on YouTube
        </a>
      </div>
    </div>
  )
}

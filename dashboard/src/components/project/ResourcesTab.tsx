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

import { RTYPE_ICON, RTypeIcon, ytId } from './resourceHelpers'
import { FolderNameModal, ConfirmFolderDelete, ConfirmResourceDelete, AddLinkModal, AddResourceModal } from './ResourceModals'
import { PreviewModal, TextViewer, YouTubeEmbed } from './ResourcePreview'
import { CardMenu, ListCardMenu } from './ResourceCardMenus'
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


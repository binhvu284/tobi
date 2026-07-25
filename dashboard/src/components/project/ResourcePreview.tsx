// Resource preview modal + inline viewers, extracted from ResourcesTab.tsx.
import { useEffect, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Info, Trash2, X, ChevronLeft, ChevronRight, FileAudio, ExternalLink,
  Download, Pencil, Tag, Youtube, Loader2,
} from 'lucide-react'
import { pmResourceRawUrl, type PMResource } from '../../api.pm'
import { fmtAgo, fmtBytes } from './shared'
import { RTypeIcon, ytId } from './resourceHelpers'

export function TextViewer({ url }: { url: string }) {
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

export function YouTubeEmbed({ url, title }: { url: string; title: string }) {
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

export function PreviewModal({ projectId, resource, resources, onClose, onNavigate, onDelete, onRename, onTags }: {
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

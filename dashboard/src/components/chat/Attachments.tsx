import { useEffect, useMemo, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { FileText, FileType2, X, Expand, Download, Paperclip, ChevronLeft } from 'lucide-react'
import { attachmentUrl, type StoredAttachment } from '../../api.chat'

/**
 * What the owner attached: shown in his own message, and collected in a session files panel.
 *
 * Attachments used to live for exactly one request. The browser read the file into a data URL,
 * `core/attachments.py` decoded it for the vision model, and the bytes were dropped. All that
 * survived on the message was the literal text "📎×1", so a completed turn (which refetches the
 * message list from the server) or a restart left nothing to look at.
 *
 * They are now rows in `chat_attachments` with the bytes content-addressed on disk beside the
 * database, and everything here renders from `/api/chat/attachments/{id}`. Nothing carries
 * base64 in component state, so a session with twenty screenshots stays as cheap to load as one
 * with none.
 */

/** The tag the backend appends to stored message text. Display strips it. */
export const ATTACH_TAG = /\s*📎×(\d+)\s*$/

export function attachCount(content: string): number {
  const m = content.match(ATTACH_TAG)
  return m ? Number(m[1]) : 0
}

export function stripAttachTag(content: string): string {
  return content.replace(ATTACH_TAG, '')
}

export const isImage = (a: StoredAttachment) => a.kind === 'image' || a.mime.startsWith('image/')

export function prettyBytes(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${Math.round(n / 1024)} KB`
  return `${(n / (1024 * 1024)).toFixed(1)} MB`
}

function FileGlyph({ a, size = 12 }: { a: StoredAttachment; size?: number }) {
  return a.mime === 'application/pdf' ? <FileType2 size={size} /> : <FileText size={size} />
}

/** Thumbnails and file chips for one message. */
export function AttachmentStrip({ items, pendingCount, onOpen }: {
  items: StoredAttachment[]
  /** Shown only while a turn is in flight, before the server has stored anything yet. */
  pendingCount?: number
  onOpen: (a: StoredAttachment) => void
}) {
  if (!items.length) {
    if (!pendingCount) return null
    return (
      <div className="mt-1.5 flex justify-end">
        <span className="flex items-center gap-1.5 rounded-lg border border-border bg-bg/50 px-2 py-1 text-[11px] text-muted">
          <Paperclip size={11} />
          Sending {pendingCount} file{pendingCount === 1 ? '' : 's'}
        </span>
      </div>
    )
  }
  const images = items.filter(isImage)
  const files = items.filter(a => !isImage(a))
  return (
    <div className="mt-1.5 flex flex-col items-end gap-1.5">
      {images.length > 0 && (
        <div className="flex flex-wrap justify-end gap-1.5">
          {images.map(a => (
            <button
              key={a.id} type="button" onClick={() => onOpen(a)}
              title={`Open ${a.name}`} aria-label={`Open ${a.name} full screen`}
              className="att-thumb"
            >
              <img src={attachmentUrl(a.id)} alt={a.name} loading="lazy" />
              <span className="att-thumb-veil" aria-hidden><Expand size={15} /></span>
            </button>
          ))}
        </div>
      )}
      {files.length > 0 && (
        <div className="flex flex-wrap justify-end gap-1.5">
          {files.map(a => (
            <a
              key={a.id} href={attachmentUrl(a.id, true)} title={`Download ${a.name}`}
              className="flex max-w-[230px] items-center gap-1.5 rounded-lg border border-border bg-bg/50 px-2 py-1 text-[11px] text-muted transition-colors hover:border-accent/50 hover:text-accent"
            >
              <FileGlyph a={a} />
              <span className="truncate">{a.name}</span>
              <span className="shrink-0 text-muted/60">{prettyBytes(a.bytes)}</span>
            </a>
          ))}
        </div>
      )}
    </div>
  )
}

/**
 * Everything sent in this session, in a rail that tucks away.
 *
 * Codex, Claude and Gemini all keep sent files reachable outside the transcript, because
 * scrolling back through a long conversation to find one screenshot is the wrong job for a
 * message list. Collapsed it is a single tab with a count; expanded it is a grid of thumbnails.
 */
export function SessionFiles({ items, collapsed, onToggle, onOpen }: {
  items: StoredAttachment[]
  collapsed: boolean
  onToggle: () => void
  onOpen: (a: StoredAttachment) => void
}) {
  const images = useMemo(() => items.filter(isImage), [items])
  const files = useMemo(() => items.filter(a => !isImage(a)), [items])
  if (!items.length) return null

  if (collapsed) {
    return (
      <button
        type="button" onClick={onToggle}
        aria-expanded={false}
        title={`${items.length} file${items.length === 1 ? '' : 's'} in this session`}
        className="sf-tab"
      >
        <Paperclip size={13} />
        <span className="sf-tab-count">{items.length}</span>
      </button>
    )
  }

  return (
    <motion.aside
      initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -10 }}
      transition={{ duration: 0.22, ease: [0.16, 1, 0.3, 1] }}
      className="sf-panel"
      aria-label="Files in this session"
    >
      <div className="mb-2 flex items-center gap-2">
        <Paperclip size={13} className="text-muted" />
        <span className="text-[11px] font-medium uppercase tracking-[0.12em] text-muted">
          Session files
        </span>
        <span className="ml-auto text-[10px] text-muted/60">{items.length}</span>
        <button
          type="button" onClick={onToggle} aria-expanded aria-label="Collapse session files"
          className="rounded p-0.5 text-muted transition-colors hover:text-accent"
        >
          <ChevronLeft size={14} />
        </button>
      </div>

      <div className="sf-scroll">
        {images.length > 0 && (
          <div className="grid grid-cols-2 gap-1.5">
            {images.map(a => (
              <button
                key={a.id} type="button" onClick={() => onOpen(a)}
                title={`${a.name} · ${prettyBytes(a.bytes)}`}
                aria-label={`Open ${a.name} full screen`}
                className="sf-cell"
              >
                <img src={attachmentUrl(a.id)} alt={a.name} loading="lazy" />
                <span className="att-thumb-veil" aria-hidden><Expand size={14} /></span>
              </button>
            ))}
          </div>
        )}
        {files.length > 0 && (
          <div className={`flex flex-col gap-1 ${images.length ? 'mt-2 border-t border-border/60 pt-2' : ''}`}>
            {files.map(a => (
              <a
                key={a.id} href={attachmentUrl(a.id, true)} title={`Download ${a.name}`}
                className="flex items-center gap-1.5 rounded px-1 py-1 text-[11px] text-muted transition-colors hover:text-accent"
              >
                <FileGlyph a={a} />
                <span className="truncate">{a.name}</span>
                <span className="ml-auto shrink-0 text-muted/60">{prettyBytes(a.bytes)}</span>
              </a>
            ))}
          </div>
        )}
      </div>
    </motion.aside>
  )
}

/** Full-screen view of one attached image. Esc or a click outside closes it. */
export function ImageLightbox({ attachment, onClose }: {
  attachment: StoredAttachment | null
  onClose: () => void
}) {
  const closeRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (!attachment) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    const prev = document.body.style.overflow      // the page behind must not scroll
    document.body.style.overflow = 'hidden'
    closeRef.current?.focus()
    return () => {
      window.removeEventListener('keydown', onKey)
      document.body.style.overflow = prev
    }
  }, [attachment, onClose])

  return (
    <AnimatePresence>
      {attachment && (
        <motion.div
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
          transition={{ duration: 0.16 }}
          className="att-overlay" role="dialog" aria-modal="true" aria-label={attachment.name}
          onClick={onClose}
        >
          <div className="att-actions" onClick={e => e.stopPropagation()}>
            <a href={attachmentUrl(attachment.id, true)} className="att-btn" title="Download" aria-label="Download image">
              <Download size={16} />
            </a>
            <button ref={closeRef} type="button" onClick={onClose} className="att-btn" aria-label="Close image">
              <X size={18} />
            </button>
          </div>
          <motion.img
            key={attachment.id}
            src={attachmentUrl(attachment.id)}
            alt={attachment.name}
            initial={{ opacity: 0, scale: 0.97 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.98 }}
            transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
            className="att-full"
            onClick={e => e.stopPropagation()}
          />
          <span className="att-caption">
            {attachment.name}
            <span className="text-muted/60"> · {prettyBytes(attachment.bytes)}</span>
          </span>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
